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

from demo.footage import Camera, Drift, drift_px, fit_from_lines, from_pitchwatch  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FOOTAGE = ROOT / "data" / "footage"
MOMENTS = Path(__file__).with_name("footage_moments.yaml")
OUT = ROOT / "packages" / "demo" / "out" / "footage"
STANDIN_CF = ROOT / "data" / "matches" / "4242" / "cache" / "counterfactuals" / "cf_000070.json"
W, H, FPS = 1920, 1080, 30
FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_REG = "/System/Library/Fonts/Supplemental/Arial.ttf"
ORANGE, WHITE, YELLOW = (255, 122, 26), (236, 242, 248), (255, 214, 10)
PANEL = (12, 16, 22)
SUBDIV = 10
APPARENT_HEIGHT_M = 1.42   # a player's height in the picture over the grass scale across it (4 players, lfc 875 s)
RING_R = 1.1              # metres
GHOST_S = 4               # seconds of each future drawn: the decision and what follows it, not the whole 8 s
GHOST_KEEP = 36           # paths drawn per branch: the ones nearest the branch's median path
GHOST_REPS = 6            # of those, drawn bolder
GHOST_FADE_T = (1.2, 3.5)   # s: full strength through the first leg, gone by 3.5 s ...
GHOST_FADE_D = (5.0, 12.0)  # m: ... unless still within this of where the branch is going
GHOST_MARGIN_M = 2.0       # futures are clamped to the pitch plus this, as the overlay's ghost layer


# ---------------------------------------------------------------------------------------------- inputs
def load_moment(name: str) -> dict:
    """The moment's spec; with a `moment_file` (T-107: players and ball in pitch metres, hand-marked or tracked)
    the actor, the target and the ball take their positions from it (`at`), else from their feet pixels."""
    moments = yaml.safe_load(MOMENTS.read_text())["moments"]
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
    return cam, drift_px(cam, frame, m["camera"]["lines"], top=top_rows(m["camera"]["top"])), path.name


def camera_for(m: dict, frame: np.ndarray, refit: bool = False) -> tuple[Camera, Drift]:
    """The moment's camera: hand landmarks refined against the frame's own markings (cached per moment)."""
    path = OUT / f"{m['name']}_camera.json"
    spec = m["camera"]
    key = {"t_s": m["t_s"], "camera": spec}
    if path.exists() and not refit:
        doc = json.loads(path.read_text())
        if doc.get("key") == key:
            return Camera.from_json(doc), Drift(**doc["drift"])
    fit = fit_from_lines(frame, spec["landmarks"]["pitch"], spec["landmarks"]["pixel"], spec["lines"],
                         top=top_rows(spec["top"]))
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
FADE_OUT = (6.3, 6.9)
T_GRADE = (0.0, 0.35)
T_RINGS = (0.2, 0.8)
T_BASE = (0.6, 2.2)
T_ALT = (1.8, 3.6)
T_TRAIL = (1.8, 2.6)
T_CARD = (2.6, 3.0)
T_SWING = (3.0, 4.2)
T_LOWER = (2.3, 2.7)
CARD_H = 222
PANEL_W = 540              # lower-third and swing card, bottom left; clear of the players in the featured frames


# ---------------------------------------------------------------------------------------------- drawing
class Painter:
    """Draws one overlay state over a frozen frame: matplotlib's Agg (antialiased, alpha-blended strokes) for the
    pitch graphics, PIL for the grade, the tags and the card."""

    def __init__(self, m: dict, frame: np.ndarray, cam: Camera, fut: Futures | None,
                 referee_lines: list | None = None):
        self.m, self.frame, self.cam, self.fut = m, frame, cam, fut
        self.fig = Figure(figsize=(W / 100, H / 100), dpi=100)
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
        self.trail_px = None
        if self.target_m is not None:                            # stop at the receiver's ring
            curve = pass_curve(self.ball, self.target_m)
            far = np.linalg.norm(curve - self.target_m, axis=1) > RING_R + 0.35
            self.trail_px = cam.project(curve[far])
        self.spot = self._spotlight()
        self.font = {s: ImageFont.truetype(FONT, s) for s in (22, 26, 30, 34, 64)}
        self.line = None
        if m.get("line") and (ROOT / m["line"]).exists():          # the reviewed lower-third (T-109)
            doc = json.loads((ROOT / m["line"]).read_text())
            self.line = doc["json"] if doc.get("verified") else None
        self.font_reg = {s: ImageFont.truetype(FONT_REG, s) for s in (20, 22)}

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
        for g in getattr(self, "ghosts", []):
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
        if trail > 0 and self.trail_px is not None:
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
        return np.asarray(self.canvas.buffer_rgba(), float) / 255

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
        g = self._graphics(t, fade)
        f = f * (1 - g[..., 3:4]) + g[..., :3] * g[..., 3:4]
        im = Image.fromarray(np.clip(f * 255, 0, 255).astype(np.uint8))
        a = window(t, *T_RINGS) * (1 - fade)
        if a > 0:
            self._tag(im, self.m["actor"].get("label"), self.actor_m, WHITE, a)
            if self.target_m is not None:
                self._tag(im, self.m["target"].get("label"), self.target_m, ORANGE, a)
        c = window(t, *T_CARD) * (1 - fade)
        if c > 0 and self.fut:
            self._card(im, c, window(t, *T_SWING))
        lt = window(t, *T_LOWER) * (1 - fade)
        if lt > 0 and self.line:
            self._lower_third(im, lt)
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

    def _tag(self, im: Image.Image, label: str | None, where_m, colour, a: float):
        """A pill just above the player's head."""
        if not label:
            return
        feet = self.cam.project([where_m])[0]
        y = feet[1] - APPARENT_HEIGHT_M * self._lateral_px_per_m(feet) - 14
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        font = self.font[26]
        w = d.textlength(label.upper(), font=font)
        box = (feet[0] - w / 2 - 14, y - 40, feet[0] + w / 2 + 14, y)
        d.rounded_rectangle(box, radius=8, fill=(*PANEL, int(215 * a)), outline=(*colour, int(255 * a)), width=3)
        d.text((feet[0], y - 20), label.upper(), font=font, fill=(*colour, int(255 * a)), anchor="mm")
        im.paste(layer, (0, 0), layer)

    def _wrap(self, text: str, font, width: float) -> list[str]:
        words, lines = text.split(), [""]
        for w in words:
            trial = f"{lines[-1]} {w}".strip()
            if ImageDraw.Draw(Image.new("L", (1, 1))).textlength(trial, font=font) <= width:
                lines[-1] = trial
            else:
                lines.append(w)
        return lines

    def _lower_third(self, im: Image.Image, a: float):
        """The reviewed line (headline and body) above the swing card, as the overlay's lower-third."""
        x0, w = 96 - int((1 - a) * 40), PANEL_W
        body = self._wrap(self.line.get("body", ""), self.font_reg[22], w - 64)
        h = 70 + 32 * len(body)
        y0 = H - 96 - CARD_H - 16 - h
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        al = int(255 * a)
        d.rounded_rectangle((x0, y0, x0 + w, y0 + h), radius=10, fill=(*PANEL, int(232 * a)))
        d.rectangle((x0, y0, x0 + 8, y0 + h), fill=(*WHITE, al))
        d.text((x0 + 32, y0 + 18), self.line["headline"], font=self.font[30], fill=(255, 255, 255, al))
        for i, row in enumerate(body):
            d.text((x0 + 32, y0 + 64 + 32 * i), row, font=self.font_reg[22], fill=(214, 222, 232, al))
        im.paste(layer, (0, 0), layer)

    def _card(self, im: Image.Image, a: float, swing: float):
        """The win-chance card: one labelled bar per option (what he did, the alternative), the difference, and the
        counterfactual's n, horizon and seed (shown with every number, as the overlay's SwingBar). Bars start at 0;
        the scale tops out a quarter above the larger value so both read."""
        cf = self.fut.cf
        lo, hi = cf["baseline"]["win_prob_home"], cf["alternative_outcome"]["win_prob_home"]
        names = {"actual": "What he did", "alternative": "The alternative", **(self.m.get("options") or {})}
        x0, w, h = 96 - int((1 - a) * 40), PANEL_W, CARD_H
        y0 = H - 96 - h
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        al = int(255 * a)
        d.rounded_rectangle((x0, y0, x0 + w, y0 + h), radius=10, fill=(*PANEL, int(232 * a)))
        d.rectangle((x0, y0, x0 + 8, y0 + h), fill=(*ORANGE, al))
        d.text((x0 + 32, y0 + 20), "WIN CHANCE", font=self.font[22], fill=(169, 180, 194, al))
        delta = round((hi - lo) * 100)
        d.text((x0 + w - 28, y0 + 16), f"{'+' if delta >= 0 else '−'}{abs(delta)} pts", font=self.font[30],
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
        im.paste(layer, (0, 0), layer)


# ---------------------------------------------------------------------------------------------- outputs
def stem(m: dict, standin: bool) -> str:
    return m["name"] + ("_standin" if standin else "")


def export_png(p: Painter, path: Path, standin: bool) -> Path:
    p.render(FADE_OUT[0] - 0.01, standin_mark=standin).save(path)
    return path


def export_clip(m: dict, p: Painter, path: Path, standin: bool, pre_s: float = 4.0, post_s: float = 3.0) -> Path:
    """Pre-roll of the real clip up to the freeze instant, the freeze with the overlay building and fading, then
    the real clip resuming from the same instant. 30 fps H.264, no audio."""
    t0 = m["t_s"]
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "16",
                            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)], stdin=subprocess.PIPE)

    def real(start: float, dur: float):
        dec = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-i", str(clip_path(m)), "-t",
                              f"{dur:.3f}", "-vf", f"fps={FPS}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True, check=True).stdout
        enc.stdin.write(dec)

    real(t0 - pre_s, pre_s)
    for i in range(int(round(FREEZE_S * FPS))):
        enc.stdin.write(p.render(i / FPS, standin_mark=standin).tobytes())
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
    args = ap.parse_args(argv)
    m = load_moment(args.moment)
    if not clip_path(m).exists():
        print(f"composite: {clip_path(m).relative_to(ROOT)} is not here (clips are never committed)", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
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
    fut = load_futures(m, cam, args.standin)
    p = Painter(m, frame, cam, fut)
    s = stem(m, fut.standin)
    if args.png or not args.clip:
        print(f"wrote {export_png(p, OUT / f'{s}.png', fut.standin).relative_to(ROOT)}")
    if args.clip:
        print(f"wrote {export_clip(m, p, OUT / f'{s}.mp4', fut.standin).relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
