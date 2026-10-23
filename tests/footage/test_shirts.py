"""Shirt numbers (video v6): a number needs consistent crops, a squad list to name it, and one owner per moment.
Committed reads only, no model call."""

from footage.names import verify
from footage.shirts import squad, vote


def test_vote_needs_agreeing_crops_and_no_rival():
    assert vote([{"number": 19}] * 8)["number"] == 19
    assert vote([{"number": 18}, {"number": 18}, {"number": None}] * 1)["number"] is None        # 2 reads only
    assert vote([{"number": 7}] * 4 + [{"number": 1}] * 2)["consistent"] is False              # a rival twice
    assert vote([{"number": None}] * 8)["why"] == "no crop shows a number"


def test_squad_lists_carry_their_source():
    sq = squad("manutd-mancity-2526", "home")
    assert sq["numbers"]["19"] == "Bryan Mbeumo" and sq["season"] == "2025-26" and sq["source"].startswith("https://")
    assert squad("manutd-spurs-2425", "away")["numbers"]["16"] == "Timo Werner"              # 2024/25 list


def test_shirt_reads_name_players_once_per_moment():
    d = verify("manutd-mancity-2526")
    assert {"clip_ms": 877000, "label": "#19", "track_id": 4} in d["names"]["Bryan Mbeumo"]["links"]
    ars = verify("arsenal-chelsea-2526")
    assert any(r.get("label") == "A6" and "two players cannot share" in r["why"] for r in ars["rejected"])
    assert verify("liverpool-mancity-2526")["shots"]["e_0065"]["name"] == "Hugo Ekitike"     # tagger said Mac Allister


def test_a_hand_label_gives_a_live_window_only_without_a_rival_read():
    import json
    from pathlib import Path

    r = json.loads((Path(__file__).resolve().parents[2] / "data/footage/manutd-mancity-2526/cache/v6/names_live_0.json")
                   .read_text())["result"]["players"]
    amad = [p for p in r if p["name"] == "Amad"]
    assert [(p["track_id"], p["from_clip_ms"], p["to_clip_ms"], p["shirt"]) for p in amad] == [(19, 875500, 878500, 16)]
    assert not any(p["name"] == "Casemiro" and p["track_id"] == 16 for p in r)   # t16 also reads 19 in the passage
