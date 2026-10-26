"""Every event is schema-valid, ids are monotonic, events carry player ids only."""

import json
import re
from pathlib import Path

import numpy as np
from jsonschema import Draft202012Validator

from kickoff import Engine
from kickoff.events import EVENT_TYPES
from kickoff.physics_prior import TACKLE_R, to_team
from kickoff.rules import PASS, ScriptedRule

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = Draft202012Validator(json.loads((ROOT / "schemas" / "event.schema.json").read_text()))


def test_every_event_validates(full_match):
    events = full_match["record"].events
    errors = [f"{e['id']}: {err.message}" for e in events for err in VALIDATOR.iter_errors(e)]
    assert not errors, errors[:5]


def test_metadata_first_and_ids_monotonic(full_match):
    events = full_match["record"].events
    assert events[0]["type"] == "match_metadata"
    assert [e["idx"] for e in events] == list(range(1, len(events) + 1))
    assert all(e["id"] == f"e_{e['idx']:04d}" for e in events)
    t = [e["t_ms"] for e in events]
    assert t == sorted(t)


def test_event_types_cover_the_match(full_match):
    seen = {e["type"] for e in full_match["record"].events}
    missing = set(EVENT_TYPES) - seen - {"offside"}          # offside has its own forced test below
    assert not missing, missing


def test_player_ids_only_never_names(full_match, league):
    events = full_match["record"].events
    text = "".join(json.dumps(e, ensure_ascii=False) for e in events)
    for e in events:
        assert e["player"] is None or re.fullmatch(r"p_\d{3}", e["player"])
    names = [p.name for p in league.players.values()]
    assert not [n for n in names if n in text]


def test_foul_geometry_matches_tracking(full_match):
    rec = full_match["record"]
    t_index = {int(t): i for i, t in enumerate(rec.tracking["t_ms"])}
    ids = list(rec.tracking["player_ids"])
    fouls = [e for e in rec.events if e["type"] == "foul"]
    assert fouls
    for f in fouls:
        frame = rec.tracking["S"][t_index[f["t_ms"]]]
        rows = {pid: i for i, pid in enumerate(ids)}
        if f["player"] not in rows or f["attrs"]["fouled_player"] not in rows:
            continue                                              # a substitute: row mapping changed
        a, b = frame[rows[f["player"]], :2], frame[rows[f["attrs"]["fouled_player"]], :2]
        assert np.hypot(*(a - b)) < TACKLE_R + 0.6
        assert np.allclose(f["attrs"]["contact_point"], (a + b) / 2, atol=0.6)
    cards = [e for e in rec.events if e["type"] == "card"]
    assert all(c["attrs"]["colour"] == "yellow" and c["related_event_ids"] for c in cards)


class _ForcePassToCentreForward(ScriptedRule):
    def decide_batch(self, batch):
        out = super().decide_batch(batch)
        out.act[:] = True
        out.kind[:] = PASS
        out.target[:] = 9
        out.lofted[:] = False
        return out


def test_forced_offside_has_consistent_geometry(league):
    engine = Engine(league, league.club_order[0], league.club_order[1], seed=11)
    while not (engine.t_ms > 120_000 and engine.holder[0] >= 0 and engine.holder[0] < 11
               and engine.holder[0] != 9 and not engine.dead[0] and engine.worlds[0].first_touch_restart == ""):
        engine.step()
    away_u, _ = to_team(engine.S[0, 11:22, 0], engine.S[0, 11:22, 1], engine.team_dir(0))
    second_last = float(np.sort(away_u)[-2])
    ball_u = float(to_team(engine.S[0, 22, 0], engine.S[0, 22, 1], engine.team_dir(0))[0])
    line = max(second_last, ball_u, 52.5)
    cf_x = to_team(np.float64(min(line + 4.0, 103.0)), np.float64(34.0), engine.team_dir(0))[0]
    engine.S[0, 9, 0:4] = [float(cf_x), 34.0, 0.0, 0.0]
    engine.model = _ForcePassToCentreForward()
    engine.control_since[0] = 0
    released = engine.step()
    released += [e for w in engine.worlds for e in w.log.release(flush=True)]
    offside = [e for e in released if e.type == "offside"]
    assert len(offside) == 1
    ev = offside[0].to_dict(engine.match_id)
    assert ev["attrs"]["margin_m"] > 0
    assert ev["player"] == engine.worlds[0].row_ids[9]
    assert ev["attrs"]["pass_event_id"].startswith("e_")
    assert engine.dead[0] and engine.worlds[0].restart_kind == "free_kick" and engine.worlds[0].restart_team == 1
    assert VALIDATOR.is_valid(ev)
