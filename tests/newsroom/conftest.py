"""Fixture evidence for newsroom tests: the golden match lineups plus the schema-example moment at 31:14
(Silva -> Okafor pass e_8809, Reyes' run e_8811, Okafor's shot e_8812, counterfactual cf_000077,
pitch-control snapshot pc_000412) and three facts."""

import json
from pathlib import Path

import pytest

from blackboard import SqliteBlackboard

ROOT = Path(__file__).resolve().parents[2]


def _example(name: str, i: int = 0) -> dict:
    return json.loads((ROOT / "schemas" / f"{name}.schema.json").read_text())["examples"][i]


def seed_evidence(bb) -> None:
    meta = json.loads((ROOT / "data/matches/4242/events.jsonl").read_text().splitlines()[0])
    bb.put("events", meta)
    bb.put("events", _example("event", 0))
    bb.put("events", {"schema_version": "1.0.0", "id": "e_8811", "match_id": "m_4242", "idx": 8811,
                      "t_ms": 1873600, "period": 1, "clock": "31:13", "type": "carry", "team": "home",
                      "player": "p_031", "location": [92.0, 40.0], "end_location": [98.9, 39.8],
                      "outcome": "complete", "under_pressure": False, "related_event_ids": [],
                      "attrs": {"distance_m": 6.9, "progressive_m": 6.9}})
    bb.put("events", _example("event", 1))
    bb.put("counterfactuals", _example("counterfactual"))
    bb.put("pitch_control", {"snapshot_id": "pc_000412", "match_id": "m_4242", "t_ms": 1873800,
                             "home_share": 0.56, "contested_frac": 0.18,
                             "zones": {"overload_right": {"home": 2, "away": 1}, "right_half_space": "home"}})
    bb.put("facts", {"fact_id": "f_000001", "match_id": "m_4242", "t_ms": 1874000, "kind": "stat",
                     "name": "alternative_shot_xg", "value": 0.31, "unit": "xg", "window_s": 0,
                     "counterfactual_id": "cf_000077", "evidence_event_ids": ["e_8812"]})
    bb.put("facts", {"fact_id": "f_000002", "match_id": "m_4242", "t_ms": 1873600, "kind": "stat",
                     "name": "top_speed", "value": 33.4, "unit": "kmh", "window_s": 10, "players": ["p_031"],
                     "evidence_event_ids": ["e_8811"]})
    bb.put("facts", {"fact_id": "f_000003", "match_id": "m_4242", "t_ms": 1860000, "kind": "state",
                     "name": "cluster", "value": "high_press", "unit": None, "window_s": 60,
                     "label": "high_press", "evidence_event_ids": []})


@pytest.fixture
def evidence_bb(tmp_path):
    bb = SqliteBlackboard(tmp_path / "evidence.sqlite")
    seed_evidence(bb)
    yield bb
    bb.close()


@pytest.fixture
def explanation_example():
    return _example("explanation")
