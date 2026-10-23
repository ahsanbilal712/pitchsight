"""Video v4 lines: the verdict comes from the 95% intervals, every number prints one display string, names are
verified, the wording follows the verdict. No model call."""

from footage.v4_lines import BEST, BETTER, CLOSE, describe, gates, pct, story, verdict

ACTUAL = {"option": {"kind": "shoot"}, "p_goal_10s": 0.011, "ci95": [0.0073, 0.0166], "goals": 22}


def alt(p, lo, hi, kind="pass", target="L3"):
    return {"option": {"kind": kind, "target": target}, "p_goal_10s": p, "ci95": [lo, hi],
            "diff_vs_actual": {"verdict": "better"}}


def test_display_matches_the_overlay():
    assert (pct(0.033), pct(0.0065), pct(0.0245), pct(0.3155), pct(0.1705)) == ("3.3%", "0.7%", "2.5%", "32%", "17%")


def test_better_only_when_the_intervals_are_clear():
    assert verdict(ACTUAL, alt(0.033, 0.026, 0.0418)) == BETTER
    assert verdict(ACTUAL, alt(0.02, 0.0147, 0.0271)) == CLOSE            # paired test says better; intervals overlap
    assert story({"options": [ACTUAL, alt(0.02, 0.0147, 0.0271)]})["verdict"] == CLOSE
    assert story({"options": [ACTUAL, alt(0.004, 0.002, 0.0072)]})["verdict"] == BEST


def test_position_phrase_follows_the_attacking_direction():
    m = {"home_attacks": "+x"}
    assert describe(m, {"team": "home", "x": 87.2, "y": 41.5}) == "the team-mate at the edge of the box, on the left"
    assert describe(m, {"team": "away", "x": 19.2, "y": 24.2}) == "the team-mate at the edge of the box, on the left"
    assert describe(m, {"team": "home", "x": 100.0, "y": 34.0}) == "the team-mate in the six-yard box, central"


FACTS = [{"fact_id": "f_600001", "display": "1.1%"}, {"fact_id": "f_600002", "display": "3.3%"}]
VIEW = {"verdict": BETTER}


def body(lower, why, texts=("1.1%", "3.3%")):
    return {"lower_third": lower, "why": why,
            "claims": [{"text": t, "kind": "number", "evidence_ids": [f["fact_id"]]} for t, f in zip(texts, FACTS, strict=True)]}


def test_gates_pass_a_clean_line():
    b = body("Szoboszlai shoots: 1.1%, the pass 3.3%", "A pass to the team-mate at the edge of the box gives 3.3%.")
    assert gates("liverpool-mancity-2526", b, FACTS, VIEW) == []


def test_gates_catch_display_names_and_wording():
    slug = "liverpool-mancity-2526"
    assert any("display" in p for p in gates(slug, body("x", "y", ("1%", "3.3%")), FACTS, VIEW))
    assert any("unverified" in p for p in gates(slug, body("Van Dijk 1.1%", "3.3%"), FACTS, VIEW))
    assert any("close call" in p for p in gates(slug, body("A better pass 3.3%", "1.1%"), FACTS, {"verdict": CLOSE}))
    assert any("blame" in p for p in gates(slug, body("He should have passed", "3.3% 1.1%"), FACTS, VIEW))
