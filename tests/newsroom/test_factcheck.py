"""Fact Checker: one passing and one failing test per TECH_PLAN 1.7 rule, every tolerance (T-019)."""

import asyncio
import time

import pytest

from newsroom.executors.base import Deps
from newsroom.executors.factcheck import FactCheckExecutor
from newsroom.factcheck import BannedMatcher, banned_matcher, verify_claims
from newsroom.graph import build_workflow
from newsroom.worker import run_moment, start_message

M = "m_4242"


def claim(text, kind="number", value=None, unit=None, ids=("e_8812",)):
    return {"text": text, "kind": kind, "value": value, "unit": unit, "evidence_ids": list(ids), "verified": False}


def one(bb, c, text=None):
    r = verify_claims(M, [c], bb, text)
    return r["claims"][0]["reject_reason"], r


# ---------------------------------------------------------------- acceptance: the schema example verifies

def test_explanation_example_verifies_under_50ms(evidence_bb, explanation_example):
    ex = explanation_example
    verify_claims(M, ex["claims"], evidence_bb, {"why": ex["why"]})  # warm the league and matcher caches
    t0 = time.perf_counter()
    r = verify_claims(M, ex["claims"], evidence_bb, {"why": ex["why"]})
    ms = (time.perf_counter() - t0) * 1000
    print(f"verify_claims on the example: {ms:.2f} ms")
    assert r["verified"], r["diff"]
    assert all(c["verified"] and c["reject_reason"] is None for c in r["claims"])
    assert ms < 50


# ---------------------------------------------------------------- rule 1: evidence resolves

def test_rule1_evidence_resolves(evidence_bb):
    assert one(evidence_bb, claim("0.06 xG", value=0.06, unit="xg"))[0] is None


def test_rule1_missing_evidence_rejected(evidence_bb):
    reason, r = one(evidence_bb, claim("0.06 xG", value=0.06, unit="xg", ids=["e_9999"]))
    assert reason == "evidence_not_found" and r["diff"][0]["missing"] == ["e_9999"]
    assert one(evidence_bb, claim("0.06 xG", value=0.06, unit="xg", ids=[]))[0] == "no_evidence"


# ---------------------------------------------------------------- rule 2: numbers within tolerance

@pytest.mark.parametrize("text,value,unit,ids", [
    ("0.06 xG", 0.06, "xg", ["e_8812"]),
    ("0.064 xG", 0.064, "xg", ["e_8812"]),                      # xG +-0.005
    ("0.31 xG", 0.31, "xg", ["cf_000077"]),                     # derived fact linked to the counterfactual
    ("11%", 0.11, "p_goal", ["cf_000077"]),
    ("28%", 0.28, "p_goal", ["cf_000077"]),                     # probabilities +-0.01
    ("51%", 0.51, "win_prob", ["cf_000077"]),
    ("59%", 0.59, "percent", ["e_8809"]),                       # pass_completion_p 0.59
    ("18 metres", 18.0, "metres", ["e_8812"]),                  # distance 18.1, +-0.5 m
    ("18.4 m", 18.4, "m", ["e_8809"]),
    ("94 km/h", 94.0, "kmh", ["e_8812"]),                       # shot speed 94.3, +-1 km/h
    ("34 km/h", 34.0, "kmh", ["f_000002"]),                     # sprint 33.4
    ("42% to 51%", 0.09, "win_prob_delta", ["cf_000077"]),
    ("+9 points", 0.09, "win_prob_delta", ["cf_000077"]),
    ("0.03 xT", 0.031, "xt", ["cf_000077"]),
    ("200 replays", 200, "count", ["cf_000077"]),
    ("8 seconds", 8, "seconds", ["cf_000077"]),
])
def test_rule2_number_within_tolerance(evidence_bb, text, value, unit, ids):
    assert one(evidence_bb, claim(text, value=value, unit=unit, ids=ids))[0] is None


@pytest.mark.parametrize("text,value,unit,ids,reason", [
    ("0.066 xG", 0.066, "xg", ["e_8812"], "value_out_of_tolerance"),
    ("13%", 0.13, "p_goal", ["cf_000077"], "value_out_of_tolerance"),
    ("53%", 0.53, "win_prob", ["cf_000077"], "value_out_of_tolerance"),
    ("19 metres", 19.0, "metres", ["e_8812"], "value_out_of_tolerance"),
    ("96 km/h", 96.0, "kmh", ["e_8812"], "value_out_of_tolerance"),
    ("42% to 53%", 0.11, "win_prob_delta", ["cf_000077"], "value_out_of_tolerance"),
    ("40% to 49%", 0.09, "win_prob_delta", ["cf_000077"], "text_value_mismatch"),
    ("+9 points", 0.09, "win_prob_delta", ["e_8812"], "win_prob_delta_needs_counterfactual"),
    ("0.04 xT", 0.04, "xt", ["cf_000077"], "value_out_of_tolerance"),
    ("199 replays", 199, "count", ["cf_000077"], "value_out_of_tolerance"),
    ("0.31 xG", 0.06, "xg", ["e_8812"], "text_value_mismatch"),
    ("a big chance", 0.06, "xg", ["e_8812"], "no_number_in_text"),
    ("94 km/h", 94.0, "kmh", ["cf_000077"], "no_evidence_for_unit"),
    ("3 furlongs", 3, "furlongs", ["e_8812"], "unit_not_supported"),
])
def test_rule2_number_rejected(evidence_bb, text, value, unit, ids, reason):
    assert one(evidence_bb, claim(text, value=value, unit=unit, ids=ids))[0] == reason


# ---------------------------------------------------------------- rule 3: players and teams

def test_rule3_player_in_lineup_and_evidence(evidence_bb):
    assert one(evidence_bb, claim("Okafor", "player", "p_017"))[0] is None
    assert one(evidence_bb, claim("Reyes", "player", "p_031"))[0] is None          # via related e_8811
    assert one(evidence_bb, claim("Reyes", "player", "p_031", ids=["cf_000077"]))[0] is None
    assert one(evidence_bb, claim("Verdant", "team", "verdant"))[0] is None
    assert one(evidence_bb, claim("Verdant Athletic", "team", "home"))[0] is None


def test_rule3_player_and_team_rejected(evidence_bb):
    assert one(evidence_bb, claim("Okafor", "player", "p_031"))[0] == "player_name_mismatch"
    assert one(evidence_bb, claim("Fennimore", "player", "p_001"))[0] == "player_not_in_evidence"
    assert one(evidence_bb, claim("X", "player", "p_100"))[0] == "player_not_in_lineup"
    assert one(evidence_bb, claim("X", "player", "p_999"))[0] == "unknown_player"
    assert one(evidence_bb, claim("Saltmarsh", "team", "saltmarsh"))[0] == "team_not_in_match"
    assert one(evidence_bb, claim("Ironvale", "team", "verdant"))[0] == "team_name_mismatch"


# ---------------------------------------------------------------- rule 4: minutes within 1

@pytest.mark.parametrize("value", [31, 32])
def test_rule4_minute_within_one(evidence_bb, value):
    assert one(evidence_bb, claim(f"{value}th minute", "minute", value))[0] is None


@pytest.mark.parametrize("value", [30 - 1, 33])
def test_rule4_minute_rejected(evidence_bb, value):
    assert one(evidence_bb, claim(f"{value}th minute", "minute", value))[0] == "minute_out_of_range"


# ---------------------------------------------------------------- rule 5: tactical patterns

def test_rule5_tactical_pattern_in_snapshot_or_fact(evidence_bb):
    assert one(evidence_bb, claim("2v1 overload on the right", "tactical", "overload_right", None,
                                  ["pc_000412"]))[0] is None
    assert one(evidence_bb, claim("high press", "tactical", "high_press", None, ["f_000003"]))[0] is None


def test_rule5_tactical_rejected(evidence_bb):
    assert one(evidence_bb, claim("low block", "tactical", "low_block", None,
                                  ["pc_000412"]))[0] == "tactical_pattern_not_found"
    assert one(evidence_bb, claim("overload", "tactical", "overload_right", None,
                                  ["e_8812"]))[0] == "tactical_needs_pc_or_fact"


# ---------------------------------------------------------------- rule 6: unbound numbers

def test_rule6_numbers_bound_to_verified_claims(evidence_bb):
    c = claim("0.06 xG", value=0.06, unit="xg")
    r = verify_claims(M, [c], evidence_bb, {"headline": "Okafor shoots", "body": "A shot worth 0.06 xG."})
    assert r["verified"] and r["diff"] == []


def test_rule6_unbound_number_rejected(evidence_bb):
    c = claim("0.06 xG", value=0.06, unit="xg")
    r = verify_claims(M, [c], evidence_bb, {"body": "In 200 replays the shot was worth 0.06 xG."})
    assert not r["verified"]
    assert r["diff"] == [{"where": "body", "token": "200", "reject_reason": "unbound_number"}]
    bad = claim("0.07 xG", value=0.07, unit="xg")  # rejected claim does not bind its number
    r = verify_claims(M, [bad], evidence_bb, {"why": "Worth 0.07 xG."})
    assert {d["reject_reason"] for d in r["diff"]} == {"value_out_of_tolerance", "unbound_number"}


# ---------------------------------------------------------------- rule 7: banned content

def test_rule7_clean_copy_passes(evidence_bb):
    r = verify_claims(M, [], evidence_bb, {"body": "Better options existed; the betting-free studio agrees."})
    assert r["verified"]


@pytest.mark.parametrize("text,category", [
    ("The odds were long.", "betting"), ("Fans will bet on Verdant.", "betting"),
    ("He looks injured after that.", "injury_speculation"), ("A hamstring strain, surely.", "injury_speculation"),
    ("Another biased referee decision.", "referee_bias"), ("The ref favours Ironvale.", "referee_bias"),
    ("Like Arsenal in their pomp.", "real_name"), ("A finish worthy of manchester united", "real_name"),
])
def test_rule7_banned_content_rejected(evidence_bb, text, category):
    r = verify_claims(M, [], evidence_bb, {"body": text})
    assert not r["verified"] and r["diff"][0]["category"] == category
    assert one(evidence_bb, claim("Arsenal", "team", "verdant"))[0] in ("banned_content", "team_name_mismatch")


def test_rule7_matcher_is_whole_phrase():
    m = BannedMatcher(["Silva Junior"])
    assert m.find("silva junior scores") and not m.find("Silva scores") and not m.find("a better alphabet")
    assert banned_matcher().find("Verdant Athletic") == []


# ---------------------------------------------------------------- rule 8: rejection carries reasons and a diff

def test_rule8_rejection_has_reasons_and_diff(evidence_bb, explanation_example):
    claims = [dict(c) for c in explanation_example["claims"]]
    claims[1] = {**claims[1], "text": "0.41 xG", "value": 0.41}
    r = verify_claims(M, claims, evidence_bb, {"why": explanation_example["why"]})
    assert not r["verified"]
    assert [c["verified"] for c in r["claims"]] == [True, False, True, True, True]
    assert r["claims"][1]["reject_reason"] == "value_out_of_tolerance"
    assert r["diff"] == [{"where": "claims[1]", "text": "0.41 xG", "reject_reason": "value_out_of_tolerance"}]


def test_rule8_accepted_has_no_diff(evidence_bb, explanation_example):
    r = verify_claims(M, explanation_example["claims"], evidence_bb)
    assert r["verified"] and r["diff"] == []


# ---------------------------------------------------------------- the executor in the graph

def test_executor_rejects_unbound_numbers_until_attempt_3(evidence_bb):
    deps = Deps(bb=evidence_bb)
    wf = build_workflow(deps, overrides={"factcheck": FactCheckExecutor("factcheck", deps)})
    moment = {"moment_id": "mo_00077", "match_id": M, "t_ms": 1878200, "clock": "31:18", "kind": "big_chance",
              "fast": False}
    cue = asyncio.run(run_moment(wf, start_message(moment)))["outputs"][0]
    assert cue["attempt"] == 3 and cue["verified"] is False   # "Big chance at 31:18." binds no claims
    goal = {**moment, "moment_id": "mo_00078", "kind": "goal", "fast": True}
    cue = asyncio.run(run_moment(wf, start_message(goal)))["outputs"][0]
    assert cue["verified"] is True
    rows = evidence_bb.query("traces", executor="factcheck")
    assert [r["status"] for r in rows] == ["rejected"] * 3 + ["verified"]
