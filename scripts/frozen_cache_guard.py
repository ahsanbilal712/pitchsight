"""Frozen-cache guard (TECH_PLAN 1.8 "Freeze rule", 1.10 CI job frozen-cache-guard; T-060).

Usage: python scripts/frozen_cache_guard.py [--base REF] [--head REF] [--manifest PATH] [--repo DIR]

If the manifest at --base has `frozen: true`, any difference at --head (an entry added, removed or with another
sha256, the match hashes, or the frozen flag itself) fails unless docs/video/VERSION changed between the two refs
and its number went up. A manifest that is not frozen (before T-071), or absent at the base, passes.
Base default: the PR base (GITHUB_BASE_REF) in CI pull requests, else HEAD^. Exit 0 pass, 1 fail.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

MANIFEST = "data/matches/4242/cache/manifest.json"
VERSION = "docs/video/VERSION"


def git(repo: str, *args: str) -> str | None:
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def at(repo: str, ref: str, path: str) -> str | None:
    return git(repo, "show", f"{ref}:{path}")


def fingerprint(manifest: dict) -> dict:
    return {"frozen": bool(manifest.get("frozen")), "events": manifest.get("events_sha256"),
            "tracking": manifest.get("tracking_sha256"),
            "entries": {e["key"]: e["sha256"] for e in manifest.get("entries", [])}}


def default_base() -> str:
    base = os.environ.get("GITHUB_BASE_REF")
    return f"origin/{base}" if base else "HEAD^"


def check(repo: str, base: str, head: str, manifest_path: str = MANIFEST) -> tuple[bool, str]:
    if git(repo, "rev-parse", "--verify", f"{base}^{{commit}}") is None:
        return True, f"base {base} not found (first commit?): nothing to guard"
    old = at(repo, base, manifest_path)
    if old is None:
        return True, f"no manifest at {base}: nothing frozen yet"
    old_m = json.loads(old)
    if not old_m.get("frozen"):
        return True, f"manifest at {base} is not frozen: changes allowed (freeze happens at T-071)"
    new = at(repo, head, manifest_path)
    new_fp = fingerprint(json.loads(new)) if new is not None else None
    old_fp = fingerprint(old_m)
    if new_fp == old_fp:
        return True, "frozen manifest unchanged"
    diff = {k for k in old_fp if new_fp is None or old_fp[k] != new_fp[k]}
    v_old, v_new = at(repo, base, VERSION), at(repo, head, VERSION)
    try:
        bumped = v_new is not None and int(v_new.strip()) > int((v_old or "0").strip())
    except ValueError:
        bumped = False
    if bumped:
        return True, f"frozen manifest changed ({', '.join(sorted(diff))}) with {VERSION} {(v_old or '0').strip()} " \
                     f"-> {v_new.strip()}: allowed (new video required)"
    return False, f"frozen manifest changed ({', '.join(sorted(diff))}) without a {VERSION} bump (TECH_PLAN 1.8)"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=None)
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--manifest", default=MANIFEST)
    ap.add_argument("--repo", default=".")
    args = ap.parse_args(argv)
    ok, why = check(args.repo, args.base or default_base(), args.head, args.manifest)
    print(f"frozen_cache_guard: {'OK' if ok else 'FAIL'}: {why}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
