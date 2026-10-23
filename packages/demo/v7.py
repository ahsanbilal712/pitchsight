"""Video v7: analytics on every frame (owner, 23 Oct: "keep it analytics full").

An always-on layer from player positions alone (track A cache/v7 always_<start_ms>.json: pitch control, dangerous
space in view per team, team shape), drawn under v6's ball layer (carrier, shot now, best pass, priced pass lines). The
panel never blanks: between carriers it shows the defending side's shape. Format: track-c-v7-formats.md.

Until track A's file lands a beat can run on a STAND-IN computed here from v6's tracked positions (a soft Voronoi,
the deepest defenders): drawn for the look only, watermarked, and no number of it is ever printed.
"""

from __future__ import annotations

import base64
import json

import numpy as np
from PIL import ImageDraw, ImageFont

from demo.live import FONT, FONT_REG, MUTED, PANEL, ROOT, H, W, bracket
from demo.v6 import ACCENT, LiveHUD, fmt_xg

TINT_ALPHA = 0.16              # the control tint stays under everything
LINE_ALPHA = 0.55              # team lines, the back line a step stronger
DANGER_H = 104                 # the always-on card stacked over the v6 panel
SEEN_M = 12.0                  # control is tinted only this close to a tracked player
SHAPE_MIN = 3                  # stand-in: a line needs this many players of one side in view


def _decode(c, grid: dict) -> np.ndarray:
    if isinstance(c, str):
        a = np.frombuffer(base64.b64decode(c), np.uint8).astype(float) / 255
        return a.reshape(grid["ny"], grid["nx"])
    return np.asarray(c, float)


class AlwaysOn(LiveHUD):
    """A v6 live beat with the always-on layer under it."""

    hud_above = DANGER_H + 16

    def __init__(self, m: dict):
        super().__init__(m)
        self.always = None
        if m.get("always"):
            doc = json.loads((ROOT / m["always"]).read_text())
            self.always = doc.get("result", doc)
        self.standin = self.always is None
        self.kits = {k: np.array(v) / 255 for k, v in (m.get("kits") or {}).items()}

    # -- the always-on data at t ----------------------------------------------------------------------------------
    def layer(self, t: float) -> dict | None:
        """{control (ny, nx) P(home), grid, danger {home, away} | None, shape {home, away}, defending}."""
        if self.always is not None:
            fr = self.always["frames"]
            i, _, _ = bracket(fr, t * 1000)
            f = fr[i]
            if not f.get("trusted") or f.get("control") is None or abs(f["clip_ms"] - t * 1000) > 150:
                return None
            att = self._attacking(t)
            return {"control": _decode(f["control"], self.always["grid"]), "grid": self.always["grid"],
                    "seen": self._seen(t),
                    "danger": f.get("danger"), "shape": f.get("shape") or {},
                    "defending": {"home": "away", "away": "home"}.get(att)}
        return self._standin(t)

    def _attacking(self, t: float) -> str | None:
        s = self.data["samples"]
        i, _, _ = bracket(s, t * 1000)
        return s[i].get("attacking") or self.m.get("team")

    def _home_attacks_plus(self) -> bool:
        return self.data.get("home_attacks", "+x") == "+x"

    def _standin(self, t: float) -> dict | None:
        s = self.data["samples"]
        i, _, _ = bracket(s, t * 1000)
        f = s[i]
        ps = [p for p in f.get("players") or [] if p.get("team") in ("home", "away")]
        if not f.get("trusted") or len(ps) < 6:
            return None
        grid = {"x0": 0.0, "y0": 0.0, "dx": 2.0, "dy": 2.0, "nx": 53, "ny": 35}
        gx = grid["x0"] + grid["dx"] * np.arange(grid["nx"])
        gy = grid["y0"] + grid["dy"] * np.arange(grid["ny"])
        X, Y = np.meshgrid(gx, gy)
        dmin = {}
        for team in ("home", "away"):
            pts = np.array([[p["x"], p["y"]] for p in ps if p["team"] == team])
            dmin[team] = (np.min(np.hypot(X[..., None] - pts[:, 0], Y[..., None] - pts[:, 1]), axis=2)
                          if len(pts) else np.full(X.shape, 99.0))
        control = 1 / (1 + np.exp(-(dmin["away"] - dmin["home"]) / 2.0))
        att = self._attacking(t)
        defending = {"home": "away", "away": "home"}.get(att)
        shape = {}
        if defending:
            goal_x = 0.0 if (defending == "home") == self._home_attacks_plus() else 105.0
            outs = sorted((p for p in ps if p["team"] == defending and not p.get("keeper")),
                          key=lambda p: abs(p["x"] - goal_x))
            if len(outs) >= SHAPE_MIN:
                deep = abs(outs[0]["x"] - goal_x)
                back = [p for p in outs if abs(p["x"] - goal_x) <= deep + 8][:5]
                rest = [p for p in outs if p not in back]
                lines = [sorted(back, key=lambda p: p["y"])]
                if len(rest) >= SHAPE_MIN:
                    lines.append(sorted(rest[:5], key=lambda p: p["y"]))
                shape[defending] = {"lines": [[[p["x"], p["y"]] for p in ln] for ln in lines if len(ln) >= 2]}
        return {"control": control, "grid": grid, "danger": None, "shape": shape, "defending": defending,
                "seen": [[p["x"], p["y"]] for p in ps]}

    def _seen(self, t: float) -> list:
        s = self.data["samples"]
        i, _, _ = bracket(s, t * 1000)
        return [[p["x"], p["y"]] for p in s[i].get("players") or []]

    # -- drawing --------------------------------------------------------------------------------------------------
    def ground(self, ax, cam, t):
        lay = self.layer(t)
        if lay is not None and cam is not None:
            self._tint(ax, cam, lay)
            self._shape(ax, cam, lay)
        super().ground(ax, cam, t)

    def _tint(self, ax, cam, lay) -> None:
        g = lay["grid"]
        gx = g["x0"] + g["dx"] * np.arange(g["nx"])
        gy = g["y0"] + g["dy"] * np.arange(g["ny"])
        X, Y = np.meshgrid(gx, gy)
        px = cam.project(np.c_[X.ravel(), Y.ravel()]).reshape(*X.shape, 2)
        seen = np.array(lay.get("seen") or [[-99.0, -99.0]])     # only near players in view: no guessed space
        near = np.min(np.hypot(X[..., None] - seen[:, 0], Y[..., None] - seen[:, 1]), axis=2) <= SEEN_M
        control = np.ma.masked_where(~near, lay["control"])
        home, away = self.kits.get("home", np.array(ACCENT) / 255), self.kits.get("away", (1, 1, 1))
        lv = [0, 0.15, 0.35, 0.65, 0.85, 1.0001]           # graded: strongest where one side owns it outright
        al = [TINT_ALPHA, TINT_ALPHA * 0.5, 0, TINT_ALPHA * 0.5, TINT_ALPHA]
        cols = [(*away, al[0]), (*away, al[1]), (0, 0, 0, 0), (*home, al[3]), (*home, al[4])]
        ax.contourf(px[..., 0], px[..., 1], control, levels=lv, colors=cols, antialiased=True)
        ax.contour(px[..., 0], px[..., 1], control, levels=[0.5], colors=[(1, 1, 1, 0.30)], linewidths=1.2)

    def _shape(self, ax, cam, lay) -> None:
        for team, sh in (lay.get("shape") or {}).items():
            if not sh:
                continue
            kit = self.kits.get(team, np.array((1, 1, 1)))
            for k, ln in enumerate(sh.get("lines") or ([sh["back_line"]] if sh.get("back_line") else [])):
                pts = cam.project(np.asarray(ln, float))
                a = LINE_ALPHA if k == 0 else LINE_ALPHA * 0.6
                ax.plot(pts[:, 0], pts[:, 1], color=(0, 0, 0, a * 0.5), lw=5, solid_capstyle="round")
                ax.plot(pts[:, 0], pts[:, 1], color=(*kit, a), lw=2.4 if k == 0 else 1.6, solid_capstyle="round",
                        dashes=() if k == 0 else (5, 3))

    def _hud(self, d: ImageDraw.ImageDraw, x, a, age=None, state=None, threat=None) -> None:
        t = self._t
        lay = self.layer(t)
        self._danger(d, lay, a)
        if x is not None:
            super()._hud(d, x, a, age, state, threat)
            return
        w, h = self.hud_w, self.hud_h                     # between carriers: the defending side's shape
        x0, y0 = W - 64 - w, H - 64 - h
        al = int(255 * a)
        d.rounded_rectangle((x0, y0, x0 + w, y0 + h), radius=14, fill=(*PANEL, int(235 * a)))
        d.rectangle((x0, y0, x0 + w, y0 + 8), fill=(*ACCENT, al))
        f_small, f_label = ImageFont.truetype(FONT, 26), ImageFont.truetype(FONT_REG, 32)
        f_value = ImageFont.truetype(FONT, 56)
        d.text((x0 + 28, y0 + 26), "THEIR SHAPE", font=f_small, fill=(*MUTED, al))
        if state:
            d.text((x0 + w - 28, y0 + 26), state, font=f_small, fill=(255, 214, 10, al), anchor="ra")
        sh = ((lay or {}).get("shape") or {}).get((lay or {}).get("defending")) or {}
        rows = [("Width", sh.get("width_m")), ("Depth", sh.get("depth_m")), ("Line gap", sh.get("line_gap_m"))]
        if all(v is None for _, v in rows):                 # fixed slots: the numbers come and go, the panel stays
            d.text((x0 + 28, y0 + h - 50), "shown when 9 of their 10 outfielders are in view", font=ImageFont.truetype(
                FONT_REG, 24), fill=(*MUTED, al))
        for k, (label, v) in enumerate(rows):
            cx = x0 + 28 + k * (w - 56) // 3
            d.text((cx, y0 + 90), label, font=f_label, fill=(230, 236, 242, al))
            d.text((cx, y0 + 134), "–" if v is None else f"{v:.0f}", font=f_value, fill=(255, 255, 255, al))
            if v is not None:
                d.text((cx + d.textlength(f"{v:.0f}", font=f_value) + 8, y0 + 158), "m", font=f_label,
                       fill=(255, 255, 255, al))

    def _danger(self, d, lay, a) -> None:
        """One split bar: each side's share of the dangerous space, in its kit colour, the numbers at the ends."""
        w, h = self.hud_w, DANGER_H
        x0, y0 = W - 64 - w, H - 64 - self.hud_h - 16 - h
        al = int(255 * a)
        d.rounded_rectangle((x0, y0, x0 + w, y0 + h), radius=14, fill=(*PANEL, int(235 * a)))
        f_small, f_team = ImageFont.truetype(FONT, 26), ImageFont.truetype(FONT, 30)
        d.text((x0 + 28, y0 + 16), "DANGEROUS SPACE IN VIEW", font=f_small, fill=(*MUTED, al))
        if self.standin:
            d.text((x0 + w - 28, y0 + 16), "STAND-IN, NO NUMBERS", font=f_small, fill=(255, 90, 90, al), anchor="ra")
        race = self.m.get("race_doc") or {}
        danger = (lay or {}).get("danger") or {}
        kit = {k: tuple(int(v * 255) for v in self.kits.get(k, np.array((1, 1, 1)))) for k in ("home", "away")}
        y = y0 + 58
        hs, as_ = race.get("home_short", "HOME"), race.get("away_short", "AWAY")
        d.text((x0 + 28, y + 14), hs, font=f_team, fill=(255, 255, 255, al), anchor="lm")
        d.text((x0 + w - 28, y + 14), as_, font=f_team, fill=(255, 255, 255, al), anchor="rm")
        bx0 = x0 + 40 + d.textlength(hs, font=f_team)
        bx1 = x0 + w - 40 - d.textlength(as_, font=f_team)
        d.rounded_rectangle((bx0, y, bx1, y + 28), radius=14, fill=(58, 64, 74, al))
        hv, av = danger.get("home"), danger.get("away")
        if hv is None or av is None or self.standin:
            return
        split = bx0 + (bx1 - bx0) * hv / max(1e-9, hv + av)
        d.rounded_rectangle((bx0, y, split, y + 28), radius=14, fill=(*kit["home"], al))
        d.rounded_rectangle((split, y, bx1, y + 28), radius=14, fill=(*kit["away"], al))
        f_val = ImageFont.truetype(FONT, 24)
        d.text((bx0 + 14, y + 14), fmt_xg(hv), font=f_val, fill=(255, 255, 255, al), anchor="lm")
        d.text((bx1 - 14, y + 14), fmt_xg(av), font=f_val, fill=(20, 24, 30, al), anchor="rm")

    def panels(self, im, cam, t):
        self._t = t
        super().panels(im, cam, t)
        if self.standin:
            d = ImageDraw.Draw(im)
            d.text((W // 2, 24), "STAND-IN ALWAYS-ON LAYER (v6 positions): LOOK ONLY", font=ImageFont.truetype(FONT, 24),
                   fill=(255, 80, 80), anchor="ma")

