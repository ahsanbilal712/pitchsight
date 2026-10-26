"""Oracle threat front on a real build-up (video v2): the Oracle (rollout.oracle) run on every second of a
tracked window, with the threat zone in the frame's own coordinates so it can be drawn on the broadcast.

    python -m footage.threat <slug> <start_ms> <end_ms> [--step-ms 1000] [--n 100]

Each sample is a moment built from track A's Pitchwatch tracks (footage.from_tracks), its clock, score and attack
direction taken from the clip's featured moment; 100 unforced worlds over 8 s give p(shot in 10 s) per team (the
same estimate for seconds 8-10 as the Oracle) and the attacking team's shot origins, summarised as a threat zone:
the mean and 2-sigma ellipse of where the shots came from, in the moment file's pitch metres. No model call.
Output: data/footage/<slug>/cache/oracle/window_<start_ms>.json (manifest kind analytics; a model_cache
tool_result record, the window under `result`).
"""

from __future__ import annotations

import argparse
import math
import sys

import numpy as np

from footage.clips import CLIPS, ROOT, load_config
from footage.freeze import PITCH_L, PITCH_W, load, to_state
from footage.from_tracks import moment_from_tracks

HORIZON_S = 8.0
HOLDER_REACH_M = 6.0
SMOOTH = 0.5                 # exponential smoothing of p_shot_10s across samples, for drawing


def base_header(slug: str) -> dict:
    """Clock origin, score and attack direction from the clip's featured moment (the window is in the same half)."""
    f = next(f for f in load_config()["featured"] if f["slug"] == slug)
    m = load(slug, f["clip_ms"])
    return {"clip_ms": m["clip_ms"], "t_ms": m["t_ms"], "period": m["period"], "score": m["score"],
            "home_attacks": m["home_attacks"]}


def clock(t_ms: int) -> str:
    s = t_ms // 1000
    return f"{s // 60:02d}:{s % 60:02d}"


def ellipse(points: np.ndarray) -> dict | None:
    """Mean and 2-sigma ellipse (semi-axes, angle in degrees) of 2-D points; None for fewer than 3."""
    if len(points) < 3:
        return None
    c = points.mean(axis=0)
    w, v = np.linalg.eigh(np.cov(points.T) + np.eye(2) * 0.25)
    order = np.argsort(w)[::-1]
    w, v = w[order], v[:, order]
    return {"cx": round(float(c[0]), 2), "cy": round(float(c[1]), 2), "rx": round(float(2 * math.sqrt(w[0])), 2),
            "ry": round(float(2 * math.sqrt(w[1])), 2), "angle_deg": round(math.degrees(math.atan2(v[1, 0], v[0, 0])), 1)}


def sample(slug: str, clip_ms: int, head: dict, n: int, seed: int, last_holder: str | None = None) -> dict:
    from rollout.core import simulate
    from rollout.futures import heads
    from rollout.oracle import SHOTS_PER_GOAL, WINDOW_S, _world_shots

    t_ms = head["t_ms"] + (clip_ms - head["clip_ms"])
    base = {**head, "t_ms": t_ms, "clock": clock(t_ms), "actual": None, "players": [], "ball": {"holder": None}}
    try:
        m = moment_from_tracks(slug, clip_ms, base)
    except LookupError:                       # no trustworthy ball nearby: keep the last holder, ball at his feet
        m = moment_from_tracks(slug, clip_ms, {**base, "ball": {"x": 0.0, "y": 0.0, "holder": None}})
        m["ball"]["x"] = None
    if m["ball"].get("x") is not None and m["ball"].get("holder") is None:   # a pass or a loose ball
        near = min(((math.hypot(p["x"] - m["ball"]["x"], p["y"] - m["ball"]["y"]), p["label"]) for p in m["players"]),
                   default=(math.inf, None))
        if near[0] <= HOLDER_REACH_M:
            m["ball"]["holder"], m["ball"]["holder_assumed"] = near[1], True
    if m["ball"].get("holder") is None and last_holder in {p["label"] for p in m["players"]}:
        h = next(p for p in m["players"] if p["label"] == last_holder)
        m["ball"].update(x=h["x"], y=h["y"], holder=last_holder, holder_assumed=True)
    if m["ball"].get("x") is None:
        raise LookupError(f"{clip_ms}: no ball and no holder to carry over")
    state = to_state(m, seed=seed)
    state.source.record_events = True          # the Oracle reads the shots from the worlds' event logs
    sim = simulate(state, None, n, HORIZON_S, seed)
    eng = sim.eng
    shots = _world_shots(eng)
    goal8s, _ = heads()
    from heads.features import state_features

    team = np.where(eng.possession >= 0, eng.possession, np.where(eng.last_touch >= 11, 1, 0))
    feats = state_features(eng.S, eng.ball_z, eng.holder, team, np.full(n, eng.period), np.full(n, eng.t_ms),
                           ~eng.dead)
    head8 = goal8s.predict(feats.assign(poss_team=team))
    rest = max(0.0, WINDOW_S - HORIZON_S) / 8.0
    out = {"clip_ms": clip_ms, "t_ms": t_ms, "clock": clock(t_ms), "frame": m["tracking"]["frame"],
           "holder": m["ball"].get("holder"), "holder_assumed": bool(m["ball"].get("holder_assumed")),
           "homography": m["homography"], "ball": {k: m["ball"].get(k) for k in ("x", "y")},
           "holder_team": next((p["team"] for p in m["players"] if p["label"] == m["ball"].get("holder")), None),
           "p_shot_10s": {}, "threat_zone": {}, "shot_origins": {}}
    for k, side in enumerate(("home", "away")):
        had = np.array([any(s[0] == side for s in ws) for ws in shots])
        extra = np.minimum(1.0, head8[:, k] * SHOTS_PER_GOAL * rest)
        out["p_shot_10s"][side] = round(float(np.mean(had + (~had) * extra)), 4)
        firsts = [next(s for s in ws if s[0] == side) for ws in shots if any(s[0] == side for s in ws)]
        pts = np.array([s[1][:2] for s in firsts], float).reshape(-1, 2)
        if state.mirrored and len(pts):
            pts = np.c_[PITCH_L - pts[:, 0], PITCH_W - pts[:, 1]]     # back into the frame's coordinates
        out["shot_origins"][side] = np.round(pts, 1).tolist()
        out["threat_zone"][side] = ellipse(pts)
    return out


def run(slug: str, start_ms: int, end_ms: int, step_ms: int = 1000, n: int = 100) -> dict:
    from cache.manifest import CacheManifest
    from footage.featured import open_cache

    head = base_header(slug)
    seed = int(CLIPS[slug]["match_id"][2:])
    samples, last = [], None
    for t in range(start_ms, end_ms + 1, step_ms):
        samples.append(sample(slug, t, head, n, seed, last))
        last = samples[-1]["holder"] or last
    prev: dict[str, float] = {}
    for s in samples:
        s["p_shot_10s_smoothed"] = {k: round(v if k not in prev else SMOOTH * v + (1 - SMOOTH) * prev[k], 4)
                                    for k, v in s["p_shot_10s"].items()}
        prev = s["p_shot_10s_smoothed"]
    doc = {"schema_version": "1.0.0", "match_id": CLIPS[slug]["match_id"], "slug": slug, "start_clip_ms": start_ms,
           "end_clip_ms": end_ms, "step_ms": step_ms, "n": n, "horizon_s": HORIZON_S, "engine": "scripted_v1",
           "seed": seed, "coordinates": "moment file pitch metres (105 x 68, y from the near touchline)",
           "estimate_note": "seconds 8-10 valued by the goal-in-8-s head (rollout.oracle)", "samples": samples}
    manifest = open_cache(slug)
    manifest.add(CacheManifest.key(doc["match_id"], None, "oracle", f"window_{start_ms}", "scripted", seed),
                 "analytics", {"$schema": "model_cache.schema.json", "schema_version": "1.0.0", "record": "tool_result",
                               "result": doc}, f"oracle/window_{start_ms}.json", producer="oracle", version=f"window_{start_ms}",
                 model="scripted", seed=seed)
    manifest.save()
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("start_ms", type=int)
    ap.add_argument("end_ms", type=int)
    ap.add_argument("--step-ms", type=int, default=1000)
    ap.add_argument("--n", type=int, default=100)
    args = ap.parse_args(argv)
    doc = run(args.slug, args.start_ms, args.end_ms, args.step_ms, args.n)
    for s in doc["samples"]:
        z = s["threat_zone"]["home"] or {}
        print(s["clock"], s["clip_ms"], "holder", s["holder_team"], "p_shot_10s", s["p_shot_10s"]["home"],
              "smoothed", s["p_shot_10s_smoothed"]["home"],
              "home zone", {k: z.get(k) for k in ("cx", "cy", "rx", "ry")})
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "packages"))
    raise SystemExit(main())
