"""Read-only blackboard documents for the studio's Why? drawer and /replay3d (T-033).

    GET /match/{match_id}/doc/{collection}/{doc_id}
    GET /match/{match_id}/doc/{doc_id}            # collection from the id prefix (evidence ids in claims)

Whitelisted collections only; events of the replayed match come from its events.jsonl.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
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
        return request.app.state.bb.get(collection, doc_id, match_id=mid)
    except KeyError as exc:
        raise HTTPException(404, f"{collection}/{doc_id} not found for {mid}") from exc


@router.get("/match/{match_id}/doc/{doc_id}")
def get_doc_by_id(request: Request, match_id: str, doc_id: str) -> dict:
    collection = collection_of(doc_id)
    if collection is None:
        raise HTTPException(404, f"no collection for id {doc_id!r}")
    return get_doc(request, match_id, collection, doc_id)
