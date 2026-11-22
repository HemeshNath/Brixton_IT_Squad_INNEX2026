"""Builds what MIRA reads for one SMS (Phase 7) - wording comes from app/data/mira_prompt.json.

1. build_state(): the "state" - the masked message plus the facts our other checks found, e.g.

    SMS from: a mobile number (not a company sender ID)
    Message: "Dear customer, your eSewa wallet will be BLOCKED today. Update: <LINK 1>"
    Link 1 (esewa-kyc.xyz): NOT an official site of a known company. Facts: ... domain registered
      3 days ago; 3 threat report(s) in AlienVault OTX.
    The message asks the reader to: click a link.

2. build_questions(): one batch for MIRA = the main question (which answer option fits?) plus the
   yes/no questions, all about the same state.
3. interpret(): turns MIRA's answers into P(scam/spam/ham), the most likely scam type, each
   question's P(yes) and the weighted question points.

The message text is masked (no personal data) and quoted, so MIRA treats it as data; it is only ever
part of the state, never an answer option, and MIRA alone never sets the final verdict."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .links import LinkResult
from .mira import MiraAnswer, Question
from .mira_config import PromptConfig, prompt_config
from .senders import is_trusted_sender
from .textprep import asks_for_secret, extract_urls

MAX_MESSAGE_CHARS = 700

PHONE_SENDER_RE = re.compile(r"^\+?\d[\d\s-]{6,}$")
MONEY_REQUEST_RE = re.compile(
    r"\b(pay|send|transfer|deposit|fee|charge|processing fee|registration fee|pathau\w*|tirnu\w*|"
    r"rakam|paisa pathau\w*)\b|शुल्क|पठाउ\w*|तिर्नु\w*",
    re.IGNORECASE,
)
PRIZE_RE = re.compile(r"\b(won|winner|prize|lottery|lucky draw|gift|jitnu|inam|cashback|reward)\b|जित्नु\w*|उपहार|पुरस्कार|इनाम",
                      re.IGNORECASE)
URGENT_RE = re.compile(r"\b(urgent|immediately|today|within 24 hours|blocked|suspended|deactivated|turunta|arrest)\b"
                       r"|तुरुन्त|रोक्का|निलम्बन|बन्द", re.IGNORECASE)


def _cfg(cfg: PromptConfig | None) -> PromptConfig:
    return cfg or prompt_config()


def describe_sender(sender: str, cfg: PromptConfig | None = None) -> str:
    ph = _cfg(cfg).phrases
    s = (sender or "").strip()
    if not s or s.startswith("<"):
        return ph["sender_unknown"]
    if PHONE_SENDER_RE.match(s):
        return ph["sender_mobile"]
    if is_trusted_sender(s):
        return ph["sender_company"].format(sender=s)
    return ph["sender_name"].format(sender=s)


def describe_link(n: int, link: LinkResult, skipped: set[str], cfg: PromptConfig | None = None) -> str:
    c = _cfg(cfg)
    t, ph = c.template, c.phrases
    if link.trusted:
        return t["link_official"].format(n=n, domain=link.domain, organization=link.organization)
    facts = [r.text[0].lower() + r.text[1:] for r in link.reasons if r.points > 0 and not r.code.startswith(("OTX_", "NEW_DOMAIN"))]
    if link.domain_age_days is not None:
        days = link.domain_age_days
        facts.append(ph["age"].format(days=days, day_word="day" if days == 1 else "days"))
    elif "whois" in skipped:
        facts.append(ph["age_unknown"])
    if link.otx_reports:
        facts.append(ph["otx_reports"].format(count=link.otx_reports))
    elif link.otx_reports == 0:
        facts.append(ph["otx_none"])
    elif "otx" in skipped:
        facts.append(ph["otx_unknown"])
    text = t["link_unofficial"].format(n=n, domain=link.domain)
    return text + (t["link_facts"].format(facts="; ".join(facts)) if facts else "")


def requests_in(text: str, has_links: bool, cfg: PromptConfig | None = None) -> list[str]:
    ph = _cfg(cfg).phrases
    asks = []
    if has_links:
        asks.append(ph["ask_click"])
    if asks_for_secret(text):
        asks.append(ph["ask_secret"])
    if MONEY_REQUEST_RE.search(text):
        asks.append(ph["ask_money"])
    return asks


def signals_in(text: str, cfg: PromptConfig | None = None) -> list[str]:
    ph = _cfg(cfg).phrases
    signals = []
    if PRIZE_RE.search(text):
        signals.append(ph["signal_prize"])
    if URGENT_RE.search(text):
        signals.append(ph["signal_urgent"])
    return signals


def _clean_message(masked_text: str) -> str:
    """Links -> <LINK n>, one line, cut to MAX_MESSAGE_CHARS."""
    message = masked_text
    for n, url in enumerate(extract_urls(masked_text), 1):
        message = message.replace(url, f"<LINK {n}>")
    message = " ".join(message.split())
    if len(message) > MAX_MESSAGE_CHARS:
        message = message[:MAX_MESSAGE_CHARS] + "…"
    return message


def build_message_state(masked_text: str, cfg: PromptConfig | None = None) -> str:
    """Only the quoted message line - what the yes/no questions read when questions_read = "message"."""
    return _cfg(cfg).template["message"].format(message=_clean_message(masked_text))


def build_state(masked_text: str, links: list[LinkResult], sender: str = "", skipped: list[str] | None = None,
                cfg: PromptConfig | None = None) -> str:
    """The full state text for MIRA. `masked_text` must already have personal data removed."""
    c = _cfg(cfg)
    t = c.template
    skipped_set = set(skipped or [])
    lines = [t["sender"].format(sender=describe_sender(sender, c)), build_message_state(masked_text, c)]
    for n, link in enumerate(links, 1):
        lines.append(describe_link(n, link, skipped_set, c))
    if not links:
        lines.append(t["no_links"])
    asks = requests_in(masked_text, bool(links), c)
    lines.append(t["asks"].format(asks="; ".join(asks) if asks else c.phrases["asks_nothing"]))
    signals = signals_in(masked_text, c)
    if signals:
        lines.append(t["signals"].format(signals="; ".join(signals)))
    return "\n".join(lines)


# ---------------------------------------------------------------- questions for MIRA (7.4 / 7.5)
def build_questions(state: str, cfg: PromptConfig | None = None, message_state: str | None = None) -> list[Question]:
    """One batch: [main question with all answer options, reading the full state] + one yes/no question
    per config question. With questions_read = "message" the yes/no questions read only `message_state`
    (much shorter -> faster on the laptop CPU)."""
    c = _cfg(cfg)
    batch = [Question(state, [o.text for o in c.options])]
    q_state = message_state if (c.questions_read == "message" and message_state) else state
    for q in c.questions:
        batch.append(Question(c.template["question"].format(state=q_state, question=q.text), list(q.answers), q.kind))
    return batch


@dataclass
class MiraResult:
    """MIRA's answers for one SMS, ready for scoring (Phase 8)."""
    probabilities: dict[str, float]  # {"scam": .., "spam": .., "ham": ..} - sums of the option probabilities
    label: str  # most likely of scam / spam / ham
    top_option: str  # id of the single most likely answer option
    scam_type: str | None  # user-facing reason of the most likely scam option, e.g. "fake prize, gift or lottery"
    scam_type_probability: float
    not_sure: bool
    question_yes: dict[str, float] = field(default_factory=dict)  # question id -> P(yes)
    question_points: float = 0.0  # sum of weight_yes * P(yes)
    prompt_version: str = ""
    option_probabilities: dict[str, float] = field(default_factory=dict)  # option id -> probability (test lab)


def interpret(answers: list[MiraAnswer], cfg: PromptConfig | None = None) -> MiraResult:
    c = _cfg(cfg)
    main, rest = answers[0], answers[1:]
    by_option = {o.id: main.probabilities.get(o.text, 0.0) for o in c.options}
    probs = {lab: round(sum(p for o in c.options if o.label == lab for p in [by_option[o.id]]), 4)
             for lab in ("scam", "spam", "ham")}
    scam_options = [o for o in c.options if o.label == "scam"]
    top_scam = max(scam_options, key=lambda o: by_option[o.id])
    top_option = max(by_option, key=by_option.get)

    question_yes, points = {}, 0.0
    for q, ans in zip(c.questions, rest):
        p_yes = ans.probabilities.get(q.answers[0], 0.0)
        question_yes[q.id] = round(p_yes, 4)
        points += q.weight_yes * p_yes
    return MiraResult(
        probabilities=probs,
        label=max(probs, key=probs.get),
        top_option=top_option,
        scam_type=top_scam.reason if probs["scam"] >= max(probs["spam"], probs["ham"]) else None,
        scam_type_probability=round(by_option[top_scam.id], 4),
        not_sure=max(probs.values()) < c.not_sure_below,
        question_yes=question_yes,
        question_points=round(points, 2),
        prompt_version=c.version,
        option_probabilities={k: round(v, 4) for k, v in by_option.items()},
    )
