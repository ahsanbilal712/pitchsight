"""Game-state machine over the chaos index with hysteresis.

States: Settled, Transitional, Chaotic. Chaotic is entered only after the chaos index stays above 65 for 20 s and
left only after it stays below 50 for 30 s (then Transitional). Between the other two: Settled -> Transitional
after 10 s above 35, Transitional -> Settled after 10 s below 25 (thresholds fitted to the hidden regimes). Each threshold has one timer that runs from
the first update meeting it and resets on any update that breaks it; state changes do not reset timers, so
65+ for 20 s enters Chaotic even though Settled passes through Transitional on the way.
"""

from __future__ import annotations

SETTLED, TRANSITIONAL, CHAOTIC = "Settled", "Transitional", "Chaotic"
STATES = (SETTLED, TRANSITIONAL, CHAOTIC)

CONDITIONS = {"above65": lambda c: c > 65.0, "below50": lambda c: c < 50.0, "above35": lambda c: c > 35.0,
              "below25": lambda c: c < 25.0}
# (from-states, condition, hold ms, to-state); checked in this order
RULES = (
    ((SETTLED, TRANSITIONAL), "above65", 20_000, CHAOTIC),
    ((CHAOTIC,), "below50", 30_000, TRANSITIONAL),
    ((SETTLED,), "above35", 10_000, TRANSITIONAL),
    ((TRANSITIONAL,), "below25", 10_000, SETTLED),
)


class StateMachine:
    def __init__(self, initial: str = SETTLED) -> None:
        if initial not in STATES:
            raise ValueError(initial)
        self.state = initial
        self.since: dict[str, int | None] = dict.fromkeys(CONDITIONS)
        self.entered_ms: int | None = None

    def update(self, chaos: float, t_ms: int) -> str | None:
        """Feed one chaos value; returns the new state when it changes, else None."""
        for name, cond in CONDITIONS.items():
            if not cond(chaos):
                self.since[name] = None
            elif self.since[name] is None:
                self.since[name] = t_ms
        for sources, name, hold, target in RULES:
            start = self.since[name]
            if self.state in sources and start is not None and t_ms - start >= hold:
                self.state, self.entered_ms = target, t_ms
                return target
        return None
