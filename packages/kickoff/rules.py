"""Decision models: the on-ball choice of the player in control.

`ScriptedRule` scores every option (ten passes, shoot, clear, carry) with simple football utilities,
releases the ball with a pressure- and tempo-dependent hazard, and picks among release options with
Gumbel noise. All randomness comes from the per-tick noise row the engine draws from each world's
generator, so a decision is a pure function of (state, noise): deterministic given the rng.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from .physics_prior import (
    DT,
    PITCH_L,
    PITCH_W,
    cone_count,
    goal_angle,
    goal_distance,
    segment_distance,
    threat,
    to_team,
    xg,
)

PASS, CARRY, SHOOT, CLEAR, HOLD = 0, 1, 2, 3, 4
KINDS = ("pass", "carry", "shoot", "clear", "hold")
# Restart constraints a decision must respect.
FREE, PASS_ONLY, CROSS, PENALTY, KICK_OFF = 0, 1, 2, 3, 4
RULE_NOISE = 16                   # noise slots 0..15 belong to the rule; the engine uses the rest


@dataclass(frozen=True)
class Action:
    """One on-ball decision. `target` is a team slot (0-10) for passes; `direction` is a unit vector (x, y)."""
    kind: str
    target: int | None = None
    direction: tuple[float, float] | None = None
    lofted: bool = False


@dataclass
class DecisionBatch:
    """Inputs for D worlds that need a decision, in the holder team's frame (own goal at u = 0)."""
    U: np.ndarray            # [D, 22] players' u: slots 0-10 the holder's team, 11-21 opponents
    V: np.ndarray            # [D, 22]
    holder: np.ndarray       # [D] slot of the holder (0-10)
    styles: np.ndarray       # [D, 5] press_height, tempo, width, directness, line_height (holder's team)
    momentum: np.ndarray     # [D] hidden momentum of the holder's team, -1..1
    restart: np.ndarray      # [D] FREE | PASS_ONLY | CROSS | PENALTY | KICK_OFF
    noise: np.ndarray        # [D, >= RULE_NOISE] uniforms in [0, 1)


@dataclass
class DecisionOut:
    act: np.ndarray          # [D] bool, release the ball this tick
    kind: np.ndarray         # [D] int, PASS | CARRY | SHOOT | CLEAR | HOLD
    target: np.ndarray       # [D] int, team slot for passes, -1 otherwise
    lofted: np.ndarray       # [D] bool
    dir_u: np.ndarray        # [D] carry direction in team frame
    dir_v: np.ndarray


class DecisionModel(Protocol):
    def decide(self, state) -> Action: ...

    def decide_batch(self, batch: DecisionBatch) -> DecisionOut: ...


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


class ScriptedRule:
    """Utility + noise on-ball rule (scripted_v1)."""

    temperature = 0.012
    # Tuned on seeds 1-50 against the TECH_PLAN 1.4 realism ranges (T-014).
    shot_scale = 1.3              # weight on xG when comparing a shot with the best pass
    shot_range_m = 25.0           # no open-play shots from further out
    through_ball_bias = 0.045     # the passer over-rates a runner past the offside line (mistimed runs -> offsides)
    rate_base, rate_tempo = 0.55, 1.1   # release hazard per second: base + tempo term

    def decide_batch(self, b: DecisionBatch) -> DecisionOut:
        D = b.U.shape[0]
        rows = np.arange(D)
        u0, v0 = b.U[rows, b.holder], b.V[rows, b.holder]
        mu, mv = b.U[:, :11], b.V[:, :11]
        ou, ov = b.U[:, 11:], b.V[:, 11:]
        tempo, directness = b.styles[:, 1], b.styles[:, 3]

        # passes to the ten team-mates
        d = np.hypot(mu - u0[:, None], mv - v0[:, None])                                     # [D, 11]
        lane = segment_distance(ou[:, None, :], ov[:, None, :], u0[:, None, None], v0[:, None, None],
                                mu[:, :, None], mv[:, :, None]).min(axis=2)                  # [D, 11]
        space = np.hypot(ou[:, None, :] - mu[:, :, None], ov[:, None, :] - mv[:, :, None]).min(axis=2)
        lofted = (d > 32.0) | ((lane < 1.6) & (d > 14.0))
        lane_eff = np.where(lofted, 2.5, np.minimum(lane, 5.0))
        pc = _sigmoid(0.2 - 0.035 * d + 0.75 * lane_eff + 0.35 * np.minimum(space, 5.0) - 0.6 * lofted)
        gain = threat(mu, mv) + 0.01 * directness[:, None] * np.maximum(0.0, mu - u0[:, None]) / 10.0
        loss = 0.5 * threat(PITCH_L - u0, PITCH_W - v0)
        value_pass = pc * gain - (1.0 - pc) * loss[:, None]
        second_last = np.sort(ou, axis=1)[:, -2]
        line = np.maximum(np.maximum(second_last, u0), PITCH_L / 2)
        value_pass = value_pass + self.through_ball_bias * (mu > line[:, None] + 0.2)
        value_pass[:, 0] -= 0.01                                                            # back to the keeper
        value_pass[rows, b.holder] = -np.inf
        value_pass[d < 3.0] = -np.inf

        # shoot, clear, carry
        dist0, ang0 = goal_distance(u0, v0), goal_angle(u0, v0)
        cone = np.array([cone_count(u0[i], v0[i], ou[i], ov[i]) for i in range(D)])
        value_shoot = np.where(dist0 < self.shot_range_m, self.shot_scale * xg(dist0, ang0, cone) * (1.0 + 0.25 * b.momentum), -np.inf)
        pressure = np.hypot(ou - u0[:, None], ov - v0[:, None]).min(axis=1)
        value_clear = np.where((u0 < 25.0) & (pressure < 2.5), 0.6 * loss, -np.inf)
        value_carry = threat(np.minimum(u0 + 3.0, PITCH_L), v0) * np.clip(pressure / 4.0, 0.2, 1.0)

        # restarts narrow the options
        r = b.restart
        value_shoot = np.where(np.isin(r, (PASS_ONLY, CROSS, KICK_OFF)), -np.inf, value_shoot)
        value_shoot = np.where(r == PENALTY, 1.0, value_shoot)
        value_clear = np.where(r != FREE, -np.inf, value_clear)
        value_pass = np.where((r == PENALTY)[:, None], -np.inf, value_pass)
        value_pass = np.where(((r == PASS_ONLY) | (r == KICK_OFF))[:, None] & (d > 30.0), -np.inf, value_pass)
        value_pass = np.where((r == KICK_OFF)[:, None] & (mu > u0[:, None]), -np.inf, value_pass)
        in_box = (mu > PITCH_L - 16.5) & (np.abs(mv - PITCH_W / 2) < 20.0)
        value_pass = np.where((r == CROSS)[:, None] & ~in_box, -np.inf, value_pass)
        lofted = np.where((r == CROSS)[:, None], True, lofted)

        stuck = (r != FREE) & ~np.isfinite(value_pass).any(axis=1) & ~np.isfinite(value_shoot)
        if stuck.any():                                    # a restart with no legal target: any pass will do
            fallback = pc * gain - (1.0 - pc) * loss[:, None]
            fallback[rows, b.holder] = -np.inf
            value_pass = np.where(stuck[:, None], fallback, value_pass)
        options = np.concatenate([value_pass, value_shoot[:, None], value_clear[:, None]], axis=1)   # [D, 13]
        best = options.max(axis=1)
        rate = (self.rate_base + self.rate_tempo * tempo) * (1.0 + 0.15 * b.momentum) * (1.0 + 1.5 * np.clip((3.0 - pressure) / 3.0, 0, 1))
        rate = np.where(b.holder == 0, rate * 0.6, rate)
        p_act = 1.0 - np.exp(-rate * _sigmoid((best - value_carry) / 0.01) * DT)
        act = (b.noise[:, 0] < p_act) | (r != FREE)
        act &= np.isfinite(best)

        gumbel = -np.log(-np.log(np.clip(b.noise[:, 1:14], 1e-9, 1 - 1e-9)))
        choice = np.argmax(np.where(np.isfinite(options), options / self.temperature + gumbel, -np.inf), axis=1)
        kind = np.where(choice < 11, PASS, np.where(choice == 11, SHOOT, CLEAR))
        kind = np.where(act, kind, np.where(b.holder == 0, HOLD, CARRY))
        target = np.where(kind == PASS, choice, -1)
        lofted_out = np.where(kind == PASS, lofted[rows, np.clip(choice, 0, 10)], kind == CLEAR)

        # carry toward goal, bending away from the nearest opponent and the touchlines
        gu, gv = PITCH_L - u0, PITCH_W / 2 - v0
        norm = np.hypot(gu, gv) + 1e-9
        gu, gv = gu / norm, gv / norm
        k = np.argmin(np.hypot(ou - u0[:, None], ov - v0[:, None]), axis=1)
        au, av = ou[rows, k] - u0, ov[rows, k] - v0
        an = np.hypot(au, av) + 1e-9
        push = np.where(pressure < 4.0, 0.7, 0.0)
        du, dv = gu - push * au / an, gv - push * av / an
        dv = dv + np.where(v0 < 4.0, 0.6, 0.0) - np.where(v0 > PITCH_W - 4.0, 0.6, 0.0)
        dn = np.hypot(du, dv) + 1e-9
        return DecisionOut(act=act, kind=kind, target=target, lofted=lofted_out.astype(bool),
                           dir_u=du / dn, dir_v=dv / dn)

    def decide(self, state, world: int = 0, noise: np.ndarray | None = None) -> Action:
        """Single-world decision from a kickoff State; noise defaults to a fixed row (deterministic)."""
        S, holder = state.S[world], int(state.holder[world])
        if holder < 0:
            return Action(kind="hold")
        team = 0 if holder < 11 else 1
        direction = state.attack_dir if team == 0 else -state.attack_dir
        order = list(range(11 * team, 11 * team + 11)) + list(range(11 * (1 - team), 11 * (1 - team) + 11))
        U, V = to_team(S[order, 0], S[order, 1], direction)
        styles = state.styles["home" if team == 0 else "away"]
        batch = DecisionBatch(
            U=U[None].astype(float), V=V[None].astype(float), holder=np.array([holder - 11 * team]),
            styles=np.array([[styles[k] for k in ("press_height", "tempo", "width", "directness", "line_height")]]),
            momentum=np.zeros(1), restart=np.array([FREE]),
            noise=(np.full((1, RULE_NOISE), 0.5) if noise is None else np.asarray(noise)[None]))
        out = self.decide_batch(batch)
        kind = KINDS[int(out.kind[0])]
        dx, dy = (float(out.dir_u[0]) * direction, float(out.dir_v[0]) * direction)
        return Action(kind=kind, target=int(out.target[0]) if out.target[0] >= 0 else None,
                      direction=(dx, dy), lofted=bool(out.lofted[0]))
