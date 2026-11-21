"""Loads the editable data files in app/data/. Lists live there, not in code, so the team
can change the whitelist, brands, risky TLDs or shared-hosting networks without a code change.

Files are read once and cached; call reload() after editing them while the server runs
(or restart the server)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

TRUSTED_FILE = "trusted.json"


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
    """trusted_domains, brand_keywords, trusted_senders, shorteners, suspicious_tlds, shared_hosting_asns."""
    return load_json(TRUSTED_FILE)


def reload() -> None:
    load_json.cache_clear()
