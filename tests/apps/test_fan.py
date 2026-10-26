"""Fan app: viewer profile, server-side filtered feed per mode, storage, veto."""

import copy
import json
import time
import urllib.request
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
READY = "() => window.__whyline && window.__whyline.ready === true"
SCHEMA = json.loads((ROOT / "schemas" / "viewer_profile.schema.json").read_text())
MODES = yaml.safe_load((ROOT / "config" / "budgets.yaml").read_text())["director"]["modes"]
LAYER = {"sliding_doors": "lower_third", "state_change": "lower_third", "big_chance": "lower_third",
         "goal": "lower_third", "tempo_shift": "ticker", "player_tag": "player_tag", "milestone": "ticker",
         "pressing_trap": "pitch_overlay", "fourth_official": "referee_line", "oracle": "threat_front",
         "dugout": "options_card", "decision_index": "player_tag", "recap": "recap_card", "fast_line": "ticker"}
PHONE = {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 1}


def post(base: str, path: str, body: dict) -> dict:
    req = urllib.request.Request(f"{base}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.load(r)


def health(base: str) -> dict:
    with urllib.request.urlopen(f"{base}/health", timeout=5) as r:
        return json.load(r)


@pytest.fixture(scope="module")
def on_air(api_server):
    """One cue of every kind on air at 70:00, targeted at every mode: only the mode's kinds may filter."""
    post(api_server.base, "/replay/control", {"action": "speed", "value": 1})
    post(api_server.base, "/replay/control", {"action": "play"})
    post(api_server.base, "/replay/control", {"action": "seek", "value": "70:00"})
    deadline = time.monotonic() + 3
    while health(api_server.base)["stream_t_ms"] < 4_200_000:
        assert time.monotonic() < deadline
        time.sleep(0.02)
    now = health(api_server.base)["stream_t_ms"]
    base = json.loads((ROOT / "schemas" / "cue.schema.json").read_text())["examples"][0]
    ids = {}
    for n, kind in enumerate(LAYER):
        cue = copy.deepcopy(base)
        cue_id = f"c_{800_000 + n:06d}"
        cue.update(cue_id=cue_id, kind=kind, layer=LAYER[kind], t_in_ms=now - 200, t_out_ms=now + 600_000,
                   moment_id=None, clock="70:00")
        cue["explain"]["counterfactual_id"] = None
        cue["text"]["headline"] = f"{kind.replace('_', ' ').capitalize()} at 70:00"
        cue["targets"] = {"modes": ["analyst", "casual", "player_cam", "studio"], "clubs": ["any"],
                          "players": ["p_031"]}
        api_server.bb.put("cues", cue)
        ids[kind] = cue_id
    return ids


def open_fan(browser, fan_url, port, query="", init_script=None):
    ctx = browser.new_context(**PHONE)
    if init_script:
        ctx.add_init_script(init_script)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.errors = errors
    page.goto(f"{fan_url}?api=127.0.0.1:{port}{query}")
    page.wait_for_function(READY, timeout=5000)
    return ctx, page


def kinds_after(page, want: set[str]) -> set[str]:
    page.wait_for_function(f"() => window.__whyline.debug().kinds.length >= {len(want)}", timeout=5000)
    page.wait_for_timeout(300)                                   # nothing else arrives
    return set(page.evaluate("() => window.__whyline.debug().kinds"))


def test_casual_and_analyst_get_their_budget_kinds(browser, fan_url, api_server, on_air, out_dir):
    casual, analyst = set(MODES["casual"]["kinds"]), set(MODES["analyst"]["kinds"])
    ctx, page = open_fan(browser, fan_url, api_server.port)
    try:
        assert page.get_by_test_id("mode-casual").get_attribute("aria-checked") == "true"   # default profile
        got = kinds_after(page, casual)
        print(f"\ncasual received {len(got)} kinds: {sorted(got)}")
        assert got == casual
        cards = page.locator("[data-testid=cue-feed] .cue-card")
        assert cards.count() == len(casual)                     # every casual kind is a feed card
        assert page.locator(".cue-card p").count() == 0          # casual: one sentence, no body
        page.screenshot(path=str(out_dir / "fan_casual.png"))

        page.get_by_test_id("mode-analyst").click()
        page.wait_for_function("() => window.__whyline.debug().mode === 'analyst'")
        got = kinds_after(page, analyst)
        print(f"analyst received {len(got)} kinds: {sorted(got)}")
        assert got == analyst
        assert page.locator("[data-testid=moment-cards] .moment-card").count() == 2   # dugout + recap
        page.screenshot(path=str(out_dir / "fan_analyst.png"))

        page.get_by_test_id("mode-casual").click()
        page.wait_for_function("() => window.__whyline.debug().mode === 'casual'")
        assert kinds_after(page, casual) == casual
        assert not page.errors, page.errors
    finally:
        ctx.close()


def test_profile_is_schema_valid_and_stored(browser, fan_url, api_server):
    ctx, page = open_fan(browser, fan_url, api_server.port)
    try:
        page.get_by_test_id("mode-player_cam").click()
        page.get_by_test_id("club").select_option("home")
        page.get_by_test_id("metric").select_option("decision_index")
        page.wait_for_function("() => document.querySelectorAll('[data-testid=player] option').length === 22")
        player = page.locator("[data-testid=player] option").nth(9).get_attribute("value")  # from the lineup now
        page.get_by_test_id("player").select_option(player)
        page.get_by_test_id("high-contrast").check()
        page.wait_for_function("() => document.documentElement.dataset.contrast === 'high'")
        stored = json.loads(page.evaluate("() => localStorage.getItem('whyline.fan.profile')"))
        jsonschema.validate(stored, SCHEMA)
        assert {k: stored[k] for k in ("mode", "club", "player", "metric", "high_contrast")} == {
            "mode": "player_cam", "club": "home", "player": player, "metric": "decision_index",
            "high_contrast": True}
        page.reload()                                            # the stored profile comes back
        page.wait_for_function(READY, timeout=5000)
        assert page.get_by_test_id("mode-player_cam").get_attribute("aria-checked") == "true"
        page.wait_for_function("() => document.querySelectorAll('[data-testid=player] option').length === 22")
        assert page.get_by_test_id("player").input_value() == player
    finally:
        ctx.close()


def test_works_when_storage_throws(browser, fan_url, api_server, on_air):
    blocked = """for (const m of ['getItem', 'setItem']) Storage.prototype[m] = () => {
        throw new DOMException('blocked', 'SecurityError'); };"""
    ctx, page = open_fan(browser, fan_url, api_server.port, init_script=blocked)
    try:
        assert page.locator(".phone").get_attribute("data-stored") == "false"
        page.get_by_test_id("mode-analyst").click()
        assert kinds_after(page, set(MODES["analyst"]["kinds"])) == set(MODES["analyst"]["kinds"])
        assert not page.errors, page.errors
    finally:
        ctx.close()


def test_veto_removes_the_fan_card_within_200ms(browser, fan_url, api_server, on_air):
    ctx, page = open_fan(browser, fan_url, api_server.port, query="&mode=casual")
    cue_id = on_air["milestone"]
    try:
        page.wait_for_selector(f".cue-card[data-cue-id={cue_id}]", timeout=5000)
        page.evaluate("""(id) => { window.__gone = null; new MutationObserver(() => {
            if (!window.__gone && !document.querySelector(`.cue-card[data-cue-id=${id}]`)) window.__gone = Date.now();
            }).observe(document.body, {subtree: true, childList: true}); }""", cue_id)
        sent = time.time() * 1000
        post(api_server.base, "/producer/decision", {"request_id": cue_id, "decision": "vetoed"})
        page.wait_for_function("() => window.__gone !== null", timeout=2000)
        took = page.evaluate("() => window.__gone") - sent
        print(f"\nveto -> fan card removed: {took:.0f} ms")
        assert took < 200
    finally:
        ctx.close()
