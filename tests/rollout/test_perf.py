"""Rollout budgets (T-016): B=200 x 900 steps (90 s) scripted <= 1.3 s warm on CPU (TECH_PLAN 1.4); the $50 plan's
200 x 60 s case <= 1.2 s (config/budgets.yaml scripted_200x60s_cpu). Measured as process CPU time, best of three,
so other work on the machine (corpus generation, other test runs) does not decide the number; wall time is printed."""

import time
from pathlib import Path

import yaml

BUDGETS = yaml.safe_load((Path(__file__).resolve().parents[2] / "config" / "budgets.yaml").read_text())


def _run(src, steps: int) -> tuple[float, float]:
    wall, cpu = time.perf_counter(), time.process_time()
    eng = src.branch(src.t_ms, 200, None, seed=1, decide_now=True)
    for _ in range(steps):
        eng.step()
    return time.process_time() - cpu, time.perf_counter() - wall


def _best(src, steps: int) -> tuple[float, float]:
    runs = [_run(src, steps) for _ in range(3)]
    return min(r[0] for r in runs), min(r[1] for r in runs)


def test_scripted_200_worlds_budgets(golden, decision_t):
    src = golden.state_at(decision_t).source
    _run(src, 50)                                                       # warm up
    cpu90, wall90 = _best(src, 900)
    cpu60, wall60 = _best(src, 600)
    print(f"\nB=200 x 90 s: {cpu90:.3f} s CPU ({wall90:.3f} s wall); B=200 x 60 s: {cpu60:.3f} s CPU ({wall60:.3f} s wall)")
    assert cpu90 <= 1.3
    assert cpu60 <= BUDGETS["latency_slo"]["counterfactual_ms"]["scripted_200x60s_cpu"] / 1000
