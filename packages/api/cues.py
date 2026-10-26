"""Cue fan-out from the blackboard.

`Forwarder` watches the blackboard collections the newsroom writes (cues, moments, facts, oracle, traces, modes,
requests) and hands each new document to the hub:

- timed documents (cues, facts, moments, oracle) whose time the stream clock has already passed go out at once;
  later ones are released by the hub's ticker when the clock reaches them (so precomputed replay documents appear
  on time, and a seek replays the right ones);
- a cue rewritten as `producer_status: vetoed` becomes `cue_remove`;
- traces, modes and requests (request_info) go out at once; `modes` also sets the mode in every later hello.

`GET /match/{id}/cues?viewer=<mode>&club=&player=` lists the cues that viewer would receive.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import APIRouter, Query, Request

from api.messages import (
    NOW_COLLECTIONS,
    TIMED_COLLECTIONS,
    cue_matches,
    doc_time,
    mode_payload,
    request_payload,
)
from api.models import envelope, viewer_profile
from api.ws import Hub

log = logging.getLogger("whyline.cues")
router = APIRouter()


class Forwarder:
    def __init__(self, hub: Hub, bb) -> None:
        self.hub = hub
        self.bb = bb
        self.forwarded = 0

    def handle(self, collection: str, doc: dict) -> None:
        hub = self.hub
        if doc.get("match_id") not in (None, "", hub.match_id):
            return
        if collection == "cues" and doc.get("producer_status") == "vetoed":
            hub.send([envelope("cue_remove", {"cue_id": doc["cue_id"]})])
        elif collection in TIMED_COLLECTIONS:
            t = doc_time(doc)
            if t is not None and t > hub.released_until:
                return  # the ticker releases it when the stream clock gets there
            hub.send([envelope(TIMED_COLLECTIONS[collection], doc)])
        elif collection == "modes":
            hub.mode = doc.get("mode", hub.mode)
            hub.send([envelope("mode", mode_payload(doc))])
        elif collection == "requests":
            hub.send([envelope("request_info", request_payload(doc))])
        else:
            hub.send([envelope(NOW_COLLECTIONS[collection], doc)])
        self.forwarded += 1

    async def _watch(self, collection: str) -> None:
        async for doc in self.bb.watch(collection, from_start=False):
            try:
                self.handle(collection, doc)
            except Exception:
                log.exception("forwarding %s failed", collection)

    async def run(self) -> None:
        tasks = [asyncio.create_task(self._watch(c)) for c in (*TIMED_COLLECTIONS, *NOW_COLLECTIONS)]
        try:
            await asyncio.gather(*tasks)
        finally:
            for t in tasks:
                t.cancel()
            for t in tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await t


@router.get("/match/{match_id}/cues")
def list_cues(request: Request, match_id: str, viewer: str = Query("studio", description="viewer mode"),
              club: str | None = None, player: str | None = None) -> list[dict]:
    """Cues of a match that a viewer with this profile receives (vetoed cues excluded; studio gets all)."""
    mid = match_id if match_id.startswith("m_") else f"m_{match_id}"
    profile = viewer_profile("rest", viewer, club, player)
    cues = request.app.state.bb.query("cues", match_id=mid)
    return [c for c in cues if c.get("producer_status") != "vetoed" and cue_matches(profile, c)]


@router.get("/cues/negotiate")
def negotiate(match_id: str = Query(..., description="match whose cue group the screen joins"),
              viewer: str | None = None) -> dict:
    """Azure deployment: a short-lived Web PubSub URL for a screen on Static Web Apps. Locally the
    screens use the api's own WebSocket (`/ws`), and this answers `{"mode": "local"}`."""
    from cloud import cloud_enabled, settings

    if not (cloud_enabled() and settings().has_webpubsub):
        return {"mode": "local", "ws": "/ws"}
    from cloud.pubsub import WebPubSubCuePublisher

    mid = match_id if match_id.startswith("m_") else f"m_{match_id}"
    return {"mode": "webpubsub", "url": WebPubSubCuePublisher().client_url(user_id=viewer, match_id=mid)}
