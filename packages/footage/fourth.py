"""Fourth Official on a real foul (video v2): Bruno Fernandes on James Maddison, Man Utd v Spurs, 40:57.

    python -m footage.fourth            # moment, ruling, evidence, cue (Fact Checker gate on the reviewed text)

The contact frame comes from track A's tracks/90.json (frame 23172, clip 772.4 s): the fouler and the fouled player
are the two tracks that meet there. The assessment uses the Fourth Official's own measures (fourth_official.foul):
the contact point (midpoint of the two players at contact), the fouler's closing speed toward the fouled player
(projected relative velocity over the 0.5 s before contact; the spread over other windows is kept as its
uncertainty) and whether the contact is inside the penalty area. The on-screen text is written in review
(review/footage/fo_<slug>_<clip_ms>.md), always says it is an assessment, not a ruling, and must pass the Fact
Checker against the clip's evidence (the tagged foul and red-card events, linked to the two players, and a
closing-speed fact). No model call.
"""

from __future__ import annotations

import json
import math
import re
import sys
from dataclasses import asdict

import numpy as np

from footage.clips import CLIPS, ROOT, clip_dir, load_config
from footage.freeze import PITCH_W, save
from footage.from_tracks import moment_from_tracks

SLUG, CLIP_MS, FRAME = "manutd-spurs-2425", 772400, 23172
FOULER, FOULED = 22, 3                          # track ids at the contact frame
LABELS = {FOULER: ("home", "#8", "Bruno Fernandes"), FOULED: ("away", "#10", "James Maddison")}
T_MS, CLOCK, SCORE = 2_457_000, "40:57", [0, 1]  # score bug at the contact frame
WINDOWS = ((FRAME - 15, FRAME), (FRAME - 18, FRAME - 3), (FRAME - 22, FRAME - 7))   # 0.5 s each at 30 fps
REVIEW = ROOT / "review" / "footage" / f"fo_{SLUG}_{CLIP_MS}.md"
BLOCK = re.compile(r"```json\n(.*?)\n```", re.S)


def _positions(tracks: dict) -> dict[int, dict[int, np.ndarray]]:
    """{frame: {track_id: (x, y near-side)}}."""
    return {f["frame"]: {p["track_id"]: np.array([p["xy"][0], PITCH_W - p["xy"][1]]) for p in f["players"]
                         if p.get("xy")} for f in tracks["frames"]}


def closing_speeds(pos: dict, fps: float) -> list[float]:
    out = []
    for a, b in WINDOWS:
        dt = (b - a) / fps
        va, vb = (pos[b][FOULER] - pos[a][FOULER]) / dt, (pos[b][FOULED] - pos[a][FOULED]) / dt
        rel = pos[b][FOULED] - pos[b][FOULER]
        out.append(max(0.0, float(np.dot(va - vb, rel / max(float(np.hypot(*rel)), 1e-9)))))
    return out


def build_moment() -> dict:
    tracks = json.loads((clip_dir(SLUG) / "tracks" / "90.json").read_text())
    pos = _positions(tracks)
    base = {"t_ms": T_MS, "period": 1, "clock": CLOCK, "score": SCORE, "home_attacks": "+x",
            "actual": {"kind": "foul", "target": "#10"}, "ball": {"holder": None},
            "players": [{"team": t, "label": lab, "name": name, "x": float(pos[FRAME][tid][0]),
                         "y": float(pos[FRAME][tid][1])} for tid, (t, lab, name) in LABELS.items()]}
    m = moment_from_tracks(SLUG, CLIP_MS, base)
    m["notes"] = ("Fourth Official frame (video v2): contact of Bruno Fernandes (track 22) on James Maddison (track 3) "
                  "at frame 23172, from track A's tracks/90.json; positions about 0.5-1 m (few midfield lines).")
    return m, pos, float(tracks["fps"])


def ruling(m: dict, pos: dict, fps: float, foul_id: str, ids: dict):
    from fourth_official.foul import FoulRuling
    from fourth_official.rules import in_penalty_area, penalty_area_lines

    contact = (pos[FRAME][FOULER] + pos[FRAME][FOULED]) / 2
    speeds = closing_speeds(pos, fps)
    r = FoulRuling(foul_event_id=foul_id, t_ms=T_MS, fouler=ids["home:#8"], fouled_player=ids["away:#10"],
                   contact_point=[round(float(v), 2) for v in contact], closing_speed_ms=round(speeds[0], 2),
                   in_box=in_penalty_area(float(contact[0]), float(contact[1]), 0, 1), card="red", team="home",
                   period=1, box_lines=penalty_area_lines(0, 1))
    run = [[round(float(v), 2) for v in pos[f][FOULER]] for f in range(FRAME - 15, FRAME + 1, 5)]
    return r, speeds, run


def evidence(m: dict, ros: dict, r_ids: dict, speed_ms: float) -> tuple[list[dict], str, str]:
    """Blackboard documents: the featured evidence of the clip plus the foul and card linked to the players and a
    closing-speed fact. Returns (documents with _collection, foul event id, fact id)."""
    from footage.featured import evidence_docs

    featured = [dict(f, cf_id=f"cf_{int(f['moment_id'][3:]):06d}") for f in load_config()["featured"]
                if f["slug"] == SLUG]
    docs = evidence_docs(SLUG, featured, ros)
    events = docs["events"]
    foul = min((e for e in events if e["type"] == "foul" and e.get("player") == r_ids["home:#8"]),
               key=lambda e: abs(e["attrs"]["clip_ms"] - CLIP_MS))
    foul["attrs"]["fouled_player"] = r_ids["away:#10"]
    card = min((e for e in events if e["type"] == "card" and e.get("player") == r_ids["home:#8"]),
               key=lambda e: abs(e["attrs"]["clip_ms"] - CLIP_MS))
    card["attrs"]["colour"] = "red"
    card["related_event_ids"] = [foul["id"]]
    fact = {"fact_id": "f_000901", "match_id": CLIPS[SLUG]["match_id"], "label": "closing_speed", "unit": "kmh",
            "value": round(speed_ms * 3.6, 1), "t_ms": T_MS, "players": [r_ids["home:#8"], r_ids["away:#10"]],
            "event_id": foul["id"]}
    out = [{"_collection": "events", **e} for e in events] + [{"_collection": "facts", **f} for f in docs["facts"]]
    out.append({"_collection": "facts", **fact})
    return out, foul["id"], fact["fact_id"]


def run() -> dict:
    from blackboard import SqliteBlackboard
    from cache.manifest import CacheManifest
    from footage.featured import open_cache, roster
    from fourth_official.cue import ruling_to_cue
    from newsroom.factcheck import verify_claims

    m, pos, fps = build_moment()
    save(m)
    ros = roster(SLUG)
    docs, foul_id, fact_id = evidence(m, ros, ros["ids"], 0.0)
    r, speeds, run_line = ruling(m, pos, fps, foul_id, ros["ids"])
    docs, foul_id, fact_id = evidence(m, ros, ros["ids"], r.closing_speed_ms)
    review = json.loads(BLOCK.search(REVIEW.read_text()).group(1))
    bb = SqliteBlackboard(":memory:")
    for d in docs:
        d = dict(d)
        bb.put(d.pop("_collection"), d)
    match_id, seed = CLIPS[SLUG]["match_id"], int(CLIPS[SLUG]["match_id"][2:])
    claims = [{**c, "evidence_ids": [foul_id if e == "<foul>" else fact_id if e == "<fact>" else e
                                     for e in c["evidence_ids"]],
               "value": ros["ids"].get(c["value"], c["value"]) if isinstance(c["value"], str) else c["value"]}
              for c in review["claims"]]
    check = verify_claims(match_id, claims, bb, {"headline": review["headline"], "body": review["body"],
                                                 "why": review["why"]})
    bb.close()
    if not check["verified"]:
        raise SystemExit(f"Fact Checker refused the reviewed text: {check['diff']}")
    cue = ruling_to_cue(r, T_MS, match_id=match_id, cue_id=f"c_9{CLIP_MS // 100:05d}", evidence_event_id=foul_id,
                        period=1)
    cue["clock"] = CLOCK
    cue["text"] = {"headline": review["headline"], "body": review["body"]}
    cue["explain"].update(why=review["why"], claims=check["claims"])
    cue["graphics"]["lines"] = [[run_line[i], run_line[i + 1]] for i in range(len(run_line) - 1)]
    ruling_doc = {**asdict(r), "closing_speed_kmh": round(r.closing_speed_ms * 3.6, 1),
                  "closing_speed_spread_ms": [round(s, 2) for s in speeds], "fouler_run": run_line,
                  "frame": FRAME, "clip_ms": CLIP_MS, "assessment_note": "an assessment from tracking, not a ruling",
                  "position_error_m": "0.5-1 (track A, few midfield lines)"}
    manifest = open_cache(SLUG)
    key = CacheManifest.key(match_id, None, "fourth_official", f"footage_{CLIP_MS}", None, seed)
    manifest.add(key, "fourth_official", cue, f"fourth_official/{cue['cue_id']}.json", producer="fourth_official",
                 version=f"footage_{CLIP_MS}", seed=seed, hand_reviewed=True)
    manifest.add(CacheManifest.key(match_id, None, "fourth_official", f"ruling_{CLIP_MS}", None, seed), "analytics",
                 {"$schema": "model_cache.schema.json", "schema_version": "1.0.0", "record": "tool_result",
                  "result": ruling_doc}, f"fourth_official/ruling_{CLIP_MS}.json", producer="fourth_official",
                 version=f"ruling_{CLIP_MS}", seed=seed)
    manifest.add(CacheManifest.key(match_id, None, "evidence", f"fourth_official_{CLIP_MS}", None, seed), "analytics",
                 ("\n".join(json.dumps(d, separators=(",", ":"), ensure_ascii=False) for d in docs) + "\n").encode(),
                 f"fourth_official/evidence_{CLIP_MS}.jsonl", producer="evidence",
                 version=f"fourth_official_{CLIP_MS}", seed=seed)
    manifest.save()
    return {"cue_id": cue["cue_id"], "text": cue["text"], "contact_point": r.contact_point,
            "closing_speed_ms": r.closing_speed_ms, "spread_ms": ruling_doc["closing_speed_spread_ms"],
            "in_box": r.in_box, "fouler": r.fouler, "fouled": r.fouled_player, "foul_event": foul_id,
            "labels": {p["label"]: round(math.hypot(p["vx"], p["vy"]), 1) for p in m["players"]
                       if p["label"] in ("#8", "#10")}}


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "packages"))
    print(json.dumps(run(), indent=1, ensure_ascii=False))
