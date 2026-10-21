# ADR-009: Azure free account hosting

## Status

Accepted, 2026-10-21

## Context

- The frozen scope uses the Azure free account ($200 credit for 30 days) with always-free services (`DEMO_MASTERPLAN_50USD.md` sections 1 and 3). The pitch must name Microsoft technologies (TECH_PLAN 1.12). The project ledger counts Azure at $0.
- Verified service limits (audit A.1 rows 51 to 53): Container Apps consumption gives a free grant of 180k vCPU-s, 360k GiB-s and 2M requests per month, and scales to zero. Cosmos DB free tier is 1,000 RU/s plus 25 GB (not with serverless). Web PubSub free is 20 connections and 20k messages per day; Standard is $1.61 per unit per day. Event Hubs Basic is $0.015/h with no free tier. Static Web Apps has a free plan. `azd` is 1.36.0 (row 56).
- Serverless GPU on Container Apps is GA, but quota is default only for pay-as-you-go or EA subscriptions and may route to support. T4 is about $0.26/h and A100 about $1.90/h (row 51).
- Judges may test. The audit asks for a hosted demo kept alive through 10 Nov with scale-to-zero, plus a laptop replay mode (C.4).
- The subscription type (trial or pay-as-you-go) is still unknown (TECH_PLAN 1.14, question 5). The audit's original Azure line was $150 to $300 for the runtime, mostly from Web PubSub Standard (B.7).
- The live counterfactual in Azure runs `scripted_v1` at B=100 for 8 s with a target of 0.5 s on CPU (TECH_PLAN 1.5). The measured figure is 1.2 s for B=200 over 90 s. B=100 for 8 s is a target, not a measurement.

## Decision

`infra/` holds Bicep modules deployed with `azd` (`azure.yaml` declares `api`, `mcp`, `newsroom` as container apps and `overlay`, `studio`, `fan` as static web apps). Static Web Apps (Free) host the three front-ends. Container Apps in a consumption environment, scaled to zero, run `api`, `mcp` and `newsroom`. Cosmos DB NoSQL on the free tier holds the blackboard (`CosmosBlackboard`, partition key `/match_id`), the workflow checkpoints (`CosmosCheckpointStorage`, with a file store on a mounted volume as fallback, ADR-005) and the spend ledger (`spend` collection, ADR-011). Tracking frames (10 Hz) and the world-state stream are served over the `api` container's own WebSocket. Web PubSub on the free tier carries cues only, about 200 per match. Application Insights with Log Analytics, and Key Vault, round out the setup. Cosmos and Web PubSub are accessed by Entra managed identity.

Event Hubs Basic is deployed only during judging, from trial credit, and is optional: direct `POST /ingest/events` and `/ingest/tracking` is the default. No GPU workload profile is used. Azure live counterfactuals run on CPU with n=100.

## Alternatives rejected

- GPU workload profiles on Container Apps: quota needs a pay-as-you-go subscription and may route to support.
- Web PubSub Standard: $1.61 per unit per day for a cue stream that needs under 20 clients.
- Tracking frames over Web PubSub: 54,000 messages per client per match (estimate, 90 x 60 x 10), which would exceed the 20k per day free cap.
- Event Hubs always on: about $11 per month with no free tier.
- Foundry-hosted models for the agents: see ADR-004.

## Consequences

- Positive: idle cost is about $0. The estimate for two weeks of judging is $0 to $5 (TECH_PLAN 1.10, estimate). One `azd up` deploys everything.
- Negative: the $200 credit lasts 30 days, which sets the end of the Event Hubs option. Beyond that the demo relies on always-free tiers and scale-to-zero.
- Positive: with tracking on the `api` WebSocket and only cues on Web PubSub (about 200 per match), the 20k-per-day message cap is never approached. The 20-connection cap still applies to cue delivery, with an SSE fallback from `api` (TECH_PLAN 1.13).
- Negative: Cosmos free tier is 1,000 RU/s for the whole account, shared by the blackboard, the checkpoints and the spend ledger.
- Negative: the `api` container serves the 10 Hz tracking stream to every judge client itself, so its scale-to-zero cold start and CPU share are on the viewing path (not measured).
- Negative: `CosmosCheckpointStorage` is beta (ADR-005). The Application Insights and Key Vault allowances in TECH_PLAN 1.10 are small but were not verified in the audit (estimate); confirm them in T-001.
- Negative: no GPU means live Azure mode cannot use `policy_v1` at B=200. It uses `scripted_v1` (ADR-001, ADR-002).

## Related

- TECH_PLAN 1.1, 1.5, 1.10 (Azure table, Bicep modules, secrets), 1.12, 1.13 ("Web PubSub 20-connection cap"), 1.14.
- ADR-004, ADR-005, ADR-011.
- Config: `config/budgets.yaml`. Files: `infra/main.bicep`, `infra/modules/*.bicep`, `azure.yaml`.
- Audit: A.1 rows 51 to 56, B.7, C.4.
