"""Keeper positioning on a real save (video v3): how much of the goal mouth the keeper covers from where he stood,
against the best point on the bisector of the shooting angle.

The engine's shot model does not use the keeper's position (kickoff `_kick_shot`: p_goal = FINISH * xg(distance,
angle, cone)), so this is geometry, not an engine save probability, and the cue says so. Shots are spread evenly
along the goal line between the posts; the keeper reaches a shot when its path passes within his reach, which grows
with the time the ball takes to get to him: standing reach plus a dive after a reaction delay. The constants below
are assumptions, written into every result.
"""

from __future__ import annotations

import math

import numpy as np

GOAL_HALF = 3.66
SHOT_SPEED_MS = 26.0        # the engine's shots leave at 22-31 m/s
REACTION_S = 0.25
DIVE_MS = 3.5
STAND_REACH_M = 1.0
MAX_REACH_M = 2.6
SAMPLES = 201
ASSUMPTIONS = {"shot_speed_ms": SHOT_SPEED_MS, "reaction_s": REACTION_S, "dive_speed_ms": DIVE_MS,
               "standing_reach_m": STAND_REACH_M, "max_reach_m": MAX_REACH_M,
               "shots": "uniform along the goal line between the posts"}


def coverage(shooter: tuple[float, float], keeper: tuple[float, float], goal_x: float, goal_y: float = 34.0) -> float:
    """Share of shots (uniform along the goal mouth) whose path passes within the keeper's reach in time."""
    sx, sy = shooter
    kx, ky = keeper
    targets = np.linspace(goal_y - GOAL_HALF, goal_y + GOAL_HALF, SAMPLES)
    dx, dy = goal_x - sx, targets - sy
    length = np.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    along = (kx - sx) * ux + (ky - sy) * uy                 # distance along the shot to the keeper's crossing point
    perp = np.abs((kx - sx) * uy - (ky - sy) * ux)          # how far the keeper is from the shot's path
    t = np.clip(along, 0.0, None) / SHOT_SPEED_MS
    reach = np.minimum(STAND_REACH_M + DIVE_MS * np.clip(t - REACTION_S, 0.0, None), MAX_REACH_M)
    ok = (along > 0) & (along < length) & (perp <= reach)
    return float(ok.mean())


def bisector_point(shooter: tuple[float, float], goal_x: float, depth_m: float, goal_y: float = 34.0
                   ) -> tuple[float, float]:
    """The point `depth_m` off the goal line on the bisector of the angle the posts make at the shooter."""
    sx, sy = shooter
    a1 = math.atan2(goal_y + GOAL_HALF - sy, goal_x - sx)
    a2 = math.atan2(goal_y - GOAL_HALF - sy, goal_x - sx)
    a = (a1 + a2) / 2
    cos = math.cos(a)
    if abs(cos) < 1e-6:
        raise ValueError("shooter on the goal line")
    s = (goal_x - sx - math.copysign(depth_m, goal_x - sx)) / cos      # walk the bisector to x = goal_x -/+ depth
    return sx + s * math.cos(a), sy + s * math.sin(a)


def best_on_bisector(shooter: tuple[float, float], goal_x: float, goal_y: float = 34.0) -> dict:
    """The depth off the goal line (0.3-8 m) on the bisector that covers most of the goal mouth."""
    best = None
    for depth in np.arange(0.3, 8.01, 0.1):
        p = bisector_point(shooter, goal_x, float(depth), goal_y)
        c = coverage(shooter, p, goal_x, goal_y)
        if best is None or c > best["coverage"] + 1e-9:
            best = {"coverage": round(c, 4), "x": round(p[0], 2), "y": round(p[1], 2), "depth_m": round(float(depth), 1)}
    return best


def assess(shooter: tuple[float, float], keeper: tuple[float, float], goal_x: float, goal_y: float = 34.0) -> dict:
    actual = coverage(shooter, keeper, goal_x, goal_y)
    best = best_on_bisector(shooter, goal_x, goal_y)
    return {"actual_coverage": round(actual, 4), "best": best,
            "move_m": round(math.hypot(best["x"] - keeper[0], best["y"] - keeper[1]), 2),
            "shot_distance_m": round(math.hypot(goal_x - shooter[0], goal_y - shooter[1]), 1),
            "assumptions": ASSUMPTIONS}
