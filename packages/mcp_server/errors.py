"""Structured tool errors (TECH_PLAN 1.4 mcp_server): every tool returns {error, code} and never raises into the agent."""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import Any

log = logging.getLogger("whyline.mcp")


class ToolError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def error(code: str, message: str) -> dict:
    return {"error": message, "code": code}


def guarded(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Turn any exception into {error, code}; list-returning tools get [{error, code}] so their type holds."""
    returns_list = str(fn.__annotations__.get("return", "")).startswith("list")

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ToolError as exc:
            out = error(exc.code, str(exc))
        except Exception as exc:  # never raise into the agent
            log.exception("tool %s failed", fn.__name__)
            out = error("internal", f"{type(exc).__name__}: {exc}")
        return [out] if returns_list else out

    return wrapper
