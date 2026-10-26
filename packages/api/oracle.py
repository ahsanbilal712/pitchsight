"""Oracle forecasts on the replay clock.

The golden precompute writes cache/analytics/oracle.json as {producer: "oracle", forecasts: [...]}, one forecast
every 2 s with per-team values ({"home": p, "away": p}). `message` turns one into the 1.9 shape the overlay threat
front draws: both teams' shot probabilities, and the zone and shooter of the likelier side. An Oracle *cue* is only
allowed at p_shot >= 0.30 (budgets.yaml hard_rules.oracle_min_p_shot); the message itself streams every forecast.
"""

from __future__ import annotations


def is_forecast_file(raw) -> bool:
    return isinstance(raw, dict) and raw.get("producer") == "oracle" and isinstance(raw.get("forecasts"), list)


def message(f: dict, match_id: str, zones: dict, period_at) -> dict:
    """1.9 oracle message for one forecast. `period_at(t_ms)` gives the period (for the attacking direction)."""
    p = f["p_shot_10s"]
    side = "home" if p["home"] >= p["away"] else "away"
    team = 0 if side == "home" else 1
    label = f["likely_zone"].get(side) or "outside_box"
    u, v, r = zones.get(label, zones["outside_box"])
    toward_right = ((1 if period_at(int(f["t_ms"])) == 1 else -1) * (1 if team == 0 else -1)) > 0
    x, y = (u, v) if toward_right else (105.0 - u, 68.0 - v)
    return {"match_id": match_id, "t_ms": int(f["t_ms"]), "p_shot_home": round(float(p["home"]), 3),
            "p_shot_away": round(float(p["away"]), 3), "zone": {"x": x, "y": y, "r": r}, "zone_label": label,
            "shooter": f["likely_shooter"].get(side), "team": side, "n": f.get("n"), "horizon_s": f.get("horizon_s"),
            "seed": f.get("seed"), "estimated_share": round(float(f["p_shot_10s_estimated"][side]), 3)}
