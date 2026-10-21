"""The Blackboard protocol (TECH_PLAN 1.4): the shared store of facts, moments, cues and traces."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable


class NotFound(KeyError):
    """No document with that id in the collection."""


@runtime_checkable
class Blackboard(Protocol):
    def put(self, collection: str, doc: dict) -> str:
        """Insert or replace `doc`; allocates the id when the doc has none. Returns the id."""
        ...

    def get(self, collection: str, id: str, match_id: str | None = None) -> dict:
        """The document, or raise NotFound."""
        ...

    def query(self, collection: str, **filters) -> list[dict]:
        """Documents in insertion order. Filters are equality on top-level fields (list value = any of);
        `t_from_ms` / `t_to_ms` bound the document time inclusively."""
        ...

    def watch(self, collection: str, match_id: str | None = None, from_start: bool = True) -> AsyncIterator[dict]:
        """Yield documents in insertion order as they are written, also by other processes."""
        ...
