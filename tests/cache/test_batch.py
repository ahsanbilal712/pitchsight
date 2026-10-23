"""Golden precompute of model calls (T-042): rounds of batched requests matched by custom_id, a Fact Checker verdict
on every cached line, and a replay of the same moments with zero cache misses and identical cues."""

import asyncio
import json
import shutil
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from blackboard import SqliteBlackboard
from cache import CacheClient, CacheManifest
from cache.batch import (
    CUSTOM_ID,
    BatchRequest,
    FakeRunner,
    custom_id_for,
    parse_vertex_line,
    to_vertex_request,
)
from cache.client import preload_evidence
from cache.precompute_models import stage_newsroom
from mcp_server.tools_core import MatchStore
from newsroom.executors.base import Deps
from newsroom.graph import build_workflow
from newsroom.tools import LocalTools
from newsroom.worker import run_moment, start_message

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "data" / "matches" / "4242"
MOMENTS = ["mo_00002", "mo_00003", "mo_00012", "mo_00013"]   # a foul, a state change, a goal, a decision


def arun(coro):
    """asyncio.run on a worker thread: Playwright's session-scoped sync API (tests/apps) keeps a loop running in
    the main thread, and asyncio.run refuses to start inside it."""
    with ThreadPoolExecutor(1) as pool:
        return pool.submit(asyncio.run, coro).result()


def fake_model(r: BatchRequest):
    """Plausible structured answers built from each request's own inputs (no network)."""
    payload = json.loads(r.messages[-1]["content"])
    if r.live_role == "proposer":
        return {"alternatives": []}                       # invalid: the Proposer retries, then uses its rule
    if r.live_role == "tactician_live":
        cf = payload.get("COUNTERFACTUAL")
        if not cf:
            return {"why": "", "claims": [], "confidence": 0.3}
        p = cf["alternative_outcome"]["p_goal_home"]
        text = f"{round(100 * p)}%"
        return {"why": f"The alternative carries a {text} goal chance.", "confidence": 0.6, "claims": [
            {"text": text, "kind": "number", "value_number": p, "unit": "p_goal",
             "evidence_ids": [cf["counterfactual_id"]]}]}
    if r.live_role == "narrator_fast":
        texts = [c["text"] for c in payload.get("CLAIMS", [])][:2]
        return {"headline": "Key moment", "body": ". ".join(texts) + ("." if texts else ""), "claims": texts}
    if r.live_role == "panel_pundit":
        cf = (payload.get("EVIDENCE") or {}).get("counterfactual")
        claims = []
        if cf:
            p = cf["baseline"]["p_goal_home"]
            claims = [{"text": f"{round(100 * p)}%", "kind": "number", "value_number": p, "unit": "p_goal",
                       "evidence_ids": [cf["counterfactual_id"]]}]
        return {"take": "The panel debates the decision.", "stance": "nuance", "claims": claims}
    if r.live_role == "panel_chair":
        return {"consensus": "The panel splits on the decision.", "dissent": "none", "headline": "Panel: a split"}
    raise AssertionError(f"unexpected role {r.live_role}")


@pytest.fixture(scope="module")
def precomputed(tmp_path_factory):
    d = tmp_path_factory.mktemp("golden") / "4242"
    d.mkdir()
    for name in ("events.jsonl", "tracking.npz"):
        (d / name).symlink_to(GOLDEN / name)
    shutil.copytree(GOLDEN / "cache", d / "cache")
    (d / "cache" / "batches.json").unlink(missing_ok=True)       # this test's run is the only one in its log
    manifest = CacheManifest.load(d / "cache")
    events = [json.loads(line) for line in (d / "events.jsonl").read_text().splitlines()]
    seen_first = {}

    def model_and_concurrent_write(r):
        if not seen_first:   # another stage saves the manifest while the batch rounds run
            seen_first["done"] = True
            other = CacheManifest.load(d / "cache")
            other.add(CacheManifest.key("m_4242", None, "decision_index", "decision_index@1", None, 4242),
                      "analytics", {"x": 1}, "analytics/concurrent.json", producer="decision_index", seed=4242)
            other.save()
        return fake_model(r)

    runner = FakeRunner(model_and_concurrent_write)
    args = types.SimpleNamespace(mode="batch", runner=runner, moments=",".join(MOMENTS),
                                 runtime_dir=tmp_path_factory.mktemp("runtime"))
    with ThreadPoolExecutor(1) as pool:   # stage_newsroom calls asyncio.run: off the main thread (Playwright loop)
        summary = pool.submit(stage_newsroom, 4242, manifest, events, None, args).result()
    manifest.save()
    return {"dir": d, "manifest": CacheManifest.load(d / "cache"), "summary": summary, "runner": runner}


def test_requests_leave_in_rounds_and_match_by_custom_id(precomputed):
    s, runner = precomputed["summary"], precomputed["runner"]
    print(json.dumps(s))
    assert s["moments"] == 4 and s["failed"] == 0 and s["rounds"] >= 3 and len(runner.jobs) == s["rounds"]
    batches = json.loads((precomputed["dir"] / "cache" / "batches.json").read_text())
    assert len(batches["custom_ids"]) == s["requests"]
    for cid, key in batches["custom_ids"].items():
        assert CUSTOM_ID.match(cid) and cid == custom_id_for(key)
    keys = {e["key"] for e in precomputed["manifest"].entries}
    assert set(batches["custom_ids"].values()) <= keys            # every answered request is a cache entry


def test_every_cached_line_has_a_fact_checker_verdict(precomputed):
    m = precomputed["manifest"]
    lines = m.find(kind="fast_line")
    assert lines
    for e in lines:
        payload = m.read(e)
        if payload.get("error"):           # a call that failed in the golden run has no line to judge
            continue
        assert payload["verified"] in (True, False), e["key"]
    for e in m.find(producer="tactician"):
        assert "verified" in m.read(e)
    assert m.find(producer="evidence") and m.verify_hashes()
    assert m.find(path="analytics/concurrent.json")       # a write made during the run survives the stage's save


def test_replay_has_zero_cache_misses_and_the_same_cues(precomputed, tmp_path):
    manifest = precomputed["manifest"]
    bb = SqliteBlackboard(tmp_path / "replay.sqlite")
    store = MatchStore(bb, matches_dir=precomputed["dir"].parent, runtime_dir=tmp_path)
    cache = CacheClient(manifest, speed=1e9, inner_tools=LocalTools(store))
    assert preload_evidence(bb, manifest, store) > 0
    deps = Deps(bb=bb, llm=cache, rollout=cache, store=store, mode="replay", panel_enabled=True)
    moments = {json.loads(line)["moment_id"]: json.loads(line)
               for line in (precomputed["dir"] / "cache" / "moments.jsonl").read_text().splitlines()}
    cues = []
    for mid in MOMENTS:
        cues += arun(run_moment(build_workflow(deps), start_message(moments[mid], "replay")))["outputs"]
    assert cache.misses == []
    replayed = {(c["cue_id"], c["text"]["headline"], c["text"]["body"]) for c in cues}
    assert len(replayed) == precomputed["summary"]["cues"]
    bb.close()


def test_vertex_line_round_trip():
    r = BatchRequest("r_abc", "k", "narrator_fast", "narrator_fast", "gemini-3.8-flash",
                     [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}], {"type": "object"}, 300,
                     "none", {})
    line = to_vertex_request(r)
    assert line["request"]["labels"]["custom_id"] == "r_abc"
    assert line["request"]["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}
    out = {"request": line["request"], "response": {
        "candidates": [{"content": {"parts": [{"text": "{\"a\": 1}"}]}}],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 3, "thoughtsTokenCount": 2}}}
    assert parse_vertex_line(out) == ("r_abc", {"text": "{\"a\": 1}", "tokens_in": 10, "tokens_out": 5})
