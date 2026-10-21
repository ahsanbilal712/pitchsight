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
