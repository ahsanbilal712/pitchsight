"""Keeper positioning beat (video v3): David Raya at Chelsea's chance in stoppage time, Arsenal v Chelsea 92:15
(clip 1382.65 s, wide main camera). Hand-marked frame: goal-area homography from the posts, the six-yard box and
the D's junctions with the box edge (8 points, RMS 0.1 m, leave-one-out <= 0.54 m). Coverage is geometry
(footage.keeper), not an engine save probability.

    python -m footage.keeper_beat
"""

from __future__ import annotations

import json
import sys

from footage.clips import ROOT
from footage.freeze import apply_h, fit_homography, save
from footage.keeper import assess

SLUG, CLIP_MS, T_MS, CLOCK = "arsenal-chelsea-2526", 1382650, 5_535_000, "92:15"
POINTS = [((0, 24.84), (220, 301)), ((0, 30.34), (565, 264)), ((0, 37.66), (975, 216)), ((0, 43.16), (1246, 188)),
          ((5.5, 24.84), (260, 432)), ((5.5, 43.16), (1399, 283)), ((16.5, 26.69), (612, 832)),
          ((16.5, 41.31), (1751, 599))]
BALL_PX, KEEPER_PX, SHOOTER_PX = (855, 332), (787, 263), (930, 407)


def run() -> dict:
    from footage.v3 import write_beat

    H, rms = fit_homography([i for _, i in POINTS], [p for p, _ in POINTS])
    ball, keeper, shooter = (tuple(round(float(v), 2) for v in apply_h(H, [px])[0])
                             for px in (BALL_PX, KEEPER_PX, SHOOTER_PX))
    moment = {"schema_version": "1.0.0", "slug": SLUG, "match_id": "m_9003", "clip_ms": CLIP_MS, "t_ms": T_MS,
              "period": 2, "clock": CLOCK, "score": [2, 1], "home_attacks": "+x",
              "frame": f"frames/moment_{CLIP_MS}.png",
              "homography": {"image_to_pitch": [[round(v, 10) for v in row] for row in H.tolist()],
                             "rms_m": round(rms, 3), "image_size": [1920, 1080],
                             "points": [{"pitch": list(p), "image": list(i)} for p, i in POINTS]},
              "players": [{"team": "home", "label": "GK", "name": "David Raya", "slot": "GK", "x": keeper[0],
                           "y": keeper[1], "vx": 0.0, "vy": 0.0, "source": "hand", "image": list(KEEPER_PX)},
                          {"team": "away", "label": "CHE-shooter", "name": None, "slot": None, "x": shooter[0],
                           "y": shooter[1], "vx": 0.0, "vy": 0.0, "source": "hand", "image": list(SHOOTER_PX)}],
              "ball": {"x": ball[0], "y": ball[1], "holder": None, "image": list(BALL_PX)},
              "actual": {"kind": "save", "target": None},
              "notes": "Hand-marked keeper-positioning frame (v3): Chelsea's close-range chance at 92:15, Raya saves "
                       "at 1383.3 s. The ball is already off the sliding Chelsea player's foot, so the shot origin "
                       "is the ball's position in this frame."}
    save(moment)
    from footage.featured import roster

    pid = roster(SLUG)["ids"]["home:GK"]
    a = assess(ball, keeper, 0.0)
    beat = {"clip_ms": CLIP_MS, "clock": CLOCK, "shot_id": 190, "shot_from": list(ball),
            "shooter": {"label": "CHE-shooter", "name": None, "x": shooter[0], "y": shooter[1]},
            "keeper": {"label": "GK", "name": "David Raya", "pid": pid, "x": keeper[0], "y": keeper[1]},
            "best": {"x": float(a["best"]["x"]), "y": float(a["best"]["y"]), "depth_m": a["best"]["depth_m"]},
            "coverage_actual": a["actual_coverage"], "coverage_best": a["best"]["coverage"], "move_m": a["move_m"],
            "shot_distance_m": a["shot_distance_m"], "save_actual": None, "save_best": None,
            "measure": "share of the goal mouth the keeper covers (shots spread evenly between the posts, his reach "
                       "growing with the time the ball takes to reach him); geometry, not a save probability",
            "assumptions": a["assumptions"], "engine": "geometry (footage.keeper)", "n": None, "seed": None,
            "homography": moment["homography"], "error_note": f"hand-marked; homography RMS {rms:.2f} m",
            "small_print": "Coverage assumes a 1.0 m standing reach plus a dive at 3.5 m/s after a 0.25 s reaction, "
                           "up to 2.6 m, against a 26 m/s shot, with shots spread evenly between the posts. "
                           "Geometry, not a save probability.",
            "source": f"moments/{CLIP_MS}.json + footage.keeper (reach 1.0 m + dive 3.5 m/s after 0.25 s, max "
                      "2.6 m; shot 26 m/s; shots uniform between the posts)"}
    write_beat(SLUG, "keeper_cone", CLIP_MS, beat)
    return {k: beat[k] for k in ("shot_from", "keeper", "best", "coverage_actual", "coverage_best", "move_m")}


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "packages"))
    print(json.dumps(run(), indent=1))
