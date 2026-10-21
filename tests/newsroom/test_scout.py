"""Scout: exact TECH_PLAN 1.7 predicates, one message per branch, moments with every 1.3 field, 25-60 explained
moments on the golden match, < 50 ms per event (T-029)."""

import asyncio
import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest

from blackboard import SqliteBlackboard
from heads.models import GoalIn8sHead, HeadArtifactMissing
from newsroom import scout_rules as sr
from newsroom.executors.base import Deps
from newsroom.executors.stubs import StubCueBus, StubDirector
from newsroom.graph import build_workflow
from newsroom.worker import run_moment, start_message

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "data" / "matches" / "4242"
MOMENT_FIELDS = {"match_id", "t_ms", "clock", "kind", "leverage", "players", "team", "evidence_event_ids",
                 "hypotheses", "fast", "status"}


def arun(coro):
    """asyncio.run on a worker thread: Playwright's session-scoped sync API (tests/apps) keeps a loop running in
    the main thread, and asyncio.run refuses to start inside it."""
    with ThreadPoolExecutor(1) as pool:
        return pool.submit(asyncio.run, coro).result()


# ---------------------------------------------------------------- predicates, exactly as TECH_PLAN 1.7

@pytest.mark.parametrize("moment,expected", [
    ({"kind": "goal"}, True), ({"kind": "milestone"}, True),
    ({"kind": "big_chance", "xg": 0.30}, True), ({"kind": "big_chance", "xg": 0.299}, False),
    ({"kind": "player_tag", "kmh": sr.PLAYER_TAG_KMH}, True), ({"kind": "player_tag", "kmh": 33.9}, False),
    ({"kind": "decision", "leverage": 0.5}, False),
])
def test_is_fast(moment, expected):
    assert sr.is_fast(moment) is expected


@pytest.mark.parametrize("moment,expected", [
    ({"kind": "decision", "leverage": 0.04}, True), ({"kind": "decision", "leverage": 0.0399}, False),
    ({"kind": "decision", "leverage": -0.0}, False), ({"kind": "state_change", "leverage": None}, True),
    ({"kind": "goal", "leverage": None}, False),
])
def test_is_explained(moment, expected):
    assert sr.is_explained(moment) is expected


def test_is_panel_needs_006_and_enabled():
    assert sr.is_panel({"leverage": 0.06}, True) and not sr.is_panel({"leverage": 0.0599}, True)
    assert not sr.is_panel({"leverage": 0.5}, False)


def test_referee_and_recap():
    assert all(sr.is_referee({"kind": k}) for k in ("offside", "foul", "card"))
    assert not sr.is_referee({"kind": "goal"})
    assert sr.is_recap({"kind": "period_end"}) and not sr.is_recap({"kind": "goal"})


def test_branches_one_per_match():
    m = {"kind": "goal", "leverage": 0.07}
    assert sr.branches(m, panel_enabled=True) == ["fast", "explained", "panel"]
    assert sr.branches(m) == ["fast", "explained"]
    assert sr.branches({"kind": "foul", "leverage": 0.01}) == ["referee"]
    assert sr.branches({"kind": "decision", "leverage": 0.01}) == []


# ---------------------------------------------------------------- the executor

def test_scout_emits_one_message_per_branch(tmp_path):
    bb = SqliteBlackboard(tmp_path / "bb.sqlite")
    deps = Deps(bb=bb, panel_enabled=True)
    wf = build_workflow(deps, overrides={"director": StubDirector("director", deps),
                                         "cuebus": StubCueBus("cuebus", deps)})
    goal = {"moment_id": "mo_00003", "match_id": "m_4242", "t_ms": 600_000, "kind": "goal", "leverage": 0.07,
            "players": [], "team": "home", "evidence_event_ids": []}
    outputs = arun(run_moment(wf, start_message(goal)))["outputs"]
    paths = sorted(o["agent_path"][2] for o in outputs)
    assert paths == ["fast_line", "panel", "proposer"]
    assert [r["branch"] for r in bb.query("traces", executor="scout")] == ["fast", "explained", "panel"]
    quiet = {**goal, "moment_id": "mo_00004", "kind": "decision", "leverage": 0.01}
    assert arun(run_moment(wf, start_message(quiet)))["outputs"] == []
    assert bb.query("traces", executor="drop", moment_id="mo_00004")
    bb.close()


# ---------------------------------------------------------------- golden match

@pytest.fixture(scope="module")
def golden(tmp_path_factory):
    bb = SqliteBlackboard(tmp_path_factory.mktemp("scout") / "bb.sqlite")
    t0 = time.perf_counter()
    moments = sr.detect_match(GOLDEN, bb)
    return {"bb": bb, "moments": moments, "seconds": time.perf_counter() - t0}


def test_golden_moments_carry_every_field(golden):
    moments = golden["moments"]
    assert moments and all(MOMENT_FIELDS <= set(m) for m in moments)
    ids = [m["moment_id"] for m in moments]
    assert ids == [f"mo_{i:05d}" for i in range(1, len(ids) + 1)]
    assert [m["t_ms"] for m in moments] == sorted(m["t_ms"] for m in moments)
    assert golden["bb"].get("moments", ids[0])["status"] == "new"
    assert all(m["evidence_event_ids"] for m in moments)
    assert all(m["fast"] == sr.is_fast(m) for m in moments)


def test_golden_explained_moments_25_to_60(golden):
    moments = golden["moments"]
    branches = Counter(b for m in moments for b in sr.branches(m))
    kinds = Counter(m["kind"] for m in moments if sr.is_explained(m))
    print(f"golden 4242: {len(moments)} moments in {golden['seconds']:.1f} s, branches {dict(branches)}, "
          f"explained by kind {dict(kinds)}")
    assert 25 <= branches["explained"] <= 60


def test_missing_head_artefact_raises(tmp_path):
    with pytest.raises(HeadArtifactMissing):
        GoalIn8sHead(tmp_path)


def test_stream_under_50ms_per_event(golden):
    from heads.models import XGHead
    from physics.window import TrackingWindow

    events = [json.loads(line) for line in (GOLDEN / "events.jsonl").read_text().splitlines()]
    stream = sr.ScoutStream("m_4242", TrackingWindow.load(GOLDEN), xg_head=XGHead())
    stream.observe(events[0])  # warm-up: first LightGBM call
    cpu, wall = [], []
    for e in events[1:1500]:
        c0, w0 = time.process_time(), time.perf_counter()
        stream.observe(e)
        cpu.append((time.process_time() - c0) * 1000)
        wall.append((time.perf_counter() - w0) * 1000)
    c, w = np.asarray(cpu), np.asarray(wall)
    print(f"Scout per event, CPU: p50 {np.median(c):.2f} ms, p99 {np.quantile(c, .99):.2f} ms, max {c.max():.1f} ms; "
          f"wall: p50 {np.median(w):.2f} ms, p99 {np.quantile(w, .99):.2f} ms, max {w.max():.1f} ms")
    # process CPU time, as the physics budget test does (T-013): wall time measures the machine's other load
    assert c.max() < 50
