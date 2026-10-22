"""FastLineExecutor: the Scout's fast path (goal, big chance, milestone, player tag) to a one-line cue in < 3 s
(TECH_PLAN 1.7, T-020). Claims come straight from the moment's evidence events, are verified first, and the
narrator_fast model (or the template) writes the line from those claims only.
"""

from __future__ import annotations

import time

from agent_framework import WorkflowContext, handler

from blackboard.protocol import NotFound
from newsroom.executors.base import NewsroomExecutor
from newsroom.executors.narrator import CUE_KINDS, write_line
from newsroom.factcheck import league_data, verify_claims
from newsroom.messages import Draft, Routed

FAST_KINDS = {"goal", "big_chance", "milestone", "player_tag"}


def surname(player_id: str) -> str | None:
    players, _ = league_data()
    p = players.get(player_id)
    return p["name"].split()[-1] if p else None


def claims_from_moment(moment, bb) -> list[dict]:
    """Player, team and xG claims bound to the moment's evidence events (unverified). For a goal or a big chance
    only the scorer or shooter is named: the evidence also holds the passer, the goalkeeper and the defender who
    lost the ball, and a one-line cue must not credit the wrong player (T-057 review)."""
    claims: list[dict] = []
    seen: set[str] = set()
    _, clubs = league_data()
    events = []
    for eid in moment.evidence_event_ids:
        try:
            events.append((eid, bb.get("events", eid, moment.match_id)))
        except NotFound:
            continue
    focus = {"goal": ("goal",), "big_chance": ("shot",)}.get(moment.kind)
    if focus:
        last = [ev.get("player") for _, ev in events if ev.get("type") in focus]
        named = set(last[-1:])
        shots = [(eid, ev) for eid, ev in events if ev.get("type") == "shot"]
        events = [(eid, ev) for eid, ev in events if ev.get("player") in named and ev.get("type") in
                  ("goal", "shot")] + shots[-1:]
        events = list(dict(events).items())
    if focus and moment.team is None:
        moment.team = next((ev["team"] for _, ev in events if ev.get("team") in ("home", "away")), None)
    for eid, ev in events:
        pid = ev.get("player")
        if focus and pid not in named:
            pid = None
        if isinstance(pid, str) and pid not in seen and (name := surname(pid)):
            seen.add(pid)
            claims.append({"text": name, "kind": "player", "value": pid, "unit": None, "evidence_ids": [eid],
                           "verified": False})
        xg = (ev.get("attrs") or {}).get("xg")
        if ev.get("type") == "shot" and isinstance(xg, int | float):
            claims.append({"text": f"{xg:.2f} xG", "kind": "number", "value": round(float(xg), 2), "unit": "xg",
                           "evidence_ids": [eid], "verified": False})
    team = moment.team
    meta = bb.query("events", match_id=moment.match_id, type="match_metadata", limit=1)
    club_id = meta[0]["attrs"].get(team) if meta and team in ("home", "away") else None
    if club_id in clubs and moment.evidence_event_ids:
        claims.append({"text": clubs[club_id]["short_name"], "kind": "team", "value": club_id, "unit": None,
                       "evidence_ids": [moment.evidence_event_ids[0]], "verified": False})
    return claims


class FastLineExecutor(NewsroomExecutor):
    @handler
    async def line(self, msg: Routed, ctx: WorkflowContext[Draft]) -> None:
        started = time.perf_counter()
        m = msg.moment
        kind = m.kind if m.kind in CUE_KINDS else "fast_line"
        checked = verify_claims(m.match_id, claims_from_moment(m, self.deps.bb), self.deps.bb)["claims"]
        claims = [c for c in checked if c["verified"]]
        line = await write_line(self.deps, msg, kind, claims, producer="fast_line")
        out = Draft(**msg.hop(self.id).model_dump(), kind=kind,
                    layer="player_tag" if kind == "player_tag" else "lower_third",
                    headline=line["headline"], body=line["body"], claims=claims, model=line.get("model"),
                    prompt_version=line["prompt_version"], cache_key=line.get("cache_key"), status=line["status"],
                    reason=line.get("reason"))
        self.trace(out, started, status=line["status"], model=line.get("model"), tokens_in=line.get("tokens_in", 0),
                   tokens_out=line.get("tokens_out", 0), cost_usd=line.get("cost_usd", 0.0),
                   cache_hit=line.get("cache_hit"), reason=line.get("reason"))
        await ctx.send_message(out)
