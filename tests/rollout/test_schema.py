"""sliding_doors output validates against schemas/counterfactual.schema.json; illegal branches raise (T-016)."""

import json
from pathlib import Path

import jsonschema
import pytest

from kickoff import Action, BranchError, Override
from rollout import rollout, sliding_doors

SCHEMA = json.loads((Path(__file__).resolve().parents[2] / "schemas" / "counterfactual.schema.json").read_text())


def test_sliding_doors_validates(golden, decision_t):
    actor = next(e for e in golden.events() if e["t_ms"] == decision_t + 100 and e["type"] == "pass")["player"]
    cf = sliding_doors(golden, decision_t, {"kind": "shoot", "actor": actor, "target": None}, n=50)
    jsonschema.validate(cf, SCHEMA)
    assert cf["engine"] == "scripted_v1" and cf["n"] == 50 and cf["horizon_s"] == 8 and cf["seed"] == 4242
    assert cf["actual"]["kind"] == "pass" and cf["actual"]["actor"] == actor
    assert len(cf["futures_sample"]) == 50 and len(cf["futures_sample"][0]) == 9
    assert abs(cf["delta_win_prob_home"] - (cf["alternative_outcome"]["win_prob_home"]
                                            - cf["baseline"]["win_prob_home"])) < 2e-4


def test_illegal_alternatives(golden, decision_t):
    st = golden.state_at(decision_t)
    bad = rollout(st, Override(first_action=Action(kind="pass", target=99)), 8, 8, seed=1)
    assert bad.invalid_reason
    with pytest.raises(BranchError):
        sliding_doors(golden, decision_t, Action(kind="pass", target=99), n=50)


def test_policy_horizon_capped(golden, decision_t):
    with pytest.raises(ValueError):
        rollout(golden.state_at(decision_t), None, 8, 9, seed=1, engine="policy_v1")
