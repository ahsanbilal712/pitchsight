# physics

Pitch control, indices, chaos index, speeds, auto-events and the game-state machine.

Interface restated from `TECH_PLAN.md` section 1.4 "physics (analytics)" (TECH_PLAN wins on conflict).
Tests live in `tests/physics/`.

```python
def pitch_control(S: np.ndarray, cell_m: float = 2.0) -> np.ndarray                # [34,53] home share, Spearman-style
def indices(window: TrackingWindow, events: list[Event]) -> dict[str, float]       # control_home, control_away, pressure_home/away, tempo, turnover_rate
def chaos_index(pc: np.ndarray, turnovers_60s: int, transition_share: float) -> float   # 0–100 fallback formula until the learned head exists
def speeds(window: TrackingWindow) -> SpeedReport                                   # ball_kmh, shot_kmh, sprints[(player, kmh, t_ms)]
def auto_events(window, events) -> list[Event]                                      # pressing_trap, line_break, switch_of_play, overload, counter_attack, big_chance
class StateMachine: def update(self, chaos: float, t_ms: int) -> str | None         # Settled/Transitional/Chaotic with hysteresis (enter >65 for 20 s, exit <50 for 30 s)
```

Performance: all of the above for one 100 ms frame in < 15 ms on CPU (target; 1,802 cells × 22 players vectorised). Tests: pitch control sums to 1 per cell; symmetry test (mirror the pitch, shares invert); state machine hysteresis unit tests. Libraries: numpy, scipy 1.18.1.
