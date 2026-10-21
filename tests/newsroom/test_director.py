"""Director: budgets and hard rules on a timeline, schema-valid cues, deterministic cue ids, degraded mode (T-021)."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from api.spend import SpendGuard
from blackboard import SqliteBlackboard
from newsroom.executors.base import Deps
from newsroom.executors.director import DirectorExecutor, clock, cue_id_for
from newsroom.factcheck import verify_claims
from newsroom.graph import build_workflow
from newsroom.messages import Draft, Moment
from newsroom.worker import run_moment, start_message


def arun(coro):
    """asyncio.run on a worker thread: Playwright's session-scoped sync API (tests/apps) keeps a loop running in
    the main thread, and asyncio.run refuses to start inside it."""
    with ThreadPoolExecutor(1) as pool:
        return pool.submit(asyncio.run, coro).result()


ROOT = Path(__file__).resolve().parents[2]
M = "m_4242"


def cue_validator():
    registry = Registry()
    schemas = {}
    for p in (ROOT / "schemas").glob("*.schema.json"):
        s = json.loads(p.read_text())
        schemas[p.name] = s
        registry = registry.with_resource(s["$id"], Resource.from_contents(s))
    return Draft202012Validator(schemas["cue.schema.json"], registry=registry)


VALIDATOR = cue_validator()


class Ctx:
    def __init__(self):
        self.sent = []

    async def send_message(self, msg):
        self.sent.append(msg)


@pytest.fixture
def deps(evidence_bb):
    return Deps(bb=evidence_bb)


def draft(n, t_ms, kind="big_chance", branch="fast", layer="lower_third", leverage=0.1, verified=True,
          status="ok", claims=None, **moment):
    m = Moment(moment_id=f"mo_{n:05d}", match_id=M, t_ms=t_ms, kind=moment.pop("mkind", kind), leverage=leverage,
               players=["p_017"], team="home", evidence_event_ids=["e_8812"], period=1, **moment)
    return Draft(run_id=f"run_{n}", branch=branch, moment=m, agent_path=["ingest", "scout"], kind=kind, layer=layer,
                 headline="Okafor shoots", body="A 0.06 xG chance.", why="A 0.06 xG chance.",
                 claims=claims if claims is not None else [
                     {"text": "0.06 xG", "kind": "number", "value": 0.06, "unit": "xg", "evidence_ids": ["e_8812"],
                      "verified": True, "reject_reason": None}],
                 verified=verified, checked=True, attempt=1 if verified else 3, status=status,
                 model="gemini-3.8-flash", prompt_version="narrator@2", trace_id="0af7c2d1e9b84b3f")


def direct(deps, d, director=None):
    """Run one draft through the Director and the CueBus write; returns the cue or None."""
    director = director or DirectorExecutor("director", deps)
    ctx = Ctx()
    arun(director.direct(d, ctx))
    if not ctx.sent:
        return None
    cue = ctx.sent[0].cue
    deps.bb.put("cues", cue)
    return cue


def event(bb, eid, t_ms, typ):
    bb.put("events", {"id": eid, "match_id": M, "t_ms": t_ms, "type": typ, "period": 1})


# ---------------------------------------------------------------- schema and ids

def test_cues_validate_against_the_schema(deps, evidence_bb):
    cf = evidence_bb.get("counterfactuals", "cf_000077")
    exp = {"explanation_id": "ex_000077", "why": "x"}
    sd = draft(77, 1_000_000, kind="sliding_doors", branch="explained").model_copy(
        update={"counterfactual": cf, "explanation": exp})
    for d in (draft(12, 600_000), sd, draft(30, 1_200_000, verified=False), draft(40, 1_400_000, status="error")):
        cue = direct(deps, d)
        errors = [e.message for e in VALIDATOR.iter_errors(cue)]
        assert not errors, (cue, errors)
    assert sd and evidence_bb.get("cues", "c_000771")["graphics"]["bar"]["from"] == 0.42


def test_cue_id_depends_only_on_moment_and_branch(tmp_path):
    assert cue_id_for("mo_00077", "explained") == "c_000771" and cue_id_for("mo_00077", "fast") == "c_000770"
    ids = []
    for order in ([12, 30], [30, 12]):  # processing order and process state do not matter
        bb = SqliteBlackboard(tmp_path / f"bb{order[0]}.sqlite")
        d = Deps(bb=bb)
        ids.append({n: direct(d, draft(n, n * 60_000))["cue_id"] for n in order})
        bb.close()
    assert ids[0] == ids[1] == {12: "c_000120", 30: "c_000300"}


def test_clock_format():
    assert clock(1_878_200) == "31:18" and clock(0) == "00:00" and clock(5_430_000) == "90:30"


# ---------------------------------------------------------------- hard rules

def test_no_overlay_during_a_shot_sequence(deps, evidence_bb):
    event(evidence_bb, "e_9001", 2_000_000, "shot")
    event(evidence_bb, "e_9002", 2_002_500, "possession_change")
    assert direct(deps, draft(50, 2_000_000))["t_in_ms"] == 2_002_500       # waits for the possession change
    event(evidence_bb, "e_9003", 2_300_000, "shot")                        # nothing ends it: max 6 s
    assert direct(deps, draft(51, 2_300_500, kind="goal"))["t_in_ms"] == 2_306_000


def test_no_overlay_within_3s_after_a_goal(deps, evidence_bb):
    event(evidence_bb, "e_9010", 3_000_000, "goal")
    assert direct(deps, draft(60, 3_001_000, kind="goal"))["t_in_ms"] == 3_003_000
    assert direct(deps, draft(61, 3_200_000, kind="milestone"))["t_in_ms"] == 3_200_000


def test_same_kind_dedupe_90s(deps):
    assert direct(deps, draft(70, 4_000_000)) is not None
    assert direct(deps, draft(71, 4_060_000)) is None                      # 60 s later, same kind: dropped
    assert direct(deps, draft(72, 4_095_000)) is not None                  # 95 s later


def test_unshown_cue_expires_after_45s(deps):
    deps.state["match_clock_ms"] = 5_050_000
    assert direct(deps, draft(80, 5_000_000)) is None                      # 50 s old by the time it is ready
    deps.state["match_clock_ms"] = 5_040_000
    assert direct(deps, draft(81, 5_000_000, kind="goal")) is not None


def test_sliding_doors_needs_leverage_004(deps):
    assert direct(deps, draft(90, 6_000_000, kind="sliding_doors", branch="explained", leverage=0.03)) is None
    assert direct(deps, draft(91, 6_000_000, kind="sliding_doors", branch="explained", leverage=0.05)) is not None


def test_oracle_needs_p_shot_030(deps):
    assert direct(deps, draft(100, 6_500_000, kind="oracle", p_shot=0.25)) is None
    cue = direct(deps, draft(101, 6_500_000, kind="oracle", p_shot=0.35))
    assert cue is not None and cue["targets"]["modes"] == ["analyst", "studio"]


# ---------------------------------------------------------------- per-mode budgets

def test_min_gap_between_lower_thirds_per_mode(deps):
    first = direct(deps, draft(110, 7_000_000, kind="sliding_doors", branch="explained"))
    assert first["targets"]["modes"] == ["analyst", "casual", "player_cam", "studio"]
    second = direct(deps, draft(111, 7_025_000, kind="goal"))               # 25 s later
    assert second["targets"]["modes"] == ["player_cam", "studio"]          # analyst 30 s, casual 60 s; cam 20 s


def test_max_per_10min_casual(deps):
    kinds = ["goal", "big_chance", "milestone", "fourth_official", "sliding_doors", "goal", "big_chance"]
    shown = []
    for i, k in enumerate(kinds):
        cue = direct(deps, draft(120 + i, 8_000_000 + i * 61_000, kind=k, leverage=0.2,
                                 branch="explained" if k == "sliding_doors" else "fast"))
        shown.append("casual" in cue["targets"]["modes"])
    assert shown == [True] * 6 + [False]                                   # casual max 6 per 10 minutes


def test_casual_sliding_doors_per_half(deps):
    casual = []
    for i in range(3):
        cue = direct(deps, draft(130 + i, 9_000_000 + i * 200_000, kind="sliding_doors", branch="explained"))
        casual.append("casual" in cue["targets"]["modes"])
    assert casual == [True, True, False]


def test_kind_not_in_mode(deps):
    cue = direct(deps, draft(140, 9_800_000, kind="tempo_shift"))
    assert cue["targets"]["modes"] == ["analyst", "studio"]


# ---------------------------------------------------------------- failures and degraded mode

def test_model_error_or_cache_miss_gives_template_and_red_trace(deps, evidence_bb):
    cue = direct(deps, draft(150, 10_000_000, status="cache_miss"))
    assert cue["provenance"]["model"] == "template" and cue["text"]["body"] == "Chance quality: 0.06 xG."
    row = evidence_bb.query("traces", executor="director", moment_id="mo_00150")[0]
    assert row["status"] == "cache_miss"


def test_third_rejection_uses_template_from_verified_claims(deps, evidence_bb):
    claims = [{"text": "0.06 xG", "kind": "number", "value": 0.06, "unit": "xg", "evidence_ids": ["e_8812"],
               "verified": True, "reject_reason": None},
              {"text": "0.50 xG", "kind": "number", "value": 0.5, "unit": "xg", "evidence_ids": ["e_8812"],
               "verified": False, "reject_reason": "value_out_of_tolerance"}]
    cue = direct(deps, draft(160, 10_500_000, verified=False, claims=claims))
    assert "0.50" not in cue["text"]["body"] and cue["verified"] is True
    assert [c["text"] for c in cue["explain"]["claims"]] == ["0.06 xG"]
    r = verify_claims(M, cue["explain"]["claims"], evidence_bb, cue["text"])
    assert r["verified"]


def test_spend_cap_switches_to_degraded(tmp_path, evidence_bb):
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(json.dumps({"ts": "2026-10-21T10:00:00Z", "role": "x", "model": "gemini-4-argon",
                                  "tokens_in": 0, "tokens_out": 0, "cost_usd": 2.5, "match_id": M,
                                  "mode": "live"}) + "\n")
    deps = Deps(bb=evidence_bb, guard=SpendGuard(ledger_path=ledger), mode="live")
    cue = direct(deps, draft(170, 11_000_000))
    assert cue["provenance"]["mode"] == "degraded" and deps.state["degraded"]
    assert evidence_bb.query("modes", match_id=M)[0]["mode"] == "degraded"
    direct(deps, draft(171, 11_200_000, kind="goal"))
    assert len(evidence_bb.query("modes", match_id=M)) == 1                # announced once


def test_director_in_the_graph(evidence_bb):
    deps = Deps(bb=evidence_bb)
    moment = {"moment_id": "mo_00077", "match_id": M, "t_ms": 1874000, "kind": "big_chance", "xg": 0.31, "leverage": 0.02,
              "players": ["p_017"], "team": "home", "evidence_event_ids": ["e_8812"], "fast": True}
    cue = arun(run_moment(build_workflow(deps), start_message(moment)))["outputs"][0]
    assert not list(VALIDATOR.iter_errors(cue))
    assert cue["cue_id"] == "c_000770" and cue["provenance"]["agent_path"][-2:] == ["director", "cuebus"]
    assert evidence_bb.get("cues", "c_000770")["verified"] is True
