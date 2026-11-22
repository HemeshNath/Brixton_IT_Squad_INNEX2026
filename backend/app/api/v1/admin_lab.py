"""Admin test lab (Phase 10A step A7). Admin+.

POST /api/v1/admin/test-lab   {"text", "sender"?, "source"?: "SMS", "use_link_lookups"?: true}
     runs the normal check with the live settings and returns everything: verdict, score, every reason, MIRA's
     probability for each answer option and each yes/no question (with what MIRA was shown), link facts
     (OTX, domain age, block lists), known-scam match, skipped parts and timings.
     Nothing is saved to any user's history. use_link_lookups=false skips OTX / WHOIS (saves OTX quota)."""
from __future__ import annotations

import dataclasses

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...admin_auth import audit, require_role
from ...checks.pipeline import run_check
from ...checks.sender_trust import SenderFacts
from ...db import AdminUser, get_db

router = APIRouter(prefix="/admin", tags=["admin"])


class LabIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    sender: str = Field(default="", max_length=128)
    source: str = Field(default="SMS", max_length=64)  # readable app name for MIRA's prompt, e.g. "WhatsApp"
    sender_in_contacts: bool | None = None  # sender trust, as the phone would send it (None = unknown)
    sender_seen_before: int | None = Field(default=None, ge=0, le=1_000_000)
    use_link_lookups: bool = True


@router.post("/test-lab")
def test_lab(body: LabIn, request: Request, db: Session = Depends(get_db), admin: AdminUser = Depends(require_role("admin"))):
    checkers = request.app.state.checkers
    if not body.use_link_lookups:
        checkers = dataclasses.replace(checkers, otx=None, ages=None)
    result = run_check(body.text, body.sender, checkers, detail=True, source=body.source.strip() or "SMS",
                       sender_facts=SenderFacts(body.sender_in_contacts, body.sender_seen_before))
    result["settings_version"] = getattr(request.app.state, "settings_version", 0)
    # the audit log notes that a test ran - never the message itself
    audit(db, request, admin.username, "test_lab_run", verdict=result["verdict"], score=result["score"],
          characters=len(body.text), link_lookups=body.use_link_lookups)
    return result
