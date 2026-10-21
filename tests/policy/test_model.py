"""DecisionPolicy (T-028): about 4.9M parameters (within 10%), forward on [200, 23, 16] on mps, pointer masking,
sampling from a kickoff State, and a loss that is finite with the holder slot masked."""

import numpy as np
import pytest
import torch

from policy.data import F, G
from policy.model import DecisionPolicy, state_tokens
from policy.train import masked_cross_entropy


def test_parameter_count():
    n = DecisionPolicy().n_params()
    print(f"\nparameters: {n:,}")
    assert abs(n - 4.9e6) <= 0.1 * 4.9e6


@pytest.mark.skipif(not torch.backends.mps.is_available(), reason="needs Apple GPU")
def test_forward_on_mps():
    model = DecisionPolicy().to("mps").eval()
    tokens = torch.randn(200, 23, F, device="mps")
    tokens[:, :, 5] = 0
    tokens[torch.arange(200), torch.randint(0, 11, (200,)), 5] = 1
    with torch.no_grad():
        out = model(tokens, torch.randn(200, G, device="mps"))
    assert out.kind_logits.shape == (200, 5) and out.pass_logits.shape == (200, 11) and out.carry_logits.shape == (200, 8)
    holder = tokens[:, :11, 5].argmax(1)
    assert torch.isinf(out.pass_logits[torch.arange(200), holder]).all()


def test_masked_loss_ignores_holder_slot():
    logits = torch.tensor([[float("-inf"), 2.0, 0.0]])
    loss = masked_cross_entropy(logits, torch.tensor([1]), smoothing=0.05)
    assert torch.isfinite(loss) and loss < 0.3


def test_act_from_kickoff_state():
    from kickoff import Engine, League
    eng = Engine(League.load("data/league"), "verdant", "ironvale", seed=4242, batch=4)
    for _ in range(700):
        eng.step()
    st = eng.state()
    tok, ctx, valid = state_tokens(st)
    assert tok.shape == (4, 23, F) and ctx.shape == (4, G)
    actions = DecisionPolicy().eval().act(st, torch.Generator().manual_seed(1))
    assert len(actions) == 4
    assert all(a.kind in ("pass", "carry", "shoot", "clear", "hold") for a in actions)
    assert all(a.target is None or 0 <= a.target <= 10 for a in actions)
    assert not np.isnan(tok).any()
