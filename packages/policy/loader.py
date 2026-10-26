"""Load a trained DecisionPolicy for rollouts, refusing ungated checkpoints.

A checkpoint loads only when artifacts/metrics.json (written by policy.evaluate) says every 1.6 gate passed,
unless WHYLINE_ALLOW_UNGATED_POLICY=1 (used for timing tests before the gate exists).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import torch

from .config import ARTIFACTS, default_device
from .model import DecisionPolicy

_CACHE: dict[tuple[str, str], DecisionPolicy] = {}


class PolicyNotGated(RuntimeError):
    pass


def gate_passed(metrics_path: Path) -> tuple[bool, str]:
    if not metrics_path.exists():
        return False, f"{metrics_path} is missing (run python -m policy.evaluate)"
    m = json.loads(metrics_path.read_text(encoding="utf-8"))
    failed = [k for k, g in m.get("gates", {}).items() if not g.get("passed")]
    if not m.get("gates"):
        return False, "metrics.json has no gates"
    return (not failed), ("failed gates: " + ", ".join(failed)) if failed else "all gates passed"


def latest_checkpoint(artifacts: Path = ARTIFACTS, name: str = "policy_v1") -> Path:
    best = artifacts / f"{name}.pt"
    if best.exists():
        return best
    eps = sorted(artifacts.glob(f"{name}_ep*.pt"), key=lambda p: int(p.stem.split("_ep")[-1]))
    if not eps:
        raise FileNotFoundError(f"no {name} checkpoint in {artifacts}")
    return eps[-1]


def load_policy(ckpt: Path | None = None, device: str | None = None, artifacts: Path = ARTIFACTS) -> DecisionPolicy:
    """The policy in eval mode on `device` (WHYLINE_DEVICE, else mps when available). Raises PolicyNotGated when
    metrics.json fails the gates and WHYLINE_ALLOW_UNGATED_POLICY is not 1."""
    ok, why = gate_passed(artifacts / "metrics.json")
    if not ok and os.environ.get("WHYLINE_ALLOW_UNGATED_POLICY") != "1":
        raise PolicyNotGated(f"refusing to load an ungated policy: {why}")
    ckpt = Path(ckpt) if ckpt else latest_checkpoint(artifacts)
    device = device or default_device()
    key = (str(ckpt.resolve()), device)
    if key not in _CACHE:
        state = torch.load(ckpt, map_location="cpu", weights_only=False)
        cfg = state.get("config", {})
        model = DecisionPolicy(cfg.get("d_model", 256), cfg.get("n_layers", 6), cfg.get("n_heads", 8),
                               cfg.get("d_ff", 1024), 0.0)
        model.load_state_dict(state["model"])
        if device == "cpu":                  # OMP_NUM_THREADS=1 is the process default (policy/__init__.py)
            torch.set_num_threads(int(os.environ.get("WHYLINE_TORCH_THREADS", max(1, (os.cpu_count() or 2) // 2))))
        _CACHE[key] = model.to(device).eval()
    return _CACHE[key]
