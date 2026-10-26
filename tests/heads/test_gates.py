"""Outcome heads meet their gates; metrics record data size and split seeds."""

import json
import shutil

import pytest

from heads.gates import GATES, GateFailed, check
from heads.models import ARTIFACTS


def test_committed_heads_pass_the_gates():
    res = check(ARTIFACTS)
    for head, metrics in res.items():
        print(f"\n{head}: " + ", ".join(f"{m} {r['value']:.4f}" for m, r in metrics.items()))
    assert set(res) == set(GATES)


def test_metrics_record_data_size_and_split():
    for head in GATES:
        m = json.loads((ARTIFACTS / f"{head}.metrics.json").read_text())
        assert m["data"]["split_seed"] == 4242 and m["data"]["rows"]["train"] > 0
        assert sum(m["data"]["matches"].values()) >= 1900, "trained on the full 2,000-match corpus"
        assert m["data"]["test_seeds"] and m["data"]["val_seeds"]


def test_a_missed_gate_names_the_head_and_number(tmp_path):
    for f in ARTIFACTS.glob("*.metrics.json"):
        shutil.copy(f, tmp_path / f.name)
    m = json.loads((tmp_path / "xg.metrics.json").read_text())
    m["test"]["ece"] = 0.05
    (tmp_path / "xg.metrics.json").write_text(json.dumps(m))
    with pytest.raises(GateFailed, match=r"xg ece 0\.0500"):
        check(tmp_path)
