"""Overlay DOM components: lower-third, score bug, chaos meter, player tags, ticker (T-023)."""

import json
import urllib.request
from pathlib import Path

import pytest

FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "stream" / "sample_stream.jsonl"

READY = "() => window.__whyline && window.__whyline.ready === true"
CUE_IN, CUE_OUT = 1_878_200, 1_886_200            # the cue.schema.json example c_000912 (31:18-31:26)
LT = ".lower-third[data-cue-id=c_000912][data-state=in]"

# schema maximum lengths with wide letters, in words so they can wrap like real copy
HEADLINE_MAX = ("WWWWWW MMMMMM " * 5)[:60]
BODY_MAX = ("Mmmmmm Wwwwww 0.31 xG, 27% win chance. " * 8)[:279] + "."


def to_canvas(x: float, y: float) -> tuple[float, float]:
    """Pitch2D transform (same as tests/apps/test_pitch2d.py): 105 x 68 m in the title-safe box, y flipped."""
    bw, bh = 1920 - 2 * 96, 1080 - 2 * 54
    scale = min(bw / 105, bh / 68)
    left, top = 96 + (bw - 105 * scale) / 2, 54 + (bh - 68 * scale) / 2
    return left + x * scale, top + (68 - y) * scale


def frame_at(t_ms: int) -> dict:
    for line in FIXTURE.read_text().splitlines():
        msg = json.loads(line)
        if msg["type"] == "tracking_frame" and msg["payload"]["t_ms"] == t_ms:
            return msg["payload"]
    raise KeyError(t_ms)


def open_fixture(page, url, t_ms):
    page.goto(f"{url}?fixture=1&record=1")
    page.wait_for_function(READY, timeout=5000)
    seek(page, t_ms)


def seek(page, t_ms):
    page.evaluate("(t) => { window.__whyline.pause(true); window.__whyline.seek(t); }", t_ms)
    page.wait_for_function(f"() => window.__whyline.debug().clock === {t_ms}", timeout=2000)


def cue(cue_id, layer, kind, t_in, t_out, headline, body="", players=()):
    return {"type": "cue", "payload": {
        "schema_version": "1.0.0", "cue_id": cue_id, "match_id": "m_4242", "moment_id": None,
        "t_in_ms": t_in, "t_out_ms": t_out, "clock": "31:20", "period": 1, "layer": layer, "priority": 0.9,
        "kind": kind, "targets": {"modes": ["analyst"], "clubs": ["any"], "players": list(players)},
        "text": {"headline": headline, "body": body}, "explain": {"why": "", "claims": []}, "verified": False,
        "producer_status": "auto", "provenance": {"mode": "replay", "agent_path": [], "trace_id": "t"}}}


def overflow(page, selector):
    """Elements under `selector` whose content is larger than their box, or whose box leaves the stage."""
    return page.evaluate("""(sel) => Array.from(document.querySelectorAll(sel)).flatMap((el) => {
        const r = el.getBoundingClientRect();
        const bad = [];
        if (el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1)
          bad.push(`${el.className}: content ${el.scrollWidth}x${el.scrollHeight} > box ${el.clientWidth}x${el.clientHeight}`);
        if (r.left < 0 || r.top < 0 || r.right > 1920 || r.bottom > 1080)
          bad.push(`${el.className}: off stage ${JSON.stringify(r)}`);
        return bad;
    })""", selector)


# ---------------------------------------------------------------- lower-third
def test_cue_enters_at_t_in_and_leaves_at_t_out(page, overlay_url):
    open_fixture(page, overlay_url, CUE_IN - 100)
    assert page.locator(LT).count() == 0
    seek(page, CUE_IN)
    page.wait_for_selector(LT, timeout=1000)
    assert page.locator(f"{LT} .lt-headline").inner_text() == "Okafor shoots. Reyes was free."
    assert "VERIFIED" in page.locator(f"{LT} [data-testid=lt-verified]").inner_text().upper()
    seek(page, CUE_OUT - 100)
    assert page.locator(LT).count() == 1
    seek(page, CUE_OUT)
    page.wait_for_selector(".lower-third[data-cue-id=c_000912]", state="detached", timeout=1000)
    assert not page.errors, page.errors


def test_lower_third_slides_in_over_300ms(page, overlay_url):
    open_fixture(page, overlay_url, CUE_IN)
    page.wait_for_selector(LT, timeout=1000)
    anim = page.evaluate(f"() => getComputedStyle(document.querySelector('{LT}')).animationDuration")
    assert anim == "0.3s"


def test_text_never_overflows_at_schema_maximum(page, overlay_url, out_dir):
    open_fixture(page, overlay_url, 1_875_000)
    assert len(HEADLINE_MAX) == 60 and len(BODY_MAX) == 280
    page.evaluate("(m) => window.__whyline.inject(m)",
                  cue("c_900001", "lower_third", "big_chance", 1_870_000, 1_880_000, HEADLINE_MAX, BODY_MAX))
    page.evaluate("(m) => window.__whyline.inject(m)",
                  cue("c_900002", "ticker", "milestone", 1_870_000, 1_880_000, "W" * 60))
    page.evaluate("(m) => window.__whyline.inject(m)",
                  cue("c_900003", "player_tag", "player_tag", 1_870_000, 1_880_000, "M" * 60, players=["p_031"]))
    page.wait_for_selector(".lower-third[data-cue-id=c_900001][data-state=in]", timeout=1000)
    page.wait_for_timeout(400)                                  # entry animations finish
    assert page.locator(".lower-third[data-cue-id=c_900001] .lt-headline").inner_text() == HEADLINE_MAX
    assert page.locator(".lower-third[data-cue-id=c_900001] .lt-body").inner_text() == BODY_MAX
    bad = overflow(page, ".lt-headline, .lt-body, .lower-third, .ticker, .tk-items li, .score-bug, .chaos-meter")
    bad += overflow(page, ".player-tag > span")
    page.screenshot(path=str(out_dir / "overlay_components_max.png"))
    assert not bad, bad
    sizes = page.evaluate("""() => ['.lt-headline', '.lt-body'].map((s) =>
        parseFloat(getComputedStyle(document.querySelector('.lower-third[data-cue-id=c_900001] ' + s)).fontSize))""")
    print(f"\nfitted font sizes at schema max: headline {sizes[0]} px, body {sizes[1]} px")
    assert sizes[0] >= 22 and sizes[1] >= 15


# ---------------------------------------------------------------- chaos meter
def test_chaos_meter_follows_facts(page, overlay_url, out_dir):
    open_fixture(page, overlay_url, 1_875_000)                  # f_000301: 67.4, state still Transitional
    meter = page.get_by_test_id("chaos-meter")
    assert page.get_by_test_id("chaos-value").inner_text() == "67"
    assert page.get_by_test_id("chaos-state").inner_text() == "Transitional"
    seek(page, 1_890_000)                                       # state machine turned Chaotic at 31:26
    assert page.get_by_test_id("chaos-value").inner_text() == "69"
    assert page.get_by_test_id("chaos-state").inner_text() == "Chaotic"
    assert meter.get_attribute("data-state") == "Chaotic"
    page.screenshot(path=str(out_dir / "overlay_components.png"))
    page.evaluate("(m) => window.__whyline.inject(m)", {"type": "fact", "payload": {
        "id": "f_999999", "t_ms": 1_890_000, "name": "chaos_state", "value": "Settled", "kind": "state"}})
    page.wait_for_function("() => document.querySelector('[data-testid=chaos-meter]').dataset.state === 'Settled'")


# ---------------------------------------------------------------- player tags and ticker
def test_player_tag_is_pinned_to_its_player(page, overlay_url):
    open_fixture(page, overlay_url, 1_875_000)
    page.evaluate("(m) => window.__whyline.inject(m)",
                  cue("c_900004", "player_tag", "player_tag", 1_870_000, 1_880_000, "32 km/h", players=["p_031"]))
    tag = page.locator(".player-tag[data-cue-id=c_900004][data-state=in]")
    tag.wait_for(state="attached", timeout=1000)  # the anchor is 0x0; its spans carry the size
    assert "32 km/h" in tag.inner_text() and "Reyes" in tag.inner_text()
    page.wait_for_timeout(200)                                  # 100 ms position transition
    box = tag.bounding_box()
    # Reyes is row 10 in the fixture; his canvas position at 31:15 from the same transform as Pitch2D
    x, y = to_canvas(*frame_at(1_875_000)["p"][10][:2])
    assert abs(box["x"] - x) <= 2 and abs(box["y"] - y) <= 2, (box, x, y)


def test_ticker_shows_ticker_cues(page, overlay_url):
    open_fixture(page, overlay_url, 1_875_000)
    assert page.get_by_test_id("ticker").get_attribute("data-empty") == "true"
    page.evaluate("(m) => window.__whyline.inject(m)",
                  cue("c_900005", "ticker", "tempo_shift", 1_870_000, 1_880_000, "Ironvale slow it down: 4.1 passes/min"))
    page.wait_for_selector(".tk-items li[data-cue-id=c_900005][data-state=in]", timeout=1000)
    assert page.get_by_test_id("ticker").get_attribute("data-empty") == "false"


# ---------------------------------------------------------------- score bug over the API
def control(port, **body):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/replay/control", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.load(r)


@pytest.mark.parametrize("speed", [10])
def test_score_bug_follows_goal_events(page, overlay_url, api_port, speed):
    control(api_port, action="speed", value=1)
    control(api_port, action="play")
    page.goto(f"{overlay_url}?record=1&api=127.0.0.1:{api_port}")
    page.wait_for_function(READY, timeout=5000)
    control(api_port, action="seek", value="39:00")
    page.wait_for_function("() => window.__whyline.debug().clock >= 2340000", timeout=3000)
    assert page.get_by_test_id("score").inner_text().replace("\n", "") == "0–0"
    assert page.get_by_test_id("sb-home").inner_text() == "VER"
    assert page.get_by_test_id("sb-away").inner_text() == "IRO"
    control(api_port, action="speed", value=speed)              # the 39:05 goal arrives as an event
    page.wait_for_function("() => window.__whyline.debug().clock >= 2347000", timeout=5000)
    control(api_port, action="speed", value=1)
    assert page.get_by_test_id("score").inner_text().replace("\n", "") == "0–1"
    assert page.get_by_test_id("score").get_attribute("data-goal") == "true"   # flashes after the goal
    assert page.get_by_test_id("score-clock").inner_text().startswith("39:")
    assert not page.errors, page.errors
