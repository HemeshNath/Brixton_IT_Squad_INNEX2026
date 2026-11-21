"""GET /api/v1/me – the signed-in user's profile (uid, email, plan, number of checks)."""
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...auth import get_current_user
from ...db import Check, Profile, get_db

router = APIRouter(tags=["account"])


class MeOut(BaseModel):
    uid: str
    email: str
    plan: str
    created_at: datetime
    checks_total: int


@router.get("/me", response_model=MeOut)
def me(user: Profile = Depends(get_current_user), db: Session = Depends(get_db)) -> MeOut:
    """The signed-in user's profile."""
    total = db.scalar(select(func.count()).select_from(Check).where(Check.user_id == user.uid)) or 0
    return MeOut(uid=user.uid, email=user.email, plan=user.plan, created_at=user.created_at, checks_total=total)
