"""Hand review of the featured real-clip moments.

    python -m footage.review export      # review/footage/<slug>_<moment_id>.md
    python -m footage.review import      # Fact Checker gate, then cache entries with hand_reviewed: true

A review file holds the model's explanation and its verified claims, plus an empty on-screen line (headline,
body). Edit the why and write the line in this session, citing only the listed claims; the import verifies the why,
headline and body against the clip's evidence (the cache's evidence.jsonl, the same documents the precompute
checked) and refuses any file with a Fact Checker diff. Accepted reviews become an explanation.schema.json document
(producer "explanation") and a line (producer "narrator", version footage_line@1) in the clip's cache.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from footage.clips import CLIPS, ROOT, load_config
from footage.featured import PROMPT, open_cache

REVIEW_DIR = ROOT / "review" / "footage"
BLOCK = re.compile(r"```json\n(.*?)\n```", re.S)
HEADLINE_MAX, BODY_MAX = 60, 280


def evidence_board(manifest):
    from blackboard import SqliteBlackboard

    bb = SqliteBlackboard(":memory:")
    entry = manifest.find(producer="evidence")[0]
    for line in (manifest.cache_dir / entry["path"]).read_text().splitlines():
        if line.strip():
            doc = json.loads(line)
            bb.put(doc.pop("_collection"), doc)
    return bb


def export(out_dir: Path = REVIEW_DIR) -> list[str]:
    from footage.featured import check

    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for f in load_config()["featured"]:
        manifest = open_cache(f["slug"])
        found = manifest.find(moment_id=f["moment_id"], producer="tactician", version=PROMPT)
        if not found:
            continue
        bb = evidence_board(manifest)
        exp, result = check(manifest.data["match_id"], manifest.read(found[0])["json"] or {}, bb)
        bb.close()
        claims = [{k: c[k] for k in ("text", "kind", "value", "unit", "evidence_ids")} for c in exp["claims"]
                  if c["verified"]]
        doc = {"slug": f["slug"], "moment_id": f["moment_id"], "why": exp["why"], "claims": claims,
               "line": {"headline": "", "body": ""}}
        body = (f"# {CLIPS[f['slug']]['home']} v {CLIPS[f['slug']]['away']} · {f['moment_id']}\n\n"
                f"Model why: {exp['why']}\n\nFact Checker on the model output: "
                f"{'verified' if result['verified'] else json.dumps(result['diff'])}\n\n"
                f"```json\n{json.dumps(doc, indent=1, ensure_ascii=False)}\n```\n")
        path = out_dir / f"{f['slug']}_{f['moment_id']}.md"
        path.write_text(body)
        written.append(str(path))
    return written


def import_(review_dir: Path = REVIEW_DIR) -> dict:
    from cache.manifest import CacheManifest
    from newsroom.executors.tactician import explanation_id_for
    from newsroom.factcheck import verify_claims

    imported, refused = [], {}
    for path in sorted(review_dir.glob("*_mo_*.md")):
        doc = json.loads(BLOCK.search(path.read_text()).group(1))
        slug, mid, line = doc["slug"], doc["moment_id"], doc["line"]
        manifest = open_cache(slug)
        match_id, seed = manifest.data["match_id"], manifest.data["match_seed"]
        bb = evidence_board(manifest)
        claims = [{**c, "verified": False, "reject_reason": None} for c in doc["claims"]]
        result = verify_claims(match_id, claims, bb, {"why": doc["why"], "headline": line["headline"],
                                                      "body": line["body"]})
        bb.close()
        problems = list(result["diff"])
        if not line["headline"] or len(line["headline"]) > HEADLINE_MAX or len(line["body"]) > BODY_MAX:
            problems.append({"reject_reason": "line_empty_or_too_long"})
        if problems:
            refused[path.name] = problems
            continue
        model_entry = manifest.find(moment_id=mid, producer="tactician", version=PROMPT)[0]
        cf = manifest.find(moment_id=mid, producer="rollout")[0]
        cf_doc = manifest.read(cf)
        alt = cf_doc["alternative"]
        explanation = {"schema_version": "1.0.0", "explanation_id": explanation_id_for(mid), "match_id": match_id,
                       "moment_id": mid, "why": doc["why"], "claims": result["claims"],
                       "counterfactual_id": cf_doc["counterfactual_id"],
                       "alternatives_considered": [f"{alt['kind']} {alt.get('target') or ''}".strip()],
                       "confidence": float(manifest.read(model_entry)["json"].get("confidence", 0.5)),
                       "model": model_entry["model"], "prompt_version": PROMPT, "tool_trace_id": None, "attempt": 1}
        manifest.add(CacheManifest.key(match_id, mid, "explanation", "explanation@reviewed", model_entry["model"],
                                       seed), "explanation", explanation,
                     f"explanations/{explanation['explanation_id']}.json", moment_id=mid, producer="explanation",
                     version="explanation@reviewed", model=model_entry["model"], seed=seed, hand_reviewed=True)
        used = [c["text"] for c in result["claims"] if c["text"] in line["headline"] + " " + line["body"]]
        manifest.add(CacheManifest.key(match_id, mid, "narrator", "footage_line@1", None, seed), "fast_line",
                     {"$schema": "model_cache.schema.json", "schema_version": "1.0.0", "record": "model_result",
                      "json": {**line, "claims": used}, "text": json.dumps({**line, "claims": used}),
                      "verified": True, "hand_reviewed": True},
                     f"lines/{mid}.json", moment_id=mid, producer="narrator", version="footage_line@1", seed=seed,
                     hand_reviewed=True)
        manifest.save()
        imported.append(f"{slug}:{mid}")
    return {"imported": imported, "refused": refused}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=("export", "import"))
    args = ap.parse_args(argv)
    if args.action == "export":
        print("\n".join(export()))
        return 0
    out = import_()
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 1 if out["refused"] else 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "packages"))
    raise SystemExit(main())
