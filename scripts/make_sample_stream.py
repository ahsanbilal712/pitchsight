"""Build the 60-second sample WebSocket stream so screens can start before the engine exists (T-003).

Usage:
  python3 scripts/make_sample_stream.py           # writes tests/fixtures/stream/sample_stream.jsonl
  python3 scripts/make_sample_stream.py --check   # re-parses the file, asserts counts and byte-identity

Standard library only and deterministic: no randomness, floats rounded to 2 decimals, keys sorted.
Each line is one message envelope {"type": <TECH_PLAN 1.9 message type>, "payload": {...}}; the
message type names the schema the payload follows (event -> event.schema.json, cue -> cue.schema.json).

The window is 30:50-31:50 of the golden match m_4242 (Verdant v Ironvale), around the storyboard
moment: Silva finds Okafor (e_8809), Okafor shoots wide (e_8812) while Reyes is free at the far post.
Two 4-4-2 blocks drift with the ball; key players follow hand-placed waypoints.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "fixtures" / "stream" / "sample_stream.jsonl"
# documents the overlay fetches by id in fixture mode (no schema exists for pitch_control, so not tests/fixtures)
DOCS = ROOT / "apps" / "overlay" / "public" / "fixtures" / "docs"
SCHEMAS = ROOT / "schemas"

MATCH_ID = "m_4242"
T0, N_FRAMES, DT = 1_850_000, 600, 100        # 60 s at 10 Hz
BALL_REST_Z = 0.11
# Rows 0-10 home (Verdant, attacking +x in period 1), 11-21 away (Ironvale), 22 ball (TECH_PLAN 1.3).
PLAYER_IDS = [
    "p_001", "p_004", "p_005", "p_006", "p_007", "p_012", "p_022", "p_013", "p_014", "p_017", "p_031",
    "p_026", "p_029", "p_030", "p_032", "p_033", "p_037", "p_038", "p_039", "p_040", "p_045", "p_046",
]
HOME_ROWS, AWAY_ROWS = range(0, 11), range(11, 22)

# Block centre of the home team over time (x, metres); the away block sits 10 m deeper toward its goal.
BLOCK_X = [(1850000, 50), (1866000, 60), (1872800, 66), (1874000, 70), (1878000, 62), (1886000, 52),
           (1895000, 45), (1911000, 50)]

# Hand-placed waypoints (t_ms, x, y) for players involved in the action; blended into the formation.
WAYPOINTS = {
    2: [(1850000, 38, 27), (1853000, 40, 26), (1856000, 42, 26)],                       # CB p_005
    6: [(1852000, 52, 31), (1854200, 56, 30), (1858000, 58, 28), (1862000, 62, 26),     # Silva p_022
        (1866900, 66, 24), (1872800, 70, 21), (1874000, 74, 24)],
    5: [(1857000, 66, 12), (1859200, 68, 10), (1866000, 72, 11), (1868000, 74, 12)],    # RM p_012
    9: [(1869000, 80, 35), (1871000, 82, 33), (1873400, 86, 30), (1874000, 87.5, 29.5),  # Okafor p_017
        (1874400, 88, 29.3), (1877000, 84, 30)],
    10: [(1868000, 84, 46), (1870000, 88, 44), (1873800, 98.9, 39.8), (1874600, 99.5, 39.5),  # Reyes p_031
         (1877000, 94, 38)],
    13: [(1872000, 92, 32), (1873700, 88.5, 31), (1874400, 89.5, 30.5)],               # away CB p_030
    11: [(1877000, 101, 33), (1879500, 99.5, 30), (1880500, 100, 32)],                 # away GK p_026
    19: [(1860000, 74, 14), (1862000, 71, 10.5), (1864000, 73, 13)],                    # away MF p_040
    7: [(1893000, 58, 30), (1894800, 56, 33), (1900000, 60, 32)],                      # CM p_013
}
BLEND_MS = 3000

# Ball script: ("hold", row, t0, t1) | ("pass", from_row, to_row, t0, t1, z_peak) |
# ("shot", row, t0, t1, end_xy) | ("dead", t0, t1, xy) | ("cut", from_row, to_row, t0, t1, z_peak)
BALL = [
    ("hold", 2, 1850000, 1853000),
    ("pass", 2, 6, 1853000, 1854200, 0.0),
    ("hold", 6, 1854200, 1858000),
    ("pass", 6, 5, 1858000, 1859200, 0.0),
    ("hold", 5, 1859200, 1866000),
    ("pass", 5, 6, 1866000, 1866900, 0.0),
    ("hold", 6, 1866900, 1872800),
    ("pass", 6, 9, 1872800, 1873400, 0.0),
    ("hold", 9, 1873400, 1874000),
    ("shot", 9, 1874000, 1874850, (109.0, 26.0)),
    ("dead", 1874850, 1878000, (109.0, 26.0)),
    ("dead", 1878000, 1879500, (99.5, 30.0)),
    ("hold", 11, 1879500, 1879600),
    ("pass", 11, 15, 1879600, 1880800, 6.0),
    ("hold", 15, 1880800, 1886000),
    ("pass", 15, 18, 1886000, 1887000, 0.0),
    ("hold", 18, 1887000, 1894000),
    ("cut", 18, 7, 1894000, 1894800, 0.0),
    ("hold", 7, 1894800, 1911000),
]


def lerp_track(points, t):
    if t <= points[0][0]:
        return points[0][1:]
    for (ta, *a), (tb, *b) in zip(points, points[1:], strict=False):
        if ta <= t <= tb:
            s = (t - ta) / (tb - ta)
            return tuple(av + (bv - av) * s for av, bv in zip(a, b, strict=True))
    return points[-1][1:]


def formation(row: int, t: int) -> tuple[float, float]:
    bx = lerp_track(BLOCK_X, t)[0]
    phase = 2 * math.pi * t / 9000 + row
    wobble = (1.2 * math.sin(phase), 0.8 * math.cos(phase))
    if row in HOME_ROWS:
        line = [(max(6.0, bx - 44), 34.0)] + [(bx - 18, y) for y in (12, 27, 41, 56)] \
            + [(bx - 2, y) for y in (10, 27, 41, 58)] + [(bx + 14, y) for y in (28, 40)]
        x, y = line[row]
    else:
        ax = bx + 10
        line = [(min(101.0, ax + 44), 34.0)] + [(min(100.0, ax + 18), y) for y in (56, 41, 27, 12)] \
            + [(ax + 3, y) for y in (58, 41, 27, 10)] + [(ax - 12, y) for y in (40, 28)]
        x, y = line[row - 11]
    return x + wobble[0], y + wobble[1]


def player_pos(row: int, t: int) -> tuple[float, float]:
    fx, fy = formation(row, t)
    wps = WAYPOINTS.get(row)
    if not wps:
        return fx, fy
    first, last = wps[0][0], wps[-1][0]
    gap = first - t if t < first else (t - last if t > last else 0)
    w = max(0.0, 1.0 - gap / BLEND_MS)
    wx, wy = lerp_track(wps, t)
    return w * wx + (1 - w) * fx, w * wy + (1 - w) * fy


def ball_state(t: int) -> tuple[float, float, float, int]:
    """Return (x, y, z, holder_row) at time t."""
    for seg in BALL:
        kind = seg[0]
        if kind == "hold" and seg[2] <= t < seg[3]:
            x, y = player_pos(seg[1], t)
            return x, y, BALL_REST_Z, seg[1]
        if kind in ("pass", "cut") and seg[3] <= t < seg[4]:
            _, a, b, t0, t1, zp = seg
            (x0, y0), (x1, y1) = player_pos(a, t0), player_pos(b, t1)
            s = (t - t0) / (t1 - t0)
            return x0 + (x1 - x0) * s, y0 + (y1 - y0) * s, BALL_REST_Z + 4 * zp * s * (1 - s), -1
        if kind == "shot" and seg[2] <= t < seg[3]:
            _, a, t0, t1, (x1, y1) = seg
            x0, y0 = player_pos(a, t0)
            s = (t - t0) / (t1 - t0)
            return x0 + (x1 - x0) * s, y0 + (y1 - y0) * s, BALL_REST_Z + 4 * 1.5 * s * (1 - s), -1
        if kind == "dead" and seg[1] <= t < seg[2]:
            return seg[3][0], seg[3][1], BALL_REST_Z, -1
    raise ValueError(f"no ball segment covers t={t}")


def possession(t: int) -> int:
    if t < 1874850:
        return 0
    if t < 1879500:
        return -1
    return 1 if t < 1894800 else 0


def r2(v: float) -> float:
    return round(v, 2) + 0.0     # + 0.0 turns -0.0 into 0.0


def frame(t: int) -> dict:
    rows = []
    for row in range(22):
        (x, y), (x2, y2) = player_pos(row, t), player_pos(row, t + DT)
        rows.append([r2(x), r2(y), r2((x2 - x) / (DT / 1000)), r2((y2 - y) / (DT / 1000))])
    bx, by, bz, holder = ball_state(t)
    bx2, by2, _, _ = ball_state(t + DT)
    rows.append([r2(bx), r2(by), r2((bx2 - bx) / (DT / 1000)), r2((by2 - by) / (DT / 1000))])
    return {"t_ms": t, "period": 1, "p": rows, "ball_z": r2(bz), "holder": holder, "possession": possession(t)}


def clock(t: int) -> str:
    s = t // 1000
    return f"{s // 60:02d}:{s % 60:02d}"


def schema_example(name: str, idx: int = 0) -> dict:
    return json.loads((SCHEMAS / name).read_text())["examples"][idx]


def event(n: int, t: int, typ: str, row: int | None, outcome: str, *, end=None, under_pressure=False,
          related=(), attrs=None, location=None) -> dict:
    team = "none" if row is None else ("home" if row in HOME_ROWS else "away")
    loc = location if location is not None else (None if row is None else [r2(v) for v in ball_state(t)[:2]])
    return {"schema_version": "1.0.0", "id": f"e_{n:04d}", "match_id": MATCH_ID, "idx": n, "t_ms": t, "period": 1,
            "clock": clock(t), "type": typ, "team": team, "player": None if row is None else PLAYER_IDS[row],
            "location": loc, "end_location": end, "outcome": outcome, "under_pressure": under_pressure,
            "related_event_ids": list(related), "attrs": attrs or {}}


def pass_event(n: int, a: int, b: int, t0: int, t1: int, *, height="ground", outcome="complete", related=()) -> dict:
    (x0, y0), (x1, y1) = player_pos(a, t0), player_pos(b, t1)
    sign = 1 if a in HOME_ROWS else -1
    length = math.hypot(x1 - x0, y1 - y0)
    attrs = {"recipient": PLAYER_IDS[b] if outcome == "complete" else None, "length_m": r2(length),
             "angle_deg": r2(math.degrees(math.atan2(y1 - y0, sign * (x1 - x0)))), "height": height,
             "progressive_m": r2(sign * (x1 - x0)), "pass_difficulty": 0.3, "pass_completion_p": 0.8}
    return event(n, t0, "pass", a, outcome, end=[r2(x1), r2(y1)], related=related, attrs=attrs,
                 location=[r2(x0), r2(y0)])


# chaos_index once a second (TECH_PLAN 1.9 "indices every 1 s"): (t_ms, value) knots, linear in between.
# The storyboard fact f_000301 (67.4 at 31:15) stays as it was in T-003; the state machine (enter > 65 for 20 s)
# turns Chaotic at 31:26; the window opens Transitional.
CHAOS_KNOTS = [(1850000, 46.0), (1862000, 55.0), (1866000, 66.0), (1875000, 67.4), (1880000, 72.0),
               (1890000, 69.0), (1899000, 58.0)]


def chaos_facts() -> list[dict]:
    facts, n = [], 275  # numbered so the 31:15 fact keeps its T-003 id f_000301
    for t in range(T0, T0 + N_FRAMES * DT, 1000):
        (ta, va), (tb, vb) = next(((a, b) for a, b in zip(CHAOS_KNOTS, CHAOS_KNOTS[1:], strict=False)
                                   if a[0] <= t <= b[0]), (CHAOS_KNOTS[-2], CHAOS_KNOTS[-1]))
        value = r2(va + (vb - va) * min(1.0, (t - ta) / (tb - ta)))
        n += 1
        ev = ["e_8811", "e_8812"] if t == 1875000 else []
        facts.append({"id": f"f_{n:06d}", "match_id": MATCH_ID, "t_ms": t, "kind": "index", "name": "chaos_index",
                      "value": value, "unit": "index_0_100", "window_s": 60, "evidence_event_ids": ev})
        if t == 1886000:
            n += 1
            facts.append({"id": f"f_{n:06d}", "match_id": MATCH_ID, "t_ms": t, "kind": "state",
                          "name": "chaos_state", "value": "Chaotic", "unit": None, "window_s": 20,
                          "evidence_event_ids": []})
    assert any(f["id"] == "f_000301" and f["value"] == 67.4 for f in facts)
    # the state the window opens in, so screens never derive one without hysteresis
    facts.insert(0, {"id": "f_000274", "match_id": MATCH_ID, "t_ms": T0, "kind": "state", "name": "chaos_state",
                     "value": "Transitional", "unit": None, "window_s": 20, "evidence_event_ids": []})
    return facts


# Ghost futures for the counterfactual (T-024): 200 ball paths at 1 Hz over the 8 s horizon from the branch
# point. Renderer convention (docs/cue_contract.md gap 7): the first half of futures_sample are baseline futures,
# the second half alternative futures. Variation comes from a fixed trig hash, not a random generator.
N_FUTURES, HORIZON_S = 200, 8


def _jitter(k: int, j: int, scale: float) -> float:
    return scale * math.sin(12.9898 * (k + 1) + 78.233 * (j + 1)) * math.cos(4.1414 * (k + 3) * (j + 2))


def ghost_futures(start: tuple[float, float]) -> list[list[list[float]]]:
    # baseline: the shot from the tight angle, then the rebound or goal kick drifting back out
    base = [start, (103.5, 31.5), (100.5, 30.0), (96.0, 31.0), (90.0, 33.0), (84.0, 35.0), (78.0, 36.0),
            (72.0, 36.0), (66.0, 35.0)]
    # alternative: the square pass to Reyes at the far post, his shot, then the scramble in the six-yard box
    alt = [start, (96.5, 37.5), (99.5, 39.0), (104.0, 34.5), (102.0, 33.5), (99.0, 35.0), (96.0, 36.0),
           (93.0, 36.5), (90.0, 36.0)]
    paths = []
    for k in range(N_FUTURES):
        knots = base if k < N_FUTURES // 2 else alt
        path = []
        for j, (x, y) in enumerate(knots):
            spread = 0.0 if j == 0 else min(6.0, 0.9 * j)
            px = min(105.0, max(0.0, x + _jitter(k, j, spread)))
            py = min(68.0, max(0.0, y + _jitter(k + 101, j, spread)))
            path.append([r2(px), r2(py)])
        paths.append(path)
    return paths


def counterfactual() -> dict:
    cf = schema_example("counterfactual.schema.json")
    cf["futures_sample"] = ghost_futures(tuple(cf["futures_sample"][0][0]))
    assert len(cf["futures_sample"]) == N_FUTURES and all(len(p) == HORIZON_S + 1 for p in cf["futures_sample"])
    return cf


# Oracle (T-045 until T-046): every 2 s, {t_ms, p_shot_home, p_shot_away, zone {x, y, r} in metres, shooter}.
# Verdant's threat builds toward the right-hand box and peaks just before Okafor's shot at 31:14.
ORACLE_KNOTS = [(1850000, 0.06), (1862000, 0.12), (1868000, 0.24), (1872000, 0.34), (1876000, 0.18),
                (1882000, 0.05), (1910000, 0.04)]


def oracle_messages() -> list[dict]:
    out = []
    for t in range(T0, T0 + N_FRAMES * DT, 2000):
        (ta, va), (tb, vb) = next(((a, b) for a, b in zip(ORACLE_KNOTS, ORACLE_KNOTS[1:], strict=False)
                                   if a[0] <= t <= b[0]), (ORACLE_KNOTS[-2], ORACLE_KNOTS[-1]))
        p = r2(va + (vb - va) * (t - ta) / (tb - ta))
        x, y = player_pos(9, t)                                  # Okafor leads the threat
        out.append({"t_ms": t, "p_shot_home": p, "p_shot_away": 0.02,
                    "zone": {"x": r2(min(100.0, x + 6)), "y": r2(y), "r": 11.0},
                    "shooter": PLAYER_IDS[9] if p >= 0.2 else None})
    return out


def referee_cue() -> dict:
    """A Fourth Official ruling (T-045 until T-049): offside lines in metres, onside by 0.4 m."""
    cue = schema_example("cue.schema.json")
    cue.update({"cue_id": "c_000913", "moment_id": None, "t_in_ms": 1900000, "t_out_ms": 1908000, "clock": "31:40",
                "layer": "referee_line", "kind": "fourth_official", "priority": 0.9, "leverage": None,
                "targets": {"modes": ["analyst", "casual", "player_cam"], "clubs": ["any"], "players": ["p_040"]},
                "text": {"headline": "Onside by 0.4 m.", "body": "Ironvale's runner was level with the last "
                         "Verdant defender's line when the pass was played."}})
    cue["graphics"] = {"pitch_control_snapshot": None, "ghost_trail": [], "players_highlight": ["p_040"],
                       "lines": [[[88.2, 0.0], [88.2, 68.0]], [[88.6, 0.0], [88.6, 68.0]]], "bar": None}
    cue["explain"] = {"why": "Measured at the frame of the pass.", "counterfactual_id": None, "explanation_id": None,
                      "claims": [{"text": "0.4 m", "kind": "number", "value": 0.4, "unit": "metres",
                                  "evidence_ids": ["e_8816"], "verified": True}]}
    return cue


def pitch_control_doc(t: int) -> dict:
    """pc_000412 for the fixture cue: [34, 53] home share from a soft nearest-player rule (stdlib, deterministic)."""
    pos = [player_pos(r, t) for r in range(22)]
    grid = []
    for row in range(34):
        y = 1.0 + 2.0 * row
        line = []
        for col in range(53):
            x = 1.0 + 2.0 * col
            d = [math.hypot(px - x, py - y) for px, py in pos]
            home, away = min(d[:11]), min(d[11:])
            line.append(r2(1.0 / (1.0 + math.exp((home - away) / 2.5))))
        grid.append(line)
    share = sum(map(sum, grid)) / (34 * 53)
    contested = sum(1 for line in grid for v in line if 0.3 <= v <= 0.7) / (34 * 53)
    return {"snapshot_id": "pc_000412", "match_id": MATCH_ID, "t_ms": t, "period": 1, "team_in_possession": "home",
            "home_share": r2(share), "contested_frac": r2(contested), "grid": grid}


def fixture_docs() -> dict[str, dict]:
    """Documents the overlay fetches by id in fixture mode (the api serves the same from the blackboard)."""
    return {"pc_000412": pitch_control_doc(1874000), "cf_000077": counterfactual()}


def write_docs() -> list[Path]:
    DOCS.mkdir(parents=True, exist_ok=True)
    paths = []
    for doc_id, doc in fixture_docs().items():
        path = DOCS / f"{doc_id}.json"
        path.write_text(json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n")
        paths.append(path)
    return paths


def build() -> list[dict]:
    ex_pass, ex_shot = schema_example("event.schema.json", 0), schema_example("event.schema.json", 1)
    cue = schema_example("cue.schema.json")
    okafor_carry_end = [r2(v) for v in player_pos(9, 1874000)]
    events = [
        pass_event(8805, 2, 6, 1853000, 1854200),
        pass_event(8806, 6, 5, 1858000, 1859200),
        event(8807, 1862000, "pressure", 19, "n/a", location=[r2(v) for v in player_pos(19, 1862000)],
              attrs={"duration_ms": 1800, "closing_speed_ms": 4.2}),
        pass_event(8808, 5, 6, 1866000, 1866900, related=["e_8807"]),
        ex_pass,                                                    # e_8809 Silva -> Okafor (schema example)
        event(8810, 1873400, "carry", 9, "complete", end=okafor_carry_end, related=["e_8809"],
              attrs={"distance_m": r2(math.dist(player_pos(9, 1873400), player_pos(9, 1874000))),
                     "progressive_m": r2(player_pos(9, 1874000)[0] - player_pos(9, 1873400)[0])}),
        event(8811, 1873700, "pressure", 13, "n/a", location=[r2(v) for v in player_pos(13, 1873700)],
              related=["e_8810"], attrs={"duration_ms": 300, "closing_speed_ms": 5.1}),
        ex_shot,                                                    # e_8812 Okafor shot (schema example)
        event(8813, 1879500, "set_piece", 11, "n/a", attrs={"kind": "goal_kick"}, related=["e_8812"]),
        pass_event(8814, 11, 15, 1879600, 1880800, height="lofted", related=["e_8813"]),
        pass_event(8815, 15, 18, 1886000, 1887000),
        pass_event(8816, 18, 21, 1894000, 1894800, outcome="incomplete"),
        event(8817, 1894800, "interception", 7, "won", related=["e_8816"]),
        event(8818, 1894800, "possession_change", 7, "n/a", related=["e_8817"]),
    ]
    events[11]["end_location"] = [r2(v) for v in player_pos(7, 1894800)]   # the cut-out pass ends at the interceptor
    facts = chaos_facts()
    hello = {"match_id": MATCH_ID, "mode": "replay", "replay_speed": 1.0, "player_ids": PLAYER_IDS,
             "viewer_profile": {"schema_version": "1.0.0", "viewer_id": "v_fixture", "mode": "analyst", "club": None,
                                "player": None, "metric": None, "high_contrast": False, "show_heatmap": True}}

    timed = [(T0 + k * DT, 4, "tracking_frame", frame(T0 + k * DT)) for k in range(N_FRAMES)]
    timed += [(e["t_ms"], 0, "event", e) for e in events]
    timed += [(f["t_ms"], 1, "fact", f) for f in facts]
    cf = counterfactual()
    timed += [(cue["t_in_ms"], 2, "counterfactual", cf), (cue["t_in_ms"], 2, "cue", cue),
              (cue["t_out_ms"], 3, "cue_remove", {"cue_id": cue["cue_id"]})]
    timed += [(o["t_ms"], 1, "oracle", o) for o in oracle_messages()]
    ref = referee_cue()
    timed += [(ref["t_in_ms"], 2, "cue", ref)]
    timed.sort(key=lambda m: (m[0], m[1], m[3].get("id", "")))
    return [{"type": "hello", "payload": hello}] + [{"type": typ, "payload": p} for _, _, typ, p in timed]


def render(messages: list[dict]) -> str:
    return "".join(json.dumps(m, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n" for m in messages)


def check() -> list[str]:
    errors = []
    text = OUT.read_text(encoding="utf-8")
    if text != render(build()):
        errors.append("file differs from a fresh build (not byte-identical)")
    for doc_id, doc in fixture_docs().items():
        path = DOCS / f"{doc_id}.json"
        if not path.exists() or path.read_text() != json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n":
            errors.append(f"{path.relative_to(ROOT)} missing or stale")
    counts: dict[str, int] = {}
    frames, events = [], []
    for n, line in enumerate(text.splitlines(), 1):
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {n}: {exc}")
            continue
        counts[msg["type"]] = counts.get(msg["type"], 0) + 1
        if msg["type"] == "tracking_frame":
            frames.append(msg["payload"])
        elif msg["type"] == "event":
            events.append(msg["payload"])
    want = {"hello": (1, 1), "tracking_frame": (600, 600), "event": (6, None), "cue": (2, 2), "fact": (62, 62), "counterfactual": (1, 1),
            "oracle": (30, 30)}
    for typ, (lo, hi) in want.items():
        got = counts.get(typ, 0)
        if got < lo or (hi is not None and got > hi):
            errors.append(f"{typ}: {got} messages, expected {lo}" + ("" if hi == lo else "+"))
    if text.splitlines() and json.loads(text.splitlines()[0])["type"] != "hello":
        errors.append("first message is not hello")
    ts = [f["t_ms"] for f in frames]
    if any(b - a != DT for a, b in zip(ts, ts[1:], strict=False)):
        errors.append("tracking frames are not 100 ms apart")
    for f in frames:
        if len(f["p"]) != 23 or any(len(r) != 4 for r in f["p"]):
            errors.append(f"frame {f['t_ms']}: p is not 23 x [x, y, vx, vy]")
            break
        if set(f) != {"t_ms", "period", "p", "ball_z", "holder", "possession"}:
            errors.append(f"frame {f['t_ms']}: keys {sorted(f)}")
            break
    if ts and any(not (ts[0] <= e["t_ms"] <= ts[-1]) for e in events):
        errors.append("an event lies outside the tracking window")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="validate the existing file instead of writing it")
    args = ap.parse_args()
    if args.check:
        errors = check()
        if errors:
            print("make_sample_stream --check: FAIL")
            for e in errors:
                print("  " + e)
            return 1
        print(f"make_sample_stream --check: OK ({OUT.relative_to(ROOT)})")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(build()), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    for path in write_docs():
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
