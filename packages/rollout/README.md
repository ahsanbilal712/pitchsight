# rollout

The rollout primitive and its callers: Sliding Doors, Oracle, Dugout.

Interface restated from `TECH_PLAN.md` section 1.4 "rollout (the primitive and three callers)" (TECH_PLAN wins on conflict).
Tests live in `tests/rollout/`.

See 1.5. Public interface:

```python
def rollout(state: State, overrides: Override | None, B: int, horizon_s: float, seed: int,
            engine: Literal["scripted_v1", "policy_v1"] = "scripted_v1") -> Futures
def sliding_doors(match: MatchRef, t_ms: int, alternative: Action, n: int = 200, horizon_s: float = 8, seed: int = 4242, engine=...) -> CounterfactualResult
def oracle(match: MatchRef, t_ms: int, n: int = 100, horizon_s: float = 8, seed=...) -> Forecast          # p_shot_10s per team, likely zone, likely shooter
def dugout(match: MatchRef, t_ms: int, team: str, options: list[StyleDelta], n: int = 100, horizon_s: float = 8, seed=...) -> list[OptionResult]
```

Implementation notes (T-016):
- `MatchRef(seed, match_dir=...)` re-simulates world 0 from kick-off to any tick (never reads `truth.json`);
  `state_at(t_ms)` returns a `State` whose `source` is a one-world engine fork. Events with ids come from
  `match_dir` (`events.jsonl` or `.jsonl.gz`).
- `Engine.branch(t_ms, B, override, seed, decide_now)` forks world 0 into B worlds; world b uses
  `default_rng(seed + b)`. `override.first_action` (an `Action`: team slot for passes, unit vector for carries) is
  played on the first tick; `decide_now=True` makes the engine's own choice on the first tick (the baseline at a
  decision point). `override.styles` shifts a team's style profile (Dugout).
- `rollout(..., decide_now=False, events=None)`: `events` (the match so far) give the win-probability context
  (xT and xG difference over 15 min, chaos); `Futures.digest()` hashes everything for the determinism test;
  `Futures.per_world` keeps per-world p(goal), win probability and first decision.
- `sliding_doors` branches at the decision tick (event t_ms − 100). `policy_prob` is the softmax of the rule's
  utilities (`option_probs`). `compute_ms` is null so cached results stay byte-identical.
- `placebo`: forced actual action vs the baseline worlds whose own first choice was that action (same seeds);
  passes inside the two-sample 95% interval, floored at ±0.005 (half a displayed point).
- Measured on this Mac, idle: B=200 × 90 s 1.265 s CPU, B=200 × 60 s 0.845 s, B=200 × 8 s about 0.12 s.
