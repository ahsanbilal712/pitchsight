"""Golden precompute of the model calls (T-042): the stages fast_lines, tactician, narrator, panel and factcheck of
`scripts/precompute.py`, served by one pass.

The real newsroom graph runs every golden moment with a `cache.batch.BatchingClient` (calls leave in rounds: one
Vertex AI batch job per model per round, matched by custom_id) and `RecordingTools`. The Fact Checker and its
rewrites run in the graph. Every result is written under the key replay looks up, together with the evidence the
Fact Checker saw (evidence.jsonl, preloaded by the replay worker) and batches.json.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from cache.manifest import CacheManifest

ROOT = Path(__file__).resolve().parents[2]
BUDGET_USD = 2.00   # T-042 limit, raised from $1.50 by the owner on 22 Oct (no batch bucket: live calls)
NEWSROOM_STAGES = ("fast_lines", "tactician", "narrator", "panel", "factcheck")
MODEL_PRODUCERS = ("tactician", "proposer", "narrator", "fast_line", "panel")
TOOL_PRODUCERS = ("get_state", "get_pitch_control", "query_events", "player_stats")


def verdicts(bb, client) -> dict[str, bool | None]:
    """Fact Checker verdict per recorded line (its moment, branch and attempt) and per explanation (all claims)."""
    from newsroom.factcheck import verify_claims

    rows = bb.query("traces", executor="factcheck")
    out: dict[str, bool | None] = {}
    for rec in client.records.values():
        r = rec.request
        producer, moment = r.ctx.get("producer"), r.ctx.get("moment_id")
        if producer in ("narrator", "fast_line"):
            attempt = int(r.ctx.get("attempt") or 1)
            mine = [t for t in rows if t["moment_id"] == moment and t.get("attempt") == attempt
                    and (t["branch"] == "fast") == (producer == "fast_line")]
            out[r.key] = any(t["status"] == "verified" for t in mine) if mine else None
        elif producer == "tactician" and isinstance(rec.result.json, dict):
            exp = next(iter(bb.query("explanations", moment_id=moment)), None)
            out[r.key] = bool(exp) and verify_claims(exp["match_id"], exp["claims"], bb)["verified"]
    return out


def stage_newsroom(seed: int, manifest: CacheManifest, events: list[dict], window, args) -> dict:
    from blackboard import SqliteBlackboard
    from cache.batch import (
        BatchingClient,
        BatchLog,
        LiveRunner,
        RecordingTools,
        VertexBatchRunner,
        record_entries,
        run_rounds,
    )
    from cache.client import EVIDENCE_COLLECTIONS
    from mcp_server.tools_core import MatchStore
    from newsroom.executors.base import Deps
    from newsroom.graph import build_workflow
    from newsroom.worker import run_moment, start_message

    if getattr(args, "_newsroom_done", False):
        return {"ran_with": "an earlier model stage"}
    args._newsroom_done = True
    os.environ["WHYLINE_ROLLOUT_TIMEOUT_S"] = "600"          # every n = 200 rollout completes; no n = 50 fallback
    match_id = events[0]["match_id"]
    entry = manifest.find(producer="scout")
    if not entry:
        raise SystemExit("run the moments stage first (T-039)")
    moments = [json.loads(line) for line in (manifest.cache_dir / entry[0]["path"]).read_text().splitlines()
               if line.strip()]
    if getattr(args, "moments", None):
        wanted = set(args.moments.split(","))
        moments = [m for m in moments if m["moment_id"] in wanted]
    runtime = Path(getattr(args, "runtime_dir", None) or ROOT / "data" / "runtime" / "precompute")
    runtime.mkdir(parents=True, exist_ok=True)
    for f in runtime.glob(f"newsroom_{seed}.sqlite*"):
        f.unlink()
    bb = SqliteBlackboard(runtime / f"newsroom_{seed}.sqlite")
    store = MatchStore(bb, matches_dir=manifest.cache_dir.parent.parent, runtime_dir=runtime)
    store.match(match_id)                                  # events in the blackboard, as the replay preload does
    client, tools = BatchingClient(seed), RecordingTools(manifest, store)
    deps = Deps(bb=bb, llm=client, rollout=tools, store=store, mode="replay", panel_enabled=True)
    deps.state["panel_budget_s"] = None
    runner = getattr(args, "runner", None)
    if runner is None:
        if args.mode == "batch":
            bucket = getattr(args, "bucket", None) or os.environ.get("WHYLINE_BATCH_BUCKET")
            if not bucket:
                raise SystemExit("--mode batch needs --bucket gs://... or WHYLINE_BATCH_BUCKET (Vertex AI batch I/O)")
            runner = VertexBatchRunner(bucket, live=LiveRunner(budget_usd=BUDGET_USD))
        else:
            runner = LiveRunner(budget_usd=BUDGET_USD)
    for m in moments:
        bb.put("moments", m)

    async def go():
        tasks = [asyncio.create_task(run_moment(build_workflow(deps), start_message(m, "replay"))) for m in moments]
        return tasks, await run_rounds(tasks, client, tools, runner)

    tasks, jobs = asyncio.run(go())
    cues = [c for t in tasks for c in t.result()["outputs"] if isinstance(c, dict)]
    judged = verdicts(bb, client)
    if (manifest.cache_dir / "manifest.json").exists():
        # a batch run takes hours: re-read the manifest so entries other stages saved meanwhile are kept
        fresh = CacheManifest.load(manifest.cache_dir)
        manifest.data, manifest._by_key = fresh.data, fresh._by_key
    keep = [e for e in manifest.entries if not (
        e.get("producer") in MODEL_PRODUCERS + TOOL_PRODUCERS + ("evidence",)
        or (e.get("producer") == "rollout" and e["path"].startswith("counterfactuals/x_")))]
    manifest.data["entries"] = keep
    manifest._by_key = {e["key"]: e for e in keep}
    counts = record_entries(manifest, client, tools, judged, seed)
    lines = [json.dumps({**doc, "_collection": coll}, sort_keys=True) for coll in EVIDENCE_COLLECTIONS
             for doc in bb.query(coll, match_id=match_id)]
    manifest.add(CacheManifest.key(match_id, None, "evidence", "evidence@1", None, seed), "analytics",
                 ("\n".join(lines) + "\n").encode(), "evidence.jsonl", producer="evidence", version="evidence@1",
                 seed=seed)
    values = [v for v in judged.values() if v is not None]
    summary = {"moments": len(moments), "rounds": client.round, "requests": len(client.records),
               "failed": sum(1 for r in client.records.values() if r.result.error), "entries": counts,
               "cues": len(cues), "cues_verified": sum(1 for c in cues if c.get("verified")),
               "lines_verified": f"{sum(values)}/{len(values)}", "evidence_docs": len(lines),
               "cost_usd": round(sum(r.result.cost_usd for r in client.records.values()), 4)}
    BatchLog(jobs=jobs).save(manifest.cache_dir / "batches.json", client, {"summary": summary})
    bb.close()
    return summary
