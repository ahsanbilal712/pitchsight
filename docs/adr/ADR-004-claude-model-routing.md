# ADR-004: Claude model routing with Gemini as fallback and video tagger

## Status

Accepted, 2026-10-21

## Context

- The frozen scope uses Claude through the API and a Gemini key the team already has (`DEMO_MASTERPLAN_50USD.md` section 1). Claude Code is a development tool, not a runtime. Anthropic's Agent SDK documentation does not allow third-party products to offer claude.ai login or rate limits, so a judge-testable product needs an API key (DEMO section 4).
- Claude on Foundry needs a paid pay-as-you-go subscription. Free-trial, student and credit-only subscriptions get 0 quota (audit A.1 row 49). Tier 0 subscriptions have no GPT-6 quota (row 48). Gemini is not hosted in Foundry (row 50). The team's Azure subscription type is still an open question (TECH_PLAN 1.14).
- Gemini 4 Argon has no free tier and costs $2/$10 per 1M tokens until 30 Nov, then $4/$20 (row 30). Gemini 3.8 Flash has a free tier whose limits are unpublished; paid price is $0.75/$3.75 until 31 Dec, then it doubles (row 31).
- Prices per 1M tokens (DEMO section 2): Opus 5.5 $4 in / $20 out; Sonnet 5.5 $2 / $10; Haiku 5.5 $0.10 / $0.50; cache reads $0.20 on Opus and Sonnet; Batch halves everything. At the table's token counts a live match costs about $1.55 and the golden match via Batch about $1.10.
- Latency targets are 3 s p95 for a fast cue and 15 s p95 for an explained cue (`config/budgets.yaml`). The Tactician's tool rounds are the budget killer (audit C.1).

## Decision

`config/models.yaml` maps roles to models. Opus 5.5 serves `tactician_golden` (effort high, Batch) and `recap` (Batch). The Batch API cannot run tool rounds, so `scripts/precompute.py` pre-resolves the Tactician's tool results and inlines them in the prompt (`max_tool_rounds: 0`). The live Tactician (`tactician_live`, Sonnet 5.5) uses the MCP tools with `max_tool_rounds: 2`. Sonnet 5.5 serves `tactician_live` (effort medium, 12 s timeout), `proposer`, `panel_pundit`, `panel_chair`, `recap_live`, `judge` and `cluster_namer`. Haiku 5.5 serves `narrator_fast`. Gemini 3.8 Flash is the optional `video_tagger` and the narrator's `gemini_fallback`. Roles with `provider: none` are templates.

Claude is reached through `agent-framework-anthropic` (`from agent_framework.anthropic import AnthropicClient`) inside the workflow, and through the `anthropic` SDK for the Batch API and structured output. Gemini uses `agent-framework-gemini` (`GeminiChatClient`) and `google-genai`. Provider defaults: adaptive thinking, `cache_control: ephemeral` on the frozen system prompt and league block, and the beta `server-side-fallback-2026-07-01` with `fallbacks: default` on every Opus and Sonnet call. Azure workloads call the Anthropic API directly with the key from Key Vault, not through Foundry.

## Alternatives rejected

- Foundry-hosted Claude: needs a paid pay-as-you-go subscription; trial gets 0 quota.
- Foundry-hosted GPT-6 (the audit's option in E.3): Tier 0 subscriptions have no GPT-6 quota.
- Gemini 4 Argon: no free tier and not needed.
- Opus on the live path: doubles the Tactician cost ($1.28 versus $0.64 per match in the DEMO table). Opus is kept for the golden match.
- Running the product on a claude.ai login or Claude Code session: not permitted for third-party products.

## Consequences

- Positive: a match costs cents. The strongest model is used where the camera points. A refusal or outage is covered by the server-side fallback, the template path and the degraded badge.
- Negative: `agent-framework-anthropic` and `agent-framework-gemini` are beta (`1.0.0b261015` in `config/pins.txt`). The client API can change; pins are fixed in T-001.
- Negative: two providers mean two failure modes. Gemini free-tier limits are visible only in AI Studio; the risk register watches for 429s (trigger 23 Oct).
- Negative: model constraints in `config/models.yaml`: thinking cannot be disabled (use effort); forced `tool_choice` "any" or "tool" returns 400 (use auto, strict tools and a prompt instruction); no prefill; no sampling parameters on Opus 5.5. Opus 5.5 defaults to medium effort, so effort must be set explicitly.
- Negative: the Haiku 5.5 cache-read price in `config/budgets.yaml` is an estimate until T-001.
- Negative: Foundry Evaluations cannot be assumed on a free account, so groundedness uses the project's own evaluator (TECH_PLAN 1.14 item 1).

## Related

- TECH_PLAN 1.7 (agents table, prompt versioning), 1.8 (live mode), 1.10 (secrets), 1.13, 1.14.
- ADR-003, ADR-005, ADR-011.
- Config: `config/models.yaml`, `config/budgets.yaml`, `config/pins.txt`. Schemas: `schemas/explanation.schema.json` (`model`, `prompt_version`).
- Audit: A.1 rows 30, 31, 39, 48 to 50; C.1.

## Revision 1 (2026-10-21): Gemini replaces Claude at runtime

Status: Accepted, 2026-10-21, owner decision. Supersedes the Decision section above where they conflict.

- Every runtime role moves to Gemini on Vertex AI (project ffc-19484, gcloud application-default credentials):
  `gemini-4-argon` (Google's top tier) for `tactician_golden`, `tactician_live`, `panel_pundit`, `recap`,
  `recap_live` and `judge`; `gemini-3.8-flash` for `narrator_fast`, `proposer`, `panel_chair`, `cluster_namer`
  and `video_tagger`. Template roles are unchanged. Both models answered a smoke call on 21 Oct 2026
  (`scripts/smoke_models.py`, ledger cost $0.000135).
- Why: one provider and one bill; no Anthropic API account or credit needed. Argon's list price ($2 / $10 per 1M
  until 30 Nov 2026) is half of Opus 5.5 and equal to Sonnet 5.5, so the $50 plan still holds; after 30 Nov the
  price doubles, which is after judging closes on 10 Nov.
- Batch: the golden precompute (T-042) uses Vertex AI batch prediction (0.5x) instead of the Anthropic Message
  Batches API. Results are still matched by `custom_id`-style keys, never by position.
- Claude-specific rules in this ADR (effort, no prefill, no forced `tool_choice`, server-side fallback beta,
  `cache_control`) no longer apply. Gemini equivalents: `thinking_level` for effort, `response_json_schema` for
  structured output, explicit context caching for the frozen league block, and the template fallback when a call
  fails or times out. Thinking tokens are billed as output and must be counted in `tokens_out`.
- Claude stays possible: the `anthropic` provider block remains in `config/models.yaml`, and the smoke test calls
  Claude only when `ANTHROPIC_API_KEY` is set.
- New risk: Argon has no free tier and Flash free-tier limits are unpublished; on Vertex both are paid per token,
  so 429s come from project quota, not a free tier. Check quota before the day-6 recording.
