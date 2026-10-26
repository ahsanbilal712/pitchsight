"""Front-end console sweep: every screen and route against a local replay of the golden match.

    PYTHONPATH=packages python scripts/frontend_sweep.py [--out packages/demo/out/sweep] [--no-newsroom]

Starts whyline-api in replay mode with the replay feed (and, unless --no-newsroom, the newsroom supervisor) on a
fresh blackboard in a temp dir, serves apps/*/dist, and opens in GPU Chromium: overlay (fixture; analyst, casual,
player_cam), /replay3d on the Sliding Doors counterfactual, studio, and fan (casual, analyst, player_cam) at phone
widths 360, 390 and 430. It seeks to each storyboard beat of packages/demo/golden_moments.yaml, plays a few
seconds, and records console errors and warnings, page errors, failed requests (HTTP >= 400 or network
failures), horizontal overflow on phones, and a screenshot per page and beat. Prints a JSON report; exits 1 when
any page logged an error. Hosted URLs (Azure) are out of scope while Azure is deferred.
"""

from __future__ import annotations

import argparse
import collections
import functools
import http.server
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from demo.clocks import fmt, load_moments, resolve  # noqa: E402

GPU = ["--use-angle=metal", "--ignore-gpu-blocklist"]
READY = "() => window.__whyline && window.__whyline.ready === true"


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(app: str) -> str:
    s = http.server.ThreadingHTTPServer(("127.0.0.1", 0),
                                        functools.partial(_Quiet, directory=str(ROOT / "apps" / app / "dist")))
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{s.server_address[1]}/index.html"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(ROOT / "packages" / "demo" / "out" / "sweep"))  # git-ignored
    ap.add_argument("--no-newsroom", action="store_true")
    ap.add_argument("--play-s", type=float, default=4.0, help="seconds of play at each beat")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="sweep_"))
    port = free_port()
    api = f"http://127.0.0.1:{port}"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "packages"), "WHYLINE_MODE": "replay",
           "WHYLINE_BLACKBOARD": str(tmp / "bb.sqlite"), "WHYLINE_WORKER_PIDFILE": str(tmp / "newsroom.pid"),
           "WHYLINE_CHECKPOINT_DIR": str(tmp / "ckpt"), "WHYLINE_SPEND_LEDGER": str(tmp / "ledger.jsonl"),
           "WHYLINE_REPLAY_FEED": "1"}
    py = str(ROOT / ".venv" / "bin" / "python")
    procs = [subprocess.Popen([py, "-m", "api.replay", "--seed", "4242", "--port", str(port), "--feed"], cwd=ROOT,
                              env=env, stdout=open(tmp / "api.log", "w"), stderr=subprocess.STDOUT)]
    if not args.no_newsroom:
        procs.append(subprocess.Popen([py, "-m", "newsroom.supervisor", "--mode", "replay", "--match", "m_4242"],
                                      cwd=ROOT, env=env, stdout=open(tmp / "newsroom.log", "w"),
                                      stderr=subprocess.STDOUT))

    def post(path: str, body: dict) -> None:
        req = urllib.request.Request(api + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()

    def health() -> dict:
        with urllib.request.urlopen(api + "/health", timeout=10) as r:
            return json.load(r)

    moments = load_moments()
    beats = {"sliding_doors": resolve("@sliding_doors-4s", moments),
             "fourth_official": resolve("@fourth_official-3s", moments),
             "oracle": resolve("@oracle-4s", moments), "dugout": resolve("@dugout-2s", moments),
             "kill": resolve("@kill-6s", moments), "halftime": resolve("45:00", moments)}
    cf = moments["sliding_doors"]["counterfactual_id"]
    cam_player = moments["sliding_doors"]["alternative_target"]
    urls = {a: serve(a) for a in ("overlay", "studio", "fan")}
    q = f"record=1&api=127.0.0.1:{port}"
    pages_spec = [
        ("overlay_fixture", urls["overlay"] + "?fixture=1&record=1", (1920, 1080)),
        ("overlay_analyst", f"{urls['overlay']}?{q}&mode=analyst", (1920, 1080)),
        ("overlay_casual", f"{urls['overlay']}?{q}&mode=casual", (1920, 1080)),
        ("overlay_player_cam", f"{urls['overlay']}?{q}&mode=player_cam&player={cam_player}", (1920, 1080)),
        ("replay3d", f"{urls['overlay']}?{q}&view=replay3d&cf={cf}&mode=analyst", (1920, 1080)),
        ("replay3d_fixture", urls["overlay"] + "?fixture=1&record=1&view=replay3d&cf=cf_000077", (1920, 1080)),
        ("studio", f"{urls['studio']}?{q}", (1920, 1080)),
        ("fan_casual_360", f"{urls['fan']}?{q}&mode=casual", (360, 780)),
        ("fan_analyst_390", f"{urls['fan']}?{q}&mode=analyst", (390, 844)),
        ("fan_player_cam_430", f"{urls['fan']}?{q}&mode=player_cam&player={cam_player}", (430, 932)),
    ]
    report: dict = {"api": api, "beats": {k: fmt(v) for k, v in beats.items()}, "pages": {}}
    issues = collections.defaultdict(list)
    try:
        for _ in range(150):
            try:
                health()
                break
            except Exception:
                time.sleep(0.2)
        time.sleep(3)
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=GPU)
            pages = {}
            for name, url, (w, h) in pages_spec:
                ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
                page = ctx.new_page()
                page.on("console", lambda m, n=name: m.type in ("error", "warning")
                        and issues[n].append(f"console.{m.type}: {m.text[:300]}"))
                page.on("pageerror", lambda e, n=name: issues[n].append(f"pageerror: {str(e)[:300]}"))
                page.on("requestfailed", lambda r, n=name: issues[n].append(f"requestfailed: {r.url} {r.failure}"))
                page.on("response", lambda r, n=name: r.status >= 400
                        and issues[n].append(f"http {r.status}: {r.url}"))
                started = time.monotonic()
                page.goto(url)
                page.wait_for_function(READY, timeout=30_000)
                report["pages"][name] = {"ready_s": round(time.monotonic() - started, 2), "size": [w, h]}
                pages[name] = page
            for beat, t in beats.items():
                post("/replay/control", {"action": "pause"})
                post("/replay/control", {"action": "seek", "value": t})
                post("/replay/control", {"action": "speed", "value": 1})
                post("/replay/control", {"action": "play"})
                time.sleep(args.play_s)
                post("/replay/control", {"action": "pause"})
                for name, page in pages.items():
                    if name.endswith("_fixture"):
                        continue
                    page.screenshot(path=str(out / f"{name}_{beat}.png"))
                    if name.startswith("fan_"):
                        over = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
                        if over > 0:
                            issues[name].append(f"horizontal overflow {over}px at {beat}")
            for name, page in pages.items():
                if name.endswith("_fixture"):
                    page.screenshot(path=str(out / f"{name}.png"))
                report["pages"][name]["debug"] = page.evaluate(
                    "() => { const d = window.__whyline.debug(); return {clock: d.clock, cues: d.cues ?? d.visibleCues"
                    " ?? d.feed} }")
            browser.close()
        report["clock_end"] = fmt(health()["stream_t_ms"])
    finally:
        for p in procs:
            p.terminate()
        time.sleep(1)
        for p in procs:
            if p.poll() is None:
                p.kill()
    report["issues"] = dict(issues)
    report["logs"] = str(tmp)
    print(json.dumps(report, indent=1, default=str))
    return 1 if any(any(not i.startswith("console.warning") for i in v) for v in issues.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
