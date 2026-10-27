"""Video v6 graphics (23 Oct: broadcast-grade live analytics, no cartoon, no placeholders).

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
import re

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
    HiDraw,
    Live,
    Still,
    W,
    bracket,
    flatten,
    ground_circle,
    hi_layer,
    window,
)

ACCENT = (255, 122, 26)
GOOD = (64, 220, 140)
LINE_MIN_ALPHA = 0.18          # the weakest option's line
FRESH_S = 0.3                  # a sample this recent is live: lines on the pitch
THREAT_FULL = 0.30             # the threat meter is full at 0.30 xG (shot now or the best pass)
DRAW_ON_MS = 150               # a new option's line draws on
PULSE_S = 1.2                  # the best option's glow pulses this slowly
LABEL_PX = 30                  # pass labels (phone-legible)
HUD_W, HUD_H = 760, 290        # the live panel, bottom right
V8_BOTTOM = 150                # v8: the analytics stack ends here, the caption line below it
RADIUS = 14                    # v8: one corner radius for every panel and pill
ROLL_S = 0.06                  # a changed number crossfades over 2 frames (data changes at 10 Hz); no in-between values
HOLD_FADE_S = 1.0              # a held value starts fading after this
STATES = {"ball loose": "BALL LOOSE", "ball out of play": "OUT OF PLAY", "dead ball after the goal": "OUT OF PLAY",
          "ball not detected": "TRACKING THE BALL…", "camera fit not trusted": "CAMERA MOVING…",
          "possession unsettled": "CONTESTED", "own half": "BUILDING FROM THE BACK"}
HOLD_S = 2.0                   # the panel holds the last value this long, with its age
BEST_GLOW = 0.30


SHIRTS_VERIFIED = False        # track B: print a live shirt number only once their per-passage list is in


def ease_in_out(f: float) -> float:
    return 0.5 - 0.5 * np.cos(np.pi * min(1.0, max(0.0, f)))


def threat_colour(frac: float) -> tuple[int, int, int]:
    """Green to amber to red as the threat rises."""
    stops = [(0.0, (64, 220, 140)), (0.4, (255, 214, 10)), (1.0, (235, 60, 60))]
    for (f0, c0), (f1, c1) in zip(stops, stops[1:], strict=False):
        if frac <= f1:
            u = (frac - f0) / (f1 - f0)
            return tuple(int(a + (b - a) * u) for a, b in zip(c0, c1, strict=True))
    return stops[-1][1]


PARTICLES = {"mac", "mc", "van", "von", "de", "der", "den", "di", "da", "dos", "le", "la", "el"}


def surname(name: str) -> str:
    """The on-screen surname: the last word, with its particle ("Mac Allister", "van Dijk", "De Bruyne")."""
    parts = name.split()
    if len(parts) >= 3 and parts[-2].lower() in PARTICLES:
        return " ".join(parts[-2:])
    return parts[-1]


def who(p: dict | None, shirts: bool | None = None) -> str | None:
    """A verified name (surname), else a verified shirt number, else nothing (no placeholders)."""
    if not p:
        return None
    if p.get("name"):
        return surname(p["name"])
    if p.get("shirt") and (p.get("shirt_verified") or (SHIRTS_VERIFIED if shirts is None else shirts)):
        return f"#{str(p['shirt']).lstrip('#')}"
    return None


def fmt_xg(v: float | None) -> str:
    return "–" if v is None else f"{v:.2f}"


class LiveHUD(Live):
    """The live analytics layer over a playing attacking passage (track A's live_<start>.json, 10 Hz frames; the
    shared note track-a-v6-live-format.md). A frame that is not trusted, or has no holder, draws nothing."""

    hud_w, hud_h, hud_above = HUD_W, HUD_H, 0           # hud_above: a card stacked over the panel (v7)

    def __init__(self, m: dict):
        super().__init__(m)
        self.v8 = m.get("theme") in ("v8", "v9")          # PITCHSIGHT: glass panels, one radius, team accents
        self.v9 = m.get("theme") == "v9"                  # v9: tracking boxes, a steadier danger card
        self.bottom = V8_BOTTOM if self.v8 else 64         # v8: the stack sits clear of the one caption line
        self._glass: list[tuple] = []
        d = self.data
        if "frames" in d and "samples" not in d:          # track A's layout -> the fields drawn here
            d["samples"] = [{**f, "carrier": f.get("holder") if f.get("trusted") else None}
                            for f in d["frames"]]
        lo, hi = m.get("t0"), m.get("t1")
        if lo is not None or hi is not None:
            d["samples"] = [x for x in d["samples"] if (lo or 0) <= x["clip_ms"] / 1000 <= (hi or 1e9)]
            d["start_clip_ms"], d["end_clip_ms"] = d["samples"][0]["clip_ms"], d["samples"][-1]["clip_ms"]
        if m.get("names_live"):                            # track B's per-passage reads, inside their windows
            doc = json.loads((ROOT / m["names_live"]).read_text())
            reads = [r for r in doc.get("result", doc)["players"] if r.get("name") or r.get("shirt")]
            for x in d["samples"]:
                for p in [x.get("carrier")] + list(x.get("options") or []):
                    if not p:
                        continue
                    hit = next((r for r in reads if r["track_id"] == p.get("track_id")
                                and r["from_clip_ms"] <= x["clip_ms"] <= r["to_clip_ms"]), None)
                    p["name"] = hit.get("name") if hit else None     # only a verified read names anyone
                    p["shirt"] = hit.get("shirt") if hit else None
                    p["shirt_verified"] = bool(p["shirt"])
        race = m.get("race")
        if race:
            doc = json.loads((ROOT / race).read_text())
            self.m["race_doc"] = {**doc.get("result", doc), **m.get("race_labels", {})}

    def span(self):
        return (self.data["start_clip_ms"] / 1000 - float(self.m.get("pre_s", 0.3)),
                self.data["end_clip_ms"] / 1000 + float(self.m.get("post_s", 0.3)))

    def valued(self) -> list[dict]:
        if not hasattr(self, "_valued"):
            self._valued = [x for x in self.data["samples"] if x.get("carrier") and (
                x.get("shot_now_xg") is not None or any(o.get("xg_after_pass") is not None
                                                        for o in x.get("options", [])))]
        return self._valued

    def sample(self, t: float, max_age_s: float = FRESH_S) -> dict | None:
        """The latest valued sample at or before t, if it is at most max_age_s old (printed numbers are samples,
        never interpolations; a held value shows its age)."""
        v = [x for x in self.valued() if x["clip_ms"] <= t * 1000 + 1]
        if not v or t * 1000 - v[-1]["clip_ms"] > max_age_s * 1000:
            return None
        return v[-1]

    def ranked(self, x: dict) -> list[dict]:
        return sorted((o for o in x.get("options", []) if o.get("xg_after_pass") is not None
                       and not o.get("offside_risk")), key=lambda o: -o["xg_after_pass"])

    def streak_start(self, label: str, x: dict) -> int:
        """When this option first appeared in the current run of fresh samples (for the 150 ms draw-on)."""
        v = self.valued()
        i = next(k for k, y in enumerate(v) if y is x)
        start = x["clip_ms"]
        while i > 0 and start - v[i - 1]["clip_ms"] <= 250 and any(
                o.get("label") == label for o in v[i - 1].get("options", [])):
            i -= 1
            start = v[i]["clip_ms"]
        return start

    def ground(self, ax, cam, t):
        x = self.sample(t)
        if x is None:
            return
        c = np.array([x["carrier"]["x"], x["carrier"]["y"]])
        opts = self.ranked(x)
        if not opts:
            return
        top = opts[0]["xg_after_pass"] or 1e-9
        team = x.get("attacking") or self.m.get("team", "home")       # the frame's own attacking side
        kit = np.array((self.m.get("kits") or {}).get(team, ACCENT)) / 255
        pulse = 0.5 + 0.5 * np.sin(2 * np.pi * t / PULSE_S)
        for k, o in reversed(list(enumerate(opts[: int(self.m.get("max_options", 5))]))):
            end = np.array([o["x"], o["y"]])
            grow = window(t * 1000 - self.streak_start(o.get("label"), x), 0, DRAW_ON_MS)   # draws on, 150 ms
            pts = np.linspace(c, c + (end - c) * max(grow, 0.02), 30)
            seg = cam.project(pts)
            best = k == 0
            a = 1.0 if best else max(LINE_MIN_ALPHA, 0.75 * o["xg_after_pass"] / top)
            col = np.array(ACCENT) / 255 if best else np.array((1, 1, 1))
            if best:                                       # the best option pulses gently
                ax.plot(seg[:, 0], seg[:, 1], color=(*col, BEST_GLOW * (0.6 + 0.6 * pulse)), lw=16 + 6 * pulse,
                        solid_capstyle="round")
            ax.plot(seg[:, 0], seg[:, 1], color=(0, 0, 0, 0.5 * a), lw=7 if best else 4, solid_capstyle="round")
            ax.plot(seg[:, 0], seg[:, 1], color=(*col, a), lw=4 if best else 1.8, solid_capstyle="round")
            if grow >= 1:
                ring = cam.project(ground_circle(end, 0.9 if best else 0.6))
                ax.plot(ring[:, 0], ring[:, 1], color=(*col, a), lw=3 if best else 1.4)
        ring = cam.project(ground_circle(c, 1.0))
        ax.plot(ring[:, 0], ring[:, 1], color=(0, 0, 0, 0.5), lw=7)
        ax.plot(ring[:, 0], ring[:, 1], color=(*kit, 1.0), lw=3.5)

    def threat_at(self, t: float) -> float | None:
        """The threat meter's position: eased between consecutive valued samples (the bar moves smoothly; no
        number is printed for it)."""
        v = [y for y in self.valued() if y.get("threat") is not None]
        if not v:
            return None
        i, j, f = bracket(v, t * 1000)
        if t * 1000 - v[i]["clip_ms"] > HOLD_S * 1000 and f == 0:
            return None
        return v[i]["threat"] + (v[j]["threat"] - v[i]["threat"]) * ease_in_out(f)

    def panels(self, im, cam, t):
        self._t, self._glass = t, []
        layer = hi_layer(im.size)
        d = HiDraw(layer)
        x = self.sample(t)
        held = self.sample(t, HOLD_S)
        a = window(t, self.span()[0], self.span()[0] + 0.3)
        if x is not None and cam is not None:
            opts = self.ranked(x)
            font = ImageFont.truetype(FONT, LABEL_PX)
            placed = []
            for k, o in enumerate(opts[:3]):                # labels on the top 3 options only
                if window(t * 1000 - self.streak_start(o.get("label"), x), 0, DRAW_ON_MS) < 1:
                    continue
                pt = cam.project([[o["x"], o["y"]]])[0]
                name = who(o)
                sep = " · " if self.v8 else "  "
                text = (f"{name}{sep}" if name else "") + f"{o['p_pass'] * 100:.0f}% · {o['xg_after_pass']:.2f} xG"
                w = d.textlength(text, font=font) + 24
                x0 = float(np.clip(pt[0] - w / 2, 12, W - 12 - w))
                y0 = pt[1] + 22
                hx0, hy0 = W - 64 - self.hud_w - 12, H - self.bottom - self.hud_h - self.hud_above - 12   # not under it
                if x0 + w > hx0 and y0 + LABEL_PX + 16 > hy0:
                    up = y0 + LABEL_PX + 16 - hy0
                    if up <= 40:                                   # a small nudge up keeps it by its player
                        y0 -= up
                    else:
                        x0 = max(12.0, hx0 - w)
                for bx0, by0, bx1, by1 in placed:                  # never on top of another label
                    if x0 < bx1 + 6 and x0 + w > bx0 - 6 and y0 < by1 + 6 and y0 + LABEL_PX + 16 > by0 - 6:
                        y0 = by1 + 8
                placed.append((x0, y0, x0 + w, y0 + LABEL_PX + 16))
                col = ACCENT if k == 0 else WHITE
                d.rounded_rectangle((x0, y0, x0 + w, y0 + LABEL_PX + 16), radius=RADIUS if self.v8 else 8,
                                    fill=(*PANEL, 225),
                                    outline=(*col, 255 if k == 0 else 140), width=3 if k == 0 else 2)
                d.text((x0 + w / 2, y0 + (LABEL_PX + 16) / 2), text, font=font, fill=(*col, 255), anchor="mm")
        age = (t * 1000 - held["clip_ms"]) / 1000 if held is not None else None
        state = self.state(t) if x is None else None
        self._hud(d, held, a, age if age is not None and age > FRESH_S else None, state, self.threat_at(t))
        self._score(d, t, a)
        self._frost(im)
        flatten(im, layer)

    # -- v8 panel style ---------------------------------------------------------------------------------------
    def accent(self) -> tuple[int, int, int]:
        """The thin accent: the kit colour of the side attacking now (v8), else the brand orange."""
        if not self.v8:
            return ACCENT
        s = self.data["samples"]
        i, _, _ = bracket(s, self._t * 1000)
        team = s[i].get("attacking") or self.m.get("team", "home")
        return tuple((self.m.get("kits") or {}).get(team, ACCENT))

    def _panel(self, d, box, a: float) -> None:
        """One panel: v8 dark glass (the picture blurred under it), a hairline edge and a thin accent line on top."""
        x0, y0, x1, y1 = box
        if not self.v8:
            d.rounded_rectangle(box, radius=14, fill=(*PANEL, int(235 * a)))
            d.rectangle((x0, y0, x1, y0 + 8), fill=(*ACCENT, int(255 * a)))
            return
        self._glass.append(tuple(int(v) for v in box))
        d.rounded_rectangle(box, radius=RADIUS, fill=(14, 18, 24, int(178 * a)), outline=(255, 255, 255, int(40 * a)),
                            width=1)
        d.rounded_rectangle((x0 + RADIUS, y0, x1 - RADIUS, y0 + 4), radius=2, fill=(*self.accent(), int(255 * a)))

    def _frost(self, im) -> None:
        from PIL import ImageFilter
        for box in self._glass:
            region = im.crop(box).filter(ImageFilter.GaussianBlur(16))
            mask = Image.new("L", region.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, region.size[0] - 1, region.size[1] - 1), radius=RADIUS,
                                                   fill=255)
            im.paste(region, box[:2], mask)

    def value_at(self, key, t: float):
        """(value now, the value before it, seconds since it changed) over the valued samples, for the roll."""
        cur = prev = None
        since = None
        for y in self.valued():
            if y["clip_ms"] > t * 1000:
                break
            v = key(y)
            if v != cur:
                prev, cur, since = cur, v, y["clip_ms"] / 1000
        return cur, prev, (t - since) if since is not None else 99.0

    def roll(self, d, xy, text: str, old: str | None, f: float, font, fill, vis: int) -> None:
        """A changed number: a quick crossfade in place (ROLL_S), the old value out as the new one comes in; both are
        real values and share one box, so nothing is ever clipped or stacked."""
        if not self.v8 or old is None or old == text or f >= 1:
            d.text(xy, text, font=font, fill=(*fill, vis))
            return
        e = ease_in_out(f)
        d.text(xy, old, font=font, fill=(*fill, int(vis * (1 - e))))
        d.text(xy, text, font=font, fill=(*fill, int(vis * e)))

    def state(self, t: float) -> str | None:
        """What the tracking says now when there is no live value: the frame's null reason as a broadcast state,
        with the receiver for a pass in flight (the next frame's holder, if named or numbered)."""
        s = self.data["samples"]
        i, _, _ = bracket(s, t * 1000)
        text = s[i].get("state_text")                      # track A's explicit state (6a12c81), never blank
        if text and s[i].get("state") != "carry":          # a carry is named by the panel's ON THE BALL line
            if text == "Pass in flight":
                nxt = next((x for x in s[i:] if x.get("carrier")), None)
                name = who(nxt["carrier"]) if nxt else None
                return f"PASS IN FLIGHT → {name}" if name else "PASS IN FLIGHT"
            return text.upper()
        reason = s[i].get("null_reason")
        if reason == "ball in flight" or reason == "ball speed not measurable":
            nxt = next((x for x in s[i:] if x.get("carrier")), None)
            name = who(nxt["carrier"]) if nxt else None
            return f"PASS IN FLIGHT → {name}" if name else "BALL IN FLIGHT"
        return STATES.get(reason)

    def _hud(self, d: ImageDraw.ImageDraw, x: dict | None, a: float, age: float | None = None,
             state: str | None = None, threat: float | None = None) -> None:
        """Bottom-right broadcast panel: who is on the ball, the two live values in the biggest type on screen,
        and a threat meter that moves smoothly and shifts colour as threat rises."""
        w, h = self.hud_w, self.hud_h
        x0, y0 = W - 64 - w, H - self.bottom - h
        al = int(255 * a)
        self._panel(d, (x0, y0, x0 + w, y0 + h), a)
        f_label = ImageFont.truetype(FONT_REG, 32)
        f_value = ImageFont.truetype(FONT, 72)
        right = state
        if not right and x is not None:
            age_ = age if age is not None else None
            nm = who(x["carrier"])
            right = f"{age_:.1f} s ago" if age_ is not None else (f"ON THE BALL  {nm}" if nm else "ON THE BALL")
        self._header(d, x0, y0, w, "LIVE ANALYTICS", right, (255, 214, 10) if state else
                     (MUTED if age is not None else (255, 255, 255)), al)
        if x is None:
            if not self.v8:                                # v8: the state line alone, no filler text
                d.text((x0 + 28, y0 + 90), "waiting for a carrier in the attacking half", font=f_label,
                       fill=(*MUTED, al))
            return
        vis = al
        if age is not None:                                # a held value fades after HOLD_FADE_S
            vis = int(al * max(0.35, 1 - max(0.0, age - HOLD_FADE_S)))
        best = (self.ranked(x) or [None])[0]
        cols = [("Shot now", x.get("shot_now_xg"), WHITE)]
        if best is not None:
            bn = who(best)
            cols.append((f"Best pass{' · ' + bn if bn else ''}", best["xg_after_pass"], ACCENT))
        keys = [lambda y: fmt_xg(y.get("shot_now_xg")),
                lambda y: fmt_xg(((self.ranked(y) or [{}])[0]).get("xg_after_pass"))]
        for k, (label, value, col) in enumerate(cols):
            cx = x0 + 28 + k * (w - 56) // 2
            d.text((cx, y0 + 76), label, font=f_label, fill=(230, 236, 242, vis))
            _, old, since = self.value_at(keys[k], self._t) if self.v8 else (None, None, 99.0)
            self.roll(d, (cx, y0 + 116), fmt_xg(value), old, since / ROLL_S, f_value, col, vis)
            d.text((cx + d.textlength(fmt_xg(value), font=f_value) + 10, y0 + 152), "xG", font=f_label,
                   fill=(*col, vis))
        if threat is not None:
            y = y0 + h - 58
            d.text((x0 + 28, y), "Threat", font=f_label, fill=(230, 236, 242, al))
            bx0, bx1 = x0 + 170, x0 + w - 28
            d.rounded_rectangle((bx0, y + 8, bx1, y + 32), radius=12, fill=(58, 64, 74, al))
            frac = min(1.0, threat / THREAT_FULL)
            d.rounded_rectangle((bx0, y + 8, bx0 + max(24, (bx1 - bx0) * frac), y + 32), radius=12,
                                fill=(*threat_colour(frac), al))

    @staticmethod
    def _header(d, x0, y0, w, left: str, right: str | None, colour, al: int) -> None:
        """The panel's top line: its title left, the state right; a long state shrinks to fit beside the title, and
        takes the whole line (no title) before it would ever overlap or be cut."""
        f = ImageFont.truetype(FONT, 26)
        if not right:
            d.text((x0 + 28, y0 + 26), left, font=f, fill=(*MUTED, al))
            return
        room = w - 56 - d.textlength(left, font=f) - 24
        if d.textlength(right, font=ImageFont.truetype(FONT, 20)) <= room:
            d.text((x0 + 28, y0 + 26), left, font=f, fill=(*MUTED, al))
            rf = shrink(d, right, FONT, 26, room)
        else:
            rf = shrink(d, right, FONT, 26, w - 56)
        d.text((x0 + w - 28, y0 + 26 + (26 - rf.size) / 2), right, font=rf, fill=(*colour, al), anchor="ra")

    def _score(self, d: ImageDraw.ImageDraw, t: float, a: float) -> None:
        """Top strip under the broadcast score bug: each team's cumulative xG so far (xg_race_0)."""
        race = self.m.get("race_doc")
        if not race or self.m.get("no_score"):            # v10: no xG banner
            return
        now = t * 1000
        pts = [p for p in race["series"] if p["clip_ms"] <= now] or [{"home_xg": 0.0, "away_xg": 0.0}]
        cur = pts[-1]
        f = ImageFont.truetype(FONT, 38)
        text = f"xG  {race['home_short']} {cur['home_xg']:.2f} · {cur['away_xg']:.2f} {race['away_short']}"
        x0, y0 = float(self.m.get("score_x", 96)), float(self.m.get("score_y", 164))   # below the broadcast bug
        w = d.textlength(text, font=f) + 40
        if self.v8:
            self._panel(d, (x0, y0, x0 + w, y0 + 60), a)
        else:
            d.rounded_rectangle((x0, y0, x0 + w, y0 + 60), radius=10, fill=(*PANEL, int(230 * a)))
            d.rectangle((x0, y0, x0 + 6, y0 + 60), fill=(*ACCENT, int(255 * a)))
        d.text((x0 + 22, y0 + 30), text, font=f, fill=(255, 255, 255, int(255 * a)), anchor="lm")


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
        layer = hi_layer(im.size)
        d = HiDraw(layer)
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
        flatten(im, layer)


def _opt_label(o: dict) -> str | None:
    """An option on screen: a verified name, else a shirt label ('#19'), else nothing (never 'U5', 't4')."""
    if o.get("name"):
        return o["name"].split()[-1]
    lab = str(o.get("label") or "")
    return lab if lab.startswith("#") else None


def nodes_from_track_b(doc: dict) -> list[dict]:
    """Track B's pipeline_<clip_ms>.json (node / what / outputs / timing) -> the lines each node shows: only values
    present in the file, the timing only where it was measured or recorded."""
    out = []
    for n in doc["nodes"]:
        o, name = n.get("outputs") or {}, n["node"]
        tm = n.get("timing") or {}
        ms = tm.get("ms") if tm.get("source") in ("measured re-run", "recorded live", "replay") else None
        node = {"agent": name, "latency_ms": None if ms is None else (round(ms) if ms >= 1 else "<1"),
                "timing_source": {"measured re-run": "re-run", "recorded live": "live",
                                  "replay": "replay"}.get(tm.get("source"))}
        if name == "Freeze":
            node["says"] = f"{o.get('players_in_view')} players in view, {o.get('holder')} on the ball"
        elif name == "Scout":
            node["says"] = f"flags a {str(o.get('kind', '')).replace('_', ' ')}"
        elif name == "Proposer":
            opts = [x for x in o.get("options", []) if _opt_label(x)]
            node["says"] = "  ·  ".join(f"{_opt_label(x)} {x['xg_after_pass']:.2f}" for x in opts[:3]) or n["what"]
        elif name == "Model":
            node["says"] = f"xG for the shot and {o.get('options_computed')} passes, the published PL model"
        elif name == "Tactician":
            node["says"] = f"drafts: \u201c{o.get('lower_third')}\u201d"
            if tm.get("tokens_in"):
                node["latency_ms"] = round(ms) if ms else None
        elif name == "Fact Checker":
            node["claims"] = [{"text": c["text"], "ok": bool(c.get("verified"))} for c in o.get("claims", [])]
        elif name == "Producer review":
            node["says"] = f"approves: \u201c{(o.get('final') or {}).get('lower_third')}\u201d"
        elif name == "Director":
            node["says"] = f"{str(o.get('layer', '')).replace('_', ' ')}, {(o['t_out_ms'] - o['t_in_ms']) // 1000} s"
        elif name == "On air":
            node["line"] = o.get("headline")
        else:
            node["says"] = n.get("what")
        out.append(node)
    return out


class Pipeline(Still):
    """The newsroom's real run for one moment as a full-height split: the frozen frame with the decision arcs on the
    left (55%), the agents on the right as a vertical flow of cards joined by arrows. Each card expands as it fires
    (agent, what it did, its real output, the timing and where the timing comes from) and compacts as the next one
    fires; it ends on ON AIR with the line sliding onto the frame (track B's pipeline_<slug>_<clip_ms>.json)."""

    needs_camera = False
    LEFT_W = 1056                                          # 55% of the frame
    CROP = (270, 170, 1570, 1075)                          # the decision on the arcs still: goal to Amad
    INTRO_S = 0.7
    GROW_S = 0.25
    WHAT = {"scout": "spots the chance in the live feed", "proposer": "puts every option on the table",
            "rollout": "values each option", "tactician": "drafts the line", "factcheck":
            "checks every claim against the evidence", "director": "schedules it on air",
            "cuebus": "sends the line to air"}

    def __init__(self, m: dict):
        super().__init__(m)
        if self.data.get("nodes") and "node" in self.data["nodes"][0]:
            self.data = {**self.data, "nodes": nodes_from_track_b(self.data)}
        for n in self.data["nodes"]:                       # track B's own format: latency with its source
            if "latency_source" in n:
                ms = n.get("latency_ms")
                n["latency_ms"] = None if ms is None else (round(ms) if ms >= 1 else "<1")
                n["timing_source"] = {"measured re-run": "re-run", "recorded live": "live",
                                      "replay": "replay"}.get(n["latency_source"])
        self.still = Image.open(ROOT / m["left"]).convert("RGB") if m.get("left") else None
        self.f = {z: ImageFont.truetype(FONT, z) for z in (24, 26, 30, 34, 40, 72)}
        self.r = {z: ImageFont.truetype(FONT_REG, z) for z in (22, 24, 27, 30)}
        self.v8 = m.get("theme") in ("v8", "v9")          # PITCHSIGHT: nothing under 24 px, one radius, "Gemini"
        self.small, self.floor = (24, 24) if self.v8 else (22, 14)
        tmp = ImageDraw.Draw(Image.new("RGB", (8, 8)))
        self.rows = [self._lines(n, tmp) for n in self.data["nodes"]]
        self.starts, t = [], self.INTRO_S + 0.2
        for rows in self.rows:                             # time on screen grows with what there is to read
            self.starts.append(t)
            t += min(1.8, 0.75 + 0.2 * len(rows))
        self.expanded = m.get("layout") == "expanded"      # v11: every card open from the start, read aloud in turn
        if m.get("fire_s"):                                # each agent fires as the voice names it
            self.starts = [float(x) for x in m["fire_s"]]
        self.air = self.starts[-1]

    def span(self):
        t = self.at_ms() / 1000
        return t - float(self.m.get("pre_s", 0.0)), t + float(self.m.get("hold_s", 10.0))

    def at_ms(self) -> int:
        return int(self.m["clip_ms"])

    # -- layout --------------------------------------------------------------------------------------------------
    def grown(self, k: int, tau: float) -> float:
        """How far card k is expanded (0 compact, 1 open): it opens as it fires, compacts as the next one fires."""
        e = ease_in_out(window(tau, self.starts[k], self.starts[k] + self.GROW_S))
        if k + 1 < len(self.starts):
            e *= 1 - ease_in_out(window(tau, self.starts[k + 1], self.starts[k + 1] + self.GROW_S))
        return e

    COMPACT_H, GAP, ROW = 58, 26, 38

    def open_h(self, k: int) -> int:
        return 98 + self.ROW * len(self.rows[k]) + 14

    def frame(self, img, t, ax, canvas, cam_t=None):
        tau = self.tau(t)
        im = Image.new("RGB", (W, H), PANEL)
        e = ease_in_out(window(tau, 0.0, self.INTRO_S))
        self._left(im, e, tau)
        layer = hi_layer((W, H))
        d = HiDraw(layer)
        dx = int((1 - e) * (W - self.LEFT_W))              # the panel slides in from the right
        if self.expanded:
            self._flow_expanded(d, tau, dx)
            self._banner(d, tau, dx)
        else:
            self._flow(d, tau, dx)
        self._on_air(d, tau)
        flatten(im, layer)
        return im

    def _left(self, im: Image.Image, e: float, tau: float) -> None:
        still = self.still or Image.new("RGB", (W, H), (0, 0, 0))
        cx0, cy0, cx1, cy1 = self.CROP
        tw = self.LEFT_W - 40
        th = int(tw * (cy1 - cy0) / (cx1 - cx0))
        tx0, ty0 = 20, (H - th) // 2 + 10
        if e > 0:                                          # the column behind: the frame itself, blurred and dark
            from PIL import ImageEnhance, ImageFilter
            if not hasattr(self, "_bg"):
                bg = still.resize((W // 4, H // 4)).filter(ImageFilter.GaussianBlur(6)).resize((W, H))
                self._bg = ImageEnhance.Brightness(bg).enhance(0.35).crop((0, 0, self.LEFT_W, H))
            im.paste(Image.blend(Image.new("RGB", self._bg.size, PANEL), self._bg, e), (0, 0))
        src = [a + (b - a) * e for a, b in zip((0, 0, W, H), (cx0, cy0, cx1, cy1), strict=True)]
        dst = [a + (b - a) * e for a, b in zip((0, 0, W, H), (tx0, ty0, tx0 + tw, ty0 + th), strict=True)]
        size = (max(1, int(dst[2] - dst[0])), max(1, int(dst[3] - dst[1])))
        im.paste(still.crop(tuple(int(v) for v in src)).resize(size, Image.LANCZOS), (int(dst[0]), int(dst[1])))
        d = ImageDraw.Draw(im)
        if e >= 1:
            d.rectangle((tx0, ty0, tx0 + tw, ty0 + th), outline=(70, 78, 90), width=2)
            clock = self.data.get("clock")
            d.text((tx0, ty0 - 58), f"THE MOMENT{'  ·  ' + clock if clock else ''}", font=self.f[34],
                   fill=(255, 255, 255))
            d.line((self.LEFT_W, 0, self.LEFT_W, H), fill=ACCENT, width=3)
        self._frame_box = (tx0, ty0, tx0 + tw, ty0 + th)

    def _flow(self, d: ImageDraw.ImageDraw, tau: float, dx: int) -> None:
        x0 = self.LEFT_W + 40 + dx
        w = W - 48 - (self.LEFT_W + 40)
        d.text((x0, 52), "THE NEWSROOM", font=self.f[40], fill=(255, 255, 255, 255))
        sub_ = "Recorded run · real clip, replayed" if self.v8 else "how the line on air was made, agent by agent"
        d.text((x0, 104), sub_, font=self.r[24], fill=(*MUTED, 255))
        y = 160
        boxes = []
        for k in range(len(self.data["nodes"])):
            g = self.grown(k, tau)
            h = int(self.COMPACT_H + (self.open_h(k) - self.COMPACT_H) * g)
            boxes.append((y, h, g))
            y += h + self.GAP
        self._bottom = y
        for k, (n, (y, h, g)) in enumerate(zip(self.data["nodes"], boxes, strict=True)):
            state = "future" if tau < self.starts[k] else ("active" if g > 0.01 or k == len(boxes) - 1
                                                          and tau < self.air + 0.4 else "done")
            if k:                                          # the arrow from the card before draws on as this fires
                ya, yb, ax_ = boxes[k - 1][0] + boxes[k - 1][1], y, x0 + 28
                p = window(tau, self.starts[k] - 0.3, self.starts[k])
                d.line((ax_, ya + 2, ax_, yb - 2), fill=(90, 98, 110, 90), width=2)
                if p > 0:
                    ye = ya + 2 + (yb - ya - 4) * p
                    d.line((ax_, ya + 2, ax_, ye), fill=(*ACCENT, 255), width=4)
                    d.polygon([(ax_ - 8, ye - 10), (ax_ + 8, ye - 10), (ax_, ye)], fill=(*ACCENT, 255))
                    if p < 1:                              # the hand-off travelling down the arrow
                        d.ellipse((ax_ - 7, ye - 17, ax_ + 7, ye - 3), fill=(255, 255, 255, 255))
            self._card(d, n, k, x0, y, w, h, g, state)

    def _card(self, d, n, k, x0, y, w, h, g, state) -> None:
        al = 90 if state == "future" else 255
        col = {"active": ACCENT, "done": (90, 100, 112), "future": (70, 76, 86)}[state]
        d.rounded_rectangle((x0, y, x0 + w, y + h), radius=RADIUS if self.v8 else 12,
                            fill=(28, 32, 40, 255 if state != "future" else 150),
                            outline=(*col, al), width=3 if state == "active" else 2)
        dot = GOOD if state == "done" else col
        d.ellipse((x0 + 18, y + 19, x0 + 38, y + 39), fill=(*dot, al))
        big = g > 0.5
        d.text((x0 + 54, y + (12 if big else 14)), self.label(n), font=self.f[34 if big else 26],
               fill=(255, 255, 255, al))
        timing = self._timing(n, model=big)                # the model name only on the open card
        if timing:
            d.text((x0 + w - 20, y + 18), timing, font=self.r[24 if big else self.small], fill=(*MUTED, al), anchor="ra")
        if not big:                                        # compact: one short phrase, never cut
            short = self.short(n)
            if short and state != "future":
                x1 = x0 + w - 20 - (d.textlength(timing, font=self.r[self.small]) + 24 if timing else 0)
                nx = x0 + 54 + d.textlength(self.label(n), font=self.f[26]) + 20
                tx = nx
                if n.get("claims") and all(c.get("ok") for c in n["claims"]):
                    d.line((tx, y + 30, tx + 6, y + 36, tx + 16, y + 24), fill=(*GOOD, al), width=4)
                    tx += 26
                f = shrink(d, short, FONT_REG, self.small, x1 - tx, floor=self.floor)
                d.text((tx, y + 29), short, font=f, fill=(*MUTED, al), anchor="lm")
            return
        a = int(255 * window(g, 0.6, 1.0))
        d.text((x0 + 54, y + 58), self.WHAT.get(n["agent"], ""), font=self.r[24], fill=(*MUTED, a))
        for j, (text, colour, mark) in enumerate(self.rows[k]):
            ty = y + 98 + self.ROW * j
            if ty + self.ROW > y + h:
                break
            tx = x0 + 54
            if mark is not None:                           # a drawn tick or cross (the fonts have no glyph)
                yy = ty + 15
                if mark:
                    d.line((tx, yy, tx + 7, yy + 7, tx + 19, yy - 7), fill=(*GOOD, a), width=4)
                else:
                    d.line((tx, yy - 7, tx + 14, yy + 7), fill=(*ORANGE, a), width=4)
                    d.line((tx, yy + 7, tx + 14, yy - 7), fill=(*ORANGE, a), width=4)
                tx += 32
            d.text((tx, ty), text, font=shrink(d, text, FONT_REG, 27, x0 + w - 24 - tx, floor=self.floor),
                   fill=(*colour, a))

    SCREEN = {"rollout": "Model", "factcheck": "Fact Checker", "cuebus": "On air"}   # track B, v8: what each does

    def label(self, n: dict) -> str:
        if self.m.get("theme") == "v9" and n["agent"] == "rollout":   # v9: as the architecture diagram names it
            return "ROLLOUT"
        return (self.SCREEN.get(n["agent"], n["agent"]) if self.v8 else n["agent"]).upper()

    def short(self, n: dict) -> str | None:
        """The compact card's phrase: the beat's own (`compact` in the moment, numbers from the view's facts), else
        a claim count for the factcheck, else nothing."""
        text = (self.m.get("compact") or {}).get(n["agent"])
        if text:
            return text
        if n.get("claims"):
            return f"{len(n['claims'])} claims checked"
        return None

    @staticmethod
    def _timing(n: dict, model: bool = True) -> str:
        lat = n.get("latency_ms")
        if lat is None:
            return ""
        text = f"{lat / 1000:.1f} s" if isinstance(lat, int | float) and lat >= 1000 else f"{lat} ms"
        if n.get("timing_source"):                         # where the number comes from, beside it
            text += f" · {n['timing_source']}"
        if model and n.get("model"):                        # the family only on screen (lead, v8): "Gemini"
            text += " · Gemini" if str(n["model"]).lower().startswith("gemini") else f" · {n['model']}"
        return text

    # -- v11: every card open, the agents read in turn, the action-to-air budget underneath ------------------------
    WHAT_SHORT = {"scout": "flags the moment", "proposer": "lists every option", "rollout": "prices each option",
                  "tactician": "drafts the line", "factcheck": "checks every number", "director": "schedules it",
                  "cuebus": "sends it to air"}
    CARD_H, CARD_GAP, CARDS_Y = 96, 16, 150

    def _out_line(self, n: dict) -> tuple[str, list | None]:
        """The card's second line: what the agent produced, from the record (a moment may reword it, no new
        numbers); the Fact Checker's claims come back as a list to draw with their ticks."""
        a = n["agent"]
        if n.get("claims"):
            return "", n["claims"]
        if n.get("options"):
            def val(o):
                return float(o.get("xg_after_pass") or o.get("xg") or 0)
            opts = n["options"]
            named = [o for o in opts if o["label"] == "Shot" or o["label"].startswith("Pass to ")][:3]
            parts = [f"{o['label'][8:] if o['label'].startswith('Pass to ') else o['label']} "
                     f"{o.get('xg_after_pass') or o.get('xg')}" for o in sorted(named, key=val, reverse=True)]
            more = len(opts) - len(named)
            return "  ·  ".join(parts) + (f"  ·  {more} more" if more else "") + "  (xG)", None
        says = (self.m.get("says") or {}).get(a)
        if says:
            return says, None
        if n.get("says") and a == "tactician":
            return f"\u201c{n['says']}\u201d", None
        if n.get("line"):
            return f"\u201c{n['line']}\u201d", None
        return (self.m.get("compact") or {}).get(a) or n.get("says") or "", None

    def _flow_expanded(self, d: ImageDraw.ImageDraw, tau: float, dx: int) -> None:
        x0 = self.LEFT_W + 40 + dx
        w = W - 48 - (self.LEFT_W + 40)
        d.text((x0, 40), "THE NEWSROOM", font=self.f[40], fill=(255, 255, 255, 255))
        d.text((x0, 92), "from the action to the line on air, agent by agent", font=self.r[24], fill=(*MUTED, 255))
        n_cards = len(self.data["nodes"])
        for k, n in enumerate(self.data["nodes"]):
            y = self.CARDS_Y + k * (self.CARD_H + self.CARD_GAP)
            nxt = self.starts[k + 1] if k + 1 < n_cards else self.air + 99
            state = "future" if tau < self.starts[k] else ("active" if tau < nxt else "done")
            if k:                                          # the hand-off arrow from the card above
                ya, yb, ax_ = y - self.CARD_GAP, y, x0 + 28
                lit = state != "future"
                d.line((ax_, ya, ax_, yb), fill=(*(ACCENT if lit else (90, 98, 110)), 255 if lit else 120), width=3)
            col = {"active": ACCENT, "done": (90, 100, 112), "future": (64, 70, 80)}[state]
            d.rounded_rectangle((x0, y, x0 + w, y + self.CARD_H), radius=RADIUS,
                                fill=(36, 41, 52, 255) if state == "active" else (28, 32, 40, 255),
                                outline=(*col, 255), width=3 if state == "active" else 2)
            dot = GOOD if state == "done" else (ACCENT if state == "active" else (90, 98, 110))
            d.ellipse((x0 + 18, y + 20, x0 + 38, y + 40), fill=(*dot, 255))
            label = self.label(n)
            d.text((x0 + 54, y + 12), label, font=self.f[30], fill=(255, 255, 255, 255))
            timing = self._timing(n)
            tw = d.textlength(timing, font=self.r[24]) if timing else 0
            if timing:
                d.text((x0 + w - 20, y + 16), timing, font=self.r[24], fill=(*MUTED, 255), anchor="ra")
            wx = x0 + 54 + d.textlength(label, font=self.f[30]) + 16
            what = self.WHAT_SHORT.get(n["agent"], "")
            fw = shrink(d, what, FONT_REG, 24, x0 + w - 36 - tw - wx, floor=self.floor)
            d.text((wx, y + 17), what, font=fw, fill=(*MUTED, 255))
            text, claims = self._out_line(n)
            ty, tx = y + 54, x0 + 54
            body = (240, 244, 248, 255) if state != "future" else (205, 212, 220, 255)
            if claims:                                     # every claim with its drawn tick
                for c in claims:
                    yy = ty + 15
                    good = c.get("ok")
                    if good:
                        d.line((tx, yy, tx + 7, yy + 7, tx + 19, yy - 7), fill=(*GOOD, 255), width=4)
                    else:
                        d.line((tx, yy - 7, tx + 14, yy + 7), fill=(*ORANGE, 255), width=4)
                        d.line((tx, yy + 7, tx + 14, yy - 7), fill=(*ORANGE, 255), width=4)
                    d.text((tx + 28, ty), c["text"], font=self.r[27], fill=body)
                    tx += 28 + d.textlength(c["text"], font=self.r[27]) + 30
                d.text((tx, ty), "all verified" if all(c.get("ok") for c in claims) else "", font=self.r[24],
                       fill=(*GOOD, 255))
            elif text:
                f = shrink(d, text, FONT_REG, 27, x0 + w - 24 - tx, floor=self.floor)
                d.text((tx, ty), text, font=f, fill=body)
        self._bottom = self.CARDS_Y + n_cards * (self.CARD_H + self.CARD_GAP)

    def _banner(self, d: ImageDraw.ImageDraw, tau: float, dx: int) -> None:
        """The action-to-air budget and its live measurement (footage_moments `banner`, bound in
        footage.grounding.v6_pipeline to config/budgets.yaml and packages/evals/results.json)."""
        b = self.m.get("banner")
        if not b:
            return
        x0 = self.LEFT_W + 40 + dx
        x1 = W - 48 + dx
        y0, y1 = self._bottom + 8, H - 32
        lit = tau >= self.air
        d.rounded_rectangle((x0, y0, x1, y1), radius=RADIUS, fill=(*((60, 22, 22) if lit else (24, 28, 36)), 255),
                            outline=(*((220, 40, 40) if lit else ACCENT), 255), width=3)
        d.text((x0 + 26, y0 + 14), b["label"], font=self.f[24], fill=(*MUTED, 255))
        d.text((x0 + 26, y0 + 44), b["value"], font=self.f[40], fill=(*ACCENT, 255))
        d.text((x1 - 24, y0 + 18), b["note_label"], font=self.r[24], fill=(*MUTED, 255), anchor="ra")
        d.text((x1 - 24, y0 + 50), b["note"], font=self.f[30], fill=(255, 255, 255, 255), anchor="ra")

    def _on_air(self, d: ImageDraw.ImageDraw, tau: float) -> None:
        a = window(tau, self.air, self.air + 0.3)
        if a <= 0:
            return
        if self.expanded:                                  # the last card and the banner say it; the line slides on
            self._lower_third(d, tau, self.data["nodes"][-1].get("line"))
            return
        line = self.data["nodes"][-1].get("line")
        pop = 1 + 0.15 * (1 - ease_in_out(window(tau, self.air, self.air + 0.4)))
        f = ImageFont.truetype(FONT, int(72 * pop))
        x0 = self.LEFT_W + 40
        w = d.textlength("ON AIR", font=f) + 120
        y0 = min(self._bottom + 10, H - 150)
        d.rounded_rectangle((x0, y0, x0 + w, y0 + 110 * pop), radius=RADIUS, fill=(220, 40, 40, int(255 * a)))
        on = 0.5 + 0.5 * np.sin(2 * np.pi * (tau - self.air) / 1.0)
        d.ellipse((x0 + 26, y0 + 55 * pop - 14, x0 + 54, y0 + 55 * pop + 14), fill=(255, 255, 255, int(255 * a * (0.5 + 0.5 * on))))
        d.text((x0 + 72, y0 + 55 * pop), "ON AIR", font=f, fill=(255, 255, 255, int(255 * a)), anchor="lm")
        self._lower_third(d, tau, line)

    def _lower_third(self, d: ImageDraw.ImageDraw, tau: float, line: str | None) -> None:
        s = ease_in_out(window(tau, self.air + 0.2, self.air + 0.7))
        if s <= 0 or not line:
            return
        fx0, _, fx1, fy1 = self._frame_box                 # the line slides onto the frame as a lower third
        lines = Live._wrap(d, line, self.f[34], fx1 - fx0 - 120)
        bh = 64 + 46 * len(lines)
        bw = fx1 - fx0 - 40
        bx = fx0 + 20 - (1 - s) * (bw + 60)
        by = fy1 - bh - 24
        d.rounded_rectangle((bx, by, bx + bw, by + bh), radius=RADIUS, fill=(*PANEL, 240))
        d.rectangle((bx, by, bx + 10, by + bh), fill=(220, 40, 40, 255))
        d.text((bx + 34, by + 14), "ON AIR", font=self.f[24], fill=(255, 90, 90, 255))
        for j, ln in enumerate(lines):
            d.text((bx + 34, by + 48 + 46 * j), ln, font=self.f[34], fill=(255, 255, 255, 255))

    def _lines(self, n: dict, d: ImageDraw.ImageDraw) -> list[tuple[str, tuple, bool | None]]:
        out = []
        says = (self.m.get("says") or {}).get(n["agent"], n.get("says"))   # a moment may reword a line (no numbers)
        if says:
            out.append((says, (230, 236, 242), None))
        opts = n.get("options", [])
        if opts:                                           # the options the proposer put on the table, the best lit
            def val(o):
                return float(o.get("xg_after_pass") or o.get("xg") or 0)
            best = max(opts, key=val)
            for o in opts[:5]:
                name = o["label"][8:] if o["label"].startswith("Pass to ") else o["label"]
                text = f"{name}   {o['p_pass']} · {o['xg_after_pass']} xG" if o.get("xg_after_pass") \
                    else f"{name}   {o.get('xg')} xG"
                out.append((text, ACCENT if o is best else (230, 236, 242), None))
        if n.get("draft"):
            out.append((f"draft: \u201c{n['draft']}\u201d", MUTED, None))
        for c in n.get("claims", []):                      # every claim with its tick and its evidence
            ev = re.sub(r"\s*\([^()]*(\([^()]*\)[^()]*)*\)", "", c.get("evidence", ""))   # without the asides
            numeric = any(ch.isdigit() for ch in c["text"])     # a name is checked, its evidence is a number's
            out.append((f"{c['text']}   {ev}" if ev and numeric else c["text"], GOOD if c.get("ok") else ORANGE,
                        bool(c.get("ok"))))
        if n.get("line"):
            for ln in Live._wrap(d, n["line"], self.r[27], 700):
                out.append((ln, ACCENT, None))
        return out


def shrink(d: ImageDraw.ImageDraw, text: str, face: str, size: int, width: float, floor: int = 14):
    """The largest font up to `size` that fits the text on one line (nothing on screen is ever cut)."""
    while size >= max(floor, 14):
        f = ImageFont.truetype(face, size)
        if d.textlength(text, font=f) <= width:
            return f
        size -= 1
    raise ValueError(f"does not fit on one line even at {max(floor, 14)} px: {text!r}")
