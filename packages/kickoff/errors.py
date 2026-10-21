"""Kickoff engine errors."""


class EngineError(RuntimeError):
    """Raised when the simulation reaches an invalid state (for example a NaN in S); the match is discarded."""


class BranchError(ValueError):
    """The requested branch cannot be made (no player in control, illegal or offside first action)."""
