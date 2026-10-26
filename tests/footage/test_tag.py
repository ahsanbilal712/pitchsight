"""Gemini tagging: converting the model's per-segment answers into event.schema.json events. No model call."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from footage.clips import CLIPS
from footage.tag import RESPONSE_SCHEMA, mmss_ms, side, to_events

SCHEMA = json.loads((Path(__file__).resolve().parents[2] / "schemas" / "event.schema.json").read_text())


def tag(segment, start_s, events):
    return {"segment": segment, "start_s": start_s, "events": events}


def ev(clip_time, clock, type_, team="Liverpool", player="", outcome="n/a", replay=False):
    return {"clip_time": clip_time, "match_clock": clock, "type": type_, "team": team, "player": player,
            "outcome": outcome, "replay": replay, "note": ""}


def test_events_validate_drop_replays_and_carry_the_clock():
    tags = [tag(0, 0.0, [ev("00:10", "84:00", "shot", player="Dominik Szoboszlai", outcome="blocked"),
                         ev("00:20", "", "clearance", team="Manchester City"),
                         ev("00:30", "84:20", "goal", replay=True)]),
            tag(1, 180.0, [ev("00:05", "87:05", "card", team="Man City", player="Bernardo Silva")])]
    events, counts = to_events("liverpool-mancity-2526", tags)
    assert counts == {"tagged": 4, "replays_dropped": 1, "events": 3}
    validator = Draft202012Validator(SCHEMA)
    assert all(not list(validator.iter_errors(e)) for e in events)
    shot, clear, card = events
    assert (shot["clock"], shot["period"], shot["team"], shot["attrs"]["player_name"]) == ("84:00", 2, "home",
                                                                                          "Dominik Szoboszlai")
    assert clear["t_ms"] == 84 * 60_000 + 10_000 and clear["attrs"]["clock_source"] == "carried"
    assert card["team"] == "away" and card["attrs"]["clip_ms"] == 185_000 and card["match_id"] == "m_9001"
    assert [e["id"] for e in events] == ["e_0001", "e_0002", "e_0003"]


def test_segment_boundary_duplicate_is_merged():
    tags = [tag(0, 0.0, [ev("02:59", "10:00", "shot", player="Salah")]),
            tag(1, 180.0, [ev("00:00", "10:01", "shot", player="Salah")])]
    assert len(to_events("liverpool-mancity-2526", tags)[0]) == 1


def test_side_matches_club_names_loosely():
    utd = CLIPS["manutd-mancity-2526"]
    assert side("Man Utd", utd) == "home" and side("Man City", utd) == "away" and side("", utd) == "none"
    spurs = CLIPS["manutd-spurs-2425"]
    assert side("Spurs", spurs) == "away" and side("Tottenham", spurs) == "away" and side("Man Utd", spurs) == "home"
    assert side("Arsenal", CLIPS["arsenal-chelsea-2526"]) == "home"


def test_mmss_and_schema_have_no_type_arrays():
    assert mmss_ms("93:12") == 5_592_000 and mmss_ms("") is None and mmss_ms("1:02") == 62_000
    assert "type': [" not in str(RESPONSE_SCHEMA)        # Gemini rejects type arrays
