"""Message-level rules learned from real Nepal scam SMS (Phase 8) and the scoring config loader.

- brand_mismatch(): the message names a company (eSewa, RBB, connectIPS, Ncell...) but its link is
  not that company's official site - the most common pattern in the collected real scams.
- has_gambling_words(): casino / betting / slot wording.
- scoring_config(): numbers from app/data/scoring.json (points, weights, cut-offs)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .config_data import load_json, trusted
from .links import LinkResult

SCORING_FILE = "scoring.json"

GAMBLING_RE = re.compile(
    r"\b(casino|betting|bet now|place a bet|slots?|jackpot|poker|roulette|baccarat|teen ?patti|aviator|1xbet|"
    r"juwa|jua)\b|🎰|🎲|जुवा|क्यासिनो",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ScoringConfig:
    version: str
    safe_max: int
    suspicious_max: int
    mira: dict
    domain_age: dict
    otx: dict
    rules: dict
    hard_rules: dict
    known_scam: dict


def scoring_config() -> ScoringConfig:
    d = load_json(SCORING_FILE)
    try:
        cfg = ScoringConfig(
            version=d["version"],
            safe_max=int(d["cutoffs"]["safe_max"]),
            suspicious_max=int(d["cutoffs"]["suspicious_max"]),
            mira=d["mira"], domain_age=d["domain_age"], otx=d["otx"], rules=d["rules"], hard_rules=d["hard_rules"],
            known_scam=d["known_scam"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"{SCORING_FILE}: missing or bad value ({exc})") from None
    if not 0 <= cfg.safe_max < cfg.suspicious_max < 100:
        raise RuntimeError(f"{SCORING_FILE}: cut-offs must satisfy 0 <= safe_max < suspicious_max < 100")
    if cfg.mira.get("max_points", 0) > cfg.suspicious_max:
        raise RuntimeError(f"{SCORING_FILE}: mira.max_points must not exceed suspicious_max (MIRA must never decide alone)")
    return cfg


def _mentions(text: str, word: str) -> bool:
    if word.isascii():
        return re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", text, re.IGNORECASE) is not None
    return word in text  # Devanagari: plain substring


def brands_mentioned(text: str) -> list[str]:
    return [brand for brand, words in trusted().get("brand_mentions", {}).items() if any(_mentions(text, w) for w in words)]


def brand_mismatch(text: str, links: list[LinkResult]) -> list[str]:
    """Brands named in the message whose official site is NOT among the links, when the message has at
    least one non-official link. Example: "RBB Dashain gift ... rbb.nwmhkb.top" -> ["Rastriya Banijya Bank"]."""
    unofficial = [l for l in links if not l.trusted]
    if not unofficial:
        return []
    official_orgs = [l.organization or "" for l in links if l.trusted]
    return [b for b in brands_mentioned(text) if not any(org.startswith(b) for org in official_orgs)]


def has_gambling_words(text: str) -> bool:
    return GAMBLING_RE.search(text) is not None
