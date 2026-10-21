"""Physical constants and small vectorised models the engine and the scripted rule share.

All distances in metres, speeds in m/s, times in seconds. Team-frame coordinates (u, v) put the team's
own goal at u = 0 and the goal it attacks at u = 105, with v mirrored so the right flank stays low v.
"""

from __future__ import annotations

import numpy as np

PITCH_L, PITCH_W = 105.0, 68.0
DT = 0.1                          # seconds per tick (10 Hz)
TICK_MS = 100
GOAL_Y, GOAL_HALF, GOAL_H = 34.0, 3.66, 2.44
BOX_DEPTH, BOX_HALF = 16.5, 20.16
PENALTY_SPOT = 94.0               # team frame u
BALL_REST_Z = 0.11
G = 9.81

CONTROL_R = 1.0                   # a player can take the ball within this radius
KEEPER_R = 1.8
HEADER_Z = 2.3                    # highest ball a player can control
PRESSURE_R = 3.0
TACKLE_R = 1.3

SPRINT = 7.8                      # reference top speed (m/s); each player's own comes from top_speed()
JOG = 4.2
ACCEL = 4.5                       # m/s^2
GROUND_DECAY = 0.75               # 1/s, exponential speed decay of a rolling ball
AIR_DRAG = 0.08
STAMINA_COST = 1.3e-6             # per tick per (m/s)^2
XG_INTERCEPT = -2.65              # open-play xG logit at zero angle, zero distance, empty cone


TOP_SPEED_BASE = {"GK": 7.3, "DF": 8.5, "MF": 8.4, "FW": 8.8}      # m/s at full stamina (26-32 km/h)
TOP_SPEED_TRAITS = {"recovery pace": 0.5, "runs in behind": 0.5, "overlapping runs": 0.3, "dribbler": 0.25,
                    "progressive carrier": 0.2, "inverted runs": 0.2, "back-post runner": 0.15}


def top_speed(position: str, traits: list[str], age: int, player_id: str) -> float:
    """A player's top speed (m/s): position base, pace traits, -0.05 per year past 27, and a fixed +-0.25 spread
    from the player id (no random draw, so the engine's random streams are untouched)."""
    spread = ((int(player_id[2:]) * 37) % 11 - 5) / 20.0
    v = TOP_SPEED_BASE.get(position, 8.4) + sum(TOP_SPEED_TRAITS.get(t, 0.0) for t in traits)
    return float(v - 0.05 * max(0, age - 27) + spread)


def to_team(x, y, direction):
    """Absolute (x, y) to team frame (u, v); direction is +1 when the team attacks +x."""
    pos = direction > 0
    return np.where(pos, x, PITCH_L - x), np.where(pos, y, PITCH_W - y)


from_team = to_team               # the mapping is its own inverse


def goal_angle(u, v):
    """Opening angle (radians) of the attacked goal mouth seen from (u, v) in team frame."""
    a1 = np.arctan2(GOAL_Y + GOAL_HALF - v, PITCH_L - u)
    a2 = np.arctan2(GOAL_Y - GOAL_HALF - v, PITCH_L - u)
    return np.abs(a1 - a2)


def goal_distance(u, v):
    return np.hypot(PITCH_L - u, GOAL_Y - v)


def xg(dist, angle, cone):
    """Open-play expected goals: logistic in goal angle, distance and defenders in the shooting cone."""
    z = XG_INTERCEPT + 2.8 * angle - 0.07 * dist - 0.5 * cone
    return 1.0 / (1.0 + np.exp(-z))


def threat(u, v):
    """Rough probability that possession at (u, v) becomes a goal soon (an expected-threat surface)."""
    return 0.25 * np.exp(-goal_distance(u, v) / 12.0)


def pass_launch(dist, lofted):
    """Initial horizontal speed and vertical speed of a pass over `dist` metres."""
    if lofted:
        flight = 0.35 + dist / 22.0
        return dist / flight, 0.5 * G * flight
    v0 = dist * GROUND_DECAY + 6.0
    return float(np.clip(v0, 8.0, 28.0)), 0.0


def segment_distance(px, py, ax, ay, bx, by):
    """Distance from points (px, py) to the segment a-b (broadcasts)."""
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    s = np.minimum(np.maximum(((px - ax) * dx + (py - ay) * dy) / np.where(seg2 > 1e-9, seg2, 1.0), 0.0), 1.0)
    return np.hypot(px - (ax + s * dx), py - (ay + s * dy))


def cone_counts(u, v, opp_u, opp_v) -> np.ndarray:
    """`cone_count` for D shooters at once: u, v [D]; opp_u, opp_v [D, 11]."""
    u, v = np.asarray(u)[:, None], np.asarray(v)[:, None]
    a = np.arctan2(GOAL_Y + GOAL_HALF - v, PITCH_L - u)
    b = np.arctan2(GOAL_Y - GOAL_HALF - v, PITCH_L - u)
    ang = np.arctan2(opp_v - v, opp_u - u)
    ahead = (opp_u > u) & (np.hypot(opp_u - u, opp_v - v) < goal_distance(u, v))
    lo, hi = np.minimum(a, b) - 0.03, np.maximum(a, b) + 0.03
    return np.sum(ahead & (ang >= lo) & (ang <= hi), axis=1).astype(np.int64)


def cone_count(u, v, opp_u, opp_v):
    """Opponents inside the triangle between the shooter and the two posts (team frame)."""
    a = np.arctan2(GOAL_Y + GOAL_HALF - v, PITCH_L - u)
    b = np.arctan2(GOAL_Y - GOAL_HALF - v, PITCH_L - u)
    ang = np.arctan2(opp_v - v, opp_u - u)
    ahead = (opp_u > u) & (np.hypot(opp_u - u, opp_v - v) < goal_distance(u, v))
    lo, hi = np.minimum(a, b) - 0.03, np.maximum(a, b) + 0.03
    return int(np.sum(ahead & (ang >= lo) & (ang <= hi)))
