"""Admin review of "Wrong result?" reports and the known-scam memory (Phase 10). Admins only (profiles.is_admin).

GET  /api/v1/admin/reports?status=pending&page=1   reports to review, oldest first (20 per page)
POST /api/v1/admin/reports/{id}                    {"action": "approve" | "reject", "category": ""}
                                                   approved scam reports join the known-scam memory
GET  /api/v1/admin/known-scams?page=1              the memory, newest first
GET  /api/v1/admin/dataset.csv                     approved reports as labelled data (text,label,lang,source)

All texts here are already masked."""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...auth import get_current_user
from ...db import Feedback, KnownScam, Profile, get_db

router = APIRouter(prefix="/admin", tags=["admin"])
PAGE_SIZE = 20


def require_admin(user: Profile = Depends(get_current_user)) -> Profile:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only.")
    return user


class ReviewIn(BaseModel):
    action: Literal["approve", "reject"]
    category: str = Field(default="", max_length=64)  # e.g. "fake KYC"; stored with a known scam


def _report(f: Feedback) -> dict:
    return {"id": f.id, "check_id": f.check_id, "text": f.text, "correct_label": f.correct_label, "note": f.note,
            "status": f.status, "created_at": f.created_at.isoformat() if f.created_at else None,
            "reviewed_at": f.reviewed_at.isoformat() if f.reviewed_at else None}


@router.get("/reports")
def list_reports(status_: Literal["pending", "approved", "rejected"] = Query("pending", alias="status"), page: int = 1,
                 db: Session = Depends(get_db), _: Profile = Depends(require_admin)):
    page = max(1, page)
    where = Feedback.status == status_
    total = db.scalar(select(func.count()).select_from(Feedback).where(where)) or 0
    rows = db.scalars(select(Feedback).where(where).order_by(Feedback.created_at, Feedback.id)
                      .offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)).all()
    return {"page": page, "total": total, "has_next": page * PAGE_SIZE < total, "results": [_report(f) for f in rows]}


@router.post("/reports/{report_id}")
def review_report(report_id: int, body: ReviewIn, request: Request, db: Session = Depends(get_db),
                  _: Profile = Depends(require_admin)):
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
    return _report(fb) | {"known_scam_id": known_id}


@router.get("/known-scams")
def list_known_scams(page: int = 1, db: Session = Depends(get_db), _: Profile = Depends(require_admin)):
    page = max(1, page)
    total = db.scalar(select(func.count()).select_from(KnownScam)) or 0
    rows = db.scalars(select(KnownScam).order_by(KnownScam.id.desc())
                      .offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)).all()
    return {"page": page, "total": total, "has_next": page * PAGE_SIZE < total,
            "results": [{"id": k.id, "text": k.text, "category": k.category, "source": k.source,
                         "created_at": k.created_at.isoformat() if k.created_at else None} for k in rows]}


@router.get("/dataset.csv")
def dataset(db: Session = Depends(get_db), _: Profile = Depends(require_admin)):
    """Approved reports in the same format as eval/data/*.csv, for tuning (L1) and training (L2)."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["text", "label", "lang", "source"])
    for f in db.scalars(select(Feedback).where(Feedback.status == "approved").order_by(Feedback.id)):
        lang = "ne" if re.search(r"[ऀ-ॿ]", f.text) else "en"
        w.writerow([f.text, f.correct_label, lang, "feedback"])
    return Response(out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=checkscam_feedback.csv"})
