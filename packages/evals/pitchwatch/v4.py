"""Video v4 beats (track A): goal chance in the next 10 s, ghost futures, xG at every shot, xG race.

    python -m evals.pitchwatch.v4 decisions      # every featured freeze: actual vs every option, goal in 10 s
    python -m evals.pitchwatch.v4 ghosts         # the most typical world of each freeze's best alternative

Goal in 10 s. From a freeze (track B's moment file -> footage.freeze.to_state), each option (the action the player
really took, a pass to every labelled team-mate, a carry toward goal) is forced as the first action and the
scripted_v1 engine plays N worlds for HORIZON_S. p = share of worlds in which the attacking team scores within
the horizon, counted from the simulated goals (no model hand-off; scripted_v1 has no horizon cap; the cap
applies only to the learned policy). 95% interval: Wilson. Every option uses the same per-world random streams (world b draws
from default_rng(seed + b)), so the difference to the actual action is paired: mean of per-world differences
+- 1.96 standard errors. `verdict` says "better" or "worse" only when that interval excludes 0, else "within noise".

Ghost future: the alternative's N worlds are replayed with every player's and the ball's position recorded at
10 Hz; the medoid world (smallest summed ball-path distance to all others) is the "most typical" future, exported
in pitch metres in the moment-file frame (y from the near touchline).
"""

from __future__ import annotations

import json
import math
import sys

import numpy as np

N, HORIZON_S, SEED = 2000, 10.0, 4242
HOLD_M = 2.5                   # metres: the tracking error is ~0.5 m, a dribbler keeps the ball within ~2 m
DECISION_MOMENTS = {"liverpool-mancity-2526": [875000], "manutd-mancity-2526": [877000, 1079360, 1189840],
                    "arsenal-chelsea-2526": [1300500], "manutd-spurs-2425": [682800]}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(c - h, 4), round(c + h, 4)


def options(state, moment: dict) -> list[dict]:
    eng = state.source
    h = int(eng.holder[0])
    team = h // 11
    mates = sorted(lab for lab, row in state.labels.items() if row // 11 == team and row != h and row % 11 != 0)
    home = team == 0
    attacks_plus = (moment["home_attacks"] == "+x") == home
    out = [{"kind": "actual", **moment["actual"]}]
    out += [{"kind": "pass", "target": lab} for lab in mates]
    out.append({"kind": "carry", "direction": [1.0 if attacks_plus else -1.0, 0.0]})
    if moment["actual"]["kind"] != "shoot":
        out.append({"kind": "shoot"})
    return out


def holder_label(state) -> str | None:
    h = int(state.source.holder[0])
    return next((lab for lab, row in state.labels.items() if row == h), None)


def run_option(state, moment: dict, spec: dict, n: int, seed: int, record: bool = False):
    from footage.featured import engine_action
    from kickoff import Override
    from kickoff.engine import TICK_MS

    real = moment["actual"] if spec["kind"] == "actual" else spec
    eng = state.source.branch(state.source.t_ms, n, Override(first_action=engine_action(state, moment, real)),
                              seed=seed)
    score0 = eng.score.copy()
    steps = int(round(HORIZON_S * 1000 / TICK_MS))
    frames = [eng.S[:, :23, 0:2].astype(np.float32).copy()] if record else None
    for _ in range(steps):
        eng.step()
        if record:
            frames.append(eng.S[:, :23, 0:2].astype(np.float32).copy())
    goals = eng.score - score0
    return goals, (np.stack(frames, axis=1) if record else None)


def tracked_moment(slug: str, clip_ms: int, clock: str, period: int, score: list[int],
                   allow_loose: bool = False) -> dict | None:
    """A moment at any tracked frame (track B's moment_from_tracks, in memory: nothing is written to moments/),
    with the match clock and score from the score bug, the attacking direction from the reviewed directions, and
    the ball holder = the labelled player nearest the ball when within HOLD_M (else None: the ball is loose)."""
    from evals.pitchwatch.shotxg import HOME_ATTACKS_P2
    from footage.from_tracks import moment_from_tracks

    for dt in (0, 40, -40, 80, -80, 120, -120, 160, -160, 200, -200):   # no ball here: nearest frame with one
        try:
            m = moment_from_tracks(slug, clip_ms + dt)
            m["tracked_clip_ms"] = clip_ms + dt
            break
        except LookupError:
            m = None
    if m is None:
        return None
    mm, ss = (int(v) for v in clock.split(":"))
    home = HOME_ATTACKS_P2[slug] * (1 if period == 2 else -1)
    m.update({"t_ms": (mm * 60 + ss) * 1000, "period": period, "clock": clock, "score": score,
              "home_attacks": "+x" if home > 0 else "-x"})
    bx, by = m["ball"]["x"], m["ball"]["y"]
    near = min((p for p in m["players"] if p.get("label")), key=lambda p: math.hypot(p["x"] - bx, p["y"] - by))
    if math.hypot(near["x"] - bx, near["y"] - by) > HOLD_M:
        if allow_loose:
            m["ball"]["holder"] = None
            m["actual"] = None
            return m
        return None
    m["ball"]["holder"] = near["label"]
    m["actual"] = {"kind": "carry", "direction": [1.0 if (home > 0) == (near["team"] == "home") else -1.0, 0.0]}
    return m


def decision(slug: str, clip_ms: int, n: int = N, seed: int = SEED, moment: dict | None = None) -> dict:
    from footage.freeze import load, to_state

    moment = moment or load(slug, clip_ms)
    state = to_state(moment, seed=seed)
    team = int(state.source.holder[0]) // 11
    rows, scored = [], {}
    for spec in options(state, moment):
        try:
            goals, _ = run_option(state, moment, spec, n, seed)
        except Exception as exc:                       # an illegal option (offside target): reported, not valued
            rows.append({"option": spec, "error": f"{type(exc).__name__}: {exc}"})
            continue
        g = goals[:, team] > 0
        scored[json.dumps(spec, sort_keys=True)] = g
        rows.append({"option": spec, "p_goal_10s": round(float(g.mean()), 4), "ci95": wilson(int(g.sum()), n),
                     "goals": int(g.sum())})
    act = scored[json.dumps(rows[0]["option"], sort_keys=True)]
    for r in rows[1:]:
        if "error" in r:
            continue
        d = scored[json.dumps(r["option"], sort_keys=True)].astype(float) - act.astype(float)
        se = float(d.std(ddof=1) / math.sqrt(n))
        lo, hi = float(d.mean()) - 1.96 * se, float(d.mean()) + 1.96 * se
        r["diff_vs_actual"] = {"mean": round(float(d.mean()), 4), "ci95": [round(lo, 4), round(hi, 4)],
                               "verdict": "better" if lo > 0 else "worse" if hi < 0 else "within noise"}
    valued = [r for r in rows if "error" not in r]
    best = max(valued[1:], key=lambda r: r["p_goal_10s"], default=None)
    return {"slug": slug, "clip_ms": clip_ms, "clock": moment["clock"], "holder": holder_label(state),
            "team": "home" if team == 0 else "away", "n": n, "horizon_s": HORIZON_S, "seed": seed,
            "engine": "scripted_v1", "options": rows, "best_alternative": best["option"] if best else None,
            "method": "P(attacking team scores within 10 s) counted over n simulated worlds; Wilson 95% interval; "
                      "difference to the actual action paired by world (shared random streams)",
            "source": {"moment": f"{slug}/moments/{clip_ms}.json", "engine": "kickoff scripted_v1"}}


def ghost(slug: str, clip_ms: int, spec: dict, n: int = 500, seed: int = SEED) -> dict:
    """The medoid world of `spec` (by ball path), every player and the ball at 10 Hz, moment-file frame."""
    from footage.freeze import load, to_state

    moment = load(slug, clip_ms)
    state = to_state(moment, seed=seed)
    goals, paths = run_option(state, moment, spec, n, seed, record=True)         # [n, T, 23, 2]
    ball = paths[:, :, 22, :]
    dist = np.zeros(n)
    for i in range(n):
        dist[i] = np.linalg.norm(ball - ball[i], axis=2).mean(axis=1).sum()
    k = int(np.argmin(dist))
    P = paths[k].astype(np.float64)
    if state.mirrored:                                  # back to the moment file's frame
        P = np.stack([105.0 - P[..., 0], 68.0 - P[..., 1]], axis=-1)
    inv = {row: lab for lab, row in state.labels.items()}
    names = {p.get("label"): p.get("name") for p in moment["players"] if p.get("label")}
    team = int(state.source.holder[0]) // 11
    players = []
    for row in range(22):
        players.append({"row": row, "team": "home" if row < 11 else "away", "label": inv.get(row),
                        "name": names.get(inv.get(row)),
                        "path": [[round(float(x), 2), round(float(y), 2)] for x, y in P[:, row]]})
    return {"slug": slug, "clip_ms": clip_ms, "option": spec, "world": k, "n": n, "horizon_s": HORIZON_S,
            "seed": seed, "world_seed": seed + k, "engine": "scripted_v1", "hz": 10,
            "scored": bool(goals[k, team] > 0), "share_of_worlds_scoring": round(float((goals[:, team] > 0).mean()), 4),
            "ball": [[round(float(x), 2), round(float(y), 2)] for x, y in P[:, 22]], "players": players,
            "note": "The most typical of n simulated futures (medoid by ball path), not the most likely outcome; "
                    "players without a label were placed by role prior at the freeze."}


def xray10(slug: str, t0: float, t1: float, clock_at_t0: str, period: int, score: list[int], n: int = 1000,
           step_s: float = 0.5) -> dict:
    """Pass X-ray in goal-in-10-s terms: at every step with a ball holder, each option's P(team scores in 10 s)."""
    mm, ss = (int(v) for v in clock_at_t0.split(":"))
    samples = []
    for t in np.arange(t0, t1 + 1e-9, step_s):
        clip_ms = int(round(t * 1000))
        sec = mm * 60 + ss + int(t - t0)
        m = tracked_moment(slug, clip_ms, f"{sec // 60:02d}:{sec % 60:02d}", period, score)
        if m is None:
            samples.append({"clip_ms": clip_ms, "holder": None, "note": "ball loose (no player within 2.5 m)"})
            continue
        r = decision(slug, clip_ms, n=n, moment=m)
        holder = next(p for p in m["players"] if p.get("label") == r["holder"])
        opts = []
        for o in r["options"]:
            if "error" in o or o["option"]["kind"] == "actual":
                continue
            tgt = o["option"].get("target")
            pl = next((p for p in m["players"] if p.get("label") == tgt), None)
            opts.append({"label": tgt or o["option"]["kind"], "kind": o["option"]["kind"],
                         "x": pl and pl["x"], "y": pl and pl["y"], "p_goal_10s": o["p_goal_10s"], "ci95": o["ci95"]})
        opts.sort(key=lambda o: -o["p_goal_10s"])
        top = [o for o in opts if o["kind"] == "pass"]
        samples.append({"clip_ms": clip_ms, "holder": r["holder"], "holder_xy": [holder["x"], holder["y"]],
                        "team": r["team"], "options": opts,
                        "best_clear": bool(len(top) >= 2 and top[0]["ci95"][0] > top[-1]["ci95"][1])})
    return {"slug": slug, "t0_clip_ms": int(t0 * 1000), "t1_clip_ms": int(t1 * 1000), "samples": samples, "n": n,
            "horizon_s": HORIZON_S, "seed": SEED, "engine": "scripted_v1",
            "method": "each option forced as the first action from the tracked state, n worlds, P(the holder's team "
                      "scores within 10 s), Wilson 95%; labels are track ids (t<id>) unless matched to a hand label",
            "source": {"tracks": f"{slug}/tracks/*.json", "converter": "footage.from_tracks.moment_from_tracks"}}


def _near(P: np.ndarray, mirrored: bool) -> np.ndarray:
    """Engine frame -> moment-file frame (y from the near touchline)."""
    return np.stack([105.0 - P[..., 0], 68.0 - P[..., 1]], axis=-1) if mirrored else P


def _branch(state, moment: dict, spec: dict, n: int, seed: int) -> dict:
    """Median ball path and 25-75% spread band every 0.5 s, the medoid world, and its outcome time."""
    from kickoff.engine import TICK_MS
    goals, paths = run_option(state, moment, spec, n, seed, record=True)          # [n, T, 23, 2]
    team = int(state.source.holder[0]) // 11
    P = _near(paths.astype(np.float64), state.mirrored)
    ball = P[:, :, 22, :]
    every = 500 // TICK_MS
    med = np.median(ball[:, ::every], axis=0)
    rad = np.percentile(np.linalg.norm(ball[:, ::every] - med[None], axis=2), 75, axis=0)
    dist = np.array([np.linalg.norm(ball - ball[i], axis=2).mean(axis=1).sum() for i in range(n)])
    k = int(np.argmin(dist))
    return {"goals": goals[:, team] > 0, "median": med, "band": rad, "world": k, "paths": P[k], "team": team}


def c_format(slug: str, clip_ms: int, n: int = N, seed: int = SEED) -> tuple[dict, dict]:
    """Track C's v4 goal10_<clip_ms> and ghost_future_<clip_ms> from the committed decision."""
    from evals.pitchwatch.insights import FOOTAGE
    from footage.freeze import load, to_state
    from kickoff.engine import TICK_MS
    dec = json.loads((FOOTAGE / slug / "cache" / "v4" / f"goal10_decision_{clip_ms}.json").read_text())["result"]
    moment = load(slug, clip_ms)
    state = to_state(moment, seed=seed)
    names = {p.get("label"): p.get("name") for p in moment["players"] if p.get("label")}
    valued = [o for o in dec["options"][1:] if "error" not in o]
    better = [o for o in valued if o["diff_vs_actual"]["verdict"] == "better"]
    alt = max(better or valued, key=lambda o: o["p_goal_10s"])

    def label(spec):
        if spec["kind"] == "pass":
            return f"Pass to {names.get(spec['target']) or spec['target']}"
        return {"shoot": "Shot", "carry": "Carry on", "actual": None}.get(spec["kind"], spec["kind"])
    act_spec = dec["options"][0]["option"]
    a = _branch(state, moment, act_spec, n, seed)
    b = _branch(state, moment, alt["option"], n, seed)
    for br, row in ((a, dec["options"][0]), (b, alt)):        # same seeds, same worlds: must match the decision
        assert abs(float(br["goals"].mean()) - row["p_goal_10s"]) < 1e-9, "decision and branch disagree"
    actual_kind = moment["actual"]["kind"]
    common = {"n": n, "horizon_s": HORIZON_S, "seed": seed, "engine": "scripted_v1",
              "source": {"decision": f"{slug}/cache/v4/goal10_decision_{clip_ms}.json",
                         "moment": f"{slug}/moments/{clip_ms}.json"}}
    goal10 = {"clip_ms": clip_ms, "clock": dec["clock"], "team": dec["team"], "holder": dec["holder"],
              "actual": {"kind": actual_kind, "label": label({"kind": actual_kind, **moment["actual"]}),
                         "target": moment["actual"].get("target"), "p": dec["options"][0]["p_goal_10s"],
                         "ci95": dec["options"][0]["ci95"]},
              "alternative": {"kind": alt["option"]["kind"], "label": label(alt["option"]),
                              "target": alt["option"].get("target"), "p": alt["p_goal_10s"], "ci95": alt["ci95"]},
              "difference": alt["diff_vs_actual"],
              "median_paths": {k: [[round(float(x), 2), round(float(y), 2)] for x, y in br["median"]]
                               for k, br in (("actual", a), ("alternative", b))},
              "band": {k: [[round(float(x), 2), round(float(y), 2), round(float(r), 2)]
                           for (x, y), r in zip(br["median"], br["band"], strict=True)]
                       for k, br in (("actual", a), ("alternative", b))},
              "band_note": "radius = 75th percentile of the worlds' ball distance from the median, every 0.5 s",
              **common}
    inv = {row: lab for lab, row in state.labels.items()}
    P = b["paths"]
    frames = [{"t_ms": i * TICK_MS, "ball": [round(float(P[i, 22, 0]), 2), round(float(P[i, 22, 1]), 2)],
               "players": [{"label": inv.get(r), "name": names.get(inv.get(r)), "team": "home" if r < 11 else "away",
                            "x": round(float(P[i, r, 0]), 2), "y": round(float(P[i, r, 1]), 2)} for r in range(22)]}
              for i in range(P.shape[0])]
    scored = bool(b["goals"][b["world"]])
    ghost = {"clip_ms": clip_ms, "branch": "alternative", "option": alt["option"], "label": label(alt["option"]),
             "step_ms": TICK_MS, "horizon_s": HORIZON_S, "frames": frames,
             "outcome": {"label": "goal" if scored else "no goal within 10 s", "at_ms": None},
             "share_of_worlds_scoring": alt["p_goal_10s"], **common,
             "representative": {"which": "medoid", "world": b["world"], "world_seed": seed + b["world"]},
             "note": "The most typical of the n futures (medoid by ball path), not the likeliest outcome; players "
                     "without a label were placed by role prior at the freeze."}
    return goal10, ghost


def unforced(state, n: int, seed: int) -> np.ndarray:
    """Goals per team within HORIZON_S, engine left to play (no forced action)."""
    from kickoff.engine import TICK_MS
    eng = state.source.branch(state.source.t_ms, n, None, seed=seed)
    score0 = eng.score.copy()
    for _ in range(int(round(HORIZON_S * 1000 / TICK_MS))):
        eng.step()
    return (eng.score - score0) > 0


def oracle_goal10(slug: str = "liverpool-mancity-2526", t0: float = 867.0, t1: float = 875.0,
                  clock_t0: str = "86:15", period: int = 2, score: list[int] | None = None, n: int = N,
                  seed: int = SEED) -> dict:
    """P(home / away scores in the next 10 s) on the Oracle window, every 0.5 s, unforced from the tracked state."""
    from footage.freeze import load, to_state
    score = score or [1, 1]
    mm, ss = (int(v) for v in clock_t0.split(":"))
    samples = []
    for t in np.arange(t0, t1 + 1e-9, 0.5):
        clip_ms = int(round(t * 1000))
        sec = mm * 60 + ss + int(t - t0)
        m = tracked_moment(slug, clip_ms, f"{sec // 60:02d}:{sec % 60:02d}", period, score, allow_loose=True)
        if m is None:
            samples.append({"clip_ms": clip_ms, "p_goal_10s": None, "note": "no ball detected within 0.2 s"})
            continue
        g = unforced(to_state(m, seed=seed), n, seed)
        samples.append({"clip_ms": clip_ms, "tracked_clip_ms": m["tracked_clip_ms"], "clock": m["clock"],
                        "holder": m["ball"]["holder"],
                        "p_goal_10s": {"home": round(float(g[:, 0].mean()), 4), "away": round(float(g[:, 1].mean()), 4)},
                        "ci95": {"home": wilson(int(g[:, 0].sum()), n), "away": wilson(int(g[:, 1].sum()), n)}})
    end = int(round(t1 * 1000))
    ref_state = to_state(load(slug, end), seed=seed)
    g = unforced(ref_state, n, seed)
    dec = json.loads((__import__("evals.pitchwatch.insights", fromlist=["FOOTAGE"]).FOOTAGE / slug / "cache" / "v4" /
                      f"goal10_decision_{end}.json").read_text())["result"]
    return {"slug": slug, "start_clip_ms": int(t0 * 1000), "end_clip_ms": end, "step_ms": 500, "samples": samples,
            "n": n, "horizon_s": HORIZON_S, "seed": seed, "engine": "scripted_v1",
            "at_freeze": {"clip_ms": end, "state": f"{slug}/moments/{end}.json",
                          "unforced": {"home": round(float(g[:, 0].mean()), 4), "away": round(float(g[:, 1].mean()), 4),
                                       "ci95_home": wilson(int(g[:, 0].sum()), n)},
                          "forced_actual_shot": {"p": dec["options"][0]["p_goal_10s"],
                                                 "ci95": dec["options"][0]["ci95"]}},
            "method": "every 0.5 s: the tracked frame (moment_from_tracks, in memory) -> engine state; the engine "
                      "plays on unforced for 10 s in n worlds; p = share of worlds where the team scores. Not the "
                      "same quantity as goal10_decision's actual (which forces the shot): both are given at the "
                      "freeze. The window samples come from tracking; at_freeze uses track B's reviewed moment file.",
            "source": {"tracks": f"{slug}/tracks/62.json", "calib": f"{slug}/calib/62_refined.json"}}


def main(argv: list[str] | None = None) -> int:
    from evals.pitchwatch.v3 import write
    kind = (argv or sys.argv[1:])[0]
    if kind == "oracle":
        print(write("liverpool-mancity-2526", "oracle_goal10", 867000, oracle_goal10(), version="v4"))
        return 0
    if kind == "cformat":
        for slug, moments in DECISION_MOMENTS.items():
            for clip_ms in moments:
                g10, gh = c_format(slug, clip_ms)
                print(write(slug, "goal10", clip_ms, g10, version="v4"))
                print(write(slug, "ghost_future", clip_ms, gh, version="v4"))
        return 0
    if kind == "xray":
        res = xray10("manutd-spurs-2425", 240.0, 242.5, "02:13", 1, [0, 0])
        print(write("manutd-spurs-2425", "pass_xray_goal10", 240000, res, version="v4"))
        return 0
    for slug, moments in DECISION_MOMENTS.items():
        for clip_ms in moments:
            if kind == "decisions":
                res = decision(slug, clip_ms)
                print(write(slug, "goal10_decision", clip_ms, res, version="v4"))
            elif kind == "ghosts":
                dec = json.loads((__import__("evals.pitchwatch.insights", fromlist=["FOOTAGE"]).FOOTAGE / slug /
                                  "cache" / "v4" / f"goal10_decision_{clip_ms}.json").read_text())["result"]
                if dec["best_alternative"]:
                    print(write(slug, "ghost_future", clip_ms, ghost(slug, clip_ms, dec["best_alternative"]),
                                version="v4"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
