"""Admin dashboard (Phase 10A step A2): one call with everything the panel's home page shows. Reviewer+.

GET /api/v1/admin/dashboard

- services: server, MIRA, database (Supabase), OTX, WHOIS - each "ok" | "warning" | "down" | "off" with a short note
- otx quota: lookups today / daily limit
- today (Nepal time): checks, verdict split, active users, average and p90 check time, skipped parts
- last 7 days: checks per day
- slowest 5 checks today, recent server errors, totals (users, known scams, pending reports)
No external service is called here (the OTX quota is never spent by the dashboard)."""
from __future__ import annotations

import time
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ...admin_auth import require_role
from ...db import AdminUser, Check, DomainCache, Feedback, KnownScam, OtxCache, Profile, get_db
from ...checks.owner_decision import config as owner_config
from ...checks.pipeline import TRAINED_DEFAULTS

SLOW_CHECK_SECONDS = 60  # a check slower than this counts as slow on the dashboard

router = APIRouter(prefix="/admin", tags=["admin"])
NEPAL = timezone(timedelta(hours=5, minutes=45))


def nepal_day_start(now: datetime | None = None, days_ago: int = 0) -> datetime:
    """Midnight in Nepal (as an aware datetime), `days_ago` days back."""
    local = (now or datetime.now(timezone.utc)).astimezone(NEPAL)
    return local.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)


def utc(dt: datetime) -> datetime:
    """The same moment in UTC - for database comparisons. Times are stored in UTC; SQLite compares them as text, so
    a Nepal-time bound (+05:45) would put checks made between 00:00 and 05:45 Nepal time on the wrong day."""
    return dt.astimezone(timezone.utc)


def _nepal_date(dt: datetime) -> str:
    """Nepal calendar day of a stored time (SQLite gives naive UTC times)."""
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(NEPAL).date().isoformat()


def _p90(values: list[int]) -> int | None:
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, int(round(0.9 * (len(s) - 1))))]


def _service(status: str, note: str, **extra) -> dict:
    return {"status": status, "note": note, **extra}


@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db), _: AdminUser = Depends(require_role("reviewer"))):
    app = request.app
    settings = app.state.settings
    checkers = app.state.checkers
    recorder = app.state.errors
    now = datetime.now(timezone.utc)
    today = utc(nepal_day_start(now))

    # ---- services ----
    services: dict[str, dict] = {}
    services["server"] = _service("ok", f"Up {recorder.uptime_seconds // 3600} h {recorder.uptime_seconds % 3600 // 60} min",
                                  version=settings.version, started_at=recorder.started_at.isoformat())
    mira = app.state.mira
    mira_state = {"ready": "ok", "loading": "warning", "not_started": "warning", "failed": "down", "disabled": "off"}
    services["mira"] = _service(mira_state.get(mira.status, "warning"),
                                {"ready": f"Ready ({mira.version})", "loading": "Loading the model…",
                                 "not_started": "Not loaded yet", "failed": f"Failed: {mira.error or 'unknown'}",
                                 "disabled": "Replaced by the trained model"}.get(mira.status, mira.status),
                                load_seconds=mira.load_seconds)
    clf = getattr(app.state, "classifier", None)
    trained_on = {**TRAINED_DEFAULTS, **app.state.checkers.trained}["enabled"]
    if clf is None or clf.status == "not_found":
        services["trained_model"] = _service("off", "No trained model in the models folder")
    elif not trained_on:
        services["trained_model"] = _service("off", f"Switched off in Settings ({clf.version})")
    else:
        services["trained_model"] = _service(
            mira_state.get(clf.status, "warning"),
            {"ready": f"Ready ({clf.version})", "loading": "Loading the model…", "not_started": "Not loaded yet",
             "failed": f"Failed: {clf.error or 'unknown'}"}.get(clf.status, clf.status),
            load_seconds=clf.load_seconds)
    t = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        ms = round((time.perf_counter() - t) * 1000)
        services["database"] = _service("ok" if ms < 500 else "warning", f"Answers in {ms} ms", ms=ms)
    except Exception as exc:  # noqa: BLE001
        services["database"] = _service("down", f"Not reachable ({type(exc).__name__})")
        db.rollback()

    otx_today = db.scalar(select(func.count()).select_from(OtxCache).where(
        OtxCache.checked_at >= now.replace(hour=0, minute=0, second=0, microsecond=0))) or 0
    quota = {"used": otx_today, "limit": settings.otx_daily_limit}
    if checkers.otx is None:
        services["otx"] = _service("off", "No OTX key set")
    else:
        share = otx_today / max(1, settings.otx_daily_limit)
        services["otx"] = _service("warning" if share >= 0.8 else "ok",
                                   f"{otx_today} of {settings.otx_daily_limit} lookups used today (UTC)")
    domains = db.scalar(select(func.count()).select_from(DomainCache)) or 0
    services["whois"] = (_service("off", "Switched off") if checkers.ages is None
                         else _service("ok", f"Only for ad links (not for messages) · {domains} domains cached",
                                       cached=domains))

    # ---- checks today ----
    rows = db.execute(select(Check.id, Check.user_id, Check.verdict, Check.score, Check.timings_ms, Check.checks_skipped,
                             Check.source, Check.created_at, Check.label).where(Check.created_at >= today)).all()
    times = [int((r.timings_ms or {}).get("total", 0)) for r in rows if (r.timings_ms or {}).get("total") is not None]
    skipped = Counter(part for r in rows for part in (r.checks_skipped or []))
    verdicts = Counter(r.verdict for r in rows)
    class_ids = [c.id for c in owner_config().classes]
    classes = Counter(r.label if r.label in class_ids else "unknown" for r in rows)
    slowest = sorted(rows, key=lambda r: int((r.timings_ms or {}).get("total", 0)), reverse=True)[:5]
    todays = {
        "checks": len(rows),
        "verdicts": {v: verdicts.get(v, 0) for v in ("safe", "suspicious", "dangerous", "unknown")},  # unknown: MIRA gave no answer (B6)
        # B8: the owner's five classes (the label column holds the class); unknown = MIRA gave no answer
        "risk_classes": {c: classes.get(c, 0) for c in class_ids + ["unknown"]},
        "active_users": len({r.user_id for r in rows}),
        "avg_ms": round(sum(times) / len(times)) if times else None,
        "p90_ms": _p90(times),
        "skipped": dict(skipped),
        # B8: with the owner's prompt a check takes ~30-70 s, so "slow" now means over SLOW_CHECK_SECONDS
        "slow_checks": sum(1 for x in times if x > SLOW_CHECK_SECONDS * 1000),
        "slow_after_s": SLOW_CHECK_SECONDS,
    }

    # ---- last 7 days ----
    week_start = nepal_day_start(now, 6)
    week = Counter(_nepal_date(c) for c in db.scalars(select(Check.created_at).where(Check.created_at >= utc(week_start))))
    days = [(week_start + timedelta(days=i)).date().isoformat() for i in range(7)]

    return {
        "generated_at": now.isoformat(),
        "services": services,
        "otx_quota": quota,
        "today": todays,
        "week": [{"day": d, "checks": week.get(d, 0)} for d in days],
        "slowest": [{"check_id": r.id, "verdict": r.verdict, "score": r.score, "source": r.source,
                     "total_ms": int((r.timings_ms or {}).get("total", 0)), "timings_ms": r.timings_ms or {},
                     "skipped": r.checks_skipped or [], "created_at": r.created_at.isoformat()} for r in slowest],
        "errors": {"since_start": recorder.total, "today": recorder.since(today), "recent": list(recorder.recent)[:10]},
        "totals": {
            "users": db.scalar(select(func.count()).select_from(Profile)) or 0,
            "known_scams": db.scalar(select(func.count()).select_from(KnownScam)) or 0,
            "pending_reports": db.scalar(select(func.count()).select_from(Feedback).where(Feedback.status == "pending")) or 0,
        },
    }
