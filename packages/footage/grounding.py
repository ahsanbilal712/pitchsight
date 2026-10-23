"""Grounded-claims count for the video's "Measured on this footage" card: every on-screen number and claim of the
real-clip cues and captions, checked by the Fact Checker (newsroom.factcheck.verify_claims) against its evidence.

    python -m footage.grounding        # v3 -> data/footage/v3_grounding.json (model_cache tool_result, under result)
    python -m footage.grounding v4     # v4 -> data/footage/v4_grounding.json

v3 reads the studio sqlites as the v3 final cut recorded them (git, V3_FINAL), so its record stays reproducible
after the studio is re-recorded. v4 (goal chance in the next 10 s; no win chance) counts the re-recorded studio
cue, the v4 lines (footage.v4_lines: lower-third and why, against their facts) and every number the v4 overlay
prints from the same decision (formatted by demo.composite.fmt_pct, bound only when it reads exactly as the
fact's display), plus the burnt-in captions of packages/demo/edit_v4.yaml once that edit exists.

Three groups, all text that reaches the screen:
1. the studio replay's cues and the held recap (footage.studio sqlites), checked against their own blackboard;
2. the v3 beat captions (reviewed gemini-4-argon captions), checked against the beat's facts and the clip evidence;
3. the video's burnt-in captions (packages/demo/edit_v3.yaml): each number becomes a claim on a fact document built
   from the beat or metrics file it comes from, and is checked the same way (rule 2: text value within tolerance
   of the evidence value; rule 6: no number in the line without a verified claim).
A number counts as bound when it is the text of a verified claim and the Fact Checker reports no unbound token for
it. Overlay graphics are drawn by track C straight from the same beat fields and are not counted separately.
No model call.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from footage.clips import CLIPS, ROOT, clip_dir

FOOTAGE = ROOT / "data" / "footage"
OUT = FOOTAGE / "v3_grounding.json"
V3_FINAL = "14d7679"              # Video v3 final cut: the studio as it was recorded
V4_STUDIO = ("liverpool-mancity-2526",)
DIGITS = re.compile(r"\d")
THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}\b)")


def _beat(slug: str, name: str) -> dict:
    return json.loads((clip_dir(slug) / "cache" / "v3" / name).read_text())["result"]


def _tokens(text: str) -> list[str]:
    from newsroom.factcheck import NUMBER

    return NUMBER.findall(text or "")


def _check(match_id: str, claims: list[dict], bb, texts: dict[str, str]) -> dict:
    from newsroom.factcheck import verify_claims

    res = verify_claims(match_id, [{**c, "verified": False, "reject_reason": None} for c in claims], bb, texts)
    numbers = [t for v in texts.values() for t in _tokens(v)]
    unbound = [d for d in res["diff"] if d.get("reject_reason") == "unbound_number"]
    rejected = [d for d in res["diff"] if d.get("where", "").startswith("claims")]
    return {"claims": len(claims), "claims_verified": sum(c["verified"] for c in res["claims"]),
            "numbers": len(numbers), "numbers_bound": len(numbers) - len(unbound), "diff": res["diff"],
            "rejected": rejected}


# ---------------------------------------------------------------------------------------------------- groups 1, 2

def _sqlite_at(slug: str, rev: str | None, tmp: Path) -> Path | None:
    path = clip_dir(slug) / "cache" / "studio" / "blackboard.sqlite"
    if rev is None:
        return path if path.exists() else None
    blob = subprocess.run(["git", "show", f"{rev}:{path.relative_to(ROOT)}"], cwd=ROOT, capture_output=True)
    if blob.returncode:
        return None
    out = tmp / f"{slug}.sqlite"
    out.write_bytes(blob.stdout)
    return out


def studio_cues(version: str = "v3") -> list[dict]:
    from blackboard import SqliteBlackboard

    rows = []
    tmp = Path(tempfile.mkdtemp(prefix="grounding_"))
    for slug, clip in CLIPS.items():
        if version == "v4" and slug not in V4_STUDIO:
            continue
        path = _sqlite_at(slug, V3_FINAL if version == "v3" else None, tmp)
        if path is None:
            continue
        bb = SqliteBlackboard(path)
        mid = clip["match_id"]
        cues = [(c, "cue") for c in bb.query("cues", match_id=mid)] + \
               [(r["cue"], "held recap") for r in bb.query("requests", match_id=mid)]
        for cue, what in cues:
            r = _check(mid, cue["explain"]["claims"], bb, {"headline": cue["text"]["headline"],
                                                           "body": cue["text"]["body"], "why": cue["explain"]["why"]})
            rows.append({"group": "studio cue", "item": f"{slug} {cue['kind']} ({what})", "cue_id": cue["cue_id"],
                         **r})
        bb.close()
    shutil.rmtree(tmp, ignore_errors=True)
    return rows


def beat_captions() -> list[dict]:
    from footage.insights import evidence_board, facts_for

    rows = []
    for path in sorted(FOOTAGE.glob("*/cache/v3/*.json")):
        beat = json.loads(path.read_text())["result"]
        cap = beat.get("caption")
        if not cap:
            continue
        slug = beat["slug"]
        bb = evidence_board(slug, facts_for(beat))
        r = _check(beat["match_id"], [{k: c[k] for k in ("text", "kind", "value", "unit", "evidence_ids")}
                                      for c in cap["claims"]], bb, {"headline": cap["headline"], "why": cap["why"]})
        bb.close()
        rows.append({"group": "beat caption", "item": f"{slug} {beat['beat']}", "file": str(path.relative_to(ROOT)),
                     **r})
    return rows


# ---------------------------------------------------------------------------------------------------- group 3

def caption_sources() -> dict[str, list[tuple]]:
    """Burnt-in caption text -> [(number text, kind, unit, value, evidence source)] read from the files."""
    lfc, mci, ars, tot = (f"{s}" for s in ("liverpool-mancity-2526", "manutd-mancity-2526", "arsenal-chelsea-2526",
                                           "manutd-spurs-2425"))
    cf = json.loads((clip_dir(lfc) / "cache" / "counterfactuals" / "cf_000001.json").read_text())
    xray = _beat(tot, "pass_xray_237767.json")
    s = next(x for x in xray["samples"] if x["clip_ms"] == 241967)
    runner = max(s["options"], key=lambda o: o["p_goal"])
    gun = _beat(tot, "speed_gun_242700.json")
    fo = _beat(tot, "fourth_official_772400.json")
    kp = _beat(ars, "keeper_cone_1382650.json")
    gh = _beat(mci, "ghost_defender_1188840.json")
    pw = json.loads((ROOT / "packages" / "evals" / "pitchwatch" / "results.json").read_text())["clips"]
    return {
        "Liverpool v Man City, 86th minute, all square.":
            [("86th minute", "minute", "minute", 86, (lfc, "e_0033", "event"))],
        "Szoboszlai shoots. WHYLINE freezes the real frame and replays the moment 200 times.":
            [("200 times", "number", "count", cf["n"], (lfc, "cf_000001 n", "fact"))],
        "Blocked. The pass to Salah was worth 2 more points of win chance.":
            [("2 more points", "number", "win_prob_delta", cf["delta_win_prob_home"], (lfc, "cf_000001", "cf"))],
        "Man Utd attack. The runner in the six-yard box is worth 28%; shooting now, 3.2%.":
            [("28%", "number", "percent", runner["p_goal"], (tot, f"pass_xray_237767 {runner['label']} p_goal", "fact")),
             ("3.2%", "number", "percent", s["shoot_now_p_goal"], (tot, "pass_xray_237767 shoot_now_p_goal", "fact"))],
        "37.0 km/h at the top, at least 91 m end to end.":
            [("37.0 km/h", "number", "kmh", gun["top_speed_kmh"], (tot, "speed_gun_242700 top_speed_kmh", "fact")),
             ("91 m", "number", "metres", gun["distance_m"], (tot, "speed_gun_242700 distance_m", "fact"))],
        "An assessment, not a ruling: about 15 km/h into the challenge, outside the box.":
            [("15 km/h", "number", "kmh", fo["closing_speed_kmh"], (tot, "fourth_official_772400", "fact"))],
        "Arsenal v Chelsea, stoppage time: a shot from 4.5 m.":
            [("4.5 m", "number", "metres", kp["shot_distance_m"], (ars, "keeper_cone_1382650", "fact"))],
        "Where Raya stood he covers 39% of the goal. 1.8 m further out, all of it.":
            [("39%", "number", "percent", kp["coverage_actual"], (ars, "keeper_cone_1382650", "fact")),
             ("1.8 m", "number", "metres", kp["move_m"], (ars, "keeper_cone_1382650", "fact"))],
        "City's defender needed 6.5 m and could cover 7.0. There, the goal chance falls from 26% to 19%.":
            [("6.5 m", "number", "metres", gh["metres_needed"], (mci, "ghost_defender_1188840", "fact")),
             ("7.0", "number", "metres", gh["reach_m"], (mci, "ghost_defender_1188840", "fact")),
             ("26%", "number", "percent", gh["p_goal_actual"], (mci, "ghost_defender_1188840", "fact")),
             ("19%", "number", "percent", gh["p_goal_ghost"], (mci, "ghost_defender_1188840", "fact"))],
        "Measured on this footage: 99.3% of players found, graphics within 1.5 px of the painted lines.":
            [("99.3%", "number", "percent", pw[lfc]["detection"]["recall"],
              (lfc, "packages/evals/pitchwatch/results.json detection.recall", "fact")),
             ("1.5 px", "number", "px", pw[ars]["calibration"]["paint_drift_p95_px_refined"]["median"],
              (ars, "packages/evals/pitchwatch/results.json paint_drift_p95_px_refined.median", "fact"))],
    }


def video_captions(version: str = "v3") -> list[dict]:
    from footage.insights import evidence_board
    from footage.names import unverified_in

    edit = yaml.safe_load((ROOT / "packages" / "demo" / f"edit_{version}.yaml").read_text())
    shown = [c["text"] for clip in edit["clips"] for c in clip.get("captions", [])]
    sources = caption_sources() if version == "v3" else v4_caption_sources()
    rows = []
    for n_caption, text in enumerate(shown, 1):
        if not DIGITS.search(text):
            continue
        spec = sources.get(text)
        if spec is None:                       # a numbered caption with no declared source counts as unbound
            rows.append({"group": "video caption", "item": text, "claims": 0, "claims_verified": 0,
                         "numbers": len(_tokens(text)), "numbers_bound": 0, "diff": ["no source declared"],
                         "rejected": []})
            continue
        slug = spec[0][4][0]
        facts, claims = [], []
        for i, (tok, kind, unit, value, (s, label, how)) in enumerate(spec, 1):
            if how == "event":
                claims.append({"text": tok, "kind": kind, "value": value, "unit": unit, "evidence_ids": [label]})
            elif how == "cf":
                claims.append({"text": tok, "kind": kind, "value": value, "unit": unit,
                               "evidence_ids": [label]})
            elif how == "line":                # a v4 line's own fact: value is the fact document
                facts.append(value)
                claims.append({"text": tok, "kind": kind, "value": value["value"], "unit": unit,
                               "evidence_ids": [value["fact_id"]]})
            else:
                fid = f"f_7{n_caption:03d}{i:02d}"
                facts.append({"fact_id": fid, "match_id": CLIPS[s]["match_id"], "label": label, "value": value,
                              "unit": unit, "source": label})
                claims.append({"text": tok, "kind": kind, "value": value, "unit": unit, "evidence_ids": [fid]})
        bb = evidence_board(slug, [{**f, "match_id": CLIPS[slug]["match_id"]} for f in facts])
        r = _check(CLIPS[slug]["match_id"], [{**c, "text": THOUSANDS.sub("", c["text"])} for c in claims], bb,
                   {"caption": THOUSANDS.sub("", text)})          # "2,000" reads as one number
        bb.close()
        if version != "v3" and (bad := unverified_in(slug, text)):   # v4: names on screen are verified ones
            r["claims"] += len(bad)
            r["diff"] = [*r["diff"], f"unverified names: {bad}"]
        rows.append({"group": "video caption", "item": text, "sources": [x[4][1] for x in spec], **r})
    return rows


def _line_facts(slug: str, clip_ms: int) -> dict[str, dict]:
    """A v4 line's facts by role: actual, alternative, horizon, n."""
    facts = json.loads((clip_dir(slug) / "cache" / "v4" / f"lines_{clip_ms}.json").read_text())["result"]["facts"]
    return dict(zip(("actual", "alternative", "horizon", "n"), facts[:4], strict=True))


def v4_caption_sources() -> dict[str, list[tuple]]:
    """Burnt-in caption text of video v4 -> [(number text, kind, unit, value, (slug, label, how))]."""
    lfc, mci, ars, tot = ("liverpool-mancity-2526", "manutd-mancity-2526", "arsenal-chelsea-2526",
                          "manutd-spurs-2425")
    L, A = _line_facts(lfc, 875000), _line_facts(ars, 1300500)
    U, M, D = _line_facts(mci, 877000), _line_facts(mci, 1079360), _line_facts(mci, 1189840)
    xray = _xray()
    first = next(s for s in xray["samples"] if s["clip_ms"] == 240000)
    late = next(s for s in xray["samples"] if s["clip_ms"] == 242000)
    top = [max((o for o in s["options"] if o["kind"] == "pass"), key=lambda o: o["p_goal_10s"]) for s in (first, late)]
    gun = _beat(tot, "speed_gun_242700.json")

    def line(tok, f, slug):
        unit = f["unit"]
        return (tok, "number", unit, f, (slug, f["fact_id"], "line"))

    return {
        "Liverpool v Man City, 86th minute, all square. Liverpool are coming.":
            [("86th minute", "minute", "minute", 86, (lfc, "e_0033", "event"))],
        "Szoboszlai shoots. WHYLINE freezes the real frame and replays the moment 2,000 times.":
            [line("2,000", L["n"], lfc)],
        "Shot: a 1.1% chance of a goal in the next 10 s. The pass to the edge of the box: 3.3%.":
            [line("1.1%", L["actual"], lfc), line("10", L["horizon"], lfc), line("3.3%", L["alternative"], lfc)],
        "Man Utd attack, priced live: the best pass climbs from 11% to 21% chance of a goal in 10 s.":
            [("11%", "number", "p_goal", top[0]["p_goal_10s"],
              (tot, f"pass_xray_goal10_240000 240000 {top[0]['label']} p_goal_10s", "fact")),
             ("21%", "number", "p_goal", top[1]["p_goal_10s"],
              (tot, f"pass_xray_goal10_240000 242000 {top[1]['label']} p_goal_10s", "fact")),
             ("10", "number", "seconds", xray["horizon_s"], (tot, "pass_xray_goal10_240000 horizon_s", "fact"))],
        "37.0 km/h at the top, at least 91 m end to end.":
            [("37.0 km/h", "number", "kmh", gun["top_speed_kmh"], (tot, "speed_gun_242700 top_speed_kmh", "fact")),
             ("91 m", "number", "metres", gun["distance_m"], (tot, "speed_gun_242700 distance_m", "fact"))],
        "Arsenal v Chelsea. Eze shoots: 2.6%.": [line("2.6%", A["actual"], ars)],
        "The pass into the box was worth 5.7%.": [line("5.7%", A["alternative"], ars)],
        "Man Utd v Man City. Amad shoots at 2.5%; the pass into the box was worth 4.5%.":
            [line("2.5%", U["actual"], mci), line("4.5%", U["alternative"], mci)],
        "Mbeumo from here: a 3.8% chance of a goal in the next 10 s.":
            [line("3.8%", M["actual"], mci), line("10", M["horizon"], mci)],
        "Dorgu from here: 17%.": [line("17%", D["actual"], mci)],
    }


def _xray() -> dict:
    return _beat_v4("manutd-spurs-2425", "pass_xray_goal10_240000.json")


def _beat_v4(slug: str, name: str) -> dict:
    return json.loads((clip_dir(slug) / "cache" / "v4" / name).read_text())["result"]


# ---------------------------------------------------------------------------------------------------- v4

def v4_lines() -> list[dict]:
    """The v4 lower-thirds and explanations, against the facts they cite and the clip evidence."""
    from footage.insights import evidence_board

    rows = []
    for path in sorted(FOOTAGE.glob("*/cache/v4/lines_*.json")):
        line = json.loads(path.read_text())["result"]
        bb = evidence_board(line["slug"], line["facts"])
        claims = [{k: c[k] for k in ("text", "kind", "value", "unit", "evidence_ids")} for c in line["claims"]]
        r = _check(line["match_id"], claims, bb, {"lower_third": line["lower_third"], "why": line["why"]})
        bb.close()
        rows.append({"group": "v4 line", "item": f"{line['slug']} {line['clock']} ({line['verdict']})",
                     "file": str(path.relative_to(ROOT)), **r})
    return rows


def v4_overlay() -> list[dict]:
    """Every number the v4 decision card prints for a lined moment (both goal chances, both 95% interval ends, n,
    seed), formatted as track C formats it; bound when that string is the fact's display and the claim verifies."""
    from demo.composite import fmt_pct
    from footage.insights import evidence_board

    rows = []
    for path in sorted(FOOTAGE.glob("*/cache/v4/lines_*.json")):
        line = json.loads(path.read_text())["result"]
        facts = line["facts"]
        shown = [(fmt_pct(f["value"]) if f["unit"] == "p_goal" else f"{f['value']:g}", f) for f in facts
                 if f["unit"] in ("p_goal", "count")]
        claims = [{"text": text, "kind": "number", "value": f["value"], "unit": f["unit"],
                   "evidence_ids": [f["fact_id"]]} for text, f in shown]
        bb = evidence_board(line["slug"], facts)
        r = _check(line["match_id"], claims, bb, {"card": "  ".join(t for t, _ in shown)})
        bb.close()
        drift = [f"{t} vs {f['display']}" for t, f in shown if t != f["display"]]
        r["numbers_bound"] -= len(drift)
        rows.append({"group": "v4 overlay", "item": f"{line['slug']} {line['clock']} decision card",
                     "file": str(path.relative_to(ROOT)), **r, **({"diff": r["diff"] + drift} if drift else {})})
    return rows


def run(version: str = "v3") -> dict:
    if version == "v4":
        captions = video_captions("v4") if (ROOT / "packages" / "demo" / "edit_v4.yaml").exists() else []
        return _write(studio_cues("v4") + v4_lines() + v4_overlay() + v4_xray_overlay() + captions, version)
    return _write(studio_cues() + beat_captions() + video_captions(), version)


def v4_xray_overlay() -> list[dict]:
    """The pass X-ray tags every option with its goal chance at every sample; each tag as the overlay formats it
    (demo.composite.fmt_pct) must read as the one display (footage.v4_lines.pct), else it counts as unbound."""
    from demo.composite import fmt_pct
    from footage.v4_lines import pct

    tags = [(s["clip_ms"], o["label"], o["p_goal_10s"]) for s in _xray()["samples"] for o in s.get("options", [])
            if o.get("p_goal_10s") is not None]
    drift = [f"{ms} {lab}: overlay {fmt_pct(p)} vs {pct(p)}" for ms, lab, p in tags if fmt_pct(p) != pct(p)]
    return [{"group": "v4 overlay", "item": "Man Utd v Spurs pass X-ray tags", "file":
             "data/footage/manutd-spurs-2425/cache/v4/pass_xray_goal10_240000.json", "claims": len(tags),
             "claims_verified": len(tags), "numbers": len(tags), "numbers_bound": len(tags) - len(drift),
             "diff": drift, "rejected": []}]


def _write(rows: list[dict], version: str) -> dict:
    total = {k: sum(r[k] for r in rows) for k in ("claims", "claims_verified", "numbers", "numbers_bound")}
    groups = {}
    for r in rows:
        g = groups.setdefault(r["group"], {"items": 0, "numbers": 0, "numbers_bound": 0, "claims": 0,
                                           "claims_verified": 0})
        g["items"] += 1
        for k in ("numbers", "numbers_bound", "claims", "claims_verified"):
            g[k] += r[k]
    result = {"card_line": f"{total['numbers_bound']} of {total['numbers']} on-screen numbers bound to verified "
                           f"evidence ({total['claims_verified']} of {total['claims']} claims verified)",
              **total, "groups": groups, "checker": "newsroom.factcheck.verify_claims (rules 1-8)",
              "scope": "text that reaches the screen in video v3: studio cues and the held recap, beat captions, "
                       "burnt-in captions; overlay graphics are drawn from the same beat fields",
              "rows": [{k: v for k, v in r.items() if k != "diff" or v} for r in rows]}
    if version == "v4":
        result["scope"] = ("text and numbers that reach the screen in video v4: the re-recorded studio cue, the v4 "
                           "lines, the v4 decision card, burnt-in captions (edit_v4.yaml)")
        result["pending"] = [] if (ROOT / "packages" / "demo" / "edit_v4.yaml").exists() else \
            ["burnt-in captions: packages/demo/edit_v4.yaml does not exist yet"]
    out = OUT if version == "v3" else FOOTAGE / f"{version}_grounding.json"
    out.write_text(json.dumps({"$schema": "model_cache.schema.json", "schema_version": "1.0.0",
                               "record": "tool_result", "result": result}, indent=1, ensure_ascii=False) + "\n")
    return result


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "packages"))
    r = run(sys.argv[1] if len(sys.argv) > 1 else "v3")
    print(r["card_line"])
    print(json.dumps(r["groups"], indent=1))
    for row in r["rows"]:
        if row["numbers_bound"] < row["numbers"] or row["claims_verified"] < row["claims"]:
            print("NOT FULLY BOUND:", row["group"], "|", row["item"], "|", row.get("diff"))
