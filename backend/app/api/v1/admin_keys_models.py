"""API keys and AI model in the admin panel (Phase 10A step A5). Owner only.

GET    /api/v1/admin/keys                    which keys are set (source, last 4 characters) - never the key itself
POST   /api/v1/admin/keys/{name}/test        {"value"} -> asks the provider if the key works (nothing saved)
POST   /api/v1/admin/keys/{name}             {"value", "skip_test"?} -> tests, then saves encrypted; live at once
DELETE /api/v1/admin/keys/{name}             removes the panel key (the .env key is used again, if any)

GET    /api/v1/admin/model                   live version, approved versions, downloaded?, last test of each
POST   /api/v1/admin/model/test/{id}         test run on the data set (background)
GET    /api/v1/admin/model/tests/{test_id}   progress / result of a test run
POST   /api/v1/admin/model/switch/{id}       {"note"} -> load that version and use it (needs a finished test)"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ... import ai_models, api_keys
from ...admin_auth import audit, require_role
from ...db import AdminUser, ApiKey, ModelChoice, ModelTest, get_db

router = APIRouter(prefix="/admin", tags=["admin"])
owner = require_role("owner")


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def _key_name(name: str) -> str:
    if name not in api_keys.KEYS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown key.")
    return name


class KeyIn(BaseModel):
    value: str = Field(min_length=8, max_length=200)
    skip_test: bool = False  # only when the provider cannot be reached


@router.get("/keys")
def list_keys(request: Request, db: Session = Depends(get_db), _: AdminUser = Depends(owner)):
    settings = request.app.state.settings
    out = []
    for name, info in api_keys.KEYS.items():
        value, source = api_keys.effective(db, settings, name)
        row = db.get(ApiKey, name)
        out.append({"name": name, "label": info.label, "help": info.help, "source": source,
                    "last4": api_keys.last4(value) if value else None,
                    "updated_by": row.updated_by if row else None, "updated_at": _iso(row.updated_at) if row else None,
                    "tested_ok": row.tested_ok if row else None})
    return out


@router.post("/keys/{name}/test")
def test_key(name: str, body: KeyIn, request: Request, db: Session = Depends(get_db), admin: AdminUser = Depends(owner)):
    ok, message = api_keys.test_key(_key_name(name), body.value.strip())
    audit(db, request, admin.username, "key_tested", key=name, result={True: "ok", False: "refused", None: "unreachable"}[ok])
    return {"ok": ok, "message": message}


@router.post("/keys/{name}")
def save_key(name: str, body: KeyIn, request: Request, db: Session = Depends(get_db), admin: AdminUser = Depends(owner)):
    value = body.value.strip()
    ok, message = api_keys.test_key(_key_name(name), value)
    if ok is False:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, message)
    if ok is None and not body.skip_test:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, message + " Save anyway only if you are sure the key is right.")
    api_keys.save(db, request.app.state.settings, name, value, admin.username, tested=ok is True)
    api_keys.apply(request.app)
    audit(db, request, admin.username, "key_saved", key=name, last4=api_keys.last4(value), tested=ok is True)
    return {"name": name, "last4": api_keys.last4(value), "tested_ok": ok is True, "message": message}


@router.delete("/keys/{name}")
def delete_key(name: str, request: Request, db: Session = Depends(get_db), admin: AdminUser = Depends(owner)):
    if not api_keys.remove(db, _key_name(name)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No key saved in the panel.")
    api_keys.apply(request.app)
    audit(db, request, admin.username, "key_removed", key=name)
    _, source = api_keys.effective(db, request.app.state.settings, name)
    return {"name": name, "source": source}


# ---------------- AI model ----------------

def _test(t: ModelTest | None) -> dict | None:
    if t is None:
        return None
    return {"id": t.id, "status": t.status, "result": t.result, "started_by": t.started_by,
            "started_at": _iso(t.started_at), "finished_at": _iso(t.finished_at)}


@router.get("/model")
def model_overview(request: Request, db: Session = Depends(get_db), _: AdminUser = Depends(owner)):
    app = request.app
    mira = app.state.mira
    history = db.scalars(select(ModelChoice).order_by(ModelChoice.id.desc()).limit(10)).all()
    return {
        "live": {"version_id": getattr(mira, "version_id", ""), "version": mira.version, "status": mira.status,
                 "load_seconds": mira.load_seconds, "switching_to": getattr(app.state, "switching_to", None)},
        "versions": [v | {"downloaded": ai_models.downloaded(app.state.settings, v),
                          "live": getattr(mira, "version_id", "") == v["id"],
                          "last_test": _test(ai_models.last_test(db, v["id"]))} for v in ai_models.versions()],
        "history": [{"version_id": h.version_id, "chosen_by": h.chosen_by, "note": h.note,
                     "created_at": _iso(h.created_at)} for h in history],
    }


@router.post("/model/test/{version_id}", status_code=status.HTTP_202_ACCEPTED)
def start_test(version_id: str, request: Request, db: Session = Depends(get_db), admin: AdminUser = Depends(owner)):
    try:
        test_id = ai_models.start_test(request.app, version_id, admin.username)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    audit(db, request, admin.username, "model_test_started", version=version_id, test=test_id)
    return {"test_id": test_id}


@router.get("/model/tests/{test_id}")
def get_test(test_id: int, db: Session = Depends(get_db), _: AdminUser = Depends(owner)):
    t = db.get(ModelTest, test_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Test not found.")
    return _test(t)


class SwitchIn(BaseModel):
    note: str = Field(default="", max_length=200)


@router.post("/model/switch/{version_id}", status_code=status.HTTP_202_ACCEPTED)
def switch_model(version_id: str, body: SwitchIn, request: Request, db: Session = Depends(get_db),
                 admin: AdminUser = Depends(owner)):
    try:
        ai_models.switch(request.app, version_id, admin.username, body.note)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    audit(db, request, admin.username, "model_switch_started", version=version_id, note=body.note)
    return {"switching_to": version_id}
