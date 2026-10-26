"""Serve a built front-end app and drive it with Playwright for Python."""

import functools
import http.server
import socket
import threading
import time
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "out"


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # keep pytest output clean
        pass


def _serve(app: str):
    dist = ROOT / "apps" / app / "dist"
    if not (dist / "index.html").exists():
        pytest.fail(f"apps/{app}/dist missing: run `npm --prefix apps/{app} run build` first")
    handler = functools.partial(_Quiet, directory=str(dist))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/index.html"


@pytest.fixture(scope="session")
def overlay_url():
    server, url = _serve("overlay")
    yield url
    server.shutdown()


@pytest.fixture(scope="session")
def studio_url():
    server, url = _serve("studio")
    yield url
    server.shutdown()


@pytest.fixture(scope="session")
def fan_url():
    server, url = _serve("fan")
    yield url
    server.shutdown()


@pytest.fixture(scope="session")
def playwright_session():
    """One sync Playwright per session: a second one in the same thread fails."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        yield pw


@pytest.fixture(scope="session")
def browser(playwright_session):
    b = playwright_session.chromium.launch()
    yield b
    b.close()


@pytest.fixture(scope="session")
def gpu_browser(playwright_session):
    """Chromium on the Mac's GPU (Metal through ANGLE). Plain headless Chromium renders WebGL with SwiftShader on
    the CPU, which says nothing about how the 3D scene records; the demo recorder uses the same flags."""
    b = playwright_session.chromium.launch(args=["--use-angle=metal", "--ignore-gpu-blocklist"])
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
def api_server(tmp_path_factory):
    """whyline-api serving the golden match 4242 at x1 on a free port, for screens opened with ?api=.
    Yields (port, bb, app): tests seed the blackboard the way the newsroom would."""
    import uvicorn

    from api.main import create_app
    from blackboard import SqliteBlackboard

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    bb = SqliteBlackboard(tmp_path_factory.mktemp("bb") / "bb.sqlite")
    app = create_app(seed=4242, speed=1, bb=bb)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while not server.started:
        if time.time() > deadline:
            pytest.fail("api did not start")
        time.sleep(0.05)
    yield types.SimpleNamespace(port=port, bb=bb, app=app, base=f"http://127.0.0.1:{port}")
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="session")
def api_port(api_server):
    return api_server.port
