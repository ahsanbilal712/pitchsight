"""WebSocket fan-out (TECH_PLAN 1.9): one ticker walks the stream clock and pushes `tracking_frame` (10 Hz match
time), `event`, `lineup` and the blackboard's timed documents (cues, facts, moments, oracle) to every connected
screen; each client has its own bounded queue and its own filter (cue targets, studio-only types).

On connect, and again after every seek, a client receives `hello` {match_id, mode, replay_speed, viewer_profile}
plus optional fields screens use to rebuild state at the new clock: `t_ms`, `score`, `player_ids` (row order
with substitutions applied) and `clubs` {home, away}; then the current frame and a snapshot: cues on screen at that
clock (each preceded by its counterfactual), the latest fact per name and, for studio, recent moments, recent
trace rows and undecided producer requests. Screens treat a `hello` as a reset. `lineup` {t_ms, player_ids}
follows each substitution. Unknown fields and types are ignored by consumers (1.3).

Replay mode walks `ReplayClock` over `MatchData`; live mode (first POST /ingest/*) takes the clock from the
ingested frames instead (`LiveState`).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass, field

from fastapi import WebSocket, WebSocketDisconnect

from api.messages import TIMED_COLLECTIONS, cue_matches, doc_time, is_studio, request_payload, wants
from api.models import envelope
from api.replay import MatchData, ReplayClock

log = logging.getLogger("whyline.ws")
TICK_S = 0.05
QUEUE_MAX = 400  # about 40 s of frames at x1; a client that falls further behind loses the oldest lines
MAX_FRAMES_PER_TICK = 50  # after a stall, skip to the newest frame instead of flooding
FACT_SNAPSHOT_MS = 120_000  # index facts older than this are not replayed on reset (state facts always are)
MOMENT_SNAPSHOT = 20
TRACE_SNAPSHOT = 60


def dumps(msg: dict) -> str:
    return json.dumps(msg, separators=(",", ":"))


@dataclass(eq=False)
class Client:
    websocket: WebSocket
    profile: dict
    queue: asyncio.Queue[str] = field(default_factory=lambda: asyncio.Queue(QUEUE_MAX))
    dropped: int = 0
    cfs: set[str] = field(default_factory=set)  # counterfactual ids already sent since the last reset

    def push(self, lines: list[str]) -> None:
        if not lines:
            return
        text = "\n".join(lines)
        if self.queue.full():
            self.queue.get_nowait()
            self.dropped += 1
        self.queue.put_nowait(text)


@dataclass
class LiveState:
    """Match state rebuilt from POST /ingest/* (live mode)."""

    match_id: str
    t_ms: int = 0
    frame: dict | None = None
    score: list[int] = field(default_factory=lambda: [0, 0])
    player_ids: list[str] = field(default_factory=list)
    clubs: dict | None = None


class Hub:
    def __init__(self, data: MatchData, clock: ReplayClock, mode: str = "replay", bb=None) -> None:
        self.data = data
        self.clock = clock
        self.mode = mode
        self.bb = bb
        self.live: LiveState | None = None
        self.clients: set[Client] = set()
        state = clock.state()
        self._generation = state.generation
        self._last_t = state.t_ms
        self._last_idx = data.index_at(state.t_ms)
        self._last_doc_t = state.t_ms  # timed blackboard documents up to here have been released
        self._cf_cache: dict[str, dict] = {}

    # ------------------------------------------------------------------ clock
    @property
    def match_id(self) -> str:
        return self.live.match_id if self.live else self.data.match_id

    def now(self) -> int:
        """Stream clock: what screens are showing now (last emitted replay time, or the last ingested frame)."""
        return self.live.t_ms if self.live else self._last_t

    @property
    def released_until(self) -> int:
        """Timed documents at or before this time have been sent (or belong in a reset snapshot)."""
        return self._last_doc_t

    # ------------------------------------------------------------------ messages
    def hello(self, client: Client, t_ms: int) -> dict:
        if self.live:
            extra = {"t_ms": t_ms, "score": list(self.live.score), "player_ids": list(self.live.player_ids),
                     "clubs": self.live.clubs}
            speed = 1.0
        else:
            extra = {"t_ms": t_ms, "score": self.data.score_at(t_ms), "player_ids": self.data.lineup_at(t_ms),
                     "clubs": self.data.clubs}
            speed = self.clock.speed
        return envelope("hello", {"match_id": self.match_id, "mode": self.mode, "replay_speed": speed,
                                  "viewer_profile": client.profile, **extra})

    def counterfactual_for(self, cue: dict) -> dict | None:
        cf_id = (cue.get("explain") or {}).get("counterfactual_id")
        if not cf_id or self.bb is None:
            return None
        if cf_id not in self._cf_cache:
            try:
                self._cf_cache[cf_id] = self.bb.get("counterfactuals", cf_id, match_id=cue.get("match_id"))
            except KeyError:  # NotFound: the screen hides the swing bar until it exists
                return None
        return self._cf_cache[cf_id]

    def lines_for(self, client: Client, msgs: list[dict]) -> list[str]:
        """The lines of `msgs` this client may see; a cue brings its counterfactual along the first time."""
        out = []
        for m in msgs:
            kind = m["type"]
            if kind == "cue":
                if not cue_matches(client.profile, m["payload"]):
                    continue
                cf = self.counterfactual_for(m["payload"])
                if cf and cf["counterfactual_id"] not in client.cfs:
                    client.cfs.add(cf["counterfactual_id"])
                    out.append(dumps(envelope("counterfactual", cf)))
            elif not wants(client.profile, kind):
                continue
            out.append(dumps(m))
        return out

    def send(self, msgs: list[dict]) -> int:
        """Queue messages for every client that may see them; returns how many clients got something."""
        n = 0
        for c in list(self.clients):
            lines = self.lines_for(c, msgs)
            if lines:
                c.push(lines)
                n += 1
        return n

    def broadcast(self, msg: dict, accept=None) -> int:
        if accept is None:
            return self.send([msg])
        line = dumps(msg)
        clients = [c for c in list(self.clients) if accept(c)]
        for c in clients:
            c.push([line])
        return len(clients)

    # ------------------------------------------------------------------ blackboard documents
    def timed_between(self, after_ms: int, until_ms: int) -> list[tuple[int, dict]]:
        """Timed blackboard documents with after_ms < t <= until_ms, as (t, message)."""
        if self.bb is None or until_ms <= after_ms:
            return []
        out = []
        for coll, kind in TIMED_COLLECTIONS.items():
            for doc in self.bb.query(coll, match_id=self.match_id, t_from_ms=after_ms + 1, t_to_ms=until_ms):
                if coll == "cues" and doc.get("producer_status") == "vetoed":
                    continue
                out.append((doc_time(doc) or until_ms, envelope(kind, doc)))
        return out

    def snapshot(self, client: Client, t_ms: int) -> list[dict]:
        """What a screen needs to show the right things at t_ms after a reset."""
        if self.bb is None:
            return []
        mid = self.match_id
        msgs: list[dict] = []
        latest: dict[str, dict] = {}
        for f in self.bb.query("facts", match_id=mid, kind="state", t_to_ms=t_ms):
            latest[f.get("name", "")] = f
        for f in self.bb.query("facts", match_id=mid, t_from_ms=t_ms - FACT_SNAPSHOT_MS, t_to_ms=t_ms):
            latest[f.get("name", "")] = f
        msgs += [envelope("fact", f) for f in sorted(latest.values(), key=lambda f: doc_time(f) or 0)]
        if is_studio(client.profile):
            msgs += [envelope("moment", m) for m in
                     self.bb.query("moments", match_id=mid, t_to_ms=t_ms)[-MOMENT_SNAPSHOT:]]
            msgs += [envelope("trace", r) for r in self.bb.query("traces", match_id=mid)[-TRACE_SNAPSHOT:]]
            decided = {d.get("request_id") for d in self.bb.query("decisions", match_id=mid)}
            msgs += [envelope("request_info", request_payload(r)) for r in self.bb.query("requests", match_id=mid)
                     if request_payload(r)["request_id"] not in decided]
        for cue in self.bb.query("cues", match_id=mid, t_to_ms=t_ms):
            if cue.get("producer_status") != "vetoed" and int(cue.get("t_out_ms", 0)) > t_ms:
                msgs.append(envelope("cue", cue))
        return msgs

    def _reset_lines(self, client: Client) -> list[str]:
        client.cfs.clear()
        t_ms = self.now()
        frame = self.live.frame if self.live else self.data.frame(self._last_idx)
        msgs = [self.hello(client, t_ms)]
        if frame is not None:
            msgs.append(envelope("tracking_frame", frame))
        return self.lines_for(client, msgs + self.snapshot(client, t_ms))

    def reset_all(self) -> None:
        self._last_doc_t = self.now()
        for c in list(self.clients):
            c.push(self._reset_lines(c))

    # ------------------------------------------------------------------ live ingest
    def _live_for(self, match_id: str) -> tuple[LiveState, bool]:
        """The live state for match_id, and whether it was just created (screens then need a reset)."""
        if self.live is None or self.live.match_id != match_id:
            self.live = LiveState(match_id=match_id)
            self.mode = "live"
            self._cf_cache.clear()
            return self.live, True
        return self.live, False

    def ingest_events(self, events: list[dict]) -> None:
        if not events:
            return
        live, fresh = self._live_for(events[0]["match_id"])
        msgs = []
        for e in events:
            msgs.append(envelope("event", e))
            attrs = e.get("attrs") or {}
            if e["type"] == "match_metadata":
                lineups = attrs.get("lineups") or {}
                live.player_ids = [*(lineups.get("home") or {}).get("starting", []),
                                   *(lineups.get("away") or {}).get("starting", [])]
                if "home" in attrs and "away" in attrs:
                    live.clubs = {"home": attrs["home"], "away": attrs["away"]}
            elif e["type"] == "goal" and e.get("team") in ("home", "away"):
                live.score[0 if e["team"] == "home" else 1] += 1
            elif e["type"] == "substitution" and attrs.get("player_off") in live.player_ids:
                live.player_ids[live.player_ids.index(attrs["player_off"])] = attrs.get("player_on")
                msgs.append(envelope("lineup", {"t_ms": e["t_ms"], "player_ids": list(live.player_ids)}))
        if fresh:
            self.reset_all()  # after the metadata, so the hello carries the lineup and clubs
        self.send(msgs)

    def ingest_frames(self, match_id: str, frames: list[dict]) -> None:
        live, fresh = self._live_for(match_id)
        for f in frames:
            if f["t_ms"] >= live.t_ms:
                live.t_ms, live.frame = int(f["t_ms"]), f
        if fresh:
            self.reset_all()
        self.send([envelope("tracking_frame", f) for f in frames])

    # ------------------------------------------------------------------ ticker
    def tick(self) -> None:
        """Advance from the last emitted clock to now and queue everything in between."""
        if self.live:
            t = self.live.t_ms
            timed = self.timed_between(self._last_doc_t, t)
            self._last_doc_t = max(self._last_doc_t, t)
            if timed:
                self.send([m for _, m in sorted(timed, key=lambda x: x[0])])
            return
        state = self.clock.state()
        if state.generation != self._generation:  # seek: every screen resets at the new clock
            self._generation = state.generation
            self._last_t = state.t_ms
            self._last_idx = self.data.index_at(state.t_ms)
            self.reset_all()
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
        for doc_t, msg in self.timed_between(self._last_doc_t, t):
            timed.append((doc_t, 3, msg))
        self._last_t, self._last_idx, self._last_doc_t = t, max(idx, self._last_idx), t
        if not timed or not self.clients:
            return
        timed.sort(key=lambda x: (x[0], x[1]))
        self.send([m for _, _, m in timed])

    async def run(self) -> None:
        while True:
            try:
                self.tick()
            except Exception:  # keep the stream alive; a bad tick is logged, not fatal
                log.exception("stream tick failed")
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
