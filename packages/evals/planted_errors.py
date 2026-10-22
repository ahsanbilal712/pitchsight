"""Fact Checker planted-error suite (TECH_PLAN 1.11 rows "Fact Checker planted errors caught" / "false rejects", T-055).

    python -m evals.planted_errors --n 500

Source: the golden match's verified Tactician explanations (cache entries producer "tactician" with verified true,
claims rebuilt with the Tactician's own `to_claim`), checked against the evidence the golden precompute's Fact Checker
saw (match events through MatchStore, `evidence.jsonl` through `cache.client.preload_evidence`, as replay does).
Fewer than 500 exist, so explanations are sampled with replacement (fixed RNG seed) and the JSON says so.

Each planted output is a copy of one verified explanation whose claims and `why` both pass (so the injected error is
the only one), with exactly one injected error:
  wrong_number    a number claim's value and its on-screen text scaled by +-10% (claims where 10% stays within the
                  rule's stated tolerance, TOLERANCE, or rounds to the same shown number are not eligible: the error
                  would not be visible);
  wrong_player    a player claim names another player of the match who is not in the cited evidence;
  wrong_minute    a minute claim (or a planted one citing the explanation's event) moved 2-10 minutes;
  unbound_number  a sentence with a number no claim binds is added to `why`;
  banned_word     a banned phrase (injury speculation, referee bias, betting) is added to `why`.
`newsroom.factcheck.verify_claims` runs on it (claims plus the `why` text); the error is caught when the output is not
verified, and the first reject reason gives the rule (catch table per rule). False rejects: the unmodified verified
explanations through the call that gave the golden verdict (claims; `why` is checked separately on screen, and the
Narrator drops a rejected why). Gates: 100% caught, false rejects <= 2%.

Stress set (reported, not gated): `wrong_number_widened`, the claims where +-10% would be invisible, moved to the
smallest visible change beyond the tolerance. Rule 2 accepts a value that matches any same-unit number in the cited
evidence, so a number swapped for another one of the same counterfactual (the alternative's 2% for the shot's 4%)
passes; the misses are listed.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "packages" / "evals" / "out"
ERRORS = ("wrong_number", "wrong_player", "wrong_minute", "unbound_number", "banned_word")
RULE = {"no_evidence": 1, "evidence_not_found": 1,
        "unit_not_supported": 2, "value_not_numeric": 2, "no_number_in_text": 2, "text_value_mismatch": 2,
        "win_prob_delta_needs_counterfactual": 2, "value_out_of_tolerance": 2, "no_evidence_for_unit": 2,
        "unknown_player": 3, "player_not_in_lineup": 3, "player_name_mismatch": 3, "player_not_in_evidence": 3,
        "team_not_in_match": 3, "team_name_mismatch": 3,
        "minute_out_of_range": 4, "no_evidence_time": 4,
        "tactical_needs_pc_or_fact": 5, "tactical_pattern_missing": 5, "tactical_pattern_not_found": 5,
        "unknown_kind": 5,
        "unbound_number": 6, "banned_content": 7}
BANNED = ("the bookies will be paying out on that", "that looks like a hamstring injury",
          "the referee is biased against them", "the odds on that were long", "he was limping badly afterwards",
          "punters will not be happy", "the officials were bent tonight", "a fitness doubt for the weekend")
NUMBER = re.compile(r"\d+(?:\.\d+)?")
CATCH_MIN, FALSE_REJECT_MAX = 1.0, 0.02


# ---------------------------------------------------------------------------------------------------- sources
def load_sources(match_dir: Path):
    """(verified explanations [{match_id, moment_id, why, claims}], blackboard holding the Fact Checker's evidence)."""
    from blackboard import SqliteBlackboard
    from cache.client import preload_evidence
    from cache.manifest import CacheManifest
    from mcp_server.tools_core import MatchStore
    from newsroom.executors.tactician import to_claim

    manifest = CacheManifest.load(match_dir / "cache")
    match_id = manifest.data["match_id"]
    exps = []
    for e in manifest.find(producer="tactician"):
        payload = json.loads((manifest.cache_dir / e["path"]).read_text(encoding="utf-8"))
        body = payload.get("json") if isinstance(payload.get("json"), dict) else {}
        claims = [c for c in (to_claim(x) for x in body.get("claims", []) if isinstance(x, dict)) if c]
        if payload.get("verified") and claims and body.get("why"):
            exps.append({"match_id": match_id, "moment_id": e.get("moment_id"), "key": e["key"],
                         "why": str(body["why"])[:400], "claims": claims[:8]})
    runtime = Path(tempfile.mkdtemp(prefix="planted_"))
    bb = SqliteBlackboard(runtime / "bb.sqlite")
    store = MatchStore(bb, matches_dir=match_dir.parent, runtime_dir=runtime)
    preload_evidence(bb, manifest, store)
    return exps, bb


def check(exp: dict, bb, with_why: bool = True) -> dict:
    from newsroom.factcheck import verify_claims
    res = verify_claims(exp["match_id"], exp["claims"], bb, {"why": exp["why"]} if with_why else None)
    reasons = [d["reject_reason"] for d in res["diff"]]
    return {"verified": res["verified"], "reasons": reasons, "rule": RULE.get(reasons[0]) if reasons else None}


# ---------------------------------------------------------------------------------------------------- injections
def _fmt_like(token: str, x: float) -> str:
    decimals = len(token.split(".")[1]) if "." in token else 0
    return f"{x:.{decimals}f}"


def _step(token: str) -> float:
    return 10.0 ** -(len(token.split(".")[1]) if "." in token else 0)


def wrong_number(exp: dict, rng, bb, widen: bool = False) -> dict | None:
    from newsroom.factcheck import PROBABILITY_UNITS, TOLERANCE, _unit
    idx = [i for i, c in enumerate(exp["claims"]) if c["kind"] == "number" and _unit(c["unit"]) in TOLERANCE
           and _unit(c["unit"]) not in ("minute", "win_prob_delta") and isinstance(c["value"], int | float)
           and len(NUMBER.findall(c["text"])) == 1]
    if not idx:
        return None
    i = int(rng.choice(idx))
    c = exp["claims"][i]
    unit, token = _unit(c["unit"]), NUMBER.findall(c["text"])[0]
    shown = float(token)
    pct = "%" in c["text"] and unit in PROBABILITY_UNITS
    scale = 100.0 if pct else 1.0                      # shown number = value x scale
    sign = 1.0 if rng.random() < 0.5 else -1.0
    if c["value"] == 0:
        sign = 1.0
    target = c["value"] * (1.0 + 0.1 * sign)
    new_shown = float(_fmt_like(token, target * scale))
    widened = False
    floor = TOLERANCE[unit] * scale
    invisible = abs(new_shown - shown) <= floor + 1e-9
    if invisible != widen:                             # plain set: 10% must show; stress set: only where it would not
        return None
    while abs(new_shown - shown) <= floor + 1e-9 or new_shown < 0:
        if new_shown < 0:
            sign = 1.0
        new_shown = round(new_shown + sign * _step(token), 6)
        widened = True
    out = copy.deepcopy(exp)
    out["claims"][i] = {**c, "value": new_shown / scale, "text": c["text"].replace(token, _fmt_like(token, new_shown), 1)}
    old_txt, new_txt = token, _fmt_like(token, new_shown)
    if old_txt in out["why"]:
        out["why"] = out["why"].replace(old_txt, new_txt, 1)
    return {"exp": out, "detail": {"claim": i, "from": c["text"], "to": out["claims"][i]["text"],
                                   "change": round(new_shown / shown - 1.0, 4) if shown else None,
                                   "widened": widened}}


def wrong_player(exp: dict, rng, bb) -> dict | None:
    from newsroom.factcheck import _Evidence, _players_in, league_data
    idx = [i for i, c in enumerate(exp["claims"]) if c["kind"] == "player" and isinstance(c["value"], str)]
    if not idx:
        return None
    i = int(rng.choice(idx))
    c = exp["claims"][i]
    players, _ = league_data()
    meta = next(iter(bb.query("events", match_id=exp["match_id"], type="match_metadata", limit=1)), {})
    squad = sorted({p for side in meta.get("attrs", {}).get("lineups", {}).values() for g in side.values() for p in g})
    ev = _Evidence(bb, exp["match_id"])
    ev.resolve(c["evidence_ids"])
    involved = set()
    for eid in c["evidence_ids"]:
        if eid in ev.docs:
            coll, doc = ev.docs[eid]
            involved |= _players_in(doc, coll)
            ev.resolve(list(doc.get("related_event_ids", [])))
            for r in doc.get("related_event_ids", []):
                if r in ev.docs:
                    involved |= _players_in(ev.docs[r][1], ev.docs[r][0])
    pool = [p for p in squad if p not in involved and p in players]
    if not pool:
        return None
    new = str(rng.choice(pool))
    full = players[new]["name"]
    old_full = players.get(c["value"], {}).get("name", "")
    text = full if c["text"].strip().lower() == old_full.lower() else full.split()[-1]
    out = copy.deepcopy(exp)
    out["claims"][i] = {**c, "value": new, "text": text}
    if c["text"] in out["why"]:
        out["why"] = out["why"].replace(c["text"], text, 1)
    return {"exp": out, "detail": {"claim": i, "from": c["value"], "to": new}}


def wrong_minute(exp: dict, rng, bb) -> dict | None:
    shift = int(rng.integers(2, 11)) * (1 if rng.random() < 0.5 else -1)
    out = copy.deepcopy(exp)
    idx = [i for i, c in enumerate(exp["claims"]) if (c["kind"] == "minute" or c["unit"] == "minute")
           and isinstance(c["value"], int | float)]
    if idx:
        i = int(rng.choice(idx))
        c = exp["claims"][i]
        new = max(1, int(round(c["value"])) + shift)
        if abs(new - c["value"]) <= 1:
            new = int(round(c["value"])) + abs(shift)
        tok = NUMBER.findall(c["text"])
        text = c["text"].replace(tok[0], str(new), 1) if tok else f"{new}'"
        out["claims"][i] = {**c, "value": new, "text": text}
        return {"exp": out, "detail": {"claim": i, "from": c["value"], "to": new, "planted_claim": False}}
    events = [e for c in exp["claims"] for e in c["evidence_ids"] if e.startswith("e_")]
    if not events or len(exp["claims"]) >= 8:         # a planted claim needs a free slot (schema: at most 8)
        return None
    try:
        t = bb.get("events", events[0], exp["match_id"])["t_ms"]
    except Exception:
        return None
    true_min = int(t // 60000)
    new = max(1, true_min + shift)
    if abs(new - t / 60000.0) <= 1:
        new = true_min + abs(shift)
    claim = {"text": f"{new}'", "kind": "minute", "value": new, "unit": "minute", "evidence_ids": [events[0]],
             "verified": False, "reject_reason": None}
    out["claims"] = out["claims"] + [claim]
    out["why"] = (out["why"] + f" It came in the {new}'.")[:400]
    return {"exp": out, "detail": {"claim": len(out["claims"]) - 1, "evidence": events[0], "true_minute": true_min,
                                   "to": new, "planted_claim": True}}


def unbound_number(exp: dict, rng, bb) -> dict | None:
    from newsroom.factcheck import _token_keys
    bound = set()
    for c in exp["claims"]:
        bound |= _token_keys(c["text"])
    n = int(rng.integers(3, 99))
    while str(n) in bound or f"{n}%" in bound:
        n += 1
    sentence = rng.choice([f" He had {n} metres of space.", f" They had won {n}% of duels.",
                           f" It was their {n}th attempt."])
    out = copy.deepcopy(exp)
    out["why"] = (out["why"][: 400 - len(sentence)] + sentence)
    return {"exp": out, "detail": {"added": sentence.strip()}}


def banned_word(exp: dict, rng, bb) -> dict | None:
    phrase = str(rng.choice(BANNED))
    sentence = f" Honestly, {phrase}."
    out = copy.deepcopy(exp)
    out["why"] = out["why"][: 400 - len(sentence)] + sentence
    return {"exp": out, "detail": {"added": phrase}}


def wrong_number_widened(exp: dict, rng, bb) -> dict | None:
    return wrong_number(exp, rng, bb, widen=True)


INJECT = {"wrong_number": wrong_number, "wrong_player": wrong_player, "wrong_minute": wrong_minute,
          "unbound_number": unbound_number, "banned_word": banned_word, "wrong_number_widened": wrong_number_widened}
STRESS = ("wrong_number_widened",)


# ---------------------------------------------------------------------------------------------------- suite
def _eligible(kind: str, exps: list[dict], bb) -> list[dict]:
    """Sources where the injection applies for some draw (wrong_number depends on the drawn sign: try both)."""
    out = []
    for e in exps:
        if any(INJECT[kind](e, np.random.default_rng(s), bb) is not None for s in range(8)):
            out.append(e)
    return out


def run(exps: list[dict], bb, n: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    per_type = {k: n // len(ERRORS) + (1 if i < n % len(ERRORS) else 0) for i, k in enumerate(ERRORS)}
    per_type.update({k: n // len(ERRORS) for k in STRESS})
    clean_why = [check(e, bb)["verified"] for e in exps]
    bases = [e for e, ok in zip(exps, clean_why, strict=True) if ok]
    planted, by_type, by_rule, stress = [], {}, {}, {}
    for kind, count in per_type.items():
        eligible = _eligible(kind, bases, bb)
        rows = []
        tries = 0
        while len(rows) < count and eligible and tries < 50 * count:
            tries += 1
            src = eligible[int(rng.integers(len(eligible)))]
            got = INJECT[kind](src, rng, bb)
            if got is None:
                continue
            res = check(got["exp"], bb)
            rows.append({"error": kind, "moment_id": src["moment_id"], **got["detail"], "caught": not res["verified"],
                         "reasons": res["reasons"], "rule": res["rule"]})
        caught = sum(r["caught"] for r in rows)
        if kind in STRESS:
            stress[kind] = {"n": len(rows), "caught": caught, "catch_rate": round(caught / max(len(rows), 1), 4),
                            "sources": len(eligible), "missed": [r for r in rows if not r["caught"]][:20]}
            continue
        rules: dict[str, int] = {}
        for r in rows:
            if r["caught"]:
                rules[f"rule {r['rule']}"] = rules.get(f"rule {r['rule']}", 0) + 1
                by_rule.setdefault(f"rule {r['rule']}", {}).setdefault(kind, 0)
                by_rule[f"rule {r['rule']}"][kind] += 1
        by_type[kind] = {"n": len(rows), "caught": caught, "catch_rate": round(caught / max(len(rows), 1), 4),
                         "sources": len(eligible), "caught_by": rules}
        planted += rows
    picks = rng.integers(len(exps), size=n) if exps else []
    clean = [check(e, bb, with_why=False) for e in exps]
    sampled_rejects = sum(not clean[int(i)]["verified"] for i in picks)
    total = len(planted)
    caught_all = sum(r["caught"] for r in planted)
    return {
        "n_planted": total, "caught": caught_all, "catch_rate": round(caught_all / max(total, 1), 4),
        "by_error": by_type, "catch_table_by_rule": by_rule,
        "false_rejects": {"n": int(len(picks)), "rejected": int(sampled_rejects),
                          "rate": round(sampled_rejects / max(len(picks), 1), 4),
                          "unique_outputs": len(exps), "unique_rejected": sum(not c["verified"] for c in clean),
                          "reasons": sorted({r for c in clean for r in c["reasons"]}),
                          "check": "claims (the golden verdict's call)"},
        "why_text": {"explanations": len(exps), "why_passes": sum(clean_why),
                     "note": "a why with a number no claim binds is rejected by rule 6 and dropped by the Narrator; "
                             "planted errors use only explanations whose why passes"},
        "stress": stress,
        "source": {"verified_explanations": len(exps), "sampled_with_replacement": len(exps) < n, "seed": seed,
                   "note": (f"only {len(exps)} verified golden explanations exist; the {n} planted and {n} clean "
                            "outputs are sampled from them with replacement") if len(exps) < n else None},
        "thresholds": {"catch_rate_min": CATCH_MIN, "false_reject_max": FALSE_REJECT_MAX},
        "examples": [r for k in ERRORS for r in [next((x for x in planted if x["error"] == k), None)] if r],
        "missed": [r for r in planted if not r["caught"]][:20],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m evals.planted_errors")
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--match-dir", type=Path, default=ROOT / "data" / "matches" / "4242")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    exps, bb = load_sources(args.match_dir)
    if not exps:
        raise SystemExit("no verified Tactician explanations in the cache (run the golden model precompute, T-042)")
    res = run(exps, bb, args.n, args.seed)
    res["passed"] = res["catch_rate"] >= CATCH_MIN and res["false_rejects"]["rate"] <= FALSE_REJECT_MAX \
        and all(v["n"] > 0 for v in res["by_error"].values())
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "planted_errors.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"catch_rate": res["catch_rate"], "n": res["n_planted"],
                      "by_error": {k: v["catch_rate"] for k, v in res["by_error"].items()},
                      "false_reject_rate": res["false_rejects"]["rate"], "passed": res["passed"]}))
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
