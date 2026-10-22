"""Clip registry: config/footage.yaml (slug -> match id, home, away) and the media folder data/footage/<slug>/."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
FOOTAGE = ROOT / "data" / "footage"


@lru_cache(maxsize=1)
def load_config() -> dict:
    return yaml.safe_load((ROOT / "config" / "footage.yaml").read_text())


CLIPS: dict[str, dict] = load_config()["clips"]


def clip_dir(slug: str) -> Path:
    if slug not in CLIPS:
        raise KeyError(f"unknown clip {slug!r}; known: {sorted(CLIPS)}")
    return FOOTAGE / slug
