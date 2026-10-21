"""Sliding Doors: baseline vs one alternative at a decision point (TECH_PLAN 1.5 "Callers").

The branch point is the decision state: for an on-ball event kicked at T, t_ms = T - 100 (the tick before, as in
samples.npz). Baseline = the player in control takes the engine's own choice on the first tick, then the engine
plays on (unforced continuation at a decision point). Alternative = that first choice forced. Both are sampled n
times for horizon_s seconds with the same seed and valued by the goal-in-8-s and win-probability heads.
"""

from __future__ import annotations

import math

import numpy as np

from kickoff import Action, BranchError, Override, ScriptedRule
from kickoff.engine import Engine
from kickoff.physics_prior import to_team
from kickoff.rules import RULE_NOISE, DecisionBatch

from .core import MatchRef, engine_hash, rollout

SCHEMA_VERSION = "1.0.0"
EVENT_KIND = {"pass": "pass", "shot": "shoot", "clearance": "clear"}
MIN_HALF_WIDTH = 0.005     # win probability is shown in whole percentage points
KIND_CODES = {"pass": 0, "carry": 1, "shoot": 2, "clear": 3, "hold": 4}       # kickoff.rules PASS..HOLD
TAGS = ("e", "ne", "n", "nw", "w", "sw", "s", "se")


def direction_tag(dx: float, dy: float) -> str:
    """Absolute compass tag (e = +x, n = +y) of a carry direction, 8 bins."""
    return TAGS[int(round(math.atan2(dy, dx) / (math.pi / 4))) % 8]


def tag_direction(tag: str) -> tuple[float, float]:
    a = TAGS.index(tag) * math.pi / 4
    return math.cos(a), math.sin(a)


def _rule_at(eng: Engine):
    """The scripted rule's evaluation of the branch point (fixed noise): (rule, DecisionOut, team)."""
    row = int(eng.holder[0])
    team = 0 if row < 11 else 1
    d = eng.team_dir(team)
    order = list(range(11 * team, 11 * team + 11)) + list(range(11 * (1 - team), 11 * (1 - team) + 11))
    U, V = to_team(eng.S[0, order, 0], eng.S[0, order, 1], d)
    rule = eng.model if isinstance(eng.model, ScriptedRule) else ScriptedRule()
    out = rule.decide_batch(DecisionBatch(U=U[None], V=V[None], holder=np.array([row - 11 * team]),
                                          styles=eng.eff_styles[0:1, team], momentum=eng.mom[0:1, team],
                                          restart=eng.restart_flag[0:1], noise=np.full((1, RULE_NOISE), 0.5)))
    return rule, out, team


def option_probs(eng: Engine) -> dict[str, float]:
    """scripted_v1 probabilities at the branch point: softmax of the rule's utilities (passes by player id, shoot,
    clear, carry); used as `policy_prob` and by the RolloutExecutor filter (T-031)."""
    rule, out, team = _rule_at(eng)
    p = rule.option_probs(out)[0]
    names = [eng.worlds[0].row_ids[11 * team + s] for s in range(11)] + ["shoot", "clear", "carry"]
    return {n: float(v) for n, v in zip(names, p, strict=True)}


def _prob(probs: dict[str, float], action: dict) -> float | None:
    key = action["target"] if action["kind"] == "pass" else action["kind"]
    return None if key not in probs else round(probs[key], 4)


def actual_action(match: MatchRef, eng: Engine, t_ms: int) -> tuple[dict, list[str]]:
    """The decision the player in control actually made at t_ms (the on-ball event kicked at t_ms + 100, else a
    carry or hold), as a schema action, plus evidence event ids."""
    row = int(eng.holder[0])
    actor = eng.worlds[0].row_ids[row]
    events = match.events()
    ev = next((e for e in events if e["t_ms"] == t_ms + 100 and e["player"] == actor and e["type"] in EVENT_KIND), None)
    recent = [e["id"] for e in events if t_ms - 10_000 <= e["t_ms"] <= t_ms + 100 and e["player"] == actor
              and e["type"] in ("pass", "carry", "shot", "clearance", "possession_change", "interception", "tackle")]
    if ev is not None:
        target = ev["attrs"].get("recipient") if ev["type"] == "pass" else None
        evidence = sorted(set(recent + [ev["id"]] + ev["related_event_ids"]))
        return {"kind": EVENT_KIND[ev["type"]], "actor": actor, "target": target}, evidence
    vx, vy = float(eng.S[0, row, 2]), float(eng.S[0, row, 3])
    if math.hypot(vx, vy) < 0.5:
        return {"kind": "hold", "actor": actor, "target": None}, recent
    return {"kind": "carry", "actor": actor, "target": direction_tag(vx, vy)}, recent


def to_engine_action(eng: Engine, action: dict) -> Action:
    """Schema action (player ids, direction tags) -> engine Action (team slot, unit vector)."""
    row = int(eng.holder[0])
    team = 0 if row < 11 else 1
    if action["kind"] == "pass":
        ids = eng.worlds[0].row_ids[11 * team:11 * team + 11]
        if action["target"] not in ids:
            raise BranchError(f"{action['target']} is not on the pitch for the passer's team")
        slot = ids.index(action["target"])
        _, out, _ = _rule_at(eng)
        return Action(kind="pass", target=slot, lofted=bool(out.lofted_all[0, slot]))   # the rule's own height
    if action["kind"] == "carry":
        return Action(kind="carry", direction=tag_direction(action["target"]))
    return Action(kind=action["kind"])


def sliding_doors(match: MatchRef, t_ms: int, alternative: Action | dict, n: int = 200, horizon_s: float = 8,
                  seed: int = 4242, engine: str = "scripted_v1", counterfactual_id: str | None = None,
                  moment_id: str | None = None) -> dict:
    """CounterfactualResult (schemas/counterfactual.schema.json). `alternative` is a schema action dict or an engine
    Action. Raises BranchError when the alternative cannot be played (the caller picks another)."""
    state = match.state_at(t_ms)
    eng = state.source
    if int(eng.holder[0]) < 0 or eng.dead[0]:
        raise BranchError(f"no player in control at {t_ms}")
    actual, evidence = actual_action(match, eng, t_ms)
    if isinstance(alternative, dict):
        alt_dict, alt_action = alternative, to_engine_action(eng, alternative)
    else:
        alt_action = alternative
        team = 0 if eng.holder[0] < 11 else 1
        target = None
        if alternative.kind == "pass":
            if alternative.target is None or not 0 <= int(alternative.target) <= 10:
                raise BranchError("pass needs a team-mate slot 0-10")
            target = eng.worlds[0].row_ids[11 * team + int(alternative.target)]
        elif alternative.kind == "carry":
            target = direction_tag(*alternative.direction)
        alt_dict = {"kind": alternative.kind, "actor": actual["actor"], "target": target}
    probs = option_probs(eng)
    events = match.events()
    base = rollout(state, None, n, horizon_s, seed, engine=engine, decide_now=True, events=events)
    alt = rollout(state, Override(first_action=alt_action), n, horizon_s, seed, engine=engine, events=events)
    if alt.invalid_reason:
        raise BranchError(alt.invalid_reason)
    if not evidence:
        evidence = [e["id"] for e in events if e["t_ms"] <= t_ms][-1:]
    paths = np.round(alt.ball_paths[:200].astype(np.float64), 2).tolist()
    return {
        "schema_version": SCHEMA_VERSION,
        "counterfactual_id": counterfactual_id or f"cf_{t_ms // 100:06d}",
        "match_id": match.match_id,
        "moment_id": moment_id,
        "t_ms": int(t_ms),
        "engine": engine,
        "n": int(n),
        "horizon_s": float(horizon_s),
        "seed": int(seed),
        "actual": {**actual, "policy_prob": _prob(probs, actual)},
        "alternative": {**alt_dict, "policy_prob": _prob(probs, alt_dict)},
        "baseline": base.outcome(),
        "alternative_outcome": alt.outcome(),
        "delta_win_prob_home": round(alt.win_prob_home - base.win_prob_home, 4),
        "futures_sample": paths,
        "evidence_event_ids": evidence,
        "pitch_control_snapshot_id": f"pc_{t_ms // 100:06d}",
        "compute_ms": None,
        "engine_hash": engine_hash(),
    }


def placebo(match: MatchRef, t_ms: int, n: int = 200, horizon_s: float = 8, seed: int = 4242,
            engine: str = "scripted_v1", min_support: int = 10, min_half_width: float = MIN_HALF_WIDTH) -> dict:
    """Placebo for the forcing mechanism: force the action the player actually took, and compare with the baseline
    worlds (same seeds) whose own first decision was that action. Forcing is unbiased when the forced mean win
    probability lies within the two-sample 95% interval of that conditional baseline. The interval is at least
    ±`min_half_width` (half a displayed percentage point): over 8 s win probability barely moves, so raw intervals
    can be 1e-5 wide and would test the heads' rounding, not the forcing. Moments where the engine rarely picks the
    actual action (fewer than `min_support` worlds) are reported as not testable."""
    state = match.state_at(t_ms)
    eng = state.source
    actual, _ = actual_action(match, eng, t_ms)
    action = to_engine_action(eng, actual)
    events = match.events()
    base = rollout(state, None, n, horizon_s, seed, engine=engine, decide_now=True, events=events)
    forced = rollout(state, Override(first_action=action), n, horizon_s, seed, engine=engine, events=events)
    kind = KIND_CODES[action.kind]
    same = base.per_world["first_kind"] == kind
    if action.kind == "pass":
        same &= base.per_world["first_target"] == int(action.target)
    support = int(same.sum())
    wb, wf = base.per_world["win_prob"][same], forced.per_world["win_prob"]
    out = {"t_ms": t_ms, "actual": actual, "support": support, "baseline": base.outcome(), "forced": forced.outcome()}
    if support < min_support:
        return {**out, "testable": False, "passed": None}
    diff = float(wf.mean() - wb.mean())
    se = math.sqrt(float(wf.var(ddof=1)) / wf.size + float(wb.var(ddof=1)) / wb.size)
    half = max(1.96 * se, min_half_width)
    return {**out, "testable": True, "diff_win_prob": diff, "half_width": half, "raw_half_width": 1.96 * se,
            "passed": bool(abs(diff) <= half)}
