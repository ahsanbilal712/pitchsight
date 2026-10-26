# Prompt: Complete Technical Plan for WHYLINE, Ready to Execute

Paste everything below the line into the forked Claude Code session.

---

You are the technical lead and delivery manager for WHYLINE. The idea has been researched, audited and scoped. Your job now is to turn it into a **complete, executable engineering plan**: every architecture decision made, every interface specified, every task written as a ticket with acceptance criteria, in an order that a small team (or Claude Code itself, one ticket at a time) can execute without stopping to ask what to do next. You are NOT building the product in this session. You are producing the plan that makes building it mechanical.

## Read first, in this order, completely

1. `DEMO_MASTERPLAN_50USD.md` — **the frozen decisions.** Core features, model routing, $50 budget ledger, no voice, English only, replay-from-cache demo mechanism, the 14-day build sequence, the acceptance checklist. Nothing in your plan may contradict this file. If you believe something in it is wrong, flag it in a "disagreements" section and plan around the frozen decision anyway.
2. `FEASIBILITY_AUDIT.md` — the adversarial audit. It contains verified facts, corrections to earlier documents, measured timings, licences, and the minimum viable version. Every correction in its Part E list must be reflected in your plan (for example: `RequestInfoExecutor` does not exist in the Python Agent Framework, use `ctx.request_info()` and `@response_handler`; learned rollouts are decision-only and capped at 6–8 seconds; ffmpeg cannot author HLS ID3 metadata; `sv.ByteTrack` was removed from supervision 0.31, use `trackers.ByteTrackTracker`; gfootball is not installed on this Mac and is not a dependency of the demo).
3. `ZERO_COST_ML.md` — the laptop-first ML path: the pre-recorded GRF tracking dataset (`Dtradke/grf_tracking_data`), the measured Mac GPU throughput, the decision-only policy design.
4. `ML_CORE.md` — the ML design as originally intended. Use it for intent; the audit and the $50 plan override its numbers and horizons.
5. `THE_IDEA.md` — the plain-language product description, so the plan serves the product and not the other way round.
6. `WHYLINE_PROPOSAL.md` — the original architecture, directory layout, cue schema, agent roster and Microsoft stack mapping. Reuse what still stands; correct what the audit corrected.
7. `/Users/ahsanbilal/Downloads/OFFICIAL RULES.md` — submission requirements and compliance constraints.

Context: Microsoft × Premier League "Inside the Game: Developer Hackathon." Today is 21 October 2026. The official rules say submissions close 27 October; the website banner says the event runs to 21 November. Plan so that **day 7 produces a complete, submittable build** and days 8–14 make it flawless, exactly as the $50 plan sequences it; anything beyond day 14 is optional polish. Team: assume 3 people (A: engine and ML, B: agents and cloud, C: screens and video), but write every ticket so that Claude Code could execute it alone. Hardware: this Mac (Apple Silicon, 18 GB, no discrete GPU, Metal GPU available to PyTorch), an Azure free account, a Claude API key and a Gemini API key (never written into project files; always read from environment variables).

## What to produce

Write these files into the project folder. Do not write product code, except the schemas and configuration files listed below, which are planning artefacts.

### 1. `TECH_PLAN.md` — the engineering blueprint

A document an engineer can build from without reading anything else. Sections:

**1.1 System overview.** One diagram (ASCII or mermaid) of every runtime component and the data flowing between them, in both modes: *replay-from-cache* (the demo) and *live* (for judges). Name every process, port, queue, store and file.

**1.2 Architecture decision records.** One short ADR per decision, each with context, decision, alternatives rejected, consequences. At minimum: scripted Kickoff engine as the live world; decision-only learned policy with 6–8 s horizon and hand-off to the goal-in-horizon head; replay-from-cache as the demo mechanism; Claude model routing (Opus golden / Sonnet live / Haiku volume) with Gemini 3.8 Flash as fallback and video tagger; Microsoft Agent Framework graph workflows with file checkpoints locally and Cosmos checkpoints in Azure; MCP server as the only data path for agents; Cue Sheet as the product boundary; 2.5D canvas for live overlays and one stylised 3D scene for Sliding Doors replays; Azure free-tier hosting; English-only, no voice; spend caps in code.

**1.3 Data contracts.** Full JSON Schemas (also written as files under `schemas/`): `event.schema.json` (the StatsBomb-like event with every field, type, enum and example), `tracking` frame format (document the `.npz` layout and a JSON equivalent), `fact` (blackboard document), `moment`, `explanation` (structured claims bound to evidence IDs), `counterfactual_result`, `cue.schema.json` (the Cue Sheet, with layers, timing, targets, evidence, verification and producer status), `viewer_profile`, `cache manifest` (how precomputed outputs are keyed by match seed, moment ID, model, prompt version and seed). Every schema has a worked example. State the versioning rule for schemas.

**1.4 Module specifications.** For each package in the repo (engine, physics, outcome heads, policy, sliding doors / oracle / dugout rollout primitive, blackboard, MCP server, newsroom agents and workflow, fact checker, director, cache/replay layer, API and streaming, overlay app, studio console, fan app, 3D replay scene, Fourth Official rules engine, evaluation harness, demo recorder, spend guard): purpose, public interface (function and class signatures with types), inputs and outputs by schema, performance budget, failure behaviour, tests required, and the exact third-party libraries with pinned versions and licences (from the audit's verified list). Where the audit named an API precisely (Agent Framework class names, `ctx.request_info()`, `WorkflowBuilder` edges, `FileCheckpointStorage`, `CosmosCheckpointStorage`, `agent-framework-anthropic`), use those names and cite the audit.

**1.5 The rollout primitive.** Specify `rollout(state, overrides, B, horizon_s, seed)` precisely: state tensor layout, how an alternative first action is forced, when the learned policy is called versus the scripted decision rule, how physics advances between decisions, how the horizon hands off to the goal-in-horizon head, what is returned, determinism guarantees, and the measured budgets to hit (from the audit: 200 × 8 s decision-only ≈ 0.3 s on the Mac GPU; 200 × 90 s scripted ≈ 1.2 s on CPU). Specify the three callers (Sliding Doors, Oracle, Dugout) as thin wrappers.

**1.6 ML specification.** For the on-ball decision policy: data pipeline from `grf_tracking_data` and Kickoff matches to training tensors (field mapping, normalisation, action labelling, train/val/test split by match), model architecture with parameter count, loss, training schedule for one night on the Mac GPU (batch size, epochs, measured samples/s), checkpointing, evaluation metrics with pass/fail thresholds (top-3 action accuracy vs velocity baseline, 4 s FDE, shape-collapse and teleport counters on 20 rollouts), and the fallback decision (scripted rule stays in the video if the policy fails the thresholds by day 4). For each outcome head (xG with defender geometry, pass completion, win probability, goal-in-8-s) and the moment-embedding/chaos head: features, model, data size, training time, calibration check. State the licence and attribution text for every dataset.

**1.7 Agent and workflow specification.** The exact workflow graph (nodes, edges, conditions, fan-out/fan-in, the rewrite loop with its cap), each agent's role, model, system-prompt location and version, tool list, structured output schema, timeout, retry, and fallback. The Fact Checker's deterministic rule set written out. The Director's budget table per viewer mode. The human-in-the-loop producer veto using the correct Agent Framework API. The checkpoint and resume design and the exact kill-switch demo procedure with what the log must show. The MCP server's tool list with signatures. The prompt-versioning and few-shot-example mechanism (Claude Code hand-reviews the top twenty moments; those become few-shots).

**1.8 Replay-from-cache and live mode.** How the golden match (seed 4242) is generated, frozen and hashed; what is precomputed (analytics, counterfactuals, every model output via the Batch API) and how it is keyed; how the demo app serves cache hits with simulated latencies so the trace panel animates; the demo-script file that fires the kill-switch and veto at fixed clock times; how live mode uses identical code paths with real calls, spend caps and a degraded badge. The rule that nothing after day 7 may touch the golden cache without regenerating the video.

**1.9 Screens.** For the overlay, studio console, fan app and 3D replay scene: component tree, state model, the WebSocket/SSE message types consumed, the exact visual elements (score bug, chaos meter, heatmap, ghost trail, swing bar, lower-third, evidence drawer, agent trace, veto, kill switch, Player-Cam tags, Fourth Official lines), viewer-mode differences, 1080p recording requirements, and the Playwright recording script's responsibilities.

**1.10 Infrastructure and operations.** Local `docker compose` topology; Azure topology on the free account (which always-free services, which trial-credit services, estimated monthly cost at idle and during judging); Bicep module list; `azd` configuration; secrets handling (environment variables, Key Vault in Azure, never in the repo); CI pipeline stages (lint, unit, schema validation, golden-match replay determinism, evaluation gates, licence scan, spend-ledger check); observability (OpenTelemetry to App Insights, what spans and attributes); the spend guard design (per-match and daily caps, ledger file committed to the repo).

**1.11 Evaluation harness.** Every number the README will publish, the script that produces it, the data it runs on, and the pass threshold: state-detection F1 vs hidden truth, counterfactual Brier score, policy metrics, Fact Checker planted-error catch rate and false-reject rate, cue latency p50/p95 in live mode, cost per match from the ledger, groundedness via Foundry Evaluations if accessible on the free account. Include the planted-error test design.

**1.12 Rules compliance checklist.** Each rule from the official rules mapped to the artefact that proves compliance (fictional league file, licence scan output, public repo, video length, judge instructions, "new project after 29 Sep 2026" evidenced by first commit date).

**1.13 Risk register.** Every risk from the audit and the $50 plan that still applies, with owner, early-warning signal, trigger date, and the pre-decided response.

**1.14 Disagreements and open questions.** Anything in the frozen plan you would change, and the open questions only the user can answer (the real deadline, team size, whether the Gemini free tier suffices, whether the rendering-partner spec is available).

### 2. `TASKS.md` — the executable backlog

Every ticket needed to deliver days 1–14 of the $50 plan, and nothing else. For each ticket:

- ID (`T-001`…), title, owner (A/B/C), day, estimated hours.
- Depends on (ticket IDs). The graph must have no cycles and must let the three owners work in parallel from day 1.
- Files to create or change (paths).
- Precise scope: what is in, what is explicitly out.
- Acceptance criteria as checkable statements (commands that must pass, outputs that must exist, numbers that must be met).
- Test or verification step.
- A self-contained **brief** of 5–15 lines that could be pasted into a fresh Claude Code session to execute that ticket alone, naming the schema files, interfaces and documents it must read first.

Group tickets by day with a one-line "end of day" definition of done, and mark the day-7 submittable build and the day-14 flawless build as milestones with their own acceptance lists (copy the $50 plan's acceptance checklist and make each item a ticket or a check). Mark cut lines: which tickets are dropped first if a day slips.

### 3. `schemas/` — the data contracts as files

`event.schema.json`, `cue.schema.json`, `explanation.schema.json`, `counterfactual.schema.json`, `viewer_profile.schema.json`, `cache_manifest.schema.json`, each JSON Schema draft 2020-12, each with an `examples` array containing at least one full example from the Okafor/Reyes moment at 31:14.

### 4. `docs/adr/` — one file per ADR from section 1.2.

### 5. `config/` — planning-grade configuration

`models.yaml` (role → model ID, max tokens, effort, temperature, cache settings, fallback), `budgets.yaml` (Director budgets per mode, spend caps per match and per day, token ceilings), `pins.txt` (every Python and npm dependency with the exact version and licence from the audit), `.env.example` (variable names only, no values).

## Standards for the plan

- **No contradictions with the frozen plan.** The $50 plan's decisions, budget, scope cuts (no voice, English only) and 14-day sequence are fixed. Plan inside them.
- **Every number traceable.** Performance budgets, costs and timings come from the audit's measured values or primary sources already cited there; mark anything you estimate as an estimate.
- **Every API name correct.** Use the audit's verified names for Agent Framework, Foundry, Azure SDKs, supervision/trackers, RF-DETR, the Claude and Gemini SDKs. If you need an API the audit did not verify, check the primary documentation and record the URL in the plan.
- **Every ticket executable in isolation.** A reader with only the ticket brief, the schemas and the named documents can do the work.
- **Determinism first.** The golden match must replay identically; seeds, hashes and cache keys are specified, not implied.
- **Nothing speculative in days 1–7.** The learned policy, the 3D scene and the Pitchwatch adapter are scheduled where the $50 plan puts them, with scripted fallbacks already wired on day 2 so the video never depends on them.
- **Plain language.** Short sentences, tables for data, define any term a non-specialist would not know.

## Deliverable

Write `TECH_PLAN.md`, `TASKS.md`, the `schemas/`, `docs/adr/` and `config/` files. Then give me a short summary in chat: how many tickets, the critical path for day 7, the three tickets to start right now, and any disagreement with the frozen plan.
