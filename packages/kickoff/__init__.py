"""kickoff: batched numpy match engine with hidden tactical truth (ADR-001)."""

from .engine import Engine, MatchRecord, Override, State
from .errors import BranchError, EngineError
from .events import Event
from .league import League
from .rules import Action, DecisionModel, ScriptedRule

__all__ = ["Action", "BranchError", "DecisionModel", "Engine", "EngineError", "Event", "League", "MatchRecord",
           "Override", "ScriptedRule", "State"]
