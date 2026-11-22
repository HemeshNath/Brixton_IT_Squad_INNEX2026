"""Live system settings in the admin panel (Phase 10A step A4). Admin+.

GET  /api/v1/admin/settings                  current version, its values, the defaults and the field list
POST /api/v1/admin/settings                  {"data": {...}, "note": ""} -> new version, live at once
GET  /api/v1/admin/settings/history?page=1   saved versions, newest first, with what changed
POST /api/v1/admin/settings/restore/{n}      undo: saves version n again as a new version (0 = defaults)"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ... import live_settings as ls
from ...admin_auth import audit, require_role
from ...db import AdminUser, SettingsVersion, get_db

router = APIRouter(prefix="/admin", tags=["admin"])
PAGE_SIZE = 20


class SettingsIn(BaseModel):
    data: dict
    note: str = Field(default="", max_length=200)


def _changes(old: dict, new: dict) -> list[dict]:
    """What differs between two settings versions, as readable rows."""
    out = []
    for f in ls.FIELDS:
        a, b = (old.get(f.group) or {}).get(f.key), (new.get(f.group) or {}).get(f.key)
        if a != b:
            out.append({"group": f.group, "key": f.key, "label": f.label, "old": a, "new": b})
    return out


def _version(row: SettingsVersion | None) -> dict:
    if row is None:
        return {"number": 0, "note": "Defaults (.env)", "created_by": "", "created_at": None,
                "restored_from": None}
    return {"number": row.number, "note": row.note, "created_by": row.created_by,
            "created_at": row.created_at.isoformat() if row.created_at else None, "restored_from": row.restored_from}


def _current_data(request: Request, row: SettingsVersion | None) -> dict:
    settings = request.app.state.settings
    return ls.validate(ls.with_defaults(row.data, settings))[0] if row is not None else ls.defaults(settings)


def _save(db: Session, request: Request, admin: AdminUser, data: dict, note: str, restored_from: int | None = None) -> dict:
    clean, problems = ls.validate(data)
    if problems:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, " ".join(problems))
    current = ls.latest(db)
    old = _current_data(request, current)
    changes = _changes(old, clean)
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing changed.")
    number = (current.number if current else 0) + 1
    row = SettingsVersion(number=number, data=clean, note=note.strip()[:200], created_by=admin.username,
                          restored_from=restored_from)
    db.add(row)
    db.commit()
    ls.apply(request.app, clean, number)
    audit(db, request, admin.username, "settings_restored" if restored_from is not None else "settings_saved",
          version=number, restored_from=restored_from,
          changes=[f"{c['label']}: {c['old']} → {c['new']}" for c in changes][:20])
    return {"version": _version(row), "data": clean, "changes": changes}


@router.get("/settings")
def get_settings(request: Request, db: Session = Depends(get_db), _: AdminUser = Depends(require_role("admin"))):
    row = ls.latest(db)
    return {
        "version": _version(row),
        "live_version": getattr(request.app.state, "settings_version", 0),
        "scoring_version": ls.version_label(row.number if row else 0),
        "data": _current_data(request, row),
        "defaults": ls.defaults(request.app.state.settings),
        "fields": [f.as_dict() for f in ls.FIELDS],
        "groups": ls.GROUPS,
    }


@router.post("/settings")
def save_settings(body: SettingsIn, request: Request, db: Session = Depends(get_db),
                  admin: AdminUser = Depends(require_role("admin"))):
    return _save(db, request, admin, body.data, body.note)


@router.get("/settings/history")
def history(request: Request, page: int = 1, db: Session = Depends(get_db),
            _: AdminUser = Depends(require_role("admin"))):
    """Versions newest first; each shows what it changed compared with the version before it."""
    page = max(1, page)
    rows = db.scalars(select(SettingsVersion).order_by(SettingsVersion.number.desc())).all()  # a few hundred at most
    settings = request.app.state.settings
    items = [(_version(r), ls.with_defaults(r.data, settings)) for r in rows] + [(_version(None), ls.defaults(request.app.state.settings))]
    results = [v | {"changes": _changes(items[i + 1][1], data) if i + 1 < len(items) else []}
               for i, (v, data) in enumerate(items)]
    start = (page - 1) * PAGE_SIZE
    return {"page": page, "total": len(results), "has_next": start + PAGE_SIZE < len(results),
            "results": results[start:start + PAGE_SIZE]}


@router.post("/settings/restore/{number}")
def restore(number: int, request: Request, db: Session = Depends(get_db),
            admin: AdminUser = Depends(require_role("admin"))):
    if number == 0:
        data = ls.defaults(request.app.state.settings)
    else:
        row = db.get(SettingsVersion, number)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found.")
        data = ls.with_defaults(row.data, request.app.state.settings)
    return _save(db, request, admin, data, f"Undo: back to version {number}", restored_from=number)
