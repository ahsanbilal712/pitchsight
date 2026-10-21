"""policy_v1 rollouts (T-036): byte-identical Futures on MPS twice and on MPS vs CPU; ungated checkpoints refused."""

import json

import pytest
import torch

from policy.config import ARTIFACTS
from policy.loader import PolicyNotGated, latest_checkpoint, load_policy
from policy.model import DecisionPolicy
from rollout import rollout

NO_CKPT = not list(ARTIFACTS.glob("policy_v1*.pt"))


@pytest.fixture
def ungated_ok(monkeypatch):
    monkeypatch.setenv("WHYLINE_ALLOW_UNGATED_POLICY", "1")


def _run(golden, decision_t, device, monkeypatch):
    monkeypatch.setenv("WHYLINE_DEVICE", device)
    return rollout(golden.state_at(decision_t), None, 200, 8, seed=9, engine="policy_v1", decide_now=True,
                   events=golden.events())


@pytest.mark.skipif(NO_CKPT, reason="needs a policy_v1 checkpoint (T-028)")
@pytest.mark.skipif(not torch.backends.mps.is_available(), reason="needs Apple GPU")
def test_mps_twice_and_mps_vs_cpu(golden, decision_t, ungated_ok, monkeypatch):
    a = _run(golden, decision_t, "mps", monkeypatch)
    b = _run(golden, decision_t, "mps", monkeypatch)
    c = _run(golden, decision_t, "cpu", monkeypatch)
    assert a.invalid_reason is None
    assert a.digest() == b.digest() == c.digest()


def test_ungated_checkpoint_is_refused(tmp_path, monkeypatch):
    monkeypatch.delenv("WHYLINE_ALLOW_UNGATED_POLICY", raising=False)
    torch.save({"model": DecisionPolicy().state_dict(), "config": {}}, tmp_path / "policy_v1.pt")
    (tmp_path / "metrics.json").write_text(json.dumps({"gates": {"top1_kind_accuracy": {"passed": False}}}))
    with pytest.raises(PolicyNotGated):
        load_policy(tmp_path / "policy_v1.pt", device="cpu", artifacts=tmp_path)
    monkeypatch.setenv("WHYLINE_ALLOW_UNGATED_POLICY", "1")
    assert load_policy(tmp_path / "policy_v1.pt", device="cpu", artifacts=tmp_path) is not None
    assert latest_checkpoint(tmp_path).name == "policy_v1.pt"
