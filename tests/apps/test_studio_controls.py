"""Studio producer panel and demo controls (T-035).

Approve, veto and hold post /producer/decision; vetoing an on-air cue removes it from the overlay within 200 ms
(two pages: the studio clicks, the overlay's lower-third leaves); kill posts /demo/kill; speed and seek post
/replay/control.
"""

import copy
import json
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
READY = "() => window.__whyline && window.__whyline.ready === true"
VETO_LIMIT_MS = 200


def get(base: str, path: str) -> dict:
    with urllib.request.urlopen(f"{base}{path}", timeout=5) as r:
        return json.load(r)


def control(base: str, **body) -> dict:
    req = urllib.request.Request(f"{base}/replay/control", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.load(r)


def cue_example(cue_id: str, t_in: int, t_out: int) -> dict:
    cue = copy.deepcopy(json.loads((ROOT / "schemas" / "cue.schema.json").read_text())["examples"][0])
    cue.update(cue_id=cue_id, t_in_ms=t_in, t_out_ms=t_out, priority=1.0, moment_id=None)
    cue["explain"]["counterfactual_id"] = None
    cue["graphics"]["bar"] = None
    cue["text"]["headline"] = "Ironvale's press breaks."
    cue["targets"]["modes"] = ["analyst", "casual", "studio"]
    return cue


def seek_and_wait(base: str, clock: str, ms: int) -> None:
    control(base, action="speed", value=1)
    control(base, action="play")
    control(base, action="seek", value=clock)
    deadline = time.monotonic() + 3
    while get(base, "/health")["stream_t_ms"] < ms:
        assert time.monotonic() < deadline
        time.sleep(0.02)


def open_studio(browser, studio_url, port):
    ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
    page = ctx.new_page()
    page.goto(f"{studio_url}?api=127.0.0.1:{port}")
    page.wait_for_function(READY, timeout=5000)
    return ctx, page


def test_approve_veto_hold_post_decisions(browser, studio_url, api_server):
    tag = uuid.uuid4().hex[:6]
    ids = {d: f"req_{tag}_{d}" for d in ("approve", "veto", "hold")}
    ctx, studio = open_studio(browser, studio_url, api_server.port)
    try:
        for rid in ids.values():
            api_server.bb.put("requests", {"id": rid, "request_id": rid, "match_id": "m_4242",
                                           "cue": {**cue_example("c_000500", 0, 1), "kind": "recap"}})
        for rid in ids.values():
            studio.locator(f"[data-request-id={rid}]").wait_for(timeout=3000)
        studio.locator(f"[data-request-id={ids['approve']}] button.approve").click()
        studio.locator(f"[data-request-id={ids['veto']}] button.veto").click()
        studio.locator(f"[data-request-id={ids['hold']}] button.hold").click()
        studio.locator(f"[data-request-id={ids['approve']}]").wait_for(state="detached", timeout=2000)
        studio.locator(f"[data-request-id={ids['veto']}]").wait_for(state="detached", timeout=2000)
        studio.wait_for_selector(f"[data-request-id={ids['hold']}][data-held=true]", timeout=2000)
        got = {d: api_server.bb.get("decisions", rid)["decision"] for d, rid in ids.items()}
        assert got == {"approve": "approved", "veto": "vetoed", "hold": "held"}
    finally:
        ctx.close()


def test_decision_made_elsewhere_clears_the_pending_card(browser, studio_url, api_server):
    """A veto from another studio or the demo runner (control.decide) removes the request from every studio's
    producer panel (v1 frame review: the recap stayed 'pending' after the demo veto)."""
    from api.control import decide
    rid = f"req_{uuid.uuid4().hex[:6]}_elsewhere"
    ctx, studio = open_studio(browser, studio_url, api_server.port)
    try:
        api_server.bb.put("requests", {"id": rid, "request_id": rid, "match_id": "m_4242",
                                       "cue": {**cue_example("c_000501", 0, 1), "kind": "recap"}})
        studio.locator(f"[data-request-id={rid}]").wait_for(timeout=3000)
        decide(api_server.bb, api_server.app.state.hub, rid, "vetoed", "m_4242")
        studio.locator(f"[data-request-id={rid}]").wait_for(state="detached", timeout=2000)
        doc = api_server.bb.get("requests", rid)                  # the newsroom then marks the request resolved
        api_server.bb.put("requests", {**doc, "status": "vetoed"})
        studio.wait_for_timeout(800)                                  # the watcher re-sends it: it must stay gone
        assert studio.locator(f"[data-request-id={rid}]").count() == 0
    finally:
        ctx.close()


def test_veto_of_on_air_cue_leaves_the_overlay_within_200ms(browser, studio_url, overlay_url, api_server, out_dir):
    seek_and_wait(api_server.base, "50:00", 3_000_000)
    now = get(api_server.base, "/health")["stream_t_ms"]
    cue_id = f"c_{700_000 + int(time.time()) % 99_999:06d}"
    api_server.bb.put("cues", cue_example(cue_id, now + 300, now + 60_000))
    octx = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
    overlay = octx.new_page()
    sctx, studio = open_studio(browser, studio_url, api_server.port)
    try:
        overlay.goto(f"{overlay_url}?record=1&api=127.0.0.1:{api_server.port}")
        overlay.wait_for_function(READY, timeout=5000)
        lt = f".lower-third[data-cue-id={cue_id}][data-state=in]"
        overlay.wait_for_selector(lt, timeout=5000)
        button = studio.locator(f"[data-on-air-cue={cue_id}] button.veto")
        button.wait_for(timeout=5000)
        studio.screenshot(path=str(out_dir / "studio_controls.png"))
        # both pages stamp Date.now(): the click in the studio, the lower-third leaving in the overlay
        overlay.evaluate("""(id) => { window.__gone = null; const done = () => {
            const el = document.querySelector(`.lower-third[data-cue-id=${id}]`);
            if (!window.__gone && (!el || el.dataset.state === 'out')) window.__gone = Date.now(); };
            new MutationObserver(done).observe(document.body, {subtree: true, childList: true, attributes: true}); }""",
                         cue_id)
        button.evaluate("b => b.addEventListener('click', () => { window.__clicked = Date.now(); }, {capture: true})")
        button.click()
        overlay.wait_for_function("() => window.__gone !== null", timeout=2000)
        clicked, gone = studio.evaluate("() => window.__clicked"), overlay.evaluate("() => window.__gone")
        print(f"\nveto click -> overlay lower-third leaving: {gone - clicked} ms")
        assert gone - clicked < VETO_LIMIT_MS
        studio.wait_for_selector(f"[data-on-air-cue={cue_id}]", state="detached", timeout=2000)
        row = studio.locator(f"[data-testid=cue-list] li[data-cue-id={cue_id}]")
        assert row.get_attribute("data-status") == "vetoed"
        assert api_server.bb.get("cues", cue_id)["producer_status"] == "vetoed"
    finally:
        octx.close()
        sctx.close()


def test_kill_speed_and_seek(browser, studio_url, api_server):
    ctx, studio = open_studio(browser, studio_url, api_server.port)
    try:
        with studio.expect_request(lambda r: r.url.endswith("/demo/kill") and r.method == "POST") as req:
            studio.get_by_test_id("kill").click()
        assert req.value.post_data_json == {"target": "newsroom"}
        studio.get_by_test_id("demo-note").wait_for(timeout=2000)
        assert "kill sent" in studio.get_by_test_id("demo-note").inner_text()

        with studio.expect_request(lambda r: r.url.endswith("/replay/control")) as req:
            studio.get_by_test_id("speed-5").click()
        assert req.value.post_data_json == {"action": "speed", "value": 5}
        studio.wait_for_function("() => document.querySelector('[data-testid=speed-5]').ariaPressed === 'true'")
        assert get(api_server.base, "/health")["clock"]["speed"] == 5
        studio.get_by_test_id("speed-1").click()

        studio.get_by_test_id("seek-input").fill("52:30")
        studio.get_by_test_id("seek").click()
        deadline = time.monotonic() + 3
        while not 3_150_000 <= get(api_server.base, "/health")["clock"]["t_ms"] < 3_153_000:
            assert time.monotonic() < deadline, get(api_server.base, "/health")
            time.sleep(0.02)
        studio.wait_for_function("() => window.__whyline.debug().clock >= 3150000", timeout=3000)
        assert get(api_server.base, "/health")["clock"]["speed"] == 1
    finally:
        ctx.close()
