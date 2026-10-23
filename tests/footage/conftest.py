"""Footage tests that re-run a producer (footage.studio, footage.river) write into the committed clip cache; the
fixture puts the cache back byte for byte afterwards, so a test run never leaves run timings in the working tree."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def restore_clip_cache():
    snaps = {}

    def keep(slug: str) -> None:
        cache = ROOT / "data" / "footage" / slug / "cache"
        snaps[cache] = {p: p.read_bytes() for p in cache.rglob("*") if p.is_file() and not _journal(p)}

    yield keep
    for cache, files in snaps.items():
        for p in cache.rglob("*"):
            if p.is_file() and p not in files:
                p.unlink()                     # new files, and sqlite journals that belong to the run's database
        for p, data in files.items():
            if not p.exists() or p.read_bytes() != data:
                p.write_bytes(data)


def _journal(p: Path) -> bool:
    return p.name.endswith(("-wal", "-shm", "-journal"))
