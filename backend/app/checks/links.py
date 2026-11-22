"""Link rules (from SRS v1.1 section 8), applied to URLs found inside a message.
Pure functions: they only look at the URL text, they never open the page."""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import tldextract

from .config_data import trusted as trusted_data

# Offline extractor: uses the public-suffix snapshot bundled with tldextract.
_extract = tldextract.TLDExtract(suffix_list_urls=())


@dataclass
class Reason:
    code: str
    text: str
    points: int

    def as_dict(self) -> dict:
        return {"code": self.code, "text": self.text, "points": self.points}


@dataclass
class LinkResult:
    url: str
    domain: str  # registered domain, e.g. esewa-kyc.xyz (or the IP for IP links)
    trusted: bool = False
    organization: str | None = None
    reasons: list[Reason] = field(default_factory=list)
    host: str = ""  # full host name, e.g. login.esewa-kyc.xyz (used for the DNS lookup)
    # Filled by the reputation checks (Phase 4, link_reputation.py):
    ip: str | None = None
    country: str | None = None  # server country from OTX - information only, adds no points
    otx_reports: int | None = None
    shared_hosting: bool = False  # server IP is a shared CDN/hosting network
    domain_age_days: int | None = None  # filled by the domain-age check (Phase 5); None = unknown
    registrar: str | None = None
    blocked: bool = False  # on the admin panel block list (Phase 10A) - always Dangerous
    # Replies kept for MIRA's prompt (backend flow B3); None = no reply (lookup failed, timed out or switched off)
    otx_counts: dict | None = None  # {"pulses", "passive_dns", "urls", "files", "whitelisted"}
    otx_text: str | None = None  # "0 Pulses 7 Passive DNS 0 URLS 0 Files"
    whois: dict | None = None  # WhoisDetails.to_dict()
    whois_text: str | None = None  # "Domain Information Domain: ... Registered On: ..." (full WHOIS text)

    @property
    def points(self) -> int:
        return sum(r.points for r in self.reasons)


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _normalize(url: str) -> str:
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        url = "http-unknown://" + url  # scheme not given in the SMS
    return url


def _trusted_match(host: str, registered: str) -> str | None:
    domains = trusted_data()["trusted_domains"]
    for candidate in (host, registered):
        if candidate in domains:
            return domains[candidate]
    # subdomain of a trusted domain, e.g. www.esewa.com.np or anything.gov.np
    for dom, org in domains.items():
        if host.endswith("." + dom):
            return org
    return None


def analyze_url(raw_url: str) -> LinkResult | None:
    """Return the rule findings for one URL, or None if it is not a valid web address."""
    parts = urlsplit(_normalize(raw_url))
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        return None

    data = trusted_data()
    reasons: list[Reason] = []

    try:
        ipaddress.ip_address(host)
        is_ip = True
    except ValueError:
        is_ip = False

    if is_ip:
        result = LinkResult(url=raw_url, domain=host, host=host)
        result.reasons.append(Reason("IP_HOST", "Link uses a bare IP address instead of a name", 25))
        if parts.scheme == "http":
            result.reasons.append(Reason("NO_HTTPS", "Link is not secure (no HTTPS)", 10))
        return result

    ext = _extract(host)
    if not ext.suffix or not ext.domain:
        return None
    registered = f"{ext.domain}.{ext.suffix}"
    result = LinkResult(url=raw_url, domain=registered, host=host)

    org = _trusted_match(host, registered)
    if org:
        result.trusted = True
        result.organization = org
        return result

    tld = ext.suffix.split(".")[-1]
    if tld in data["suspicious_tlds"]:
        reasons.append(Reason("SUSPICIOUS_TLD", f"Link uses a risky domain ending (.{tld})", 15))

    if registered in data["shorteners"]:
        reasons.append(Reason("SHORTENER", "Link is shortened, so the real destination is hidden", 10))

    if parts.scheme == "http":
        reasons.append(Reason("NO_HTTPS", "Link is not secure (no HTTPS)", 10))

    sub_count = len([s for s in ext.subdomain.split(".") if s]) if ext.subdomain else 0
    if sub_count > 3 or host.count("-") > 4:
        reasons.append(Reason("COMPLEX_HOST", "Link address is unusually long or complicated", 10))

    # Brand name inside a domain that does not belong to the brand: esewa-login.xyz
    name = ext.domain.lower()
    flat = (ext.subdomain + "." + name).lower()
    brand_hit = next(
        (b for b in data["brand_keywords"] if len(b) >= 4 and b in flat.replace("-", "")),
        None,
    )
    if brand_hit:
        reasons.append(Reason(
            "BRAND_IN_DOMAIN", f"Link pretends to be '{brand_hit}' but is not its official site", 25
        ))
    else:
        # Typosquat: esvva.com vs esewa.com.np (compare the name part only)
        for dom, org in data["trusted_domains"].items():
            trusted_name = _extract(dom).domain.lower()
            if len(trusted_name) < 4 or trusted_name == name:
                continue
            dist = levenshtein(name, trusted_name)
            if 1 <= dist <= 2 and abs(len(name) - len(trusted_name)) <= 2:
                reasons.append(Reason("TYPOSQUAT", f"Link looks like {dom} ({org}) but is spelled differently", 30))
                break

    result.reasons = reasons
    return result
