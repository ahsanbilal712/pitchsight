"""Video v5 lines: real-data xG. The lower-third and the explanation for each featured freeze, from track A's
cache/v5/xg_decision_<clip_ms>.json, through the same writer as v4 (footage.v4_lines: gemini-4-argon, the Fact
Checker, the gates, hand review, import to cache/v5/lines_<clip_ms>.json).

    python -m footage.v5_lines run <slug> <clip_ms> [--dry-run]
    python -m footage.v5_lines import

Shot xG is the published reference model at the shooter's spot; xG after a pass is P(pass completes) x the
reference xG from the receiver's spot. Both are deterministic, so the comparison is on the numbers as the screen
shows them (two decimals, as the overlay prints them): the pass is "higher" or "lower" only when the two shown
values differ by at least 0.02 xG; 0.01 is within the rounding of what is shown, so it reads as level (a close
call). A receiver in an offside position at the freeze (beyond the second-last opponent and the ball, toward the
goal his team attacks; moment file) is not an option. A moment that ended in a goal gets a finishing line, with the xG of the shot he scored (the reviewed strike, which
can be closer than the freeze: Dorgu 0.30 at the freeze, 0.48 at the strike); every other shot number is "from
where he stood" at the freeze, where the passes are compared.
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import ROUND_HALF_UP, Decimal

from footage.clips import CLIPS, ROOT, clip_dir
from footage.v4_lines import (
    BEST,
    BETTER,
    CLOSE,
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

PROMPT = "insight_footage@6"
MARGIN_XG = Decimal("0.02")        # the smallest gap between two shown xG values that is not rounding


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


def compare(actual: float, alt: float) -> str:
    gap = Decimal(xg(alt)) - Decimal(xg(actual))
    return BETTER if gap >= MARGIN_XG else BEST if -gap >= MARGIN_XG else CLOSE


def facts_for(slug: str, clip_ms: int) -> tuple[list[dict], dict]:
    d, m = decision(slug, clip_ms), moment(slug, clip_ms)
    mid, src = d["match_id"], f"cache/v5/xg_decision_{clip_ms}.json"
    team = d["team"]
    alts = []
    for o in d.get("alternatives") or []:
        beyond = offside(m, team, o["x"])
        if o.get("gate") or (beyond is not None and beyond > 0):
            continue                                       # not a legal option at the freeze
        alts.append({**o, "offside_margin_m": beyond})
    best = max(alts, key=lambda o: o.get("xg_after_pass_exact", o["xg_after_pass"]), default=None)
    real = outcome(slug, clip_ms)
    if real and real.endswith(" scores"):
        verdict, best = FINISH, None
    else:
        verdict = compare(d["actual"]["xg"], best["xg_after_pass"]) if best else SHOT_ONLY   # no team-mate seen
    holder = person(slug, m, d["holder"])
    target = person(slug, m, best["label"]) if best else None
    who = [x["pid"] for x in (holder, target) if x and x.get("pid")]
    k = 10 * (clip_ms // 100 % 1000)
    a = d["actual"]
    if verdict in (FINISH, SHOT_ONLY) and a.get("strike_reviewed") and a.get("strike_xg") is not None:
        shot_xg, shot_label = a["strike_xg"], "xG of the shot he took, at the strike (reviewed frame)"
    else:                              # the options are compared where he stood at the freeze
        shot_xg, shot_label = a.get("xg_exact", a["xg"]), "xG of a shot from where he stood at the freeze"
    facts = [_fact(k + 1, mid, f"{shot_label} (published PL reference model)", shot_xg, "xg", xg(shot_xg), src,
                   players=who, role="actual")]
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
            "actual": {"choice": "shoot", "xg": shot_xg, "measured": shot_label, "fact": facts[0]["fact_id"]},
            "alternative": None if not best else
            {"choice": f"pass to {target['name'] if target and target['name'] else (target or {}).get('describe')}",
             "xg_after_pass": best["xg_after_pass"], "p_pass": best["p_pass"], "xg_receiver": best["xg_receiver"],
             "label": best["label"], "offside_margin_m": best["offside_margin_m"], "fact": facts[1]["fact_id"],
             "target": {x: target.get(x) for x in ("name", "pid", "describe")} if target else None},
            "overlay_labels": {"actual": "Shot", "alternative": None if not best else
                               (f"Pass to {target['name'].split()[-1]}" if target and target["name"] else "Pass")},
            "excluded_offside": [o["label"] for o in d.get("alternatives") or []
                                 if (offside(m, team, o["x"]) or 0) > 0],
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
