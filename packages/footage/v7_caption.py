"""Video v7: the one caption that explains "dangerous space in view" the first time it appears (track A's
cache/v7/always_*.json: danger_def, control_model), written by gemini-4-argon from the definition, checked by the
Fact Checker and the gates, hand-reviewed.

    python -m footage.v7_caption run [--dry-run]     # one live call (SpendGuard, Man Utd v City's match id)
    python -m footage.v7_caption import              # review/footage/v7_caption.md -> cache/v7/caption_danger.json

Facts: the zone threshold (a shot worth at least 0.05 xG), that the shares add up to 100%, and a worked example
from the first passage the layer appears in (Man Utd v City 56:41, clip 877.0 s: home and away shares as the
overlay prints them, whole percent).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys

from footage.clips import CLIPS, ROOT, clip_dir

PROMPT, ROLE = "insight_footage@9", "tactician_golden"   # @8: both teams' shares (superseded)
SLUG, FILE, AT_MS = "manutd-mancity-2526", "always_869000.json", 877000
REVIEW = ROOT / "review" / "footage" / "v7_caption.md"
BLOCK = re.compile(r"```json\n(.*?)\n```", re.S)
MAX_CHARS = 150
SCHEMA = {"type": "object", "required": ["caption", "claims", "confidence"], "properties": {
    "caption": {"type": "string"}, "confidence": {"type": "number"},
    "claims": {"type": "array", "items": {"type": "object", "required": ["text", "kind", "unit", "evidence_ids"],
                                          "properties": {
        "text": {"type": "string"}, "kind": {"type": "string", "enum": ["number"]},
        "value_number": {"type": "number"}, "unit": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}}}}}}}
BANNED = re.compile(r"\b(possession|territory|pressure|probability of scoring|chance of scoring)\b", re.I)


def source() -> dict:
    return json.loads((clip_dir(SLUG) / "cache" / "v7" / FILE).read_text())["result"]


def facts() -> tuple[list[dict], dict]:
    r = source()
    fr = next(f for f in r["frames"] if f["clip_ms"] == AT_MS)
    mid, src = CLIPS[SLUG]["match_id"], f"cache/v7/{FILE}"
    home, away = r["team_names"]["home"], r["team_names"]["away"]
    out = [
        {"fact_id": "f_700001", "match_id": mid, "label": "zone: cells from which a shot is worth at least this xG",
         "value": 0.05, "unit": "xg", "display": "0.05", "source": f"{src} danger_def"}]
    d = fr["danger"]
    if "share" in d:                   # one number, for the team attacking the goal in view
        out.append({"fact_id": "f_700003", "match_id": mid, "label": f"{d['team_name']} (attacking) share of the "
                    "dangerous space in view at 56:41", "value": d["share"], "unit": "percent",
                    "display": f"{d['share'] * 100:.0f}%", "source": f"{src} frame {AT_MS} danger.share"})
    else:                              # both teams' shares (home + away = 1)
        out += [{"fact_id": "f_700002", "match_id": mid, "label": "the two teams' shares add up to", "value": 1.0,
                 "unit": "percent", "display": "100%", "source": f"{src} danger_def (home + away = 1)"}] + \
            [{"fact_id": f"f_70000{3 + i}", "match_id": mid, "label": f"{r['team_names'][side]} share of the "
              "dangerous space in view at 56:41", "value": d[side], "unit": "percent",
              "display": f"{d[side] * 100:.0f}%", "source": f"{src} frame {AT_MS} danger.{side}"}
             for i, side in enumerate(("home", "away"))]
    view = {"DEFINITION": r["danger_def"], "CONTROL": r["control_model"], "attacking_team": home,
            "defending_team": away, "on_screen": d.get("text") or "<team> control NN% of the danger zone in view"}
    return out, view


def gates(body: dict, fs: list[dict]) -> list[str]:
    problems = []
    text = body.get("caption", "")
    by_id = {f["fact_id"]: f for f in fs}
    for c in body.get("claims", []):
        shown = [by_id[e]["display"] for e in c.get("evidence_ids", []) if e in by_id]
        if c.get("text") not in shown:
            problems.append(f"claim {c.get('text')!r} is not its fact's display {shown}")
    if BANNED.search(text):
        problems.append("the metric is not possession, territory, pressure or a scoring probability")
    if not text or len(text) > MAX_CHARS:
        problems.append(f"caption empty or over {MAX_CHARS} characters")
    if re.search(r"\b(Amad|Mbeumo|Bruno|Casemiro|Dorgu)\b", text):
        problems.append("no player names in this caption")
    return problems


def check(body: dict, fs: list[dict]) -> dict:
    from footage.insights import evidence_board
    from newsroom.factcheck import verify_claims

    claims = [{"text": c["text"], "kind": "number", "value": c.get("value_number", c.get("value")),
               "unit": c.get("unit") or None, "evidence_ids": c["evidence_ids"], "verified": False,
               "reject_reason": None} for c in body.get("claims", [])]
    bb = evidence_board(SLUG, fs)
    res = verify_claims(CLIPS[SLUG]["match_id"], claims, bb, {"caption": body.get("caption", "")})
    bb.close()
    return res


def run(dry_run: bool = False) -> dict:
    from footage.featured import footage_block, roster
    from newsroom import config

    fs, view = facts()
    _, system = config.prompt(PROMPT)
    ros = {**roster(SLUG), "ids": {}, "names": {}}
    msgs = [{"role": "system", "content": footage_block(SLUG, ros) + "\n\n" + system},
            {"role": "user", "content": json.dumps({**view, "FACTS": fs}, ensure_ascii=False)}]
    if dry_run:
        return {"facts": fs, "messages": msgs}
    from cache.manifest import CacheManifest
    from footage.featured import open_cache
    from newsroom.llm import LiveClient

    digest = hashlib.sha256(msgs[1]["content"].encode()).hexdigest()[:8]
    version, mid = f"{PROMPT}.danger.{digest}", CLIPS[SLUG]["match_id"]
    manifest = open_cache(SLUG)
    hit = manifest.find(producer="insight", version=version)
    if hit:
        res = manifest.read(hit[0])
    else:
        out = asyncio.run(LiveClient(mode="precompute").complete(
            ROLE, msgs, None, match_id=mid, moment_id=None, schema=SCHEMA, prompt_version=PROMPT, producer="insight",
            timeout_s=config.role(ROLE).timeout_s, hedge_after_s=None))
        res = {"$schema": "model_cache.schema.json", "schema_version": "1.0.0", "record": "model_result",
               "via": "live", "payload": msgs[1]["content"],
               **{k: out.get(k) for k in ("json", "text", "model", "tokens_in", "tokens_out", "cost_usd",
                                          "latency_ms")}}
        manifest = open_cache(SLUG)                   # reloaded just before the save: other tracks write it too
        manifest.add(CacheManifest.key(mid, None, "insight", version, res["model"], int(mid[2:])), "analytics", res,
                     f"captions/v7_danger_{PROMPT}_{digest}.json", producer="insight", version=version,
                     model=res["model"], seed=int(mid[2:]), cost_usd=res.get("cost_usd"),
                     tokens_in=res.get("tokens_in"), tokens_out=res.get("tokens_out"))
        manifest.save()
    body = res.get("json") or {}
    checked, problems = check(body, fs), gates(body, fs)
    doc = {"caption": body.get("caption", ""), "claims": body.get("claims", []), "model": res.get("model"),
           "cost_usd": res.get("cost_usd"), "latency_ms": res.get("latency_ms"), "prompt_version": PROMPT,
           "version": version}
    REVIEW.write_text(f"# v7 caption · dangerous space in view\n\nModel draft (gemini-4-argon). Fact Checker: "
                      f"{'verified' if checked['verified'] else checked['diff']}. Gates: {problems or 'pass'}.\n"
                      + "".join(f"- {f['fact_id']} {f['label']} = {f['display']}\n" for f in fs)
                      + f"\n```json\n{json.dumps(doc, indent=1, ensure_ascii=False)}\n```\n")
    return {"draft": doc["caption"], "verified": checked["verified"], "diff": checked["diff"], "gates": problems,
            "cost_usd": res.get("cost_usd")}


def import_() -> dict:
    from footage.pipeline import register

    doc = json.loads(BLOCK.search(REVIEW.read_text()).group(1))
    fs, _ = facts()
    checked, problems = check(doc, fs), gates(doc, fs)
    if not doc.get("hand_reviewed") or checked["diff"] or not checked["verified"] or problems:
        return {"refused": checked["diff"] or problems or "not hand-reviewed yet"}
    res = {"beat": "v7_caption", "slug": SLUG, "match_id": CLIPS[SLUG]["match_id"], "metric": "dangerous space in view",
           "caption": doc["caption"], "claims": checked["claims"], "facts": fs, "model": doc["model"],
           "prompt_version": doc["prompt_version"], "hand_reviewed": True, "source": f"cache/v7/{FILE}"}
    register(SLUG, "v7/caption_danger.json", "caption_danger",
             {"$schema": "model_cache.schema.json", "schema_version": "1.0.0", "record": "tool_result", "result": res})
    return {"imported": "cache/v7/caption_danger.json", "caption": doc["caption"]}


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "packages"))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["run", "import"])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    print(json.dumps(run(a.dry_run) if a.cmd == "run" else import_(), indent=1, ensure_ascii=False, default=str)[:3000])
