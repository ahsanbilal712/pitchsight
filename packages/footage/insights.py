"""Captions for the video v3 beats (red-card cost, ghost defender, keeper coverage, win-probability river):
gemini-4-argon writes each from the beat's own numbers, the Fact Checker verifies it, a hand review edits it.

    python -m footage.insights run <slug> <beat_file> [--dry-run]   # one live call per beat (SpendGuard, clip id)
    python -m footage.insights import                                # review/footage/v3_*.md -> caption in the beat

Every number the caption may use becomes a fact document (f_8nnnnn) built from the beat JSON, so a claim cites the
same value the graphic shows. The clip's evidence (match_metadata with the roster and clubs, tagged events) is
loaded too, so real names pass rules 3 and 7 for that match only. Accepted captions are written into the beat under
`caption` {headline, why, claims, source}.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

from footage.clips import CLIPS, ROOT

PROMPT, ROLE = "insight_footage@2", "tactician_golden"     # @1: the river caption (kept with its record)
REVIEW_DIR = ROOT / "review" / "footage"
BLOCK = re.compile(r"```json\n(.*?)\n```", re.S)
SCHEMA = {"type": "object", "required": ["headline", "why", "claims", "confidence"], "properties": {
    "headline": {"type": "string"}, "why": {"type": "string"}, "confidence": {"type": "number"},
    "claims": {"type": "array", "items": {"type": "object", "required": ["text", "kind", "unit", "evidence_ids"],
                                          "properties": {
        "text": {"type": "string"}, "kind": {"type": "string", "enum": ["number", "player", "team", "minute"]},
        "value_number": {"type": "number"}, "value_text": {"type": "string"}, "unit": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}}}}}}}


def _fact(n: int, match_id: str, label: str, value: float, unit: str, source: str, **extra) -> dict:
    return {"fact_id": f"f_8{n:05d}", "match_id": match_id, "label": label, "value": value, "unit": unit,
            "source": source, **extra}


def facts_for(beat: dict) -> list[dict]:
    """The numbers a caption may use, one fact each, from the beat's own fields."""
    mid, kind, out = beat["match_id"], beat["beat"], []
    if kind == "win_prob_river":
        n = 0
        for e in beat["events"]:
            if e["kind"] != "goal":
                continue
            before = max((s for s in beat["series"] if s["clip_ms"] < e["clip_ms"]), key=lambda s: s["clip_ms"],
                         default=None)
            after = min((s for s in beat["series"] if s["clip_ms"] >= e["clip_ms"] + 15_000),
                        key=lambda s: s["clip_ms"], default=None)
            if before is None or after is None:
                continue
            for side in ("home", "away"):
                n += 1
                out.append(_fact(n, mid, f"{side}_win_chance_before {e['label']}", before[side], "win_prob",
                                 beat["source"], event_id=e["source"], clock=e["clock"]))
                n += 1
                out.append(_fact(n, mid, f"{side}_win_chance_after {e['label']}", after[side], "win_prob",
                                 beat["source"], event_id=e["source"], clock=e["clock"]))
    elif kind == "ghost_defender":
        who = [p for p in (beat["shooter"].get("pid"), beat["defender"].get("pid")) if p]
        out = [_fact(1, mid, "goal chance, actual positions (engine rollouts)", beat["p_goal_actual"], "p_goal",
                     beat["source"], players=who),
               _fact(2, mid, "goal chance, defender at the ghost spot (engine rollouts)", beat["p_goal_ghost"],
                     "p_goal", beat["source"], players=who),
               _fact(3, mid, "metres the defender needed", beat["metres_needed"], "metres", beat["source"],
                     players=who),
               _fact(4, mid, "metres he could cover at top speed in the time", beat["reach_m"], "metres",
                     beat["source"]),
               _fact(5, mid, "seconds available (before the shot)", beat["t_avail_s"], "seconds", beat["source"])]
    elif kind == "keeper_cone":
        out = [_fact(1, mid, "share of the goal covered, actual position", beat["coverage_actual"], "percent",
                     beat["source"]),
               _fact(2, mid, "share of the goal covered, best point on the bisector", beat["coverage_best"],
                     "percent", beat["source"]),
               _fact(3, mid, "metres to the best point", beat["move_m"], "metres", beat["source"]),
               _fact(4, mid, "distance of the shot from the goal line", beat["shot_distance_m"], "metres",
                     beat["source"], players=[beat["keeper"].get("pid")] if beat["keeper"].get("pid") else [])]
    elif kind == "fourth_official":
        out = [_fact(1, mid, "closing speed toward the fouled player (assessment)", beat["closing_speed_kmh"], "kmh",
                     beat["source"], players=[beat["fouler"]["pid"], beat["fouled"]["pid"]],
                     event_id=beat["foul_event_id"])]
    elif kind == "recap":
        h, a = beat["final_score"]
        scorers = [g["pid"] for g in beat["goals"] if g.get("pid")]
        out = [_fact(1, mid, f"final score, {beat['home']} goals", h, "count", beat["source"], players=scorers),
               _fact(2, mid, f"final score, {beat['away']} goals", a, "count", beat["source"], players=scorers)]
    elif kind == "red_card_cost":
        out = [_fact(1, mid, "win chance 11 v 11 (engine estimate)", beat["win_prob_11v11"], "win_prob",
                     beat["source"]),
               _fact(2, mid, "win chance 11 v 10 (engine estimate)", beat["win_prob_11v10"], "win_prob",
                     beat["source"])]
    else:
        raise ValueError(f"no caption facts for beat {kind!r}")
    return out


def evidence_board(slug: str, facts: list[dict]):
    from blackboard import SqliteBlackboard
    from footage.featured import open_cache

    manifest = open_cache(slug)
    bb = SqliteBlackboard(":memory:")
    entry = next(e for e in manifest.find(producer="evidence") if e["path"] == "evidence.jsonl")
    for line in (manifest.cache_dir / entry["path"]).read_text().splitlines():
        if line.strip():
            doc = json.loads(line)
            bb.put(doc.pop("_collection"), doc)
    for f in facts:
        bb.put("facts", f)
    return bb


def messages(slug: str, beat: dict, facts: list[dict]) -> list[dict]:
    from footage.featured import footage_block, roster
    from newsroom import config

    _, system = config.prompt(PROMPT)
    view = {k: v for k, v in beat.items() if k not in ("series",)}
    return [{"role": "system", "content": footage_block(slug, roster(slug)) + "\n\n" + system},
            {"role": "user", "content": json.dumps({"BEAT": view, "FACTS": facts}, separators=(",", ":"),
                                                   default=str)}]


def check(match_id: str, body: dict, bb) -> dict:
    from newsroom.executors.tactician import to_claim
    from newsroom.factcheck import verify_claims

    claims = [c for c in (to_claim(x) for x in body.get("claims", []) if isinstance(x, dict)) if c]
    return verify_claims(match_id, claims, bb, {"headline": body.get("headline", ""), "why": body.get("why", "")})


def run(slug: str, beat_path: Path, dry_run: bool = False) -> dict:
    beat = json.loads(Path(beat_path).read_text())["result"]
    facts = facts_for(beat)
    msgs = messages(slug, beat, facts)
    if dry_run:
        return {"facts": facts, "messages": msgs}
    from cache.manifest import CacheManifest
    from footage.featured import open_cache
    from newsroom import config
    from newsroom.llm import LiveClient

    beat_path = Path(beat_path).resolve()
    match_id = CLIPS[slug]["match_id"]
    version = f"{PROMPT}.{beat_path.stem}"
    manifest = open_cache(slug)
    cached = manifest.find(producer="insight", version=version)
    if cached:                                 # the model answer is kept: a re-run never pays twice
        res = manifest.read(cached[0])
    else:
        llm = LiveClient(mode="precompute")
        res = asyncio.run(llm.complete(ROLE, msgs, None, match_id=match_id, moment_id=None, schema=SCHEMA,
                                       prompt_version=PROMPT, producer="insight",
                                       timeout_s=config.role(ROLE).timeout_s, hedge_after_s=None))
        res = {"$schema": "model_cache.schema.json", "schema_version": "1.0.0", "record": "model_result",
               "via": "live", **{k: res.get(k) for k in ("json", "text", "model", "tokens_in", "tokens_out",
                                                          "cost_usd", "latency_ms")}}
        manifest.add(CacheManifest.key(match_id, None, "insight", version, res["model"], int(match_id[2:])),
                     "analytics", res, f"captions/{beat_path.stem}.json", producer="insight", version=version,
                     model=res["model"], seed=int(match_id[2:]), cost_usd=res.get("cost_usd"),
                     tokens_in=res.get("tokens_in"), tokens_out=res.get("tokens_out"))
        manifest.save()
    body = res.get("json") or {}
    bb = evidence_board(slug, facts)
    result = check(CLIPS[slug]["match_id"], body, bb)
    bb.close()
    claims = [{k: c[k] for k in ("text", "kind", "value", "unit", "evidence_ids")} for c in result["claims"]
              if c["verified"]]
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    out = REVIEW_DIR / f"v3_{Path(beat_path).stem}.md"
    doc = {"slug": slug, "beat_file": str(Path(beat_path).relative_to(ROOT)), "headline": body.get("headline", ""),
           "why": body.get("why", ""), "claims": claims, "model": res.get("model"), "cost_usd": res.get("cost_usd"),
           "prompt_version": version.split(".")[0] if "." in version else PROMPT}
    out.write_text(f"# v3 caption · {beat['beat']} · {slug}\n\nModel draft (gemini-4-argon); Fact Checker on it: "
                   f"{'verified' if result['verified'] else json.dumps(result['diff'])}\n\n```json\n"
                   f"{json.dumps(doc, indent=1, ensure_ascii=False)}\n```\n")
    return {"review": str(out), "verified": result["verified"], "diff": result["diff"], "cost_usd": res.get("cost_usd")}


def import_() -> dict:
    """Reviewed captions -> `caption` in their beat JSON, after the Fact Checker passes the edited text."""
    from footage.featured import open_cache

    done, refused = [], {}
    for path in sorted(REVIEW_DIR.glob("v3_*.md")):
        doc = json.loads(BLOCK.search(path.read_text()).group(1))
        beat_file = ROOT / doc["beat_file"]
        wrapper = json.loads(beat_file.read_text())
        beat = wrapper["result"]
        facts = facts_for(beat)
        bb = evidence_board(doc["slug"], facts)
        from newsroom.factcheck import verify_claims

        claims = [{**c, "verified": False, "reject_reason": None} for c in doc["claims"]]
        res = verify_claims(beat["match_id"], claims, bb, {"headline": doc["headline"], "why": doc["why"]})
        bb.close()
        if res["diff"] or not doc["headline"] or len(doc["headline"]) > 60 or len(doc["why"]) > 280:
            refused[path.name] = res["diff"] or "empty or too long"
            continue
        beat["caption"] = {"headline": doc["headline"], "why": doc["why"], "claims": res["claims"],
                           "facts": facts, "model": doc.get("model"),
                           "prompt_version": doc.get("prompt_version", "insight_footage@1"), "hand_reviewed": True}
        manifest = open_cache(doc["slug"])
        entry = next(e for e in manifest.entries if manifest.cache_dir / e["path"] == beat_file)
        manifest.add(entry["key"], entry["kind"], wrapper, entry["path"], producer=entry["producer"],
                     version=entry["version"], seed=entry["seed"], hand_reviewed=True)
        manifest.save()
        done.append(path.name)
    return {"imported": done, "refused": refused}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("slug")
    r.add_argument("beat_file")
    r.add_argument("--dry-run", action="store_true")
    sub.add_parser("import")
    args = ap.parse_args(argv)
    out = run(args.slug, Path(args.beat_file), args.dry_run) if args.cmd == "run" else import_()
    print(json.dumps(out, indent=1, ensure_ascii=False, default=str)[:4000])
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "packages"))
    raise SystemExit(main())
