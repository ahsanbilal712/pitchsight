"""Read-only blackboard documents for the studio's Why? drawer and /replay3d (T-033).

    GET /match/{match_id}/doc/{collection}/{doc_id}
    GET /match/{match_id}/doc/{doc_id}            # collection from the id prefix (evidence ids in claims)

Whitelisted collections only; events of the replayed match come from its events.jsonl. A pitch-control document
gets its [34, 53] grid inlined (rows = y bottom to top, 2 m cells, home share 0..1, two decimals) from the
`grid_path` .npz the MCP server writes, so the studio can draw the thumbnail.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
ROOT = Path(__file__).resolve().parents[2]
COLLECTIONS = ("counterfactuals", "explanations", "pitch_control", "moments", "facts", "events")
PREFIX = {"cf": "counterfactuals", "ex": "explanations", "pc": "pitch_control", "mo": "moments", "f": "facts",
          "e": "events"}


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
        raise HTTPException(404, f"{collection}/{doc_id} not found for {mid}") from exc
    if collection == "pitch_control" and "grid" not in doc and doc.get("grid_path"):
        path = Path(doc["grid_path"])
        path = path if path.is_absolute() else ROOT / path
        if path.exists():
            with np.load(path) as z:
                doc = {**doc, "grid": np.round(z["grid"].astype(np.float64), 2).tolist()}
    return doc


@router.get("/match/{match_id}/doc/{doc_id}")
def get_doc_by_id(request: Request, match_id: str, doc_id: str) -> dict:
    collection = collection_of(doc_id)
    if collection is None:
        raise HTTPException(404, f"no collection for id {doc_id!r}")
    return get_doc(request, match_id, collection, doc_id)
