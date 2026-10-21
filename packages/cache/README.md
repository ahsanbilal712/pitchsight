# cache

Cache manifest, CacheClient and the golden-match precompute.

Interface restated from `TECH_PLAN.md` section 1.4 "cache (replay layer and precompute)" (TECH_PLAN wins on conflict).
Tests live in `tests/cache/`.

```python
class CacheManifest: load/save; key(match_id, moment_id, producer, version, model, seed) -> str; verify_hashes() -> bool
class CacheClient(LLMClient, RolloutClient):  # serves cache hits with simulated latency; misses raise CacheMiss in replay mode
def precompute(seed: int, mode: Literal["batch", "live"], roles: list[str], hand_review_top_k: int = 20) -> Report
```
