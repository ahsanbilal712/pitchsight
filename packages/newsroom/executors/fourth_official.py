"""FourthOfficialExecutor: referee moments (offside, foul, card) -> a referee_line draft, by code
(about 5 ms). The ruling is re-derived from the tracking frames (fourth_official.check_offside /
check_foul), so the draft is verified by construction; its numbers are claims that cite the referee event.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from agent_framework import WorkflowContext, handler

from fourth_official import check_foul, check_offside, ruling_to_cue
from newsroom.executors.base import NewsroomExecutor
from newsroom.messages import Draft, Routed

ROOT = Path(__file__).resolve().parents[3]
REFEREE = ("offside", "foul", "card")


def _match_data(deps, match_id: str):
    """(events, TrackingWindow) from the MCP match store when there is one, else the match folder."""
    if deps.store is not None:
        m = deps.store.match(match_id)
        return m.events, m.window
    from physics.window import TrackingWindow
    d = ROOT / "data" / "matches" / match_id[2:]
    events = [json.loads(line) for line in (d / "events.jsonl").read_text().splitlines() if line.strip()]
    return events, TrackingWindow.load(d)


def cue_id_for(event: dict) -> str:
    """c_9NNNNN from the referee event's index: unique per event (a foul and its card share a time)."""
    return f"c_{900000 + int(event['id'][2:]):06d}"


def rule_event(event: dict, events: list[dict], window, match_id: str) -> dict | None:
    """The referee_line cue for one offside, foul or card event (None if the geometry cannot be rebuilt)."""
    by_id = {e["id"]: e for e in events}
    cid = cue_id_for(event)
    if event["type"] == "offside":
        p = by_id.get(event["attrs"].get("pass_event_id"))
        if p is None:
            return None
        ruling = check_offside(window.frame_at(p["t_ms"] - 100), p)
        return None if ruling is None else ruling_to_cue(ruling, event["t_ms"], match_id, cue_id=cid,
                                                         evidence_event_id=event["id"], period=event["period"])
    foul = event if event["type"] == "foul" else next((by_id[r] for r in event.get("related_event_ids", [])
                                                       if r in by_id and by_id[r]["type"] == "foul"), None)
    if foul is None:
        return None
    near = [e for e in events if abs(e["t_ms"] - foul["t_ms"]) <= 200 and e["type"] in ("foul", "card")]
    ruling = check_foul(near, window.slice(foul["t_ms"] - 2000, foul["t_ms"] + 500))
    return None if ruling is None else ruling_to_cue(ruling, event["t_ms"], match_id, cue_id=cid,
                                                     evidence_event_id=event["id"], period=event["period"])


class FourthOfficialExecutor(NewsroomExecutor):
    @handler
    async def rule(self, msg: Routed, ctx: WorkflowContext[Draft]) -> None:
        started = time.perf_counter()
        m = msg.moment
        events, window = _match_data(self.deps, m.match_id)
        by_id = {e["id"]: e for e in events}
        ev = next((by_id[i] for i in m.evidence_event_ids if i in by_id and by_id[i]["type"] in REFEREE), None)
        if ev is None:
            ev = next((e for e in events if e["type"] in REFEREE and e["t_ms"] == m.t_ms), None)
        cue = rule_event(ev, events, window, m.match_id) if ev is not None and window is not None else None
        out = msg.hop(self.id)
        if cue is None:
            draft = Draft(**out.model_dump(), kind="fourth_official", layer="referee_line", headline="Fourth Official",
                          verified=False, checked=True, status="error")
        else:
            draft = Draft(**out.model_dump(), kind="fourth_official", layer="referee_line",
                          headline=cue["text"]["headline"], body=cue["text"]["body"], why=cue["explain"]["why"],
                          claims=cue["explain"]["claims"], graphics=cue["graphics"], verified=True, checked=True)
        self.trace(draft, started, cache_hit=None)
        await ctx.send_message(draft)
