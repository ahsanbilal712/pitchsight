"""Request and message shapes of whyline-api."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

SPEED_MIN, SPEED_MAX = 1.0, 10.0


class ControlRequest(BaseModel):
    """POST /replay/control. `value` carries the speed or the seek target (ms or "mm:ss").

    `t_ms` is accepted as an alias of `value` for seek (the overlay's record handle sends it)."""

    action: Literal["play", "pause", "seek", "speed"]
    value: float | int | str | None = None
    t_ms: int | None = None


class ClockState(BaseModel):
    t_ms: int
    speed: float
    playing: bool
    generation: int = Field(description="bumps on every seek; screens reset their state on a new hello")


def envelope(kind: str, payload: Any) -> dict:
    """Every stream message is {type, payload}; one JSON object per line."""
    return {"type": kind, "payload": payload}


def viewer_profile(viewer_id: str, mode: str, club: str | None, player: str | None) -> dict:
    """ViewerProfile (schemas/viewer_profile.schema.json) built from the /ws query string."""
    mode = mode if mode in ("analyst", "casual", "player_cam", "studio") else "analyst"
    return {
        "schema_version": "1.0.0",
        "viewer_id": viewer_id or "anonymous",
        "mode": mode,
        "club": club if club in ("home", "away") else None,
        "player": player or None,
        "metric": None,
        "high_contrast": False,
        "show_heatmap": mode == "analyst",
    }
