"""Messages that flow along the newsroom graph. One workflow run per moment.

Every message carries the run envelope (run id, mode, branch, moment, agent path); executors evolve it with
`hop()` and `model_copy(update=...)`. All types are registered for checkpoint restore.
"""

from __future__ import annotations

from typing import Literal

from agent_framework import register_checkpoint_type
from pydantic import BaseModel, ConfigDict, Field

Branch = Literal["fast", "explained", "panel", "referee", "recap", "drop"]
Mode = Literal["replay", "live", "degraded"]


class Moment(BaseModel):
    """A blackboard `moments` document; unknown fields are kept."""

    model_config = ConfigDict(extra="allow")
    moment_id: str
    match_id: str
    t_ms: int
    clock: str = "00:00"
    period: int = 1
    kind: str
    leverage: float | None = None
    players: list[str] = Field(default_factory=list)
    team: str | None = None
    evidence_event_ids: list[str] = Field(default_factory=list)
    hypotheses: list = Field(default_factory=list)
    fast: bool = False
    status: str = "new"


class Envelope(BaseModel):
    run_id: str
    mode: Mode = "replay"
    branch: Branch | None = None
    moment: Moment
    agent_path: list[str] = Field(default_factory=list)
    trace_id: str = ""
    resumed_from_checkpoint: str | None = None

    def hop(self, executor_id: str, **update):
        return self.model_copy(update={"agent_path": [*self.agent_path, executor_id], **update})


class MomentIn(Envelope):
    """Start message: the worker wraps each new blackboard moment in one of these."""


class Routed(Envelope):
    """Scout output, one per branch the moment takes."""


class Proposals(Envelope):
    alternatives: list[dict] = Field(default_factory=list)
    decision: dict | None = None        # the on-ball decision point the alternatives replace (newsroom.decision)


class RolloutDone(Envelope):
    alternatives: list[dict] = Field(default_factory=list)
    decision: dict | None = None
    counterfactual: dict | None = None


class Explained(Envelope):
    explanation: dict
    counterfactual: dict | None = None


class Draft(Envelope):
    """Narrator / fast-line / panel / recap output; the Fact Checker returns it with `verified` and `diff` set."""

    kind: str = "fast_line"
    layer: str = "lower_third"
    headline: str = ""
    body: str = ""
    why: str = ""
    claims: list[dict] = Field(default_factory=list)
    explanation: dict | None = None
    counterfactual: dict | None = None
    graphics: dict | None = None
    attempt: int = 1
    verified: bool = False
    checked: bool = False
    diff: list[dict] = Field(default_factory=list)
    model: str | None = None
    prompt_version: str | None = None
    cache_key: str | None = None
    status: str = "ok"            # ok | template | cache_miss | error
    reason: str | None = None     # why a non-ok status: the exception or "invalid_json" (studio trace drawer)


class CueOut(Envelope):
    cue: dict


class ProducerApproval(Envelope):
    """Director -> producer (request_info): a recap cue waiting for approval."""

    cue: dict


class ProducerDecision(BaseModel):
    """Producer -> Director (the response): approved, vetoed or held."""

    status: Literal["approved", "vetoed", "held"]


for _cls in (Moment, Envelope, MomentIn, Routed, Proposals, RolloutDone, Explained, Draft, CueOut, ProducerApproval,
             ProducerDecision):
    register_checkpoint_type(_cls)
