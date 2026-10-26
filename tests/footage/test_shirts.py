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
    import json

    from footage.clips import clip_dir

    d = verify("manutd-mancity-2526")
    assert {"clip_ms": 877000, "label": "#19", "track_id": 4} in d["names"]["Bryan Mbeumo"]["links"]
    ars = verify("arsenal-chelsea-2526")
    assert not any(lk.get("label") == "A6" for n in ars["names"].values() for lk in n["links"])
    a6 = json.loads((clip_dir("arsenal-chelsea-2526") / "shirts.json").read_text())["players"]["1300500:A6"]
    assert a6["number"] is None and "gemini-4-argon" in a6["why"]        # Flash read 29, the second read 6
    assert verify("liverpool-mancity-2526")["shots"]["e_0065"]["name"] == "Hugo Ekitike"     # tagger said Mac Allister


def test_a_hand_label_gives_a_live_window_only_without_a_rival_read():
    import json
    from pathlib import Path

    r = json.loads((Path(__file__).resolve().parents[2] / "data/footage/manutd-mancity-2526/cache/v6/names_live_0.json")
                   .read_text())["result"]["players"]
    amad = [p for p in r if p["name"] == "Amad"]
    assert [(p["track_id"], p["from_clip_ms"], p["to_clip_ms"], p["shirt"]) for p in amad] == [(19, 875500, 878500, 16)]
    assert not any(p["name"] == "Casemiro" and p["track_id"] == 16 for p in r)   # t16 also reads 19 in the passage


def test_the_kit_colour_leaves_the_grass_out(tmp_path, monkeypatch):
    import json

    import numpy as np
    from PIL import Image

    import footage.shirts as shirts

    monkeypatch.setattr(shirts, "clip_dir", lambda slug: tmp_path)
    (tmp_path / "teams.json").write_text(json.dumps({"teams": [{"kit_rgb": [95, 35, 75]}, {"kit_rgb": [232, 232, 236]}]}))
    im = np.zeros((360, 200, 3), np.uint8)
    im[:] = (90, 115, 60)                                   # grass: nearer the dark kit than the white one
    im[90:170, 85:115] = (230, 232, 238)                    # a thin white shirt, most of the torso band is grass
    Image.fromarray(im).save(tmp_path / "1.png")
    assert shirts.kit_side("any", tmp_path / "1.png") == "away"


def test_a_number_names_a_player_only_when_the_second_model_reads_it_too(monkeypatch):
    import footage.shirts as shirts

    monkeypatch.setattr(shirts, "squad", lambda slug, team: {
        "club": "c", "season": "s", "source": "src", "retrieved": "r", "goalkeepers": ["1"],
        "numbers": {"12": "Twelve", "17": "Seventeen"}})
    second = {"reads": [{"crop": i, "number": 17} for i in range(1, 9)], "cost_usd": 0.02}
    monkeypatch.setattr(shirts, "read", lambda *a, **k: second)
    first = [{"crop": i, "number": 12} for i in range(1, 8)] + [{"crop": 8, "number": None}]
    t = {"key": "live1:t5", "team": "away"}
    d = shirts.decide(None, None, "any", t, first, ["away"] * 8, [])
    assert d["number"] is None and d["name"] is None and "not 12" in d["why"]    # "12" in 7 of 8, but it is a 17
    second["reads"] = [{"crop": i, "number": 12} for i in range(1, 9)]
    assert shirts.decide(None, None, "any", t, first, ["away"] * 8, [])["name"] == "Twelve"
