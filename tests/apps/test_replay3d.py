"""/replay3d: the Sliding Doors scene renders, records at >= 30 fps, seeks and switches cameras (T-053).

Runs in Chromium on the GPU (`gpu_browser`, Metal via ANGLE), the way the demo recorder runs it.
"""

import time

READY = "() => window.__whyline && window.__whyline.ready === true"
BRANCH = 1_874_000                     # cf_000077.t_ms
RECORD_S = 20
FPS_MIN = 30


def open_scene(browser, url, query=""):
    ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
    page = ctx.new_page()
    errors, requests = [], []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("request", lambda r: requests.append(r.url))
    page.goto(f"{url}?fixture=1&record=1&view=replay3d&cf=cf_000077{query}")
    page.wait_for_function(READY, timeout=15000)
    return ctx, page, errors, requests


def test_renders_seeks_and_switches_cameras(gpu_browser, overlay_url, out_dir):
    ctx, page, errors, requests = open_scene(gpu_browser, overlay_url)
    try:
        assert page.evaluate("() => window.__whyline.scene()") == {"cam": "wide", "cf": "cf_000077", "rendered": True}
        assert page.evaluate("() => window.__whyline.debug().clock") <= BRANCH   # opens before the branch point
        page.evaluate("(t) => { window.__whyline.pause(true); window.__whyline.seek(t); }", BRANCH + 6000)
        page.wait_for_function(f"() => window.__whyline.debug().clock === {BRANCH + 6000}")
        page.wait_for_selector("[data-testid=r3d-swing]", timeout=3000)
        assert page.get_by_test_id("r3d-provenance").inner_text() == "n = 200, 8 s, seed 4242"
        assert page.get_by_test_id("r3d-swing").get_attribute("data-progress") == "0.75"   # 6 s of the 8 s fan
        page.wait_for_timeout(1500)                                                         # camera eases in
        page.screenshot(path=str(out_dir / "replay3d_wide.png"))
        page.evaluate("() => window.__whyline.camera('player')")
        page.wait_for_function("() => window.__whyline.scene().cam === 'player'")
        assert page.locator(".r3d-stage").get_attribute("data-cam") == "player"
        page.wait_for_timeout(1500)
        page.screenshot(path=str(out_dir / "replay3d_player.png"))
        page.keyboard.press("c")                                                            # back to wide
        page.wait_for_function("() => window.__whyline.scene().cam === 'wide'")
        # the scene is procedural: nothing but the page, its bundles, league.json and fixtures is fetched
        external = [u for u in requests if not u.startswith(overlay_url.rsplit("/", 1)[0])]
        assert not external, external
        assert not any(u.endswith((".glb", ".gltf", ".fbx", ".obj", ".hdr", ".ktx2")) for u in requests)
        assert not errors, errors
    finally:
        ctx.close()


def test_20s_records_at_30fps(gpu_browser, overlay_url):
    ctx, page, errors, _ = open_scene(gpu_browser, overlay_url, "&ghost=full")
    try:
        page.evaluate("(t) => window.__whyline.seek(t)", BRANCH - 2000)                    # playing through the branch
        started = time.monotonic()
        page.wait_for_timeout(RECORD_S * 1000)
        fps = page.evaluate(f"() => window.__whyline.fps({RECORD_S * 1000})")
        print(f"\n/replay3d at 1920x1080, DPR 1, 200 ghost paths: {fps:.1f} fps over {time.monotonic() - started:.1f} s")
        assert fps >= FPS_MIN
        assert not errors, errors
    finally:
        ctx.close()
