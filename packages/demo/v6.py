"""Video v6 graphics (owner, 23 Oct: broadcast-grade live analytics, no cartoon, no placeholders).

    python -m demo.composite <moment>        # kind live_hud | shot_map | pipeline (demo.live SCENES)

- LiveHUD: over an attacking passage, every frame through its camera: thin lines from the carrier to each teammate in
  view labelled with P(complete) and xG after the pass, the best one glowing, weak ones faded; a broadcast panel
  with the carrier, "Shot now", "Best pass" and a threat meter; the team's xG on a score strip, ticking at each
  shot (track A's live_*.json and xg_race_0; shared note track-c-v6-formats.md).
- ShotMap: the passage's or clip's shots on the real pitch, dots sized by xG, goals ringed.
- Pipeline: the newsroom's real run for one moment as an animated flow beside the frozen frame: each agent node
  lights up in turn with what it did (track B's pipeline_*.json), ending with the line going on air.
Labels: a verified name, else a shirt number, else none. Every printed number is a data value; nothing counts up.
"""

from __future__ import annotations

import json

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from demo.live import (
    FONT,
    FONT_REG,
    MUTED,
    ORANGE,
    PANEL,
    ROOT,
    WHITE,
    H,
    Live,
    Still,
    W,
    bracket,
    ground_circle,
    window,
)

ACCENT = (255, 122, 26)
GOOD = (64, 220, 140)
LINE_MIN_ALPHA = 0.18          # the weakest option's line
BEST_GLOW = 0.30


def who(p: dict | None) -> str | None:
    """A verified name (surname), else a shirt number, else nothing (owner: no placeholders)."""
    if not p:
        return None
    if p.get("name"):
        return p["name"].split()[-1]
    if p.get("shirt"):
        return f"#{p['shirt']}"
    return None


def fmt_xg(v: float | None) -> str:
    return "–" if v is None else f"{v:.2f}"


class LiveHUD(Live):
    """The live analytics layer over a playing attacking passage (track A's live_<start>.json, 10 Hz frames; the
    shared note track-a-v6-live-format.md). A frame that is not trusted, or has no holder, draws nothing."""

    def __init__(self, m: dict):
        super().__init__(m)
        d = self.data
        if "frames" in d and "samples" not in d:          # track A's layout -> the fields drawn here
            d["samples"] = [{**f, "carrier": f.get("holder") if f.get("trusted") else None}
                            for f in d["frames"]]
        lo, hi = m.get("t0"), m.get("t1")
        if lo is not None or hi is not None:
            d["samples"] = [x for x in d["samples"] if (lo or 0) <= x["clip_ms"] / 1000 <= (hi or 1e9)]
            d["start_clip_ms"], d["end_clip_ms"] = d["samples"][0]["clip_ms"], d["samples"][-1]["clip_ms"]
        race = m.get("race")
        if race:
            doc = json.loads((ROOT / race).read_text())
            self.m["race_doc"] = {**doc.get("result", doc), **m.get("race_labels", {})}

    def span(self):
        return (self.data["start_clip_ms"] / 1000 - float(self.m.get("pre_s", 0.3)),
                self.data["end_clip_ms"] / 1000 + float(self.m.get("post_s", 0.3)))

    def sample(self, t: float) -> dict | None:
        """The latest sample at or before t (printed numbers are samples, never interpolations)."""
        s = self.data["samples"]
        i, _, _ = bracket(s, t * 1000)
        x = s[i]
        if abs(x["clip_ms"] - t * 1000) > 2 * float(self.data.get("step_ms", 200)) or not x.get("carrier"):
            return None
        if x.get("shot_now_xg") is None and not any(o.get("xg_after_pass") is not None for o in x.get("options", [])):
            return None                                    # own half or no analytics: nothing on screen
        return x

    def ranked(self, x: dict) -> list[dict]:
        return sorted((o for o in x.get("options", []) if o.get("xg_after_pass") is not None
                       and not o.get("offside_risk")), key=lambda o: -o["xg_after_pass"])

    def ground(self, ax, cam, t):
        x = self.sample(t)
        if x is None:
            return
        c = np.array([x["carrier"]["x"], x["carrier"]["y"]])
        opts = self.ranked(x)
        if not opts:
            return
        top = opts[0]["xg_after_pass"] or 1e-9
        kit = np.array((self.m.get("kits") or {}).get(self.m.get("team", "home"), ACCENT)) / 255
        for k, o in reversed(list(enumerate(opts[: int(self.m.get("max_options", 5))]))):
            end = np.array([o["x"], o["y"]])
            seg = cam.project(np.linspace(c, end, 30))
            best = k == 0
            a = 1.0 if best else max(LINE_MIN_ALPHA, 0.75 * o["xg_after_pass"] / top)
            col = np.array(ACCENT) / 255 if best else np.array((1, 1, 1))
            if best:
                ax.plot(seg[:, 0], seg[:, 1], color=(*col, BEST_GLOW), lw=14, solid_capstyle="round")
            ax.plot(seg[:, 0], seg[:, 1], color=(0, 0, 0, 0.45 * a), lw=5 if best else 3.5, solid_capstyle="round")
            ax.plot(seg[:, 0], seg[:, 1], color=(*col, a), lw=3 if best else 1.6, solid_capstyle="round")
            ring = cam.project(ground_circle(end, 0.8 if best else 0.6))
            ax.plot(ring[:, 0], ring[:, 1], color=(*col, a), lw=2.5 if best else 1.4)
        ring = cam.project(ground_circle(c, 1.0))
        ax.plot(ring[:, 0], ring[:, 1], color=(0, 0, 0, 0.5), lw=6)
        ax.plot(ring[:, 0], ring[:, 1], color=(*kit, 1.0), lw=3)

    def panels(self, im, cam, t):
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        x = self.sample(t)
        a = window(t, self.span()[0], self.span()[0] + 0.3)
        if x is not None and cam is not None:
            opts = self.ranked(x)
            small = ImageFont.truetype(FONT, 20)
            for k, o in enumerate(opts[: int(self.m.get("max_labels", 3))]):      # labels on the best few only
                pt = cam.project([[o["x"], o["y"]]])[0]
                name = who(o)
                text = (f"{name}  " if name else "") + f"{o['p_pass'] * 100:.0f}% · {o['xg_after_pass']:.2f} xG"
                w = d.textlength(text, font=small) + 18
                x0 = float(np.clip(pt[0] - w / 2, 12, W - 12 - w))
                y0 = pt[1] + 18
                col = ACCENT if k == 0 else WHITE
                d.rounded_rectangle((x0, y0, x0 + w, y0 + 30), radius=6, fill=(*PANEL, 215),
                                    outline=(*col, 255 if k == 0 else 120), width=2)
                d.text((x0 + w / 2, y0 + 15), text, font=small, fill=(*col, 255), anchor="mm")
        self._hud(d, x, a)
        self._score(d, t, a)
        im.paste(layer, (0, 0), layer)

    def _hud(self, d: ImageDraw.ImageDraw, x: dict | None, a: float) -> None:
        """Bottom-right broadcast panel: carrier, shot now, best pass, threat meter."""
        w, h = 560, 210
        x0, y0 = W - 96 - w, H - 96 - h
        al = int(255 * a)
        d.rounded_rectangle((x0, y0, x0 + w, y0 + h), radius=10, fill=(*PANEL, int(232 * a)))
        d.rectangle((x0, y0, x0 + w, y0 + 6), fill=(*ACCENT, al))
        f22, f30, f26 = ImageFont.truetype(FONT, 22), ImageFont.truetype(FONT, 30), ImageFont.truetype(FONT_REG, 24)
        d.text((x0 + 24, y0 + 20), "LIVE ANALYTICS", font=f22, fill=(*MUTED, al))
        if x is None:
            d.text((x0 + 24, y0 + 64), "no ball carrier in view", font=f26, fill=(*MUTED, al))
            return
        name = who(x["carrier"])
        d.text((x0 + w - 24, y0 + 18), f"ON THE BALL  {name}" if name else "ON THE BALL", font=f22,
               fill=(255, 255, 255, al), anchor="ra")
        rows = [("Shot now", fmt_xg(x.get("shot_now_xg")) + " xG", WHITE)]
        best = (self.ranked(x) or [None])[0]
        if best is not None:
            bn = who(best)
            rows.append((f"Best pass{' · ' + bn if bn else ''}", f"{best['xg_after_pass']:.2f} xG", ACCENT))
        for k, (label, value, col) in enumerate(rows):
            y = y0 + 58 + 44 * k
            d.text((x0 + 24, y), label, font=f26, fill=(230, 236, 242, al))
            d.text((x0 + w - 24, y + 14), value, font=f30, fill=(*col, al), anchor="rm")
        thr = x.get("threat")
        if thr is not None:
            y = y0 + h - 40
            d.text((x0 + 24, y - 4), "Threat", font=f26, fill=(230, 236, 242, al))
            bx0, bx1 = x0 + 150, x0 + w - 24
            d.rounded_rectangle((bx0, y + 4, bx1, y + 18), radius=7, fill=(255, 255, 255, int(30 * a)))
            col = GOOD if thr < 0.33 else (255, 214, 10) if thr < 0.66 else (235, 60, 60)
            d.rounded_rectangle((bx0, y + 4, bx0 + max(14, (bx1 - bx0) * thr), y + 18), radius=7, fill=(*col, al))

    def _score(self, d: ImageDraw.ImageDraw, t: float, a: float) -> None:
        """Top strip under the broadcast score bug: each team's cumulative xG so far (xg_race_0)."""
        race = self.m.get("race_doc")
        if not race:
            return
        now = t * 1000
        pts = [p for p in race["series"] if p["clip_ms"] <= now] or [{"home_xg": 0.0, "away_xg": 0.0}]
        cur = pts[-1]
        f = ImageFont.truetype(FONT, 24)
        text = f"xG  {race['home_short']} {cur['home_xg']:.2f} · {cur['away_xg']:.2f} {race['away_short']}"
        x0, y0 = float(self.m.get("score_x", 96)), float(self.m.get("score_y", 168))   # below the broadcast bug
        w = d.textlength(text, font=f) + 32
        d.rounded_rectangle((x0, y0, x0 + w, y0 + 40), radius=8, fill=(*PANEL, int(225 * a)))
        d.text((x0 + 16, y0 + 20), text, font=f, fill=(255, 255, 255, int(255 * a)), anchor="lm")


class ShotMap(Still):
    """The passage's shots on the real pitch, dots sized by xG (unmeasured: a small hollow mark), goals ringed."""

    needs_camera = True

    def shots(self) -> list[dict]:
        s = self.data["shots"]
        lo, hi = self.m.get("from_ms", -1), self.m.get("to_ms", 1e12)
        team = self.m.get("team_filter")
        return [x for x in s if lo <= x["clip_ms"] <= hi and (team is None or x.get("team") == team)
                and x.get("x") is not None]

    def dim(self, t):
        return 0.35 * window(self.tau(t), 0.0, 0.5)

    def ground(self, ax, cam, t):
        tau = self.tau(t)
        for k, x in enumerate(self.shots()):
            a = window(tau, 0.3 + 0.25 * k, 0.6 + 0.25 * k)
            if a <= 0:
                continue
            c = np.array([x["x"], x["y"]])
            r = 0.45 + 1.6 * (x["xg"] or 0.0) if x.get("xg") is not None else 0.4     # 0.45 m to 2 m
            col = np.array((self.m.get("kits") or {}).get(x.get("team", "home"), ACCENT)) / 255
            disc = cam.project(ground_circle(c, r, 48))
            from matplotlib.patches import Polygon
            ax.add_patch(Polygon(disc, closed=True, fc=(*col, (0.85 if x.get("xg") is not None else 0.0) * a),
                                 ec=(1, 1, 1, a), lw=2))
            if x.get("outcome") == "goal":
                ring = cam.project(ground_circle(c, r + 0.45, 48))
                ax.plot(ring[:, 0], ring[:, 1], color=(1, 1, 1, a), lw=3)

    def panels(self, im, cam, t):
        tau = self.tau(t)
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        f = ImageFont.truetype(FONT, 22)
        for k, x in enumerate(self.shots()):
            a = window(tau, 0.5 + 0.25 * k, 0.8 + 0.25 * k)
            if a <= 0 or x.get("xg") is None:
                continue
            pt = cam.project([[x["x"], x["y"]]])[0]
            name = who(x.get("shooter"))
            text = (f"{name} " if name else "") + f"{x['xg']:.2f}" + (" · GOAL" if x.get("outcome") == "goal" else "")
            d.text((pt[0], pt[1] - 26), text, font=f, fill=(255, 255, 255, int(255 * a)), anchor="mb",
                   stroke_width=3, stroke_fill=(0, 0, 0, int(200 * a)))
        a = window(tau, 0.2, 0.6)
        d.text((96, 120), self.m.get("label", "SHOT MAP").upper(), font=ImageFont.truetype(FONT, 34),
               fill=(255, 255, 255, int(255 * a)), stroke_width=4, stroke_fill=(0, 0, 0, int(200 * a)))
        im.paste(layer, (0, 0), layer)


class Pipeline(Still):
    """The newsroom's real run for one moment, as an animated flow on the right of the frozen frame (dimmed): each
    agent node lights up in turn with what it did, the claims tick, and the line goes on air."""

    needs_camera = False
    STEP_S = 0.9

    def dim(self, t):
        return 0.55 * window(self.tau(t), 0.0, 0.4)

    def at_ms(self) -> int:
        return int(self.m["clip_ms"])

    def panels(self, im, cam, t):
        tau = self.tau(t) - 0.3
        nodes = self.data["nodes"]
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        f_title = ImageFont.truetype(FONT, 22)
        f_agent = ImageFont.truetype(FONT, 26)
        f_says = ImageFont.truetype(FONT_REG, 22)
        x0, w = W - 96 - 760, 760
        y = 230                                            # below the broadcast's own logo
        d.text((x0, y - 50), "THE NEWSROOM, LIVE ON THIS MOMENT", font=f_title, fill=(*MUTED, 255))
        for k, n in enumerate(nodes):
            on = window(tau, k * self.STEP_S, k * self.STEP_S + 0.3)
            if on <= 0:
                break
            lit = tau < (k + 1) * self.STEP_S or k == len(nodes) - 1
            lines = self._lines(n)
            h = 50 + 30 * len(lines)
            col = ACCENT if lit else (110, 120, 132)
            d.rounded_rectangle((x0, y, x0 + w, y + h), radius=10, fill=(*PANEL, int(235 * on)),
                                outline=(*col, int(255 * on)), width=3 if lit else 1)
            d.ellipse((x0 + 18, y + 18, x0 + 34, y + 34), fill=(*col, int(255 * on)))
            d.text((x0 + 48, y + 14), n["agent"].upper(), font=f_agent, fill=(255, 255, 255, int(255 * on)))
            if n.get("latency_ms") is not None:
                d.text((x0 + w - 18, y + 16), f"{n['latency_ms']} ms", font=f_says,
                       fill=(*MUTED, int(255 * on)), anchor="ra")
            for j, (text, colour, mark) in enumerate(lines):
                tx = x0 + 48
                if mark is not None:                       # a drawn tick or cross (the fonts have no glyph)
                    yy = y + 50 + 30 * j + 12
                    if mark:
                        d.line((tx, yy, tx + 6, yy + 6, tx + 16, yy - 6), fill=(*GOOD, int(255 * on)), width=4)
                    else:
                        d.line((tx, yy - 6, tx + 12, yy + 6), fill=(*ORANGE, int(255 * on)), width=4)
                        d.line((tx, yy + 6, tx + 12, yy - 6), fill=(*ORANGE, int(255 * on)), width=4)
                    tx += 26
                d.text((tx, y + 50 + 30 * j), text, font=f_says, fill=(*colour, int(255 * on)))
            y += h + 14
            if k < len(nodes) - 1:
                d.line((x0 + 26, y - 14, x0 + 26, y), fill=(*col, int(200 * on)), width=3)
        im.paste(layer, (0, 0), layer)

    @staticmethod
    def _lines(n: dict) -> list[tuple[str, tuple]]:
        out = []
        if n.get("says"):
            out.append((n["says"], (230, 236, 242), None))
        for c in n.get("claims", []):
            out.append((c["text"] + (f"  ({c['evidence']})" if c.get("evidence") else ""),
                        GOOD if c.get("ok") else ORANGE, bool(c.get("ok"))))
        if n.get("line"):
            out.append((f"ON AIR: {n['line']}", ACCENT, None))
        return out
