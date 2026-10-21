# newsroom

Agent Framework workflow graph and executors.

Interface restated from `TECH_PLAN.md` section 1.4 "newsroom" (TECH_PLAN wins on conflict).
Tests live in `tests/newsroom/`.

Agent Framework `agent-framework-core==1.22.0`, `agent-framework-orchestrations==1.3.2`, `agent-framework-anthropic==1.0.0b261015` (`from agent_framework.anthropic import AnthropicClient`), `agent-framework-gemini==1.0.0b261015` (`from agent_framework.gemini import GeminiChatClient`). Executors are plain `Executor` subclasses with `@handler` methods; LLM-backed executors hold an `Agent` built on the client for their role from `config/models.yaml`. See 1.7.
