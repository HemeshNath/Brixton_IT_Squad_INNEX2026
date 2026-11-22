"""App control (Phase 10A step A10).

Admin+ (panel):
  GET /api/v1/admin/app-control      the current app settings
  PUT /api/v1/admin/app-control      change them (audit log)
Phone (public - read before sign-in too):
  GET /api/v1/app/config?version=1.0.0
      {"min_version", "latest_version", "update_url", "must_update", "notice", "chat_apps_allowed", "trusted_senders"}

- min_version: older apps show a "please update" screen and stop checking until updated.
- notice: an in-app message on the home screen (e.g. "a new scam is going around"), in English and Nepali.
- chat_apps_allowed: off = the phone stops watching WhatsApp / Viber / Messenger (SMS only).
- trusted_senders: the official sender IDs (trusted.json + admin panel list), so the phone's on-device filter
  matches the server's list instead of its built-in copy."""
from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ... import data_lists
from ...admin_auth import audit, require_role
from ...db import AdminUser, AppConfig, get_db

admin_router = APIRouter(prefix="/admin", tags=["admin"])
router = APIRouter(tags=["app"])

KEY = "app"
VERSION_RE = re.compile(r"^\d+(\.\d+){0,2}$")


class Notice(BaseModel):
    active: bool = False
    level: Literal["info", "warning"] = "info"
    title_en: str = Field(default="", max_length=80)
    text_en: str = Field(default="", max_length=400)
    title_ne: str = Field(default="", max_length=80)
    text_ne: str = Field(default="", max_length=400)


class AppControlIn(BaseModel):
    min_version: str = Field(default="1.0.0", max_length=16)
    latest_version: str = Field(default="1.0.0", max_length=16)
    update_url: str = Field(default="", max_length=500)
    notice: Notice = Notice()
    chat_apps_allowed: bool = True


DEFAULTS = AppControlIn().model_dump()


def version_tuple(v: str) -> tuple[int, int, int]:
    """"1.2" -> (1, 2, 0); "1.0.0+5" -> (1, 0, 0). Bad text -> (0, 0, 0)."""
    core = (v or "").split("+")[0].strip()
    if not VERSION_RE.match(core):
        return (0, 0, 0)
    parts = [int(x) for x in core.split(".")] + [0, 0]
    return (parts[0], parts[1], parts[2])


def current(db: Session) -> dict:
    row = db.get(AppConfig, KEY)
    data = {**DEFAULTS, **(row.data if row else {})}
    data["notice"] = {**DEFAULTS["notice"], **(data.get("notice") or {})}
    return data


@admin_router.get("/app-control")
def get_app_control(db: Session = Depends(get_db), _: AdminUser = Depends(require_role("admin"))):
    row = db.get(AppConfig, KEY)
    return current(db) | {"updated_by": row.updated_by if row else "",
                          "updated_at": row.updated_at.isoformat() if row and row.updated_at else None}


@admin_router.put("/app-control")
def put_app_control(body: AppControlIn, request: Request, db: Session = Depends(get_db),
                    admin: AdminUser = Depends(require_role("admin"))):
    for name in ("min_version", "latest_version"):
        if not VERSION_RE.match(getattr(body, name).strip()):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{name.replace('_', ' ')}: use numbers like 1.2.0.")
    if version_tuple(body.min_version) > version_tuple(body.latest_version):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The minimum version cannot be newer than the latest version.")
    if body.update_url and not body.update_url.startswith(("https://", "http://")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The update link must start with https://.")
    n = body.notice
    if n.active and not ((n.title_en or n.text_en) and (n.title_ne or n.text_ne)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "An active notice needs English and Nepali text.")
    old = current(db)
    data = body.model_dump()
    row = db.get(AppConfig, KEY) or AppConfig(key=KEY)
    row.data, row.updated_by = data, admin.username
    db.merge(row)
    db.commit()
    changed = [k for k in data if data[k] != old.get(k)]
    audit(db, request, admin.username, "app_control_saved", changed=changed)
    return get_app_control(db, admin)


@router.get("/app/config")
def app_config(request: Request, version: str = "", db: Session = Depends(get_db)):
    data = current(db)
    senders = sorted(data_lists.effective(data_lists.rows(db), "trusted_sender"))
    must = bool(version) and version_tuple(version) < version_tuple(data["min_version"])
    return {
        "min_version": data["min_version"], "latest_version": data["latest_version"],
        "update_url": data["update_url"], "must_update": must,
        "notice": data["notice"] if data["notice"]["active"] else None,
        "chat_apps_allowed": data["chat_apps_allowed"], "trusted_senders": senders,
    }
