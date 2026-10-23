"""Overlays on the playing real clips (demo.live, video v3).

Interpolation rules are checked without footage; one preview per beat type renders on the Liverpool clip when it is
on this machine (clips are never committed), from small inline data in the beat formats of the shared note.
"""

import json

import numpy as np
import pytest

from demo import live as L

CLIP = L.FOOTAGE / "liverpool-mancity-2526" / "clip.mp4"
HAS_CLIP = CLIP.exists() and (L.FOOTAGE / "liverpool-mancity-2526" / "calib" / "62_refined.json").exists()
BASE = {"clip": "liverpool-mancity-2526", "shot_id": 62, "kits": {"home": [214, 32, 52], "away": [120, 182, 232]}}


def test_bracket_clamps_and_interpolates():
    s = [{"clip_ms": 1000}, {"clip_ms": 1500}, {"clip_ms": 2000}]
    assert L.bracket(s, 500) == (0, 1, 0.0)
    assert L.bracket(s, 1250) == (0, 1, 0.5)
    assert L.bracket(s, 2500) == (2, 2, 0.0)


def write(tmp_path, name, result):
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps({"record": "tool_result", "result": result}))
    return str(path)


def scene(cls, tmp_path, name, result, **extra):
    L.ROOT, root = L.Path("/"), L.ROOT                     # absolute data paths in tests
    try:
        return cls({**BASE, "name": name, "data": write(tmp_path, name, result), **extra})
    finally:
        L.ROOT = root


@pytest.mark.skipif(not HAS_CLIP, reason="clip or refined calibration not on this machine")
def test_printed_values_are_samples_not_interpolations(tmp_path):
    samples = [{"clip_ms": 870000 + 500 * k, "frame": 43500 + 25 * k, "p_shot_10s_smoothed": {"home": v, "away": 0},
                "threat_zone": {"home": None, "away": None}} for k, v in enumerate((0.10, 0.40))]
    o = scene(L.Oracle, tmp_path, "o", {"start_clip_ms": 870000, "end_clip_ms": 870500, "samples": samples, "n": 100,
                                       "horizon_s": 8, "seed": 1})
    bar, value, _ = o.at(870.25)
    assert value == 0.10 and 0.10 < bar < 0.40                 # the bar eases, the number is the latest sample
    sg = scene(L.SpeedGun, tmp_path, "sg", {
        "player": {"label": "#8", "name": "Dominik Szoboszlai"}, "shot_id": 62,
        "samples": [{"clip_ms": 870000, "x": 70.0, "y": 20.0, "speed_kmh": 20.0},
                    {"clip_ms": 871000, "x": 76.0, "y": 20.0, "speed_kmh": 21.6}],
        "top_speed_kmh": 21.6, "top_speed_clip_ms": 871000, "distance_m": 6.0, "start_clip_ms": 870000,
        "end_clip_ms": 871000})
    assert np.allclose(sg.pos(870.5), [73.0, 20.0]) and sg.freeze_at() == 871.0


@pytest.mark.skipif(not HAS_CLIP, reason="clip or refined calibration not on this machine")
def test_each_beat_previews_on_the_real_clip(tmp_path):
    beats = {
        "ghost": (L.GhostDefender, {"clip_ms": 875000, "defender": {"label": "C4", "name": "Test Defender",
                                                                      "x": 90.57, "y": 20.5},
                                    "ghost": {"x": 88.5, "y": 15.0}, "metres_needed": 5.9, "p_goal_actual": 0.053,
                                    "p_goal_ghost": 0.021, "n": 200, "horizon_s": 8, "seed": 1}, 878.0),
        "keeper": (L.KeeperCone, {"clip_ms": 875000, "shot_from": [79.27, 19.08], "keeper": {"name": "Test Keeper",
                                                                                            "x": 102.0, "y": 32.3},
                                  "best": {"x": 102.6, "y": 30.4}, "save_actual": 0.71, "save_best": 0.83, "n": 200,
                                  "seed": 1}, 878.0),
        "red": (L.RedCardCost, {"clip_ms": 875000, "team": "home", "win_prob_11v11": 0.41, "win_prob_11v10": 0.27,
                                "n": 500, "seed": 1}, 877.0),
    }
    for name, (cls, result, t) in beats.items():
        img = np.asarray(scene(cls, tmp_path, name, result).preview(t))
        assert img.shape == (L.H, L.W, 3)
        L.Image.fromarray(img).save(tmp_path / f"live_{name}.png")
        card = img[L.H - 300:L.H - 100, 120:600].astype(int)    # the card darkens the bottom left
        assert card.mean() < 90, (name, card.mean())


@pytest.mark.skipif(not HAS_CLIP, reason="clip or refined calibration not on this machine")
def test_v4_beats_render(tmp_path):
    """The xG bubble, the ghost future and the xG race render from data in the shared v4 formats."""
    shots = {"shots": [{"clip_ms": 875900, "shot_id": 62, "shooter": {"label": "#8", "name": "Test Shooter"},
                        "x": 79.3, "y": 19.1, "xg": 0.03, "outcome": "goal", "outcome_clip_ms": 876300,
                        "camera_ok": True}]}
    img = np.asarray(scene(L.ShotXG, tmp_path, "shot", shots, index=0, team="home").preview(876.6))
    assert img.shape == (L.H, L.W, 3)
    frames = [{"t_ms": k * 100, "ball": [80.0 + k * 0.5, 20.0],
               "players": [{"label": "#8", "team": "home", "x": 78.0 + k * 0.3, "y": 19.0}]} for k in range(30)]
    gf = scene(L.GhostFuture, tmp_path, "ghost", {"clip_ms": 875000, "step_ms": 100, "frames": frames,
                                                 "outcome": {"label": "goal", "at_ms": 2000},
                                                 "source": {"n": 200, "seed": 1}}, shot_id=62, team="home")
    assert np.allclose(gf.at(150)["ball"], [80.75, 20.0])
    assert gf.preview(875.0 + 0.6 + 1.0).size == (L.W, L.H)
    race = {"home": "A", "away": "B", "series": [{"clip_ms": 11000, "clock": "72:00", "home_xg": 0.1, "away_xg": 0.0},
                                                 {"clip_ms": 900000, "clock": "87:00", "home_xg": 1.2,
                                                  "away_xg": 0.4}], "events": []}
    assert scene(L.XGRace, tmp_path, "race", race, t0=1.0).preview(9.0).size == (L.W, L.H)


def test_v6_labels_never_placeholders():
    """Owner (v6): a verified name, else a shirt number, else no label at all."""
    from demo.v6 import who
    assert who({"name": "Bruno Fernandes"}) == "Fernandes"
    assert who({"name": None, "shirt": 19}) == "#19"
    assert who({"name": None, "shirt": None, "track_id": 7}) is None
    assert who(None) is None
