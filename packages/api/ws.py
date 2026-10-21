"""WebSocket fan-out (TECH_PLAN 1.9): one ticker walks the replay clock and pushes `tracking_frame` (10 Hz match
time), `event` and `lineup` messages to every connected screen; each client has its own bounded queue.

On connect, and again after every seek, a client receives `hello` {match_id, mode, replay_speed, viewer_profile}
plus three optional fields screens use to rebuild state at the new clock: `t_ms`, `score` and `player_ids`
(row order with substitutions applied). Screens treat a `hello` as a reset. `lineup` {t_ms, player_ids} follows
each substitution so row-to-player mapping stays right. Unknown fields and types are ignored by consumers (1.3).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi import WebSocket, WebSocketDisconnect

from api.models import envelope
from api.replay import MatchData, ReplayClock

log = logging.getLogger("whyline.ws")
TICK_S = 0.05
QUEUE_MAX = 400  # about 40 s of frames at x1; a client that falls further behind loses the oldest lines
MAX_FRAMES_PER_TICK = 50  # after a stall, skip to the newest frame instead of flooding


def dumps(msg: dict) -> str:
    return json.dumps(msg, separators=(",", ":"))


@dataclass(eq=False)
class Client:
    websocket: WebSocket
    profile: dict
    queue: asyncio.Queue[str] = field(default_factory=lambda: asyncio.Queue(QUEUE_MAX))
    dropped: int = 0

    def push(self, lines: list[str]) -> None:
        if not lines:
            return
        text = "\n".join(lines)
        if self.queue.full():
            self.queue.get_nowait()
            self.dropped += 1
        self.queue.put_nowait(text)


class Hub:
    def __init__(self, data: MatchData, clock: ReplayClock, mode: str = "replay") -> None:
        self.data = data
        self.clock = clock
        self.mode = mode
        self.clients: set[Client] = set()
        state = clock.state()
        self._generation = state.generation
        self._last_t = state.t_ms
        self._last_idx = data.index_at(state.t_ms)

    # ------------------------------------------------------------------ messages
    def hello(self, client: Client, t_ms: int) -> dict:
        return envelope("hello", {
            "match_id": self.data.match_id, "mode": self.mode, "replay_speed": self.clock.speed,
            "viewer_profile": client.profile, "t_ms": t_ms, "score": self.data.score_at(t_ms),
            "player_ids": self.data.lineup_at(t_ms),
        })

    def _reset_lines(self, client: Client) -> list[str]:
        return [dumps(self.hello(client, self._last_t)),
                dumps(envelope("tracking_frame", self.data.frame(self._last_idx)))]

    def broadcast(self, msg: dict, accept: Callable[[Client], bool] | None = None) -> int:
        """Queue one message for every client (or those `accept` lets through); returns the count."""
        line = dumps(msg)
        n = 0
        for c in list(self.clients):
            if accept is None or accept(c):
                c.push([line])
                n += 1
        return n

    # ------------------------------------------------------------------ ticker
    def tick(self) -> None:
        """Advance from the last emitted clock to now and queue everything in between."""
        state = self.clock.state()
        if state.generation != self._generation:  # seek: every screen resets at the new clock
            self._generation = state.generation
            self._last_t = state.t_ms
            self._last_idx = self.data.index_at(state.t_ms)
            for c in list(self.clients):
                c.push(self._reset_lines(c))
            return
        t = state.t_ms
        if t <= self._last_t:
            return
        idx = self.data.index_at(t)
        timed: list[tuple[int, int, dict]] = []
        first = max(self._last_idx + 1, idx - MAX_FRAMES_PER_TICK + 1)
        for i in range(first, idx + 1):
            frame = self.data.frame(i)
            timed.append((frame["t_ms"], 0, envelope("tracking_frame", frame)))
        for e in self.data.events_between(self._last_t, t):
            timed.append((int(e["t_ms"]), 1, envelope("event", e)))
        for sub_t, _row, _pid in self.data.subs_between(self._last_t, t):
            timed.append((sub_t, 2, envelope("lineup", {"t_ms": sub_t, "player_ids": self.data.lineup_at(sub_t)})))
        self._last_t, self._last_idx = t, max(idx, self._last_idx)
        if not timed or not self.clients:
            return
        timed.sort(key=lambda x: (x[0], x[1]))
        lines = [dumps(m) for _, _, m in timed]
        for c in list(self.clients):
            c.push(lines)

    async def run(self) -> None:
        while True:
            try:
                self.tick()
            except Exception:  # keep the stream alive; a bad tick is logged, not fatal
                log.exception("replay tick failed")
            await asyncio.sleep(TICK_S)

    # ------------------------------------------------------------------ connections
    async def serve(self, websocket: WebSocket, profile: dict) -> None:
        client = Client(websocket, profile)
        client.push(self._reset_lines(client))
        self.clients.add(client)

        async def sender() -> None:
            while True:
                await websocket.send_text(await client.queue.get())

        async def receiver() -> None:
            with contextlib.suppress(WebSocketDisconnect):
                while True:
                    await websocket.receive_text()  # screens send nothing yet; this notices the close

        tasks = [asyncio.create_task(sender()), asyncio.create_task(receiver())]
        try:
            _done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
            for t in tasks:
                with contextlib.suppress(asyncio.CancelledError, Exception):  # a closed socket ends both tasks
                    await t
        finally:
            self.clients.discard(client)
