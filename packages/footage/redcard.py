"""What the red card cost (video v3): from the real score and clock at Bruno Fernandes' foul (Man Utd 0-1 Spurs,
40:57), the engine plays the rest of the match twice from the same frozen state and the same seeds: 11 v 11, and
11 v 10 with his slot sent off (kickoff `Override(sent_off=...)`). Man Utd's win / draw / loss shares and the gap
with a paired bootstrap 95% interval (same seed per world on both sides). An estimate from the synthetic engine.

    python -m footage.redcard run <side: 11v11|11v10> [--n 200]     # one side, final scores -> scratch npz
    python -m footage.redcard combine                                 # the beat (cache/v3/red_card_cost_772400.json)
"""

from __future__ import annotations

import argparse
import json
import sys

import numpy as np

from footage.clips import ROOT, clip_dir
from footage.freeze import load, to_state

SLUG, CLIP_MS, LABEL = "manutd-spurs-2425", 772400, "#8"
SEED, FULL_TIME_MS, BOOT = 9004, 5_400_000, 5000
SENT_OFF_SLOT = 6         # CM: Bruno Fernandes' role. The role prior put him at LCB (where he stood at the foul);
#                           sending a centre-back off made the engine's United score more (10-min check, n=200)
OUT = clip_dir(SLUG) / "cache" / "redcard"


def run_side(side: str, n: int) -> dict:
    from kickoff import Override
    from rollout.core import simulate

    m = load(SLUG, CLIP_MS)
    state = to_state(m, seed=SEED)
    slot = SENT_OFF_SLOT
    override = Override(sent_off={"home": [slot]}) if side == "11v10" else None
    horizon = (FULL_TIME_MS - state.t_ms) / 1000
    sim = simulate(to_state(m, seed=SEED), override, n, horizon, SEED)
    final = np.asarray(sim.eng.score, dtype=np.int64)
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUT / f"{side}.npz", final=final, start=np.asarray(state.score[0]), slot=slot, n=n,
                        horizon_s=horizon, seed=SEED, t_ms=state.t_ms)
    return {"side": side, "n": n, "mean_final": final.mean(axis=0).round(3).tolist()}


def shares(final: np.ndarray) -> np.ndarray:
    """[N, 3] one-hot of the home result per world (win, draw, loss)."""
    d = final[:, 0] - final[:, 1]
    return np.c_[d > 0, d == 0, d < 0].astype(float)


def combine() -> dict:
    from footage.v3 import write_beat

    a, b = np.load(OUT / "11v11.npz"), np.load(OUT / "11v10.npz")
    fa, fb = a["final"], b["final"]
    n = min(len(fa), len(fb))
    sa, sb = shares(fa[:n]), shares(fb[:n])
    rng = np.random.default_rng(0)
    idx = rng.integers(0, n, size=(BOOT, n))
    gap = (sb[idx].mean(axis=1) - sa[idx].mean(axis=1))          # paired: the same worlds on both sides
    lo, hi = np.percentile(gap, [2.5, 97.5], axis=0)
    res = {k: v for k, v in zip(("win", "draw", "loss"), range(3), strict=True)}
    beat = {"clip_ms": CLIP_MS, "clock": "40:57", "team": "Manchester United", "player": {"label": LABEL,
            "name": "Bruno Fernandes", "slot": int(b["slot"])}, "score_at": a["start"].tolist(),
            "win_prob_11v11": round(float(sa[:, 0].mean()), 4), "win_prob_11v10": round(float(sb[:, 0].mean()), 4),
            "draw_11v11": round(float(sa[:, 1].mean()), 4), "draw_11v10": round(float(sb[:, 1].mean()), 4),
            "loss_11v11": round(float(sa[:, 2].mean()), 4), "loss_11v10": round(float(sb[:, 2].mean()), 4),
            "gap_ci95": {k: [round(float(lo[i]), 4), round(float(hi[i]), 4)] for k, i in res.items()},
            "gap_significant": {k: bool(lo[i] > 0 or hi[i] < 0) for k, i in res.items()},
            "expected_points": [round(float(3 * sa[:, 0].mean() + sa[:, 1].mean()), 3),
                                round(float(3 * sb[:, 0].mean() + sb[:, 1].mean()), 3)],
            "goals_for_mean": [round(float((fa[:n, 0] - a["start"][0]).mean()), 3),
                               round(float((fb[:n, 0] - b["start"][0]).mean()), 3)],
            "goals_against_mean": [round(float((fa[:n, 1] - a["start"][1]).mean()), 3),
                                   round(float((fb[:n, 1] - b["start"][1]).mean()), 3)],
            "n": int(n), "horizon": "to full time (90:00)", "horizon_s": float(a["horizon_s"]), "seed": SEED,
            "engine": "scripted_v1", "paired": "same seed per world on both sides; bootstrap 5000",
            "note": "an estimate: the synthetic engine plays on from the real frozen positions; the sent-off slot is "
                    "his role (central midfield); the ten keep their slots (no reshuffle)", "source": f"redcard/11v11.npz + redcard/11v10.npz (seed {SEED})"}
    write_beat(SLUG, "red_card_cost", CLIP_MS, beat)
    return beat


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("side", choices=("11v11", "11v10"))
    r.add_argument("--n", type=int, default=200)
    sub.add_parser("combine")
    args = ap.parse_args(argv)
    print(json.dumps(run_side(args.side, args.n) if args.cmd == "run" else combine(), indent=1))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "packages"))
    raise SystemExit(main())
