"""Moment freeze: a real clip's frozen frame -> a synthetic `State` the engine can branch (FOOTAGE_ADDENDUM.md step 5,
T-107).

A moment file `data/footage/<slug>/moments/<clip_ms>.json` holds the players and ball of one frame in pitch metres
(105 x 68, origin bottom-left as event.schema.json), whichever way the broadcast shows them:

    {"slug", "match_id", "clip_ms", "t_ms", "period", "clock", "score": [home, away],
     "home_attacks": "+x" | "-x",                      # in this file's coordinates
     "frame": "frames/moment_<clip_ms>.png",            # git-ignored, relative to the clip folder
     "homography": {"image_to_pitch": 3x3, "points": [{"pitch": [x, y], "image": [u, v]}], "rms_m": ...},
     "players": [{"team": "home"|"away", "label": "#8", "name": "...", "slot": "CF"|null,
                  "x", "y", "vx", "vy", "source": "hand"|"tracking"|"prior", "image": [u, v]}],
     "ball": {"x", "y", "holder": <label of the player in control> | null},
     "actual": {"kind": "shoot"|"pass"|"carry", "target": <label>|null}, "notes": "..."}

Tracking (T-105) or a hand-marked frame fills the observed players; `fill` adds the missing ones from the role
prior: the engine's 4-3-3 slots (kickoff SLOTS) shifted to the team's observed shape, matched to the observed players
with the Hungarian algorithm, so each player also gets the engine slot his row will take. `to_state` builds an
Engine for a neutral synthetic fixture, sets that one world to the frame (mirrored when the broadcast's direction
differs from the engine's period convention), puts the holder in control, and returns `Engine.snapshot_state()`:
its `source` branches like any other state (rollout, Sliding Doors).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from footage.clips import CLIPS, clip_dir

PITCH_L, PITCH_W = 105.0, 68.0
SLOT_NAMES = ("GK", "RB", "RCB", "LCB", "LB", "RCM", "CM", "LCM", "RW", "CF", "LW")
SLOT_U = np.array([0.0, 3.0, 0.0, 0.0, 3.0, 14.0, 10.0, 14.0, 30.0, 32.0, 30.0])   # kickoff.engine 4-3-3
SLOT_V = np.array([34.0, 8.0, 25.0, 43.0, 60.0, 22.0, 34.0, 46.0, 10.0, 34.0, 58.0])
GK_U = 4.0
LAST_TICK_MARGIN_MS = 30_000     # the engine stops at 90:00; a later frame is placed at 89:30 (stoppage time)


def moments_dir(slug: str) -> Path:
    return clip_dir(slug) / "moments"


def load(slug: str, clip_ms: int) -> dict:
    return json.loads((moments_dir(slug) / f"{clip_ms}.json").read_text())


def save(moment: dict) -> Path:
    path = moments_dir(moment["slug"]) / f"{moment['clip_ms']}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(moment, indent=1) + "\n")
    return path


# ---------------------------------------------------------------------------------------------------- geometry

def apply_h(H, pts) -> np.ndarray:
    p = np.c_[np.asarray(pts, float), np.ones(len(pts))] @ np.asarray(H, float).T
    return p[:, :2] / p[:, 2:]


def fit_homography(image_pts, pitch_pts) -> tuple[np.ndarray, float]:
    """Image -> pitch homography (DLT) and its RMS error in metres on the given points."""
    A = []
    for (u, v), (x, y) in zip(image_pts, pitch_pts, strict=True):
        A += [[u, v, 1, 0, 0, 0, -x * u, -x * v, -x], [0, 0, 0, u, v, 1, -y * u, -y * v, -y]]
    H = np.linalg.svd(np.array(A, float))[2][-1].reshape(3, 3)
    H = H / H[2, 2]
    err = np.linalg.norm(apply_h(H, image_pts) - np.asarray(pitch_pts, float), axis=1)
    return H, float(np.sqrt((err ** 2).mean()))


def _team_frame(x, y, attacks_plus_x: bool):
    """Pitch (x, y) -> team frame (u, v): own goal at u = 0, attacking +u (kickoff.physics_prior.to_team)."""
    return (x, y) if attacks_plus_x else (PITCH_L - np.asarray(x), PITCH_W - np.asarray(y))


# ---------------------------------------------------------------------------------------------------- role prior

def _in_view(moment: dict, x: float, y: float) -> bool:
    """True when pitch (x, y) projects inside the frame (needs the moment's homography; False without one)."""
    hom = moment.get("homography") or {}
    if not hom.get("image_to_pitch"):
        return False
    w, h = hom.get("image_size") or (1920, 1080)
    p = np.array([x, y, 1.0]) @ np.linalg.inv(np.asarray(hom["image_to_pitch"], float)).T
    if p[2] <= 0:                  # behind the camera
        return False
    u, v = p[0] / p[2], p[1] / p[2]
    return 0 <= u <= w and 0 <= v <= h


def fill(moment: dict) -> dict:
    """Assign every observed player an engine slot and add the missing players at their role prior. Players with a
    hand-set `slot` keep it. Returns a new moment with 11 per team, each with `slot`."""
    from scipy.optimize import linear_sum_assignment

    home_plus = moment["home_attacks"] == "+x"
    players = []
    for team in ("home", "away"):
        plus = home_plus if team == "home" else not home_plus
        seen = [dict(p) for p in moment["players"] if p["team"] == team]
        fixed = {p["slot"] for p in seen if p.get("slot")}
        free = [p for p in seen if not p.get("slot")]
        open_slots = [s for s in range(11) if SLOT_NAMES[s] not in fixed]
        if len(free) > len(open_slots):
            raise ValueError(f"{team}: {len(seen)} players in the frame, at most 11")
        uv = np.array([_team_frame(p["x"], p["y"], plus) for p in free], float).reshape(-1, 2)
        best = None
        for line in np.arange(5.0, 70.0, 0.5):          # the defensive line that best explains the observed shape
            target = np.c_[np.where(np.arange(11) == 0, GK_U, line + SLOT_U), SLOT_V][open_slots]
            cost = np.linalg.norm(uv[:, None, :] - target[None, :, :], axis=2) if len(free) else np.zeros((0, 0))
            rows, cols = linear_sum_assignment(cost) if len(free) else ([], [])
            total = float(cost[rows, cols].sum()) if len(free) else 0.0
            if best is None or total < best[0]:
                best = (total, line, rows, cols)
        _, line, rows, cols = best
        for r, c in zip(rows, cols, strict=True):
            free[r]["slot"] = SLOT_NAMES[open_slots[c]]
        taken = {p["slot"] for p in seen}
        for s in range(11):
            if SLOT_NAMES[s] in taken:
                continue
            u = GK_U if s == 0 else line + SLOT_U[s]
            while u > 1.0 and _in_view(moment, *_team_frame(u, SLOT_V[s], plus)):
                u -= 1.0            # not seen in the frame: the player is off camera, towards his own goal
            x, y = _team_frame(u, SLOT_V[s], plus)
            seen.append({"team": team, "label": None, "slot": SLOT_NAMES[s], "x": round(float(x), 2),
                         "y": round(float(y), 2), "vx": 0.0, "vy": 0.0, "source": "prior"})
        players += sorted(seen, key=lambda p: SLOT_NAMES.index(p["slot"]))
    return {**moment, "players": players}


# ---------------------------------------------------------------------------------------------------- state

def neutral_engine(match_id: str, seed: int):
    """An Engine for a synthetic fixture with league-average styles: the real clubs' styles are unknown."""
    from kickoff import Engine, League
    from rollout.core import LEAGUE_DIR

    league = League.load(LEAGUE_DIR)
    home, away = league.fixture(seed)
    keys = list(next(iter(league.styles.values())))
    mean = {k: float(np.mean([s[k] for s in league.styles.values()])) for k in keys}
    eng = Engine(league, home, away, seed=seed, styles={"home": mean, "away": mean})
    eng.record_events = False
    return eng


def to_state(moment: dict, seed: int | None = None):
    """The moment as a one-world engine state with `source` set (branchable). Fills missing players first."""
    from kickoff.engine import BALL_REST_Z, MATCH_MS, PERIOD_MS, TICK_MS

    m = fill(moment) if sum(1 for p in moment["players"]) < 22 or any(not p.get("slot") for p in moment["players"]) \
        else moment
    seed = int(seed if seed is not None else int(m["match_id"][2:]))
    eng = neutral_engine(m["match_id"], seed)
    w = eng.worlds[0]
    t = min(int(m["t_ms"]) // TICK_MS * TICK_MS, MATCH_MS - LAST_TICK_MARGIN_MS)
    period = int(m.get("period") or (1 if t < PERIOD_MS else 2))
    eng.t_ms, eng.period = t, period
    # engine convention: home attacks +x in period 1, -x in period 2; mirror the frame when it differs
    mirror = (m["home_attacks"] == "+x") != (period == 1)

    def put(x, y, vx, vy):
        return (PITCH_L - x, PITCH_W - y, -vx, -vy) if mirror else (x, y, vx, vy)

    stamina = max(0.75, 1.0 - 0.25 * t / MATCH_MS)
    rows = {}
    for p in m["players"]:
        row = (0 if p["team"] == "home" else 11) + SLOT_NAMES.index(p["slot"])
        x, y, vx, vy = put(float(p["x"]), float(p["y"]), float(p.get("vx") or 0), float(p.get("vy") or 0))
        attack = 1.0 if (p["team"] == "home") == (period == 1) else -1.0
        facing = math.atan2(vy, vx) if math.hypot(vx, vy) > 0.3 else (0.0 if attack > 0 else math.pi)
        eng.S[0, row] = [x, y, vx, vy, stamina, facing]
        if p.get("label"):
            if p["label"] in rows:
                raise ValueError(f"label {p['label']!r} is used twice; labels name one player each")
            rows[p["label"]] = row
    bx, by, _, _ = put(float(m["ball"]["x"]), float(m["ball"]["y"]), 0.0, 0.0)
    eng.S[0, 22, 0:4] = [bx, by, 0.0, 0.0]
    eng.ball_z[0], eng.ball_vz[0] = BALL_REST_Z, 0.0
    eng.score[0] = m.get("score") or [0, 0]
    # live play: no pending restart
    eng.dead[0] = False
    eng.restart_flag[0] = 0
    w.restart_kind, w.ball_placed, w.first_touch_restart = "", True, ""
    holder = m["ball"].get("holder")
    if holder is not None:
        if holder not in rows:
            raise ValueError(f"ball holder {holder!r} is not a labelled player")
        row = rows[holder]
        eng.S[0, 22, 0:2] = eng.S[0, row, 0:2]           # the engine keeps the ball at the holder's feet
        eng._take_control(w, row, latency_ms=0, change_event=False)
    st = eng.snapshot_state()
    st.labels = rows                                         # label -> engine row, for picking alternatives
    st.mirrored = mirror
    return st


def row_of(state, label: str) -> int:
    return int(state.labels[label])


def slot_of(state, label: str) -> int:
    return row_of(state, label) % 11


def clip_moments(slug: str) -> list[int]:
    return sorted(int(p.stem) for p in moments_dir(slug).glob("*.json"))


__all__ = ["CLIPS", "fill", "fit_homography", "load", "save", "to_state"]
