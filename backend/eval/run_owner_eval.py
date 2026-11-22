"""Backend flow B9: runs the owner's flow (OTX + WHOIS -> owner's prompt -> MIRA decides) on a labelled SMS file.

Same code path as the server: app.checks.pipeline.run_check with real OTX, WHOIS and MIRA (owner's prompt).
Run from backend/:
  ..\\.venv\\Scripts\\python eval\\run_owner_eval.py                 (collected_sms.csv)
  ..\\.venv\\Scripts\\python eval\\run_owner_eval.py seed_sms.csv    (any file in eval/data)
Writes eval/reports/owner_eval_<file>.csv (one row per message, written as it goes) and prints a summary."""
from __future__ import annotations

import csv
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.checks.domain_age import DomainAgeClient  # noqa: E402
from app.checks.otx import OtxClient  # noqa: E402
from app.checks.pipeline import Checkers, run_check  # noqa: E402
from app.config import Settings  # noqa: E402
from app.db import make_engine, make_sessionmaker  # noqa: E402
from app.main import make_mira_service  # noqa: E402

HERE = Path(__file__).resolve().parent
FIELDS = ["no", "label", "risk_class", "probability", "verdict", "owner_result", "warnings", "links", "skipped",
          "links_ms", "mira_ms", "text"]


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "collected_sms.csv"
    rows = list(csv.DictReader(open(HERE / "data" / name, encoding="utf-8")))
    s = Settings()
    sessions = make_sessionmaker(make_engine(s.database_url))
    mira = make_mira_service(s)
    t0 = time.perf_counter()
    mira.start_loading(background=False)  # includes the warm-up
    mira.timeout = 120  # evaluating, not serving
    print(f"MIRA {mira.status} ({mira.version}) in {time.perf_counter() - t0:.0f} s | {len(rows)} messages", flush=True)
    checkers = Checkers(
        otx=OtxClient(s.otx_api_key, sessions, timeout=s.otx_timeout_seconds, daily_limit=s.otx_daily_limit,
                      save_in_background=True) if s.otx_api_key else None,
        ages=DomainAgeClient(sessions, timeout=s.whois_timeout_seconds, cache_days=s.domain_cache_days,
                             save_in_background=True),
        mira=mira, link_timeout=s.link_checks_timeout_seconds,
    )
    out_path = HERE / "reports" / f"owner_eval_{Path(name).stem}.csv"
    results = []
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for i, row in enumerate(rows, 1):
            t = time.perf_counter()
            r = run_check(row["text"], "", checkers, source="SMS")
            out = {
                "no": i, "label": row["label"], "risk_class": r["risk_class"] or "not_checked",
                "probability": r["score"], "verdict": r["verdict"],
                "owner_result": (r["owner_result"] or {}).get("Probability", ""),
                "warnings": ";".join(x["code"] for x in r["reasons"][1:]), "links": len(r["links"]),
                "skipped": ";".join(r["checks_skipped"]), "links_ms": r["timings_ms"]["links"],
                "mira_ms": r["timings_ms"]["mira"], "text": r["masked_text"][:300],
            }
            w.writerow(out)
            f.flush()
            results.append(out)
            print(f"{i:3}/{len(rows)} {row['label']:5} -> {out['risk_class']:13} {out['probability']:3}%  "
                  f"({time.perf_counter() - t:.0f} s)", flush=True)

    print("\n=== summary ===")
    by_label = Counter(r["label"] for r in results)
    for label in sorted(by_label):
        part = [r for r in results if r["label"] == label]
        classes = Counter(r["risk_class"] for r in part)
        print(f"{label} ({len(part)}): " + ", ".join(f"{k} {v}" for k, v in classes.most_common()))
    scams = [r for r in results if r["label"] == "scam"]
    if scams:
        high_plus = sum(r["risk_class"] in ("high", "critical", "very_harmful") for r in scams)
        dangerous = sum(r["verdict"] == "dangerous" for r in scams)
        print(f"scams flagged HIGH RISK or worse (41-100): {high_plus}/{len(scams)} = {high_plus / len(scams):.0%}")
        print(f"scams flagged CRITICAL or VERY HARMFUL (61-100, phone 'dangerous'): {dangerous}/{len(scams)} "
              f"= {dangerous / len(scams):.0%}")
    probs = [r["probability"] for r in results if r["risk_class"] != "not_checked"]
    if probs:
        print(f"probability: min {min(probs)}%, max {max(probs)}%, average {sum(probs) / len(probs):.0f}%")
    print(f"not checked (MIRA no answer): {sum(r['risk_class'] == 'not_checked' for r in results)}")
    print(f"average MIRA time: {sum(r['mira_ms'] for r in results) / len(results) / 1000:.0f} s | report: {out_path}")


if __name__ == "__main__":
    main()
