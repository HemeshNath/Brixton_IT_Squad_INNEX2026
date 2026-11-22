"""API keys set from the admin panel (Phase 10A step A5): OTX and WHOIS.

- Keys are stored encrypted (Fernet: AES-128 + HMAC) in the `api_keys` table. The encryption key is SECRETS_KEY
  from .env, or else a random key in backend/.secret_key, created on first use (never sent to GitHub).
- A key is never sent back to the browser: only its last 4 characters.
- A key saved in the panel wins over the same key in .env; deleting it falls back to .env.
- Before a key is saved it is tested with its own provider (OTX: /user/me, WhoisXML API: one lookup).
- Applying a key is live: the OTX and WHOIS clients pick it up without a restart."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from .config import BACKEND_DIR
from .db import ApiKey

log = logging.getLogger("checkscam.keys")
KEY_FILE = BACKEND_DIR / ".secret_key"


@dataclass(frozen=True)
class KeyInfo:
    name: str
    label: str
    env_setting: str  # Settings attribute with the .env value
    help: str


KEYS = {
    "otx": KeyInfo("otx", "AlienVault OTX API key", "otx_api_key",
                   "Free at otx.alienvault.com → Settings → API key. Used for link reputation."),
    "whois": KeyInfo("whois", "WHOIS API key (WhoisXML API)", "whois_api_key",
                     "From whoisxmlapi.com. Optional: without it, free RDAP/WHOIS lookups are used."),
}


# ---- encryption ----

def _fernet(settings) -> Fernet:
    key = (getattr(settings, "secrets_key", "") or "").strip()
    if not key:
        path = Path(getattr(settings, "secret_key_file", "") or KEY_FILE)
        if not path.exists():
            path.write_text(Fernet.generate_key().decode(), encoding="utf-8")
            log.info("Created a new encryption key file for API keys")
        key = path.read_text(encoding="utf-8").strip()
    return Fernet(key.encode())


def encrypt(settings, value: str) -> str:
    return _fernet(settings).encrypt(value.encode()).decode()


def decrypt(settings, token: str) -> str | None:
    try:
        return _fernet(settings).decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        log.warning("A stored API key could not be decrypted (encryption key changed?)")
        return None


def last4(value: str) -> str:
    return value[-4:] if len(value) >= 8 else "••••"


# ---- reading / writing ----

def effective(db: Session, settings, name: str) -> tuple[str, str]:
    """(key value, source) - source is 'panel', '.env' or 'none'."""
    row = db.get(ApiKey, name)
    if row is not None:
        value = decrypt(settings, row.encrypted)
        if value:
            return value, "panel"
    env = (getattr(settings, KEYS[name].env_setting, "") or "").strip()
    return (env, ".env") if env else ("", "none")


def save(db: Session, settings, name: str, value: str, admin: str, tested: bool) -> ApiKey:
    row = db.get(ApiKey, name) or ApiKey(name=name)
    row.encrypted = encrypt(settings, value)
    row.last4 = last4(value)
    row.updated_by = admin
    row.tested_ok = tested
    db.merge(row)
    db.commit()
    return db.get(ApiKey, name)


def remove(db: Session, name: str) -> bool:
    row = db.get(ApiKey, name)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


# ---- testing with the provider ----

def test_key(name: str, value: str, http: httpx.Client | None = None) -> tuple[bool | None, str]:
    """(True = works, False = refused by the provider, None = provider not reachable), message."""
    client = http or httpx.Client(timeout=10)
    try:
        if name == "otx":
            r = client.get("https://otx.alienvault.com/api/v1/user/me", headers={"X-OTX-API-KEY": value})
            if r.status_code == 200:
                return True, "OTX accepted the key."
            if r.status_code in (401, 403):
                return False, "OTX refused this key."
            return None, f"OTX answered {r.status_code}; try again later."
        r = client.get("https://www.whoisxmlapi.com/whoisserver/WhoisService",
                       params={"apiKey": value, "domainName": "google.com", "outputFormat": "JSON"})
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code == 200 and "WhoisRecord" in body:
            return True, "WhoisXML API accepted the key."
        if r.status_code in (401, 403) or "ErrorMessage" in body:
            return False, "WhoisXML API refused this key."
        return None, f"WhoisXML API answered {r.status_code}; try again later."
    except (httpx.HTTPError, ValueError):
        return None, "The provider could not be reached."
    finally:
        if http is None:
            client.close()


# ---- applying ----

def apply(app) -> None:
    """Gives the current keys to the OTX and WHOIS clients (start-up and after every change)."""
    from .checks.otx import OtxClient

    settings = app.state.settings
    checkers = app.state.checkers
    try:
        with app.state.sessionmaker() as db:
            otx_key, _ = effective(db, settings, "otx")
            whois_key, _ = effective(db, settings, "whois")
    except Exception as exc:  # noqa: BLE001 - e.g. table not migrated yet: keep the .env keys
        log.warning("Stored API keys not loaded (%s)", type(exc).__name__)
        otx_key, whois_key = settings.otx_api_key, getattr(settings, "whois_api_key", "")
    if otx_key:
        if checkers.otx is None:
            checkers.otx = OtxClient(otx_key, app.state.sessionmaker, timeout=settings.otx_timeout_seconds,
                                     daily_limit=settings.otx_daily_limit, cache_hours=settings.otx_cache_hours,
                                     save_in_background=True)
        else:
            checkers.otx.api_key = otx_key
    else:
        checkers.otx = None
    if checkers.ages is not None:
        checkers.ages.whois_api_key = whois_key or ""
