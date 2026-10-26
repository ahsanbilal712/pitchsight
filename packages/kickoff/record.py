"""Byte-identical writers for a match folder: events.jsonl, tracking.npz, truth.json.

numpy.savez_compressed stamps the current time into each zip entry, so tracking.npz is written with
zipfile directly: fixed ZipInfo.date_time (1980-01-01), deflate, entries in a fixed order. JSON is dumped
with sorted keys and fixed separators; floats are rounded before they reach the writer.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import numpy as np

from .engine import MatchRecord

TRACKING_ORDER = ("t_ms", "period", "S", "ball_z", "holder", "possession", "player_ids",
                  "sub_t_ms", "sub_row", "sub_player_id")
ZIP_DATE = (1980, 1, 1, 0, 0, 0)


def dumps_line(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"


def write_events(events: list[dict], path: Path) -> None:
    path.write_text("".join(dumps_line(e) for e in events), encoding="utf-8")


def write_tracking(tracking: dict[str, np.ndarray], path: Path) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for name in TRACKING_ORDER:
            buf = io.BytesIO()
            np.lib.format.write_array(buf, np.ascontiguousarray(tracking[name]), allow_pickle=False)
            info = zipfile.ZipInfo(f"{name}.npy", date_time=ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, buf.getvalue(), compresslevel=6)


def write_truth(truth: dict, path: Path) -> None:
    path.write_text(json.dumps(truth, sort_keys=True, indent=1, ensure_ascii=False, allow_nan=False) + "\n",
                    encoding="utf-8")


def write_match(record: MatchRecord, out: str | Path) -> Path:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    write_events(record.events, out / "events.jsonl")
    write_tracking(record.tracking, out / "tracking.npz")
    write_truth(record.truth, out / "truth.json")
    return out


def load_tracking(path: str | Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}
