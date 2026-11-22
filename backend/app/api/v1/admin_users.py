"""App users and their usage (Phase 10A step A3). Admin+.

GET  /api/v1/admin/users?search=&sort=last_seen|checks|joined&page=1
     every app user: email, joined, last seen, checks (total / today / last 7 days), verdict split, blocked, plan
GET  /api/v1/admin/users/{uid}
     one user: the same numbers, checks per day for the last 30 days (Nepal time), sources, last 20 checks
     (time, verdict, score, source - never the message text)
POST /api/v1/admin/users/{uid}   {"blocked"?: bool, "plan"?: "free" | "premium"}
     blocked users get 403 from every app endpoint; every change is in the audit log"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from ...admin_auth import audit, require_role
from ...db import AdminUser, Check, Feedback, Profile, get_db
from .admin_dashboard import _nepal_date, nepal_day_start, utc

router = APIRouter(prefix="/admin", tags=["admin"])
PAGE_SIZE = 25


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


def _stats_query(today: datetime, week: datetime):
    """Per-user check counts (total, today, 7 days, per verdict) as a subquery."""
    return (select(
        Check.user_id.label("uid"),
        func.count().label("total"),
        func.sum(case((Check.created_at >= today, 1), else_=0)).label("today"),
        func.sum(case((Check.created_at >= week, 1), else_=0)).label("week"),
        func.sum(case((Check.verdict == "safe", 1), else_=0)).label("safe"),
        func.sum(case((Check.verdict == "suspicious", 1), else_=0)).label("suspicious"),
        func.sum(case((Check.verdict == "dangerous", 1), else_=0)).label("dangerous"),
        func.sum(case((Check.verdict == "unknown", 1), else_=0)).label("unknown"),  # MIRA gave no answer (B6)
        func.max(Check.created_at).label("last_check"),
    ).group_by(Check.user_id).subquery())


def _user_row(p: Profile, s) -> dict:
    return {
        "uid": p.uid,
        "email": p.email,
        "kind": "development" if p.uid.startswith("dev:") else "google",
        "plan": p.plan,
        "blocked": p.blocked,
        "joined_at": _iso(p.created_at),
        "last_seen_at": _iso(p.last_seen_at),
        "last_check_at": _iso(s.last_check) if s is not None else None,
        "checks": {"total": int(s.total or 0) if s is not None else 0,
                   "today": int(s.today or 0) if s is not None else 0,
                   "week": int(s.week or 0) if s is not None else 0},
        "verdicts": {v: int(getattr(s, v) or 0) if s is not None else 0 for v in ("safe", "suspicious", "dangerous", "unknown")},
    }


@router.get("/users")
def list_users(search: str = Query("", max_length=100), sort: Literal["last_seen", "checks", "joined"] = "last_seen",
               page: int = 1, db: Session = Depends(get_db), _: AdminUser = Depends(require_role("admin"))):
    page = max(1, page)
    now = datetime.now(timezone.utc)
    stats = _stats_query(utc(nepal_day_start(now)), utc(nepal_day_start(now, 6)))
    q = select(Profile, stats).outerjoin(stats, stats.c.uid == Profile.uid)
    if search.strip():
        like = f"%{search.strip().lower()}%"
        q = q.where(or_(func.lower(Profile.email).like(like), func.lower(Profile.uid).like(like)))
    order = {"last_seen": Profile.last_seen_at.desc(), "checks": func.coalesce(stats.c.total, 0).desc(),
             "joined": Profile.created_at.desc()}[sort]
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.execute(q.order_by(order.nulls_last() if sort == "last_seen" else order, Profile.uid)
                      .offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)).all()
    blocked = db.scalar(select(func.count()).select_from(Profile).where(Profile.blocked.is_(True))) or 0
    active_today = db.scalar(select(func.count()).select_from(Profile).where(
        Profile.last_seen_at >= utc(nepal_day_start(now)))) or 0
    return {"page": page, "total": total, "has_next": page * PAGE_SIZE < total,
            "summary": {"users": db.scalar(select(func.count()).select_from(Profile)) or 0,
                        "active_today": active_today, "blocked": blocked},
            "results": [_user_row(r[0], r) for r in rows]}


def _get(db: Session, uid: str) -> Profile:
    p = db.get(Profile, uid)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    return p


@router.get("/users/{uid}")
def user_detail(uid: str, db: Session = Depends(get_db), _: AdminUser = Depends(require_role("admin"))):
    p = _get(db, uid)
    now = datetime.now(timezone.utc)
    stats = _stats_query(utc(nepal_day_start(now)), utc(nepal_day_start(now, 6)))
    s = db.execute(select(stats).where(stats.c.uid == uid)).first()
    start = nepal_day_start(now, 29)
    recent = db.execute(select(Check.created_at, Check.source).where(Check.user_id == uid, Check.created_at >= utc(start))).all()
    per_day = Counter(_nepal_date(r.created_at) for r in recent)
    days = [(start + timedelta(days=i)).date().isoformat() for i in range(30)]
    sources = Counter(src for src in db.scalars(select(Check.source).where(Check.user_id == uid)))
    last = db.execute(select(Check.id, Check.created_at, Check.verdict, Check.score, Check.source, Check.checks_skipped)
                      .where(Check.user_id == uid).order_by(Check.created_at.desc()).limit(20)).all()
    reports = db.scalar(select(func.count()).select_from(Feedback).where(Feedback.user_id == uid)) or 0
    return _user_row(p, s) | {
        "per_day": [{"day": d, "checks": per_day.get(d, 0)} for d in days],
        "sources": dict(sources),
        "reports_sent": reports,
        "last_checks": [{"check_id": r.id, "at": _iso(r.created_at), "verdict": r.verdict, "score": r.score,
                         "source": r.source, "skipped": r.checks_skipped or []} for r in last],
    }


class UserUpdate(BaseModel):
    blocked: bool | None = None
    plan: Literal["free", "premium"] | None = None


@router.post("/users/{uid}")
def update_user(uid: str, body: UserUpdate, request: Request, db: Session = Depends(get_db),
                admin: AdminUser = Depends(require_role("admin"))):
    p = _get(db, uid)
    changes = {}
    if body.blocked is not None and body.blocked != p.blocked:
        p.blocked = changes["blocked"] = body.blocked
    if body.plan is not None and body.plan != p.plan:
        p.plan = changes["plan"] = body.plan
    db.commit()
    if changes:
        action = "user_blocked" if changes.get("blocked") else "user_unblocked" if "blocked" in changes else "user_updated"
        audit(db, request, admin.username, action, user=p.email or p.uid, **changes)
    return {"uid": p.uid, "blocked": p.blocked, "plan": p.plan}

