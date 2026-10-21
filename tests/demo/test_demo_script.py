"""Demo script, runner, shot list and recorder (T-061)."""

import json
import socket
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from api.demo_runner import DemoRunner, load_script
from api.replay import ReplayClock
from blackboard import SqliteBlackboard
from demo.clocks import ClockError, clock_ms, fmt, load_moments, resolve
from demo.record_demo import Shot, load_shots, main

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "packages" / "demo" / "demo_script.yaml"
SHOTS = ROOT / "packages" / "demo" / "shot_list.yaml"
SAMPLE = ROOT / "tests" / "demo" / "data" / "golden_moments_sample.yaml"
BEATS = {"opener", "sliding_doors", "fourth_official", "panel_kill", "oracle_dugout", "split_modes",
         "architecture", "halftime"}                     # DEMO_MASTERPLAN §7 beats (T-061 brief)


# ---------------------------------------------------------------- demo_script.yaml
def test_demo_script_is_exactly_the_tech_plan_entries():
    rows = yaml.safe_load(SCRIPT.read_text())
    core = [{k: v for k, v in r.items() if k != "ref"} for r in rows]
    assert core == [
        {"at_clock": "44:10", "action": "kill", "target": "newsroom"},
        {"at_clock": "45:00+15s", "action": "veto", "cue_kind": "recap"},
        {"at_clock": "31:10", "action": "speed", "value": 1},
        {"at_clock": "33:00", "action": "speed", "value": 10},
    ]
    assert [a.at_ms for a in load_script(SCRIPT)] == [2_650_000, 2_715_000, 1_870_000, 1_980_000]


def test_demo_script_clocks_come_from_golden_moments():
    """Each entry with a `ref` must match golden_moments.yaml (T-039 writes it)."""
    moments = load_moments()                              # raises until the golden precompute has run
    for row in yaml.safe_load(SCRIPT.read_text()):
        if "ref" in row:
            assert resolve(row["ref"], moments) == resolve(row["at_clock"]), row


# ---------------------------------------------------------------- clocks
def test_clock_references():
    m = load_moments(SAMPLE)
    assert resolve("31:10") == 1_870_000 and resolve("45:00+15s") == 2_715_000 and resolve("90:00") == 5_400_000
    assert resolve("@sliding_doors-4s", m) == 1_870_000
    assert resolve("@fourth_official[0]+1s", m) == 1_901_000
    assert resolve("@kill+0:10", m) == 2_660_000
    with pytest.raises(ClockError):
        resolve("@nowhere", m)
    with pytest.raises(ClockError):
        clock_ms("31.10")


# ---------------------------------------------------------------- runner on a fake clock
@pytest.fixture
def stage(tmp_path):
    now = [0.0]
    clock = ReplayClock(5_400_000, speed=1, start_ms=1_860_000, wall=lambda: now[0])
    bb = SqliteBlackboard(tmp_path / "bb.sqlite")
    sent = []
    hub = SimpleNamespace(live=None, match_id="m_4242", now=clock.now, send=sent.append)
    kills = []
    runner = DemoRunner(SimpleNamespace(clock=clock, bb=bb, hub=hub), load_script(SCRIPT),
                        kill=lambda target: kills.append(target) or {"killed": True})

    def advance(to_ms: int, step_ms: int = 500):
        while clock.now() < to_ms:
            now[0] += step_ms / 1000 / clock.speed
            runner.tick()

    return SimpleNamespace(clock=clock, bb=bb, runner=runner, advance=advance, kills=kills, sent=sent, now=now)


def test_runner_applies_actions_on_the_clock(stage):
    stage.runner.tick()
    stage.advance(1_869_500)
    assert stage.clock.speed == 1
    stage.clock.set_speed(4)
    stage.advance(1_871_000)
    assert stage.clock.speed == 1                          # speed 1 at 31:10
    stage.advance(1_981_000)
    assert stage.clock.speed == 10                         # speed 10 at 33:00
    stage.advance(2_651_000)
    assert stage.kills == ["newsroom"]                     # kill at 44:10, once
    stage.bb.put("requests", {"id": "req_recap", "request_id": "req_recap", "match_id": "m_4242",
                              "cue": {"kind": "recap", "cue_id": "c_000234"}})
    stage.bb.put("requests", {"id": "req_other", "request_id": "req_other", "match_id": "m_4242",
                              "cue": {"kind": "dugout"}})
    stage.advance(2_716_000)
    assert stage.bb.get("decisions", "req_recap")["decision"] == "vetoed"
    assert not stage.bb.query("decisions", request_id="req_other")
    assert [a.fired for a in stage.runner.actions] == [True, True, True, True]
    assert stage.kills == ["newsroom"]


def test_runner_waits_for_a_late_recap_request(stage):
    stage.clock.seek(2_714_000)
    stage.runner.tick()
    stage.advance(2_720_000)                               # veto due, request not written yet
    assert not stage.bb.query("decisions")
    stage.bb.put("requests", {"id": "req_late", "request_id": "req_late", "match_id": "m_4242",
                              "cue": {"kind": "recap"}})
    stage.advance(2_721_000)
    assert stage.bb.get("decisions", "req_late")["decision"] == "vetoed"


def test_seek_back_rearms_and_seek_forward_skips(stage):
    stage.runner.tick()
    stage.clock.seek(2_700_000)                            # jump over 44:10: the kill is skipped
    stage.advance(2_701_000)
    assert stage.kills == []
    stage.clock.seek(2_640_000)                            # back before 44:10: armed again
    stage.advance(2_652_000)
    assert stage.kills == ["newsroom"]


# ---------------------------------------------------------------- shot list
def test_shot_list_covers_every_storyboard_beat():
    shots = load_shots(SHOTS, load_moments(SAMPLE))
    assert {s.beat for s in shots} == BEATS
    by = {s.shot: s for s in shots}
    assert by["sliding_doors_3d_player"].route == "/replay3d?cf=cf_000077&cam=player"
    assert by["split_player_cam"].player == "p_031" and by["split_player_cam"].app == "fan"
    assert by["sliding_doors_2d"].clock_in == 1_868_000 and by["sliding_doors_2d"].keyframes[0] == 1_874_000
    assert {s.viewer for s in shots if s.beat == "split_modes" and s.app != "studio"} == {"analyst", "casual",
                                                                                          "player_cam"}
    for s in shots:
        assert set(s.outputs) >= {f"{s.shot}.webm"}


def test_dry_run_prints_the_plan(capsys):
    assert main(["--shots", str(SHOTS), "--moments", str(SAMPLE), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "sliding_doors_2d" in out and "sliding_doors_2d_3114.png" in out and "dry run: 14 shots" in out


# ---------------------------------------------------------------- one real recording
def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _off_loop(fn):
    """tests/apps may leave a Playwright loop in the main thread; run sync Playwright on a worker thread."""
    box = {}
    t = threading.Thread(target=lambda: box.update(result=fn()))
    t.start()
    t.join(timeout=180)
    if "result" not in box:
        raise AssertionError("recording thread did not finish")
    return box["result"]


def test_records_a_shot_with_video_and_keyframes(tmp_path):
    import uvicorn
    from playwright.sync_api import sync_playwright

    from api.main import create_app
    from demo.record_demo import GPU_ARGS, record_shot, serve

    dist = ROOT / "apps" / "overlay" / "dist"
    if not (dist / "index.html").exists():
        pytest.fail("apps/overlay/dist missing: run `npm --prefix apps/overlay run build` first")
    port = _free_port()
    bb = SqliteBlackboard(Path(tempfile.mkdtemp()) / "bb.sqlite")
    server = uvicorn.Server(uvicorn.Config(create_app(seed=4242, speed=1, bb=bb), host="127.0.0.1", port=port,
                                           log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    deadline = time.time() + 20
    while not server.started:
        assert time.time() < deadline
        time.sleep(0.05)
    http, base = serve(dist)
    shot = Shot(shot="smoke", beat="sliding_doors", app="overlay", viewer="analyst",
                clock_in=600_000, clock_out=602_500, speed=1, keyframes=[601_000])
    try:
        def run():
            with sync_playwright() as pw:
                browser = pw.chromium.launch(args=GPU_ARGS)
                marks = record_shot(browser, shot, {"overlay": base}, f"http://127.0.0.1:{port}", tmp_path)
                browser.close()
                return marks

        marks = _off_loop(run)
    finally:
        http.shutdown()
        server.should_exit = True
        bb.close()
    video, png = tmp_path / "smoke.webm", tmp_path / f"smoke_{fmt(601_000).replace(':', '')}.png"
    print(f"\nrecorded smoke.webm {video.stat().st_size // 1024} KB, ready after {marks['ready_s']:.1f} s")
    assert video.stat().st_size > 20_000 and png.stat().st_size > 20_000
    assert json.loads((tmp_path / "smoke.json").read_text())["play_s"] >= marks["ready_s"]
