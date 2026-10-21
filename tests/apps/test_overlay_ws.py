"""The overlay plays the golden match from the API WebSocket instead of the fixture (T-022)."""

import socket
import threading
import time

import pytest
import uvicorn

from api.main import create_app

READY = "() => window.__whyline && window.__whyline.ready === true"


@pytest.fixture(scope="module")
def api_port():
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


def test_overlay_plays_golden_match_over_ws(page, overlay_url, api_port, out_dir):
    page.goto(f"{overlay_url}?record=1&api=127.0.0.1:{api_port}")
    page.wait_for_function(READY, timeout=5000)
    first = page.evaluate("() => window.__whyline.debug()")
    page.wait_for_timeout(1500)
    second = page.evaluate("() => window.__whyline.debug()")
    print(f"\nws: {second['frames'] - first['frames']} frames, clock +{second['clock'] - first['clock']} ms in 1.5 s")
    assert second["frames"] - first["frames"] >= 10
    assert 1000 <= second["clock"] - first["clock"] <= 2200
    page.evaluate("() => window.__whyline.seek('39:10')")
    page.wait_for_function("() => window.__whyline.debug().clock >= 2350000", timeout=3000)
    assert "0-1" in page.get_by_test_id("clock").inner_text()  # score rebuilt from the hello after the seek
    page.screenshot(path=str(out_dir / "overlay_ws.png"))
    assert not page.errors, page.errors
