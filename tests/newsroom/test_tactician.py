"""Tactician: explanation.schema.json output with evidence on every claim, 12 s timeout with one retry, then the
tactician_degraded template, tools over the newsroom tool client, the stable league block."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from blackboard import SqliteBlackboard
from mcp_server.tools_core import MatchStore
from newsroom.executors.base import Deps
from newsroom.executors.tactician import (
    VALIDATOR,
    explain,
    explanation_id_for,
    league_block,
    make_tools,
    to_claim,
)
from newsroom.factcheck import verify_claims
from newsroom.llm import FakeClient, LiveClient, LLMError, LLMTimeout
from newsroom.tools import LocalTools
from newsroom.worker import start_message

ROOT = Path(__file__).resolve().parents[2]
M = "m_4242"


def arun(coro):
    """asyncio.run on a worker thread: Playwright's session-scoped sync API (tests/apps) keeps a loop running in
    the main thread, and asyncio.run refuses to start inside it."""
    with ThreadPoolExecutor(1) as pool:
        return pool.submit(asyncio.run, coro).result()


@pytest.fixture
def cf(evidence_bb):
    return evidence_bb.get("counterfactuals", "cf_000077")


MOMENT = {"moment_id": "mo_00077", "match_id": M, "t_ms": 1874000, "clock": "31:14", "kind": "decision",
          "leverage": 0.09, "players": ["p_017"], "team": "home", "evidence_event_ids": ["e_8812"]}


def model_output(**over):
    body = {"why": "A 2v1 overload on the right pulled the centre-back out; the shot was 0.06 xG.",
            "confidence": 0.8, "claims": [
                {"text": "0.06 xG", "kind": "number", "value_number": 0.06, "unit": "xg", "evidence_ids": ["e_8812"]},
                {"text": "Okafor", "kind": "player", "value_text": "p_017", "unit": "", "evidence_ids": ["e_8812"]},
                {"text": "2v1 overload on the right", "kind": "tactical", "value_text": "overload_right", "unit": "",
                 "evidence_ids": ["pc_000412"]},
                {"text": "11%", "kind": "number", "value_number": 0.11, "unit": "p_goal",
                 "evidence_ids": ["cf_000077"]}]}
    body.update(over)
    return {"json": body, "model": "gemini-4-argon"}


def run_explain(bb, cf, script, **state):
    deps = Deps(bb=bb, llm=FakeClient({"tactician_live": script}))
    deps.state.update(state)
    exp, info = arun(explain(deps, start_message(MOMENT), None, cf, [{"kind": "pass", "target": "p_031"}]))
    return exp, info, deps.llm.calls


def test_output_validates_and_every_claim_has_evidence(evidence_bb, cf):
    exp, info, calls = run_explain(evidence_bb, cf, [model_output()])
    assert info["status"] == "ok" and not list(VALIDATOR.iter_errors(exp))
    assert exp["explanation_id"] == "ex_000077" and exp["counterfactual_id"] == "cf_000077"
    assert all(c["evidence_ids"] for c in exp["claims"]) and exp["prompt_version"] == "tactician@3"
    assert calls[0]["timeout_s"] == 12 and calls[0]["max_tool_rounds"] == 1
    assert verify_claims(M, exp["claims"], evidence_bb, {"why": exp["why"]})["verified"]


def test_claims_without_evidence_are_dropped():
    assert to_claim({"text": "x", "kind": "number", "value_number": 1, "unit": "xg", "evidence_ids": []}) is None
    assert to_claim({"text": "x", "kind": "vibes", "evidence_ids": ["e_1"]}) is None
    c = to_claim({"text": "27%", "kind": "number", "value_number": 0.27, "unit": "", "evidence_ids": ["cf_000077"]})
    assert c["unit"] is None and c["value"] == 0.27 and c["verified"] is False


def test_timeout_retries_once_then_template(evidence_bb, cf):
    exp, info, calls = run_explain(evidence_bb, cf, [LLMTimeout("12 s"), model_output()])
    assert info["status"] == "ok" and len(calls) == 2
    exp, info, calls = run_explain(evidence_bb, cf, [LLMTimeout("12 s"), LLMError("503")])
    assert info["status"] == "error" and exp["model"] == "template" and len(calls) == 2
    assert not list(VALIDATOR.iter_errors(exp))


def test_invalid_output_twice_gives_template(evidence_bb, cf):
    exp, info, _ = run_explain(evidence_bb, cf, [model_output(claims=[]), {"json": {"why": "x"}}])
    assert info["status"] == "invalid_output" and exp["model"] == "template"


def test_degraded_template_passes_the_fact_checker(evidence_bb, cf):
    exp, info, calls = run_explain(evidence_bb, cf, [], degraded=True)
    assert info["status"] == "template" and calls == []
    assert not list(VALIDATOR.iter_errors(exp))
    r = verify_claims(M, exp["claims"], evidence_bb, {"why": exp["why"]})
    assert r["verified"], r["diff"]
    assert {"11%", "27%", "42% to 51%"} <= {c["text"] for c in exp["claims"]}


def test_explanation_ids_follow_the_moment():
    assert explanation_id_for("mo_00077") == "ex_000077"


def test_league_block_is_stable_and_names_both_squads():
    meta = json.loads((ROOT / "data/matches/4242/events.jsonl").read_text().splitlines()[0])["attrs"]
    block = league_block(meta)
    assert block == league_block(meta) and "Verdant" in block and "Okafor" in block and "Style:" in block
    assert len(block) // 4 < 2500   # ~1,500-token budget in budgets.yaml, with margin


def test_tools_go_through_the_tool_client(tmp_path):
    store = MatchStore(SqliteBlackboard(tmp_path / "bb.sqlite"), runtime_dir=tmp_path)
    trace = []
    tools = {t.name: t for t in make_tools(Deps(bb=store.bb, rollout=LocalTools(store)), trace)}
    assert set(tools) == {"query_events", "get_pitch_control", "simulate_counterfactual", "player_stats"}
    out = json.loads(arun(tools["query_events"].func(M, 0, 120_000, ["pass"])))
    assert out and set(out[0]) >= {"id", "t_ms", "type", "attrs"} and len(out) <= 40
    pc = json.loads(arun(tools["get_pitch_control"].func(M, 600_000)))
    assert pc["snapshot_id"] == "pc_006000"
    assert [t["tool"] for t in trace] == ["query_events", "get_pitch_control"]


def test_live_client_runs_tool_rounds_through_its_own_client(tmp_path):
    """With tools, LiveClient uses a chat client whose loop stops after max_tool_rounds (injected fake here)."""
    from api.spend import SpendGuard

    seen = {}

    class Fake:
        async def get_response(self, messages, options=None):
            seen.update(options)
            return SimpleNamespace(text='{"why": "w", "claims": [], "confidence": 1}',
                                   usage_details={"input_token_count": 10, "output_token_count": 5})

    lc = LiveClient(SpendGuard(ledger_path=tmp_path / "l.jsonl"), clients={"gemini": Fake()})
    res = arun(lc.complete("tactician_live", [{"role": "user", "content": "x"}], ["tool"], schema={"type": "object"}))
    assert seen["tools"] == ["tool"] and seen["model"] == "gemini-3.8-flash" and res["json"]["why"] == "w"
    assert seen["thinking_config"] == {"thinking_budget": 0}         # live Tactician: Flash, thinking off


@pytest.mark.live
def test_live_tactician(evidence_bb, cf):
    """One live Tactician call on the schema-example moment (no tool rounds); validates and is cited."""
    from api.spend import SpendGuard

    deps = Deps(bb=evidence_bb, llm=LiveClient(SpendGuard(), mode="dev"))
    deps.state["max_tool_rounds"] = 0
    exp, info = arun(explain(deps, start_message(MOMENT), None, cf, []))
    print(info, json.dumps(exp)[:600])
    assert info["status"] == "ok" and not list(VALIDATOR.iter_errors(exp))
