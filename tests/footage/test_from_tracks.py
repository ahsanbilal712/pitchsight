"""Pitchwatch format v1 -> moment file (T-107): y flip, 1 s velocities, labels from the hand marks, a state that
branches. A synthetic shots/calib/tracks fixture; no media."""

import json

import numpy as np

from footage.freeze import apply_h, to_state
from footage.from_tracks import FLIP, moment_from_tracks

FPS = 50.0
H_A = np.array([[0.05, 0.002, 3.0], [0.001, 0.06, -2.0], [0.0, 0.00001, 1.0]])   # image -> (x, y from far side)


def player(tid, team, x, y_far, role="player"):
    u, v = apply_h(np.linalg.inv(H_A), [(x, y_far)])[0]
    return {"track_id": tid, "team": team, "role": role, "bbox": [0, 0, 1, 1], "foot_px": [u, v], "xy": [x, y_far],
            "conf": 0.9}


def fixture(tmp_path):
    folder = tmp_path / "liverpool-mancity-2526"
    (folder / "calib").mkdir(parents=True)
    (folder / "tracks").mkdir()
    (folder / "shots.json").write_text(json.dumps({"summary": {}, "shots": [
        {"id": 62, "start": 800.0, "end": 900.0, "usable": True}]}))
    frames = {str(f): {"H": H_A.tolist(), "rms_px": 1.2, "ok": f % 2 == 0} for f in range(43700, 43800)}
    (folder / "calib" / "62.json").write_text(json.dumps({"fps": FPS, "image_size": [1920, 1080], "frames": frames}))
    before = [player(1, 0, 75.0, 50.0), player(2, 0, 87.5, 59.0), player(3, 1, 101.0, 36.0, "goalkeeper"),
              player(4, 1, 85.0, 40.0), {"track_id": 9, "team": None, "role": "referee", "xy": [60, 30],
                                         "foot_px": [1, 1], "bbox": [0, 0, 1, 1]}]
    now = [player(1, 0, 78.0, 49.0), player(2, 0, 87.5, 59.0), player(3, 1, 102.0, 35.7, "goalkeeper"),
           player(4, 1, 86.0, 40.0)]
    (folder / "tracks" / "62.json").write_text(json.dumps({
        "fps": FPS, "step": 2, "teams": {"0": {"name": "Liverpool"}, "1": {"name": "Man City"}},
        "frames": [{"frame": 43700, "t": 874.0, "players": before, "ball": None},
                   {"frame": 43750, "t": 875.0, "players": now, "ball": {"px": [1, 1], "xy": [78.5, 49.2],
                                                                          "conf": 0.6}}]}))
    return folder


BASE = {"t_ms": 5_183_000, "period": 2, "clock": "86:23", "score": [1, 1], "home_attacks": "+x",
        "actual": {"kind": "shoot", "target": None},
        "players": [{"team": "home", "label": "#8", "name": "Dominik Szoboszlai", "x": 77.5, "y": 19.5},
                    {"team": "home", "label": "#11", "name": "Mohamed Salah", "x": 87.0, "y": 9.5},
                    {"team": "away", "label": "GK", "name": None, "slot": "GK", "x": 102.0, "y": 32.5}],
        "ball": {"x": 79.0, "y": 19.0, "holder": "#8"}}


def test_tracks_become_a_moment_with_flipped_y_velocities_and_labels(tmp_path):
    m = moment_from_tracks("liverpool-mancity-2526", 875000, BASE, fixture(tmp_path))
    by = {p["label"]: p for p in m["players"]}
    assert set(by) == {"#8", "#11", "GK", "t4"}                      # the referee is dropped
    assert (by["#8"]["x"], by["#8"]["y"]) == (78.0, 19.0)             # y from the near side: 68 - 49
    assert (by["#8"]["vx"], by["#8"]["vy"]) == (3.0, 1.0)             # 1 s difference, y flipped
    assert by["#8"]["name"] == "Dominik Szoboszlai" and by["GK"]["slot"] == "GK" and by["t4"]["team"] == "away"
    assert m["ball"]["holder"] == "#8" and m["ball"]["y"] == 18.8 and m["clock"] == "86:23"
    assert m["homography"]["source"] == "calib/62.json frame 43750"
    H = np.asarray(m["homography"]["image_to_pitch"])
    assert np.allclose(H, FLIP @ H_A, atol=1e-8)
    assert np.allclose(apply_h(H, [by["#8"]["image"]])[0], (78.0, 19.0), atol=0.05)
    st = to_state(m)                                                  # fills the rest by role prior and branches
    assert int(st.holder[0]) == st.labels["#8"]


def test_keeper_without_kit_cluster_and_team_conflict_are_reported(tmp_path):
    folder = fixture(tmp_path)
    path = folder / "tracks" / "62.json"
    doc = json.loads(path.read_text())
    sample = doc["frames"][1]["players"]
    sample[2] = {**sample[2], "team": None, "role": "other"}         # keeper: no kit cluster
    sample[3] = {**sample[3], "team": 0}                              # an away player clustered as home
    path.write_text(json.dumps(doc))
    base = {**BASE, "players": [*BASE["players"], {"team": "away", "label": "C4", "x": 86.0, "y": 28.0}]}
    m = moment_from_tracks("liverpool-mancity-2526", 875000, base, folder)
    gk = next(p for p in m["players"] if p["label"] == "GK")
    assert gk["team"] == "away" and gk["slot"] == "GK"               # home attacks +x: the right goal is away's
    assert m["team_conflicts"] == [{"label": "C4", "hand_team": "away", "track": "t4", "distance_m": 0.0}]


def test_hand_marked_player_without_a_track_is_kept(tmp_path):
    base = {**BASE, "players": [*BASE["players"], {"team": "away", "label": "C2", "x": 70.0, "y": 60.0}]}
    m = moment_from_tracks("liverpool-mancity-2526", 875000, base, fixture(tmp_path))
    c2 = next(p for p in m["players"] if p["label"] == "C2")
    assert c2["source"] == "hand" and (c2["x"], c2["y"]) == (70.0, 60.0)
