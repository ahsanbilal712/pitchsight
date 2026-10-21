# cache

Cache manifest, CacheClient and the golden-match precompute.

Interface restated from `TECH_PLAN.md` section 1.4 "cache (replay layer and precompute)" (TECH_PLAN wins on conflict).
Tests live in `tests/cache/`.

```python
class CacheManifest: load/save; key(match_id, moment_id, producer, version, model, seed) -> str; verify_hashes() -> bool
class CacheClient(LLMClient, RolloutClient):  # serves cache hits with simulated latency; misses raise CacheMiss in replay mode
def precompute(seed: int, mode: Literal["batch", "live"], roles: list[str], hand_review_top_k: int = 20) -> Report
```

## As built (T-038)

- `manifest.py`: `CacheManifest.load/new/save/add/read/find/key/verify_hashes/problems`. Keys
  `<match>/<moment or match>/<producer>@<version>/<model or engine or none>/s<seed>` (a version that already names
  its producer, like `tactician@3`, is not repeated); rewrites are versions `narrator@2.a2`. Every save validates
  against `schemas/cache_manifest.schema.json`; a frozen manifest refuses new entries.
- `client.py`: `CacheClient` is both the replay `LLMClient` (`complete`) and tool client (`call`). Hits wait
  `simulated_latency_ms / WHYLINE_REPLAY_SPEED`; model misses raise `CacheMiss`, tool misses return
  `{error, code: "cache_miss"}` (or go to an inner tool client for the deterministic read tools). Counterfactuals
  are found by content (t_ms, alternative, n, horizon). Tool entries are `analytics` with key
  `<match>/match/<tool>@<args sha1[:12]>/mcp/s<seed>` and payload `{"result": ...}`.
- Injection: `newsroom.worker.make_deps("replay")` uses CacheClient for model calls and tools;
  `python -m mcp_server` with `WHYLINE_MODE=replay` serves cached counterfactuals and refuses fresh simulations.
