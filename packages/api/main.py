"""whyline-api (TECH_PLAN 1.1, 1.4 api): REST, the WebSocket stream and the replay controller.

Run: `PYTHONPATH=packages uvicorn api.main:app --port 8000`, or `python -m api.replay --seed 4242`.
WHYLINE_MATCH_SEED picks the match under data/matches/, WHYLINE_REPLAY_SPEED the starting speed (x1..x10),
WHYLINE_BLACKBOARD the blackboard file the newsroom writes cues into, WHYLINE_REPLAY_FEED=1 the replay feed
(cached analytics, oracle and moments on the clock; api/replay_feed.py).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import AsyncIterator, Callable

from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from api import control, cues, demo_runner, docs, ingest, players
from api.models import envelope, viewer_profile
from api.replay import MatchData, ReplayClock, parse_clock
from api.spend import SpendGuard
from api.ws import Hub

SPEND_EVERY_S = 5.0


def spend_payload(match_id: str) -> dict:
    """{match_usd, day_usd, caps} from the ledger (a fresh SpendGuard re-reads it, so other processes count)."""
    s = SpendGuard().summary(match_id)
    return {"match_usd": s["match_usd"], "day_usd": s["day_usd"], "project_usd": s["project_usd"], "caps": s["caps"]}


def create_app(seed: int | str | None = None, speed: float | None = None, playing: bool = True,
               wall: Callable[[], float] | None = None, bb=None, feed: bool | None = None) -> FastAPI:
    seed = seed if seed is not None else os.environ.get("WHYLINE_MATCH_SEED", "4242")
    feed = feed if feed is not None else os.environ.get("WHYLINE_REPLAY_FEED") == "1"
    speed = speed if speed is not None else float(os.environ.get("WHYLINE_REPLAY_SPEED") or 1)
    mode = os.environ.get("WHYLINE_MODE", "replay")

    async def spend_loop(hub: Hub) -> None:
        while True:
            await asyncio.sleep(SPEND_EVERY_S)
            with contextlib.suppress(Exception):
                hub.send([envelope("spend", spend_payload(hub.match_id))])

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        data = MatchData.load(seed)
        kwargs = {"wall": wall} if wall else {}
        clock = ReplayClock(data.end_ms, speed=speed, playing=playing, **kwargs)
        if bb is None:
            from blackboard import SqliteBlackboard

            board = SqliteBlackboard()
        else:
            board = bb
        app.state.data, app.state.clock, app.state.bb = data, clock, board
        replay_feed = None
        if feed:
            from api.replay import match_dir
            from api.replay_feed import ReplayFeed

            replay_feed = ReplayFeed(data, match_dir(seed) / "cache", board)
        app.state.hub = Hub(data, clock, mode=mode, bb=board, feed=replay_feed)
        app.state.forwarder = cues.Forwarder(app.state.hub, board)
        tasks = [asyncio.create_task(app.state.hub.run()), asyncio.create_task(app.state.forwarder.run()),
                 asyncio.create_task(spend_loop(app.state.hub))]
        app.state.demo_runner = app.state.demo_task = None
        if os.environ.get("WHYLINE_DEMO_SCRIPT"):  # the demo script (TECH_PLAN 1.8) armed from the start
            demo_runner.start(app)
        try:
            yield
        finally:
            demo_runner.stop(app)
            for t in tasks:
                t.cancel()
            for t in tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await t

    app = FastAPI(title="whyline-api", lifespan=lifespan)
    # the screens are served from other origins (:5173-5175, static files in tests); the API holds no secrets
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    for module in (control, cues, demo_runner, docs, ingest, players):
        app.include_router(module.router)

    @app.get("/health")
    def health() -> dict:
        hub: Hub = app.state.hub
        return {"status": "ok", "match_id": hub.match_id, "mode": hub.mode, "clients": len(hub.clients),
                "clock": app.state.clock.state().model_dump(), "stream_t_ms": hub.now()}

    @app.get("/match/{match_id}/events")
    def events(match_id: str, start: str | None = Query(None, alias="from"),
               end: str | None = Query(None, alias="to")) -> list[dict]:
        data: MatchData = app.state.data
        try:
            lo = parse_clock(start) if start is not None else None
            hi = parse_clock(end) if end is not None else None
        except ValueError as exc:
            raise HTTPException(422, f"bad from/to: {exc}") from exc
        if match_id.removeprefix("m_") == data.match_id.removeprefix("m_"):
            return data.events_range(lo, hi)
        mid = match_id if match_id.startswith("m_") else f"m_{match_id}"
        found = app.state.bb.query("events", match_id=mid, t_from_ms=lo, t_to_ms=hi)
        if not found and mid != app.state.hub.match_id:
            raise HTTPException(404, f"match {match_id} is not loaded (serving {data.match_id})")
        return found

    @app.get("/spend")
    def spend() -> dict:
        return spend_payload(app.state.hub.match_id)

    @app.websocket("/ws")
    async def ws(websocket: WebSocket, viewer_id: str = "", mode: str = "analyst", club: str | None = None,
                 player: str | None = None) -> None:
        await websocket.accept()
        await app.state.hub.serve(websocket, viewer_profile(viewer_id, mode, club, player))

    return app


app = create_app()
