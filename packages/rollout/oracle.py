"""Oracle: will there be a shot in the next 10 s, from where, by whom (TECH_PLAN 1.5 "Callers", 1.14 #2, T-046).

    oracle(match, t_ms, n=100, horizon_s=8, seed=4242) -> Forecast

One unforced rollout of n worlds from the current state. A shot inside the 8 s horizon counts directly; seconds 8-10
are an estimate (the learned engine is capped at 8 s, ADR-002): for worlds without a shot, the goal-in-8-s head on
the terminal state times the corpus shots-per-goal ratio, scaled to the remaining 2 s. `p_shot_10s_estimated` says
how much of the number came from that estimate.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from kickoff.physics_prior import BOX_DEPTH, BOX_HALF, GOAL_Y, PITCH_L

from .core import MatchRef, simulate
from .futures import heads

SHOTS_PER_GOAL = 9.0          # corpus seeds 1-50: 13.2 shots and 1.52 goals per team per match (T-014)
WINDOW_S = 10.0


@dataclass
class Forecast:
    t_ms: int
    p_shot_10s: dict[str, float]               # {"home": p, "away": p}
    p_shot_10s_estimated: dict[str, float]     # the part contributed by the 8-10 s hand-off
    likely_zone: dict[str, str | None]
    likely_shooter: dict[str, str | None]
    n: int
    horizon_s: float
    seed: int
    engine: str
    shots_in_horizon: dict[str, float] = field(default_factory=dict)

    def to_doc(self, match_id: str) -> dict:
        return {"match_id": match_id, "t_ms": self.t_ms, "p_shot_10s": self.p_shot_10s,
                "p_shot_10s_estimated": self.p_shot_10s_estimated, "likely_zone": self.likely_zone,
                "likely_shooter": self.likely_shooter, "n": self.n, "horizon_s": self.horizon_s, "seed": self.seed,
                "engine": self.engine, "estimate_note": "seconds 8-10 valued by the goal-in-8-s head"}


def shot_zone(x: float, y: float, team: int, period: int) -> str:
    """Zone of a shot in the shooter's attacking frame: inside_box_left/central/right or outside_box."""
    d = (1 if period == 1 else -1) * (1 if team == 0 else -1)
    u, v = (x, y) if d > 0 else (PITCH_L - x, 68.0 - y)
    if u < PITCH_L - BOX_DEPTH or abs(v - GOAL_Y) > BOX_HALF:
        return "outside_box"
    # v is mirrored in the team frame so low v is the attacking team's right
    return "box_central" if abs(v - GOAL_Y) <= 7.0 else ("box_right" if v < GOAL_Y else "box_left")


def _world_shots(eng) -> list[list[tuple[str, list[float], int]]]:
    """Per world: (team, location, period) of every shot event logged during the rollout."""
    out = []
    for w in eng.worlds:
        evs = [x[2] for x in w.log._ready] + list(w.log._open.values()) + list(w.log.released)
        out.append([(e.team, e.location, e.player, e.period) for e in evs if e.type == "shot"])
    return out


def oracle(match: MatchRef, t_ms: int, n: int = 100, horizon_s: float = 8, seed: int = 4242,
           engine: str = "scripted_v1") -> Forecast:
    sim = simulate(match.state_at(t_ms), None, n, horizon_s, seed, engine)
    eng = sim.eng
    shots = _world_shots(eng)
    goal8s, _ = heads()
    from heads.features import state_features
    team = np.where(eng.possession >= 0, eng.possession, np.where(eng.last_touch >= 11, 1, 0))
    feats = state_features(eng.S, eng.ball_z, eng.holder, team, np.full(n, eng.period), np.full(n, eng.t_ms), ~eng.dead)
    head = goal8s.predict(feats.assign(poss_team=team))                            # [n, 2]
    rest = max(0.0, WINDOW_S - horizon_s) / 8.0
    p, est, zone, shooter, count = {}, {}, {}, {}, {}
    for k, side in enumerate(("home", "away")):
        had = np.array([any(s[0] == side for s in ws) for ws in shots])
        extra = np.minimum(1.0, head[:, k] * SHOTS_PER_GOAL * rest)
        p[side] = round(float(np.mean(had + (~had) * extra)), 4)
        est[side] = round(float(np.mean((~had) * extra)), 4)
        firsts = [next(s for s in ws if s[0] == side) for ws in shots if any(s[0] == side for s in ws)]
        zone[side] = Counter(shot_zone(s[1][0], s[1][1], k, s[3]) for s in firsts).most_common(1)[0][0] if firsts else None
        shooter[side] = Counter(s[2] for s in firsts).most_common(1)[0][0] if firsts else None
        count[side] = round(float(np.mean([sum(s[0] == side for s in ws) for ws in shots])), 3)
    return Forecast(t_ms=int(t_ms), p_shot_10s=p, p_shot_10s_estimated=est, likely_zone=zone, likely_shooter=shooter,
                    n=n, horizon_s=float(horizon_s), seed=seed, engine=engine, shots_in_horizon=count)
