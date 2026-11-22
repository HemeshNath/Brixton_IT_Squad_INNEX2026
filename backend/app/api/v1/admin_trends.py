"""Scam trends (Phase 10A step A8). Reviewer+.

GET /api/v1/admin/trends?days=7|30
    per day (Nepal time): checks per risk class; totals per class; the most-seen link domains with their average
    and highest risk; risky domains first seen in the period; sources (SMS, WhatsApp, ...); the most common warnings.
Counts and domains only - message texts are never sent."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...admin_auth import require_role
from ...checks.owner_decision import config as owner_config
from ...checks.sources import source_name
from ...db import AdminUser, Check, get_db
from .admin_dashboard import _nepal_date, nepal_day_start, utc

router = APIRouter(prefix="/admin", tags=["admin"])
RISKY_FROM = 61  # CRITICAL RISK and VERY HARMFUL


@router.get("/trends")
def trends(days: int = Query(7, ge=1, le=90), db: Session = Depends(get_db),
           _: AdminUser = Depends(require_role("reviewer"))):
    now = datetime.now(timezone.utc)
    start = nepal_day_start(now, days - 1)
    rows = db.execute(select(Check.created_at, Check.label, Check.score, Check.links, Check.reasons, Check.source,
                             Check.source_app).where(Check.created_at >= utc(start))).all()
    class_ids = [c.id for c in owner_config().classes]
    labels = {c.id: c.label for c in owner_config().classes} | {"unknown": "Not checked"}

    day_names = [(start + timedelta(days=i)).date().isoformat() for i in range(days)]
    per_day = {d: Counter() for d in day_names}
    totals, sources, warnings = Counter(), Counter(), Counter()
    domains: dict[str, dict] = defaultdict(lambda: {"count": 0, "score_sum": 0, "max_score": 0, "first_seen": None})
    for r in rows:
        cls = r.label if r.label in class_ids else "unknown"
        day = _nepal_date(r.created_at)
        if day in per_day:
            per_day[day][cls] += 1
        totals[cls] += 1
        sources[source_name(r.source, r.source_app)] += 1
        for reason in r.reasons or []:
            code = str(reason.get("code", ""))
            if code and not code.startswith(("RISK_", "NOT_")):
                warnings[code] += 1
        for d in {str(l.get("domain", "")).lower() for l in (r.links or []) if l.get("domain")}:
            info = domains[d]
            info["count"] += 1
            info["score_sum"] += int(r.score or 0)
            info["max_score"] = max(info["max_score"], int(r.score or 0))
            seen = r.created_at if r.created_at.tzinfo else r.created_at.replace(tzinfo=timezone.utc)
            info["first_seen"] = min(info["first_seen"], seen) if info["first_seen"] else seen

    def domain_row(name: str, info: dict) -> dict:
        return {"domain": name, "count": info["count"], "avg_score": round(info["score_sum"] / info["count"]),
                "max_score": info["max_score"], "first_seen": info["first_seen"].isoformat()}

    top = sorted(domains.items(), key=lambda kv: (-kv[1]["count"], -kv[1]["max_score"]))[:10]
    newest_risky = sorted(((d, i) for d, i in domains.items() if i["max_score"] >= RISKY_FROM),
                          key=lambda kv: kv[1]["first_seen"], reverse=True)[:10]
    return {
        "days": days,
        "classes": [{"id": c, "label": labels[c]} for c in class_ids + ["unknown"]],
        "per_day": [{"day": d, **{c: per_day[d].get(c, 0) for c in class_ids + ["unknown"]}} for d in day_names],
        "totals": {c: totals.get(c, 0) for c in class_ids + ["unknown"]},
        "checks": len(rows),
        "risky_share": round(sum(totals[c] for c in ("critical", "very_harmful")) / len(rows), 3) if rows else 0.0,
        "top_domains": [domain_row(d, i) for d, i in top],
        "newest_risky_domains": [domain_row(d, i) for d, i in newest_risky],
        "sources": dict(sources.most_common()),
        "warnings": dict(warnings.most_common(10)),
    }
