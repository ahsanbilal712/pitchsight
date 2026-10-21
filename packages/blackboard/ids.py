"""Blackboard document IDs (TECH_PLAN 1.3): zero-padded, monotonic per match, identical across runs of a seed.

    f_000001  facts            mo_00077  moments          pc_000412  pitch_control
    cf_000077 counterfactuals  ex_000077 explanations     c_000912   cues
    tr_000001 traces

Events keep the engine's own `id` (`e_0001`) and are never allocated here.
"""

from __future__ import annotations

import re
import threading
from collections import defaultdict

PREFIXES: dict[str, tuple[str, int]] = {
    "facts": ("f", 6),
    "moments": ("mo", 5),
    "pitch_control": ("pc", 6),
    "counterfactuals": ("cf", 6),
    "explanations": ("ex", 6),
    "cues": ("c", 6),
    "traces": ("tr", 6),
}

# The document field that holds each collection's key.
ID_FIELDS: dict[str, str] = {
    "facts": "fact_id",
    "moments": "moment_id",
    "pitch_control": "snapshot_id",
    "counterfactuals": "counterfactual_id",
    "explanations": "explanation_id",
    "cues": "cue_id",
    "traces": "trace_row_id",
    "events": "id",
    "viewer_profiles": "viewer_id",
    "manifests": "match_id",
}

_ID_RE = re.compile(r"^([a-z]+)_([0-9]+)$")


def id_field(collection: str) -> str:
    return ID_FIELDS.get(collection, "id")


def format_id(collection: str, n: int) -> str:
    prefix, width = PREFIXES[collection]
    if n < 1 or n >= 10**width:
        raise ValueError(f"{collection} id number {n} outside 1..{10**width - 1}")
    return f"{prefix}_{n:0{width}d}"


def parse_id(doc_id: str) -> tuple[str, int]:
    m = _ID_RE.match(doc_id)
    if not m:
        raise ValueError(f"not a blackboard id: {doc_id!r}")
    return m.group(1), int(m.group(2))


def collection_of(doc_id: str) -> str:
    """Collection an id belongs to by prefix (`e_` is events)."""
    prefix, _ = parse_id(doc_id)
    if prefix == "e":
        return "events"
    for coll, (p, _) in PREFIXES.items():
        if p == prefix:
            return coll
    raise ValueError(f"unknown id prefix in {doc_id!r}")


class IdAllocator:
    """In-memory allocator; SqliteBlackboard keeps the same counters in its own table across processes."""

    def __init__(self) -> None:
        self._n: dict[tuple[str, str], int] = defaultdict(int)
        self._lock = threading.Lock()

    def next_id(self, collection: str, match_id: str) -> str:
        with self._lock:
            self._n[(collection, match_id)] += 1
            return format_id(collection, self._n[(collection, match_id)])

    def observe(self, collection: str, match_id: str, doc_id: str) -> None:
        """Keep the counter above an id that was written explicitly."""
        _, n = parse_id(doc_id)
        with self._lock:
            self._n[(collection, match_id)] = max(self._n[(collection, match_id)], n)


_default = IdAllocator()


def next_id(collection: str, match_id: str) -> str:
    return _default.next_id(collection, match_id)
