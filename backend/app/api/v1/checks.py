"""Check endpoints (Phase 8) - the same request/response format the phone app already uses.

POST   /api/v1/check/sms        check one SMS (from the phone listener or the manual check screen)
POST   /api/v1/check/link       check a single link
GET    /api/v1/history?page=1   the signed-in user's past checks, newest first (20 per page)
DELETE /api/v1/history/{id}     delete one of the user's checks
POST   /api/v1/feedback         "Wrong result?" - stored for review (Phase 10)

Only masked text is stored (no phone numbers, OTPs, names...)."""
from __future__ import annotations

from datetime import datetime, timezone

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from ...auth import get_current_user
from ...checks.pipeline import run_check
from ...checks.owner_decision import config as owner_config
from ...checks.sender_trust import SenderFacts
from ...checks.sources import source_name
from ...checks.textprep import extract_urls, mask_pii
from ...checks.memcache import save_later
from ...db import Check, Feedback, Profile, get_db, new_id

router = APIRouter(tags=["checks"])
PAGE_SIZE = 20


class SmsCheckIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    sender: str = Field(default="", max_length=128)
    source_app: str = Field(default="", max_length=128)
    source: Literal["sms", "notification", "manual"] = "manual"
    # sender trust, worked out on the phone (contacts never leave it); None = unknown
    sender_in_contacts: bool | None = None
    sender_seen_before: int | None = Field(default=None, ge=0, le=1_000_000)


class LinkCheckIn(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class FeedbackIn(BaseModel):
    check_id: str | None = None
    text: str = Field(default="", max_length=5000)
    correct_label: Literal["ham", "spam", "scam"]
    note: str = Field(default="", max_length=1000)


def _owner_fields(c: Check) -> dict:
    """B6: the owner's output from a saved check - label holds the risk class, reasons the warnings."""
    classes = {k.id: k.label for k in owner_config().classes}
    if c.label not in classes:
        return {"risk_class": None, "risk_label": None, "owner_result": None}
    warnings = [r.get("text", "") for r in (c.reasons or []) if not str(r.get("code", "")).startswith(("RISK_", "NOT_"))]
    reason = ", ".join(w[:1].lower() + w[1:] for w in warnings) or owner_config().no_warning_reason
    return {"risk_class": c.label, "risk_label": classes[c.label],
            "owner_result": {"Probability": f"{c.score}% ({reason[:1].upper() + reason[1:]})", "Class": classes[c.label]}}


def _public(c: Check) -> dict:
    return _owner_fields(c) | {
        "check_id": c.id, "verdict": c.verdict, "score": c.score, "label": c.label,
        "probabilities": c.probabilities, "not_sure": c.not_sure, "reasons": c.reasons,
        "suggestion": c.suggestion, "links": c.links, "checks_skipped": c.checks_skipped,
        "model_version": c.model_version, "source": c.source, "sender": c.sender, "text": c.text,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _check_and_save(request: Request, db: Session, user: Profile, text: str, sender: str, source: str,
                    source_app: str = "", facts: SenderFacts | None = None) -> dict:
    result = run_check(text, sender, request.app.state.checkers, source=source_name(source, source_app),
                       sender_facts=facts)
    settings = request.app.state.settings
    row = Check(
        id=new_id(), created_at=datetime.now(timezone.utc),  # set here: the phone gets them before the row is saved
        user_id=user.uid, source=source, source_app=source_app[:128], sender=mask_pii(sender)[:128],
        text=result["masked_text"] if settings.store_message_text else "",
        verdict=result["verdict"], score=result["score"], label=result["label"], not_sure=result["not_sure"],
        probabilities=result["probabilities"], reasons=result["reasons"], links=result["links"],
        suggestion=result["suggestion"], checks_skipped=result["checks_skipped"],
        model_version=result["model_version"],
        option_set_version=f"{result['prompt_version']}/{result['scoring_version']}",
        timings_ms=result["timings_ms"],
    )
    answer = _public(row) | {"scam_type": result["scam_type"]}
    sessions = request.app.state.sessionmaker

    def save() -> None:
        try:
            with sessions() as s:
                s.add(row)
                s.commit()
        except OperationalError:  # the database connection dropped (Supabase pooler) - retry once on a fresh one
            with sessions() as retry:
                retry.add(row)
                retry.commit()

    # Speed: the phone gets its answer first; the row (history, reports, dashboard) is saved right after.
    # Supabase is far away, so saving first cost the phone ~0.3-1 s on every check.
    if settings.save_checks_in_background:
        save_later(save)
    else:
        save()
    return answer


# Plain `def` endpoints: FastAPI runs them in a worker thread, so a slow check never blocks others.
@router.post("/check/sms")
def check_sms(body: SmsCheckIn, request: Request, user: Profile = Depends(get_current_user), db: Session = Depends(get_db)):
    """Check one SMS. Answers within ~5 s; slow parts are skipped and listed in checks_skipped."""
    facts = SenderFacts(body.sender_in_contacts, body.sender_seen_before)
    return _check_and_save(request, db, user, body.text, body.sender, body.source, body.source_app, facts)


@router.post("/check/link")
def check_link(body: LinkCheckIn, request: Request, user: Profile = Depends(get_current_user), db: Session = Depends(get_db)):
    if not extract_urls(body.url):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That does not look like a valid link.")
    return _check_and_save(request, db, user, body.url, "", "link")


@router.get("/history")
def history(page: int = 1, user: Profile = Depends(get_current_user), db: Session = Depends(get_db)):
    page = max(1, page)
    total = db.scalar(select(func.count()).select_from(Check).where(Check.user_id == user.uid)) or 0
    rows = db.scalars(select(Check).where(Check.user_id == user.uid).order_by(Check.created_at.desc())
                      .offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)).all()
    return {"page": page, "total": total, "has_next": page * PAGE_SIZE < total, "results": [_public(c) for c in rows]}


@router.delete("/history/{check_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_check(check_id: str, user: Profile = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(Check, check_id)
    if row is None or row.user_id != user.uid:  # someone else's check looks exactly like a missing one
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    db.delete(row)
    db.commit()


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
def feedback(body: FeedbackIn, user: Profile = Depends(get_current_user), db: Session = Depends(get_db)):
    check = None
    if body.check_id:
        check = db.get(Check, body.check_id)
        if check is None or check.user_id != user.uid:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Check not found.")
    text = check.text if check else mask_pii(body.text)
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Give a check_id or the message text.")
    fb = Feedback(user_id=user.uid, check_id=check.id if check else None, text=text,
                  correct_label=body.correct_label, note=body.note)
    db.add(fb)
    db.commit()
    return {"id": fb.id, "status": fb.status}
