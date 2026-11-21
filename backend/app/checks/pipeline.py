"""The check pipeline (Phase 8): one SMS in, one verdict out - within the phone's 8-second wait.

  1. find links in the original text, mask personal data       (textprep, links)
  2. OTX + domain age for the links, in parallel               (link_reputation)   <= link budget
  3. build MIRA's prompt with those facts and ask MIRA         (mira_prompt, mira) <= MIRA timeout
  4. message rules: OTP request, brand mismatch, gambling      (textprep, rules)
  5. scoring v2 -> score, verdict, reasons, advice             (scoring)
Anything slow or failing is skipped and listed in `checks_skipped`; the check never crashes."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from .domain_age import DomainAgeClient
from .link_reputation import check_links
from .links import analyze_url
from .mira import MiraService, MiraUnavailable
from .mira_config import prompt_config
from .mira_prompt import build_message_state, build_questions, build_state, interpret
from .otx import OtxClient
from .rules import brand_mismatch, has_gambling_words
from .scoring import ScoreInput, score_message
from .senders import is_trusted_sender
from .textprep import asks_for_secret, extract_urls, mask_pii

log = logging.getLogger("checkscam.pipeline")

MAX_TEXT = 2000


@dataclass
class Checkers:
    """The outside services a check may use; any of them can be None (then that part is skipped)."""
    otx: OtxClient | None = None
    ages: DomainAgeClient | None = None
    mira: MiraService | None = None
    link_timeout: float = 2.0


def run_check(text: str, sender: str, checkers: Checkers) -> dict:
    t_start = time.perf_counter()
    timings: dict[str, int] = {}
    text = (text or "")[:MAX_TEXT]

    # 1. links (from the original text, so they survive masking) + masking
    links = [l for l in (analyze_url(u) for u in extract_urls(text)) if l is not None]
    masked = mask_pii(text)

    # 2. OTX + domain age
    skipped: list[str] = []
    t = time.perf_counter()
    if links and (checkers.otx or checkers.ages):
        skipped += check_links(links, checkers.otx, total_timeout=checkers.link_timeout, ages=checkers.ages)
    else:
        if links and checkers.otx is None:
            skipped.append("otx")
        if links and checkers.ages is None:
            skipped.append("whois")
    timings["links"] = round((time.perf_counter() - t) * 1000)

    # 3. MIRA with the full prompt
    cfg = prompt_config()
    mira_result = None
    t = time.perf_counter()
    if checkers.mira is not None:
        state = build_state(masked, links, sender=sender, skipped=skipped, cfg=cfg)
        try:
            answers = checkers.mira.batch(build_questions(state, cfg, build_message_state(masked, cfg)))
            mira_result = interpret(answers, cfg)
        except MiraUnavailable as exc:
            log.info("MIRA skipped: %s", exc.reason)
            skipped.append("mira")
    else:
        skipped.append("mira")
    timings["mira"] = round((time.perf_counter() - t) * 1000)

    # 4 + 5. rules and score
    result = score_message(ScoreInput(
        probabilities=mira_result.probabilities if mira_result else None,
        links=links,
        sender_trusted=is_trusted_sender(sender),
        asks_secret=asks_for_secret(text),
        question_points=mira_result.question_points if mira_result else 0.0,
        scam_type=mira_result.scam_type if mira_result else None,
        not_sure=mira_result.not_sure if mira_result else False,
        brand_mismatch=brand_mismatch(text, links),
        gambling=has_gambling_words(text),
    ))
    timings["total"] = round((time.perf_counter() - t_start) * 1000)

    result.update({
        "probabilities": mira_result.probabilities if mira_result else {},
        "not_sure": bool(mira_result and mira_result.not_sure),
        "scam_type": mira_result.scam_type if mira_result else None,
        "links": [{"url": mask_pii(l.url), "domain": l.domain, "trusted": l.trusted, "ip": l.ip,
                   "country": l.country, "otx_reports": l.otx_reports, "domain_age_days": l.domain_age_days}
                  for l in links],
        "checks_skipped": sorted(set(skipped)),
        "model_version": checkers.mira.version if (checkers.mira and checkers.mira.ready) else "",
        "prompt_version": cfg.version,
        "timings_ms": timings,
        "masked_text": masked,
    })
    log.info("check verdict=%s score=%s links=%d skipped=%s total=%sms",
             result["verdict"], result["score"], len(links), result["checks_skipped"], timings["total"])
    return result
