"""Seed 4242 twice into different folders gives byte-identical files."""

import hashlib
from pathlib import Path

from kickoff import Engine
from kickoff.record import write_match

FILES = ("events.jsonl", "tracking.npz", "truth.json")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_golden_seed_is_byte_identical(league, tmp_path):
    hashes = []
    for run in ("a", "b"):
        record = Engine(league, league.club_order[0], league.club_order[1], seed=4242).play()
        out = write_match(record, tmp_path / run)
        hashes.append({name: _sha(out / name) for name in FILES})
    assert hashes[0] == hashes[1]
