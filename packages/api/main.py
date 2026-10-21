"""whyline-api (TECH_PLAN 1.1, 1.4 api): REST, the WebSocket stream and the replay controller.

Run: `PYTHONPATH=packages uvicorn api.main:app --port 8000`, or `python -m api.replay --seed 4242`.
WHYLINE_MATCH_SEED picks the match under data/matches/, WHYLINE_REPLAY_SPEED the starting speed (x1..x10).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import AsyncIterator, Callable

from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from api.models import ControlRequest, viewer_profile
from api.replay import MatchData, ReplayClock, parse_clock
from api.ws import Hub


def create_app(seed: int | str | None = None, speed: float | None = None, playing: bool = True,
               wall: Callable[[], float] | None = None) -> FastAPI:
    seed = seed if seed is not None else os.environ.get("WHYLINE_MATCH_SEED", "4242")
    speed = speed if speed is not None else float(os.environ.get("WHYLINE_REPLAY_SPEED") or 1)
    mode = os.environ.get("WHYLINE_MODE", "replay")

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        data = MatchData.load(seed)
        kwargs = {"wall": wall} if wall else {}
        clock = ReplayClock(data.end_ms, speed=speed, playing=playing, **kwargs)
        app.state.data, app.state.clock = data, clock
        app.state.hub = Hub(data, clock, mode=mode)
        ticker = asyncio.create_task(app.state.hub.run())
        try:
            yield
        finally:
            ticker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await ticker

    app = FastAPI(title="whyline-api", lifespan=lifespan)
    # the screens are served from other origins (:5173-5175, static files in tests); the API holds no secrets
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "match_id": app.state.data.match_id, "mode": app.state.hub.mode,
                "clients": len(app.state.hub.clients), "clock": app.state.clock.state().model_dump()}

    @app.get("/match/{match_id}/events")
    def events(match_id: str, start: str | None = Query(None, alias="from"),
               end: str | None = Query(None, alias="to")) -> list[dict]:
        data: MatchData = app.state.data
        if match_id.removeprefix("m_") != data.match_id.removeprefix("m_"):
            raise HTTPException(404, f"match {match_id} is not loaded (serving {data.match_id})")
        try:
            lo = parse_clock(start) if start is not None else None
            hi = parse_clock(end) if end is not None else None
        except ValueError as exc:
            raise HTTPException(422, f"bad from/to: {exc}") from exc
        return data.events_range(lo, hi)

    @app.post("/replay/control")
    def control(req: ControlRequest) -> dict:
        clock: ReplayClock = app.state.clock
        try:
            if req.action == "play":
                clock.play()
            elif req.action == "pause":
                clock.pause()
            elif req.action == "seek":
                target = req.value if req.value is not None else req.t_ms
                if target is None:
                    raise ValueError("seek needs value (ms or mm:ss) or t_ms")
                clock.seek(parse_clock(target))
            elif req.action == "speed":
                if req.value is None:
                    raise ValueError("speed needs value")
                clock.set_speed(float(req.value))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return clock.state().model_dump()

    @app.websocket("/ws")
    async def ws(websocket: WebSocket, viewer_id: str = "", mode: str = "analyst", club: str | None = None,
                 player: str | None = None) -> None:
        await websocket.accept()
        await app.state.hub.serve(websocket, viewer_profile(viewer_id, mode, club, player))

    return app


app = create_app()
