"""Replay feed (TECH_PLAN 1.1 "Data flow, replay mode", 1.8): what the golden cache contributes on the replay clock.

    analytics/frames.npz  -> `fact` messages: indices once a second (chaos_index, control_home, pressure_home,
                             pressure_away, tempo, turnovers_60s) and `chaos_state` on every state change
    analytics/oracle.json -> `oracle` messages in the 1.9 shape {t_ms, p_shot_home, p_shot_away, zone {x, y, r},
                             shooter}, converted from the rollout doc (p_shot_10s, likely_zone, likely_shooter)
    moments.jsonl         -> blackboard `moments`, written when the clock reaches each moment, so the newsroom
                             worker runs it then (the 44:10 kill needs its run in flight at 44:10)

Facts and oracle go straight to the stream (screens only need them as messages; thousands of index facts would
only bloat the blackboard). A reset (connect, seek) gets the latest values at the new clock. Moments the clock has
passed are written once; ones already in the blackboard (written by the Scout, T-029) are left alone.
Enabled with WHYLINE_REPLAY_FEED=1 or `python -m api.replay --feed`.
"""

from __future__ import annotations

import bisect
import json
from pathlib import Path

import numpy as np

from api.models import envelope

INDEX_FACTS = {"chaos": ("chaos_index", "index_0_100"), "control_home": ("control_home", "share"),
               "pressure_home": ("pressure_home", "index_0_1"), "pressure_away": ("pressure_away", "index_0_1"),
               "tempo": ("tempo", "passes_per_min"), "turnovers_60s": ("turnovers_60s", "count")}
EVERY_MS = 1000
ORACLE_FRESH_MS = 4000
# zone centres in the attacking team's frame (attacking toward x = 105), metres, with a radius
ZONES = {"box_central": (97.0, 34.0, 8.0), "box_left": (96.0, 45.0, 8.0), "box_right": (96.0, 23.0, 8.0),
         "outside_box": (83.0, 34.0, 11.0)}


def _round(v: float) -> float:
    return round(float(v), 3)


class ReplayFeed:
    def __init__(self, data, cache_dir: Path, bb=None) -> None:
        self.data = data
        self.bb = bb
        self.match_id = data.match_id
        self.facts_t: list[int] = []
        self.facts: list[dict[str, float]] = []
        self.states: list[tuple[int, str]] = []
        frames = cache_dir / "analytics" / "frames.npz"
        if frames.exists():
            with np.load(frames) as d:
                t = d["t_ms"]
                keep = np.nonzero(t % EVERY_MS == 0)[0]
                self.facts_t = [int(x) for x in t[keep]]
                cols = {k: d[k][keep] for k in INDEX_FACTS if k in d.files}
                self.facts = [{k: _round(v[i]) for k, v in cols.items()} for i in range(len(keep))]
                names = [str(n) for n in d["state_names"]]
                state = d["state"]
                change = np.nonzero(np.r_[True, state[1:] != state[:-1]])[0]
                self.states = [(int(t[i]), names[int(state[i])]) for i in change]
        self.oracle: list[dict] = []
        oracle = cache_dir / "analytics" / "oracle.json"
        if oracle.exists():
            raw = json.loads(oracle.read_text())
            docs = raw.get("docs", raw.get("oracle", raw)) if isinstance(raw, dict) else raw
            self.oracle = sorted((self.oracle_message(d) for d in docs if isinstance(d, dict) and "t_ms" in d),
                                 key=lambda o: o["t_ms"])
        self.oracle_t = [o["t_ms"] for o in self.oracle]
        self.moments: list[dict] = []
        path = cache_dir / "moments.jsonl"
        if path.exists():
            self.moments = sorted((json.loads(x) for x in path.read_text().splitlines() if x.strip()),
                                  key=lambda m: m["t_ms"])
        self.moments_t = [int(m["t_ms"]) for m in self.moments]
        self.released: set[str] = set()

    # ------------------------------------------------------------------ conversions
    def oracle_message(self, doc: dict) -> dict:
        """Rollout oracle doc -> TECH_PLAN 1.9 oracle message (the overlay threat front draws zone {x, y, r})."""
        t = int(doc["t_ms"])
        i = self.data.index_at(t)
        shooter = doc.get("likely_shooter")
        ids = self.data.lineup_at(t)
        team = (0 if ids.index(shooter) < 11 else 1) if shooter in ids else int(self.data.possession[i])
        team = max(team, 0)
        p = float(doc.get("p_shot_10s", doc.get("p_shot", 0.0)))
        period = int(self.data.period[i])
        u, v, r = ZONES.get(str(doc.get("likely_zone")), ZONES["outside_box"])
        toward_right = ((1 if period == 1 else -1) * (1 if team == 0 else -1)) > 0
        x, y = (u, v) if toward_right else (105.0 - u, 68.0 - v)
        return {"match_id": self.match_id, "t_ms": t, "p_shot_home": _round(p if team == 0 else 0.0),
                "p_shot_away": _round(p if team == 1 else 0.0), "zone": {"x": x, "y": y, "r": r},
                "zone_label": doc.get("likely_zone"), "shooter": shooter, "n": doc.get("n"),
                "horizon_s": doc.get("horizon_s"), "seed": doc.get("seed")}

    def _facts_at(self, i: int) -> list[dict]:
        t = self.facts_t[i]
        return [{"id": f"af_{name}_{t}", "match_id": self.match_id, "t_ms": t, "kind": "index", "name": name,
                 "value": self.facts[i][col], "unit": unit, "window_s": 60, "source": "cache/analytics"}
                for col, (name, unit) in INDEX_FACTS.items() if col in self.facts[i]]

    def _state(self, t: int, name: str) -> dict:
        return {"id": f"af_chaos_state_{t}", "match_id": self.match_id, "t_ms": t, "kind": "state",
                "name": "chaos_state", "value": name, "unit": None, "window_s": 20, "source": "cache/analytics"}

    # ------------------------------------------------------------------ clock
    def between(self, after_ms: int, until_ms: int) -> list[tuple[int, dict]]:
        """Stream messages with after_ms < t <= until_ms, as (t, message)."""
        out: list[tuple[int, dict]] = []
        lo, hi = bisect.bisect_right(self.facts_t, after_ms), bisect.bisect_right(self.facts_t, until_ms)
        for i in range(lo, hi):
            out += [(self.facts_t[i], envelope("fact", f)) for f in self._facts_at(i)]
        for t, name in self.states:
            if after_ms < t <= until_ms:
                out.append((t, envelope("fact", self._state(t, name))))
        lo, hi = bisect.bisect_right(self.oracle_t, after_ms), bisect.bisect_right(self.oracle_t, until_ms)
        out += [(self.oracle[i]["t_ms"], envelope("oracle", self.oracle[i])) for i in range(lo, hi)]
        return out

    def snapshot(self, t_ms: int) -> list[dict]:
        """The latest facts and a fresh oracle at t_ms, for a screen that just reset."""
        msgs = []
        i = bisect.bisect_right(self.facts_t, t_ms) - 1
        if i >= 0:
            msgs += [envelope("fact", f) for f in self._facts_at(i)]
        state = next((s for s in reversed(self.states) if s[0] <= t_ms), None)
        if state:
            msgs.append(envelope("fact", self._state(*state)))
        j = bisect.bisect_right(self.oracle_t, t_ms) - 1
        if j >= 0 and t_ms - self.oracle_t[j] <= ORACLE_FRESH_MS:
            msgs.append(envelope("oracle", self.oracle[j]))
        return msgs

    def release_moments(self, until_ms: int) -> int:
        """Write every cached moment at or before until_ms that is not in the blackboard yet; returns how many."""
        if self.bb is None:
            return 0
        n = 0
        for m in self.moments[: bisect.bisect_right(self.moments_t, until_ms)]:
            mid = m["moment_id"]
            if mid in self.released:
                continue
            self.released.add(mid)
            try:
                self.bb.get("moments", mid, match_id=self.match_id)
                continue  # the Scout (or an earlier run) already wrote it
            except KeyError:
                pass
            self.bb.put("moments", {**m, "status": "new"})
            n += 1
        return n
