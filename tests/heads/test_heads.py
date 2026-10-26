"""Outcome heads: artefacts present, no silent fallback, monotonicity sanity."""

import json
import shutil

import numpy as np
import pandas as pd
import pytest

from heads.features import CHAOS_FEATURES, GOAL8_FEATURES, PASS_FEATURES
from heads.models import (
    ARTIFACTS,
    ChaosHead,
    GoalIn8sHead,
    HeadArtifactMissing,
    PassHead,
    WinProbHead,
    XGHead,
    load_all,
)

HEADS = ("xg", "pass", "winprob", "goal8s", "chaos")


def test_artifacts_and_metrics_exist():
    for name in HEADS:
        assert (ARTIFACTS / f"{name}.txt").exists(), name
        m = json.loads((ARTIFACTS / f"{name}.metrics.json").read_text())
        assert m["head"] == name and m["test"]["ece"] >= 0 and m["data"]["matches"]["test"] > 0
        assert (ARTIFACTS / f"{name}.calibration.png").stat().st_size > 1000
    assert set(HEADS) <= set(json.loads((ARTIFACTS / "metrics.json").read_text()))


def test_missing_artifact_raises_at_start_up(tmp_path):
    for name in HEADS:
        for suffix in (".txt", ".metrics.json"):
            shutil.copy(ARTIFACTS / f"{name}{suffix}", tmp_path / f"{name}{suffix}")
    load_all(tmp_path)
    (tmp_path / "goal8s.txt").unlink()
    with pytest.raises(HeadArtifactMissing):
        load_all(tmp_path)
    with pytest.raises(HeadArtifactMissing):
        XGHead(tmp_path / "nowhere")


def test_xg_rises_as_distance_falls():
    dist = np.array([30.0, 25.0, 20.0, 16.0, 12.0, 8.0, 5.0])
    shots = pd.DataFrame({"distance_m": dist, "angle_rad": 2 * np.arctan(3.66 / dist), "body_part": 0,
                          "defenders_in_cone": 1, "keeper_line_m": 1.5, "under_pressure": 0, "control_at_shot": 0.5,
                          "penalty": 0})
    p = XGHead().predict(shots)
    assert np.all(np.diff(p) >= 0) and p[-1] > p[0] + 0.05, p


def test_win_probability_rises_with_score_difference():
    states = pd.DataFrame({"score_diff": [-2, -1, 0, 1, 2], "minute": 60.0, "period": 2, "red_card_diff": 0,
                           "xt_diff_15": 0.0, "xg_diff_15": 0.0, "chaos": 40.0})
    P = WinProbHead().predict(states)
    assert P.shape == (5, 3) and np.allclose(P.sum(axis=1), 1.0)
    assert np.all(np.diff(P[:, 0]) > 0) and np.all(np.diff(P[:, 2]) < 0), P


def test_goal8s_chaos_and_pass_shapes():
    rng = np.random.default_rng(0)
    states = pd.DataFrame(rng.uniform(0, 1, (8, len(GOAL8_FEATURES))), columns=GOAL8_FEATURES)
    states["ball_u"] = np.linspace(20, 100, 8)
    states["poss_team"] = [0, 1] * 4
    P = GoalIn8sHead().predict(states)
    assert P.shape == (8, 2) and np.all((P >= 0) & (P <= 1))
    feats = pd.DataFrame(rng.uniform(0, 1, (5, len(CHAOS_FEATURES))), columns=CHAOS_FEATURES)
    assert np.all((ChaosHead().predict(feats) >= 0) & (ChaosHead().predict(feats) <= 1))
    passes = pd.DataFrame(rng.uniform(0, 1, (5, len(PASS_FEATURES))), columns=PASS_FEATURES)
    assert PassHead().predict(passes).shape == (5,)
