"""CacheManifest: the index of every precomputed artefact of one match (schemas/cache_manifest.schema.json).

Key: `<match_id>/<moment_id or "match">/<producer>@<version>/<model or engine or "none">/s<seed>`. When the version
already names the producer (prompt versions like `tactician@3`) it is not repeated:
`m_4242/mo_00077/tactician@3/gemini-4-argon/s4242`, `m_4242/mo_00077/rollout@scripted_v1/scripted/s4242`.

The manifest lives at `<cache_dir>/manifest.json` (default data/matches/<seed>/cache, WHYLINE_CACHE_DIR); entry
paths are relative to the cache directory. `verify_hashes()` checks events.jsonl, tracking.npz and every entry.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator

from cache.errors import CacheCorrupt, CacheFrozen

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "schemas" / "cache_manifest.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA)
KINDS = tuple(SCHEMA["properties"]["entries"]["items"]["properties"]["kind"]["enum"])
# producer -> manifest kind (schema enum; Oracle, Dugout, Decision Index and tool calls are "analytics")
KIND_BY_PRODUCER = {"tactician": "explanation", "narrator": "fast_line", "fast_line": "fast_line",
                    "proposer": "analytics", "panel": "panel", "recap": "recap", "rollout": "counterfactual",
                    "pitch_control": "pitch_control", "fourth_official": "fourth_official", "director": "cue",
                    "oracle": "analytics", "dugout": "analytics", "decision_index": "analytics"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_cache_dir(seed: int | None = None) -> Path:
    env = os.environ.get("WHYLINE_CACHE_DIR")
    if env and seed is None:
        p = Path(env)
        return p if p.is_absolute() else ROOT / p
    return ROOT / "data" / "matches" / str(seed or int(os.environ.get("WHYLINE_MATCH_SEED", "4242"))) / "cache"


class CacheManifest:
    def __init__(self, data: dict, cache_dir: str | Path) -> None:
        self.data = data
        self.cache_dir = Path(cache_dir)
        self._by_key = {e["key"]: e for e in data["entries"]}

    # ------------------------------------------------------------------ keys
    @staticmethod
    def key(match_id: str, moment_id: str | None, producer: str, version: str | None, model: str | None,
            seed: int | None) -> str:
        version = version or "none"
        tag = version if version.startswith(f"{producer}@") else f"{producer}@{version}"
        return f"{match_id}/{moment_id or 'match'}/{tag}/{model or 'none'}/s{seed if seed is not None else 0}"

    # ------------------------------------------------------------------ load / save
    @classmethod
    def load(cls, cache_dir: str | Path) -> CacheManifest:
        cache_dir = Path(cache_dir)
        data = json.loads((cache_dir / "manifest.json").read_text())
        errors = [e.message for e in VALIDATOR.iter_errors(data)]
        if errors:
            raise CacheCorrupt(f"{cache_dir / 'manifest.json'} does not validate: {errors[:3]}")
        return cls(data, cache_dir)

    @classmethod
    def new(cls, match_dir: str | Path, cache_dir: str | Path | None = None, engine_hash: str | None = None
            ) -> CacheManifest:
        match_dir = Path(match_dir)
        first = json.loads((match_dir / "events.jsonl").read_text().splitlines()[0])
        if engine_hash is None:
            from rollout.core import engine_hash as eh

            engine_hash = eh()
        data = {"schema_version": "1.0.0", "match_id": first["match_id"], "match_seed": int(first["attrs"]["seed"]),
                "events_sha256": sha256_file(match_dir / "events.jsonl"),
                "tracking_sha256": sha256_file(match_dir / "tracking.npz"), "engine_hash": engine_hash,
                "created_at": now_iso(), "frozen": False, "entries": [], "totals": {"entries": 0, "cost_usd": 0.0}}
        return cls(data, cache_dir or match_dir / "cache")

    def save(self) -> Path:
        self.data["entries"].sort(key=lambda e: e["key"])
        ents = self.data["entries"]
        self.data["totals"] = {"entries": len(ents), "cost_usd": round(sum(e.get("cost_usd") or 0 for e in ents), 6),
                               "tokens_in": sum(e.get("tokens_in") or 0 for e in ents),
                               "tokens_out": sum(e.get("tokens_out") or 0 for e in ents)}
        errors = [e.message for e in VALIDATOR.iter_errors(self.data)]
        if errors:
            raise CacheCorrupt(f"manifest does not validate: {errors[:3]}")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.cache_dir / "manifest.json"
        path.write_text(json.dumps(self.data, indent=1, sort_keys=True) + "\n")
        return path

    # ------------------------------------------------------------------ entries
    @property
    def frozen(self) -> bool:
        return bool(self.data.get("frozen"))

    @property
    def entries(self) -> list[dict]:
        return self.data["entries"]

    def get(self, key: str) -> dict | None:
        return self._by_key.get(key)

    def find(self, **match) -> list[dict]:
        return [e for e in self.entries if all(e.get(k) == v for k, v in match.items())]

    def add(self, key: str, kind: str, payload: dict | bytes, path: str, *, moment_id: str | None = None,
            producer: str | None = None, version: str | None = None, model: str | None = None,
            seed: int | None = None, **meta) -> dict:
        """Write the payload under the cache dir and index it (precompute only)."""
        if self.frozen:
            raise CacheFrozen("manifest is frozen; bump docs/video/VERSION to regenerate")
        if kind not in KINDS:
            raise ValueError(f"kind {kind!r} not in {KINDS}")
        target = self.cache_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        body = payload if isinstance(payload, bytes) else (json.dumps(payload, indent=1, sort_keys=True) + "\n").encode()
        target.write_bytes(body)
        entry = {"key": key, "kind": kind, "moment_id": moment_id, "producer": producer, "version": version,
                 "model": model, "seed": seed, "path": path, "sha256": hashlib.sha256(body).hexdigest(),
                 "created_at": now_iso(), "hand_reviewed": False, **meta}
        self.data["entries"] = [e for e in self.entries if e["key"] != key] + [entry]
        self._by_key[key] = entry
        return entry

    def read(self, entry: dict) -> dict:
        path = self.cache_dir / entry["path"]
        if not path.exists():
            raise CacheCorrupt(f"missing cache file {path}")
        return json.loads(path.read_text())

    # ------------------------------------------------------------------ hashes
    def problems(self, match_dir: str | Path | None = None) -> list[str]:
        """Every hash mismatch or missing file (empty list = all good)."""
        out = []
        match_dir = Path(match_dir) if match_dir else self.cache_dir.parent
        for name, field in (("events.jsonl", "events_sha256"), ("tracking.npz", "tracking_sha256")):
            f = match_dir / name
            if not f.exists():
                out.append(f"missing {f}")
            elif sha256_file(f) != self.data[field]:
                out.append(f"{name} hash differs from {field}")
        for e in self.entries:
            f = self.cache_dir / e["path"]
            if not f.exists():
                out.append(f"missing {e['path']} ({e['key']})")
            elif sha256_file(f) != e["sha256"]:
                out.append(f"{e['path']} hash differs ({e['key']})")
        return out

    def verify_hashes(self, match_dir: str | Path | None = None) -> bool:
        return not self.problems(match_dir)
