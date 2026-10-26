"""Video edit: every caption number has a source; the v1 edit list is consistent."""

from pathlib import Path

import pytest
import yaml

from demo.assemble import EditError, check_sources, numbers

ROOT = Path(__file__).resolve().parents[2]
EDIT = ROOT / "packages" / "demo" / "edit_v1.yaml"


def test_numbers_in_captions():
    assert numbers("replayed 200 times: +4 points, $2.31 a match, 141 of 141.") == ["200", "+4", "$2.31", "141", "141"]
    assert numbers("No numbers here.") == []


def test_unsourced_number_is_refused():
    edit = {"clips": [{"captions": [{"from": 0, "to": 1, "text": "ninety-seven percent, or 97%"}]}], "sources": {}}
    with pytest.raises(EditError, match="97%"):
        check_sources(edit)


def test_v1_edit_is_sourced_and_under_two_minutes():
    edit = yaml.safe_load(EDIT.read_text())
    check_sources(edit)
    total = sum(float(c["duration"]) if "card" in c else float(c["to"]) - float(c["from"]) for c in edit["clips"])
    assert total < 120
    for c in edit["clips"]:
        dur = float(c["duration"]) if "card" in c else float(c["to"]) - float(c["from"])
        assert all(0 <= cap["from"] < cap["to"] <= dur for cap in c.get("captions", []))
