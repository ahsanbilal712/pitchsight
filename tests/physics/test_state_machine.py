"""State machine hysteresis: enter Chaotic only above 65 for 20 s, leave only below 50 for 30 s."""

from physics import CHAOTIC, SETTLED, TRANSITIONAL, StateMachine


def feed(sm: StateMachine, values: list[tuple[float, int]], start_ms: int = 0) -> list[tuple[int, str]]:
    """Feed (chaos, seconds) runs at 1 Hz; return (t_ms, new_state) for every change."""
    out, t = [], start_ms
    for chaos, seconds in values:
        for _ in range(seconds):
            new = sm.update(chaos, t)
            if new:
                out.append((t, new))
            t += 1000
    return out


def test_enters_chaotic_only_after_20_s_above_65():
    sm = StateMachine()
    assert feed(sm, [(70, 20)]) == [(10_000, TRANSITIONAL)]   # 0 .. 19 s: above 50 for 10 s, not 65 for 20 s
    assert sm.update(70, 20_000) == CHAOTIC


def test_a_dip_resets_the_entry_timer():
    sm = StateMachine()
    changes = feed(sm, [(70, 15), (60, 1), (70, 15)])
    assert CHAOTIC not in [s for _, s in changes]
    changes = feed(sm, [(70, 6)], start_ms=31_000)
    assert (36_000, CHAOTIC) in changes               # the run restarted at 16 s, so 20 s held at 36 s


def test_leaves_chaotic_only_after_30_s_below_50():
    sm = StateMachine(initial=CHAOTIC)
    assert feed(sm, [(45, 30)]) == []
    assert sm.update(45, 30_000) == TRANSITIONAL


def test_values_between_50_and_65_keep_chaotic():
    sm = StateMachine(initial=CHAOTIC)
    assert feed(sm, [(55, 120), (49, 29), (51, 1), (49, 29)]) == []
    assert sm.state == CHAOTIC


def test_settled_transitional_round_trip():
    sm = StateMachine()
    changes = feed(sm, [(40, 11), (20, 11)])
    assert [s for _, s in changes] == [TRANSITIONAL, SETTLED]
    assert changes[0][0] == 10_000 and changes[1][0] == 21_000
