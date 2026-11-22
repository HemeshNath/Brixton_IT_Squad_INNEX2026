"""Data sets in the admin panel (Phase 10A step A6): editable lists, known-scam memory, CSV exports.

Lists (view: reviewer+, change: admin+)
GET    /api/v1/admin/lists                          the four lists with entry counts
GET    /api/v1/admin/lists/{list}?search=           entries: built-in (trusted.json) and added here
POST   /api/v1/admin/lists/{list}                   {"value", "label"} add (or switch a built-in back on)
DELETE /api/v1/admin/lists/{list}?value=            remove an added entry / switch off a built-in one
Known-scam memory (reviewer+; export admin+)
POST   /api/v1/admin/known-scams                    {"text", "category"} add a scam by hand (masked first)
DELETE /api/v1/admin/known-scams/{id}
GET    /api/v1/admin/known-scams.csv
Every change is live for the next check and written to the audit log."""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ... import data_lists as dl
from ...admin_auth import audit, require_role
from ...checks.known_scams import DUPLICATE, grams
from ...checks.textprep import mask_pii
from ...db import AdminUser, KnownScam, ListEntry, get_db

router = APIRouter(prefix="/admin", tags=["admin"])


def _list(name: str) -> dl.ListInfo:
    if name not in dl.LISTS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown list.")
    return dl.LISTS[name]


def _entries(db: Session, name: str) -> list[dict]:
    rows = {r.value: r for r in db.scalars(select(ListEntry).where(ListEntry.list == name))}
    out = []
    for value, label in dl.builtin(name).items():
        r = rows.get(value)
        out.append({"value": value, "label": (r.label if r and r.active and r.label else label), "source": "built-in",
                    "active": not (r is not None and not r.active), "changed_by": r.created_by if r else None})
    builtin = dl.builtin(name)
    for value, r in rows.items():
        if value not in builtin:
            out.append({"value": value, "label": r.label, "source": "panel", "active": r.active,
                        "changed_by": r.created_by, "created_at": r.created_at.isoformat() if r.created_at else None})
    return sorted(out, key=lambda e: (e["source"] != "panel", e["value"]))


@router.get("/lists")
def lists_overview(db: Session = Depends(get_db), _: AdminUser = Depends(require_role("reviewer"))):
    rows = dl.rows(db)
    return [{"name": i.name, "title": i.title, "value_label": i.value_label, "label_label": i.label_label,
             "help": i.help, "count": len(dl.effective(rows, i.name)),
             "added": sum(1 for r in rows if r.list == i.name and r.active and r.value not in dl.builtin(i.name)),
             "switched_off": sum(1 for r in rows if r.list == i.name and not r.active)} for i in dl.LISTS.values()]


@router.get("/lists/{name}")
def list_entries(name: str, search: str = Query("", max_length=100), db: Session = Depends(get_db),
                 _: AdminUser = Depends(require_role("reviewer"))):
    _list(name)
    entries = _entries(db, name)
    q = search.strip().lower()
    if q:
        entries = [e for e in entries if q in e["value"] or q in (e["label"] or "").lower()]
    return {"list": name, "total": len(entries), "results": entries}


class EntryIn(BaseModel):
    value: str = Field(min_length=1, max_length=300)
    label: str = Field(default="", max_length=200)


@router.post("/lists/{name}", status_code=status.HTTP_201_CREATED)
def add_entry(name: str, body: EntryIn, request: Request, db: Session = Depends(get_db),
              admin: AdminUser = Depends(require_role("admin"))):
    info = _list(name)
    value, problem = dl.normalize(name, body.value)
    if problem:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)
    label = body.label.strip()
    row = db.scalar(select(ListEntry).where(ListEntry.list == name, ListEntry.value == value))
    in_builtin = value in dl.builtin(name)
    if row is not None and row.active or (row is None and in_builtin):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{value} is already on the list.")
    if row is not None and not row.active:  # a switched-off built-in: switch it back on
        db.delete(row)
        action = "list_entry_restored"
    else:
        db.add(ListEntry(list=name, value=value, label=label, created_by=admin.username))
        action = "list_entry_added"
    db.commit()
    dl.apply(request.app)
    audit(db, request, admin.username, action, list=name, value=value, label=label)
    warning = None
    if name == "blocked_domain" and value in dl.effective(dl.rows(db), "trusted_domain"):
        warning = f"{value} is also an official site; the block list wins."
    if name == "trusted_domain" and value in dl.effective(dl.rows(db), "blocked_domain"):
        warning = f"{value} is also blocked; the block list wins."
    return {"list": name, "value": value, "label": label, "title": info.title, "warning": warning}


@router.delete("/lists/{name}")
def remove_entry(name: str, request: Request, value: str = Query(min_length=1, max_length=300),
                 db: Session = Depends(get_db), admin: AdminUser = Depends(require_role("admin"))):
    _list(name)
    v, _ = dl.normalize(name, value)
    row = db.scalar(select(ListEntry).where(ListEntry.list == name, ListEntry.value == v))
    if v in dl.builtin(name):
        if row is not None and not row.active:
            raise HTTPException(status.HTTP_409_CONFLICT, f"{v} is already switched off.")
        if row is not None:
            row.active, row.created_by = False, admin.username
        else:
            db.add(ListEntry(list=name, value=v, active=False, created_by=admin.username))
        action = "list_entry_switched_off"
    elif row is not None:
        db.delete(row)
        action = "list_entry_removed"
    else:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{v} is not on the list.")
    db.commit()
    dl.apply(request.app)
    audit(db, request, admin.username, action, list=name, value=v)
    return {"list": name, "value": v, "action": action}


# ---------------- known-scam memory ----------------

class KnownScamIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    category: str = Field(default="", max_length=64)


@router.post("/known-scams", status_code=status.HTTP_201_CREATED)
def add_known_scam(body: KnownScamIn, request: Request, db: Session = Depends(get_db),
                   admin: AdminUser = Depends(require_role("reviewer"))):
    memory = request.app.state.checkers.known
    masked = mask_pii(body.text)
    if grams(masked) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Too little text left after removing links and numbers to compare messages.")
    hit = memory.best_match(masked)
    if hit and hit.similarity >= DUPLICATE:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Already in the memory (#{hit.id}, {hit.similarity:.0%} alike).")
    new_id = memory.add(db, masked, body.category.strip(), source="panel")
    audit(db, request, admin.username, "known_scam_added", known_scam=new_id, category=body.category.strip())
    return {"id": new_id, "text": masked, "category": body.category.strip()}


@router.delete("/known-scams/{scam_id}")
def delete_known_scam(scam_id: int, request: Request, db: Session = Depends(get_db),
                      admin: AdminUser = Depends(require_role("reviewer"))):
    row = db.get(KnownScam, scam_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    db.delete(row)
    db.commit()
    request.app.state.checkers.known.reload()
    audit(db, request, admin.username, "known_scam_removed", known_scam=scam_id)
    return {"id": scam_id, "removed": True}


@router.get("/known-scams.csv")
def known_scams_csv(request: Request, db: Session = Depends(get_db), admin: AdminUser = Depends(require_role("admin"))):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["text", "label", "category", "source", "created_at"])
    n = 0
    for k in db.scalars(select(KnownScam).order_by(KnownScam.id)):
        w.writerow([k.text, "scam", k.category, k.source, k.created_at.isoformat() if k.created_at else ""])
        n += 1
    audit(db, request, admin.username, "known_scams_exported", rows=n)
    return Response(out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=checkscam_known_scams.csv"})
