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
from demo.live import FONT, FONT_REG, ROOT, H, Still, W, bracket, window
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
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(box, radius=RADIUS, fill=(*INK, int(178 * a)), outline=(255, 255, 255, int(40 * a)), width=1)
    if accent:
        d.rounded_rectangle((box[0] + RADIUS, box[1], box[2] - RADIUS, box[1] + 4), radius=2,
                            fill=(*accent, int(255 * a)))
    im.paste(layer, (0, 0), layer)


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
        g = np.asarray(canvas.buffer_rgba(), float) / 255
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
        return _dim(_zoom(img, 1.0 + 0.03 * tau / float(self.m["duration"])), 0.62 * window(tau, 0.0, 0.5) + 0.2)

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
        a = window(tau, 2.8, 3.5)
        if a <= 0:
            return
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        s = 1 + 0.08 * (1 - ease_in_out(a))
        f = ImageFont.truetype(FONT, int(150 * s))
        word = "PITCHSIGHT"
        d.text((W / 2, H / 2 - 40), word, font=f, fill=(255, 255, 255, int(255 * a)), anchor="mm")
        wl = d.textlength(word, font=f) * ease_in_out(window(tau, 3.2, 3.9))
        d.rounded_rectangle((W / 2 - wl / 2, H / 2 + 52, W / 2 + wl / 2, H / 2 + 58), radius=3,
                            fill=(*ACCENT, int(255 * a)))
        b = window(tau, 3.7, 4.3)
        d.text((W / 2, H / 2 + 110), self.m.get("tagline", ""), font=font(44, bold=False),
               fill=(230, 236, 242, int(255 * b)), anchor="mm")
        im.paste(layer, (0, 0), layer)


class Explainer(Motion):
    """6-30 s: how it works, from one real frame. SEE: track A's detection boxes snap onto the players and the ball,
    then the frame folds (through the camera's homography) into a top-down mini-pitch where the tracked dots move.
    MEASURE: the reference xG surface fills it, then the live pass options, priced. EXPLAIN: the newsroom's agents
    light in turn. VERIFY: the grounding count. NEXT: what comes next, labelled as such."""

    STEPS = (("SEE", 0.0), ("MEASURE", 5.5), ("EXPLAIN", 11.0), ("VERIFY", 16.5), ("NEXT", 20.5))
    MINI = (300, 170, 11.0)                      # mini-pitch: left, top, px per metre (the attacking half)

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
    def mini(self, xy) -> np.ndarray:
        """Pitch metres -> the top-down mini-pitch: the attacking half, its goal at the right (mirrored when the side
        attacks the left goal), y from the near touchline at the bottom."""
        x0, y0, s = self.MINI
        p = np.asarray(xy, float).reshape(-1, 2)
        depth = (105 - p[:, 0]) if not self.attacks_left else p[:, 0]          # metres from the goal attacked
        return np.c_[x0 + (52.5 - depth) * s, y0 + ((68 - p[:, 1]) if not self.attacks_left else p[:, 1]) * s]

    def fold(self) -> float:
        return ease_in_out(window(self.tau_now, 2.4, 3.6))

    def background(self, img, tau, cam):
        self.tau_now = tau
        f = self.fold()
        if f <= 0 or cam is None:
            return _dim(img, 0.15 * window(tau, 1.5, 2.4))
        # the fold: only the grass, its corners carried from where the camera sees them to the top-down mini-pitch
        quad = np.array([[0, 0], [52.5, 0], [52.5, 68], [0, 68]], float)         # the attacking half
        if not self.attacks_left:
            quad[:, 0] = 105 - quad[:, 0]
        src = cam.project(quad).astype(np.float32)
        dst = self.mini(quad).astype(np.float32)
        mid = (src * (1 - f) + dst * f).astype(np.float32)
        M = cv2.getPerspectiveTransform(src, mid)
        mask = np.zeros(img.shape[:2], np.uint8)
        cv2.fillConvexPoly(mask, cam.project(quad).astype(np.int32), 255)
        picture = np.where(mask[..., None] > 0, img, 0).astype(np.uint8)
        warped = cv2.warpPerspective(picture, M, (W, H), borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        wmask = cv2.warpPerspective(mask, M, (W, H)) / 255.0
        stands = _dim(img, 0.15 + 0.85 * f)             # the rest of the picture fades away under it
        out = stands.astype(float) * (1 - wmask[..., None]) + warped.astype(float) * wmask[..., None]
        k = window(tau, 3.3, 4.2)                # the warped picture gives way to the clean mini-pitch
        out = out * (1 - k) + self._pitch_image().astype(float) * k
        return np.clip(out, 0, 255).astype(np.uint8)

    def _pitch_image(self) -> np.ndarray:
        if hasattr(self, "_pitch"):
            return self._pitch
        im = Image.new("RGB", (W, H), INK)
        d = ImageDraw.Draw(im)
        x0, y0, s = self.MINI
        d.rounded_rectangle((x0 - 20, y0 - 20, x0 + 52.5 * s + 20, y0 + 68 * s + 20), radius=RADIUS,
                            fill=(22, 52, 36))
        half = (lambda p: p[:, 0] >= 52.5 - 0.01) if not self.attacks_left else (lambda p: p[:, 0] <= 52.5 + 0.01)
        for _, pts in model_lines().items():
            keep = half(pts)
            if keep.sum() < 2:
                continue
            q = self.mini(pts[keep])
            for a_, b_ in zip(q[:-1], q[1:], strict=True):     # no chord across a cut circle
                if np.hypot(*(b_ - a_)) < 4 * s:
                    d.line((tuple(a_), tuple(b_)), fill=(225, 235, 228), width=2)
        self._pitch = np.asarray(im)
        return self._pitch

    # -- drawing ----------------------------------------------------------------------------------------------
    def draw(self, ax, cam, tau):
        if tau < 2.4:
            return
        if 5.5 <= tau < 16.5:
            self._xg_surface(ax, tau)
        if tau >= 3.6:
            self._dots(ax, tau)
        if 7.6 <= tau < 16.5:
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
        p = window(tau, 3.6, 5.5)                # track A's tracked run, replayed at speed, then held
        f = self.run[min(len(self.run) - 1, int(p * (len(self.run) - 1)))]
        kits = self.m.get("kits") or {}
        for pl in f.get("players") or []:
            if pl.get("team") not in ("home", "away"):
                continue
            q = self.mini([[pl["x"], pl["y"]]])[0]
            c = np.array(kits.get(pl["team"], (255, 255, 255))) / 255
            ax.scatter([q[0]], [q[1]], s=170, color=(*c, 1), edgecolors=(1, 1, 1, 0.9), linewidths=1.6, zorder=5)
        b = f.get("ball")
        if b and b.get("x") is not None:
            q = self.mini([[b["x"], b["y"]]])[0]
            ax.scatter([q[0]], [q[1]], s=60, color=(1, 1, 1, 1), edgecolors=(0, 0, 0, 0.8), linewidths=1, zorder=6)

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
            p = window(tau, 7.6 + 0.25 * k, 7.9 + 0.25 * k)
            if p <= 0:
                continue
            e = self.mini([[o["x"], o["y"]]])[0]
            seg = np.linspace(c, c + (e - c) * p, 20)
            best = k == 0
            col = np.array(ACCENT) / 255 if best else np.array((1, 1, 1))
            al = 1.0 if best else 0.55
            if best:
                pulse = 0.5 + 0.5 * np.sin(2 * np.pi * tau / 1.2)
                ax.plot(seg[:, 0], seg[:, 1], color=(*col, 0.25 + 0.2 * pulse), lw=14, solid_capstyle="round")
            ax.plot(seg[:, 0], seg[:, 1], color=(*col, al), lw=4 if best else 2, solid_capstyle="round", zorder=4)

    # -- type -------------------------------------------------------------------------------------------------
    def overlay(self, im, cam, tau):
        if tau < 2.4:
            self._boxes(im, tau)
        step = max(k for k, (_, t0) in enumerate(self.STEPS) if tau >= t0)
        name, _ = self.STEPS[step]
        probe = ImageDraw.Draw(im)
        bw = 150 - 64 + probe.textlength(name, font=font(40)) + 40 + probe.textlength("HOW IT WORKS", font=font(24)) + 28
        glass(im, (64, 64, 64 + bw, 64 + 84), 1.0)
        d = ImageDraw.Draw(im)
        d.text((92, 106), f"{step + 1}", font=font(40), fill=ACCENT, anchor="lm")
        d.text((150, 106), name, font=font(40), fill=(255, 255, 255), anchor="lm")
        d.text((64 + bw - 28, 106), "HOW IT WORKS", font=font(24), fill=MUTED_24, anchor="rm")
        if 7.9 <= tau < 16.5:
            self._pills(im, tau)
        if 11.0 <= tau < 16.5:
            self._agents(im, tau - 11.0)
        if 16.5 <= tau < 20.5:
            self._verify(im, tau - 16.5)
        if tau >= 20.5:
            self._next(im, tau - 20.5)

    def _boxes(self, im, tau):
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        dets = [(p["bbox"], p.get("team"), 0.04 * k) for k, p in enumerate(self.det["players"])]
        if self.det.get("ball"):
            dets.append((self.det["ball"]["bbox"], "ball", 0.04 * len(dets)))
        kits = {k: tuple(v) for k, v in (self.m.get("kits") or {}).items()}
        fade = 1 - window(tau, 2.2, 2.6)
        for (x0, y0, x1, y1), team, delay in dets:
            p = window(tau, 0.4 + delay, 0.7 + delay)
            if p <= 0:
                continue
            g = 1.35 - 0.35 * ease_in_out(p)       # snaps in from a little larger
            cx, cy, hw, hh = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2 * g, (y1 - y0) / 2 * g
            if team == "ball":
                hw, hh = max(hw, 10), max(hh, 10)
            col = (255, 255, 255) if team == "ball" else kits.get(team, (200, 206, 214))
            al = int(255 * p * fade)
            L = min(hw, hh) * 0.6
            for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):   # corner brackets, the tracker's look
                px, py = cx + sx * hw, cy + sy * hh
                d.line((px, py, px - sx * L, py), fill=(*col, al), width=3)
                d.line((px, py, px, py - sy * L), fill=(*col, al), width=3)
        b = window(tau, 1.2, 1.5) * fade
        if b > 0:
            text = "Every player in view and the ball, detected in this frame"
            f = font(28)
            w = d.textlength(text, font=f) + 48
            d.rounded_rectangle((W / 2 - w / 2, 180, W / 2 + w / 2, 236), radius=RADIUS, fill=(*INK, int(200 * b)))
            d.text((W / 2, 208), text, font=f, fill=(255, 255, 255, int(255 * b)), anchor="mm")
        im.paste(layer, (0, 0), layer)

    def _pills(self, im, tau):
        car, opts = self.options()
        if not car:
            return
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        f = font(26)
        placed = []
        for k, o in enumerate(opts[:3]):                 # top 3 labelled only
            p = window(tau, 7.9 + 0.25 * k, 8.2 + 0.25 * k)
            if p <= 0:
                continue
            e = self.mini([[o["x"], o["y"]]])[0]
            name = who(o)
            text = (f"{name} · " if name else "") + f"{o['p_pass'] * 100:.0f}% · {o['xg_after_pass']:.2f} xG"
            w = d.textlength(text, font=f) + 28
            x0, y0 = e[0] - w / 2, e[1] + 16
            for bx0, by0, bx1, by1 in placed:
                if x0 < bx1 + 6 and x0 + w > bx0 - 6 and y0 < by1 + 6 and y0 + 44 > by0 - 6:
                    y0 = by1 + 8
            placed.append((x0, y0, x0 + w, y0 + 44))
            col = ACCENT if k == 0 else (255, 255, 255)
            d.rounded_rectangle((x0, y0, x0 + w, y0 + 44), radius=RADIUS, fill=(*INK, int(225 * p)),
                                outline=(*col, int(255 * p)), width=2)
            d.text((x0 + w / 2, y0 + 22), text, font=f, fill=(*col, int(255 * p)), anchor="mm")
        cname = who(car)
        if cname:
            q = self.mini([[car["x"], car["y"]]])[0]
            d.text((q[0], q[1] - 22), cname, font=font(26), fill=(255, 255, 255, 255), anchor="mb",
                   stroke_width=3, stroke_fill=(0, 0, 0, 200))
        im.paste(layer, (0, 0), layer)

    def _agents(self, im, tau):
        names = self.m["agents"]                     # track B: the newsroom's real order, as the screen names it
        roles = self.m.get("agent_roles", {})
        x0, y0, w, h, gap = 1250, 250, 600, 62, 12
        step = 4.4 / len(names)
        glass(im, (x0 - 24, y0 - 28, x0 + w + 24, y0 + len(names) * (h + gap) - gap + 28), 1.0)
        d = ImageDraw.Draw(im)
        for k, n in enumerate(names):
            t_on = 0.3 + step * k
            lit = tau >= t_on
            y = y0 + k * (h + gap)
            col = ACCENT if lit and tau < t_on + step else ((70, 200, 130) if lit else (80, 88, 100))
            d.rounded_rectangle((x0, y, x0 + w, y + h), radius=RADIUS, fill=(28, 32, 40) if lit else (22, 25, 31),
                                outline=col, width=3 if lit else 1)
            d.ellipse((x0 + 20, y + h / 2 - 10, x0 + 40, y + h / 2 + 10), fill=col)
            d.text((x0 + 58, y + h / 2), n.upper(), font=font(28), fill=(255, 255, 255) if lit else MUTED_24,
                   anchor="lm")
            if roles.get(n):
                d.text((x0 + w - 20, y + h / 2), roles[n], font=font(24, bold=False),
                       fill=(214, 222, 230) if lit else (90, 98, 110), anchor="rm")
            if k:
                p = window(tau, t_on - 0.2, t_on)
                d.line((x0 + 30, y - gap, x0 + 30, y - gap + gap * p), fill=ACCENT, width=4)
        chips = self.m.get("stack", [])
        cx = 150
        a = window(tau, 4.6, 5.0)
        for c in chips if a > 0 else []:
            f = font(26)
            cw = d.textlength(c, font=f) + 36
            d.rounded_rectangle((cx, 850, cx + cw, 900), radius=RADIUS, fill=(28, 32, 40), outline=ACCENT, width=2)
            d.text((cx + cw / 2, 875), c, font=f, fill=(255, 255, 255), anchor="mm")
            cx += cw + 16

    def _verify(self, im, tau):
        n = int(self.m["checked"])
        glass(im, (360, 250, 1560, 830), 1.0, accent=GOOD)
        d = ImageDraw.Draw(im)
        p = ease_in_out(window(tau, 0.2, 1.4))         # a bar fills; only the real count is ever printed
        d.rounded_rectangle((560, 330, 1360, 346), radius=8, fill=(58, 64, 74))
        d.rounded_rectangle((560, 330, 560 + 800 * max(0.02, p), 346), radius=8, fill=GOOD)
        a = window(tau, 1.3, 1.6)
        d.text((W / 2, 430), f"{n:,} of {n:,}", font=font(120), fill=(255, 255, 255, int(255 * a)), anchor="mm")
        d.text((W / 2, 520), "on-screen numbers checked against the data", font=font(36, bold=False),
               fill=(230, 236, 242), anchor="mm")
        claims = [c for n_ in self.pipe["nodes"] for c in n_.get("claims", []) if any(ch.isdigit() for ch in c["text"])]
        for j, c in enumerate(claims[:3]):
            a = window(tau, 1.6 + 0.35 * j, 1.9 + 0.35 * j)
            if a <= 0:
                continue
            y = 610 + 56 * j
            ev = c.get("evidence", "").split("(")[0].strip()
            d.line((520, y, 530, y + 10, 548, y - 10), fill=(*GOOD,), width=5)
            d.text((570, y), c["text"], font=font(30), fill=(255, 255, 255), anchor="lm")
            d.text((700, y), ev, font=font(26, bold=False), fill=MUTED_24, anchor="lm")

    def _next(self, im, tau):
        items = self.m["next"]
        glass(im, (360, 300, 1560, 780), 1.0, accent=(150, 160, 175))
        d = ImageDraw.Draw(im)
        label = "NEXT · NOT BUILT YET"                     # track B: plans, never shown as done
        lw = d.textlength(label, font=font(30)) + 48
        d.rounded_rectangle((W / 2 - lw / 2, 340, W / 2 + lw / 2, 392), radius=RADIUS, outline=(255, 255, 255), width=2)
        d.text((W / 2, 366), label, font=font(30), fill=(255, 255, 255), anchor="mm")
        for j, it in enumerate(items):
            a = window(tau, 0.3 + 0.4 * j, 0.6 + 0.4 * j)
            if a <= 0:
                continue
            y = 470 + 90 * j
            d.rounded_rectangle((520, y - 34, 1400, y + 34), radius=RADIUS, outline=(150, 160, 175), width=2)
            d.text((W / 2, y), it, font=font(34, bold=False), fill=(230, 236, 242), anchor="mm")


class EndCard(Motion):
    """The close: the wordmark over the frame, blurred and dark; the permission line and the repository link."""

    def background(self, img, tau, cam):
        if not hasattr(self, "_bg"):
            blur = Image.fromarray(img).filter(ImageFilter.GaussianBlur(18))
            self._bg = _dim(np.asarray(blur), 0.72)
        return self._bg

    def overlay(self, im, cam, tau):
        a = window(tau, 0.0, 0.5)
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
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
        im.paste(layer, (0, 0), layer)
