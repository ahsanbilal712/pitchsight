"""Ghost trail (200 smoothed futures + the chosen alternative) and swing bar."""

import re

READY = "() => window.__whyline && window.__whyline.ready === true"
CUE_IN = 1_878_200                       # c_000912, explain.counterfactual_id = cf_000077
STATS = "() => window.__whyline.layerStats().ghost_trail || {}"


def open_at(page, url, t_ms):
    page.goto(f"{url}?fixture=1&record=1")
    page.wait_for_function(READY, timeout=5000)
    page.evaluate("(t) => { window.__whyline.pause(true); window.__whyline.seek(t); }", t_ms)
    page.wait_for_function(f"() => window.__whyline.debug().clock === {t_ms}", timeout=2000)


def test_200_paths_draw_under_8ms_p95(page, overlay_url, out_dir):
    open_at(page, overlay_url, CUE_IN + 1800)
    page.wait_for_function(f"() => ({STATS})().paths === 200", timeout=2000)
    stats = page.evaluate(STATS)
    assert stats["alpha"] == 1 and stats["chosen"] == 1
    # 9 points at 1 Hz over the 8 s horizon, smoothed into 10 samples per segment
    assert stats["pointsPerPath"] == 8 * 10 + 1
    page.evaluate("() => performance.clearMeasures('pitch2d-draw')")
    page.wait_for_function("() => performance.getEntriesByName('pitch2d-draw', 'measure').length >= 300",
                           timeout=20000)
    durations = sorted(page.evaluate(
        "() => performance.getEntriesByName('pitch2d-draw', 'measure').slice(0, 300).map(m => m.duration)"))
    p95 = durations[int(0.95 * (len(durations) - 1))]
    print(f"\nghost trail, {stats['paths']} paths: p50 {durations[len(durations) // 2]:.2f} ms, p95 {p95:.2f} ms")
    assert page.evaluate(STATS)["paths"] == 200               # still drawing 200 paths while measured
    # the measure is CPU-side canvas time; frame intervals show no frame is dropped either
    gaps = sorted(page.evaluate("""() => new Promise((done) => {
        const t = []; const step = (now) => { t.push(now); t.length > 301 ? done(t.slice(1).map((v, i) => v - t[i]))
        : requestAnimationFrame(step); }; requestAnimationFrame(step); })"""))
    print(f"rAF interval over 300 frames: p50 {gaps[150]:.1f} ms, p95 {gaps[int(0.95 * 299)]:.1f} ms")
    page.screenshot(path=str(out_dir / "ghost_trail.png"))
    assert p95 < 8.0
    assert not page.errors, page.errors


def test_ghost_fades_in_over_800ms(page, overlay_url):
    open_at(page, overlay_url, CUE_IN)
    page.wait_for_function(f"() => ({STATS})().alpha === 0", timeout=2000)
    assert page.evaluate(STATS)["paths"] == 0
    open_at(page, overlay_url, CUE_IN + 400)
    page.wait_for_function(f"() => ({STATS})().alpha > 0", timeout=2000)
    page.wait_for_timeout(250)                                  # the 100 ms interpolation from the previous frame settles
    assert abs(page.evaluate(STATS)["alpha"] - 0.5) < 0.01      # 400 ms into an 800 ms fade


def test_ghost_disappears_with_the_cue(page, overlay_url):
    open_at(page, overlay_url, 1_886_200)
    page.wait_for_function(f"() => ({STATS})().paths === 0", timeout=2000)


def test_swing_bar_prints_n_horizon_seed(page, overlay_url, out_dir):
    open_at(page, overlay_url, CUE_IN + 1800)
    bar = page.locator("[data-testid=swing-bar][data-state=in]")
    bar.wait_for(timeout=2000)
    assert page.get_by_test_id("swing-provenance").inner_text() == "n = 200, 8 s, seed 4242"
    assert re.fullmatch(r"n = \d+, [\d.]+ s, seed \d+", page.get_by_test_id("swing-provenance").inner_text())
    page.wait_for_function("() => document.querySelector('[data-testid=swing-number]').textContent === '51%'",
                           timeout=3000)                       # animated from 42% to 51%
    assert "42% → 51% (+9 pts)" in page.get_by_test_id("swing-delta").inner_text()
    assert "VERDANT WIN CHANCE" in bar.inner_text().upper()
    page.screenshot(path=str(out_dir / "swing_bar.png"))


def test_swing_bar_hidden_without_counterfactual(page, overlay_url):
    open_at(page, overlay_url, 1_870_000)
    cue = page.evaluate("""() => fetch('fixtures/sample_stream.jsonl').then(r => r.text()).then(t =>
        t.split('\\n').filter(Boolean).map(JSON.parse).find(m => m.type === 'cue'))""")
    cue["payload"].update({"cue_id": "c_900010", "t_in_ms": 1_869_000, "t_out_ms": 1_875_000})
    cue["payload"]["explain"]["counterfactual_id"] = "cf_999999"   # never streamed
    page.evaluate("(m) => window.__whyline.inject(m)", cue)
    page.wait_for_selector(".lower-third[data-cue-id=c_900010]", timeout=1000)
    assert page.locator("[data-testid=swing-bar]").count() == 0
