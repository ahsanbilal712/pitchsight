"""Ball, shot and sprint speeds over a tracking window (TECH_PLAN 1.4 physics)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .window import TrackingWindow

KMH = 3.6
SPRINT_KMH = 25.0         # a run counts as a sprint above this speed
SHOT_MIN_KMH = 54.0       # a ball this fast with no holder is a strike


@dataclass
class SpeedReport:
    ball_kmh: float                                      # ball speed in the last frame
    shot_kmh: float | None                               # fastest unheld ball in the window, if a strike happened
    sprints: list[tuple[str, float, int]] = field(default_factory=list)   # (player, peak km/h, t_ms of the peak)


def speeds(window: TrackingWindow) -> SpeedReport:
    """Speeds from the velocity columns of S. A sprint is one contiguous run above SPRINT_KMH; it is reported
    with its peak speed and the time of the peak. Players are named by id with substitutions applied."""
    if len(window) == 0:
        raise ValueError("empty tracking window")
    S = np.asarray(window.S, dtype=np.float64)
    ball = np.hypot(S[:, 22, 2], S[:, 22, 3]) * KMH
    loose = window.holder < 0
    shot = float(ball[loose].max()) if loose.any() and ball[loose].max() >= SHOT_MIN_KMH else None
    sp = np.hypot(S[:, :22, 2], S[:, :22, 3]) * KMH                       # [T, 22]
    fast = sp > SPRINT_KMH
    sprints: list[tuple[str, float, int]] = []
    for row in np.flatnonzero(fast.any(axis=0)):
        f = fast[:, row].astype(np.int8)
        edges = np.diff(np.r_[0, f, 0])
        for a, b in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1), strict=True):
            k = a + int(np.argmax(sp[a:b, row]))
            t = int(window.t_ms[k])
            sprints.append((window.player_at(int(row), t), round(float(sp[k, row]), 1), t))
    sprints.sort(key=lambda s: (s[2], s[0]))
    return SpeedReport(ball_kmh=round(float(ball[-1]), 1), shot_kmh=None if shot is None else round(shot, 1),
                       sprints=sprints)
