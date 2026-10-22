"""Read-only blackboard documents for the studio's Why? drawer and /replay3d (T-033).

    GET /match/{match_id}/doc/{collection}/{doc_id}
    GET /match/{match_id}/doc/{doc_id}            # collection from the id prefix (evidence ids in claims)

Whitelisted collections only; events of the replayed match come from its events.jsonl. Counterfactuals and
pitch-control snapshots missing from the blackboard are read from the match's golden cache
(data/matches/<seed>/cache/{counterfactuals/cf_*.json, pitch_control/pc_*.npz}), so replay screens (the 3D scene,
the Why? drawer) work before or without a newsroom run. A pitch-control document
gets its [34, 53] grid inlined (rows = y bottom to top, 2 m cells, home share 0..1, two decimals) from the
`grid_path` .npz the MCP server writes, so the studio can draw the thumbnail.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

import numpy as np
from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
ROOT = Path(__file__).resolve().parents[2]
COLLECTIONS = ("counterfactuals", "explanations", "pitch_control", "moments", "facts", "events")
PREFIX = {"cf": "counterfactuals", "ex": "explanations", "pc": "pitch_control", "mo": "moments", "f": "facts",
          "e": "events"}


@functools.lru_cache(maxsize=256)
def cache_doc(match_id: str, collection: str, doc_id: str) -> dict | None:
    """A counterfactual or pitch-control document from the golden cache, or None."""
    from api.replay import match_dir

    cache = match_dir(match_id) / "cache"
    if collection == "counterfactuals":
        path = cache / "counterfactuals" / f"{doc_id}.json"
        return json.loads(path.read_text()) if path.exists() else None
    if collection == "pitch_control":
        path = cache / "pitch_control" / f"{doc_id}.npz"
        if not path.exists():
            return None
        with np.load(path) as z:
            stub = json.loads(str(z["stub"])) if "stub" in z.files else {"snapshot_id": doc_id}
            return {**stub, "grid": np.round(z["grid"].astype(np.float64), 2).tolist()}
    return None


def _grid_file(match_id: str, grid_path: str) -> Path | None:
    """grid_path is repo-relative (MCP server) or cache-relative (precompute)."""
    from api.replay import match_dir

    p = Path(grid_path)
    for candidate in (p, ROOT / p, match_dir(match_id) / "cache" / p):
        if candidate.is_absolute() and candidate.exists():
            return candidate
    return None


def collection_of(doc_id: str) -> str | None:
    return PREFIX.get(doc_id.split("_", 1)[0])


@router.get("/match/{match_id}/doc/{collection}/{doc_id}")
def get_doc(request: Request, match_id: str, collection: str, doc_id: str) -> dict:
    if collection not in COLLECTIONS:
        raise HTTPException(404, f"collection {collection!r} is not served (allowed: {', '.join(COLLECTIONS)})")
    mid = match_id if match_id.startswith("m_") else f"m_{match_id}"
    data = request.app.state.data
    if collection == "events" and mid == data.match_id:
        for e in data.events:
            if e["id"] == doc_id:
                return e
    try:
        doc = request.app.state.bb.get(collection, doc_id, match_id=mid)
    except KeyError as exc:
        doc = cache_doc(mid, collection, doc_id)
        if doc is None:
            raise HTTPException(404, f"{collection}/{doc_id} not found for {mid}") from exc
    if collection == "pitch_control" and "grid" not in doc and doc.get("grid_path"):
        path = _grid_file(mid, doc["grid_path"])
        if path is not None:
            with np.load(path) as z:
                doc = {**doc, "grid": np.round(z["grid"].astype(np.float64), 2).tolist()}
    return doc


@router.get("/match/{match_id}/doc/{doc_id}")
def get_doc_by_id(request: Request, match_id: str, doc_id: str) -> dict:
    collection = collection_of(doc_id)
    if collection is None:
        raise HTTPException(404, f"no collection for id {doc_id!r}")
    return get_doc(request, match_id, collection, doc_id)
