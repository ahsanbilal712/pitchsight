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
FRESH_S = 0.3                  # a sample this recent is live: lines on the pitch
THREAT_FULL = 0.30             # the threat meter is full at 0.30 xG (shot now or the best pass)
HOLD_FADE_S = 1.0              # a held value starts fading after this
STATES = {"ball loose": "BALL LOOSE", "ball out of play": "OUT OF PLAY", "dead ball after the goal": "OUT OF PLAY",
          "ball not detected": "TRACKING THE BALL…", "camera fit not trusted": "CAMERA MOVING…",
          "possession unsettled": "CONTESTED", "own half": "BUILDING FROM THE BACK"}
HOLD_S = 2.0                   # the panel holds the last value this long, with its age
BEST_GLOW = 0.30


SHIRTS_VERIFIED = False        # track B: print a live shirt number only once their per-passage list is in


def who(p: dict | None, shirts: bool | None = None) -> str | None:
    """A verified name (surname), else a verified shirt number, else nothing (owner: no placeholders)."""
    if not p:
        return None
    if p.get("name"):
        return p["name"].split()[-1]
    if p.get("shirt") and (SHIRTS_VERIFIED if shirts is None else shirts):
        return f"#{str(p['shirt']).lstrip('#')}"
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
        held = self.sample(t, HOLD_S)
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
        age = (t * 1000 - held["clip_ms"]) / 1000 if held is not None else None
        state = self.state(t) if x is None else None
        self._hud(d, held, a, age if age is not None and age > FRESH_S else None, state)
        self._score(d, t, a)
        im.paste(layer, (0, 0), layer)

    def state(self, t: float) -> str | None:
        """What the tracking says now when there is no live value: the frame's null reason as a broadcast state,
        with the receiver for a pass in flight (the next frame's holder, if named or numbered)."""
        s = self.data["samples"]
        i, _, _ = bracket(s, t * 1000)
        reason = s[i].get("null_reason")
        if reason == "ball in flight" or reason == "ball speed not measurable":
            nxt = next((x for x in s[i:] if x.get("carrier")), None)
            name = who(nxt["carrier"]) if nxt else None
            return f"PASS IN FLIGHT → {name}" if name else "BALL IN FLIGHT"
        return STATES.get(reason)

    def _hud(self, d: ImageDraw.ImageDraw, x: dict | None, a: float, age: float | None = None,
             state: str | None = None) -> None:
        """Bottom-right broadcast panel: carrier, shot now, best pass, threat meter."""
        w, h = 560, 210
        x0, y0 = W - 96 - w, H - 96 - h
        al = int(255 * a)
        d.rounded_rectangle((x0, y0, x0 + w, y0 + h), radius=10, fill=(*PANEL, int(232 * a)))
        d.rectangle((x0, y0, x0 + w, y0 + 6), fill=(*ACCENT, al))
        f22, f30, f26 = ImageFont.truetype(FONT, 22), ImageFont.truetype(FONT, 30), ImageFont.truetype(FONT_REG, 24)
        d.text((x0 + 24, y0 + 20), "LIVE ANALYTICS", font=f22, fill=(*MUTED, al))
        if state:                                          # the tracking's own state, top right
            d.text((x0 + w - 24, y0 + 18), state, font=f22, fill=(255, 214, 10, al), anchor="ra")
        if x is None:
            d.text((x0 + 24, y0 + 64), "waiting for a carrier in the attacking half", font=f26, fill=(*MUTED, al))
            return
        if age is not None:                                # a held value fades after HOLD_FADE_S
            al = int(al * max(0.35, 1 - max(0.0, age - HOLD_FADE_S)))
        name = who(x["carrier"])
        if age is not None and not state:                  # a held value, never presented as live
            d.text((x0 + w - 24, y0 + 18), f"{age:.1f} s ago", font=f22, fill=(*MUTED, al), anchor="ra")
        elif not state:
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
            col = GOOD if thr < 0.05 else (255, 214, 10) if thr < 0.15 else (235, 60, 60)
            d.rounded_rectangle((bx0, y + 4, bx0 + max(14, (bx1 - bx0) * min(1.0, thr / THREAT_FULL)), y + 18), radius=7,
                                fill=(*col, al))

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
    """The newsroom's real run for one moment, as an animated flow on the right of the frozen frame (dimmed): each
    agent node lights up in turn with what it did, the claims tick, and the line goes on air (track B's
    pipeline_<clip_ms>.json)."""

    needs_camera = False
    STEP_S = 0.75

    def __init__(self, m: dict):
        super().__init__(m)
        if self.data.get("nodes") and "node" in self.data["nodes"][0]:
            self.data = {**self.data, "nodes": nodes_from_track_b(self.data)}

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
        f_agent = ImageFont.truetype(FONT, 22)
        f_says = ImageFont.truetype(FONT_REG, 20)
        x0, w = W - 64 - 800, 800
        y = 200                                            # below the broadcast's own logo
        d.text((x0, y - 50), "THE NEWSROOM, LIVE ON THIS MOMENT", font=f_title, fill=(*MUTED, 255))
        for k, n in enumerate(nodes):
            on = window(tau, k * self.STEP_S, k * self.STEP_S + 0.3)
            if on <= 0:
                break
            lit = tau < (k + 1) * self.STEP_S or k == len(nodes) - 1
            lines = self._lines(n)
            h = 40 + 26 * len(lines)
            col = ACCENT if lit else (110, 120, 132)
            d.rounded_rectangle((x0, y, x0 + w, y + h), radius=10, fill=(*PANEL, int(235 * on)),
                                outline=(*col, int(255 * on)), width=3 if lit else 1)
            d.ellipse((x0 + 16, y + 14, x0 + 30, y + 28), fill=(*col, int(255 * on)))
            d.text((x0 + 44, y + 10), n["agent"].upper(), font=f_agent, fill=(255, 255, 255, int(255 * on)))
            lat = n.get("latency_ms")
            if lat is not None:
                text = f"{lat / 1000:.1f} s" if isinstance(lat, int | float) and lat >= 1000 else f"{lat} ms"
                if n.get("timing_source"):                 # where the number comes from, beside it
                    text += f" · {n['timing_source']}"
                d.text((x0 + w - 16, y + 12), text, font=f_says,
                       fill=(*MUTED, int(255 * on)), anchor="ra")
            for j, (text, colour, mark) in enumerate(lines):
                tx = x0 + 44
                if mark is not None:                       # a drawn tick or cross (the fonts have no glyph)
                    yy = y + 40 + 26 * j + 11
                    if mark:
                        d.line((tx, yy, tx + 6, yy + 6, tx + 16, yy - 6), fill=(*GOOD, int(255 * on)), width=4)
                    else:
                        d.line((tx, yy - 6, tx + 12, yy + 6), fill=(*ORANGE, int(255 * on)), width=4)
                        d.line((tx, yy + 6, tx + 12, yy - 6), fill=(*ORANGE, int(255 * on)), width=4)
                    tx += 26
                d.text((tx, y + 40 + 26 * j), text, font=f_says, fill=(*colour, int(255 * on)))
            y += h + 10
            if k < len(nodes) - 1:
                d.line((x0 + 23, y - 10, x0 + 23, y), fill=(*col, int(200 * on)), width=3)
        im.paste(layer, (0, 0), layer)

    @staticmethod
    def _lines(n: dict) -> list[tuple[str, tuple]]:
        out = []
        if n.get("says"):
            out.append((n["says"], (230, 236, 242), None))
        claims = n.get("claims", [])
        if claims:                                        # one row: every claim with its tick
            ok = all(c.get("ok") for c in claims)
            out.append(("   ".join(c["text"] for c in claims) + ("  all verified" if ok else ""),
                        GOOD if ok else ORANGE, ok))
        if n.get("line"):
            out.append((n["line"], ACCENT, None))
        return out
