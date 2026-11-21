"""AlienVault OTX client: has this IP or domain been reported as malicious?

- Asks OTX's free API (needs OTX_API_KEY) for the number of threat reports ("pulses"), the
  server country and whether OTX whitelists the indicator (well-known safe sites).
- Every answer is cached in the otx_cache table for otx_cache_hours, so the same link never
  costs a second call; a daily limit stops calls before the free quota runs out.
- Any problem (no key, limit, rate limit, timeout, server error) raises OtxUnavailable so the
  caller can mark the check as skipped instead of crashing."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ..db import OtxCache

log = logging.getLogger("checkscam.otx")

BASE_URL = "https://otx.alienvault.com/api/v1/indicators"


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


def otx_points(reports: int) -> int:
    """1-2 OTX threat reports +20, 3 or more +35."""
    if reports <= 0:
        return 0
    return 20 if reports <= 2 else 35


class OtxClient:
    def __init__(
        self,
        api_key: str,
        session_factory: sessionmaker[Session],
        timeout: float = 4.0,
        daily_limit: int = 5000,
        cache_hours: int = 24,
        http: httpx.Client | None = None,
    ):
        self.api_key = api_key
        self.session_factory = session_factory
        self.timeout = timeout
        self.daily_limit = daily_limit
        self.cache_hours = cache_hours
        self.http = http or httpx.Client(timeout=timeout)

    def ip(self, ip: str) -> OtxInfo:
        return self._lookup("ip", ip, f"{BASE_URL}/IPv4/{ip}/general" if ":" not in ip else f"{BASE_URL}/IPv6/{ip}/general")

    def domain(self, domain: str) -> OtxInfo:
        return self._lookup("domain", domain.lower(), f"{BASE_URL}/domain/{domain.lower()}/general")

    # --- internals ---
    def _calls_today(self, session: Session) -> int:
        start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        return session.scalar(select(func.count()).select_from(OtxCache).where(OtxCache.checked_at >= start)) or 0

    def _lookup(self, kind: str, value: str, url: str) -> OtxInfo:
        key = f"{kind}:{value}"
        with self.session_factory() as session:
            row = session.get(OtxCache, key)
            if row is not None:
                checked = row.checked_at if row.checked_at.tzinfo else row.checked_at.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) - checked < timedelta(hours=self.cache_hours):
                    cached = row.result or {}
                    return OtxInfo(value, kind, row.pulse_count, row.country, row.whitelisted,
                                   cached.get("pulse_names", []), cached.get("asn"), from_cache=True)

            if not self.api_key:
                raise OtxUnavailable("no_key")
            if self._calls_today(session) >= self.daily_limit:
                log.warning("OTX daily limit reached (%s)", self.daily_limit)
                raise OtxUnavailable("daily_limit")

            try:
                resp = self.http.get(url, headers={"X-OTX-API-KEY": self.api_key}, timeout=self.timeout)
            except httpx.TimeoutException:
                raise OtxUnavailable("timeout") from None
            except httpx.HTTPError as exc:
                log.info("OTX request failed: %s", type(exc).__name__)
                raise OtxUnavailable("error") from None

            if resp.status_code == 404:  # OTX knows nothing about it -> no reports
                info = OtxInfo(value, kind)
            elif resp.status_code == 429:
                raise OtxUnavailable("rate_limited")
            elif resp.status_code != 200:
                log.info("OTX returned HTTP %s", resp.status_code)
                raise OtxUnavailable("error")
            else:
                try:
                    info = parse_general(kind, value, resp.json())
                except ValueError:
                    raise OtxUnavailable("error") from None

            session.merge(OtxCache(
                indicator=key, kind=kind, country=info.country, pulse_count=info.pulse_count,
                whitelisted=info.whitelisted, result={"pulse_names": info.pulse_names, "asn": info.asn},
                checked_at=datetime.now(timezone.utc),
            ))
            session.commit()
            return info
