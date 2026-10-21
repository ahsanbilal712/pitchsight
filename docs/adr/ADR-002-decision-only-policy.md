# ADR-002: Decision-only learned policy, 6-8 s horizon, hand-off to the goal-in-8-s head

## Status

Accepted, 2026-10-21

## Context

- The audit timed a 4.7M-parameter set transformer (6 layers, d=256, batch 200 x 23 tokens, PyTorch 2.14.1): 80 ms per forward pass on CPU and 20 ms on Apple MPS (measured). A per-tick rollout of 150 steps (15 s) therefore costs 12 s on CPU and 3 s on MPS (audit A.2).
- Calling the policy only at decisions was also measured: 15 calls at batch 200 took 1.2 s on CPU and 0.3 s on MPS. This is the figure TECH_PLAN quotes for 200 x 8 s futures.
- Published stable horizons are short: FootBots 4 s, CausalTraj 4 s, GenTac 5 s, TranSPORTmer 6.4 s one-shot (audit B.1). A 15 s per-tick horizon is 2.3 to 3.75 times longer than any published soccer result. Naive rollouts compound error (the DAgger bound grows as T^2 times epsilon; Le et al. 2017 report 20 to 30 m error versus about 4 m with rollout-aware training).
- After a forced first action the state may be one the policy never saw. The audit calls the results "plausibility-weighted scenario samples", not forecasts (B.2).
- An 8 s horizon needs about 8 to 15 policy calls, depending on possession changes (at one call per second, 8 calls, plus extra calls when possession changes). The measured 15-call time therefore covers the worst case, so the budget is conservative.

## Decision

The policy is called only at decision points: (a) a player gains control, or (b) 1.0 s has passed since the last call for the current holder. Between calls the previous action persists, off-ball players move toward role targets from the style profile, the ball follows ballistic physics, and duels resolve by deterministic rules (TECH_PLAN 1.5). `rollout(...)` caps the learned horizon at `horizon_s <= 8`. This is the top of the audit's 6 to 8 s range. The gates in TECH_PLAN 1.6 test ball error at 4 s and team shape at 8 s.

For worlds with no goal inside the horizon, the terminal state is valued by `GoalIn8sHead`: `p_goal_team = mean_b[goal_b + (1 - goal_b) * head(terminal_b)]`. `policy_v1` loads only if its `metrics.json` passes the gates in TECH_PLAN 1.6 (override: `WHYLINE_ALLOW_UNGATED_POLICY=1`). If any gate fails by the end of day 4, `scripted_v1` stays the engine for every cached counterfactual and the policy ships as a documented experiment.

## Alternatives rejected

- Per-tick learned policy: 3 to 12 s per 15 s rollout, measured.
- 15 s horizons: beyond every published stable horizon.
- gfootball `set_state` as the futures generator: about 5 to 10 s per 200 branches (inferred) and not installable here (ADR-001).

## Consequences

- Positive: 200 x 8 s futures in about 0.3 s on MPS and 1.2 s on CPU. Those are measured for 15 calls, and an 8 s horizon needs 8 to 15, so the budget is conservative. Off-ball movement is physics, which removes the main drift source.
- Positive: a pre-wired scripted fallback means a weak policy cannot block the demo.
- Negative: 8 s is above the longest published stable horizon (6.4 s), though inside the audit's 6 to 8 s range. Futures must be labelled as simulated samples with n, horizon and seed on screen.
- Negative: the head's value for the terminal state is a model estimate beyond 8 s, and is labelled as such.
- Negative: the Decision Index needs a rollout at every on-ball decision (about 1,500 per match), so it is precomputed for the golden match only (TECH_PLAN 1.14 item 3). The Oracle runs at 2 s with n=200 in replay but 5 s with n=50 live (1.14 item 2).
- Negative: rollout-aware training loss (audit B.1 mitigation) is not in the v1 training spec (1.6). DEMO_MASTERPLAN_50USD section 8 schedules it for policy v2, days 8 to 10.

## Related

- TECH_PLAN 1.4 (policy, rollout), 1.5, 1.6, 1.13 (policy risk), 1.14.
- ADR-001, ADR-012.
- Schemas: `schemas/counterfactual.schema.json` (n, horizon, seed, engine). Config: `config/budgets.yaml` `latency_slo.counterfactual_ms`.
- Audit: A.2, B.1, B.2, C.1.
