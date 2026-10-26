"""Proposer and RolloutExecutor: decision point, rule fallback, model output validated, 6 s timeout with one retry,
2 s rollout timeout with n = 50 fallback, invalid alternatives skipped, policy_prob >= 0.05."""

import asyncio
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from blackboard import SqliteBlackboard
from mcp_server.tools_core import MatchStore
from newsroom.decision import attach_options, decision_point, proposer_rule, valid_alternatives
from newsroom.executors.base import Deps
from newsroom.executors.proposer import propose
from newsroom.executors.rollout import choose, simulate
from newsroom.executors.stubs import StubCueBus, StubDirector
from newsroom.graph import build_workflow
from newsroom.llm import FakeClient, LiveClient, LLMError, LLMTimeout
from newsroom.tools import LocalTools
from newsroom.worker import run_moment, start_message

ROOT = Path(__file__).resolve().parents[2]
M = "m_4242"
EVENTS = [json.loads(line) for line in (ROOT / "data/matches/4242/events.jsonl").read_text().splitlines()]
PASS = next(e for e in EVENTS if e["type"] == "pass" and e["t_ms"] > 120_000)


def arun(coro):
    """asyncio.run on a worker thread: Playwright's session-scoped sync API (tests/apps) keeps a loop running in
    the main thread, and asyncio.run refuses to start inside it."""
    with ThreadPoolExecutor(1) as pool:
        return pool.submit(asyncio.run, coro).result()


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    d = tmp_path_factory.mktemp("proposer")
    s = MatchStore(SqliteBlackboard(d / "bb.sqlite"), runtime_dir=d)
    yield s
    s.bb.close()


@pytest.fixture(scope="module")
def moment():
    return {"moment_id": "mo_00009", "match_id": M, "t_ms": PASS["t_ms"], "kind": "decision", "leverage": 0.05,
            "players": [PASS["player"]], "team": PASS["team"], "evidence_event_ids": [PASS["id"]]}


@pytest.fixture(scope="module")
def decision(store, moment):
    d = decision_point(store, moment)
    state = arun(LocalTools(store).call("get_state", {"match_id": M, "t_ms": d["t_ms"]}))
    return attach_options(d, state["options"])


def test_decision_point(decision):
    assert decision["t_ms"] == PASS["t_ms"] - 100 and decision["actor"] == PASS["player"]
    assert decision["actual"] == {"kind": "pass", "actor": PASS["player"], "target": PASS["attrs"]["recipient"]}
    assert len(decision["teammates"]) == 10 and PASS["player"] not in {m["player_id"] for m in decision["teammates"]}
    assert decision["options"] is not None and all(m["policy_prob"] is not None for m in decision["teammates"])
    gains = [m["xt_gain"] for m in decision["teammates"]]
    assert gains == sorted(gains, reverse=True)


def test_no_decision_point_without_on_ball_event(store):
    assert decision_point(store, {"match_id": M, "t_ms": 500, "evidence_event_ids": ["e_0001"], "team": None}) \
        is None


def test_rule_top3_by_xt_gain_excluding_actual_target(decision):
    alts = proposer_rule(decision)
    plausible = [m for m in decision["teammates"] if m["player_id"] != decision["actual"]["target"]
                 and m["policy_prob"] >= 0.05]
    passes = [a["target"] for a in alts if a["kind"] == "pass"]
    assert passes == [m["player_id"] for m in plausible][:3] and 1 <= len(alts) <= 3
    probs = {m["player_id"]: m["policy_prob"] for m in decision["teammates"]} | decision["options"]
    assert all(probs[a["target"] if a["kind"] == "pass" else a["kind"]] >= 0.05 for a in alts)


def test_rule_without_probabilities_is_pure_xt(decision):
    blind = {**decision, "options": None, "teammates": [{**m, "policy_prob": None} for m in decision["teammates"]]}
    expected = [m["player_id"] for m in decision["teammates"] if m["player_id"] != decision["actual"]["target"]][:3]
    assert [a["target"] for a in proposer_rule(blind)] == expected


def test_model_output_is_validated(decision):
    mate = decision["teammates"][0]["player_id"]
    proposed = [{"kind": "pass", "actor": "p_999", "target": mate, "reason": "r"},       # actor forced to the real one
                {"kind": "pass", "actor": "x", "target": "p_199", "reason": "bench"},       # not on the pitch
                {"kind": "carry", "actor": "x", "target": "up", "reason": "bad tag"},
                {"kind": "pass", "actor": "x", "target": decision["actual"]["target"], "reason": "the actual"},
                {"kind": "shoot", "actor": "x", "target": "goal", "reason": "shoot"},
                {"kind": "dance", "actor": "x", "target": None, "reason": "no"},
                {"kind": "carry", "actor": "x", "target": "ne", "reason": "drive"}]
    out = valid_alternatives(decision, proposed)
    assert [(a["kind"], a["actor"], a["target"]) for a in out] == [
        ("pass", decision["actor"], mate), ("shoot", decision["actor"], None), ("carry", decision["actor"], "ne")]


def other_mate(decision):
    """A team-mate who is not the actual pass target (the model may never propose the action played)."""
    return next(m["player_id"] for m in decision["teammates"] if m["player_id"] != decision["actual"]["target"])


def _propose(store, decision, script):
    deps = Deps(bb=store.bb, llm=FakeClient({"proposer": script}), store=store)
    alts, info = arun(propose(deps, start_message({"moment_id": "mo_00009", "match_id": M, "t_ms": 1,
                                                   "kind": "decision"}), decision))
    return alts, info, deps.llm.calls


def test_proposer_uses_model_alternatives(store, decision):
    mate = other_mate(decision)
    alts, info, calls = _propose(store, decision, [{"json": {"alternatives": [
        {"kind": "pass", "actor": decision["actor"], "target": mate, "reason": "switch"}]}}])
    assert info["status"] == "ok" and alts[0]["target"] == mate and len(calls) == 1
    assert calls[0]["timeout_s"] == 6 and calls[0]["prompt_version"] == "proposer@1"


def test_proposer_timeout_retries_once_then_rule(store, decision):
    mate = other_mate(decision)
    good = {"json": {"alternatives": [{"kind": "pass", "actor": "x", "target": mate, "reason": "r"}]}}
    alts, info, calls = _propose(store, decision, [LLMTimeout("6 s"), good])
    assert info["status"] == "ok" and len(calls) == 2
    alts, info, calls = _propose(store, decision, [LLMTimeout("6 s"), LLMError("503")])
    assert info["model"] == "proposer_rule" and alts == proposer_rule(decision) and len(calls) == 2
    alts, info, _ = _propose(store, decision, [{"json": {"alternatives": []}}, {"json": {}}])
    assert info["status"] == "invalid_output" and alts == proposer_rule(decision)


class FakeTools:
    def __init__(self, results, delay=None):
        self.results, self.delay, self.calls = results, delay or {}, []

    async def call(self, name, args):
        self.calls.append(args)
        await asyncio.sleep(self.delay.get(args["n"], 0))
        return self.results[args["alternative"]["target"]]


def cf(target, prob, delta, cid):
    return {"counterfactual_id": cid, "alternative": {"kind": "pass", "actor": "a", "target": target,
                                                      "policy_prob": prob}, "delta_win_prob_home": delta}


def test_choose_largest_delta_with_policy_prob_005():
    results = [cf("p1", 0.30, 0.01, "cf_000001"), cf("p2", 0.04, -0.20, "cf_000002"),
               cf("p3", 0.05, -0.03, "cf_000003"), {"error": "x", "code": "invalid_alternative"}]
    assert choose(results)["counterfactual_id"] == "cf_000003"
    assert choose([results[1], results[3]]) is None


def test_rollout_timeout_falls_back_to_n50():
    tools = FakeTools({"p1": cf("p1", 0.3, 0.02, "cf_000001")}, delay={200: 0.5})
    res, n = arun(simulate(tools, M, 1000, {"kind": "pass", "actor": "a", "target": "p1"}, 0.1))
    assert n == 50 and [c["n"] for c in tools.calls] == [200, 50] and res["counterfactual_id"] == "cf_000001"
    slow = FakeTools({"p1": cf("p1", 0.3, 0.02, "cf_000001")}, delay={200: 0.5, 50: 0.5})
    res, n = arun(simulate(slow, M, 1000, {"kind": "pass", "actor": "a", "target": "p1"}, 0.1))
    assert n == 0 and res["code"] == "timeout"


def test_proposer_and_rollout_in_the_graph(store, moment, decision):
    """Real rollouts on the golden match through the in-process tools; the invalid alternative is skipped."""
    bench = "p_199"
    mate = decision["teammates"][0]["player_id"]
    script = [{"json": {"alternatives": [{"kind": "pass", "actor": "x", "target": mate, "reason": "r"},
                                         {"kind": "carry", "actor": "x", "target": "n", "reason": "r"}]}}]
    deps = Deps(bb=store.bb, llm=FakeClient({"proposer": script}), store=store, rollout=LocalTools(store))
    os.environ["WHYLINE_ROLLOUT_TIMEOUT_S"] = "30"   # the first call re-simulates the match from kick-off
    try:
        wf = build_workflow(deps, overrides={"director": StubDirector("director", deps),
                                             "cuebus": StubCueBus("cuebus", deps)})
        t0 = time.perf_counter()
        arun(run_moment(wf, start_message(moment)))
        print(f"proposer + 2 rollouts: {time.perf_counter() - t0:.1f} s")
    finally:
        del os.environ["WHYLINE_ROLLOUT_TIMEOUT_S"]
    rows = {r["executor"]: r for r in store.bb.query("traces", moment_id="mo_00009")}
    assert rows["proposer"]["alternatives"] == 2 and rows["rollout"]["tried"] == 2
    cfs = store.bb.query("counterfactuals", match_id=M, t_ms=decision["t_ms"])
    assert cfs and all(c["n"] in (200, 50) for c in cfs)
    best = [c for c in cfs if c.get("moment_id") == "mo_00009"]
    if best:  # shown only when its alternative has policy_prob >= 0.05
        assert best[0]["alternative"]["policy_prob"] >= 0.05
    bad = arun(LocalTools(store).call("simulate_counterfactual", {
        "match_id": M, "t_ms": decision["t_ms"], "alternative": {"kind": "pass", "actor": decision["actor"],
                                                                 "target": bench}, "n": 20}))
    assert bad["code"] == "invalid_alternative"


@pytest.mark.live
def test_live_proposer(store, moment, decision):
    from api.spend import SpendGuard

    guard = SpendGuard()
    before = guard.total
    deps = Deps(bb=store.bb, llm=LiveClient(guard, mode="dev"), store=store)
    t0 = time.perf_counter()
    alts, info = arun(propose(deps, start_message(moment), decision))
    print(f"live proposer {time.perf_counter() - t0:.2f} s, {info}, alternatives {alts}")
    assert info["status"] == "ok" and 1 <= len(alts) <= 3
    assert guard.total - before <= 0.20
