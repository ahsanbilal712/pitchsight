"""MomentEncoder: cluster purity vs the hidden match regime >= 0.6, six named clusters, a 64-d code, and
similar_moments returning golden-season neighbours from other matches."""

import json

import numpy as np
import pytest

from blackboard import SqliteBlackboard
from heads.models import ARTIFACTS
from heads.moment_encoder import K, MomentEncoder
from mcp_server.tools_core import MatchStore
from mcp_server.tools_similar import similar_moments


def test_purity_and_names():
    m = json.loads((ARTIFACTS / "metrics_encoder.json").read_text())
    print(f"\npurity test {m['purity_test']} (train {m['purity_train']}, majority {m['majority_label_rate_test']})")
    assert m["purity_test"] >= 0.6
    c = json.loads((ARTIFACTS / "clusters.json").read_text())
    assert len(c["names"]) == K and len(set(c["names"])) == K
    assert (c["naming"].get("cost_usd") or 0) <= 0.05


def test_encode_and_phase():
    enc = MomentEncoder()
    rng = np.random.default_rng(0)
    z = enc.encode(rng.uniform(0, 1, (34, 53)), rng.uniform(0, 1, 12))
    assert z.shape == (64,) and np.isfinite(z).all()
    assert enc.phase(z) in enc.names


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    d = tmp_path_factory.mktemp("similar")
    return MatchStore(SqliteBlackboard(d / "bb.sqlite"), runtime_dir=d)


def test_similar_moments_from_other_matches(store):
    out = similar_moments(store, "m_4242", 1_874_000, k=3)
    assert len(out) == 3
    assert all(r["match_id"] != "m_4242" and r["phase"] for r in out)
    assert out[0]["distance"] <= out[1]["distance"] <= out[2]["distance"]
    assert out[0]["query"]["phase"]
