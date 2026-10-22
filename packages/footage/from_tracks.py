"""Pitchwatch tracking -> moment file (T-107): track A's calib/<shot>.json and tracks/<shot>.json (format v1,
shared notes track-a-pitchwatch-format.md) become data/footage/<slug>/moments/<clip_ms>.json.

    python -m footage.from_tracks <slug> <clip_ms> [--write]

Track A's pitch frame has y from the FAR touchline; moment files use event.schema.json's y from the NEAR side
(origin bottom-left), so y -> 68 - y and the homography is composed with that flip. Velocities are the 1 s
difference of each track's position. Labels, names, clock, score and the real action come from the hand-marked
moment for the same clip_ms when there is one (each hand-marked player takes the nearest track of his team within
2.5 m); unmatched tracks are labelled t<track_id>. Without --write it prints how far tracking and the hand marks
disagree; with --write the hand-marked file is kept as moments/hand/<clip_ms>.json and replaced.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

from footage.clips import CLIPS, ROOT, clip_dir
from footage.freeze import PITCH_W, moments_dir, save
from footage.tag import side

FLIP = np.array([[1.0, 0.0, 0.0], [0.0, -1.0, PITCH_W], [0.0, 0.0, 1.0]])   # (x, y_far) -> (x, y_near)
MATCH_RADIUS_M = 2.5


def usable_shot(folder: Path, clip_s: float) -> dict:
    shots = json.loads((folder / "shots.json").read_text())["shots"]
    for s in shots:
        if s.get("usable") and s["start"] <= clip_s <= s["end"]:
            return s
    raise LookupError(f"no usable shot contains {clip_s:.2f} s")


def homography(calib: dict, frame: int) -> tuple[np.ndarray, dict]:
    """Image -> pitch (y from the near touchline) at `frame`, from the nearest frame whose fit is trusted."""
    ok = [int(k) for k, v in calib["frames"].items() if v.get("ok")]
    if not ok:
        raise LookupError("no trusted homography in this shot")
    k = min(ok, key=lambda f: abs(f - frame))
    entry = calib["frames"][str(k)]
    return FLIP @ np.asarray(entry["H"], float), {"frame": k, "rms_px": entry.get("rms_px")}


def _sample(tracks: dict, frame: int) -> dict:
    return min(tracks["frames"], key=lambda s: abs(s["frame"] - frame))


def _flip(xy) -> tuple[float, float]:
    return float(xy[0]), float(PITCH_W - xy[1])


def moment_from_tracks(slug: str, clip_ms: int, base: dict | None = None, folder: Path | None = None) -> dict:
    folder = folder or clip_dir(slug)
    clip = CLIPS[slug]
    shot = usable_shot(folder, clip_ms / 1000)
    calib = json.loads((folder / "calib" / f"{shot['id']}.json").read_text())
    tracks = json.loads((folder / "tracks" / f"{shot['id']}.json").read_text())
    fps = float(tracks["fps"])
    frame = round(clip_ms / 1000 * fps)
    now, before = _sample(tracks, frame), _sample(tracks, frame - round(fps))
    dt = (now["frame"] - before["frame"]) / fps
    prev = {p["track_id"]: _flip(p["xy"]) for p in before["players"] if p.get("xy")}
    team_side = {int(k): side(v.get("name", ""), clip) for k, v in tracks["teams"].items()}
    players = []
    for p in now["players"]:
        if p.get("role") == "referee" or p.get("team") is None or not p.get("xy"):
            continue
        x, y = _flip(p["xy"])
        vx = vy = 0.0
        if dt > 0 and p["track_id"] in prev:
            vx, vy = (x - prev[p["track_id"]][0]) / dt, (y - prev[p["track_id"]][1]) / dt
        players.append({"team": team_side[int(p["team"])], "label": f"t{p['track_id']}", "name": None,
                        "slot": "GK" if p.get("role") == "goalkeeper" else None, "x": round(x, 2), "y": round(y, 2),
                        "vx": round(vx, 2), "vy": round(vy, 2), "source": "tracking",
                        "image": [round(v) for v in p["foot_px"]], "track_id": p["track_id"]})
    H, used = homography(calib, frame)
    ball = now.get("ball")
    if ball and ball.get("xy"):
        bx, by = _flip(ball["xy"])
        ball_doc = {"x": round(bx, 2), "y": round(by, 2), "holder": None, "image": ball.get("px"),
                    "conf": ball.get("conf")}
    elif base:
        ball_doc = {k: base["ball"].get(k) for k in ("x", "y", "image")} | {"holder": None, "source": "hand"}
    else:
        raise LookupError("no ball in the tracking sample and no hand-marked moment to take it from")
    moment = {"schema_version": "1.0.0", "slug": slug, "match_id": clip["match_id"], "clip_ms": int(clip_ms),
              "frame": f"frames/moment_{clip_ms}.png",
              "homography": {"image_to_pitch": np.round(H, 10).tolist(), "image_size": calib["image_size"],
                             "rms_px": used["rms_px"], "source": f"calib/{shot['id']}.json frame {used['frame']}"},
              "players": players, "ball": ball_doc,
              "tracking": {"shot_id": shot["id"], "frame": now["frame"], "velocity_dt_s": round(dt, 3)}}
    if base:
        moment.update({k: base[k] for k in ("t_ms", "period", "clock", "score", "home_attacks", "actual", "notes")
                       if k in base})
        inherit_labels(moment, base)
    else:
        moment["home_attacks"] = infer_home_attacks(players)
    holder = moment["ball"].get("holder")
    if holder is None:
        near = [(math.hypot(p["x"] - moment["ball"]["x"], p["y"] - moment["ball"]["y"]), p["label"]) for p in players]
        if near and min(near)[0] <= 2.0:
            moment["ball"]["holder"] = min(near)[1]
    return moment


def inherit_labels(moment: dict, base: dict) -> dict:
    """Each hand-marked labelled player gives his label and name to the nearest track of his team within 2.5 m; the
    ball holder follows his label. Returns {label: distance_m} for the report."""
    taken, dist = set(), {}
    for h in base["players"]:
        if not h.get("label") or h.get("source") == "prior":
            continue
        cands = [(math.hypot(p["x"] - h["x"], p["y"] - h["y"]), i) for i, p in enumerate(moment["players"])
                 if p["team"] == h["team"] and i not in taken]
        if not cands:
            continue
        d, i = min(cands)
        if d <= MATCH_RADIUS_M:
            taken.add(i)
            moment["players"][i].update(label=h["label"], name=h.get("name"),
                                        slot=h.get("slot") if h.get("slot") == "GK" else moment["players"][i]["slot"])
            dist[h["label"]] = round(d, 2)
    if base["ball"].get("holder") in dist:
        moment["ball"]["holder"] = base["ball"]["holder"]
    moment["label_match_m"] = dist
    return dist


def infer_home_attacks(players: list[dict]) -> str:
    gk = [p for p in players if p["slot"] == "GK" and p["team"] == "home"]
    xs = [p["x"] for p in gk] or [p["x"] for p in players if p["team"] == "home"]
    return "+x" if xs and np.mean(xs) < 52.5 else "-x"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("clip_ms", type=int)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    path = moments_dir(args.slug) / f"{args.clip_ms}.json"
    base = json.loads(path.read_text()) if path.exists() else None
    m = moment_from_tracks(args.slug, args.clip_ms, base)
    seen = {p["label"] for p in m["players"] if not p["label"].startswith("t")}
    missing = sorted({p["label"] for p in (base or {}).get("players", []) if p.get("label")} - seen)
    print(json.dumps({"players": len(m["players"]), "labels_matched_m": m.get("label_match_m"),
                      "hand_labels_without_track": missing, "holder": m["ball"]["holder"]}, indent=1))
    if args.write:
        if base:
            (moments_dir(args.slug) / "hand").mkdir(exist_ok=True)
            (moments_dir(args.slug) / "hand" / f"{args.clip_ms}.json").write_text(json.dumps(base, indent=1) + "\n")
        print(save(m))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "packages"))
    raise SystemExit(main())
