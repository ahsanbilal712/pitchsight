"""Video v8 ("Pitchsight" intro, "how it works"): the SEE and MEASURE steps and the intro fact-check.

    python -m evals.pitchwatch.v8          # cache/v8/see_<clip_ms>.json, xg_surface_0.json, intro_facts_0.json

SEE: one clean wide frame's real boxes (the tracker's players, the tiled detector's ball) and 3 s of the tracked
positions in pitch metres from the v6 live frames. MEASURE: the reference xG surface on a 1 m grid. Facts: each
intro claim checked against the repo's own records, with the corrected wording.
"""

from __future__ import annotations

import json
import sys

from evals.pitchwatch.insights import FOOTAGE
from evals.pitchwatch.shotxg import reference_xg
from evals.pitchwatch.v5 import GOAL_Y, SOURCE, L, W, gate

SEES = [("liverpool-mancity-2526", 62, "live_802600.json", 870200, 870200, 873200),   # clip, shot, live file, frame,
        ("manutd-mancity-2526", 104, "live_869000.json", 876400, 874400, 877400)]   # positions window (clip_ms)
# Amad's window ends before track 4's identity switch at 878.1 s


def see(slug: str, shot: int, live_file: str, clip_ms: int, t0: int, t1: int) -> dict:
    d = FOOTAGE / slug
    tracks = json.loads((d / "tracks" / f"{shot}.json").read_text())
    tiled = json.loads((d / "tracks" / f"{shot}.ball_tiled.json").read_text())["frames"]
    live = json.loads((d / "cache" / "v6" / live_file).read_text())["result"]
    calib = json.loads((d / "calib" / f"{shot}.json").read_text())
    r = min(tracks["frames"], key=lambda f: abs(f["t"] * 1000 - clip_ms))
    lf = {f["clip_ms"]: f for f in live["frames"]}
    at = {p["track_id"]: p for p in lf[clip_ms]["players"]}
    boxes = []
    for p in r["players"]:
        q = at.get(p["track_id"])
        boxes.append({"track_id": p["track_id"], "bbox": p["bbox"], "conf": p["conf"],
                      "team": q["team"] if q else None,
                      "role": ("goalkeeper" if q["keeper"] else "player") if q else "unassigned (referee or no team)",
                      "name": q["name"] if q else None, "shirt": q["shirt"] if q else None,
                      "feet_px": p["foot_px"], "pitch_xy": [q["x"], q["y"]] if q else None})
    key = min(tiled, key=lambda k: abs(int(k) - r["frame"]))             # the tiled pass keys its own sample frames
    balls = tiled[key] if abs(int(key) - r["frame"]) <= tracks["step"] else []
    ball = {"bbox": balls[0]["bbox"], "conf": balls[0]["conf"], "source": "tiled (640 px tiles, full resolution)",
            "pitch_xy": lf[clip_ms]["ball"] and [lf[clip_ms]["ball"]["x"], lf[clip_ms]["ball"]["y"]]} if balls else None
    path = []
    for t in range(t0, t1, 100):
        f = lf.get(t)
        if f is None:
            continue
        path.append({"clip_ms": t, "ball": f["ball"] and {"x": f["ball"]["x"], "y": f["ball"]["y"]},
                     "players": [{k: p[k] for k in ("track_id", "team", "keeper", "name", "shirt", "x", "y")}
                                 for p in f["players"]]})
    return {
        "shot_id": shot, "frame": r["frame"], "fps": tracks["fps"], "clip_ms": clip_ms, "image_size": calib["image_size"],
        "players_in_view": sum(1 for b in boxes if b["team"]), "boxes": boxes, "ball": ball,
        "positions": {"hz": 10, "start_clip_ms": path[0]["clip_ms"], "end_clip_ms": path[-1]["clip_ms"], "samples": path},
        "how": {"detector": "RF-DETR Medium 1.11.2 (COCO-pretrained, Apache-2.0; not trained by us), threshold 0.3 "
                            "people; the ball on 640 px tiles of the full 1920x1080 frame, threshold 0.2",
                "tracker": "trackers.ByteTrackTracker 2.6.1 (ids across frames)",
                "teams": "kit colour of each box's torso, clustered into two teams (k-means), keepers by position",
                "pitch": "our camera calibration: a pan-tilt-zoom camera fitted to the pitch lines each frame, feet "
                         "(bottom centre of the box) projected to metres"},
        "coordinates": "bbox/feet in image pixels of the clip frame; pitch_xy and positions in metres, x from the left "
                       "goal line, y from the NEAR touchline; names and shirts only within track B's names_live windows",
        "source": {"tracks": f"{slug}/tracks/{shot}.json", "ball": f"{slug}/tracks/{shot}.ball_tiled.json",
                   "positions": f"{slug}/cache/v6/{live_file}", "calib": f"{slug}/calib/{shot}.json"}}


def xg_surface() -> dict:
    rows = []
    for j in range(int(W)):
        y = j + 0.5
        rows.append([round(reference_xg(max(L - (i + 0.5), 0.5), abs(y - GOAL_Y)), 3) if i + 0.5 >= L / 2 else 0.0
                     for i in range(int(L))])
    return {"goal_x": L, "cell_m": 1.0, "nx": int(L), "ny": int(W), "values": rows, "model": SOURCE,
            "order": "values[j][i]: j = y index from the NEAR touchline (centre j + 0.5 m), i = x index from the left "
                     "goal line (centre i + 0.5 m); the goal attacked is at x = 105 (mirror x for the other end); 0 in "
                     "the attacker's own half (no shots there in the data); positions on the goal line valued 0.5 m out",
            "benchmarks": gate()["benchmarks"], "penalty": 0.76,
            "source": "evals.pitchwatch.shotxg.reference_xg (Soccermatics' published logistic fit; we use its "
                      "coefficients, we did not fit it)"}


def intro_facts() -> dict:
    heads = json.loads((FOOTAGE.parent.parent / "packages/heads/artifacts/metrics.json").read_text())
    pas = heads["pass"]
    enc = json.loads((FOOTAGE.parent.parent / "packages/heads/artifacts/metrics_encoder.json").read_text())
    pol_gate = json.loads((FOOTAGE.parent.parent / "packages/policy/artifacts/gate.json").read_text())
    pol_data = json.loads((FOOTAGE.parent.parent / "packages/policy/artifacts/dataset_report.json").read_text())
    return {"claims": [
        {"claim": "computer vision tracks all 22 players from one broadcast camera",
         "verdict": "not exact: the camera shows part of the pitch",
         "use": "Computer vision tracks every player in view from one broadcast camera",
         "facts": ["players in view per tracked wide frame: about 11-16 on average in the featured passages (e.g. "
                   "15.6 in Liverpool 802600, 10.7 in Amad's 869000); 18 or more of 22 on about 11% of all tracked "
                   "frames (v7 coverage report)",
                   "detector: RF-DETR Medium 1.11.2, COCO-pretrained (Apache-2.0), not trained by us; person recall "
                   "0.9927 on 200 hand-labelled frames (T-105, packages/evals/pitchwatch/recall.py)",
                   "tracker: ByteTrack (trackers 2.6.1); teams by kit colour; our camera calibration puts feet on the "
                   "pitch in metres (check points mean 0.32 m, max 2.21 m against a 1.5 m gate, T-104 still open)",
                   "ball: the same detector on 640 px tiles; 32 of 32 sampled detections were the ball"]},
        {"claim": "models we trained",
         "verdict": "true only if it names what was trained and that the training data is simulated",
         "use": "A pass model we trained on 2.1 million passes from 1,600 simulated matches",
         "facts": [f"pass model (the one trained model behind the on-screen numbers): LightGBM, "
                   f"{pas['rows']['train']:,} training passes from {heads['_data']['matches_per_split']['train']:,} "
                   f"matches simulated by our Kickoff engine (val {heads['_data']['matches_per_split']['val']}, test "
                   f"{heads['_data']['matches_per_split']['test']}); test AUC {pas['test']['auc']:.3f}, calibration "
                   f"error {pas['test']['ece']:.4f}",
                   "other heads trained on the same 2,000 simulated matches (xG, goal in 8 s, chaos, win probability) "
                   "are not used for v5-v8 on-screen numbers: shot xG is the published reference model",
                   f"MomentEncoder: trained on MPS on {enc['matches_train']} simulated matches ({enc['states_train']:,} "
                   f"states) in {enc['minutes']} min, test purity {enc['purity_test']} (gate 0.6); not behind any "
                   "v5-v8 number",
                   f"decision policy (set transformer, about 4.7M parameters): trained on MPS on "
                   f"{pol_data['games_per_split']['train']['kickoff']:,} simulated matches plus "
                   f"{pol_data['games_per_split']['train']['grf']} GRF games (Radke & Tilbury, licence unconfirmed); it "
                   f"failed its gate ({pol_gate['reasons'][0]}), so the engine stayed scripted_v1; no v6-v8 number uses a "
                   "rollout (v5's cut ghost-future figure used 2,000 scripted_v1 rollouts)"]},
        {"claim": "an xG model fitted on 8,451 Premier League shots",
         "verdict": "true for the model, but it is published, not ours",
         "use": "A published xG model (Soccermatics), fitted on 8,451 Premier League shots from 2017/18 (Wyscout data)",
         "facts": ["evals.pitchwatch.shotxg.reference_xg uses Soccermatics' published logistic coefficients (distance, "
                   "angle and their interactions); we did not fit it",
                   "sanity bands pass: six-yard central 0.30-0.50, edge of box 0.06-0.12, 30 m 0.02-0.04; penalty "
                   "0.76 is Wyscout's fixed value (evals.pitchwatch.v5 gate)"]},
    ], "source": {"heads": "packages/heads/artifacts/metrics.json", "encoder": "packages/heads/artifacts/metrics_encoder.json",
                  "policy": "packages/policy/artifacts/gate.json, dataset_report.json", "data": "docs/DATA.md"}}


def main(argv: list[str] | None = None) -> int:
    from evals.pitchwatch.v3 import write
    for spec in SEES:
        print(write(spec[0], "see", spec[3], see(*spec), version="v8"))
    print(write(SEES[0][0], "xg_surface", 0, xg_surface(), version="v8"))
    print(write(SEES[0][0], "intro_facts", 0, intro_facts(), version="v8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
