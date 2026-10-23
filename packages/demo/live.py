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
import numpy as np  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from demo.footage import PITCH_W, Camera, from_pitchwatch  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FOOTAGE = ROOT / "data" / "footage"
W, H, FPS = 1920, 1080, 30
FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_REG = "/System/Library/Fonts/Supplemental/Arial.ttf"
ORANGE, WHITE, YELLOW, PANEL, MUTED = (255, 122, 26), (236, 242, 248), (255, 214, 10), (12, 16, 22), (169, 180, 194)
PANEL_W = 540
APPARENT_HEIGHT_M = 1.42          # demo.composite: a player's height in the picture over the grass scale across it


def ease(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return 1 - (1 - t) ** 3


def window(t: float, a: float, b: float) -> float:
    return ease((t - a) / (b - a)) if b > a else float(t >= a)


def ground_circle(c, r: float, n: int = 64) -> np.ndarray:
    t = np.linspace(0, 2 * np.pi, n)
    return np.c_[c[0] + r * np.cos(t), c[1] + r * np.sin(t)]


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
        self.calib = self._calib()
        self.fps_clip = float(self.calib.get("fps", 50.0))

    # -- time and camera -------------------------------------------------------------------------------------
    def span(self) -> tuple[float, float]:
        raise NotImplementedError

    def _calib(self) -> dict:
        shot = self.m.get("shot_id") or self.data.get("shot_id")
        if shot is None:
            shots = json.loads((FOOTAGE / self.m["clip"] / "shots.json").read_text())["shots"]
            t0 = self.span()[0]
            shot = next(s["id"] for s in shots if s.get("usable") and s["start"] <= t0 <= s["end"])
        d = FOOTAGE / self.m["clip"] / "calib"
        path = next(p for p in (d / f"{shot}_refined.json", d / f"{shot}.json") if p.exists())
        return json.loads(path.read_text())

    def camera(self, t: float) -> Camera:
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
        box = (feet[0] - w / 2, y - font_size - 16, feet[0] + w / 2, y)
        if glow:
            d.rounded_rectangle((box[0] - 4, box[1] - 4, box[2] + 4, box[3] + 4), radius=12,
                                fill=(*colour, int(90 * a)))
        d.rounded_rectangle(box, radius=8, fill=(*PANEL, int(220 * a)), outline=(*colour, int(255 * a)), width=3)
        d.text(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2), text, font=font, fill=(*colour, int(255 * a)),
               anchor="mm")

    def card(self, d: ImageDraw.ImageDraw, title: str, rows: list[tuple[str, str, tuple]], foot: str, a: float,
             accent=None, big: str | None = None) -> None:
        """Bottom-left card: a title, an optional big number, label/value rows, a provenance line."""
        h = 64 + (80 if big else 0) + 42 * len(rows) + 34
        x0, y0 = 96 - int((1 - a) * 40), H - 96 - h
        al = int(255 * a)
        accent = accent or tuple(int(v) for v in self.kit * 255)
        d.rounded_rectangle((x0, y0, x0 + PANEL_W, y0 + h), radius=10, fill=(*PANEL, int(232 * a)))
        d.rectangle((x0, y0, x0 + 8, y0 + h), fill=(*accent, al))
        d.text((x0 + 32, y0 + 20), title.upper(), font=self.font[22], fill=(*MUTED, al))
        y = y0 + 54
        if big:
            d.text((x0 + 32, y), big, font=self.font[64], fill=(255, 255, 255, al))
            y += 80
        for label, value, colour in rows:
            d.text((x0 + 32, y + 4), label, font=self.reg[22], fill=(230, 236, 242, al))
            d.text((x0 + PANEL_W - 28, y + 16), value, font=self.font[30], fill=(*colour, al), anchor="rm")
            y += 42
        d.text((x0 + PANEL_W - 28, y0 + h - 14), foot, font=self.reg[20], fill=(*MUTED, al), anchor="rb")

    # -- export ----------------------------------------------------------------------------------------------
    def export(self, path: Path) -> Path:
        t0, t1 = self.span()
        src = FOOTAGE / self.m["clip"] / "clip.mp4"
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-i", str(src), "-t", f"{t1 - t0:.3f}",
                              "-vf", f"fps={FPS}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True, check=True).stdout
        frames = np.frombuffer(raw, np.uint8).reshape(-1, H, W, 3)
        fig = Figure(figsize=(W / 100, H / 100), dpi=100)
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
        fig = Figure(figsize=(W / 100, H / 100), dpi=100)
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
        self.ground(ax, cam, t)
        canvas.draw()
        g = np.asarray(canvas.buffer_rgba(), float) / 255
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
        bar, value, _ = self.at(t)
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        x0, h = 96 - int((1 - a) * 40), 196
        y0, al = H - 96 - h, int(255 * a)
        kit = tuple(int(v) for v in self.kit * 255)
        d.rounded_rectangle((x0, y0, x0 + PANEL_W, y0 + h), radius=10, fill=(*PANEL, int(232 * a)))
        d.rectangle((x0, y0, x0 + 8, y0 + h), fill=(*kit, al))
        d.text((x0 + 32, y0 + 20), self.m.get("label", "Shot in the next 10 s").upper(), font=self.font[22],
               fill=(*MUTED, al))
        d.text((x0 + 32, y0 + 50), f"{round(value * 100)}%", font=self.font[64], fill=(255, 255, 255, al))
        bx0, bx1, by = x0 + 32, x0 + PANEL_W - 28, y0 + 132
        d.rounded_rectangle((bx0, by, bx1, by + 12), radius=6, fill=(255, 255, 255, int(28 * a)))
        d.rounded_rectangle((bx0, by, bx0 + max(12, (bx1 - bx0) * bar), by + 12), radius=6, fill=(*kit, al))
        d.text((x0 + PANEL_W - 28, y0 + h - 16),
               f"n = {self.data['n']} per 0.5 s, {self.data['horizon_s']:g} s, seed {self.data['seed']}",
               font=self.reg[20], fill=(*MUTED, al), anchor="rb")
        im.paste(layer, (0, 0), layer)


class SpeedGun(Live):
    """A player's run: a trail of where he has been, a ring and a live km/h tag on him, and at the end a card with
    his top speed and the distance (track A's tracking; every printed speed is a tracking sample)."""

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
        if now < start:
            return
        pts = np.array([[p["x"], p["y"]] for p in s if max(start, now - self.TRAIL_S * 1000) <= p["clip_ms"] <= now]
                       + [self.pos(now / 1000).tolist()])
        if len(pts) > 1:
            px = cam.project(pts)
            n = len(px)
            for k in range(n - 1):                               # fades toward the tail
                a = 0.15 + 0.85 * (k + 1) / n
                ax.plot(px[k:k + 2, 0], px[k:k + 2, 1], color=(0, 0, 0, 0.45 * a), lw=10, solid_capstyle="round")
                ax.plot(px[k:k + 2, 0], px[k:k + 2, 1], color=(*self.kit, a), lw=5.5, solid_capstyle="round")
        ring = cam.project(ground_circle(self.pos(now / 1000), 1.0))
        ax.plot(ring[:, 0], ring[:, 1], color=(0, 0, 0, 0.5), lw=7)
        ax.plot(ring[:, 0], ring[:, 1], color=(*self.kit, 1.0), lw=3.5)

    def panels(self, im, cam, t):
        start, end = self.data["start_clip_ms"], self.data["end_clip_ms"]
        if t * 1000 < start:
            return
        s = self.data["samples"]
        now = min(t * 1000, end)
        i, _, _ = bracket(s, now)
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        p = self.data["player"]
        kit = tuple(int(v) for v in self.kit * 255)
        self.tag(d, cam, self.pos(now / 1000), f"{p.get('name', p['label']).split()[-1].upper()}  "
                                               f"{s[i]['speed_kmh']:.1f} km/h", kit, font_size=30)
        a = window(t, end / 1000, end / 1000 + 0.5)
        if a > 0:
            self.card(d, f"{p.get('name', p['label'])}: the run",
                      [("Top speed", f"{self.data['top_speed_kmh']:.1f} km/h", WHITE),
                       ("Distance", f"{round(self.data['distance_m'])} m", WHITE)],
                      self.data.get("error_note", "from broadcast tracking"), a)
        im.paste(layer, (0, 0), layer)


class PassXray(Live):
    """Every teammate tagged with his goal chance if the holder passed to him now, ranked; the best one glows and
    the line to him is drawn bright (track B's samples every 0.5 s; tags print the latest sample's values)."""

    def span(self):
        s = self.data["samples"]
        return s[0]["clip_ms"] / 1000 - float(self.m.get("pre_s", 0.5)), s[-1]["clip_ms"] / 1000 + 0.5

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
        best = max(cur["options"], key=lambda o: o["p_goal"])["label"] if cur["options"] else None
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
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for rank, o in enumerate(ranked):
            name = (o.get("name") or o["label"]).split()[-1]
            self.tag(d, cam, place[o["label"]], f"{rank + 1}  {name}  {round(o['p_goal'] * 100)}%",
                     ORANGE if rank == 0 else WHITE, font_size=26 if rank else 30, glow=rank == 0)
        a = window(t, s[0]["clip_ms"] / 1000, s[0]["clip_ms"] / 1000 + 0.5)
        self.card(d, self.m.get("label", "Pass X-ray: goal chance if passed to"),
                  [(f"{k + 1}. {o.get('name') or o['label']}", f"{round(o['p_goal'] * 100)}%",
                    ORANGE if k == 0 else WHITE) for k, o in enumerate(ranked[:3])],
                  f"n = {self.data['n']}, {self.data['horizon_s']:g} s, seed {self.data['seed']}", a)
        im.paste(layer, (0, 0), layer)


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
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        gap = self.data["gap_m"]
        verdict = "Offside" if gap > 0 else "Onside"
        self.card(d, "Offside line at the pass", [(verdict + " by", f"{abs(gap):.1f} m", YELLOW),
                                                  ("Uncertainty", f"± {self.data['uncertainty_m']:.1f} m", WHITE)],
                  "from broadcast tracking", a, accent=YELLOW)
        im.paste(layer, (0, 0), layer)


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
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        kit = tuple(int(v) for v in self.kit * 255)
        name = r["defender"].get("name", r["defender"]["label"])
        self.tag(d, cam, [r["defender"]["x"], r["defender"]["y"]], name.split()[-1].upper(), WHITE)
        g = window(tau, 1.2, 1.8)
        if g > 0:
            ghost_figure(d, cam, [r["ghost"]["x"], r["ghost"]["y"]], kit, g)
            mid = (np.array([r["defender"]["x"], r["defender"]["y"]]) + [r["ghost"]["x"], r["ghost"]["y"]]) / 2
            px = cam.project([mid])[0]
            d.text((px[0], px[1] + 26), f"{r['metres_needed']:.1f} m", font=self.font[30],
                   fill=(*YELLOW, int(255 * g)), anchor="mm", stroke_width=3, stroke_fill=(0, 0, 0, int(200 * g)))
        c = window(tau, 2.0, 2.5)
        if c > 0:
            self.card(d, self.m.get("label", f"If {name} had been there"),
                      [("Goal chance, as it was", f"{round(r['p_goal_actual'] * 100)}%", WHITE),
                       (f"With {name.split()[-1]} {r['metres_needed']:.1f} m across",
                        f"{round(r['p_goal_ghost'] * 100)}%", YELLOW)],
                      f"n = {r['n']}, {r['horizon_s']:g} s, seed {r['seed']}", c, accent=kit)
        im.paste(layer, (0, 0), layer)


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
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        kit = tuple(int(v) for v in self.kit * 255)
        name = r["keeper"].get("name", "Keeper")
        self.tag(d, cam, [r["keeper"]["x"], r["keeper"]["y"]], name.split()[-1].upper(), WHITE)
        b = window(tau, 1.2, 1.8)
        if b > 0:
            ghost_figure(d, cam, [r["best"]["x"], r["best"]["y"]], kit, b)
        c = window(tau, 2.0, 2.5)
        if c > 0:
            gap = float(np.hypot(r["best"]["x"] - r["keeper"]["x"], r["best"]["y"] - r["keeper"]["y"]))
            self.card(d, self.m.get("label", f"{name}: where to stand"),
                      [("Save chance where he stood", f"{round(r['save_actual'] * 100)}%", WHITE),
                       (f"From the best spot, {gap:.1f} m away", f"{round(r['save_best'] * 100)}%", YELLOW)],
                      f"n = {r['n']}, seed {r['seed']}", c, accent=kit)
        im.paste(layer, (0, 0), layer)


class CardOnly(Still):
    """A card over the frozen, dimmed picture: the red-card cost (11 v 11 against 11 v 10) or the measurement card.
    `rows` are built from the data by the subclass."""

    def dim(self, t):
        return 0.35 * window(self.tau(t), 0.0, 0.6)

    def content(self) -> tuple[str, str | None, list[tuple[str, str, tuple]], str]:
        raise NotImplementedError

    def panels(self, im, cam, t):
        c = window(self.tau(t), 0.3, 0.9)
        if c <= 0:
            return
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        title, big, rows, foot = self.content()
        self.card(d, title, rows, foot, c, big=big)
        im.paste(layer, (0, 0), layer)


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
    over the dimmed frame, with the events marked."""

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
                ax.plot([ex, ex], [y0 - 10, y1 + 10], color=(1, 1, 1, 0.9), lw=2, dashes=(3, 3))

    def panels(self, im, cam, t):
        r, tau = self.data, self.tau(t)
        a = window(tau, 0.2, 0.8)
        if a <= 0:
            return
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        al = int(255 * a)
        d.text((160, 200), self.m.get("label", "Win probability").upper(), font=self.font[34], fill=(255, 255, 255, al))
        d.text((160, 244), f"{r['home']} · draw · {r['away']}", font=self.reg[26], fill=(*MUTED, al))
        s = r["series"]
        x, x0, x1 = np.array([p["clip_ms"] for p in s], float), 160, W - 160
        grow = window(tau, 0.4, float(self.m.get("draw_s", 4.0)))
        for e in r.get("events", []):
            ex = x0 + (e["clip_ms"] - x[0]) / (x[-1] - x[0]) * (x1 - x0)
            if ex <= x0 + (x1 - x0) * grow:
                d.text((ex, 910), f"{e['clock']} {e['label']}", font=self.font[22], fill=(255, 255, 255, al),
                       anchor="ma")
        d.text((160, 890), s[0]["clock"], font=self.reg[22], fill=(*MUTED, al), anchor="la")
        d.text((W - 160, 890), s[-1]["clock"], font=self.reg[22], fill=(*MUTED, al), anchor="ra")
        d.text((W - 160, 960), f"{r.get('engine', '')}, n = {r.get('n', '')} per point", font=self.reg[20],
               fill=(*MUTED, al), anchor="ra")
        im.paste(layer, (0, 0), layer)


SCENES = {"oracle": Oracle, "speed_gun": SpeedGun, "pass_xray": PassXray, "offside": Offside,
          "ghost_defender": GhostDefender, "keeper_cone": KeeperCone, "red_card_cost": RedCardCost, "river": River}
