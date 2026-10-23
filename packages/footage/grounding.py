"""Grounded-claims count for the video's "Measured on this footage" card: every on-screen number and claim of the
real-clip cues and captions, checked by the Fact Checker (newsroom.factcheck.verify_claims) against its evidence.

    python -m footage.grounding [--edit packages/demo/edit_v4.yaml]   # default: the latest edit_vN.yaml
    # -> data/footage/vN_grounding.json (model_cache tool_result, under result); N from the edit's name

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
from decimal import Decimal
from pathlib import Path

import yaml

from footage.clips import CLIPS, ROOT, clip_dir

FOOTAGE = ROOT / "data" / "footage"
OUT = FOOTAGE / "v3_grounding.json"
V3_FINAL = "14d7679"              # Video v3 final cut: the studio as it was recorded
V4_FINAL = "6920af1"              # v4 grounding at 170 of 170: the studio before the v5 re-record
V4_STUDIO = ("liverpool-mancity-2526",)
V5_STUDIO = ("liverpool-mancity-2526", "manutd-mancity-2526")   # re-recorded on the v5 lines (Amad's is the beat)
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
        if version in ("v4", "v5") and slug not in {"v4": V4_STUDIO, "v5": V5_STUDIO}[version]:
            continue
        path = _sqlite_at(slug, {"v3": V3_FINAL, "v4": V4_FINAL}.get(version), tmp)
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
    gun = _beat(tot, "speed_gun_242700.json")             # the Spurs pass X-ray caption is withdrawn (WITHDRAWN)
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


def latest_edit() -> Path:
    return max((ROOT / "packages" / "demo").glob("edit_v*.yaml"), key=lambda p: int(p.stem.split("_v")[1]))


def version_of(edit: Path) -> str:
    return "v" + Path(edit).stem.split("_v")[1]


def video_captions(version: str = "v3", edit_path: Path | None = None) -> list[dict]:
    from footage.insights import evidence_board
    from footage.names import unverified_in

    edit = yaml.safe_load((edit_path or ROOT / "packages" / "demo" / f"edit_{version}.yaml").read_text())
    shown = [c["text"] for clip in edit["clips"] for c in clip.get("captions", [])]
    sources = {"v3": caption_sources, "v4": v4_caption_sources, "v5": v5_caption_sources,
               "v6": v6_caption_sources}[version]()
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
        if version != "v3" and (bad := unverified_in(slug, text)):   # v4+: names on screen are verified ones
            r["claims"] += len(bad)
            r["diff"] = [*r["diff"], f"unverified names: {bad}"]
        rows.append({"group": "video caption", "item": text, "sources": [x[4][1] for x in spec], **r})
    return rows


def _line_facts(slug: str, clip_ms: int) -> dict[str, dict]:
    """A v4 line's facts by role (actual, alternative, horizon, n, ...; a finishing line has no alternative)."""
    facts = json.loads((clip_dir(slug) / "cache" / "v4" / f"lines_{clip_ms}.json").read_text())["result"]["facts"]
    return {f["role"]: f for f in facts}


def v4_caption_sources() -> dict[str, list[tuple]]:
    """Burnt-in caption text of video v4 -> [(number text, kind, unit, value, (slug, label, how))]."""
    lfc, mci, ars, tot = ("liverpool-mancity-2526", "manutd-mancity-2526", "arsenal-chelsea-2526",
                          "manutd-spurs-2425")
    L, A = _line_facts(lfc, 875000), _line_facts(ars, 1300500)
    U, M, D = _line_facts(mci, 877000), _line_facts(mci, 1079360), _line_facts(mci, 1189840)
    gun = _beat(tot, "speed_gun_242700.json")             # the Spurs pass X-ray caption is withdrawn (WITHDRAWN)

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


def v5_caption_sources() -> dict[str, list[tuple]]:
    """Burnt-in caption text of video v5 -> [(number text, kind, unit, value, (slug, label, how))]: shots and the
    race from track A's cache/v5 files, freezes from the reviewed v5 lines, the clip's span from its title."""
    lfc, mci, ars, tot = ("liverpool-mancity-2526", "manutd-mancity-2526", "arsenal-chelsea-2526",
                          "manutd-spurs-2425")

    def shot(slug, eid):
        s = next(x for x in _v5(slug, "shots_0.json")["shots"] if x["event_id"] == eid)
        return s

    def xg_of(tok, slug, eid):
        return (tok, "number", "xg", shot(slug, eid)["xg"], (slug, f"v5 shots_0 {eid} xg", "fact"))

    def dist_of(tok, slug, eid):
        return (tok, "number", "metres", shot(slug, eid)["distance_m"], (slug, f"v5 shots_0 {eid} distance_m", "fact"))

    def line(tok, slug, ms, role):
        f = {f["role"]: f for f in _v5(slug, f"lines_{ms}.json")["facts"]}[role]
        return (tok, "number", f["unit"], f, (slug, f["fact_id"], "line"))

    def shot_xg(tok, slug, ms, caption):
        """Lead's ruling: a shot number said "from here" is the freeze value (xg_decision, frame_role freeze),
        any other the reviewed strike (shots_0, frame_role strike)."""
        d = _v5(slug, f"xg_decision_{ms}.json")
        if "from here" in caption.lower():
            return (tok, "number", "xg", d["actual"].get("xg_exact", d["actual"]["xg"]),
                    (slug, f"v5 xg_decision_{ms} actual.xg (freeze)", "fact"))
        return xg_of(tok, slug, d["actual"]["event_id"])

    race = _v5(lfc, "xg_race_0.json")["series"][-1]
    title = json.loads((clip_dir(lfc) / "description.json").read_text())["title"]
    return {
        "Liverpool v Man City. Szoboszlai's free kick: 0.02 xG. In.": [xg_of("0.02", lfc, "e_0006")],
        "Silva equalises: 0.28 xG.": [xg_of("0.28", lfc, "e_0027")],
        "Haaland's penalty: 0.76.": [xg_of("0.76", lfc, "e_0048")],
        "86th minute, all square. Szoboszlai shoots from 29 m.":
            [("86th minute", "minute", "minute", 86, (lfc, "e_0033", "event")), dist_of("29 m", lfc, "e_0033")],
        "0.02 xG: the keeper, the cone, the bodies in the way. Blocked.": [xg_of("0.02", lfc, "e_0033")],
        "Man Utd v Man City. Amad shoots from here: 0.06 xG.":
            [shot_xg("0.06", mci, 877000, "Amad shoots from here")],
        "The pass into the box was worth 0.11, almost twice as much.": [line("0.11", mci, 877000, "alternative")],
        "Seconds later, 0.32 xG: saved.": [xg_of("0.32", mci, "e_0038")],
        "Arsenal v Chelsea. Eze from 16 m: 0.08 xG. Saved.":
            [dist_of("16 m", ars, "e_0046"), xg_of("0.08", ars, "e_0046")],
        "Mbeumo from here: 0.10 xG.": [shot_xg("0.10", mci, 1079360, "Mbeumo from here")],
        "Dorgu, from 4.5 m: 0.48 xG.": [dist_of("4.5 m", mci, "e_0054"), line("0.48", mci, 1189840, "actual")],
        "It replays the pass 2,000 times. This is the most typical future, on the real pitch.":
            [("2,000", "number", "count", _beat_v4(mci, "ghost_future_877000.json")["n"],
              (mci, "v4 ghost_future_877000 n (the pass to #19, medoid of n futures)", "fact"))],
        "Werner, from 16 m: 0.08 xG. Saved.":
            [line("16 m", tot, 682800, "distance"), line("0.08", tot, 682800, "actual")],
        "Liverpool v Man City, the last 20 minutes in xG: City 1.21, Liverpool 0.20.":
            [("20", "number", "count", 20 if "Final 20 Minutes" in title else None,
              (lfc, "description.json title (Final 20 Minutes)", "fact")),
             ("1.21", "number", "xg", race["away_xg"], (lfc, "v5 xg_race_0 final away_xg", "fact")),
             ("0.20", "number", "xg", race["home_xg"], (lfc, "v5 xg_race_0 final home_xg", "fact"))],
    }


def _v5(slug: str, name: str) -> dict:
    return json.loads((clip_dir(slug) / "cache" / "v5" / name).read_text())["result"]


def _beat_v4(slug: str, name: str) -> dict:
    return json.loads((clip_dir(slug) / "cache" / "v4" / name).read_text())["result"]


# ---------------------------------------------------------------------------------------------------- v4

def v4_lines() -> list[dict]:
    """The v4 lower-thirds and explanations, against the facts they cite and the clip evidence."""
    return _lines_rows("v4")


def _lines_rows(tag: str) -> list[dict]:
    from footage.insights import evidence_board

    rows = []
    for path in sorted(FOOTAGE.glob(f"*/cache/{tag}/lines_*.json")):
        line = json.loads(path.read_text())["result"]
        bb = evidence_board(line["slug"], line["facts"])
        claims = [{k: c[k] for k in ("text", "kind", "value", "unit", "evidence_ids")} for c in line["claims"]]
        r = _check(line["match_id"], claims, bb, {"lower_third": line["lower_third"], "why": line["why"]})
        bb.close()
        rows.append({"group": f"{tag} line", "item": f"{line['slug']} {line['clock']} ({line['verdict']})",
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
        shown = [(fmt_pct(f["value"]) if f["unit"] == "p_goal" else
                  f"{f['value']:,}" if f.get("role") == "n" else f"{f['value']:g}", f) for f in facts
                 if f["unit"] in ("p_goal", "count")]                  # the card prints "n = 2,000, ..., seed 4242"
        claims = [{"text": THOUSANDS.sub("", text), "kind": "number", "value": f["value"], "unit": f["unit"],
                   "evidence_ids": [f["fact_id"]]} for text, f in shown]
        bb = evidence_board(line["slug"], facts)
        r = _check(line["match_id"], claims, bb, {"card": THOUSANDS.sub("", "  ".join(t for t, _ in shown))})
        bb.close()
        drift = [f"{t} vs {f['display']}" for t, f in shown if t != f["display"]]
        r["numbers_bound"] -= len(drift)
        rows.append({"group": "v4 overlay", "item": f"{line['slug']} {line['clock']} decision card",
                     "file": str(path.relative_to(ROOT)), **r, **({"diff": r["diff"] + drift} if drift else {})})
    return rows


def run(version: str = "v3", edit: Path | None = None) -> dict:
    """Count for one video version; `edit` defaults to packages/demo/edit_<version>.yaml."""
    edit = Path(edit) if edit else ROOT / "packages" / "demo" / f"edit_{version}.yaml"
    if version == "v6":
        beats = _v6_beats(edit)
        return _write(v6_lines(beats) + v6_freezes(beats) + v6_live(beats) + v6_shots(beats) + v6_pipeline(beats)
                      + video_captions("v6", edit), version, edit)
    if version == "v5":
        captions = video_captions("v5", edit) if edit.exists() else []
        return _write(studio_cues("v5") + v5_lines() + v5_decisions() + v5_shots_and_race() + v5_ghost_footer(edit)
                      + captions, version, edit)
    if version == "v4":
        captions = video_captions("v4", edit) if edit.exists() else []
        return _write(studio_cues("v4") + v4_lines() + v4_overlay() + v4_small_print() + captions, version, edit)
    return _write(studio_cues() + beat_captions() + video_captions("v3", edit), version, edit)


# ---------------------------------------------------------------------------------------------------- v5

V5_CITATION = {"8,451": 8451, "2017/18": None}   # the reference model's sample, as the formula line prints it


def _row(group: str, item: str, file: str, numbers: int, bound: int, diff: list) -> dict:
    return {"group": group, "item": item, "file": file, "claims": numbers, "claims_verified": bound,
            "numbers": numbers, "numbers_bound": bound, "diff": diff, "rejected": []}


def v5_lines() -> list[dict]:
    return [{**r, "group": "v5 line"} for r in _lines_rows("v5")]


def v5_decisions() -> list[dict]:
    """Every number a v5 beat of the edit prints (demo.composite, lead's rules): the shot (on a decision freeze the
    card's "Shot from here", the freeze value; on a strike or goal beat the reviewed strike from shots_0, card row
    and goal flash alike), the one pass only where the line shows one (+0.04 xG, more than 0.5 m onside), and the
    formula line's numbers; each as {:.2f} of the file's two-decimal values, which must read exactly as the
    reviewed line's display."""
    from footage.v5_lines import strike

    rows = []
    for path in sorted(FOOTAGE.glob("*/cache/v5/xg_decision_*.json")):
        if path.relative_to(ROOT).as_posix() not in _edit_decisions():
            continue                                    # not a beat of the edit (e.g. Werner: montage only)
        x = json.loads(path.read_text())["result"]
        slug, ms = x["slug"], x["clip_ms"]
        line_path = path.with_name(f"lines_{ms}.json")
        if not line_path.exists():
            continue
        line = json.loads(line_path.read_text())["result"]
        roles = {f["role"]: f["display"] for f in line["facts"]}
        freeze = line["verdict"] == "alternative_better"     # a decision freeze: "Shot from here", act["xg"]
        value = x["actual"]["xg"] if freeze else strike(slug, x["actual"]["event_id"])["xg"]
        shown = [("shot" if line["verdict"] != "finishing" else "goal flash", f"{value:.2f}", roles["actual"])]
        if line["decision"]["alternative"]:
            hero = next(o for o in x["alternatives"] if o["label"] == line["decision"]["alternative"]["label"])
            shown.append((f"pass {hero['label']}", f"{hero['xg_after_pass']:.2f}", roles["alternative"]))
        cites = [t for t in V5_CITATION if t in x.get("formula", "")]
        diff = [f"{what}: prints {got}, line shows {want}" for what, got, want in shown if got != want]
        n = len(shown) + len(cites)
        rows.append(_row("v5 overlay", f"{slug} {x['clock']} beat ({line['verdict']})", str(path.relative_to(ROOT)),
                         n, n - len(diff), diff))
    return rows


def _edit_decisions(edit: Path | None = None) -> set[str]:
    """The xg_decision files the v5 edit draws a beat from: an edit shot footage/<beat>_v5 is the beat <beat> of
    packages/demo/footage_moments.yaml, whose `xg` names the file."""
    edit = edit or ROOT / "packages" / "demo" / "edit_v5.yaml"
    beats = yaml.safe_load((ROOT / "packages" / "demo" / "footage_moments.yaml").read_text())["moments"]
    shots = {c["shot"].split("/")[-1].removesuffix("_v5") for c in yaml.safe_load(edit.read_text())["clips"]
             if c.get("shot")}
    return {f"data/footage/{beats[b]['xg'].removeprefix('data/footage/')}" for b in shots
            if isinstance(beats.get(b), dict) and beats[b].get("xg")}


def v5_ghost_footer(edit: Path | None = None) -> list[dict]:
    """A ghost-future beat of the edit prints "the most typical of <n> simulated futures, seed <seed>" (demo.live):
    both from its data file."""
    edit = edit or ROOT / "packages" / "demo" / "edit_v5.yaml"
    beats = yaml.safe_load((ROOT / "packages" / "demo" / "footage_moments.yaml").read_text())["moments"]
    shots = {c["shot"].split("/")[-1] for c in yaml.safe_load(edit.read_text())["clips"] if c.get("shot")}
    rows = []
    for name in sorted(shots):
        b = beats.get(name) or beats.get(name.removesuffix("_v5")) or {}
        if b.get("kind") != "ghost_future":
            continue
        g = json.loads((ROOT / b["data"]).read_text())["result"]
        ok = isinstance(g.get("n"), int) and isinstance(g.get("seed"), int)
        rows.append(_row("v5 overlay", f"{name}: ghost future footer (n {g.get('n'):,}, seed {g.get('seed')})",
                         b["data"], 2, 2 if ok else 0, [] if ok else ["n or seed missing in the file"]))
    return rows


def v5_shots_and_race() -> list[dict]:
    """The xG montage (each measured shot's xG, its shooter's name only if names_verified has that shot) and the
    xG race (its running totals must be the sums of the measured shots)."""
    rows = []
    for path in sorted(FOOTAGE.glob("*/cache/v5/shots_0.json")):
        r = json.loads(path.read_text())["result"]
        slug = r["slug"]
        shots_v = json.loads((clip_dir(slug) / "names_verified.json").read_text())["shots"]
        measured = [s for s in r["shots"] if s.get("xg") is not None]
        diff = [f"{s['event_id']}: name {s['shooter']['name']!r} not verified for this shot" for s in measured
                if s["shooter"].get("name") and (shots_v.get(s["event_id"]) or {}).get("name") is None]
        named = sum(1 for s in measured if s["shooter"].get("name"))
        rows.append(_row("v5 overlay", f"{slug} xG montage", str(path.relative_to(ROOT)), len(measured) + named,
                         len(measured) + named - len(diff), diff))
        race_path = path.with_name("xg_race_0.json")
        if race_path.exists():
            race = json.loads(race_path.read_text())["result"]
            last = race["series"][-1]
            diff = []
            for side in ("home", "away"):
                total = round(sum(Decimal(str(s["xg"])) for s in measured if s["team"] == side), 2)
                if f"{last[f'{side}_xg']:.2f}" != f"{total:.2f}":
                    diff.append(f"{side} race total {last[f'{side}_xg']:.2f} vs shots {total:.2f}")
            rows.append(_row("v5 overlay", f"{slug} xG race totals", str(race_path.relative_to(ROOT)), 2,
                             2 - len(diff), diff))
    return rows


def v4_small_print() -> list[dict]:
    """The Liverpool Oracle card (each sample's goal chance as demo.live.pct prints it, and its "n = 2,000 per
    0.5 s, 10 s, seed 4242") and the ghost future's "the most typical of 2,000 simulated futures, seed 4242": each
    number from its file, each value as the one display (footage.v4_lines.pct)."""
    from demo.live import pct as live_pct
    from footage.v4_lines import pct

    lfc = "liverpool-mancity-2526"
    rows = []
    o = _beat_v4(lfc, "oracle_goal10_867000.json")
    vals = [s["p_goal_10s"]["home"] for s in o["samples"] if (s.get("p_goal_10s") or {}).get("home") is not None]
    drift = [f"{v}: overlay {live_pct(v)} vs {pct(v)}" for v in vals if live_pct(v) != pct(v)]
    tags = len(vals) + 4                                     # + n, the 0.5 s step, the 10 s horizon, the seed
    ok = (o["n"], o["step_ms"], o["horizon_s"]) == (2000, 500, 10.0) and o["seed"] == 4242
    rows.append({"group": "v4 overlay", "item": "Liverpool Oracle card (goal in 10 s, every 0.5 s)",
                 "file": f"data/footage/{lfc}/cache/v4/oracle_goal10_867000.json", "claims": tags,
                 "claims_verified": tags if ok else len(vals), "numbers": tags,
                 "numbers_bound": tags - len(drift) - (0 if ok else 4), "diff": drift, "rejected": []})
    g = _beat_v4(lfc, "ghost_future_875000.json")
    ok = g["n"] == 2000 and g["seed"] == 4242
    rows.append({"group": "v4 overlay", "item": "Liverpool ghost future footer (n, seed)",
                 "file": f"data/footage/{lfc}/cache/v4/ghost_future_875000.json", "claims": 2,
                 "claims_verified": 2 if ok else 0, "numbers": 2, "numbers_bound": 2 if ok else 0, "diff": [],
                 "rejected": []})
    return rows


# ---------------------------------------------------------------------------------------------------- v6

def _v6_beats(edit: Path) -> dict[str, dict]:
    """The beats of an edit: edit shot footage/<name> is footage_moments beat <name> (or <name> less its last
    "_v6", the freezes' render suffix)."""
    beats = yaml.safe_load((ROOT / "packages" / "demo" / "footage_moments.yaml").read_text())["moments"]
    out = {}
    for c in yaml.safe_load(edit.read_text())["clips"]:
        name = (c.get("shot") or "").split("/")[-1]
        for key in (name, name.removesuffix("_v6")):
            if isinstance(beats.get(key), dict):
                out[key] = beats[key]
                break
    return out


def v6_lines(beats: dict) -> list[dict]:
    """The reviewed lines the v6 freezes show (line_v5 of each freeze beat), against their facts."""
    from footage.insights import evidence_board

    rows = []
    for name, b in sorted(beats.items()):
        if not b.get("line_v5"):
            continue
        line = json.loads((ROOT / b["line_v5"]).read_text())["result"]
        bb = evidence_board(line["slug"], line["facts"])
        claims = [{k: c[k] for k in ("text", "kind", "value", "unit", "evidence_ids")} for c in line["claims"]]
        r = _check(line["match_id"], claims, bb, {"lower_third": line["lower_third"], "why": line["why"]})
        bb.close()
        rows.append({"group": "v6 line", "item": f"{name}: {line['lower_third']}", "file": b["line_v5"], **r})
    return rows


def v6_freezes(beats: dict) -> list[dict]:
    """The v6 freeze cards (v5's drawing): the same check as v5_decisions, on the beats of this edit."""
    from footage.v5_lines import strike

    rows = []
    for name, b in sorted(beats.items()):
        if not b.get("line_v5") or not b.get("xg"):
            continue
        x = json.loads((ROOT / b["xg"]).read_text())["result"]
        line = json.loads((ROOT / b["line_v5"]).read_text())["result"]
        roles = {f["role"]: f["display"] for f in line["facts"]}
        freeze = line["verdict"] == "alternative_better"
        value = x["actual"]["xg"] if freeze else strike(x["slug"], x["actual"]["event_id"])["xg"]
        shown = [("shot", f"{value:.2f}", roles["actual"])]
        if line["decision"]["alternative"]:
            hero = next(o for o in x["alternatives"] if o["label"] == line["decision"]["alternative"]["label"])
            shown += [("pass", f"{hero['xg_after_pass']:.2f}", roles["alternative"]),
                      ("arrives", f"{round(hero['p_pass'] * 100)}%", roles["p_pass"])]
        diff = [f"{w}: prints {g}, line shows {v}" for w, g, v in shown if g != v]
        rows.append(_row("v6 overlay", f"{name}: freeze card", b["xg"], len(shown), len(shown) - len(diff), diff))
    return rows


def v6_live(beats: dict) -> list[dict]:
    """The live HUD over each passage's on-screen window (demo.v6.LiveHUD): every option tag (p_pass, xG after
    the pass), the shot-now and best-pass rows. Each printed value is its frame's own; it must also be the
    product it claims to be (xG after the pass = p_pass x xG at the receiver, to the two decimals shown), and a
    printed name or shirt must be a verified live read whose window covers the frame (names_live_0)."""
    rows = []
    for name, b in sorted(beats.items()):
        if b.get("kind") != "live_hud":
            continue
        live = json.loads((ROOT / b["data"]).read_text())["result"]
        names = json.loads((ROOT / b["names_live"]).read_text())["result"]["players"] if b.get("names_live") else []
        ok_names = {(p["label"], p["from_clip_ms"], p["to_clip_ms"]) for p in names if p["name"] or p["shirt"]}
        shown, diff = set(), []
        for fr in live["frames"]:
            if not b["t0"] * 1000 <= fr["clip_ms"] <= b["t1"] * 1000:
                continue
            if fr.get("shot_now_xg") is not None:
                shown.add(("shot now", f"{fr['shot_now_xg']:.2f}"))
            for o in fr.get("options") or []:
                if o.get("xg_after_pass") is None:
                    continue
                shown.add((o["label"], f"{o['p_pass'] * 100:.0f}%", f"{o['xg_after_pass']:.2f}"))
                want = o["p_pass"] * o["xg_receiver"]
                if abs(want - o["xg_after_pass"]) > 0.011:
                    diff.append(f"{fr['clip_ms']} {o['label']}: {o['xg_after_pass']} is not {o['p_pass']} x "
                                f"{o['xg_receiver']}")
                if (o.get("name") or o.get("shirt")) and not any(
                        lab == o["label"] and a <= fr["clip_ms"] <= z for lab, a, z in ok_names):
                    diff.append(f"{fr['clip_ms']} {o['label']}: a name or shirt outside a verified read")
        n = sum(1 if len(t) == 2 else 2 for t in shown)
        rows.append(_row("v6 overlay", f"{name}: live HUD {b['t0']:.1f}-{b['t1']:.1f} s ({len(shown)} distinct tags)",
                         b["data"], n, n - len(diff), diff))
    return rows


def v6_shots(beats: dict) -> list[dict]:
    """Single-shot beats and the shot map: each xG as printed, a name only where that shot is verified; the score
    strip (xg_running_0) must add up to the shot map's measured shots."""
    from footage.names import _same

    rows = []
    for name, b in sorted(beats.items()):
        if b.get("kind") not in ("shot_xg", "shot_map"):
            continue
        slug = b.get("clip") or Path(b["data"]).parts[2]
        doc = json.loads((ROOT / b["data"]).read_text())["result"]
        shots = [x for x in doc["shots"] if x.get("xg") is not None and
                 (b["kind"] == "shot_map" or x["clip_ms"] == b.get("clip_ms"))]
        verified_shots = json.loads((clip_dir(slug) / "names_verified.json").read_text())["shots"]
        diff = []
        for x in shots:
            nm = (x.get("shooter") or {}).get("name")
            v = (verified_shots.get(x["event_id"]) or {}).get("name")
            if nm and not (v and _same(nm, v)):
                diff.append(f"{x['event_id']}: {nm} is not verified for this shot")
        rows.append(_row("v6 overlay", f"{name}: {len(shots)} shot xG", b["data"], len(shots), len(shots) - len(diff),
                         diff))
        if b["kind"] == "shot_map":
            run = json.loads((clip_dir(slug) / "cache" / "v6" / "xg_running_0.json").read_text())["result"]
            last, diff = run["series"][-1], []
            for side in ("home", "away"):
                total = round(sum(Decimal(str(x["xg"])) for x in shots if x["team"] == side), 2)
                if f"{last[f'{side}_xg']:.2f}" != f"{total:.2f}":
                    diff.append(f"{side}: strip {last[f'{side}_xg']:.2f} vs shot map {total:.2f}")
            rows.append(_row("v6 overlay", f"{slug}: score-strip xG totals", "cache/v6/xg_running_0.json", 2,
                             2 - len(diff), diff))
    return rows


def v6_pipeline(beats: dict) -> list[dict]:
    """The pipeline beat (demo.v6.Pipeline on track B's view): every number it prints (the agents' says, the
    options, the line, the latencies) must be a fact of the view, a latency of a node whose source is recorded,
    measured or replay, or a number of the reviewed line; nothing printed where the source is "not recorded"."""
    rows = []
    for name, b in sorted(beats.items()):
        if b.get("kind") != "pipeline":
            continue
        v = json.loads((ROOT / b["data"]).read_text())["result"]
        allowed = {f["display"] for f in v["facts"]} | {t for f in v["facts"] for t in _tokens(f["display"])}
        printed, diff = [], []
        for n in v["nodes"]:
            for text in (n.get("says"), n.get("line"), n.get("draft"), *[c["text"] for c in n.get("claims", [])]):
                printed += [(n["agent"], t) for t in _tokens(text or "")]
            for o in n.get("options", []):
                printed += [(n["agent"], o[k]) for k in ("xg", "xg_after_pass") if o.get(k)]
            if n.get("latency_ms") is not None:
                if n["latency_source"] == "not recorded":
                    diff.append(f"{n['agent']}: a latency printed without a recorded source")
                printed.append((n["agent"], "latency"))
        bad = [f"{a}: {t}" for a, t in printed if t != "latency" and t not in allowed
               and t.replace("%", "") not in allowed]
        diff += bad
        rows.append(_row("v6 overlay", f"{name}: pipeline view ({len(v['nodes'])} agents)", b["data"], len(printed),
                         len(printed) - len(diff), diff))
    return rows


def v6_caption_sources() -> dict[str, list[tuple]]:
    """Burnt-in caption text of video v6 -> sources: the v5 sources where the caption is the same, the live
    passages from track A's cache/v6 files."""
    lfc, mci, ars = "liverpool-mancity-2526", "manutd-mancity-2526", "arsenal-chelsea-2526"
    v5 = v5_caption_sources()
    live = _v6(ars, "live_823600.json")
    best = next(f["best"] for f in live["frames"] if f["clip_ms"] == 834800)
    shots = {x["event_id"]: x for x in _v5(lfc, "shots_0.json")["shots"]}
    L = {f["role"]: f for f in _v5(mci, "lines_877000.json")["facts"]}

    def line(tok, f, slug):
        return (tok, "number", f["unit"], f, (slug, f["fact_id"], "line"))

    def shot(tok, slug, eid):
        x = next(s for s in _v5(slug, "shots_0.json")["shots"] if s["event_id"] == eid)
        return (tok, "number", "xg", x["xg"], (slug, f"v5 shots_0 {eid} xg", "fact"))

    out = {
        "Amad shoots from here: 0.06 xG.": v5["Man Utd v Man City. Amad shoots from here: 0.06 xG."],
        "The pass to Mbeumo, arriving 84% of the time, was worth 0.11.":
            [line("84%", L["p_pass"], mci), line("0.11", L["alternative"], mci)],
        "Szoboszlai shoots from 29 m: 0.02 xG. Blocked.":
            [(("29 m", "number", "metres", shots["e_0033"]["distance_m"], (lfc, "v5 shots_0 e_0033 distance_m", "fact"))),
             shot("0.02", lfc, "e_0033")],
        "Silva: 0.28 xG.": [shot("0.28", lfc, "e_0027")],
        "Haaland's penalty: 0.76.": v5["Haaland's penalty: 0.76."],
        "Mbeumo from 15 m: 0.10 xG.":
            [line("15 m", {r["role"]: r for r in _v5(mci, "lines_1079360.json")["facts"]}["distance"], mci),
             line("0.10", {r["role"]: r for r in _v5(mci, "lines_1079360.json")["facts"]}["actual"], mci)],
        "Dorgu from 4.5 m: 0.48 xG.": v5["Dorgu, from 4.5 m: 0.48 xG."],
        "Liverpool v Man City, the last 20 minutes in xG: City 1.21, Liverpool 0.20.":
            v5["Liverpool v Man City, the last 20 minutes in xG: City 1.21, Liverpool 0.20."],
        "Liverpool v Man City, 86th minute. The pass options update as the play moves.":
            [("86th minute", "minute", "minute", 86, (lfc, "e_0033", "event"))],
        "Arsenal v Chelsea: as the ball moves forward, the best pass climbs to 0.19 xG.":
            [("0.19", "number", "xg", best["xg_after_pass"], (ars, "v6 live_823600 frame 834800 best xg_after_pass",
                                                               "fact"))],
    }
    return out


def _v6(slug: str, name: str) -> dict:
    return json.loads((clip_dir(slug) / "cache" / "v6" / name).read_text())["result"]


WITHDRAWN_REASON = ("withdrawn: the Spurs clip's attack directions were reversed (track A 115f6a0); 240-242 s is "
                    "Man Utd clearing their own box, valued as an attack")
WITHDRAWN = {                     # Man Utd v Spurs pass X-ray captions: not counted, listed with the reason
    "Man Utd attack. The runner in the six-yard box is worth 28%; shooting now, 3.2%.",
    "Man Utd attack, priced live: the best pass climbs from 11% to 21% chance of a goal in 10 s.",
    "Man Utd attack, priced live: the top pass option climbs from 11% to 21% chance of a goal in 10 s.",
    "Man Utd attack, priced live in xG: the top pass option climbs to 0.32.",
}


def _write(rows: list[dict], version: str, edit: Path) -> dict:
    in_edit = {r["item"] for r in rows}
    withdrawn = [{"caption": c, "still_in_edit": c in in_edit, "reason": WITHDRAWN_REASON} for c in sorted(WITHDRAWN)]
    rows = [r for r in rows if r["item"] not in WITHDRAWN]
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
              "rows": [{k: v for k, v in r.items() if k != "diff" or v} for r in rows],
              "withdrawn": {"beats": "Man Utd v Spurs pass X-ray (v3 28% / 3.2%, v4 11% -> 21%, v5 0.32), "
                                     "its tags and its caption", "captions": withdrawn}}
    if version == "v5":
        known = {"goal flash": "track C: print the strike's xG on a finishing beat (the shot he scored)",
                 "shot: prints": "track C: print the strike's xG (shots_0) on the beat",
                 "text_value_mismatch": "track C: the caption must give the strike's xG (lead: every shot at its "
                                        "reviewed strike; Amad 0.07)"}
        result["unbound"] = [{"item": r["item"], "diff": r["diff"],
                              "owner": next((v for k, v in known.items() if k in json.dumps(r["diff"])), "open")}
                             for r in rows if r["numbers_bound"] < r["numbers"] or r["claims_verified"] < r["claims"]]
        result["scope"] = ("text and numbers that reach the screen in video v5 (real-data xG): the re-recorded "
                           "studio cue, the v5 lines, every number the v5 freeze, xG montage, xG race and pass X-ray "
                           "print, burnt-in captions (edit_v5.yaml)")
        result["pending"] = [] if edit.exists() else [f"burnt-in captions: {edit.name} does not exist yet"]
    if version == "v4":
        result["scope"] = ("text and numbers that reach the screen in video v4: the re-recorded studio cue, the v4 "
                           "lines, the v4 decision card, burnt-in captions (edit_v4.yaml)")
        result["pending"] = [] if edit.exists() else [f"burnt-in captions: {edit.name} does not exist yet"]
    result["edit"] = str(edit.relative_to(ROOT)) if edit.is_relative_to(ROOT) else str(edit)
    out = OUT if version == "v3" else FOOTAGE / f"{version}_grounding.json"
    out.write_text(json.dumps({"$schema": "model_cache.schema.json", "schema_version": "1.0.0",
                               "record": "tool_result", "result": result}, indent=1, ensure_ascii=False) + "\n")
    return result


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "packages"))
    import argparse

    ap = argparse.ArgumentParser(description="Grounded on-screen numbers for one video edit")
    ap.add_argument("--edit", type=Path, default=None, help="packages/demo/edit_vN.yaml (default: the latest)")
    args = ap.parse_args()
    edit = (args.edit if args.edit is None or args.edit.is_absolute() else ROOT / args.edit) or latest_edit()
    r = run(version_of(edit), edit)
    print(r["card_line"])
    print(json.dumps(r["groups"], indent=1))
    for row in r["rows"]:
        if row["numbers_bound"] < row["numbers"] or row["claims_verified"] < row["claims"]:
            print("NOT FULLY BOUND:", row["group"], "|", row["item"], "|", row.get("diff"))
