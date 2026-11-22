"""Web admin panel API (Phase 10, 10A). Signed in with admin ID + password (cookie), never with the app's Google sign-in.

Sign-in
POST /api/v1/admin/auth/login            {"username", "password"} -> sets the session cookie
POST /api/v1/admin/auth/logout
GET  /api/v1/admin/auth/me               the signed-in admin
POST /api/v1/admin/auth/password         {"current_password", "new_password"}; other sessions are signed out

Admin accounts (owner only)
GET  /api/v1/admin/accounts
POST /api/v1/admin/accounts              {"username", "password", "role"}
POST /api/v1/admin/accounts/{id}         {"role"?, "active"?, "password"?}

Audit log (admin+)
GET  /api/v1/admin/audit?page=1

Reports and known-scam memory (reviewer+; dataset export admin+)
GET  /api/v1/admin/reports?status=pending&page=1
POST /api/v1/admin/reports/{id}          {"action": "approve" | "reject", "category": ""}
GET  /api/v1/admin/known-scams?page=1&search=
GET  /api/v1/admin/dataset.csv

Every change sends the header "X-Admin-Request: 1". All message texts here are already masked."""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...admin_auth import (COOKIE, CSRF_HEADER, LoginError, audit, current_admin, end_all_sessions,
                           hash_password, login, logout, normalize_username, password_problem, require_role,
                           verify_password)
from ...db import AdminUser, AuditLog, Feedback, KnownScam, get_db

router = APIRouter(prefix="/admin", tags=["admin"])
PAGE_SIZE = 20
Role = Literal["owner", "admin", "reviewer"]


def _page(db: Session, query, count_query, page: int, convert) -> dict:
    page = max(1, page)
    total = db.scalar(count_query) or 0
    rows = db.scalars(query.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)).all()
    return {"page": page, "total": total, "has_next": page * PAGE_SIZE < total, "results": [convert(r) for r in rows]}


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _account(a: AdminUser) -> dict:
    return {"id": a.id, "username": a.username, "role": a.role, "active": a.active,
            "last_login_at": _iso(a.last_login_at), "created_at": _iso(a.created_at)}


# ---------------- sign-in ----------------

class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class PasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


@router.post("/auth/login")
def admin_login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    if request.headers.get(CSRF_HEADER) != "1":
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing {CSRF_HEADER} header.")
    try:
        user, token = login(db, request, body.username, body.password)
    except LoginError as exc:
        raise HTTPException(exc.status_code, exc.message) from None
    settings = request.app.state.settings
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict", secure=settings.admin_cookie_secure,
                        path="/", max_age=12 * 3600)
    return _account(user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def admin_logout(request: Request, response: Response, db: Session = Depends(get_db),
                 user: AdminUser = Depends(current_admin)):
    logout(db, request.state.admin_token)
    audit(db, request, user.username, "logout")
    response.delete_cookie(COOKIE, path="/")


@router.get("/auth/me")
def admin_me(user: AdminUser = Depends(current_admin)):
    return _account(user)


@router.post("/auth/password")
def change_password(body: PasswordIn, request: Request, db: Session = Depends(get_db),
                    user: AdminUser = Depends(current_admin)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is wrong.")
    if problem := password_problem(body.new_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)
    user.password_hash = hash_password(body.new_password)
    db.commit()
    end_all_sessions(db, user.id, keep_token=request.state.admin_token)
    audit(db, request, user.username, "password_changed")
    return {"ok": True}


# ---------------- admin accounts (owner) ----------------

class AccountIn(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=1, max_length=256)
    role: Role = "reviewer"


class AccountUpdate(BaseModel):
    role: Role | None = None
    active: bool | None = None
    password: str | None = Field(default=None, max_length=256)


@router.get("/accounts")
def list_accounts(db: Session = Depends(get_db), _: AdminUser = Depends(require_role("owner"))):
    return [_account(a) for a in db.scalars(select(AdminUser).order_by(AdminUser.id))]


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
def create_account(body: AccountIn, request: Request, db: Session = Depends(get_db),
                   owner: AdminUser = Depends(require_role("owner"))):
    name = normalize_username(body.username)
    if db.scalar(select(AdminUser).where(AdminUser.username == name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "That admin ID already exists.")
    if problem := password_problem(body.password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)
    acc = AdminUser(username=name, password_hash=hash_password(body.password), role=body.role)
    db.add(acc)
    db.commit()
    audit(db, request, owner.username, "account_created", account=name, role=body.role)
    return _account(acc)


@router.post("/accounts/{account_id}")
def update_account(account_id: int, body: AccountUpdate, request: Request, db: Session = Depends(get_db),
                   owner: AdminUser = Depends(require_role("owner"))):
    acc = db.get(AdminUser, account_id)
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Admin account not found.")
    if acc.id == owner.id and (body.role not in (None, "owner") or body.active is False):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot remove your own owner access.")
    changes = {}
    if body.role is not None:
        acc.role = changes["role"] = body.role
    if body.active is not None:
        acc.active = changes["active"] = body.active
    if body.password:
        if problem := password_problem(body.password):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)
        acc.password_hash = hash_password(body.password)
        acc.failed_logins, acc.locked_until = 0, None
        changes["password"] = "reset"
    db.commit()
    if body.active is False or body.password:
        end_all_sessions(db, acc.id)
    audit(db, request, owner.username, "account_updated", account=acc.username, **changes)
    return _account(acc)


# ---------------- audit log ----------------

@router.get("/audit")
def audit_log(page: int = 1, db: Session = Depends(get_db), _: AdminUser = Depends(require_role("admin"))):
    return _page(db, select(AuditLog).order_by(AuditLog.id.desc()), select(func.count()).select_from(AuditLog), page,
                 lambda a: {"id": a.id, "admin": a.admin_username, "action": a.action, "detail": a.detail,
                            "ip": a.ip, "created_at": _iso(a.created_at)})


# ---------------- reports and known-scam memory ----------------

class ReviewIn(BaseModel):
    action: Literal["approve", "reject"]
    category: str = Field(default="", max_length=64)  # e.g. "fake KYC"; stored with a known scam


def _report(f: Feedback) -> dict:
    return {"id": f.id, "check_id": f.check_id, "text": f.text, "correct_label": f.correct_label, "note": f.note,
            "status": f.status, "created_at": _iso(f.created_at), "reviewed_at": _iso(f.reviewed_at)}


@router.get("/reports")
def list_reports(status_: Literal["pending", "approved", "rejected"] = Query("pending", alias="status"), page: int = 1,
                 db: Session = Depends(get_db), _: AdminUser = Depends(require_role("reviewer"))):
    where = Feedback.status == status_
    counts = dict(db.execute(select(Feedback.status, func.count()).group_by(Feedback.status)).all())
    return _page(db, select(Feedback).where(where).order_by(Feedback.created_at, Feedback.id),
                 select(func.count()).select_from(Feedback).where(where), page, _report) | {
        "counts": {s: int(counts.get(s, 0)) for s in ("pending", "approved", "rejected")}}


@router.post("/reports/{report_id}")
def review_report(report_id: int, body: ReviewIn, request: Request, db: Session = Depends(get_db),
                  admin: AdminUser = Depends(require_role("reviewer"))):
    fb = db.get(Feedback, report_id)
    if fb is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found.")
    if fb.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Report was already {fb.status}.")
    fb.status = "approved" if body.action == "approve" else "rejected"
    fb.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    known_id = None
    if fb.status == "approved" and fb.correct_label == "scam":
        known_id = request.app.state.checkers.known.add(db, fb.text, body.category, source="feedback")
    audit(db, request, admin.username, f"report_{fb.status}", report=fb.id, label=fb.correct_label,
          known_scam=known_id)
    return _report(fb) | {"known_scam_id": known_id}


@router.get("/known-scams")
def list_known_scams(page: int = 1, search: str = Query("", max_length=100), db: Session = Depends(get_db),
                     _: AdminUser = Depends(require_role("reviewer"))):
    q, c = select(KnownScam), select(func.count()).select_from(KnownScam)
    if search.strip():
        like = f"%{search.strip().lower()}%"
        cond = func.lower(KnownScam.text).like(like) | func.lower(KnownScam.category).like(like)
        q, c = q.where(cond), c.where(cond)
    return _page(db, q.order_by(KnownScam.id.desc()), c, page,
                 lambda k: {"id": k.id, "text": k.text, "category": k.category, "source": k.source,
                            "created_at": _iso(k.created_at)})


@router.get("/dataset.csv")
def dataset(request: Request, db: Session = Depends(get_db), admin: AdminUser = Depends(require_role("admin"))):
    """Approved reports in the same format as eval/data/*.csv, for tuning (L1) and training (L2)."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["text", "label", "lang", "source"])
    count = 0
    for f in db.scalars(select(Feedback).where(Feedback.status == "approved").order_by(Feedback.id)):
        lang = "ne" if re.search(r"[ऀ-ॿ]", f.text) else "en"
        w.writerow([f.text, f.correct_label, lang, "feedback"])
        count += 1
    audit(db, request, admin.username, "dataset_exported", rows=count)
    return Response(out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=checkscam_feedback.csv"})

