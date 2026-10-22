"""Dugout (T-047): options ranked by the team's win-probability change; three cached at 60:00 with n, horizon and
seed; the 'Dugout called it' log records whether the recommendation matched."""

import json
from pathlib import Path

import pytest

from rollout.dugout import GRID, dugout, label

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "matches" / "4242" / "cache"


def test_grid_and_labels():
    assert len(GRID) == 8 and {"press_height": 0.0, "directness": 0.0} not in GRID
    assert label({"press_height": 0.15, "directness": -0.15}) == "press higher and keep the ball"


def test_ranked_by_delta(golden):
    res = dugout(golden, 3_600_000, "home", options=GRID[:3], n=20, horizon_s=8)
    assert len(res) == 3 and all(r.n == 20 and r.horizon_s == 8 for r in res)
    assert [r.delta_win_prob for r in res] == sorted((r.delta_win_prob for r in res), reverse=True)


def test_cached_options_at_60_minutes():
    files = sorted((CACHE / "dugout").glob("dugout_*_3600000.json")) if (CACHE / "dugout").exists() else []
    if not files:
        pytest.skip("dugout stage not run yet")
    for f in files:
        doc = json.loads(f.read_text())
        assert doc["t_ms"] == 3_600_000 and len(doc["options"]) == 3
        assert all({"delta_win_prob", "n", "horizon_s", "seed"} <= set(o) for o in doc["options"])
    log = ROOT / "packages" / "evals" / "out" / "dugout_log.json"
    if log.exists():
        for team in json.loads(log.read_text())["teams"].values():
            assert team["caption_allowed"] == (team["matched"] and team["delta_win_prob"] > 0)
