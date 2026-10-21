"""DecisionPolicy: a set transformer over the 22 players and the ball (TECH_PLAN 1.4 policy, 1.6 "Model").

Tokens [B, 23, F] (possession team's 11, opponents' 11, ball; see policy.data) go through a linear F -> 256 and
six encoder layers (d 256, 8 heads, FFN 1024, no positional encoding: identity is in the features) together with a
global token built from the context [B, G]. Heads: kind (5) and carry direction (8) from the global and holder
outputs; pass target as a pointer over the possession team's 11 tokens, the holder masked.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch
from torch import Tensor, nn

from .data import CARRY, CLEAR, HOLD, KICKOFF_ROLE, KINDS, PASS, SHOOT, F, G, context, tokens_from_arrays


@dataclass
class PolicyOut:
    kind_logits: Tensor      # [B, 5]
    pass_logits: Tensor      # [B, 11], holder slot = -inf
    carry_logits: Tensor     # [B, 8]


class DecisionPolicy(nn.Module):
    def __init__(self, d_model: int = 256, n_layers: int = 6, n_heads: int = 8, d_ff: int = 1024,
                 dropout: float = 0.1) -> None:
        super().__init__()
        self.embed = nn.Linear(F, d_model)
        self.ctx = nn.Linear(G, d_model)
        layer = nn.TransformerEncoderLayer(d_model, n_heads, d_ff, dropout, batch_first=True, norm_first=True)
        self.encoder = nn.TransformerEncoder(layer, n_layers, enable_nested_tensor=False)
        self.norm = nn.LayerNorm(d_model)
        self.kind_head = nn.Sequential(nn.Linear(2 * d_model, d_model), nn.GELU(), nn.Linear(d_model, len(KINDS)))
        self.carry_head = nn.Sequential(nn.Linear(2 * d_model, d_model), nn.GELU(), nn.Linear(d_model, 8))
        self.query = nn.Linear(2 * d_model, d_model)
        self.key = nn.Linear(d_model, d_model)

    def forward(self, tokens: Tensor, ctx: Tensor) -> PolicyOut:
        x = torch.cat([self.ctx(ctx).unsqueeze(1), self.embed(tokens)], dim=1)          # [B, 24, d]
        h = self.norm(self.encoder(x))
        glob = h[:, 0]
        holder_w = tokens[:, :11, 5]                                                     # one-hot holder slot
        holder = torch.einsum("bs,bsd->bd", holder_w, h[:, 1:12])
        z = torch.cat([glob, holder], dim=1)
        q = self.query(z)
        k = self.key(h[:, 1:12])
        pass_logits = torch.einsum("bd,bsd->bs", q, k) / (k.shape[-1] ** 0.5)
        pass_logits = pass_logits.masked_fill(holder_w > 0.5, float("-inf"))
        return PolicyOut(self.kind_head(z), pass_logits, self.carry_head(z))

    def n_params(self) -> int:
        return sum(p.numel() for p in self.parameters())

    @torch.no_grad()
    def act(self, state, generator: torch.Generator) -> list:
        """One sampled Action per world of a kickoff State (worlds with nobody in control get hold). Logits are moved
        to CPU before torch.multinomial so the sample does not depend on the device (TECH_PLAN 1.5)."""
        from kickoff import Action

        tokens, ctx, valid = state_tokens(state)
        device = next(self.parameters()).device
        out = self(torch.from_numpy(tokens).to(device), torch.from_numpy(ctx).to(device))
        kind = torch.multinomial(torch.softmax(out.kind_logits.float().cpu(), -1), 1, generator=generator)[:, 0]
        target = torch.multinomial(torch.softmax(out.pass_logits.float().cpu(), -1), 1, generator=generator)[:, 0]
        carry = torch.multinomial(torch.softmax(out.carry_logits.float().cpu(), -1), 1, generator=generator)[:, 0]
        actions = []
        for b in range(len(valid)):
            if not valid[b]:
                actions.append(Action(kind="hold"))
                continue
            k = int(kind[b])
            if k == PASS:
                actions.append(Action(kind="pass", target=int(target[b])))
            elif k == CARRY:
                ang = int(carry[b]) * np.pi / 4
                sign = _sign(state, b)
                actions.append(Action(kind="carry", direction=(float(np.cos(ang)) * sign, float(np.sin(ang)) * sign)))
            else:
                actions.append(Action(kind={SHOOT: "shoot", CLEAR: "clear", HOLD: "hold"}[k]))
        return actions


def _sign(state, b: int) -> int:
    team = int(state.holder[b] >= 11)
    d = state.attack_dir
    return d if team == 0 else -d


def state_tokens(state) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Policy inputs for every world of a kickoff State: tokens [B, 23, F], context [B, G], valid [B] (someone in
    control). Worlds without a holder get the tokens of holder row 0 and are marked invalid."""
    S = np.asarray(state.S, dtype=np.float64)
    B = S.shape[0]
    holder = np.asarray(state.holder).astype(np.int64)
    valid = holder >= 0
    h = np.where(valid, holder, 0)
    poss = (h >= 11).astype(np.int64)
    sign = np.where(poss == 0, state.attack_dir, -state.attack_dir)
    roles = np.tile(np.r_[KICKOFF_ROLE, KICKOFF_ROLE], (B, 1))
    tok = tokens_from_arrays(S[:, :, 0:2], S[:, :, 2:4], roles, h, poss, sign)
    score = np.asarray(state.score, dtype=np.float64)
    diff = np.where(poss == 0, score[:, 0] - score[:, 1], score[:, 1] - score[:, 0])
    ctx = context(diff, np.full(B, state.t_ms / 5_400_000.0), np.full(B, float(state.period)), (poss == 0).astype(float))
    return tok.astype(np.float32), ctx, valid
