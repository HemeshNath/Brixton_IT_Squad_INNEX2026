"""MIRA's prompt in the owner's format (backend flow B4).

The wording lives in app/data/mira_prompt_owner.txt, so it can be changed without touching code. Its five places
${source} ${content} ${url} ${ip_reputation} ${domain_information} are filled from the Context variables
(context.py: B2/B3). Everything else - intro, the two examples, the risk ranges and the five questions - is used
exactly as written.

The message is personal-data-masked before it gets here and only ever fills ${content}: it is data inside the
prompt, never an instruction or an answer option."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from string import Template

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "data" / "mira_prompt_owner.txt"
PLACES = ("source", "content", "url", "ip_reputation")
VERSION = "owner-v2"  # v2: only the four Context lines (old MIRA removed; WHOIS no longer used for messages)


@lru_cache(maxsize=1)
def template() -> Template:
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    missing = [p for p in PLACES if "${" + p + "}" not in text]
    if missing:
        raise ValueError(f"mira_prompt_owner.txt lacks: {', '.join(missing)}")
    return Template(text.strip())


def reload() -> None:
    template.cache_clear()


def _one_line(value: str) -> str:
    """Keeps each Context field on its own line, as in the owner's format."""
    return " ".join(str(value or "").split())


def build_prompt(context: dict[str, str]) -> str:
    """The full prompt text for MIRA from the Context variables."""
    return template().substitute({p: _one_line(context.get(p, "")) for p in PLACES})
