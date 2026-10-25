"""Does the readiness estimate match reality?

Two kinds of evidence arrive from learners (see ``/api/outcome``):

* **Official exam results** (pass/fail): the gold standard, but slow and rare. We compare the app's
  "chance of reaching the pass line" with what actually happened (reliability bins, Brier score versus
  a naive "everyone has the average pass rate" baseline).
* **Microsoft practice-assessment scores** (percent): plentiful, so they show drift early. We compare
  the app's estimated score with the reported percentage (bias, mean absolute error, correlation).

Each result carries the app's prediction *as of the day it happened* (computed on the server), so the
comparison is fair. Run ``python -m app.calibration`` on the server; output is aggregate only.
"""
from __future__ import annotations

import argparse
import json
import math
import sys

MIN_EXAMS_TO_JUDGE = 30
BIN_EDGES = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / (sx * sy)


def calibration_report(outcomes: list[dict], min_answered: int = 20) -> dict:
    usable = [o for o in outcomes if o["answered"] >= min_answered]
    exams = [o for o in usable if o["kind"] == "exam"]
    assessments = [o for o in usable if o["kind"] == "practice_assessment"]

    exam: dict = {"n": len(exams)}
    if exams:
        rate = sum(o["passed"] for o in exams) / len(exams)
        brier = sum((o["p_pass"] - o["passed"]) ** 2 for o in exams) / len(exams)
        baseline = sum((rate - o["passed"]) ** 2 for o in exams) / len(exams)
        bins = []
        for i in range(len(BIN_EDGES) - 1):
            lo, hi = BIN_EDGES[i], BIN_EDGES[i + 1]
            group = [o for o in exams if lo <= o["p_pass"] < hi or (hi == 1.0 and o["p_pass"] == 1.0)]
            bins.append({
                "range": [lo, hi], "n": len(group),
                "mean_predicted": sum(o["p_pass"] for o in group) / len(group) if group else None,
                "observed_pass_rate": sum(o["passed"] for o in group) / len(group) if group else None,
            })
        exam.update({
            "pass_rate": rate, "brier": brier, "baseline_brier": baseline,
            "beats_baseline": brier < baseline, "bins": bins,
            "verdict": ("Not enough exam results to judge accuracy yet."
                        if len(exams) < MIN_EXAMS_TO_JUDGE
                        else ("Predictions beat the naive baseline." if brier < baseline
                              else "Predictions do NOT beat the naive baseline: recalibrate.")),
        })

    practice: dict = {"n": len(assessments)}
    if assessments:
        est = [o["est_score"] * 100 for o in assessments]
        actual = [o["score"] for o in assessments]
        errors = [e - a for e, a in zip(est, actual, strict=True)]
        practice.update({
            "bias_points": sum(errors) / len(errors),  # > 0 means the app is more optimistic than reality
            "mean_abs_error_points": sum(abs(e) for e in errors) / len(errors),
            "correlation": _pearson(est, actual),
        })
    return {"min_answered": min_answered, "ignored_low_evidence": len(outcomes) - len(usable),
            "exam": exam, "practice_assessment": practice}


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI over calibration_report
    from . import db

    parser = argparse.ArgumentParser(prog="python -m app.calibration", description=__doc__.split("\n\n")[0])
    parser.add_argument("--min-answered", type=int, default=20, help="ignore results from learners with less evidence")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = calibration_report(db.get_all_outcomes(), args.min_answered)
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    exam, pa = report["exam"], report["practice_assessment"]
    print(f"Results with enough evidence: exams {exam['n']}, practice assessments {pa['n']} "
          f"(ignored {report['ignored_low_evidence']} with < {args.min_answered} answers)")
    if exam["n"]:
        print(f"Exam: pass rate {exam['pass_rate']:.0%}, Brier {exam['brier']:.3f} vs baseline {exam['baseline_brier']:.3f}")
        for b in exam["bins"]:
            if b["n"]:
                print(f"  predicted {b['range'][0]:.0%}-{b['range'][1]:.0%}: n={b['n']}, "
                      f"mean predicted {b['mean_predicted']:.0%}, observed {b['observed_pass_rate']:.0%}")
        print(exam["verdict"])
    if pa["n"]:
        corr = "n/a" if pa["correlation"] is None else f"{pa['correlation']:.2f}"
        print(f"Practice assessments: bias {pa['bias_points']:+.1f} pts, MAE {pa['mean_abs_error_points']:.1f} pts, r={corr}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
