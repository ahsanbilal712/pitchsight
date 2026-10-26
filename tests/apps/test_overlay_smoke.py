"""The overlay shell plays the sample fixture and exposes the record-mode handle."""

import time

READY = "() => window.__whyline && window.__whyline.ready === true"


def test_fixture_playback_becomes_ready_within_5s(page, overlay_url):
    started = time.perf_counter()
    page.goto(f"{overlay_url}?fixture=1&record=1")
    page.wait_for_function(READY, timeout=5000)
    print(f"\nready after {time.perf_counter() - started:.2f} s")
    assert not page.errors, page.errors


def test_record_mode_hides_cursor_and_forces_dpr_1(page, overlay_url):
    page.goto(f"{overlay_url}?fixture=1&record=1")
    page.wait_for_function(READY, timeout=5000)
    handle = page.evaluate("() => ({record: window.__whyline.record, dpr: window.__whyline.dpr})")
    assert handle == {"record": True, "dpr": 1}
    cursor = page.evaluate("() => getComputedStyle(document.querySelector('.stage')).cursor")
    assert cursor == "none"


def test_seek_shows_the_cue_inside_its_window_only(page, overlay_url):
    page.goto(f"{overlay_url}?fixture=1&record=1")
    page.wait_for_function(READY, timeout=5000)
    page.evaluate("() => window.__whyline.seek('31:20')")
    page.wait_for_function("() => window.__whyline.debug().visibleCues.includes('c_000912')", timeout=2000)
    headline = page.locator(".lower-third[data-cue-id=c_000912] .lt-headline")
    assert headline.inner_text() == "Okafor shoots. Reyes was free."
    page.evaluate("() => window.__whyline.seek('31:30')")
    page.wait_for_function("() => window.__whyline.debug().visibleCues.length === 0", timeout=2000)


def test_playback_advances_on_the_10hz_clock(page, overlay_url):
    page.goto(f"{overlay_url}?fixture=1&record=1")
    page.wait_for_function(READY, timeout=5000)
    first = page.evaluate("() => window.__whyline.debug().clock")
    page.wait_for_timeout(1000)
    second = page.evaluate("() => window.__whyline.debug().clock")
    assert 700 <= second - first <= 1500, (first, second)
