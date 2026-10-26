"""Video v9 narration: the script's sections, its length and the claims it may not make."""

import re

from footage.narration import sections, sentences, words


def test_the_script_opens_with_the_hackathon_and_stays_in_length():
    s = sections()
    assert list(s) == ["intro", "architecture", "architecture_short"]
    assert s["intro"].startswith("Built for Inside the Game: the Premier League and Microsoft developer hackathon.")
    assert 120 <= len(s["intro"].split()) + len(s["architecture"].split()) <= 150
    assert len(s["architecture_short"].split()) < len(s["architecture"].split()) / 1.5     # the submit cut's version
    assert all(t.endswith(".") for t in sentences(s["architecture"]))


def test_the_script_makes_no_ruled_out_claim_and_speaks_no_number():
    text = " ".join(sections().values())
    for banned in ("YOLO", "trained", "training", "Foundry", "Azure", "live"):
        assert not re.search(rf"\b{banned}\b", text, re.I), banned
    assert not re.search(r"\d", text.replace("RF-DETR", ""))       # nothing for grounding to bind


def test_the_transcriber_spelling_is_not_a_different_word():
    assert words("a position in meters") == words("a position in metres")
    assert words("fact-checker") == words("fact checker")
    assert words("This is PitchSite") == words("This is Pitchsight")     # the product's name heard as a homophone


def test_v10_voice_keeps_its_rules():
    from footage.clips import ROOT

    s = sections(ROOT / "docs" / "video" / "narration_v10.md")
    text = " ".join(s.values())
    for banned in ("VAR", "ruled out", "offside", "he", "she", "him", "his", "her", "Mount", "Mbeumo", "Eze", "Amad",
                   "Szoboszlai", "Arsenal", "Liverpool", "United", "Chelsea"):
        assert not re.search(rf"\b{banned}\b", text, re.I), banned
    assert not re.search(r"\bgoals?\b", s["mount_pass"] + s["mount_shot"], re.I)     # Mount: the shot only
    assert "red team" in s["mci_live"] and "red team" in s["lfc_pass"]                # sides by kit colour


def test_a_number_is_compared_as_it_is_spoken():
    assert words("They shoot: 0.06 expected goals.") == words("they shoot nought point oh six expected goals")
    assert words("66% of the time") == words("sixty-six per cent of the time")
    assert words("0.20") != words("0.2")                     # the HUD prints 0.20: the take must say it
