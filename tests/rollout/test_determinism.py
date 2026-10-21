"""Same (state, overrides, B, horizon_s, seed, engine, engine_hash) gives byte-identical Futures (T-016, TECH_PLAN 1.5)."""

from kickoff import Action, Override
from rollout import MatchRef, rollout


def test_same_inputs_byte_identical(golden, decision_t):
    a = rollout(golden.state_at(decision_t), None, 64, 8, seed=7, decide_now=True, events=golden.events())
    b = rollout(golden.state_at(decision_t), None, 64, 8, seed=7, decide_now=True, events=golden.events())
    assert a.digest() == b.digest()
    c = rollout(golden.state_at(decision_t), None, 64, 8, seed=8, decide_now=True, events=golden.events())
    assert c.digest() != a.digest()


def test_branch_from_the_past_resimulates_identically(golden, decision_t):
    fresh = MatchRef(4242, match_dir=golden.match_dir)
    fresh.engine_at(decision_t + 60_000)                    # move past the branch point first
    alt = Override(first_action=Action(kind="shoot"))
    a = rollout(golden.state_at(decision_t), alt, 32, 8, seed=3)
    b = rollout(fresh.state_at(decision_t), alt, 32, 8, seed=3)
    assert a.digest() == b.digest()


def test_world_zero_does_not_depend_on_batch_size(golden, decision_t):
    st = golden.state_at(decision_t)
    small = rollout(st, None, 1, 8, seed=11, decide_now=True)
    big = rollout(st, None, 16, 8, seed=11, decide_now=True)
    assert (small.ball_paths[0] == big.ball_paths[0]).all()
    assert (small.S_end[0] == big.S_end[0]).all()
