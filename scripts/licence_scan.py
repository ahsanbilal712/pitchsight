"""Licence scan: Python packages, production npm packages of the three apps, and the asset list.

Usage: python scripts/licence_scan.py [--json]

- Python: `pip-licenses --format=json` over the current environment.
- npm: `apps/{overlay,studio,fan}/package-lock.json`, packages not marked dev (no node_modules needed; a missing
  licence field falls back to the package's LICENSE file when node_modules exists, else to config exceptions).
- Assets: `data/league/assets.json` if present (`[{path, licence, source}]`).
Every licence is checked against `config/licence_allowlist.txt`. GPL, AGPL, LGPL and non-commercial always fail.
Exit 1 on any offender.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST = ROOT / "config" / "licence_allowlist.txt"
APPS = ("overlay", "studio", "fan")
ASSETS = ROOT / "data" / "league" / "assets.json"
FORBIDDEN = re.compile(r"(^|[^A-Z])(A?GPL|LGPL)|NON-?COMMERCIAL|(^|-)NC(-|$)|CC-BY-NC", re.IGNORECASE)

NORMALISE = {
    "mit license": "MIT", "mit": "MIT", "the mit license": "MIT", "expat": "MIT",
    "apache software license": "Apache-2.0", "apache 2.0": "Apache-2.0", "apache license 2.0": "Apache-2.0",
    "apache-2.0": "Apache-2.0", "apache license, version 2.0": "Apache-2.0", "apache 2.0 license": "Apache-2.0",
    "bsd license": "BSD", "bsd": "BSD", "new bsd license": "BSD-3-Clause", "3-clause bsd": "BSD-3-Clause",
    "python software foundation license": "PSF-2.0", "psf": "PSF-2.0", "psf-2.0": "PSF-2.0",
    "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0", "mpl-2.0 and mit": "MPL-2.0 AND MIT", "isc license (iscl)": "ISC", "isc license": "ISC",
    "cc0 1.0 universal": "CC0-1.0", "cc0": "CC0-1.0", "cc by 4.0": "CC-BY-4.0", "cc-by-4.0": "CC-BY-4.0",
}


def norm(lic: str) -> str:
    return NORMALISE.get(lic.strip().lower(), lic.strip())


def load_allowlist(path: Path = ALLOWLIST) -> tuple[set[str], dict[str, str]]:
    allowed, packages, section = set(), {}, None
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("["):
            section = line.strip("[]")
        elif section == "licences":
            allowed.add(line)
        elif section == "packages":
            name, lic = line.split(None, 1)
            packages[name] = lic
    return allowed, packages


def unwrap(text: str) -> str:
    """Drop surrounding spaces and outer parentheses that enclose the whole text, never a parenthesis that belongs
    to a name such as "ISC License (ISCL)"."""
    text = text.strip()
    while text.startswith("(") and text.endswith(")"):
        depth = 0
        for i, ch in enumerate(text):
            depth += (ch == "(") - (ch == ")")
            if depth == 0 and i < len(text) - 1:
                return text                      # the first "(" closes before the end: not an outer pair
        text = text[1:-1].strip()
    return text


def allowed_expr(expr: str, allowed: set[str]) -> bool:
    """SPDX-ish expression check: AND binds tighter than OR; pip's '; ' lists alternatives."""
    if not expr.strip() or FORBIDDEN.search(expr):
        return False
    expr = re.sub(r"\s+WITH\s+[\w.-]+", "", unwrap(expr))
    for alternative in re.split(r"\s+OR\s+|;\s*", expr):
        parts = [unwrap(p) for p in re.split(r"\s+AND\s+", unwrap(alternative)) if unwrap(p)]
        if parts and all(norm(p) in allowed for p in parts):
            return True
    return False


def pip_packages() -> list[dict]:
    out = subprocess.run([sys.executable, "-m", "piplicenses", "--format=json", "--with-system"],
                         capture_output=True, text=True, check=True).stdout
    return [{"ecosystem": "pip", "name": p["Name"], "version": p["Version"], "licence": p["License"]}
            for p in json.loads(out)]


def npm_packages() -> list[dict]:
    found = []
    for app in APPS:
        lock = ROOT / "apps" / app / "package-lock.json"
        if not lock.exists():
            continue
        for key, meta in json.loads(lock.read_text()).get("packages", {}).items():
            if not key or meta.get("dev") or meta.get("devOptional"):
                continue
            name = key.split("node_modules/")[-1]
            lic = meta.get("license")
            if isinstance(lic, dict):
                lic = lic.get("type")
            if not lic:
                lic_file = next((ROOT / "apps" / app / key).glob("LICEN[CS]E*"), None) if (
                    ROOT / "apps" / app / key).exists() else None
                if lic_file and lic_file.read_text(errors="replace").lstrip().upper().startswith("MIT LICENSE"):
                    lic = "MIT"
            found.append({"ecosystem": "npm", "name": name, "version": meta.get("version"), "licence": lic or "",
                          "app": app})
    return found


def asset_entries() -> list[dict]:
    if not ASSETS.exists():
        return []
    return [{"ecosystem": "asset", "name": a["path"], "version": "", "licence": a.get("licence", "")}
            for a in json.loads(ASSETS.read_text())]


def scan() -> tuple[list[dict], list[dict]]:
    allowed, exceptions = load_allowlist()
    rows, offenders = pip_packages() + npm_packages() + asset_entries(), []
    for r in rows:
        key = f"{r['ecosystem']}:{r['name']}"
        exception = exceptions.get(key)
        if exception is not None:  # named exception: the recorded licence must still be what we reviewed
            same = not r["licence"] or norm(r["licence"]) == norm(exception) or allowed_expr(r["licence"], allowed)
            r["status"] = "exception" if same and not FORBIDDEN.search(r["licence"]) else "offender"
        else:
            r["status"] = "ok" if r["licence"] and allowed_expr(r["licence"], allowed) else "offender"
        if r["status"] == "offender":
            offenders.append(r)
    return rows, offenders


def main() -> int:
    rows, offenders = scan()
    if "--json" in sys.argv:
        print(json.dumps(rows, indent=1))
    by_eco: dict[str, int] = {}
    for r in rows:
        by_eco[r["ecosystem"]] = by_eco.get(r["ecosystem"], 0) + 1
    for r in rows:
        if r["status"] == "exception":
            print(f"exception {r['ecosystem']}:{r['name']} {r['version']} {r['licence']!r}")
    for r in offenders:
        print(f"OFFENDER {r['ecosystem']}:{r['name']} {r['version']} {r['licence']!r}")
    print(f"licence_scan: {sum(by_eco.values())} entries {by_eco}, {len(offenders)} offenders")
    return 1 if offenders else 0


if __name__ == "__main__":
    sys.exit(main())
