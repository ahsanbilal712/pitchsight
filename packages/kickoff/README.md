# kickoff

Batched numpy match engine with hidden tactical truth.

Tests live in `tests/kickoff/`.

Purpose: generate a football-realistic synthetic match with events, 10 Hz tracking and hidden truth; expose a batched state for rollouts.

```python
class Engine:
    def __init__(self, league: League, home: str, away: str, seed: int, batch: int = 1,
                 decision_model: DecisionModel = ScriptedRule(), styles: dict | None = None) -> None
    def step(self) -> list[Event]            # advances 100 ms for all B worlds
    def state(self) -> State                 # S [B,23,6], ball_z [B], holder [B], possession [B], score [B,2], t_ms, period
    def branch(self, t_ms: int, batch: int, override: Override | None) -> "Engine"   # clone at t_ms into `batch` worlds
    def play(self, until_ms: int | None = None) -> MatchRecord                      # events, tracking, truth
class League: clubs, players (fictional), style profiles; loaded from data/league/*.json
class ScriptedRule(DecisionModel): def decide(self, state: State) -> Action        # utility + noise; deterministic given rng
@dataclass class Override: first_action: Action; styles: dict[str, StyleDelta] | None
```

Inputs: league JSON, seed. Outputs: `events.jsonl` (schema-valid), `tracking.npz`, `truth.json` (`phases[]`, `momentum[]`, `style_profiles`), `match_metadata` event first. Performance: a 90-minute match at B=1 in under 60 s on CPU (target); `branch` + 900 steps at B=200 in ≤ 1.3 s (measured 1.2 s warm). Failure behaviour: any NaN in `S` raises `EngineError` and the match is discarded. Tests: schema validity of every event; seed reproducibility (byte-identical `events.jsonl` across two runs); no truth leakage (no key from `truth.json` appears in events); realism ranges on 50 matches (pass completion 78–86%, 1.0–1.8 goals per team, 8–16 shots per team). Libraries: numpy 2.5.4, pydantic 2.14.1.
