"""Video v9 narration (ADR-010 amendment): the script's sections, its length and the claims it may not make."""

import re

from footage.narration import sections, sentences, words


def test_the_script_opens_with_the_hackathon_and_stays_in_length():
    s = sections()
    assert list(s) == ["intro", "architecture"]
    assert s["intro"].startswith("Built for Inside the Game: the Premier League and Microsoft developer hackathon.")
    assert 120 <= sum(len(t.split()) for t in s.values()) <= 150
    assert all(t.endswith(".") for t in sentences(s["architecture"]))


def test_the_script_makes_no_claim_the_owner_ruled_out_and_speaks_no_number():
    text = " ".join(sections().values())
    for banned in ("YOLO", "trained", "training", "Foundry", "Azure", "live"):
        assert not re.search(rf"\b{banned}\b", text, re.I), banned
    assert not re.search(r"\d", text.replace("RF-DETR", ""))       # nothing for grounding to bind


def test_the_transcriber_spelling_is_not_a_different_word():
    assert words("a position in meters") == words("a position in metres")
    assert words("fact-checker") == words("fact checker")
