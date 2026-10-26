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
from collections import Counter

import numpy as np
from PIL import ImageDraw, ImageFont

from demo.live import FONT, FONT_REG, MUTED, ROOT, H, W, bracket
from demo.v6 import ACCENT, LiveHUD, shrink

TINT_ALPHA = 0.10              # the control tint stays under everything
LINE_ALPHA = 0.55              # team lines, the back line a step stronger
DANGER_H = 172                 # the always-on card stacked over the v6 panel
DANGER_DEF = "weighted by xG: the share of the scoring danger in front of goal they would reach first"
SEEN_M = 12.0
EMA_S = 0.5                    # v9: the tint and the danger bar's time constant
HIDE_S = 1.0                   # v9: the layer hides only after this long without data
HOLD_TEXT_S = 0.5              # v9: a printed danger sentence stays at least this long                  # control is tinted only this close to a tracked player
SHAPE_MIN = 3                  # stand-in: a line needs this many players of one side in view


def _decode(c: str, grid: dict) -> np.ma.MaskedArray:
    """Track A's control grid: base64 uint8, row-major y then x, P(home) x 254; 255 = cell not in view."""
    a = np.frombuffer(base64.b64decode(c), np.uint8).reshape(grid["ny"], grid["nx"])
    return np.ma.masked_where(a == 255, a.astype(float) / 254)


class AlwaysOn(LiveHUD):
    """A v6 live beat with the always-on layer under it."""

    hud_above = DANGER_H + 16

    @property
    def danger_h(self) -> int:
        return 158 if self.v8 else DANGER_H

    def __init__(self, m: dict):
        super().__init__(m)
        self.always = None
        if m.get("always"):
            doc = json.loads((ROOT / m["always"]).read_text())
            self.always = doc.get("result", doc)
        self.standin = self.always is None
        if self.v8:
            self.hud_above = 158 + 16
        self.kits = {k: np.array(v) / 255 for k, v in (m.get("kits") or {}).items()}

    # -- the always-on data at t ----------------------------------------------------------------------------------
    def layer(self, t: float) -> dict | None:
        """{control (ny, nx) P(home), grid, danger {home, away} | None, shape {home, away}, defending}."""
        if self.always is not None and self.v9:
            return self._steady(t)
        if self.always is not None:                       # track A's v7/always_<start>.json (5acf68e)
            fr = self.always["frames"]
            i, _, _ = bracket(fr, t * 1000)
            f = fr[i]
            if not f.get("trusted") or abs(f["clip_ms"] - t * 1000) > 150:
                return None
            g = self.always["grid"]
            grid = {"x0": g["x0"] + g["dx"] / 2, "y0": g["y0"] + g["dy"] / 2, "dx": g["dx"], "dy": g["dy"],
                    "nx": g["nx"], "ny": g["ny"]}
            zone = f.get("danger_zone") or {}
            att = zone.get("attacked_by") or self._attacking(t)
            return {"control": _decode(f["control"], g) if f.get("control") else None, "grid": grid,
                    "danger": f.get("danger"), "attacker": zone.get("attacked_by"), "shape": f.get("shape") or {},
                    "defending": {"home": "away", "away": "home"}.get(att)}
        return self._standin(t)

    def _steady(self, t: float) -> dict | None:
        """v9: the layer without flicker. The tint and the danger bar follow an EMA (time constant EMA_S) of the
        frames so far; the layer hides only after more than HIDE_S of nulls. The printed sentence is always a real
        frame's own (held at least HOLD_TEXT_S before it changes), never a smoothed number."""
        fr = self.always["frames"]
        t_ms = t * 1000
        i, _, _ = bracket(fr, t_ms)
        g = self.always["grid"]
        ctrl = share = shown = None
        shown_at = last_ok = last_share = None
        last = None
        k = 1 - np.exp(-0.1 / EMA_S)
        for f in fr[max(0, i - 40): i + 1]:
            if f["clip_ms"] > t_ms + 50:
                break
            if f.get("trusted") and f.get("control"):
                c = _decode(f["control"], g).filled(np.nan)
                if ctrl is None:
                    ctrl = c
                else:
                    ctrl = np.where(np.isnan(c), ctrl, np.where(np.isnan(ctrl), c, ctrl + k * (c - ctrl)))
                last_ok, last = f["clip_ms"], f
            dz = f.get("danger") or {}
            if dz.get("share") is not None:
                share = dz["share"] if share is None else share + k * (dz["share"] - share)
                last_share = f["clip_ms"]
                if shown is None or (f["clip_ms"] - shown_at >= HOLD_TEXT_S * 1000 and dz.get("text") != shown.get("text")):
                    shown, shown_at = dz, f["clip_ms"]
        if last is None or t_ms - last_ok > HIDE_S * 1000:
            return None
        grid = {"x0": g["x0"] + g["dx"] / 2, "y0": g["y0"] + g["dy"] / 2, "dx": g["dx"], "dy": g["dy"],
                "nx": g["nx"], "ny": g["ny"]}
        zone = last.get("danger_zone") or {}
        att = zone.get("attacked_by") or self._attacking(t)
        danger = None
        if shown is not None and t_ms - last_share <= HIDE_S * 1000:
            danger = {**shown, "share": shown["share"], "bar": float(np.clip(share, 0, 1))}
        return {"control": np.ma.masked_invalid(ctrl), "grid": grid, "danger": danger,
                "attacker": zone.get("attacked_by"), "shape": last.get("shape") or {},
                "defending": {"home": "away", "away": "home"}.get(att)}

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
        if self.v9:
            self._boxes(ax, t)
        lay = self.layer(t)
        if lay is not None and cam is not None:
            if lay.get("control") is not None:
                self._tint(ax, cam, lay)
            self._shape(ax, cam, lay)
        super().ground(ax, cam, t)

    def _tracks(self) -> list[dict]:
        """Track A's per-frame boxes for this beat's camera shot, with each track's side (home/away) from the live
        frames' labels; a track the live frames never label takes its kit cluster's majority side."""
        if hasattr(self, "_trk"):
            return self._trk
        path = ROOT / "data" / "footage" / self.m["clip"] / "tracks" / f"{self.m.get('shot_id')}.json"
        doc = json.loads(path.read_text()) if path.exists() else {"frames": []}
        doc = doc.get("result", doc)
        side, votes = {}, {}
        for x in self.data["samples"]:
            for p in x.get("players") or []:
                if p.get("team") in ("home", "away") and p.get("track_id") is not None:
                    side[p["track_id"]] = p["team"]
        for f in doc["frames"]:
            for p in f.get("players") or []:
                if p.get("track_id") in side and p.get("team") is not None:
                    votes.setdefault(str(p["team"]), Counter())[side[p["track_id"]]] += 1
        cluster = {k: v.most_common(1)[0][0] for k, v in votes.items()}
        for f in doc["frames"]:
            for p in f.get("players") or []:
                p["_side"] = side.get(p.get("track_id")) or cluster.get(str(p.get("team")))
        self._trk = doc["frames"]
        return self._trk

    def _boxes(self, ax, t: float) -> None:
        """v9: a thin rounded box in the team colour on every player track A detects in this frame; the ball
        carrier's box gets orange corner accents."""
        from matplotlib.patches import FancyBboxPatch
        fr = self._tracks()
        if not fr:
            return
        if not hasattr(self, "_trk_t"):
            self._trk_t = np.array([x["t"] for x in fr])
        j = int(np.clip(np.searchsorted(self._trk_t, t), 1, len(fr) - 1))
        f = fr[j] if abs(self._trk_t[j] - t) < abs(self._trk_t[j - 1] - t) else fr[j - 1]
        if abs(f["t"] - t) > 0.06:
            return
        s = self.sample(t)
        carrier = ((s or {}).get("carrier") or {}).get("track_id")
        for p in f.get("players") or []:
            if p.get("role") == "referee":                  # players and keepers; never the officials
                continue
            x0, y0, x1, y1 = p["bbox"]
            col = self.kits.get(p.get("_side"), np.array((0.85, 0.87, 0.9)))
            ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0, boxstyle="round,pad=0,rounding_size=5",
                                        fc="none", ec=(*col, 0.85), lw=1.3))
            if p.get("track_id") == carrier:
                acc = np.array(ACCENT) / 255
                L = min(x1 - x0, y1 - y0) * 0.35
                for cx, cy, sx, sy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
                    ax.plot([cx, cx + sx * L], [cy, cy], color=(*acc, 1), lw=2.6, solid_capstyle="round")
                    ax.plot([cx, cx], [cy, cy + sy * L], color=(*acc, 1), lw=2.6, solid_capstyle="round")

    def _tint(self, ax, cam, lay) -> None:
        g = lay["grid"]
        gx = g["x0"] + g["dx"] * np.arange(g["nx"])
        gy = g["y0"] + g["dy"] * np.arange(g["ny"])
        X, Y = np.meshgrid(gx, gy)
        px = cam.project(np.c_[X.ravel(), Y.ravel()]).reshape(*X.shape, 2)
        control = lay["control"]
        if lay.get("seen") is not None:                   # stand-in: only near players in view, no guessed space
            seen = np.array(lay["seen"])
            near = np.min(np.hypot(X[..., None] - seen[:, 0], Y[..., None] - seen[:, 1]), axis=2) <= SEEN_M
            control = np.ma.masked_where(~near, control)
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
            lines = sh.get("lines") or ([sh["back_line"]] if sh.get("back_line") else [])
            for k, ln in enumerate(lines):
                if isinstance(ln, dict):                   # track A: {points, x, y_min, y_max, n}
                    ln = ln.get("points") or []
                if len(ln) < 2:
                    continue
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
        sh = ((lay or {}).get("shape") or {}).get((lay or {}).get("defending")) or {}
        if sh.get("width_m") is None:                     # track A's 9-of-10 gate failed: the tint and line only
            return
        w, h = self.hud_w, self.hud_h                     # between carriers: the defending side's shape
        x0, y0 = W - 64 - w, H - self.bottom - h
        al = int(255 * a)
        self._panel(d, (x0, y0, x0 + w, y0 + h), a)
        f_label = ImageFont.truetype(FONT_REG, 32)
        f_value = ImageFont.truetype(FONT, 56)
        self._header(d, x0, y0, w, "THEIR SHAPE", state, (255, 214, 10), al)
        rows = [("Width", sh.get("width_m")), ("Depth", sh.get("depth_m")),
                ("Line gap", sh.get("back_to_mid_m", sh.get("line_gap_m")))]
        for k, (label, v) in enumerate(rows):
            cx = x0 + 28 + k * (w - 56) // 3
            d.text((cx, y0 + 90), label, font=f_label, fill=(230, 236, 242, al))
            d.text((cx, y0 + 134), "–" if v is None else f"{v:.0f}", font=f_value, fill=(255, 255, 255, al))
            if v is not None:
                d.text((cx + d.textlength(f"{v:.0f}", font=f_value) + 8, y0 + 158), "m", font=f_label,
                       fill=(255, 255, 255, al))

    def _danger(self, d, lay, a) -> None:
        """The attacking side's one number: its control of the danger zone in view (track A's dangerous_space, the
        visible region; null under half the zone in view). Track A's own definition sits under it, verbatim."""
        w, h = self.hud_w, self.danger_h
        x0, y0 = W - 64 - w, H - self.bottom - self.hud_h - 16 - h
        al = int(255 * a)
        self._panel(d, (x0, y0, x0 + w, y0 + h), a)
        f_small, f_big, f_note = (ImageFont.truetype(FONT, 24), ImageFont.truetype(FONT, 32),
                                  ImageFont.truetype(FONT_REG, 20))
        box = None                                         # name the box: the defending side's goal in view
        dz = (lay or {}).get("danger") or {}
        if dz.get("team") in ("home", "away"):
            other = {"home": "away", "away": "home"}[dz["team"]]
            box = (self.m.get("race_doc") or {}).get(f"{other}_short")
        d.text((x0 + 28, y0 + 14), "DANGER ZONE IN VIEW" + (f" · {box} BOX" if box else ""), font=f_small,
               fill=(*MUTED, al))
        if self.standin:
            d.text((x0 + w - 28, y0 + 14), "STAND-IN, NO NUMBERS", font=f_small, fill=(255, 90, 90, al), anchor="ra")
        danger = (lay or {}).get("danger") or {}
        y = y0 + 50
        bx0, bx1 = x0 + 28, x0 + w - 28
        if "share" in danger:                              # track A: the attacking side's one number, its own words
            team, v, text = danger.get("team"), danger.get("share"), danger.get("text")
        else:
            team = (lay or {}).get("attacker")
            v, text = danger.get(team) if team else None, None
        if v is None or self.standin or not text:
            d.text((bx0, y), "the danger zone is not in view" if lay else "waiting for the camera",
                   font=f_big, fill=(*MUTED, al))
        else:
            kit = tuple(int(c * 255) for c in self.kits.get(team, np.array((1, 1, 1))))
            if self.v8:                                    # two lines at 28 px, never under 24, never cut
                f28 = ImageFont.truetype(FONT, 28)          # a sentence swaps whole (its share changes every few
                for k, ln in enumerate(self._wrap(d, text, f28, bx1 - bx0)[:2]):   # frames; a roll would garble it)
                    d.text((bx0, y - 6 + 38 * k), ln, font=f28, fill=(255, 255, 255, al))
                y += 40
            else:
                d.text((bx0, y), text, font=shrink(d, text, FONT, 32, bx1 - bx0), fill=(255, 255, 255, al))
            d.rounded_rectangle((bx0, y + 44, bx1, y + 60), radius=8, fill=(58, 64, 74, al))
            bar = danger.get("bar", v)                      # v9: the bar eases; the sentence is the frame's own
            d.rounded_rectangle((bx0, y + 44, bx0 + max(16, (bx1 - bx0) * bar), y + 60), radius=8, fill=(*kit, al))
        if not self.v8:                                    # v8: the caption explains it once; nothing under 24 px
            for k, ln in enumerate(self._wrap(d, DANGER_DEF, f_note, bx1 - bx0)):   # never cut: two lines
                d.text((bx0, y0 + h - 54 + 24 * k), ln, font=f_note, fill=(*MUTED, al))

    def _prev_text(self, text: str) -> tuple[str | None, float]:
        """The danger sentence shown before this one and how long ago it changed (for the roll)."""
        prev, since, cur = None, 99.0, None
        for f in (self.always or {}).get("frames", []):
            if f["clip_ms"] > self._t * 1000:
                break
            v = (f.get("danger") or {}).get("text")
            if v and v != cur:
                prev, cur, since = cur, v, self._t - f["clip_ms"] / 1000
        return (prev if cur == text else None), since

    def panels(self, im, cam, t):
        self._t = t
        super().panels(im, cam, t)
        if self.standin:
            d = ImageDraw.Draw(im)
            d.text((W // 2, 24), "STAND-IN ALWAYS-ON LAYER (v6 positions): LOOK ONLY", font=ImageFont.truetype(FONT, 24),
                   fill=(255, 80, 80), anchor="ma")

