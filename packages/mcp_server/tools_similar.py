"""MCP tool similar_moments: the k nearest moments of the golden season to a moment.

The query moment is embedded with heads.MomentEncoder (pitch-control grid + 12 chaos features -> 64-d); neighbours
come from packages/heads/artifacts/moment_index.npz (evaluation seeds 1-50 and the golden match, every 10 s), other
matches only, nearest by Euclidean distance in the standardised code space. Each result names its phase cluster.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from mcp_server.errors import ToolError


@lru_cache(maxsize=1)
def _index():
    from heads.models import ARTIFACTS
    from heads.moment_encoder import MomentEncoder

    enc = MomentEncoder()
    path = ARTIFACTS / "moment_index.npz"
    if not path.exists():
        raise ToolError("index_missing", f"{path} is missing; run python -m heads.moment_encoder index")
    with np.load(path) as z:
        idx = {k: z[k] for k in z.files}
    zz = (idx["z"].astype(np.float64) - enc.z_mean) / enc.z_scale
    return enc, idx, zz


def _clock(t_ms: int) -> str:
    s = int(t_ms) // 1000
    return f"{s // 60:02d}:{s % 60:02d}"


def similar_moments(store, match_id: str, t_ms: int, k: int = 3) -> list[dict]:
    from heads.features import moment_features
    from physics.pitch_control import pitch_control

    if not 1 <= int(k) <= 10:
        raise ToolError("bad_k", "k must be 1-10")
    m = store.match(match_id)
    w = store.tracking(m)
    if w is None or not (w.t_ms[0] <= t_ms <= w.t_ms[-1]):
        raise ToolError("bad_time", f"no tracking for {match_id} at {t_ms}")
    enc, idx, zz = _index()
    feats, team = moment_features(w, m.events, int(t_ms))
    z = enc.encode(pitch_control(w.S[w.index_at(int(t_ms))].astype(np.float64)), feats, team)
    q = (z - enc.z_mean) / enc.z_scale
    seed = int(match_id[2:])
    d = np.sqrt(((zz - q) ** 2).sum(axis=1))
    d[idx["seed"] == seed] = np.inf
    order = np.argsort(d, kind="stable")
    out, seen = [], set()
    for i in order:
        key = (int(idx["seed"][i]), int(idx["t_ms"][i]) // 60_000)       # one per match minute
        if key in seen or not np.isfinite(d[i]):
            continue
        seen.add(key)
        out.append({"match_id": f"m_{int(idx['seed'][i])}", "t_ms": int(idx["t_ms"][i]),
                    "clock": _clock(int(idx["t_ms"][i])), "distance": round(float(d[i]), 3),
                    "phase": enc.names[int(idx["cluster"][i])]})
        if len(out) == int(k):
            break
    return [{"query": {"match_id": match_id, "t_ms": int(t_ms), "phase": enc.phase(z)}, **r} for r in out]
