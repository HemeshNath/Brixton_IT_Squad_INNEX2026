"""Runs the whole current check system on a labelled SMS file and reports the verdicts.

Pipeline per message (same parts the Phase 8 endpoint will use):
  PII masking -> link rules -> OTX + domain age (real services, cached in Supabase)
  -> MIRA asked twice: (a) baseline: SMS text only with 3 simple v0 options,
     (b) full prompt from app/data/mira_prompt.json (link/OTX/domain-age facts, answer options and
     yes/no questions; its version is written into the report) -> scoring -> verdict.
  Note: scoring here uses only MIRA's scam/spam/ham probabilities; question points are reported
  but only used by scoring v2 (Phase 8).

Run from backend/:
  ..\\.venv\\Scripts\\python eval\\run_system_eval.py                 (collected_sms.csv)
  ..\\.venv\\Scripts\\python eval\\run_system_eval.py seed_sms.csv    (any file in eval/data)
Writes eval/reports/system_eval_<file>.csv with one row per message."""
from __future__ import annotations

import csv
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.checks.domain_age import DomainAgeClient  # noqa: E402
from app.checks.link_reputation import check_links  # noqa: E402
from app.checks.links import analyze_url  # noqa: E402
from app.checks.mira import MiraUnavailable, Question  # noqa: E402
from app.checks.mira_config import prompt_config  # noqa: E402
from app.checks.mira_prompt import build_questions, build_state, interpret  # noqa: E402
from app.checks.otx import OtxClient  # noqa: E402
from app.checks.scoring import ScoreInput, score_message  # noqa: E402
from app.checks.textprep import asks_for_secret, extract_urls, mask_pii  # noqa: E402
from app.config import Settings  # noqa: E402
from app.db import make_engine, make_sessionmaker  # noqa: E402
from app.main import make_mira_service  # noqa: E402

HERE = Path(__file__).resolve().parent
OPTIONS_V0 = {
    "scam": "This message is a scam trying to get money, an OTP, a PIN or personal details",
    "spam": "This message is an advertisement or promotion",
    "ham": "This is a normal personal, bank or service message",
}


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "collected_sms.csv"
    rows = list(csv.DictReader(open(HERE / "data" / name, encoding="utf-8")))
    s = Settings()
    sessions = make_sessionmaker(make_engine(s.database_url))
    otx = OtxClient(s.otx_api_key, sessions, timeout=s.otx_timeout_seconds, daily_limit=s.otx_daily_limit) if s.otx_api_key else None
    ages = DomainAgeClient(sessions, timeout=s.whois_timeout_seconds, cache_days=s.domain_cache_days)

    cfg = prompt_config()
    print(f"prompt config: {cfg.version} | {len(cfg.options)} answer options | {len(cfg.questions)} yes/no questions")
    mira = make_mira_service(s)
    t0 = time.perf_counter()
    mira.start_loading(background=False)
    mira.timeout = 30  # evaluating, not serving
    print(f"MIRA: {mira.status} ({mira.version}) in {time.perf_counter() - t0:.0f} s | OTX: {'on' if otx else 'off (no key)'}")

    out = []
    for i, r in enumerate(rows, 1):
        text = r["text"]
        links = [l for l in (analyze_url(u) for u in extract_urls(text)) if l is not None]
        skipped = check_links(links, otx, total_timeout=20, ages=ages) if links else []
        secret = asks_for_secret(text)

        without = score_message(ScoreInput(probabilities=None, links=links, asks_secret=secret))
        masked = mask_pii(text)
        state = build_state(masked, links, sender=r.get("sender", ""), skipped=skipped)
        probs = probs_state = result = None
        try:
            answers = mira.batch([Question(masked, list(OPTIONS_V0.values()))] + build_questions(state, cfg))
            probs = {k: answers[0].probabilities[v] for k, v in OPTIONS_V0.items()}
            result = interpret(answers[1:], cfg)
            probs_state = result.probabilities
        except MiraUnavailable as exc:
            skipped.append(f"mira:{exc.reason}")
        with_mira = score_message(ScoreInput(probabilities=probs, links=links, asks_secret=secret))
        with_state = score_message(ScoreInput(probabilities=probs_state, links=links, asks_secret=secret))
        pred = lambda p: max(p, key=p.get) if p else ""

        codes = [x["code"] for x in with_state["reasons"] if x["points"] > 0]
        out.append({
            "no": i, "label": r["label"], "lang": r.get("lang", ""),
            "mira_text_pred": pred(probs), "mira_prompt_pred": pred(probs_state),
            "verdict_without_mira": without["verdict"], "score_without_mira": without["score"],
            "verdict_with_mira": with_mira["verdict"], "score_with_mira": with_mira["score"],
            "verdict_with_prompt": with_state["verdict"], "score_with_prompt": with_state["score"],
            "mira_p_scam": round(probs["scam"], 2) if probs else "",
            "prompt_p_scam": round(probs_state["scam"], 2) if probs_state else "",
            "prompt_version": cfg.version,
            "scam_type": (result.scam_type or "") if result else "",
            "question_points": result.question_points if result else "",
            "mira_ms": round(answers[0].ms) if result else "",
            "links": len(links), "domain_age_days": next((l.domain_age_days for l in links if l.domain_age_days is not None), ""),
            "otx_reports": max((l.otx_reports or 0 for l in links), default=""),
            "reasons": " ".join(codes), "skipped": " ".join(sorted(set(skipped))), "text": text.replace("\n", " ")[:300],
        })
        o = out[-1]
        print(f"{i:3} {r['label']:4} | MIRA text: {o['mira_text_pred']:4} p_scam {o['mira_p_scam']!s:4} -> {with_mira['verdict']:10} | "
              f"MIRA prompt: {o['mira_prompt_pred']:4} p_scam {o['prompt_p_scam']!s:4} -> {with_state['verdict']:10}")

    reports = HERE / "reports"
    reports.mkdir(exist_ok=True)
    path = reports / f"system_eval_{Path(name).stem}.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)

    print()
    print("=== MIRA answer (scam / spam=ad / ham=normal) vs the real label ===")
    for col, title in (("mira_text_pred", "SMS text only"), ("mira_prompt_pred", "full prompt v1")):
        ok = sum(r[col] == r["label"] for r in out)
        per = "  ".join(f"{lab}: {sum(r[col] == lab for r in out if r['label'] == lab)}/{sum(r['label'] == lab for r in out)}"
                        for lab in ("scam", "spam", "ham") if any(r["label"] == lab for r in out))
        print(f"{title:24} correct {ok}/{len(out)} = {ok / len(out):.0%}   ({per})")
    print()
    print("=== final verdicts ===")
    for col in ("verdict_without_mira", "verdict_with_mira", "verdict_with_prompt"):
        for lab in sorted({r["label"] for r in out}):
            c = Counter(r[col] for r in out if r["label"] == lab)
            print(f"{col:22} label {lab:4}: dangerous {c['dangerous']:3} | suspicious {c['suspicious']:3} | safe {c['safe']:3}")
    ms = sorted(r["mira_ms"] for r in out if r["mira_ms"] != "")
    if ms:
        print()
        print(f"MIRA time per SMS (baseline + full prompt batch): p50 {ms[len(ms) // 2]} ms | p90 {ms[int(len(ms) * 0.9)]} ms")
    print(f"prompt version: {cfg.version} | saved: {path}")


if __name__ == "__main__":
    main()
