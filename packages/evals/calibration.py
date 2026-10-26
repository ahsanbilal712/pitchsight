"""Counterfactual calibration and placebo on held-out matches.

    python -m evals.calibration --seeds 51..350 --engine-from packages/policy/artifacts/gate.json --out packages/evals/out

For every held-out match (calibration seeds 51-350, never used for training) the match is re-simulated from its
seed; explained moments are the on-ball decisions (pass, shot, clearance) whose leverage, the GoalIn8sHead swing the
Scout uses (newsroom.scout_rules.Leverage), reaches 0.04. At each moment the unforced branch runs from the decision
state (n = 200, horizon 8 s, seed 4242, the engine named in gate.json) and its P(goal for the attacking team within
the horizon, with the head hand-off) is compared with what happened in the real match in the next 8 s: Brier score,
log-loss, base rate, a 10-bin reliability diagram. The placebo (rollout.placebo) forces the action actually taken.
Writes calibration.json and calibration.png.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "data" / "matches" / "corpus"
DECISIONS = {"pass", "shot", "clearance"}
EXPLAINED_LEVERAGE = 0.04
HORIZON_S, N, SEED = 8.0, 200, 4242


def parse_seeds(text: str) -> list[int]:
    out: list[int] = []
    for part in text.split(","):
        if ".." in part:
            a, b = part.split("..")
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out


def match_moments(seed: int, engine: str, max_moments: int | None = None) -> list[dict]:
    """Explained moments of one held-out match with the branch forecast, realised outcome and placebo."""
    from kickoff import Engine, League
    from newsroom.scout_rules import Leverage
    from physics.window import TrackingWindow
    from rollout import MatchRef, placebo, rollout

    league = League.load(ROOT / "data" / "league")
    home, away = league.fixture(seed)
    rec = Engine(league, home, away, seed=seed).play()
    events = rec.events
    window = TrackingWindow.from_tracking(rec.tracking)
    lev = Leverage(window)
    cands = [e for e in events if e["type"] in DECISIONS and e["t_ms"] >= 1000]
    values = lev.at([e["t_ms"] for e in cands])
    chosen = [(e, float(v)) for e, v in zip(cands, values, strict=True) if v >= EXPLAINED_LEVERAGE]
    if max_moments:
        chosen = chosen[:max_moments]
    goals = [(e["t_ms"], e["team"]) for e in events if e["type"] == "goal"]
    match = MatchRef(seed, home, away)
    match._events = events
    out = []
    for e, leverage in chosen:
        t = e["t_ms"] - 100
        state = match.state_at(t)
        src = state.source
        if src.holder[0] < 0 or src.dead[0]:
            continue
        team = "home" if src.holder[0] < 11 else "away"
        fut = rollout(state, None, N, HORIZON_S, SEED, engine=engine, decide_now=True, events=events)
        p = fut.p_goal_home if team == "home" else fut.p_goal_away
        realised = int(any(t < gt <= t + int(HORIZON_S * 1000) and gteam == team for gt, gteam in goals))
        try:
            pl = placebo(match, t, n=N, horizon_s=HORIZON_S, seed=SEED, engine=engine)
        except Exception as err:                       # an action the engine cannot replay: report, do not hide
            pl = {"testable": False, "passed": None, "error": type(err).__name__}
        out.append({"seed": seed, "t_ms": t, "event_id": e["id"], "type": e["type"], "team": team,
                    "leverage": round(leverage, 4), "p_goal": float(p), "realised": realised,
                    "placebo_testable": bool(pl.get("testable")), "placebo_passed": pl.get("passed")})
    return out


def _job(args: tuple[int, str, int | None]) -> list[dict]:
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    return match_moments(*args)


def summarise(rows: list[dict], engine: str) -> dict:
    from sklearn.metrics import brier_score_loss, log_loss
    y = np.array([r["realised"] for r in rows])
    p = np.clip(np.array([r["p_goal"] for r in rows]), 1e-6, 1 - 1e-6)
    testable = [r for r in rows if r["placebo_testable"]]
    return {"brier": float(brier_score_loss(y, p)), "log_loss": float(log_loss(y, p, labels=[0, 1])),
            "base_rate": float(y.mean()), "mean_forecast": float(p.mean()), "n_moments": len(rows),
            "n_matches": len({r["seed"] for r in rows}), "placebo_pass_rate":
            float(np.mean([r["placebo_passed"] for r in testable])) if testable else None,
            "placebo_testable": len(testable), "engine": engine, "n": N, "horizon_s": HORIZON_S, "seed": SEED,
            "explained_leverage": EXPLAINED_LEVERAGE, "thresholds": {"brier_max": 0.18, "placebo_pass_rate_min": 0.95}}


def plot(rows: list[dict], summary: dict, path: Path) -> None:
    from heads.calibration import reliability_diagram
    y = np.array([r["realised"] for r in rows])
    p = np.array([r["p_goal"] for r in rows])
    reliability_diagram({"unforced branch": (y, p)}, path, "Counterfactual calibration: P(goal within 8 s)",
                        f"{summary['n_moments']:,} moments, {summary['n_matches']} held-out matches; "
                        f"Brier {summary['brier']:.4f}, base rate {summary['base_rate']:.3f}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m evals.calibration")
    ap.add_argument("--seeds", default="51..350")
    ap.add_argument("--engine-from", type=Path, default=ROOT / "packages" / "policy" / "artifacts" / "gate.json")
    ap.add_argument("--out", type=Path, default=ROOT / "packages" / "evals" / "out")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--max-moments", type=int, default=None, help="per match (smoke runs)")
    args = ap.parse_args(argv)
    engine = json.loads(args.engine_from.read_text(encoding="utf-8"))["engine"]
    seeds = parse_seeds(args.seeds)
    if any(not 51 <= s <= 350 for s in seeds):
        raise SystemExit("calibration uses the held-out seeds 51-350 only")
    started = time.perf_counter()
    with Pool(args.workers) as pool:
        parts = pool.map(_job, [(s, engine, args.max_moments) for s in seeds], chunksize=1)
    rows = [r for part in parts for r in part]
    summary = summarise(rows, engine)
    summary["minutes"] = round((time.perf_counter() - started) / 60, 1)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "calibration.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (args.out / "calibration_moments.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows),
                                                        encoding="utf-8")
    plot(rows, summary, args.out / "calibration.png")
    print(json.dumps(summary, indent=1))
    ok = summary["brier"] <= 0.18 and (summary["placebo_pass_rate"] or 0) >= 0.95
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
