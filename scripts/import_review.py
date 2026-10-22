"""Import hand-reviewed explanations and lines into the golden cache (T-057, TECH_PLAN 1.7).

Usage: python scripts/import_review.py review/ [--seed 4242]

Each review/<moment_id>.md holds a JSON block {moment_id, explanation, line}. Both are checked by the Fact Checker
against the golden match's evidence; a passing review replaces the cached Tactician and Narrator results of that
moment (hand_reviewed: true) and is appended to packages/newsroom/prompts/fewshot/{tactician,narrator}.jsonl.
Exit 1 if any review is refused (the reasons are printed).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from cache.manifest import CacheManifest  # noqa: E402
from cache.review import import_review  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("review_dir", type=Path)
    ap.add_argument("--seed", type=int, default=4242)
    args = ap.parse_args()
    manifest = CacheManifest.load(ROOT / "data" / "matches" / str(args.seed) / "cache")
    out = import_review(manifest, args.review_dir)
    manifest.save()
    flagged = sum(1 for e in manifest.entries if e.get("hand_reviewed"))
    print(f"import_review: {len(out['imported'])} imported, {len(out['refused'])} refused, "
          f"{flagged} cache entries hand_reviewed")
    for name, why in out["refused"].items():
        print(f"  refused {name}: {json.dumps(why)[:300]}")
    return 1 if out["refused"] else 0


if __name__ == "__main__":
    sys.exit(main())
