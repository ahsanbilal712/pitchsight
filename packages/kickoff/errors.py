"""Kickoff engine errors."""


class EngineError(RuntimeError):
    """Raised when the simulation reaches an invalid state (for example a NaN in S); the match is discarded."""
