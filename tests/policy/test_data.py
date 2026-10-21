"""Policy dataset (T-027): shapes F = 16 and G = 4, labels in range, splits disjoint by game, report written."""

import json
from pathlib import Path

import numpy as np
import pytest

from policy.data import KINDS, PASS, F, G, build_dataset

ROOT = Path(__file__).resolve().parents[2]
GRF_TINY = ROOT / "data" / "grf" / "tiny_set"
CORPUS = ROOT / "data" / "matches" / "corpus"
ARTIFACTS = ROOT / "packages" / "policy" / "artifacts"
FULL = ROOT / "data" / "grf" / "dataset"


@pytest.fixture(scope="module")
def small(tmp_path_factory):
    if not GRF_TINY.exists() or not (CORPUS / "1001" / "samples.npz").exists():
        pytest.skip("needs data/grf/tiny_set (T-012) and the Kickoff corpus (T-014)")
    out = tmp_path_factory.mktemp("dataset")
    report_before = (ARTIFACTS / "dataset_report.json").read_bytes() if (ARTIFACTS / "dataset_report.json").exists() else None
    plot_before = (ARTIFACTS / "coord_sanity.png").read_bytes() if (ARTIFACTS / "coord_sanity.png").exists() else None
    rep = build_dataset(GRF_TINY, CORPUS, out, split_seed=4242, workers=2, kickoff_limit=20)
    if report_before is not None:            # keep the full build's report and plot
        (ARTIFACTS / "dataset_report.json").write_bytes(report_before)
    if plot_before is not None:
        (ARTIFACTS / "coord_sanity.png").write_bytes(plot_before)
    return out, rep


def test_files_shapes_and_labels(small):
    out, rep = small
    for part in ("train", "val", "test"):
        with np.load(out / f"{part}.npz") as z:
            tok, ctx, kind, tgt, car = z["tokens"], z["ctx"], z["kind"], z["pass_target"], z["carry_dir"]
            assert tok.shape[1:] == (23, F) and ctx.shape[1] == G and tok.dtype == np.float16
            assert set(np.unique(kind)) <= set(range(5))
            assert np.all((tgt >= 0) == (kind == PASS)) and tgt.max() <= 10
            holder_slot = tok[:, :11, 5].argmax(axis=1)
            assert np.all(tgt[kind == PASS] != holder_slot[kind == PASS])
            assert np.all((car >= 0) == (kind == 1)) and car.max() <= 7
            assert np.allclose(tok[:, :, 5].sum(axis=1), 1.0)          # exactly one holder token
            assert np.all(tok[:, :11, 4] == 1) and np.all(tok[:, 11:22, 4] == -1) and np.all(tok[:, 22, 4] == 0)


def test_splits_disjoint_by_game(small):
    out, _ = small
    groups = {p: set(np.load(out / f"{p}.npz")["group"].tolist()) for p in ("train", "val", "test")}
    assert not (groups["train"] & groups["val"]) and not (groups["train"] & groups["test"]) and not (groups["val"] & groups["test"])
    grf = {p: {g for g in s if g >= 1_000_000} for p, s in groups.items()}
    assert sum(len(v) for v in grf.values()) == 12                     # the 12 tiny_set games


def test_report_counts(small):
    _, rep = small
    assert set(rep.counts["train"]) <= set(KINDS) and rep.samples_per_split["train"] > rep.samples_per_split["test"] > 0


def test_full_dataset_report_if_built():
    path = ARTIFACTS / "dataset_report.json"
    if not path.exists():
        pytest.skip("full dataset not built yet")
    rep = json.loads(path.read_text())
    assert rep["F"] == F and rep["G"] == G and len(rep["token_features"]) == F
    assert set(rep["counts"]["train"]) == set(KINDS)
    assert (ARTIFACTS / "coord_sanity.png").stat().st_size > 10_000
    if FULL.exists():
        assert all((FULL / f"{p}.npz").exists() for p in ("train", "val", "test"))
