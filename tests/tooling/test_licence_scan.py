"""Licence scan rules (T-066): allow-list expressions, hard fails for copyleft and non-commercial."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("licence_scan", ROOT / "scripts" / "licence_scan.py")
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)
ALLOWED, EXCEPTIONS = scan.load_allowlist()


@pytest.mark.parametrize("expr", ["MIT", "MIT License", "Apache Software License; BSD License",
                                  "Apache-2.0 OR BSD-3-Clause", "BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0",
                                  "Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSL-1.0", "PSF-2.0", "ISC",
                                  "CC-BY-4.0", "ISC License (ISCL)", "Apache 2.0 License", "(MIT OR Apache-2.0)",
                                  "(MIT) AND (BSD-3-Clause)"])
def test_allowed(expr):
    assert scan.allowed_expr(expr, ALLOWED)


@pytest.mark.parametrize("expr", ["GPL-3.0", "AGPL-3.0-only", "LGPL-2.1", "GNU General Public License v3 (GPLv3)",
                                  "CC-BY-NC-4.0", "MIT AND GPL-2.0", "MPL-2.0", "UNKNOWN", "",
                                  "Creative Commons Non-Commercial"])
def test_rejected(expr):
    assert not scan.allowed_expr(expr, ALLOWED)


def test_exceptions_are_named_packages_only():
    assert set(EXCEPTIONS) == {"pip:certifi", "pip:tqdm", "npm:webgl-constants"}


def test_repository_scan_is_clean():
    rows, offenders = scan.scan()
    assert not offenders, offenders
    assert {r["ecosystem"] for r in rows} >= {"pip", "npm"}
