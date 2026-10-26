"""policy_v1 budget: B=200, 8 s, decision-only <= 0.3 s on MPS and <= 1.2 s on CPU (config/budgets.yaml).
Branch + 80 steps, best of three warm runs, wall time (the GPU path cannot be measured as process CPU time). Run on an idle machine."""

import time
from pathlib import Path

import pytest
import torch
import yaml

from policy.config import ARTIFACTS
from policy.loader import load_policy
from rollout import rollout
from rollout.policy_engine import policy_branch

BUDGET = yaml.safe_load((Path(__file__).resolve().parents[2] / "config" / "budgets.yaml").read_text())
MS = BUDGET["latency_slo"]["counterfactual_ms"]

pytestmark = pytest.mark.skipif(not list(ARTIFACTS.glob("policy_v1*.pt")), reason="needs a policy_v1 checkpoint")


def _best(golden, decision_t, device, monkeypatch) -> float:
    """Branch + 80 steps (the decision-only rollout; valuation by the heads is the same for both engines)."""
    monkeypatch.setenv("WHYLINE_ALLOW_UNGATED_POLICY", "1")
    model = load_policy(device=device)
    src = golden.state_at(decision_t).source
    times = []
    for seed in (1, 2, 3, 4):
        t = time.perf_counter()
        eng = policy_branch(src, 200, None, seed=seed, decide_now=True, model=model)
        for _ in range(80):
            eng.step()
        times.append(time.perf_counter() - t)
        assert eng.policy_calls <= 20
    total = time.perf_counter()
    rollout(golden.state_at(decision_t), None, 200, 8, seed=5, engine="policy_v1", decide_now=True)
    print(f"\n{device}: futures only {min(times[1:]):.3f} s; whole rollout with head valuation "
          f"{time.perf_counter() - total:.3f} s")
    return min(times[1:])


@pytest.mark.skipif(not torch.backends.mps.is_available(), reason="needs Apple GPU")
def test_policy_200x8s_mps(golden, decision_t, monkeypatch):
    monkeypatch.setenv("WHYLINE_DEVICE", "mps")
    best = _best(golden, decision_t, "mps", monkeypatch)
    print(f"\npolicy_v1 B=200 x 8 s on mps: {best:.3f} s")
    assert best <= MS["policy_200x8s_decision_only_mps"] / 1000


def test_policy_200x8s_cpu(golden, decision_t, monkeypatch):
    monkeypatch.setenv("WHYLINE_DEVICE", "cpu")
    best = _best(golden, decision_t, "cpu", monkeypatch)
    print(f"\npolicy_v1 B=200 x 8 s on cpu: {best:.3f} s")
    assert best <= MS["policy_200x8s_decision_only_cpu"] / 1000
