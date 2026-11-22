"""The owner's five questions answered instantly, without old MIRA (which took 30-70 s per check).

  1. asks for OTP, password, personal or bank details -> the message asks for a secret, or for card / account /
     KYC details                                                                    (words: English, Roman Nepali, Nepali)
  2. offers a prize, offer or lottery                                               (words)
  3. does the link's IP have a good reputation?   No = AlienVault OTX threat reports for the link
  4. does the link have good domain information?   No = WHOIS: registered under 15 days ago, or registered outside
     Nepal (registrant country is not NP) - the owner's prompt's definition
  5. shows urgency                                                                  (words)
Questions 3 and 4 only count for messages with a link. The answers only fill the text in brackets; the Probability
comes from the owner's trained model."""
from __future__ import annotations

import re

from .links import LinkResult
from .textprep import asks_for_secret

NEW_DOMAIN_DAYS = 15

DETAILS_RE = re.compile(
    r"\b(otp|pin|password|cvv|card number|account number|bank details?|kyc|verify your (account|details)|"
    r"citizenship|nagarikta|khata number|login details?)\b|पासवर्ड|ओटीपी|खाता नम्बर|नागरिकता|केवाइसी",
    re.IGNORECASE,
)
PRIZE_RE = re.compile(
    r"\b(won|win|winner|prize|lottery|lucky draw|gift|free|bonus|offer|discount|cashback|reward|jitnu\w*|"
    r"inam|chitha|muft|nishulka)\b|जित्नु\w*|जित्नुभयो|उपहार|पुरस्कार|इनाम|चिट्ठा|निःशुल्क|नि:शुल्क|अफर|छुट",
    re.IGNORECASE,
)
URGENT_RE = re.compile(
    r"\b(urgent\w*|immediately|right now|today|within \d+ (hours?|minutes?)|blocked|suspended|deactivated|expire\w*|"
    r"last chance|asap|turunta|jaruri|chito|arrest\w*)\b|तुरुन्त|तुरुन्तै|जरुरी|छिटो|रोक्का|निलम्बन|बन्द हुनेछ|आजै",
    re.IGNORECASE,
)


def answers(text: str, links: list[LinkResult], reasons: dict[str, str]) -> list[str]:
    """The warnings (owner_decision.json reason texts, by question id) that apply to this message, in question order."""
    out = []
    if asks_for_secret(text) or DETAILS_RE.search(text):
        out.append(reasons["asks_credentials"])
    if PRIZE_RE.search(text):
        out.append(reasons["offers_prize"])
    if links:
        if any((l.otx_counts or {}).get("pulses") and not (l.otx_counts or {}).get("whitelisted") for l in links):
            out.append(reasons["good_ip_reputation"])
        if any(_bad_domain(l) for l in links):
            out.append(reasons["good_domain"])
    if URGENT_RE.search(text):
        out.append(reasons["urgency"])
    return out


def _bad_domain(link: LinkResult) -> bool:
    if link.domain_age_days is not None and link.domain_age_days < NEW_DOMAIN_DAYS:
        return True
    country = str(((link.whois or {}).get("registrant") or {}).get("country") or "").strip().upper()
    return bool(country) and country not in ("NP", "NEPAL")
