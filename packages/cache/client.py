"""CacheClient: replay mode's LLMClient and tool client.

    CacheClient.complete(role, messages, tools, **ctx)   # same signature as newsroom.llm.LiveClient
    CacheClient.call(name, args)                         # same signature as newsroom.tools.McpTools

A model call's key comes from the context the executor passes (match, moment, producer, prompt version, attempt)
and the manifest's seed. The entry's stored result is served after `simulated_latency_ms / speed`, so the studio's
trace panel animates with the real timings. The speed is the live replay clock the api publishes to blackboard
`replay/<match_id>` {speed, playing} (studio buttons, demo script, recorder), read at most every 0.5 s; while the
replay is paused no simulated time passes. Without that document, WHYLINE_REPLAY_SPEED. A miss raises CacheMiss (the executors turn it into a
template line and a red `cache_miss` trace row; never silent).

Tool calls: counterfactuals are found by content (t_ms, alternative kind/actor/target, n, horizon), so a cached
`cf_` serves any caller, including the MCP server in replay mode. Other tools are cached as `analytics` entries
keyed by the arguments' hash; a miss there goes to the inner tool client when one is given (those tools are
deterministic reads of the match files), else returns {error, code: "cache_miss"}.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from pathlib import Path

from cache.errors import CacheMiss
from cache.manifest import CacheManifest, default_cache_dir

log = logging.getLogger("whyline.cache")

CLOCK_TTL_S = 0.5     # how stale the replay clock may be
SLICE_S = 0.25        # longest single sleep, so a speed change or pause applies within a wait

PRODUCER_BY_ROLE = {"tactician_live": "tactician", "tactician_golden": "tactician", "narrator_fast": "narrator",
                    "proposer": "proposer", "panel_pundit": "panel", "panel_chair": "panel", "recap": "recap",
                    "recap_live": "recap"}


def replay_speed() -> float:
    return max(float(os.environ.get("WHYLINE_REPLAY_SPEED", "1") or 1), 1e-6)


def entry_version(prompt_version: str | None, attempt: int | None) -> str | None:
    """Rewrites (attempt 2, 3) are separate entries: `narrator@2.a2`."""
    if prompt_version and attempt and int(attempt) > 1:
        return f"{prompt_version}.a{int(attempt)}"
    return prompt_version


def tool_key(match_id: str, name: str, args: dict, seed: int) -> str:
    body = json.dumps({k: v for k, v in args.items() if k != "match_id"}, sort_keys=True, separators=(",", ":"))
    return CacheManifest.key(match_id, None, name, hashlib.sha1(body.encode()).hexdigest()[:12], "mcp", seed)


def cf_key(t_ms: int, alternative: dict, n: int, horizon_s: float) -> tuple:
    return (int(t_ms), alternative.get("kind"), alternative.get("actor"), alternative.get("target") or None, int(n),
            float(horizon_s))


class CacheClient:
    def __init__(self, manifest: CacheManifest | None = None, cache_dir: str | Path | None = None,
                 speed: float | None = None, inner_tools=None, clock_bb=None) -> None:
        if manifest is None:
            cache_dir = Path(cache_dir or default_cache_dir())
            manifest = CacheManifest.load(cache_dir) if (cache_dir / "manifest.json").exists() else None
        self.manifest = manifest
        self.speed = speed
        self.inner = inner_tools
        self.clock_bb = clock_bb
        self._clock: tuple[float, float, bool] | None = None   # (read at, speed, playing)
        self.misses: list[str] = []
        self._cf: dict[tuple, dict] = {}
        if manifest is not None:
            for e in manifest.find(kind="counterfactual"):
                doc = manifest.read(e)
                self._cf[cf_key(doc["t_ms"], doc["alternative"], doc["n"], doc["horizon_s"])] = {
                    "entry": e, "doc": doc}

    @property
    def seed(self) -> int:
        return int(self.manifest.data["match_seed"]) if self.manifest else 0

    def current_speed(self) -> tuple[float, bool]:
        """(speed, playing): a fixed speed if one was given, else the live replay clock, else the env var."""
        if self.speed:
            return self.speed, True
        now = time.monotonic()
        if self._clock is None or now - self._clock[0] > CLOCK_TTL_S:
            speed, playing = replay_speed(), True
            if self.clock_bb is not None and self.manifest is not None:
                from blackboard import NotFound

                try:
                    doc = self.clock_bb.get("replay", self.manifest.data["match_id"])
                    speed = max(float(doc.get("speed") or speed), 1e-6)
                    playing = doc.get("playing", True) is not False
                except (NotFound, TypeError, ValueError):
                    pass
            self._clock = (now, speed, playing)
        return self._clock[1], self._clock[2]

    async def _wait(self, entry: dict) -> int:
        ms = int(entry.get("simulated_latency_ms") or 0)
        left = ms / 1000.0   # simulated seconds still to pass
        while left > 1e-6:
            speed, playing = self.current_speed()
            step = SLICE_S if not playing else min(left / speed, SLICE_S)
            await asyncio.sleep(step)
            if playing:
                left -= step * speed
        return ms

    def _miss(self, key: str) -> None:
        self.misses.append(key)
        log.warning("cache miss %s", key)

    # ------------------------------------------------------------------ LLMClient
    def lookup(self, role: str, **ctx) -> dict | None:
        from newsroom import config

        if self.manifest is None:
            return None
        producer = ctx.get("producer") or PRODUCER_BY_ROLE.get(role, role)
        version = entry_version(ctx.get("prompt_version"), ctx.get("attempt"))
        found = self.manifest.find(moment_id=ctx.get("moment_id"), producer=producer, version=version,
                                   seed=self.seed)
        found = [e for e in found if e["key"].startswith(f"{ctx.get('match_id')}/")]
        if not found:
            return None
        preferred = [config.role(r).model for r in (role, "tactician_golden") if r in config.load_models()["roles"]]
        found.sort(key=lambda e: (e.get("model") not in preferred, e["key"]))
        return found[0]

    async def complete(self, role: str, messages: list[dict], tools: list | None = None, **ctx) -> dict:
        entry = self.lookup(role, **ctx)
        if entry is None:
            key = CacheManifest.key(ctx.get("match_id", "?"), ctx.get("moment_id"),
                                    ctx.get("producer") or PRODUCER_BY_ROLE.get(role, role),
                                    entry_version(ctx.get("prompt_version"), ctx.get("attempt")), None, self.seed)
            self._miss(key)
            raise CacheMiss(key)
        stored = self.manifest.read(entry)
        ms = await self._wait(entry)
        if stored.get("error"):   # the golden run's call failed: replay fails the same way (same fallback)
            from newsroom.llm import LLMError

            raise LLMError(f"cached failure: {stored['error']}")
        return {**stored, "role": role, "model": entry.get("model") or stored.get("model"), "cache_hit": True,
                "cache_key": entry["key"], "latency_ms": ms, "cost_usd": 0.0,
                "tokens_in": entry.get("tokens_in") or 0, "tokens_out": entry.get("tokens_out") or 0}

    # ------------------------------------------------------------------ tool client (RolloutClient)
    def counterfactual(self, match_id: str, t_ms: int, alternative: dict, n: int, horizon_s: float) -> dict | None:
        """Synchronous content lookup; the MCP server uses it in replay mode."""
        if self.manifest is None or self.manifest.data["match_id"] != match_id:
            return None
        hit = self._cf.get(cf_key(t_ms, alternative, n, horizon_s))
        return None if hit is None else hit["doc"]

    async def call(self, name: str, args: dict):
        match_id = args.get("match_id", "")
        if name == "simulate_counterfactual":
            alt = args.get("alternative") or {}
            k = cf_key(args.get("t_ms", 0), alt, args.get("n", 200), args.get("horizon_s", 8))
            hit = self._cf.get(k) if self.manifest and self.manifest.data["match_id"] == match_id else None
            if hit is None:   # an alternative the engine could not play is cached as its error
                entry = self.manifest.get(tool_key(match_id, name, args, self.seed)) if self.manifest else None
                if entry is not None:
                    await self._wait(entry)
                    return self.manifest.read(entry)["result"]
                self._miss(f"{match_id}/simulate_counterfactual/{k}")
                return {"error": f"no cached counterfactual for {k}", "code": "cache_miss"}
            await self._wait(hit["entry"])
            return hit["doc"]
        if self.manifest is not None:
            entry = self.manifest.get(tool_key(match_id, name, args, self.seed))
            if entry is not None:
                await self._wait(entry)
                return self.manifest.read(entry)["result"]
        if self.inner is not None:
            return await self.inner.call(name, args)
        self._miss(tool_key(match_id, name, args, self.seed))
        return {"error": f"no cached {name} result", "code": "cache_miss"}


EVIDENCE_COLLECTIONS = ("counterfactuals", "pitch_control", "facts")


def preload_evidence(bb, manifest: CacheManifest | None, store=None) -> int:
    """Replay start: put the evidence the golden precompute's Fact Checker saw into the blackboard (the match events
    through `store`, and the `evidence.jsonl` documents: counterfactuals, pitch-control snapshots, facts), so every
    verdict, and with it every rewrite, is the same as when the cache was made. Returns the documents loaded."""
    n = 0
    if manifest is None:
        return n
    if store is not None:
        store.match(manifest.data["match_id"])
    for e in manifest.find(producer="evidence"):
        for line in (manifest.cache_dir / e["path"]).read_text().splitlines():
            if line.strip():
                doc = json.loads(line)
                bb.put(doc.pop("_collection"), doc)
                n += 1
    return n
