# newsroom

Agent Framework workflow graph and executors.

Tests live in `tests/newsroom/`.

Agent Framework `agent-framework-core==1.22.0`, `agent-framework-orchestrations==1.3.2`, `agent-framework-anthropic==1.0.0b261015` (`from agent_framework.anthropic import AnthropicClient`), `agent-framework-gemini==1.0.0b261015` (`from agent_framework.gemini import GeminiChatClient`). Executors are plain `Executor` subclasses with `@handler` methods; LLM-backed executors hold an `Agent` built on the client for their role from `config/models.yaml`. See 1.7.

## As built

- `messages.py`: pydantic messages carrying the run envelope (`run_id`, `mode`, `branch`, `moment`, `agent_path`,
  `trace_id`); all registered with `register_checkpoint_type` so `FileCheckpointStorage` can restore them.
- `graph.py`: `build_workflow(deps, storage, overrides)` wires the newsroom graph;
  executor ids are fixed (`EXECUTOR_IDS`); `executors/stubs.py` holds test doubles with the same ids and types.
- `llm.py`: `LLMClient.complete(role, messages, tools, **ctx)`; `LiveClient` (Gemini on Vertex AI through
  `agent_framework.gemini.GeminiChatClient`, SpendGuard on every call, thinking tokens counted as output);
  `FakeClient` for tests.
- `worker.py`: `python -m newsroom.worker` watches blackboard `moments` (status `new`) and runs one workflow per
  moment; run ids are deterministic (`run_<match>_<moment>`), checkpoints in `WHYLINE_CHECKPOINT_DIR`.
