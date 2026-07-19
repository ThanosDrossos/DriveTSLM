"""Evaluation harness for the consistency checker.

Runs the checker over ALL narrative variants x N repetitions (default 3) and
reports:
- contradiction detection precision/recall (per injected error type + overall)
- error localization (was the contradicted assertion of the injected type?)
- abstention rate (unverifiable verdicts / all verdicts)
- citation validity (validator pass rate, fully-grounded runs, uncited claims)
- cost and tokens per case
- run-to-run agreement across repetitions

Scoring is deterministic: a run "flags" a narrative iff its DERIVED overall
verdict (>=1 contradicted assertion) is "inconsistent". Positive class =
narratives with an injected error.

Each run is cached as eval/results/runs/<narrative_id>__rep<k>.json, so the
harness is resumable and re-runs are free. Summary lands in
eval/results/summary.json + eval/results/summary.md.

  python eval/run_eval.py [--reps 3] [--model ID] [--workers 2] [--only PREFIX]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import narratives  # noqa: E402
from app.consistency import run_consistency_check  # noqa: E402
from app.llm import MODEL  # noqa: E402

RUNS_DIR = ROOT / "eval" / "results" / "runs"

ERROR_TO_ASSERTION_TYPE = {
    "speed_mismatch": "speed",
    "claimed_braking_absent": "braking",
    "wrong_impact_direction": "impact_direction",
    "event_count_mismatch": "impact_count",
    "understated_severity": "severity",
}


def run_one(narrative: dict, rep: int, model: str) -> dict:
    path = RUNS_DIR / f"{narrative['narrative_id']}__rep{rep}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    t0 = time.time()
    final = {}
    try:
        for ev in run_consistency_check(narrative["event_id"], narrative["text"],
                                        model=model):
            final = ev
    except Exception as exc:  # record failures, don't kill the sweep
        final = {"type": "error", "message": f"{type(exc).__name__}: {exc}"}

    record = {
        "narrative_id": narrative["narrative_id"],
        "event_id": narrative["event_id"],
        "ground_truth": narrative["ground_truth"],
        "injected_error": narrative["injected_error"],
        "rep": rep,
        "model": model,
        "wall_s": round(time.time() - t0, 1),
        "result": final,
    }
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=1), encoding="utf-8")
    return record


def summarize(records: list[dict]) -> dict:
    ok = [r for r in records if r["result"].get("type") == "final"]
    failed = [r for r in records if r["result"].get("type") != "final"]

    tp = fp = fn = tn = 0
    per_error: dict[str, Counter] = defaultdict(Counter)
    abst_num = abst_den = 0
    cit_rates, grounded, uncited_total = [], 0, 0
    costs, in_toks, out_toks = [], [], []
    by_narrative: dict[str, list[str]] = defaultdict(list)

    for r in ok:
        res = r["result"]
        flagged = res["derived_overall"] == "inconsistent"
        positive = r["ground_truth"] == "inconsistent"
        if positive and flagged:
            tp += 1
        elif positive:
            fn += 1
        elif flagged:
            fp += 1
        else:
            tn += 1

        if positive:
            err = r["injected_error"]
            per_error[err]["n"] += 1
            if flagged:
                per_error[err]["detected"] += 1
                atype = ERROR_TO_ASSERTION_TYPE.get(err)
                types_by_id = {a["id"]: a["type"] for a in res.get("assertions", [])}
                localized = any(
                    v["verdict"] == "contradicted"
                    and types_by_id.get(v["assertion_id"]) == atype
                    for v in res["verdicts"]
                )
                if localized:
                    per_error[err]["localized"] += 1

        verdicts = res.get("verdicts", [])
        abst_num += sum(1 for v in verdicts if v["verdict"] == "unverifiable")
        abst_den += len(verdicts)

        val = res.get("validation") or {}
        if val.get("citation_validity_rate") is not None:
            cit_rates.append(val["citation_validity_rate"])
        grounded += 1 if val.get("fully_grounded") else 0
        uncited_total += val.get("n_uncited", 0)

        usage = res.get("usage", {})
        costs.append(usage.get("cost_usd_estimate", 0.0))
        in_toks.append(usage.get("input_tokens", 0) + usage.get("cache_read_tokens", 0)
                       + usage.get("cache_creation_tokens", 0))
        out_toks.append(usage.get("output_tokens", 0))

        by_narrative[r["narrative_id"]].append(res["derived_overall"])

    agreements = []
    for _nid, overalls in by_narrative.items():
        if len(overalls) > 1:
            agreements.append(Counter(overalls).most_common(1)[0][1] / len(overalls))

    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    mean = lambda xs: round(sum(xs) / len(xs), 4) if xs else None  # noqa: E731

    return {
        "model": records[0]["model"] if records else MODEL,
        "n_runs": len(records),
        "n_ok": len(ok),
        "n_failed": len(failed),
        "failed_runs": [{"narrative_id": r["narrative_id"], "rep": r["rep"],
                         "message": r["result"].get("message")} for r in failed],
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "contradiction_precision": round(precision, 3) if precision is not None else None,
        "contradiction_recall": round(recall, 3) if recall is not None else None,
        "false_positive_rate": round(fp / (fp + tn), 3) if fp + tn else None,
        "per_error_type": {
            err: {
                "n": c["n"],
                "detected": c["detected"],
                "recall": round(c["detected"] / c["n"], 3) if c["n"] else None,
                "localized": c["localized"],
            } for err, c in sorted(per_error.items())
        },
        "abstention_rate": round(abst_num / abst_den, 3) if abst_den else None,
        "citation_validity_rate_mean": mean(cit_rates),
        "fully_grounded_runs": grounded,
        "uncited_claims_total": uncited_total,
        "mean_cost_usd_per_case": mean(costs),
        "mean_input_tokens": mean(in_toks),
        "mean_output_tokens": mean(out_toks),
        "run_to_run_agreement_mean": mean(agreements),
        "per_narrative_overalls": {k: v for k, v in sorted(by_narrative.items())},
    }


def to_markdown(s: dict) -> str:
    lines = [
        f"## Consistency-checker evaluation ({s['model']}, {s['n_ok']}/{s['n_runs']} runs ok)",
        "",
        f"- contradiction detection: precision **{s['contradiction_precision']}**, "
        f"recall **{s['contradiction_recall']}** "
        f"(FP rate {s['false_positive_rate']}, confusion {s['confusion']})",
        f"- abstention rate: **{s['abstention_rate']}** of assertion verdicts",
        f"- citation validity: mean **{s['citation_validity_rate_mean']}**, "
        f"fully grounded runs {s['fully_grounded_runs']}/{s['n_ok']}, "
        f"uncited claims total {s['uncited_claims_total']}",
        f"- cost/case: **${s['mean_cost_usd_per_case']}** "
        f"({s['mean_input_tokens']:.0f} in / {s['mean_output_tokens']:.0f} out tokens)",
        f"- run-to-run agreement (majority share across reps): "
        f"**{s['run_to_run_agreement_mean']}**",
        "",
        "| injected error | runs | detected | recall | localized to right assertion |",
        "|---|---|---|---|---|",
    ]
    for err, c in s["per_error_type"].items():
        lines.append(f"| {err} | {c['n']} | {c['detected']} | {c['recall']} | {c['localized']} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--only", help="only narrative_ids starting with this prefix")
    args = ap.parse_args()

    ns = narratives.load_all()
    if args.only:
        ns = [n for n in ns if n["narrative_id"].startswith(args.only)]
    jobs = [(n, rep) for n in ns for rep in range(1, args.reps + 1)]
    print(f"{len(ns)} narratives x {args.reps} reps = {len(jobs)} runs "
          f"on {args.model} ({args.workers} workers)")

    records = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_one, n, rep, args.model): (n, rep)
                   for n, rep in jobs}
        for i, fut in enumerate(as_completed(futures), 1):
            n, rep = futures[fut]
            rec = fut.result()
            status = rec["result"].get("derived_overall",
                                       rec["result"].get("type"))
            print(f"[{i}/{len(jobs)}] {n['narrative_id']} rep{rep}: {status} "
                  f"({rec.get('wall_s', '?')}s)")
            records.append(rec)

    summary = summarize(records)
    out_dir = ROOT / "eval" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1),
                                          encoding="utf-8")
    (out_dir / "summary.md").write_text(to_markdown(summary), encoding="utf-8")
    print("\n" + to_markdown(summary))
    print(f"wrote {out_dir / 'summary.json'} and summary.md")


if __name__ == "__main__":
    main()
