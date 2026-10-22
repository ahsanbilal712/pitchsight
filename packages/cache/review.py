"""Hand review and the cached cue stream (TECH_PLAN 1.7 "Prompt versioning and few-shots", 1.8 precompute step 6;
T-057).

    replay(manifest)                         every golden moment through the graph from the cache (no model call)
    export_review(manifest, k, out_dir)      review/<moment_id>.md for the k highest-leverage explained moments
    import_review(manifest, review_dir)      edited explanation + line back into the cache (hand_reviewed: true),
                                             each passing the Fact Checker, and appended to the few-shot files
    build_cue_stream(manifest)               every cue the replay delivers (and each recap held for the producer)
                                             as cache entries of kind "cue", with the explanations they cite

A review file carries the moment, its evidence and a JSON block: `explanation` is the Tactician's structured output
(why, claims with value_number / value_text, confidence) and `line` the Narrator's (headline, body, claim texts).
Editing rules: sharper why and line; claims and their numbers stay verified; no new unverified number.
"""

from __future__ import annotations

import asyncio
import json
import re
import tempfile
from pathlib import Path

from cache.manifest import CacheManifest

ROOT = Path(__file__).resolve().parents[2]
FEWSHOT = ROOT / "packages" / "newsroom" / "prompts" / "fewshot"
BLOCK = re.compile(r"```json\n(.*?)\n```", re.S)


def _moments(manifest: CacheManifest) -> list[dict]:
    entry = manifest.find(producer="scout")[0]
    return [json.loads(line) for line in (manifest.cache_dir / entry["path"]).read_text().splitlines()
            if line.strip()]


def evidence_board(manifest: CacheManifest, path: Path | None = None):
    """A blackboard with the golden match's events and evidence.jsonl, as the replay worker preloads it."""
    from blackboard import SqliteBlackboard
    from cache.client import preload_evidence
    from mcp_server.tools_core import MatchStore

    tmp = Path(path or tempfile.mkdtemp(prefix="whyline_review_"))
    bb = SqliteBlackboard(tmp / "bb.sqlite")
    store = MatchStore(bb, matches_dir=manifest.cache_dir.parent.parent, runtime_dir=tmp)
    preload_evidence(bb, manifest, store)
    return bb, store


def replay(manifest: CacheManifest, workdir: Path | None = None) -> dict:
    """{cues, held (recap cues waiting for the producer), bb, misses}: the golden match served from the cache."""
    from cache.client import CacheClient
    from newsroom.executors.base import Deps
    from newsroom.graph import build_workflow
    from newsroom.tools import LocalTools
    from newsroom.worker import run_moment, start_message

    bb, store = evidence_board(manifest, workdir)
    cache = CacheClient(manifest, speed=1e9, inner_tools=LocalTools(store))
    deps = Deps(bb=bb, llm=cache, rollout=cache, store=store, mode="replay", panel_enabled=True)

    async def go():
        cues, held = [], []
        for m in _moments(manifest):
            bb.put("moments", m)
            out = await run_moment(build_workflow(deps), start_message(m, "replay"))
            cues += [c for c in out["outputs"] if isinstance(c, dict)]
            held += [{**ev.data.cue, "producer_status": "held"} for ev in out["requests"]]
        return cues, held

    cues, held = asyncio.run(go())
    return {"cues": cues, "held": held, "bb": bb, "misses": list(cache.misses)}


# ---------------------------------------------------------------------------------------------------- export

def _entry(manifest: CacheManifest, moment_id: str, producer: str, version: str) -> dict | None:
    found = [e for e in manifest.find(moment_id=moment_id, producer=producer, version=version)
             if not manifest.read(e).get("error")]
    return found[0] if found else None


def export_review(manifest: CacheManifest, k: int, out_dir: Path) -> list[str]:
    """review/<moment_id>.md for the k highest-leverage moments with a model explanation and a Narrator line."""
    rows = []
    for m in _moments(manifest):
        exp = _entry(manifest, m["moment_id"], "tactician", "tactician@3")
        line = _entry(manifest, m["moment_id"], "narrator", "narrator@2")
        if exp and line and isinstance(manifest.read(exp).get("json"), dict) and m.get("leverage") is not None:
            rows.append((m, exp, line))
    rows.sort(key=lambda r: -float(r[0]["leverage"]))
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for m, exp, line in rows[:k]:
        ex_json, line_json = manifest.read(exp)["json"], manifest.read(line)["json"]
        claims = "\n".join(f"| {c.get('text')} | {c.get('kind')} | {c.get('value_number', c.get('value_text'))} | "
                           f"{c.get('unit') or ''} | {', '.join(c.get('evidence_ids', []))} |"
                           for c in ex_json.get("claims", []))
        body = (f"# {m['moment_id']} · {m['clock']} · {m['kind']} · leverage {m['leverage']}\n\n"
                f"Keys: `{exp['key']}` and `{line['key']}`.\n\n"
                "Edit the JSON block only: a sharper `why` and line, the same verified numbers, no new unverified "
                "number. `import_review.py` runs the Fact Checker on both and refuses anything that fails.\n\n"
                "| text | kind | value | unit | evidence |\n|---|---|---|---|---|\n" + claims + "\n\n"
                "```json\n" + json.dumps({"moment_id": m["moment_id"], "explanation": ex_json, "line": line_json},
                                         indent=1) + "\n```\n")
        path = out_dir / f"{m['moment_id']}.md"
        path.write_text(body)
        written.append(str(path))
    return written


def export_fast_lines(manifest: CacheManifest, out_dir: Path) -> list[str]:
    """review/fast_<moment_id>.md for every cached fast line (goals, big chances): the claims it may use come from
    the moment's evidence (newsroom.executors.fast_line.claims_from_moment)."""
    from newsroom.executors.fast_line import claims_from_moment
    from newsroom.messages import Moment

    bb, _ = evidence_board(manifest)
    written = []
    for m in _moments(manifest):
        e = _entry(manifest, m["moment_id"], "fast_line", "narrator@2")
        if not e:
            continue
        claims = claims_from_moment(Moment.model_validate(m), bb)
        body = (f"# fast line {m['moment_id']} · {m['clock']} · {m['kind']}\n\nKey: `{e['key']}`. Claims it may use: "
                + ", ".join(f"`{c['text']}`" for c in claims) + "\n\n```json\n"
                + json.dumps({"moment_id": m["moment_id"], "fast_line": manifest.read(e)["json"]}, indent=1)
                + "\n```\n")
        path = out_dir / f"fast_{m['moment_id']}.md"
        path.write_text(body)
        written.append(str(path))
    bb.close()
    return written


def broken_rewrites(manifest: CacheManifest) -> list[dict]:
    """Cached Narrator rewrites (narrator@2.a2, .a3) that replay as a red trace row: the golden call failed or
    returned no headline/body."""
    out = []
    for e in manifest.find(producer="narrator"):
        if ".a" not in (e.get("version") or ""):
            continue
        doc = manifest.read(e)
        body = doc.get("json")
        if doc.get("error") or not (isinstance(body, dict) and isinstance(body.get("headline"), str)
                                    and isinstance(body.get("body"), str)):
            out.append(e)
    return sorted(out, key=lambda e: e["key"])


def narrator_inputs(manifest: CacheManifest) -> dict[tuple[str, int], dict]:
    """{(moment_id, attempt): {kind, claims}}: what the Narrator received in a replay of the cache (the verified
    claims a line may use; for a Panel moment they are the Panel's, not the Tactician's)."""
    from newsroom.executors import narrator

    seen: dict[tuple[str, int], dict] = {}
    original = narrator.write_line

    async def recording(deps, msg, kind, claims, diff=None, previous=None, attempt=1, producer="narrator"):
        if producer == "narrator":
            seen[(msg.moment.moment_id, attempt)] = {"kind": kind, "claims": [c for c in claims if c.get("verified")]}
        return await original(deps, msg, kind, claims, diff, previous, attempt, producer)

    narrator.write_line = recording
    try:
        replay(manifest)["bb"].close()
    finally:
        narrator.write_line = original
    return seen


def _line_key(manifest: CacheManifest, moment_id: str, attempt: int) -> str:
    version = "narrator@2" if attempt == 1 else f"narrator@2.a{attempt}"
    return CacheManifest.key(manifest.data["match_id"], moment_id, "narrator", version, "gemini-3.8-flash",
                             manifest.data["match_seed"])


def export_lines(manifest: CacheManifest, out_dir: Path, which: list[tuple[str, int]] | None = None) -> list[str]:
    """review/line_<moment_id>_a<n>.md for Narrator lines to rewrite by hand: the given (moment, attempt) pairs
    (lines a reviewer or the judge found wrong), else every broken cached rewrite. Each lists the claims the
    Narrator received for that attempt; the import gates the edit on exactly those."""
    inputs = narrator_inputs(manifest)
    which = which or [(e["moment_id"], int(e["version"].rsplit(".a", 1)[1])) for e in broken_rewrites(manifest)]
    written = []
    for mid, attempt in which:
        stored = manifest.read(manifest.get(_line_key(manifest, mid, attempt)))
        exp = _entry(manifest, mid, "tactician", "tactician@3")
        why = manifest.read(exp)["json"].get("why", "") if exp else ""
        body = (f"# line {mid} attempt {attempt} ({inputs[(mid, attempt)]['kind']})\n\n"
                f"Key: `{_line_key(manifest, mid, attempt)}`. Cached: "
                f"`{(stored.get('error') or stored.get('text') or '')[:200]}`\n\nTactician why: {why}\n\n"
                "Claims it may use: " + ", ".join(f"`{c['text']}`" for c in inputs[(mid, attempt)]["claims"])
                + "\n\n```json\n" + json.dumps({"moment_id": mid, "attempt": attempt,
                                                   "line": {"headline": "", "body": "", "claims": []}}, indent=1)
                + "\n```\n")
        path = out_dir / f"line_{mid}_a{attempt}.md"
        path.write_text(body)
        written.append(str(path))
    return written


# ---------------------------------------------------------------------------------------------------- import

def check_reviewed(bb, match_id: str, explanation: dict, line: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """(verified explanation claims, verified line claims, problems) under the Fact Checker."""
    from newsroom.executors.tactician import to_claim
    from newsroom.factcheck import verify_claims

    claims = [c for c in (to_claim(x) for x in explanation.get("claims", [])) if c]
    ex = verify_claims(match_id, claims, bb, {"why": explanation.get("why", "")})
    good = [c for c in ex["claims"] if c["verified"]]
    used = [c for c in good if c["text"] in line.get("claims", []) or c["text"] in line.get("headline", "")
            or c["text"] in line.get("body", "")]
    ln = verify_claims(match_id, used, bb, {"headline": line.get("headline", ""), "body": line.get("body", "")})
    problems = ex["diff"] + ln["diff"]
    if len(line.get("headline", "")) > 60 or len(line.get("body", "")) > 280:
        problems.append({"reject_reason": "too_long"})
    return good, used, problems


def import_review(manifest: CacheManifest, review_dir: Path) -> dict:
    """Write every passing review back (hand_reviewed: true) and append it to the few-shot files."""
    import hashlib

    bb, _ = evidence_board(manifest)
    match_id = manifest.data["match_id"]
    imported, refused = [], {}
    shots_n, shots_t = [], []
    from newsroom.executors.fast_line import claims_from_moment
    from newsroom.factcheck import verify_claims
    from newsroom.messages import Moment

    moments = {m["moment_id"]: m for m in _moments(manifest)}
    for path in sorted(Path(review_dir).glob("fast_mo_*.md")):
        doc = json.loads(BLOCK.search(path.read_text()).group(1))
        mid, line = doc["moment_id"], doc["fast_line"]
        claims = [c for c in claims_from_moment(Moment.model_validate(moments[mid]), bb)
                  if c["text"] in line.get("headline", "") + " " + line.get("body", "")]
        check = verify_claims(match_id, claims, bb, {"headline": line["headline"], "body": line["body"]})
        if check["diff"] or len(line["headline"]) > 60 or len(line["body"]) > 280:
            refused[path.name] = check["diff"] or "too long"
            continue
        e = _entry(manifest, mid, "fast_line", "narrator@2")
        line = {**line, "claims": [c["text"] for c in claims]}
        payload = {**manifest.read(e), "json": line, "text": json.dumps(line), "verified": True, "hand_reviewed": True}
        raw = (json.dumps(payload, indent=1, sort_keys=True) + "\n").encode()
        (manifest.cache_dir / e["path"]).write_bytes(raw)
        e["sha256"], e["hand_reviewed"] = hashlib.sha256(raw).hexdigest(), True
        imported.append(f"fast:{mid}")
    from newsroom.factcheck import banned_matcher

    for path in sorted(Path(review_dir).glob("chair_mo_*.md")):   # a Panel chair's {consensus, dissent, headline}
        doc = json.loads(BLOCK.search(path.read_text()).group(1))
        chair = doc["chair"]
        hits = [h for v in chair.values() for h in banned_matcher().find(v)]
        if hits or not chair.get("headline") or set(chair) != {"consensus", "dissent", "headline"}:
            refused[path.name] = hits or "needs consensus, dissent and headline"
            continue
        e = manifest.get(CacheManifest.key(match_id, doc["moment_id"], "panel", "chair@1", "gemini-3.8-flash",
                                           manifest.data["match_seed"]))
        payload = {**manifest.read(e), "json": chair, "text": json.dumps(chair, indent=2), "hand_reviewed": True}
        raw = (json.dumps(payload, indent=1, sort_keys=True) + "\n").encode()
        (manifest.cache_dir / e["path"]).write_bytes(raw)
        e["sha256"], e["hand_reviewed"] = hashlib.sha256(raw).hexdigest(), True
        imported.append(f"chair:{doc['moment_id']}")
    lines = sorted(Path(review_dir).glob("line_mo_*.md"))
    inputs = narrator_inputs(manifest) if lines else {}
    for path in lines:
        doc = json.loads(BLOCK.search(path.read_text()).group(1))
        mid, attempt, line = doc["moment_id"], int(doc["attempt"]), doc["line"]
        given = inputs.get((mid, attempt), {}).get("claims", [])
        used = [c for c in given if c["text"] in line["headline"] or c["text"] in line["body"]]
        check = verify_claims(match_id, used, bb, {"headline": line["headline"], "body": line["body"]})
        if check["diff"] or not line["headline"] or len(line["headline"]) > 60 or len(line["body"]) > 280:
            refused[path.name] = check["diff"] or "empty or too long"
            continue
        e = manifest.get(_line_key(manifest, mid, attempt))
        line = {**line, "claims": [c["text"] for c in used]}
        payload = {k: v for k, v in manifest.read(e).items() if k != "error"}
        payload.update(json=line, text=json.dumps(line), verified=True, hand_reviewed=True)
        raw = (json.dumps(payload, indent=1, sort_keys=True) + "\n").encode()
        (manifest.cache_dir / e["path"]).write_bytes(raw)
        e["sha256"], e["hand_reviewed"] = hashlib.sha256(raw).hexdigest(), True
        imported.append(f"line:{mid}:a{attempt}")
    for path in sorted(Path(review_dir).glob("mo_*.md")):
        block = BLOCK.search(path.read_text())
        if not block:
            refused[path.name] = "no JSON block"
            continue
        doc = json.loads(block.group(1))
        mid = doc["moment_id"]
        good, used, problems = check_reviewed(bb, match_id, doc["explanation"], doc["line"])
        if problems:
            refused[path.name] = problems
            continue
        for producer, version, body in (("tactician", "tactician@3", doc["explanation"]),
                                        ("narrator", "narrator@2", doc["line"])):
            e = _entry(manifest, mid, producer, version)
            payload = {**manifest.read(e), "json": body, "text": json.dumps(body), "verified": True,
                       "hand_reviewed": True}
            raw = (json.dumps(payload, indent=1, sort_keys=True) + "\n").encode()
            (manifest.cache_dir / e["path"]).write_bytes(raw)
            e["sha256"], e["hand_reviewed"] = hashlib.sha256(raw).hexdigest(), True
        shots_t.append({"input": {"moment_id": mid}, "output": doc["explanation"]})
        shots_n.append({"input": {"moment_kind": "sliding_doors" if any(
            c.get("evidence_ids", [""])[0].startswith("cf_") for c in good) else "decision",
            "CLAIMS": [{"text": c["text"], "kind": c["kind"], "unit": c.get("unit")} for c in used]},
            "output": doc["line"]})
        imported.append(mid)
    FEWSHOT.mkdir(parents=True, exist_ok=True)
    for name, shots in (("narrator.jsonl", shots_n), ("tactician.jsonl", shots_t)):
        path = FEWSHOT / name
        have = path.read_text() if path.exists() else ""
        new = [json.dumps(s, sort_keys=True) for s in shots if json.dumps(s, sort_keys=True) not in have]
        path.write_text(have + "".join(line + "\n" for line in new))
    bb.close()
    return {"imported": imported, "refused": refused}


# ---------------------------------------------------------------------------------------------------- cue stream

def build_cue_stream(manifest: CacheManifest) -> dict:
    """Cache every cue the replay delivers and every recap held for the producer (kind "cue"), plus the
    explanation documents they cite (kind "explanation"), so screens and checks need no model and no newsroom."""
    out = replay(manifest)
    if out["misses"]:
        raise SystemExit(f"replay has cache misses, run replay_check --repair first: {out['misses'][:3]}")
    match_id, seed = manifest.data["match_id"], manifest.data["match_seed"]
    manifest.data["entries"] = [e for e in manifest.entries if not (
        e["kind"] == "cue" or (e["kind"] == "explanation" and e["path"].startswith("explanations/ex_")))]
    manifest._by_key = {e["key"]: e for e in manifest.entries}
    cited = set()
    for cue in out["cues"] + out["held"]:
        key = CacheManifest.key(match_id, cue.get("moment_id"), "director", f"cue@{cue['kind']}", None, seed) + \
            f"/{cue['cue_id']}"
        manifest.add(key, "cue", cue, f"cues/{cue['cue_id']}.json", moment_id=cue.get("moment_id"),
                     producer="director", version="cue@1", seed=seed, simulated_latency_ms=0)
        if cue["explain"].get("explanation_id"):
            cited.add(cue["explain"]["explanation_id"])
    for ex_id in sorted(cited):
        doc = out["bb"].get("explanations", ex_id, match_id)
        manifest.add(CacheManifest.key(match_id, doc["moment_id"], "tactician", "explanation@doc", doc["model"], seed),
                     "explanation", doc, f"explanations/{ex_id}.json", moment_id=doc["moment_id"],
                     producer="explanation", version="explanation@doc", model=doc["model"], seed=seed)
    out["bb"].close()
    kept = {e["path"] for e in manifest.entries}
    for stale in [*manifest.cache_dir.glob("cues/c_*.json"), *manifest.cache_dir.glob("explanations/ex_*.json")]:
        if str(stale.relative_to(manifest.cache_dir)) not in kept:   # a cue an earlier stream delivered
            stale.unlink()
    return {"cues": len(out["cues"]), "held_recaps": len(out["held"]), "explanations": len(cited),
            "verified": sum(1 for c in out["cues"] if c.get("verified"))}
