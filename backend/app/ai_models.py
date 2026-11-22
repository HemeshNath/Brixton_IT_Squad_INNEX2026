"""Approved AI model versions (Phase 10A step A5): list, test run on the data set, switch and roll back.

- Only versions in app/data/models.json can be chosen, each pinned to an exact revision.
- A test run sends the data set (eval/data/seed_sms.csv + collected_sms.csv) through the normal check with only
  MIRA and the message rules (no OTX/WHOIS calls, no quota spent) and stores how many scams were caught and how
  many normal messages were called Dangerous / Suspicious. One test at a time, in the background.
- Switching needs a finished test of that version. The new version loads in the background; checks keep using
  the old one until it is ready. The choice is saved, so it survives a restart. Rolling back = switching back."""
from __future__ import annotations

import csv
import logging
import os
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .checks.config_data import load_json
from .checks.mira import MiraModel, MiraService
from .db import ModelChoice, ModelTest

log = logging.getLogger("checkscam.models")
MODELS_FILE = "models.json"
DATA_DIR = Path(__file__).resolve().parent.parent / "eval" / "data"
DATA_FILES = ("seed_sms.csv", "collected_sms.csv")
_test_lock = threading.Lock()
_switch_lock = threading.Lock()


def versions() -> list[dict]:
    return [v for v in load_json(MODELS_FILE)["versions"] if v.get("approved")]


def find(version_id: str) -> dict | None:
    return next((v for v in versions() if v["id"] == version_id), None)


def default_version(settings) -> dict | None:
    """The approved version that matches .env (MIRA_MODEL_ID / MIRA_REVISION)."""
    return next((v for v in versions() if v["model_id"] == settings.mira_model_id
                 and v["revision"] == settings.mira_revision), None)


def chosen_version(db: Session, settings) -> dict | None:
    row = db.scalars(select(ModelChoice).order_by(ModelChoice.id.desc()).limit(1)).first()
    if row is not None and find(row.version_id):
        return find(row.version_id)
    return default_version(settings)


def cache_dir(settings) -> str | None:
    return os.path.join(settings.hf_home, "hub") if settings.hf_home else None


def downloaded(settings, v: dict) -> bool:
    """True if the version's files are already in the Hugging Face cache (nothing is downloaded here)."""
    try:
        from huggingface_hub import try_to_load_from_cache
        path = try_to_load_from_cache(v["model_id"], "config.json", cache_dir=cache_dir(settings), revision=v["revision"])
        return isinstance(path, str)
    except Exception:  # noqa: BLE001
        return False


def owner_warmup(model: MiraModel) -> None:
    """One practice batch with the owner's prompt, so the first real check is not the slow one (B7)."""
    from .checks.context import build_context
    from .checks.owner_decision import build_batch
    from .checks.owner_prompt import build_prompt

    model.batch(build_batch(build_prompt(build_context("SMS", "Hello, how are you?", []))))


def make_service(settings, v: dict | None) -> MiraService:
    """A MiraService for version `v` (None = the .env model)."""
    model_id = v["model_id"] if v else settings.mira_model_id
    revision = v["revision"] if v else settings.mira_revision

    def loader() -> MiraModel:
        return MiraModel.load(model_id, revision, cache_dir=cache_dir(settings), local_only=settings.mira_local_only,
                              not_sure_below=settings.mira_not_sure_below)

    service = MiraService(loader, timeout=settings.mira_timeout_seconds, enabled=settings.mira_enabled,
                          warmup=owner_warmup)
    service.version_id = v["id"] if v else ""
    return service


# ---- test run ----

def _data_set() -> list[dict]:
    rows = []
    for name in DATA_FILES:
        path = DATA_DIR / name
        if path.exists():
            with open(path, encoding="utf-8") as f:
                rows += [r for r in csv.DictReader(f) if r.get("label") in ("scam", "spam", "ham")]
    return rows


def summarize(results: list[tuple[str, str, float]]) -> dict:
    """results = [(true label, verdict, mira ms)] -> the numbers shown in the panel."""
    by = {lab: Counter(v for l, v, _ in results if l == lab) for lab in ("scam", "spam", "ham")}
    n = {lab: sum(c.values()) for lab, c in by.items()}

    def share(part: int, whole: int) -> float | None:
        return round(100 * part / whole, 1) if whole else None

    ms = [m for _, _, m in results if m]
    return {
        "messages": len(results),
        "by_label": {lab: dict(c) for lab, c in by.items()},
        "scams_caught_pct": share(by["scam"]["suspicious"] + by["scam"]["dangerous"], n["scam"]),
        "scams_dangerous_pct": share(by["scam"]["dangerous"], n["scam"]),
        "normal_dangerous_pct": share(by["ham"]["dangerous"], n["ham"]),
        "normal_suspicious_pct": share(by["ham"]["suspicious"], n["ham"]),
        "ads_dangerous_pct": share(by["spam"]["dangerous"], n["spam"]),
        "avg_mira_ms": round(sum(ms) / len(ms)) if ms else None,
    }


def start_test(app, version_id: str, admin: str) -> int:
    """Starts a background test run; returns its id. Raises ValueError with a readable reason."""
    from .checks.pipeline import Checkers, run_check

    v = find(version_id)
    if v is None:
        raise ValueError("Not an approved model version.")
    if not downloaded(app.state.settings, v) and not _is_live(app, v):
        raise ValueError("This version is not downloaded on the server yet.")
    if not _test_lock.acquire(blocking=False):
        raise ValueError("A test is already running. Wait for it to finish.")
    rows = _data_set()
    with app.state.sessionmaker() as db:
        test = ModelTest(version_id=version_id, started_by=admin, result={"done": 0, "total": len(rows)})
        db.add(test)
        db.commit()
        test_id = test.id

    def run() -> None:
        try:
            service = app.state.mira if _is_live(app, v) else make_service(app.state.settings, v)
            if not service.ready:
                service.start_loading(background=False)
            checkers = Checkers(mira=service)  # MIRA + message rules only: no OTX/WHOIS calls
            results = []
            for i, row in enumerate(rows, 1):
                r = run_check(row["text"], "", checkers)
                results.append((row["label"], r["verdict"], r["timings_ms"].get("mira", 0)))
                if i % 10 == 0 or i == len(rows):
                    _save_test(app, test_id, "running", {"done": i, "total": len(rows)})
            _save_test(app, test_id, "done", summarize(results) | {"done": len(rows), "total": len(rows),
                                                                   "model_version": service.version}, finished=True)
        except Exception as exc:  # noqa: BLE001
            log.exception("Model test failed")
            _save_test(app, test_id, "failed", {"error": type(exc).__name__}, finished=True)
        finally:
            _test_lock.release()

    threading.Thread(target=run, name="model-test", daemon=True).start()
    return test_id


def _save_test(app, test_id: int, status: str, result: dict, finished: bool = False) -> None:
    with app.state.sessionmaker() as db:
        t = db.get(ModelTest, test_id)
        t.status, t.result = status, result
        if finished:
            t.finished_at = datetime.now(timezone.utc)
        db.commit()


def _is_live(app, v: dict) -> bool:
    return getattr(app.state.mira, "version_id", "") == v["id"]


def last_test(db: Session, version_id: str) -> ModelTest | None:
    return db.scalars(select(ModelTest).where(ModelTest.version_id == version_id)
                      .order_by(ModelTest.id.desc()).limit(1)).first()


# ---- switching ----

def switch(app, version_id: str, admin: str, note: str = "") -> None:
    """Loads `version_id` in the background and swaps it in when ready. Raises ValueError with a reason."""
    v = find(version_id)
    if v is None:
        raise ValueError("Not an approved model version.")
    if _is_live(app, v):
        raise ValueError("This version is already in use.")
    if not downloaded(app.state.settings, v):
        raise ValueError("This version is not downloaded on the server yet.")
    with app.state.sessionmaker() as db:
        t = last_test(db, version_id)
        if t is None or t.status != "done":
            raise ValueError("Run a test of this version first.")
        db.add(ModelChoice(version_id=version_id, chosen_by=admin, note=note[:200]))
        db.commit()
    if not _switch_lock.acquire(blocking=False):
        raise ValueError("A switch is already in progress.")
    old = app.state.mira
    new = make_service(app.state.settings, v)
    new.timeout = old.timeout  # keep the live time limit from the settings
    app.state.switching_to = version_id

    def run() -> None:
        try:
            new.start_loading(background=False)
            if new.ready:
                app.state.mira = new
                app.state.checkers.mira = new
                log.info("AI model switched to %s", version_id)
            else:
                log.error("New model did not load (%s); keeping the old one", new.error)
        finally:
            app.state.switching_to = None
            _switch_lock.release()

    threading.Thread(target=run, name="model-switch", daemon=True).start()


def wait_for_switch(app, timeout: float = 30.0) -> None:
    """Tests only: waits until a background switch has finished."""
    end = time.time() + timeout
    while getattr(app.state, "switching_to", None) and time.time() < end:
        time.sleep(0.05)
