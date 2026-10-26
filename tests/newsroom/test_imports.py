"""The Agent Framework APIs the newsroom is built on import from the pinned packages.

Located in agent-framework-core 1.22.0: `Case` and `Default` are defined in
`agent_framework._workflows._edge` and re-exported as `agent_framework.Case` / `agent_framework.Default`.
"""

import warnings


def test_agent_framework_surface():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import agent_framework
        from agent_framework import (  # noqa: F401
            Case,
            Default,
            Executor,
            FileCheckpointStorage,
            MCPStreamableHTTPTool,
            WorkflowBuilder,
            WorkflowContext,
            handler,
            response_handler,
        )
        from agent_framework.anthropic import AnthropicClient  # noqa: F401
        from agent_framework.gemini import GeminiChatClient  # noqa: F401
        from agent_framework.orchestrations import GroupChatBuilder  # noqa: F401
    assert Case.__module__ == "agent_framework._workflows._edge"
    assert Default.__module__ == "agent_framework._workflows._edge"
    assert not hasattr(agent_framework, "RequestInfoExecutor")
