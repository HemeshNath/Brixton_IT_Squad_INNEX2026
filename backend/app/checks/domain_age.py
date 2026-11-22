"""Domain age (Phase 5) and full WHOIS details (backend flow B3): when and by whom was a link's domain registered?

Scam sites are usually only days or weeks old. Order of lookups:
1. cache (domain_cache table, domain_cache_days)
2. WhoisXML API when its key is set
3. RDAP via rdap.org (modern, free JSON version of WHOIS; redirects to the right registry), plus the registrar's
   own RDAP record for the contacts
4. classic WHOIS on port 43 (whois.iana.org tells which server handles the TLD)
Each answer also carries WhoisDetails (whois_details.py) - the "Domain Information" text for MIRA's prompt.
Domains with no public data (most .np domains) are "unknown" and never counted as risky.
Any network problem raises DomainAgeUnavailable so the check is marked skipped, never crashes."""
from __future__ import annotations

import logging
import re
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from ..db import DomainCache
from .memcache import MemoryCache, save_later
from .whois_details import (WhoisDetails, parse_rdap_details, parse_whois_text_details, parse_whoisxml_details,
                            registrar_rdap_url, render)

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
    source: str = "none"  # whoisxml | rdap | whois | none (no public data)
    from_cache: bool = False
    details: WhoisDetails | None = None  # full WHOIS details (B3); None = no public data

    @property
    def text(self) -> str | None:
        """Full WHOIS details in the owner's layout, or None when there is no public data."""
        return render(self.details) if self.details else None

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


WHOISXML_URL = "https://www.whoisxmlapi.com/whoisserver/WhoisService"


def parse_whoisxml(domain: str, data: dict) -> DomainAge:
    """WhoisXML API answer (JSON). Dates may sit in WhoisRecord or in its registryData."""
    rec = data.get("WhoisRecord") or {}
    reg = rec.get("registryData") or {}
    return DomainAge(
        domain=domain,
        registered_at=parse_date(rec.get("createdDate") or reg.get("createdDate")),
        expires_at=parse_date(rec.get("expiresDate") or reg.get("expiresDate")),
        registrar=(rec.get("registrarName") or reg.get("registrarName") or None),
        source="whoisxml",
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
        whois_api_key: str = "",
        save_in_background: bool = False,
    ):
        self.save_in_background = save_in_background  # the server: True (checks never wait for the save)
        self.memory = MemoryCache()  # answers also kept in memory: the database is far away (B3 speed)
        self.session_factory = session_factory
        self.timeout = timeout
        self.cache_days = cache_days
        self.http = http or httpx.Client(timeout=timeout, follow_redirects=True)
        self.whois_api_key = whois_api_key  # WhoisXML API key from the admin panel / .env ("" = free lookups only)

    def lookup(self, domain: str) -> DomainAge:
        domain = domain.lower().strip(".")
        hit = self.memory.get(domain)
        if hit is not None:
            return hit

        with self.session_factory() as session:  # short: the connection goes back before the slow lookup
            row = session.get(DomainCache, domain)
            if row is not None:
                checked = row.checked_at if row.checked_at.tzinfo else row.checked_at.replace(tzinfo=timezone.utc)
                left = timedelta(days=self.cache_days) - (datetime.now(timezone.utc) - checked)
                # rows saved before B3 have no details -> look the domain up again
                if left.total_seconds() > 0 and (row.details or row.source == "none"):
                    details = WhoisDetails.from_dict(row.details) if row.details else None
                    info = DomainAge(domain, _utc(row.registered_at), _utc(row.expires_at), row.registrar,
                                     row.source, from_cache=True, details=details)
                    self.memory.put(domain, info, left.total_seconds())
                    return info

        info = self._fetch(domain)
        self.memory.put(domain, DomainAge(info.domain, info.registered_at, info.expires_at, info.registrar,
                                          info.source, from_cache=True, details=info.details),
                        self.cache_days * 86400)

        def store() -> None:
            with self.session_factory() as session:
                try:
                    session.merge(DomainCache(
                        domain=domain, registered_at=info.registered_at, expires_at=info.expires_at,
                        registrar=info.registrar, source=info.source, checked_at=datetime.now(timezone.utc),
                        details=info.details.to_dict() if info.details else None,
                    ))
                    session.commit()
                except IntegrityError:  # a parallel lookup of the same domain saved it first - fine
                    session.rollback()
                except OperationalError:  # database connection problem: keep the answer, skip caching it
                    session.rollback()
                    log.warning("could not save the domain age to the cache")

        if self.save_in_background:
            save_later(store)
        else:
            store()
        return info

    def _fetch(self, domain: str) -> DomainAge:
        if domain.rsplit(".", 1)[-1] in NO_PUBLIC_DATA_TLDS:
            return DomainAge(domain)  # unknown, no network call

        # Paid WHOIS API first when its key is set (Phase 10A); any problem -> the free lookups below
        if self.whois_api_key:
            try:
                resp = self.http.get(WHOISXML_URL, timeout=self.timeout, params={
                    "apiKey": self.whois_api_key, "domainName": domain, "outputFormat": "JSON"})
                if resp.status_code == 200:
                    data = resp.json()
                    info = parse_whoisxml(domain, data)
                    if info.registered_at:
                        info.details = parse_whoisxml_details(domain, data)
                        return info
            except (httpx.HTTPError, ValueError):
                log.info("WhoisXML API lookup failed; using RDAP/WHOIS")

        rdap_failed = False
        try:
            resp = self.http.get(RDAP_URL.format(domain=domain), timeout=self.timeout,
                                 headers={"Accept": "application/rdap+json"})
            if resp.status_code == 200:
                data = resp.json()
                info = parse_rdap(domain, data)
                if info.registered_at:
                    info.details = self._rdap_details(domain, data)
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
        info = parse_whois(domain, text)
        info.details = parse_whois_text_details(domain, text)
        return info

    def _rdap_details(self, domain: str, registry: dict) -> WhoisDetails:
        """Registry RDAP details, with the contacts (and anything else missing) from the registrar's RDAP record."""
        details = parse_rdap_details(domain, registry)
        url = registrar_rdap_url(registry)
        if url:
            try:
                resp = self.http.get(url, timeout=self.timeout, headers={"Accept": "application/rdap+json"})
                if resp.status_code == 200:
                    details.fill_missing(parse_rdap_details(domain, resp.json()))
            except (httpx.HTTPError, ValueError):
                log.info("registrar RDAP lookup failed; registry details only")
        return details


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def age_points(age_days: int | None) -> tuple[int, str | None]:
    """Points for a young domain from scoring.json (defaults: < 7 days +35, < 30 days +25, < 90 days +15;
    only the highest level counts). Unknown age -> 0, never risky."""
    from .rules import scoring_config  # local import: rules -> links, avoids a cycle at import time

    if age_days is None:
        return 0, None
    pts = scoring_config().domain_age
    if age_days < 7:
        return int(pts["under_7_days"]), "NEW_DOMAIN_7"
    if age_days < 30:
        return int(pts["under_30_days"]), "NEW_DOMAIN_30"
    if age_days < 90:
        return int(pts["under_90_days"]), "NEW_DOMAIN_90"
    return 0, None
