"""Replay clock over a recorded match (TECH_PLAN 1.1 "Data flow, replay mode", 1.3 tracking frame format).

`MatchData` loads `data/matches/<seed>/{tracking.npz, events.jsonl}`; `ReplayClock` maps wall time to match
time at speed x1..x10 with play, pause and seek. `python -m api.replay --seed 4242` serves the match on
WHYLINE_API_PORT (default 8000).
"""

from __future__ import annotations

import argparse
import bisect
import json
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from api.models import SPEED_MAX, SPEED_MIN, ClockState

ROOT = Path(__file__).resolve().parents[2]
MATCHES = ROOT / "data" / "matches"


def match_dir(seed: int | str) -> Path:
    return MATCHES / str(seed).removeprefix("m_")


@dataclass
class MatchData:
    match_id: str
    t_ms: np.ndarray
    period: np.ndarray
    S: np.ndarray
    ball_z: np.ndarray
    holder: np.ndarray
    possession: np.ndarray
    player_ids: list[str]
    subs: list[tuple[int, int, str]]  # (t_ms, row, player_id), sorted by time
    events: list[dict]
    event_t: list[int] = field(default_factory=list)

    @classmethod
    def load(cls, seed: int | str) -> MatchData:
        root = match_dir(seed)
        events = [json.loads(line) for line in (root / "events.jsonl").read_text().splitlines() if line.strip()]
        with np.load(root / "tracking.npz") as d:
            subs = sorted(zip(d["sub_t_ms"].tolist(), d["sub_row"].tolist(), d["sub_player_id"].tolist(),
                              strict=True)) if "sub_t_ms" in d.files else []
            data = cls(
                match_id=events[0]["match_id"] if events else f"m_{seed}",
                t_ms=d["t_ms"], period=d["period"], S=d["S"], ball_z=d["ball_z"], holder=d["holder"],
                possession=d["possession"], player_ids=[str(p) for p in d["player_ids"]], subs=subs, events=events,
            )
        data.event_t = [int(e["t_ms"]) for e in events]
        return data

    @property
    def end_ms(self) -> int:
        return int(self.t_ms[-1])

    def index_at(self, t_ms: int) -> int:
        """Index of the last frame at or before t_ms (0 before kick-off)."""
        return max(0, int(np.searchsorted(self.t_ms, t_ms, side="right")) - 1)

    def frame(self, i: int) -> dict:
        """tracking_frame payload (TECH_PLAN 1.3): 23 rows of [x, y, vx, vy] rounded to cm and cm/s."""
        return {
            "t_ms": int(self.t_ms[i]),
            "period": int(self.period[i]),
            "p": np.round(self.S[i, :, :4].astype(np.float64), 2).tolist(),
            "ball_z": round(float(self.ball_z[i]), 2),
            "holder": int(self.holder[i]),
            "possession": int(self.possession[i]),
        }

    def events_between(self, after_ms: int, until_ms: int) -> list[dict]:
        """Events with after_ms < t_ms <= until_ms, in file order."""
        lo = bisect.bisect_right(self.event_t, after_ms)
        hi = bisect.bisect_right(self.event_t, until_ms)
        return self.events[lo:hi]

    def events_range(self, start_ms: int | None, end_ms: int | None) -> list[dict]:
        """Events with start_ms <= t_ms <= end_ms (either bound optional)."""
        lo = 0 if start_ms is None else bisect.bisect_left(self.event_t, start_ms)
        hi = len(self.events) if end_ms is None else bisect.bisect_right(self.event_t, end_ms)
        return self.events[lo:hi]

    def score_at(self, t_ms: int) -> list[int]:
        score = [0, 0]
        for e in self.events_range(None, t_ms):
            if e["type"] == "goal" and e["team"] in ("home", "away"):
                score[0 if e["team"] == "home" else 1] += 1
        return score

    def lineup_at(self, t_ms: int) -> list[str]:
        """player_ids in row order with every substitution up to t_ms applied."""
        ids = list(self.player_ids)
        for t, row, pid in self.subs:
            if t <= t_ms:
                ids[row] = pid
        return ids

    def subs_between(self, after_ms: int, until_ms: int) -> list[tuple[int, int, str]]:
        return [s for s in self.subs if after_ms < s[0] <= until_ms]


class ReplayClock:
    """Match time = anchor + (wall - wall_anchor) x speed while playing; clamped to [0, end_ms]."""

    def __init__(self, end_ms: int, speed: float = 1.0, start_ms: int = 0, playing: bool = True,
                 wall: Callable[[], float] = time.monotonic) -> None:
        self.end_ms = end_ms
        self._wall = wall
        self._lock = threading.Lock()
        self._speed = _check_speed(speed)
        self._anchor_ms = float(start_ms)
        self._anchor_wall = wall()
        self._playing = playing
        self.generation = 0

    def _now(self) -> float:
        t = self._anchor_ms
        if self._playing:
            t += (self._wall() - self._anchor_wall) * 1000.0 * self._speed
        return min(max(t, 0.0), float(self.end_ms))

    def _rebase(self) -> None:
        self._anchor_ms = self._now()
        self._anchor_wall = self._wall()

    def now(self) -> int:
        with self._lock:
            return int(self._now())

    def play(self) -> None:
        with self._lock:
            self._rebase()
            self._playing = True

    def pause(self) -> None:
        with self._lock:
            self._rebase()
            self._playing = False

    def seek(self, t_ms: int) -> None:
        with self._lock:
            self._anchor_ms = float(min(max(int(t_ms), 0), self.end_ms))
            self._anchor_wall = self._wall()
            self.generation += 1

    def set_speed(self, speed: float) -> None:
        speed = _check_speed(speed)
        with self._lock:
            self._rebase()
            self._speed = speed

    @property
    def speed(self) -> float:
        return self._speed

    @property
    def playing(self) -> bool:
        return self._playing

    def state(self) -> ClockState:
        with self._lock:
            return ClockState(t_ms=int(self._now()), speed=self._speed, playing=self._playing,
                              generation=self.generation)


def _check_speed(speed: float) -> float:
    speed = float(speed)
    if not SPEED_MIN <= speed <= SPEED_MAX:
        raise ValueError(f"replay speed must be within x{SPEED_MIN:g}..x{SPEED_MAX:g}, got {speed:g}")
    return speed


def parse_clock(value: int | float | str) -> int:
    """Milliseconds, or "mm:ss" (minutes may exceed 59), to milliseconds of match time."""
    if isinstance(value, int | float):
        return int(value)
    text = str(value).strip()
    if ":" in text:
        minutes, seconds = text.split(":", 1)
        return (int(minutes) * 60 + int(seconds)) * 1000
    return int(float(text))


def main(argv: list[str] | None = None) -> None:
    import uvicorn

    parser = argparse.ArgumentParser(prog="python -m api.replay", description="Serve a recorded match on /ws")
    parser.add_argument("--seed", type=int, default=int(os.environ.get("WHYLINE_MATCH_SEED", "4242")))
    parser.add_argument("--speed", type=float, default=float(os.environ.get("WHYLINE_REPLAY_SPEED", "1")))
    parser.add_argument("--port", type=int, default=int(os.environ.get("WHYLINE_API_PORT", "8000")))
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args(argv)
    os.environ["WHYLINE_MATCH_SEED"] = str(args.seed)
    os.environ["WHYLINE_REPLAY_SPEED"] = str(args.speed)
    uvicorn.run("api.main:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
