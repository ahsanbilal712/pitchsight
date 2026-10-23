"""Video v5 lines: real-data xG. The lower-third and the explanation for each featured freeze, from track A's
cache/v5/xg_decision_<clip_ms>.json, through the same writer as v4 (footage.v4_lines: gemini-4-argon, the Fact
Checker, the gates, hand review, import to cache/v5/lines_<clip_ms>.json).

    python -m footage.v5_lines run <slug> <clip_ms> [--dry-run]
    python -m footage.v5_lines import

Shot xG is the published reference model at the shooter's spot; xG after a pass is P(pass completes) x the
reference xG from the receiver's spot. Lead's rules for v5: a pass is shown, and called worth more, only when its xG
after the pass is at least 0.04 above the shot's, both at the freeze (the same instant) and as shown (two
decimals), and the receiver is more than 0.5 m onside (track A's onside_margin_m; the tracking error); that shot is
"from here" (the freeze). Every other beat is shot-only or a goal, with the xG of its reviewed strike (shots_0).
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import ROUND_HALF_UP, Decimal

from footage.clips import CLIPS, ROOT, clip_dir
from footage.v4_lines import (
    BETTER,
    FINISH,
    SHOT_ONLY,
    Version,
    _fact,
    import_,
    moment,
    outcome,
    person,
    run,
)

PROMPT = "insight_footage@7"      # @6: freeze comparisons, close calls at 0.02
MARGIN_XG = Decimal("0.04")        # lead: a pass is worth more only by 0.04 xG or more, as shown
ONSIDE_M = 0.5                     # and the receiver more than the tracking error onside


def xg(v: float) -> str:
    """The one display of an xG value: two decimals, as the overlay prints it ("0.03", "0.30")."""
    return f"{Decimal(str(v)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"


def whole_pct(p: float) -> str:
    return f"{(Decimal(str(p)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP)}%"


def decision(slug: str, clip_ms: int) -> dict:
    return json.loads((clip_dir(slug) / "cache" / "v5" / f"xg_decision_{clip_ms}.json").read_text())["result"]


def offside(m: dict, team: str, x: float) -> float | None:
    """Metres beyond the second-last opponent and the ball toward the attacked goal (> 0: offside position), from
    the moment file's tracked and hand-marked players (role-prior fills excluded); None when unknown."""
    plus = (m["home_attacks"] == "+x") == (team == "home")
    opp = sorted((p["x"] if plus else 105 - p["x"]) for p in m["players"]
                 if p["team"] != team and p.get("source") != "prior")
    if len(opp) < 2:
        return None
    line = max(opp[-2], (m["ball"]["x"] if plus else 105 - m["ball"]["x"]) if m["ball"].get("x") is not None
               else opp[-2])
    return round((x if plus else 105 - x) - line, 2)


def compare(actual: float, alt: dict) -> str:
    gap = Decimal(xg(alt["xg_after_pass"])) - Decimal(xg(actual))
    return BETTER if gap >= MARGIN_XG and (alt.get("onside_margin_m") or 0) > ONSIDE_M else SHOT_ONLY


def strike(slug: str, event_id: str) -> dict:
    return next(s for s in json.loads((clip_dir(slug) / "cache" / "v5" / "shots_0.json").read_text())["result"]
                ["shots"] if s["event_id"] == event_id)


def metres(v: float) -> str:
    q = Decimal("0.1") if v < 10 else Decimal("1")
    return f"{Decimal(str(v)).quantize(q, rounding=ROUND_HALF_UP)} m"


def facts_for(slug: str, clip_ms: int) -> tuple[list[dict], dict]:
    d, m = decision(slug, clip_ms), moment(slug, clip_ms)
    mid, src = d["match_id"], f"cache/v5/xg_decision_{clip_ms}.json"
    team = d["team"]
    shot = strike(slug, d["actual"]["event_id"])
    alts = [o for o in d.get("alternatives") or [] if o.get("xg_after_pass") is not None
            and not o.get("offside_risk") and (offside(m, team, o["x"]) or -1) <= 0]
    best = max(alts, key=lambda o: o.get("xg_after_pass_exact", o["xg_after_pass"]), default=None)
    real = outcome(slug, clip_ms)
    freeze_xg = d["actual"].get("xg_exact", d["actual"]["xg"])
    if real and real.endswith(" scores"):
        verdict = FINISH
    else:                              # a pass is compared with the shot at the same instant: the freeze
        verdict = compare(freeze_xg, best) if best else SHOT_ONLY
    if verdict != BETTER:
        best = None                                        # no pass is shown on a shot-only or finishing beat
    holder = person(slug, m, d["holder"])
    target = person(slug, m, best["label"]) if best else None
    who = [x["pid"] for x in (holder, target) if x and x.get("pid")]
    k = 10 * (clip_ms // 100 % 1000)
    if verdict == BETTER:              # a decision freeze, labelled "from here" on screen
        ssrc, shot_xg, dist = src, freeze_xg, d["actual"]["distance_m"]
        shot_label, dist_label = "xG of a shot from here (the freeze, where the pass is compared)", \
            "distance from goal at the freeze"
    else:                              # a shot-only or finishing beat: the shot he took, at the reviewed strike
        ssrc, shot_xg, dist = f"cache/v5/shots_0.json {shot['event_id']}", shot["xg"], shot["distance_m"]
        shot_label, dist_label = "xG of the shot he took, at the reviewed strike", "distance of the strike from goal"
    facts = [_fact(k + 1, mid, f"{shot_label} (published PL reference model)", shot_xg, "xg", xg(shot_xg), ssrc,
                   players=who, role="actual"),
             _fact(k + 3, mid, dist_label, dist, "metres", metres(dist), ssrc, role="distance")]
    if best:
        facts += [_fact(k + 2, mid, "xG after the pass (P(pass completes) x reference xG at the receiver)",
                        best["xg_after_pass"], "xg", xg(best["xg_after_pass"]), src, players=who, role="alternative"),
                  _fact(k + 4, mid, "chance the pass completes (pass model)", best["p_pass"], "percent",
                        whole_pct(best["p_pass"]), src, role="p_pass"),
                  _fact(k + 5, mid, "reference xG of a shot from the receiver's spot", best["xg_receiver"], "xg",
                        xg(best["xg_receiver"]), src, role="xg_receiver")]
    view = {"clip_ms": clip_ms, "clock": d["clock"], "team": CLIPS[slug][team + "_short"], "verdict": verdict,
            "real_outcome": real, "metric": "xG (published reference model); after a pass: P(complete) x xG",
            "holder": {x: holder.get(x) for x in ("name", "pid", "describe")} if holder else None,
            "actual": {"choice": "shoot", "xg": shot_xg, "distance_m": dist, "event_id": shot["event_id"],
                       "outcome": shot["outcome"], "measured": shot_label, "fact": facts[0]["fact_id"]},
            "alternative": None if not best else
            {"choice": f"pass to {target['name'] if target and target['name'] else (target or {}).get('describe')}",
             "xg_after_pass": best["xg_after_pass"], "p_pass": best["p_pass"], "xg_receiver": best["xg_receiver"],
             "label": best["label"], "onside_margin_m": best.get("onside_margin_m"), "fact": facts[2]["fact_id"],
             "target": {x: target.get(x) for x in ("name", "pid", "describe")} if target else None},
            "overlay_labels": {"actual": "Shot", "alternative": None if not best else
                               (f"Pass to {target['name'].split()[-1]}" if target and target["name"] else "Pass")},
            "excluded_offside": [o["label"] for o in d.get("alternatives") or []
                                 if o.get("offside_risk") or (offside(m, team, o["x"]) or 0) > 0],
            "formula": d.get("formula")}
    return facts, view


V5 = Version("v5", PROMPT, facts_for, lambda ms: f"cache/v5/xg_decision_{ms}.json",
             lambda slug, ms: f"{PROMPT}.xg_{ms}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("slug")
    r.add_argument("clip_ms", type=int)
    r.add_argument("--dry-run", action="store_true")
    sub.add_parser("import")
    args = ap.parse_args(argv)
    out = run(args.slug, args.clip_ms, args.dry_run, V5) if args.cmd == "run" else import_(V5)
    print(json.dumps(out, indent=1, ensure_ascii=False, default=str)[:6000])
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "packages"))
    raise SystemExit(main())
