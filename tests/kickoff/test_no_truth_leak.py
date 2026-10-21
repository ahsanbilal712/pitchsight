"""No key or string value of truth.json appears in events.jsonl (T-006)."""

import json


def _keys_and_strings(obj, out: set) -> set:
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k)
            _keys_and_strings(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _keys_and_strings(v, out)
    elif isinstance(obj, str):
        out.add(obj)
    return out


def test_truth_keys_and_values_absent_from_events(full_match):
    rec = full_match["record"]
    truth = _keys_and_strings(rec.truth, set())
    events = set()
    for e in rec.events:
        _keys_and_strings(e, events)
    assert truth and not (truth & events), sorted(truth & events)
    text = "".join(json.dumps(e) for e in rec.events)
    for label in {p["label"] for p in rec.truth["phases"]}:
        assert label not in text


def test_truth_has_the_documented_shape(full_match):
    truth = full_match["record"].truth
    assert set(truth) == {"truth_version", "style_profiles", "phases", "momentum"}
    assert truth["phases"] and truth["phases"][0]["start_ms"] == 0
    assert len(truth["momentum"]["H"]) == 91


def test_truth_has_match_regimes(full_match):
    phases = full_match["record"].truth["phases"]
    regimes = [p for p in phases if p["side"] == "M"]
    assert regimes and regimes[0]["start_ms"] == 0 and regimes[-1]["end_ms"] == 90 * 60 * 1000
    assert {p["label"] for p in regimes} <= {"state_settled", "state_transitional", "state_chaotic"}
    assert all(a["end_ms"] == b["start_ms"] and a["label"] != b["label"] for a, b in zip(regimes, regimes[1:]))
