"""Editable lists for the admin panel (Phase 10A step A6).

  trusted_domain  official / allowed sites (domain -> company). Built-in entries come from trusted.json.
  trusted_sender  company sender IDs whose plain messages are trusted. Built-in entries come from trusted.json.
  blocked_domain  sites that are always Dangerous (domain or IP, subdomains included).
  blocked_sender  sender IDs / phone numbers whose messages are always Dangerous.

The panel never edits trusted.json: it stores additions and "switched-off built-in" rows in `list_entries`, and the
effective lists (file + changes) are applied live - the checks use them for the very next message."""
from __future__ import annotations

import copy
import ipaddress
import logging
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .checks import config_data
from .checks.config_data import load_json
from .db import ListEntry

log = logging.getLogger("checkscam.lists")


@dataclass(frozen=True)
class ListInfo:
    name: str
    title: str
    value_label: str
    label_label: str
    builtin_key: str | None  # key in trusted.json, or None (no built-in entries)
    kind: str  # domain | sender_id | sender
    help: str


LISTS = {
    "trusted_domain": ListInfo("trusted_domain", "Official & allowed sites", "Domain", "Company", "trusted_domains",
                               "domain", "Links to these sites (and their subdomains) count as official and add no "
                                         "points. The company name is used for the brand-mismatch rule."),
    "trusted_sender": ListInfo("trusted_sender", "Trusted sender IDs", "Sender ID", "Company", "trusted_senders",
                               "sender_id", "Plain messages from these company sender IDs count as safe. "
                                            "Phone numbers cannot be trusted (they are easy to fake)."),
    "blocked_domain": ListInfo("blocked_domain", "Blocked sites", "Domain or IP", "Reason", None, "domain",
                               "A link to one of these sites (or a subdomain) is always Dangerous."),
    "blocked_sender": ListInfo("blocked_sender", "Blocked senders", "Sender ID or phone number", "Reason", None,
                               "sender", "Messages from these senders are always Dangerous."),
}

_DOMAIN_RE = re.compile(r"^(?=.{3,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9-]{2,63}$")


def normalize_domain(raw: str) -> str:
    v = raw.strip().lower()
    v = re.sub(r"^[a-z][a-z0-9+.-]*://", "", v)  # scheme
    v = re.split(r"[/?#]", v, maxsplit=1)[0]  # path, query
    v = v.split("@")[-1]  # user:pass@
    if v.count(":") == 1:
        v = v.split(":")[0]  # port
    v = v.strip(".")
    if v.startswith("www."):
        v = v[4:]
    if v and not v.isascii():
        try:
            v = v.encode("idna").decode("ascii")
        except UnicodeError:
            return ""
    return v


def normalize_sender_id(raw: str) -> str:
    return re.sub(r"[^a-z0-9]", "", raw.lower())


def normalize_phone_or_id(raw: str) -> str:
    """Phone numbers -> digits (Nepal +977 removed); sender IDs -> lower-case letters and digits."""
    compact = re.sub(r"[\s()+.-]", "", raw)
    if compact.isdigit():
        if len(compact) == 13 and compact.startswith("977"):
            compact = compact[3:]
        return compact
    return normalize_sender_id(raw)


def _is_ip(v: str) -> bool:
    try:
        ipaddress.ip_address(v)
        return True
    except ValueError:
        return False


def normalize(list_name: str, raw: str) -> tuple[str, str | None]:
    """(normalised value, problem or None)."""
    info = LISTS[list_name]
    if info.kind == "domain":
        v = normalize_domain(raw)
        if _is_ip(v):
            return (v, None) if list_name == "blocked_domain" else (v, "An IP address cannot be an official site.")
        return (v, None) if _DOMAIN_RE.match(v) else (v, "That does not look like a domain, e.g. example.com.np")
    if info.kind == "sender_id":
        v = normalize_sender_id(raw)
        if len(v) < 3:
            return v, "Sender ID must have at least 3 letters or digits."
        if v.isdigit():
            return v, "Phone numbers cannot be trusted senders (they are easy to fake). Use the company's sender ID."
        return v, None
    v = normalize_phone_or_id(raw)
    if v.isdigit():
        return (v, None) if 7 <= len(v) <= 15 else (v, "A phone number needs 7 to 15 digits.")
    return (v, None) if len(v) >= 3 else (v, "Sender ID must have at least 3 letters or digits.")


def builtin(list_name: str) -> dict[str, str]:
    """value -> label of the entries in trusted.json (empty for the block lists)."""
    key = LISTS[list_name].builtin_key
    if key is None:
        return {}
    data = load_json(config_data.TRUSTED_FILE).get(key, {})
    return dict(data) if isinstance(data, dict) else {v: "" for v in data}


def effective(rows: list[ListEntry], list_name: str) -> dict[str, str]:
    out = builtin(list_name)
    for r in rows:
        if r.list != list_name:
            continue
        if r.active:
            out[r.value] = r.label or out.get(r.value, "")
        else:
            out.pop(r.value, None)
    return out


@dataclass
class Blocklist:
    domains: set[str] = field(default_factory=set)
    senders: set[str] = field(default_factory=set)

    def domain_blocked(self, host: str) -> bool:
        h = (host or "").lower().strip(".")
        if h.startswith("www."):
            h = h[4:]
        return any(h == d or h.endswith("." + d) for d in self.domains)

    def sender_blocked(self, sender: str) -> bool:
        return bool(sender) and normalize_phone_or_id(sender) in self.senders


def rows(db: Session) -> list[ListEntry]:
    return list(db.scalars(select(ListEntry).order_by(ListEntry.id)))


def apply(app) -> None:
    """Makes the effective lists live: trusted lists for the link / sender checks, block lists for the pipeline."""
    try:
        with app.state.sessionmaker() as db:
            all_rows = rows(db)
    except Exception as exc:  # noqa: BLE001 - e.g. table not migrated yet: built-in lists only
        log.warning("List changes not loaded (%s); using trusted.json only", type(exc).__name__)
        all_rows = []
    base = load_json(config_data.TRUSTED_FILE)
    if any(r.list in ("trusted_domain", "trusted_sender") for r in all_rows):
        merged = copy.deepcopy(base)
        merged["trusted_domains"] = effective(all_rows, "trusted_domain")
        merged["trusted_senders"] = sorted(effective(all_rows, "trusted_sender"))
        config_data.set_trusted_override(merged)
    else:
        config_data.set_trusted_override(None)
    app.state.checkers.blocklist = Blocklist(set(effective(all_rows, "blocked_domain")),
                                             set(effective(all_rows, "blocked_sender")))
