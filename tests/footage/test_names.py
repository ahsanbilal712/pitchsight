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
    assert "Marcus Rashford" in unverified_in("manutd-spurs-2425", "Rashford shoots")
    # Mount's disallowed "3-0": the tagger alone is not enough (his goal is rejected), but the tracking has t2, read #7
    # by both models, on the ball 0.2 s before the tagged strike with no pass in between
    mount = verify("manutd-mancity-2526")["shots"]["e_0070"]
    assert mount["name"] == "Mason Mount" and mount["source"].startswith("live_1390000.json: t2 on the ball at 1414800")
    # the tagger's "Enzo shot" at 832 s is his pass to Palmer in the tracking: unnamed
    assert verify("arsenal-chelsea-2526")["shots"]["e_0024"]["name"] is None


def test_a_shot_is_named_only_when_that_shot_is_verified():
    shots = verify("liverpool-mancity-2526")["shots"]
    assert shots["e_0006"]["name"] == "Dominik Szoboszlai" and shots["e_0006"]["source"] == "score_bug goal"
    assert shots["e_0033"]["source"] == "moments/hand/875000.json (holder shoots)"
    haaland_blocked = next(s for s in shots.values() if s["clip_ms"] == 707000)
    assert haaland_blocked["tagger_name"] and haaland_blocked["name"] is None   # verified player, unverified shot


def test_a_clip_without_tagged_events_names_strikes_by_score_bug_and_shirt(tmp_path, monkeypatch):
    import json

    import footage.names as names_mod

    monkeypatch.setattr(names_mod, "clip_dir", lambda slug: tmp_path)
    (tmp_path / "strikes.json").write_text(json.dumps({"strikes": [
        {"id": "s_0614", "clip_ms": 61400, "team": "away", "goal": True},
        {"id": "s_0961", "clip_ms": 96100, "team": "away", "goal": False},
        {"id": "s_1282", "clip_ms": 128200, "team": "away", "goal": False}]}))
    (tmp_path / "score_bug.json").write_text(json.dumps({"readings": [
        {"clip_ms": 66000, "before": [0, 0], "after": None},
        {"clip_ms": 97000, "before": None, "after": [0, 1], "changed": "away"}]}))
    (tmp_path / "description.json").write_text(json.dumps({"goals": [
        {"clip_s": 58, "score": [0, 1], "scorer": "Mbappé", "own_goal": False, "minute": None}]}))
    named = {"Kylian Mbappé": {"team": "away", "sources": [], "links": []},
             "Yan Diomande": {"team": "away", "sources": [{"kind": "shirt", "ref": "shirts.json s_0961:t7: #25"}],
                              "links": [{"event": "s_0961", "label": "t7", "clip_ms": 96100}]}}
    shots = names_mod.strike_names("any", named)
    assert shots["s_0614"]["name"] == "Kylian Mbappé" and "score_bug.json 97000" in shots["s_0614"]["source"]
    assert shots["s_0961"]["name"] == "Yan Diomande"
    assert shots["s_1282"]["name"] is None                      # no consistent read at the strike: unnamed
