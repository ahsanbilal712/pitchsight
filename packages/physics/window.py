"""TrackingWindow and Frame: slices of a match's 10 Hz tracking (TECH_PLAN 1.3 tracking table).

Coordinates: 105 x 68 m, origin bottom-left, home attacks +x in period 1. S rows 0-10 home, 11-21 away, 22 ball;
columns x, y, vx, vy, stamina, facing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

PITCH_L, PITCH_W = 105.0, 68.0
FRAME_MS = 100


def home_dir(period: int) -> int:
    """+1 when the home team attacks +x (period 1), -1 in period 2."""
    return 1 if int(period) == 1 else -1


@dataclass
class Frame:
    t_ms: int
    period: int
    S: np.ndarray            # [23, 6]
    ball_z: float
    holder: int              # row index, -1 none
    possession: int          # 0 home, 1 away, -1 none
    player_ids: np.ndarray | None = None
    subs: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None   # (t_ms, row, player_on)

    def row_of(self, player_id: str) -> int:
        """Row of a player at this frame (substitutions applied), -1 if not on the pitch."""
        if self.player_ids is None:
            return -1
        ids = [str(p) for p in self.player_ids]
        if self.subs is not None:
            for st, sr, on in zip(*self.subs, strict=True):
                if int(st) <= self.t_ms:
                    ids[int(sr)] = str(on)
        return ids.index(player_id) if player_id in ids else -1

    def attack_dir(self, team: int) -> int:
        """+1 when `team` (0 home, 1 away) attacks +x in this frame's period."""
        d = home_dir(self.period)
        return d if team == 0 else -d


@dataclass
class TrackingWindow:
    t_ms: np.ndarray         # [T] int64
    period: np.ndarray       # [T] int8
    S: np.ndarray            # [T, 23, 6]
    ball_z: np.ndarray       # [T]
    holder: np.ndarray       # [T]
    possession: np.ndarray   # [T]
    player_ids: np.ndarray | None = None      # starting XI in row order
    subs: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None   # (t_ms, row, player_on)

    @classmethod
    def from_tracking(cls, tracking: dict, start_ms: int | None = None, end_ms: int | None = None) -> TrackingWindow:
        """Window [start_ms, end_ms] (inclusive) of a tracking dict as written by kickoff.record."""
        t = np.asarray(tracking["t_ms"])
        lo = 0 if start_ms is None else int(np.searchsorted(t, start_ms, side="left"))
        hi = len(t) if end_ms is None else int(np.searchsorted(t, end_ms, side="right"))
        sl = slice(lo, hi)
        return cls(t_ms=t[sl], period=np.asarray(tracking["period"])[sl], S=np.asarray(tracking["S"])[sl],
                   ball_z=np.asarray(tracking["ball_z"])[sl], holder=np.asarray(tracking["holder"])[sl],
                   possession=np.asarray(tracking["possession"])[sl],
                   player_ids=tracking.get("player_ids"),
                   subs=tracking.get("subs") or ((tracking["sub_t_ms"], tracking["sub_row"], tracking["sub_player_id"])
                                                 if "sub_t_ms" in tracking else None))

    @classmethod
    def load(cls, match_dir: str | Path, start_ms: int | None = None, end_ms: int | None = None) -> TrackingWindow:
        with np.load(Path(match_dir) / "tracking.npz", allow_pickle=False) as z:
            tracking = {k: z[k] for k in z.files}
        return cls.from_tracking(tracking, start_ms, end_ms)

    def __len__(self) -> int:
        return len(self.t_ms)

    def slice(self, start_ms: int | None, end_ms: int | None) -> TrackingWindow:
        return TrackingWindow.from_tracking(self.__dict__, start_ms, end_ms)

    def player_at(self, row: int, t_ms: int) -> str:
        """Player id in `row` at t_ms, with substitutions applied; `row_<n>` when the window has no ids."""
        if self.player_ids is None:
            return f"row_{row}"
        pid = str(self.player_ids[row])
        if self.subs is not None:
            for st, sr, on in zip(*self.subs, strict=True):
                if int(sr) == row and int(st) <= t_ms:
                    pid = str(on)
        return pid

    def index_at(self, t_ms: int) -> int:
        """Index of the last frame at or before t_ms (0 if t_ms precedes the window)."""
        return max(0, int(np.searchsorted(self.t_ms, t_ms, side="right")) - 1)

    def frame(self, i: int = -1) -> Frame:
        return Frame(t_ms=int(self.t_ms[i]), period=int(self.period[i]), S=self.S[i], ball_z=float(self.ball_z[i]),
                     holder=int(self.holder[i]), possession=int(self.possession[i]), player_ids=self.player_ids,
                     subs=self.subs)

    def frame_at(self, t_ms: int) -> Frame:
        return self.frame(self.index_at(t_ms))

    @property
    def duration_s(self) -> float:
        return 0.0 if len(self) < 2 else (int(self.t_ms[-1]) - int(self.t_ms[0])) / 1000.0
