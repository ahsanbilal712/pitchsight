"""Every cached cue's evidence resolves (M1 item 2).

Usage: python scripts/check_cue_evidence.py --seed 4242

For every cue in data/matches/<seed>/cache (kind "cue"): each claim's evidence ids, the explanation id and the
counterfactual id must resolve to a golden document: events (events.jsonl), counterfactuals and pitch-control
snapshots and facts (the cache's counterfactual files and evidence.jsonl), explanations (the cached ex_ documents).
Every cue must be verified. Exit 1 on any unresolved id or unverified cue.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from cache.manifest import CacheManifest  # noqa: E402


def known_ids(manifest: CacheManifest, match_dir: Path) -> set[str]:
    ids = {json.loads(line)["id"] for line in (match_dir / "events.jsonl").read_text().splitlines() if line.strip()}
    for e in manifest.find(kind="counterfactual"):
        ids.add(manifest.read(e)["counterfactual_id"])
    for e in manifest.find(producer="evidence"):
        for line in (manifest.cache_dir / e["path"]).read_text().splitlines():
            if line.strip():
                doc = json.loads(line)
                ids.add(doc.get("counterfactual_id") or doc.get("snapshot_id") or doc.get("fact_id") or doc.get("id"))
    for e in manifest.find(kind="explanation"):
        if e["path"].startswith("explanations/ex_"):
            ids.add(manifest.read(e)["explanation_id"])
    return ids


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=4242)
    args = ap.parse_args()
    match_dir = ROOT / "data" / "matches" / str(args.seed)
    manifest = CacheManifest.load(match_dir / "cache")
    ids = known_ids(manifest, match_dir)
    cues = [manifest.read(e) for e in manifest.find(kind="cue")]
    problems = []
    for cue in cues:
        cid = cue["cue_id"]
        if not cue.get("verified"):
            problems.append(f"{cid}: not verified")
        ex = cue.get("explain", {})
        for field in ("explanation_id", "counterfactual_id"):
            if ex.get(field) and ex[field] not in ids:
                problems.append(f"{cid}: {field} {ex[field]} does not resolve")
        for claim in ex.get("claims", []):
            for eid in claim.get("evidence_ids", []):
                if eid not in ids:
                    problems.append(f"{cid}: claim {claim.get('text')!r} cites {eid}, which does not resolve")
    if not cues:
        problems.append("no cached cues (run scripts/precompute.py --stages cue_stream)")
    for p in problems[:50]:
        print("  " + p)
    n_claims = sum(len(c.get("explain", {}).get("claims", [])) for c in cues)
    print(f"check_cue_evidence: {'FAIL' if problems else 'OK'} ({len(cues)} cues, {n_claims} claims, "
          f"{len(problems)} problems)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
