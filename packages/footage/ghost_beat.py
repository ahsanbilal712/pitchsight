"""Ghost defender beats (video v3): Mbeumo's and Dorgu's goals against Manchester City (Man Utd v City 2025/26).

    python -m footage.ghost_beat

For each goal: the shot frame from track A's tracks (shot 127: Mbeumo, track 25, clip 1079.36 s; shot 137: Dorgu,
track 6, clip 1189.84 s), the City players' positions one second earlier, and footage.ghost: the defender with the
least ground to cover into the shooting cone, the metres, whether he could cover them at 7 m/s, and the goal chance
with him there (the engine's own shot value, and n forced-shot rollouts). The beat's freeze is one second before the
shot, where the defender starts. Defender shirt numbers are not readable at broadcast size, so they are not named.
"""

from __future__ import annotations

import json
import sys

from footage.clips import ROOT, clip_dir
from footage.freeze import save
from footage.from_tracks import _flip, moment_from_tracks
from footage.ghost import ghost, rollout_check

SLUG, T_AVAIL_S, N, SEED, HORIZON_S = "manutd-mancity-2526", 1.0, 200, 9002, 2.0
GOALS = [
    {"name": "Bryan Mbeumo", "label": "Mbeumo", "shot": 127, "track": 25, "shot_ms": 1079360, "t_ms": 3_867_000,
     "clock": "64:27", "score": [0, 0]},
    {"name": "Patrick Dorgu", "label": "Dorgu", "shot": 137, "track": 6, "shot_ms": 1189840, "t_ms": 4_528_000,
     "clock": "75:28", "score": [1, 0]},
]


def one(g: dict) -> dict:
    from footage.featured import roster
    from footage.v3 import write_beat

    base = {"t_ms": g["t_ms"], "period": 2, "clock": g["clock"], "score": g["score"], "home_attacks": "-x",
            "actual": {"kind": "shoot", "target": None}, "players": [], "ball": {"holder": None}}
    m = moment_from_tracks(SLUG, g["shot_ms"], base)
    shooter = next(p for p in m["players"] if p["label"] == f"t{g['track']}")
    shooter.update(label=g["label"], name=g["name"])
    m["ball"].update(x=round(shooter["x"] - 0.3, 2), y=shooter["y"], holder=g["label"])
    early_ms = g["shot_ms"] - int(T_AVAIL_S * 1000)
    tracks = json.loads((clip_dir(SLUG) / "tracks" / f"{g['shot']}.json").read_text())
    fr = min(tracks["frames"], key=lambda f: abs(f["frame"] - round(early_ms / 1000 * tracks["fps"])))
    earlier = {f"t{p['track_id']}": _flip(p["xy"]) for p in fr["players"] if p.get("xy")}
    res = ghost(m, g["label"], earlier, T_AVAIL_S)
    d = res["ghost"]
    defender = next(p for p in m["players"] if p["label"] == d["label"])
    defender.update(label=f"CITY-{g['label']}")              # a stable label (roster id) for the unnamed defender
    m["notes"] = (f"Shot frame of {g['name']}'s goal from track A's tracks/{g['shot']}.json (v3 ghost defender); "
                  f"the ghost defender is {defender['label']} (track {d['label'][1:]}), shirt number not readable.")
    save(m)
    ids = roster(SLUG)["ids"]
    actual = rollout_check(m, g["label"], None, n=N, seed=SEED)
    ghosted = rollout_check(m, g["label"], {defender["label"]: tuple(d["to"])}, n=N, seed=SEED)
    beat = {"clip_ms": early_ms, "shot_clip_ms": g["shot_ms"], "clock": g["clock"], "shot_id": g["shot"],
            "shooter": {"label": g["label"], "name": g["name"], "pid": ids.get(f"home:{g['label']}"),
                        "track_id": g["track"], "x": shooter["x"], "y": shooter["y"]},
            "defender": {"label": defender["label"], "name": None, "pid": ids.get(f"away:{defender['label']}"),
                         "track_id": int(d["label"][1:]), "x": d["from"][0], "y": d["from"][1],
                         "at_shot": [defender["x"], defender["y"]]},
            "ghost": {"x": d["to"][0], "y": d["to"][1]}, "metres_needed": d["metres"], "reach_m": d["reach_m"],
            "reachable": d["reachable"], "t_avail_s": T_AVAIL_S, "top_speed_ms": res["top_speed_ms"],
            "p_goal_actual": actual, "p_goal_ghost": ghosted,
            "p_goal_formula": {"actual": res["before"]["p_goal"], "ghost": res["after"]["p_goal"]},
            "n": N, "horizon_s": HORIZON_S, "seed": SEED, "engine": "scripted_v1",
            "measure": "goal chance of the shot in the engine (forced shot, n rollouts); the defender moved into the "
                       "shooting cone from where he was one second before the shot, at up to 7 m/s",
            "homography": m["homography"], "error_note": "tracking about 0.5 m (not paint-refined)",
            "source": f"moments/{g['shot_ms']}.json + tracks/{g['shot']}.json + footage.ghost"}
    write_beat(SLUG, "ghost_defender", early_ms, beat)
    return {k: beat[k] for k in ("clock", "metres_needed", "reachable", "p_goal_actual", "p_goal_ghost",
                                 "p_goal_formula")}


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "packages"))
    print(json.dumps([one(g) for g in GOALS], indent=1))
