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
RECAP_STAGES = ("recap",)       # T-050: only the period-end moments, merged into the existing entries
MODEL_PRODUCERS = ("tactician", "proposer", "narrator", "fast_line", "panel", "recap")
TOOL_PRODUCERS = ("get_state", "get_pitch_control", "query_events", "player_stats")


MODEL_DIRS = ("explanations", "fast_lines", "panel", "proposals", "recaps", "failed", "tools")


def prune_orphans(manifest: CacheManifest) -> int:
    """Delete files in the model-stage directories that no manifest entry references (a replaced entry's file)."""
    used = {e["path"] for e in manifest.entries}
    gone = 0
    for d in MODEL_DIRS:
        for f in (manifest.cache_dir / d).glob("*.json") if (manifest.cache_dir / d).exists() else []:
            if str(f.relative_to(manifest.cache_dir)) not in used:
                f.unlink()
                gone += 1
    return gone


def _id_field(collection: str) -> str:
    from blackboard.ids import id_field

    return id_field(collection)


def stage_recap(seed: int, manifest: CacheManifest, events: list[dict], window, args) -> dict:
    """T-050: the half-time and full-time recaps only (the period-end moments), merged into the golden cache."""
    args.recap_only = True
    return stage_newsroom(seed, manifest, events, window, args)


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
        elif producer == "recap":
            mine = [t for t in rows if t["moment_id"] == moment and t["branch"] == "recap"]
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

    if getattr(args, "_newsroom_done", False) and not getattr(args, "recap_only", False):
        return {"ran_with": "an earlier model stage"}
    if not getattr(args, "recap_only", False):
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
    elif getattr(args, "recap_only", False):
        moments = [m for m in moments if m["kind"] == "period_end"]
    partial = bool(getattr(args, "moments", None) or getattr(args, "recap_only", False))
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
        bucket = getattr(args, "bucket", None) or os.environ.get("WHYLINE_BATCH_BUCKET")
        if args.mode == "batch" and bucket:
            runner = VertexBatchRunner(bucket, live=LiveRunner(budget_usd=BUDGET_USD))
        else:
            if args.mode == "batch":   # owner decision 22 Oct: no new GCP resources, so no batch bucket
                print("no batch bucket (--bucket / WHYLINE_BATCH_BUCKET): the model calls run live")
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
    ran = {m["moment_id"] for m in moments}
    if partial:   # replace only these moments' model entries; tool results and evidence merge by key
        keep = [e for e in manifest.entries if not (e.get("producer") in MODEL_PRODUCERS and e.get("moment_id") in ran)]
    else:
        keep = [e for e in manifest.entries if not (
            e.get("producer") in MODEL_PRODUCERS + TOOL_PRODUCERS + ("evidence",)
            or (e.get("producer") == "rollout" and e["path"].startswith("counterfactuals/x_")))]
    previous = {}
    if partial and (manifest.cache_dir / "evidence.jsonl").exists():
        for line in (manifest.cache_dir / "evidence.jsonl").read_text().splitlines():
            if line.strip():
                doc = json.loads(line)
                previous[(doc["_collection"], doc.get(_id_field(doc["_collection"])))] = doc
    manifest.data["entries"] = keep
    manifest._by_key = {e["key"]: e for e in keep}
    counts = record_entries(manifest, client, tools, judged, seed)
    for coll in EVIDENCE_COLLECTIONS:
        for doc in bb.query(coll, match_id=match_id):
            previous[(coll, doc.get(_id_field(coll)))] = {**doc, "_collection": coll}
    lines = [json.dumps(doc, sort_keys=True) for _, doc in sorted(previous.items(), key=lambda kv: str(kv[0]))]
    manifest.add(CacheManifest.key(match_id, None, "evidence", "evidence@1", None, seed), "analytics",
                 ("\n".join(lines) + "\n").encode(), "evidence.jsonl", producer="evidence", version="evidence@1",
                 seed=seed)
    values = [v for v in judged.values() if v is not None]
    summary = {"moments": len(moments), "rounds": client.round, "requests": len(client.records),
               "failed": sum(1 for r in client.records.values() if r.result.error), "entries": counts,
               "cues": len(cues), "cues_verified": sum(1 for c in cues if c.get("verified")),
               "lines_verified": f"{sum(values)}/{len(values)}", "evidence_docs": len(lines),
               "cost_usd": round(sum(r.result.cost_usd for r in client.records.values()), 4)}
    summary["orphans_pruned"] = prune_orphans(manifest)
    BatchLog(jobs=jobs).save(manifest.cache_dir / "batches.json", client,
                             {"summary" if not partial else f"summary_{'recap' if getattr(args, 'recap_only', False) else 'partial'}":
                              summary}, merge=partial)
    bb.close()
    return summary


def stage_replay_check(seed: int, manifest: CacheManifest, events: list[dict], window, args) -> dict:
    """Replay every golden moment from the cache with no model call (TECH_PLAN 1.8 replay serving) and count the
    cache misses. With --repair, close the gaps no model call is needed for: an alternative's counterfactual (or
    the engine's error for it) is simulated and cached, and a model call the golden run lost is cached as failed,
    so replay takes the fallback the golden run took. Repeats until clean (at most three passes)."""
    from blackboard import SqliteBlackboard
    from cache.batch import RECORD, BatchingClient, custom_id_for
    from cache.client import CacheClient, preload_evidence, tool_key
    from mcp_server.tools_core import MatchStore
    from newsroom.executors.base import Deps
    from newsroom.graph import build_workflow
    from newsroom.llm import CacheMiss
    from newsroom.tools import LocalTools
    from newsroom.worker import run_moment, start_message

    entry = manifest.find(producer="scout")
    moments = [json.loads(line) for line in (manifest.cache_dir / entry[0]["path"]).read_text().splitlines()
               if line.strip()]
    runtime = Path(getattr(args, "runtime_dir", None) or ROOT / "data" / "runtime" / "precompute")
    runtime.mkdir(parents=True, exist_ok=True)
    repaired: dict[str, int] = {"counterfactuals": 0, "engine_errors": 0, "failed_model_calls": 0}
    passes = []
    for _ in range(3 if getattr(args, "repair", False) else 1):
        for f in runtime.glob(f"replay_{seed}.sqlite*"):
            f.unlink()
        bb = SqliteBlackboard(runtime / f"replay_{seed}.sqlite")
        store = MatchStore(bb, matches_dir=manifest.cache_dir.parent.parent, runtime_dir=runtime)
        sims, models = [], []

        class Probe(CacheClient):
            async def complete(self, role, messages, tools=None, **ctx):
                try:
                    return await super().complete(role, messages, tools, **ctx)
                except CacheMiss:
                    self.model_misses.append((role, messages, ctx))
                    raise

            async def call(self, name, args_):
                out = await super().call(name, args_)
                if isinstance(out, dict) and out.get("code") == "cache_miss":
                    self.sim_misses.append((name, args_))
                return out

        cache = Probe(manifest, speed=1e9, inner_tools=LocalTools(store))
        cache.sim_misses, cache.model_misses = sims, models
        preload_evidence(bb, manifest, store)
        deps = Deps(bb=bb, llm=cache, rollout=cache, store=store, mode="replay", panel_enabled=True)

        async def go(deps=deps, bb=bb):
            cues = []
            for m in moments:
                bb.put("moments", m)
                out = await run_moment(build_workflow(deps), start_message(m, "replay"))
                cues += [c for c in out["outputs"] if isinstance(c, dict)]
            return cues

        cues = asyncio.run(go())
        passes.append({"cues": len(cues), "verified": sum(1 for c in cues if c.get("verified")),
                       "templates": sum(1 for c in cues if c["provenance"]["model"] == "template"),
                       "counterfactual_misses": len(sims), "model_misses": len(models)})
        bb.close()
        if not (sims or models) or not getattr(args, "repair", False):
            break
        local = LocalTools(MatchStore(SqliteBlackboard(runtime / f"repair_{seed}.sqlite"),
                                      matches_dir=manifest.cache_dir.parent.parent, runtime_dir=runtime))
        for name, a in {json.dumps(x, sort_keys=True): x for x in sims}.values():
            out = asyncio.run(local.call(name, a))
            if isinstance(out, dict) and "counterfactual_id" in out:
                alt = out["alternative"]
                key = CacheManifest.key(out["match_id"], out.get("moment_id"), "rollout", f"rollout@{out['engine']}",
                                        out["engine"], seed) + f"/{alt['kind']}-{alt.get('target') or 'none'}/{out['t_ms']}"
                manifest.add(key, "counterfactual", out, f"counterfactuals/x_r{custom_id_for(key)[2:14]}.json",
                             moment_id=out.get("moment_id"), producer="rollout", version=f"rollout@{out['engine']}",
                             model=out["engine"], seed=seed, simulated_latency_ms=1200)
                repaired["counterfactuals"] += 1
            else:
                key = tool_key(a["match_id"], name, a, seed)
                manifest.add(key, "analytics", {**RECORD, "record": "tool_result", "result": out},
                             f"tools/{custom_id_for(key)}.json", producer=name, seed=seed, simulated_latency_ms=50)
                repaired["engine_errors"] += 1
        batcher = BatchingClient(seed)
        for role, messages, ctx in models:
            req = batcher.request(role, messages, **ctx)
            if manifest.get(req.key) is None:
                producer = ctx.get("producer") or role
                manifest.add(req.key, "fast_line" if producer in ("narrator", "fast_line") else "analytics",
                             {**RECORD, "record": "model_result", "error": "no result in the golden run (the call failed)",
                              "verified": None},
                             f"failed/{req.custom_id}.json", moment_id=ctx.get("moment_id"), producer=producer,
                             version=req.key.split("/")[2], model=req.model, seed=seed, simulated_latency_ms=2000)
                repaired["failed_model_calls"] += 1
        manifest.save()
    return {"passes": passes, "repaired": repaired, "clean": passes[-1]["counterfactual_misses"] == 0
            and passes[-1]["model_misses"] == 0}


def stage_cue_stream(seed: int, manifest: CacheManifest, events: list[dict], window, args) -> dict:
    """T-057: cache the full cue stream (every delivered cue, each recap held for the producer, the explanations
    they cite) so replay screens and checks need no model."""
    from cache.review import build_cue_stream

    return build_cue_stream(manifest)
