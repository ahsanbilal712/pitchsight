# ADR-001: Scripted Kickoff engine is the live world

## Status

Accepted, 2026-10-21

## Context

- Sliding Doors needs a world that can be cloned at any past instant and run forward 200 times. The same world must also produce the events and 10 Hz tracking for both replay and live mode.
- No football behaviour model with public weights exists (audit A.1 row 21: FootBots, TranSPORTmer, TacticAI, GenTac, TacticGen, Ball Radar, MIDAS and CausalTraj were checked). Published soccer forecasters are stable for only 4 to 6.4 s (audit B.1). A learned world model cannot be trusted on the live path by day 7.
- gfootball is archived (19 Aug 2026; last code commit Apr 2022). PyPI has Windows-only wheels. `pip install gfootball` failed in three spikes on this Mac: first on a `psutil` import inside the build environment, then on a missing `cmake` (audit A.2). The "successor game server" domain `research-football.dev` does not resolve. The Docker route was not built because the daemon was not running.
- gfootball does support `get_state` / `set_state`, so branching is real there (audit A.1 row 6). The audit estimates 200 branches x 80 steps at about 60 core-seconds (about 270 steps/s per core, inferred), so 5 to 10 s on a 12-core box. That is too slow for a live cue.
- A scripted numpy rollout at B=200 was measured on this Mac: 150 steps (15 s) took 4.2 s cold and about 0.2 s warm; 900 steps (90 s) took 1.2 s warm (audit A.2).
- The frozen scope (`DEMO_MASTERPLAN_50USD.md` section 1) names the Kickoff scripted engine as the world and says no gfootball install. The rules require synthetic, football-realistic data (TECH_PLAN 1.12).

## Decision

`kickoff.Engine` is a deterministic, batched numpy engine with hidden tactical truth. It exposes `step()`, `state()`, `branch(t_ms, batch, override)` and `play()`. It takes a `DecisionModel`; the default is `ScriptedRule()` (utility plus noise, deterministic given the rng). `truth.json` (phases, momentum, style profiles) is written beside `events.jsonl` and `tracking.npz` but never appears in events.

The same engine generates the golden match (seed 4242), live matches, and every rollout (`rollout(..., engine="scripted_v1")` is the default). The learned `DecisionPolicy` is an optional `DecisionModel` plugged into the engine (ADR-002, ADR-012). It is not the world.

## Alternatives rejected

- gfootball as the live world: not installable on this machine, archived, and 5 to 10 s per 200 branches (inferred).
- gfootball as an offline footage and counterfactual source (the audit's one-day Docker spike): dropped by the frozen scope; `config/pins.txt` lists it as not a dependency.
- A learned world model generating tracking: no public weights, and horizons beyond 4 to 6.4 s are unproven.
- Per-tick learned rollouts: measured at 3 to 12 s for 15 s of play (see ADR-002).

## Consequences

- Positive: the headline feature exists by day 3 with no trained model. Results are reproducible byte for byte from `(state, overrides, B, horizon_s, seed, engine, engine_hash)`. Hidden truth gives a score for state detection (F1 >= 0.75, TECH_PLAN 1.11). Training and running cost $0.
- Positive: 200 x 90 s in 1.2 s warm on CPU fits an Azure CPU-only live path (ADR-009).
- Negative: realism is bounded by the engine's style profiles. The policy must be calibrated to the engine, not to football.
- Negative: the audit's circularity objection (B.6) applies in full: the simulator grades itself. The audit called a second independent world the strongest answer. This ADR gives that up. What remains is realism validation against SkillCorner (MIT) and DFL (CC BY 4.0) marginals, the placebo test, and wording such as "in 200 simulated replays".
- Negative: any change to the engine after day 7 invalidates the replay cache and the video (ADR-003).

## Related

- TECH_PLAN 1.1, 1.4 (kickoff), 1.5, 1.11, 1.12, 1.13 ("gfootball temptation").
- ADR-002, ADR-003, ADR-012.
- Schemas: `schemas/event.schema.json`, `schemas/counterfactual.schema.json`.
- Audit: A.1 rows 1 to 9 and 21, A.2, B.1, B.2, B.6, C.5.
