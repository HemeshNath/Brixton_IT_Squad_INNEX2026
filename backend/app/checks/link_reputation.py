"""Reputation checks for the links in a message:
DNS -> server IP -> AlienVault OTX (IP and domain)                      (Phase 4)
RDAP/WHOIS -> domain age                                                (Phase 5)

Adds its findings to each LinkResult (ip, country, otx_reports and extra reasons), so the scorer
treats them like the other link rules. All links are checked in parallel with one overall time
limit; anything slow or failing is reported in `skipped` instead of breaking the check.
Trusted domains (esewa.com.np, ...) are not looked up at all."""
from __future__ import annotations

import ipaddress
import logging
from concurrent.futures import ThreadPoolExecutor, wait

from .config_data import trusted
from .dns_lookup import lookup
from .domain_age import DomainAgeClient, DomainAgeUnavailable, age_points
from .links import LinkResult, Reason
from .otx import OtxClient, OtxUnavailable, otx_points

log = logging.getLogger("checkscam.reputation")

_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="linkrep")


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def shared_hosting_asns() -> set[str]:
    return {a.upper() for a in trusted().get("shared_hosting_asns", [])}


def _check_one(link: LinkResult, otx: OtxClient | None, dns_timeout: float) -> set[str]:
    """Checks one link in place. Returns the names of checks that had to be skipped."""
    skipped: set[str] = set()
    dns = lookup(link.host or link.domain, timeout=dns_timeout)
    if dns.error == "timeout":
        skipped.add("dns")
    ip = dns.public_ips[0] if dns.public_ips else None  # private IPs are never sent to OTX
    link.ip = ip

    reports = 0
    if otx is None:
        skipped.add("otx")
    else:
        try:
            if ip:
                info = otx.ip(ip)
                if info.asn in shared_hosting_asns():
                    # Shared CDN/hosting IP (Cloudflare, AWS...): its reports and country belong to
                    # millions of other sites, so only the domain check below counts.
                    link.shared_hosting = True
                else:
                    reports = max(reports, info.reported)
                    link.country = info.country
            if link.domain and link.domain != ip:
                reports = max(reports, otx.domain(link.domain).reported)
            link.otx_reports = reports
        except OtxUnavailable as exc:
            log.info("OTX skipped: %s", exc.reason)
            skipped.add("otx")

    points = otx_points(reports)
    if points:
        link.reasons.append(Reason(
            "OTX_REPORTED", f"Link's server or domain has {reports} threat report(s) in AlienVault OTX", points))

    return skipped


def _check_age(link: LinkResult, ages: DomainAgeClient) -> set[str]:
    """Domain age for one link (skipped for IP links). Adds NEW_DOMAIN_* reasons."""
    try:
        info = ages.lookup(link.domain)
    except DomainAgeUnavailable as exc:
        log.info("domain age skipped: %s", exc.reason)
        return {"whois"}
    link.domain_age_days = info.age_days()
    link.registrar = info.registrar
    points, code = age_points(link.domain_age_days)
    if code:
        days = link.domain_age_days
        link.reasons.append(Reason(code, f"Link's domain was registered only {days} day{'s' if days != 1 else ''} ago", points))
    return set()


def check_links(
    links: list[LinkResult],
    otx: OtxClient | None,
    dns_timeout: float = 2.0,
    total_timeout: float = 6.0,
    ages: DomainAgeClient | None = None,
) -> list[str]:
    """Runs the reputation checks (OTX, domain age) for all untrusted links in parallel.
    Returns the sorted list of skipped checks ("dns", "otx", "whois"), [] when everything ran."""
    targets = [l for l in links if not l.trusted]
    if not targets:
        return []
    jobs = {_pool.submit(_check_one, link, otx, dns_timeout): "otx" for link in targets}
    if ages is not None:
        for link in targets:
            if link.domain and not _is_ip(link.domain):  # IP links have no domain to look up
                jobs[_pool.submit(_check_age, link, ages)] = "whois"
    done, not_done = wait(jobs, timeout=total_timeout)
    skipped: set[str] = set()
    for f in done:
        try:
            skipped |= f.result()
        except Exception:  # never let one broken link break the whole check
            log.exception("link reputation check failed")
            skipped.add(jobs[f])
    for f in not_done:
        log.warning("%s check timed out", jobs[f])
        skipped.add(jobs[f])
    return sorted(skipped)
