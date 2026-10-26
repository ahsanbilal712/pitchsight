"""Real-frame compositing (FOOTAGE_ADDENDUM §2 and §3 step 7, T-108).

    python -m demo.composite lfc_sliding_doors [--png] [--clip] [--standin] [--refit]

The headline beat on a real broadcast clip: the clip plays, freezes at the decisive instant, the two players are
lit and ringed on the grass, the 200 ghost futures of the counterfactual (first half what happened, second half the
alternative, as in the overlay's ghost layer) and the alternative pass are drawn on the frozen frame through the
moment's camera (packages/demo/footage.py), the win-chance card swings, everything fades and the clip resumes.
Everything on the grass is drawn in pitch metres and projected through the camera, lens term included, so it sits
on the painted lines to the camera's measured drift.

Moments are described in packages/demo/footage_moments.yaml. Outputs (git-ignored) in packages/demo/out/footage/:
<moment>.png (the composite at full build), <moment>.mp4 (pre-roll, freeze, resume; 30 fps, no audio) and
<moment>_camera.json (the fitted camera and its drift). With --standin the futures are the golden match's
cf_000070 re-anchored on the players, for checking the look before track B's precomputed counterfactual (T-109)
exists; those files carry a _standin suffix and a watermark, and never go in the video.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import numpy as np  # noqa: E402
import yaml  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402
from scipy import ndimage as ndi  # noqa: E402

from demo.footage import (  # noqa: E402
    PITCH_L,
    PITCH_W,
    Camera,
    Drift,
    board_top,
    drift_px,
    fit_from_lines,
    from_pitchwatch,
    model_lines,
    occluders,
)
from demo.live import SCENES, SS, HiDraw, downsample_rgba, flatten, hi_layer  # noqa: E402
from demo.v3_data import build  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FOOTAGE = ROOT / "data" / "footage"
MOMENTS = Path(__file__).with_name("footage_moments.yaml")
OUT = ROOT / "packages" / "demo" / "out" / "footage"
STANDIN_CF = ROOT / "data" / "matches" / "4242" / "cache" / "counterfactuals" / "cf_000070.json"
W, H, FPS = 1920, 1080, 30
_INTER = Path(__file__).resolve().parent / "out" / "fonts"   # Inter (OFL), fetched locally: docs/video/FONTS.md
_DEJAVU = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
FONT_DIR = _INTER if (_INTER / "Inter-Bold.ttf").exists() else _DEJAVU
FONT = str(FONT_DIR / ("Inter-Bold.ttf" if FONT_DIR == _INTER else "DejaVuSans-Bold.ttf"))
FONT_REG = str(FONT_DIR / ("Inter-Regular.ttf" if FONT_DIR == _INTER else "DejaVuSans.ttf"))
FONT_NAME = "Inter" if FONT_DIR == _INTER else "DejaVu Sans"
ORANGE, WHITE, YELLOW = (255, 122, 26), (236, 242, 248), (255, 214, 10)
PANEL = (12, 16, 22)
SUBDIV = 10
REFINE_LINES = [n for n in model_lines() if n != "touchline_far"]
APPARENT_HEIGHT_M = 1.42   # a player's height in the picture over the grass scale across it (4 players, lfc 875 s)
RING_R = 1.1              # metres
LANE_S = {"actual": 1, "alternative": 2}   # v4: seconds of each branch's median drawn (the strike, the pass and on)
GHOST_S = 4               # seconds of each future drawn: the decision and what follows it, not the whole 8 s
GHOST_KEEP = 36           # paths drawn per branch: the ones nearest the branch's median path
GHOST_REPS = 6            # of those, drawn bolder
GHOST_FADE_T = (1.0, 2.4)   # s: full strength through the first leg, gone by 2.4 s ...
GHOST_FADE_D = (5.0, 12.0)  # m: ... unless still within this of where the branch is going
GHOST_MARGIN_M = 2.0       # futures are clamped to the pitch plus this, as the overlay's ghost layer


# ---------------------------------------------------------------------------------------------- inputs
def load_moment(name: str) -> dict:
    """The moment's spec; with a `moment_file` (T-107: players and ball in pitch metres, hand-marked or tracked)
    the actor, the target and the ball take their positions from it (`at`), else from their feet pixels."""
    moments = yaml.safe_load(MOMENTS.read_text())["moments"]
    extra = os.environ.get("PITCHSIGHT_MOMENTS")          # a generated cut's moments (git-ignored, demo.match_cut)
    if extra:
        moments = {**moments, **yaml.safe_load(Path(extra).read_text())["moments"]}
    if name not in moments:
        raise SystemExit(f"composite: no moment {name!r} in {MOMENTS.name} ({', '.join(moments)})")
    m = {"name": name, **moments[name]}
    path = FOOTAGE / m["moment_file"] if m.get("moment_file") else None
    if path and path.exists():
        doc = json.loads(path.read_text())
        players = {p["label"]: p for p in doc["players"]}
        for role in ("actor", "target"):
            if m.get(role) and m[role].get("player") in players:
                p = players[m[role]["player"]]
                m[role] = {**m[role], "at": [p["x"], p["y"]]}
        m["ball_at"] = [doc["ball"]["x"], doc["ball"]["y"]]
        m["moment_h"] = doc.get("homography", {}).get("image_to_pitch")
    return m


def clip_path(m: dict) -> Path:
    return FOOTAGE / m["clip"] / "clip.mp4"


def frame_at(m: dict, t_s: float) -> np.ndarray:
    """One RGB frame of the moment's clip at t_s (decoded, never written next to the media)."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t_s:.3f}", "-i", str(clip_path(m)), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(H, W, 3).copy()


def top_rows(poly) -> np.ndarray:
    """Per-column first pitch row from the boards' lower-edge polyline."""
    p = np.asarray(poly, float)
    return np.ceil(np.interp(np.arange(W), p[:, 0], p[:, 1])).astype(int)


def pitchwatch_camera(m: dict, frame: np.ndarray) -> tuple[Camera, Drift, str] | None:
    """Track A's per-frame calibration (T-104) for the freeze instant, measured the same way, if published; the
    paint-refined file (demo.refine_calib) first."""
    shots = json.loads((FOOTAGE / m["clip"] / "shots.json").read_text())["shots"]
    shot = next((s["id"] for s in shots if s.get("usable") and s["start"] <= m["t_s"] <= s["end"]), None)
    calib_dir = FOOTAGE / m["clip"] / "calib"
    path = next((p for p in (calib_dir / f"{shot}_refined.json", calib_dir / f"{shot}.json") if p.exists()), None)
    if shot is None or path is None:
        return None
    calib = json.loads(path.read_text())
    cam = from_pitchwatch(calib, int(round(m["t_s"] * calib.get("fps", 50.0))))
    lines, top = fit_spec(m)
    return cam, drift_px(cam, frame, lines, top=top), path.name


def seed_camera(m: dict) -> Camera | None:
    """The moment file's own homography (pixels -> its pitch metres, this module's convention), as a camera."""
    h = m.get("moment_h")
    return Camera(np.linalg.inv(np.asarray(h, float))) if h is not None else None


def fit_spec(m: dict) -> tuple[list[str], np.ndarray]:
    """The lines a moment's camera is measured on and the per-column first pitch row (boards above): from the spec,
    else every marking but the far touchline, with the boards cut above it as the seed camera sees it."""
    spec = m.get("camera") or {}
    lines = spec.get("lines") or REFINE_LINES
    top = top_rows(spec["top"]) if spec.get("top") else board_top(seed_camera(m), W)
    return lines, top


def camera_for(m: dict, frame: np.ndarray, refit: bool = False) -> tuple[Camera, Drift]:
    """The moment's camera, refined against the frame's own markings (cached per moment): from hand landmarks when
    the spec has them, else seeded with the moment file's homography (T-107/T-109)."""
    path = OUT / f"{m['name']}_camera.json"
    spec = m.get("camera") or {}
    key = {"t_s": m["t_s"], "camera": spec, "seed": m.get("moment_h")}
    if path.exists() and not refit:
        doc = json.loads(path.read_text())
        if doc.get("key") == key:
            return Camera.from_json(doc), Drift(**doc["drift"])
    lines, top = fit_spec(m)
    if spec.get("refine") is False:                     # too little paint in view to refine on: the seed as it is
        cam = seed_camera(m)
        cam = Camera(cam.h, size=(frame.shape[1], frame.shape[0]))
        drift = drift_px(cam, frame, lines, top=top)
        OUT.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"key": key, **cam.to_json(), "drift": drift.__dict__}, indent=1))
        return cam, drift
    if spec.get("landmarks"):
        fit = fit_from_lines(frame, spec["landmarks"]["pitch"], spec["landmarks"]["pixel"], lines, top=top)
    else:
        fit = fit_from_lines(frame, None, None, lines, top=top, seed=seed_camera(m))
    OUT.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"key": key, **fit.camera.to_json(), "drift": fit.drift.__dict__}, indent=1))
    return fit.camera, fit.drift


@dataclass
class Futures:
    baseline: list[np.ndarray]          # metres, 1 Hz points
    alternative: list[np.ndarray]
    cf: dict
    standin: bool


def split(cf: dict) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """First half of futures_sample is the baseline (what happened), second half the alternative (cue contract
    gap 7, as the overlay's ghost layer)."""
    paths = [np.asarray(p, float) for p in cf["futures_sample"][:200]]
    half = len(paths) // 2
    return paths[:half], paths[half:]


def _similarity(a0, a1, b0, b1):
    """The rotation + scale + shift taking a0 -> b0 and a1 -> b1 (complex arithmetic)."""
    za0, za1, zb0, zb1 = (complex(*p) for p in (a0, a1, b0, b1))
    k = (zb1 - zb0) / (za1 - za0)

    def f(pts):
        z = (pts[:, 0] + 1j * pts[:, 1] - za0) * k + zb0
        return np.c_[z.real, z.imag]
    return f


def standin_futures(start_m, target_m, goal_m=(105.0, 34.0)) -> Futures:
    """cf_000070's futures re-anchored: every path starts at the ball, the baseline branch's mean first second
    points at the goal, the alternative's at the target. Looks only; the numbers are cf_000070's."""
    cf = json.loads(STANDIN_CF.read_text())
    base, alt = split(cf)
    s0 = base[0][0]
    out = []
    for branch, aim in ((base, None), (alt, np.asarray(target_m, float))):
        m1 = np.mean([p[1] for p in branch], axis=0)
        if aim is None:
            d = np.asarray(goal_m, float) - start_m
            aim = start_m + d / np.linalg.norm(d) * np.linalg.norm(m1 - s0)
        f = _similarity(s0, m1, start_m, aim)
        out.append([f(p) for p in branch])
    return Futures(out[0], out[1], cf, standin=True)


def load_futures(m: dict, cam: Camera, standin: bool) -> Futures:
    if m.get("counterfactual"):
        cf = json.loads((ROOT / m["counterfactual"]).read_text())
        if m.get("futures") == "alternative":            # every path is the alternative (featured moments today)
            return Futures([], [np.asarray(p, float) for p in cf["futures_sample"][:200]], cf, standin=False)
        b, a = split(cf)
        return Futures(b, a, cf, standin=False)
    if not standin:
        raise SystemExit(f"composite: {m['name']} has no counterfactual yet (T-109); pass --standin to check the look")
    return standin_futures(ball_m(m, cam), at_m(m["target"], cam))


def at_m(who: dict, cam: Camera) -> np.ndarray:
    """A player's position in metres: from the moment file, else his feet pixel through the camera."""
    return np.asarray(who["at"], float) if "at" in who else cam.unproject([who["feet"]])[0]


def ball_m(m: dict, cam: Camera) -> np.ndarray:
    if m.get("ball_at"):
        return np.asarray(m["ball_at"], float)
    return cam.unproject([m["ball"]])[0] if m.get("ball") else at_m(m["actor"], cam)


# ---------------------------------------------------------------------------------------------- geometry
def catmull_rom(points: np.ndarray, subdiv: int = SUBDIV) -> np.ndarray:
    """Uniform Catmull-Rom through every point, endpoints clamped (the overlay's ghostTrail.ts)."""
    p = np.asarray(points, float)
    if len(p) < 3:
        return p
    q = np.vstack([p[:1], p, p[-1:]])
    t = np.linspace(0, 1, subdiv, endpoint=False)[:, None]
    t2, t3 = t * t, t * t * t
    out = []
    for i in range(len(p) - 1):
        a, b, c, d = q[i], q[i + 1], q[i + 2], q[i + 3]
        out.append(0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2 + (-a + 3 * b - 3 * c + d) * t3))
    return np.vstack(out + [p[-1:]])


def ground_circle(centre, r: float, n: int = 72) -> np.ndarray:
    t = np.linspace(0, 2 * np.pi, n)
    return np.c_[centre[0] + r * np.cos(t), centre[1] + r * np.sin(t)]


def pass_curve(a, b, bend: float = 0.08, n: int = 60) -> np.ndarray:
    """A gently bent pass from a to b in metres (quadratic Bezier, bowed to the left of travel)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = b - a
    c = (a + b) / 2 + bend * np.array([-d[1], d[0]])
    t = np.linspace(0, 1, n)[:, None]
    return (1 - t) ** 2 * a + 2 * (1 - t) * t * c + t * t * b


def densify(seg, step: float = 0.25) -> np.ndarray:
    """Points every `step` metres along a polyline, so the lens term bends straight lines as the camera does."""
    seg = np.asarray(seg, float)
    out = []
    for a, b in zip(seg[:-1], seg[1:], strict=True):
        n = max(2, int(np.hypot(*(b - a)) / step))
        out.append(np.linspace(a, b, n, endpoint=False))
    return np.vstack(out + [seg[-1:]])


def ease(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return 1 - (1 - t) ** 3


def window(t: float, a: float, b: float) -> float:
    return ease((t - a) / (b - a)) if b > a else float(t >= a)


# ---------------------------------------------------------------------------------------------- timeline
FREEZE_S = 7.0
V4_PUNCH = 1.12           # v4 freeze: zoom on the decision (pitch graphics are drawn before the zoom, so they scale)
RAMP_SLOW_S = 0.8         # v4: the last real seconds before the freeze ...
RAMP_RATE = 0.5           # ... play at this speed (eased in): the speed ramp
REWIND_S = 1.5            # v4: after the freeze the clip rewinds this far (every REWIND_STEP-th frame) and replays
REWIND_STEP = 3
MODES_FREEZE_S = 11.0     # viewer-mode clips (split screen): the built overlay held long enough to read
FADE_OUT = (6.3, 6.9)
T_GRADE = (0.0, 0.35)
T_RINGS = (0.2, 0.8)
T_BASE = (0.6, 2.2)
T_ALT = (1.8, 3.6)
T_TRAIL = (1.8, 2.6)
T_CARD = (2.6, 3.0)
T_SWING = (3.0, 4.2)
T_LOWER = (2.3, 2.7)
HEAT_ALPHA = 0.30
PHONE = (780, 1688, 640)   # Player-Cam screen (2x a 390 x 844 phone) and the frame width cropped round the player
CARD_H = 222
PANEL_W = 540              # lower-third and swing card, bottom left; clear of the players in the featured frames


# ---------------------------------------------------------------------------------------------- drawing
class Painter:
    """Draws one overlay state over a frozen frame: matplotlib's Agg (antialiased, alpha-blended strokes) for the
    pitch graphics, PIL for the grade, the tags and the card."""

    def __init__(self, m: dict, frame: np.ndarray, cam: Camera, fut: Futures | None,
                 referee_lines: list | None = None, mode: str = "broadcast"):
        self.m, self.frame, self.cam, self.fut, self.mode = m, frame, cam, fut, mode
        self.fig = Figure(figsize=(W / 100, H / 100), dpi=100 * SS)
        self.fig.patch.set_alpha(0)
        self.canvas = FigureCanvasAgg(self.fig)
        self.ax = self.fig.add_axes((0, 0, 1, 1))
        self.actor_m = at_m(m["actor"], cam)
        self.target_m = at_m(m["target"], cam) if m.get("target") else None
        self.ball = ball_m(m, cam)
        self.referee = [cam.project(densify(seg)) for seg in (referee_lines or [])]
        if fut:
            lo, hi = (-GHOST_MARGIN_M, -GHOST_MARGIN_M), (105 + GHOST_MARGIN_M, 68 + GHOST_MARGIN_M)
            self.base_px = [cam.project(np.clip(catmull_rom(p), lo, hi)) for p in fut.baseline]
            self.alt_px = [cam.project(np.clip(catmull_rom(p), lo, hi)) for p in fut.alternative]
            shot_to = np.median([p[1] for p in fut.baseline], axis=0) if fut.baseline else None
            self.ghosts = [g for g in (self._branch(fut.baseline, shot_to, WHITE, T_BASE),
                                       self._branch(fut.alternative, self.target_m, ORANGE, T_ALT)) if g]
        self.v8 = m.get("style") == "v8"                   # PITCHSIGHT: v6's rules, the fixed right stack, glass
        self.v6 = m.get("style") in ("v6", "v8")           # v5's drawing with v6's rules (owner, 23 Oct)
        self.v5 = m.get("style") in ("v5", "v6", "v8")
        self.v4 = m.get("style") in ("v4", "v5", "v6", "v8")           # v5 keeps v4's ramp, punch-in, rewind and lower-thirds
        self.xg = load_json(m.get("xg"), "result") if m.get("xg") else None
        if self.v5 and self.xg is None and m.get("xg"):
            self.xg = load_json(m["xg"])                   # track A writes v5 files bare or wrapped
        self.goal10 = load_json(m.get("goal10"), "result")
        if self.v5 and m.get("strike"):                   # a finish: the strike itself (track A's shots file)
            doc = load_json(m["strike"]["file"])
            shots = (doc.get("result") or doc)["shots"]
            hit = next(x for x in shots if x["clip_ms"] == int(m["strike"]["clip_ms"]))
            strike = {"kind": "shoot", "xg": hit["xg"], "strike_xg": hit["xg"], "label": "Shot",
                      "distance_m": hit.get("distance_m"), "outcome": hit["outcome"]}
            if m["strike"].get("value_only"):             # a decision freeze: the strike's number, the freeze's picture
                self.xg = {**(self.xg or {}), "actual": {**(self.xg or {}).get("actual", {}), **strike}}
            else:
                self.xg = {**(self.xg or {}), "actual": strike, "comparison": "finish",
                           "formula": (doc.get("result") or doc)["model"]["xg"]}
                self.ball = np.array([hit["x"], hit["y"]], float)
                self.actor_m = self.ball                  # the shooter is where he struck it
        if self.v5:
            self.v5_geom = self._v5_geometry()
        if self.v4 and not self.v5 and self.goal10 and "options" in self.goal10:
            self.lanes = self._decision_lanes()
        elif self.v4 and not self.v5 and fut:
            self.lanes = [ln for ln in (self._lane(fut.baseline, WHITE, T_BASE, "actual"),
                                        self._lane(fut.alternative, ORANGE, T_ALT, "alternative")) if ln]
        self.trail_px = None
        self.ruling = load_json(m.get("ruling"), "result")
        self.contact_px = None
        if self.ruling:                                          # Fourth Official: the fouler's run, the contact
            run = densify(self.ruling["fouler_run"], 0.1)
            self.trail_px = cam.project(run)
            self.contact_px = cam.project(ground_circle(self.ruling["contact_point"], 0.75))
        elif self.target_m is not None:                          # stop at the receiver's ring
            curve = pass_curve(self.ball, self.target_m)
            far = np.linalg.norm(curve - self.target_m, axis=1) > RING_R + 0.35
            self.trail_px = cam.project(curve[far])
        elif fut and fut.alternative:                            # a carry: the alternative's median first second
            med = np.median(np.array([np.asarray(p, float)[:3] for p in fut.alternative]), axis=0)
            path = catmull_rom(med)[: SUBDIV + 1]
            self.trail_px = cam.project(path[np.linalg.norm(path - path[0], axis=1) > RING_R + 0.35])
        self.spot = self._spotlight()
        self.heat = self._heatmap() if mode == "analyst" else None
        self.font = {s: ImageFont.truetype(FONT, s) for s in (22, 26, 30, 34, 50, 64)}  # bold sizes
        self.line = None
        if m.get("line") and (ROOT / m["line"]).exists():          # the reviewed lower-third (T-109)
            doc = json.loads((ROOT / m["line"]).read_text())
            self.line = doc["json"] if doc.get("verified") else None
        if self.v4:                                       # v4 lower-thirds come only from track B's v4 lines
            doc = load_json(m.get("line_v5") or m.get("line_v4"), "result")
            ok = doc and (doc.get("verdict") in ("finishing", "finish")) == bool(m.get("finishing"))   # a goal line never
            self.line = {"headline": doc["lower_third"]} if ok and doc.get("lower_third") else None   # an alternative
            if ok:                                        # their overlay labels, never internal ids
                labels = {k: v for k, v in doc.get("decision", {}).get("overlay_labels", {}).items() if v}
                m["options"] = {**(m.get("options") or {}), **labels}
        cue = load_json(m.get("cue"))
        if cue and all(c.get("verified") for c in cue["explain"]["claims"]):   # a Fact-Checked cue's own text
            self.line = cue["text"]
        self.font_reg = {s: ImageFont.truetype(FONT_REG, s) for s in (20, 22)}

    # -- v5: xG from the real-data reference model (track A cache/v5) ---------------------------------------
    def v5_options(self) -> list[dict]:
        """The pass drawn as better, by the lead's rule: track A says 'pass higher', it beats the shot by at least
        `min_gap` xG (0.04) and the receiver is more than 0.5 m onside; at most one. None on shot-only beats."""
        x = self.xg or {}
        if self.m.get("finishing") or self.m.get("shot_only") or x.get("comparison") != "pass higher":
            return []
        hero = x.get("best_alternative")
        if not hero or hero.get("xg_after_pass") is None:
            return []
        gap = hero["xg_after_pass"] - x["actual"]["xg"]
        onside = hero.get("onside_margin_m")
        if gap < float(self.m.get("min_gap", 0.04)) - 1e-9 or (onside is not None and onside <= 0.5) \
                or hero.get("offside_risk"):
            return []
        return [hero]

    def verified_names(self) -> dict[str, str]:
        """{label: name} from track B's names_verified.json, for links at this moment (clip_ms) only."""
        if not hasattr(self, "_names"):
            self._names = {}
            path = FOOTAGE / self.m["clip"] / "names_verified.json"
            ms = int(round(float(self.m.get("moment_ms", self.m["t_s"] * 1000))))
            if path.exists():
                for name, v in json.loads(path.read_text())["names"].items():
                    for link in v.get("links", []):
                        if link.get("label") and abs(int(link.get("clip_ms", -1e9)) - ms) <= 200:
                            self._names[str(link["label"])] = name
        return self._names

    def area_label(self, x: float, y: float) -> str:
        """Where a player stands, for an unnamed receiver: in the box, on its edge (within 2 m) or outside it."""
        gx = 105.0 if self.m.get("attacks", "+x") == "+x" else 0.0
        depth, wide = abs(x - gx), abs(y - 34)
        if depth <= 16.5 and wide <= 20.16:
            return "in the box"
        if depth <= 18.5 and wide <= 22.2:
            return "edge of the box"
        return "outside the box"

    def option_label(self, o: dict) -> str | None:
        """'Saka' for a verified name; v6: else a shirt number, else nothing (no placeholders); before v6: the team
        and where he stands. Never an internal id."""
        if o.get("name"):
            return o["name"].split()[-1]
        if self.v6:                                        # a verified name for this label at this moment
            name = self.verified_names().get(str(o.get("label")))
            if name:
                return name.split()[-1]
        if self.v6:                                        # a shirt number, from `shirt` or a '#19' label
            if o.get("shirt"):
                return f"#{o['shirt']}"
            return o["label"] if str(o.get("label", "")).startswith("#") else None
        return f"{self.m.get('team_name', 'Teammate')} · {self.area_label(o['x'], o['y'])}"

    def _v5_geometry(self) -> dict:
        gx = 105.0 if self.m.get("attacks", "+x") == "+x" else 0.0
        posts = np.array([[gx, 34 - 3.66], [gx, 34 + 3.66]])
        keeper = None
        doc = json.loads((FOOTAGE / self.m["moment_file"]).read_text()) if self.m.get("moment_file") else {}
        team = self.m.get("team", "home")
        others = [p for p in doc.get("players", []) if p["team"] != team]
        gk = [p for p in others if p.get("slot") == "GK" or p.get("label") == "GK"]
        if not gk and others:                          # the opponent nearest his goal
            gk = [min(others, key=lambda p: abs(p["x"] - gx) + 0.3 * abs(p["y"] - 34))]
        moment_s = doc.get("clip_ms", 0) / 1000 if doc else None
        if gk and (moment_s is None or abs(moment_s - self.m["t_s"]) <= 0.3):   # a keeper seen at this instant
            keeper = np.array([gk[0]["x"], gk[0]["y"]])
        # the target spot: the middle of the larger gap between the keeper and a post
        if keeper is not None:
            ky = float(np.clip(keeper[1], posts[0, 1], posts[1, 1]))
            lo, hi = (posts[0, 1], ky), (ky, posts[1, 1])
            gap = lo if lo[1] - lo[0] >= hi[1] - hi[0] else hi
            target = np.array([gx, (gap[0] + gap[1]) / 2])
        else:
            target = np.array([gx, 34.0])
        return {"posts": posts, "keeper": keeper, "target": target, "gx": gx}

    def _arc(self, a, b, bend: float = 0.12, n: int = 48) -> np.ndarray:
        """A curved pass from a to b in metres (quadratic Bezier, bowed to the left of travel)."""
        return pass_curve(a, b, bend=bend, n=n)

    def _v5_graphics(self, ax, t: float, a_all: float) -> None:
        g = self.v5_geom
        shot = window(t, *T_BASE)
        if shot > 0 and (self.xg or {}).get("actual", {}).get("kind", "shoot") == "shoot":
            cone = np.vstack([np.linspace(self.ball, g["posts"][0], 24), np.linspace(g["posts"][0], g["posts"][1], 12),
                              np.linspace(g["posts"][1], self.ball, 24)])
            px = self.cam.project(cone)
            ax.add_patch(Polygon(px, closed=True, fc=(1, 1, 1, 0.14 * shot * a_all), ec=(1, 1, 1, 0.55 * shot * a_all),
                                 lw=1.6))
            if g["keeper"] is not None:
                kr = self.cam.project(ground_circle(g["keeper"], 0.9))
                ax.plot(kr[:, 0], kr[:, 1], color=(0, 0, 0, 0.5 * shot * a_all), lw=6)
                ax.plot(kr[:, 0], kr[:, 1], color=(*(np.array(YELLOW) / 255), shot * a_all), lw=3)
            tp = self.cam.project([g["target"]])[0]
            for r, al in ((26, 0.18), (16, 0.35), (8, 0.95)):          # a glowing spot in the goal mouth
                ax.scatter([tp[0]], [tp[1]], s=r * r, color=(1, 1, 1, al * shot * a_all), lw=0, zorder=6)
        for k, o in enumerate(self.v5_options()):
            grow = window(t, *T_ALT) if k == 0 else window(t, T_ALT[0] + 0.4, T_ALT[1] + 0.4)
            if grow <= 0:
                continue
            hero = k == 0
            col = np.array(ORANGE) / 255 if hero else np.array((235, 238, 245)) / 255
            fade = 1.0 if hero else 0.45
            end = np.asarray([o["x"], o["y"]], float)       # the pass to where he stands (track A's xG spot)
            run_to = o.get("run_to") or o.get("arrival")
            arc = self.cam.project(self._arc(self.ball, end))
            m = max(2, int(round(grow * len(arc))))
            p = arc[:m]
            if hero:
                ax.plot(p[:, 0], p[:, 1], color=(*col, 0.25 * a_all), lw=20, solid_capstyle="round")   # glow
            ax.plot(p[:, 0], p[:, 1], color=(0, 0, 0, 0.55 * fade * a_all), lw=9 if hero else 6, solid_capstyle="round")
            ax.plot(p[:, 0], p[:, 1], color=(*col, fade * a_all), lw=5 if hero else 3, solid_capstyle="round")
            if grow >= 1:
                self._arrowhead(ax, p, col, fade * a_all, size=30.0 if hero else 20.0)
                ring = self.cam.project(ground_circle(end, 1.1))
                ax.plot(ring[:, 0], ring[:, 1], color=(0, 0, 0, 0.5 * fade * a_all), lw=7)
                ax.plot(ring[:, 0], ring[:, 1], color=(*col, fade * a_all), lw=3.5)
                if run_to is not None and np.linalg.norm(np.asarray(run_to) - end) > 0.6:   # his tracked run
                    run = self.cam.project(np.linspace(end, np.asarray(run_to, float), 20))
                    ax.plot(run[:, 0], run[:, 1], color=(1, 1, 1, 0.9 * fade * a_all), lw=2.8, dashes=(3, 2.5))
                    self._arrowhead(ax, run, np.array([1, 1, 1]), 0.9 * fade * a_all, size=16.0)

    def _v5_labels(self, im: Image.Image, t: float, fade: float) -> None:
        """Ground labels: the shot's xG at the goal mouth, each option's xG after the pass at its ring."""
        x = self.xg or {}
        layer = hi_layer(im.size)
        d = HiDraw(layer)
        items = []
        a0 = window(t, T_BASE[1] - 0.3, T_BASE[1] + 0.3) * (1 - fade)
        if a0 > 0 and x.get("actual"):
            items.append((self.v5_geom["target"], f"{'SHOT · ' if self.v8 else 'SHOT  '}{x['actual']['xg']:.2f} xG",
                          WHITE, a0, -70))
        for k, o in enumerate(self.v5_options()):
            a = window(t, T_ALT[1] + 0.4 * k, T_ALT[1] + 0.4 * k + 0.4) * (1 - fade) * (1.0 if k == 0 else 0.6)
            end = [o["x"], o["y"]]
            label = self.option_label(o)
            if self.v8:                                  # the pass pill: name · arrives · worth
                text = (f"{label} · " if label else "") + f"{o['p_pass'] * 100:.0f}% · {o['xg_after_pass']:.2f} xG"
            else:
                text = f"{label.upper() + '  → ' if label else 'PASS → '}{o['xg_after_pass']:.2f} xG"
            items.append((end, text, ORANGE if k == 0 else WHITE, a, 40))
        for where, text, colour, a, dy in items:
            if a <= 0:
                continue
            pt = self.cam.project([where])[0]
            f = ImageFont.truetype(FONT, 28) if self.v8 else self.font[26]
            ph = 46 if self.v8 else 42
            w = d.textlength(text, font=f) + 28
            x0 = float(np.clip(pt[0] - w / 2, 24, W - 24 - w))
            y0 = float(np.clip(pt[1] + dy, 24, H - 300))
            if self.v8 and x0 + w > W - 64 - 760 - 12 and y0 + ph > H - 150 - 330:   # never under the card
                x0 = max(24.0, W - 64 - 760 - 12 - w)
            d.rounded_rectangle((x0, y0, x0 + w, y0 + ph), radius=14 if self.v8 else 10, fill=(*PANEL, int(228 * a)),
                                outline=(*colour, int(255 * a)), width=3)
            d.text((x0 + w / 2, y0 + ph / 2), text, font=f, fill=(*colour, int(255 * a)), anchor="mm")
        flatten(im, layer)

    def _card_v5(self, im: Image.Image, a: float, swing: float, t: float):
        """The xG card: the shot, the hero pass (when one beats it), a counting xG number, the formula."""
        x = self.xg
        act = x["actual"]
        if self.m.get("strike"):                         # the strike frame: from how far
            dist = act.get("distance_m")
            if dist is None:
                dist = float(np.hypot(self.ball[0] - self.v5_geom["gx"], self.ball[1] - 34))
            shot_label = f"Shot from {dist:.0f} m"
        else:                                            # a decision freeze, before the strike
            shot_label = "Shot from here"
        rows = [(shot_label, act["xg"], (196, 204, 214))]
        opts = self.v5_options()
        if opts:
            label = self.option_label(opts[0])
            rows.append((f"Pass to {label}" if label else "Pass", opts[0]["xg_after_pass"], ORANGE))
        x0, w = self._panel_x(a), PANEL_W + 60
        formula = self._wrap(x.get("formula", ""), self.font_reg[20], w - 64)
        has_note = bool(self.m.get("card_note") or self.m.get("finishing"))
        h = 58 + 70 * len(rows) + (52 if has_note else 0) + 24 * len(formula) + 24
        y0 = H - 96 - h
        layer = hi_layer(im.size)
        d = HiDraw(layer)
        al = int(255 * a)
        d.rounded_rectangle((x0, y0, x0 + w, y0 + h), radius=10, fill=(*PANEL, int(232 * a)))
        d.rectangle((x0, y0, x0 + 8, y0 + h), fill=(*ORANGE, al))
        d.text((x0 + 32, y0 + 20), "EXPECTED GOALS (xG)", font=self.font[22], fill=(169, 180, 194, al))
        top = max(r[1] for r in rows) * 1.2 or 1.0
        bx0, bx1 = x0 + 32, x0 + w - 150
        for k, (label, v, col) in enumerate(rows):
            grow = swing if k else (1.0 if self.v6 else window(t, T_CARD[0], T_CARD[0] + 0.8))   # v6: no count-up
            y = y0 + 56 + 70 * k
            d.text((bx0, y), label, font=self.font_reg[22], fill=(230, 236, 242, al))
            by = y + 30
            d.rounded_rectangle((bx0, by, bx1, by + 12), radius=6, fill=(255, 255, 255, int(28 * a)))
            d.rounded_rectangle((bx0, by, bx0 + max(12, (bx1 - bx0) * v / top * grow), by + 12), radius=6,
                                fill=(*col, al))
            shown = v if self.v6 or k else v * grow                            # v6 prints only the value
            d.text((x0 + w - 28, by + 6), f"{shown:.2f}", font=self.font[34],
                   fill=(*col, int(al * (1 if k == 0 else grow))), anchor="rm")
        yy = y0 + 56 + 70 * len(rows)
        note = self.m.get("card_note") or ("Scored." if self.m.get("finishing") else None)
        if note:
            d.text((x0 + 32, yy), note, font=self.font[30], fill=(*ORANGE, al))
            yy += 52
        for k, line in enumerate(formula):
            d.text((x0 + 32, yy + 24 * k), line, font=self.font_reg[20], fill=(169, 180, 194, al))
        flatten(im, layer)

    def _glass(self, im: Image.Image, box, a: float) -> ImageDraw.ImageDraw:
        """v8: a dark glass panel (the picture blurred under it, a hairline, a thin team accent); returns a drawer on
        a layer the caller pastes."""
        from PIL import ImageFilter
        box = tuple(int(v) for v in box)
        region = im.crop(box).filter(ImageFilter.GaussianBlur(16))
        mask = Image.new("L", region.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, region.size[0] - 1, region.size[1] - 1), radius=14,
                                               fill=int(255 * a))
        im.paste(region, box[:2], mask)
        d = ImageDraw.Draw(im, "RGBA")
        d.rounded_rectangle(box, radius=14, fill=(14, 18, 24, int(178 * a)), outline=(255, 255, 255, int(40 * a)),
                            width=1)
        kit = tuple((self.m.get("kits") or {}).get(self.m.get("team", "home"), ORANGE))   # the attacking side's kit
        d.rounded_rectangle((box[0] + 14, box[1], box[2] - 14, box[1] + 4), radius=2, fill=(*kit, int(255 * a)))
        return d

    def _card_v8(self, im: Image.Image, a: float, swing: float, t: float):
        """The xG card in the fixed right stack: the shot, the hero pass (when one beats it), the outcome; type from
        28 px, no footnote (the explainer and the caption carry the model)."""
        x = self.xg
        act = x["actual"]
        if self.m.get("strike"):
            dist = act.get("distance_m")
            if dist is None:
                dist = float(np.hypot(self.ball[0] - self.v5_geom["gx"], self.ball[1] - 34))
            shot_label = f"Shot from {dist:.0f} m"
        else:
            shot_label = "Shot from here"
        rows = [(shot_label, act["xg"], (196, 204, 214))]
        opts = self.v5_options()
        if opts:
            label = self.option_label(opts[0])
            rows.append((f"Pass to {label}" if label else "Pass", opts[0]["xg_after_pass"], ORANGE))
        note = self.m.get("card_note") or ("Scored." if self.m.get("finishing") else None)
        w = 760
        h = 76 + 92 * len(rows) + (56 if note else 0) + 12
        x0, y0 = W - 64 - w + int((1 - a) * 60), H - 150 - h
        d = self._glass(im, (x0, y0, x0 + w, y0 + h), a)
        al = int(255 * a)
        d.text((x0 + 28, y0 + 24), "EXPECTED GOALS (xG)", font=ImageFont.truetype(FONT, 26), fill=(169, 180, 194, al))
        top = max(r[1] for r in rows) * 1.2 or 1.0
        bx0, bx1 = x0 + 28, x0 + w - 170
        for k, (label, v, col) in enumerate(rows):
            grow = swing if k else 1.0
            y = y0 + 70 + 92 * k
            d.text((bx0, y), label, font=ImageFont.truetype(FONT_REG, 30), fill=(230, 236, 242, al))
            by = y + 46
            d.rounded_rectangle((bx0, by, bx1, by + 16), radius=8, fill=(58, 64, 74, al))
            d.rounded_rectangle((bx0, by, bx0 + max(16, (bx1 - bx0) * v / top * grow), by + 16), radius=8,
                                fill=(*col, al))
            d.text((x0 + w - 28, y + 36), f"{v:.2f}", font=ImageFont.truetype(FONT, 52),
                   fill=(*col, int(al * (1 if k == 0 else grow))), anchor="rm")
        if note:
            d.text((x0 + 28, y0 + 70 + 92 * len(rows)), note, font=ImageFont.truetype(FONT, 30), fill=(*ORANGE, al))

    def _score_v8(self, im: Image.Image, a: float) -> None:
        """Team xG under the broadcast score bug at the frozen moment (xg_running_0), as on the live beats."""
        if not self.m.get("race") or a <= 0:
            return
        doc = json.loads((ROOT / self.m["race"]).read_text())
        race = {**doc.get("result", doc), **(self.m.get("race_labels") or {})}
        now = float(self.m["t_s"]) * 1000
        pts = [p for p in race["series"] if p["clip_ms"] <= now] or [{"home_xg": 0.0, "away_xg": 0.0}]
        cur = pts[-1]
        f = ImageFont.truetype(FONT, 38)
        text = f"xG  {race['home_short']} {cur['home_xg']:.2f} · {cur['away_xg']:.2f} {race['away_short']}"
        probe = ImageDraw.Draw(im)
        x0, y0 = 96.0, 164.0
        w = probe.textlength(text, font=f) + 40
        d = self._glass(im, (x0, y0, x0 + w, y0 + 60), a)
        d.text((x0 + 22, y0 + 30), text, font=f, fill=(255, 255, 255, int(255 * a)), anchor="lm")

    def _straight_lane(self, a, b, colour, span, key) -> dict:
        pts = np.linspace(np.asarray(a, float), np.asarray(b, float), SUBDIV * 2 + 1)
        return {"px": self.cam.project(pts), "band": None, "n": len(pts), "colour": np.array(colour) / 255,
                "span": span, "key": key}

    def _decision_lanes(self) -> list[dict]:
        """v4 with track A's decision file: what he did (a shot: to the middle of the goal mouth) and, when one is
        better beyond the noise, the alternative (a pass: to the receiver; a carry: 8 m along its direction)."""
        g = self.goal10
        act = g["options"][0]["option"]
        goal_x = 105.0 if self.m.get("attacks", "+x") == "+x" else 0.0
        lanes = []
        if act["kind"] == "shoot":
            lanes.append(self._straight_lane(self.ball, [goal_x, 34.0], WHITE, T_BASE, "actual"))
        alt = self.alternative_option()
        if alt is not None:
            op = alt["option"]
            if op["kind"] == "pass" and self.target_m is not None:
                lanes.append(self._straight_lane(self.ball, self.target_m, ORANGE, T_ALT, "alternative"))
            elif op["kind"] == "carry":
                d = np.asarray(op.get("direction", [1, 0]), float)
                lanes.append(self._straight_lane(self.ball, self.ball + d / np.linalg.norm(d) * 8.0, ORANGE, T_ALT,
                                                 "alternative"))
        return lanes

    def _lane(self, paths, colour, span, key) -> dict | None:
        """v4: one branch as its median path (bold, glowing, an arrow at the end) inside a soft band of the spread
        around it, instead of dozens of strands. From track A's goal10 file when it carries median paths and bands,
        else derived here from the counterfactual's futures (median position and median distance to it at each
        second, first LANE_S seconds)."""
        g = (self.goal10 or {}).get("median_paths", {}).get(key)
        if g:
            med = np.asarray(g, float)
            band = np.asarray(self.goal10["band"][key], float)[:, 2]
        elif paths:
            secs = int((self.m.get("lanes_s") or {}).get(key, LANE_S[key]))
            cut = np.array([np.asarray(p, float)[: secs + 1] for p in paths])
            med = np.median(cut, axis=0)
            band = np.median(np.linalg.norm(cut - med, axis=2), axis=0)
        else:
            return None
        if key == "alternative" and self.target_m is not None and not g:   # a pass: the lane ends at the receiver
            med = np.vstack([med[:1], self.target_m])
        sm = catmull_rom(med) if len(med) >= 3 else np.linspace(med[0], med[-1], SUBDIV + 1)   # a 1 s lane: straight
        r = np.interp(np.linspace(0, len(band) - 1, len(sm)), np.arange(len(band)), band)
        r = np.clip(r, 0.3, 6.0)
        tang = np.gradient(sm, axis=0)
        tang /= np.linalg.norm(tang, axis=1, keepdims=True) + 1e-9
        nrm = np.c_[-tang[:, 1], tang[:, 0]]
        poly = np.vstack([sm + nrm * r[:, None], (sm - nrm * r[:, None])[::-1]])
        return {"px": self.cam.project(sm), "band": self.cam.project(poly), "n": len(sm),
                "colour": np.array(colour) / 255, "span": span, "key": key}

    def _branch(self, paths, anchor, colour, span) -> dict | None:
        """One branch of the futures as drawn: the GHOST_KEEP paths nearest the branch's median over the first
        GHOST_S seconds (the spray of outliers left out), every 6th of them bolder, each segment's opacity fading
        after the first leg unless it stays near where the branch is going (`anchor`: the receiver, or where the
        shots go)."""
        if not paths:
            return None
        cut = np.array([np.asarray(p, float)[: GHOST_S + 1] for p in paths])
        med = np.median(cut, axis=0)
        order = np.argsort(np.linalg.norm(cut - med, axis=2).mean(axis=1))[:GHOST_KEEP]
        lo, hi = (-GHOST_MARGIN_M, -GHOST_MARGIN_M), (105 + GHOST_MARGIN_M, 68 + GHOST_MARGIN_M)
        segs, alpha, bold = [], [], []
        for rank, i in enumerate(order):
            m = np.clip(catmull_rom(cut[i]), lo, hi)
            t = np.arange(len(m)) / SUBDIV
            fade_t = np.clip(1 - (t - GHOST_FADE_T[0]) / (GHOST_FADE_T[1] - GHOST_FADE_T[0]), 0, 1)
            d = np.linalg.norm(m - anchor, axis=1) if anchor is not None else np.full(len(m), np.inf)
            fade_d = np.clip(1 - (d - GHOST_FADE_D[0]) / (GHOST_FADE_D[1] - GHOST_FADE_D[0]), 0, 1)
            px = self.cam.project(m)
            segs.append(np.stack([px[:-1], px[1:]], axis=1))
            alpha.append(np.maximum(fade_t, fade_d)[1:])
            bold.append(rank % (GHOST_KEEP // GHOST_REPS) == 0)
        return {"segs": segs, "alpha": alpha, "bold": bold, "colour": np.array(colour) / 255, "span": span}

    def _heatmap(self) -> np.ndarray | None:
        """Analyst mode: the frozen moment's pitch-control snapshot (T-109, same grid as the overlay's heatmap: home
        share in 2 m cells) laid on the grass in the two kits' colours, RGBA in [0, 1]; contested cells stay clear,
        and nothing is painted over the players or above the boards."""
        pc = pitch_control_for(self.m, self.fut.cf if self.fut else None)
        if pc is None:
            return None
        grid, mirrored = pc
        step = 2
        vs, us = np.mgrid[0:H:step, 0:W:step]
        xy = self.cam.unproject(np.c_[us.ravel(), vs.ravel()]).reshape(vs.shape + (2,))
        x, y = xy[..., 0], xy[..., 1]
        if mirrored:                                   # the grid is in the engine's frame for the period
            x, y = PITCH_L - x, PITCH_W - y
        cell = PITCH_L / grid.shape[1]
        v = ndi.map_coordinates(grid.astype(float), [y / 2.0 - 0.5, x / cell - 0.5], order=1, mode="nearest")
        on = (xy[..., 0] >= 0) & (xy[..., 0] <= PITCH_L) & (xy[..., 1] >= 0) & (xy[..., 1] <= PITCH_W)
        kits = self.m.get("kits") or {"home": (63, 167, 255), "away": (255, 61, 90)}
        rgb = np.where((v >= 0.5)[..., None], np.array(kits["home"]) / 255, np.array(kits["away"]) / 255)
        alpha = HEAT_ALPHA * np.clip(np.abs(v - 0.5) * 2, 0, 1) * on
        out = np.concatenate([rgb, alpha[..., None]], axis=-1).repeat(step, 0).repeat(step, 1)[:H, :W]
        _, top = fit_spec(self.m)
        out[np.arange(H)[:, None] < top[None, :], 3] = 0
        out[occluders(self.frame), 3] = 0
        out[..., 3] = ndi.gaussian_filter(out[..., 3], 1.5)
        return out

    def _spotlight(self) -> np.ndarray:
        """1 on the grass within ~3 m of the lit players, falling to 0, in pixels."""
        im = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(im)
        for c in [self.actor_m, self.target_m]:
            if c is not None:
                d.polygon([tuple(p) for p in self.cam.project(ground_circle(c, 2.6))], fill=255)
        return np.asarray(im.filter(ImageFilter.GaussianBlur(18)), float)[..., None] / 255

    # -- pitch graphics (Agg) ---------------------------------------------------------------------------------
    def _graphics(self, t: float, fade: float) -> np.ndarray:
        ax = self.ax
        ax.clear()
        ax.set_xlim(0, W)
        ax.set_ylim(H, 0)
        ax.axis("off")
        ax.patch.set_alpha(0)
        a_all = 1 - fade
        if self.v5:
            self._v5_graphics(ax, t, a_all)
        for ln in getattr(self, "lanes", []) if self.v4 else []:
            grow = window(t, *ln["span"])
            if grow <= 0:
                continue
            col, n = ln["colour"], ln["n"]
            k = max(2, int(round(grow * n)))
            band = ln["band"]                                    # the band grows with the line: both halves
            if band is not None:
                half = len(band) // 2
                kb = max(2, int(round(grow * half)))
                shown = np.vstack([band[:kb], band[len(band) - kb:]])
                ax.add_patch(Polygon(shown, closed=True, fc=(*col, 0.16 * a_all), ec="none"))
            p = ln["px"][:k]
            ax.plot(p[:, 0], p[:, 1], color=(*col, 0.22 * a_all), lw=18, solid_capstyle="round")   # glow
            ax.plot(p[:, 0], p[:, 1], color=(0, 0, 0, 0.6 * a_all), lw=9, solid_capstyle="round")
            ax.plot(p[:, 0], p[:, 1], color=(*col, a_all), lw=5, solid_capstyle="round")
            if grow >= 1:
                self._arrowhead(ax, p, col, a_all, size=34.0)
        for g in getattr(self, "ghosts", []) if not self.v4 else []:
            grow = window(t, *g["span"])
            if grow <= 0:
                continue
            for segs, alpha, bold in zip(g["segs"], g["alpha"], g["bold"], strict=True):
                k = max(1, int(round(grow * len(segs))))
                a = alpha[:k] * a_all * (0.62 if bold else 0.2)
                if bold:                                         # a dark edge so the bold paths read on grass
                    ax.add_collection(LineCollection(segs[:k], colors=[(0, 0, 0, 0.25 * x) for x in a],
                                                     linewidths=4.0, capstyle="round"))
                ax.add_collection(LineCollection(segs[:k], colors=[(*g["colour"], x) for x in a],
                                                 linewidths=2.2 if bold else 1.4, capstyle="round"))
        rings = window(t, *T_RINGS)
        if rings > 0:
            for c, colour, lw in ((self.actor_m, WHITE, 3.2), (self.target_m, ORANGE, 3.6)):
                if c is None:
                    continue
                r = RING_R * (0.6 + 0.4 * rings)
                ring = self.cam.project(ground_circle(c, r))
                col = np.array(colour) / 255
                ax.add_patch(Polygon(ring, closed=True, fill=True, fc=(*col, 0.18 * rings * a_all), ec="none"))
                ax.plot(ring[:, 0], ring[:, 1], color=(0, 0, 0, 0.45 * rings * a_all), lw=lw + 3.5,
                        solid_capstyle="round")
                ax.plot(ring[:, 0], ring[:, 1], color=(*col, 0.3 * rings * a_all), lw=lw * 3.2,
                        solid_capstyle="round")
                ax.plot(ring[:, 0], ring[:, 1], color=(*col, rings * a_all), lw=lw, solid_capstyle="round")
        trail = window(t, *T_TRAIL)
        if trail > 0 and self.trail_px is not None and self.ruling:
            k = max(2, int(round(trail * (len(self.trail_px) - 1))) + 1)
            p = self.trail_px[:k]
            col = np.array(YELLOW) / 255
            ax.plot(p[:, 0], p[:, 1], color=(0, 0, 0, 0.6 * a_all), lw=9.5, solid_capstyle="round")
            ax.plot(p[:, 0], p[:, 1], color=(*col, a_all), lw=5.2, solid_capstyle="round")
            if trail >= 1:
                self._arrowhead(ax, p, col, a_all, size=26.0)
                c = self.contact_px
                ax.add_patch(Polygon(c, closed=True, fc=(*col, 0.35 * a_all), ec=(0, 0, 0, 0.6 * a_all), lw=2.5))
                ax.plot(c[:, 0], c[:, 1], color=(*col, a_all), lw=2.5)
        elif trail > 0 and self.trail_px is not None and not self.v4:   # v4: the alternative's lane is the pass
            k = max(2, int(round(trail * (len(self.trail_px) - 1))) + 1)
            p = self.trail_px[:k]
            col = np.array(ORANGE) / 255
            ax.plot(p[:, 0], p[:, 1], color=(0, 0, 0, 0.6 * a_all), lw=9.5, solid_capstyle="round")
            ax.plot(p[:, 0], p[:, 1], color=(*col, a_all), lw=5.2, dashes=(3.0, 1.5), dash_capstyle="round")
            if trail >= 1:
                self._arrowhead(ax, p, col, a_all)
        for line in self.referee:
            ax.plot(line[:, 0], line[:, 1], color=(*(np.array(YELLOW) / 255), a_all), lw=3.0)
        self.canvas.draw()
        return downsample_rgba(np.asarray(self.canvas.buffer_rgba(), float) / 255, W, H)

    @staticmethod
    def _arrowhead(ax, p, col, a_all, size: float = 30.0):
        """An arrowhead in pixels at the end of the drawn trail."""
        d = p[-1] - p[-3]
        d /= np.linalg.norm(d)
        n = np.array([-d[1], d[0]])
        tip = p[-1] + d * size * 0.5
        tri = np.array([tip, tip - d * size + n * size * 0.55, tip - d * size - n * size * 0.55])
        ax.add_patch(Polygon(tri, closed=True, fc=(*col, a_all), ec=(0, 0, 0, 0.6 * a_all), lw=2.0))

    # -- frame, tags, card (PIL) ------------------------------------------------------------------------------
    def render(self, t: float, standin_mark: bool = False) -> Image.Image:
        fade = window(t, *FADE_OUT)
        grade = window(t, *T_GRADE) * (1 - fade)
        f = self.frame.astype(float) / 255
        lum = f @ np.array([0.299, 0.587, 0.114])
        dim = 1 - grade * (0.30 * (1 - self.spot))                      # lit players, the rest a step down
        sat = 1 - 0.25 * grade * (1 - self.spot)
        f = (lum[..., None] + (f - lum[..., None]) * sat) * dim
        if self.heat is not None:
            ha = self.heat[..., 3:4] * window(t, *T_RINGS) * (1 - fade)
            f = f * (1 - ha) + self.heat[..., :3] * ha
        g = self._graphics(t, fade)
        f = f * (1 - g[..., 3:4]) + g[..., :3] * g[..., 3:4]
        im = Image.fromarray(np.clip(f * 255, 0, 255).astype(np.uint8))
        im, to_screen = self._zoom(im, t, fade)
        a = window(t, *T_RINGS) * (1 - fade)
        if a > 0:
            tags = [(self.m["actor"].get("label"), self.actor_m, WHITE)]
            if self.target_m is not None:
                tags.append((self.m["target"].get("label"), self.target_m, ORANGE))
            self._tags(im, tags, to_screen, a)
        if self.mode == "player_cam":
            return self._phone(im, t, fade)
        c = window(t, *T_CARD) * (1 - fade)
        if self.v5:
            self._v5_labels(im, t, fade)
            if c > 0 and self.xg and not self.m.get("no_card"):   # no_card: the arcs alone (the pipeline's left half)
                (self._card_v8 if self.v8 else self._card_v5)(im, c, window(t, *T_SWING), t)
            if self.v8 and not self.m.get("no_card"):     # the Newsroom's still is cropped: no strip on it
                self._score_v8(im, 1 - fade)
        if self.v4 and getattr(self, "lanes", None):
            self._lane_labels(im, window(t, T_ALT[1] - 0.2, T_ALT[1] + 0.4) * (1 - fade))
        if c > 0 and self.v4 and not self.v5 and self.goal10 and self.mode != "casual":
            self._card_v4(im, c, window(t, *T_SWING))
        elif c > 0 and self.fut and self.mode != "casual":
            self._card(im, c, window(t, *T_SWING))
        elif c > 0 and self.ruling:
            self._ruling_card(im, c)
        lt = window(t, *T_LOWER) * (1 - fade)
        if lt > 0 and self.line and not self.v8:        # v8: the caption line carries it                         # v4 shows no win chance: the headline alone
            self._lower_third(im, lt, body=self.mode != "casual" and not self.v4)
        if standin_mark:
            d = ImageDraw.Draw(im)
            d.text((W - 24, H - 24), "STAND-IN FUTURES (cf_000070), NOT THIS MOMENT", font=self.font[22],
                   fill=(255, 80, 80), anchor="rb")
        return im

    def _lateral_px_per_m(self, feet) -> float:
        """Pixels per metre on the grass at `feet`, along the direction that runs across the picture."""
        m, e = self.cam.unproject([feet])[0], 1e-3
        jac = np.c_[self.cam.project([m + [e, 0], m + [0, e]]).T - self.cam.project([m]).T] / e
        return 1 / np.linalg.norm(np.linalg.solve(jac, [1.0, 0.0]))

    def _zoom(self, im: Image.Image, t: float, fade: float):
        """A punch-in on `zoom: {factor, at}` (metres) while frozen, for a moment far from the camera (Fourth
        Official): eases in with the rings and out with the fade. Returns the image and the pixel map for what is
        drawn after it (tags), so those stay sharp."""
        z = self.m.get("zoom")
        if z is None and self.v4:                         # v4: a gentle punch-in on the decision
            mid = self.actor_m if self.target_m is None else (self.actor_m + self.target_m) / 2
            if self.v5:                                   # v5: between the ball and the goal mouth
                mid = (self.ball + self.v5_geom["target"]) / 2
            z = {"factor": V4_PUNCH, "at": list(mid)}
        k = 1 + (float(z["factor"]) - 1) * window(t, *T_GRADE) * (1 - fade) if z else 1.0
        if k <= 1.0001:
            return im, lambda p: np.asarray(p, float)
        cx, cy = self.cam.project([z["at"]])[0]
        bw, bh = W / k, H / k
        x0, y0 = float(np.clip(cx - bw / 2, 0, W - bw)), float(np.clip(cy - bh / 2, 0, H - bh))
        if self.v5:                                       # anchored to the top: the score bug stays whole
            y0 = 0.0
        im = im.resize((W, H), Image.Resampling.LANCZOS, box=(x0, y0, x0 + bw, y0 + bh))
        return im, lambda p: (np.asarray(p, float) - [x0, y0]) * k

    def _tags(self, im: Image.Image, tags, to_screen, a: float):
        """Pills just above the players' heads; two that would overlap are pushed apart sideways."""
        font = self.font[26]
        d0 = ImageDraw.Draw(im)
        boxes = []
        for label, where_m, colour in tags:
            if not label:
                continue
            feet = self.cam.project([where_m])[0]
            head = feet - [0, APPARENT_HEIGHT_M * self._lateral_px_per_m(feet)]
            fx, hy = to_screen(feet)[0], to_screen(head)[1]
            w = d0.textlength(label.upper(), font=font) + 28
            boxes.append([fx - w / 2, hy - 54, w, label, colour])
        boxes.sort(key=lambda b: b[0])
        for left, right in zip(boxes, boxes[1:], strict=False):
            overlap = left[0] + left[2] + 12 - right[0]
            if overlap > 0 and abs(left[1] - right[1]) < 44:
                left[0] -= overlap / 2
                right[0] += overlap / 2
        layer = hi_layer(im.size)
        d = HiDraw(layer)
        for x, y, w, label, colour in boxes:
            d.rounded_rectangle((x, y, x + w, y + 40), radius=8, fill=(*PANEL, int(215 * a)),
                                outline=(*colour, int(255 * a)), width=3)
            d.text((x + w / 2, y + 20), label.upper(), font=font, fill=(*colour, int(255 * a)), anchor="mm")
        flatten(im, layer)

    def _panel_x(self, a: float) -> int:
        """Left edge of the lower-third and card: bottom left, or bottom right (`panels: right`) when the action is
        on the left of the frame; they slide in from their own edge."""
        if self.m.get("panels") == "right":
            return W - 96 - PANEL_W + int((1 - a) * 40)
        return 96 - int((1 - a) * 40)

    def _wrap(self, text: str, font, width: float) -> list[str]:
        words, lines = text.split(), [""]
        for w in words:
            trial = f"{lines[-1]} {w}".strip()
            if ImageDraw.Draw(Image.new("L", (1, 1))).textlength(trial, font=font) <= width:
                lines[-1] = trial
            else:
                lines.append(w)
        return lines

    def _lower_third(self, im: Image.Image, a: float, body: bool = True):
        """The reviewed line (headline and body) above the swing card, as the overlay's lower-third; casual mode
        shows the headline alone at the foot of the frame (its one sentence)."""
        x0, w = self._panel_x(a), PANEL_W
        body = self._wrap(self.line.get("body", ""), self.font_reg[22], w - 64) if body else []
        h = 70 + 32 * len(body)
        y0 = H - 96 - CARD_H - 16 - h if self.mode != "casual" else H - 96 - h
        layer = hi_layer(im.size)
        d = HiDraw(layer)
        al = int(255 * a)
        d.rounded_rectangle((x0, y0, x0 + w, y0 + h), radius=10, fill=(*PANEL, int(232 * a)))
        d.rectangle((x0, y0, x0 + 8, y0 + h), fill=(*WHITE, al))
        size = next(z for z in (30, 26, 22) if d.textlength(self.line["headline"], font=self.font[z]) <= w - 60
                    or z == 22)
        d.text((x0 + 32, y0 + 18 + (30 - size) // 2), self.line["headline"], font=self.font[size],
               fill=(255, 255, 255, al))
        for i, row in enumerate(body):
            d.text((x0 + 32, y0 + 64 + 32 * i), row, font=self.font_reg[22], fill=(214, 222, 232, al))
        flatten(im, layer)

    def _goal10_rows(self) -> list[tuple[str, dict]]:
        """(label, {p, ci95}) for actual and alternative from track A's goal10 file; [] without it (v4 prints no
        goal-in-10s number it was not given)."""
        g = self.goal10
        if not g:
            return []
        names = {"actual": "What he did", "alternative": "The alternative", **(self.m.get("options") or {})}
        if "options" in g:                               # track A's goal10_decision: options[0] is what he did
            act = g["options"][0]
            rows = [(names["actual"], {"p": act["p_goal_10s"], "ci95": act["ci95"]})]
            alt = self.alternative_option()
            if alt is not None:
                rows.append((names["alternative"], {"p": alt["p_goal_10s"], "ci95": alt["ci95"]}))
            return rows
        return [(g[k].get("label") or names[k], g[k]) for k in ("actual", "alternative")]

    def alternative_option(self) -> dict | None:
        """The option the beat draws as the alternative: the spec's `alternative` (a target label or 'carry'),
        else track A's best_alternative, and only when it is better than what he did beyond the noise."""
        g = self.goal10 or {}
        want = self.m.get("alternative") or g.get("best_alternative")
        if not want or self.m.get("finishing"):
            return None
        for o in g.get("options", [])[1:]:
            op = o["option"]
            if (isinstance(want, dict) and op == want) or op.get("target") == want or op.get("kind") == want:
                verdict = (o.get("diff_vs_actual") or {}).get("verdict")
                return o if verdict == "better" and o.get("p_goal_10s") is not None else None
        return None

    def _lane_labels(self, im: Image.Image, a: float):
        """v4: each lane's end labelled with its branch and its goal chance in the next 10 s."""
        if a <= 0:
            return
        rows = dict((k, r) for k, r in zip(("actual", "alternative"), self._goal10_rows(), strict=False))
        names = {"actual": "What he did", "alternative": "The alternative", **(self.m.get("options") or {})}
        layer = hi_layer(im.size)
        d = HiDraw(layer)
        for ln in self.lanes:
            end = ln["px"][-1]
            colour = tuple(int(v * 255) for v in ln["colour"])
            label, p = (rows[ln["key"]][0], rows[ln["key"]][1]["p"]) if ln["key"] in rows else (names[ln["key"]], None)
            text = f"{label.upper()}  {fmt_pct(p)}" if p is not None else label.upper()
            w = d.textlength(text, font=self.font[26]) + 28
            x0 = float(np.clip(end[0] - w / 2, 24, W - 24 - w))              # inside the frame
            y0 = end[1] - 74 if ln["key"] == "actual" else end[1] + 40     # the receiver's own tag sits above him
            d.rounded_rectangle((x0, y0, x0 + w, y0 + 42), radius=10, fill=(*PANEL, int(225 * a)),
                                outline=(*colour, int(255 * a)), width=3)
            d.text((x0 + w / 2, y0 + 21), text, font=self.font[26], fill=(*colour, int(255 * a)), anchor="mm")
        flatten(im, layer)

    def _card_v4(self, im: Image.Image, a: float, swing: float):
        """v4 decision card: the attacking team's goal chance in the next 10 s, what he did against the
        alternative, each with its 95% interval in small print; nothing about winning."""
        rows = self._goal10_rows()
        if not rows:
            return
        g = self.goal10
        x0, w = self._panel_x(a), PANEL_W
        h = 58 + 78 * len(rows) + (44 if self.m.get("card_note") else 0) + 34
        y0 = H - 96 - h
        layer = hi_layer(im.size)
        d = HiDraw(layer)
        al = int(255 * a)
        d.rounded_rectangle((x0, y0, x0 + w, y0 + h), radius=10, fill=(*PANEL, int(232 * a)))
        d.rectangle((x0, y0, x0 + 8, y0 + h), fill=(*ORANGE, al))
        d.text((x0 + 32, y0 + 20), "GOAL IN THE NEXT 10 S", font=self.font[22], fill=(169, 180, 194, al))
        lo = rows[0][1]["p"]
        hi = rows[1][1]["p"] if len(rows) > 1 else lo
        # no ratio printed: it divides two noisy estimates (track B, 23 Oct)
        note = self.m.get("card_note")                    # a finishing beat: "He scored."
        if note:
            d.text((x0 + 32, y0 + 58 + 78 * len(rows)), note, font=self.font[30], fill=(*ORANGE, al))
        top = max(lo, hi) * 1.25
        bx0, bx1 = x0 + 32, x0 + w - 110
        for row, ((label, r), col, grow) in enumerate(zip(rows, ((196, 204, 214), ORANGE), (1.0, swing),
                                                          strict=False)):
            y = y0 + 58 + 78 * row
            d.text((bx0, y), label, font=self.font_reg[22], fill=(230, 236, 242, al))
            by = y + 30
            d.rounded_rectangle((bx0, by, bx1, by + 12), radius=6, fill=(255, 255, 255, int(28 * a)))
            if grow > 0:
                d.rounded_rectangle((bx0, by, bx0 + max(12, (bx1 - bx0) * r["p"] / top * grow), by + 12), radius=6,
                                    fill=(*col, al))
            d.text((x0 + w - 28, by + 6), fmt_pct(r["p"]), font=self.font[34],
                   fill=(*(col if row else (255, 255, 255)), int(al * grow)), anchor="rm")
            if r.get("ci95"):
                d.text((bx0, by + 18), f"95%: {fmt_pct(r['ci95'][0])}–{fmt_pct(r['ci95'][1])}",
                       font=self.font_reg[20], fill=(169, 180, 194, al))
        d.text((x0 + w - 28, y0 + h - 14), f"n = {g['n']:,}, {g.get('horizon_s', 10):g} s, seed {g['seed']}",
               font=self.font_reg[20], fill=(169, 180, 194, al), anchor="rb")
        flatten(im, layer)

    def _ruling_card(self, im: Image.Image, a: float):
        """Fourth Official: the assessment's numbers (closing speed, where the contact was, the card shown), and
        that it is an assessment from tracking, not a ruling."""
        r = self.ruling
        x0, w, h = self._panel_x(a), PANEL_W, CARD_H
        y0 = H - 96 - h
        layer = hi_layer(im.size)
        d = HiDraw(layer)
        al = int(255 * a)
        d.rounded_rectangle((x0, y0, x0 + w, y0 + h), radius=10, fill=(*PANEL, int(232 * a)))
        d.rectangle((x0, y0, x0 + 8, y0 + h), fill=(*YELLOW, al))
        d.text((x0 + 32, y0 + 20), "FOURTH OFFICIAL", font=self.font[22], fill=(169, 180, 194, al))
        rows = [("Closing speed", f"{round(r['closing_speed_kmh'])} km/h"),
                ("Contact", "inside the box" if r["in_box"] else "outside the box"),
                ("Card shown", r["card"])]
        for i, (label, value) in enumerate(rows):
            y = y0 + 60 + 40 * i
            d.text((x0 + 32, y), label, font=self.font_reg[22], fill=(230, 236, 242, al))
            d.text((x0 + w - 28, y + 13), value, font=self.font[30], fill=(*YELLOW, al), anchor="rm")
        d.text((x0 + w - 28, y0 + h - 16), "an assessment from tracking, not a ruling", font=self.font_reg[20],
               fill=(169, 180, 194, al), anchor="rb")
        flatten(im, layer)

    def _card(self, im: Image.Image, a: float, swing: float):
        """The win-chance card: one labelled bar per option (what he did, the alternative), the difference, and the
        counterfactual's n, horizon and seed (shown with every number, as the overlay's SwingBar). Bars start at 0;
        the scale tops out a quarter above the larger value so both read."""
        cf = self.fut.cf
        lo, hi = cf["baseline"]["win_prob_home"], cf["alternative_outcome"]["win_prob_home"]
        names = {"actual": "What he did", "alternative": "The alternative", **(self.m.get("options") or {})}
        x0, w, h = self._panel_x(a), PANEL_W, CARD_H
        y0 = H - 96 - h
        layer = hi_layer(im.size)
        d = HiDraw(layer)
        al = int(255 * a)
        d.rounded_rectangle((x0, y0, x0 + w, y0 + h), radius=10, fill=(*PANEL, int(232 * a)))
        d.rectangle((x0, y0, x0 + 8, y0 + h), fill=(*ORANGE, al))
        d.text((x0 + 32, y0 + 20), "WIN CHANCE", font=self.font[22], fill=(169, 180, 194, al))
        delta = round((hi - lo) * 100)
        diff = "≈ 0 pts" if delta == 0 else f"{'+' if delta > 0 else '−'}{abs(delta)} pt{'s' if abs(delta) > 1 else ''}"
        d.text((x0 + w - 28, y0 + 16), diff, font=self.font[30],
               fill=(*ORANGE, int(255 * a * swing)), anchor="ra")
        top = max(lo, hi) * 1.25
        bx0, bx1 = x0 + 32, x0 + w - 110
        for row, (key, value, col, grow) in enumerate((("actual", lo, (196, 204, 214), 1.0),
                                                       ("alternative", hi, ORANGE, swing))):
            y = y0 + 58 + 56 * row
            d.text((bx0, y), names[key], font=self.font_reg[22], fill=(230, 236, 242, al))
            by = y + 30
            d.rounded_rectangle((bx0, by, bx1, by + 12), radius=6, fill=(255, 255, 255, int(28 * a)))
            if grow > 0:
                d.rounded_rectangle((bx0, by, bx0 + max(12, (bx1 - bx0) * value / top * grow), by + 12), radius=6,
                                    fill=(*col, al))
            d.text((x0 + w - 28, by + 6), f"{round(value * 100)}%", font=self.font[34],    # only the real value,
                   fill=(*(col if key == "alternative" else (255, 255, 255)), int(al * grow)), anchor="rm")  # faded in
        d.text((x0 + w - 28, y0 + h - 16), f"n = {cf['n']}, {cf['horizon_s']:g} s, seed {cf['seed']}",
               font=self.font_reg[20], fill=(169, 180, 194, al), anchor="rb")
        flatten(im, layer)


    def _phone(self, im: Image.Image, t: float, fade: float) -> Image.Image:
        """Player-Cam (the fan app's card) for the moment's actor, as a phone screen: the frozen frame cropped
        round him with the drawn futures, then his card: name, club, and the moment's verified numbers (the
        distance fact, each option's goal chance and win chance from the counterfactual)."""
        pw, ph, crop_w = PHONE
        crop_h = int(crop_w * 1.28)
        feet = self.cam.project([self.actor_m])[0]
        cx = int(np.clip(feet[0] + crop_w * 0.18, crop_w / 2, W - crop_w / 2))
        cy = int(np.clip(feet[1] - crop_h * 0.38, crop_h / 2, H - crop_h / 2))
        top = im.crop((cx - crop_w // 2, cy - crop_h // 2, cx + crop_w // 2, cy + crop_h // 2))
        top = top.resize((pw, int(pw * crop_h / crop_w)), Image.Resampling.LANCZOS)
        phone = Image.new("RGB", (pw, ph), PANEL)
        phone.paste(top, (0, 0))
        a = window(t, *T_CARD) * (1 - fade)
        if a <= 0:
            return phone
        layer = Image.new("RGBA", phone.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        al = int(255 * a)
        y = top.height + 36
        d.rounded_rectangle((36, y, 36 + d.textlength("PLAYER-CAM", font=self.font[22]) + 28, y + 40), radius=8,
                            fill=(*ORANGE, al))
        d.text((50, y + 20), "PLAYER-CAM", font=self.font[22], fill=(255, 255, 255, al), anchor="lm")
        who = self.m["player_cam"]
        d.text((36, y + 70), who["name"], font=self.font[50], fill=(255, 255, 255, al))
        d.text((36, y + 140), who["club"], font=self.font[30], fill=(169, 180, 194, al))
        for i, (label, value, colour) in enumerate(self._phone_rows()):
            ry = y + 220 + 70 * i
            d.line((36, ry - 14, pw - 36, ry - 14), fill=(255, 255, 255, int(40 * a)), width=2)
            d.text((36, ry + 14), label, font=self.font[30], fill=(214, 222, 232, al), anchor="lm")
            d.text((pw - 36, ry + 14), value, font=self.font[34], fill=(*colour, al), anchor="rm")
        cf = self.fut.cf
        d.text((pw - 36, ph - 40), f"n = {cf['n']}, {cf['horizon_s']:g} s, seed {cf['seed']}", font=self.font_reg[22],
               fill=(169, 180, 194, al), anchor="rb")
        phone.paste(layer, (0, 0), layer)
        return phone

    def _phone_rows(self) -> list[tuple[str, str, tuple]]:
        cf, who = self.fut.cf, self.m["player_cam"]
        side = who.get("side", "home")
        names = {"actual": "What he did", "alternative": "The alternative", **(self.m.get("options") or {})}
        rows = []
        for fact in facts_for(self.m, who.get("facts", [])):
            rows.append((fact["caption"], f"{round(fact['value'])} m" if fact["unit"] == "metres"
                         else f"{fact['value']} {fact['unit']}", WHITE))
        rows += [(f"{names['actual']}: goal chance", f"{round(cf['baseline'][f'p_goal_{side}'] * 100)}%", WHITE),
                 (f"{names['alternative']}: goal chance",
                  f"{round(cf['alternative_outcome'][f'p_goal_{side}'] * 100)}%", ORANGE)]
        lo, hi = cf["baseline"][f"win_prob_{side}"], cf["alternative_outcome"][f"win_prob_{side}"]
        rows.append(("Win chance", f"{round(lo * 100)}% → {round(hi * 100)}%", ORANGE))
        return rows


def fmt_pct(v: float) -> str:
    """A small probability for the screen: one decimal under 10%."""
    return f"{v * 100:.1f}%" if v < 0.1 else f"{int(v * 100 + 0.5)}%"      # half up, as printed in captions


def load_json(rel: str | None, key: str | None = None):
    """A repo-relative JSON file (optionally one key of it), or None when the spec does not name one."""
    if not rel:
        return None
    doc = json.loads((ROOT / rel).read_text())
    return doc[key] if key else doc


def cache_dir(m: dict) -> Path | None:
    return (ROOT / m["counterfactual"]).parents[1] if m.get("counterfactual") else None


def evidence(m: dict, collection: str) -> list[dict]:
    path = cache_dir(m) / "evidence.jsonl" if cache_dir(m) else None
    if not path or not path.exists():
        return []
    docs = (json.loads(line) for line in path.read_text().splitlines() if line.strip())
    return [d for d in docs if d.get("_collection") == collection]


def facts_for(m: dict, wanted: list[dict]) -> list[dict]:
    """The named facts from the moment's evidence (T-109), each with the caption the spec gives it."""
    have = {f["fact_id"]: f for f in evidence(m, "facts")}
    return [{**have[w["id"]], "caption": w["caption"]} for w in wanted if w["id"] in have]


def pitch_control_for(m: dict, cf: dict | None):
    """(grid, mirrored) of the counterfactual's pitch-control snapshot, or None."""
    if not cf or not cache_dir(m):
        return None
    doc = next((d for d in evidence(m, "pitch_control") if d["snapshot_id"] == cf["pitch_control_snapshot_id"]), None)
    path = cache_dir(m) / doc["grid_path"] if doc else None
    if not path or not path.exists():
        return None
    return np.load(path)["grid"], bool(doc.get("mirrored"))


# ---------------------------------------------------------------------------------------------- outputs
def stem(m: dict, standin: bool) -> str:
    return m["name"] + ("_standin" if standin else "")


def export_png(p: Painter, path: Path, standin: bool) -> Path:
    p.render(FADE_OUT[0] - 0.01, standin_mark=standin).save(path)
    return path


def decode_range(m: dict, start: float, dur: float) -> np.ndarray:
    """The clip's frames over [start, start + dur] at FPS, decoded (never written next to the media)."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-i", str(clip_path(m)), "-t", f"{dur:.3f}",
                          "-vf", f"fps={FPS}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, H, W, 3)


def goal_tag(m: dict, enc, frames: np.ndarray, start_s: float, p: Painter) -> None:
    """v6: no flash; a small broadcast tag 'GOAL · 0.48 xG' slides in at the bottom left when the ball crosses the
    line (owner: the big flash was cartoonish)."""
    goal_t = float(m["goal_clip_s"])
    colour = tuple((m.get("kits") or {}).get(m.get("team", "home"), ORANGE))
    act = (p.xg or {}).get("actual", {})
    xg = act.get("strike_xg") if act.get("strike_xg") is not None else act.get("xg")
    f = ImageFont.truetype(FONT, 34)
    text = f"GOAL · {xg:.2f} xG" if xg is not None else "GOAL"
    for i, fr in enumerate(frames):
        dt = start_s + i / FPS - goal_t
        if dt < 0:
            enc.stdin.write(fr.tobytes())
            continue
        a = min(1.0, dt / 0.25)
        im = Image.fromarray(fr.copy())
        d = ImageDraw.Draw(im, "RGBA")
        w = d.textlength(text, font=f) + 44
        x0, y0 = 96 - int((1 - a) * 40), H - (150 if p.v8 else 96) - 64
        if p.v8:
            d = p._glass(im, (x0, y0, x0 + w, y0 + 64), a)
        else:
            d.rounded_rectangle((x0, y0, x0 + w, y0 + 64), radius=10, fill=(*PANEL, int(235 * a)))
            d.rectangle((x0, y0, x0 + 8, y0 + 64), fill=(*colour, int(255 * a)))
        d.text((x0 + 28, y0 + 32), text, font=f, fill=(255, 255, 255, int(255 * a)), anchor="lm")
        enc.stdin.write(np.asarray(im.convert("RGB")).tobytes())


def goal_flash(m: dict, enc, frames: np.ndarray, start_s: float, p: Painter) -> None:
    """The real replay with the goal marked: a flash in the team colour on the frame the ball crosses the line
    (`goal_clip_s`, from track A), then 'GOAL' and the shot's xG with 'scored' held to the end."""
    goal_t = float(m["goal_clip_s"])
    colour = np.array((m.get("kits") or {}).get(m.get("team", "home"), ORANGE), float)
    act = (p.xg or {}).get("actual", {})
    xg = act.get("strike_xg") if act.get("strike_xg") is not None else act.get("xg")   # the strike's value
    small = ImageFont.truetype(FONT, 46)
    for i, fr in enumerate(frames):
        dt = start_s + i / FPS - goal_t
        if dt < 0:
            enc.stdin.write(fr.tobytes())
            continue
        flash = max(0.0, 1 - dt / 0.35)
        f = fr.astype(float) * (1 - 0.55 * flash) + colour * 0.55 * flash
        im = Image.fromarray(np.clip(f, 0, 255).astype(np.uint8))
        d = ImageDraw.Draw(im)
        scale = 1 + 0.2 * max(0.0, 1 - dt / 0.3)      # the word lands slightly large and settles
        d.text((W / 2, H / 2 - 80), "GOAL", font=ImageFont.truetype(FONT, int(170 * scale)),
               fill=tuple(int(c) for c in colour), anchor="mm", stroke_width=10, stroke_fill=(0, 0, 0))
        if xg is not None and dt > 0.4:
            d.text((W / 2, H / 2 + 50), f"{xg:.2f} xG · scored", font=small, fill=(255, 255, 255), anchor="mm",
                   stroke_width=6, stroke_fill=(0, 0, 0))
        enc.stdin.write(np.asarray(im).tobytes())


def export_clip(m: dict, p: Painter, path: Path, standin: bool, pre_s: float = 4.0, post_s: float = 3.0,
                freeze_s: float = FREEZE_S) -> Path:
    """Pre-roll of the real clip up to the freeze instant, the freeze with the overlay building and fading, then
    the real clip resuming from the same instant. A freeze_s longer than FREEZE_S holds the built overlay before
    it fades. 30 fps H.264, no audio."""
    t0 = m["t_s"]
    size = p.render(0.0).size
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s",
                            f"{size[0]}x{size[1]}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "16",
                            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)], stdin=subprocess.PIPE)

    def real(start: float, dur: float):
        if dur <= 0:
            return
        dec = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-i", str(clip_path(m)), "-t",
                              f"{dur:.3f}", "-vf", f"fps={FPS}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True, check=True).stdout
        enc.stdin.write(dec)

    if m.get("style") in ("v4", "v5", "v6", "v8"):     # a speed ramp into slow motion before the freeze
        ramp = min(RAMP_SLOW_S, pre_s)
        real(t0 - pre_s, pre_s - ramp)
        frames = decode_range(m, t0 - ramp, ramp)
        n_out = int(round(ramp / RAMP_RATE * FPS))      # the last `ramp` real seconds at RAMP_RATE speed
        for k in range(n_out):
            u = k / max(1, n_out - 1)
            src = (1 - (1 - u) ** 1.6) * (len(frames) - 1)   # easing from normal speed down into slow motion
            i0 = int(src)
            f = src - i0
            a, b = frames[i0].astype(float), frames[min(i0 + 1, len(frames) - 1)].astype(float)
            enc.stdin.write(np.clip(a * (1 - f) + b * f, 0, 255).astype(np.uint8).tobytes())
    else:
        real(t0 - pre_s, pre_s)
    hold = max(0.0, freeze_s - FREEZE_S)
    for i in range(int(round(freeze_s * FPS))):
        t = i / FPS
        t = t if t < FADE_OUT[0] else (FADE_OUT[0] - 0.01 if t < FADE_OUT[0] + hold else t - hold)
        enc.stdin.write(p.render(t, standin_mark=standin).tobytes())
    if m.get("style") in ("v4", "v5", "v6", "v8") and post_s > 0:   # a rewind sting, then what really happened
        back = decode_range(m, t0 - REWIND_S, REWIND_S)[::-1][:: REWIND_STEP]
        for fr in back:
            g = fr.astype(float) * 0.82 + np.array([10, 18, 40]) * 0.18   # cool tint while it runs backwards
            enc.stdin.write(np.clip(g, 0, 255).astype(np.uint8).tobytes())
        if m.get("goal_clip_s") is not None:              # v5: the goal flash on the real replay
            (goal_tag if m.get("style") in ("v6", "v8") else goal_flash)(
                m, enc, decode_range(m, t0 - REWIND_S, post_s + REWIND_S), t0 - REWIND_S, p)
        else:
            real(t0 - REWIND_S, post_s + REWIND_S)
    else:
        real(t0, post_s)
    enc.stdin.close()
    if enc.wait():
        raise RuntimeError("ffmpeg encode failed")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("moment")
    ap.add_argument("--png", action="store_true")
    ap.add_argument("--clip", action="store_true")
    ap.add_argument("--standin", action="store_true", help="re-anchored cf_000070 futures until T-109 lands")
    ap.add_argument("--refit", action="store_true", help="refit the camera even if cached")
    ap.add_argument("--style", choices=["v3", "v4", "v5", "v6", "v8"], help="v4: median lanes, goal in the next 10 s, slow-motion "
                    "ramp and punch-in (video v4); default the moment's own")
    ap.add_argument("--mode", choices=["broadcast", "analyst", "casual", "player_cam"], default="broadcast",
                    help="viewer mode: analyst adds the pitch-control heatmap, casual keeps one sentence, "
                         "player_cam is the actor's phone card; their clips are the freeze alone")
    args = ap.parse_args(argv)
    m = load_moment(args.moment)
    if args.style:
        m["style"] = args.style
    if not clip_path(m).exists():
        print(f"composite: {clip_path(m).relative_to(ROOT)} is not here (clips are never committed)", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    if m.get("adapter"):                                # track A's insight files -> the beat's data (demo.v3_data)
        m["data"] = build(m)
    if m.get("kind") in SCENES:                         # an overlay on the playing clip (demo.live)
        scene = SCENES[m["kind"]](m)
        if scene.camera_note:
            print(f"camera: {scene.camera_note}")
        print(f"wrote {scene.export(OUT / (m['name'] + '.mp4')).relative_to(ROOT)}")
        return 0
    frame = frame_at(m, m["t_s"])
    Image.fromarray(frame).save(OUT / f"{m['name']}_frame.png")
    cam, drift = camera_for(m, frame, refit=args.refit)
    print(f"camera k1 {cam.k1:+.4f}; drift over {', '.join(drift.lines)}: median {drift.median} px, "
          f"p95 {drift.p95} px, {drift.samples} samples")
    for name, v in drift.per_line.items():
        print(f"  {name:<20} median {v['median']:5} p95 {v['p95']:5} coverage {v['coverage']}")
    pw = pitchwatch_camera(m, frame)
    if pw:
        print(f"track A calibration ({pw[2]}): drift median {pw[1].median} px, p95 {pw[1].p95} px over "
              f"{', '.join(pw[1].lines)}" + ("; using it" if pw[1].p95 <= drift.p95 else "; keeping the line fit"))
        if pw[1].p95 <= drift.p95:
            cam, drift = pw[0], pw[1]
    fut = None if m.get("kind") == "fourth_official" or ((m.get("goal10") or m.get("xg")) and not m.get("counterfactual")) \
        else load_futures(m, cam, args.standin)
    p = Painter(m, frame, cam, fut, mode=args.mode)
    standin = bool(fut and fut.standin)
    s = stem(m, standin) + ("" if args.mode == "broadcast" else f"_{args.mode}") + \
        (f"_{m['style']}" if m.get("style") in ("v4", "v5", "v6", "v8") else "")
    if args.png or not args.clip:
        print(f"wrote {export_png(p, OUT / f'{s}.png', standin).relative_to(ROOT)}")
    if args.clip:
        pre, post, freeze = ((m.get("pre_s", 4.0), m.get("post_s", 3.0), FREEZE_S) if args.mode == "broadcast"
                             else (0.0, 0.0, MODES_FREEZE_S))
        print(f"wrote {export_clip(m, p, OUT / f'{s}.mp4', standin, pre, post, freeze).relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
