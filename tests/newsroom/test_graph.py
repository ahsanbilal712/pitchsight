"""Newsroom graph: fast branch to a cue, the rewrite loop stops at attempt 3, checkpoints per superstep (T-018)."""

import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest
from agent_framework import FileCheckpointStorage

from blackboard import SqliteBlackboard
from newsroom.executors.base import Deps
from newsroom.executors.stubs import StubCueBus, StubDirector, StubFactCheck
from newsroom.graph import EXECUTOR_IDS, WORKFLOW_NAME, build_workflow
from newsroom.worker import run_moment, serve, start_message


def arun(coro):
    """asyncio.run on a worker thread: Playwright's session-scoped sync API (tests/apps) keeps a loop running in
    the main thread, and asyncio.run refuses to start inside it."""
    with ThreadPoolExecutor(1) as pool:
        return pool.submit(asyncio.run, coro).result()


GOAL = {"moment_id": "mo_00012", "match_id": "m_4242", "t_ms": 1_874_000, "clock": "31:14", "kind": "goal",
        "leverage": 0.21, "players": ["p_017"], "team": "home", "evidence_event_ids": ["e_0812"], "fast": True}
EXPLAINED = {"moment_id": "mo_00077", "match_id": "m_4242", "t_ms": 1_878_200, "clock": "31:18",
             "kind": "big_chance", "leverage": 0.09, "players": ["p_017", "p_031"], "team": "home",
             "evidence_event_ids": ["e_0812"], "fast": False}


def plumbing(deps, **extra):
    """Stub Director and CueBus: these tests check routing; the Director's rules have their own tests."""
    return {"director": StubDirector("director", deps), "cuebus": StubCueBus("cuebus", deps), **extra}


@pytest.fixture
def deps(tmp_path):
    bb = SqliteBlackboard(tmp_path / "bb.sqlite")
    yield Deps(bb=bb)
    bb.close()


def test_graph_has_every_tech_plan_executor(deps):
    wf = build_workflow(deps)
    assert set(EXECUTOR_IDS) <= set(wf.executors)
    assert wf.name == WORKFLOW_NAME


def test_goal_reaches_a_cue_through_the_fast_branch(deps):
    wf = build_workflow(deps, overrides=plumbing(deps))
    result = arun(run_moment(wf, start_message(GOAL)))
    assert len(result["outputs"]) == 1
    cue = result["outputs"][0]
    assert cue["agent_path"] == ["ingest", "scout", "fast_line", "factcheck", "director", "cuebus"]
    assert cue["verified"] is True and cue["moment_id"] == "mo_00012"
    assert deps.bb.query("cues", moment_id="mo_00012")[0]["cue_id"] == cue["cue_id"]
    assert {t["executor"] for t in deps.bb.query("traces", run_id="run_m_4242_mo_00012")} >= {"ingest", "scout"}


def test_rejecting_factcheck_loops_to_narrator_and_stops_at_attempt_3(deps):
    seen = []

    def reject(draft):
        seen.append(draft.attempt)
        return False

    wf = build_workflow(deps, overrides=plumbing(deps, factcheck=StubFactCheck("factcheck", deps, verdict=reject)))
    result = arun(run_moment(wf, start_message(EXPLAINED)))
    assert seen == [1, 2, 3]
    cue = result["outputs"][0]
    assert cue["attempt"] == 3 and cue["verified"] is False
    path = cue["agent_path"]
    assert path[:6] == ["ingest", "scout", "proposer", "rollout", "tactician", "narrator"]
    assert path.count("narrator") == 3 and path.count("factcheck") == 3 and path[-2:] == ["director", "cuebus"]


def test_unknown_branch_goes_to_drop(deps):
    wf = build_workflow(deps)
    result = arun(run_moment(wf, start_message({**GOAL, "moment_id": "mo_00013", "branches": ["drop"]})))
    assert result["outputs"] == []
    assert deps.bb.query("traces", executor="drop")[0]["status"] == "dropped"


def test_checkpoint_after_each_superstep(deps, tmp_path, monkeypatch):
    ckpt = tmp_path / "ckpt"
    monkeypatch.setenv("WHYLINE_CHECKPOINT_DIR", str(ckpt))
    from newsroom.worker import make_storage

    storage = make_storage()
    assert storage.storage_path == ckpt
    wf = build_workflow(deps, storage=storage)
    result = arun(run_moment(wf, start_message(GOAL)))
    supersteps = result["events"].count("superstep_completed")
    files = list(ckpt.glob("*.json"))
    assert supersteps == 6 and len(files) >= supersteps
    cps = arun(storage.list_checkpoints(workflow_name=WORKFLOW_NAME))
    assert len(cps) == len(files)


def test_resume_from_a_mid_run_checkpoint(deps, tmp_path):
    storage = FileCheckpointStorage(tmp_path / "ckpt")
    wf = build_workflow(deps, storage=storage, overrides=plumbing(deps))
    arun(run_moment(wf, start_message(EXPLAINED)))
    cps = arun(storage.list_checkpoints(workflow_name=WORKFLOW_NAME))
    mid = next(c for c in cps if "tactician" in c.messages)  # message waiting for the Tactician

    async def resume():
        fresh = build_workflow(deps, storage=storage, overrides=plumbing(deps))
        return [e.data async for e in fresh.run(checkpoint_id=mid.checkpoint_id, checkpoint_storage=storage,
                                                  stream=True) if e.type == "output"]

    outputs = arun(resume())
    assert len(outputs) == 1 and outputs[0]["moment_id"] == "mo_00077"
    assert outputs[0]["agent_path"][-4:] == ["narrator", "factcheck", "director", "cuebus"]


def test_worker_runs_one_workflow_per_new_moment(deps):
    deps.bb.put("moments", GOAL)
    deps.bb.put("moments", {**EXPLAINED, "status": "done"})  # not new: skipped
    deps.bb.put("moments", {**GOAL, "moment_id": "mo_00014", "t_ms": GOAL["t_ms"] + 120_000})  # past the dedupe
    runs = []

    async def go():
        stop = asyncio.Event()

        def on_result(msg, result):
            runs.append(msg.moment.moment_id)
            if len(runs) == 2:
                stop.set()

        await asyncio.wait_for(serve(deps, stop=stop, on_result=on_result), timeout=20)

    arun(go())
    assert runs == ["mo_00012", "mo_00014"]
    assert [c["moment_id"] for c in deps.bb.query("cues")] == ["mo_00012", "mo_00014"]
