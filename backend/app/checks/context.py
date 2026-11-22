"""The "Context" block of MIRA's prompt (backend flow B2/B3), built from one message:

    Source: WhatsApp
    Content: <the message, personal data masked>
    URL: <the links in it>                       or "No URL"
    IP Reputation: <OTX reply per link>          or "No IP"     (no link in the message)
    Domain Information: <full WHOIS per link>    or "No Domain"

A link whose lookup gave no reply (failed, too slow, switched off) says so ("No reply from OTX" / "No reply from
WHOIS"), so MIRA never reads a missing reply as a clean one. Several links: one part per site, "Link 1 (domain): ..."
(a message with "https://x.xyz/a" and the bare "x.xyz" is one site, shown once)."""
from __future__ import annotations

import ipaddress

from .links import LinkResult
from .textprep import mask_pii

NO_URL, NO_IP, NO_DOMAIN = "No URL", "No IP", "No Domain"
NO_OTX_REPLY, NO_WHOIS_REPLY = "No reply from OTX", "No reply from WHOIS"


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _ip_reputation(link: LinkResult) -> str:
    return link.otx_text or NO_OTX_REPLY


def _domain_information(link: LinkResult) -> str:
    if _is_ip(link.domain):
        return f"{NO_DOMAIN} (the link uses the IP address {link.domain})"
    return link.whois_text or NO_WHOIS_REPLY


def _per_link(links: list[LinkResult], part) -> str:
    if len(links) == 1:
        return part(links[0])
    return " ".join(f"Link {n} ({link.domain}): {part(link)}" for n, link in enumerate(links, 1))


def _one_per_site(links: list[LinkResult]) -> list[LinkResult]:
    seen, out = set(), []
    for link in links:
        key = (link.host or link.domain).lower()
        if key not in seen:
            seen.add(key)
            out.append(link)
    return out


def build_context(source: str, masked_text: str, links: list[LinkResult]) -> dict[str, str]:
    """{"source", "content", "url", "ip_reputation", "domain_information"} - the replies stored in variables."""
    links = _one_per_site(links)
    return {
        "source": source,
        "content": masked_text,
        "url": " ".join(mask_pii(l.url) for l in links) if links else NO_URL,
        "ip_reputation": _per_link(links, _ip_reputation) if links else NO_IP,
        "domain_information": _per_link(links, _domain_information) if links else NO_DOMAIN,
    }
