"""CacheClient: hits after simulated_latency_ms / WHYLINE_REPLAY_SPEED, misses raise CacheMiss, counterfactuals by
content (also through the MCP tool in replay mode), replay injection in the worker (T-038)."""

import asyncio
import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from blackboard import SqliteBlackboard
from cache import CacheClient, CacheManifest, CacheMiss
from cache.client import tool_key
from mcp_server import tools_core
from mcp_server.errors import guarded
from newsroom.executors.base import Deps
from newsroom.graph import build_workflow
from newsroom.worker import run_moment, start_message

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "data" / "matches" / "4242"
CF = json.loads((ROOT / "schemas/counterfactual.schema.json").read_text())["examples"][0]
ALT = {k: CF["alternative"][k] for k in ("kind", "actor", "target")}


def arun(coro):
    """asyncio.run on a worker thread: Playwright's session-scoped sync API (tests/apps) keeps a loop running in
    the main thread, and asyncio.run refuses to start inside it."""
    with ThreadPoolExecutor(1) as pool:
        return pool.submit(asyncio.run, coro).result()


@pytest.fixture
def manifest(tmp_path):
    d = tmp_path / "4242"
    d.mkdir()
    for name in ("events.jsonl", "tracking.npz"):
        shutil.copy(GOLDEN / name, d / name)
    m = CacheManifest.new(d, engine_hash="0" * 40)
    line = {"json": {"headline": "Okafor shoots", "body": "A shot.", "claims": []}, "text": "{}"}
    m.add(m.key("m_4242", "mo_00077", "narrator", "narrator@2", "gemini-3.8-flash", 4242), "fast_line", line,
          "lines/mo_00077.json", moment_id="mo_00077", producer="narrator", version="narrator@2",
          model="gemini-3.8-flash", seed=4242, simulated_latency_ms=400, tokens_in=480, tokens_out=90)
    m.add(m.key("m_4242", "mo_00077", "narrator", "narrator@2.a2", "gemini-3.8-flash", 4242), "fast_line",
          {"json": {"headline": "Rewrite", "body": "", "claims": []}}, "lines/mo_00077_a2.json",
          moment_id="mo_00077", producer="narrator", version="narrator@2.a2", model="gemini-3.8-flash", seed=4242)
    for model in ("gemini-3.8-flash", "gemini-4-argon"):
        m.add(m.key("m_4242", "mo_00077", "tactician", "tactician@3", model, 4242), "explanation",
              {"json": {"why": model}}, f"explanations/{model}.json", moment_id="mo_00077", producer="tactician",
              version="tactician@3", model=model, seed=4242, simulated_latency_ms=0)
    m.add(m.key("m_4242", "mo_00077", "rollout", "scripted_v1", "scripted", 4242), "counterfactual", CF,
          "counterfactuals/cf_000077.json", moment_id="mo_00077", producer="rollout", version="scripted_v1",
          model="scripted", seed=4242, simulated_latency_ms=1180)
    args = {"match_id": "m_4242", "t_ms": 600_000}
    m.add(tool_key("m_4242", "get_state", args, 4242), "analytics", {"result": {"clock": "10:00", "cached": True}},
          "tools/get_state_600000.json", producer="get_state", seed=4242, simulated_latency_ms=0)
    m.save()
    return m


def test_hit_waits_simulated_latency_over_replay_speed(manifest, monkeypatch):
    monkeypatch.setenv("WHYLINE_REPLAY_SPEED", "10")
    c = CacheClient(manifest)
    t0 = time.perf_counter()
    res = arun(c.complete("narrator_fast", [], None, match_id="m_4242", moment_id="mo_00077",
                          prompt_version="narrator@2", attempt=1, producer="narrator"))
    waited = time.perf_counter() - t0
    assert 0.035 <= waited < 0.4                         # 400 ms / speed 10
    assert res["json"]["headline"] == "Okafor shoots" and res["cache_hit"] is True and res["latency_ms"] == 400
    assert res["cache_key"] == "m_4242/mo_00077/narrator@2/gemini-3.8-flash/s4242" and res["cost_usd"] == 0.0


def test_rewrite_attempts_have_their_own_entries(manifest):
    res = arun(CacheClient(manifest, speed=1e6).complete("narrator_fast", [], match_id="m_4242",
                                                         moment_id="mo_00077", prompt_version="narrator@2",
                                                         attempt=2, producer="narrator"))
    assert res["json"]["headline"] == "Rewrite"


def test_prefers_the_roles_model(manifest):
    res = arun(CacheClient(manifest).complete("tactician_live", [], match_id="m_4242", moment_id="mo_00077",
                                              prompt_version="tactician@3", producer="tactician"))
    assert res["json"]["why"] == "gemini-4-argon"


def test_miss_raises_and_is_recorded(manifest):
    c = CacheClient(manifest)
    with pytest.raises(CacheMiss):
        arun(c.complete("narrator_fast", [], match_id="m_4242", moment_id="mo_00099", prompt_version="narrator@2",
                        producer="narrator"))
    assert c.misses == ["m_4242/mo_00099/narrator@2/none/s4242"]
    with pytest.raises(CacheMiss):
        arun(CacheClient(None).complete("proposer", [], match_id="m_4242", moment_id="mo_00077"))


def test_counterfactual_by_content_and_tool_entries(manifest):
    c = CacheClient(manifest, speed=1e6)
    cf = arun(c.call("simulate_counterfactual", {"match_id": "m_4242", "t_ms": CF["t_ms"], "alternative": ALT,
                                                 "n": 200, "horizon_s": 8}))
    assert cf["counterfactual_id"] == "cf_000077"
    miss = arun(c.call("simulate_counterfactual", {"match_id": "m_4242", "t_ms": CF["t_ms"], "alternative": ALT,
                                                   "n": 50, "horizon_s": 8}))
    assert miss["code"] == "cache_miss"
    assert arun(c.call("get_state", {"match_id": "m_4242", "t_ms": 600_000}))["cached"] is True
    assert arun(c.call("get_state", {"match_id": "m_4242", "t_ms": 1}))["code"] == "cache_miss"

    class Inner:
        async def call(self, name, args):
            return {"from": "inner"}

    assert arun(CacheClient(manifest, inner_tools=Inner()).call("get_state", {"match_id": "m_4242", "t_ms": 1})) \
        == {"from": "inner"}


def test_mcp_simulate_counterfactual_returns_cached_cf_in_replay(manifest, tmp_path):
    store = tools_core.MatchStore(SqliteBlackboard(tmp_path / "bb.sqlite"), runtime_dir=tmp_path,
                                  cache=CacheClient(manifest), replay=True)
    cf = tools_core.simulate_counterfactual(store, "m_4242", CF["t_ms"], ALT)
    assert cf["counterfactual_id"] == "cf_000077" and store.bb.get("counterfactuals", "cf_000077", "m_4242")
    out = guarded(tools_core.simulate_counterfactual)(store, "m_4242", CF["t_ms"], {**ALT, "target": "p_020"})
    assert out["code"] == "cache_miss"


def test_replay_graph_serves_cached_lines_and_flags_misses(manifest, tmp_path):
    bb = SqliteBlackboard(tmp_path / "graph.sqlite")
    cache = CacheClient(manifest, speed=1e6)
    deps = Deps(bb=bb, llm=cache, rollout=cache)
    shot = {"moment_id": "mo_00077", "match_id": "m_4242", "t_ms": 1_874_000, "kind": "big_chance", "xg": 0.31,
            "leverage": 0.01, "players": [], "team": "home", "evidence_event_ids": []}
    # the fast line's producer is fast_line: not cached here, so this is a miss -> template and a red row
    cue = arun(run_moment(build_workflow(deps), start_message(shot)))["outputs"][0]
    assert cue["provenance"]["model"] == "template"
    assert bb.query("traces", executor="director")[0]["status"] == "cache_miss"
    assert cache.misses == ["m_4242/mo_00077/fast_line@narrator@2/none/s4242"]


def test_worker_injects_cache_client_in_replay(monkeypatch, tmp_path):
    from newsroom.worker import make_deps

    monkeypatch.setenv("WHYLINE_BLACKBOARD", str(tmp_path / "bb.sqlite"))
    deps = make_deps("replay")
    assert isinstance(deps.llm, CacheClient) and deps.rollout is deps.llm
    deps.bb.close()
