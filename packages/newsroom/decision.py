"""The on-ball decision a moment turns on, and the rule-based alternatives (TECH_PLAN 1.5, 1.7; T-031).

decision_point(store, moment) finds the last pass, carry, shot or clearance among the moment's evidence (else the
last one by the moment's team in the 10 s before it) and describes the branch point the rollout forces:
t_ms = event time - 100 ms (the engine kicks the on-ball event one tick after the decision), the actor, the
actual action and every team-mate on the pitch with the expected-threat gain of a pass to that player.
`attach_options` adds the engine's option probabilities, which the MCP tool get_state returns.
"""

from __future__ import annotations

import numpy as np

DECISIONS = {"pass", "carry", "shot", "clearance"}
EVENT_KIND = {"pass": "pass", "carry": "carry", "shot": "shoot", "clearance": "clear"}
DIRECTIONS = ("n", "ne", "e", "se", "s", "sw", "w", "nw")


def _get(m, key, default=None):
    return m.get(key, default) if isinstance(m, dict) else getattr(m, key, default)


def decision_point(store, moment) -> dict | None:
    from kickoff.physics_prior import threat, to_team
    from newsroom.factcheck import league_data

    match_id, t = _get(moment, "match_id"), int(_get(moment, "t_ms"))
    m = store.match(match_id)
    by_id = {e["id"]: e for e in m.events}
    cited = [by_id[i] for i in _get(moment, "evidence_event_ids", []) or [] if i in by_id]
    anchor = max((e for e in cited if e["type"] in DECISIONS and e.get("player")), key=lambda e: e["t_ms"],
                 default=None)
    if anchor is None:
        team = _get(moment, "team")
        recent = [e for e in m.events if t - 10_000 <= e["t_ms"] <= t and e["type"] in DECISIONS and e.get("player")
                  and (team is None or e["team"] == team)]
        anchor = recent[-1] if recent else None
    if anchor is None or m.window is None:
        return None
    t_dec = int(anchor["t_ms"]) - 100
    w = m.window
    i = w.index_at(t_dec)
    S = w.S[i].astype(np.float64)
    period = int(w.period[i])
    side = 0 if anchor["team"] == "home" else 1
    d = (1 if period == 1 else -1) * (1 if side == 0 else -1)
    rows = list(range(11 * side, 11 * side + 11))
    ids = [w.player_at(r, t_dec) for r in rows]
    if anchor["player"] not in ids:
        return None
    me = rows[ids.index(anchor["player"])]
    u0, v0 = to_team(S[me, 0], S[me, 1], d)
    players, _ = league_data()
    mates = []
    for r, pid in zip(rows, ids, strict=True):
        if r == me:
            continue
        u, v = to_team(S[r, 0], S[r, 1], d)
        mates.append({"player_id": pid, "name": players.get(pid, {}).get("name", pid),
                      "position": players.get(pid, {}).get("position"), "x": round(float(S[r, 0]), 1),
                      "y": round(float(S[r, 1]), 1), "xt_gain": round(float(threat(u, v) - threat(u0, v0)), 4)})
    mates.sort(key=lambda x: -x["xt_gain"])
    target = (anchor.get("attrs") or {}).get("recipient") if anchor["type"] == "pass" else None
    for mate in mates:
        mate["policy_prob"] = None
    return {"match_id": match_id, "t_ms": t_dec, "anchor_event_id": anchor["id"], "actor": anchor["player"],
            "actor_name": players.get(anchor["player"], {}).get("name", anchor["player"]), "team": anchor["team"],
            "actual": {"kind": EVENT_KIND[anchor["type"]], "actor": anchor["player"], "target": target},
            "ball": [round(float(S[22, 0]), 1), round(float(S[22, 1]), 1)], "attack_tag": "e" if d > 0 else "w",
            "options": None, "teammates": mates}


def attach_options(decision: dict, options: dict | None) -> dict:
    """Add the engine's option probabilities (MCP get_state `options`: team-mate ids, shoot, clear, carry)."""
    if not options:
        return decision
    mates = [{**m, "policy_prob": round(float(options.get(m["player_id"], 0.0)), 4)} for m in decision["teammates"]]
    return {**decision, "teammates": mates,
            "options": {k: round(float(v), 4) for k, v in options.items() if k in ("shoot", "clear", "carry")}}


def proposer_rule(decision: dict, k: int = 3, min_prob: float = 0.05) -> list[dict]:
    """models.yaml `proposer_rule`: passes to the k team-mates with the highest xT gain (never the actual target).
    When the engine's option probabilities are known, only options it gives at least `min_prob` count (the
    RolloutExecutor would drop the rest, audit B.2 guard 1), and shoot / clear / carry fill any free places."""
    actual = decision["actual"]
    known = decision.get("options") is not None

    def plausible(p):
        return not known or (p or 0) >= min_prob

    out = []
    for mate in decision["teammates"]:
        if actual["kind"] == "pass" and mate["player_id"] == actual["target"]:
            continue
        if plausible(mate.get("policy_prob")):
            out.append({"kind": "pass", "actor": decision["actor"], "target": mate["player_id"],
                        "reason": "highest expected-threat gain among team-mates"})
        if len(out) == k:
            return out
    if known:
        tags = {"carry": decision.get("attack_tag", "e"), "shoot": None, "clear": None}
        for kind, p in sorted(decision["options"].items(), key=lambda kv: -kv[1]):
            if kind != actual["kind"] and p >= min_prob and len(out) < k:
                out.append({"kind": kind, "actor": decision["actor"], "target": tags[kind],
                            "reason": "the engine's next most likely choice"})
    return out


def valid_alternatives(decision: dict, proposed: list, k: int = 3) -> list[dict]:
    """Keep well-formed alternatives for this decision point: actor fixed, known targets, not the actual action."""
    mates = {m["player_id"] for m in decision["teammates"]}
    actual = decision["actual"]
    out, seen = [], set()
    for a in proposed if isinstance(proposed, list) else []:
        if not isinstance(a, dict):
            continue
        kind, target = a.get("kind"), a.get("target")
        if kind == "pass" and target not in mates:
            continue
        if kind == "carry" and target not in DIRECTIONS:
            continue
        if kind in ("shoot", "clear", "hold"):
            target = None
        elif kind not in ("pass", "carry"):
            continue
        key = (kind, target)
        if key in seen or (kind == actual["kind"] and target == actual["target"]):
            continue
        seen.add(key)
        out.append({"kind": kind, "actor": decision["actor"], "target": target,
                    "reason": str(a.get("reason", ""))[:200]})
        if len(out) == k:
            break
    return out
