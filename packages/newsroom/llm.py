"""LLMClient protocol and the live implementation (TECH_PLAN 1.7, 1.8; ADR-004 Revision 1).

`complete(role, messages, tools)` is the only way an executor reaches a model. Replay mode injects
`cache.CacheClient` (T-038) with the same signature; live mode injects `LiveClient`, which builds the
Agent Framework chat client for the role's provider (`agent_framework.gemini.GeminiChatClient` on Vertex AI,
or `agent_framework.anthropic.AnthropicClient` if a role is switched back) and records every call through
SpendGuard. Thinking tokens are billed as output.

A result is a dict: {text, json, model, role, tokens_in, tokens_out, cost_usd, latency_ms, cache_hit, cache_key}.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from newsroom.config import ROOT, Role, role

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class LLMError(RuntimeError):
    """The provider failed (after the client's own retries)."""


class LLMTimeout(LLMError):
    """The role's timeout elapsed."""


class CacheMiss(LLMError):
    """Replay mode: no cached output for this key (raised by cache.CacheClient)."""


class TemplateRole(LLMError):
    """The role has provider `none`; callers build a template instead."""


def parse_json(text: str) -> Any:
    """Parse model JSON output, tolerating a ```json fence."""
    return json.loads(_FENCE.sub("", text.strip()))


@runtime_checkable
class LLMClient(Protocol):
    async def complete(self, role: str, messages: list[dict], tools: list | None = None, **ctx) -> dict:
        """Run one model call for `role`. ctx: match_id, moment_id, schema (JSON schema dict), timeout_s."""
        ...


def _to_messages(messages: list[dict]):
    from agent_framework import Message

    return [Message(m["role"], [m["content"]]) for m in messages]


class LiveClient:
    """Real model calls through Agent Framework chat clients, every call through SpendGuard."""

    def __init__(self, guard=None, mode: str = "live", clients: dict[str, Any] | None = None) -> None:
        if guard is None:
            from api.spend import SpendGuard

            guard = SpendGuard()
        self.guard = guard
        self.mode = mode
        self._clients: dict[str, Any] = dict(clients or {})

    def _client(self, provider: str):
        if provider not in self._clients:
            if provider == "gemini":
                from agent_framework.gemini import GeminiChatClient
                from dotenv import load_dotenv
                from google import genai

                load_dotenv(ROOT / ".env")
                # same routing as scripts/smoke_models.py: Vertex AI with gcloud ADC, else the Developer API key
                if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true", "yes"):
                    sdk = genai.Client(vertexai=True, project=os.environ["GOOGLE_CLOUD_PROJECT"],
                                       location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"))
                else:
                    sdk = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
                self._sdk = sdk
                self._clients[provider] = GeminiChatClient(client=sdk)
            elif provider == "anthropic":
                from agent_framework.anthropic import AnthropicClient

                self._clients[provider] = AnthropicClient()
            else:
                raise TemplateRole(f"provider {provider!r} has no client")
        return self._clients[provider]

    def _tool_client(self, provider: str, rounds: int):
        """A chat client whose function-invocation loop stops after `rounds` tool rounds plus the final answer.
        The loop runs here, in the workflow process, calling our tool functions (Gemini's own automatic function
        calling stays off; models.yaml header)."""
        key = f"{provider}:tools{rounds}"
        if key not in self._clients:
            base = self._client(provider)
            if provider != "gemini" or not hasattr(self, "_sdk"):
                return base  # injected test clients run their own loop
            from agent_framework.gemini import GeminiChatClient

            self._clients[key] = GeminiChatClient(client=self._sdk,
                                                  function_invocation_configuration={"max_iterations": rounds + 1})
        return self._clients[key]

    async def warm(self, role_name: str = "narrator_fast") -> float:
        """One tiny call so credentials, TLS and the client are ready before the first moment (the cold first
        call measured 5.4 s against 1.3-1.8 s warm). Recorded in the ledger as role `warmup`. Returns seconds."""
        r = role(role_name)
        started = time.perf_counter()
        self.guard.check(None)
        resp = await self._client(r.provider).get_response(
            _to_messages([{"role": "user", "content": "Reply with: ok"}]),
            options={**self.options(r), "max_tokens": 5})
        usage = dict(resp.usage_details or {})
        self.guard.record("warmup", r.model, int(usage.get("input_token_count") or 0),
                          int(usage.get("output_token_count") or 0) + int(usage.get("reasoning_output_token_count")
                                                                         or 0), None, self.mode)
        return time.perf_counter() - started

    def options(self, r: Role, schema: dict | None = None, tools: list | None = None) -> dict:
        opts: dict[str, Any] = {"model": r.model}
        if r.max_tokens:
            opts["max_tokens"] = r.max_tokens
        if (level := r.thinking_level()) == "none":
            opts["thinking_config"] = {"thinking_budget": 0}
        elif level is not None:
            opts["thinking_config"] = {"thinking_level": level.upper()}
        if schema is not None:
            opts["response_schema"] = schema
        if tools:
            opts["tools"] = tools
        return opts

    async def complete(self, role_name: str, messages: list[dict], tools: list | None = None, **ctx) -> dict:
        r = role(role_name)
        if r.is_template:
            raise TemplateRole(role_name)
        match_id = ctx.get("match_id")
        self.guard.check(match_id)  # SpendCapReached propagates to the Director
        rounds = int(ctx.get("max_tool_rounds", r.max_tool_rounds))
        client = self._tool_client(r.provider, rounds) if tools else self._client(r.provider)
        started = time.perf_counter()
        try:
            resp = await asyncio.wait_for(
                client.get_response(_to_messages(messages), options=self.options(r, ctx.get("schema"), tools)),
                timeout=ctx.get("timeout_s") or r.timeout_s)
        except TimeoutError as exc:
            # the provider may still bill the abandoned call and returns no usage: record a worst case
            # (input ~ 4 characters per token, output = max_tokens) so the caps stay conservative
            est_in = sum(len(m["content"]) for m in messages) // 4
            calls = rounds + 1 if tools else 1
            self.guard.record(f"{role_name}:timeout", r.model, est_in * calls, (r.max_tokens or 0) * calls, match_id,
                              self.mode)
            raise LLMTimeout(f"{role_name} timed out after {ctx.get('timeout_s') or r.timeout_s}s") from exc
        except Exception as exc:  # provider errors become LLMError for the fallback chain
            raise LLMError(f"{role_name}: {type(exc).__name__}: {exc}") from exc
        latency_ms = int((time.perf_counter() - started) * 1000)
        usage = dict(resp.usage_details or {})
        cached = int(usage.get("cache_read_input_token_count") or 0)
        tokens_in = int(usage.get("input_token_count") or 0)
        tokens_out = int(usage.get("output_token_count") or 0) + int(usage.get("reasoning_output_token_count") or 0)
        row = self.guard.record(role_name, r.model, max(tokens_in - cached, 0), tokens_out, match_id, self.mode,
                                cache_read=cached)
        text = resp.text or ""
        try:
            parsed = parse_json(text) if (ctx.get("schema") or r.output_format) else None
        except (json.JSONDecodeError, ValueError):
            parsed = None
        return {"text": text, "json": parsed, "model": r.model, "role": role_name, "tokens_in": tokens_in,
                "tokens_out": tokens_out, "cost_usd": row["cost_usd"], "latency_ms": latency_ms,
                "cache_hit": False, "cache_key": None}


class FakeClient:
    """Scripted client for tests: `script[role]` is a list of results, exceptions or callables(messages)."""

    def __init__(self, script: dict[str, list] | None = None, model: str = "fake-model",
                 delay_s: float = 0.0) -> None:
        self.script = {k: list(v) for k, v in (script or {}).items()}
        self.model = model
        self.delay_s = delay_s
        self.calls: list[dict] = []

    async def complete(self, role: str, messages: list[dict], tools: list | None = None, **ctx) -> dict:
        self.calls.append({"role": role, "messages": messages, "tools": tools, **ctx})
        queue = self.script.get(role) or []
        item: Any = queue.pop(0) if queue else {"text": "{}", "json": {}}
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if isinstance(item, BaseException) or (isinstance(item, type) and issubclass(item, BaseException)):
            raise item
        if isinstance(item, Callable) and not isinstance(item, dict):
            item = item(messages)
            if asyncio.iscoroutine(item):
                item = await item
        out = {"text": json.dumps(item.get("json")) if "text" not in item else item["text"], "model": self.model,
               "role": role, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "latency_ms": 0,
               "cache_hit": False, "cache_key": None}
        out.update(item)
        return out


def load_fewshot(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
