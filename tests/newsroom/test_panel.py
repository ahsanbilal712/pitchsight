"""Panel: GroupChatBuilder sub-workflow, three pundits in a fixed order, chair summary, claims citing cf_/pc_ and
passing the Fact Checker, 25 s budget with drop-on-timeout (T-041)."""

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from newsroom.executors import panel as P
from newsroom.executors.base import Deps
from newsroom.executors.stubs import StubCueBus, StubDirector, StubScout
from newsroom.graph import build_workflow
from newsroom.llm import FakeClient, LiveClient
from newsroom.worker import run_moment, start_message

M = "m_4242"
MOMENT = {"moment_id": "mo_00077", "match_id": M, "t_ms": 1874000, "clock": "31:14", "kind": "decision",
          "leverage": 0.09, "players": ["p_017"], "team": "home", "evidence_event_ids": ["e_8812"],
          "branches": ["panel"]}


def arun(coro):
    """asyncio.run on a worker thread: Playwright's session-scoped sync API (tests/apps) keeps a loop running in
    the main thread, and asyncio.run refuses to start inside it."""
    with ThreadPoolExecutor(1) as pool:
        return pool.submit(asyncio.run, coro).result()


def take(name, stance="agree"):
    return {"json": {"take": f"{name} take: the pass to Reyes takes the chance from 11% to 27%.", "stance": stance,
                     "claims": [
                         {"text": "11%", "kind": "number", "value_number": 0.11, "unit": "p_goal",
                          "evidence_ids": ["cf_000077"]},
                         {"text": "27%", "kind": "number", "value_number": 0.27, "unit": "p_goal",
                          "evidence_ids": ["cf_000077"]},
                         {"text": "2v1 overload on the right", "kind": "tactical", "value_text": "overload_right",
                          "unit": "", "evidence_ids": ["pc_000412"]},
                         {"text": "0.06 xG", "kind": "number", "value_number": 0.06, "unit": "xg",
                          "evidence_ids": ["e_8812"]},                        # no cf_/pc_: dropped
                         {"text": "40%", "kind": "number", "value_number": 0.40, "unit": "p_goal",
                          "evidence_ids": ["cf_000077"]}]}}                   # fails the Fact Checker: dropped


CHAIR = {"json": {"consensus": "All three back the pass: 11% to 27%.", "dissent": "The sceptic doubts the overload.",
                  "headline": "Panel: the pass was on"}}


def fake(delay=0.0):
    return FakeClient({"panel_pundit": [take(n) for n in P.PUNDITS], "panel_chair": [CHAIR]}, delay_s=delay)


def test_three_pundits_in_order_then_the_chair(evidence_bb):
    deps = Deps(bb=evidence_bb, llm=fake())
    out = arun(P.run_panel(deps, start_message(MOMENT)))
    roles = [c["role"] for c in deps.llm.calls]
    assert roles == ["panel_pundit"] * 3 + ["panel_chair"]
    assert [c["prompt_version"] for c in deps.llm.calls[:3]] == ["pundit_press@1", "pundit_possession@1",
                                                                  "pundit_sceptic@1"]
    later = json.loads(deps.llm.calls[2]["messages"][1]["content"])["EARLIER_TAKES"]
    assert [t["pundit"] for t in later] == ["press", "possession"]          # the sceptic hears both
    assert set(out["takes"]) == set(P.PUNDITS) and out["chair"]["headline"] == "Panel: the pass was on"


def test_every_kept_claim_cites_cf_or_pc_and_passes(evidence_bb):
    out = arun(P.run_panel(Deps(bb=evidence_bb, llm=fake()), start_message(MOMENT)))
    for t in out["takes"].values():
        assert [c["text"] for c in t["claims"]] == ["11%", "27%", "2v1 overload on the right"]
        assert all(c["verified"] and any(i[:3] in ("cf_", "pc_") for i in c["evidence_ids"]) for c in t["claims"])


def test_structured_outputs():
    assert set(P.PUNDIT_SCHEMA["required"]) == {"take", "claims", "stance"}
    assert set(P.CHAIR_SCHEMA["required"]) == {"consensus", "dissent", "headline"}


def test_timeout_drops_the_panel_without_retry(evidence_bb, monkeypatch):
    monkeypatch.setattr(P, "BUDGET_S", 0.3)
    deps = Deps(bb=evidence_bb, llm=fake(delay=0.2))
    wf = build_workflow(deps, overrides={"scout": StubScout("scout", deps), "director": StubDirector("director", deps),
                                         "cuebus": StubCueBus("cuebus", deps)})
    t0 = time.perf_counter()
    outputs = arun(run_moment(wf, start_message(MOMENT)))["outputs"]
    assert outputs == [] and time.perf_counter() - t0 < 2
    row = evidence_bb.query("traces", executor="panel")[0]
    assert row["status"] == "timeout"
    assert len(deps.llm.calls) <= 2                                         # stopped, never retried


def test_panel_branch_reaches_a_verified_cue(evidence_bb):
    deps = Deps(bb=evidence_bb, llm=fake(), panel_enabled=True)
    wf = build_workflow(deps, overrides={"scout": StubScout("scout", deps)})
    out = arun(run_moment(wf, start_message(MOMENT)))["outputs"]
    assert len(out) == 1
    cue = out[0]
    assert cue["cue_id"] == "c_000772" and cue["layer"] == "options_card" and cue["verified"] is True
    assert cue["text"]["headline"] == "Panel: the pass was on"
    assert {c["text"] for c in cue["explain"]["claims"]} == {"11%", "27%", "2v1 overload on the right"}


@pytest.mark.live
def test_live_panel(tmp_path):
    """A golden shot moment (Okafor at 45:15, carry vs shot), real pundits and chair, in-process tools."""
    from api.spend import SpendGuard
    from blackboard import SqliteBlackboard
    from mcp_server.tools_core import MatchStore
    from newsroom.tools import LocalTools

    events = [json.loads(line) for line in open("data/matches/4242/events.jsonl")]
    shot = next(e for e in events if e["type"] == "shot" and e["t_ms"] >= 2_715_000)
    store = MatchStore(SqliteBlackboard(tmp_path / "bb.sqlite"), runtime_dir=tmp_path)
    store.match(M)
    guard = SpendGuard()
    before = guard.total
    client = LiveClient(guard, mode="dev")
    arun(client.warm("panel_pundit"))
    arun(client.warm("panel_chair"))
    deps = Deps(bb=store.bb, llm=client, store=store, rollout=LocalTools(store))
    moment = {"moment_id": "mo_00060", "match_id": M, "t_ms": shot["t_ms"], "kind": "decision", "leverage": 0.0471,
              "players": [shot["player"]], "team": shot["team"], "evidence_event_ids": [shot["id"]]}
    # a live match's engine is already at the moment: advance it (and the 1 Hz chaos series) to just before
    from rollout.core import MatchRef
    match = store.match(M)
    match.ref = MatchRef(seed=4242, match_dir=match.dir)
    match.ref.engine_at(shot["t_ms"] - 2000)
    arun(LocalTools(store).call("get_state", {"match_id": M, "t_ms": shot["t_ms"] - 2000}))
    t0 = time.perf_counter()
    try:
        out = arun(P.run_panel(deps, start_message(moment)))
    except TimeoutError:
        out = None
    seconds = time.perf_counter() - t0
    print("panel timings", P.LAST_TIMINGS)
    print(f"live panel {seconds:.1f} s, spend ${guard.total - before:.4f}")
    if out:
        print(json.dumps({k: {"take": v["take"], "stance": v["stance"], "claims": [c["text"] for c in v["claims"]]}
                          for k, v in out["takes"].items()}, indent=1), out["chair"])
    assert guard.total - before <= 0.50
    assert out is not None, f"panel exceeded {P.BUDGET_S} s ({seconds:.1f} s): the cue would be dropped"
    assert all(c["verified"] for t in out["takes"].values() for c in t["claims"])
