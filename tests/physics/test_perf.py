"""All physics functions for one 100 ms frame in < 15 ms on CPU (T-013, TECH_PLAN 1.4)."""

import json
import time
from pathlib import Path

import numpy as np
import pytest

from physics import StateMachine, TrackingWindow, chaos_index, indices, pitch_control, speeds

GOLDEN = Path(__file__).resolve().parents[2] / "data" / "matches" / "4242"
BUDGET_MS = 15.0


@pytest.fixture(scope="module")
def golden():
    window = TrackingWindow.load(GOLDEN)
    events = [json.loads(line) for line in (GOLDEN / "events.jsonl").read_text().splitlines()]
    return window, events


def _pass(window, events) -> list[float]:
    sm = StateMachine()
    times = []
    for t in range(1_800_000, 1_830_000, 100):                 # 300 consecutive frames around 30:00
        started = time.process_time()
        frame = window.frame_at(t)
        pc = pitch_control(frame.S)
        last60 = window.slice(t - 60_000, t)
        ix = indices(last60, [e for e in events if t - 60_000 <= e["t_ms"] <= t])
        chaos = chaos_index(pc, ix["turnovers_60s"], ix["transition_share"])
        speeds(window.slice(t - 1_000, t))
        sm.update(chaos, t)
        times.append((time.process_time() - started) * 1000)
    return times


def test_one_frame_under_budget(golden):
    # CPU time of this process, best of three passes, so a busy machine (corpus workers) does not decide it
    window, events = golden
    p50, p95 = min((tuple(np.percentile(_pass(window, events), [50, 95])) for _ in range(3)), key=lambda p: p[1])
    print(f"\nphysics per frame: p50 {p50:.2f} ms, p95 {p95:.2f} ms (budget {BUDGET_MS} ms)")
    assert p95 < BUDGET_MS


def test_indices_keys_and_ranges(golden):
    window, events = golden
    ix = indices(window.slice(1_740_000, 1_800_000), events)
    for key in ("control_home", "control_away", "pressure_home", "pressure_away", "tempo", "turnover_rate"):
        assert key in ix and np.isfinite(ix[key])
    assert abs(ix["control_home"] + ix["control_away"] - 1.0) < 1e-9
    assert 0 <= ix["chaos"] <= 100 and 0 <= ix["transition_share"] <= 1


def test_speeds_report(golden):
    window, _ = golden
    report = speeds(window.slice(0, 600_000))
    assert report.sprints and all(kmh >= 25.0 for _, kmh, _ in report.sprints)
    assert all(p.startswith("p_") for p, _, _ in report.sprints)
    assert report.shot_kmh is None or report.shot_kmh >= 54.0
