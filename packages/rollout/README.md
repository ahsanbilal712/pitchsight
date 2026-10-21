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
