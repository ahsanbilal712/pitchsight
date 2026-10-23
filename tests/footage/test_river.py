"""Win-probability river (video v3): score from the tagged goals, the head's curve, markers. Committed events only."""

from footage.river import clock, events, goals, run, score_at

SLUG = "liverpool-mancity-2526"


def test_goals_and_final_score_follow_the_broadcast():
    gs = goals(events(SLUG))
    assert [(g["team"], g["attrs"]["player_name"]) for g in gs][:2] == [("home", "Dominik Szoboszlai"),
                                                                         ("away", "Bernardo Silva")]
    assert score_at(gs, 10**9) == [1, 3] and clock(6_285_000) == "104:45"


def test_river_swings_with_the_score_and_marks_the_moments(restore_clip_cache):
    restore_clip_cache(SLUG)
    d = run(SLUG)
    by = {s["clock"]: s for s in d["samples"]}
    assert by["73:15"]["wp"]["draw"] > 0.5 and by["74:00"]["wp"]["home"] > 0.7     # Szoboszlai's free kick
    assert d["samples"][-1]["wp"]["away"] > 0.95                                   # 1-3 at the end
    kinds = [m["kind"] for m in d["markers"]]
    assert kinds.count("goal") == 4 and kinds.count("penalty_foul") == 1 and "sliding_doors" in kinds
