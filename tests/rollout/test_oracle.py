"""Oracle (T-046): p_shot_10s per team with the 8-10 s estimate labelled, deterministic, cached every 2 s; the
storyboard Oracle beat has p_shot >= 0.30 (config/budgets.yaml hard_rules.oracle_min_p_shot)."""

import json
from pathlib import Path

import pytest
import yaml

from rollout.oracle import oracle, shot_zone

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "matches" / "4242" / "cache"
MIN_P = yaml.safe_load((ROOT / "config" / "budgets.yaml").read_text())["director"]["hard_rules"]["oracle_min_p_shot"]


def test_forecast_shape_and_determinism(golden):
    a = oracle(golden, 1_870_000, n=50)
    b = oracle(golden, 1_870_000, n=50)
    assert a == b
    for side in ("home", "away"):
        assert 0 <= a.p_shot_10s_estimated[side] <= a.p_shot_10s[side] <= 1
    assert a.horizon_s == 8 and a.n == 50


def test_shot_zones():
    assert shot_zone(100.0, 34.0, 0, 1) == "box_central"
    assert shot_zone(100.0, 20.0, 0, 1) == "box_right"
    assert shot_zone(80.0, 34.0, 0, 1) == "outside_box"
    assert shot_zone(5.0, 20.0, 1, 1) == "box_left"          # away attacks -x in period 1, v mirrored


def test_cached_every_two_seconds():
    manifest = CACHE / "manifest.json"
    if not (CACHE / "analytics" / "oracle.json").exists():
        pytest.skip("oracle stage not run yet")
    doc = json.loads((CACHE / "analytics" / "oracle.json").read_text())
    ts = [f["t_ms"] for f in doc["forecasts"]]
    assert doc["every_ms"] == 2000 and doc["n"] == 200 and all(b - a == 2000 for a, b in zip(ts, ts[1:], strict=False))
    assert max(max(f["p_shot_10s"].values()) for f in doc["forecasts"]) >= MIN_P
    assert "oracle" in manifest.read_text()
    gm = ROOT / "packages" / "demo" / "golden_moments.yaml"
    if gm.exists():
        beat = yaml.safe_load(gm.read_text()).get("oracle")
        if beat:
            f = next(f for f in doc["forecasts"] if f["t_ms"] == beat["t_ms"])
            assert max(f["p_shot_10s"].values()) >= MIN_P
