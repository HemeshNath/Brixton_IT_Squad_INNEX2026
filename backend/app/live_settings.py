"""Live system settings (Phase 10A step A4, trimmed in B8): on/off switches and time limits, changed from the admin
panel without restarting the server.

B8: in the owner's flow MIRA alone decides, so the old points / cut-off / rule settings were removed - they no longer
changed anything. Older saved versions still load: groups that are no longer known are simply ignored.

- Every save is a new numbered version in `settings_versions` (who, when, note). "Undo" restores an older
  version by saving it again as a new version, so the history is never rewritten.
- With no saved version, the defaults come from .env (version 0).
- FIELDS describes every setting (group, label, type, limits, help); the admin panel builds its form from it and
  the server checks every value against it, plus the rule between fields (links + MIRA < the phone's wait)."""
from __future__ import annotations

import copy
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .checks import rules
from .checks.owner_decision import config as owner_config
from .checks.pipeline import TRAINED_DEFAULTS
from .checks.sender_trust import DEFAULTS as SENDER_TRUST_DEFAULTS
from .db import SettingsVersion

log = logging.getLogger("checkscam.settings")
PHONE_WAIT_SECONDS = 20.0  # old MIRA removed (trained model ~0.1 s); was 90.0  # B6: the phone waits at most this long for a whole check (MIRA with the owner's prompt: 26-55 s)


@dataclass(frozen=True)
class Field:
    group: str
    key: str
    label: str
    kind: str  # int | float | bool
    min: float | None = None
    max: float | None = None
    help: str = ""

    def as_dict(self) -> dict:
        return {"group": self.group, "key": self.key, "label": self.label, "type": self.kind, "min": self.min,
                "max": self.max, "help": self.help}


FIELDS: list[Field] = [
    Field("switches", "otx", "AlienVault OTX (IP Reputation)", "bool",
          help="Off: links are not sent to OTX; the prompt says 'No reply from OTX'."),
    Field("timeouts", "links_seconds", "Link check time limit (s)", "float", 0.5, 10,
          "The OTX reputation lookup waits this long; a slower answer still finishes and is saved for next time."),
    Field("sender_trust", "enabled", "Use sender trust", "bool",
          help="Off: saved contacts and sender history do not change the Probability."),
    Field("sender_trust", "contact_points", "Saved contact", "int", -50, 0,
          "Added to the Probability when the sender is in the user's contacts (negative = more trust)."),
    Field("sender_trust", "frequent_points", "Frequent sender", "int", -50, 0,
          "Added when the user often gets messages from this sender."),
    Field("sender_trust", "frequent_from", "Frequent from (messages before)", "int", 1, 100,
          "How many earlier messages make a sender 'frequent'."),
    Field("sender_trust", "new_points", "First message from a new sender", "int", 0, 50,
          "Added for the first message from a sender that is not a saved contact (red flag)."),
]
FIELDS += [
    Field("trained_model", "temperature", "Score softness (T)", "float", 1, 10,
          "1 = mostly 0% or 100%; higher = more graded scores. The decision (above / below 50%) stays the same."),
]
GROUPS = {"switches": "On / off", "timeouts": "Time limits", "sender_trust": "Sender trust",
          "trained_model": "Trained model"}


def defaults(settings) -> dict:
    """Version 0: the .env values."""
    return {
        "switches": {"otx": True},
        "timeouts": {"links_seconds": settings.link_checks_timeout_seconds},
        "sender_trust": dict(SENDER_TRUST_DEFAULTS),
        "trained_model": {"temperature": TRAINED_DEFAULTS["temperature"]},
    }


def with_defaults(data: dict | None, settings) -> dict:
    """Saved settings + any setting added since they were saved (taken from the defaults)."""
    out = copy.deepcopy(defaults(settings))
    for group, values in (data or {}).items():
        if isinstance(values, dict) and group in out:
            out[group].update(values)
    return out


def validate(data: dict) -> tuple[dict, list[str]]:
    """Returns (clean data with only known fields, list of problems)."""
    clean: dict = {g: {} for g in GROUPS}
    problems: list[str] = []
    for f in FIELDS:
        value = (data.get(f.group) or {}).get(f.key)
        if value is None:
            problems.append(f"{f.label}: missing.")
            continue
        if f.kind == "bool":
            if not isinstance(value, bool):
                problems.append(f"{f.label}: must be on or off.")
                continue
        else:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                problems.append(f"{f.label}: must be a number.")
                continue
            if f.kind == "int":
                if float(value) != int(value):
                    problems.append(f"{f.label}: must be a whole number.")
                    continue
                value = int(value)
            else:
                value = round(float(value), 3)
            if (f.min is not None and value < f.min) or (f.max is not None and value > f.max):
                problems.append(f"{f.label}: must be between {f.min:g} and {f.max:g}.")
                continue
        clean[f.group][f.key] = value
    if not problems:
        t = clean["timeouts"]
        if t["links_seconds"] > PHONE_WAIT_SECONDS - 5:
            problems.append(f"The link time limit must be at most {PHONE_WAIT_SECONDS - 5:g} s "
                            f"(the phone waits {PHONE_WAIT_SECONDS:g} s).")
    return clean, problems


def version_label(number: int) -> str:
    """e.g. "owner-v1" (defaults) or "owner-v1.v3" (saved settings version 3)."""
    base = owner_config().version
    return base if number == 0 else f"{base}.v{number}"


def apply(app, data: dict, number: int) -> None:
    """Makes `data` live: switches and time limits. Used at start-up and after every save."""
    rules.set_scoring_override(None)  # B8: the old points settings are gone; scoring.py is not used by checks
    checkers = app.state.checkers
    checkers.link_timeout = float(data["timeouts"]["links_seconds"])
    # old MIRA is only used when USE_ORIGINAL_MIRA is on in .env (it is not an admin setting any more)
    checkers.switches = dict(data["switches"]) | {"mira": bool(getattr(app.state.settings, "use_original_mira", False))}
    checkers.sender_trust = dict(data["sender_trust"])
    checkers.trained = dict(data["trained_model"])
    app.state.settings_version = number


def latest(db: Session) -> SettingsVersion | None:
    return db.scalars(select(SettingsVersion).order_by(SettingsVersion.number.desc()).limit(1)).first()


def load_on_start(app) -> None:
    """Applies the newest saved version (or the defaults). Never stops the server from starting."""
    try:
        with app.state.sessionmaker() as db:
            row = latest(db)
    except Exception as exc:  # noqa: BLE001 - e.g. table not migrated yet
        log.warning("Saved settings not loaded (%s); using defaults", type(exc).__name__)
        row = None
    if row is None:
        apply(app, defaults(app.state.settings), 0)
        return
    data, problems = validate(with_defaults(row.data, app.state.settings))
    if problems:
        log.warning("Saved settings v%s are invalid (%s); using defaults", row.number, problems[0])
        apply(app, defaults(app.state.settings), 0)
    else:
        apply(app, data, row.number)
        log.info("Settings v%s applied", row.number)
