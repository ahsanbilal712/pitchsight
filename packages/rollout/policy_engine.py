"""policy_v1: rollouts whose on-ball decisions come from the learned DecisionPolicy.

Decision points: the policy is asked when a player gains control or 1.0 s after its last call for the same holder,
on a shared 0.5 s grid so that all due worlds go through one forward pass (about 16 calls for 8 s at B = 200, the
audit's "decision-only" path). Between calls the previous action persists (a carry continues, a pass is in flight).
Restarts and a forced first action (Override) stay with the engine rule. Off-ball movement, ball physics and duels
are the engine's. Sampling: torch.Generator().manual_seed(seed) with logits moved to CPU before torch.multinomial,
so MPS and CPU draw the same samples.
"""

from __future__ import annotations

import math
import types

import numpy as np
import torch

from kickoff.engine import Engine
from kickoff.physics_prior import segment_distance, to_team
from kickoff.rules import CARRY, CLEAR, FREE, HOLD, PASS, SHOOT
from policy.data import KICKOFF_ROLE, context, tokens_from_arrays
from policy.loader import load_policy

GRID_MS = 500
RECALL_MS = 1000
POLICY_KIND = {0: PASS, 1: CARRY, 2: SHOOT, 3: CLEAR, 4: HOLD}       # policy.data order -> engine codes


def policy_branch(src: Engine, B: int, overrides, seed: int, decide_now: bool = False, device: str | None = None,
                  model=None) -> Engine:
    eng = src.branch(src.t_ms, B, overrides, seed=seed, decide_now=False)
    eng.policy = model or load_policy(device=device)
    eng.policy_gen = torch.Generator().manual_seed(int(seed))
    eng.pol_last_call = np.full(B, -10**9, dtype=np.int64)
    eng.pol_last_holder = np.full(B, -2, dtype=np.int64)
    eng.pol_now = np.full(B, bool(decide_now))                          # baseline: the policy decides on tick 1
    eng.policy_calls = 0
    eng._decide = types.MethodType(_policy_decide, eng)
    return eng


def _policy_decide(self: Engine, noise: np.ndarray) -> None:
    t = self.t_ms
    live = (~self.dead) & (self.holder >= 0) & (t - self.control_since >= self.latency)
    rule = live & (self.restart_flag != FREE)
    if self.force is not None and self.force.get("action") is not None:
        rule |= self.force_pending & (self.holder == self.force["row"]) & ~self.dead
    if rule.any():
        Engine._decide(self, noise, only=rule)
    now = self.pol_now & ~self.dead & (self.holder >= 0) & ~rule
    gained = self.holder != self.pol_last_holder
    due = live & ~rule & (gained | (t - self.pol_last_call >= RECALL_MS)) & (t % GRID_MS == 0)
    due |= now
    self.pol_now[:] = False
    idx = np.flatnonzero(due)
    if idx.size == 0:
        return
    self.pol_last_call[idx], self.pol_last_holder[idx] = t, self.holder[idx]
    h = self.holder[idx].astype(np.int64)
    poss = (h >= 11).astype(np.int64)
    sign = np.where(poss == 0, self.home_dir, -self.home_dir)
    roles = np.tile(np.r_[KICKOFF_ROLE, KICKOFF_ROLE], (idx.size, 1))
    tok = tokens_from_arrays(self.S[idx, :, 0:2], self.S[idx, :, 2:4], roles, h, poss, sign)
    sc = self.score[idx].astype(np.float64)
    diff = np.where(poss == 0, sc[:, 0] - sc[:, 1], sc[:, 1] - sc[:, 0])
    ctx = context(diff, np.full(idx.size, t / 5_400_000.0), np.full(idx.size, float(self.period)),
                  (poss == 0).astype(float))
    device = next(self.policy.parameters()).device
    with torch.no_grad():
        out = self.policy(torch.from_numpy(tok.astype(np.float32)).to(device), torch.from_numpy(ctx).to(device))
        logits = [out.kind_logits.float().cpu(), out.pass_logits.float().cpu(), out.carry_logits.float().cpu()]
    self.policy_calls += 1
    g = self.policy_gen
    kind = torch.multinomial(torch.softmax(logits[0], -1), 1, generator=g)[:, 0].numpy()
    target = torch.multinomial(torch.softmax(logits[1], -1), 1, generator=g)[:, 0].numpy()
    carry = torch.multinomial(torch.softmax(logits[2], -1), 1, generator=g)[:, 0].numpy()
    for i, b in enumerate(idx):
        b, row, team = int(b), int(h[i]), int(poss[i])
        k = POLICY_KIND[int(kind[i])]
        w = self.worlds[b]
        self.mode[b] = k
        if k == CARRY:
            ang = int(carry[i]) * math.pi / 4
            self.carry_dir[b] = [math.cos(ang) * sign[i], math.sin(ang) * sign[i]]
        elif k == PASS:
            tgt = 11 * team + int(target[i])
            self._kick_pass(w, row, tgt, _lofted(self, b, row, tgt), noise[b])
        elif k == SHOOT:
            self._kick_shot(w, row, noise[b])
        elif k == CLEAR:
            self._kick_clear(w, row, noise[b])


def _lofted(eng: Engine, b: int, row: int, tgt: int) -> bool:
    """The engine rule's pass height: long passes and passes with an opponent in the lane go in the air."""
    team = row // 11
    d = eng.team_dir(team)
    u, v = to_team(eng.S[b, :22, 0], eng.S[b, :22, 1], d)
    dist = math.hypot(u[tgt] - u[row], v[tgt] - v[row])
    opp = np.arange(11 * (1 - team), 11 * (1 - team) + 11)
    lane = float(segment_distance(u[opp], v[opp], u[row], v[row], u[tgt], v[tgt]).min())
    return dist > 32.0 or (lane < 1.6 and dist > 14.0)
