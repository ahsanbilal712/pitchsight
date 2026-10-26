"""Overlay viewer modes, heatmap, threat front and referee lines.

The same fixture moment is rendered in analyst, casual and player_cam; the layers each mode draws must differ in
exactly these ways: analyst adds heatmap and threat front, casual drops heatmap, threat front and
ticker, player_cam adds the player trail and the player tag.
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
READY = "() => window.__whyline && window.__whyline.ready === true"
MOMENT = 1_878_600        # c_000912 on screen (pc_000412 snapshot, ghost futures), oracle p_shot 0.14 from 31:18
REFEREE = 1_900_700       # c_000913 referee_line from 31:40, fully drawn after 0.6 s
PID = "p_017"
MODES_DIR = ROOT / "apps" / "overlay" / "src" / "modes"


def to_canvas(x: float, y: float) -> tuple[int, int]:
    bw, bh = 1920 - 2 * 96, 1080 - 2 * 54
    scale = min(bw / 105, bh / 68)
    left, top = 96 + (bw - 105 * scale) / 2, 54 + (bh - 68 * scale) / 2
    return round(left + x * scale), round(top + (68 - y) * scale)


def open_mode(page, url, mode, t_ms, play_ms=0):
    page.goto(f"{url}?fixture=1&record=1&mode={mode}&player={PID}")
    page.wait_for_function(READY, timeout=5000)
    page.evaluate("(t) => { window.__whyline.pause(true); window.__whyline.seek(t); }", t_ms - play_ms)
    page.wait_for_function(f"() => window.__whyline.debug().clock === {t_ms - play_ms}", timeout=2000)
    if play_ms:                                                  # let the trail collect positions
        page.evaluate("() => window.__whyline.pause(false)")
        page.wait_for_function(f"() => window.__whyline.debug().clock >= {t_ms}", timeout=5000)
        page.evaluate("() => window.__whyline.pause(true)")
    page.evaluate("""(pid) => window.__whyline.inject({type: 'cue', payload: {cue_id: 'c_900100', t_in_ms: 0,
        t_out_ms: 9e9, layer: 'ticker', kind: 'milestone', priority: 0.5, clock: '31:18',
        targets: {modes: ['analyst', 'casual', 'player_cam'], clubs: ['any'], players: [pid]},
        text: {headline: 'Okafor: 5th shot of the night', body: ''}}})""", PID)
    page.wait_for_timeout(400)                                   # doc fetch, entry animations, a few frames


def layers_drawn(page) -> dict:
    stats = page.evaluate("() => window.__whyline.layerStats()")
    return {
        "heatmap": stats.get("heatmap", {}).get("drawn", 0) == 1,
        "threat_front": stats.get("threat_front", {}).get("drawn", 0) == 1,
        "ghost_trail": stats.get("ghost_trail", {}).get("paths", 0) == 200,
        "player_trail": stats.get("player_trail", {}).get("points", 0) > 1,
        "ticker": page.locator("[data-testid=ticker]").count() == 1,
        "player_cam_tag": page.locator(f".player-tag[data-cue-id=cam_{PID}]").count() == 1,
        "lower_third": page.locator(".lower-third[data-cue-id=c_000912]").count() == 1,
    }


def test_modes_differ_in_exactly_the_listed_layers(page, overlay_url, out_dir):
    seen = {}
    for mode in ("analyst", "casual", "player_cam"):
        open_mode(page, overlay_url, mode, MOMENT, play_ms=1500 if mode == "player_cam" else 0)
        seen[mode] = layers_drawn(page)
        page.screenshot(path=str(out_dir / f"mode_{mode}.png"))
        print(f"\n{mode}: {sorted(k for k, v in seen[mode].items() if v)}")
    common = {"ghost_trail": True, "lower_third": True}
    assert seen["analyst"] == {**common, "heatmap": True, "threat_front": True, "ticker": True,
                               "player_trail": False, "player_cam_tag": False}
    assert seen["casual"] == {**common, "heatmap": False, "threat_front": False, "ticker": False,
                              "player_trail": False, "player_cam_tag": False}
    assert seen["player_cam"] == {**common, "heatmap": False, "threat_front": False, "ticker": True,
                                  "player_trail": True, "player_cam_tag": True}
    diff = lambda a, b: {k for k in seen[a] if seen[a][k] != seen[b][k]}  # noqa: E731
    assert diff("analyst", "casual") == {"heatmap", "threat_front", "ticker"}
    assert diff("analyst", "player_cam") == {"heatmap", "threat_front", "player_trail", "player_cam_tag"}
    assert not page.errors, page.errors


def test_casual_shows_only_its_kinds(page, overlay_url):
    open_mode(page, overlay_url, "casual", MOMENT)
    page.evaluate("""() => window.__whyline.inject({type: 'cue', payload: {cue_id: 'c_900101', t_in_ms: 0,
        t_out_ms: 9e9, layer: 'lower_third', kind: 'state_change', priority: 1, clock: '31:18',
        targets: {modes: ['analyst', 'casual'], clubs: ['any'], players: []},
        text: {headline: 'The match turns chaotic', body: ''}}})""")
    page.wait_for_timeout(300)
    visible = page.evaluate("() => window.__whyline.debug().visibleCues")
    assert "c_900101" not in visible and "c_000912" in visible   # state_change is analyst-only
    open_mode(page, overlay_url, "analyst", MOMENT)
    page.evaluate("""() => window.__whyline.inject({type: 'cue', payload: {cue_id: 'c_900101', t_in_ms: 0,
        t_out_ms: 9e9, layer: 'lower_third', kind: 'state_change', priority: 1, clock: '31:18',
        targets: {modes: ['analyst', 'casual'], clubs: ['any'], players: []},
        text: {headline: 'The match turns chaotic', body: ''}}})""")
    page.wait_for_function("() => window.__whyline.debug().visibleCues.includes('c_900101')", timeout=1000)


def test_mode_kinds_mirror_budgets():
    budgets = yaml.safe_load((ROOT / "config" / "budgets.yaml").read_text())["director"]["modes"]
    for mode, file in (("analyst", "analyst.ts"), ("casual", "casual.ts"), ("player_cam", "playerCamConfig.ts")):
        src = (MODES_DIR / file).read_text()
        kinds = re.findall(r'"([a-z_]+)"', re.search(r"kinds:\s*\[(.*?)\]", src, re.S).group(1))
        assert kinds == budgets[mode]["kinds"], mode
        for flag, key in (("heatmap", "heatmap"), ("threatFront", "threat_front")):
            want = bool(budgets[mode].get(key, False))
            assert re.search(rf"{flag}: {str(want).lower()}", src), (mode, flag)


def test_referee_line_draws_in_metres_with_margin_label(page, overlay_url, out_dir):
    open_mode(page, overlay_url, "casual", REFEREE)
    stats = page.evaluate("() => window.__whyline.layerStats().referee_lines")
    assert stats == {"lines": 2, "progress": 1, "margin_m": 0.4}
    for x in (88.2, 88.6):                                       # yellow at the lines' positions in metres
        px = to_canvas(x, 20)
        r, g, b, _ = page.evaluate("""([x, y]) => Array.from(document.querySelector('canvas.pitch2d')
            .getContext('2d').getImageData(x, y, 1, 1).data)""", list(px))
        assert r > 200 and g > 180 and b < 120, (x, (r, g, b))
    assert "Onside by 0.4 m." in page.locator(".lower-third[data-cue-id=c_000913]").inner_text()
    page.screenshot(path=str(out_dir / "referee_lines.png"))
    open_mode(page, overlay_url, "casual", REFEREE - 400)        # mid-animation: drawn over 0.6 s
    progress = page.evaluate("() => window.__whyline.layerStats().referee_lines.progress")
    assert abs(progress - 0.5) < 0.02


def test_heatmap_redraw_under_8ms_p95(page, overlay_url):
    open_mode(page, overlay_url, "analyst", MOMENT)
    assert page.evaluate("() => window.__whyline.layerStats().heatmap.drawn") == 1
    page.evaluate("() => performance.clearMeasures('pitch2d-draw')")
    page.wait_for_function("() => performance.getEntriesByName('pitch2d-draw', 'measure').length >= 300",
                           timeout=20000)
    durations = sorted(page.evaluate(
        "() => performance.getEntriesByName('pitch2d-draw', 'measure').slice(0, 300).map(m => m.duration)"))
    p95 = durations[int(0.95 * (len(durations) - 1))]
    build = page.evaluate("() => window.__whyline.layerStats().heatmap.build_ms")
    print(f"\nanalyst frame with heatmap, threat front and 200 ghosts: p95 {p95:.2f} ms; grid image built in "
          f"{build:.2f} ms")
    assert page.evaluate("() => window.__whyline.layerStats().heatmap.drawn") == 1
    assert p95 < 8.0 and build < 8.0


def test_single_offside_line_labels_the_claimed_margin(page, overlay_url):
    """The golden offside call carries one line (the offside line); the margin label comes from its verified
    metres claim."""
    open_mode(page, overlay_url, "casual", REFEREE)
    page.evaluate("""() => window.__whyline.inject({type: 'cue', payload: {cue_id: 'c_900200', t_in_ms: 1900000,
        t_out_ms: 1908000, layer: 'referee_line', kind: 'fourth_official', priority: 1, clock: '31:40',
        targets: {modes: ['casual'], clubs: ['any'], players: []},
        text: {headline: 'Offside: 1.1 m', body: ''}, graphics: {lines: [[[30.17, 0], [30.17, 68]]]},
        explain: {why: '', claims: [{text: '1.1 m', kind: 'number', value: 1.1, unit: 'metres',
                                      evidence_ids: ['e_8816'], verified: true}]}}})""")
    page.wait_for_function("() => window.__whyline.layerStats().referee_lines.margin_m === 1.1", timeout=2000)
