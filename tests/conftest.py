"""Shared pytest configuration: tests marked `live` run only when WHYLINE_LIVE_TESTS=1."""

import os

import pytest

# torch's libomp must load before LightGBM's, with OpenMP defaulting to one thread (packages/policy/__init__.py)
os.environ.setdefault("OMP_NUM_THREADS", "1")
import torch  # noqa: E402, F401


def pytest_collection_modifyitems(config, items):
    if os.environ.get("WHYLINE_LIVE_TESTS") == "1":
        return
    skip_live = pytest.mark.skip(reason="live API test; set WHYLINE_LIVE_TESTS=1 to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
