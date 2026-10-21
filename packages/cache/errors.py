"""Cache errors. `CacheMiss` is the newsroom's (an LLMError), so every executor's existing fallback handles it."""

from newsroom.llm import CacheMiss


class CacheFrozen(RuntimeError):
    """A frozen manifest cannot take new entries without a docs/video/VERSION bump (TECH_PLAN 1.8)."""


class CacheCorrupt(RuntimeError):
    """An entry's file is missing or its SHA-256 differs from the manifest."""


__all__ = ["CacheCorrupt", "CacheFrozen", "CacheMiss"]
