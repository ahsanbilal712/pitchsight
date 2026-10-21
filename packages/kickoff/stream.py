"""Stream a simulated match into whyline-api in real time (TECH_PLAN 1.1 live data flow, T-033).

    python -m kickoff play --seed N --target api [--api http://localhost:8000] [--speed 1]

The engine plays the match first (about 10 s for 90 minutes), then events and 10 Hz tracking frames are posted to
POST /ingest/events and POST /ingest/tracking on the match clock: one tracking post per frame, events in the same
post cycle as the frame they belong to. Standard library HTTP only.
"""

from __future__ import annotations

import json
import time
import urllib.request
from collections.abc import Callable

import numpy as np


def frame_json(tracking: dict, i: int) -> dict:
    """tracking_frame payload (TECH_PLAN 1.3) for frame i of a tracking dict (same keys as tracking.npz)."""
    return {
        "t_ms": int(tracking["t_ms"][i]),
        "period": int(tracking["period"][i]),
        "p": np.round(tracking["S"][i, :, :4].astype(np.float64), 2).tolist(),
        "ball_z": round(float(tracking["ball_z"][i]), 2),
        "holder": int(tracking["holder"][i]),
        "possession": int(tracking["possession"][i]),
    }


def post_json(url: str, body: object, timeout: float = 5.0) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body, separators=(",", ":")).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def stream_match(match_id: str, events: list[dict], tracking: dict, api: str = "http://localhost:8000",
                 speed: float = 1.0, start_ms: int = 0, until_ms: int | None = None,
                 post: Callable[[str, object], dict] = post_json, sleep: Callable[[float], None] = time.sleep,
                 now: Callable[[], float] = time.monotonic) -> dict:
    """Post events and frames on the match clock (x`speed`). Returns counts {events, frames}."""
    api = api.rstrip("/")
    t_ms = tracking["t_ms"]
    events = sorted(events, key=lambda e: (e["t_ms"], e.get("idx", 0)))
    head = [e for e in events if e["type"] == "match_metadata"]
    if head:
        post(f"{api}/ingest/events", head)
    rest = [e for e in events if e["type"] != "match_metadata" and e["t_ms"] >= start_ms]
    first = int(np.searchsorted(t_ms, start_ms, side="left"))
    last = len(t_ms) if until_ms is None else int(np.searchsorted(t_ms, until_ms, side="right"))
    wall0, k, sent_frames = now(), 0, 0
    for i in range(first, last):
        t = int(t_ms[i])
        due = wall0 + (t - int(t_ms[first])) / 1000.0 / speed
        wait = due - now()
        if wait > 0:
            sleep(wait)
        batch = []
        while k < len(rest) and rest[k]["t_ms"] <= t:
            batch.append(rest[k])
            k += 1
        if batch:
            post(f"{api}/ingest/events", batch)
        post(f"{api}/ingest/tracking?match_id={match_id}", frame_json(tracking, i))
        sent_frames += 1
    return {"events": len(head) + k, "frames": sent_frames}
