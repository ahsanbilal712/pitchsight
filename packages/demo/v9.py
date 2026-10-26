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
        fade = 1 - 0.75 * window(t, 1.6, 2.2) - 0.25 * window(t, 4.6, 5.2)
        for k, q in enumerate(self.lines):                 # the markings draw on, staggered, then sink back
            p = ease_in_out(window(t, 0.1 + 0.05 * k, 1.0 + 0.05 * k))
            if p <= 0:
                continue
            n = max(2, int(len(q) * p))
            pts = [tuple(v) for v in q[:n]]
            d.line(pts, fill=(*LINE_GREEN, int(70 * fade)), width=7)
            d.line(pts, fill=(*LINE_GREEN, int(255 * fade)), width=2)
            for v in (q[0], q[n - 1]):                     # square nodes at each end
                a = int(255 * fade * window(t, 0.15 + 0.05 * k, 0.35 + 0.05 * k))
                d.rectangle((v[0] - 5, v[1] - 5, v[0] + 5, v[1] + 5), fill=(*INK, a), outline=(*LINE_GREEN, a), width=2)
        e = window(t, 0.6, 1.1) * (1 - window(t, 4.8, 5.2))     # under "Built for Inside the Game ..."
        if e > 0:
            d.text((W / 2, H / 2 - 30), self.m["event"], font=font(64), fill=(255, 255, 255, int(255 * e)), anchor="mm")
            d.text((W / 2, H / 2 + 50), self.m["event_sub"], font=font(36, bold=False), fill=(*MUTED, int(255 * e)),
                   anchor="mm")
        w = window(t, 5.35, 5.65)                       # "This is Pitchsight" at 5.56 s
        if w > 0:
            s = 1 + 0.05 * (1 - ease_in_out(window(t, 5.35, 5.9)))
            f = ImageFont.truetype(FONT, int(170 * s))
            d.text((W / 2, H / 2 - 40), "PITCHSIGHT", font=f, fill=(255, 255, 255, int(255 * w)), anchor="mm")
            wl = d.textlength("PITCHSIGHT", font=f) * ease_in_out(window(t, 5.6, 6.3))
            d.rounded_rectangle((W / 2 - wl / 2, H / 2 + 62, W / 2 + wl / 2, H / 2 + 70), radius=4,
                                fill=(*ACCENT, int(255 * w)))
            b = window(t, 6.0, 6.5)
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
        w = json.loads((ROOT / m["window"]).read_text())           # track A v9: boxes every frame, team held
        self.trk = w.get("result", w)["frames"]
        self.trk_t = np.array([f["clip_ms"] / 1000 for f in self.trk])
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
        for p in f.get("boxes") or []:                     # track A's boxes, scaled onto the broadcast
            if p.get("team") == "referee":
                continue
            x0, y0, x1, y1 = p["bbox"]
            col = kits.get(p.get("team"), (158, 168, 184))
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
        d.text((lx, ly - 30), "BROADCAST · PLAYERS IN VIEW, DETECTED", font=font(28), fill=(*MUTED, 255), anchor="ls")
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
        d.text((x0 + 26, y0 + 26), title, font=shrink(d, title, FONT, 42, x1 - x0 - 52, floor=30),
               fill=(255, 255, 255, int(255 * a)))
        yy = y0 + 90
        for ln in sub:
            d.text((x0 + 26, yy), ln, font=shrink(d, ln, FONT_REG, 32, x1 - x0 - 52, floor=26),
                   fill=(*MUTED, int(255 * a)))
            yy += 44

    def render(self, t: float) -> Image.Image:
        im = Image.new("RGB", (W, H), INK)
        layer = hi_layer((W, H))
        d = HiDraw(layer)
        d.text((64, 120), "HOW IT WORKS", font=font(48), fill=(255, 255, 255, 255), anchor="ls")
        top, bottom = self.m["top"], self.m["bottom"]
        gap = 28
        w_top = (W - 128 - gap * (len(top) - 1)) / len(top)
        boxes = []
        for k, n in enumerate(top):
            x0 = 64 + k * (w_top + gap)
            boxes.append(((x0, 200, x0 + w_top, 200 + 270), n))
        widths = [float(n.get("w", 1)) for n in bottom]
        unit = (W - 128 - gap * (len(bottom) - 1)) / sum(widths)
        x0 = 64
        for n, wf in zip(bottom, widths, strict=True):
            boxes.append(((x0, 590, x0 + unit * wf, 590 + 360), n))
            x0 += unit * wf + gap
        step = float(self.m.get("step_s", 1.3))
        reveal = self.m.get("reveal") or [0.5 + step * k for k in range(len(boxes))]   # under the narration
        for k, (box, n) in enumerate(boxes):
            t_on = float(reveal[k])
            on = window(t, t_on, t_on + 0.4)
            if on <= 0:
                continue
            nxt = float(reveal[k + 1]) if k + 1 < len(reveal) else 1e9
            lit = t_on <= t < nxt
            if k:                                           # the arrow from the node before draws on
                (ax0, ay0, ax1, ay1), _ = boxes[k - 1]
                bx0, by0, bx1, by1 = box
                p = ease_in_out(window(t, t_on - 0.3, t_on + 0.1))
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


class DecisionFreeze(Live):
    """The decision gap, held on the real frame (track A decision_gap_0's pick): the shot cone from the carrier to
    the posts against the cutback to the runner, both priced; track A's boxes; a card in the right stack. Neutral
    wording: the published xG model sees distance and angle only, so the card never says the player chose wrongly."""

    def __init__(self, m: dict):
        super().__init__(m)
        doc = json.loads((ROOT / m["decision"]).read_text())
        doc = doc.get("result", doc)
        if m.get("pick_key"):                              # e.g. "eze": {best_option, shot_xg, ...}
            r = doc[m["pick_key"]]
            self.pick = {**r["best_option"], "shot_xg": r["shot_xg"]}
        else:
            self.pick = next(p for p in doc["passages_top"] if p["clip_ms"] == int(m["clip_ms"]))
        if not self.pick.get("receiver_xy"):               # the receiver's spot at that sample (live frame)
            fr = min(self.data["frames"], key=lambda f: abs(f["clip_ms"] - int(self.pick["clip_ms"])))
            o = next(o for o in fr["options"] if o.get("track_id") == self.pick["receiver_track"])
            self.pick["receiver_xy"] = [o["x"], o["y"]]
        w = json.loads((ROOT / m["window"]).read_text())
        self.win = w.get("result", w)

    def span(self):
        t = int(self.m["clip_ms"]) / 1000
        return t, t + float(self.m.get("hold_s", 6.0))

    def freeze_at(self):
        return int(self.m["clip_ms"]) / 1000

    def dim(self, t):
        return 0.25 * window(t - self.freeze_at(), 0.0, 0.4)

    def _carrier(self) -> dict | None:
        x = self.data["frames"]
        i, _, _ = bracket(x, int(self.m["clip_ms"]))
        return x[i].get("holder")

    def ground(self, ax, cam, t):
        tau = t - self.freeze_at()
        car = self._carrier()
        if car is None:
            return
        c = np.array([car["x"], car["y"]])
        goal_x = 0.0 if self.pick["receiver_xy"][0] < 52.5 else 105.0
        a = window(tau, 0.2, 0.6)
        tri = np.array([c, [goal_x, 34 - 3.66], [goal_x, 34 + 3.66], c])
        poly = cam.project(np.vstack([np.linspace(tri[i], tri[i + 1], 16) for i in range(3)]))
        ax.fill(poly[:, 0], poly[:, 1], color=(1, 1, 1, 0.16 * a), lw=0)
        ax.plot(poly[:, 0], poly[:, 1], color=(1, 1, 1, 0.9 * a), lw=1.8)
        b = ease_in_out(window(tau, 0.8, 1.5))             # then the cutback draws on
        if b > 0:
            r = np.array(self.pick["receiver_xy"])
            seg = cam.project(np.linspace(c, c + (r - c) * b, 40))
            col = np.array(ACCENT) / 255
            ax.plot(seg[:, 0], seg[:, 1], color=(*col, 0.3), lw=16, solid_capstyle="round")
            ax.plot(seg[:, 0], seg[:, 1], color=(*col, 1), lw=4, solid_capstyle="round")
            if b >= 1:
                ring = cam.project(np.c_[r[0] + 1.0 * np.cos(np.linspace(0, 2 * np.pi, 48)),
                                         r[1] + 1.0 * np.sin(np.linspace(0, 2 * np.pi, 48))])
                ax.plot(ring[:, 0], ring[:, 1], color=(*col, 1), lw=3)

    def panels(self, im, cam, t):
        tau = t - self.freeze_at()
        layer = hi_layer(im.size)
        d = HiDraw(layer)
        kits = {k: tuple(v) for k, v in (self.m.get("kits") or {}).items()}
        fr = min(self.win["frames"], key=lambda f: abs(f["clip_ms"] - int(self.m["clip_ms"])))
        for bx in fr.get("boxes") or []:                   # track A's boxes on the held frame
            if bx.get("team") == "referee":
                continue
            x0, y0, x1, y1 = bx["bbox"]
            d.rounded_rectangle((x0, y0, x1, y1), radius=5, outline=(*kits.get(bx.get("team"), (158, 168, 184)), 220),
                                width=1.3)
        car = self._carrier()
        p = self.pick
        f30 = font(30)
        if car is not None and cam is not None:
            pt = cam.project([[car["x"], car["y"]]])[0]
            a = window(tau, 0.4, 0.8)
            text = f"{p['holder'].split()[-1]} shoots · {p['shot_xg']:.2f} xG"
            w = d.textlength(text, font=f30) + 32
            sx = float(np.clip(pt[0] - w / 2, 24, W - 64 - 760 - 16 - w))   # below the shooter, left of the card
            sy = pt[1] + 30
            d.rounded_rectangle((sx, sy, sx + w, sy + 50), radius=RADIUS, fill=(14, 18, 24, int(225 * a)),
                                outline=(255, 255, 255, int(255 * a)), width=2)
            d.text((sx + w / 2, sy + 25), text, font=f30, fill=(255, 255, 255, int(255 * a)), anchor="mm")
            rp = cam.project([p["receiver_xy"]])[0]
            b = window(tau, 1.5, 1.9)
            text = f"{p['xg_receiver']:.2f} xG if it arrives"   # no name on the pitch unless verified
            w = d.textlength(text, font=f30) + 32
            x0 = float(np.clip(rp[0] - w / 2, 24, W - 24 - w))
            y0 = rp[1] - 190                                # above the runner, clear of the cutback line
            d.rounded_rectangle((x0, y0, x0 + w, y0 + 50), radius=RADIUS, fill=(14, 18, 24, int(225 * b)),
                                outline=(*ACCENT, int(255 * b)), width=2)
            d.text((x0 + w / 2, y0 + 25), text, font=f30, fill=(*ACCENT, int(255 * b)), anchor="mm")
        c = window(tau, 2.2, 2.7)                          # the card, in the right stack
        if c > 0:
            w, h = 760, 300
            x0, y0 = W - 64 - w, H - 150 - h
            d.rounded_rectangle((x0, y0, x0 + w, y0 + h), radius=RADIUS, fill=(14, 18, 24, int(232 * c)),
                                outline=(255, 255, 255, int(40 * c)), width=1)
            kit = kits.get(self.m.get("team", "away"), ACCENT)
            d.rounded_rectangle((x0 + RADIUS, y0, x0 + w - RADIUS, y0 + 4), radius=2, fill=(*kit, int(255 * c)))
            d.text((x0 + 28, y0 + 26), self.m["card_title"], font=font(26), fill=(*MUTED, int(255 * c)))
            rows = [(f"{p['holder'].split()[-1]} shoots", f"{p['shot_xg']:.2f}", (230, 236, 242)),
                    (self.m.get("pass_label", "The pass, if it reaches him"), f"{p['xg_receiver']:.2f}", ACCENT)]
            for k, (label, v, col) in enumerate(rows):
                y = y0 + 80 + 78 * k
                vw = d.textlength(f"{v} xG", font=font(40))
                d.text((x0 + 28, y + 4), label, font=shrink(d, label, FONT_REG, 30, w - 56 - vw - 24, floor=24),
                       fill=(230, 236, 242, int(255 * c)))
                d.text((x0 + w - 28, y + 18), f"{v} xG", font=font(40), fill=(*col, int(255 * c)), anchor="rm")
            who_ = self.m.get("receiver_label")
            d.text((x0 + 28, y0 + h - 52), (f"{who_} · " if who_ else "") + f"arrives {p['p_complete'] * 100:.0f}% of the time",
                   font=font(26, bold=False), fill=(*MUTED, int(255 * c)))
        flatten(im, layer)
