"""Loads and checks app/data/mira_prompt.json - everything about how we ask MIRA (Phase 7):
prompt template, phrases, answer options and the yes/no questions with their weights.
A broken file stops with a clear message instead of giving silently wrong verdicts."""
from __future__ import annotations

from dataclasses import dataclass

from .config_data import load_json

PROMPT_FILE = "mira_prompt.json"
LABELS = {"scam", "spam", "ham"}
TEMPLATE_KEYS = {"sender", "message", "link_official", "link_unofficial", "link_facts", "no_links", "asks", "signals", "question"}
PHRASE_KEYS = {"sender_unknown", "sender_mobile", "sender_company", "sender_name", "age", "age_unknown", "otx_reports",
               "otx_none", "otx_unknown", "asks_nothing", "ask_click", "ask_secret", "ask_money", "signal_prize", "signal_urgent"}


@dataclass(frozen=True)
class Option:
    id: str
    label: str  # scam | spam | ham
    text: str  # what MIRA reads
    reason: str  # short text shown to the user, e.g. "fake prize, gift or lottery"


@dataclass(frozen=True)
class YesNoQuestion:
    id: str
    text: str
    weight_yes: float  # points added at P(yes)=1 (negative = makes the message look safer)
    answers: tuple[str, str] = ("yes", "no")
    kind: str = "plain"


@dataclass(frozen=True)
class PromptConfig:
    version: str
    not_sure_below: float
    template: dict[str, str]
    phrases: dict[str, str]
    options: tuple[Option, ...]
    questions: tuple[YesNoQuestion, ...]
    questions_read: str = "full"  # "full" = questions read the whole prompt, "message" = only the message (faster)


class PromptConfigError(RuntimeError):
    pass


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise PromptConfigError(f"{PROMPT_FILE}: {message}")


def parse_prompt_config(data: dict) -> PromptConfig:
    _check(isinstance(data.get("version"), str) and data["version"], "missing 'version'")
    template, phrases = data.get("template") or {}, data.get("phrases") or {}
    _check(not (TEMPLATE_KEYS - template.keys()), f"template is missing {sorted(TEMPLATE_KEYS - template.keys())}")
    _check(not (PHRASE_KEYS - phrases.keys()), f"phrases is missing {sorted(PHRASE_KEYS - phrases.keys())}")

    options = []
    for o in data.get("options") or []:
        _check({"id", "label", "text", "reason"} <= o.keys(), f"option {o.get('id')!r} needs id, label, text, reason")
        _check(o["label"] in LABELS, f"option {o['id']!r} has unknown label {o['label']!r}")
        options.append(Option(o["id"], o["label"], o["text"], o["reason"]))
    _check(len({o.id for o in options}) == len(options), "option ids must be unique")
    _check({o.label for o in options} == LABELS, "options need at least one scam, one spam and one ham answer")

    questions = []
    for q in data.get("questions") or []:
        _check({"id", "text", "weight_yes"} <= q.keys(), f"question {q.get('id')!r} needs id, text, weight_yes")
        answers = tuple(q.get("answers", ("yes", "no")))
        _check(len(answers) == 2, f"question {q['id']!r} needs exactly two answers")
        questions.append(YesNoQuestion(q["id"], q["text"], float(q["weight_yes"]), answers, q.get("kind", "plain")))
    _check(len({q.id for q in questions}) == len(questions), "question ids must be unique")

    threshold = float(data.get("not_sure_below", 0.5))
    _check(0 < threshold < 1, "not_sure_below must be between 0 and 1")
    reads = data.get("questions_read", "full")
    _check(reads in ("full", "message"), "questions_read must be 'full' or 'message'")
    return PromptConfig(data["version"], threshold, dict(template), dict(phrases), tuple(options), tuple(questions), reads)


def prompt_config() -> PromptConfig:
    """Cached; call config_data.reload() after editing the file while the server runs."""
    return parse_prompt_config(load_json(PROMPT_FILE))
