"""Video v4 lines: the lower-third and the explanation for each goal-in-10s decision (track A's
cache/v4/goal10_decision_<clip_ms>.json), written by gemini-4-argon from the decision's own numbers, then checked
three ways and hand-reviewed.

    python -m footage.v4_lines run <slug> <clip_ms> [--dry-run]   # one live call per moment (SpendGuard, clip id)
    python -m footage.v4_lines import                             # review/footage/v4_*.md -> cache/v4/lines_<ms>.json

The verdict is decided here, not by the model: an alternative is "better" only when its 95% interval is clear of
the actual choice's (no overlap); overlapping intervals are a "close call"; if every alternative is clear below,
the choice was the best the engine found. Every number the line may use is a fact (f_6nnnnn) carrying its one
`display` string, so the overlay, the caption and the lower-third print the same text.

Gates (run on the model draft and again on the reviewed text): the Fact Checker (newsroom.factcheck, rules 1-8);
every number claim's text equals its fact's display; every player name is verified (footage.names); the wording
follows the verdict; length.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from footage.clips import CLIPS, ROOT, clip_dir

PROMPT, ROLE = "insight_footage@5", "tactician_golden"     # @3: no real outcome; @4: no finishing verdict
REVIEW_DIR = ROOT / "review" / "footage"
BLOCK = re.compile(r"```json\n(.*?)\n```", re.S)
LOWER_MAX, WHY_MAX = 60, 160
SCHEMA = {"type": "object", "required": ["lower_third", "why", "claims", "confidence"], "properties": {
    "lower_third": {"type": "string"}, "why": {"type": "string"}, "confidence": {"type": "number"},
    "claims": {"type": "array", "items": {"type": "object", "required": ["text", "kind", "unit", "evidence_ids"],
                                          "properties": {
        "text": {"type": "string"}, "kind": {"type": "string", "enum": ["number", "player", "team", "minute"]},
        "value_number": {"type": "number"}, "value_text": {"type": "string"}, "unit": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}}}}}}}
CLOSE, BETTER, BEST, FINISH, SHOT_ONLY = "close_call", "alternative_better", "actual_best", "finishing", "shot_only"


# ---------------------------------------------------------------------------------------------------- numbers

def pct(p: float) -> str:
    """The one display form of a goal chance, as the v4 overlay prints it (demo.composite.fmt_pct): one decimal
    under 10% ("4.2%", "0.9%"), whole percent from 10% ("17%"); halves round up."""
    v = Decimal(str(p)) * 100
    step = Decimal("0.1") if v < 10 else Decimal("1")
    return f"{v.quantize(step, rounding=ROUND_HALF_UP)}%"


def decision(slug: str, clip_ms: int) -> dict:
    return json.loads((clip_dir(slug) / "cache" / "v4" / f"goal10_decision_{clip_ms}.json").read_text())["result"]


def moment(slug: str, clip_ms: int) -> dict:
    return json.loads((clip_dir(slug) / "moments" / f"{clip_ms}.json").read_text())


def verdict(actual: dict, alt: dict) -> str:
    (alo, ahi), (blo, bhi) = actual["ci95"], alt["ci95"]
    if blo > ahi:
        return BETTER
    if bhi < alo:
        return "alternative_worse"
    return CLOSE


def story(d: dict) -> dict:
    """The actual choice, the alternative the line talks about, and the verdict between them."""
    opts = [o for o in d["options"] if "p_goal_10s" in o]
    actual = next(o for o in opts if "diff_vs_actual" not in o)
    alts = [o for o in opts if o is not actual]
    for o in alts:
        o["verdict_ci"] = verdict(actual, o)
    better = [o for o in alts if o["verdict_ci"] == BETTER]
    close = [o for o in alts if o["verdict_ci"] == CLOSE]
    if better:
        return {"verdict": BETTER, "actual": actual, "alternative": max(better, key=lambda o: o["p_goal_10s"])}
    if close:
        return {"verdict": CLOSE, "actual": actual, "alternative": max(close, key=lambda o: o["p_goal_10s"])}
    return {"verdict": BEST, "actual": actual, "alternative": max(alts, key=lambda o: o["p_goal_10s"])}


# ---------------------------------------------------------------------------------------------------- people

def describe(m: dict, p: dict) -> str:
    """Where a player stands, from his team's point of view (attacking direction from the moment file)."""
    home_plus = m["home_attacks"] == "+x"
    plus = home_plus == (p["team"] == "home")
    depth = 105 - p["x"] if plus else p["x"]
    lateral = (p["y"] - 34) if plus else (34 - p["y"])         # facing +x, the attacker's left is +y
    side = "central" if abs(lateral) < 6 else ("on the left" if lateral > 0 else "on the right")
    if depth <= 5.5 and abs(lateral) <= 9.16:
        zone = "in the six-yard box"
    elif depth <= 16.5 and abs(lateral) <= 20.16:
        zone = "in the box"
    elif depth <= 22 and abs(lateral) <= 20.16:
        zone = "at the edge of the box"
    elif abs(lateral) > 20.16 and depth <= 30:
        zone = "out wide"
    else:
        zone = "further out"
    if zone == "out wide":
        return f"the team-mate out wide {side.removeprefix('on ')}"
    return f"the team-mate {zone}, {side}"


def person(slug: str, m: dict, label: str | None) -> dict | None:
    from footage.featured import roster
    from footage.names import _same, verified

    if label is None:
        return None
    p = next((q for q in m["players"] if q.get("label") == label), None)
    if p is None:
        return {"label": label, "name": None, "pid": None, "describe": "a team-mate"}
    ok = verified(slug)
    name = p.get("name") if p.get("name") and any(_same(p["name"], k) for k in ok) else None
    pid = roster(slug)["ids"].get(f"{p['team']}:{label}")
    return {"label": label, "name": name, "pid": pid if name else None, "describe": describe(m, p),
            "x": p["x"], "y": p["y"]}


def outcome(slug: str, clip_ms: int) -> str | None:
    """What really happened after the choice: the featured moment's reviewed outcome, or a goal the score bug
    confirms (footage.names) within 5 s."""
    from footage.clips import load_config
    from footage.names import verified

    for f in load_config()["featured"]:
        if f["slug"] == slug and f["clip_ms"] == clip_ms:
            return f.get("real_outcome")
    for name, e in verified(slug).items():
        if any(src["kind"] == "score_bug" for src in e["sources"]) and \
                any(lk.get("event") and -2000 <= lk["clip_ms"] - clip_ms <= 5000 for lk in e["links"]):
            return f"{name.split()[-1]} scores"
    return None


def option_text(o: dict, who: dict | None) -> str:
    k = o["option"]["kind"]
    if k == "shoot":
        return "shoot"
    if k == "carry":
        return "carry the ball on"
    return f"pass to {who['name'] if who and who['name'] else (who or {}).get('describe', 'a team-mate')}"


def overlay_label(o: dict, who: dict | None) -> str:
    """The short label on the graphic: a verified name or none, never an internal label ("L3", "#19", "A7")."""
    k = o["option"]["kind"]
    if k == "pass":
        return f"Pass to {who['name'].split()[-1]}" if who and who.get("name") else "Pass"
    return {"shoot": "Shot", "carry": "Carry on"}.get(k, k.capitalize())


# ---------------------------------------------------------------------------------------------------- facts

ROLES = ("actual", "alternative", "horizon", "n", "actual_ci_low", "actual_ci_high", "alternative_ci_low",
         "alternative_ci_high", "seed")


def _fact(n: int, mid: str, label: str, value: float, unit: str, display: str, source: str, **extra) -> dict:
    return {"fact_id": f"f_6{n:05d}", "match_id": mid, "label": label, "value": value, "unit": unit,
            "display": display, "source": source, **extra}


def facts_for(slug: str, clip_ms: int) -> tuple[list[dict], dict]:
    d, m = decision(slug, clip_ms), moment(slug, clip_ms)
    s = story(d)
    real = outcome(slug, clip_ms)
    if real and real.endswith(" scores"):     # a goal went in: the line is about the finish, never another option
        s = {**s, "verdict": FINISH}
    mid, src = d["match_id"], f"cache/v4/goal10_decision_{clip_ms}.json"
    holder = person(slug, m, d["holder"])
    target = person(slug, m, s["alternative"]["option"].get("target"))
    who = [x["pid"] for x in (holder, target) if x and x.get("pid")]
    a, b = s["actual"], s["alternative"]
    k = 10 * (clip_ms // 100 % 1000)                         # f_6 ids unique per moment within a clip
    facts = [_fact(k + 1, mid, f"goal chance in the next 10 s, actual choice ({option_text(a, None)})",
                   a["p_goal_10s"], "p_goal", pct(a["p_goal_10s"]), src, players=who, ci95=a["ci95"]),
             _fact(k + 2, mid, f"goal chance in the next 10 s, alternative ({option_text(b, target)})",
                   b["p_goal_10s"], "p_goal", pct(b["p_goal_10s"]), src, players=who, ci95=b["ci95"]),
             _fact(k + 3, mid, "seconds after the choice that count", d["horizon_s"], "seconds",
                   f"{d['horizon_s']:g}", src),
             _fact(k + 4, mid, "replays of the frozen frame per option", d["n"], "count", f"{d['n']:,}", src),
             _fact(k + 5, mid, "95% interval low, actual choice", a["ci95"][0], "p_goal", pct(a["ci95"][0]), src),
             _fact(k + 6, mid, "95% interval high, actual choice", a["ci95"][1], "p_goal", pct(a["ci95"][1]), src),
             _fact(k + 7, mid, "95% interval low, alternative", b["ci95"][0], "p_goal", pct(b["ci95"][0]), src),
             _fact(k + 8, mid, "95% interval high, alternative", b["ci95"][1], "p_goal", pct(b["ci95"][1]), src),
             _fact(k + 9, mid, "random seed of the replays", d["seed"], "count", str(d["seed"]), src)]   # small print
    for f, role in zip(facts, ROLES, strict=True):
        f["role"] = role
    if s["verdict"] == FINISH:
        facts = [f for f in facts if "alternative" not in f["role"]]
    view = {"clip_ms": clip_ms, "clock": d["clock"], "team": CLIPS[slug][d["team"] + "_short"],
            "verdict": s["verdict"], "real_outcome": real,
            "holder": {k2: holder.get(k2) for k2 in ("name", "pid", "describe")} if holder else None,
            "actual": {"choice": option_text(a, None), "p_goal_10s": a["p_goal_10s"], "ci95": a["ci95"],
                       "fact": facts[0]["fact_id"]},
            "alternative": None if s["verdict"] == FINISH else
            {"choice": option_text(b, target), "p_goal_10s": b["p_goal_10s"], "ci95": b["ci95"],
             "fact": facts[1]["fact_id"],
             "target": {k2: target.get(k2) for k2 in ("name", "pid", "describe")} if target else None},
            "overlay_labels": {"actual": "From here", "alternative": None} if s["verdict"] == FINISH else
            {"actual": overlay_label(a, None), "alternative": overlay_label(b, target)},
            "n": d["n"], "horizon_s": d["horizon_s"], "engine": d["engine"], "seed": d["seed"]}
    return facts, view


# ---------------------------------------------------------------------------------------------------- gates

def gates(slug: str, body: dict, facts: list[dict], view: dict) -> list[str]:
    """Everything but the Fact Checker: displays, names, the verdict's wording, length."""
    from footage.names import unverified_in

    problems = []
    by_id = {f["fact_id"]: f for f in facts}
    for c in body.get("claims", []):
        if c.get("kind") != "number":
            continue
        shown = [by_id[e]["display"] for e in c.get("evidence_ids", []) if e in by_id]
        nums = re.findall(r"\d+(?:\.\d+)?%?", c.get("text", ""))
        if not shown or not nums or not all(any(n == re.findall(r"\d+(?:\.\d+)?%?", s)[0] for s in shown)
                                            for n in nums):
            problems.append(f"claim {c.get('text')!r} does not print its fact's display {shown}")
    text = f"{body.get('lower_third', '')} {body.get('why', '')}"
    if bad := unverified_in(slug, text):
        problems.append(f"unverified names: {bad}")
    v = view["verdict"]
    if v == CLOSE and ("close call" not in text.lower() or re.search(r"\bbetter\b", text, re.I)):
        problems.append("close call: the line must say so and must not call an option better")
    if v == BETTER and (re.search(r"\b(should have|mistake|wrong)\b", text, re.I) or "close call" in text.lower()):
        problems.append("alternative better: no blame, and not a close call")
    if v == BEST and re.search(r"\b(should have|mistake|wrong|close call)\b", text, re.I):
        problems.append("actual best: the line must not suggest another option")
    if v == FINISH and (not re.search(r"\bscor", text, re.I)
                        or re.search(r"\b(better|close call|instead|carry|carrying|pass|passing)\b", text, re.I)):
        problems.append("finishing: say he scored, and mention no other option")
    if v == SHOT_ONLY and re.search(r"\b(better|close call|instead|carry|carrying|pass|passing)\b", text, re.I):
        problems.append("shot only: no other option was measured, mention none")
    if len(body.get("lower_third", "")) > LOWER_MAX or not body.get("lower_third"):
        problems.append(f"lower_third empty or over {LOWER_MAX} characters")
    if len(body.get("why", "")) > WHY_MAX or not body.get("why"):
        problems.append(f"why empty or over {WHY_MAX} characters")
    return problems


def evidence(slug: str, facts: list[dict]):
    from footage.insights import evidence_board

    return evidence_board(slug, facts)


def fact_check(slug: str, body: dict, facts: list[dict], reviewed: bool = False) -> dict:
    from newsroom.executors.tactician import to_claim
    from newsroom.factcheck import verify_claims

    claims = [{**c, "verified": False, "reject_reason": None} for c in body.get("claims", [])] if reviewed else \
        [c for c in (to_claim(x) for x in body.get("claims", []) if isinstance(x, dict)) if c]
    bb = evidence(slug, facts)
    res = verify_claims(CLIPS[slug]["match_id"], claims, bb,
                        {"lower_third": body.get("lower_third", ""), "why": body.get("why", "")})
    bb.close()
    return res


# ---------------------------------------------------------------------------------------------------- run, import

def messages(slug: str, facts: list[dict], view: dict, prompt: str = PROMPT) -> list[dict]:
    from footage.featured import footage_block, roster
    from newsroom import config

    _, system = config.prompt(prompt)
    ros = roster(slug)
    named = {x["pid"] for x in (view["holder"], (view["alternative"] or {}).get("target")) if x and x.get("pid")}
    ros = {**ros, "ids": {k: v for k, v in ros["ids"].items() if v in named},
           "names": {k: v for k, v in ros["names"].items() if k in named}}
    return [{"role": "system", "content": footage_block(slug, ros) + "\n\n" + system},
            {"role": "user", "content": json.dumps({"DECISION": view, "FACTS": facts}, separators=(",", ":"),
                                                   ensure_ascii=False)}]


@dataclass(frozen=True)
class Version:
    """What differs between the video versions' lines: tag (paths), prompt, the facts and view builder, the
    decision file a line is computed from, and the cache version of its model call."""

    tag: str
    prompt: str
    facts_for: Callable[[str, int], tuple[list[dict], dict]]
    source: Callable[[int], str]
    key: Callable[[str, int], str]


def _v4_key(slug: str, clip_ms: int) -> str:
    src = decision(slug, clip_ms)
    return f"{PROMPT}.goal10_{clip_ms}.n{src['n']}s{src['seed']}"


V4 = Version("v4", PROMPT, facts_for, lambda ms: f"cache/v4/goal10_decision_{ms}.json", _v4_key)


def run(slug: str, clip_ms: int, dry_run: bool = False, v: Version = V4) -> dict:
    facts, view = v.facts_for(slug, clip_ms)
    msgs = messages(slug, facts, view, v.prompt)
    if dry_run:
        return {"facts": facts, "view": view, "messages": msgs}
    from cache.manifest import CacheManifest
    from footage.featured import open_cache
    from newsroom import config
    from newsroom.llm import LiveClient

    match_id = CLIPS[slug]["match_id"]
    digest = hashlib.sha256(msgs[1]["content"].encode()).hexdigest()[:8]     # one record per payload, never overwritten
    version = f"{v.key(slug, clip_ms)}.{digest}"
    manifest = open_cache(slug)
    cached = [e for e in manifest.find(producer="insight", version=version)
              if json.loads((manifest.cache_dir / e["path"]).read_text()).get("payload") == msgs[1]["content"]]
    if cached:                                 # same prompt, same numbers: never pay twice
        res = manifest.read(cached[0])
    else:
        llm = LiveClient(mode="precompute")
        out = asyncio.run(llm.complete(ROLE, msgs, None, match_id=match_id, moment_id=None, schema=SCHEMA,
                                       prompt_version=v.prompt, producer="insight",
                                       timeout_s=config.role(ROLE).timeout_s, hedge_after_s=None))
        res = {"$schema": "model_cache.schema.json", "schema_version": "1.0.0", "record": "model_result",
               "via": "live", "payload": msgs[1]["content"],
               **{k: out.get(k) for k in ("json", "text", "model", "tokens_in", "tokens_out", "cost_usd",
                                          "latency_ms")}}
        manifest.add(CacheManifest.key(match_id, None, "insight", version, res["model"], int(match_id[2:])),
                     "analytics", res, f"captions/{v.tag}_{clip_ms}_{v.prompt}_{digest}.json", producer="insight",
                     version=version,
                     model=res["model"], seed=int(match_id[2:]), cost_usd=res.get("cost_usd"),
                     tokens_in=res.get("tokens_in"), tokens_out=res.get("tokens_out"))
        manifest.save()
    body = res.get("json") or {}
    checked = fact_check(slug, body, facts)
    problems = gates(slug, body, facts, view)
    doc = {"slug": slug, "clip_ms": clip_ms, "verdict": view["verdict"], "lower_third": body.get("lower_third", ""),
           "why": body.get("why", ""),
           "claims": [{k: c[k] for k in ("text", "kind", "value", "unit", "evidence_ids")} for c in checked["claims"]],
           "confidence": body.get("confidence"), "model": res.get("model"), "cost_usd": res.get("cost_usd"),
           "prompt_version": v.prompt, "cache_key": cached[0]["key"] if cached else manifest.find(
               producer="insight", version=version)[-1]["key"], "decision_source": v.source(clip_ms)}
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    out = REVIEW_DIR / f"{v.tag}_{slug}_{clip_ms}.md"
    status = "verified" if checked["verified"] else json.dumps(checked["diff"], ensure_ascii=False)
    out.write_text(f"# {v.tag} line · {slug} {view['clock']} · {view['verdict']}\n\nModel draft (gemini-4-argon). "
                   f"Fact Checker: {status}. Gates: {problems or 'pass'}.\nFacts: "
                   + "; ".join(f"{f['fact_id']} {f['label']} = {f['display']}" for f in facts)
                   + f"\n\n```json\n{json.dumps(doc, indent=1, ensure_ascii=False)}\n```\n")
    return {"review": str(out.relative_to(ROOT)), "verified": checked["verified"], "diff": checked["diff"],
            "gates": problems, "cost_usd": res.get("cost_usd"), "draft": {k: doc[k] for k in ("lower_third", "why")}}


def import_(v: Version = V4) -> dict:
    """Reviewed lines -> cache/<tag>/lines_<clip_ms>.json, after the Fact Checker and the gates pass the edited
    text."""
    from footage.featured import open_cache

    done, refused = [], {}
    for path in sorted(REVIEW_DIR.glob(f"{v.tag}_*.md")):
        doc = json.loads(BLOCK.search(path.read_text()).group(1))
        if not doc.get("hand_reviewed"):
            refused[path.name] = "not hand-reviewed yet"
            continue
        slug, clip_ms = doc["slug"], doc["clip_ms"]
        facts, view = v.facts_for(slug, clip_ms)
        checked = fact_check(slug, doc, facts, reviewed=True)
        problems = gates(slug, doc, facts, view) + ([] if view["verdict"] == doc["verdict"] else
                                                    [f"verdict changed to {view['verdict']}: rewrite"])
        if checked["diff"] or not checked["verified"] or problems:
            refused[path.name] = checked["diff"] or problems
            continue
        line = {"beat": f"{v.tag}_line", "slug": slug, "match_id": CLIPS[slug]["match_id"], "clip_ms": clip_ms,
                "clock": view["clock"], "verdict": view["verdict"], "lower_third": doc["lower_third"],
                "why": doc["why"], "claims": checked["claims"], "facts": facts,
                "display": {f["fact_id"]: f["display"] for f in facts}, "decision": view,
                "confidence": doc.get("confidence"), "model": doc.get("model"), "cache_key": doc.get("cache_key"),
                "prompt_version": doc.get("prompt_version"), "hand_reviewed": True,
                "source": v.source(clip_ms)}
        wrapper = {"$schema": "model_cache.schema.json", "schema_version": "1.0.0", "record": "tool_result",
                   "result": line}
        manifest = open_cache(slug)
        mid = CLIPS[slug]["match_id"]
        out = manifest.cache_dir / v.tag / f"lines_{clip_ms}.json"
        if out.exists() and json.loads(out.read_text()) == json.loads(json.dumps(wrapper)):
            done.append(path.name)            # unchanged: no rewrite, no new timestamp
            continue
        manifest.add(f"{mid}/match/{v.tag}@line_{clip_ms}/none/s{mid[2:]}", "analytics", wrapper,
                     f"{v.tag}/lines_{clip_ms}.json", producer=v.tag, version=f"line_{clip_ms}", seed=int(mid[2:]),
                     hand_reviewed=True)
        manifest.save()
        done.append(path.name)
    return {"imported": done, "refused": refused}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("slug")
    r.add_argument("clip_ms", type=int)
    r.add_argument("--dry-run", action="store_true")
    sub.add_parser("import")
    args = ap.parse_args(argv)
    out = run(args.slug, args.clip_ms, args.dry_run) if args.cmd == "run" else import_()
    print(json.dumps(out, indent=1, ensure_ascii=False, default=str)[:6000])
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "packages"))
    raise SystemExit(main())
