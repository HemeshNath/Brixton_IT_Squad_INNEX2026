"""Web admin panel sign-in (Phase 10A): admin ID + password, roles, lockout, cookie sessions, audit log.

- Passwords are stored only as scrypt hashes (Python standard library, salted, memory-hard).
- Sign-in sets an HTTP-only, SameSite=Strict cookie holding a random token; only its sha256 is stored.
- A session ends after `admin_idle_minutes` without activity, or on sign-out.
- After `admin_max_failed_logins` wrong passwords the account is locked for `admin_lock_minutes`.
- Requests that change something must carry the header "X-Admin-Request: 1" (blocks cross-site form posts).
- Roles: owner > admin > reviewer (reviewer: reports and the known-scam memory only). The app's Google sign-in never opens the admin panel."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import delete
from sqlalchemy.orm import Session

from .db import AdminSession, AdminUser, AuditLog, get_db

COOKIE = "checkscam_admin"
CSRF_HEADER = "X-Admin-Request"
ROLES = ("reviewer", "admin", "owner")  # lowest -> highest
MIN_PASSWORD = 10
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}


# ---- passwords ----

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, dklen=32, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        kind, salt_b64, digest_b64 = stored.split("$")
        if kind != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode("utf-8"), salt=base64.b64decode(salt_b64), dklen=32, **_SCRYPT)
        return hmac.compare_digest(digest, base64.b64decode(digest_b64))
    except (ValueError, TypeError):
        return False


_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))  # unknown IDs take as long as wrong passwords


def password_problem(password: str) -> str | None:
    """Why a new password is not allowed, or None."""
    if len(password) < MIN_PASSWORD:
        return f"Password must be at least {MIN_PASSWORD} characters."
    if password.lower() == password or password.upper() == password or not any(c.isdigit() for c in password):
        return "Use upper and lower case letters and at least one number."
    return None


def normalize_username(username: str) -> str:
    return username.strip().lower()


# ---- helpers ----

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite gives back naive datetimes; treat them as UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def client_ip(request: Request) -> str:
    return (request.client.host if request.client else "")[:64]


def audit(db: Session, request: Request | None, username: str, action: str, **detail) -> None:
    db.add(AuditLog(admin_username=username[:64], action=action[:64], detail=detail,
                    ip=client_ip(request) if request else "local"))
    db.commit()


# ---- sign-in / sign-out ----

class LoginError(Exception):
    def __init__(self, message: str, status_code: int = status.HTTP_401_UNAUTHORIZED):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def login(db: Session, request: Request, username: str, password: str) -> tuple[AdminUser, str]:
    """Checks ID + password. Returns (account, new session token) or raises LoginError."""
    settings = request.app.state.settings
    name = normalize_username(username)
    user = db.query(AdminUser).filter(AdminUser.username == name).one_or_none()
    now = _now()
    if user is None or not user.active:
        verify_password(password, _DUMMY_HASH)
        audit(db, request, name, "login_failed", reason="unknown or inactive account")
        raise LoginError("Wrong admin ID or password.")
    locked = _aware(user.locked_until)
    if locked and locked > now:
        audit(db, request, name, "login_blocked", reason="account locked")
        minutes = max(1, round((locked - now).total_seconds() / 60))
        raise LoginError(f"Too many wrong tries. Try again in {minutes} minute(s).", status.HTTP_423_LOCKED)
    if not verify_password(password, user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= settings.admin_max_failed_logins:
            user.locked_until = now + timedelta(minutes=settings.admin_lock_minutes)
            user.failed_logins = 0
        db.commit()
        audit(db, request, name, "login_failed", reason="wrong password")
        raise LoginError("Wrong admin ID or password.")
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    token = secrets.token_urlsafe(32)
    db.add(AdminSession(token_hash=_token_hash(token), admin_id=user.id, created_at=now, last_seen_at=now))
    db.commit()
    audit(db, request, name, "login")
    return user, token


def logout(db: Session, token: str) -> None:
    db.execute(delete(AdminSession).where(AdminSession.token_hash == _token_hash(token)))
    db.commit()


def end_all_sessions(db: Session, admin_id: int, keep_token: str | None = None) -> None:
    q = delete(AdminSession).where(AdminSession.admin_id == admin_id)
    if keep_token:
        q = q.where(AdminSession.token_hash != _token_hash(keep_token))
    db.execute(q)
    db.commit()


# ---- request dependencies ----

def current_admin(request: Request, db: Session = Depends(get_db)) -> AdminUser:
    """The signed-in admin (cookie session), or 401. Refreshes the idle timer."""
    token = request.cookies.get(COOKIE, "")
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Admin sign-in required.")
    session = db.get(AdminSession, _token_hash(token))
    now = _now()
    idle = timedelta(minutes=request.app.state.settings.admin_idle_minutes)
    if session is None or _aware(session.last_seen_at) + idle < now:
        if session is not None:
            db.delete(session)
            db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Signed out. Please sign in again.")
    user = db.get(AdminUser, session.admin_id)
    if user is None or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Admin sign-in required.")
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(CSRF_HEADER) != "1":
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing {CSRF_HEADER} header.")
    session.last_seen_at = now
    db.commit()
    request.state.admin_token = token
    return user


def require_role(minimum: str):
    """Dependency: the signed-in admin must have at least this role (reviewer < admin < owner)."""
    need = ROLES.index(minimum)

    def check(user: AdminUser = Depends(current_admin)) -> AdminUser:
        if user.role not in ROLES or ROLES.index(user.role) < need:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Needs the {minimum} role.")
        return user

    return check
