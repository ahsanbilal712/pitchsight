"""CI judge: plausibility of explained cues. Reported only.

    python -m evals.judge [--n 30] [--seed 4242]

Takes `--n` random explained cues of the golden match (a replay of the committed cache, `groundedness.replay_cues`),
asks the `judge` role (config/models.yaml, through SpendGuard; never on the live path) with prompts/judge@1.md for
{plausible, reason}, and writes packages/evals/out/judge.json with the plausibility rate. No threshold. Judge spend
over all runs (the ledger's judge rows) is capped at MAX_USD: a run stops before a call that could exceed it (worst
case per call from the role's max_tokens); a timed-out call is recorded unjudged. Ledger rows carry no match id, so
the golden match's per-match cap is untouched.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "packages" / "evals" / "out"
PROMPT = "judge@1"
MAX_USD = 0.50
EXPLAINED = ("sliding_doors", "big_chance", "goal")
SCHEMA = {"type": "object", "required": ["plausible", "reason"],
          "properties": {"plausible": {"type": "boolean"}, "reason": {"type": "string"}}}


def judge_input(cue: dict, cf: dict | None) -> str:
    claims = [{k: c.get(k) for k in ("text", "kind", "value", "unit")} for c in cue["explain"].get("claims") or []
              if c.get("verified")]
    doc = {"CUE": {"headline": cue["text"]["headline"], "body": cue["text"]["body"], "why": cue["explain"].get("why"),
                   "claims": claims}}
    if cf:
        keep = ("p_goal_home", "p_goal_away", "win_prob_home")
        doc["COUNTERFACTUAL"] = {"actual": cf.get("actual"), "alternative": cf.get("alternative"),
                                 "after_actual": {k: (cf.get("baseline") or {}).get(k) for k in keep},
                                 "after_alternative": {k: (cf.get("alternative_outcome") or {}).get(k) for k in keep}}
    return json.dumps(doc, separators=(",", ":"), default=str)


def worst_case_usd(role_name: str = "judge") -> float:
    import yaml

    from newsroom import config

    r = config.role(role_name)
    prices = yaml.safe_load((ROOT / "config" / "budgets.yaml").read_text())["spend"]["prices_usd_per_1m"][r.model]
    return (4000 * prices["in"] + int(r.max_tokens or 800) * prices["out"]) / 1e6


def ledger_judge_usd() -> float:
    path = ROOT / "data" / "spend" / "ledger.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
    return sum(float(r.get("cost_usd") or 0.0) for r in rows if str(r.get("role", "")).startswith("judge"))


def run(n: int, seed: int) -> dict:
    from cache.manifest import CacheManifest
    from evals.groundedness import GOLDEN, replay_cues
    from newsroom.llm import LiveClient, LLMError

    cues, _ = replay_cues(GOLDEN)
    pool = [c for c in cues if c["kind"] in EXPLAINED and c.get("verified") and c["explain"].get("why")]
    rng = np.random.default_rng(seed)
    picks = [pool[int(i)] for i in rng.choice(len(pool), size=min(n, len(pool)), replace=False)]
    manifest = CacheManifest.load(GOLDEN / "cache")
    cfs = {}
    for e in manifest.entries:
        if e["kind"] == "counterfactual":
            doc = json.loads((manifest.cache_dir / e["path"]).read_text())
            cfs[doc.get("counterfactual_id")] = doc
    system = (ROOT / "packages" / "newsroom" / "prompts" / f"{PROMPT}.md").read_text(encoding="utf-8")
    client = LiveClient(mode="eval")
    prior = ledger_judge_usd()
    per_call, spent, rows = worst_case_usd(), prior, []
    for cue in picks:
        if spent + per_call > MAX_USD:
            break
        cf = cfs.get(cue["explain"].get("counterfactual_id"))
        try:
            res = asyncio.run(client.complete("judge", [{"role": "system", "content": system},
                                                        {"role": "user", "content": judge_input(cue, cf)}],
                                              schema=SCHEMA, match_id=None, prompt_version=PROMPT))
        except LLMError as exc:                    # a timeout is billed at its worst case in the ledger
            spent += per_call
            rows.append({"cue_id": cue["cue_id"], "kind": cue["kind"], "plausible": None, "reason": None,
                         "error": type(exc).__name__})
            continue
        spent += float(res.get("cost_usd") or 0.0)
        body = res.get("json") if isinstance(res.get("json"), dict) else {}
        rows.append({"cue_id": cue["cue_id"], "kind": cue["kind"], "plausible": body.get("plausible"),
                     "reason": body.get("reason"), "model": res.get("model")})
    judged = [r for r in rows if isinstance(r["plausible"], bool)]
    return {"n": len(rows), "judged": len(judged), "pool": len(pool), "errors": sum(1 for r in rows if r.get("error")),
            "plausibility_rate": round(sum(r["plausible"] for r in judged) / len(judged), 4) if judged else None,
            "cost_usd": round(spent - prior, 4), "judge_total_usd": round(spent, 4), "max_usd": MAX_USD, "prompt": PROMPT, "seed": seed, "rows": rows,
            "threshold": None, "note": "reported only"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m evals.judge")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    res = run(args.n, args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "judge.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("n", "judged", "plausibility_rate", "cost_usd")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
