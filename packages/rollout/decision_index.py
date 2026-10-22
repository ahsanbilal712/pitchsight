"""Decision Index: how good each on-ball decision was, by rollout (TECH_PLAN 1.14 #3, 1.8 step 3; T-048).

Formula. For every pass, shot and clearance of the match (the decision tick, event t_ms - 100), force the action
actually taken and each of the engine's three most likely other options (scripted_v1 option probabilities at that
state), n = 50 futures each, 8 s, the same seed. Let p(a) be P(the player's team scores within 8 s, with the goal-in-8-s
hand-off) after forcing a. The decision's value is

    value = p(actual) - max(p(alternative_1..3))

(positive: the player beat every option the engine considered; negative: a better option was there). The engine
refuses to force a pass to an offside target; when the actual pass was one, its consequence is known (offside, free
kick to the opponents), so p(actual) is an unforced rollout from the realised state just after the whistle. A player's
Decision Index is the percentile (0-100) of his mean value among all players of the match with at least
MIN_DECISIONS decisions. Live mode cannot afford this many rollouts (TECH_PLAN 1.14 #3), so `live_values` uses the
goal-in-8-s head swing per decision, net of the opponent: (p(team scores) - p(opponent scores)) at t + 1 s minus the
same at t - 100 ms, aggregated the same way; `spearman` reports how well it ranks players like the rollout index.
(Net, because a decision that gives the ball away raises the opponent's chance, which the team-only swing misses:
Spearman with the rollout index 0.645 / 0.529 / 0.534 on seeds 4242 / 1 / 2, team-only 0.417 / 0.451 / 0.664.)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from kickoff import BranchError, Override

from .core import MatchRef, rollout
from .sliding_doors import EVENT_KIND, actual_action, option_probs, to_engine_action

DECISIONS = ("pass", "shot", "clearance")
N, HORIZON_S, TOP_K = 50, 8.0, 3
MIN_DECISIONS = 5


@dataclass
class DecisionValue:
    event_id: str
    t_ms: int
    player: str
    team: str
    actual: dict
    p_actual: float
    p_best_alternative: float
    best_alternative: dict | None
    value: float


def _alternatives(probs: dict[str, float], actual: dict, actor: str, attack_tag: str) -> list[dict]:
    keys = sorted(probs, key=lambda k: -probs[k])
    out = []
    for k in keys:
        if k in ("shoot", "clear", "carry"):
            alt = {"kind": k, "actor": actor, "target": attack_tag if k == "carry" else None}
        else:
            alt = {"kind": "pass", "actor": actor, "target": k}
        if alt["kind"] == actual["kind"] and alt["target"] == actual.get("target"):
            continue
        out.append(alt)
        if len(out) == TOP_K:
            break
    return out


def _p_goal(state, eng, action: dict | None, team: str, n: int, horizon_s: float, seed: int,
            engine: str) -> tuple[float | None, str | None]:
    """(P(the team scores within the horizon, with the head hand-off) after forcing `action`, or unforced when None;
    None if illegal) and the invalid reason."""
    override = None if action is None else Override(first_action=to_engine_action(eng, action))
    try:
        f = rollout(state, override, n, horizon_s, seed, engine=engine)
    except BranchError as exc:
        return None, str(exc)
    if f.invalid_reason:
        return None, f.invalid_reason
    return (f.p_goal_home if team == "home" else f.p_goal_away), None


def decision_values(match: MatchRef, events: list[dict], seed: int = 4242, n: int = N,
                    horizon_s: float = HORIZON_S, engine: str = "scripted_v1") -> list[DecisionValue]:
    """Values for the given decision events (in time order; MatchRef moves forward through them)."""
    out = []
    for e in sorted(events, key=lambda e: e["t_ms"]):
        t = int(e["t_ms"]) - 100
        state = match.state_at(t)
        eng = state.source
        if int(eng.holder[0]) < 0 or eng.dead[0] or eng.worlds[0].row_ids[int(eng.holder[0])] != e["player"]:
            continue
        team = e["team"]
        actual, _ = actual_action(match, eng, t)
        tag = "e" if eng.team_dir(0 if team == "home" else 1) > 0 else "w"
        alts = _alternatives(option_probs(eng), actual, e["player"], tag)

        pa, why = _p_goal(state, eng, actual, team, n, horizon_s, seed, engine)
        if pa is None and why and "offside" in why:
            pa, _ = _p_goal(match.state_at(int(e["t_ms"]) + 100), None, None, team, n, horizon_s, seed, engine)
        if pa is None:
            continue
        scored = [(_p_goal(state, eng, a, team, n, horizon_s, seed, engine)[0], a) for a in alts]
        scored = [(p, a) for p, a in scored if p is not None]
        best_p, best_a = max(scored, key=lambda x: x[0]) if scored else (pa, None)
        out.append(DecisionValue(event_id=e["id"], t_ms=t, player=e["player"], team=team, actual=actual,
                                 p_actual=round(pa, 5), p_best_alternative=round(best_p, 5), best_alternative=best_a,
                                 value=round(pa - best_p, 5)))
    return out


def player_index(values: list[tuple[str, float]]) -> dict[str, dict]:
    """{player: {index 0-100, mean_value, decisions}} from (player, value) pairs; players with fewer than
    MIN_DECISIONS decisions get index None."""
    by: dict[str, list[float]] = {}
    for p, v in values:
        by.setdefault(p, []).append(v)
    means = {p: float(np.mean(v)) for p, v in by.items() if len(v) >= MIN_DECISIONS}
    ranked = sorted(means.values())
    out = {}
    for p, v in by.items():
        if p in means:
            below = sum(1 for x in ranked if x < means[p]) + 0.5 * (sum(1 for x in ranked if x == means[p]) - 1)
            idx = round(100.0 * below / max(len(ranked) - 1, 1), 1)
        else:
            idx = None
        out[p] = {"index": idx, "mean_value": round(float(np.mean(v)), 5), "decisions": len(v)}
    return out


def live_values(events: list[dict], window, head=None) -> list[tuple[str, float]]:
    """Live approximation: the net goal-in-8-s swing (team minus opponent) across each decision (t - 100 ms to t + 1 s)."""
    from heads.features import state_features
    from heads.models import GoalIn8sHead

    head = head or GoalIn8sHead()
    pos = np.asarray(window.possession).astype(np.int64)
    idx = np.where(pos >= 0, np.arange(len(pos)), -1)
    np.maximum.accumulate(idx, out=idx)
    team_all = np.where(idx >= 0, pos[np.maximum(idx, 0)], 0)
    dec = [e for e in events if e["type"] in DECISIONS and e.get("player")]
    before = np.array([window.index_at(e["t_ms"] - 100) for e in dec])
    after = np.array([window.index_at(e["t_ms"] + 1000) for e in dec])
    fr = np.concatenate([before, after])
    f = state_features(window.S[fr], window.ball_z[fr], window.holder[fr], team_all[fr], window.period[fr],
                       window.t_ms[fr], np.asarray(window.possession)[fr] >= 0)
    p = head.predict(f.assign(poss_team=team_all[fr]))
    out = []
    for i, e in enumerate(dec):
        k = 0 if e["team"] == "home" else 1
        j = len(dec) + i
        out.append((e["player"], float((p[j, k] - p[j, 1 - k]) - (p[i, k] - p[i, 1 - k]))))
    return out


def spearman(a: dict[str, dict], b: dict[str, dict]) -> float:
    from scipy.stats import spearmanr
    common = [p for p in a if a[p]["index"] is not None and b.get(p, {}).get("index") is not None]
    if len(common) < 3:
        return float("nan")
    return float(spearmanr([a[p]["mean_value"] for p in common], [b[p]["mean_value"] for p in common]).statistic)


__all__ = ["DecisionValue", "EVENT_KIND", "decision_values", "live_values", "player_index", "spearman"]
