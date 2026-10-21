"""Realism ranges on evaluation seeds 1-50 (T-014, TECH_PLAN 1.4).

Reads the per-seed stats that scripts/generate_corpus.py stores in data/matches/corpus/progress.json when that
corpus was built by the current engine; otherwise simulates the 50 matches itself in a process pool.
"""

import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEEDS = list(range(1, 51))


def _corpus_module():
    spec = importlib.util.spec_from_file_location("generate_corpus", ROOT / "scripts" / "generate_corpus.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _summary() -> dict:
    gc = _corpus_module()
    progress = gc.load_progress(gc.DEFAULT_OUT)
    fresh = progress.get("engine_hash") == gc.engine_hash()
    if not (fresh and all(progress["seeds"].get(str(s), {}).get("status") == "done" for s in SEEDS)):
        from multiprocessing import Pool

        progress = {"seeds": {}}
        with Pool(max(1, (os.cpu_count() or 2) - 1)) as pool:
            records = pool.map(_play, SEEDS)
        for seed, events in zip(SEEDS, records, strict=True):
            progress["seeds"][str(seed)] = {"status": "done", "stats": gc.match_stats(events)}
    return gc.summarise(progress, SEEDS)


def _play(seed: int) -> list[dict]:
    from kickoff import Engine, League
    league = League.load(ROOT / "data" / "league")
    return Engine(league, *league.fixture(seed), seed=seed).play().events


def test_realism_ranges_on_seeds_1_to_50():
    s = _summary()
    print(f"\nseeds 1-50: {s}")
    assert s["matches"] == 50
    assert 0.78 <= s["pass_completion"] <= 0.86, s
    assert 1.0 <= s["goal_per_team"] <= 1.8, s
    assert 8.0 <= s["shot_per_team"] <= 16.0, s


def test_running_distance_and_top_speeds_on_seeds_1_to_50():
    """Movement realism (added 22 Oct after the golden match showed 13.5 km per 90 and every top speed at the old
    28.1 km/h cap): outfield players cover 9.5-12.5 km per 90 and keepers 4-7 km; top speeds vary per player, and
    each match's fastest outfield player is between 30 and 37 km/h."""
    import numpy as np
    corpus = ROOT / "data" / "matches" / "corpus"
    paths = [corpus / str(s) / "tracking.npz" for s in SEEDS]
    if not all(p.exists() for p in paths):
        import pytest
        pytest.skip("needs the full-tracking evaluation seeds 1-50 (python scripts/generate_corpus.py --seeds 1..50 --full)")
    out, gk, fastest, spreads = [], [], [], []
    for p in paths:
        with np.load(p) as z:
            S = z["S"].astype(np.float64)
        dist = np.hypot(*np.diff(S[:, :22, 0:2], axis=0).transpose(2, 0, 1)).sum(0) / 1000
        top = np.hypot(S[:, :22, 2], S[:, :22, 3]).max(0) * 3.6
        outfield = np.r_[1:11, 12:22]
        out.append(dist[outfield].mean())
        gk.append(dist[[0, 11]].mean())
        fastest.append(top[outfield].max())
        spreads.append(top[outfield].std())
    print(f"\noutfield {np.mean(out):.2f} km/90, keepers {np.mean(gk):.2f} km/90, fastest per match median "
          f"{np.median(fastest):.1f} km/h, top-speed spread {np.mean(spreads):.2f} km/h")
    assert 9.5 <= np.mean(out) <= 12.5
    assert 4.0 <= np.mean(gk) <= 7.0
    assert 30.0 <= np.median(fastest) <= 37.0
    assert np.mean(spreads) > 1.0
