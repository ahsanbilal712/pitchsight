"""Every TECH_PLAN 1.11 number in one table (T-056).

    python -m evals.run_evals --seeds 1..50 --out packages/evals/results.md

Re-runs the cheap evaluations (state detection on --seeds, planted errors, groundedness and replay latency from the
committed golden cache, cost from the ledger) and reads the expensive ones from their committed artefacts
(calibration and placebo from evals/out/calibration.json, T-040; policy metrics from policy/artifacts, T-037; the CI
judge from evals/out/judge.json when it was run). Writes results.md (number, threshold, result, script, data for every
row; a row that cannot be measured yet says "pending T-0xx") and results.json beside it for `evals.gate`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "packages" / "evals" / "out"


def _load(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _row(id_, number, measured, threshold, status, script, data, detail=None) -> dict:
    return {"id": id_, "number": number, "measured": measured, "threshold": threshold, "status": status,
            "script": script, "data": data, "detail": detail}


def collect(seeds: str, rerun: bool = True) -> list[dict]:
    from evals import cost, groundedness, latency, planted_errors, state_detection

    rows = []
    if rerun:
        state_detection.main(["--seeds", seeds])
        planted_errors.main(["--n", "500"])
        groundedness.main([])
    sd = _load(OUT / "state_detection.json")
    rows.append(_row("state_detection", "State-detection precision/recall/F1 vs hidden truth",
                     f"F1 {sd['macro']['f1']:.3f} (P {sd['macro']['precision']:.3f}, R {sd['macro']['recall']:.3f})",
                     "F1 >= 0.75", "pass" if sd["macro"]["f1"] >= 0.75 else "fail", "evals/state_detection.py",
                     f"{sd['matches']} Kickoff matches, seeds {sd['seeds'][0]}-{sd['seeds'][1]}, {sd['seconds']:,} s",
                     "evals/out/state_confusion.png"))

    cal = _load(OUT / "calibration.json")
    rows.append(_row("calibration_brier", "Counterfactual calibration (Brier, reliability diagram)",
                     f"Brier {cal['brier']:.4f} (base rate {cal['base_rate']:.3f}, log-loss {cal['log_loss']:.3f})",
                     "Brier <= 0.18", "pass" if cal["brier"] <= 0.18 else "fail", "evals/calibration.py",
                     f"{cal['n_matches']} held-out matches, {cal['n_moments']:,} explained moments, n={cal['n']}, "
                     f"{cal['horizon_s']:g} s, {cal['engine']}", "evals/out/calibration.png"))
    rows.append(_row("calibration_placebo", "Placebo test (forcing the actual action reproduces the baseline)",
                     f"{cal['placebo_pass_rate']:.3f} of {cal['placebo_testable']:,} moments within the 95% interval",
                     ">= 0.95", "pass" if cal["placebo_pass_rate"] >= 0.95 else "fail", "evals/calibration.py",
                     "same moments"))

    gate = _load(ROOT / "packages" / "policy" / "artifacts" / "gate.json")
    metrics = _load(ROOT / "packages" / "policy" / "artifacts" / "metrics.json") or {}
    failing = gate.get("reasons") or []
    rows.append(_row("policy_metrics", "Policy metrics (table in TECH_PLAN 1.6)",
                     "; ".join(failing) if failing else "all gates pass",
                     "TECH_PLAN 1.6 gates", "cut" if failing else "pass", "policy/evaluate.py",
                     "test split + 20 rollouts",
                     f"cut line applied (T-037): {gate['engine']} serves every counterfactual; "
                     "docs/evidence/policy_gate_day4.md" if failing else (metrics.get("checkpoint") or None)))

    pe = _load(OUT / "planted_errors.json")
    src = pe["source"]
    rows.append(_row("planted_errors", "Fact Checker planted errors caught",
                     f"{pe['caught']}/{pe['n_planted']} = {pe['catch_rate']:.1%}", "100% caught",
                     "pass" if pe["catch_rate"] >= 1.0 else "fail", "evals/planted_errors.py",
                     f"{pe['n_planted']} outputs, one injected error each (5 kinds x 100) from "
                     f"{src['verified_explanations']} verified golden explanations"
                     + (", sampled with replacement" if src["sampled_with_replacement"] else ""),
                     "per-rule catch table in evals/out/planted_errors.json; stress set (not gated): "
                     f"{pe['stress']['wrong_number_widened']['catch_rate']:.0%} of numbers moved just past tolerance"))
    fr = pe["false_rejects"]
    rows.append(_row("false_rejects", "Fact Checker false rejects", f"{fr['rejected']}/{fr['n']} = {fr['rate']:.1%}",
                     "<= 2%", "pass" if fr["rate"] <= 0.02 else "fail", "evals/planted_errors.py",
                     f"{fr['n']} golden verified outputs ({fr['unique_outputs']} unique, sampled with replacement)"))

    live = _load(OUT / "latency_live.json")
    if live and live.get("source") == "live":
        t = live["tiers"]
        rows.append(_row("latency_live", "Cue latency p50/p95 (live)",
                         f"fast p95 {t['fast'].get('p95_s')} s; explained p95 {t['explained'].get('p95_s')} s",
                         "fast <= 3 s p95; explained <= 15 s p95", "pass" if live["passed"] else "fail",
                         "evals/latency.py", f"{len(live['matches'])} live matches"))
    else:
        rows.append(_row("latency_live", "Cue latency p50/p95 (live)", "pending T-080 (3 live matches)",
                         "fast <= 3 s p95; explained <= 15 s p95", "pending", "evals/latency.py", "3 live matches",
                         "interim: explained p95 12.9 s over 6 golden moments (T-032 probe D, "
                         "docs/evidence/latency_probe_day3.md)"))
    rep = latency.summarise(latency.cue_latencies(groundedness.replay_cues()[1]), "replay")
    rows.append(_row("latency_replay", "Cue latency (replay, simulated)",
                     "; ".join(f"{k} n={v['n']}" for k, v in rep["tiers"].items()), "none (replay is not gated)",
                     "reported", "evals/latency.py --source replay", "golden match from the cache"))

    led = cost.ledger_costs()
    live_ids = [m for m in (live or {}).get("matches", [])]
    if live_ids:
        worst = max(led["matches"].get(m, {"total_usd": 0.0})["total_usd"] for m in live_ids)
        rows.append(_row("cost_per_match", "Cost per match", f"max ${worst:.2f} over {len(live_ids)} live matches",
                         "<= $2.50", "pass" if worst <= led["per_match_cap_usd"] else "fail", "evals/cost.py (ledger)",
                         ", ".join(live_ids)))
    else:
        rows.append(_row("cost_per_match", "Cost per match", "pending T-080 (3 live matches)", "<= $2.50", "pending",
                         "evals/cost.py (ledger)", "same 3 matches"))
    g = led["matches"].get("m_4242")
    if g:
        rows.append(_row("cost_golden", "Cost, golden match (all modes)", f"${g['total_usd']:.2f} "
                         f"({', '.join(f'{k} ${v:.2f}' for k, v in g['by_mode'].items())})", "<= $2.50",
                         "pass" if g["passed"] else "fail", "evals/cost.py (ledger)", "m_4242"))
    rows.append(_row("cost_project", "Project spend", f"${led['project_total_usd']:.2f} over {led['rows']} calls",
                     "<= $50", "pass" if led["project_passed"] else "fail", "evals/cost.py (ledger)",
                     "data/spend/ledger.jsonl"))

    gr = _load(OUT / "groundedness.json")
    rows.append(_row("groundedness", "Groundedness (own evaluator: numbers on screen bound to verified claims)",
                     f"{gr['grounded']}/{gr['numbers']} = {gr['groundedness']:.3f}", ">= 0.95",
                     "pass" if gr["passed"] else "fail", "evals/groundedness.py",
                     f"{gr['cues']} golden cues (500 once the demo season lands, T-085); Foundry optional (T-086)"))

    rows.append(_row("realism", "Realism (Kickoff vs SkillCorner/DFL marginals)", "pending T-073",
                     "plots published; no threshold", "pending", "evals/realism.py", "SkillCorner/DFL marginals"))
    rows.append(_row("resume", "Resume (kill switch)", "pending T-091 (20-run chaos test)", "0 cues lost in 20 runs",
                     "pending", "tests/chaos/test_resume.py", "20 runs",
                     "interim: the one-run CI test (T-051) resumes with the same cue id; docs/evidence/kill_resume.log"))

    jd = _load(OUT / "judge.json")
    rows.append(_row("judge", "CI judge plausibility (reported only)",
                     f"{jd['plausibility_rate']:.0%} of {jd['judged']} explained cues (${jd['cost_usd']:.2f})"
                     if jd and jd.get("plausibility_rate") is not None else "not run (python -m evals.judge)",
                     "none", "reported", "evals/judge.py", "30 random explained golden cues, prompts/judge@1.md"))
    return rows


def to_markdown(rows: list[dict]) -> str:
    mark = {"pass": "pass", "fail": "**FAIL**", "pending": "pending", "reported": "reported", "cut": "cut line"}
    lines = ["# WHYLINE evaluation results (TECH_PLAN 1.11)", "",
             "Written by `python -m evals.run_evals --seeds 1..50 --out packages/evals/results.md`; "
             "`python -m evals.gate packages/evals/results.json` fails CI when a measured number misses its "
             "threshold. Pending rows name the ticket that measures them.", "",
             "| Number | Measured | Threshold | Result | Script | Data |", "|---|---|---|---|---|---|"]
    for r in rows:
        measured = r["measured"] + (f" ({r['detail']})" if r.get("detail") else "")
        lines.append(f"| {r['number']} | {measured} | {r['threshold']} | {mark[r['status']]} | `{r['script']}` | "
                     f"{r['data']} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m evals.run_evals")
    ap.add_argument("--seeds", default="1..50")
    ap.add_argument("--out", type=Path, default=ROOT / "packages" / "evals" / "results.md")
    ap.add_argument("--no-rerun", action="store_true", help="only read the committed artefacts")
    args = ap.parse_args(argv)
    rows = collect(args.seeds, rerun=not args.no_rerun)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(to_markdown(rows), encoding="utf-8")
    args.out.with_suffix(".json").write_text(json.dumps({"rows": rows}, indent=1) + "\n", encoding="utf-8")
    print(to_markdown(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
