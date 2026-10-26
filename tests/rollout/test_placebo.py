"""Placebo: forcing the action the player actually took reproduces the baseline within its 95% interval."""

import pytest

from rollout import placebo

CLOCKS = ("00:01", "05:10", "10:05", "15:10", "20:04", "25:07", "30:03")


@pytest.fixture(scope="module")
def moments(golden):
    out = []
    for clock in CLOCKS:
        m, s = map(int, clock.split(":"))
        t = (m * 60 + s) * 1000
        ev = next(e for e in golden.events() if e["type"] in ("pass", "shot") and e["t_ms"] >= t)
        out.append(ev["t_ms"] - 100)
    return out


def test_forced_actual_action_reproduces_baseline(golden, moments):
    results = [placebo(golden, t, n=200) for t in moments]
    for r in results:
        print(f"\n{r['t_ms']}: {r['actual']['kind']} support {r['support']} diff {r.get('diff_win_prob')} "
              f"half {r.get('half_width')} passed {r['passed']}")
    testable = [r for r in results if r["testable"]]
    assert len(testable) >= 5
    assert all(r["passed"] for r in testable)
