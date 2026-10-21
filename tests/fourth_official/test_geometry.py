"""Fourth Official geometry on hand-built frames (T-049): onside/offside by 0.4 m, level is onside, own-half
exception, foul in/out of the box; each check < 5 ms; the golden match's offsides re-derive to the event margins."""

import json
import time
from pathlib import Path

import jsonschema
import numpy as np
import pytest

from fourth_official import check_foul, check_offside, ruling_to_cue
from physics import TrackingWindow
from physics.window import Frame

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "data" / "matches" / "4242"
IDS = np.array([f"p_{i:03d}" for i in range(1, 23)])
SCHEMA = json.loads((ROOT / "schemas" / "cue.schema.json").read_text())


def frame(receiver_x: float, second_last_x: float, period: int = 1, ball_x: float = 50.0) -> Frame:
    """Home attacks +x in period 1. Home passer (row 5) at ball_x; home receiver row 9; away keeper row 11 at 103,
    away second-last defender row 12 at second_last_x, other away players deeper in their half than... behind him."""
    S = np.zeros((23, 6))
    S[:11, 0], S[:11, 1] = 30.0, np.linspace(5, 63, 11)
    S[5, 0:2] = [ball_x, 34.0]
    S[9, 0:2] = [receiver_x, 30.0]
    S[11:22, 0], S[11:22, 1] = 60.0, np.linspace(5, 63, 11)
    S[11, 0:2] = [103.0, 34.0]
    S[12, 0:2] = [second_last_x, 40.0]
    S[22, 0:2] = S[5, 0:2]
    if period == 2:                                           # mirror: home attacks -x
        S[:, 0], S[:, 1] = 105.0 - S[:, 0], 68.0 - S[:, 1]
    return Frame(t_ms=600_000 if period == 1 else 3_000_000, period=period, S=S, ball_z=0.11, holder=5, possession=0,
                 player_ids=IDS)


def pass_ev(t: int = 600_100) -> dict:
    return {"id": "e_0100", "type": "pass", "t_ms": t, "team": "home", "player": "p_006", "period": 1,
            "attrs": {"recipient": "p_010"}}


@pytest.mark.parametrize("period", [1, 2])
def test_offside_by_0_4_m(period):
    r = check_offside(frame(80.4, 80.0, period), pass_ev())
    assert r.offside and r.margin_m == pytest.approx(0.4) and r.last_defender == "p_013"
    expected_x = 80.0 if period == 1 else 25.0
    assert r.line == [[pytest.approx(expected_x), 0.0], [pytest.approx(expected_x), 68.0]]


def test_onside_by_0_4_m():
    r = check_offside(frame(79.6, 80.0), pass_ev())
    assert not r.offside and r.margin_m == pytest.approx(-0.4) and r.reason == "onside"


def test_level_is_onside():
    r = check_offside(frame(80.0, 80.0), pass_ev())
    assert not r.offside and r.reason == "level"


def test_own_half_exception():
    r = check_offside(frame(50.0, 40.0, ball_x=30.0), pass_ev())       # beyond a deep defender but in his own half
    assert not r.offside and r.reason == "own_half"


def test_restart_exemption_and_not_a_pass():
    assert not check_offside(frame(85.0, 80.0), pass_ev(), restart_kind="throw_in").offside
    assert check_offside(frame(85.0, 80.0), {**pass_ev(), "type": "shot"}) is None


def foul_window(contact_x: float) -> tuple[TrackingWindow, list[dict]]:
    n = 30
    S = np.zeros((n, 23, 6))
    S[:, :22, 1] = np.tile(np.linspace(5, 63, 11), 2)
    S[:, :11, 0], S[:, 11:22, 0] = 40.0, 70.0
    S[:, 15, 0:2] = [contact_x - 0.5, 34.0]          # away defender (fouler) running at...
    S[:, 15, 2] = 4.0
    S[:, 9, 0:2] = [contact_x + 0.5, 34.0]           # ...the home attacker
    w = TrackingWindow(t_ms=600_000 + 100 * np.arange(n), period=np.ones(n, dtype=np.int8), S=S,
                       ball_z=np.full(n, 0.11), holder=np.full(n, 9, dtype=np.int16), possession=np.zeros(n, dtype=np.int8),
                       player_ids=IDS)
    ev = [{"id": "e_0200", "type": "foul", "t_ms": 601_500, "team": "away", "player": "p_016", "period": 1,
           "location": [contact_x, 34.0], "attrs": {"contact_point": [contact_x, 34.0], "fouled_player": "p_010"},
           "related_event_ids": []},
          {"id": "e_0201", "type": "card", "t_ms": 601_500, "team": "away", "player": "p_016", "period": 1,
           "attrs": {"colour": "yellow"}, "related_event_ids": ["e_0200"]}]
    return w, ev


def test_foul_in_and_out_of_the_box():
    w, ev = foul_window(95.0)                          # away defends the +x goal in period 1
    r = check_foul(ev, w)
    assert r.in_box and r.card == "yellow" and r.closing_speed_ms == pytest.approx(4.0)
    w, ev = foul_window(85.0)
    assert not check_foul(ev, w).in_box


def test_each_check_under_5_ms():
    f, p = frame(80.4, 80.0), pass_ev()
    w, ev = foul_window(95.0)
    for fn in (lambda: check_offside(f, p), lambda: check_foul(ev, w)):
        fn()
        times = []
        for _ in range(50):
            t = time.perf_counter()
            fn()
            times.append((time.perf_counter() - t) * 1000)
        assert np.percentile(times, 95) < 5.0


def test_cues_validate_and_cite_events():
    validator = jsonschema.Draft202012Validator(SCHEMA, registry=_registry())
    off = ruling_to_cue(check_offside(frame(80.4, 80.0), pass_ev()), 600_100, evidence_event_id="e_0101")
    validator.validate(off)
    assert off["verified"] and off["layer"] == "referee_line" and off["graphics"]["lines"]
    assert "0.4 m" in off["text"]["body"] and off["explain"]["claims"][0]["evidence_ids"] == ["e_0101"]
    w, ev = foul_window(95.0)
    validator.validate(ruling_to_cue(check_foul(ev, w), 601_500))


def test_golden_offsides_re_derive():
    w = TrackingWindow.load(GOLDEN)
    events = [json.loads(line) for line in (GOLDEN / "events.jsonl").read_text().splitlines()]
    byid = {e["id"]: e for e in events}
    offsides = [e for e in events if e["type"] == "offside"]
    assert offsides
    for o in offsides:
        p = byid[o["attrs"]["pass_event_id"]]
        r = check_offside(w.frame_at(p["t_ms"] - 100), p)
        assert r.offside and r.margin_m == pytest.approx(o["attrs"]["margin_m"], abs=0.01)
        assert r.last_defender == o["attrs"]["last_defender"]


def _registry():
    from referencing import Registry, Resource
    reg = Registry()
    for path in (ROOT / "schemas").glob("*.schema.json"):
        doc = json.loads(path.read_text())
        res = Resource.from_contents(doc)
        reg = reg.with_resource(doc["$id"], res).with_resource(path.name, res)
    return reg
