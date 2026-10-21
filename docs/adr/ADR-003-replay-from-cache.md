# ADR-003: Replay-from-cache is the demo mechanism

## Status

Accepted, 2026-10-21

## Context

- The two-minute video must be recorded with no live failure. `DEMO_MASTERPLAN_50USD.md` section 6 defines "flawless" as: every frame is the real product, and nothing can fail during recording.
- The audit ranks "demo recording fails because live LLM and GPU calls are flaky" as failure 8 of 10 (D.1). Its early-warning signal is no replay-with-cached-outputs mode by day 21.
- Live timing is too variable to film. The audit puts a fully explained cue at 10 to 20 s p50 and about 25 s p95 when serial (C.1). The Tactician with two or three tool rounds is 4 to 10 s of that.
- Judges may test the project. The audit recommends a replay mode with cached model outputs that runs on a laptop (C.4). The acceptance list asks for three identical replays on a clean machine with no network (DEMO section 9).
- The Anthropic Batch API halves token prices. The golden-match precompute is budgeted at about $1.10 to $1.50 (DEMO sections 2 and 3). Batch latency for Opus is an estimate of 4 to 8 s (TECH_PLAN 1.8), not a measurement.

## Decision

`scripts/precompute.py --seed 4242 --mode batch` computes and stores, under `data/matches/4242/cache/`: analytics, pitch-control snapshots, Scout moments, every counterfactual, and every model output. Model calls go through `client.messages.batches.create(requests=[...])`, are polled until `ended`, and are joined by `custom_id`, never by position. The Batch API cannot run tool rounds, so the script calls the Tactician's five tools itself (counterfactual, pitch control, player stats, similar moments, events) and inlines the results in each prompt (`max_tool_rounds: 0`). The Fact Checker runs over every output; rejected outputs are re-queued with the diff (at most two rewrites). The twenty highest-leverage moments are hand-reviewed and written back as `hand_reviewed: true`.

`manifest.json` (`schemas/cache_manifest.schema.json`) records SHA-256 hashes, latencies, tokens and costs. Keys are `<match_id>/<moment_id>/<producer>@<version>/<model>/s<seed>`. `CacheClient` implements both `LLMClient` and `RolloutClient`. `CacheClient.complete(role, messages, tools)` looks up the key, sleeps `simulated_latency_ms x (1 / WHYLINE_REPLAY_SPEED)`, and returns the stored output. A miss raises `CacheMiss`; the Director turns it into a template line and a red "cache miss" trace row. The workflow graph, Director and screens are the same as in live mode. `demo/demo_script.yaml` fires the kill-switch (44:10) and the producer veto (45:00 + 15 s) on the replay clock.

After day 7, `manifest.frozen = true`. The CI job `frozen-cache-guard` fails if hashes change unless `docs/video/VERSION` is bumped in the same commit.

## Alternatives rejected

- Live recording with retries: a stalled, refused or slow call lands in the take, and no two takes are alike.
- Fall back to a live call on a cache miss: hides misses during rehearsal. The plan makes a miss visible instead.

## Consequences

- Positive: the take is repeatable and the trace panel animates with stored timings. Replay needs no API keys and runs offline.
- Positive: cost for the golden match is fixed and recorded before the video is cut.
- Negative: replay latencies are stored values (measured live latency of the same call, or the Batch estimate), not live timings. Anything shown as "live" must come from live mode (TECH_PLAN 1.8).
- Negative: any change to the engine, a prompt version or the schema major version after day 7 means a new cache and a new video.
- Negative: two client implementations (`CacheClient`, `LiveClient`) differ exactly where failures happen. The live path gets less rehearsal unless tested separately.
- Negative: the golden Tactician does not choose its own tools. `scripts/precompute.py` decides which results to inline, so the tool-use behaviour judges can see live is not what produced the cached explanations. The trace panel must not present the replayed run as a tool loop.

## Related

- TECH_PLAN 1.1 (replay data flow), 1.7 (prompt versioning, hand review), 1.8, 1.12, 1.13 ("cache miss during recording").
- ADR-001, ADR-004, ADR-011.
- Schemas: `schemas/cache_manifest.schema.json`, `schemas/cue.schema.json` (`provenance.cache_key`, `provenance.mode`).
- Audit: C.1, C.4, D.1.
