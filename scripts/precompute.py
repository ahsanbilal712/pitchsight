"""Golden-match precompute into the replay cache (TECH_PLAN 1.8 "Precompute", ADR-003).

    python scripts/precompute.py --seed 4242 --mode batch --stages fourth_official
    python scripts/precompute.py --seed 4242 --mode batch --stages analytics,moments,counterfactuals   (T-039)

Every stage writes files under data/matches/<seed>/cache/ and indexes them in cache/manifest.json (CacheManifest,
T-038) with their SHA-256. Stages are idempotent: re-running replaces their entries. `--mode live` is accepted for
the CLI contract (later stages call models); the code-only stages behave the same in both modes. Other tickets add
stages to STAGES: analytics, moments, counterfactuals (T-039), model calls (T-042), oracle (T-046), dugout (T-047),
decision_index (T-048), hand review (T-057).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from cache.manifest import CacheManifest  # noqa: E402

RULES_VERSION = "rules1"


def load_match(seed: int):
    from physics.window import TrackingWindow
    d = ROOT / "data" / "matches" / str(seed)
    events = [json.loads(line) for line in (d / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    return d, events, TrackingWindow.load(d)


def open_manifest(match_dir: Path) -> CacheManifest:
    cache = match_dir / "cache"
    if (cache / "manifest.json").exists():
        return CacheManifest.load(cache)
    return CacheManifest.new(match_dir, cache)


# ---------------------------------------------------------------------------------------------------- stages
def stage_fourth_official(seed: int, manifest: CacheManifest, events: list[dict], window, args) -> dict:
    """A referee_line cue for every offside, foul and card (T-049); keyed by the referee event id."""
    from newsroom.executors.fourth_official import REFEREE, rule_event

    match_id = events[0]["match_id"]
    stale = [e["key"] for e in manifest.entries if e.get("producer") == "fourth_official"]
    manifest.data["entries"] = [e for e in manifest.entries if e["key"] not in stale]
    counts, missing = {k: 0 for k in REFEREE}, []
    for ev in events:
        if ev["type"] not in REFEREE:
            continue
        cue = rule_event(ev, events, window, match_id)
        if cue is None:
            missing.append(ev["id"])
            continue
        key = CacheManifest.key(match_id, ev["id"], "fourth_official", RULES_VERSION, None, seed)
        manifest.add(key, "fourth_official", cue, f"fourth_official/{cue['cue_id']}.json", moment_id=None,
                     producer="fourth_official", version=RULES_VERSION, model=None, seed=seed,
                     simulated_latency_ms=5)
        counts[ev["type"]] += 1
    if missing:
        raise SystemExit(f"fourth_official: could not rebuild the geometry for {missing}")
    return counts


STAGES = {"fourth_official": stage_fourth_official}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="scripts/precompute.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--mode", choices=("batch", "live"), default="batch")
    ap.add_argument("--stages", required=True, help=f"comma list of {', '.join(STAGES)}")
    ap.add_argument("--hand-review", type=int, default=0, help="top K moments for hand review (T-057)")
    args = ap.parse_args(argv)
    stages = [s for s in args.stages.split(",") if s]
    unknown = [s for s in stages if s not in STAGES]
    if unknown:
        ap.error(f"unknown stage(s) {unknown}; available: {sorted(STAGES)}")
    match_dir, events, window = load_match(args.seed)
    manifest = open_manifest(match_dir)
    for name in stages:
        started = time.perf_counter()
        result = STAGES[name](args.seed, manifest, events, window, args)
        manifest.save()
        print(f"{name}: {json.dumps(result)} in {time.perf_counter() - started:.1f} s")
    problems = manifest.problems(match_dir)
    if problems:
        print("manifest problems:", problems[:5])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
