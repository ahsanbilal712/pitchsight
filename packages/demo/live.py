"""Overlays on a playing real clip (video v3: Oracle, speed gun, pass X-ray, offside line).

    python -m demo.composite <moment>        # a moment with `kind: oracle | speed_gun | pass_xray | offside`

Unlike the freeze beats (demo.composite.Painter), these draw on every frame of the clip as it plays: each frame
goes through that frame's camera from the paint-refined calibration of its shot (calib/<shot>_refined.json, see
demo.refine_calib), so the graphics stay on the grass while the broadcast camera pans. A beat's data is one JSON
under data/footage/<slug>/cache/ in the format of the shared note track-c-v3-overlay-formats.md: positions in the
moment-file frame (y from the near touchline), times as clip_ms. Values between samples: positions and bars are
interpolated, printed numbers are always a real sample's (the latest one), never an interpolation.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import cv2  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from demo.footage import PITCH_W, Camera, from_pitchwatch  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FOOTAGE = ROOT / "data" / "footage"
W, H, FPS = 1920, 1080, 30
_INTER = Path(__file__).resolve().parent / "out" / "fonts"   # Inter (OFL), fetched locally: docs/video/FONTS.md
_DEJAVU = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
FONT_DIR = _INTER if (_INTER / "Inter-Bold.ttf").exists() else _DEJAVU
FONT = str(FONT_DIR / ("Inter-Bold.ttf" if FONT_DIR == _INTER else "DejaVuSans-Bold.ttf"))
FONT_REG = str(FONT_DIR / ("Inter-Regular.ttf" if FONT_DIR == _INTER else "DejaVuSans.ttf"))
FONT_NAME = "Inter" if FONT_DIR == _INTER else "DejaVu Sans"
ORANGE, WHITE, YELLOW, PANEL, MUTED = (255, 122, 26), (236, 242, 248), (255, 214, 10), (12, 16, 22), (169, 180, 194)
PANEL_W = 540
GHOST_DIM = 0.40         # ghost future: the players the story is not about
GHOST_NEAR = 7           # ghost future: the players nearest the ball, drawn bright
GHOST_DARKEN = 0.40      # ghost future: how far the real frame is darkened under the other timeline
GHOST_TRAIL_MS = 800      # ghost future: each player's short motion trail
RUNNER_RING_M = 0.65    # the speed gun's ring: tight, since a detector box can sit half a metre off a sprinting player
APPARENT_HEIGHT_M = 1.42          # demo.composite: a player's height in the picture over the grass scale across it


def ease(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return 1 - (1 - t) ** 3


def window(t: float, a: float, b: float) -> float:
    return ease((t - a) / (b - a)) if b > a else float(t >= a)


def ground_circle(c, r: float, n: int = 64) -> np.ndarray:
    t = np.linspace(0, 2 * np.pi, n)
    return np.c_[c[0] + r * np.cos(t), c[1] + r * np.sin(t)]


def pct(v: float) -> str:
    """A probability for the screen: one decimal under 10%, whole points above."""
    return f"{v * 100:.1f}%" if v < 0.1 else f"{int(v * 100 + 0.5)}%"      # half up, as printed in captions


def ellipse_m(z: dict, n: int = 72) -> np.ndarray:
    """A zone {cx, cy, rx, ry, angle_deg} as a ground polygon in metres."""
    t = np.linspace(0, 2 * np.pi, n)
    a = np.radians(z["angle_deg"])
    x, y = z["rx"] * np.cos(t), z["ry"] * np.sin(t)
    return np.c_[z["cx"] + x * np.cos(a) - y * np.sin(a), z["cy"] + x * np.sin(a) + y * np.cos(a)]


def bracket(samples: list[dict], t_ms: float) -> tuple[int, int, float]:
    """Indices of the samples around t_ms and the fraction between them (clamped at the ends)."""
    times = np.array([s["clip_ms"] for s in samples], float)
    i = int(np.clip(np.searchsorted(times, t_ms, side="right") - 1, 0, len(samples) - 1))
    j = min(i + 1, len(samples) - 1)
    f = 0.0 if j == i else float(np.clip((t_ms - times[i]) / (times[j] - times[i]), 0, 1))
    return i, j, f


def lateral_px_per_m(cam: Camera, xy) -> float:
    """Pixels per metre on the grass at xy, along the direction that runs across the picture."""
    m, e = np.asarray(xy, float), 1e-3
    jac = np.c_[cam.project([m + [e, 0], m + [0, e]]).T - cam.project([m]).T] / e
    return 1 / np.linalg.norm(np.linalg.solve(jac, [1.0, 0.0]))


SS = 2                         # overlays are drawn at SS x and downsampled: anti-aliased shapes and text (v9)


def _hi_font(font):
    key = (getattr(font, "path", None), getattr(font, "size", None))
    if key not in _HI_FONTS:
        _HI_FONTS[key] = ImageFont.truetype(font.path, font.size * SS)
    return _HI_FONTS[key]


_HI_FONTS: dict = {}


def _sc(v):
    if v is None:
        return None
    if isinstance(v, int | float | np.integer | np.floating):
        return v * SS
    return [_sc(x) for x in v] if not isinstance(v, tuple) else tuple(_sc(x) for x in v)


class HiDraw:
    """ImageDraw on an SS x layer that takes 1x coordinates, sizes and fonts (so call sites stay unchanged); the
    layer is flattened onto the frame with `flatten`, which downsamples it with premultiplied alpha."""

    def __init__(self, layer: Image.Image):
        self.d = ImageDraw.Draw(layer)
        self._image = layer

    def text(self, xy, text, fill=None, font=None, anchor=None, stroke_width=0, stroke_fill=None, **kw):
        self.d.text(_sc(xy), text, fill=fill, font=_hi_font(font) if font else None, anchor=anchor,
                    stroke_width=int(stroke_width * SS), stroke_fill=stroke_fill, **kw)

    def textlength(self, text, font=None, **kw) -> float:
        return self.d.textlength(text, font=_hi_font(font), **kw) / SS

    def textbbox(self, xy, text, font=None, anchor=None, **kw):
        return tuple(v / SS for v in self.d.textbbox(_sc(xy), text, font=_hi_font(font), anchor=anchor, **kw))

    def rounded_rectangle(self, box, radius=0, fill=None, outline=None, width=1, **kw):
        self.d.rounded_rectangle(_sc(tuple(box)), radius=radius * SS, fill=fill, outline=outline, width=int(width * SS),
                                 **kw)

    def rectangle(self, box, fill=None, outline=None, width=1):
        self.d.rectangle(_sc(tuple(box)), fill=fill, outline=outline, width=int(width * SS))

    def ellipse(self, box, fill=None, outline=None, width=1):
        self.d.ellipse(_sc(tuple(box)), fill=fill, outline=outline, width=int(width * SS))

    def line(self, xy, fill=None, width=0, joint=None):
        self.d.line(_sc(xy if isinstance(xy, tuple) else [tuple(p) if not isinstance(p, int | float) else p
                                                           for p in xy]),
                    fill=fill, width=int(width * SS), joint=joint)

    def polygon(self, xy, fill=None, outline=None, width=1):
        self.d.polygon(_sc([tuple(p) for p in xy]), fill=fill, outline=outline, width=int(width * SS))

    def composite(self, slot: Image.Image, xy) -> None:
        """Paste an SS x RGBA slot at 1x position xy."""
        self._image.alpha_composite(slot, (int(xy[0] * SS), int(xy[1] * SS)))


def hi_layer(size) -> Image.Image:
    return Image.new("RGBA", (size[0] * SS, size[1] * SS), (0, 0, 0, 0))


def flatten(im: Image.Image, layer: Image.Image) -> None:
    """Downsample an SS x layer (premultiplied, so edges stay clean) and composite it onto the frame."""
    small = layer.convert("RGBa").resize(im.size, Image.LANCZOS).convert("RGBA")
    im.paste(small, (0, 0), small)


def downsample_rgba(buf: np.ndarray, w: int, h: int) -> np.ndarray:
    """An SS x matplotlib RGBA buffer (0..1) to w x h, premultiplied so the anti-aliased edges keep their colour."""
    if buf.shape[1] == w:
        return buf
    a = buf[..., 3:4]
    pm = np.concatenate([buf[..., :3] * a, a], axis=2).astype(np.float32)
    small = cv2.resize(pm, (w, h), interpolation=cv2.INTER_AREA)
    out = small.copy()
    out[..., :3] = np.where(small[..., 3:4] > 1e-6, small[..., :3] / np.maximum(small[..., 3:4], 1e-6), 0)
    return out


class Live:
    """One overlay beat on the playing clip. Subclasses draw `ground` (pitch-plane graphics through the frame's
    camera, matplotlib) and `panels` (tags and cards, PIL); `span` is the clip time it covers."""

    def __init__(self, m: dict):
        self.m = m
        self.data = json.loads((ROOT / m["data"]).read_text())
        self.data = self.data.get("result", self.data)
        self.kit = np.array((m.get("kits") or {}).get(m.get("team", "home"), ORANGE)) / 255
        self.font = {z: ImageFont.truetype(FONT, z) for z in (22, 26, 30, 34, 50, 64)}
        self.reg = {z: ImageFont.truetype(FONT_REG, z) for z in (20, 22, 26)}
        self.camera_note = ""
        self.calib = self._calib()
        self.fps_clip = float(self.calib.get("fps", 50.0))

    # -- time and camera -------------------------------------------------------------------------------------
    def span(self) -> tuple[float, float]:
        raise NotImplementedError

    def _calib(self) -> dict:
        shot = self.m.get("shot_id") or self.data.get("shot_id")
        if isinstance(shot, list):                       # a run across camera cuts: one fit per shot
            shots = json.loads((FOOTAGE / self.m["clip"] / "shots.json").read_text())["shots"]
            d = FOOTAGE / self.m["clip"] / "calib"
            multi = {}
            for sid in shot:
                path = next(p for p in (d / f"{sid}_refined.json", d / f"{sid}.json") if p.exists())
                rng = next((x["start"], x["end"]) for x in shots if x["id"] == sid)
                multi[sid] = (rng, json.loads(path.read_text()))
            return {"multi": multi, "fps": next(iter(multi.values()))[1].get("fps", 50.0)}
        if shot is None:
            shots = json.loads((FOOTAGE / self.m["clip"] / "shots.json").read_text())["shots"]
            t0 = self.span()[0]
            shot = next((s["id"] for s in shots if s["start"] <= t0 <= s["end"]), None)
        d = FOOTAGE / self.m["clip"] / "calib"
        path = next((p for p in (d / f"{shot}_refined.json", d / f"{shot}.json") if p.exists()), None)
        cands = []
        if self.data.get("homography") and self.freeze_at() is not None:     # the beat's own fit
            cands.append(("beat homography", {"static": self.data["homography"]["image_to_pitch"]}))
        if path is not None:
            cands.append((path.name, json.loads(path.read_text())))
        if not cands:
            if self.needs_camera:
                raise FileNotFoundError(f"{self.m['name']}: no calibration for shot {shot} (demo.refine_calib)")
            return {}
        if len(cands) == 1 or self.freeze_at() is None:
            return cands[-1][1]
        return self._best(cands)

    def _best(self, cands: list[tuple[str, dict]]) -> dict:
        """A frozen beat with more than one camera (its own homography, fitted at some instant; the shot's per-frame
        fit): each measured on the freeze frame against the paint (demo.footage.drift_px), the lowest p95 kept."""
        from demo.footage import board_top, drift_px, model_lines
        t = self.freeze_at()
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(FOOTAGE / self.m["clip"] /
                              "clip.mp4"), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True, check=True).stdout
        frame = np.frombuffer(raw, np.uint8).reshape(H, W, 3)
        lines = [n for n in model_lines() if n != "touchline_far"]
        scored = []
        for name, c in cands:
            self.calib, self.fps_clip = c, float(c.get("fps", 50.0))
            cam = self.camera(t)
            dr = drift_px(cam, frame, lines, top=board_top(cam, W))
            scored.append((dr.p95 if dr.lines else float("inf"), name, c, dr))
        scored.sort(key=lambda x: x[0])
        best = scored[0]
        self.camera_note = "; ".join(f"{n}: p95 {p:.2f} px" for p, n, _, _ in scored) + f" -> {best[1]}"
        return best[2]

    needs_camera = True                    # charts and cards over the frame draw nothing on the grass
    always_panels = False                  # panels that stay up through a cut with no camera

    def _panels_only(self, img: np.ndarray, t: float) -> Image.Image:
        im = Image.fromarray(img.copy())
        self.panels(im, None, t)
        return im

    def camera(self, t: float) -> Camera | None:
        if not self.calib:
            return None
        if "static" in self.calib:                       # moment-file frame already (y from the near touchline)
            return Camera(np.linalg.inv(np.asarray(self.calib["static"], float)))
        if "multi" in self.calib:                        # the shot on screen at t; None in a cut between them
            hit = next(((rng, c) for rng, c in self.calib["multi"].values() if rng[0] <= t <= rng[1]), None)
            return from_pitchwatch(hit[1], int(round(t * self.fps_clip))) if hit else None
        return from_pitchwatch(self.calib, int(round(t * self.fps_clip)))

    def freeze_at(self) -> float | None:
        """Clip seconds after which the picture holds still (the end of a run, the pass), or None."""
        return None

    def dim(self, t: float) -> float:
        """How far the picture is darkened under a chart or card (0..1)."""
        return 0.0

    # -- drawing ---------------------------------------------------------------------------------------------
    def ground(self, ax, cam: Camera, t: float) -> None:
        pass

    def panels(self, im: Image.Image, cam: Camera, t: float) -> None:
        pass

    def tag(self, d: ImageDraw.ImageDraw, cam: Camera, xy, text: str, colour, a: float = 1.0,
            font_size: int = 26, glow: bool = False) -> None:
        """A pill just above the head of the player standing at xy (metres)."""
        feet = cam.project([xy])[0]
        y = feet[1] - APPARENT_HEIGHT_M * lateral_px_per_m(cam, xy) - 14
        font = self.font[font_size]
        w = d.textlength(text, font=font) + 28
        cx = float(np.clip(feet[0], 24 + w / 2, W - 24 - w / 2))          # inside the frame
        box = (cx - w / 2, y - font_size - 16, cx + w / 2, y)
        if glow:
            d.rounded_rectangle((box[0] - 4, box[1] - 4, box[2] + 4, box[3] + 4), radius=12,
                                fill=(*colour, int(90 * a)))
        d.rounded_rectangle(box, radius=8, fill=(*PANEL, int(220 * a)), outline=(*colour, int(255 * a)), width=3)
        d.text(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2), text, font=font, fill=(*colour, int(255 * a)),
               anchor="mm")

    def card(self, d: ImageDraw.ImageDraw, title: str, rows: list[tuple[str, str, tuple]], foot: str, a: float,
             accent=None, big: str | None = None) -> None:
        """Bottom-left card: a title, an optional big number, label/value rows, a provenance line."""
        w = getattr(self, "card_w", PANEL_W)
        foot_lines = self._wrap(d, foot, self.reg[20], w - 60)
        h = 64 + (80 if big else 0) + 42 * len(rows) + 12 + 24 * len(foot_lines)
        x0, y0 = 96 - int((1 - a) * 40), H - 96 - h
        al = int(255 * a)
        accent = accent or tuple(int(v) for v in self.kit * 255)
        d.rounded_rectangle((x0, y0, x0 + w, y0 + h), radius=10, fill=(*PANEL, int(232 * a)))
        d.rectangle((x0, y0, x0 + 8, y0 + h), fill=(*accent, al))
        d.text((x0 + 32, y0 + 20), title.upper(), font=self.font[22], fill=(*MUTED, al))
        y = y0 + 54
        if big:
            d.text((x0 + 32, y), big, font=self.font[64], fill=(255, 255, 255, al))
            y += 80
        for label, value, colour in rows:
            d.text((x0 + 32, y + 4), label, font=self.reg[22], fill=(230, 236, 242, al))
            d.text((x0 + w - 28, y + 16), value, font=self.font[30], fill=(*colour, al), anchor="rm")
            y += 42
        for k, line in enumerate(foot_lines):
            d.text((x0 + w - 28, y0 + h - 14 - 24 * (len(foot_lines) - 1 - k)), line, font=self.reg[20],
                   fill=(*MUTED, al), anchor="rb")

    @staticmethod
    def _wrap(d, text: str, font, width: float) -> list[str]:
        lines = [""]
        for word in text.split():
            trial = f"{lines[-1]} {word}".strip()
            if d.textlength(trial, font=font) <= width or not lines[-1]:
                lines[-1] = trial
            else:
                lines.append(word)
        return [ln for ln in lines if ln]

    # -- export ----------------------------------------------------------------------------------------------
    def export(self, path: Path) -> Path:
        t0, t1 = self.span()
        src = FOOTAGE / self.m["clip"] / "clip.mp4"
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-i", str(src), "-t", f"{t1 - t0:.3f}",
                              "-vf", f"fps={FPS}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True, check=True).stdout
        frames = np.frombuffer(raw, np.uint8).reshape(-1, H, W, 3)
        fig = Figure(figsize=(W / 100, H / 100), dpi=100 * SS)
        fig.patch.set_alpha(0)
        canvas = FigureCanvasAgg(fig)
        ax = fig.add_axes((0, 0, 1, 1))
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s",
                                f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf",
                                "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)],
                               stdin=subprocess.PIPE)
        hold = self.freeze_at()
        for i in range(int(round((t1 - t0) * FPS))):
            t = t0 + i / FPS
            k = min(i, len(frames) - 1) if hold is None or t <= hold else min(int(round((hold - t0) * FPS)),
                                                                                len(frames) - 1)
            enc.stdin.write(self.frame(frames[k], t, ax, canvas, cam_t=min(t, hold) if hold else t).tobytes())
        enc.stdin.close()
        if enc.wait():
            raise RuntimeError("ffmpeg encode failed")
        return path

    def preview(self, t: float) -> Image.Image:
        """One frame of the beat at clip time t (for review and tests)."""
        hold = self.freeze_at()
        tc = min(t, hold) if hold else t
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{tc:.3f}", "-i",
                              str(FOOTAGE / self.m["clip"] / "clip.mp4"), "-frames:v", "1", "-f", "rawvideo",
                              "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
        fig = Figure(figsize=(W / 100, H / 100), dpi=100 * SS)
        fig.patch.set_alpha(0)
        canvas = FigureCanvasAgg(fig)
        return self.frame(np.frombuffer(raw, np.uint8).reshape(H, W, 3), t, fig.add_axes((0, 0, 1, 1)), canvas,
                          cam_t=tc)

    def frame(self, img: np.ndarray, t: float, ax, canvas, cam_t: float | None = None) -> Image.Image:
        cam = self.camera(t if cam_t is None else cam_t)
        ax.clear()
        ax.set_xlim(0, W)
        ax.set_ylim(H, 0)
        ax.axis("off")
        if cam is None and self.needs_camera:            # a cut to a camera with no geometry: the clip alone
            return Image.fromarray(img) if not self.always_panels else self._panels_only(img, t)
        self.ground(ax, cam, t)
        canvas.draw()
        g = downsample_rgba(np.asarray(canvas.buffer_rgba(), float) / 255, W, H)
        f = img.astype(float) / 255 * (1 - self.dim(t))
        f = f * (1 - g[..., 3:4]) + g[..., :3] * g[..., 3:4]
        im = Image.fromarray(np.clip(f * 255, 0, 255).astype(np.uint8))
        self.panels(im, cam, t)
        return im


class Oracle(Live):
    """The attacking team's chance of a shot in the next 10 s (bar) and its threat zone on the grass (track B's
    cache/oracle window, a sample every 0.5 s)."""

    def span(self):
        return self.data["start_clip_ms"] / 1000 - float(self.m.get("pre_s", 1.0)), self.data["end_clip_ms"] / 1000

    def __init__(self, m: dict):
        super().__init__(m)
        g = json.loads((ROOT / m["goal_data"]).read_text()) if m.get("goal_data") else None
        self.goal = g.get("result", g) if g else None

    def goal_at(self, t: float) -> tuple[float, float] | None:
        """(bar value eased between samples, the latest sample's value) from track A's goal-in-10s series; a sample
        with no value (no ball detected) holds the one before."""
        if not self.goal:
            return None
        team = self.m.get("team", "home")
        s = [x for x in self.goal["samples"] if (x.get("p_goal_10s") or {}).get(team) is not None]
        i, j, f = bracket(s, t * 1000)
        pi, pj = s[i]["p_goal_10s"][team], s[j]["p_goal_10s"][team]
        return pi + (pj - pi) * ease(f), pi

    def at(self, t: float):
        s, team = self.data["samples"], self.m.get("team", "home")
        i, j, f = bracket(s, t * 1000)
        pi, pj = s[i]["p_shot_10s_smoothed"][team], s[j]["p_shot_10s_smoothed"][team]
        zi, zj = s[i]["threat_zone"][team], s[j]["threat_zone"][team]
        if zi and zj:
            zone = {k: zi[k] + (zj[k] - zi[k]) * f for k in ("cx", "cy", "rx", "ry")}
            zone["angle_deg"] = zi["angle_deg"] + ((zj["angle_deg"] - zi["angle_deg"] + 90) % 180 - 90) * f
        else:
            zone = (zj if f > 0.5 else zi) or zi or zj
        return pi + (pj - pi) * ease(f), pi, zone

    def ground(self, ax, cam, t):
        a = window(t, self.data["start_clip_ms"] / 1000 - 0.2, self.data["start_clip_ms"] / 1000 + 0.4)
        _, _, zone = self.at(t)
        if zone and a > 0:
            poly = cam.project(ellipse_m(zone))
            ax.add_patch(Polygon(poly, closed=True, fc=(*self.kit, 0.30 * a), ec=(0, 0, 0, 0.5 * a), lw=5.5))
            ax.add_patch(Polygon(poly, closed=True, fill=False, ec=(*self.kit, a), lw=3.0))

    def panels(self, im, cam, t):
        a = window(t, self.data["start_clip_ms"] / 1000 - 0.2, self.data["start_clip_ms"] / 1000 + 0.4)
        if a <= 0:
            return
        if self.m.get("card") is False:                 # v5: the zone alone, a label and no number
            layer = hi_layer(im.size)
            d = HiDraw(layer)
            d.text((W / 2, 120), self.m.get("label", "WHYLINE IS WATCHING").upper(), font=self.font[34],
                   fill=(255, 255, 255, int(235 * a)), anchor="mm", stroke_width=4, stroke_fill=(0, 0, 0, int(200 * a)))
            flatten(im, layer)
            return
        bar, value, _ = self.at(t)
        goal = self.goal_at(t)
        if goal is not None:                             # v4: the owner's metric, goal in the next 10 s
            bar, value = goal
        layer = hi_layer(im.size)
        d = HiDraw(layer)
        x0, h = 96 - int((1 - a) * 40), 196
        y0, al = H - 96 - h, int(255 * a)
        kit = tuple(int(v) for v in self.kit * 255)
        d.rounded_rectangle((x0, y0, x0 + PANEL_W, y0 + h), radius=10, fill=(*PANEL, int(232 * a)))
        d.rectangle((x0, y0, x0 + 8, y0 + h), fill=(*kit, al))
        d.text((x0 + 32, y0 + 20), self.m.get("label", "Shot in the next 10 s").upper(), font=self.font[22],
               fill=(*MUTED, al))
        d.text((x0 + 32, y0 + 50), pct(value) if self.goal else f"{round(value * 100)}%", font=self.font[64],
               fill=(255, 255, 255, al))
        bar = min(1.0, bar / float(self.m.get("bar_max", 1.0)))   # a goal chance of a few % needs its own scale
        bx0, bx1, by = x0 + 32, x0 + PANEL_W - 28, y0 + 132
        d.rounded_rectangle((bx0, by, bx1, by + 12), radius=6, fill=(255, 255, 255, int(28 * a)))
        d.rounded_rectangle((bx0, by, bx0 + max(12, (bx1 - bx0) * bar), by + 12), radius=6, fill=(*kit, al))
        src = self.goal or self.data
        d.text((x0 + PANEL_W - 28, y0 + h - 16),
               f"n = {src['n']:,} per 0.5 s, {src['horizon_s']:g} s, seed {src['seed']}",
               font=self.reg[20], fill=(*MUTED, al), anchor="rb")
        flatten(im, layer)


class SpeedGun(Live):
    """A player's run: a trail of where he has been, a ring and a live km/h tag on him, and at the end a card with
    his top speed and the distance (track A's tracking; every printed speed is a tracking sample). Across camera
    cuts each shot draws through its own fit; through a cut with no geometry (a close-up) nothing is drawn, and the
    distance, which crosses it in a straight line, is shown as a lower bound."""

    always_panels = True

    TRAIL_S = 3.0

    def span(self):
        return (self.data["start_clip_ms"] / 1000 - float(self.m.get("pre_s", 0.5)),
                self.data["end_clip_ms"] / 1000 + float(self.m.get("hold_s", 2.5)))

    def freeze_at(self):
        return self.data["end_clip_ms"] / 1000

    def pos(self, t: float) -> np.ndarray:
        s = self.data["samples"]
        i, j, f = bracket(s, t * 1000)
        return np.array([s[i]["x"] + (s[j]["x"] - s[i]["x"]) * f, s[i]["y"] + (s[j]["y"] - s[i]["y"]) * f])

    def ground(self, ax, cam, t):
        s = self.data["samples"]
        start, end = self.data["start_clip_ms"], self.data["end_clip_ms"]
        now = min(t * 1000, end)
        if now < start or self.in_gap(now):
            return
        start = max([start] + [g["to_clip_ms"] for g in self.data.get("gaps", []) if g["to_clip_ms"] <= now])
        pts = np.array([[p["x"], p["y"]] for p in s if max(start, now - self.TRAIL_S * 1000) <= p["clip_ms"] <= now]
                       + [self.pos(now / 1000).tolist()])
        if len(pts) > 1:
            px = cam.project(pts)
            n = len(px)
            for k in range(n - 1):                               # fades toward the tail
                a = 0.15 + 0.85 * (k + 1) / n
                ax.plot(px[k:k + 2, 0], px[k:k + 2, 1], color=(0, 0, 0, 0.45 * a), lw=10, solid_capstyle="round")
                ax.plot(px[k:k + 2, 0], px[k:k + 2, 1], color=(*self.kit, a), lw=5.5, solid_capstyle="round")
        ring = cam.project(ground_circle(self.pos(now / 1000), RUNNER_RING_M))
        ax.plot(ring[:, 0], ring[:, 1], color=(0, 0, 0, 0.5), lw=6)
        ax.plot(ring[:, 0], ring[:, 1], color=(*self.kit, 1.0), lw=3)

    def in_gap(self, ms: float) -> bool:
        return any(g["from_clip_ms"] <= ms <= g["to_clip_ms"] for g in self.data.get("gaps", []))

    def speed_now(self, ms: float) -> float | None:
        """The latest trusted speed sample at or before ms (speeds are null where the fit is not trusted)."""
        good = [p for p in self.data["samples"] if p["clip_ms"] <= ms and p.get("speed_kmh") is not None]
        return good[-1]["speed_kmh"] if good and ms - good[-1]["clip_ms"] < 600 else None

    def panels(self, im, cam, t):
        start, end = self.data["start_clip_ms"], self.data["end_clip_ms"]
        if t * 1000 < start:
            return
        now = min(t * 1000, end)
        layer = hi_layer(im.size)
        d = HiDraw(layer)
        p = self.data["player"]
        kit = tuple(int(v) for v in self.kit * 255)
        v = self.speed_now(now)
        if cam is not None and not self.in_gap(now):
            label = self.m.get("tag_name", p.get("name", p["label"]).split()[-1]).upper()
            self.tag(d, cam, self.pos(now / 1000), f"{label}  {v:.1f} km/h" if v is not None else label, kit,
                     font_size=30)
        a = window(t, end / 1000, end / 1000 + 0.5)
        if a > 0:
            dist = f"at least {int(self.data['distance_m'])} m" if self.data.get("gaps") else \
                f"{round(self.data['distance_m'])} m"
            self.card(d, self.m.get("label", f"{p.get('name', p['label'])}: the run"),
                      [("Top speed", f"{self.data['top_speed_kmh']:.1f} km/h", WHITE), ("Distance", dist, WHITE)],
                      self.m.get("foot", "from broadcast tracking"), a)
        flatten(im, layer)


class PassXray(Live):
    """Every teammate tagged with his goal chance if the holder passed to him now, ranked; the best one glows and
    the line to him is drawn bright (track B's samples every 0.5 s; tags print the latest sample's values)."""

    def __init__(self, m: dict):
        super().__init__(m)
        s = self.data["samples"]
        if "t0" in m or "t1" in m or "team_index" in m:   # the attack the beat is about: one team, one window
            s = [x for x in s if m.get("t0", 0) <= x["clip_ms"] / 1000 <= m.get("t1", 1e9)
                 and ("team_index" not in m or x.get("team") == m["team_index"])]
        self.data["samples"] = s
        self._holders()

    def _holders(self) -> None:
        """Holder positions from the shot's tracks where the samples carry none (labels 't<track_id>')."""
        shot = self.data.get("shot_id")
        path = FOOTAGE / self.m["clip"] / "tracks" / f"{shot}.json"
        if not path.exists() or all(x.get("holder_xy") for x in self.data["samples"]):
            return
        tr = json.loads(path.read_text())
        frames = {f["frame"]: f for f in tr["frames"]}
        keys = np.array(sorted(frames))
        for x in self.data["samples"]:
            want = int(str(x["holder"]).lstrip("t"))
            k = int(keys[np.argmin(np.abs(keys - x["clip_ms"] / 1000 * float(tr["fps"])))])
            hit = next((p for p in frames[k]["players"] if p["track_id"] == want and p.get("xy")), None)
            x["holder_xy"] = [hit["xy"][0], PITCH_W - hit["xy"][1]] if hit else None

    def value(self, v: float) -> str:
        """An option's value as printed: xG to two decimals (v5), else a probability."""
        return f"{v:.2f} xG" if self.m.get("value_fmt") == "xg" else pct(v)

    def role(self, o: dict) -> str:
        """Where an unnamed player stands, for his label: six-yard box, penalty box or outside it."""
        team = (self.data.get("team") or {}).get(str(self.m.get("team_index", "")), self.m.get("unnamed", "Teammate"))
        team = self.m.get("team_short", team)
        gx = 0.0 if o["x"] < 52.5 else 105.0
        depth, wide = abs(o["x"] - gx), abs(o["y"] - 34)
        where = "six-yard box" if depth <= 5.5 and wide <= 9.16 else "in the box" if depth <= 16.5 and wide <= 20.16 \
            else "outside the box"
        return f"{team} runner, {where}"

    def span(self):
        s = self.data["samples"]
        return s[0]["clip_ms"] / 1000 - float(self.m.get("pre_s", 0.5)), s[-1]["clip_ms"] / 1000 + \
            float(self.m.get("hold_s", 0.5))

    def freeze_at(self):
        return self.data["samples"][-1]["clip_ms"] / 1000 if self.m.get("hold_s") else None

    def ground(self, ax, cam, t):
        s = self.data["samples"]
        if t * 1000 < s[0]["clip_ms"]:
            return
        i, j, f = bracket(s, t * 1000)
        cur, nxt = s[i], s[j]
        place = {o["label"]: np.array([o["x"], o["y"]]) for o in cur["options"]}
        for o in nxt["options"]:
            if o["label"] in place:
                place[o["label"]] = place[o["label"]] + (np.array([o["x"], o["y"]]) - place[o["label"]]) * f
        holder = place.get(cur["holder"]) if cur["holder"] in place else self._holder_xy(cur, nxt, f)
        best = max(cur["options"], key=lambda o: o["p_goal"]) if cur["options"] else None
        shoot = cur.get("shoot_now_p_goal")
        best = best["label"] if best and (shoot is None or best["p_goal"] >= shoot) else None   # a pass only
        for o in cur["options"]:
            if holder is None or o["label"] == cur["holder"]:
                continue
            seg = cam.project(np.linspace(holder, place[o["label"]], 24))
            on = o["label"] == best
            col = (*(np.array(ORANGE) / 255), 0.95) if on else (1, 1, 1, 0.28)
            ax.plot(seg[:, 0], seg[:, 1], color=(0, 0, 0, 0.4 if on else 0.15), lw=8 if on else 4)
            ax.plot(seg[:, 0], seg[:, 1], color=col, lw=4.5 if on else 2, dashes=(4, 2) if on else (2, 3))
            ring = cam.project(ground_circle(place[o["label"]], 1.0))
            ax.plot(ring[:, 0], ring[:, 1], color=col[:3] + (1.0 if on else 0.6,), lw=4 if on else 2)
        if holder is not None:
            ring = cam.project(ground_circle(holder, 1.1))
            ax.plot(ring[:, 0], ring[:, 1], color=(*self.kit, 1.0), lw=4)

    def _holder_xy(self, cur, nxt, f):
        h = cur.get("holder_xy")
        return np.array(h) if h else None

    def panels(self, im, cam, t):
        s = self.data["samples"]
        if t * 1000 < s[0]["clip_ms"]:
            return
        i, j, f = bracket(s, t * 1000)
        cur = s[i]
        place = {o["label"]: np.array([o["x"], o["y"]]) for o in cur["options"]}
        for o in s[j]["options"]:
            if o["label"] in place:
                place[o["label"]] = place[o["label"]] + (np.array([o["x"], o["y"]]) - place[o["label"]]) * f
        ranked = sorted((o for o in cur["options"] if o["label"] != cur["holder"]), key=lambda o: -o["p_goal"])
        layer = hi_layer(im.size)
        d = HiDraw(layer)
        shoot = cur.get("shoot_now_p_goal")
        pass_best = bool(ranked) and (shoot is None or ranked[0]["p_goal"] >= shoot)   # else the shot is best
        for rank, o in enumerate(ranked[: int(self.m.get("tags", 5))]):
            name = f"  {o['name'].split()[-1]}" if o.get("name") else ""
            top = rank == 0 and pass_best
            self.tag(d, cam, place[o["label"]], f"{rank + 1}{name}  {self.value(o['p_goal'])}",
                     ORANGE if top else WHITE, font_size=30 if top else 26, glow=top)
        a = window(t, s[0]["clip_ms"] / 1000, s[0]["clip_ms"] / 1000 + 0.5)
        foot = (f"n = {self.data['n']}, {self.data['horizon_s']:g} s, seed {self.data['seed']}"
                if self.data.get("n") else self.m.get("foot", ""))
        entries = [(o.get("name") or self.role(o), o["p_goal"]) for o in ranked[: int(self.m.get("rows", 3))]]
        if shoot is not None:                            # the shot ranked with the passes
            entries.append(("Shooting now", shoot))
        entries.sort(key=lambda e: -e[1])
        rows = [(f"{k + 1}. {label}", self.value(v), ORANGE if k == 0 else WHITE)
                for k, (label, v) in enumerate(entries)]
        self.card(d, self.m.get("label", "Pass X-ray: goal chance if passed to"), rows, foot, a)
        flatten(im, layer)


class Offside(Live):
    """A line across the pitch at the second-last defender, following him; at the pass it holds and the gap to the
    attacker is printed with its uncertainty (track A/B's offside samples)."""

    def span(self):
        s = self.data["samples"]
        return (s[0]["clip_ms"] / 1000 - float(self.m.get("pre_s", 0.5)),
                self.data["pass_clip_ms"] / 1000 + float(self.m.get("hold_s", 3.0)))

    def freeze_at(self):
        return self.data["pass_clip_ms"] / 1000

    def line_x(self, t: float) -> float:
        s = self.data["samples"]
        i, j, f = bracket(s, min(t * 1000, self.data["pass_clip_ms"]))
        return s[i]["line_x"] + (s[j]["line_x"] - s[i]["line_x"]) * f

    def ground(self, ax, cam, t):
        s = self.data["samples"]
        if t * 1000 < s[0]["clip_ms"]:
            return
        x = self.line_x(t)
        line = cam.project(np.c_[np.full(120, x), np.linspace(0, PITCH_W, 120)])
        ax.plot(line[:, 0], line[:, 1], color=(0, 0, 0, 0.55), lw=8)
        ax.plot(line[:, 0], line[:, 1], color=(*(np.array(YELLOW) / 255), 1.0), lw=3.5)
        if t * 1000 >= self.data["pass_clip_ms"]:
            ax_x = self.data["samples"][-1].get("attacker_x", self.data.get("attacker_x"))
            if ax_x is not None:
                att = cam.project(np.c_[np.full(120, ax_x), np.linspace(0, PITCH_W, 120)])
                ax.plot(att[:, 0], att[:, 1], color=(*(np.array(ORANGE) / 255), 0.9), lw=3, dashes=(6, 3))

    def panels(self, im, cam, t):
        a = window(t, self.data["pass_clip_ms"] / 1000, self.data["pass_clip_ms"] / 1000 + 0.4)
        if a <= 0:
            return
        layer = hi_layer(im.size)
        d = HiDraw(layer)
        gap, err = self.data["gap_m"], self.data["uncertainty_m"]
        who = self.m.get("attacker", "Attacker")
        verdict = "level: inside the error" if abs(gap) <= err else ("beyond the line" if gap > 0 else "onside")
        self.card(d, self.m.get("label", "Last defender's line at the pass"),
                  [(f"{who}", f"{'+' if gap > 0 else '−'}{abs(gap):.1f} m", YELLOW),
                   ("Tracking error", f"± {err:.1f} m", WHITE), ("Verdict", verdict, YELLOW)],
                  self.m.get("foot", "from broadcast tracking"), a, accent=YELLOW)
        flatten(im, layer)


class Still(Live):
    """A beat drawn on a frozen frame: `pre_s` of the clip playing up to `clip_ms`, then the picture holds for
    `hold_s` while the graphics build (tau = seconds since the freeze)."""

    def at_ms(self) -> int:
        return int(self.data.get("clip_ms") or self.m["clip_ms"])

    def span(self):
        t = self.at_ms() / 1000
        return t - float(self.m.get("pre_s", 2.0)), t + float(self.m.get("hold_s", 6.0))

    def freeze_at(self):
        return self.at_ms() / 1000

    def tau(self, t: float) -> float:
        return t - self.at_ms() / 1000


def ghost_figure(d: ImageDraw.ImageDraw, cam: Camera, xy, colour, a: float) -> None:
    """A translucent standing figure (capsule) at xy: where a player should have been."""
    feet = cam.project([xy])[0]
    h = APPARENT_HEIGHT_M * lateral_px_per_m(cam, xy)
    w = h * 0.32
    d.rounded_rectangle((feet[0] - w / 2, feet[1] - h, feet[0] + w / 2, feet[1]), radius=int(w / 2),
                        fill=(*colour, int(110 * a)), outline=(255, 255, 255, int(200 * a)), width=2)
    d.ellipse((feet[0] - w * 0.42, feet[1] - h - w * 0.62, feet[0] + w * 0.42, feet[1] - h + w * 0.2),
              fill=(*colour, int(120 * a)), outline=(255, 255, 255, int(200 * a)), width=2)


class GhostDefender(Still):
    """The key defender ringed where he was, his ghost where he should have been, the metres between, and the goal
    chance with him there instead (track B's counterfactual)."""

    def ground(self, ax, cam, t):
        r, a = self.data, window(self.tau(t), 0.2, 0.8)
        if a <= 0:
            return
        real, ghost = np.array([r["defender"]["x"], r["defender"]["y"]]), np.array([r["ghost"]["x"], r["ghost"]["y"]])
        ring = cam.project(ground_circle(real, 1.0))
        ax.plot(ring[:, 0], ring[:, 1], color=(1, 1, 1, a), lw=3.5)
        g = window(self.tau(t), 0.8, 1.8)
        if g > 0:
            path = cam.project(np.linspace(real, real + (ghost - real) * g, 30))
            ax.plot(path[:, 0], path[:, 1], color=(0, 0, 0, 0.5), lw=8)
            ax.plot(path[:, 0], path[:, 1], color=(*(np.array(YELLOW) / 255), 1.0), lw=4, dashes=(4, 2))
            disc = cam.project(ground_circle(ghost, 1.0))
            ax.add_patch(Polygon(disc, closed=True, fc=(*self.kit, 0.35 * g), ec=(1, 1, 1, 0.8 * g), lw=2.5))

    def panels(self, im, cam, t):
        r, tau = self.data, self.tau(t)
        if tau < 0.2:
            return
        layer = hi_layer(im.size)
        d = HiDraw(layer)
        kit = tuple(int(v) for v in self.kit * 255)
        name = r["defender"].get("name") or self.m.get("defender_label", "Defender")   # never a guessed name
        self.tag(d, cam, [r["defender"]["x"], r["defender"]["y"]], name.upper(), WHITE)
        g = window(tau, 1.2, 1.8)
        if g > 0:
            ghost_figure(d, cam, [r["ghost"]["x"], r["ghost"]["y"]], kit, g)
            mid = (np.array([r["defender"]["x"], r["defender"]["y"]]) + [r["ghost"]["x"], r["ghost"]["y"]]) / 2
            px = cam.project([mid])[0]
            d.text((px[0], px[1] + 26), f"{r['metres_needed']:.1f} m", font=self.font[30],
                   fill=(*YELLOW, int(255 * g)), anchor="mm", stroke_width=3, stroke_fill=(0, 0, 0, int(200 * g)))
        c = window(tau, 2.0, 2.5)
        if c > 0:
            rows = [("Goal chance, as it was", f"{round(r['p_goal_actual'] * 100)}%", WHITE),
                    (f"With him {r['metres_needed']:.1f} m across", f"{round(r['p_goal_ghost'] * 100)}%", YELLOW)]
            if r.get("reach_m") is not None:
                rows.append((f"Ground he could cover in {r.get('t_avail_s', 1):g} s", f"{r['reach_m']:.1f} m", WHITE))
            self.card(d, self.m.get("label", f"If the {name.lower()} had been there"), rows,
                      f"n = {r['n']}, {r['horizon_s']:g} s, seed {r['seed']}; {r.get('error_note', '')}", c,
                      accent=kit)
        flatten(im, layer)


class KeeperCone(Still):
    """The shot's cone to the two posts, the keeper where he stood and where he should have stood, and the save
    chance at each (track B)."""

    def goal_x(self) -> float:
        return 105.0 if self.data["shot_from"][0] > 52.5 else 0.0

    def ground(self, ax, cam, t):
        r, tau = self.data, self.tau(t)
        a = window(tau, 0.2, 0.9)
        if a <= 0:
            return
        gx = self.goal_x()
        cone = np.array([r["shot_from"], [gx, 34 - 3.66], [gx, 34 + 3.66]])
        poly = cam.project(np.vstack([np.linspace(cone[0], cone[1], 20), np.linspace(cone[1], cone[2], 10),
                                      np.linspace(cone[2], cone[0], 20)]))
        ax.add_patch(Polygon(poly, closed=True, fc=(1, 1, 1, 0.16 * a), ec=(1, 1, 1, 0.7 * a), lw=2))
        k = np.array([r["keeper"]["x"], r["keeper"]["y"]])
        ring = cam.project(ground_circle(k, 0.9))
        ax.plot(ring[:, 0], ring[:, 1], color=(1, 1, 1, a), lw=3.5)
        b = window(tau, 1.0, 1.8)
        if b > 0:
            best = np.array([r["best"]["x"], r["best"]["y"]])
            path = cam.project(np.linspace(k, k + (best - k) * b, 20))
            ax.plot(path[:, 0], path[:, 1], color=(*(np.array(YELLOW) / 255), 1.0), lw=4, dashes=(4, 2))
            disc = cam.project(ground_circle(best, 0.9))
            ax.add_patch(Polygon(disc, closed=True, fc=(*self.kit, 0.4 * b), ec=(1, 1, 1, 0.9 * b), lw=2.5))

    def panels(self, im, cam, t):
        r, tau = self.data, self.tau(t)
        if tau < 0.2:
            return
        layer = hi_layer(im.size)
        d = HiDraw(layer)
        kit = tuple(int(v) for v in self.kit * 255)
        name = r["keeper"].get("name", "Keeper")
        self.tag(d, cam, [r["keeper"]["x"], r["keeper"]["y"]], name.split()[-1].upper(), WHITE)
        b = window(tau, 1.2, 1.8)
        if b > 0:
            ghost_figure(d, cam, [r["best"]["x"], r["best"]["y"]], kit, b)
        c = window(tau, 2.0, 2.5)
        if c > 0:
            gap = float(np.hypot(r["best"]["x"] - r["keeper"]["x"], r["best"]["y"] - r["keeper"]["y"]))
            if r.get("coverage_actual") is not None:         # geometry: share of the goal mouth he covers
                a_ = r.get("assumptions", {})
                self.card(d, self.m.get("label", f"{name}: where to stand"),
                          [("Goal covered where he stood", f"{round(r['coverage_actual'] * 100)}%", WHITE),
                           (f"From the best point, {r.get('move_m', gap):.1f} m out",
                            f"{round(r['coverage_best'] * 100)}%", YELLOW)],
                          f"geometry, not a save chance: reach {a_.get('standing_reach_m')} m standing to "
                          f"{a_.get('max_reach_m')} m diving, {a_.get('reaction_s')} s to react, shot "
                          f"{a_.get('shot_speed_ms')} m/s; {r.get('error_note', '')}", c, accent=kit)
            else:
                self.card(d, self.m.get("label", f"{name}: where to stand"),
                          [("Save chance where he stood", f"{round(r['save_actual'] * 100)}%", WHITE),
                           (f"From the best spot, {gap:.1f} m away", f"{round(r['save_best'] * 100)}%", YELLOW)],
                          f"n = {r['n']}, seed {r['seed']}", c, accent=kit)
        flatten(im, layer)


class CardOnly(Still):
    """A card over the frozen, dimmed picture: the red-card cost (11 v 11 against 11 v 10) or the measurement card.
    `rows` are built from the data by the subclass."""

    needs_camera = False

    def dim(self, t):
        return 0.35 * window(self.tau(t), 0.0, 0.6)

    def content(self) -> tuple[str, str | None, list[tuple[str, str, tuple]], str]:
        raise NotImplementedError

    def panels(self, im, cam, t):
        c = window(self.tau(t), 0.3, 0.9)
        if c <= 0:
            return
        layer = hi_layer(im.size)
        d = HiDraw(layer)
        title, big, rows, foot = self.content()
        self.card(d, title, rows, foot, c, big=big)
        flatten(im, layer)


class RedCardCost(CardOnly):
    def content(self):
        r = self.data
        team = self.m.get("team_name", r.get("team", ""))
        lost = round((r["win_prob_11v11"] - r["win_prob_11v10"]) * 100)
        return (f"What the red card cost {team}", f"−{lost} pts",
                [("Win chance with 11", f"{round(r['win_prob_11v11'] * 100)}%", WHITE),
                 ("Win chance with 10", f"{round(r['win_prob_11v10'] * 100)}%", YELLOW)],
                f"n = {r['n']}, to full time, seed {r['seed']}")


class River(Still):
    """Win probability across a stretch of the match as a stacked river (home, draw, away) drawn left to right
    over the dimmed frame, with the events marked (goals and red cards labelled, the rest as faint ticks)."""

    needs_camera = False
    LABELLED = ("goal", "red_card")

    def dim(self, t):
        return 0.62 * window(self.tau(t), 0.0, 0.6)

    def ground(self, ax, cam, t):
        r, tau = self.data, self.tau(t)
        grow = window(tau, 0.4, float(self.m.get("draw_s", 4.0)))
        if grow <= 0:
            return
        s = r["series"]
        x = np.array([p["clip_ms"] for p in s], float)
        home, draw = np.array([p["home"] for p in s]), np.array([p["draw"] for p in s])
        x0, x1, y0, y1 = 160, W - 160, 300, 900
        X = x0 + (x - x[0]) / (x[-1] - x[0]) * (x1 - x0)
        cut = X <= x0 + (x1 - x0) * grow
        hk = np.array((self.m.get("kits") or {}).get("home", ORANGE)) / 255
        ak = np.array((self.m.get("kits") or {}).get("away", WHITE)) / 255
        Y = lambda v: y1 - v * (y1 - y0)  # noqa: E731
        ax.fill_between(X[cut], Y(0), Y(home[cut]), color=(*hk, 0.85), lw=0)
        ax.fill_between(X[cut], Y(home[cut]), Y(home[cut] + draw[cut]), color=(0.55, 0.6, 0.66, 0.55), lw=0)
        ax.fill_between(X[cut], Y(home[cut] + draw[cut]), Y(1.0), color=(*ak, 0.85), lw=0)
        for e in r.get("events", []):
            ex = x0 + (e["clip_ms"] - x[0]) / (x[-1] - x[0]) * (x1 - x0)
            if ex <= x0 + (x1 - x0) * grow:
                strong = e.get("kind") in self.LABELLED
                ax.plot([ex, ex], [y0 - 10, y1 + 10], color=(1, 1, 1, 0.9 if strong else 0.35), lw=2 if strong else 1.2,
                        dashes=(3, 3))

    def panels(self, im, cam, t):
        r, tau = self.data, self.tau(t)
        a = window(tau, 0.2, 0.8)
        if a <= 0:
            return
        layer = hi_layer(im.size)
        d = HiDraw(layer)
        al = int(255 * a)
        d.text((160, 200), self.m.get("label", "Win probability").upper(), font=self.font[34], fill=(255, 255, 255, al))
        hk = tuple((self.m.get("kits") or {}).get("home", ORANGE))
        ak = tuple((self.m.get("kits") or {}).get("away", WHITE))
        x = 160
        for label, colour in ((r["home"], hk), ("draw", (140, 153, 168)), (r["away"], ak)):
            d.rectangle((x, 250, x + 22, 272), fill=(*colour, al))
            d.text((x + 32, 261), label, font=self.reg[26], fill=(230, 236, 242, al), anchor="lm")
            x += 32 + d.textlength(label, font=self.reg[26]) + 40
        s = r["series"]
        x, x0, x1 = np.array([p["clip_ms"] for p in s], float), 160, W - 160
        grow = window(tau, 0.4, float(self.m.get("draw_s", 4.0)))
        shown = [e for e in r.get("events", []) if e.get("kind") in self.LABELLED]
        for k, e in enumerate(shown):
            ex = x0 + (e["clip_ms"] - x[0]) / (x[-1] - x[0]) * (x1 - x0)
            if ex <= x0 + (x1 - x0) * grow:
                d.text((ex, 912 + 30 * (k % 2)), f"{e['clock']}  {e['label']}", font=self.font[22],
                       fill=(255, 255, 255, al), anchor="ma")
        d.text((160, 890), s[0]["clock"], font=self.reg[22], fill=(*MUTED, al), anchor="la")
        d.text((W - 160, 890), s[-1]["clock"], font=self.reg[22], fill=(*MUTED, al), anchor="ra")
        d.text((W - 160, 1010), self.m.get("foot") or r.get("engine", ""), font=self.reg[20], fill=(*MUTED, al),
               anchor="ra")
        flatten(im, layer)


class Metrics(CardOnly):
    """The measurement card from real footage only (track A's metrics.json, plus any rows the spec adds with their
    source)."""

    def content(self):
        from demo.v3_data import metrics_rows
        rows = [(label, value, WHITE) for label, value in metrics_rows(self.m["metrics_clip"])]
        rows += [(r["label"], r["value"], WHITE) for r in self.m.get("extra_rows", [])]
        return self.m.get("label", "Measured on this footage"), None, rows, self.m.get("foot", "")

    card_w = 760                                       # long labels


class RiverStrip(Live):
    """The match's win probability as one line in a strip across the lower third of the playing clip: the gap
    between the two teams' win chances (home win minus away win), the home side's colour above the middle and the
    away side's below, drawn left to right while the clip plays; each goal's marker pulses as the line reaches it."""

    needs_camera = False
    BOX = (96, H - 96 - 320, W - 96, H - 96)

    def span(self):
        t0 = float(self.m["t0"])
        return t0, t0 + float(self.m.get("duration_s", 9.0))

    def curve(self) -> tuple[np.ndarray, np.ndarray]:
        from scipy.interpolate import PchipInterpolator
        s = self.data["series"]
        x = np.array([p["clip_ms"] for p in s], float)
        v = np.array([p["home"] - p["away"] for p in s])
        xs = np.linspace(x[0], x[-1], 600)
        return xs, PchipInterpolator(x, v)(xs)          # monotone between samples: no overshoot past the data

    def geometry(self):
        x0, y0, x1, y1 = self.BOX
        top, bottom = y0 + 112, y1 - 24                  # title and the two rows of goal labels sit above
        cx0, cx1, mid, half = x0 + 230, x1 - 40, (top + bottom) / 2, (bottom - top) / 2
        s = self.data["series"]
        X = lambda ms: cx0 + (ms - s[0]["clip_ms"]) / (s[-1]["clip_ms"] - s[0]["clip_ms"]) * (cx1 - cx0)  # noqa: E731
        return X, (lambda v: mid - v * half), cx0, cx1, mid

    def progress(self, t: float) -> float:
        t0 = self.span()[0]
        return window(t - t0, 0.6, 0.6 + float(self.m.get("draw_s", 6.0)))

    def ground(self, ax, cam, t):
        from matplotlib.patches import FancyBboxPatch
        a = window(t - self.span()[0], 0.0, 0.5)
        x0, y0, x1, y1 = self.BOX
        ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0, boxstyle="round,pad=0,rounding_size=12",
                                    fc=(*(np.array(PANEL) / 255), 0.82 * a), ec="none"))
        X, Y, cx0, cx1, mid = self.geometry()
        ax.plot([cx0, cx1], [mid, mid], color=(1, 1, 1, 0.25 * a), lw=1.5)
        p = self.progress(t)
        if p <= 0:
            return
        xs, vs = self.curve()
        cut = xs <= xs[0] + (xs[-1] - xs[0]) * p
        px, py = X(xs[cut]), Y(vs[cut])
        home = np.array((self.m.get("kits") or {}).get("home", ORANGE)) / 255
        away = np.array((self.m.get("kits") or {}).get("away", WHITE)) / 255
        ax.fill_between(px, mid, py, where=vs[cut] >= 0, color=(*home, 0.45), lw=0, interpolate=True)
        ax.fill_between(px, mid, py, where=vs[cut] < 0, color=(*away, 0.45), lw=0, interpolate=True)
        ax.plot(px, py, color=(1, 1, 1, 0.95), lw=3, solid_joinstyle="round")
        ax.scatter([px[-1]], [py[-1]], s=90, color=(1, 1, 1, 1), zorder=5)
        now_ms = xs[cut][-1]
        for e in self.data.get("events", []):
            if e.get("kind") not in River.LABELLED or e["clip_ms"] > now_ms:
                continue
            ex, ey = X(e["clip_ms"]), Y(float(np.interp(e["clip_ms"], xs, vs)))
            since = (now_ms - e["clip_ms"]) / (xs[-1] - xs[0]) * float(self.m.get("draw_s", 6.0))
            pulse = max(0.0, 1 - since / 0.8)
            if e.get("kind") == "red_card":
                col = np.array((230, 30, 40)) / 255
            else:                                        # a goal: the side the line swings towards
                swing = np.interp(e["clip_ms"] + 8000, xs, vs) - np.interp(e["clip_ms"] - 8000, xs, vs)
                col = home if swing > 0 else away
            ax.scatter([ex], [ey], s=140 + 900 * pulse, color=(*col, 0.25 + 0.5 * pulse), lw=0, zorder=4)
            ax.scatter([ex], [ey], s=110, color=(*col, 1.0), edgecolors="white", linewidths=2, zorder=6)

    def panels(self, im, cam, t):
        a = window(t - self.span()[0], 0.0, 0.5)
        layer = hi_layer(im.size)
        d = HiDraw(layer)
        x0, y0, x1, y1 = self.BOX
        al = int(255 * a)
        d.text((x0 + 28, y0 + 18), self.m.get("label", "Who wins it").upper(), font=self.font[26],
               fill=(255, 255, 255, al))
        X, Y, cx0, cx1, mid = self.geometry()
        home = tuple((self.m.get("kits") or {}).get("home", ORANGE))
        away = tuple((self.m.get("kits") or {}).get("away", WHITE))
        d.text((x0 + 28, Y(0.6)), f"{self.data['home']} ahead", font=self.font[22], fill=(*home, al), anchor="lm")
        d.text((x0 + 28, Y(-0.6)), f"{self.data['away']} ahead", font=self.font[22], fill=(*away, al), anchor="lm")
        xs, _ = self.curve()
        now_ms = xs[0] + (xs[-1] - xs[0]) * self.progress(t)
        for k, e in enumerate(e for e in self.data.get("events", []) if e.get("kind") in River.LABELLED):
            if e["clip_ms"] <= now_ms:
                text = f"{e['clock']}  {e['label']}"
                half = d.textlength(text, font=self.font[22]) / 2
                ex = min(max(X(e["clip_ms"]), x0 + 24 + half), x1 - 24 - half)      # inside the strip
                d.text((ex, y0 + 66 + 26 * (k % 2)), text, font=self.font[22], fill=(255, 255, 255, al), anchor="mm")
        d.text((x1 - 24, y0 + 18), self.m.get("foot", ""), font=self.reg[20], fill=(*MUTED, al), anchor="ra")
        flatten(im, layer)


class ShotXG(Live):
    """One real shot for the xG montage (track A's shots_<slug>.json, entry `index` or the one at `clip_ms`): the
    clip runs into the strike, an xG bubble pops on the shooter at the strike, then the outcome stamps (GOAL in the
    team colour, else SAVED / BLOCKED / WIDE). Through the frame's camera when the shot's camera is trusted, else the
    bubble sits beside the score bug."""

    def _calib(self) -> dict:
        shots, m = self.data["shots"], self.m              # the shot first: the camera follows from it
        self.shot = shots[m["index"]] if "index" in m else min(shots, key=lambda s: abs(s["clip_ms"] - m["clip_ms"]))
        self.data = {**self.data, "shot_id": self.shot.get("shot_id")}
        src = (self.shot.get("source") or {}).get("calib")
        if src and (FOOTAGE / src).exists() and self.shot.get("camera_ok"):      # track A's camera for this strike
            return json.loads((FOOTAGE / src).read_text())
        if not self.shot.get("camera_ok"):
            return {}
        try:
            return super()._calib()
        except (FileNotFoundError, StopIteration):
            return {}

    def outcome_after(self) -> float:
        """Seconds from the strike to the outcome stamp: the data's outcome time, else the spec's (read off the
        frames), else 0.6 s."""
        s = self.shot
        if s.get("outcome_clip_ms"):
            return (s["outcome_clip_ms"] - s["clip_ms"]) / 1000
        return float(self.m.get("outcome_after_s", 0.6))

    def ground(self, ax, cam, t):
        """The shot's cone from the strike point to both posts, flashing in at the strike."""
        s = self.shot
        if cam is None or s.get("x") is None:
            return
        tau = t - s["clip_ms"] / 1000
        a = window(tau, -0.1, 0.1) * (1 - window(tau, 1.4, 1.8))
        if a <= 0:
            return
        gx = 105.0 if s["x"] > 52.5 else 0.0
        ball = np.array([s["x"], s["y"]])
        cone = np.vstack([np.linspace(ball, [gx, 30.34], 24), np.linspace([gx, 30.34], [gx, 37.66], 12),
                          np.linspace([gx, 37.66], ball, 24)])
        px = cam.project(cone)
        ax.add_patch(Polygon(px, closed=True, fc=(1, 1, 1, 0.16 * a), ec=(1, 1, 1, 0.7 * a), lw=1.8))

    needs_camera = False

    def span(self):
        s = self.shot
        t = s["clip_ms"] / 1000
        end = t + self.outcome_after() + float(self.m.get("post_s", 0.9))
        return t - float(self.m.get("pre_s", 1.6)), end

    def _fixed_card(self, d, s: dict, tau: float, pop: float) -> None:
        """A shot with no trusted camera: a fixed lower-left card, '0.76 xG · Haaland, penalty', with the outcome put
        in front once it is known ('GOAL · ...')."""
        o = window(tau, self.outcome_after(), self.outcome_after() + 0.12)
        name = (s.get("shooter") or {}).get("name") or self.m.get("shooter_name")   # track B verified
        last = name.split()[-1] if name else None
        what = ", penalty" if (s.get("penalty") or self.m.get("penalty")) and last else ""
        tag = f"{s['xg']:.2f} xG" + (f" · {last}{what}" if last else "")
        if o > 0 and s["outcome"] not in ("no goal", None):
            tag = f"{s['outcome'].upper()} · " + tag
        goal = s["outcome"] == "goal" and o > 0
        colour = tuple(int(v * 255) for v in self.kit) if goal else (196, 204, 214)
        f = self.font[34]
        w = d.textlength(tag, font=f) + 44
        x0, y0 = 96 - int((1 - pop) * 40), H - 96 - 64
        d.rounded_rectangle((x0, y0, x0 + w, y0 + 64), radius=10, fill=(*PANEL, int(235 * pop)))
        d.rectangle((x0, y0, x0 + 8, y0 + 64), fill=(*colour, int(255 * pop)))
        d.text((x0 + 28, y0 + 32), tag, font=f, fill=(255, 255, 255, int(255 * pop)), anchor="lm")

    def panels(self, im, cam, t):
        s = self.shot
        tau = t - s["clip_ms"] / 1000
        if tau < -0.15:
            return
        layer = hi_layer(im.size)
        d = HiDraw(layer)
        pop = window(tau, -0.15, 0.15)
        size = int(34 + 30 * pop)
        if s.get("xg") is None:                           # unmeasured: no number (track A)
            flatten(im, layer)
            return
        v6 = self.m.get("style") == "v6"
        text = f"{s['xg']:.2f} xG" if v6 else f"{s['xg'] * window(tau, 0.0, 0.6):.2f} xG"   # v6: no count-up
        if v6 and not (cam is not None and s.get("camera_ok", True)):   # no trusted camera: never projected, a card
            self._fixed_card(d, s, tau, pop)
            flatten(im, layer)
            return
        if cam is not None and s.get("camera_ok", True):
            at = cam.project([[s["x"], s["y"]]])[0]
            at = at - [0, APPARENT_HEIGHT_M * lateral_px_per_m(cam, [s["x"], s["y"]]) + 70]
        else:
            at = np.array([W / 2, 200.0])
        font = ImageFont.truetype(FONT, size)
        w = d.textlength(text, font=font) + 40
        box = (at[0] - w / 2, at[1] - size / 2 - 14, at[0] + w / 2, at[1] + size / 2 + 14)
        d.rounded_rectangle((box[0] - 6, box[1] - 6, box[2] + 6, box[3] + 6), radius=20, fill=(*ORANGE, int(90 * pop)))
        d.rounded_rectangle(box, radius=16, fill=(*PANEL, int(235 * pop)), outline=(*ORANGE, int(255 * pop)), width=4)
        d.text((at[0], at[1]), text, font=font, fill=(255, 255, 255, int(255 * pop)), anchor="mm")
        name = (s.get("shooter") or {}).get("name") or self.m.get("shooter_name")   # track B verified
        if name:
            d.text((at[0], box[3] + 18), name.upper(), font=self.font[26], fill=(255, 255, 255, int(255 * pop)),
                   anchor="mt", stroke_width=3, stroke_fill=(0, 0, 0, int(200 * pop)))
        out_t = self.outcome_after()
        o = window(tau, out_t, out_t + 0.12)
        if o > 0 and v6:                                  # a small broadcast tag, bottom left
            colour = tuple(int(v * 255) for v in self.kit) if s["outcome"] == "goal" else (196, 204, 214)
            word = "SHOT" if s["outcome"] in ("no goal", None) else s["outcome"].upper()   # track A's "no goal"
            tag = f"{word} · {s['xg']:.2f} xG"
            f = self.font[34]
            w = d.textlength(tag, font=f) + 44
            x0, y0 = 96 - int((1 - o) * 40), H - 96 - 64
            d.rounded_rectangle((x0, y0, x0 + w, y0 + 64), radius=10, fill=(*PANEL, int(235 * o)))
            d.rectangle((x0, y0, x0 + 8, y0 + 64), fill=(*colour, int(255 * o)))
            d.text((x0 + 28, y0 + 32), tag, font=f, fill=(255, 255, 255, int(255 * o)), anchor="lm")
        elif o > 0:
            goal = s["outcome"] == "goal"
            word = "GOAL" if goal else s["outcome"].upper()
            if goal and self.m.get("tag_line", True):
                d.text((W / 2, H / 2 + 80), f"{s['xg']:.2f} xG · scored", font=self.font[50],
                       fill=(255, 255, 255, int(255 * o)), anchor="mm", stroke_width=6, stroke_fill=(0, 0, 0, int(200 * o)))
            col = tuple(int(v * 255) for v in self.kit) if goal else WHITE
            f = ImageFont.truetype(FONT, int(150 if goal else 96))
            scale_in = 1 + 0.25 * (1 - o)
            f = ImageFont.truetype(FONT, int((150 if goal else 96) * scale_in))
            d.text((W / 2, H / 2 - 40), word, font=f, fill=(*col, int(255 * o)), anchor="mm", stroke_width=8,
                   stroke_fill=(0, 0, 0, int(220 * o)))
        flatten(im, layer)


class GhostFuture(Still):
    """The alternative timeline on the real pitch (track A's ghost_future_<clip_ms>.json): over the frozen frame,
    after a rewind tint, translucent ghost players and a ghost ball move along the median rollout for its horizon;
    then the outcome stamps and it hands back to what really happened (the next clip)."""

    def __init__(self, m: dict):
        super().__init__(m)
        d = self.data
        if "frames" not in d and "ball" in d:              # track A's layout: a path per player and for the ball
            step = int(round(1000 / float(d.get("hz", 10))))
            d["frames"] = [{"t_ms": k * step, "ball": d["ball"][k],
                            "players": [{"label": p.get("label") or f"r{p.get('row', i)}", "team": p["team"],
                                         "x": p["path"][k][0], "y": p["path"][k][1]}
                                        for i, p in enumerate(d["players"]) if k < len(p["path"])]}
                           for k in range(len(d["ball"]))]
            d["step_ms"] = step
            d["outcome"] = {"label": "goal", "at_ms": d["goal_ms"]} if d.get("scored") and d.get("goal_ms") else \
                {"label": "no goal in 10 s", "at_ms": len(d["ball"]) * step - 1}
            d["source"] = {"n": d.get("n"), "seed": d.get("seed")}

    def span(self):
        t = self.at_ms() / 1000
        dur = len(self.data["frames"]) * self.data.get("step_ms", 100) / 1000
        return t - float(self.m.get("pre_s", 0.0)), t + 0.6 + dur / float(self.m.get("speed", 1.6)) + 1.2

    def sim_ms(self, t: float) -> float:
        """Rollout time shown at clip time t (played at `speed` x, after a 0.6 s rewind tint)."""
        return max(0.0, (self.tau(t) - 0.6) * 1000 * float(self.m.get("speed", 1.6)))

    def dim(self, t):
        return GHOST_DARKEN * window(self.tau(t), 0.0, 0.5)

    def at(self, ms: float) -> dict:
        fr, step = self.data["frames"], self.data.get("step_ms", 100)
        i = min(int(ms // step), len(fr) - 1)
        j = min(i + 1, len(fr) - 1)
        f = (ms - i * step) / step if j > i else 0.0
        pa, pb = fr[i], fr[j]
        ball = np.array(pa["ball"]) + (np.array(pb["ball"]) - np.array(pa["ball"])) * f
        players = [{**p, "x": p["x"] + (q["x"] - p["x"]) * f, "y": p["y"] + (q["y"] - p["y"]) * f}
                   for p, q in zip(pa["players"], pb["players"], strict=False)]   # by order: labels can repeat
        return {"ball": ball, "players": players}

    def key_labels(self) -> set:
        """The players the story is about (the passer and the receiver): bright; the rest faded."""
        return {x for x in (self.m.get("passer"), self.m.get("receiver")) if x}

    def ground(self, ax, cam, t):
        """Team-coloured ground discs with short motion trails; the passer, the receiver and the ball bright, the
        other players faded to GHOST_DIM; the ball with a glowing trail."""
        if self.tau(t) < 0.6:
            return
        horizon_ms = (len(self.data["frames"]) - 1) * self.data.get("step_ms", 100)
        ms = min(self.sim_ms(t), horizon_ms)
        kits = self.m.get("kits") or {}
        keys = self.key_labels()
        now = self.at(ms)
        past = self.at(max(0.0, ms - GHOST_TRAIL_MS))
        pairs = list(zip(now["players"], past["players"], strict=False))   # same order every frame (labels repeat)
        ball = np.asarray(now["ball"], float)
        near = sorted(range(len(pairs)), key=lambda k: np.hypot(pairs[k][0]["x"] - ball[0], pairs[k][0]["y"] - ball[1]))
        bright = set(near[:GHOST_NEAR]) | {k for k, (p, _) in enumerate(pairs) if p["label"] in keys}
        order = sorted(range(len(pairs)), key=lambda k: k in bright)          # bright players drawn last
        for k in order:
            p, q = pairs[k]
            col = np.array(kits.get(p.get("team", "home"), WHITE)) / 255
            key = k in bright
            a = 1.0 if key else GHOST_DIM
            seg = cam.project(np.linspace([q["x"], q["y"]], [p["x"], p["y"]], 8))
            ax.plot(seg[:, 0], seg[:, 1], color=(*col, 0.55 * a), lw=5 if key else 3, solid_capstyle="round")
            disc = cam.project(ground_circle([p["x"], p["y"]], 1.1 if key else 0.8, 40))
            ax.add_patch(Polygon(disc, closed=True, fc=(*col, 0.95 * a), ec=(1, 1, 1, a), lw=3 if key else 1.2))
        trail = np.array([self.at(x)["ball"] for x in np.arange(max(0, ms - 2000), ms + 1, 100)])
        if len(trail) > 1:
            px = cam.project(trail)
            o = np.array(ORANGE) / 255
            ax.plot(px[:, 0], px[:, 1], color=(*o, 0.30), lw=22, solid_capstyle="round")      # glow
            ax.plot(px[:, 0], px[:, 1], color=(*o, 1.0), lw=6, solid_capstyle="round")

    def panels(self, im, cam, t):
        tau = self.tau(t)
        layer = hi_layer(im.size)
        d = HiDraw(layer)
        if tau < 0.6:
            a = window(tau, 0.0, 0.3)
            d.text((W / 2, 120), "REWIND · THE OTHER TIMELINE", font=self.font[34], fill=(255, 255, 255, int(255 * a)),
                   anchor="mm", stroke_width=4, stroke_fill=(0, 0, 0, int(200 * a)))
            flatten(im, layer)
            return
        horizon_ms = (len(self.data["frames"]) - 1) * self.data.get("step_ms", 100)
        ms = min(self.sim_ms(t), horizon_ms)
        state = self.at(ms)
        kits = self.m.get("kits") or {}
        tags = {self.m.get("receiver"): (self.m.get("receiver_tag"), ORANGE),
                self.m.get("passer"): (self.m.get("passer_tag"), WHITE)}
        for p in state["players"]:
            text, colour = tags.get(p["label"], (None, None))
            if text:
                self.tag(d, cam, [p["x"], p["y"]], text.upper(), colour, font_size=30)
        b = cam.project([state["ball"]])[0]
        for r, al in ((26, 70), (17, 130)):                # a bright ball with a glow
            d.ellipse((b[0] - r, b[1] - r, b[0] + r, b[1] + r), fill=(*ORANGE, al))
        d.ellipse((b[0] - 10, b[1] - 10, b[0] + 10, b[1] + 10), fill=(255, 255, 255, 255), outline=(*ORANGE, 255),
                  width=3)
        d.text((W / 2, 120), f"THE OTHER TIMELINE  +{ms / 1000:.1f} s", font=self.font[34], fill=(255, 255, 255, 235),
               anchor="mm", stroke_width=4, stroke_fill=(0, 0, 0, 200))
        out = dict(self.data.get("outcome") or {})
        if out and out.get("at_ms") is None:            # no goal: the stamp lands when the horizon runs out
            out["at_ms"] = len(self.data["frames"]) * self.data.get("step_ms", 100) - 1
        if out and ms >= out["at_ms"]:
            o = window(ms / 1000, out["at_ms"] / 1000, out["at_ms"] / 1000 + 0.15)
            word = out["label"].upper()
            col = tuple(kits.get(self.m.get("team", "home"), ORANGE)) if out["label"] == "goal" else WHITE
            d.text((W / 2, H / 2 - 60), word, font=ImageFont.truetype(FONT, 140), fill=(*col, int(255 * o)),
                   anchor="mm", stroke_width=8, stroke_fill=(0, 0, 0, int(220 * o)))
        src = {**(self.data.get("source") or {}), **{k: self.data[k] for k in ("n", "seed") if k in self.data}}
        d.text((W - 96, H - 60), f"the most typical of {src.get('n', 0):,} simulated futures, seed {src.get('seed', '?')}",
               font=self.reg[22], fill=(*MUTED, 230), anchor="rb")
        flatten(im, layer)


class XGRace(RiverStrip):
    """Cumulative xG for both teams across a stretch of the match, as two step lines in the lower-third strip
    over the playing clip, goals marked (track A's xg_race_<slug>.json)."""

    def curve(self):
        s = self.data["series"]
        return np.array([p["clip_ms"] for p in s], float), None

    def ground(self, ax, cam, t):
        from matplotlib.patches import FancyBboxPatch
        a = window(t - self.span()[0], 0.0, 0.5)
        x0, y0, x1, y1 = self.BOX
        ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0, boxstyle="round,pad=0,rounding_size=12",
                                    fc=(*(np.array(PANEL) / 255), 0.82 * a), ec="none"))
        s = self.data["series"]
        X = self.geometry()[0]
        top_xg = max(max(p["home_xg"], p["away_xg"]) for p in s) * 1.08 or 1.0
        bottom, top = y1 - 24, y0 + 104
        Y = lambda v: bottom - v / top_xg * (bottom - top)  # noqa: E731
        p = self.progress(t)
        if p <= 0:
            return
        now = s[0]["clip_ms"] + (s[-1]["clip_ms"] - s[0]["clip_ms"]) * p
        for side in ("home", "away"):
            col = np.array((self.m.get("kits") or {}).get(side, ORANGE)) / 255
            pts = [(q["clip_ms"], q[f"{side}_xg"]) for q in s if q["clip_ms"] <= now]
            if not pts:
                continue
            xs = [X(pts[0][0])]
            ys = [Y(pts[0][1])]
            for (_, v_prev), (ms, v) in zip(pts, pts[1:], strict=False):   # a step: xG jumps at each shot
                xs += [X(ms), X(ms)]
                ys += [Y(v_prev), Y(v)]
            xs.append(X(now))
            ys.append(ys[-1])
            ax.plot(xs, ys, color=(*col, 0.25), lw=14, solid_capstyle="round")
            ax.plot(xs, ys, color=(*col, 1.0), lw=4.5, solid_capstyle="round")
        for e in self.data.get("events", []):
            if e.get("kind") == "goal" and e["clip_ms"] <= now:
                side = e.get("team", "home")
                col = np.array((self.m.get("kits") or {}).get(side, ORANGE)) / 255
                v = max((q[f"{side}_xg"] for q in s if q["clip_ms"] <= e["clip_ms"]), default=0)
                ax.scatter([X(e["clip_ms"])], [Y(v)], s=160, color=(*col, 1.0), edgecolors="white", linewidths=2.5,
                           zorder=6)

    def panels(self, im, cam, t):
        a = window(t - self.span()[0], 0.0, 0.5)
        layer = hi_layer(im.size)
        d = HiDraw(layer)
        x0, y0, x1, y1 = self.BOX
        al = int(255 * a)
        d.text((x0 + 28, y0 + 18), self.m.get("label", "Expected goals").upper(), font=self.font[26],
               fill=(255, 255, 255, al))
        s = self.data["series"]
        p = self.progress(t)
        now = s[0]["clip_ms"] + (s[-1]["clip_ms"] - s[0]["clip_ms"]) * p
        cur = [q for q in s if q["clip_ms"] <= now] or s[:1]
        for k, side in enumerate(("home", "away")):
            col = tuple((self.m.get("kits") or {}).get(side, ORANGE))
            d.text((x0 + 28, y0 + 120 + 70 * k), f"{self.data[side]}  {cur[-1][f'{side}_xg']:.2f}", font=self.font[30],
                   fill=(*col, al))
        X = self.geometry()[0]
        shown = [e for e in self.data.get("events", []) if e.get("kind") == "goal" and e["clip_ms"] <= now]
        for k, e in enumerate(shown):
            who = (e.get("label") or self.data.get(e.get("team", "home"), "")).split()[-1]
            text = f"{e['clock']}  {who}"
            half = d.textlength(text, font=self.font[22]) / 2
            ex = min(max(X(e["clip_ms"]), x0 + 24 + half), x1 - 24 - half)
            d.text((ex, y0 + 66 + 26 * (k % 2)), text, font=self.font[22], fill=(255, 255, 255, al), anchor="mm")
        d.text((x1 - 24, y1 - 16), self.m.get("foot", ""), font=self.reg[20], fill=(*MUTED, al), anchor="rb")
        flatten(im, layer)


def _v6_scenes() -> dict:
    from demo.v6 import LiveHUD, Pipeline, ShotMap  # v6 and v7 build on this module's base classes
    from demo.v7 import AlwaysOn
    from demo.v8 import EndCard, Explainer, TitleSting
    from demo.v9 import Architecture, Opener, SeeSplit
    return {"live_hud": LiveHUD, "shot_map": ShotMap, "pipeline": Pipeline, "always_on": AlwaysOn,
            "title_sting": TitleSting, "explainer": Explainer, "end_card": EndCard,
            "opener": Opener, "see_split": SeeSplit, "architecture": Architecture}


SCENES = {"oracle": Oracle, "metrics": Metrics, "river_strip": RiverStrip, "shot_xg": ShotXG,
          "ghost_future": GhostFuture, "xg_race": XGRace, "speed_gun": SpeedGun, "pass_xray": PassXray, "offside": Offside,
          "ghost_defender": GhostDefender, "keeper_cone": KeeperCone, "red_card_cost": RedCardCost, "river": River}
SCENES.update(_v6_scenes())
