"""Recap and producer veto (TECH_PLAN 1.7, T-050): the Director holds a recap with ctx.request_info; a vetoed recap
never reaches the CueBus, an approved one does with producer_status "approved"; the run resumes from its pause
checkpoint with responses. Also the recap tools top_moments and timeline."""

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from agent_framework import FileCheckpointStorage

from blackboard import SqliteBlackboard
from mcp_server import tools_recap
from mcp_server.errors import guarded
from mcp_server.tools_core import MatchStore
from newsroom.executors.base import Deps
from newsroom.factcheck import league_data
from newsroom.graph import build_workflow
from newsroom.llm import FakeClient
from newsroom.messages import ProducerDecision
from newsroom.tools import LocalTools
from newsroom.worker import run_moment, serve, start_message

ROOT = Path(__file__).resolve().parents[2]
M = "m_4242"
HALF_TIME = {"moment_id": "mo_00068", "match_id": M, "t_ms": 2_700_000, "clock": "45:00", "period": 1,
             "kind": "period_end", "leverage": None, "players": [], "team": None, "evidence_event_ids": ["e_1777"]}


def arun(coro):
    """asyncio.run on a worker thread: Playwright's session-scoped sync API (tests/apps) keeps a loop running in
    the main thread, and asyncio.run refuses to start inside it."""
    with ThreadPoolExecutor(1) as pool:
        return pool.submit(asyncio.run, coro).result()


def recap_answer():
    events = [json.loads(line) for line in (ROOT / "data/matches/4242/events.jsonl").read_text().splitlines()]
    goal = next(e for e in events if e["type"] == "goal" and e["t_ms"] < 2_700_000)
    players, _ = league_data()
    name = players[goal["player"]]["name"].split()[-1]
    minute = goal["t_ms"] // 60000
    return {"json": {"headline": f"Half-time: {name} strikes first",
                     "body": f"{name} scores in minute {minute}. The half swings between control and chaos.",
                     "claims": [{"text": name, "kind": "player", "value_text": goal["player"], "unit": "",
                                 "evidence_ids": [goal["id"]]},
                                {"text": f"{minute}", "kind": "minute", "value_number": minute, "unit": "minute",
                                 "evidence_ids": [goal["id"]]}],
                     "cards": [{"title": "Player of the half", "text": f"{name}, the scorer."}]}}


@pytest.fixture
def env(tmp_path):
    bb = SqliteBlackboard(tmp_path / "bb.sqlite")
    store = MatchStore(bb, runtime_dir=tmp_path)
    deps = Deps(bb=bb, llm=FakeClient({"recap_live": [recap_answer()] * 3}), rollout=LocalTools(store), store=store)
    yield deps, FileCheckpointStorage(tmp_path / "ckpt")
    bb.close()


def paused(deps, storage):
    wf = build_workflow(deps, storage=storage)
    result = arun(run_moment(wf, start_message(HALF_TIME)))
    assert result["outputs"] == [] and len(result["requests"]) == 1     # held for the producer, not on screen
    req = result["requests"][0]
    cp = arun(wf.resolve_pause_checkpoint_id([req.request_id], checkpoint_storage=storage))
    return req, cp


def resume(deps, storage, req, cp, status):
    async def go():
        wf = build_workflow(deps, storage=storage)
        return [e.data async for e in wf.run(stream=True, responses={req.request_id: ProducerDecision(status=status)},
                                             checkpoint_id=cp, checkpoint_storage=storage) if e.type == "output"]
    return arun(go())


def test_vetoed_recap_never_reaches_the_cuebus(env):
    deps, storage = env
    req, cp = paused(deps, storage)
    assert req.data.cue["kind"] == "recap" and req.data.cue["layer"] == "recap_card" and cp
    assert resume(deps, storage, req, cp, "vetoed") == []
    assert deps.bb.query("cues") == []
    assert not [t for t in deps.bb.query("traces") if t["executor"] == "cuebus"]
    assert deps.bb.query("traces", executor="director", status="producer_vetoed")


def test_approved_recap_is_delivered_approved_and_verified(env):
    deps, storage = env
    req, cp = paused(deps, storage)
    out = resume(deps, storage, req, cp, "approved")
    assert len(out) == 1 and out[0]["producer_status"] == "approved" and out[0]["verified"] is True
    cue = deps.bb.get("cues", out[0]["cue_id"], M)
    assert cue["producer_status"] == "approved" and cue["kind"] == "recap"
    assert cue["cue_id"] == "c_000684"                                 # mo_00068, recap branch


def test_worker_publishes_the_request_and_resumes_on_the_decision(env):
    deps, storage = env
    deps.bb.put("moments", HALF_TIME)

    async def go():
        stop = asyncio.Event()

        async def producer():
            for _ in range(400):
                reqs = deps.bb.query("requests", status="waiting")
                if reqs:
                    deps.bb.put("decisions", {"id": reqs[0]["request_id"], "request_id": reqs[0]["request_id"],
                                              "decision": "approved", "match_id": M})
                    break
                await asyncio.sleep(0.05)
            for _ in range(400):
                if deps.bb.query("cues"):
                    break
                await asyncio.sleep(0.05)
            stop.set()

        await asyncio.gather(asyncio.wait_for(serve(deps, storage=storage, stop=stop), timeout=60), producer())

    t0 = time.perf_counter()
    arun(go())
    req = deps.bb.query("requests")[0]
    assert req["status"] == "approved" and req["cue"]["kind"] == "recap" and req["checkpoint_id"]
    assert deps.bb.query("cues")[0]["producer_status"] == "approved" and time.perf_counter() - t0 < 60


def test_top_moments_and_timeline(env):
    deps, _ = env
    store = deps.store
    top = tools_recap.top_moments(store, M, period=1, k=3)
    assert len(top) == 3 and all(m["period"] == 1 for m in top) and [m["t_ms"] for m in top] == sorted(
        m["t_ms"] for m in top)
    every = [m for m in tools_recap._moments(store, M) if m.get("period") == 1 and m.get("leverage") is not None]
    assert min(m["leverage"] for m in top) >= sorted((m["leverage"] for m in every), reverse=True)[2]
    tl = tools_recap.timeline(store, M)
    assert tl["series"][0]["t_ms"] == 30_000 and {"chaos", "state", "control_home", "xt_diff_15"} <= set(tl["series"][0])
    assert len(tl["goals"]) == sum(1 for e in store.match(M).events if e["type"] == "goal")
    assert guarded(tools_recap.top_moments)(store, M, 3)[0]["code"] == "bad_period"
