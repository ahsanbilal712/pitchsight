# ADR-005: Microsoft Agent Framework graph workflows with file checkpoints locally and Cosmos in Azure

## Status

Accepted, 2026-10-21

## Context

- The submission targets the Multi-Agent category (rules 4.2) and the pitch must name Microsoft technologies (rules 4.4; TECH_PLAN 1.12). The frozen scope names Agent Framework workflows for orchestration (`DEMO_MASTERPLAN_50USD.md` section 1).
- Verified in the audit: `agent-framework-core` 1.22.0 (15 Oct 2026; GA 1.0 on 3 Apr 2026) provides `WorkflowBuilder` with `add_edge`, `add_fan_out_edges`, `add_fan_in_edges` and `add_switch_case_edge_group`; `Executor`, `@handler`, `WorkflowContext`; `InMemoryCheckpointStorage`, `FileCheckpointStorage`; and MCP tools (audit A.1 row 35). Orchestrations (GroupChat and others) are in `agent-framework-orchestrations` 1.3.2 (row 37).
- `RequestInfoExecutor` does not exist in the Python framework. Human-in-the-loop is `await ctx.request_info(...)` plus `@response_handler`, resumed with `workflow.run(responses={...})` (row 36).
- `CosmosCheckpointStorage` is in `agent-framework-azure-cosmos` 1.0.0b261015, a beta. It stores pickles through a restricted unpickler, with partition key `/workflow_name` (row 38).
- The audit asks that failure recovery be demonstrable, not theatre, and notes that the file-backed store is the safer demo default (C.2). It also warns that a fixed DAG reads as a pipeline; the Tactician's tool use, the Director and the Panel are what make the graph agentic.
- The `agent-framework` metapackage with `[all]` stalled for more than 16 minutes on resolve; core plus named extras installed cleanly (audit A.2).

## Decision

The newsroom is one `WorkflowBuilder(start_executor=ingest, checkpoint_storage=storage, name="newsroom")` graph, run once per moment. Executors are `Executor` subclasses with `@handler` methods. Routing uses `add_switch_case_edge_group(scout, [Case(...), ..., Default(target=drop)])`. The rewrite loop is two conditional edges from the Fact Checker: back to the Narrator when `not verified and attempt < 3`, forward to the Director when `verified or attempt >= 3`. The Panel is a `GroupChatBuilder` sub-workflow inside `PanelExecutor`.

Producer approval uses `await ctx.request_info(request_data=ProducerApproval(cue=cue), response_type=ProducerDecision)` in `DirectorExecutor.handle_recap`, with an `@response_handler` named `on_decision`. The worker watches for events with `event.type == "request_info"`, forwards `{request_id, cue}` to the studio, and resumes with `workflow.run(stream=True, responses={...}, checkpoint_id=..., checkpoint_storage=storage)`.

Storage is `FileCheckpointStorage(WHYLINE_CHECKPOINT_DIR)` locally and for the recorded demo, which is the audit's recommended default. In the Azure deployment it is `CosmosCheckpointStorage(endpoint=..., credential=DefaultAzureCredential(), database_name=..., container_name=...)`, with `FileCheckpointStorage` on a mounted volume as its fallback. CI exercises the file store only. Executors that hold in-flight data implement `on_checkpoint_save` and `on_checkpoint_restore`. After a kill, the supervisor restarts the worker, which calls `storage.list_checkpoints(workflow_name="newsroom")` and resumes unfinished runs.

## Alternatives rejected

- `RequestInfoExecutor`: does not exist in Python 1.22.0.
- LangGraph: not a Microsoft technology, so it does not serve the pitch.
- A plain asyncio pipeline: no checkpoints and no human-in-the-loop primitive, and the audit warns it reads as a pipeline.
- `InMemoryCheckpointStorage` only: state is lost when the worker process is killed, so the kill-switch demo would not be a real resume.

## Consequences

- Positive: a resumable, inspectable graph. The kill-switch demo (44:10 of the golden match) is a real checkpoint resume, and the cue carries `provenance.resumed_from_checkpoint`. Human approval uses the framework's own primitive.
- Negative: `CosmosCheckpointStorage` is beta and CI never exercises it. The chaos test (`tests/chaos/test_resume.py`) runs on the file store, so the Azure resume path is untested in CI and relies on the file-store fallback if it misbehaves.
- Negative: the fallback needs a mounted volume on Container Apps, which `infra/` must provide alongside the Cosmos option. The recorded demo and the video never depend on Cosmos.
- Negative: a switch group selects one branch. A moment that needs two outputs needs two messages from the Scout (TECH_PLAN 1.7).
- Negative: checkpoints are written at superstep boundaries, so a call in flight at the kill is likely repeated on resume (inference). Executor state types must survive the restricted unpickler.
- Negative: core is GA but the Anthropic, Gemini and Cosmos packages are beta; pins matter.

## Related

- TECH_PLAN 1.1, 1.7 (workflow graph, producer veto, checkpoints and kill-switch), 1.8, 1.10, 1.13.
- ADR-004, ADR-006, ADR-009.
- Schemas: `schemas/cue.schema.json` (`producer_status`, `provenance.resumed_from_checkpoint`), `schemas/explanation.schema.json` (`attempt`).
- Audit: A.1 rows 35 to 39, A.2, C.2.
