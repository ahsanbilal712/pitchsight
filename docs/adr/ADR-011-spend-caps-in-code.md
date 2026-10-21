# ADR-011: Spend caps in code

## Status

Accepted, 2026-10-21

## Context

- Total project spend is capped at $50 (`DEMO_MASTERPLAN_50USD.md`, header). The planned budget is about $23 to $25, leaving a $25 buffer (section 3): golden precompute $1.50, five more demo matches $4.50, live reserve for judges $15 (about ten live matches at $1.55), Gemini $0 to $2, images $1.40, music $0.24.
- The original plan was estimated at $800 to $1,300 (audit B.7). The cap is a hard change of scale, not a tuning exercise.
- Judges run live mode on a hosted URL, so anyone with the link can trigger paid model calls. The cost table is an estimate, not a control (DEMO section 2).
- `config/budgets.yaml` already sets: `per_match_cap` $2.50, `per_day_cap` $10.00, `project_total_cap` $50.00, `warn_at_fraction` 0.8, ledger path `data/spend/ledger.jsonl`, token prices per model, and `batch_discount` 0.5. The Haiku 5.5 cache-read price is an estimate until T-001.
- The audit's rule for claims is that each needs a proving artefact (C.6). A committed ledger is the artefact for "under $50".
- The risk register lists spend creep with the response "caps enforced in code; precompute via Batch only" (TECH_PLAN 1.13).

## Decision

Every model call goes through `SpendGuard` (`api/spend.py`), which wraps each `LLMClient` call. It prices tokens from `config/budgets.yaml` and appends `{ts, role, model, tokens_in, tokens_out, cost_usd, match_id, mode}` to `data/spend/ledger.jsonl`. It exposes `GET /spend` and raises `SpendCapReached` at the per-match, per-day or project-total cap. All three are enforced at runtime; the project total is read from the ledger at start-up. The Director catches this and switches the system to `mode=degraded`: Haiku and Sonnet calls are replaced by templates, the badge turns amber, and the ledger records the switch (TECH_PLAN 1.8). The WebSocket sends `mode` and `spend` messages to the studio.

Locally the ledger is `data/spend/ledger.jsonl`. In Azure it is the Cosmos `spend` collection (`ledger_azure: cosmos:spend` in `config/budgets.yaml`), which survives scale-to-zero, and `scripts/pull_ledger.py` mirrors it into the committed file. The CI job `spend-ledger` fails if the total exceeds $50 or any match exceeds $2.50. Precompute uses the Batch API only. Azure is counted at $0 in the ledger (ADR-009).

## Alternatives rejected

- Rely on the cost table in the DEMO plan: it is an estimate and proves nothing after the fact.
- A hard stop at the cap (refuse requests): the screens would go blank. Degraded mode keeps the demo running on verified templates.
- Manual monitoring: judges can run live mode at any hour.

## Consequences

- Positive: a public live endpoint cannot spend more than $2.50 per match or $10 per day by design. The committed ledger is evidence for judges (DEMO section 9).
- Positive: the degraded path is the same one used for Claude outages, so it gets exercised.
- Positive: because the project total is enforced at runtime and read at start-up, a run cannot exceed $50 even over two weeks of judging, when $10 per day alone could otherwise reach $140 (estimate, 14 x $10).
- Negative: the committed ledger is a mirror in Azure. Judge-run spend appears in the repo only after someone runs `scripts/pull_ledger.py` and commits the result, and the final $50 CI check is only as current as the last pull.
- Negative: prices in `config/budgets.yaml` are copied by hand. A price change is not noticed until someone edits the file.
- Negative: caps are checked per call, so a call already in flight can push a match slightly over the cap (inference).
- Negative: degraded mode changes what judges see. The amber badge is the disclosure.

## Related

- TECH_PLAN 1.3 (traces), 1.8 (live mode), 1.9 (`mode`, `spend` messages), 1.10 (spend guard, CI jobs), 1.13.
- ADR-003, ADR-004, ADR-009.
- Config: `config/budgets.yaml`. Schemas: `schemas/cue.schema.json` (`provenance.mode`). Files: `api/spend.py`, `data/spend/ledger.jsonl`.
- Audit: B.7, C.6.
