"""Auto-events: a hand-built positive and negative case per detector; golden-match counts in [1, 40]."""

import json
import time
from pathlib import Path

import numpy as np
import pytest

from physics import TrackingWindow
from physics.auto_events import (
    KINDS,
    auto_events,
    big_chances,
    counter_attacks,
    line_breaks,
    overloads,
    pressing_traps,
    report,
    switches_of_play,
)

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "data" / "matches" / "4242"


def window(n: int = 200, t0: int = 600_000) -> TrackingWindow:
    """n frames from t0 in period 1 (home attacks +x): home spread at x 10-50, away at x 55-95, ball at centre."""
    S = np.zeros((n, 23, 6))
    S[:, 0:11, 0] = np.linspace(10, 50, 11)
    S[:, 11:22, 0] = np.linspace(95, 55, 11)
    S[:, :22, 1] = np.tile(np.linspace(5, 63, 11), 2)
    S[:, 22, 0:2] = [52.5, 34.0]
    return TrackingWindow(t_ms=t0 + 100 * np.arange(n), period=np.ones(n, dtype=np.int8), S=S,
                          ball_z=np.full(n, 0.11), holder=np.full(n, 5, dtype=np.int16),
                          possession=np.zeros(n, dtype=np.int8), player_ids=np.array([f"p_{i:03d}" for i in range(22)]))


def ev(i: int, type_: str, t: int, team: str = "home", player: str = "p_005", loc=(50.0, 34.0), end=None,
       outcome: str = "complete", **attrs) -> dict:
    return {"id": f"e_{i:04d}", "t_ms": t, "period": 1, "type": type_, "team": team, "player": player,
            "location": list(loc), "end_location": None if end is None else list(end), "outcome": outcome,
            "attrs": attrs, "related_event_ids": [], "match_id": "m_test"}


def test_big_chance():
    w = window()
    hit = ev(1, "shot", 605_000, loc=(95, 34), outcome="saved", xg=0.42)
    miss = ev(2, "shot", 606_000, loc=(80, 30), outcome="off_target", xg=0.08)
    found = big_chances(w, [hit, miss])
    assert [a.related_event_ids for a in found] == [["e_0001"]] and found[0].value == 0.42


def test_line_break():
    w = window()
    w.S[:, 12:22, 0] = np.minimum(w.S[:, 12:22, 0], 70.0)          # away outfield line at x = 70
    through = ev(1, "pass", 605_000, loc=(50, 34), end=(82, 30), recipient="p_009")
    short = ev(2, "pass", 607_000, loc=(50, 34), end=(66, 30), recipient="p_009")
    assert [a.related_event_ids[0] for a in line_breaks(w, [through, short])] == ["e_0001"]


def test_switch_of_play():
    w = window()
    wide = ev(1, "pass", 605_000, loc=(60, 4), end=(62, 50), recipient="p_010")
    landed = ev(2, "carry", 607_000, player="p_010", loc=(62, 50))
    narrow = ev(3, "pass", 608_000, loc=(60, 20), end=(62, 40), recipient="p_008")
    slow = ev(4, "pass", 610_000, loc=(60, 4), end=(62, 50), recipient="p_007")
    late = ev(5, "carry", 614_000, player="p_007", loc=(62, 50))
    found = switches_of_play(w, [wide, landed, narrow, slow, late])
    assert [a.related_event_ids[0] for a in found] == ["e_0001"]


def test_pressing_trap():
    w = window()
    press = [ev(1, "pressure", 603_000, player="p_008"), ev(2, "pressure", 604_000, player="p_009")]
    won_high = ev(3, "possession_change", 606_000, player="p_009", loc=(80, 40))
    lone = [ev(4, "pressure", 612_000, player="p_008")]
    won_lone = ev(5, "possession_change", 614_000, player="p_008", loc=(80, 40))
    won_deep = ev(6, "possession_change", 616_500, player="p_009", loc=(40, 40))
    deep_press = [ev(7, "pressure", 615_000, player="p_008"), ev(8, "pressure", 616_000, player="p_009")]
    found = pressing_traps(w, press + [won_high] + lone + [won_lone] + deep_press + [won_deep])
    assert [a.t_ms for a in found] == [606_000]


def test_counter_attack():
    w = window(300)
    t = np.arange(300)
    w.S[:, 22, 0] = np.where(t < 20, 30.0, np.minimum(30.0 + (t - 20) * 0.8, 100.0))   # 30 m to 100 m in ~9 s
    fast = counter_attacks(w, [ev(1, "possession_change", 602_000, loc=(30, 34))])
    assert len(fast) == 1 and fast[0].team == "home"
    w2 = window(300)
    w2.S[:, 22, 0] = np.where(t < 20, 30.0, np.minimum(30.0 + (t - 20) * 0.3, 100.0))  # too slow
    assert counter_attacks(w2, [ev(1, "possession_change", 602_000, loc=(30, 34))]) == []
    w3 = window(300)
    w3.S[:, 22, 0] = w.S[:, 22, 0]
    w3.possession[60:] = 1                                                             # lost it on the way
    assert counter_attacks(w3, [ev(1, "possession_change", 602_000, loc=(30, 34))]) == []


def test_overload():
    w = window(20)
    w.S[:, 22, 0:2] = [80.0, 10.0]                                 # ball on home's right flank, attacking half
    w.S[:, 7:11, 0], w.S[:, 7:11, 1] = [70, 75, 82, 88], [6, 12, 16, 20]
    w.S[:, 11:22, 1] = 50.0                                        # defenders away from that channel...
    w.S[:, 13, 0:2] = [85.0, 12.0]                                 # ...except one
    found = overloads(w, [])
    assert len(found) == 1 and found[0].value == "overload_right" and len(found[0].players) == 4
    w.S[:, 14:16, 0:2] = [[78.0, 8.0], [72.0, 18.0]]               # now 4 v 3
    assert overloads(w, []) == []


@pytest.fixture(scope="module")
def golden_report():
    return report(GOLDEN)


def test_golden_counts_in_range_and_written(golden_report):
    counts = golden_report["counts"]
    assert set(counts) == set(KINDS)
    assert all(1 <= counts[k] <= 40 for k in KINDS), counts
    written = json.loads((GOLDEN / "auto_events_report.json").read_text())
    assert written["counts"] == counts


def test_inside_physics_budget():
    w = TrackingWindow.load(GOLDEN)
    events = [json.loads(line) for line in (GOLDEN / "events.jsonl").read_text().splitlines()]
    times = []
    for t in range(1_800_000, 1_815_000, 100):
        last = w.slice(t - 15_000, t)
        started = time.process_time()
        auto_events(last, [e for e in events if t - 15_000 <= e["t_ms"] <= t])
        times.append((time.process_time() - started) * 1000)
    p95 = float(np.percentile(times, 95))
    print(f"\nauto_events on a 15 s window: p95 {p95:.2f} ms CPU")
    assert p95 < 10.0          # leaves room for the 3.5 ms of the physics functions inside the 15 ms frame budget
