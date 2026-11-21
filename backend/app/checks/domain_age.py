"""Domain age (Phase 5): when was a link's domain registered?

Scam sites are usually only days or weeks old. Order of lookups:
1. cache (domain_cache table, domain_cache_days)
2. RDAP via rdap.org (modern, free JSON version of WHOIS; redirects to the right registry)
3. classic WHOIS on port 43 (whois.iana.org tells which server handles the TLD)
Domains with no public data (most .np domains) are "unknown" and never counted as risky.
Any network problem raises DomainAgeUnavailable so the check is marked skipped, never crashes."""
from __future__ import annotations

import logging
import re
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session, sessionmaker

from ..db import DomainCache

log = logging.getLogger("checkscam.domain_age")

RDAP_URL = "https://rdap.org/domain/{domain}"
IANA_WHOIS = "whois.iana.org"

# TLDs known to have no public registration dates -> skip network calls, answer "unknown".
NO_PUBLIC_DATA_TLDS = {"np"}

# WHOIS lines that hold the registration date, in the many spellings registries use.
CREATED_RE = re.compile(
    r"^\s*(?:creation date|created(?: on| date)?|registered(?: on| date)?|registration (?:date|time)|"
    r"domain registration date|record created|commencement date)\s*[:.]\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
EXPIRES_RE = re.compile(
    r"^\s*(?:registry expiry date|expir(?:y|ation|es)(?: date| on)?|paid-till|renewal date)\s*[:.]\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
REGISTRAR_RE = re.compile(r"^\s*registrar(?: name)?\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
REFER_RE = re.compile(r"^\s*(?:refer|whois)\s*:\s*(\S+)", re.IGNORECASE | re.MULTILINE)
NOT_FOUND_RE = re.compile(r"no match|not found|no data found|no entries found|status:\s*free|is available", re.IGNORECASE)

DATE_FORMATS = (
    "%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%d-%b-%Y", "%d.%m.%Y", "%d/%m/%Y", "%Y%m%d",
    "%Y-%m-%d %H:%M:%S", "%d-%b-%Y %H:%M:%S", "%Y.%m.%d %H:%M:%S", "%a %b %d %H:%M:%S %Y",
)


class DomainAgeUnavailable(Exception):
    """reason: timeout | error"""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class DomainAge:
    domain: str
    registered_at: datetime | None = None
    expires_at: datetime | None = None
    registrar: str | None = None
    source: str = "none"  # rdap | whois | none (no public data)
    from_cache: bool = False

    def age_days(self, now: datetime | None = None) -> int | None:
        if self.registered_at is None:
            return None
        now = now or datetime.now(timezone.utc)
        return max(0, (now - self.registered_at).days)


def parse_date(text: str | None) -> datetime | None:
    """Parses the date formats seen in RDAP and WHOIS answers. Returns UTC or None."""
    if not text:
        return None
    raw = text.strip().split(" (")[0].strip()
    iso = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    cleaned = re.sub(r"\s+(UTC|GMT|[+-]\d{2}:?\d{2})$", "", raw)
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def parse_rdap(domain: str, data: dict) -> DomainAge:
    events = {e.get("eventAction"): e.get("eventDate") for e in data.get("events") or [] if isinstance(e, dict)}
    registrar = None
    for ent in data.get("entities") or []:
        if "registrar" in (ent.get("roles") or []):
            for item in (ent.get("vcardArray") or [None, []])[1]:
                if isinstance(item, list) and item and item[0] == "fn":
                    registrar = str(item[-1])
            registrar = registrar or ent.get("handle")
    return DomainAge(
        domain=domain,
        registered_at=parse_date(events.get("registration")),
        expires_at=parse_date(events.get("expiration")),
        registrar=registrar,
        source="rdap",
    )


def parse_whois(domain: str, text: str) -> DomainAge:
    created = CREATED_RE.search(text)
    expires = EXPIRES_RE.search(text)
    registrar = REGISTRAR_RE.search(text)
    return DomainAge(
        domain=domain,
        registered_at=parse_date(created.group(1)) if created else None,
        expires_at=parse_date(expires.group(1)) if expires else None,
        registrar=registrar.group(1)[:200] if registrar else None,
        source="whois",
    )


def _whois_query(server: str, query: str, timeout: float) -> str:
    """Raw WHOIS over TCP port 43 (separate function so tests can replace it)."""
    with socket.create_connection((server, 43), timeout=timeout) as sock:
        sock.settimeout(timeout)
        encoded = query.encode("ascii") if query.isascii() else query.encode("idna")  # idna: non-Latin domains
        sock.sendall(encoded + b"\r\n")
        chunks = []
        while True:
            data = sock.recv(4096)
            if not data:
                break
            chunks.append(data)
            if sum(len(c) for c in chunks) > 200_000:
                break
    return b"".join(chunks).decode("utf-8", errors="replace")


class DomainAgeClient:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        timeout: float = 10.0,
        cache_days: int = 7,
        http: httpx.Client | None = None,
    ):
        self.session_factory = session_factory
        self.timeout = timeout
        self.cache_days = cache_days
        self.http = http or httpx.Client(timeout=timeout, follow_redirects=True)

    def lookup(self, domain: str) -> DomainAge:
        domain = domain.lower().strip(".")
        with self.session_factory() as session:
            row = session.get(DomainCache, domain)
            if row is not None:
                checked = row.checked_at if row.checked_at.tzinfo else row.checked_at.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) - checked < timedelta(days=self.cache_days):
                    return DomainAge(domain, _utc(row.registered_at), _utc(row.expires_at), row.registrar,
                                     row.source, from_cache=True)

            info = self._fetch(domain)
            session.merge(DomainCache(
                domain=domain, registered_at=info.registered_at, expires_at=info.expires_at,
                registrar=info.registrar, source=info.source, checked_at=datetime.now(timezone.utc),
            ))
            session.commit()
            return info

    def _fetch(self, domain: str) -> DomainAge:
        if domain.rsplit(".", 1)[-1] in NO_PUBLIC_DATA_TLDS:
            return DomainAge(domain)  # unknown, no network call

        rdap_failed = False
        try:
            resp = self.http.get(RDAP_URL.format(domain=domain), timeout=self.timeout,
                                 headers={"Accept": "application/rdap+json"})
            if resp.status_code == 200:
                info = parse_rdap(domain, resp.json())
                if info.registered_at:
                    return info
            elif resp.status_code != 404:
                rdap_failed = True
        except httpx.TimeoutException:
            rdap_failed = True
        except (httpx.HTTPError, ValueError):
            rdap_failed = True

        # Fallback: classic WHOIS
        try:
            tld = domain.rsplit(".", 1)[-1]
            refer = REFER_RE.search(_whois_query(IANA_WHOIS, tld, self.timeout))
            if not refer:
                return DomainAge(domain)  # TLD has no WHOIS server -> unknown
            text = _whois_query(refer.group(1), domain, self.timeout)
        except socket.timeout:
            raise DomainAgeUnavailable("timeout") from None
        except OSError:
            if rdap_failed:
                raise DomainAgeUnavailable("error") from None
            return DomainAge(domain)

        if NOT_FOUND_RE.search(text) and not CREATED_RE.search(text):
            return DomainAge(domain, source="whois")  # registry says: no such domain
        return parse_whois(domain, text)


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def age_points(age_days: int | None) -> tuple[int, str | None]:
    """Under 7 days +35, under 30 days +25 (replaces the 7-day rule). Unknown -> 0."""
    if age_days is None:
        return 0, None
    if age_days < 7:
        return 35, "NEW_DOMAIN_7"
    if age_days < 30:
        return 25, "NEW_DOMAIN_30"
    return 0, None
