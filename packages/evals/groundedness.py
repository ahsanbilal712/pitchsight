"""Groundedness, our own evaluator (TECH_PLAN 1.11 row "Groundedness", 1.14 disagreement 1; T-056).

    python -m evals.groundedness [--match-dir data/matches/4242] [--out packages/evals/out]

The golden match is replayed from its committed cache (`replay_cues`: the real newsroom graph, every model result
and rollout served by CacheClient, no model call, a temporary blackboard; nothing in the cache is written). For every
delivered cue, each number on screen (headline, body, and the `why` the drawer shows) counts as grounded when a
verified claim of the same cue shows it (the Fact Checker's own number tokens, `newsroom.factcheck._token_keys`).
Groundedness = grounded numbers / numbers. Gate: >= 0.95. 500 cues once the demo season lands (T-085); until then
every golden cue. Foundry's GroundednessEvaluator is optional (T-086).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "packages" / "evals" / "out"
GOLDEN = ROOT / "data" / "matches" / "4242"
THRESHOLD = 0.95
FIELDS = (("text", "headline"), ("text", "body"), ("explain", "why"))


def replay_cues(match_dir: Path = GOLDEN, runtime: Path | None = None) -> tuple[list[dict], list[dict]]:
    """(delivered cues, trace rows) of a replay of every cached moment; read-only on the cache."""
    from blackboard import SqliteBlackboard
    from cache.client import CacheClient, preload_evidence
    from cache.manifest import CacheManifest
    from mcp_server.tools_core import MatchStore
    from newsroom.executors.base import Deps
    from newsroom.graph import build_workflow
    from newsroom.tools import LocalTools
    from newsroom.worker import run_moment, start_message

    manifest = CacheManifest.load(match_dir / "cache")
    entry = manifest.find(producer="scout")
    moments = [json.loads(line) for line in (manifest.cache_dir / entry[0]["path"]).read_text().splitlines()
               if line.strip()]
    runtime = runtime or Path(tempfile.mkdtemp(prefix="evals_replay_"))
    bb = SqliteBlackboard(runtime / "replay.sqlite")
    store = MatchStore(bb, matches_dir=match_dir.parent, runtime_dir=runtime)
    cache = CacheClient(manifest, speed=1e9, inner_tools=LocalTools(store))
    preload_evidence(bb, manifest, store)
    deps = Deps(bb=bb, llm=cache, rollout=cache, store=store, mode="replay", panel_enabled=True)

    async def go() -> list[dict]:
        cues = []
        for m in moments:
            bb.put("moments", m)
            out = await run_moment(build_workflow(deps), start_message(m, "replay"))
            cues += [c for c in out["outputs"] if isinstance(c, dict)]
        return cues

    cues = asyncio.run(go())
    traces = bb.query("traces", match_id=manifest.data["match_id"])
    bb.close()
    return cues, traces


def score(cues: list[dict]) -> dict:
    from newsroom.factcheck import _token_keys

    total = grounded = 0
    by_kind: dict[str, list[int]] = {}
    ungrounded = []
    for cue in cues:
        allowed: set[str] = set()
        for claim in (cue.get("explain") or {}).get("claims") or []:
            if claim.get("verified"):
                allowed |= _token_keys(claim.get("text") or "")
        for part, field in FIELDS:
            text = (cue.get(part) or {}).get(field) or ""
            for tok in sorted(_token_keys(text)):
                ok = tok in allowed
                total += 1
                grounded += ok
                k = by_kind.setdefault(cue["kind"], [0, 0])
                k[0] += 1
                k[1] += ok
                if not ok:
                    ungrounded.append({"cue_id": cue["cue_id"], "kind": cue["kind"], "field": field, "token": tok,
                                       "text": text[:120]})
    rate = grounded / total if total else 1.0
    return {"groundedness": round(rate, 4), "numbers": total, "grounded": grounded, "cues": len(cues),
            "cues_verified": sum(1 for c in cues if c.get("verified")),
            "by_kind": {k: {"numbers": v[0], "grounded": v[1]} for k, v in sorted(by_kind.items())},
            "ungrounded": ungrounded[:50], "threshold": THRESHOLD, "passed": rate >= THRESHOLD}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m evals.groundedness")
    ap.add_argument("--match-dir", type=Path, default=GOLDEN)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    cues, _ = replay_cues(args.match_dir)
    res = {**score(cues), "source": f"replay of {args.match_dir.name} from its committed cache (no model call)"}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "groundedness.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("groundedness", "numbers", "cues", "passed")}))
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
