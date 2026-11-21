"""Combine model probabilities and rule findings into a score, verdict, reasons and
suggestion. Pure function so every boundary can be unit tested."""
from __future__ import annotations

from dataclasses import dataclass

from .links import LinkResult, Reason

SAFE_MAX = 30
SUSPICIOUS_MAX = 60
SECRET_REQUEST_POINTS = 15
SPAM_WEIGHT = 30


@dataclass
class ScoreInput:
    probabilities: dict[str, float] | None  # None when the model is unavailable
    links: list[LinkResult]
    sender_trusted: bool = False
    asks_secret: bool = False


def verdict_for(score: int) -> str:
    if score <= SAFE_MAX:
        return "safe"
    if score <= SUSPICIOUS_MAX:
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


def score_message(inp: ScoreInput) -> dict:
    reasons: list[Reason] = []
    label = None

    risky_links = [l for l in inp.links if not l.trusted and l.points > 0]
    model_points = 0
    if inp.probabilities:
        p_scam = inp.probabilities.get("scam", 0.0)
        p_spam = inp.probabilities.get("spam", 0.0)
        label = max(inp.probabilities, key=inp.probabilities.get)
        model_points = round(100 * p_scam + SPAM_WEIGHT * p_spam)
        if inp.sender_trusted and not risky_links:
            model_points = round(model_points * 0.5)
        if p_scam >= 0.5:
            reasons.append(Reason("MODEL_SCAM", f"Wording matches known scam messages ({p_scam:.0%} sure)", model_points))
        elif p_spam >= 0.5:
            reasons.append(Reason("MODEL_SPAM", f"Looks like an advertisement / promotional message ({p_spam:.0%} sure)", model_points))
        elif model_points > 0:
            reasons.append(Reason("MODEL_SCORE", "Wording risk from our scam model", model_points))

    # Only the worst link counts, so one message with many links does not explode.
    if risky_links:
        worst = max(risky_links, key=lambda l: l.points)
        reasons.extend(worst.reasons)

    if inp.asks_secret:
        reasons.append(Reason("ASKS_SECRET", "Message asks you to send or enter an OTP, PIN or password", SECRET_REQUEST_POINTS))

    for link in inp.links:
        if link.trusted:
            reasons.append(Reason("TRUSTED_LINK", f"Link goes to the official site of {link.organization}", 0))
            break
    if inp.sender_trusted:
        reasons.append(Reason("TRUSTED_SENDER", "Sender ID belongs to a known company", 0))

    score = max(0, min(100, sum(r.points for r in reasons)))
    verdict = verdict_for(score)
    return {
        "verdict": verdict,
        "score": score,
        "label": label,
        "reasons": [r.as_dict() for r in reasons],
        "suggestion": _suggestion(verdict, bool(risky_links), inp.asks_secret),
    }
