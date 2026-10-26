# physics

Pitch control, indices, chaos index, speeds, auto-events and the game-state machine.

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

Implementation notes:
- `window.py`: `TrackingWindow` (slice of `tracking.npz`, substitutions applied by `player_at`) and `Frame`.
- `pitch_control.py`: arrival time = 0.7 s reaction on the current velocity + run at 5 m/s; softmin over all 22
  players with Spearman's logistic scale (sigma 0.45 s). Grid rows are y (bottom to top), columns x.
- `indices.py`: turnovers are open-play `possession_change` events (restarts are not chaos). `indices` also returns
  `turnovers`, `turnovers_60s` (exponentially weighted rate per minute, tau 60 s), `transition_share`,
  `contested_frac`, `closing_speed` and `chaos`. Chaos = 20 + 65 × (rate − 1) / 6, clipped to 0–100; the transition
  and contested nudges exist but are weighted 0 (they cost macro F1: 0.748 vs 0.765 on seeds 1–30).
- `state_machine.py`: one timer per threshold; Settled ↔ Transitional at 35/25 for 10 s; Chaotic at 65 for 20 s,
  out at 50 for 30 s. Against the engine's hidden match regimes (truth side `M`): macro F1 0.771 on seeds 1–50.
- Measured on the golden match: p50 0.8 ms, p95 3.4 ms per frame for pitch control + 60 s indices + chaos + speeds +
  state update.
