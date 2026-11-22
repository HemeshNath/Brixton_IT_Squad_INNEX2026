"""Sign-in as a FastAPI dependency.

Production: "Authorization: Bearer <Firebase ID token>", verified with firebase-admin.
Development: "X-Dev-User: <name>" when DEBUG and ALLOW_DEV_AUTH are both on.
The first call of a new user creates their profile (plan = free)."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import Settings
from .db import Profile, get_db

log = logging.getLogger("checkscam.auth")
_firebase_lock = threading.Lock()


class AuthNotConfigured(Exception):
    pass


def _firebase_app(settings: Settings):
    import firebase_admin
    from firebase_admin import credentials

    with _firebase_lock:
        if firebase_admin._apps:
            return firebase_admin.get_app()
        if not settings.firebase_credentials:
            raise AuthNotConfigured("FIREBASE_CREDENTIALS is not set")
        return firebase_admin.initialize_app(credentials.Certificate(settings.firebase_credentials))


def verify_firebase_token(token: str, settings: Settings) -> dict:
    """Returns the decoded token or raises. Separate function so tests can mock it."""
    from firebase_admin import auth

    return auth.verify_id_token(token, app=_firebase_app(settings), check_revoked=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def get_or_create_profile(db: Session, uid: str, email: str) -> Profile:
    profile = db.get(Profile, uid)
    if profile:
        return profile
    try:
        profile = Profile(uid=uid, email=email or "")
        db.add(profile)
        db.commit()
        log.info("Created profile for a new user")
        return profile
    except IntegrityError:  # two first requests at the same time
        db.rollback()
        return db.scalars(select(Profile).where(Profile.uid == uid)).one()


LAST_SEEN_EVERY = timedelta(minutes=5)  # write last_seen_at at most this often per user


def _active(db: Session, profile: Profile) -> Profile:
    """Refuses blocked users (403) and notes when the user was last seen (Phase 10A, admin panel)."""
    if profile.blocked:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your CheckScam account is blocked. Please contact support.")
    now = datetime.now(timezone.utc)
    seen = profile.last_seen_at
    if seen is not None and seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    if seen is None or now - seen > LAST_SEEN_EVERY:
        profile.last_seen_at = now
        db.commit()
    return profile


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Profile:
    settings: Settings = request.app.state.settings

    dev_user = request.headers.get("X-Dev-User", "").strip()
    if dev_user and settings.dev_auth_active:
        name = dev_user[:100]
        return _active(db, get_or_create_profile(db, f"dev:{name}", f"{name}@dev.local"))

    header = request.headers.get("Authorization", "")
    if not header:
        raise _unauthorized("Sign-in required.")
    scheme, _, token = header.partition(" ")
    if scheme != "Bearer" or not token.strip():
        raise _unauthorized("Invalid Authorization header.")

    try:
        decoded = verify_firebase_token(token.strip(), settings)
    except AuthNotConfigured:
        log.error("Firebase is not configured on the server")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Sign-in is not configured on the server.")
    except Exception as exc:  # expired, revoked, wrong project, malformed...
        log.info("Token rejected: %s", type(exc).__name__)
        raise _unauthorized("Invalid or expired sign-in. Please sign in again.")

    uid = decoded.get("uid") or decoded.get("user_id") or decoded.get("sub")
    if not uid:
        raise _unauthorized("Token has no user id.")
    return _active(db, get_or_create_profile(db, uid, decoded.get("email", "")))
