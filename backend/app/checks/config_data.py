"""Loads the editable data files in app/data/. Lists live there, not in code, so the team
can change the whitelist, brands, risky TLDs or blocked countries without a code change.

Files are read once and cached; call reload() after editing them while the server runs
(or restart the server)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

TRUSTED_FILE = "trusted.json"
COUNTRIES_FILE = "blocked_countries.json"


@lru_cache(maxsize=None)
def load_json(name: str) -> dict:
    path = DATA_DIR / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuntimeError(f"Data file missing: {path}") from None
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Data file {path} is not valid JSON: {exc}") from None


def trusted() -> dict:
    """trusted_domains, brand_keywords, trusted_senders, shorteners, suspicious_tlds."""
    return load_json(TRUSTED_FILE)


def blocked_countries() -> dict[str, str]:
    """ISO country code -> name, e.g. {"RU": "Russia"}."""
    data = load_json(COUNTRIES_FILE)
    return {code.strip().upper(): name for code, name in data["countries"].items()}


def blocked_country_policy() -> dict:
    """{"mode": "points" | "force_dangerous", "points": int}"""
    data = load_json(COUNTRIES_FILE)
    given = {k: v for k, v in data.get("policy", {}).items() if not k.startswith("_")}  # "_..." keys are notes
    policy = {"mode": "points", "points": 15} | given
    if policy["mode"] not in {"points", "force_dangerous"}:
        raise RuntimeError(f"Unknown blocked-country mode {policy['mode']!r}")
    return policy


def reload() -> None:
    load_json.cache_clear()
