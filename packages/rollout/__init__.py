"""rollout: The rollout primitive and its callers: Sliding Doors, Oracle, Dugout."""

import policy  # noqa: F401  (loads torch before LightGBM: the policy_v1 path and the heads share one process)

from .core import MatchRef, engine_hash, rollout
from .futures import Futures
from .sliding_doors import option_probs, placebo, sliding_doors

__all__ = ["Futures", "MatchRef", "engine_hash", "option_probs", "placebo", "rollout", "sliding_doors"]
