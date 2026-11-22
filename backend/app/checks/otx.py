"""AlienVault OTX client: has this IP or domain been reported as malicious?

- Asks OTX's free API (needs OTX_API_KEY) for the number of threat reports ("pulses"), the
  server country and whether OTX whitelists the indicator (well-known safe sites).
- Every answer is cached in the otx_cache table for otx_cache_hours, so the same link never
  costs a second call; a daily limit stops calls before the free quota runs out.
- counts() (backend flow B3) gives the "IP Reputation" of MIRA's prompt in the owner's layout,
  "0 Pulses 7 Passive DNS 0 URLS 0 Files": 4 OTX sections (general, passive_dns, url_list, malware)
  fetched at the same time, each cached as its own row. A part that gives no reply is shown as
  "(no reply)" while the other numbers are still used.
- Speed (Supabase is far away): answers are also kept in memory, today's OTX calls are counted in
  memory (one database count per day), and cache rows can be saved in the background.
- Any problem (no key, limit, rate limit, timeout, server error) raises OtxUnavailable so the
  caller can mark the check as skipped instead of crashing."""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from ..db import OtxCache
from .memcache import MemoryCache, save_later

log = logging.getLogger("checkscam.otx")

BASE_URL = "https://otx.alienvault.com/api/v1/indicators"

# section name in the OTX URL -> short cache-key prefix (keeps "files:domain:<255 chars>" within the 270-char key)
SECTIONS = {"passive_dns": "pdns", "url_list": "urls", "malware": "files"}
# Passive DNS of big sites can take OTX 10-25 s. The check stops waiting at its time limit anyway, so these calls
# may run this long in the background and fill the cache - the next check of that site is then instant.
SECTION_TIMEOUT = 30.0
_sections_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="otxsec")


class OtxUnavailable(Exception):
    """reason: no_key | daily_limit | rate_limited | timeout | error"""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class OtxInfo:
    indicator: str
    kind: str  # ip | domain
    pulse_count: int = 0
    country: str | None = None
    whitelisted: bool = False
    pulse_names: list[str] = field(default_factory=list)
    asn: str | None = None  # network of an IP, e.g. "AS13335" (Cloudflare)
    from_cache: bool = False

    @property
    def reported(self) -> int:
        """Reports that count: whitelisted indicators (e.g. google.com) count as 0."""
        return 0 if self.whitelisted else self.pulse_count


def parse_general(kind: str, value: str, data: dict) -> OtxInfo:
    """Turns OTX's 'general' answer into the few fields we use."""
    pulses = data.get("pulse_info") or {}
    validation = data.get("validation") or []
    whitelisted = bool(data.get("false_positive")) or any(
        str(v.get("source", "")).lower() in {"whitelist", "false_positive"} for v in validation if isinstance(v, dict)
    )
    country = data.get("country_code") or data.get("country_code2")
    asn_text = str(data.get("asn") or "").split()
    return OtxInfo(
        indicator=value,
        kind=kind,
        pulse_count=int(pulses.get("count") or 0),
        country=country.upper() if isinstance(country, str) and len(country) == 2 else None,
        whitelisted=whitelisted,
        pulse_names=[p.get("name", "") for p in (pulses.get("pulses") or [])[:3] if isinstance(p, dict)],
        asn=asn_text[0].upper() if asn_text and asn_text[0].upper().startswith("AS") else None,
    )


@dataclass
class OtxCounts:
    """The four numbers OTX shows for an indicator - the "IP Reputation" line of MIRA's prompt.
    None = that part gave no reply (too slow or failed)."""
    indicator: str
    kind: str  # ip | domain
    pulses: int | None = 0
    passive_dns: int | None = 0
    urls: int | None = 0
    files: int | None = 0
    whitelisted: bool = False

    @property
    def text(self) -> str:
        def n(v):
            return "(no reply)" if v is None else v

        return f"{n(self.pulses)} Pulses {n(self.passive_dns)} Passive DNS {n(self.urls)} URLS {n(self.files)} Files"

    def to_dict(self) -> dict:
        return {"pulses": self.pulses, "passive_dns": self.passive_dns, "urls": self.urls, "files": self.files,
                "whitelisted": self.whitelisted}


def section_count(section: str, data: dict) -> int:
    """Number of entries in an OTX section answer (the total, not just the first page)."""
    if section == "passive_dns":
        return int(data.get("count") or len(data.get("passive_dns") or []))
    if section == "url_list":
        return int(data.get("full_size") or len(data.get("url_list") or []))
    if section == "malware":
        return int(data.get("count") or len(data.get("data") or []))
    raise ValueError(section)


def otx_points(reports: int) -> int:
    """Points from scoring.json (defaults: 1-2 OTX threat reports +20, 3 or more +35)."""
    from .rules import scoring_config  # local import avoids a cycle at import time

    if reports <= 0:
        return 0
    pts = scoring_config().otx
    return int(pts["one_or_two_reports"] if reports <= 2 else pts["three_or_more_reports"])


class OtxClient:
    def __init__(
        self,
        api_key: str,
        session_factory: sessionmaker[Session],
        timeout: float = 4.0,
        daily_limit: int = 5000,
        cache_hours: int = 24,
        http: httpx.Client | None = None,
        save_in_background: bool = False,
    ):
        self.api_key = api_key
        self.session_factory = session_factory
        self.timeout = timeout
        self.daily_limit = daily_limit
        self.cache_hours = cache_hours
        self.http = http or httpx.Client(timeout=timeout)
        self.save_in_background = save_in_background  # the server: True (checks never wait for the save)
        self.memory = MemoryCache()
        self._day = None  # UTC day of the in-memory call counter
        self._calls = 0
        self._count_lock = threading.Lock()

    def ip(self, ip: str) -> OtxInfo:
        return self._lookup("ip", ip, f"{BASE_URL}/IPv4/{ip}/general" if ":" not in ip else f"{BASE_URL}/IPv6/{ip}/general")

    def domain(self, domain: str) -> OtxInfo:
        return self._lookup("domain", domain.lower(), f"{BASE_URL}/domain/{domain.lower()}/general")

    def counts(self, kind: str, value: str, wait_seconds: float | None = None) -> OtxCounts:
        """Pulses, passive DNS, URLs and files for an IP or domain - the 4 OTX calls run at the same time.
        A part that fails or is not back within wait_seconds is None ("(no reply)"); the slow call keeps
        running and fills the cache for next time. Raises OtxUnavailable only if no part answered."""
        value = value.lower()
        base = self._base(kind, value)
        jobs = {"general": _sections_pool.submit(self.ip if kind == "ip" else self.domain, value)}
        jobs |= {sec: _sections_pool.submit(self._section, kind, value, sec, f"{base}/{sec}") for sec in SECTIONS}
        done, _ = wait_all(jobs.values(), wait_seconds)
        got, errors = {}, []
        for name, f in jobs.items():
            if f not in done:
                continue
            try:
                got[name] = f.result()
            except OtxUnavailable as exc:
                errors.append(exc)
        if not got:
            raise errors[0] if errors else OtxUnavailable("timeout")
        info = got.get("general")
        return OtxCounts(value, kind, info.pulse_count if info else None, got.get("passive_dns"),
                         got.get("url_list"), got.get("malware"), bool(info and info.whitelisted))

    @staticmethod
    def _base(kind: str, value: str) -> str:
        if kind == "ip":
            version = "IPv6" if ":" in value else "IPv4"
            return f"{BASE_URL}/{version}/{value}"
        return f"{BASE_URL}/domain/{value}"

    # --- internals ---
    def _calls_today(self, session: Session) -> int:
        start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        return session.scalar(select(func.count()).select_from(OtxCache).where(OtxCache.checked_at >= start)) or 0

    def _take_call(self, session: Session) -> None:
        """Counts one OTX call against the daily limit. The database is asked once per UTC day; after that the
        count lives in memory (one row per call in otx_cache, so the database count matches)."""
        today = datetime.now(timezone.utc).date()
        with self._count_lock:
            if self._day != today:
                self._calls, self._day = self._calls_today(session), today
            if self._calls >= self.daily_limit:
                log.warning("OTX daily limit reached (%s)", self.daily_limit)
                raise OtxUnavailable("daily_limit")
            self._calls += 1

    def _lookup(self, kind: str, value: str, url: str) -> OtxInfo:
        def load(row: OtxCache) -> OtxInfo:
            cached = row.result or {}
            return OtxInfo(value, kind, row.pulse_count, row.country, row.whitelisted,
                           cached.get("pulse_names", []), cached.get("asn"), from_cache=True)

        info = self._cached(
            f"{kind}:{value}", kind, url,
            parse=lambda data: parse_general(kind, value, data),
            empty=lambda: OtxInfo(value, kind),
            save=lambda i: {"country": i.country, "pulse_count": i.pulse_count, "whitelisted": i.whitelisted,
                            "result": {"pulse_names": i.pulse_names, "asn": i.asn}},
            load=load,
        )
        return info

    def _section(self, kind: str, value: str, section: str, url: str) -> int:
        return self._cached(
            f"{SECTIONS[section]}:{kind}:{value}", kind, url, timeout=max(self.timeout, SECTION_TIMEOUT),
            parse=lambda data: section_count(section, data),
            empty=lambda: 0,
            save=lambda n: {"pulse_count": 0, "result": {"count": n}},
            load=lambda row: int((row.result or {}).get("count", 0)),
        )

    def _cached(self, key: str, kind: str, url: str, parse, empty, save, load, timeout: float | None = None):
        """One OTX call with the memory cache, database cache, daily limit and error handling around it."""
        hit = self.memory.get(key)
        if hit is not None:
            return _as_cached(hit)

        if not self.api_key:
            raise OtxUnavailable("no_key")
        with self.session_factory() as session:  # short: the connection goes back before the slow OTX call
            row = session.get(OtxCache, key)
            if row is not None:
                checked = row.checked_at if row.checked_at.tzinfo else row.checked_at.replace(tzinfo=timezone.utc)
                left = timedelta(hours=self.cache_hours) - (datetime.now(timezone.utc) - checked)
                if left.total_seconds() > 0:
                    value = load(row)
                    self.memory.put(key, value, left.total_seconds())
                    return value
            self._take_call(session)

        try:
            resp = self.http.get(url, headers={"X-OTX-API-KEY": self.api_key}, timeout=timeout or self.timeout)
        except httpx.TimeoutException:
            raise OtxUnavailable("timeout") from None
        except httpx.HTTPError as exc:
            log.info("OTX request failed: %s", type(exc).__name__)
            raise OtxUnavailable("error") from None

        if resp.status_code == 404:  # OTX knows nothing about it -> no reports
            result = empty()
        elif resp.status_code == 429:
            raise OtxUnavailable("rate_limited")
        elif resp.status_code != 200:
            log.info("OTX returned HTTP %s", resp.status_code)
            raise OtxUnavailable("error")
        else:
            try:
                result = parse(resp.json())
            except (ValueError, TypeError, AttributeError):
                raise OtxUnavailable("error") from None

        self.memory.put(key, result, self.cache_hours * 3600)
        fields = save(result)

        def store() -> None:
            with self.session_factory() as session:
                try:
                    session.merge(OtxCache(indicator=key, kind=kind, checked_at=datetime.now(timezone.utc), **fields))
                    session.commit()
                except IntegrityError:  # a parallel lookup of the same indicator saved it first - fine
                    session.rollback()
                except OperationalError:  # database connection problem: keep the answer, skip caching it
                    session.rollback()
                    log.warning("could not save the OTX answer to the cache")

        if self.save_in_background:
            save_later(store)
        else:
            store()
        return result


def _as_cached(value):
    """A memory-cache answer, marked as coming from the cache (OtxInfo) - ints are returned as they are."""
    if isinstance(value, OtxInfo) and not value.from_cache:
        return OtxInfo(value.indicator, value.kind, value.pulse_count, value.country, value.whitelisted,
                       list(value.pulse_names), value.asn, from_cache=True)
    return value


def wait_all(futures, seconds: float | None):
    from concurrent.futures import wait
    return wait(list(futures), timeout=seconds)
