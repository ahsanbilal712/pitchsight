"""Golden precompute of model calls (TECH_PLAN 1.8 "Precompute" steps 4, 5, 7; T-042).

The newsroom workflow itself is the source of every request: each golden moment runs through the real graph with
a `BatchingClient` as its LLM client and a `RecordingTools` as its tool client. A model call does not go out at
once: it parks until every workflow is waiting on a model, then all parked calls leave together as one batch per
model (a "round": proposers, tacticians, narrators, rewrites, pundit turns, chairs) and come back matched by
`custom_id`, never by position. Because the executors make the same calls with the same context in replay, every
recorded result lands under exactly the key `CacheClient` looks up.

Runners:
    VertexBatchRunner   Vertex AI batch prediction (JSONL in Cloud Storage, 0.5x price); requests carry the
                        custom_id as a label; after `max_wait_s` (2 h) the rest finishes live, recorded as such.
    LiveRunner          the same requests as live calls through LiveClient (SpendGuard, hedging).
    FakeRunner          tests.

Golden roles: the live Tactician and pundits map to `tactician_golden` and `panel_pundit_golden` (gemini-4-argon);
Flash roles stay as they are. Every response is recorded through SpendGuard (`batch=True` for batch results).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cache.client import PRODUCER_BY_ROLE, entry_version, tool_key
from cache.manifest import CacheManifest

log = logging.getLogger("whyline.batch")

GOLDEN_ROLES = {"tactician_live": "tactician_golden", "panel_pundit": "panel_pundit_golden", "recap_live": "recap"}
# replay waits this long before serving (TECH_PLAN 1.8): the measured live latency of the live role (T-032, T-041)
LIVE_LATENCY_MS = {"recap": 20000, "proposer": 2300, "tactician": 3700, "narrator": 2100, "fast_line": 2100, "panel_pundit": 3800,
                   "panel_chair": 2000}
CUSTOM_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
RECORD = {"$schema": "model_cache.schema.json", "schema_version": "1.0.0"}   # schemas/model_cache.schema.json


def custom_id_for(key: str) -> str:
    """Letters, digits, `_`, `-`, at most 64 characters: a hash of the cache key."""
    cid = "r_" + hashlib.sha256(key.encode()).hexdigest()[:40]
    assert CUSTOM_ID.match(cid)
    return cid


@dataclass
class BatchRequest:
    custom_id: str
    key: str
    live_role: str
    role: str               # the role whose model answers (golden mapping applied)
    model: str
    messages: list[dict]
    schema: dict | None
    max_tokens: int | None
    thinking: str | None
    ctx: dict
    round: int = 0


@dataclass
class BatchResult:
    text: str
    json: Any
    tokens_in: int
    tokens_out: int
    cost_usd: float
    via: str                 # batch | live | fake
    batch_id: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------------------------------- Vertex format

def to_vertex_request(req: BatchRequest) -> dict:
    """One Vertex AI batch line: a GenerateContentRequest with the custom_id as a label."""
    system = "\n\n".join(m["content"] for m in req.messages if m["role"] == "system")
    contents = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                for m in req.messages if m["role"] != "system"]
    gen: dict[str, Any] = {}
    if req.max_tokens:
        gen["maxOutputTokens"] = req.max_tokens
    if req.schema is not None:
        gen["responseMimeType"] = "application/json"
        gen["responseJsonSchema"] = req.schema
    if req.thinking == "none":
        gen["thinkingConfig"] = {"thinkingBudget": 0}
    elif req.thinking:
        gen["thinkingConfig"] = {"thinkingLevel": req.thinking.upper()}
    body: dict[str, Any] = {"contents": contents, "generationConfig": gen, "labels": {"custom_id": req.custom_id}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    return {"request": body}


def parse_vertex_line(line: dict) -> tuple[str | None, dict]:
    """(custom_id, {text, tokens_in, tokens_out, error}) from one Vertex output line."""
    cid = ((line.get("request") or {}).get("labels") or {}).get("custom_id")
    resp = line.get("response") or {}
    if not resp or line.get("status"):
        return cid, {"error": str(line.get("status") or "no response")}
    parts = (((resp.get("candidates") or [{}])[0]).get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    u = resp.get("usageMetadata") or {}
    return cid, {"text": text, "tokens_in": int(u.get("promptTokenCount") or 0),
                 "tokens_out": int(u.get("candidatesTokenCount") or 0) + int(u.get("thoughtsTokenCount") or 0)}


def _parse_json(text: str):
    from newsroom.llm import parse_json

    try:
        return parse_json(text)
    except (json.JSONDecodeError, ValueError):
        return None


# ---------------------------------------------------------------------------------------------------- runners

class FakeRunner:
    """Tests: `fn(request) -> dict` gives the parsed JSON each request returns."""

    def __init__(self, fn: Callable[[BatchRequest], Any]) -> None:
        self.fn = fn
        self.jobs: list[list[str]] = []

    async def run(self, requests: list[BatchRequest]) -> tuple[dict[str, BatchResult], list[dict]]:
        self.jobs.append([r.custom_id for r in requests])
        out = {}
        for r in reversed(requests):            # deliberately out of order: results are matched by custom_id
            body = self.fn(r)
            out[r.custom_id] = BatchResult(json.dumps(body), body, 0, 0, 0.0, "fake")
        return out, [{"job": f"fake_{len(self.jobs)}", "requests": len(requests), "via": "fake"}]


class LiveRunner:
    """Live calls through LiveClient (SpendGuard records each), `concurrency` at a time."""

    def __init__(self, client=None, concurrency: int = 8, budget_usd: float | None = None) -> None:
        from newsroom.llm import LiveClient

        self.client = client or LiveClient(mode="precompute")
        self.sem = asyncio.Semaphore(concurrency)
        self.budget_usd = budget_usd          # the ticket's limit: no call starts once this much is spent
        guard = getattr(self.client, "guard", None)
        self._ledger_start = guard.total if guard is not None else None

    def spent(self) -> float:
        """Ledger spend since this runner started, worst-case rows for abandoned calls included."""
        guard = getattr(self.client, "guard", None)
        return 0.0 if guard is None or self._ledger_start is None else guard.total - self._ledger_start

    async def one(self, r: BatchRequest) -> BatchResult:
        from newsroom.llm import LLMError

        async with self.sem:
            if self.budget_usd is not None and self.spent() >= self.budget_usd:
                return BatchResult("", None, 0, 0, 0.0, "live", error=f"precompute budget ${self.budget_usd:.2f} spent")
            try:
                res = await self.client.complete(r.role, r.messages, None, match_id=r.ctx.get("match_id"),
                                                 schema=r.schema, timeout_s=120, max_tool_rounds=0,
                                                 hedge_after_s=None)   # no viewer waiting: no duplicate requests
            except LLMError as exc:
                return BatchResult("", None, 0, 0, 0.0, "live", error=str(exc))
            except Exception as exc:  # SpendCapReached: a failed request, never a crashed run
                return BatchResult("", None, 0, 0, 0.0, "live", error=f"{type(exc).__name__}: {exc}")
            return BatchResult(res["text"], res["json"], res["tokens_in"], res["tokens_out"], res["cost_usd"], "live")

    async def run(self, requests: list[BatchRequest]) -> tuple[dict[str, BatchResult], list[dict]]:
        t0 = time.time()
        results = await asyncio.gather(*(self.one(r) for r in requests))
        out = {r.custom_id: res for r, res in zip(requests, results, strict=True)}
        return out, [{"job": None, "requests": len(requests), "via": "live", "seconds": round(time.time() - t0, 1)}]


class VertexBatchRunner:
    """Vertex AI batch prediction, one job per model per round. Input and output live under
    gs://<bucket>/<prefix>/<job>/; a job not finished after `max_wait_s` is cancelled and its requests run live."""

    def __init__(self, bucket: str, guard=None, prefix: str = "whyline/precompute", poll_s: float = 30.0,
                 max_wait_s: float = 7200.0, live: LiveRunner | None = None) -> None:
        from dotenv import load_dotenv

        from newsroom.config import ROOT

        load_dotenv(ROOT / ".env")
        if guard is None:
            from api.spend import SpendGuard

            guard = SpendGuard()
        self.bucket, self.prefix, self.guard = bucket.removeprefix("gs://").rstrip("/"), prefix, guard
        self.poll_s, self.max_wait_s = poll_s, max_wait_s
        self.live = live
        from google import genai

        self.sdk = genai.Client(vertexai=True, project=os.environ["GOOGLE_CLOUD_PROJECT"],
                                location=os.environ.get("GOOGLE_CLOUD_BATCH_LOCATION", "us-central1"))

    def _gs(self, *parts: str) -> str:
        return "gs://" + "/".join([self.bucket, self.prefix, *parts])

    async def run(self, requests: list[BatchRequest]) -> tuple[dict[str, BatchResult], list[dict]]:
        by_model: dict[str, list[BatchRequest]] = {}
        for r in requests:
            by_model.setdefault(r.model, []).append(r)
        jobs = await asyncio.gather(*(self._job(model, reqs) for model, reqs in by_model.items()))
        out: dict[str, BatchResult] = {}
        records = []
        for results, record in jobs:
            out.update(results)
            records.append(record)
        return out, records

    async def _job(self, model: str, reqs: list[BatchRequest]) -> tuple[dict[str, BatchResult], dict]:
        name = f"{time.strftime('%Y%m%dT%H%M%S')}_{model}_{len(reqs)}"
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "input.jsonl"
            src.write_text("".join(json.dumps(to_vertex_request(r)) + "\n" for r in reqs))
            await asyncio.to_thread(subprocess.run, ["gcloud", "storage", "cp", str(src), self._gs(name, "input.jsonl")],
                                    check=True, capture_output=True)
        from google.genai import types

        job = await asyncio.to_thread(self.sdk.batches.create, model=model, src=self._gs(name, "input.jsonl"),
                                      config=types.CreateBatchJobConfig(dest=self._gs(name, "output"),
                                                                        display_name=f"whyline-{name}"))
        record = {"job": job.name, "model": model, "requests": len(reqs), "via": "batch", "submitted": time.time()}
        started = time.time()
        state = str(job.state)
        while not any(s in state for s in ("SUCCEEDED", "FAILED", "CANCELLED", "EXPIRED", "PARTIALLY")):
            if time.time() - started > self.max_wait_s:
                await asyncio.to_thread(self.sdk.batches.cancel, name=job.name)
                record["state"] = "timed_out_cancelled"
                break
            await asyncio.sleep(self.poll_s)
            job = await asyncio.to_thread(self.sdk.batches.get, name=job.name)
            state = str(job.state)
        record.setdefault("state", state)
        record["seconds"] = round(time.time() - started, 1)
        results: dict[str, BatchResult] = {}
        if "SUCCEEDED" in state or "PARTIALLY" in state:
            listing = await asyncio.to_thread(subprocess.run, ["gcloud", "storage", "ls", "-r",
                                                               self._gs(name, "output")],
                                              capture_output=True, text=True)
            for uri in [u for u in listing.stdout.split() if u.endswith(".jsonl")]:
                cat = await asyncio.to_thread(subprocess.run, ["gcloud", "storage", "cat", uri], capture_output=True,
                                              text=True, check=True)
                for raw in cat.stdout.splitlines():
                    if not raw.strip():
                        continue
                    cid, parsed = parse_vertex_line(json.loads(raw))
                    if cid is None or "error" in parsed:
                        continue
                    req = next(r for r in reqs if r.custom_id == cid)
                    row = self.guard.record(req.live_role, model, parsed["tokens_in"], parsed["tokens_out"],
                                            req.ctx.get("match_id"), "batch", batch=True)
                    results[cid] = BatchResult(parsed["text"], _parse_json(parsed["text"]), parsed["tokens_in"],
                                               parsed["tokens_out"], row["cost_usd"], "batch", batch_id=job.name)
        missing = [r for r in reqs if r.custom_id not in results]
        if missing and self.live is not None:   # the brief: a batch not ended after 2 h finishes live
            live, live_records = await self.live.run(missing)
            results.update(live)
            record["finished_live"] = len(missing)
        record["answered"] = len(results)
        return results, record


# ---------------------------------------------------------------------------------------------------- clients

@dataclass
class Recorded:
    request: BatchRequest
    result: BatchResult
    round: int


class BatchingClient:
    """An LLMClient whose calls park until `flush()`; results are recorded for the manifest."""

    def __init__(self, seed: int) -> None:
        self.seed = seed
        self.pending: list[tuple[BatchRequest, asyncio.Future]] = []
        self.records: dict[str, Recorded] = {}
        self.round = 0

    def request(self, role: str, messages: list[dict], **ctx) -> BatchRequest:
        from newsroom import config

        golden = GOLDEN_ROLES.get(role, role)
        r = config.role(golden)
        producer = ctx.get("producer") or PRODUCER_BY_ROLE.get(role, role)
        version = entry_version(ctx.get("prompt_version"), ctx.get("attempt"))
        key = CacheManifest.key(ctx["match_id"], ctx.get("moment_id"), producer, version, r.model, self.seed)
        return BatchRequest(custom_id_for(key), key, role, golden, r.model, messages, ctx.get("schema"),
                            r.max_tokens, r.thinking_level(), {k: v for k, v in ctx.items() if k != "schema"})

    async def complete(self, role: str, messages: list[dict], tools: list | None = None, **ctx) -> dict:
        req = self.request(role, messages, **ctx)
        if req.custom_id in self.records:   # the same call twice (a resumed or repeated step): one answer
            rec = self.records[req.custom_id]
        else:
            fut = asyncio.get_running_loop().create_future()
            self.pending.append((req, fut))
            rec = await fut
        if rec.result.error:
            from newsroom.llm import LLMError

            raise LLMError(rec.result.error)
        return {"text": rec.result.text, "json": rec.result.json, "model": req.model, "role": role,
                "tokens_in": rec.result.tokens_in, "tokens_out": rec.result.tokens_out, "cost_usd": 0.0,
                "latency_ms": 0, "cache_hit": False, "cache_key": req.key}

    async def flush(self, runner) -> list[dict]:
        self.round += 1
        batch, self.pending = self.pending, []
        unique: dict[str, BatchRequest] = {}
        for req, _ in batch:
            req.round = self.round
            unique.setdefault(req.custom_id, req)
        results, jobs = await runner.run(list(unique.values()))
        for req, fut in batch:
            res = results.get(req.custom_id) or BatchResult("", None, 0, 0, 0.0, "missing", error="no result")
            rec = self.records.setdefault(req.custom_id, Recorded(req, res, self.round))
            if not fut.done():
                fut.set_result(rec)
        return [{**j, "round": self.round} for j in jobs]


class RecordingTools:
    """Tool client for the precompute: cached counterfactuals by content, everything else from the match files,
    every result recorded so replay serves it from the cache. Counterfactuals the cache lacks (an alternative
    outside proposer_rule's three) are simulated here and recorded as new `rollout` entries."""

    def __init__(self, manifest: CacheManifest, store) -> None:
        from cache.client import CacheClient
        from newsroom.tools import LocalTools

        self.cache = CacheClient(manifest, speed=1e9)
        self.local = LocalTools(store)
        self.calls: dict[str, tuple[str, dict, Any]] = {}
        self.new_cfs: dict[str, dict] = {}
        self.in_flight = 0

    async def call(self, name: str, args: dict):
        self.in_flight += 1
        try:
            if name == "simulate_counterfactual":
                out = await self.cache.call(name, args)
                if isinstance(out, dict) and out.get("code") == "cache_miss":
                    out = await self.local.call(name, args)
                    if isinstance(out, dict) and "counterfactual_id" in out:
                        self.new_cfs[out["counterfactual_id"]] = out
                    else:   # the engine could not play it: cache the error so replay skips it the same way
                        self.calls[tool_key(args.get("match_id", ""), name, args, self.cache.seed)] = (name, args, out)
                return out
            out = await self.local.call(name, args)
            key = tool_key(args.get("match_id", ""), name, args, self.cache.seed)
            self.calls[key] = (name, args, out)
            return out
        finally:
            self.in_flight -= 1


async def run_rounds(tasks: list[asyncio.Task], client: BatchingClient, tools: RecordingTools, runner,
                     settle_s: float = 0.5, poll_s: float = 0.05, on_round=None) -> list[dict]:
    """Flush parked model calls whenever every workflow is waiting on one (no tool call in flight and nothing new
    parked for `settle_s`); stop when all tasks are done."""
    jobs: list[dict] = []
    last, since = -1, time.monotonic()
    while not all(t.done() for t in tasks):
        await asyncio.sleep(poll_s)
        n = len(client.pending)
        if n != last or tools.in_flight:
            last, since = n, time.monotonic()
            continue
        if n and time.monotonic() - since >= settle_s:
            log.info("round %d: %d requests", client.round + 1, n)
            jobs += await client.flush(runner)
            if on_round:
                on_round(client.round, jobs)
            last = -1
    for t in tasks:
        t.result()          # surface any workflow exception
    return jobs


def record_entries(manifest: CacheManifest, client: BatchingClient, tools: RecordingTools, verdicts: dict[str, bool],
                   seed: int) -> dict:
    """Write every recorded model result, tool result and new counterfactual into the manifest."""
    dirs = {"tactician": "explanations", "proposer": "proposals", "narrator": "fast_lines", "fast_line": "fast_lines",
            "panel": "panel", "recap": "recaps"}
    kinds = {"tactician": "explanation", "proposer": "analytics", "narrator": "fast_line", "fast_line": "fast_line",
             "panel": "panel", "recap": "recap"}
    counts: dict[str, int] = {}
    for rec in client.records.values():
        r, res = rec.request, rec.result
        producer = r.ctx.get("producer") or PRODUCER_BY_ROLE.get(r.live_role, r.live_role)
        payload = {**RECORD, "record": "model_result", "text": res.text, "json": res.json, "round": rec.round,
                   "via": res.via, "verified": verdicts.get(r.key)}
        if res.error:   # a failed call is cached as failed: replay takes the same fallback the golden run took
            payload = {**RECORD, "record": "model_result", "error": res.error, "round": rec.round, "via": res.via,
                       "verified": None}
        latency = LIVE_LATENCY_MS.get(r.live_role if r.live_role.startswith("panel") else producer, 2000)
        manifest.add(r.key, kinds.get(producer, "analytics"), payload, f"{dirs.get(producer, 'models')}/{r.custom_id}.json",
                     moment_id=r.ctx.get("moment_id"), producer=producer,
                     version=entry_version(r.ctx.get("prompt_version"), r.ctx.get("attempt")), model=r.model,
                     seed=seed, simulated_latency_ms=latency, tokens_in=res.tokens_in, tokens_out=res.tokens_out,
                     cost_usd=res.cost_usd, batch_id=res.batch_id)
        counts[producer] = counts.get(producer, 0) + 1
    for key, (name, _args, out) in tools.calls.items():
        manifest.add(key, "analytics", {**RECORD, "record": "tool_result", "result": out},
                     f"tools/{custom_id_for(key)}.json", producer=name,
                     seed=seed, simulated_latency_ms=50)
    for cid, cf in tools.new_cfs.items():
        alt = cf["alternative"]
        key = CacheManifest.key(cf["match_id"], cf.get("moment_id"), "rollout", f"rollout@{cf['engine']}", cf["engine"],
                                seed) + f"/{alt['kind']}-{alt.get('target') or 'none'}/{cf['t_ms']}"
        manifest.add(key, "counterfactual", cf, f"counterfactuals/x_{cid}.json", moment_id=cf.get("moment_id"),
                     producer="rollout", version=f"rollout@{cf['engine']}", model=cf["engine"], seed=seed,
                     simulated_latency_ms=1200)
    counts["tools"] = len(tools.calls)
    counts["new_counterfactuals"] = len(tools.new_cfs)
    return counts


@dataclass
class BatchLog:
    """batches.json: every job, its rounds and the custom_id -> cache key map."""
    jobs: list[dict] = field(default_factory=list)
    custom_ids: dict[str, str] = field(default_factory=dict)

    def save(self, path: Path, client: BatchingClient, extra: dict | None = None, merge: bool = False) -> None:
        """Write batches.json; `merge` keeps an earlier run's jobs and custom ids (a partial re-run)."""
        self.custom_ids = {cid: rec.request.key for cid, rec in sorted(client.records.items())}
        data = {**RECORD, "record": "batches", "jobs": [], "custom_ids": {}}
        if merge and path.exists():
            data = json.loads(path.read_text())
        data["jobs"] = data.get("jobs", []) + self.jobs
        data["custom_ids"] = {**data.get("custom_ids", {}), **self.custom_ids}
        data.update(extra or {})
        path.write_text(json.dumps(data, indent=1, sort_keys=True, default=str) + "\n")
