"""Train the DecisionPolicy.

    python -m policy.train [--epochs 8] [--smoke-minutes 10] [--name policy_v1]

AdamW 3e-4 with a 1,000-step linear warm-up and cosine decay, batch 256, label smoothing 0.05; loss =
CE(kind) + CE(pass target, pass samples only) + CE(carry direction, carry samples only). One checkpoint per epoch
(artifacts/<name>_epN.pt) holding model, optimiser, scheduler and generator state; an interrupted run resumes from
the last epoch file. The best epoch by validation loss is copied to <name>.pt. Every line of
artifacts/train_log.jsonl is one JSON record (step losses and per-epoch validation). Weights (*.pt) are git-ignored;
the log and metrics are committed.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F_

from .config import TrainConfig
from .data import CARRY, PASS
from .model import DecisionPolicy


@dataclass
class TrainReport:
    epochs_done: int
    best_epoch: int
    best_val_loss: float
    params: int
    samples_per_s: float


def load_split(path: Path, max_samples: int | None = None, seed: int = 0) -> dict[str, np.ndarray]:
    with np.load(path) as z:
        data = {k: z[k] for k in ("tokens", "ctx", "kind", "pass_target", "carry_dir")}
    if max_samples and len(data["kind"]) > max_samples:
        idx = np.sort(np.random.default_rng(seed).choice(len(data["kind"]), max_samples, replace=False))
        data = {k: v[idx] for k, v in data.items()}
    return data


def batch_tensors(data: dict[str, np.ndarray], idx: np.ndarray, device: str) -> tuple[torch.Tensor, ...]:
    return (torch.from_numpy(data["tokens"][idx].astype(np.float32)).to(device),
            torch.from_numpy(data["ctx"][idx].astype(np.float32)).to(device),
            torch.from_numpy(data["kind"][idx].astype(np.int64)).to(device),
            torch.from_numpy(data["pass_target"][idx].astype(np.int64)).to(device),
            torch.from_numpy(data["carry_dir"][idx].astype(np.int64)).to(device))


def masked_cross_entropy(logits: torch.Tensor, target: torch.Tensor, smoothing: float) -> torch.Tensor:
    """Cross-entropy over the pass pointer with label smoothing spread over the valid targets only (the holder's own
    slot is -inf and gets no smoothing mass, or the logits would grow without bound to push it down)."""
    invalid = torch.isinf(logits)
    logp = F_.log_softmax(logits, dim=-1)
    nll = -logp.gather(1, target[:, None])[:, 0]
    smooth = -logp.masked_fill(invalid, 0.0).sum(dim=1) / (~invalid).sum(dim=1)
    return ((1.0 - smoothing) * nll + smoothing * smooth).mean()


def losses(model: DecisionPolicy, batch, smoothing: float) -> tuple[torch.Tensor, dict[str, float]]:
    tokens, ctx, kind, target, carry = batch
    out = model(tokens, ctx)
    l_kind = F_.cross_entropy(out.kind_logits, kind, label_smoothing=smoothing)
    total = l_kind
    parts = {"kind": float(l_kind.detach())}
    # a pass whose target is the masked holder slot (a passer regaining his own pass) carries no pointer label
    is_pass = (kind == PASS) & torch.isfinite(out.pass_logits.gather(1, target.clamp(min=0)[:, None])[:, 0])
    if is_pass.any():
        l_pass = masked_cross_entropy(out.pass_logits[is_pass], target[is_pass], smoothing)
        total = total + l_pass
        parts["pass"] = float(l_pass.detach())
    is_carry = kind == CARRY
    if is_carry.any():
        l_carry = F_.cross_entropy(out.carry_logits[is_carry], carry[is_carry], label_smoothing=smoothing)
        total = total + l_carry
        parts["carry"] = float(l_carry.detach())
    return total, parts


@torch.no_grad()
def evaluate_loss(model: DecisionPolicy, data: dict[str, np.ndarray], cfg: TrainConfig) -> dict[str, float]:
    model.eval()
    n = len(data["kind"])
    tot, acc, count = 0.0, 0, 0
    for a in range(0, n, 1024):
        idx = np.arange(a, min(a + 1024, n))
        batch = batch_tensors(data, idx, cfg.device)
        loss, _ = losses(model, batch, 0.0)
        tot += float(loss) * idx.size
        out = model(batch[0], batch[1])
        acc += int((out.kind_logits.argmax(1) == batch[2]).sum())
        count += idx.size
    model.train()
    return {"val_loss": tot / max(count, 1), "val_kind_acc": acc / max(count, 1)}


def _lr_lambda(cfg: TrainConfig, total_steps: int):
    def f(step: int) -> float:
        if step < cfg.warmup_steps:
            return (step + 1) / cfg.warmup_steps
        p = (step - cfg.warmup_steps) / max(1, total_steps - cfg.warmup_steps)
        return 0.5 * (1.0 + math.cos(math.pi * min(p, 1.0)))
    return f


def _log(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def train(cfg: TrainConfig) -> TrainReport:
    torch.manual_seed(cfg.seed)
    out = Path(cfg.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    log_path = out / "train_log.jsonl"
    print(f"loading {cfg.data_dir}", flush=True)
    train_data = load_split(Path(cfg.data_dir) / "train.npz")
    val_data = load_split(Path(cfg.data_dir) / "val.npz", cfg.val_max_samples, seed=cfg.seed)
    n = len(train_data["kind"])
    steps_per_epoch = n // cfg.batch_size
    if cfg.max_steps_per_epoch:
        steps_per_epoch = min(steps_per_epoch, cfg.max_steps_per_epoch)
    total_steps = steps_per_epoch * cfg.epochs
    model = DecisionPolicy(cfg.d_model, cfg.n_layers, cfg.n_heads, cfg.d_ff, cfg.dropout).to(cfg.device)
    opt = torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, _lr_lambda(cfg, total_steps))
    rng = np.random.default_rng(cfg.seed)
    start_epoch, best = 1, (0, float("inf"))
    done = sorted(out.glob(f"{cfg.name}_ep*.pt"), key=lambda p: int(p.stem.split("_ep")[-1]))
    if done:                                             # resume after the last finished epoch
        ck = torch.load(done[-1], map_location=cfg.device, weights_only=False)
        model.load_state_dict(ck["model"])
        opt.load_state_dict(ck["optimizer"])
        sched.load_state_dict(ck["scheduler"])
        rng.bit_generator.state = ck["rng"]
        start_epoch, best = ck["epoch"] + 1, tuple(ck["best"])
        _log(log_path, {"event": "resume", "from_epoch": ck["epoch"], "name": cfg.name})
    else:
        _log(log_path, {"event": "start", "name": cfg.name, "params": model.n_params(), "train_samples": n,
                        "val_samples": len(val_data["kind"]), "steps_per_epoch": steps_per_epoch,
                        "config": cfg.to_json()})
    started = time.perf_counter()
    seen = 0
    model.train()
    for epoch in range(start_epoch, cfg.epochs + 1):
        perm = rng.permutation(n)
        t0 = time.perf_counter()
        for step in range(steps_per_epoch):
            idx = np.sort(perm[step * cfg.batch_size:(step + 1) * cfg.batch_size])
            loss, parts = losses(model, batch_tensors(train_data, idx, cfg.device), cfg.label_smoothing)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            seen += idx.size
            if step % cfg.log_every == 0:
                rate = seen / (time.perf_counter() - started)
                _log(log_path, {"event": "step", "epoch": epoch, "step": step, "loss": round(float(loss.detach()), 4),
                                **{f"loss_{k}": round(v, 4) for k, v in parts.items()}, "lr": sched.get_last_lr()[0],
                                "samples_per_s": round(rate, 1)})
                print(f"epoch {epoch} step {step}/{steps_per_epoch} loss {float(loss.detach()):.4f} {rate:.0f} samples/s",
                      flush=True)
            if cfg.max_minutes and time.perf_counter() - started > cfg.max_minutes * 60:
                break
        val = evaluate_loss(model, val_data, cfg)
        if val["val_loss"] < best[1]:
            best = (epoch, val["val_loss"])
        record = {"event": "epoch", "epoch": epoch, **{k: round(v, 5) for k, v in val.items()},
                  "epoch_minutes": round((time.perf_counter() - t0) / 60, 2), "best_epoch": best[0]}
        _log(log_path, record)
        print(json.dumps(record), flush=True)
        ck_path = out / f"{cfg.name}_ep{epoch}.pt"
        torch.save({"model": model.state_dict(), "optimizer": opt.state_dict(), "scheduler": sched.state_dict(),
                    "rng": rng.bit_generator.state, "epoch": epoch, "best": list(best), "val": val,
                    "config": cfg.to_json()}, ck_path)
        if best[0] == epoch:
            shutil.copyfile(ck_path, out / f"{cfg.name}.pt")
        if cfg.max_minutes and time.perf_counter() - started > cfg.max_minutes * 60:
            break
    rate = seen / max(time.perf_counter() - started, 1e-9)
    return TrainReport(epochs_done=epoch, best_epoch=best[0], best_val_loss=best[1], params=model.n_params(),
                       samples_per_s=rate)


def revalidate(cfg: TrainConfig) -> dict:
    """Recompute the validation loss of every epoch checkpoint with the current loss code, copy the best to
    <name>.pt and log it (used after a run whose in-run validation could not pick a best epoch)."""
    out = Path(cfg.out_dir)
    val = load_split(Path(cfg.data_dir) / "val.npz", cfg.val_max_samples, seed=cfg.seed)
    scores = {}
    for ck_path in sorted(out.glob(f"{cfg.name}_ep*.pt"), key=lambda p: int(p.stem.split("_ep")[-1])):
        ck = torch.load(ck_path, map_location="cpu", weights_only=False)
        model = DecisionPolicy(cfg.d_model, cfg.n_layers, cfg.n_heads, cfg.d_ff, 0.0).to(cfg.device)
        model.load_state_dict(ck["model"])
        scores[ck["epoch"]] = evaluate_loss(model, val, cfg)
    best = min(scores, key=lambda e: scores[e]["val_loss"])
    shutil.copyfile(out / f"{cfg.name}_ep{best}.pt", out / f"{cfg.name}.pt")
    _log(out / "train_log.jsonl", {"event": "revalidate", "best_epoch": best,
                                   "epochs": {str(e): {k: round(v, 5) for k, v in s.items()} for e, s in scores.items()}})
    return {"best_epoch": best, "scores": scores}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m policy.train")
    ap.add_argument("--data", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--name", default="policy_v1")
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--smoke-minutes", type=float, default=None, help="short run: epochs of 1/4 the data, stop after N min")
    ap.add_argument("--device", default=None)
    ap.add_argument("--revalidate", action="store_true", help="score every epoch checkpoint, keep the best")
    args = ap.parse_args(argv)
    cfg = TrainConfig(name=args.name, epochs=args.epochs)
    if args.data:
        cfg.data_dir = args.data
    if args.out:
        cfg.out_dir = args.out
    if args.device:
        cfg.device = args.device
    if args.smoke_minutes:
        cfg.max_minutes = args.smoke_minutes
        cfg.max_steps_per_epoch = 600
        cfg.warmup_steps = 200
        cfg.val_max_samples = 50_000
        cfg.log_every = 100
    print(revalidate(cfg) if args.revalidate else train(cfg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
