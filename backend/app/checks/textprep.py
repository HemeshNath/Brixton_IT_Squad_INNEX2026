"""Pure text helpers: masking personal data, finding URLs, spotting OTP messages
and requests for secrets. No web or database code, so they are easy to unit test."""
from __future__ import annotations

import re

# ---------------------------------------------------------------- PII masking patterns
# Devanagari digits (०-९) are turned into 0-9 first so every number rule also works for Nepali text.
DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

# Nepal mobile numbers (98/97/96 + 8 digits, optional +977) and landlines (01-4xxxxxx).
PHONE_RE = re.compile(
    r"(?<!\w)(?:\+?977[-\s]?)?(?:98|97|96)\d{8}(?!\w)|(?<!\w)0\d{1,2}[-\s]?\d{6,7}(?!\w)"
)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
LONG_NUMBER_RE = re.compile(r"(?<!\w)\d{10,}(?!\w)")  # any other long number (account, ID...)

# Card numbers: 13-19 digits, optionally in groups split by spaces/dashes. Masked only if the Luhn check passes.
CARD_RE = re.compile(r"(?<![\w-])\d(?:[ -]?\d){12,18}(?![\w-])")

# Nepali citizenship numbers like 27-01-76-12345, or any number written after the word "citizenship".
CITIZENSHIP_RE = re.compile(r"(?<![\w-])\d{2}-\d{2}-\d{2}-\d{4,6}(?![\w-])")
CITIZENSHIP_KEYWORD_RE = re.compile(
    r"((?:citizenship|nagarikta|nagrikta|नागरिकता)\s*(?:no\.?|number|num|nam?bar|नं\.?)?\s*[:#.]?\s*)([\d/-]{4,20})",
    re.IGNORECASE,
)

# Account numbers written after "a/c", "account", "khata"... (bank-masked forms like XXXX4521 are left as they are).
ACCOUNT_RE = re.compile(
    r"((?:a/c|acc(?:oun)?t|khata|खाता)\s*(?:no\.?|number|num|nam?bar|नं\.?)?\s*[:#.]?\s*)(\d[\d -]{4,24}\d)",
    re.IGNORECASE,
)

# OTP / verification codes: a 4-8 digit number shortly after "otp/code/pin" or just before "is your OTP".
OTP_VALUE_RE = re.compile(
    r"((?:(?:otp|one[- ]time (?:password|code)|verification code|security code|passcode|code|m?pin)\b|ओटीपी|कोड)"
    r"[^\d<]{0,30}?)(\d{4,8})(?!\d)",
    re.IGNORECASE,
)
OTP_BEFORE_RE = re.compile(r"(?<!\d)(\d{4,8})(\s+(?:is|ho)\s+(?:your|tapai ?ko|hajur ?ko)?\s*(?:otp|code))", re.IGNORECASE)

# Passwords / PINs typed in a message: "password: abc123", "mpin is 1234", "पासवर्ड: ..."
SECRET_VALUE_RE = re.compile(
    r"((?:password|passwd|pwd|m?pin|cvv|पासवर्ड|पिन)\s*(?:is|ho|:|=|-)\s*)([^\s<,.;]{3,40})",
    re.IGNORECASE,
)

# Names (best effort, Latin letters only): "this is Ram", "my name is Ram", "Mero naam Ram", "Dear Ram,", "Hi Ram".
# The opener is case-insensitive; the name must start with a capital letter.
_NAME = r"([A-Z][a-z]{1,20}(?:\s[A-Z][a-z]{1,20})?)\b"
NAME_RE = re.compile(
    r"((?i:\b(?:this is|it'?s|i am|i'm|my name is|mero naa?m|name:|dear|hi|hello|namaste|from))\s+)" + _NAME
)
# "ma Ram ho" / "ma Sita bolde" - "ma" alone also means "in/at", so a following "ho/hu/bol..." is required.
NAME_MA_RE = re.compile(r"((?i:\bma)\s+)" + _NAME + r"(?=\s+(?i:ho|hu|hun|bol\w*)\b)")
# Words after those openers that are NOT personal names (kept, because they help detect scams).
NOT_NAMES = {
    "customer", "user", "sir", "madam", "mam", "friend", "friends", "winner", "subscriber", "member",
    "all", "team", "there", "everyone", "dai", "didi", "bhai", "bahini", "mom", "mummy", "dad", "papa",
    "your", "the", "our", "bank", "esewa", "khalti", "ncell", "ntc", "nepal", "office", "police",
    "admin", "support", "service", "valued", "account", "client", "sender", "beautiful",
    "rs", "nrs", "npr", "otp", "sms", "daraz", "pathao", "imepay", "fonepay", "nabil", "google",
    "facebook", "whatsapp", "viber", "telegram", "kathmandu", "pokhara", "korea", "government",
}

# Sensitive values inside link query strings (?email=..&token=..) are hidden; the domain and path are kept.
URL_SECRET_KEYS = re.compile(
    r"^(?:e?mail|token|access_token|auth|key|api_?key|otp|code|pin|pass(?:word)?|phone|mobile|msisdn|"
    r"session|sid|uid|user(?:name|id)?|account|acc|card|citizenship|ref|id)$",
    re.IGNORECASE,
)

# Anything that looks like a link: with scheme, starting with www., or a bare domain.
URL_RE = re.compile(
    r"(?<![@\w.-])(?:https?://|www\.)[^\s<>\"']+"
    r"|(?<![@\w.-])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}(?:/[^\s<>\"']*)?",
    re.IGNORECASE,
)
TRAILING_PUNCT = ".,;:!?)]}'\""

OTP_WORDS = re.compile(r"\b(otp|one[- ]time|verification code|verify code|passcode|code)\b", re.IGNORECASE)
OTP_DIGITS = re.compile(r"(?<!\d)\d{4,8}(?!\d)")

SECRET_WORDS = re.compile(
    r"\b(otp|m?pin|password|passcode|cvv|card number|6 digit code|code)\b|ओटीपी|पिन|पासवर्ड",
    re.IGNORECASE,
)
REQUEST_WORDS = re.compile(
    r"\b(send|share|forward|reply|enter|tell|give|provide|verify|submit|pathau\w*|pathai\w*|"
    r"bhann\w*|halnu\w*|dinu\w*)\b|पठाउ\w*|हाल्न\w*|भन्नु\w*",
    re.IGNORECASE,
)
NEGATION_WORDS = re.compile(
    r"\b(do not share|don't share|never share|not share|do not disclose|never disclose|"
    r"kasailai na\w*|nadinu\w*)\b|नदिनु\w*|कसैलाई",
    re.IGNORECASE,
)


def luhn_ok(digits: str) -> bool:
    """Luhn checksum used by every payment card; filters out ordinary long numbers."""
    total, double = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if double:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
        double = not double
    return total % 10 == 0


def _mask_card(match: re.Match) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    return "<CARD>" if 13 <= len(digits) <= 19 and luhn_ok(digits) else match.group(0)


def _mask_url_params(url: str) -> str:
    if "?" not in url:
        return url
    base, _, query = url.partition("?")

    def one(param: str) -> str:
        key, eq, value = param.partition("=")
        if not eq:
            return param
        sensitive = URL_SECRET_KEYS.match(key) or "@" in value or re.search(r"\d{7,}", value)
        return f"{key}=<REDACTED>" if sensitive and value else param

    return base + "?" + "&".join(one(p) for p in query.split("&"))


def _mask_name(match: re.Match) -> str:
    opener, name = match.group(1), match.group(2)
    if name.split()[0].lower() in NOT_NAMES:
        return match.group(0)
    return opener + "<NAME>"


def mask_pii(text: str) -> str:
    """Hide personal data and secrets before a message is analysed, stored or logged.

    Replaced with placeholders: phone numbers, emails, payment cards, citizenship and account
    numbers, OTP codes, PINs/passwords, other long numbers, people's names (best effort) and
    sensitive values in link query strings. Money amounts (Rs 5,000), links themselves (domain
    and path) and company names are kept, because they are needed to spot scams.
    Safe to run twice (placeholders are never masked again)."""
    text = text.translate(DEVANAGARI_DIGITS)
    for url in extract_urls(text):
        masked = _mask_url_params(url)
        if masked != url:
            text = text.replace(url, masked)
    text = EMAIL_RE.sub("<EMAIL>", text)
    text = CARD_RE.sub(_mask_card, text)
    text = CITIZENSHIP_RE.sub("<CITIZENSHIP>", text)
    text = CITIZENSHIP_KEYWORD_RE.sub(lambda m: m.group(1) + "<CITIZENSHIP>", text)
    text = ACCOUNT_RE.sub(lambda m: m.group(1) + "<ACCOUNT>", text)
    text = OTP_VALUE_RE.sub(lambda m: m.group(1) + "<OTP>", text)
    text = OTP_BEFORE_RE.sub(lambda m: "<OTP>" + m.group(2), text)
    text = SECRET_VALUE_RE.sub(lambda m: m.group(1) + "<SECRET>", text)
    text = PHONE_RE.sub("<PHONE>", text)
    text = LONG_NUMBER_RE.sub("<NUMBER>", text)
    text = NAME_RE.sub(_mask_name, text)
    text = NAME_MA_RE.sub(_mask_name, text)
    return text


def extract_urls(text: str) -> list[str]:
    """Return links found in the text, in order, without duplicates.
    Bare domains are only kept if they end in a real-looking TLD; the domain parser
    in links.py does the final validation."""
    found: list[str] = []
    for match in URL_RE.finditer(text):
        url = match.group(0).rstrip(TRAILING_PUNCT)
        # skip things like "Rs.500" or "5.30pm" that the bare-domain branch may catch
        if not re.search(r"[a-z]{2,}", url.split("/")[0].split(".")[-1], re.IGNORECASE):
            continue
        if url.lower() not in (u.lower() for u in found):
            found.append(url)
    return found


def is_otp_message(text: str) -> bool:
    """A normal OTP delivery: mentions OTP/code, contains a 4-8 digit number and
    tells the user not to share it, and contains no link."""
    return bool(
        OTP_WORDS.search(text)
        and OTP_DIGITS.search(text)
        and not extract_urls(text)
    )


def asks_for_secret(text: str) -> bool:
    """True when the message asks the reader to send/enter an OTP, PIN or password."""
    if NEGATION_WORDS.search(text):
        return False
    return bool(SECRET_WORDS.search(text) and REQUEST_WORDS.search(text))
