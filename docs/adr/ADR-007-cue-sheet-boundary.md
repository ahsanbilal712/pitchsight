# ADR-007: The Cue Sheet is the editorial product boundary

## Status

Accepted, 2026-10-21

## Context

- Every item shown to a viewer must carry its evidence, its verification result, who may see it, and where it came from. The producer must be able to veto it. Replay, live and degraded mode must show the same thing on the same screens.
- The hackathon mentions a rendering partner. Whether that partner's overlay specification is available behind the login is an open question (TECH_PLAN 1.14, question 4). It has not been seen.
- Broadcast integration paths checked in the audit all need adapters. Singular.live's free plan has one watermarked output and 5,000 REST calls per day, with Data Streams on "Trial" (A.1 row 57). CasparCG is GPL-3.0 (row 58). OBS browser sources are transparent by default (row 59). ffmpeg cannot author ID3 timed metadata (row 60). None of these is in the frozen scope.
- `schemas/cue.schema.json` already fixes the shape: 10 `layer` values, 14 `kind` values, `targets.modes` (analyst, casual, player_cam, studio), `text` (headline up to 60 characters, body up to 280), `explain` (`why`, `claims`, `counterfactual_id`, `explanation_id`), `verified`, `producer_status` (auto, approved, vetoed, held) and `provenance` (`mode`, `agent_path`, `trace_id`, `resumed_from_checkpoint`, `model`, `prompt_version`, `cache_key`). The schema description says "English only. No audio."

## Decision

A cue (`schemas/cue.schema.json`, JSON Schema draft 2020-12) is the only editorial output of the system. Everything below the line, the newsroom workflow and `fourth_official`, produces cues. Everything above it, the overlay, studio and fan apps, renders cues. The Director executor (code) is the only emitter and applies `config/budgets.yaml`. `api` filters cues by `targets` server-side and sends them as the WebSocket messages `cue` and `cue_remove`. Screens place cues by `t_in_ms` and `t_out_ms` against the stream clock and never read the blackboard.

A rendering partner integrates at the `cue` stream. If its specification becomes available, `cue.schema.json` gains an adapter; it does not change the producers.

The Cue Sheet is the editorial boundary. The world-state stream (`tracking_frame`, `fact`, `oracle`) is a separate, non-editorial feed that the screens also consume, along with the control messages `moment`, `trace`, `request_info`, `mode` and `spend` (TECH_PLAN 1.9). The overlay draws the pitch, chaos meter and threat front from the world-state feed and draws editorial content only from cues.

## Alternatives rejected

- Screens read the blackboard or Cosmos directly: bypasses the verified flag and the veto, and couples every screen to storage.
- Screens call agents or models: cannot be replayed (ADR-003) and cannot be verified before display.
- Free-form text from agents: the Fact Checker needs structured claims bound to evidence IDs.
- Singular.live, CasparCG or HLS timed metadata as the primary integration: each carries a limit or licence cost (audit A.1 rows 57 to 60). They remain possible adapters.

## Consequences

- Positive: verification, veto and provenance sit at one boundary. All modes use the same screens. Every fixture and cache entry is validated against the schema version it names in CI (TECH_PLAN 1.3).
- Positive: the producer console can show, for any cue, which agents and which model produced it (`provenance.agent_path`, `provenance.model`).
- Negative: schema change is expensive. Removing or retyping a field bumps the major version, needs a new `$id`, and invalidates cache manifests for matches made under the old major (TECH_PLAN 1.3).
- Negative: fixed enums and length caps mean a new overlay layer or kind needs a schema change, not just a screen change.
- Negative: a rendering partner that wants to draw a pitch needs the world-state feed as well as the cues. The cue schema does not carry positions.
- Negative: the partner's specification has not been seen, so the adapter may need fields the cue does not carry.

## Related

- TECH_PLAN 1.1, 1.3, 1.7 (Director budgets, producer veto), 1.9, 1.12, 1.14.
- ADR-003, ADR-005, ADR-006, ADR-008, ADR-010.
- Schemas: `schemas/cue.schema.json`, `schemas/explanation.schema.json`, `schemas/viewer_profile.schema.json`. Config: `config/budgets.yaml`.
- Audit: A.1 rows 57 to 60.
