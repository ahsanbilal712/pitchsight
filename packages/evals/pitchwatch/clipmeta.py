"""Per-clip metadata for Pitchwatch: registered clips (config/footage.yaml) or a local-only clip's own clip.json.

A local-only clip (data/footage/SOURCES.md: not covered by the footage permission) is never registered in the shared
config; its folder holds clip.json {match_id, home, away, ...}. A clip with neither tagged events nor reviewed strikes
has its cache files written without a manifest.
The attack direction and the period come from the clip's reviewed directions.json when it states them
({"home_attacks": {"1": "+x", "2": "-x"}, "period_by_shot": {shot_id: period}}), else from shotxg.HOME_ATTACKS_P2 and
the tagged events, as for the Premier League clips.
"""

from __future__ import annotations

import json

from evals.pitchwatch.insights import FOOTAGE


def is_local(slug: str) -> bool:
    from footage.clips import CLIPS
    return slug not in CLIPS


def has_manifest(slug: str) -> bool:
    """A cache manifest needs a registered clip with tagged events or reviewed strikes (footage.featured.open_cache
    hashes one of them); a clip with neither gets plain cache files in the same envelope."""
    d = FOOTAGE / slug
    return not is_local(slug) and ((d / "events.jsonl").exists() or (d / "strikes.json").exists())


def clip_meta(slug: str) -> dict:
    from footage.clips import CLIPS
    return CLIPS[slug] if slug in CLIPS else json.loads((FOOTAGE / slug / "clip.json").read_text())


def _directions(slug: str) -> dict:
    p = FOOTAGE / slug / "directions.json"
    return json.loads(p.read_text()) if p.exists() else {}


def period_of(slug: str, shot_id, clip_ms: int) -> int:
    by = _directions(slug).get("period_by_shot") or {}
    if str(shot_id) in by:
        return int(by[str(shot_id)])
    ev = [json.loads(x) for x in (FOOTAGE / slug / "events.jsonl").read_text().splitlines()]
    return min(ev, key=lambda e: abs(e["attrs"]["clip_ms"] - clip_ms))["period"]


def home_attacks_plus(slug: str, period: int) -> bool:
    by = _directions(slug).get("home_attacks")
    if by:
        return by[str(period)] == "+x"
    from evals.pitchwatch.shotxg import HOME_ATTACKS_P2
    return HOME_ATTACKS_P2[slug] * (1 if period == 2 else -1) > 0
