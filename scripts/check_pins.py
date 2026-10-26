"""Check that dependency pins are exact and match what is installed.

Usage: python scripts/check_pins.py   (run with the repo .venv active)

Checks:
1. Every non-comment line in config/pins.txt carries an exact version (`name==x` or `name@x`).
2. Every Python pin is installed at exactly that version, except lines tagged `[deferred: T-NNN]`,
   which may be absent until their ticket installs them (if present, the version must still match).
3. requirements.lock matches the installed environment (pip freeze), line for line.
4. Every Node pin that an app declares in apps/*/package.json is declared and locked at that exact version.
5. gfootball is not installed.
Exits 1 and lists every problem otherwise.
"""

from __future__ import annotations

import json
import re
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PINS = ROOT / "config" / "pins.txt"
LOCK = ROOT / "requirements.lock"
APPS = ROOT / "apps"

PY_PIN = re.compile(r"^([A-Za-z0-9_.\-]+)==([A-Za-z0-9_.+\-]+)$")
NODE_PIN = re.compile(r"^(@?[A-Za-z0-9_.\-/]+)@([0-9][A-Za-z0-9_.+\-]*)$")
FORBIDDEN = ["gfootball"]


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_pins(text: str) -> tuple[dict, dict, set, list[str]]:
    py, node, deferred, errors = {}, {}, set(), []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        spec, _, comment = line.partition("#")
        spec = spec.strip()
        if m := PY_PIN.match(spec):
            py[norm(m[1])] = m[2]
            if "[deferred:" in comment:
                deferred.add(norm(m[1]))
        elif m := NODE_PIN.match(spec):
            node[m[1]] = m[2]
        else:
            errors.append(f"pins.txt:{n}: no exact version: {spec!r}")
    return py, node, deferred, errors


def installed() -> dict[str, str]:
    return {norm(d.metadata["Name"]): d.version for d in metadata.distributions()}


def check_python(py: dict, deferred: set, have: dict) -> list[str]:
    errors = []
    for name, want in sorted(py.items()):
        got = have.get(name)
        if got is None:
            if name not in deferred:
                errors.append(f"{name}=={want} pinned but not installed")
        elif got != want:
            errors.append(f"{name}: pinned {want}, installed {got}")
    for name in FORBIDDEN:
        if name in have:
            errors.append(f"{name} is installed but must never be a dependency")
    return errors


def check_lock(have: dict) -> list[str]:
    if not LOCK.exists():
        return ["requirements.lock missing; write it with: python -m pip freeze > requirements.lock"]
    locked = {}
    for line in LOCK.read_text().splitlines():
        if m := PY_PIN.match(line.strip()):
            locked[norm(m[1])] = m[2]
    skip = {"pip"}
    errors = []
    for name in sorted(set(locked) | set(have)):
        if name in skip:
            continue
        if locked.get(name) != have.get(name):
            errors.append(f"requirements.lock: {name} locked {locked.get(name)}, installed {have.get(name)}")
    return errors


def check_node(node: dict) -> list[str]:
    errors = []
    for pkg_json in sorted(APPS.glob("*/package.json")):
        app = pkg_json.parent.name
        declared = {}
        data = json.loads(pkg_json.read_text())
        for section in ("dependencies", "devDependencies"):
            declared.update(data.get(section, {}))
        lock_path = pkg_json.parent / "package-lock.json"
        lock = json.loads(lock_path.read_text()) if lock_path.exists() else None
        if lock is None:
            errors.append(f"apps/{app}: package-lock.json missing")
        for name, spec in declared.items():
            if not re.fullmatch(r"[0-9][A-Za-z0-9_.+\-]*", spec):
                errors.append(f"apps/{app}: {name} declared as {spec!r}, not an exact version")
            if name in node and spec != node[name]:
                errors.append(f"apps/{app}: {name} declared {spec}, pinned {node[name]}")
            if lock is not None:
                locked = lock.get("packages", {}).get(f"node_modules/{name}", {}).get("version")
                if locked != spec:
                    errors.append(f"apps/{app}: {name} locked {locked}, declared {spec}")
    return errors


def main() -> int:
    py, node, deferred, errors = parse_pins(PINS.read_text())
    have = installed()
    errors += check_python(py, deferred, have)
    errors += check_lock(have)
    errors += check_node(node)
    if errors:
        print("check_pins: FAIL")
        for e in errors:
            print("  " + e)
        return 1
    print(f"check_pins: OK ({len(py)} Python pins, {len(deferred)} deferred, {len(node)} Node pins, "
          f"{len(have)} installed distributions match requirements.lock)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
