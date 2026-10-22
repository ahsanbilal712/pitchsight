"""Cue latency p50/p95 per tier from blackboard traces (TECH_PLAN 1.11 row "Cue latency", T-056).

    python -m evals.latency --source live --matches 9001,9002,9003 --blackboard PATH --out packages/evals/out/latency_live.json
    python -m evals.latency --source replay [--match-dir data/matches/4242]

Per moment run (`run_id`) and branch: event to cue = the Scout's frame wait (100 ms, it reads the frame after the
event) + from the run's first trace row (ingest) to the end of the CueBus row that delivered the cue. Tiers: fast,
explained (gated: fast p95 <= fast_cue_p95_s, explained p95 <= explained_cue_p95_s in config/budgets.yaml), panel and
referee (reported). Live numbers come from live runs (T-032 probe, T-080 judge run); a replay serves cached results
after their simulated latency / WHYLINE_REPLAY_SPEED, so replay numbers are labelled "replay" and never gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "packages" / "evals" / "out"
SCOUT_WAIT_MS = 100
TIERS = ("fast", "explained", "panel", "referee")


def slo() -> dict:
    s = yaml.safe_load((ROOT / "config" / "budgets.yaml").read_text(encoding="utf-8"))["latency_slo"]
    return {"fast": float(s["fast_cue_p95_s"]), "explained": float(s["explained_cue_p95_s"])}


def cue_latencies(traces: list[dict]) -> dict[str, list[float]]:
    """{tier: [seconds event -> delivered cue]} from trace rows."""
    start: dict[str, int] = {}
    for t in traces:
        start[t["run_id"]] = min(start.get(t["run_id"], t["started_ms"]), t["started_ms"])
    out: dict[str, list[float]] = {k: [] for k in TIERS}
    for t in traces:
        if t["executor"] == "cuebus" and t["status"] == "delivered" and t.get("branch") in out:
            end = t["started_ms"] + (t.get("latency_ms") or 0)
            out[t["branch"]].append((SCOUT_WAIT_MS + end - start[t["run_id"]]) / 1000.0)
    return out


def summarise(lat: dict[str, list[float]], source: str) -> dict:
    limits = slo()
    tiers = {}
    for k, v in lat.items():
        row = {"n": len(v)}
        if v:
            row.update(p50_s=round(float(np.percentile(v, 50)), 3), p95_s=round(float(np.percentile(v, 95)), 3),
                       max_s=round(max(v), 3))
        if k in limits:
            row["p95_limit_s"] = limits[k]
            row["passed"] = bool(v) and row["p95_s"] <= limits[k] if source == "live" else None
        tiers[k] = row
    gated = [tiers[k]["passed"] for k in limits if tiers[k]["n"]]
    return {"source": source, "tiers": tiers,
            "passed": (all(gated) if gated else None) if source == "live" else None,
            "note": None if source == "live" else "replay serves cached results after simulated latency: not gated"}


def live_traces(blackboard: Path, match_ids: list[str]) -> list[dict]:
    from blackboard import SqliteBlackboard

    bb = SqliteBlackboard(blackboard)
    rows = [t for m in match_ids for t in bb.query("traces", match_id=m)]
    bb.close()
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m evals.latency")
    ap.add_argument("--source", choices=("live", "replay"), default="replay")
    ap.add_argument("--matches", default="", help="live: comma list of match seeds or ids (9001 or m_9001)")
    ap.add_argument("--blackboard", type=Path, default=None, help="live: the run's blackboard (default "
                    "WHYLINE_BLACKBOARD / data/runtime/blackboard.sqlite)")
    ap.add_argument("--match-dir", type=Path, default=ROOT / "data" / "matches" / "4242")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    if args.source == "live":
        ids = [m if m.startswith("m_") else f"m_{m}" for m in args.matches.split(",") if m]
        if not ids:
            raise SystemExit("--source live needs --matches")
        import os
        path = args.blackboard or Path(os.environ.get("WHYLINE_BLACKBOARD") or ROOT / "data" / "runtime" /
                                       "blackboard.sqlite")
        res = {**summarise(cue_latencies(live_traces(path, ids)), "live"), "matches": ids}
    else:
        from evals.groundedness import replay_cues
        _, traces = replay_cues(args.match_dir)
        res = {**summarise(cue_latencies(traces), "replay"), "matches": [args.match_dir.name]}
    out = args.out or OUT / f"latency_{args.source}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: {x: v.get(x) for x in ("n", "p50_s", "p95_s")} for k, v in res["tiers"].items()}))
    return 1 if res["passed"] is False else 0


if __name__ == "__main__":
    sys.exit(main())
