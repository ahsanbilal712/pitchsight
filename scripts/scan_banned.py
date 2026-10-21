"""Scan files for Fact Checker rule-7 content (T-019): real club, league, player or broadcaster names from
data/league/banned_names.txt, injury speculation, referee-bias accusations, betting language.

Usage: python scripts/scan_banned.py PATH...    (files or directories; exit 1 on any hit)

Text files (.md .txt .ts .tsx .js .jsx .css .html .yaml .yml .csv) are scanned line by line; JSON and JSONL files
are scanned by string value (keys are code, not copy). banned_names.txt itself, node_modules and dist are skipped.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from newsroom.factcheck import banned_matcher  # noqa: E402

TEXT = {".md", ".txt", ".ts", ".tsx", ".js", ".jsx", ".css", ".html", ".yaml", ".yml", ".csv", ".py"}
JSON = {".json", ".jsonl"}
SKIP_DIRS = {"node_modules", "dist", ".git", "__pycache__", "out"}
SKIP_FILES = {"banned_names.txt"}


def strings(obj, path: str = ""):
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from strings(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from strings(v, f"{path}[{i}]")


def files(paths: list[str]):
    for p in map(Path, paths):
        if p.is_file():
            yield p
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and not SKIP_DIRS & set(f.relative_to(p).parts[:-1]):
                    yield f
        else:
            print(f"scan_banned: no such path {p}", file=sys.stderr)


def scan(path: Path) -> list[str]:
    if path.name in SKIP_FILES or path.suffix not in TEXT | JSON:
        return []
    matcher = banned_matcher()
    hits = []
    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix in JSON:
        docs = ([json.loads(ln) for ln in raw.splitlines() if ln.strip()] if path.suffix == ".jsonl"
                else [json.loads(raw)])
        units = [(f"doc{i}:{where}", s) for i, d in enumerate(docs) for where, s in strings(d)]
    else:
        units = [(f"line {n}", line) for n, line in enumerate(raw.splitlines(), 1)]
    for where, text in units:
        for category, phrase in matcher.find(text):
            hits.append(f"{path}: {where}: {category} {phrase!r}")
    return hits


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    hits, n = [], 0
    for f in files(argv):
        n += 1
        hits += scan(f)
    for h in hits:
        print(h)
    print(f"scan_banned: {n} files, {len(hits)} hits")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
