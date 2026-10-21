"""Policy evaluation and the day-4 gate (TECH_PLAN 1.6 "Evaluation and gates", T-037).

    python -m policy.evaluate --ckpt packages/policy/artifacts/policy_v1.pt --test data/grf/dataset/test.npz --n-rollouts 20

Metrics, each with its baseline:
  top-1 kind accuracy (test split)            >= 0.45     baseline: majority class
  top-3 kind+target accuracy (test split)     >= 0.80     baseline: "pass to the nearest free team-mate" (top 3)
  4 s ball FDE on rollouts                    <= velocity extrapolation of the ball over 4 s
  teleports (player speed > 12 m/s)           == 0
  shape collapse (team hull area -50% in 8 s) <= 5% of rollouts
  offside calls per rollout                   <= 0.2
Rollouts: 20 held-out states (evaluation seeds 1-20, the first pass after 30:00), B = 50 worlds, 8 s, decision-only,
compared with scripted_v1 from the same states. The 4 s FDE uses the world-mean ball position against the ball in the
real match 4 s later. Writes artifacts/metrics.json and artifacts/gate.json ({"engine": "policy_v1" | "scripted_v1",
"reasons": [...]}) and docs/evidence/policy_gate_day4.md with 20 PNG strips in docs/evidence/policy_clips/.
Thresholds are never edited here; a failed gate means scripted_v1 serves every cached counterfactual (1.6 fallback).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

from .config import ARTIFACTS, ROOT, default_device
from .data import PASS, PITCH_L, PITCH_W
from .model import DecisionPolicy

GATES = {"top1_kind_accuracy": (">=", 0.45), "top3_kind_target_accuracy": (">=", 0.80),
         "fde_4s_m": ("<=baseline", None), "teleports": ("==", 0), "shape_collapse_rate": ("<=", 0.05),
         "offside_per_rollout": ("<=", 0.2)}
EVIDENCE = ROOT / "docs" / "evidence"
CORPUS = ROOT / "data" / "matches" / "corpus"


@dataclass
class EvalReport:
    gates: dict
    baselines: dict
    engine: str
    reasons: list


def load_model(ckpt: Path, device: str) -> DecisionPolicy:
    state = torch.load(ckpt, map_location="cpu", weights_only=False)
    model = DecisionPolicy(dropout=0.0)
    model.load_state_dict(state["model"])
    return model.to(device).eval()


@torch.no_grad()
def offline_metrics(model: DecisionPolicy, test: Path, device: str, max_samples: int = 300_000) -> tuple[dict, dict]:
    with np.load(test) as z:
        d = {k: z[k] for k in ("tokens", "ctx", "kind", "pass_target")}
    n = len(d["kind"])
    if n > max_samples:
        idx = np.sort(np.random.default_rng(0).choice(n, max_samples, replace=False))
        d = {k: v[idx] for k, v in d.items()}
        n = max_samples
    top1 = top3 = base3 = 0
    for a in range(0, n, 2048):
        sl = slice(a, min(a + 2048, n))
        tok = torch.from_numpy(d["tokens"][sl].astype(np.float32)).to(device)
        out = model(tok, torch.from_numpy(d["ctx"][sl].astype(np.float32)).to(device))
        pk = torch.softmax(out.kind_logits.float(), -1).cpu().numpy()
        pt = torch.softmax(out.pass_logits.float(), -1).cpu().numpy()
        kind, tgt = d["kind"][sl].astype(int), d["pass_target"][sl].astype(int)
        top1 += int((pk.argmax(1) == kind).sum())
        joint = np.concatenate([pk[:, PASS:PASS + 1] * pt, pk[:, 1:]], axis=1)      # 11 passes, carry, shoot, clear, hold
        truth = np.where(kind == PASS, tgt, 10 + kind)
        top = np.argsort(-joint, axis=1)[:, :3]
        top3 += int((top == truth[:, None]).any(axis=1).sum())
        base3 += int(_nearest_free_hits(d["tokens"][sl].astype(np.float32), truth).sum())
    majority = float(np.bincount(d["kind"].astype(int), minlength=5).max() / n)
    return ({"top1_kind_accuracy": top1 / n, "top3_kind_target_accuracy": top3 / n},
            {"top1_kind_accuracy": majority, "top3_kind_target_accuracy": base3 / n, "test_samples": n})


def _nearest_free_hits(tok: np.ndarray, truth: np.ndarray) -> np.ndarray:
    """Baseline top 3: passes to the three nearest team-mates with no opponent within 3 m."""
    x, y = tok[..., 0] * PITCH_L, tok[..., 1] * PITCH_W
    holder = tok[:, :11, 5].argmax(axis=1)
    n = np.arange(len(tok))
    d = np.hypot(x[:, :11] - x[n, holder][:, None], y[:, :11] - y[n, holder][:, None])
    marked = np.hypot(x[:, :11, None] - x[:, None, 11:22], y[:, :11, None] - y[:, None, 11:22]).min(axis=2) < 3.0
    d = np.where(marked, d + 1e3, d)
    d[n, holder] = np.inf
    top = np.argsort(d, axis=1)[:, :3]
    return (top == truth[:, None]).any(axis=1)


def _hull_area(pts: np.ndarray) -> float:
    from scipy.spatial import ConvexHull
    try:
        return float(ConvexHull(pts).volume)
    except Exception:
        return 0.0


def eval_states(n: int) -> list[tuple[int, int]]:
    """(seed, decision t_ms) for evaluation seeds 1..n: the first pass after 30:00."""
    out = []
    for seed in range(1, n + 1):
        lines = (CORPUS / str(seed) / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ev = next(json.loads(line) for line in lines if '"type":"pass"' in line and json.loads(line)["t_ms"] > 1_800_000)
        out.append((seed, ev["t_ms"] - 100))
    return out


def rollout_metrics(model: DecisionPolicy, n_rollouts: int, worlds: int = 50) -> tuple[dict, dict, list]:
    """Policy and scripted rollouts from held-out states; returns (policy metrics, scripted metrics, clips)."""
    from physics.window import TrackingWindow
    from rollout import MatchRef
    from rollout.policy_engine import policy_branch

    res = {"policy": {"fde": [], "fde_vel": [], "teleport": 0, "collapse": [], "offside": []},
           "scripted": {"fde": [], "fde_vel": [], "teleport": 0, "collapse": [], "offside": []}}
    clips = []
    for seed, t in eval_states(n_rollouts):
        match = MatchRef(seed, match_dir=CORPUS / str(seed))
        src = match.state_at(t).source
        real = TrackingWindow.load(CORPUS / str(seed), t, t + 4100)
        truth = real.S[-1, 22, 0:2].astype(np.float64)
        ball0, vel0 = src.S[0, 22, 0:2].astype(np.float64), src.S[0, 22, 2:4].astype(np.float64)
        vel_pred = np.clip(ball0 + 4.0 * vel0, [0, 0], [PITCH_L, PITCH_W])
        for name in ("policy", "scripted"):
            eng = (policy_branch(src, worlds, None, seed=seed, decide_now=True, model=model) if name == "policy"
                   else src.branch(src.t_ms, worlds, None, seed=seed, decide_now=True))
            off0 = _offsides(eng)
            frames = [eng.S.copy()]
            for step in range(1, 81):
                eng.step()
                if step % 10 == 0:
                    frames.append(eng.S.copy())
            F_ = np.stack(frames, axis=1)                                   # [W, 9, 23, 6]
            r = res[name]
            r["fde"].append(float(np.hypot(*(F_[:, 4, 22, 0:2].mean(axis=0) - truth))))
            r["fde_vel"].append(float(np.hypot(*(vel_pred - truth))))
            r["teleport"] += int((np.hypot(F_[:, :, :22, 2], F_[:, :, :22, 3]) > 12.0).sum())
            for team in (0, 1):
                rows = slice(11 * team + 1, 11 * team + 11)
                for w in range(worlds):
                    a0 = _hull_area(F_[w, 0, rows, 0:2])
                    amin = min(_hull_area(F_[w, k, rows, 0:2]) for k in range(1, 9))
                    r["collapse"].append(a0 > 0 and amin < 0.5 * a0)
            r["offside"].append((_offsides(eng) - off0) / worlds)
            if name == "policy":
                clips.append({"seed": seed, "t_ms": t, "frames": F_[0]})
    summary = {}
    for name, r in res.items():
        summary[name] = {"fde_4s_m": float(np.mean(r["fde"])), "fde_4s_velocity_baseline_m": float(np.mean(r["fde_vel"])),
                         "teleports": r["teleport"], "shape_collapse_rate": float(np.mean(r["collapse"])),
                         "offside_per_rollout": float(np.mean(r["offside"]))}
    return summary["policy"], summary["scripted"], clips


def _offsides(eng) -> int:
    return sum(1 for w in eng.worlds for e in list(w.log._open.values()) + [x[2] for x in w.log._ready]
               + w.log.released if e.type == "offside")


def render_clip(clip: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    F_ = clip["frames"]
    fig, axes = plt.subplots(1, F_.shape[0], figsize=(2.2 * F_.shape[0], 1.8), dpi=90)
    for k, ax in enumerate(axes):
        ax.set_xlim(0, PITCH_L)
        ax.set_ylim(0, PITCH_W)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_facecolor("#2f6b3a")
        ax.scatter(F_[k, 0:11, 0], F_[k, 0:11, 1], s=6, c="white")
        ax.scatter(F_[k, 11:22, 0], F_[k, 11:22, 1], s=6, c="#e8b04a")
        ax.scatter(F_[k, 22, 0], F_[k, 22, 1], s=8, c="black")
        ax.set_title(f"+{k} s", fontsize=7)
    fig.suptitle(f"seed {clip['seed']} from {clip['t_ms'] // 60000}:{clip['t_ms'] // 1000 % 60:02d}", fontsize=8)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def evaluate(ckpt: Path, test: Path, n_rollouts: int = 20, device: str | None = None) -> EvalReport:
    device = device or default_device()
    model = load_model(Path(ckpt), device)
    offline, off_base = offline_metrics(model, Path(test), device)
    pol, scr, clips = rollout_metrics(model, n_rollouts)
    values = {**offline, **{k: pol[k] for k in ("fde_4s_m", "teleports", "shape_collapse_rate", "offside_per_rollout")}}
    baselines = {"top1_kind_accuracy": off_base["top1_kind_accuracy"],
                 "top3_kind_target_accuracy": off_base["top3_kind_target_accuracy"],
                 "fde_4s_m": pol["fde_4s_velocity_baseline_m"], "teleports": scr["teleports"],
                 "shape_collapse_rate": scr["shape_collapse_rate"], "offside_per_rollout": scr["offside_per_rollout"]}
    gates, reasons = {}, []
    for name, (op, thr) in GATES.items():
        v = values[name]
        if op == ">=":
            ok = v >= thr
        elif op == "<=":
            ok = v <= thr
        elif op == "==":
            ok = v == thr
        else:
            thr, ok = baselines[name], v <= baselines[name]
        gates[name] = {"value": round(float(v), 4), "threshold": thr, "op": op.replace("baseline", ""),
                       "baseline": round(float(baselines[name]), 4), "passed": bool(ok)}
        if not ok:
            reasons.append(f"{name} {v:.4f} misses {op.replace('baseline', '')} {thr}")
    engine = "policy_v1" if not reasons else "scripted_v1"
    metrics = {"checkpoint": str(Path(ckpt).name), "device": device, "gates": gates, "scripted_rollouts": scr,
               "policy_rollouts": pol, "test_samples": off_base["test_samples"], "n_rollouts": n_rollouts,
               "worlds_per_rollout": 50, "horizon_s": 8}
    ARTIFACTS.mkdir(exist_ok=True)
    (ARTIFACTS / "metrics.json").write_text(json.dumps(metrics, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (ARTIFACTS / "gate.json").write_text(json.dumps({"engine": engine, "reasons": reasons or ["all 1.6 gates passed"]},
                                                    indent=1) + "\n", encoding="utf-8")
    for i, clip in enumerate(clips):
        render_clip(clip, EVIDENCE / "policy_clips" / f"clip_{i + 1:02d}_seed{clip['seed']}.png")
    _write_note(metrics, engine, reasons)
    return EvalReport(gates=gates, baselines=baselines, engine=engine, reasons=reasons)


def _write_note(metrics: dict, engine: str, reasons: list) -> None:
    rows = "\n".join(f"| {k} | {g['value']} | {g['op']} {g['threshold']} | {g['baseline']} | "
                     f"{'pass' if g['passed'] else 'FAIL'} |" for k, g in metrics["gates"].items())
    text = f"""# Policy gate, day 4 (T-037)

Checkpoint `{metrics['checkpoint']}` on `{metrics['device']}`; offline metrics on {metrics['test_samples']:,} test
samples (split by game, seed 4242); rollout metrics on {metrics['n_rollouts']} held-out states (evaluation seeds 1-20,
first pass after 30:00), 50 worlds x 8 s each, decision-only, with scripted_v1 from the same states as baseline.

| Metric | Value | Threshold | Baseline | Result |
|---|---|---|---|---|
{rows}

**Decision: `{engine}`** serves every cached counterfactual. {'; '.join(reasons) if reasons else 'Every gate passed.'}

Clip review: 20 PNG strips (1 frame per second, world 0) in `docs/evidence/policy_clips/`. Generated by
`python -m policy.evaluate`; thresholds come from TECH_PLAN 1.6 and are not edited.
"""
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "policy_gate_day4.md").write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m policy.evaluate")
    ap.add_argument("--ckpt", type=Path, default=ARTIFACTS / "policy_v1.pt")
    ap.add_argument("--test", type=Path, default=ROOT / "data" / "grf" / "dataset" / "test.npz")
    ap.add_argument("--n-rollouts", type=int, default=20)
    ap.add_argument("--device", default=None)
    args = ap.parse_args(argv)
    rep = evaluate(args.ckpt, args.test, args.n_rollouts, args.device)
    print(json.dumps({"engine": rep.engine, "reasons": rep.reasons, "gates": rep.gates}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
