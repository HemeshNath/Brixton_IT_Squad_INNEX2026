"""The check pipeline - the owner's backend flow (B1-B6): one message in, MIRA's decision out.

  1. find the links in the original text, mask personal data             (textprep, links)
  2. every link -> OTX (pulses, passive DNS, URLs, files) and WHOIS
     (full details) at the same time; replies kept in variables          (link_reputation, context)
  3. the owner's MIRA prompt from those variables                         (owner_prompt)
  4. MIRA chooses one of the five risk classes and answers the five
     questions -> Probability (0-100) and Class                           (owner_decision)
  5. sender trust from the phone: saved contact / frequent sender lower the Probability, a first message from a
     new sender raises it; the Class follows the new Probability                (sender_trust)
MIRA alone decides (B6). If MIRA cannot answer (loading, too slow), the verdict is "unknown" - never a guess.

Switched off in B6 (code kept, may come back, e.g. whitelist rules from the admin panel): points scoring and hard
rules (scoring.py), admin block lists, known-scam memory, trusted senders / official sites, and the old MIRA
questions (mira_prompt.py). Anything slow or failing is listed in `checks_skipped`; the check never crashes."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from ..data_lists import Blocklist
from .context import build_context
from .domain_age import DomainAgeClient
from .known_scams import KnownScamMemory
from .link_reputation import check_links
from .links import analyze_url
from .mira import MiraService, MiraUnavailable
from .otx import OtxClient
from .owner_decision import OwnerDecision, build_batch, config as owner_config, interpret
from .owner_decision import class_for
from .owner_prompt import VERSION as PROMPT_VERSION, build_prompt
from .sender_trust import SenderFacts, adjustments as trust_adjustments, apply as apply_trust
from .textprep import extract_urls, mask_pii

log = logging.getLogger("checkscam.pipeline")

MAX_TEXT = 2000


@dataclass
class Checkers:
    """The outside services a check may use; any of them can be None (then that part is skipped)."""
    otx: OtxClient | None = None
    ages: DomainAgeClient | None = None
    mira: MiraService | None = None
    known: KnownScamMemory | None = None
    link_timeout: float = 2.0
    blocklist: Blocklist | None = None  # admin panel block lists (Phase 10A)
    switches: dict = field(default_factory=dict)  # admin panel on/off: otx, whois, mira, memory (missing = on)
    sender_trust: dict = field(default_factory=dict)  # admin panel sender-trust points (missing = sender_trust.DEFAULTS)

    def on(self, name: str):
        """The checker if it exists and is switched on, else None."""
        return getattr(self, {"whois": "ages", "memory": "known"}.get(name, name)) if self.switches.get(name, True) else None


def run_check(text: str, sender: str, checkers: Checkers, detail: bool = False, source: str = "SMS",
              sender_facts: SenderFacts | None = None) -> dict:
    """One message -> MIRA's decision. detail=True adds the prompt, MIRA's answer per class and question and the
    link facts (admin test lab). `source` is the readable app name ("SMS", "WhatsApp", ... - sources.source_name).
    `sender` is not used by the owner's flow (kept for the API and the saved history)."""
    t_start = time.perf_counter()
    timings: dict[str, int] = {}
    text = (text or "")[:MAX_TEXT]

    # 1. links (from the original text, so they survive masking) + masking
    links = [l for l in (analyze_url(u) for u in extract_urls(text)) if l is not None]
    masked = mask_pii(text)

    # 2. every link -> OTX + WHOIS at the same time
    skipped: list[str] = []
    t = time.perf_counter()
    otx, ages = checkers.on("otx"), checkers.on("whois")
    if links and (otx or ages):
        skipped += check_links(links, otx, total_timeout=checkers.link_timeout, ages=ages)
        if otx is None:
            skipped.append("otx")
        if ages is None:
            skipped.append("whois")
    elif links:
        skipped += ["otx", "whois"]
    timings["links"] = round((time.perf_counter() - t) * 1000)

    # 3. the owner's prompt from the replies
    context = build_context(source, masked, links)
    prompt = build_prompt(context)

    # 4. MIRA decides
    decision: OwnerDecision | None = None
    t = time.perf_counter()
    mira = checkers.on("mira")
    if mira is not None:
        try:
            decision = interpret(mira.batch(build_batch(prompt)), has_link=bool(links))
        except MiraUnavailable as exc:
            log.info("MIRA skipped: %s", exc.reason)
            skipped.append("mira")
    else:
        skipped.append("mira")
    timings["mira"] = round((time.perf_counter() - t) * 1000)
    timings["total"] = round((time.perf_counter() - t_start) * 1000)

    trust = trust_adjustments(sender_facts, checkers.sender_trust) if decision is not None else []
    result = _verdict(decision, bool(links), trust)
    result["mira_probability"] = decision.probability if decision is not None else None
    result["sender_trust"] = trust
    result.update({
        "links": [{"url": mask_pii(l.url), "domain": l.domain, "trusted": l.trusted, "ip": l.ip,
                   "country": l.country, "otx_reports": l.otx_reports, "domain_age_days": l.domain_age_days,
                   "otx_counts": l.otx_counts}
                  for l in links],
        "checks_skipped": sorted(set(skipped)),
        "model_version": checkers.mira.version if (checkers.mira and checkers.mira.ready) else "",
        "prompt_version": PROMPT_VERSION,
        "timings_ms": timings,
        "masked_text": masked,
        "source": source,
        "context": context,  # B2/B3: the replies kept in variables (not saved, not sent to phones)
        "mira_prompt": prompt,  # B4: the owner's prompt (not saved, not sent to phones)
    })
    if detail:
        result["detail"] = _detail(decision, prompt, links)
    log.info("check class=%s probability=%s links=%d skipped=%s total=%sms", result["risk_class"],
             result["score"], len(links), result["checks_skipped"], timings["total"])
    return result


# The phone app (until B7) knows only safe / suspicious / dangerous: each owner class maps to one of them.
LEGACY_VERDICT = {"low": "safe", "suspicious": "suspicious", "high": "suspicious",
                  "critical": "dangerous", "very_harmful": "dangerous"}

ADVICE = {
    "safe": "No scam signs found. Still, never share your OTP or PIN with anyone.",
    "suspicious": "Be careful. Do not click links or send money until you confirm with the "
                  "company through its official number or app.",
    "dangerous_secret": "This is very likely a scam. Never share your OTP, PIN or password with anyone.",
    "dangerous_link": "This is very likely a scam. Do not open the link or enter any details.",
    "dangerous": "This is very likely a scam. Do not reply, call back or send money.",
    "unknown": "CheckScam could not check this message. Be careful with links and never share your OTP or PIN.",
}


def _verdict(decision: OwnerDecision | None, has_link: bool, trust: list[dict] | None = None) -> dict:
    """The API fields from MIRA's decision (+ sender trust): the owner's output plus the older fields the phone
    app still reads."""
    if decision is None:
        return {"verdict": "unknown", "score": 0, "label": None, "risk_class": None, "risk_label": None,
                "owner_result": None, "probabilities": {}, "not_sure": True, "scam_type": None,
                "reasons": [{"code": "NOT_CHECKED", "text": "MIRA could not check this message", "points": 0}],
                "suggestion": ADVICE["unknown"], "scoring_version": owner_config().version}
    trust = trust or []
    probability = apply_trust(decision.probability, trust)
    chosen = class_for(probability)
    verdict = LEGACY_VERDICT[chosen.id]
    cfg = owner_config()
    codes = {q.reason: q.code for q in cfg.questions}
    if verdict == "dangerous":
        advice = ADVICE["dangerous_secret"] if "ASKS_CREDENTIALS" in {codes[w] for w in decision.warnings} else \
            ADVICE["dangerous_link"] if has_link else ADVICE["dangerous"]
    else:
        advice = ADVICE[verdict]
    reasons = [{"code": f"RISK_{chosen.id.upper()}",
                "text": f"MIRA: {chosen.label} ({probability}%)", "points": probability}]
    reasons += [{"code": codes[w], "text": w[:1].upper() + w[1:], "points": 0} for w in decision.warnings]
    reasons += trust
    texts = decision.warnings + [t["text"][:1].lower() + t["text"][1:] for t in trust]
    why = ", ".join(texts) if texts else cfg.no_warning_reason
    return {
        "verdict": verdict,
        "score": probability,
        "label": chosen.id,  # saved in the history's label column
        "risk_class": chosen.id,
        "risk_label": chosen.label,
        # {"Probability": "54% (...)", "Class": "HIGH RISK"}
        "owner_result": {"Probability": f"{probability}% ({why[:1].upper() + why[1:]})", "Class": chosen.label},
        "probabilities": decision.class_probabilities,
        "not_sure": False,
        "scam_type": None,
        "reasons": reasons,
        "suggestion": advice,
        "scoring_version": decision.version,
    }


def _detail(decision: OwnerDecision | None, prompt: str, links) -> dict:
    """Everything the admin test lab shows beyond the normal answer."""
    mira = None
    if decision is not None:
        cfg = owner_config()
        mira = {
            "prompt": prompt,
            "decision": decision.as_dict(),
            "classes": [{"id": c.id, "option": c.option, "label": c.label, "range": f"{c.low}-{c.high}",
                         "anchor": c.anchor, "p": decision.class_probabilities.get(c.id, 0.0)} for c in cfg.classes],
            "questions": [{"n": q.n, "id": q.id, "text": q.text, "warning_when": q.warning_when,
                           "p_yes": decision.question_yes.get(q.id, 0.0), "warning": q.reason in decision.warnings}
                          for q in cfg.questions],
        }
    return {
        "mira": mira,
        "mira_prompt": prompt,
        "links": [{"url": l.url, "host": l.host, "domain": l.domain, "ip": l.ip, "country": l.country,
                   "otx_reports": l.otx_reports, "shared_hosting": l.shared_hosting,
                   "domain_age_days": l.domain_age_days, "registrar": l.registrar,
                   "otx_counts": l.otx_counts, "otx_text": l.otx_text, "whois": l.whois, "whois_text": l.whois_text}
                  for l in links],
    }
