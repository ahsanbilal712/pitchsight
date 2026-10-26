"""Clock references for the demo script and shot list.

A clock is either literal or a reference into packages/demo/golden_moments.yaml (written by the golden
precompute), so shots and demo actions follow the moments the precompute chose:

    "31:10"              literal match clock (minutes may exceed 59)
    "45:00+15s"          literal with an offset
    "@sliding_doors"     the `clock` of golden_moments[sliding_doors] (a mapping, or the first item of a list)
    "@fourth_official[1]-0:03"   second item of a list entry, three seconds earlier
    "@kill+2s"           offsets in seconds ("Ns") or mm:ss

`resolve()` returns milliseconds of match time.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_MOMENTS = ROOT / "packages" / "demo" / "golden_moments.yaml"
_CLOCK = re.compile(r"^(\d{1,3}):(\d{2})$")
_REF = re.compile(r"^@([a-z_][a-z0-9_]*)(?:\[(\d+)\])?(?:([+-])(\d+s|\d{1,3}:\d{2}))?$")
_LIT = re.compile(r"^(\d{1,3}:\d{2})(?:([+-])(\d+s|\d{1,3}:\d{2}))?$")


class ClockError(ValueError):
    pass


def clock_ms(text: str) -> int:
    m = _CLOCK.match(text.strip())
    if not m:
        raise ClockError(f"bad clock {text!r} (want mm:ss)")
    return (int(m.group(1)) * 60 + int(m.group(2))) * 1000


def _offset(sign: str | None, amount: str | None) -> int:
    if not amount:
        return 0
    ms = int(amount[:-1]) * 1000 if amount.endswith("s") else clock_ms(amount)
    return -ms if sign == "-" else ms


def fmt(ms: int) -> str:
    s = max(0, ms) // 1000
    return f"{s // 60:02d}:{s % 60:02d}"


def load_moments(path: Path | str | None = None) -> dict:
    p = Path(path) if path else GOLDEN_MOMENTS
    if not p.exists():
        raise ClockError(f"{p.relative_to(ROOT) if p.is_relative_to(ROOT) else p} does not exist yet "
                         "(written by the golden precompute)")
    return yaml.safe_load(p.read_text()) or {}


def is_reference(text: str) -> bool:
    return str(text).strip().startswith("@")


def resolve(text: str | int, moments: dict | None = None) -> int:
    """Milliseconds of match time for a literal clock or an @reference into golden_moments.yaml."""
    if isinstance(text, int):
        return text
    t = str(text).strip()
    lit = _LIT.match(t)
    if lit:
        return clock_ms(lit.group(1)) + _offset(lit.group(2), lit.group(3))
    ref = _REF.match(t)
    if not ref:
        raise ClockError(f"bad clock reference {text!r}")
    moments = load_moments() if moments is None else moments
    key, idx = ref.group(1), ref.group(2)
    if key not in moments:
        raise ClockError(f"golden_moments.yaml has no {key!r} (has: {', '.join(sorted(moments))})")
    entry = moments[key]
    if isinstance(entry, list):
        entry = entry[int(idx or 0)]
    elif idx not in (None, "0"):
        raise ClockError(f"{key} is not a list")
    if isinstance(entry, dict):
        if "t_ms" in entry:
            base = int(entry["t_ms"])
        elif "clock" in entry:
            base = clock_ms(str(entry["clock"]))
        else:
            raise ClockError(f"golden_moments.{key} has neither clock nor t_ms")
    else:
        base = clock_ms(str(entry))
    return base + _offset(ref.group(3), ref.group(4))
