"""Trusted sender IDs (eSewa, NTC, banks...). List lives in data/trusted.json."""
from __future__ import annotations

import re

from .config_data import trusted


def is_trusted_sender(sender: str) -> bool:
    key = re.sub(r"[^a-z0-9]", "", (sender or "").lower())
    if not key:
        return False
    return any(key == s or (len(s) >= 4 and key.startswith(s)) for s in trusted()["trusted_senders"])
