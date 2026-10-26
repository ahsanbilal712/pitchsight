"""Video v9 (PITCHSIGHT, production): the opener, the SEE split and the architecture diagram.

The opener is pure motion graphics (no match frame, no logos: the event named in text only). SEE plays the real
broadcast with track A's detection boxes beside a top-down pitch where the same moment's tracked players move in sync.
The architecture diagram builds node by node from the moment's `nodes` (only what track B confirms is in use). All
overlays are drawn at 2x and downsampled (demo.live.HiDraw); nothing on screen is under 24 px.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageFont

from demo.footage import model_lines
from demo.live import FONT, FONT_REG, FPS, ROOT, H, HiDraw, Live, W, bracket, flatten, hi_layer, window
from demo.v6 import ACCENT, RADIUS, ease_in_out, shrink

INK = (10, 13, 18)
LINE_GREEN = (64, 214, 130)
MUTED = (176, 186, 198)


def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT if bold else FONT_REG, max(24, size))


def _encode(frames, path: Path, n: int) -> Path:
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt",
                            "yuv420p", "-movflags", "+faststart", str(path)], stdin=subprocess.PIPE)
    for i in range(n):
        enc.stdin.write(np.asarray(frames(i / FPS).convert("RGB")).tobytes())
    enc.stdin.close()
    if enc.wait():
        raise RuntimeError("ffmpeg encode failed")
    return path


class Opener:
    """0-8 s, motion graphics only: on black, green line-art pitch markings draw on with small square nodes at their
    ends; the event in text ("Inside the Game: Developer Hackathon", "Premier League × Microsoft"); then the wordmark
    and the tagline resolve."""

    camera_note = ""

    def __init__(self, m: dict):
        self.m = m
        s, x0, y0 = 13.0, (W - 105 * 13.0) / 2, (H - 68 * 13.0) / 2
        self.lines = [np.c_[x0 + p[:, 0] * s, y0 + (68 - p[:, 1]) * s] for _, p in sorted(model_lines().items())]

    def render(self, t: float) -> Image.Image:
        im = Image.new("RGB", (W, H), INK)
        layer = hi_layer((W, H))
        d = HiDraw(layer)
        fade = 1 - 0.75 * window(t, 2.4, 3.0) - 0.25 * window(t, 4.6, 5.2)
        for k, q in enumerate(self.lines):                 # the markings draw on, staggered, then sink back
            p = ease_in_out(window(t, 0.15 + 0.07 * k, 1.3 + 0.07 * k))
            if p <= 0:
                continue
            n = max(2, int(len(q) * p))
            pts = [tuple(v) for v in q[:n]]
            d.line(pts, fill=(*LINE_GREEN, int(70 * fade)), width=7)
            d.line(pts, fill=(*LINE_GREEN, int(255 * fade)), width=2)
            for v in (q[0], q[n - 1]):                     # square nodes at each end
                a = int(255 * fade * window(t, 0.2 + 0.07 * k, 0.4 + 0.07 * k))
                d.rectangle((v[0] - 5, v[1] - 5, v[0] + 5, v[1] + 5), fill=(*INK, a), outline=(*LINE_GREEN, a), width=2)
        e = window(t, 2.6, 3.1) * (1 - window(t, 4.5, 4.9))
        if e > 0:
            d.text((W / 2, H / 2 - 30), self.m["event"], font=font(64), fill=(255, 255, 255, int(255 * e)), anchor="mm")
            d.text((W / 2, H / 2 + 50), self.m["event_sub"], font=font(36, bold=False), fill=(*MUTED, int(255 * e)),
                   anchor="mm")
        w = window(t, 5.0, 5.35)
        if w > 0:
            s = 1 + 0.05 * (1 - ease_in_out(window(t, 5.0, 5.6)))
            f = ImageFont.truetype(FONT, int(170 * s))
            d.text((W / 2, H / 2 - 40), "PITCHSIGHT", font=f, fill=(255, 255, 255, int(255 * w)), anchor="mm")
            wl = d.textlength("PITCHSIGHT", font=f) * ease_in_out(window(t, 5.3, 6.0))
            d.rounded_rectangle((W / 2 - wl / 2, H / 2 + 62, W / 2 + wl / 2, H / 2 + 70), radius=4,
                                fill=(*ACCENT, int(255 * w)))
            b = window(t, 5.8, 6.3)
            d.text((W / 2, H / 2 + 128), self.m["tagline"], font=font(48, bold=False),
                   fill=(230, 236, 242, int(255 * b)), anchor="mm")
        flatten(im, layer)
        return im

    def export(self, path: Path) -> Path:
        return _encode(self.render, path, int(round(float(self.m["duration"]) * FPS)))


class SeeSplit(Live):
    """SEE: the real broadcast on the left with track A's boxes on every detected player (team colours), a top-down
    pitch on the right with the same moment's tracked players (cache/v6 live frames) moving in sync."""

    needs_camera = False
    LEFT = (40, 250, 1100)                       # the broadcast: left, top, width (16:9)
    PITCH = (1190, 250, 690)                     # the pitch: left, top, width (105 x 68)

    def __init__(self, m: dict):
        super().__init__(m)
        tr = json.loads((ROOT / m["tracks"]).read_text())
        self.trk = tr.get("result", tr)["frames"]
        self.trk_t = np.array([f["t"] for f in self.trk])
        side = {}
        for f in self.data["frames"]:
            for p in f.get("players") or []:
                if p.get("team") in ("home", "away"):
                    side[p["track_id"]] = p["team"]
        self.side = side

    def span(self):
        return float(self.m["t0"]), float(self.m["t1"])

    def frame(self, img, t, ax, canvas, cam_t=None):
        im = Image.new("RGB", (W, H), INK)
        lx, ly, lw = self.LEFT
        lh = lw * 9 // 16
        im.paste(Image.fromarray(img).resize((lw, lh), Image.LANCZOS), (lx, ly))
        layer = hi_layer((W, H))
        d = HiDraw(layer)
        kits = {k: tuple(v) for k, v in (self.m.get("kits") or {}).items()}
        sc = lw / W
        j = int(np.clip(np.searchsorted(self.trk_t, t), 1, len(self.trk) - 1))
        f = self.trk[j] if abs(self.trk_t[j] - t) < abs(self.trk_t[j - 1] - t) else self.trk[j - 1]
        for p in f.get("players") or []:                   # track A's boxes, scaled onto the broadcast
            if p.get("role") == "referee":
                continue
            x0, y0, x1, y1 = p["bbox"]
            col = kits.get(self.side.get(p.get("track_id")), (214, 220, 228))
            d.rounded_rectangle((lx + x0 * sc, ly + y0 * sc, lx + x1 * sc, ly + y1 * sc), radius=4, outline=(*col, 230),
                                width=1.5)
        px, py, pw = self.PITCH
        s = pw / 105
        ph = 68 * s
        d.rounded_rectangle((px - 12, py - 12, px + pw + 12, py + ph + 12), radius=RADIUS, fill=(22, 52, 36, 255))
        for _, q in model_lines().items():
            pts = [(px + x * s, py + (68 - y) * s) for x, y in q]
            for a_, b_ in zip(pts[:-1], pts[1:], strict=True):
                if abs(a_[0] - b_[0]) + abs(a_[1] - b_[1]) < 6 * s:
                    d.line([a_, b_], fill=(225, 235, 228, 255), width=1.5)
        x = self.data["frames"]
        i, _, _ = bracket(x, t * 1000)
        for p in x[i].get("players") or []:                # the same moment, top-down
            if p.get("team") not in ("home", "away"):
                continue
            cx, cy = px + p["x"] * s, py + (68 - p["y"]) * s
            col = kits.get(p["team"], (255, 255, 255))
            d.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill=(*col, 255), outline=(255, 255, 255, 230), width=1.5)
        b = x[i].get("ball")
        if b and b.get("x") is not None:
            cx, cy = px + b["x"] * s, py + (68 - b["y"]) * s
            d.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill=(255, 255, 255, 255), outline=(0, 0, 0, 200), width=1)
        d.text((lx, ly - 30), "BROADCAST · EVERY PLAYER DETECTED", font=font(28), fill=(*MUTED, 255), anchor="ls")
        d.text((px, ly - 30), "TOP-DOWN · TRACKED IN METRES", font=font(28), fill=(*MUTED, 255), anchor="ls")
        flatten(im, layer)
        return im


class Architecture:
    """How it works, one diagram that builds over about 12 s and holds: the perception chain on the top row, the
    models and the newsroom below, ending on air. Node texts come from the moment (track B confirms them)."""

    camera_note = ""

    def __init__(self, m: dict):
        self.m = m

    def _node(self, d, box, title, sub, a, lit):
        x0, y0, x1, y1 = box
        col = ACCENT if lit else (90, 100, 112)
        d.rounded_rectangle(box, radius=RADIUS, fill=(24, 29, 37, int(255 * a)), outline=(*col, int(255 * a)), width=2)
        d.text((x0 + 24, y0 + 22), title, font=shrink(d, title, FONT, 36, x1 - x0 - 48, floor=28),
               fill=(255, 255, 255, int(255 * a)))
        f = font(28, bold=False)
        yy = y0 + 76
        for ln in sub:
            d.text((x0 + 24, yy), ln, font=f, fill=(*MUTED, int(255 * a)))
            yy += 38

    def render(self, t: float) -> Image.Image:
        im = Image.new("RGB", (W, H), INK)
        layer = hi_layer((W, H))
        d = HiDraw(layer)
        d.text((64, 96), "HOW IT WORKS", font=font(44), fill=(255, 255, 255, 255), anchor="ls")
        top, bottom = self.m["top"], self.m["bottom"]
        gap = 28
        w_top = (W - 128 - gap * (len(top) - 1)) / len(top)
        boxes = []
        for k, n in enumerate(top):
            x0 = 64 + k * (w_top + gap)
            boxes.append(((x0, 170, x0 + w_top, 170 + 220), n))
        widths = [float(n.get("w", 1)) for n in bottom]
        unit = (W - 128 - gap * (len(bottom) - 1)) / sum(widths)
        x0 = 64
        for n, wf in zip(bottom, widths, strict=True):
            boxes.append(((x0, 540, x0 + unit * wf, 540 + 300), n))
            x0 += unit * wf + gap
        step = float(self.m.get("step_s", 1.3))
        for k, (box, n) in enumerate(boxes):
            on = window(t, 0.5 + step * k, 0.9 + step * k)
            if on <= 0:
                continue
            lit = 0.5 + step * k <= t < 0.5 + step * (k + 1)
            if k:                                           # the arrow from the node before draws on
                (ax0, ay0, ax1, ay1), _ = boxes[k - 1]
                bx0, by0, bx1, by1 = box
                p = ease_in_out(window(t, 0.2 + step * k, 0.6 + step * k))
                if by0 == ay0:                              # same row: left to right
                    path = [((ax1, (ay0 + ay1) / 2)), (bx0, (by0 + by1) / 2)]
                else:                                       # down to the second row: an elbow, never a diagonal
                    mid = (ay1 + by0) / 2
                    path = [((ax0 + ax1) / 2, ay1), ((ax0 + ax1) / 2, mid), ((bx0 + bx1) / 2, mid),
                            ((bx0 + bx1) / 2, by0)]
                seg = np.array(path, float)
                lens = np.hypot(*np.diff(seg, axis=0).T)
                run = p * lens.sum()
                drawn = [tuple(seg[0])]
                for a_, b_, ln in zip(seg[:-1], seg[1:], lens, strict=True):
                    if run <= 0:
                        break
                    f_ = min(1.0, run / ln)
                    drawn.append(tuple(a_ + (b_ - a_) * f_))
                    run -= ln
                d.line(drawn, fill=(*ACCENT, 255), width=3)
                sx, sy = seg[-2]
                ex, ey = seg[-1]
                if p >= 1:
                    v = np.array([ex - sx, ey - sy], float)
                    v /= np.linalg.norm(v) or 1
                    nrm = np.array([-v[1], v[0]])
                    tip = np.array([ex, ey])
                    d.polygon([tuple(tip), tuple(tip - 14 * v + 7 * nrm), tuple(tip - 14 * v - 7 * nrm)],
                              fill=(*ACCENT, 255))
            self._node(d, box, n["title"], n.get("sub", []), on, lit)
        flatten(im, layer)
        return im

    def export(self, path: Path) -> Path:
        return _encode(self.render, path, int(round(float(self.m["duration"]) * FPS)))
