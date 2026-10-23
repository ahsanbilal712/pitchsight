"""Video v3 beats in track C's overlay format (shared notes track-c-v3-overlay-formats.md): one JSON per beat at
data/footage/<slug>/cache/v3/<beat>_<clip_ms>.json, a model_cache tool_result with the beat under `result`.
Positions are moment-file pitch metres (y from the near touchline), times are clip_ms, and every number shown on
screen carries its source (cache key, evidence or event id) and, when stochastic, n / horizon_s / seed / engine."""

from __future__ import annotations

import json

from footage.clips import CLIPS


def write_beat(slug: str, beat: str, clip_ms: int, result: dict) -> str:
    from cache.manifest import CacheManifest
    from footage.featured import open_cache

    match_id = CLIPS[slug]["match_id"]
    seed = int(match_id[2:])
    manifest = open_cache(slug)
    path = f"v3/{beat}_{clip_ms}.json"
    old_file = manifest.cache_dir / path
    if old_file.exists() and "caption" not in result:      # a reviewed caption stays while the data is the same
        old = json.loads(old_file.read_text())["result"]
        if {k: v for k, v in old.items() if k != "caption"} == {"beat": beat, "slug": slug, "match_id": match_id,
                                                                **result} and "caption" in old:
            result = {**result, "caption": old["caption"]}
    manifest.add(CacheManifest.key(match_id, None, "v3", f"{beat}_{clip_ms}", None, seed), "analytics",
                 {"$schema": "model_cache.schema.json", "schema_version": "1.0.0", "record": "tool_result",
                  "result": {"beat": beat, "slug": slug, "match_id": match_id, **result}},
                 path, producer="v3", version=f"{beat}_{clip_ms}", seed=seed)
    manifest.save()
    return str(manifest.cache_dir / path)
