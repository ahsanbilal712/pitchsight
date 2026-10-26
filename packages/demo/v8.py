"""Video v8 (PITCHSIGHT): the title sting, the four-step "how it works" explainer and the end card.

Each is built from one real frame of our footage and real data only: track A's detections (tracks/<shot>.json boxes),
its tracked positions (cache/v6 live frames), the reference xG model (evals.pitchwatch.shotxg.reference_xg), the live
pass options (names only from track B's names_live windows) and track B's recorded fact-check claims. The newsroom's
names and the grounding count come from the moment (track B confirms them). Type: DejaVu Sans (docs/video/FONTS.md);
nothing under 24 px; one corner radius; dark glass panels.
"""

from __future__ import annotations

import json

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from demo.footage import model_lines
from demo.live import (
    FONT,
    FONT_REG,
    ROOT,
    H,
    HiDraw,
    Still,
    W,
    bracket,
    downsample_rgba,
    flatten,
    hi_layer,
    window,
)
from demo.v6 import ACCENT, GOOD, RADIUS, LiveHUD, ease_in_out, who

INK = (14, 18, 24)
MUTED_24 = (176, 186, 198)


def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT if bold else FONT_REG, max(24, size))


def glass(im: Image.Image, box, a: float = 1.0, accent=ACCENT) -> None:
    """A dark glass panel: the picture blurred under it, a dark tint, a hairline edge, a thin accent on top."""
    box = tuple(int(v) for v in box)
    region = im.crop(box).filter(ImageFilter.GaussianBlur(16))
    mask = Image.new("L", region.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, region.size[0] - 1, region.size[1] - 1), radius=RADIUS,
                                           fill=int(255 * a))
    im.paste(region, box[:2], mask)
    layer = hi_layer(im.size)
    d = HiDraw(layer)
    d.rounded_rectangle(box, radius=RADIUS, fill=(*INK, int(178 * a)), outline=(255, 255, 255, int(40 * a)), width=1)
    if accent:
        d.rounded_rectangle((box[0] + RADIUS, box[1], box[2] - RADIUS, box[1] + 4), radius=2,
                            fill=(*accent, int(255 * a)))
    flatten(im, layer)


class Motion(Still):
    """A self-contained graphic over one held real frame (`clip_ms`) for `duration` seconds. Subclasses give the
    background (`background`), pixel-space drawing through matplotlib (`draw`) and the type (`overlay`)."""

    needs_camera = False

    def span(self):
        t = self.at_ms() / 1000
        return t, t + float(self.m["duration"])

    def freeze_at(self):
        return self.at_ms() / 1000

    def at_ms(self) -> int:
        return int(self.m["clip_ms"])

    def background(self, img: np.ndarray, tau: float, cam) -> np.ndarray:
        return img

    def draw(self, ax, cam, tau: float) -> None:
        pass

    def overlay(self, im: Image.Image, cam, tau: float) -> None:
        pass

    def frame(self, img, t, ax, canvas, cam_t=None):
        tau = t - self.span()[0]
        cam = self.camera(self.at_ms() / 1000)
        ax.clear()
        ax.set_xlim(0, W)
        ax.set_ylim(H, 0)
        ax.axis("off")
        bg = self.background(img, tau, cam)
        self.draw(ax, cam, tau)
        canvas.draw()
        g = downsample_rgba(np.asarray(canvas.buffer_rgba(), float) / 255, W, H)
        f = bg.astype(float) / 255
        f = f * (1 - g[..., 3:4]) + g[..., :3] * g[..., 3:4]
        im = Image.fromarray(np.clip(f * 255, 0, 255).astype(np.uint8))
        self.overlay(im, cam, tau)
        return im


def _dim(img: np.ndarray, k: float) -> np.ndarray:
    return (img.astype(float) * (1 - k)).astype(np.uint8)


def _zoom(img: np.ndarray, z: float) -> np.ndarray:
    if z <= 1.0001:
        return img
    h, w = img.shape[:2]
    cw, ch = int(w / z), int(h / z)
    x0, y0 = (w - cw) // 2, (h - ch) // 2
    return cv2.resize(img[y0:y0 + ch, x0:x0 + cw], (w, h), interpolation=cv2.INTER_LINEAR)


class TitleSting(Motion):
    """0-6 s: the real frame, darkened, a slow push-in; the pitch markings draw on through the camera, then resolve into
    the wordmark and the tagline."""

    def background(self, img, tau, cam):
        base = _zoom(img, 1.0 + 0.03 * tau / float(self.m["duration"]))
        blur = window(tau, 2.4, 3.2)                    # the picture softens and darkens under the wordmark
        if blur > 0:
            soft = cv2.GaussianBlur(base, (0, 0), 14)
            base = (base.astype(float) * (1 - blur) + soft.astype(float) * blur).astype(np.uint8)
        return _dim(base, 0.55 * window(tau, 0.0, 0.5) + 0.2 + 0.15 * blur)

    def draw(self, ax, cam, tau):
        if cam is None:
            return
        lines = model_lines()
        fade = 1 - window(tau, 2.6, 3.4)
        for k, (_, pts) in enumerate(sorted(lines.items())):
            p = window(tau, 0.3 + 0.12 * k, 1.5 + 0.12 * k)
            if p <= 0 or fade <= 0:
                continue
            seg = cam.project(pts[: max(2, int(len(pts) * p))])
            ok = (seg[:, 0] > -200) & (seg[:, 0] < W + 200) & (seg[:, 1] > -200) & (seg[:, 1] < H + 200)
            seg = seg[ok]
            if len(seg) < 2:
                continue
            col = np.array(ACCENT) / 255
            ax.plot(seg[:, 0], seg[:, 1], color=(*col, 0.25 * fade), lw=9, solid_capstyle="round")
            ax.plot(seg[:, 0], seg[:, 1], color=(1, 1, 1, 0.9 * fade), lw=2.2, solid_capstyle="round")

    def overlay(self, im, cam, tau):
        a = window(tau, 2.8, 3.1)                      # crisp: full white within 0.3 s
        if a <= 0:
            return
        layer = hi_layer(im.size)
        d = HiDraw(layer)
        s = 1 + 0.06 * (1 - ease_in_out(window(tau, 2.8, 3.4)))
        f = ImageFont.truetype(FONT, int(170 * s))
        word = "PITCHSIGHT"
        d.text((W / 2, H / 2 - 40), word, font=f, fill=(255, 255, 255, int(255 * a)), anchor="mm",
               stroke_width=2, stroke_fill=(255, 255, 255, int(255 * a)))
        wl = d.textlength(word, font=f) * ease_in_out(window(tau, 3.2, 3.9))
        d.rounded_rectangle((W / 2 - wl / 2, H / 2 + 62, W / 2 + wl / 2, H / 2 + 70), radius=4,
                            fill=(*ACCENT, int(255 * a)))
        b = window(tau, 3.7, 4.3)
        d.text((W / 2, H / 2 + 128), self.m.get("tagline", ""), font=font(48, bold=False),
               fill=(230, 236, 242, int(255 * b)), anchor="mm")
        flatten(im, layer)


class Explainer(Motion):
    """6-30 s: how it works, from one real frame. SEE: track A's detection boxes snap onto the players and the ball,
    the grass of the attacking half folds through the camera's homography to top-down, turns goal-up, and holds as a
    clean mini-pitch where the tracked run plays. MEASURE: the reference xG surface fills it, the live options are
    priced, and the two models are named. EXPLAIN: the newsroom's agents light in their real order. VERIFY: the
    grounding count. NEXT: what is not built yet, as one list."""

    STEPS = (("SEE", 0.0), ("MEASURE", 5.5), ("EXPLAIN", 11.0), ("VERIFY", 16.5), ("NEXT", 20.5))
    LAND = (300, 170, 11.0)                      # the fold lands here: the attacking half, goal at the side
    GOAL_UP = (96, 196, 14.0)                    # then turns: goal at the top, 952 x 735 px
    T_FOLD, T_TURN, T_HOLD = (2.0, 3.0), (3.2, 3.9), 3.9

    def __init__(self, m: dict):
        super().__init__(m)
        see = json.loads((ROOT / m["see"]).read_text())            # track A: this frame's boxes and the run after
        self.see = see.get("result", see)
        self.det = {"players": self.see["boxes"], "ball": self.see.get("ball")}
        self.run = self.see["positions"]["samples"]
        surf = json.loads((ROOT / m["xg_surface"]).read_text())     # track A: reference xG on a 1 m grid
        self.surf = surf.get("result", surf)
        hud_m = {**m, "kind": "live_hud", "t0": m["options_at"] / 1000 - 0.5, "t1": m["options_at"] / 1000 + 0.5}
        self.live = LiveHUD(hud_m)                 # the same names rule as on air (names_live windows)
        self.attacks_left = m.get("attacks", "+x") == "-x"
        self.option_ms = int(m["options_at"])
        self.pipe = json.loads((ROOT / m["pipeline"]).read_text())
        self.pipe = self.pipe.get("result", self.pipe)

    # -- geometry ---------------------------------------------------------------------------------------------
    def depth(self, p: np.ndarray) -> np.ndarray:
        return p[:, 0] if self.attacks_left else 105 - p[:, 0]               # metres from the goal attacked

    def land(self, xy) -> np.ndarray:
        """The fold's target: top-down, the goal attacked at the right, the near touchline at the bottom."""
        x0, y0, s = self.LAND
        p = np.asarray(xy, float).reshape(-1, 2)
        side = (68 - p[:, 1]) if not self.attacks_left else p[:, 1]
        return np.c_[x0 + (52.5 - self.depth(p)) * s, y0 + side * s]

    def mini(self, xy) -> np.ndarray:
        """The mini-pitch everything is drawn on: the attacking half, goal at the top (the land view turned)."""
        x0, y0, s = self.GOAL_UP
        p = np.asarray(xy, float).reshape(-1, 2)
        across = (68 - p[:, 1]) if not self.attacks_left else p[:, 1]
        return np.c_[x0 + across * s, y0 + self.depth(p) * s]

    def turn(self, e: float) -> np.ndarray:
        """The 2x3 similarity carrying the land view to the goal-up view, e of the way (a true rotation)."""
        c = np.array([[52.5 + (26.25 if not self.attacks_left else -26.25), 34.0]])
        if self.attacks_left:
            c = np.array([[26.25, 34.0]])
        lc, fc = self.land(c)[0], self.mini(c)[0]
        th = (-np.pi / 2 if not self.attacks_left else np.pi / 2) * e
        k = (self.GOAL_UP[2] / self.LAND[2]) ** e
        R = k * np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
        ct = lc + e * (fc - lc)
        return np.c_[R, ct - R @ lc]

    def background(self, img, tau, cam):
        self.tau_now = tau
        f = ease_in_out(window(tau, *self.T_FOLD))
        if f <= 0 or cam is None:
            return _dim(img, 0.2 * window(tau, 1.2, 2.0))
        if tau >= self.T_HOLD:
            return self._pitch_image(goal_up=True)
        quad = np.array([[0, 0], [52.5, 0], [52.5, 68], [0, 68]], float)          # the attacking half
        if not self.attacks_left:
            quad[:, 0] = 105 - quad[:, 0]
        src = cam.project(quad).astype(np.float32)
        mid = (src * (1 - f) + self.land(quad).astype(np.float32) * f).astype(np.float32)
        M = cv2.getPerspectiveTransform(src, mid)
        mask = np.zeros(img.shape[:2], np.uint8)
        cv2.fillConvexPoly(mask, src.astype(np.int32), 255)
        picture = np.where(mask[..., None] > 0, img, 0).astype(np.uint8)
        warped = cv2.warpPerspective(picture, M, (W, H), borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        wmask = cv2.warpPerspective(mask, M, (W, H)) / 255.0
        stands = _dim(img, 0.2 + 0.8 * f)               # the rest of the picture fades away under it
        out = stands.astype(float) * (1 - wmask[..., None]) + warped.astype(float) * wmask[..., None]
        k = window(tau, 2.8, 3.2)                       # the warped picture gives way to the clean pitch
        out = out * (1 - k) + self._pitch_image(goal_up=False).astype(float) * k
        e = ease_in_out(window(tau, *self.T_TURN))
        if e > 0:                                       # then the whole view turns goal-up
            out = cv2.warpAffine(out.astype(np.uint8), self.turn(e), (W, H), borderMode=cv2.BORDER_CONSTANT,
                                 borderValue=INK).astype(float)
        return np.clip(out, 0, 255).astype(np.uint8)

    def _pitch_image(self, goal_up: bool) -> np.ndarray:
        key = "_pitch_up" if goal_up else "_pitch_land"
        if hasattr(self, key):
            return getattr(self, key)
        im = Image.new("RGB", (W, H), INK)
        d = ImageDraw.Draw(im)
        to = self.mini if goal_up else self.land
        corners = to(np.array([[52.5, 0], [105, 68]] if not self.attacks_left else [[0, 0], [52.5, 68]], float))
        (ax0, ay0), (ax1, ay1) = corners.min(axis=0), corners.max(axis=0)
        d.rounded_rectangle((ax0 - 20, ay0 - 20, ax1 + 20, ay1 + 20), radius=RADIUS, fill=(22, 52, 36))
        half = (lambda p: p[:, 0] >= 52.5 - 0.01) if not self.attacks_left else (lambda p: p[:, 0] <= 52.5 + 0.01)
        s = self.GOAL_UP[2] if goal_up else self.LAND[2]
        for _, pts in model_lines().items():
            keep = half(pts)
            if keep.sum() < 2:
                continue
            q = to(pts[keep])
            for a_, b_ in zip(q[:-1], q[1:], strict=True):     # no chord across a cut circle
                if np.hypot(*(b_ - a_)) < 4 * s:
                    d.line((tuple(a_), tuple(b_)), fill=(225, 235, 228), width=3 if goal_up else 2)
        setattr(self, key, np.asarray(im))
        return getattr(self, key)

    # -- drawing ----------------------------------------------------------------------------------------------
    def draw(self, ax, cam, tau):
        if tau < self.T_HOLD:
            return
        if 5.5 <= tau < 16.5:
            self._xg_surface(ax, tau)
        self._dots(ax, tau)
        if 7.4 <= tau < 16.5:
            self._passes(ax, tau)

    def _xg_surface(self, ax, tau):
        a = window(tau, 5.6, 6.6) * (1 - window(tau, 11.0, 11.6) * 0.6)
        if not hasattr(self, "_xg"):
            z = np.asarray(self.surf["values"], float)          # [j][i], toward x = 105
            if self.attacks_left:
                z = z[:, ::-1]
            xs = np.arange(z.shape[1]) + 0.5
            ys = np.arange(z.shape[0]) + 0.5
            self._xg = (xs, ys, z)
        xs, ys, z = self._xg
        X, Y = np.meshgrid(xs, ys)
        P = self.mini(np.c_[X.ravel(), Y.ravel()]).reshape(*X.shape, 2)
        reach = window(tau, 5.6, 6.8)            # it fills outward from the goal
        dist = (X if self.attacks_left else 105 - X)
        zz = np.ma.masked_where((z < 0.03) | (dist > 40 * reach + 1), z)
        col = np.array(ACCENT) / 255
        levels = [0.03, 0.05, 0.1, 0.2, 0.35, 1.0]
        alphas = [0.12, 0.28, 0.45, 0.6, 0.75]
        ax.contourf(P[..., 0], P[..., 1], zz, levels=levels, colors=[(*col, al * a) for al in alphas])

    def _frame_at(self, ms: float) -> dict | None:
        s = self.live.data["samples"]
        if not s:
            return None
        i, _, _ = bracket(s, ms)
        return s[i]

    def _dots(self, ax, tau):
        p = window(tau, self.T_HOLD, 5.5)        # track A's tracked run, replayed at speed, then held
        f = self.run[min(len(self.run) - 1, int(p * (len(self.run) - 1)))]
        kits = self.m.get("kits") or {}
        for pl in f.get("players") or []:
            if pl.get("team") not in ("home", "away"):
                continue
            q = self.mini([[pl["x"], pl["y"]]])[0]
            c = np.array(kits.get(pl["team"], (255, 255, 255))) / 255
            ax.scatter([q[0]], [q[1]], s=300, color=(*c, 1), edgecolors=(1, 1, 1, 0.9), linewidths=2, zorder=5)
        b = f.get("ball")
        if b and b.get("x") is not None:
            q = self.mini([[b["x"], b["y"]]])[0]
            ax.scatter([q[0]], [q[1]], s=110, color=(1, 1, 1, 1), edgecolors=(0, 0, 0, 0.8), linewidths=1.2, zorder=6)

    def options(self) -> tuple[dict | None, list[dict]]:
        f = self._frame_at(self.option_ms)
        if not f or not f.get("carrier"):
            return None, []
        return f["carrier"], self.live.ranked(f)[:5]

    def _passes(self, ax, tau):
        car, opts = self.options()
        if not car:
            return
        c = self.mini([[car["x"], car["y"]]])[0]
        for k, o in enumerate(opts):
            p = window(tau, 7.4 + 0.25 * k, 7.7 + 0.25 * k)
            if p <= 0:
                continue
            e = self.mini([[o["x"], o["y"]]])[0]
            seg = np.linspace(c, c + (e - c) * p, 20)
            best = k == 0
            col = np.array(ACCENT) / 255 if best else np.array((1, 1, 1))
            al = 1.0 if best else 0.55
            if best:
                pulse = 0.5 + 0.5 * np.sin(2 * np.pi * tau / 1.2)
                ax.plot(seg[:, 0], seg[:, 1], color=(*col, 0.25 + 0.2 * pulse), lw=18, solid_capstyle="round")
            ax.plot(seg[:, 0], seg[:, 1], color=(*col, al), lw=5 if best else 2.5, solid_capstyle="round", zorder=4)

    # -- type -------------------------------------------------------------------------------------------------
    def overlay(self, im, cam, tau):
        if tau < self.T_FOLD[0] + 0.2:
            self._boxes(im, tau)
        step = max(k for k, (_, t0) in enumerate(self.STEPS) if tau >= t0)
        name, _ = self.STEPS[step]
        probe = ImageDraw.Draw(im)
        bw = 64 + 50 + probe.textlength(name, font=font(52)) + 44 + probe.textlength("HOW IT WORKS", font=font(28)) + 32
        glass(im, (64, 56, 64 + bw, 56 + 100), 1.0)
        d = ImageDraw.Draw(im)
        d.text((96, 106), f"{step + 1}", font=font(52), fill=ACCENT, anchor="lm")
        d.text((96 + 50, 106), name, font=font(52), fill=(255, 255, 255), anchor="lm")
        d.text((64 + bw - 32, 106), "HOW IT WORKS", font=font(28), fill=MUTED_24, anchor="rm")
        if 7.6 <= tau < 16.5:
            self._pills(im, tau)
        if 6.0 <= tau < 11.0:
            self._models(im, tau - 6.0)
        if 11.0 <= tau < 16.5:
            self._agents(im, tau - 11.0)
        if 16.5 <= tau < 20.5:
            self._verify(im, tau - 16.5)
        if tau >= 20.5:
            self._next(im, tau - 20.5)

    def _boxes(self, im, tau):
        layer = hi_layer(im.size)
        d = HiDraw(layer)
        dets = [(p["bbox"], p.get("team"), 0.035 * k) for k, p in enumerate(self.det["players"])]
        if self.det.get("ball"):
            dets.append((self.det["ball"]["bbox"], "ball", 0.035 * len(dets)))
        kits = {k: tuple(v) for k, v in (self.m.get("kits") or {}).items()}
        fade = 1 - window(tau, self.T_FOLD[0] - 0.1, self.T_FOLD[0] + 0.2)
        for (x0, y0, x1, y1), team, delay in dets:
            p = window(tau, 0.3 + delay, 0.6 + delay)
            if p <= 0:
                continue
            g = 1.35 - 0.35 * ease_in_out(p)       # snaps in from a little larger
            cx, cy, hw, hh = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2 * g, (y1 - y0) / 2 * g
            if team == "ball":
                hw, hh = max(hw, 12), max(hh, 12)
            col = (255, 255, 255) if team == "ball" else kits.get(team, (200, 206, 214))
            al = int(255 * p * fade)
            L = min(hw, hh) * 0.6
            for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):   # corner brackets, the tracker's look
                px, py = cx + sx * hw, cy + sy * hh
                d.line((px, py, px - sx * L, py), fill=(*col, al), width=4)
                d.line((px, py, px, py - sy * L), fill=(*col, al), width=4)
        b = window(tau, 1.0, 1.3) * fade
        if b > 0:
            text = "Every player in view and the ball, detected in this frame"
            f = font(34)
            w = d.textlength(text, font=f) + 56
            d.rounded_rectangle((W / 2 - w / 2, 190, W / 2 + w / 2, 256), radius=RADIUS, fill=(*INK, int(210 * b)))
            d.text((W / 2, 223), text, font=f, fill=(255, 255, 255, int(255 * b)), anchor="mm")
        flatten(im, layer)

    def _pills(self, im, tau):
        car, opts = self.options()
        if not car:
            return
        layer = hi_layer(im.size)
        d = HiDraw(layer)
        f = font(30)
        placed = []
        for k, o in enumerate(opts[:3]):                 # top 3 labelled only
            p = window(tau, 7.6 + 0.25 * k, 7.9 + 0.25 * k)
            if p <= 0:
                continue
            e = self.mini([[o["x"], o["y"]]])[0]
            name = who(o)
            text = (f"{name} · " if name else "") + f"{o['p_pass'] * 100:.0f}% · {o['xg_after_pass']:.2f} xG"
            w = d.textlength(text, font=f) + 32
            x0, y0 = float(np.clip(e[0] - w / 2, 40, 96 + 952 - w)), e[1] + 20
            for bx0, by0, bx1, by1 in placed:
                if x0 < bx1 + 6 and x0 + w > bx0 - 6 and y0 < by1 + 6 and y0 + 50 > by0 - 6:
                    y0 = by1 + 8
            placed.append((x0, y0, x0 + w, y0 + 50))
            col = ACCENT if k == 0 else (255, 255, 255)
            d.rounded_rectangle((x0, y0, x0 + w, y0 + 50), radius=RADIUS, fill=(*INK, int(225 * p)),
                                outline=(*col, int(255 * p)), width=2)
            d.text((x0 + w / 2, y0 + 25), text, font=f, fill=(*col, int(255 * p)), anchor="mm")
        cname = who(car)
        if cname:
            q = self.mini([[car["x"], car["y"]]])[0]
            d.text((q[0], q[1] - 26), cname, font=font(30), fill=(255, 255, 255, 255), anchor="mb",
                   stroke_width=3, stroke_fill=(0, 0, 0, 200))
        flatten(im, layer)

    def _side(self) -> tuple[int, int, int, int]:
        """The column right of the mini-pitch: left, top, right, bottom."""
        return 96 + 952 + 48, 196, W - 64, 196 + 735

    def _models(self, im, tau):
        """MEASURE's right column: the two models behind every number, as track A states them (intro_facts_0)."""
        rows = self.m.get("models", [])
        x0, y0, x1, y1 = self._side()
        a = window(tau, 0.2, 0.6)
        if a <= 0 or not rows:
            return
        glass(im, (x0, y0, x1, y0 + 120 + 190 * len(rows)), a)
        d = ImageDraw.Draw(im)
        d.text((x0 + 32, y0 + 52), "THE MODELS", font=font(30), fill=MUTED_24, anchor="lm")
        for k, r in enumerate(rows):
            y = y0 + 110 + 190 * k
            d.text((x0 + 32, y), r["name"], font=font(40), fill=ACCENT if k == 0 else (255, 255, 255))
            for j, ln in enumerate(r["lines"]):
                d.text((x0 + 32, y + 58 + 40 * j), ln, font=font(30, bold=False), fill=(214, 222, 230))

    def _agents(self, im, tau):
        names = self.m["agents"]                     # track B: the newsroom's real order, as the screen names it
        roles = self.m.get("agent_roles", {})
        x0, top, x1, _ = self._side()
        w, h, gap = x1 - x0 - 48, 74, 12
        y0 = top + 24
        step = 4.2 / len(names)
        glass(im, (x0, top - 8, x1, y0 + len(names) * (h + gap) - gap + 24), 1.0)
        d = ImageDraw.Draw(im)
        bx = x0 + 24
        for k, n in enumerate(names):
            t_on = 0.3 + step * k
            lit = tau >= t_on
            y = y0 + k * (h + gap)
            col = ACCENT if lit and tau < t_on + step else ((70, 200, 130) if lit else (80, 88, 100))
            d.rounded_rectangle((bx, y, bx + w, y + h), radius=RADIUS, fill=(28, 32, 40) if lit else (22, 25, 31),
                                outline=col, width=3 if lit else 1)
            d.ellipse((bx + 22, y + h / 2 - 11, bx + 44, y + h / 2 + 11), fill=col)
            d.text((bx + 66, y + h / 2), n.upper(), font=font(32), fill=(255, 255, 255) if lit else MUTED_24,
                   anchor="lm")
            if roles.get(n):
                d.text((bx + w - 22, y + h / 2), roles[n], font=font(28, bold=False),
                       fill=(214, 222, 230) if lit else (90, 98, 110), anchor="rm")
            if k:
                p = window(tau, t_on - 0.2, t_on)
                d.line((bx + 33, y - gap, bx + 33, y - gap + gap * p), fill=ACCENT, width=4)
        chips = self.m.get("stack", [])               # the stack, top right beside the step header
        a = window(tau, 0.2, 0.6)
        cx = W - 64
        for c in reversed(chips if a > 0 else []):
            f = font(28)
            cw = d.textlength(c, font=f) + 40
            d.rounded_rectangle((cx - cw, 76, cx, 136), radius=RADIUS, fill=(28, 32, 40), outline=ACCENT, width=2)
            d.text((cx - cw / 2, 106), c, font=f, fill=(255, 255, 255), anchor="mm")
            cx -= cw + 16

    def _verify(self, im, tau):
        n = int(self.m["checked"])
        x0, y0, x1, y1 = 160, 200, W - 160, 930
        glass(im, (x0, y0, x1, y1), 1.0, accent=GOOD)
        d = ImageDraw.Draw(im)
        p = ease_in_out(window(tau, 0.2, 1.4))         # a bar fills; only the real count is ever printed
        d.rounded_rectangle((W / 2 - 520, 290, W / 2 + 520, 310), radius=10, fill=(58, 64, 74))
        d.rounded_rectangle((W / 2 - 520, 290, W / 2 - 520 + 1040 * max(0.02, p), 310), radius=10, fill=GOOD)
        a = window(tau, 1.3, 1.6)
        d.text((W / 2, 440), f"{n:,} of {n:,}", font=font(170), fill=(255, 255, 255, int(255 * a)), anchor="mm")
        d.text((W / 2, 570), "on-screen numbers checked against the data", font=font(48, bold=False),
               fill=(230, 236, 242), anchor="mm")
        claims = [c for n_ in self.pipe["nodes"] for c in n_.get("claims", []) if any(ch.isdigit() for ch in c["text"])]
        for j, c in enumerate(claims[:3]):
            a = window(tau, 1.6 + 0.3 * j, 1.9 + 0.3 * j)
            if a <= 0:
                continue
            y = 680 + 68 * j
            ev = c.get("evidence", "").split("(")[0].strip()
            d.line((560, y, 572, y + 12, 594, y - 12), fill=GOOD, width=6)
            d.text((620, y), c["text"], font=font(36), fill=(255, 255, 255), anchor="lm")
            d.text((780, y), ev, font=font(32, bold=False), fill=MUTED_24, anchor="lm")

    def _next(self, im, tau):
        items = self.m["next"]
        x0, y0, x1, y1 = 260, 220, W - 260, 900
        glass(im, (x0, y0, x1, y1), 1.0, accent=(150, 160, 175))
        d = ImageDraw.Draw(im)
        label = "NEXT · NOT BUILT YET"                     # track B: plans, never shown as done
        lw = d.textlength(label, font=font(40)) + 64
        d.rounded_rectangle((W / 2 - lw / 2, 280, W / 2 + lw / 2, 352), radius=RADIUS, outline=(255, 255, 255), width=3)
        d.text((W / 2, 316), label, font=font(40), fill=(255, 255, 255), anchor="mm")
        for j, it in enumerate(items):                    # the three together, as one list
            a = window(tau, 0.15 + 0.12 * j, 0.45 + 0.12 * j)
            y = 470 + 130 * j
            d.rounded_rectangle((x0 + 120, y - 50, x1 - 120, y + 50), radius=RADIUS,
                                outline=(150, 160, 175, int(255 * a)), width=2)
            d.ellipse((x0 + 160, y - 9, x0 + 178, y + 9), fill=(150, 160, 175))
            d.text((x0 + 210, y), it, font=font(46, bold=False), fill=(230, 236, 242), anchor="lm")


class EndCard(Motion):
    """The close: the wordmark over the frame, blurred and dark; the permission line and the repository link."""

    def background(self, img, tau, cam):
        if not hasattr(self, "_bg"):
            blur = Image.fromarray(img).filter(ImageFilter.GaussianBlur(18))
            self._bg = _dim(np.asarray(blur), 0.72)
        return self._bg

    def overlay(self, im, cam, tau):
        a = window(tau, 0.0, 0.5)
        layer = hi_layer(im.size)
        d = HiDraw(layer)
        f = ImageFont.truetype(FONT, 150)
        d.text((W / 2, H / 2 - 110), "PITCHSIGHT", font=f, fill=(255, 255, 255, int(255 * a)), anchor="mm")
        wl = d.textlength("PITCHSIGHT", font=f) * ease_in_out(window(tau, 0.3, 1.0))
        d.rounded_rectangle((W / 2 - wl / 2, H / 2 - 18, W / 2 + wl / 2, H / 2 - 12), radius=3,
                            fill=(*ACCENT, int(255 * a)))
        b = window(tau, 0.6, 1.1)
        d.text((W / 2, H / 2 + 50), self.m.get("tagline", ""), font=font(44, bold=False),
               fill=(230, 236, 242, int(255 * b)), anchor="mm")
        c = window(tau, 1.0, 1.5)
        d.text((W / 2, H / 2 + 150), self.m.get("repo", ""), font=font(36), fill=(*ACCENT, int(255 * c)), anchor="mm")
        d.text((W / 2, H - 120), self.m.get("permission", ""), font=font(28, bold=False),
               fill=(176, 186, 198, int(255 * c)), anchor="mm")
        flatten(im, layer)
