"""Full WHOIS details of a domain (backend flow B3) - the "Domain Information" of MIRA's prompt.

Three sources give the same WhoisDetails:
- WhoisXML API JSON (when its key is set),
- RDAP: the registry's record (dates, status, name servers, registrar, abuse contact) plus the registrar's own
  RDAP record (registrant / admin / tech contacts - usually a privacy service),
- classic WHOIS text (port 43) as the last fallback.

render() writes it in the owner's layout, e.g.
    Domain Information Domain: gzukw.buzz Registered On: 2026-10-19 Expires On: 2027-10-19 Updated On: 2026-10-24
    Status: client transfer prohibited server transfer prohibited Name Servers: adi.ns.cloudflare.com ...
    Registrar Information Registrar: NameSilo, LLC IANA ID: 1479 Email: ... Abuse Email: ... Abuse Phone: ...
    Registrant Contact Name: ... Organization: ... Street: ... City: ... State: ... Postal Code: ... Country: US
    Phone: ... Email: ... Administrative Contact ... Technical Contact ...
Fields a source does not give are left out (never invented). This is public registration data of the website,
not data of the CheckScam user."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime

CONTACT_FIELDS = (("name", "Name"), ("organization", "Organization"), ("street", "Street"), ("city", "City"),
                  ("state", "State"), ("postal_code", "Postal Code"), ("country", "Country"), ("phone", "Phone"),
                  ("email", "Email"))


@dataclass
class Contact:
    name: str = ""
    organization: str = ""
    street: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    country: str = ""
    phone: str = ""
    email: str = ""

    def empty(self) -> bool:
        return not any(asdict(self).values())


@dataclass
class WhoisDetails:
    domain: str
    registered_on: str = ""  # YYYY-MM-DD
    expires_on: str = ""
    updated_on: str = ""
    status: list[str] = field(default_factory=list)
    name_servers: list[str] = field(default_factory=list)
    registrar: str = ""
    iana_id: str = ""
    registrar_email: str = ""
    abuse_email: str = ""
    abuse_phone: str = ""
    registrant: Contact = field(default_factory=Contact)
    admin: Contact = field(default_factory=Contact)
    tech: Contact = field(default_factory=Contact)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "WhoisDetails":
        d = dict(d)
        for k in ("registrant", "admin", "tech"):
            d[k] = Contact(**{f: str(v or "") for f, v in (d.get(k) or {}).items() if f in Contact.__dataclass_fields__})
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def fill_missing(self, other: "WhoisDetails") -> None:
        """Takes every field this one lacks from `other` (contacts as a whole)."""
        for k in ("registered_on", "expires_on", "updated_on", "status", "name_servers", "registrar", "iana_id",
                  "registrar_email", "abuse_email", "abuse_phone"):
            if not getattr(self, k):
                setattr(self, k, getattr(other, k))
        for k in ("registrant", "admin", "tech"):
            if getattr(self, k).empty():
                setattr(self, k, getattr(other, k))


def render(d: WhoisDetails) -> str:
    """The details as one line of text, in the owner's layout."""
    parts = ["Domain Information", f"Domain: {d.domain}"]

    def add(label: str, value) -> None:
        value = " ".join(value) if isinstance(value, list) else value
        if value:
            parts.append(f"{label}: {value}")

    add("Registered On", d.registered_on)
    add("Expires On", d.expires_on)
    add("Updated On", d.updated_on)
    add("Status", d.status)
    add("Name Servers", d.name_servers)
    if d.registrar or d.iana_id or d.registrar_email or d.abuse_email or d.abuse_phone:
        parts.append("Registrar Information")
        add("Registrar", d.registrar)
        add("IANA ID", d.iana_id)
        add("Email", d.registrar_email)
        add("Abuse Email", d.abuse_email)
        add("Abuse Phone", d.abuse_phone)
    for title, contact in (("Registrant Contact", d.registrant), ("Administrative Contact", d.admin),
                           ("Technical Contact", d.tech)):
        if not contact.empty():
            parts.append(title)
            for key, label in CONTACT_FIELDS:
                add(label, getattr(contact, key))
    return " ".join(parts)


# ------------------------------------------------------------------------------------------------ helpers
def _day(value) -> str:
    """Any date text -> YYYY-MM-DD ('' if unknown)."""
    from .domain_age import parse_date  # local import: domain_age imports this module

    if isinstance(value, datetime):
        return value.date().isoformat()
    dt = parse_date(str(value)) if value else None
    return dt.date().isoformat() if dt else ""


def _status_words(value: str) -> str:
    """'clientTransferProhibited https://icann.org/...' -> 'client transfer prohibited'."""
    word = str(value).split()[0] if str(value).split() else ""
    if " " in str(value).strip() and not str(value).split()[1].startswith("http"):
        return str(value).strip().lower()  # already words, e.g. RDAP "client transfer prohibited"
    return re.sub(r"(?<!^)(?=[A-Z])", " ", word).lower()


def _clean(value) -> str:
    text = " ".join(str(value or "").split())
    return "" if text.upper().startswith("REDACTED") or text.lower() in {"data protected", "not disclosed"} else text


# ------------------------------------------------------------------------------------------------ RDAP
def _vcard(entity: dict) -> dict:
    """RDAP jCard -> {fn, org, street, city, state, postal_code, country, phone, email}."""
    out: dict[str, str] = {}
    items = (entity.get("vcardArray") or [None, []])[1] if isinstance(entity.get("vcardArray"), list) else []
    for item in items or []:
        if not isinstance(item, list) or len(item) < 4:
            continue
        kind, params, value = item[0], item[1] if isinstance(item[1], dict) else {}, item[-1]
        if kind == "fn" and not out.get("fn"):
            out["fn"] = _clean(value)
        elif kind == "org" and not out.get("org"):
            out["org"] = _clean(value if isinstance(value, str) else " ".join(map(str, value)))
        elif kind == "email" and not out.get("email"):
            out["email"] = _clean(value)
        elif kind == "tel" and not out.get("phone") and params.get("type", "voice") in ("voice", ["voice"], "work"):
            out["phone"] = _clean(str(value).removeprefix("tel:"))
        elif kind == "adr":
            if isinstance(params.get("cc"), str):
                out["country"] = params["cc"].upper()
            if isinstance(value, list) and len(value) >= 7:
                street = value[2]
                street = " ".join(map(str, street)) if isinstance(street, list) else str(street)
                pre = " ".join(str(v) for v in value[:2] if isinstance(v, str))
                out["street"] = _clean(f"{pre} {street}")
                out["city"], out["state"], out["postal_code"] = _clean(value[3]), _clean(value[4]), _clean(value[5])
                if not out.get("country") and value[6]:
                    out["country"] = _clean(value[6])
    return out


def _contact(card: dict) -> Contact:
    return Contact(name=card.get("fn", ""), organization=card.get("org", ""), street=card.get("street", ""),
                   city=card.get("city", ""), state=card.get("state", ""), postal_code=card.get("postal_code", ""),
                   country=card.get("country", ""), phone=card.get("phone", ""), email=card.get("email", ""))


def parse_rdap_details(domain: str, data: dict) -> WhoisDetails:
    """One RDAP domain record (registry or registrar) -> WhoisDetails."""
    events = {e.get("eventAction"): e.get("eventDate") for e in data.get("events") or [] if isinstance(e, dict)}
    d = WhoisDetails(
        domain=domain,
        registered_on=_day(events.get("registration")),
        expires_on=_day(events.get("expiration")),
        updated_on=_day(events.get("last changed")),
        status=[_status_words(s) for s in data.get("status") or [] if isinstance(s, str)],
        name_servers=[str(n.get("ldhName", "")).lower() for n in data.get("nameservers") or []
                      if isinstance(n, dict) and n.get("ldhName")],
    )
    for ent in data.get("entities") or []:
        if not isinstance(ent, dict):
            continue
        roles = ent.get("roles") or []
        card = _vcard(ent)
        if "registrar" in roles:
            d.registrar = card.get("fn") or card.get("org") or str(ent.get("handle") or "")
            d.registrar_email = card.get("email", "")
            d.iana_id = next((str(p.get("identifier")) for p in ent.get("publicIds") or []
                              if isinstance(p, dict) and "IANA" in str(p.get("type", ""))), "")
            for sub in ent.get("entities") or []:
                if isinstance(sub, dict) and "abuse" in (sub.get("roles") or []):
                    abuse = _vcard(sub)
                    d.abuse_email, d.abuse_phone = abuse.get("email", ""), abuse.get("phone", "")
        if "registrant" in roles:
            d.registrant = _contact(card)
        if "administrative" in roles:
            d.admin = _contact(card)
        if "technical" in roles:
            d.tech = _contact(card)
    return d


def registrar_rdap_url(data: dict) -> str | None:
    """The registrar's own RDAP record for this domain (link rel="related"), if the registry gives one."""
    for link in data.get("links") or []:
        if isinstance(link, dict) and link.get("rel") == "related" and str(link.get("href", "")).startswith("https://") \
                and "/domain/" in str(link.get("href")):
            return str(link["href"])
    return None


# ------------------------------------------------------------------------------------------------ WhoisXML
def _xml_contact(c: dict | None) -> Contact:
    c = c or {}
    street = " ".join(_clean(c.get(k)) for k in ("street1", "street2", "street3", "street4") if _clean(c.get(k)))
    return Contact(name=_clean(c.get("name")), organization=_clean(c.get("organization")), street=street,
                   city=_clean(c.get("city")), state=_clean(c.get("state")), postal_code=_clean(c.get("postalCode")),
                   country=_clean(c.get("countryCode") or c.get("country")), phone=_clean(c.get("telephone")),
                   email=_clean(c.get("email")))


def parse_whoisxml_details(domain: str, data: dict) -> WhoisDetails:
    rec = data.get("WhoisRecord") or {}
    reg = rec.get("registryData") or {}

    def pick(key: str):
        return rec.get(key) or reg.get(key)

    status = pick("status") or ""
    ns = (pick("nameServers") or {}).get("hostNames") or []
    d = WhoisDetails(
        domain=domain,
        registered_on=_day(pick("createdDate")),
        expires_on=_day(pick("expiresDate")),
        updated_on=_day(pick("updatedDate")),
        status=[_status_words(s) for s in (status.split() if isinstance(status, str) else status) if s
                and not str(s).startswith("http")],
        name_servers=[str(n).lower() for n in ns],
        registrar=_clean(pick("registrarName")),
        iana_id=_clean(pick("registrarIANAID")),
        registrar_email=_clean(pick("contactEmail")),
        registrant=_xml_contact(rec.get("registrant") or reg.get("registrant")),
        admin=_xml_contact(rec.get("administrativeContact") or reg.get("administrativeContact")),
        tech=_xml_contact(rec.get("technicalContact") or reg.get("technicalContact")),
    )
    for src in (rec, reg):
        for i in range(1, 4):
            name, value = str(src.get(f"customField{i}Name") or ""), _clean(src.get(f"customField{i}Value"))
            if "Abuse" in name and "Email" in name and not d.abuse_email:
                d.abuse_email = value
            elif "Abuse" in name and "Phone" in name and not d.abuse_phone:
                d.abuse_phone = value
    return d


# ------------------------------------------------------------------------------------------------ WHOIS text
_LINE_RE = re.compile(r"^[ \t]*([A-Za-z][A-Za-z /]*?)[ \t]*:[ \t]*(.*?)[ \t\r]*$", re.MULTILINE)  # one line only


def _fields(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for key, value in _LINE_RE.findall(text):
        value = _clean(value)
        if value:
            out.setdefault(key.strip().lower(), []).append(value)
    return out


def parse_whois_text_details(domain: str, text: str) -> WhoisDetails:
    """ICANN-style WHOIS text ("Creation Date: ...", "Registrant Name: ...") -> WhoisDetails."""
    f = _fields(text)

    def one(*keys: str) -> str:
        for k in keys:
            if f.get(k):
                return f[k][0]
        return ""

    def contact(prefix: str) -> Contact:
        return Contact(name=one(f"{prefix} name"), organization=one(f"{prefix} organization"),
                       street=" ".join(f.get(f"{prefix} street", [])), city=one(f"{prefix} city"),
                       state=one(f"{prefix} state/province", f"{prefix} state"),
                       postal_code=one(f"{prefix} postal code"), country=one(f"{prefix} country"),
                       phone=one(f"{prefix} phone"), email=one(f"{prefix} email"))

    return WhoisDetails(
        domain=domain,
        registered_on=_day(one("creation date", "created", "created on", "registered on", "registration date")),
        expires_on=_day(one("registry expiry date", "registrar registration expiration date", "expiration date",
                            "expiry date", "expires on")),
        updated_on=_day(one("updated date", "last updated", "updated on")),
        status=[_status_words(s) for s in f.get("domain status", []) or f.get("status", [])],
        name_servers=[s.split()[0].lower() for s in f.get("name server", []) or f.get("nserver", [])],
        registrar=one("registrar", "registrar name"),
        iana_id=one("registrar iana id"),
        abuse_email=one("registrar abuse contact email"),
        abuse_phone=one("registrar abuse contact phone"),
        registrant=contact("registrant"),
        admin=contact("admin"),
        tech=contact("tech"),
    )
