"""Grounded-claims count (video v3 and v4 metrics cards): every on-screen number bound, and the check bites."""

from footage.clips import CLIPS
from footage.grounding import _check, latest_edit, run, version_of
from footage.insights import evidence_board

FACT = {"fact_id": "f_799901", "match_id": "m_9002", "label": "ghost goal chance", "value": 0.2581, "unit": "p_goal"}


def test_all_v3_on_screen_numbers_are_bound():
    r = run()
    assert r["numbers"] > 0 and r["numbers_bound"] == r["numbers"] and r["claims_verified"] == r["claims"]
    assert set(r["groups"]) == {"studio cue", "beat caption", "video caption"}


def test_a_wrong_number_is_caught():
    bb = evidence_board("manutd-mancity-2526", [FACT])
    claim = {"text": "26%", "kind": "number", "value": 0.2581, "unit": "p_goal", "evidence_ids": ["f_799901"]}
    ok = _check(CLIPS["manutd-mancity-2526"]["match_id"], [claim], bb, {"caption": "it falls from 26%"})
    bad = _check(CLIPS["manutd-mancity-2526"]["match_id"], [{**claim, "text": "28%"}], bb, {"caption": "from 28%"})
    unclaimed = _check(CLIPS["manutd-mancity-2526"]["match_id"], [claim], bb, {"caption": "26% and then 7 more"})
    bb.close()
    assert ok["numbers_bound"] == ok["numbers"] == 1 and ok["claims_verified"] == 1
    assert bad["claims_verified"] == 0 and bad["numbers_bound"] == 0
    assert unclaimed["numbers"] == 2 and unclaimed["numbers_bound"] == 1


def test_v4_lines_studio_and_captions_are_bound_and_the_overlay_is_checked():
    edit = latest_edit().with_name("edit_v4.yaml")
    assert version_of(edit) == "v4" and int(version_of(latest_edit())[1:]) >= 4
    r = run("v4", edit)
    for g in ("studio cue", "v4 line", "video caption"):
        x = r["groups"][g]
        assert x["numbers_bound"] == x["numbers"] > 0 and x["claims_verified"] == x["claims"], (g, x)
    assert r["groups"]["v4 overlay"]["items"] == 8      # six decision cards, the Oracle card, the ghost footer
    assert "win" not in " ".join(row["item"] for row in r["rows"]).lower()


def test_v5_lines_studio_and_captions_are_bound():
    from footage.grounding import ROOT

    r = run("v5", ROOT / "packages" / "demo" / "edit_v5.yaml")
    for g in ("studio cue", "v5 line"):
        x = r["groups"][g]
        assert x["numbers_bound"] == x["numbers"] > 0 and x["claims_verified"] == x["claims"], (g, x)
    # whatever is not bound yet is listed with the change that binds it; nothing unexplained
    assert all(u["owner"] != "open" for u in r["unbound"]), r["unbound"]
    assert r["numbers"] - r["numbers_bound"] == sum(
        row["numbers"] - row["numbers_bound"] for row in r["rows"] if row["item"] in {u["item"] for u in r["unbound"]})
    assert "win" not in " ".join(row["item"] for row in r["rows"]).lower()


def test_v5_from_here_binds_the_freeze_and_any_other_shot_the_strike():
    from footage.grounding import v5_caption_sources

    src = v5_caption_sources()
    (amad,) = src["Man Utd v Man City. Amad shoots from here: 0.06 xG."]
    assert amad[3] == 0.0635 and "freeze" in amad[4][1]                    # strike would be 0.07
    eze = src["Arsenal v Chelsea. Eze from 16 m: 0.08 xG. Saved."][1]
    assert eze[3] == 0.08 and "shots_0 e_0046" in eze[4][1]                # strike; the freeze was 0.05


def test_v6_all_bound_and_the_live_product_check_bites(tmp_path):
    import json as _json

    from footage.grounding import ROOT, v6_live

    r = run("v6", ROOT / "packages" / "demo" / "edit_v6.yaml")
    assert r["numbers_bound"] == r["numbers"] > 400 and r["claims_verified"] == r["claims"]
    frame = {"clip_ms": 1000, "shot_now_xg": 0.04, "options": [
        {"label": "t4", "p_pass": 0.5, "xg_receiver": 0.2, "xg_after_pass": 0.15}]}      # 0.5 x 0.2 is 0.10
    path = tmp_path / "live.json"
    path.write_text(_json.dumps({"result": {"frames": [frame]}}))
    (row,) = v6_live({"x": {"kind": "live_hud", "data": str(path), "t0": 0.0, "t1": 2.0}})
    assert row["numbers_bound"] < row["numbers"] and "is not 0.5 x 0.2" in row["diff"][0]


def test_v6_pipeline_compact_phrases_are_checked():
    import yaml

    from footage.grounding import ROOT, v6_pipeline

    beat = yaml.safe_load((ROOT / "packages/demo/footage_moments.yaml").read_text())["moments"]["mci_pipeline_v6"]
    (ok,) = v6_pipeline({"p": beat})
    assert ok["numbers_bound"] == ok["numbers"]
    (bad,) = v6_pipeline({"p": {**beat, "compact": {**beat["compact"], "proposer": "Shot + 9 passes priced"}}})
    assert bad["numbers_bound"] == bad["numbers"] - 1 and any("9" in d for d in bad["diff"])


def test_v7_always_on_checks_the_share_and_the_shape():
    import json as _json

    from footage.grounding import v7_always

    lines = [{"x": 43.73}, {"x": 50.39}, {"x": 59.4}]
    fr = {"clip_ms": 1000, "danger": {"team": "home", "share": 0.28, "text": "Man Utd control 28% of the danger zone"},
          "danger_zone": {"attacked_by": "home"}, "shape": {"away": {
              "width_m": 28.96, "width_y_min": 6.82, "width_y_max": 35.78, "depth_m": 15.67, "line_gap_m": 6.67,
              "lines": lines, "n_players_seen": 9}}}
    bad = {**fr, "clip_ms": 1100, "danger": {**fr["danger"], "text": "Man Utd control 30% of the danger zone"},
           "shape": {"away": {**fr["shape"]["away"], "depth_m": 19.0}}}

    def run_on(frames, tmp):
        path = tmp / "always.json"
        path.write_text(_json.dumps({"result": {"frames": frames}}))
        (row,) = v7_always({"x": {"kind": "always_on", "always": str(path), "t0": 0.0, "t1": 2.0}})
        return row

    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp())
    assert run_on([fr], tmp)["numbers_bound"] == run_on([fr], tmp)["numbers"] == 4
    row = run_on([bad], tmp)
    assert row["numbers"] - row["numbers_bound"] == 2 and any("28%" in d for d in row["diff"])


def test_v8_counter_and_old_name(tmp_path):
    import yaml

    from footage.grounding import COUNTER, _counter_rows, v8_screen_text

    item = "VERIFY: 1,399 of 1,399 on-screen numbers bound to verified evidence."
    assert COUNTER.search(item)
    (ok,) = _counter_rows([{"item": item}], {"numbers_bound": 1399, "numbers": 1399})
    (bad,) = _counter_rows([{"item": item}], {"numbers_bound": 1398, "numbers": 1400})
    assert ok["numbers_bound"] == 2 and bad["numbers_bound"] == 0 and "1398 of 1400" in bad["diff"][0]
    edit = tmp_path / "edit_v8.yaml"
    edit.write_text(yaml.safe_dump({"clips": [{"captions": [{"text": "Pitchsight prices every option."}]},
                                              {"card": "end", "title": "WHYLINE", "lines": ["Every line has a why."]}]}))
    (row,) = v8_screen_text(edit)
    assert row["claims_verified"] == row["claims"] - 1 and "WHYLINE" in row["diff"][0]


def test_v8_explainer_binds_the_models_card_and_counts_its_graphic():
    import yaml

    from footage.grounding import ROOT, v8_explainer

    beat = yaml.safe_load((ROOT / "packages/demo/footage_moments.yaml").read_text())["moments"]["explainer_v8"]
    rows, counters = v8_explainer({"explainer_v8": beat})
    card = next(r for r in rows if "models card" in r["item"])
    assert card["numbers"] == card["numbers_bound"] == 5                  # 2.1, 1,600, 8,451, 2017/18
    bad, _ = v8_explainer({"explainer_v8": {**beat, "models": [{"name": "Pass model", "lines": ["3.2 million passes"]}]}})
    assert next(r for r in bad if "models card" in r["item"])["numbers_bound"] == 0
    assert counters and "of" in counters[0]["item"]


def test_an_edit_can_bring_its_own_beats_version_and_output(tmp_path):
    import yaml

    from footage.grounding import ROOT, _v6_beats, version_of
    from footage.shirts import passages_from_edit

    beats = yaml.safe_load((ROOT / "packages/demo/footage_moments.yaml").read_text())["moments"]
    (tmp_path / "moments.yaml").write_text(yaml.safe_dump({"moments": {"local_live": beats["mci_live_v7"]}}))
    edit = tmp_path / "edit_local.yaml"
    edit.write_text(yaml.safe_dump({"version": "v8", "moments": str(tmp_path / "moments.yaml"),
                                    "grounding_out": str(tmp_path / "out.json"),
                                    "clips": [{"shot": "footage/local_live"}]}))
    assert version_of(edit) == "v8" and list(_v6_beats(edit)) == ["local_live"]
    assert passages_from_edit(edit) == {"manutd-mancity-2526": [(872000, 877000)]}


def test_v9_both_cuts_bind_the_decision_the_strike_tags_and_the_var_call():
    from footage.grounding import ROOT, run

    for name in ("edit_v9.yaml", "edit_v9_submit.yaml"):
        r = run("v9", ROOT / "packages" / "demo" / name)
        assert r["numbers_bound"] == r["numbers"] and r["claims_verified"] == r["claims"], name
        items = {x["item"] for x in r["rows"] if x["group"] == "v9 overlay"}
        assert any("THE DECISION · 79:11" in i for i in items)                     # the clock is e_0046's
        assert any("'GOAL · 0.10 xG' (Mbeumo)" in i for i in items)
        assert any("'RULED OUT BY VAR'" in i for i in items)
    assert (ROOT / "data" / "footage" / "v9_submit_grounding.json").exists()      # each cut its own file


def test_v10_screen_prints_what_the_hud_shows_when_it_shows_it():
    """The voice's screen model on v9's cut (same beats and timings as v10): the Mount panel's 0.20 and 0.09, the
    decision freeze's pass tag only from 1.9 s, the Amad freeze's 0.11 only once its card is in."""
    from footage.grounding import ROOT, _Screen, _v6_beats

    edit = ROOT / "packages" / "demo" / "edit_v9.yaml"
    scr = _Screen(edit, _v6_beats(edit))
    start = {c["shot"].split("/")[-1]: a for a, _, c in scr.clips}
    late = scr.numbers(start["mci_late_live_v9"] + 3.4)
    assert {"0.20", "0.09"} <= set(late)
    dec = start["ars_eze_decision_v9"]
    assert "0.15" not in scr.numbers(dec + 1.0) and "0.15" in scr.numbers(dec + 2.0)
    assert "0.08" in scr.numbers(dec + 1.0)
    amad = start["mci_amad_v9_v8"]
    assert "0.11" not in scr.numbers(amad + 2.0) and {"0.06", "0.11"} <= set(scr.numbers(amad + 3.5))


def test_v10_voice_binds_each_number_where_it_is_spoken_and_bites_when_late(tmp_path):
    """Track B's v10 placement on v9's beats (the same data and timings; the LFC tail 2.6 s longer): every spoken
    number is on screen while spoken and every play is in the data; a cue moved later speaks a number too late.
    Needs the git-ignored stems (python -m footage.narration --script docs/video/narration_v10.md --segments ...)."""
    import json

    import pytest
    import yaml

    from footage.grounding import ROOT, _v6_beats, _voice_names, v10_voice

    seg = ROOT / "packages" / "demo" / "out" / "narration_v10" / "segments" / "segments.json"
    if not seg.exists():
        pytest.skip("the v10 voice stems are not built here (git-ignored media)")
    assert {"Mount", "Arsenal", "Mbeumo"} <= _voice_names({"manutd-mancity-2526", "arsenal-chelsea-2526"})
    moments = yaml.safe_load((ROOT / "packages" / "demo" / "footage_moments.yaml").read_text())["moments"]
    (tmp_path / "m.yaml").write_text(yaml.safe_dump({"moments": {"lfc_live_v9": {**moments["lfc_live_v9"],
                                                                                 "t1": 879.2}}}))
    edit = yaml.safe_load((ROOT / "packages" / "demo" / "edit_v9.yaml").read_text())
    edit["moments"] = str(tmp_path / "m.yaml")
    starts, t, seen = {}, 0.0, {}
    for c in edit["clips"]:
        if c["shot"].endswith("lfc_live_v9"):
            c["to"] = 10.6
        n = c["shot"].split("/")[-1]
        seen[n] = seen.get(n, 0) + 1
        starts[(n.replace("_v9", "_v10").replace("decision_v10", "decision_v9"), seen[n])] = t
        t += c["to"] - c["from"]
    segs = json.loads(seg.read_text())["segments"]
    edit["audio"] = [{"file": f"packages/demo/out/narration_v10/{v['m4a']}",
                      "at": starts[(v["clip"], v["occurrence"])] + v["starts_at"]} for v in segs.values()]
    path = tmp_path / "edit_v10_test.yaml"
    path.write_text(yaml.safe_dump(edit, sort_keys=False))
    rows = v10_voice(path, _v6_beats(path))
    assert len(rows) == 11 and sum(r["numbers"] for r in rows) == 7
    assert all(r["numbers_bound"] == r["numbers"] and r["claims_verified"] == r["claims"] for r in rows), \
        [r["diff"] for r in rows if r["diff"]]
    for a in edit["audio"]:                                   # Mount 1.5 s late: 0.20 after the panel's hold
        if a["file"].endswith("mount.m4a"):
            a["at"] += 1.5
    path.write_text(yaml.safe_dump(edit, sort_keys=False))
    late = next(r for r in v10_voice(path, _v6_beats(path)) if r["item"].startswith("mount_shot"))
    assert late["numbers_bound"] < late["numbers"] and any(d.startswith("0.20 spoken at") for d in late["diff"])
    assert any("after its segment's cut" in d for d in late["diff"])          # and it runs into the end card
