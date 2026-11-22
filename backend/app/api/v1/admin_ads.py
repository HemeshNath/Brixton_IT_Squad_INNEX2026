"""Ads (Phase 10A step A9).

Admin+ (panel):
  GET    /api/v1/admin/ads                 all ads with status, views, clicks
  POST   /api/v1/admin/ads                 create  {title, body, link, language, starts_at, ends_at, active, image?}
  PUT    /api/v1/admin/ads/{id}            change (a changed link is checked again)
  POST   /api/v1/admin/ads/{id}/recheck    check the link again
  DELETE /api/v1/admin/ads/{id}
Phone (signed-in users):
  GET    /api/v1/ads/active?lang=ne        ads showing now in that language
  POST   /api/v1/ads/{id}/event            {"kind": "view" | "click"} -> counts (no personal data)
  GET    /api/v1/ads/{id}/image            the ad's picture (public)

An ad can only be switched on when its link passed the safety check: a real http(s) link, not on the block list, no
AlienVault OTX threat reports, and a domain at least 30 days old (WHOIS). "image" is base64 PNG/JPEG, at most 500 KB."""
from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...admin_auth import audit, require_role
from ...auth import get_current_user
from ...checks.domain_age import DomainAgeUnavailable
from ...checks.links import analyze_url
from ...checks.otx import OtxUnavailable
from ...checks.textprep import extract_urls
from ...db import Ad, AdminUser, Profile, get_db

admin_router = APIRouter(prefix="/admin", tags=["admin"])
router = APIRouter(tags=["ads"])

MAX_IMAGE_BYTES = 500_000
MIN_DOMAIN_AGE_DAYS = 30
IMAGE_TYPES = {b"\x89PNG": "image/png", b"\xff\xd8\xff": "image/jpeg"}


class AdIn(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    body: str = Field(default="", max_length=200)
    link: str = Field(min_length=4, max_length=500)
    language: Literal["en", "ne", "all"] = "all"
    starts_at: datetime
    ends_at: datetime
    active: bool = False
    image: str | None = None  # base64; "" removes the picture, None keeps it (on change)


class EventIn(BaseModel):
    kind: Literal["view", "click"]


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def check_link(link: str, checkers) -> dict:
    """The ad link's safety check: {"ok", "problems", "notes", "domain", "checked_at"}."""
    problems, notes = [], []
    urls = extract_urls(link)
    parsed = analyze_url(urls[0]) if urls else None
    if not link.strip().lower().startswith(("http://", "https://")) or parsed is None:
        return {"ok": False, "problems": ["Not a valid web link (it must start with http:// or https://)."],
                "notes": [], "domain": None, "checked_at": datetime.now(timezone.utc).isoformat()}
    domain = parsed.domain
    if checkers.blocklist is not None and checkers.blocklist.domain_blocked(parsed.host or domain):
        problems.append("The site is on CheckScam's block list.")
    if not link.lower().startswith("https://"):
        notes.append("The link is not secure (no HTTPS).")
    otx = checkers.otx
    if otx is None:
        notes.append("AlienVault OTX is not set up - not checked.")
    else:
        try:
            counts = otx.counts("domain", domain, wait_seconds=8)
            if counts.pulses and not counts.whitelisted:
                problems.append(f"AlienVault OTX has {counts.pulses} threat report(s) for {domain}.")
        except OtxUnavailable as exc:
            notes.append(f"AlienVault OTX did not answer ({exc.reason}) - not checked.")
    ages = checkers.ages
    if ages is None:
        notes.append("WHOIS is switched off - domain age not checked.")
    else:
        try:
            age = ages.lookup(domain).age_days()
            if age is None:
                notes.append("Domain age is not public - not checked.")
            elif age < MIN_DOMAIN_AGE_DAYS:
                problems.append(f"{domain} was registered only {age} days ago (needs {MIN_DOMAIN_AGE_DAYS}+).")
        except DomainAgeUnavailable as exc:
            notes.append(f"WHOIS did not answer ({exc.reason}) - not checked.")
    return {"ok": not problems, "problems": problems, "notes": notes, "domain": domain,
            "checked_at": datetime.now(timezone.utc).isoformat()}


def _image(data: str) -> tuple[bytes, str]:
    try:
        raw = base64.b64decode(data.split(",", 1)[-1], validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The picture could not be read.") from None
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The picture is too big (at most 500 KB).")
    kind = next((t for magic, t in IMAGE_TYPES.items() if raw.startswith(magic)), None)
    if kind is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The picture must be a PNG or JPEG.")
    return raw, kind


def _status(ad: Ad, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    if not ad.active:
        return "off"
    if now < _aware(ad.starts_at):
        return "scheduled"
    if now > _aware(ad.ends_at):
        return "ended"
    return "showing"


def _row(ad: Ad) -> dict:
    return {
        "id": ad.id, "title": ad.title, "body": ad.body, "link": ad.link, "language": ad.language,
        "starts_at": _aware(ad.starts_at).isoformat(), "ends_at": _aware(ad.ends_at).isoformat(),
        "active": ad.active, "status": _status(ad), "has_image": ad.image is not None,
        "image_url": f"/api/v1/ads/{ad.id}/image" if ad.image is not None else None,
        "link_check": ad.link_check or {}, "views": ad.views, "clicks": ad.clicks,
        "click_rate": round(ad.clicks / ad.views, 3) if ad.views else 0.0,
        "created_by": ad.created_by, "updated_at": _aware(ad.updated_at).isoformat() if ad.updated_at else None,
    }


def _apply(ad: Ad, body: AdIn, request: Request, link_changed: bool) -> None:
    if _aware(body.ends_at) <= _aware(body.starts_at):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The end date must be after the start date.")
    ad.title, ad.body, ad.link, ad.language = body.title.strip(), body.body.strip(), body.link.strip(), body.language
    ad.starts_at, ad.ends_at = _aware(body.starts_at), _aware(body.ends_at)
    if body.image is not None:
        if body.image == "":
            ad.image, ad.image_type = None, ""
        else:
            ad.image, ad.image_type = _image(body.image)
    if link_changed or not ad.link_check:
        ad.link_check = check_link(ad.link, request.app.state.checkers)
    if body.active and not (ad.link_check or {}).get("ok"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This ad cannot be switched on: "
                            + " ".join((ad.link_check or {}).get("problems", ["the link did not pass the check."])))
    ad.active = body.active


def _get(db: Session, ad_id: int) -> Ad:
    ad = db.get(Ad, ad_id)
    if ad is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ad not found.")
    return ad


@admin_router.get("/ads")
def list_ads(db: Session = Depends(get_db), _: AdminUser = Depends(require_role("admin"))):
    return [_row(a) for a in db.scalars(select(Ad).order_by(Ad.id.desc())).all()]


@admin_router.post("/ads", status_code=status.HTTP_201_CREATED)
def create_ad(body: AdIn, request: Request, db: Session = Depends(get_db),
              admin: AdminUser = Depends(require_role("admin"))):
    ad = Ad(created_by=admin.username, views=0, clicks=0, link_check={})
    _apply(ad, body, request, link_changed=True)
    db.add(ad)
    db.commit()
    audit(db, request, admin.username, "ad_created", ad_id=ad.id, title=ad.title, link=ad.link, active=ad.active)
    return _row(ad)


@admin_router.put("/ads/{ad_id}")
def change_ad(ad_id: int, body: AdIn, request: Request, db: Session = Depends(get_db),
              admin: AdminUser = Depends(require_role("admin"))):
    ad = _get(db, ad_id)
    _apply(ad, body, request, link_changed=body.link.strip() != ad.link)
    db.commit()
    audit(db, request, admin.username, "ad_changed", ad_id=ad.id, title=ad.title, active=ad.active)
    return _row(ad)


@admin_router.post("/ads/{ad_id}/recheck")
def recheck_ad(ad_id: int, request: Request, db: Session = Depends(get_db),
               admin: AdminUser = Depends(require_role("admin"))):
    ad = _get(db, ad_id)
    ad.link_check = check_link(ad.link, request.app.state.checkers)
    if not ad.link_check["ok"]:
        ad.active = False  # a link that turned bad switches the ad off
    db.commit()
    audit(db, request, admin.username, "ad_link_rechecked", ad_id=ad.id, ok=ad.link_check["ok"])
    return _row(ad)


@admin_router.delete("/ads/{ad_id}")
def delete_ad(ad_id: int, request: Request, db: Session = Depends(get_db),
              admin: AdminUser = Depends(require_role("admin"))):
    ad = _get(db, ad_id)
    db.delete(ad)
    db.commit()
    audit(db, request, admin.username, "ad_deleted", ad_id=ad_id, title=ad.title)
    return {"deleted": ad_id}


# ---------------------------------------------------------------- phone
def showing(db: Session, lang: str) -> list[Ad]:
    now = datetime.now(timezone.utc)
    ads = db.scalars(select(Ad).where(Ad.active.is_(True)).order_by(Ad.id.desc())).all()
    return [a for a in ads if _status(a, now) == "showing" and a.language in ("all", lang)
            and (a.link_check or {}).get("ok")]


@router.get("/ads/active")
def active_ads(lang: Literal["en", "ne"] = "en", db: Session = Depends(get_db),
               _: Profile = Depends(get_current_user)):
    return [{"id": a.id, "title": a.title, "body": a.body, "link": a.link,
             "image_url": f"/api/v1/ads/{a.id}/image" if a.image is not None else None} for a in showing(db, lang)]


@router.post("/ads/{ad_id}/event", status_code=status.HTTP_204_NO_CONTENT)
def ad_event(ad_id: int, body: EventIn, db: Session = Depends(get_db), _: Profile = Depends(get_current_user)):
    ad = db.get(Ad, ad_id)
    if ad is None or _status(ad) != "showing":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ad not found.")
    if body.kind == "view":
        ad.views = (ad.views or 0) + 1
    else:
        ad.clicks = (ad.clicks or 0) + 1
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/ads/{ad_id}/image")
def ad_image(ad_id: int, db: Session = Depends(get_db)):
    ad = db.get(Ad, ad_id)
    if ad is None or ad.image is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No picture.")
    return Response(content=ad.image, media_type=ad.image_type or "image/png",
                    headers={"Cache-Control": "public, max-age=3600"})
