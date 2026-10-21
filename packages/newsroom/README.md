# newsroom

Agent Framework workflow graph and executors.

Interface restated from `TECH_PLAN.md` section 1.4 "newsroom" (TECH_PLAN wins on conflict).
Tests live in `tests/newsroom/`.

Agent Framework `agent-framework-core==1.22.0`, `agent-framework-orchestrations==1.3.2`, `agent-framework-anthropic==1.0.0b261015` (`from agent_framework.anthropic import AnthropicClient`), `agent-framework-gemini==1.0.0b261015` (`from agent_framework.gemini import GeminiChatClient`). Executors are plain `Executor` subclasses with `@handler` methods; LLM-backed executors hold an `Agent` built on the client for their role from `config/models.yaml`. See 1.7.

## As built (T-018)

- `messages.py`: pydantic messages carrying the run envelope (`run_id`, `mode`, `branch`, `moment`, `agent_path`,
  `trace_id`); all registered with `register_checkpoint_type` so `FileCheckpointStorage` can restore them.
- `graph.py`: `build_workflow(deps, storage, overrides)` wires the 1.7 graph with the verbatim builder calls;
  executor ids are fixed (`EXECUTOR_IDS`). Branches not yet built are stubs in `executors/stubs.py`; each ticket
  registers its real executor in `_real_executors()`.
- `llm.py`: `LLMClient.complete(role, messages, tools, **ctx)`; `LiveClient` (Gemini on Vertex AI through
  `agent_framework.gemini.GeminiChatClient`, SpendGuard on every call, thinking tokens counted as output);
  `FakeClient` for tests.
- `worker.py`: `python -m newsroom.worker` watches blackboard `moments` (status `new`) and runs one workflow per
  moment; run ids are deterministic (`run_<match>_<moment>`), checkpoints in `WHYLINE_CHECKPOINT_DIR`.
