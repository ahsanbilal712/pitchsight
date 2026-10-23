"""Verified names (video v4): only hand labels, the clip description, or a tagger goal the score bug confirms."""

from footage.names import unverified_in, verify


def test_hand_labels_are_verified_and_linked_to_their_track():
    names = verify("liverpool-mancity-2526")["names"]
    assert {"kind": "hand", "ref": "moments/hand/875000.json"} in names["Dominik Szoboszlai"]["sources"]
    assert {"clip_ms": 875000, "label": "#11", "track_id": 72} in names["Mohamed Salah"]["links"]


def test_tagger_goals_need_the_score_bug_and_the_description():
    d = verify("manutd-mancity-2526")
    assert {"Bryan Mbeumo", "Patrick Dorgu"} <= set(d["names"])
    why = {r["name"]: r["why"] for r in d["rejected"]}
    assert "Mason Mount" in why and "description" in why["Mason Mount"]      # bug showed 3-0; description: 2 goals
    assert "Bruno Fernandes" in d["names"]                                   # hand label, not his disallowed goal
    spurs = verify("manutd-spurs-2425")
    assert "Brennan Johnson" in spurs["names"]                               # 0-0 -> 0-1 on the bug at 261 s
    assert any(r["name"] == "Kulusevski" and "unchanged" in r["why"] for r in spurs["rejected"]) or \
        "Dejan Kulusevski" in spurs["names"]                                 # the 47:49 duplicate never counts


def test_unverified_names_in_a_line_are_caught():
    assert unverified_in("liverpool-mancity-2526", "Szoboszlai shoots; Salah was free") == []
    assert unverified_in("liverpool-mancity-2526", "Van Dijk heads clear from Szoboszlai") == ["Virgil van Dijk"]
    assert unverified_in("manutd-mancity-2526", "Mount makes it three") == ["Mason Mount"]
