"""Sender trust: points added to MIRA's Probability from two facts the phone sends (contacts never leave the phone).

  - sender_in_contacts: the sender is saved in the user's contacts        -> contact_points   (default -15)
  - sender_seen_before: messages CheckScam saw from this sender before
        >= frequent_from (default 5)                                       -> frequent_points  (default -10)
        0 = first message ever from this sender (and not a saved contact)  -> new_points       (default +10)
        1 .. frequent_from-1                                               -> no change
Negative points = more trust (lower risk). A saved contact never gets the "new sender" red flag (right after
CheckScam is installed every sender is new to it). Unknown facts (null) change nothing. The numbers are live
settings in the admin panel (group "sender_trust")."""
from __future__ import annotations

from dataclasses import dataclass

DEFAULTS = {"enabled": True, "contact_points": -15, "frequent_points": -10, "frequent_from": 5, "new_points": 10}


@dataclass(frozen=True)
class SenderFacts:
    in_contacts: bool | None = None
    seen_before: int | None = None

    @property
    def known(self) -> bool:
        return self.in_contacts is not None or self.seen_before is not None


def adjustments(facts: SenderFacts | None, cfg: dict | None = None) -> list[dict]:
    """The sender-trust reasons for these facts: [{"code", "text", "points"}], empty when nothing applies."""
    c = {**DEFAULTS, **(cfg or {})}
    if facts is None or not c["enabled"]:
        return []
    out = []
    if facts.in_contacts:
        out.append({"code": "SENDER_IN_CONTACTS", "text": "Sender is saved in your contacts",
                    "points": int(c["contact_points"])})
    seen = facts.seen_before
    if seen is not None:
        if seen >= int(c["frequent_from"]):
            out.append({"code": "SENDER_FREQUENT",
                        "text": f"You often get messages from this sender ({seen} before)",
                        "points": int(c["frequent_points"])})
        elif seen == 0 and not facts.in_contacts:
            out.append({"code": "SENDER_NEW", "text": "First message from this sender", "points": int(c["new_points"])})
    return [a for a in out if a["points"] != 0]


def apply(probability: int, reasons: list[dict]) -> int:
    """MIRA's Probability plus the sender-trust points, kept within 0-100."""
    return max(0, min(100, probability + sum(r["points"] for r in reasons)))
