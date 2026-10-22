"""DirectorExecutor: turns a checked draft into a schema-valid cue under the screen-time budgets (TECH_PLAN 1.7
"Director budgets", config/budgets.yaml `director`, T-021).

Hard rules: no overlay during a shot sequence (shot until ball dead or possession change, max 6 s) and none within
3 s after a goal (the cue waits); same kind within 90 s, unshown for 45 s, Sliding Doors below leverage 0.04 and
Oracle below p_shot 0.30 are dropped. Per viewer mode: allowed kinds, min gap between lower-thirds, max cues per
10 minutes, casual Sliding Doors per half. The studio sees every cue that reaches any viewer mode.

The cue id comes from the moment number and the branch only (`cue_id_for`), so a resumed run (T-051) emits the
same id as an uninterrupted one. Spend cap reached -> degraded mode and a `modes` document; a model error, timeout,
cache miss or third rejected attempt -> template line from verified claims and a red trace row.
"""

from __future__ import annotations

import time

from agent_framework import WorkflowContext, handler, response_handler

from blackboard.ids import format_id, parse_id
from newsroom.config import load_budgets
from newsroom.executors.base import Deps, NewsroomExecutor
from newsroom.factcheck import league_data, verify_claims
from newsroom.messages import CueOut, Draft, ProducerApproval, ProducerDecision
from newsroom.templates import clip, template_line

BRANCH_INDEX = {"fast": 0, "explained": 1, "panel": 2, "referee": 3, "recap": 4}
DURATION_MS = {"lower_third": 8000, "ticker": 6000, "player_tag": 6000, "referee_line": 8000, "recap_card": 15000,
               "pitch_overlay": 8000, "heatmap": 10000, "radar": 8000, "threat_front": 8000, "options_card": 8000}
PRIORITY = {"goal": 0.95, "fourth_official": 0.9, "sliding_doors": 0.8, "big_chance": 0.75, "recap": 0.7,
            "oracle": 0.7, "state_change": 0.6}
SEQUENCE_END = {"possession_change", "goal", "set_piece", "period_end", "foul", "card", "substitution"}
VIEWER_MODES = ("analyst", "casual", "player_cam")
CLAIM_FIELDS = ("text", "kind", "value", "unit", "evidence_ids", "verified", "reject_reason")
SHOT_SEQUENCE_MAX_MS = 6000


def cue_id_for(moment_id: str, branch: str | None) -> str:
    """c_ + moment number x 10 + branch index: mo_00077 explained -> c_000771."""
    _, n = parse_id(moment_id)
    return format_id("cues", n * 10 + BRANCH_INDEX.get(branch or "fast", 0))


def clock(t_ms: int) -> str:
    return f"{t_ms // 60000:02d}:{(t_ms // 1000) % 60:02d}"


class Budgets:
    def __init__(self, cfg: dict | None = None) -> None:
        d = (cfg or load_budgets())["director"]
        self.modes: dict = d["modes"]
        self.hard: dict = d["hard_rules"]

    def allows_kind(self, mode: str, kind: str) -> bool:
        kinds = self.modes[mode]["kinds"]
        return "all" in kinds or kind in kinds


def place(t_ms: int, events: list[dict]) -> tuple[int, list[str]]:
    """Push t_ms out of shot sequences and the 3 s after each goal. Returns (t_in, reasons)."""
    reasons: list[str] = []
    shots = [e for e in events if e["type"] == "shot"]
    goals = [e["t_ms"] for e in events if e["type"] == "goal"]
    for _ in range(10):
        moved = False
        for s in shots:
            end = min((e["t_ms"] for e in events if e["t_ms"] > s["t_ms"] and e["type"] in SEQUENCE_END),
                      default=s["t_ms"] + SHOT_SEQUENCE_MAX_MS)
            end = min(end, s["t_ms"] + SHOT_SEQUENCE_MAX_MS)
            if s["t_ms"] <= t_ms < end:
                t_ms, moved = end, True
                reasons.append(f"shot_sequence:{s['id']}")
        for g in goals:
            if g <= t_ms < g + 3000:
                t_ms, moved = g + 3000, True
                reasons.append("after_goal")
        if not moved:
            break
    return t_ms, reasons


class DirectorExecutor(NewsroomExecutor):
    def __init__(self, id: str, deps: Deps, budgets: Budgets | None = None) -> None:
        self.budgets = budgets or Budgets()
        super().__init__(id, deps)

    # ------------------------------------------------------------------ mode
    def _mode(self, msg: Draft) -> str:
        guard = self.deps.guard
        if guard is not None and not self.deps.state.get("degraded"):
            try:
                guard.check(msg.moment.match_id)
            except Exception as exc:
                if type(exc).__name__ != "SpendCapReached":
                    raise
                self.deps.state["degraded"] = True
                self.deps.state["degraded_reason"] = str(exc)
        if self.deps.state.get("degraded"):
            m = msg.moment
            if not self.deps.state.get("mode_announced", {}).get(m.match_id):
                self.deps.bb.put("modes", {"id": f"mode_{m.match_id}_{m.t_ms}", "match_id": m.match_id,
                                           "t_ms": m.t_ms, "mode": "degraded",
                                           "reason": self.deps.state.get("degraded_reason", "spend cap")})
                self.deps.state.setdefault("mode_announced", {})[m.match_id] = True
            return "degraded"
        return msg.mode

    # ------------------------------------------------------------------ budgets
    def _targets(self, kind: str, layer: str, t_in: int, msg: Draft) -> tuple[list[str], dict]:
        """Viewer modes that may show this cue, and why the others may not."""
        hard = self.budgets.hard
        m = msg.moment
        history = self.deps.bb.query("cues", match_id=m.match_id, t_from_ms=t_in - 600_000, t_to_ms=t_in)
        history = [c for c in history if c.get("producer_status") != "vetoed"]
        modes, why = [], {}
        for mode in VIEWER_MODES:
            cfg = self.budgets.modes[mode]
            seen = [c for c in history if mode in c["targets"]["modes"]]
            if not self.budgets.allows_kind(mode, kind):
                why[mode] = "kind_not_in_mode"
            elif any(c["kind"] == kind and c["layer"] == layer   # a debate card is not a second lower-third
                     and t_in - c["t_in_ms"] < hard["dedupe_same_kind_window_s"] * 1000
                     for c in seen):
                why[mode] = "dedupe_same_kind"
            elif layer == "lower_third" and any(c["layer"] == "lower_third" and t_in - c["t_in_ms"] <
                                                cfg["min_gap_s"] * 1000 for c in seen):
                why[mode] = "min_gap"
            elif len(seen) >= cfg["max_per_10min"]:
                why[mode] = "max_per_10min"
            elif kind == "sliding_doors" and "sliding_doors_per_half" in cfg and sum(
                    1 for c in self.deps.bb.query("cues", match_id=m.match_id, kind="sliding_doors", period=m.period)
                    if mode in c["targets"]["modes"]) >= cfg["sliding_doors_per_half"]:
                why[mode] = "sliding_doors_per_half"
            else:
                modes.append(mode)
        return modes, why

    def _drop_reason(self, kind: str, msg: Draft, t_in: int) -> str | None:
        hard = self.budgets.hard
        m = msg.moment
        if kind == "sliding_doors" and (m.leverage or 0) < hard["leverage_floor_for_sliding_doors"]:
            return "leverage_below_floor"
        if kind == "oracle" and float(getattr(m, "p_shot", 0) or 0) < hard["oracle_min_p_shot"]:
            return "oracle_p_shot_below_floor"
        expire_ms = hard["expire_unshown_after_s"] * 1000
        now = self.deps.state.get("match_clock_ms")
        if t_in - m.t_ms > expire_ms or (now is not None and now - m.t_ms > expire_ms):
            return "expired"
        return None

    # ------------------------------------------------------------------ cue
    def _text(self, msg: Draft) -> tuple[dict, list[dict], str, str | None]:
        """(text, verified claims, why, red-row status). Template on model failure or a third rejection."""
        verified = [c for c in msg.claims if c.get("verified")]
        failed = msg.status if msg.status in ("error", "cache_miss", "timeout") else None
        if failed or not msg.verified:
            t = template_line(msg.kind, verified)
            check = verify_claims(msg.moment.match_id, t["claims"], self.deps.bb,
                                  {"headline": t["headline"], "body": t["body"]})
            claims = [c for c in check["claims"] if c["verified"]]
            return {"headline": t["headline"], "body": t["body"]}, claims, t["body"], failed or "rejected_x3"
        return {"headline": msg.headline, "body": msg.body}, verified, msg.why or msg.body, None

    def _graphics(self, msg: Draft) -> dict:
        m = msg.moment
        g: dict = {"players_highlight": [p for p in m.players if isinstance(p, str) and len(p) == 5][:6],
                   "lines": []}
        cf = msg.counterfactual
        if cf:
            g["pitch_control_snapshot"] = cf.get("pitch_control_snapshot_id")
            sample = (cf.get("futures_sample") or [[]])[0]
            if sample:
                g["ghost_trail"] = sample
            meta = self.deps.bb.query("events", match_id=m.match_id, type="match_metadata", limit=1)
            _, clubs = league_data()
            home = clubs.get(meta[0]["attrs"]["home"], {}).get("short_name", "Home") if meta else "Home"
            g["bar"] = {"label": f"{home} win chance", "from": cf["baseline"]["win_prob_home"],
                        "to": cf["alternative_outcome"]["win_prob_home"]}
        g.update(msg.graphics or {})
        return g

    @handler
    async def direct(self, msg: Draft, ctx: WorkflowContext[CueOut]) -> None:
        started = time.perf_counter()
        m = msg.moment
        out = msg.hop(self.id)
        mode = self._mode(msg)
        events = self.deps.bb.query("events", match_id=m.match_id, t_from_ms=m.t_ms - SHOT_SEQUENCE_MAX_MS,
                                    t_to_ms=m.t_ms + 60_000)
        t_in, moved = place(m.t_ms, events)
        kind, layer = msg.kind, msg.layer
        drop = self._drop_reason(kind, msg, t_in)
        modes, why_not = ([], {}) if drop else self._targets(kind, layer, t_in, msg)
        if drop or not modes:
            self.trace(out, started, status="suppressed", reason=drop or why_not, t_in_ms=t_in)
            return
        text, claims, why, red = self._text(msg)
        cf = msg.counterfactual or {}
        exp = msg.explanation or {}
        cue = {
            "schema_version": "1.0.0", "cue_id": cue_id_for(m.moment_id, msg.branch), "match_id": m.match_id,
            "moment_id": m.moment_id, "t_in_ms": t_in, "t_out_ms": t_in + DURATION_MS.get(layer, 8000),
            "clock": clock(t_in), "period": m.period, "layer": layer,
            "priority": round(min(1.0, PRIORITY.get(kind, 0.5) + (m.leverage or 0)), 3),
            "leverage": None if m.leverage is None else round(min(1.0, abs(m.leverage)), 4), "kind": kind,
            "targets": {"modes": [*modes, "studio"], "clubs": ["any"],
                        "players": [p for p in m.players if isinstance(p, str) and len(p) == 5]},
            "text": text, "graphics": self._graphics(msg),
            "explain": {"why": clip(why, 400), "claims": [{k: c.get(k) for k in CLAIM_FIELDS} for c in claims],
                        "counterfactual_id": cf.get("counterfactual_id"),
                        "explanation_id": exp.get("explanation_id")},
            "verified": all(c["verified"] for c in claims) if red else bool(msg.verified), "producer_status": "auto",
            "provenance": {"mode": mode, "agent_path": [*out.agent_path, "cuebus"], "trace_id": msg.trace_id,
                           "resumed_from_checkpoint": msg.resumed_from_checkpoint
                           or self.deps.state.get("resumed", {}).get(msg.run_id),
                           "model": "template" if red else msg.model, "prompt_version": msg.prompt_version,
                           "cache_key": msg.cache_key},
        }
        envelope = out.model_dump(include=set(CueOut.model_fields) - {"cue"})
        if kind == "recap":   # TECH_PLAN 1.7 "Producer veto": a recap waits for the producer
            self.trace(out, started, status="awaiting_producer", cue_id=cue["cue_id"], t_in_ms=t_in,
                       model=cue["provenance"]["model"])
            await self.handle_recap(cue, envelope, ctx)
            return
        self.trace(out, started, status=red or "ok", cue_id=cue["cue_id"], t_in_ms=t_in, moved=moved,
                   excluded=why_not, model=cue["provenance"]["model"])
        await ctx.send_message(CueOut(**envelope, cue=cue))

    async def handle_recap(self, cue: dict, envelope: dict, ctx: WorkflowContext[CueOut]) -> None:
        await ctx.request_info(request_data=ProducerApproval(**envelope, cue=cue), response_type=ProducerDecision)

    @response_handler
    async def on_decision(self, original_request: ProducerApproval, response: ProducerDecision,
                          ctx: WorkflowContext[CueOut]) -> None:
        started = time.perf_counter()
        cue = {**original_request.cue, "producer_status": response.status}
        self.trace(original_request, started, status=f"producer_{response.status}", cue_id=cue["cue_id"])
        if response.status != "vetoed":
            envelope = original_request.model_dump(include=set(CueOut.model_fields) - {"cue"})
            await ctx.send_message(CueOut(**envelope, cue=cue))

