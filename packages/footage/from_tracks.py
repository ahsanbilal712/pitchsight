"""Pitchwatch tracking -> moment file: track A's calib/<shot>.json and tracks/<shot>.json (format v1,
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
from footage.freeze import PITCH_L, PITCH_W, moments_dir, save
from footage.tag import side

FLIP = np.array([[1.0, 0.0, 0.0], [0.0, -1.0, PITCH_W], [0.0, 0.0, 1.0]])   # (x, y_far) -> (x, y_near)
MATCH_RADIUS_M = 2.5
CONFLICT_IMAGE_PX = 12.0          # hand mark and track feet this close in the image are one player
BALL_MIN_CONF = 0.3


def overrides(folder: Path, clip_ms: int) -> dict[str, str]:
    """Hand corrections of tracking labels for one frame, moments/overrides.json {"<clip_ms>": {"<track_id>":
    "referee" | "home" | "away" | "home:goalkeeper" | "away:goalkeeper"}} (kit clusters and ID switches)."""
    path = folder / "moments" / "overrides.json"
    return json.loads(path.read_text()).get(str(clip_ms), {}) if path.exists() else {}


def apply_override(p: dict, fix: str | None) -> dict:
    if not fix:
        return p
    if fix == "referee":
        return {**p, "role": "referee", "team": None}
    team, _, role = fix.partition(":")
    return {**p, "team": team, "role": role or ("goalkeeper" if p.get("role") == "goalkeeper" else "player")}


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


def _good_ball(ball: dict | None) -> bool:
    """A ball detection worth using: on the pitch (1 m margin) and not a low-confidence blob."""
    if not ball or not ball.get("xy"):
        return False
    x, y = ball["xy"]
    return (ball.get("conf") or 1.0) >= BALL_MIN_CONF and -1 <= x <= PITCH_L + 1 and -1 <= y <= PITCH_W + 1


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
    team_side.update({"home": "home", "away": "away"})
    fixes = overrides(folder, clip_ms)
    players = []
    for p in now["players"]:
        p = apply_override(p, fixes.get(str(p["track_id"])))
        if p.get("role") == "referee" or not p.get("xy"):
            continue
        x, y = _flip(p["xy"])
        if p.get("team") is None:                 # keepers come without a kit cluster: the goal they stand in
            if not (x < 18 or x > PITCH_L - 18) or base is None:
                continue
            p = {**p, "role": "goalkeeper", "team": _keeper_team(base, x)}
        vx = vy = 0.0
        if dt > 0 and p["track_id"] in prev:
            vx, vy = (x - prev[p["track_id"]][0]) / dt, (y - prev[p["track_id"]][1]) / dt
        players.append({"team": team_side[p["team"] if p["team"] in ("home", "away") else int(p["team"])], "label": f"t{p['track_id']}", "name": None,
                        "slot": "GK" if p.get("role") == "goalkeeper" else None, "x": round(x, 2), "y": round(y, 2),
                        "vx": round(vx, 2), "vy": round(vy, 2), "source": "tracking",
                        "image": [round(v) for v in p["foot_px"]], "track_id": p["track_id"]})
    H, used = homography(calib, frame)
    ball, ball_frame = now.get("ball"), now["frame"]
    if not _good_ball(ball):                  # occluded here: the nearest sample within half a second that has it
        near = [s for s in tracks["frames"] if _good_ball(s.get("ball")) and abs(s["frame"] - frame) <= fps / 2]
        if near:
            best = min(near, key=lambda s: abs(s["frame"] - frame))
            ball, ball_frame = best["ball"], best["frame"]
    if _good_ball(ball):
        bx, by = _flip(ball["xy"])
        ball_doc = {"x": round(bx, 2), "y": round(by, 2), "holder": None, "image": ball.get("px"),
                    "conf": ball.get("conf"), "frame": ball_frame}
    elif base and base["ball"].get("x") is not None:
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


def _keeper_team(base: dict, x: float) -> str:
    """The team whose keeper defends the goal at this end (from the hand-marked moment's attack direction)."""
    home_defends_left = base["home_attacks"] == "+x"
    return "home" if (x < PITCH_L / 2) == home_defends_left else "away"


def common_mode_velocity(players: list[dict]) -> tuple[float, float]:
    """Mean velocity of all tracked players: a large value moving everyone the same way is homography drift
    between the two frames, not play."""
    v = np.array([[p["vx"], p["vy"]] for p in players if p["source"] == "tracking"]) if players else np.zeros((0, 2))
    return (round(float(v[:, 0].mean()), 2), round(float(v[:, 1].mean()), 2)) if len(v) else (0.0, 0.0)


def inherit_labels(moment: dict, base: dict) -> dict:
    """Each hand-marked labelled player gives his label and name to the nearest track of his team within 2.5 m,
    closest pairs first (two players in one merged box: the nearer hand mark takes the track, the other keeps his
    hand mark); the ball holder follows his label. Returns {label: distance_m} for the report."""
    taken, dist = set(), {}
    hands = [h for h in base["players"] if h.get("label") and h.get("source") != "prior"]
    pairs = sorted((math.hypot(p["x"] - h["x"], p["y"] - h["y"]), j, i) for j, h in enumerate(hands)
                   for i, p in enumerate(moment["players"]) if p["team"] == h["team"])
    for d, j, i in pairs:
        h = hands[j]
        if d > MATCH_RADIUS_M or i in taken or h["label"] in dist:
            continue
        taken.add(i)
        moment["players"][i].update(label=h["label"], name=h.get("name"),
                                    slot=h.get("slot") if h.get("slot") == "GK" else moment["players"][i]["slot"])
        dist[h["label"]] = round(d, 2)
    for h in hands:
        if h["label"] in dist:
            continue
        # a track of the other team on the same spot: the kit cluster and the hand mark disagree. Where both have
        # image points, the same spot means the same feet (a different player standing close is not a conflict)
        other = [(math.hypot(p["x"] - h["x"], p["y"] - h["y"]), i) for i, p in enumerate(moment["players"])
                 if p["team"] != h["team"] and i not in taken and p["label"].startswith("t")
                 and not (h.get("image") and p.get("image")
                          and math.dist(h["image"], p["image"]) > CONFLICT_IMAGE_PX)]
        if other and min(other)[0] <= 1.0:
            moment.setdefault("team_conflicts", []).append(
                {"label": h["label"], "hand_team": h["team"], "track": moment["players"][min(other)[1]]["label"],
                 "distance_m": round(min(other)[0], 2)})
    conflicted = {c["label"] for c in moment.get("team_conflicts", [])}
    for h in base["players"]:                 # seen by hand but not tracked (occluded, merged boxes): keep the hand mark
        if h.get("label") and h.get("source") != "prior" and h["label"] not in dist and h["label"] not in conflicted \
                and sum(p["team"] == h["team"] for p in moment["players"]) < 11:   # else an unlabelled track is him
            moment["players"].append({**{k: h.get(k) for k in ("team", "label", "name", "slot", "x", "y", "image")},
                                      "vx": 0.0, "vy": 0.0, "source": "hand"})
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
    hand = moments_dir(args.slug) / "hand" / f"{args.clip_ms}.json"
    path = hand if hand.exists() else path          # re-runs start from the hand marks, not the tracked file
    base = json.loads(path.read_text()) if path.exists() else None
    m = moment_from_tracks(args.slug, args.clip_ms, base)
    seen = {p["label"] for p in m["players"] if not p["label"].startswith("t")}
    missing = sorted({p["label"] for p in (base or {}).get("players", []) if p.get("label")} - seen)
    print(json.dumps({"players": len(m["players"]), "labels_matched_m": m.get("label_match_m"),
                      "hand_labels_without_track": missing, "team_conflicts": m.get("team_conflicts", []),
                      "holder": m["ball"]["holder"], "common_mode_velocity": common_mode_velocity(m["players"])},
                     indent=1))
    if args.write:
        if base:
            (moments_dir(args.slug) / "hand").mkdir(exist_ok=True)
            (moments_dir(args.slug) / "hand" / f"{args.clip_ms}.json").write_text(json.dumps(base, indent=1) + "\n")
        print(save(m))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "packages"))
    raise SystemExit(main())
