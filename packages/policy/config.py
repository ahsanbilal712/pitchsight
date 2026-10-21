"""Training configuration for the on-ball decision policy (TECH_PLAN 1.6 "Model" and "Training")."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = Path(__file__).resolve().parent / "artifacts"


def default_device() -> str:
    """WHYLINE_DEVICE, else mps when available, else cpu."""
    env = os.environ.get("WHYLINE_DEVICE")
    if env:
        return env
    import torch
    return "mps" if torch.backends.mps.is_available() else "cpu"


@dataclass
class TrainConfig:
    data_dir: Path = ROOT / "data" / "grf" / "dataset"
    out_dir: Path = ARTIFACTS
    name: str = "policy_v1"
    d_model: int = 256
    n_layers: int = 6
    n_heads: int = 8
    d_ff: int = 1024
    dropout: float = 0.1
    lr: float = 3e-4
    weight_decay: float = 0.01
    warmup_steps: int = 1000
    batch_size: int = 256
    label_smoothing: float = 0.05
    epochs: int = 8
    seed: int = 4242
    device: str = field(default_factory=default_device)
    max_steps_per_epoch: int | None = None      # smoke runs
    max_minutes: float | None = None            # stop (and checkpoint) after this much wall time
    val_max_samples: int = 200_000
    log_every: int = 200

    def to_json(self) -> dict:
        return {k: (str(v) if isinstance(v, Path) else v) for k, v in asdict(self).items()}
