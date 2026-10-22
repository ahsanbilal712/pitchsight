"""'Dugout called it' log (FEASIBILITY_AUDIT C.6, T-047): compare the Dugout's recommendation at 60:00 with the
style change the team actually showed in 60:00-70:00 versus 50:00-60:00.

    python -m evals.dugout_log --seed 4242

Measured from tracking and events, never from truth: press height = mean distance of the team's back four from its
own goal line while the opponents have the ball (metres); directness = share of the team's completed passes that
gain more than 15 m toward goal. The recommendation matches when every non-zero component of its style delta has the
sign of the observed change (and the change is larger than the noise floor). The caption "Dugout called it" may only
be used when `matched` is true and the recommendation actually helped (delta_win_prob > 0; a tie at 0 is no call). Writes packages/evals/out/dugout_log.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "packages" / "evals" / "out"
NOISE = {"press_height": 1.0, "directness": 0.02}        # metres; share of passes


def style_window(window, events: list[dict], team: int, t0: int, t1: int) -> dict:
    """Press height and directness for `team` (0 home, 1 away) between t0 and t1."""
    from physics.window import home_dir

    sl = (window.t_ms >= t0) & (window.t_ms < t1) & (window.possession == 1 - team)
    idx = np.flatnonzero(sl)
    rows = np.arange(11 * team + 1, 11 * team + 5)
    depths = []
    for i in idx[::10]:
        d = home_dir(int(window.period[i])) * (1 if team == 0 else -1)
        x = window.S[i, rows, 0]
        depths.append(float(np.mean(x if d > 0 else 105.0 - x)))
    side = "home" if team == 0 else "away"
    passes = [e for e in events if e["type"] == "pass" and e["team"] == side and e["outcome"] == "complete"
              and t0 <= e["t_ms"] < t1]
    direct = float(np.mean([e["attrs"]["progressive_m"] > 15.0 for e in passes])) if passes else 0.0
    return {"press_height": float(np.mean(depths)) if depths else 0.0, "directness": direct, "passes": len(passes)}


def dugout_log(seed: int = 4242) -> dict:
    from cache.manifest import CacheManifest
    from physics.window import TrackingWindow

    match_dir = ROOT / "data" / "matches" / str(seed)
    events = [json.loads(line) for line in (match_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    window = TrackingWindow.load(match_dir)
    manifest = CacheManifest.load(match_dir / "cache")
    out = {"match_id": events[0]["match_id"], "teams": {}}
    for entry in manifest.find(producer="dugout"):
        doc = manifest.read(entry)
        team = 0 if doc["team"] == "home" else 1
        t = doc["t_ms"]
        before = style_window(window, events, team, t - 600_000, t)
        after = style_window(window, events, team, t, t + 600_000)
        change = {k: after[k] - before[k] for k in NOISE}
        rec = doc["options"][0]
        comps = {k: v for k, v in rec["delta"].items() if v}
        matched = bool(comps) and all(np.sign(change[k]) == np.sign(v) and abs(change[k]) > NOISE[k]
                                      for k, v in comps.items())
        out["teams"][doc["team"]] = {"t_ms": t, "recommendation": rec["label"], "delta": rec["delta"],
                                     "delta_win_prob": rec["delta_win_prob"], "before": before, "after": after,
                                     "observed_change": {k: round(v, 3) for k, v in change.items()},
                                     "matched": matched, "caption_allowed": matched and rec["delta_win_prob"] > 0}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "dugout_log.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m evals.dugout_log")
    ap.add_argument("--seed", type=int, default=4242)
    args = ap.parse_args(argv)
    print(json.dumps(dugout_log(args.seed), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
