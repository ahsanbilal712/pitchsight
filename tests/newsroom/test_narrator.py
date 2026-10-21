"""Narrator and fast line: verified claims only, cue limits, timeout -> template, provider error -> retry,
rewrite with the diff, one live call (T-020)."""

import asyncio
import dataclasses
import json
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from api.spend import SpendCapReached, SpendGuard
from newsroom.executors.base import Deps
from newsroom.executors.fast_line import claims_from_moment
from newsroom.executors.narrator import write_line
from newsroom.factcheck import verify_claims
from newsroom.graph import build_workflow
from newsroom.llm import CacheMiss, FakeClient, LiveClient, LLMError, LLMTimeout
from newsroom.messages import Moment
from newsroom.templates import template_line
from newsroom.worker import run_moment, start_message


def arun(coro):
    """asyncio.run on a worker thread: Playwright's session-scoped sync API (tests/apps) keeps a loop running in
    the main thread, and asyncio.run refuses to start inside it."""
    with ThreadPoolExecutor(1) as pool:
        return pool.submit(asyncio.run, coro).result()


M = "m_4242"
SHOT = {"moment_id": "mo_00077", "match_id": M, "t_ms": 1874000, "clock": "31:14", "kind": "big_chance",
        "xg": 0.31, "leverage": 0.02, "players": ["p_017"], "team": "home", "evidence_event_ids": ["e_8812"], "fast": True}


def verified_claims(bb, explanation_example):
    return verify_claims(M, explanation_example["claims"], bb)["claims"]


def good(headline="Okafor shoots, Reyes was free", body="The shot was worth 0.06 xG; the pass to Reyes 0.31 xG."):
    return {"json": {"headline": headline, "body": body, "claims": ["0.06 xG", "0.31 xG"]}}


def line(deps, claims, **kw):
    msg = start_message(SHOT)
    return arun(write_line(deps, msg, "sliding_doors", claims, **kw))


def test_output_fits_cue_limits_and_uses_only_given_claims(evidence_bb, explanation_example):
    claims = verified_claims(evidence_bb, explanation_example)
    fake = FakeClient({"narrator_fast": [good("H" * 90, "Worth 0.06 xG. " * 40)]})
    out = line(Deps(bb=evidence_bb, llm=fake), claims)
    assert out["status"] == "ok" and len(out["headline"]) <= 60 and len(out["body"]) <= 280
    sent = json.loads(fake.calls[0]["messages"][-1]["content"])["CLAIMS"]
    assert [c["text"] for c in sent] == [c["text"] for c in claims]


def test_unverified_claims_never_reach_the_model(evidence_bb, explanation_example):
    claims = verified_claims(evidence_bb, explanation_example)
    claims.append({"text": "0.50 xG", "kind": "number", "value": 0.5, "unit": "xg", "evidence_ids": ["e_8812"],
                   "verified": False, "reject_reason": "value_out_of_tolerance"})
    fake = FakeClient({"narrator_fast": [good()]})
    line(Deps(bb=evidence_bb, llm=fake), claims)
    sent = json.loads(fake.calls[0]["messages"][-1]["content"])["CLAIMS"]
    assert "0.50 xG" not in [c["text"] for c in sent]


def test_timeout_falls_back_to_a_template_that_passes_the_fact_checker(evidence_bb, explanation_example):
    claims = verified_claims(evidence_bb, explanation_example)
    out = line(Deps(bb=evidence_bb, llm=FakeClient({"narrator_fast": [LLMTimeout("4 s")]})), claims)
    assert out["status"] == "timeout" and out["model"] == "template"
    r = verify_claims(M, out["claims"], evidence_bb, {"headline": out["headline"], "body": out["body"]})
    assert r["verified"], r["diff"]


def test_provider_error_retries_once_then_succeeds(evidence_bb, explanation_example):
    claims = verified_claims(evidence_bb, explanation_example)
    fake = FakeClient({"narrator_fast": [LLMError("503 from provider"), good()]})
    out = line(Deps(bb=evidence_bb, llm=fake), claims)
    assert out["status"] == "ok" and len(fake.calls) == 2


def test_second_failure_and_bad_json_fall_back_to_template(evidence_bb, explanation_example):
    claims = verified_claims(evidence_bb, explanation_example)
    out = line(Deps(bb=evidence_bb, llm=FakeClient({"narrator_fast": [LLMError("a"), {"json": None,
                                                                                     "text": "nope"}]})), claims)
    assert out["status"] == "error" and out["model"] == "template"


def test_cache_miss_and_spend_cap_use_template(evidence_bb, explanation_example):
    claims = verified_claims(evidence_bb, explanation_example)
    out = line(Deps(bb=evidence_bb, llm=FakeClient({"narrator_fast": [CacheMiss("k")]})), claims)
    assert out["status"] == "cache_miss"
    deps = Deps(bb=evidence_bb, llm=FakeClient({"narrator_fast": [SpendCapReached("match m_4242", 2.5, 2.5)]}))
    assert line(deps, claims)["status"] == "degraded" and deps.state["degraded"] is True
    assert line(deps, claims)["status"] == "template"  # degraded: no further model calls
    assert len(deps.llm.calls) == 1


def test_rewrite_sends_diff_and_previous_draft(evidence_bb, explanation_example):
    claims = verified_claims(evidence_bb, explanation_example)
    fake = FakeClient({"narrator_fast": [good()]})
    diff = [{"where": "body", "token": "200", "reject_reason": "unbound_number"}]
    line(Deps(bb=evidence_bb, llm=fake), claims, diff=diff, previous={"headline": "x", "body": "In 200 replays"},
         attempt=2)
    payload = json.loads(fake.calls[0]["messages"][-1]["content"])
    assert payload["REWRITE"]["rejected"] == diff and payload["REWRITE"]["previous"]["body"] == "In 200 replays"
    assert fake.calls[0]["attempt"] == 2 and fake.calls[0]["prompt_version"] == "narrator@2"


def test_template_uses_only_verified_claims(evidence_bb, explanation_example):
    claims = verified_claims(evidence_bb, explanation_example)
    t = template_line("sliding_doors", claims + [{"text": "9 goals", "kind": "number", "verified": False}])
    assert "9 goals" not in t["body"] and len(t["headline"]) <= 60 and len(t["body"]) <= 280


def test_fast_line_claims_come_from_the_moment_evidence(evidence_bb):
    claims = claims_from_moment(Moment.model_validate(SHOT), evidence_bb)
    assert [(c["kind"], c["text"]) for c in claims] == [("player", "Okafor"), ("number", "0.06 xG"),
                                                         ("team", "Verdant")]
    assert verify_claims(M, claims, evidence_bb)["verified"]


def test_fast_branch_end_to_end_verified(evidence_bb):
    fake = FakeClient({"narrator_fast": [{"json": {"headline": "Okafor goes for goal",
                                                    "body": "Verdant work it to Okafor: a 0.06 xG chance.",
                                                    "claims": ["Okafor", "0.06 xG", "Verdant"]}}]})
    deps = Deps(bb=evidence_bb, llm=fake)
    cue = arun(run_moment(build_workflow(deps), start_message(SHOT)))["outputs"][0]
    assert cue["verified"] is True and cue["text"]["headline"] == "Okafor goes for goal"


def test_live_client_times_out_and_counts_thinking_tokens(tmp_path):
    guard = SpendGuard(ledger_path=tmp_path / "ledger.jsonl")

    class Slow:
        async def get_response(self, messages, options=None):
            await asyncio.sleep(1)

    class Quick:
        async def get_response(self, messages, options=None):
            return SimpleNamespace(text='{"headline": "a", "body": "b", "claims": []}', usage_details={
                "input_token_count": 1000, "output_token_count": 100, "reasoning_output_token_count": 50})

    with pytest.raises(LLMTimeout):
        arun(LiveClient(guard, clients={"gemini": Slow()}).complete("narrator_fast", [
            {"role": "user", "content": "x"}], timeout_s=0.05))
    timeout_row = json.loads((tmp_path / "ledger.jsonl").read_text().splitlines()[0])
    assert timeout_row["role"] == "narrator_fast:timeout" and timeout_row["tokens_out"] == 300
    res = arun(LiveClient(guard, clients={"gemini": Quick()}).complete(
        "narrator_fast", [{"role": "user", "content": "x"}], match_id="m_test"))
    assert res["tokens_out"] == 150 and res["json"]["headline"] == "a"
    assert res["cost_usd"] == pytest.approx((1000 * 0.75 + 150 * 3.75) / 1e6)
    row = json.loads((tmp_path / "ledger.jsonl").read_text().splitlines()[1])
    assert row["model"] == "gemini-3.8-flash" and row["tokens_out"] == 150 and row["role"] == "narrator_fast"


@pytest.mark.live
def test_live_narrator_line(evidence_bb, explanation_example):
    guard = SpendGuard()
    before = guard.total
    claims = verified_claims(evidence_bb, explanation_example)
    client = LiveClient(guard, mode="dev")
    print(f"warm-up {arun(client.warm()):.2f} s")
    t0 = time.perf_counter()
    out = line(Deps(bb=evidence_bb, llm=client), claims)
    print(f"narrator call {time.perf_counter() - t0:.2f} s")
    print(json.dumps({k: out[k] for k in ("headline", "body", "status", "model", "cost_usd")}, indent=1))
    assert out["status"] == "ok", out
    assert len(out["headline"]) <= 60 and len(out["body"]) <= 280
    assert guard.total - before <= 0.10


def test_live_client_hedges_a_slow_call(tmp_path, monkeypatch):
    """A second identical request after hedge_after_s; the first answer wins, the loser gets a worst-case row."""
    from newsroom import config as cfg

    guard = SpendGuard(ledger_path=tmp_path / "ledger.jsonl")
    calls = []

    class Tail:
        async def get_response(self, messages, options=None):
            calls.append(time.perf_counter())
            await asyncio.sleep(2.0 if len(calls) == 1 else 0.05)   # the first request is stuck in the tail
            return SimpleNamespace(text='{"headline": "h", "body": "b", "claims": []}',
                                   usage_details={"input_token_count": 100, "output_token_count": 10})

    real = cfg.role("narrator_fast")
    monkeypatch.setattr("newsroom.llm.role", lambda name: dataclasses.replace(real, extra={"hedge_after_s": 0.2}))
    t0 = time.perf_counter()
    res = arun(LiveClient(guard, clients={"gemini": Tail()}).complete(
        "narrator_fast", [{"role": "user", "content": "x" * 400}], match_id="m_test"))
    assert time.perf_counter() - t0 < 1.0 and len(calls) == 2 and res["json"]["headline"] == "h"
    rows = [json.loads(line) for line in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert sorted(r["role"] for r in rows) == ["narrator_fast", "narrator_fast:timeout"]
