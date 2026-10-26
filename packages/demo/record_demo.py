"""Record the demo shots with Playwright.

    python -m demo.record_demo --shots packages/demo/shot_list.yaml [--only a,b] [--api http://127.0.0.1:8000]
    python -m demo.record_demo --shots packages/demo/shot_list.yaml --dry-run

Chromium at 1920x1080 (the fan app at its 390x844 phone size), DPR 1, `record_video_dir`, GPU rendering (Metal via
ANGLE: headless Chromium otherwise draws WebGL on the CPU). For each shot: pause the replay, seek to clock_in, set
the speed (after an optional warm-up: warm_from -> clock_in at warm_speed, then a settle), open the app with
?record=1&api=…&mode=<viewer>, wait for window.__whyline.ready, play until the stream
clock reaches clock_out, saving <shot>_<mmss>.png at each keyframe clock. Writes packages/demo/out/<shot>.webm and
<shot>.json (wall-clock offsets of ready and play inside the video, so the edit can trim the page load).
The apps are served from apps/<app>/dist on local ports. Needs the api running in replay mode.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import re
import shutil
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from demo.clocks import ClockError, fmt, load_moments, resolve

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "packages" / "demo" / "out"
APPS = ("overlay", "studio", "fan")
SIZES = {"overlay": (1920, 1080), "studio": (1920, 1080), "fan": (390, 844), "page": (1920, 1080)}
GPU_ARGS = ["--use-angle=metal", "--ignore-gpu-blocklist"]
READY = "() => window.__whyline && window.__whyline.ready === true"
_TEMPLATE = re.compile(r"\{([a-z_][a-z0-9_]*)(?:\[(\d+)\])?\.([a-z_][a-z0-9_]*)\}")


@dataclass
class Shot:
    shot: str
    beat: str
    app: str
    route: str = "/"
    viewer: str = "analyst"
    player: str | None = None
    clock_in: int = 0
    clock_out: int = 0
    speed: float = 1.0
    keyframes: list[int] = field(default_factory=list)
    file: str | None = None
    duration_s: float = 0.0
    warm_from: int | None = None      # play from here at warm_speed first, so the studio opens on a full history
    warm_speed: float = 10.0
    warm_settle_s: float = 20.0       # then wait for the newsroom to finish what the warm-up raised

    @property
    def outputs(self) -> list[str]:
        return [f"{self.shot}.webm", *[f"{self.shot}_{fmt(k).replace(':', '')}.png" for k in self.keyframes]]


def fill(text: str, moments: dict) -> str:
    """Replace {key.field} / {key[i].field} with values from golden_moments.yaml."""
    def one(m: re.Match) -> str:
        entry = moments.get(m.group(1))
        if isinstance(entry, list):
            entry = entry[int(m.group(2) or 0)]
        if not isinstance(entry, dict) or m.group(3) not in entry:
            raise ClockError(f"golden_moments.yaml has no {m.group(0)[1:-1]}")
        return str(entry[m.group(3)])
    return _TEMPLATE.sub(one, text)


def load_shots(path: str | Path, moments: dict | None = None) -> list[Shot]:
    rows = yaml.safe_load(Path(path).read_text()) or []
    needs = any("@" in json.dumps(r) or "{" in json.dumps(r) for r in rows)
    moments = moments if moments is not None else (load_moments() if needs else {})
    shots = []
    for r in rows:
        if r["app"] not in (*APPS, "page"):
            raise ValueError(f"{r['shot']}: unknown app {r['app']!r}")
        s = Shot(shot=r["shot"], beat=r["beat"], app=r["app"])
        if r["app"] == "page":
            s.file, s.duration_s = r["file"], float(r["duration_s"])
        else:
            s.route = fill(r.get("route", "/"), moments)
            s.viewer = r.get("viewer", "analyst")
            s.player = fill(r["player"], moments) if r.get("player") else None
            s.clock_in, s.clock_out = resolve(r["clock_in"], moments), resolve(r["clock_out"], moments)
            s.speed = float(r.get("speed", 1))
            s.keyframes = [resolve(k, moments) for k in r.get("keyframes", [])]
            if r.get("warm_from") is not None:
                s.warm_from = resolve(r["warm_from"], moments)
                s.warm_speed = float(r.get("warm_speed", 10))
                s.warm_settle_s = float(r.get("warm_settle_s", 20))
                if not s.warm_from < s.clock_in:
                    raise ValueError(f"{s.shot}: warm_from {fmt(s.warm_from)} is not before clock_in")
            if not s.clock_in < s.clock_out:
                raise ValueError(f"{s.shot}: clock_in {fmt(s.clock_in)} is not before clock_out {fmt(s.clock_out)}")
            if any(not s.clock_in <= k <= s.clock_out for k in s.keyframes):
                raise ValueError(f"{s.shot}: keyframe outside {fmt(s.clock_in)}-{fmt(s.clock_out)}")
        shots.append(s)
    names = [s.shot for s in shots]
    if len(set(names)) != len(names):
        raise ValueError("duplicate shot names")
    return shots


# ---------------------------------------------------------------------------------------------- serving and api
class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve(directory: Path) -> tuple[http.server.ThreadingHTTPServer, str]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(directory)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def api_get(api: str, path: str) -> dict:
    with urllib.request.urlopen(f"{api}{path}", timeout=10) as r:
        return json.load(r)


def api_post(api: str, path: str, body: dict) -> dict:
    req = urllib.request.Request(f"{api}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def page_url(base: str, shot: Shot, api: str) -> str:
    path, _, query = shot.route.partition("?")
    q = urllib.parse.parse_qs(query)
    params = {k: v[0] for k, v in q.items()}
    if path.rstrip("/").endswith("replay3d"):
        params["view"] = "replay3d"
    params.update({"record": "1", "api": urllib.parse.urlparse(api).netloc, "mode": shot.viewer})
    if shot.player:
        params["player"] = shot.player
    return f"{base}/index.html?{urllib.parse.urlencode(params)}"


# ---------------------------------------------------------------------------------------------- recording
def warm_up(api: str, shot: Shot) -> None:
    """Play warm_from -> clock_in at warm_speed before the take (no page open), then let the newsroom settle: the
    moments, traces and cues of those minutes are on the blackboard when the studio connects, so its panels show a
    working newsroom instead of a fresh one (v1 frame review)."""
    api_post(api, "/replay/control", {"action": "pause"})
    api_post(api, "/replay/control", {"action": "seek", "value": shot.warm_from})
    api_post(api, "/replay/control", {"action": "speed", "value": shot.warm_speed})
    api_post(api, "/replay/control", {"action": "play"})
    deadline = time.monotonic() + (shot.clock_in - shot.warm_from) / 1000 / shot.warm_speed + 60
    while api_get(api, "/health")["stream_t_ms"] < shot.clock_in - 1000:
        if time.monotonic() > deadline:
            raise TimeoutError(f"{shot.shot}: warm-up clock stuck")
        time.sleep(0.1)
    api_post(api, "/replay/control", {"action": "pause"})
    time.sleep(shot.warm_settle_s)


def record_shot(browser, shot: Shot, bases: dict[str, str], api: str, out: Path) -> dict:
    w, h = SIZES[shot.app]
    tmp = Path(tempfile.mkdtemp(prefix=f"rec_{shot.shot}_"))
    ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1,
                              record_video_dir=str(tmp), record_video_size={"width": w, "height": h})
    page = ctx.new_page()
    t0 = time.monotonic()
    marks: dict = {"shot": shot.shot, "app": shot.app, "size": [w, h]}
    try:
        if shot.app == "page":
            page.goto((ROOT / shot.file).as_uri())
            marks["ready_s"] = time.monotonic() - t0
            page.wait_for_timeout(int(shot.duration_s * 1000))
        else:
            if shot.warm_from is not None:
                warm_up(api, shot)
            api_post(api, "/replay/control", {"action": "pause"})
            api_post(api, "/replay/control", {"action": "seek", "value": shot.clock_in})
            api_post(api, "/replay/control", {"action": "speed", "value": shot.speed})
            page.goto(page_url(bases[shot.app], shot, api))
            page.wait_for_function(READY, timeout=30_000)
            page.wait_for_timeout(500)                       # first frames and entry animations settle
            marks["ready_s"] = time.monotonic() - t0
            api_post(api, "/replay/control", {"action": "play"})
            marks["play_s"] = time.monotonic() - t0
            pending = sorted(shot.keyframes)
            deadline = time.monotonic() + (shot.clock_out - shot.clock_in) / 1000 / shot.speed + 30
            while True:
                t = api_get(api, "/health")["stream_t_ms"]
                while pending and t >= pending[0]:
                    page.screenshot(path=str(out / f"{shot.shot}_{fmt(pending.pop(0)).replace(':', '')}.png"))
                if t >= shot.clock_out:
                    break
                if time.monotonic() > deadline:
                    raise TimeoutError(f"{shot.shot}: clock stuck at {fmt(t)}")
                time.sleep(0.05)
            api_post(api, "/replay/control", {"action": "pause"})
        marks["end_s"] = time.monotonic() - t0
    finally:
        video = page.video
        ctx.close()
    src = Path(video.path())
    shutil.move(str(src), out / f"{shot.shot}.webm")
    shutil.rmtree(tmp, ignore_errors=True)
    (out / f"{shot.shot}.json").write_text(json.dumps(marks, indent=1) + "\n")
    return marks


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m demo.record_demo", description=__doc__.splitlines()[0])
    ap.add_argument("--shots", default=str(ROOT / "packages" / "demo" / "shot_list.yaml"))
    ap.add_argument("--moments", default=None, help="golden_moments.yaml (default packages/demo/golden_moments.yaml)")
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--only", default="", help="comma-separated shot names")
    ap.add_argument("--dry-run", action="store_true", help="resolve and print the plan; open no browser")
    args = ap.parse_args(argv)
    try:
        moments = load_moments(args.moments) if args.moments else None
        shots = load_shots(args.shots, moments)
    except (ClockError, ValueError, KeyError) as exc:
        print(f"record_demo: {exc}", file=sys.stderr)
        return 1
    if args.only:
        wanted = set(args.only.split(","))
        shots = [s for s in shots if s.shot in wanted]
    out = Path(args.out)
    for s in shots:
        span = f"{s.duration_s:.0f} s page" if s.app == "page" else \
            f"{fmt(s.clock_in)}-{fmt(s.clock_out)} x{s.speed:g} {s.viewer}{' ' + s.player if s.player else ''}"
        print(f"{s.shot:<26} {s.beat:<16} {s.app:<8} {span:<36} -> {', '.join(s.outputs)}")
    missing = [a for a in {s.app for s in shots} - {"page"} if not (ROOT / "apps" / a / "dist" / "index.html").exists()]
    pages = [s.file for s in shots if s.app == "page" and not (ROOT / s.file).exists()]
    if args.dry_run:
        for a in missing:
            print(f"warning: apps/{a}/dist missing (npm --prefix apps/{a} run build)")
        for p in pages:
            print(f"warning: {p} missing (written by the video edit)")
        print(f"dry run: {len(shots)} shots into {out}")
        return 0
    if missing:
        print(f"record_demo: build first: {', '.join(missing)}", file=sys.stderr)
        return 1
    shots = [s for s in shots if not (s.app == "page" and s.file in pages)]
    out.mkdir(parents=True, exist_ok=True)
    servers = {a: serve(ROOT / "apps" / a / "dist") for a in APPS if (ROOT / "apps" / a / "dist").exists()}
    bases = {a: url for a, (_, url) in servers.items()}
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=GPU_ARGS)
            for s in shots:
                marks = record_shot(browser, s, bases, args.api.rstrip("/"), out)
                print(f"recorded {s.shot}: {marks['end_s']:.1f} s")
            browser.close()
    finally:
        for server, _ in servers.values():
            server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
