"""Pitch2D draws in event-schema coordinates, flipped to canvas, under 8 ms p95 per frame."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "stream" / "sample_stream.jsonl"
READY = "() => window.__whyline && window.__whyline.ready === true"
SAFE_X, SAFE_Y, STAGE_W, STAGE_H = 96, 54, 1920, 1080


def to_canvas(x: float, y: float) -> tuple[int, int]:
    """Reference transform: fit 105 x 68 m into the title-safe box, origin bottom-left, y flipped."""
    bw, bh = STAGE_W - 2 * SAFE_X, STAGE_H - 2 * SAFE_Y
    scale = min(bw / 105, bh / 68)
    left, top = SAFE_X + (bw - 105 * scale) / 2, SAFE_Y + (bh - 68 * scale) / 2
    return round(left + x * scale), round(top + (68 - y) * scale)


def frame_at(t_ms: int) -> dict:
    for line in FIXTURE.read_text().splitlines():
        msg = json.loads(line)
        if msg["type"] == "tracking_frame" and msg["payload"]["t_ms"] == t_ms:
            return msg["payload"]
    raise KeyError(t_ms)


def pixel(page, x: int, y: int) -> list[int]:
    return page.evaluate(
        "([x, y]) => Array.from(document.querySelector('canvas.pitch2d').getContext('2d')"
        ".getImageData(x, y, 1, 1).data)", [x, y])


def test_coordinates_are_flipped_to_canvas(page, overlay_url):
    page.goto(f"{overlay_url}?fixture=1&record=1")
    page.wait_for_function(READY, timeout=5000)
    t_ms = 1873000                                              # Silva's pass e_8809 rolling, ball on the ground
    page.evaluate("(t) => { window.__whyline.pause(true); window.__whyline.seek(t); }", t_ms)
    page.wait_for_function(f"() => window.__whyline.debug().clock === {t_ms}")
    page.wait_for_timeout(300)                                  # interpolation settles on the frame
    f = frame_at(t_ms)
    bx, by = f["p"][22][0], f["p"][22][1]
    assert f["ball_z"] <= 0.12
    r, g, b, _ = pixel(page, *to_canvas(bx, by))
    assert min(r, g, b) > 200, f"ball pixel at ({bx}, {by}) is {(r, g, b)}"
    r, g, b, _ = pixel(page, *to_canvas(bx, 68 - by))           # where an unflipped renderer would draw it
    assert min(r, g, b) < 200


def test_p95_draw_time_under_8ms(page, overlay_url, out_dir):
    page.goto(f"{overlay_url}?fixture=1&record=1")
    page.wait_for_function(READY, timeout=5000)
    page.evaluate("() => window.__whyline.seek('31:10')")
    page.evaluate("() => performance.clearMeasures('pitch2d-draw')")
    page.wait_for_function("() => performance.getEntriesByName('pitch2d-draw', 'measure').length >= 300",
                           timeout=20000)
    durations = sorted(page.evaluate(
        "() => performance.getEntriesByName('pitch2d-draw', 'measure').slice(0, 300).map(m => m.duration)"))
    p95 = durations[int(0.95 * (len(durations) - 1))]
    print(f"\nPitch2D draw over {len(durations)} frames: p50 {durations[len(durations) // 2]:.2f} ms, p95 {p95:.2f} ms")
    page.screenshot(path=str(out_dir / "pitch2d.png"))
    assert (out_dir / "pitch2d.png").stat().st_size > 10_000
    assert p95 < 8.0
    assert not page.errors, page.errors
