"""Reputation checks for the links in a message:
DNS -> server IP -> AlienVault OTX (IP and domain)                      (Phase 4)
RDAP/WHOIS -> domain age                                                (Phase 5)

Adds its findings to each LinkResult (ip, country, otx_reports and extra reasons), so the scorer
treats them like the other link rules. All links are checked in parallel with one overall time
limit; anything slow or failing is reported in `skipped` instead of breaking the check.
Backend flow B3: every link - official ones too - is sent to OTX (pulses, passive DNS, URLs, files) and
WHOIS (full details) at the same time, and both replies are kept on the link (otx_text, whois_text) for
MIRA's prompt. Official links get no risk points from these lookups."""
from __future__ import annotations

import ipaddress
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout, wait

from .config_data import trusted
from .dns_lookup import lookup
from .domain_age import DomainAgeClient, DomainAgeUnavailable, age_points
from .links import LinkResult, Reason
from .otx import OtxClient, OtxUnavailable, otx_points

log = logging.getLogger("checkscam.reputation")

_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="linkrep")
_side = ThreadPoolExecutor(max_workers=6, thread_name_prefix="linkrep-ip")  # the server-IP check, beside the counts


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def shared_hosting_asns() -> set[str]:
    return {a.upper() for a in trusted().get("shared_hosting_asns", [])}


def _left(deadline: float | None) -> float | None:
    return None if deadline is None else max(0.05, deadline - time.monotonic())


def _check_one(link: LinkResult, otx: OtxClient | None, dns_timeout: float, deadline: float | None = None) -> set[str]:
    """Checks one link in place. Returns the names of checks that had to be skipped.
    The server-IP check runs at the same time as the four OTX numbers of the domain; parts not back by
    `deadline` are left out (their calls keep running and fill the cache for next time)."""
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
        ip_link = _is_ip(link.domain)
        server = _side.submit(otx.ip, ip) if ip and not ip_link else None
        answered = False
        try:
            # B3: the four OTX numbers for MIRA's prompt (the domain, or the IP for links without a name)
            counts = otx.counts("ip" if ip_link else "domain", link.domain, wait_seconds=_left(deadline))
            link.otx_counts, link.otx_text = counts.to_dict(), counts.text
            answered = True
            if counts.pulses is not None and not counts.whitelisted:
                reports = counts.pulses
            if ip_link and ip:  # country / network of an IP link (already in the memory cache)
                server_info = otx.ip(ip)
                link.country = server_info.country
        except OtxUnavailable as exc:
            log.info("OTX skipped: %s", exc.reason)
        if server is not None:
            try:
                info = server.result(timeout=_left(deadline))
                answered = True
                if info.asn in shared_hosting_asns():
                    # Shared CDN/hosting IP (Cloudflare, AWS...): its reports and country belong to
                    # millions of other sites, so only the domain's reports count.
                    link.shared_hosting = True
                else:
                    reports = max(reports, info.reported)
                    link.country = info.country
            except (OtxUnavailable, FutureTimeout) as exc:
                log.info("OTX server-IP check skipped: %s", getattr(exc, "reason", "timeout"))
        if answered:
            link.otx_reports = reports
        else:
            skipped.add("otx")

    points = 0 if link.trusted else otx_points(reports)
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
    if info.details is not None:
        link.whois, link.whois_text = info.details.to_dict(), info.text
    else:
        link.whois_text = f"Domain: {link.domain} No public WHOIS data"
    points, code = age_points(link.domain_age_days)
    if code and not link.trusted:
        days = link.domain_age_days
        link.reasons.append(Reason(code, f"Link's domain was registered only {days} day{'s' if days != 1 else ''} ago", points))
    return set()


def _otx_reputation(link: LinkResult, otx: OtxClient) -> set[str]:
    """URL reputation from AlienVault OTX in ONE call: the threat reports ("pulses") of the link's domain (or of the IP
    for links without a name). Fast message checks use only this - no DNS, server-IP, passive-DNS or WHOIS lookups."""
    try:
        info = otx.ip(link.domain) if _is_ip(link.domain) else otx.domain(link.domain)
    except OtxUnavailable as exc:
        log.info("OTX skipped: %s", exc.reason)
        return {"otx"}
    link.otx_reports = info.reported
    link.otx_counts = {"pulses": info.pulse_count, "whitelisted": info.whitelisted}
    link.otx_text = f"{info.pulse_count} Pulses" + (" (whitelisted by OTX as a known safe site)" if info.whitelisted else "")
    points = 0 if link.trusted else otx_points(info.reported)
    if points:
        link.reasons.append(Reason(
            "OTX_REPORTED", f"Link's domain has {info.reported} threat report(s) in AlienVault OTX", points))
    return set()


def check_otx_only(links: list[LinkResult], otx: OtxClient | None, total_timeout: float = 2.0) -> list[str]:
    """Every link -> one OTX call, all at the same time, at most `total_timeout` seconds. A slow answer keeps running
    and fills the cache for next time. Returns ["otx"] if any link got no answer."""
    if not links:
        return []
    if otx is None:
        return ["otx"]
    jobs = [_pool.submit(_otx_reputation, link, otx) for link in links]
    done, not_done = wait(jobs, timeout=total_timeout)
    skipped: set[str] = set()
    for f in done:
        try:
            skipped |= f.result()
        except Exception:  # never let one broken link break the whole check
            log.exception("OTX link check failed")
            skipped.add("otx")
    if not_done:
        log.warning("OTX check timed out")
        skipped.add("otx")
    return sorted(skipped)


def check_links(
    links: list[LinkResult],
    otx: OtxClient | None,
    dns_timeout: float = 2.0,
    total_timeout: float = 6.0,
    ages: DomainAgeClient | None = None,
) -> list[str]:
    """Runs the reputation checks (OTX, WHOIS / domain age) for all links in parallel.
    Returns the sorted list of skipped checks ("dns", "otx", "whois"), [] when everything ran."""
    targets = list(links)
    if not targets:
        return []
    deadline = time.monotonic() + total_timeout - 0.15  # OTX parts stop waiting just before the time limit
    jobs = {_pool.submit(_check_one, link, otx, dns_timeout, deadline): "otx" for link in targets}
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
