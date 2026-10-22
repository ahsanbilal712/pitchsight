"""T-057 hand review: the golden cache replays with no red trace row (T-062 records zero)."""

from pathlib import Path

from cache import CacheManifest
from cache.review import broken_rewrites

CACHE = Path(__file__).resolve().parents[2] / "data" / "matches" / "4242" / "cache"


def test_golden_cache_has_no_broken_rewrites():
    """A cached rewrite that failed or has no headline/body replays as a red `error` row."""
    assert broken_rewrites(CacheManifest.load(CACHE)) == []
