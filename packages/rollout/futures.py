"""Futures: what a rollout returns, and the horizon hand-off to the outcome heads (TECH_PLAN 1.5).

For each world, goal_b = 1 if the team scores within the horizon; worlds without a goal are valued by GoalIn8sHead
on their terminal state, so p_goal_team = mean_b[goal_b + (1 - goal_b) * head_b]. Win probability is WinProbHead on
the terminal score, mixed over "nobody scores / home scores / away scores next" with the goal head's probabilities
(the expected score adjustment), then averaged; the 95% interval is the normal approximation over B.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from heads.features import WINPROB_FEATURES, state_features
from kickoff.physics_prior import threat, to_team

_HEADS: dict[str, object] = {}


def heads() -> tuple[object, object]:
    """(GoalIn8sHead, WinProbHead), loaded once; a missing artefact raises (no silent fallback)."""
    if not _HEADS:
        from heads.models import GoalIn8sHead, WinProbHead
        _HEADS["goal8s"], _HEADS["winprob"] = GoalIn8sHead(), WinProbHead()
    return _HEADS["goal8s"], _HEADS["winprob"]


@dataclass
class Futures:
    S_end: np.ndarray                 # [B, 23, 6] float32
    goals: np.ndarray                 # [B, 2] goals scored within the horizon (home, away)
    shots: np.ndarray                 # [B, 2]
    ball_paths: np.ndarray            # [B, horizon_s + 1, 2] float32, 1 Hz
    p_goal_home: float
    p_goal_away: float
    win_prob_home: float
    ci95: tuple[float, float]         # of win_prob_home
    xt_gain_mean: float
    invalid_reason: str | None = None
    meta: dict = field(default_factory=dict)   # t_ms, B, horizon_s, seed, engine
    per_world: dict[str, np.ndarray] = field(default_factory=dict)   # p_home, p_away, win_prob, first_kind, first_target

    @classmethod
    def invalid(cls, reason: str, meta: dict) -> Futures:
        empty = np.zeros((0,))
        return cls(S_end=empty, goals=empty, shots=empty, ball_paths=empty, p_goal_home=float("nan"),
                   p_goal_away=float("nan"), win_prob_home=float("nan"), ci95=(float("nan"), float("nan")),
                   xt_gain_mean=float("nan"), invalid_reason=reason, meta=meta)

    def digest(self) -> str:
        """SHA-256 over every array and number: equal digests mean byte-identical futures."""
        h = hashlib.sha256()
        for arr in (self.S_end, self.goals, self.shots, self.ball_paths, *(self.per_world[k] for k in sorted(self.per_world))):
            a = np.ascontiguousarray(arr)
            h.update(str((a.dtype.str, a.shape)).encode())
            h.update(a.tobytes())
        h.update(repr((self.p_goal_home, self.p_goal_away, self.win_prob_home, self.ci95, self.xt_gain_mean,
                       self.invalid_reason, sorted(self.meta.items()))).encode())
        return h.hexdigest()

    def outcome(self) -> dict:
        """The counterfactual.schema.json `outcome` object (rounded for display)."""
        return {"p_goal_home": round(self.p_goal_home, 4), "p_goal_away": round(self.p_goal_away, 4),
                "win_prob_home": round(self.win_prob_home, 4), "mean_xt_gain": round(self.xt_gain_mean, 5),
                "shots_home": round(float(self.shots[:, 0].mean()), 3),
                "shots_away": round(float(self.shots[:, 1].mean()), 3),
                "ci95_win_prob_home": [round(self.ci95[0], 4), round(self.ci95[1], 4)]}


def value_terminal(eng, goals: np.ndarray, context: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per world: P(home goal in horizon or next 8 s), the same for away, and [home win, draw, away win]."""
    goal8s, winprob = heads()
    B = eng.B
    team = np.where(eng.possession >= 0, eng.possession, np.where(eng.last_touch >= 11, 1, 0))
    period = np.full(B, eng.period)
    t = np.full(B, eng.t_ms)
    feats = state_features(eng.S, eng.ball_z, eng.holder, team, period, t, ~eng.dead)
    feats["poss_team"] = team
    head = goal8s.predict(feats)                                          # [B, 2] home, away within 8 s
    scored = goals > 0
    p_home = np.where(scored[:, 0], 1.0, head[:, 0])
    p_away = np.where(scored[:, 1], 1.0, head[:, 1])
    score = eng.score
    rows = []
    for dh, da in ((0, 0), (1, 0), (0, 1)):
        rows.append(pd.DataFrame({"score_diff": (score[:, 0] + dh) - (score[:, 1] + da), "minute": eng.t_ms / 60000.0,
                                  "period": eng.period, "red_card_diff": 0, "xt_diff_15": context["xt_diff_15"],
                                  "xg_diff_15": context["xg_diff_15"], "chaos": context["chaos"]}))
    P = winprob.predict(pd.concat(rows, ignore_index=True)[WINPROB_FEATURES]).reshape(3, B, 3)
    nh, na = head[:, 0:1], head[:, 1:2]
    mix = (1.0 - nh - na) * P[0] + nh * P[1] + na * P[2]                       # [B, 3] home, draw, away
    return p_home, p_away, mix


def xt_gain(start_ball: np.ndarray, end_ball: np.ndarray, team: int, period: int) -> np.ndarray:
    """Expected-threat change of the ball for `team` (0/1) between two positions, per world."""
    d = (1 if period == 1 else -1) * (1 if team == 0 else -1)
    u0, v0 = to_team(start_ball[..., 0], start_ball[..., 1], d)
    u1, v1 = to_team(end_ball[..., 0], end_ball[..., 1], d)
    return threat(u1, v1) - threat(u0, v0)
