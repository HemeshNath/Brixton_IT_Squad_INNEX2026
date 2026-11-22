"""MIRA's answer to the owner's prompt -> Probability and Class (backend flow B5).

MIRA cannot write text; it can only choose between answers we give it. So, for one prompt (owner_prompt.py):
1. Class: MIRA chooses between the five risk classes (LOW RISK ... very harful) -> a probability per class.
   Probability (0-100) = sum of P(class) x the class's anchor (0, 30, 50, 70, 100), so a sure LOW RISK is 0% and
   a sure "very harful" is 100%. Class = the owner's range that Probability falls in (0-20 LOW RISK, 21-40 ...).
2. The five questions: MIRA answers each one Yes or No. The answers that are warnings (e.g. "urgency: Yes",
   "good domain: No") make the text in brackets, e.g. "100% (shows urgency, link has bad domain information)".
   Questions about the link (3, 4) only count when the message has a link.
The output has the owner's format: {"Probability": "100% (...)", "Class": "VERY HARMFUL"}.

Meaning of each class / question lives in app/data/owner_decision.json; the question texts are read from the
"Questions:" part of app/data/mira_prompt_owner.txt, so prompt and answers always match."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .mira import MiraAnswer, Question
from .owner_prompt import TEMPLATE_PATH

CONFIG_PATH = Path(__file__).resolve().parent.parent / "data" / "owner_decision.json"
QUESTION_LINE = re.compile(r"^\s*(\d+)\.\s*(.+?)\s*$")


@dataclass(frozen=True)
class OwnerClass:
    id: str
    option: str  # what MIRA chooses between
    label: str  # shown to people
    low: int
    high: int
    anchor: int


@dataclass(frozen=True)
class OwnerQuestion:
    n: int
    id: str
    code: str  # reason code sent to the phone when this answer is a warning, e.g. BAD_DOMAIN
    text: str  # as written in the prompt
    warning_when: str  # "Yes" | "No"
    needs_link: bool
    reason: str


@dataclass(frozen=True)
class OwnerConfig:
    version: str
    class_question: str
    question_format: str
    answers: tuple[str, str]
    classes: tuple[OwnerClass, ...]
    questions: tuple[OwnerQuestion, ...]
    warning_from: float
    no_warning_reason: str


def prompt_questions(template_text: str) -> dict[int, str]:
    """The numbered lines after "Questions:" in the prompt template."""
    _, _, part = template_text.partition("Questions:")
    out = {}
    for line in part.splitlines():
        m = QUESTION_LINE.match(line)
        if m:
            out[int(m.group(1))] = m.group(2)
    return out


@lru_cache(maxsize=1)
def config() -> OwnerConfig:
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    texts = prompt_questions(TEMPLATE_PATH.read_text(encoding="utf-8"))
    meta = raw["questions"]
    if set(texts) != {int(n) for n in meta}:
        raise ValueError(f"questions in mira_prompt_owner.txt {sorted(texts)} do not match owner_decision.json "
                         f"{sorted(int(n) for n in meta)}")
    classes = tuple(OwnerClass(c["id"], c["option"], c["label"], c["from"], c["to"], c["anchor"]) for c in raw["classes"])
    if [c.low for c in classes] != sorted(c.low for c in classes) or classes[0].low != 0 or classes[-1].high != 100:
        raise ValueError("classes must cover 0-100 in order")
    return OwnerConfig(
        version=raw["version"],
        class_question=raw["class_question"],
        question_format=raw["question_format"],
        answers=tuple(raw["answers"]),
        classes=classes,
        questions=tuple(OwnerQuestion(n, meta[str(n)]["id"], meta[str(n)].get("code", meta[str(n)]["id"].upper()),
                                      texts[n], meta[str(n)]["warning_when"],
                                      bool(meta[str(n)]["needs_link"]), meta[str(n)]["reason"]) for n in sorted(texts)),
        warning_from=float(raw["warning_from"]),
        no_warning_reason=raw["no_warning_reason"],
    )


def reload() -> None:
    config.cache_clear()


def build_batch(prompt: str, cfg: OwnerConfig | None = None) -> list[Question]:
    """One MIRA batch: [which class?] + one Yes/No question per prompt question, all about the same prompt."""
    cfg = cfg or config()
    batch = [Question(f"{prompt}\n\n{cfg.class_question}", [c.option for c in cfg.classes])]
    for q in cfg.questions:
        batch.append(Question(f"{prompt}\n\n{cfg.question_format.format(n=q.n, text=q.text)}", list(cfg.answers)))
    return batch


def class_for(probability: int, cfg: OwnerConfig | None = None) -> OwnerClass:
    cfg = cfg or config()
    for c in cfg.classes:
        if probability <= c.high:
            return c
    return cfg.classes[-1]


@dataclass
class OwnerDecision:
    probability: int  # 0-100
    class_id: str
    class_label: str
    reason: str  # the text in brackets
    warnings: list[str] = field(default_factory=list)
    class_probabilities: dict[str, float] = field(default_factory=dict)  # class id -> MIRA's probability
    question_yes: dict[str, float] = field(default_factory=dict)  # question id -> P(Yes)
    version: str = ""

    @property
    def display(self) -> dict[str, str]:
        """The owner's output format."""
        return {"Probability": f"{self.probability}% ({self.reason})", "Class": self.class_label}

    def as_dict(self) -> dict:
        return {"probability": self.probability, "class": self.class_id, "class_label": self.class_label,
                "reason": self.reason, "warnings": self.warnings, "display": self.display,
                "class_probabilities": self.class_probabilities, "question_yes": self.question_yes,
                "version": self.version}


def interpret(answers: list[MiraAnswer], has_link: bool, cfg: OwnerConfig | None = None) -> OwnerDecision:
    cfg = cfg or config()
    main, rest = answers[0], answers[1:]
    probs = {c.id: float(main.probabilities.get(c.option, 0.0)) for c in cfg.classes}
    total = sum(probs.values()) or 1.0
    probability = max(0, min(100, round(sum(probs[c.id] / total * c.anchor for c in cfg.classes))))
    chosen = class_for(probability, cfg)

    yes_word, no_word = cfg.answers
    question_yes, warnings = {}, []
    for q, ans in zip(cfg.questions, rest):
        p_yes = float(ans.probabilities.get(yes_word, 0.0))
        question_yes[q.id] = round(p_yes, 4)
        p_warning = p_yes if q.warning_when == yes_word else 1.0 - p_yes
        if p_warning >= cfg.warning_from and (has_link or not q.needs_link):
            warnings.append(q.reason)
    reason = ", ".join(warnings) if warnings else cfg.no_warning_reason
    return OwnerDecision(
        probability=probability, class_id=chosen.id, class_label=chosen.label,
        reason=reason[:1].upper() + reason[1:], warnings=warnings,
        class_probabilities={k: round(v, 4) for k, v in probs.items()},
        question_yes=question_yes, version=cfg.version,
    )
