"""Kickoff training corpus generator (T-014).

    python scripts/generate_corpus.py --seeds 1..50 --full            # evaluation seeds, full tracking
    python scripts/generate_corpus.py --seeds 51..350                 # calibration hold-out, events + truth
    python scripts/generate_corpus.py --seeds 1001..3000              # training seeds, events + truth + samples
    python scripts/generate_corpus.py --status

One seed per task in a multiprocessing pool; finished seeds are skipped, so an interrupted run resumes where it
stopped. Each seed writes into data/matches/corpus/<seed>/ and the run records per-seed status, match stats and
the engine hash in progress.json (written atomically after every finished seed).

Storage per seed range (seed convention in TASKS.md):
  1-50       events.jsonl, tracking.npz (10 Hz), truth.json
  51-350     events.jsonl.gz, truth.json
  1001-3000  events.jsonl.gz, truth.json, samples.npz: the state at every on-ball decision (the tick before a
             pass, shot or clearance is kicked) and at 1 Hz. S is float16 (about 3 cm at 100 m); a full-tracking
             corpus would be about 30 GB, this one is about 3 GB.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import sys
import time
import zipfile
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from kickoff import Engine, League  # noqa: E402
from kickoff.record import ZIP_DATE, dumps_line, write_match, write_truth  # noqa: E402

DEFAULT_OUT = ROOT / "data" / "matches" / "corpus"
LEAGUE_DIR = ROOT / "data" / "league"
DECISION_TYPES = ("pass", "shot", "clearance")
SAMPLE_ORDER = ("t_ms", "period", "S", "ball_z", "holder", "possession", "score", "is_decision", "player_ids")


def engine_hash() -> str:
    """Behavioural fingerprint of the engine: three minutes of seed 4242 (events and tracking). A refactor that
    keeps the simulation identical keeps the hash; any change to what the engine generates marks the corpus stale."""
    league = League.load(LEAGUE_DIR)
    record = Engine(league, *league.fixture(4242), seed=4242).play(until_ms=180_000)
    h = hashlib.sha256("".join(dumps_line(e) for e in record.events).encode("utf-8"))
    h.update(np.ascontiguousarray(record.tracking["S"]).tobytes())
    return h.hexdigest()[:16]


def parse_seeds(text: str) -> list[int]:
    seeds: list[int] = []
    for part in text.split(","):
        if ".." in part:
            a, b = part.split("..")
            seeds.extend(range(int(a), int(b) + 1))
        elif part:
            seeds.append(int(part))
    return seeds


def storage_for(seed: int, full: bool) -> str:
    if full or 1 <= seed <= 50:
        return "full"
    if 51 <= seed <= 350:
        return "events"
    return "samples"


def match_stats(events: list[dict]) -> dict:
    """Per-team counts the realism test reads (TECH_PLAN 1.4 ranges)."""
    c: Counter = Counter()
    for e in events:
        if e["team"] not in ("home", "away"):
            continue
        c[(e["type"], e["team"])] += 1
        if e["type"] == "pass" and e["outcome"] == "complete":
            c[("pass_complete", e["team"])] += 1
    keys = ("pass", "pass_complete", "shot", "goal", "offside", "foul", "card")
    return {side: {k: int(c[(k, side)]) for k in keys} for side in ("home", "away")}


def sample_frames(tracking: dict[str, np.ndarray], events: list[dict]) -> dict[str, np.ndarray]:
    """Frames at 1 Hz plus the tick before every pass, shot and clearance (the state the decision saw)."""
    t = tracking["t_ms"]
    decision_t = {int(e["t_ms"]) - 100 for e in events if e["type"] in DECISION_TYPES}
    is_decision = np.isin(t, np.fromiter(decision_t, dtype=np.int64))
    keep = np.flatnonzero((t % 1000 == 0) | is_decision)
    score = np.zeros((len(t), 2), dtype=np.int16)
    for e in events:
        if e["type"] == "goal":
            side = 0 if e["team"] == "home" else 1
            score[np.searchsorted(t, e["t_ms"]):, side] += 1
    return {
        "t_ms": t[keep], "period": tracking["period"][keep], "S": tracking["S"][keep].astype(np.float16),
        "ball_z": tracking["ball_z"][keep].astype(np.float16), "holder": tracking["holder"][keep],
        "possession": tracking["possession"][keep], "score": score[keep], "is_decision": is_decision[keep],
        "player_ids": tracking["player_ids"],
    }


def write_npz(arrays: dict[str, np.ndarray], path: Path, order: tuple[str, ...]) -> None:
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for name in order:
            buf = io.BytesIO()
            np.lib.format.write_array(buf, np.ascontiguousarray(arrays[name]), allow_pickle=False)
            info = zipfile.ZipInfo(f"{name}.npy", date_time=ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, buf.getvalue(), compresslevel=6)
    tmp.replace(path)


def run_seed(args: tuple[int, str, str]) -> tuple[int, dict]:
    seed, out_dir, storage = args
    league = League.load(LEAGUE_DIR)
    home, away = league.fixture(seed)
    started = time.perf_counter()
    record = Engine(league, home, away, seed=seed).play()
    out = Path(out_dir) / str(seed)
    out.mkdir(parents=True, exist_ok=True)
    if storage == "full":
        write_match(record, out)
    else:
        with gzip.GzipFile(out / "events.jsonl.gz", "wb", mtime=0) as gz:
            gz.write("".join(dumps_line(e) for e in record.events).encode("utf-8"))
        write_truth(record.truth, out / "truth.json")
        if storage == "samples":
            write_npz(sample_frames(record.tracking, record.events), out / "samples.npz", SAMPLE_ORDER)
    stats = match_stats(record.events)
    return seed, {"status": "done", "storage": storage, "home": home, "away": away, "stats": stats,
                  "seconds": round(time.perf_counter() - started, 1)}


def load_progress(out: Path) -> dict:
    path = out / "progress.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"engine_hash": engine_hash(), "seeds": {}}


def save_progress(out: Path, progress: dict) -> None:
    tmp = out / "progress.json.tmp"
    tmp.write_text(json.dumps(progress, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    tmp.replace(out / "progress.json")


def generate(seeds: list[int], out: Path, workers: int, full: bool) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    progress = load_progress(out)
    current = engine_hash()
    if progress.get("engine_hash") != current:
        print(f"engine changed ({progress.get('engine_hash')} -> {current}); regenerating every requested seed")
        progress = {"engine_hash": current, "seeds": {}}
    todo = [s for s in seeds if progress["seeds"].get(str(s), {}).get("status") != "done"]
    print(f"{len(seeds) - len(todo)} of {len(seeds)} seeds already done; {len(todo)} to go with {workers} workers")
    started = time.perf_counter()
    with Pool(workers) as pool:
        for i, (seed, result) in enumerate(pool.imap_unordered(
                run_seed, [(s, str(out), storage_for(s, full)) for s in todo]), 1):
            progress["seeds"][str(seed)] = result
            save_progress(out, progress)
            if i % 25 == 0 or i == len(todo):
                rate = i / (time.perf_counter() - started)
                print(f"  {i}/{len(todo)} done, {rate * 60:.1f} matches/min, eta {(len(todo) - i) / rate / 60:.1f} min",
                      flush=True)
    return progress


def summarise(progress: dict, seeds: list[int]) -> dict:
    """Mean per-team realism numbers over the given seeds (only seeds that are done)."""
    tot: Counter = Counter()
    n = 0
    for s in seeds:
        entry = progress["seeds"].get(str(s))
        if not entry or entry.get("status") != "done":
            continue
        for side in ("home", "away"):
            tot.update(entry["stats"][side])
            n += 1
    if n == 0:
        return {"teams": 0}
    return {"teams": n, "matches": n // 2, "pass_completion": tot["pass_complete"] / max(tot["pass"], 1),
            **{f"{k}_per_team": tot[k] / n for k in ("pass", "shot", "goal", "offside", "foul", "card")}}


def status(out: Path) -> int:
    progress = load_progress(out)
    done = {int(s) for s, e in progress["seeds"].items() if e.get("status") == "done"}
    stale = progress.get("engine_hash") != engine_hash()
    ranges = (("evaluation 1-50", range(1, 51)), ("calibration 51-350", range(51, 351)),
              ("training 1001-3000", range(1001, 3001)))
    print(f"corpus {out}  engine {progress.get('engine_hash')}{'  STALE (engine changed)' if stale else ''}")
    for name, rng in ranges:
        print(f"  {name:20s} {len(done & set(rng)):5d} / {len(rng)}")
    summary = summarise(progress, list(range(1, 51)))
    if summary["teams"]:
        print("  realism seeds 1-50: " + ", ".join(f"{k} {v:.3f}" if isinstance(v, float) else f"{k} {v}"
                                                  for k, v in summary.items()))
    return 1 if stale else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", default=None, help="e.g. 1..50 or 1001..3000 or 1,2,3")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--full", action="store_true", help="store full 10 Hz tracking for every seed")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args(argv)
    if args.status:
        return status(args.out)
    if not args.seeds:
        ap.error("--seeds or --status is required")
    progress = generate(parse_seeds(args.seeds), args.out, args.workers, args.full)
    summary = summarise(progress, parse_seeds(args.seeds))
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
