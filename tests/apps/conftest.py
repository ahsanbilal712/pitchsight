"""Serve a built front-end app and drive it with Playwright for Python (TECH_PLAN conventions)."""

import functools
import http.server
import socket
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "out"


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # keep pytest output clean
        pass


@pytest.fixture(scope="session")
def overlay_url():
    dist = ROOT / "apps" / "overlay" / "dist"
    if not (dist / "index.html").exists():
        pytest.fail("apps/overlay/dist missing: run `npm --prefix apps/overlay run build` first")
    handler = functools.partial(_Quiet, directory=str(dist))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/index.html"
    server.shutdown()


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
    pg = context.new_page()
    errors: list[str] = []
    pg.on("pageerror", lambda exc: errors.append(str(exc)))
    pg.errors = errors
    yield pg
    context.close()


@pytest.fixture(scope="session")
def out_dir() -> Path:
    OUT.mkdir(exist_ok=True)
    return OUT


@pytest.fixture(scope="session")
def api_port():
    """whyline-api serving the golden match 4242 at x1 on a free port, for screens opened with ?api=."""
    import uvicorn

    from api.main import create_app

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(seed=4242, speed=1), host="127.0.0.1", port=port,
                                           log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while not server.started:
        if time.time() > deadline:
            pytest.fail("api did not start")
        time.sleep(0.05)
    yield port
    server.should_exit = True
    thread.join(timeout=5)
