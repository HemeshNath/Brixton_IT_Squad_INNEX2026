"""Scoring v2 (Phase 8): turns all findings into a score 0-100, a verdict, reasons and advice.
Every number comes from app/data/scoring.json (version saved with each check).

Parts of the score:
  MIRA        scam_weight*P(scam) + spam_weight*P(ad) + question points (can be negative)
  links       the worst link's rule / OTX / domain-age points (one bad link counts, not the sum of all)
  rules       asks for OTP/PIN, brand mismatch, gambling words
  memory      very similar to an approved known scam (Phase 10)
  hard rules  OTP request + non-official link -> at least Dangerous;
              registered company sender + only official links + asks nothing -> at most Safe
Pure function, so every boundary can be unit tested."""
from __future__ import annotations

from dataclasses import dataclass, field

from .links import LinkResult, Reason
from .rules import ScoringConfig, scoring_config


@dataclass
class ScoreInput:
    probabilities: dict[str, float] | None  # MIRA scam/spam/ham; None when MIRA was skipped
    links: list[LinkResult]
    sender_trusted: bool = False
    asks_secret: bool = False
    question_points: float = 0.0  # from MIRA's yes/no questions
    scam_type: str | None = None  # e.g. "fake prize, gift or lottery"
    not_sure: bool = False
    brand_mismatch: list[str] = field(default_factory=list)
    gambling: bool = False
    known_similarity: float = 0.0  # best similarity to a known scam (0 = none / not checked)


def verdict_for(score: int, cfg: ScoringConfig | None = None) -> str:
    cfg = cfg or scoring_config()
    if score <= cfg.safe_max:
        return "safe"
    if score <= cfg.suspicious_max:
        return "suspicious"
    return "dangerous"


def _suggestion(verdict: str, has_risky_link: bool, asks_secret: bool) -> str:
    if verdict == "dangerous":
        if asks_secret:
            return "This is very likely a scam. Never share your OTP, PIN or password with anyone."
        if has_risky_link:
            return "This is very likely a scam. Do not open the link or enter any details."
        return "This is very likely a scam. Do not reply, call back or send money."
    if verdict == "suspicious":
        return ("Be careful. Do not click links or send money until you confirm with the "
                "company through its official number or app.")
    return "No scam signs found. Still, never share your OTP or PIN with anyone."


def _mira_reasons(inp: ScoreInput, cfg: ScoringConfig, risky_links: list[LinkResult]) -> list[Reason]:
    m = cfg.mira
    p = inp.probabilities
    points = m["scam_weight"] * p.get("scam", 0.0) + m["spam_weight"] * p.get("spam", 0.0) + m["question_scale"] * inp.question_points
    if inp.not_sure:
        points *= m["not_sure_factor"]
    if inp.sender_trusted and not risky_links:
        points *= m["trusted_sender_factor"]
    # MIRA never decides alone: its points are capped so that on its own it reaches at most Suspicious.
    points = round(min(m.get("max_points", 100), max(m["min_points"], points)))
    label = max(p, key=p.get)
    if label == "scam":
        what = f"a {inp.scam_type}" if inp.scam_type else "a scam message"
        reasons = [Reason("MIRA_SCAM", f"The text looks like {what} ({p['scam']:.0%} sure)", points)]
    elif label == "spam":
        reasons = [Reason("MIRA_AD", f"The text looks like an advertisement ({p['spam']:.0%} sure)", points)]
    else:
        reasons = [Reason("MIRA_NORMAL", f"The text looks like a normal message ({p['ham']:.0%} sure)", points)]
    if inp.not_sure:
        reasons.append(Reason("MIRA_NOT_SURE", "The text check was not sure, so it counts less", 0))
    return reasons


def _known_scam_points(sim: float, cfg: ScoringConfig) -> int:
    k = cfg.known_scam
    if sim >= k["strong_similarity"]:
        return int(k["strong_points"])
    if sim >= k["min_similarity"]:
        return int(k["points"])
    return 0


def score_message(inp: ScoreInput, cfg: ScoringConfig | None = None) -> dict:
    cfg = cfg or scoring_config()
    reasons: list[Reason] = []
    risky_links = [l for l in inp.links if not l.trusted and l.points > 0]
    unofficial_links = [l for l in inp.links if not l.trusted]
    label = None

    if inp.probabilities:
        label = max(inp.probabilities, key=inp.probabilities.get)
        reasons += _mira_reasons(inp, cfg, risky_links)

    if risky_links:  # only the worst link counts, so many links do not add up
        reasons.extend(max(risky_links, key=lambda l: l.points).reasons)

    if inp.asks_secret:
        reasons.append(Reason("ASKS_SECRET", "Message asks you to send or enter an OTP, PIN or password", cfg.rules["asks_secret"]))
    for brand in inp.brand_mismatch[:1]:
        reasons.append(Reason("BRAND_MISMATCH", f"Message mentions {brand} but the link is not {brand}'s official site",
                              cfg.rules["brand_mismatch"]))
    if inp.gambling:
        reasons.append(Reason("GAMBLING_WORDS", "Message invites you to gambling or betting", cfg.rules["gambling_words"]))
    known = _known_scam_points(inp.known_similarity, cfg)
    if known:
        reasons.append(Reason("KNOWN_SCAM", f"Matches a known scam message ({inp.known_similarity:.0%} alike)", known))

    for link in inp.links:
        if link.trusted:
            reasons.append(Reason("TRUSTED_LINK", f"Link goes to the official site of {link.organization}", 0))
            break
    if inp.sender_trusted:
        reasons.append(Reason("TRUSTED_SENDER", "Sender ID belongs to a known company", 0))

    score = max(0, min(100, sum(r.points for r in reasons)))

    # Hard rules (decided by facts, never by MIRA alone)
    if cfg.hard_rules.get("otp_and_unofficial_link") and inp.asks_secret and unofficial_links:
        if score <= cfg.suspicious_max:
            score = cfg.suspicious_max + 1
        reasons.append(Reason("HARD_OTP_LINK", "Asks for an OTP/PIN and links to a site that is not official", 0))
    elif (cfg.hard_rules.get("trusted_sender_official_only") and inp.sender_trusted and not unofficial_links
          and not inp.asks_secret and not inp.brand_mismatch and not known):
        score = min(score, cfg.safe_max)

    verdict = verdict_for(score, cfg)
    return {
        "verdict": verdict,
        "score": score,
        "label": label,
        "reasons": [r.as_dict() for r in reasons],
        "suggestion": _suggestion(verdict, bool(risky_links), inp.asks_secret),
        "scoring_version": cfg.version,
    }
