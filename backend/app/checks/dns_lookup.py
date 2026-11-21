"""DNS lookup for link checks: domain -> public IP addresses, with a hard timeout.

Private / internal addresses (127.x, 10.x, 192.168.x, 172.16-31.x, ::1, link-local...) are
returned separately and are NEVER sent to any outside service."""
from __future__ import annotations

import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field

# Shared small pool so a hanging DNS server cannot block request threads.
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="dns")


@dataclass
class DnsResult:
    host: str
    public_ips: list[str] = field(default_factory=list)
    private_ips: list[str] = field(default_factory=list)
    error: str | None = None  # "timeout" | "not_found" | None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.public_ips)


def is_public_ip(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_global
    except ValueError:
        return False


def _resolve(host: str) -> list[str]:
    """Plain system resolver call (separate function so tests can replace it)."""
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    seen: list[str] = []
    for info in infos:
        ip = info[4][0]
        if ip not in seen:
            seen.append(ip)
    return seen


def lookup(host: str, timeout: float = 2.0) -> DnsResult:
    host = (host or "").strip().lower().rstrip(".")
    result = DnsResult(host=host)
    if not host:
        result.error = "not_found"
        return result

    # Already an IP address (e.g. http://185.12.34.56/login)
    try:
        ipaddress.ip_address(host)
        ips = [host]
    except ValueError:
        try:
            ips = _pool.submit(_resolve, host).result(timeout=timeout)
        except FutureTimeout:
            result.error = "timeout"
            return result
        except (socket.gaierror, UnicodeError, OSError):
            result.error = "not_found"
            return result

    for ip in ips:
        (result.public_ips if is_public_ip(ip) else result.private_ips).append(ip)
    if not result.public_ips and not result.private_ips:
        result.error = "not_found"
    return result
