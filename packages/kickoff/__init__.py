"""kickoff: batched numpy match engine with hidden tactical truth (ADR-001)."""

from .engine import Engine, MatchRecord, State
from .errors import EngineError
from .events import Event
from .league import League
from .rules import Action, DecisionModel, ScriptedRule

__all__ = ["Action", "DecisionModel", "Engine", "EngineError", "Event", "League", "MatchRecord", "ScriptedRule",
           "State"]
