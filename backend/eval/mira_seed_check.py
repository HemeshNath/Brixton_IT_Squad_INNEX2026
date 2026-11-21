"""Phase 6 checkpoint: MIRA speed on this laptop + raw answers for the seed SMS.

Run from backend/:  ..\\.venv\\Scripts\\python eval\\mira_seed_check.py
Writes eval/reports/mira_seed_v0.csv (one row per seed message) and prints speed and a summary.
The wording here is the simple "v0" option set - Phase 7 (prompting) tunes it."""
from __future__ import annotations

import csv
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.checks.mira import Question  # noqa: E402
from app.checks.textprep import mask_pii  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import make_mira_service  # noqa: E402

HERE = Path(__file__).resolve().parent
OPTIONS_V0 = {
    "scam": "This message is a scam trying to get money, an OTP, a PIN or personal details",
    "spam": "This message is an advertisement or promotion",
    "ham": "This is a normal personal, bank or service message",
}
SMALL_QUESTIONS = [  # yes/no questions planned for Phase 7, used here only to measure speed
    "Does this message ask for money or a fee?",
    "Does this message ask for an OTP, PIN or password?",
    "Does this message claim the reader won a prize, gift or lottery?",
    "Does this message threaten or create urgency?",
    "Does this message pretend to be a company, bank or government?",
]


def main() -> None:
    svc = make_mira_service(Settings())
    t0 = time.perf_counter()
    svc.start_loading(background=False)
    if not svc.ready:
        sys.exit(f"MIRA failed to load: {svc.error}")
    svc.timeout = 60  # measuring, not serving
    print(f"MIRA {svc.version} loaded in {time.perf_counter() - t0:.1f} s")

    with open(HERE / "data" / "seed_sms.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # --- speed: one message = main question (3 options) + 5 yes/no questions, in one batch
    times = []
    for r in rows[:50]:
        state = mask_pii(r["text"])
        qs = [Question(state, list(OPTIONS_V0.values()))] + [Question(f"{state}\nQuestion: {q}", ["yes", "no"]) for q in SMALL_QUESTIONS]
        t = time.perf_counter()
        svc.batch(qs)
        times.append((time.perf_counter() - t) * 1000)
    times.sort()
    p50, p90 = times[len(times) // 2], times[int(len(times) * 0.9)]
    print(f"speed, 1 message + 5 questions (13 pairs): p50 {p50:.0f} ms | p90 {p90:.0f} ms | max {times[-1]:.0f} ms")

    # --- raw answers for every seed message (main question only)
    out_rows, correct = [], 0
    labels = list(OPTIONS_V0)
    for r in rows:
        ans = svc.choice(mask_pii(r["text"]), list(OPTIONS_V0.values()))
        probs = [ans.probabilities[OPTIONS_V0[k]] for k in labels]
        pred = labels[probs.index(max(probs))]
        correct += pred == r["label"]
        out_rows.append({"label": r["label"], "predicted": pred, "p_scam": probs[0], "p_spam": probs[1],
                         "p_ham": probs[2], "not_sure": ans.not_sure, "lang": r.get("lang", ""), "text": r["text"]})

    reports = HERE / "reports"
    reports.mkdir(exist_ok=True)
    with open(reports / "mira_seed_v0.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0]))
        w.writeheader()
        w.writerows(out_rows)

    n = len(out_rows)
    print(f"\nseed messages: {n} | correct label (v0 wording): {correct}/{n} = {correct / n:.0%} | "
          f"not sure: {sum(r['not_sure'] for r in out_rows)}")
    for lab in labels:
        sub = [r for r in out_rows if r["label"] == lab]
        hit = sum(r["predicted"] == lab for r in sub)
        print(f"  {lab:5} {hit:3}/{len(sub):3} = {hit / len(sub):.0%}   mean p_scam {statistics.mean(r['p_scam'] for r in sub):.2f}")
    for lang in sorted({r["lang"] for r in out_rows}):
        sub = [r for r in out_rows if r["lang"] == lang]
        print(f"  lang {lang:4} {sum(r['predicted'] == r['label'] for r in sub):3}/{len(sub):3} correct")
    print(f"\nsaved: {reports / 'mira_seed_v0.csv'}")


if __name__ == "__main__":
    main()
