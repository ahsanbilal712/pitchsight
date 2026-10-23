"""The agent pipeline behind one on-air line (video v6, track C's pipeline view): one record per node, from what was
really recorded, with every timing labelled by where it comes from. No latency is invented.

    python -m footage.pipeline [<slug> <clip_ms>]    # default: Amad 56:41 and Liverpool 86:23
    # -> data/footage/<slug>/cache/v6/pipeline_<clip_ms>.json (the full record) and
    #    pipeline_<slug>_<clip_ms>.json (track C's view), both in the clip's cache manifest

Nodes: Freeze (the tracked frame), Scout (what flagged the moment), Proposer (every option listed), Model (the xG
computation), Tactician (gemini-4-argon's draft), Fact Checker (each claim against its evidence), Producer review
(the hand edit, draft against final), Director (the decision and its timing), On air (the cue).

Timing sources:
- "recorded live": the model call's own record (captions/*.json latency_ms, tokens, cost; the ledger row);
- "measured re-run": a deterministic step re-run now in-process (median of REPEATS, perf_counter), checked to give
  the stored numbers;
- "replay": the studio replay's trace row (whole milliseconds; model answers served from the cache);
- null with "not recorded" where nothing measured it.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from datetime import UTC, datetime

from footage.clips import CLIPS, ROOT, clip_dir

REPEATS = 25
DEFAULT = [("manutd-mancity-2526", 877000), ("liverpool-mancity-2526", 875000)]


def _median_ms(fn, repeats: int = REPEATS) -> tuple[float, object]:
    out, times = None, []
    for _ in range(repeats):
        t0 = time.perf_counter()
        out = fn()
        times.append((time.perf_counter() - t0) * 1000)
    return round(statistics.median(times), 3), out


def _timing(source: str, ms: float | None, **extra) -> dict:
    return {"source": source, "ms": ms, **extra}


def _stream(slug: str) -> list[dict]:
    path = clip_dir(slug) / "cache" / "studio" / "stream.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def build(slug: str, clip_ms: int) -> dict:
    from evals.pitchwatch.v5 import decision as xg_decision
    from footage.featured import open_cache
    from footage.freeze import load
    from footage.v4_lines import fact_check
    from footage.v5_lines import facts_for

    v6 = clip_dir(slug) / "cache" / "v6"
    line = json.loads((clip_dir(slug) / "cache" / "v5" / f"lines_{clip_ms}.json").read_text())["result"]
    stored = json.loads((clip_dir(slug) / "cache" / "v5" / f"xg_decision_{clip_ms}.json").read_text())["result"]
    m = load(slug, clip_ms)
    rows = _stream(slug)
    mo = next(r["doc"] for r in rows if r["collection"] == "moments" and r["doc"].get("clip_ms") == clip_ms)
    traces = {r["doc"]["executor"]: r for r in rows if r["collection"] == "traces"
              and r["doc"]["moment_id"] == mo["moment_id"]}
    cue_row = next(r for r in rows if r["collection"] == "cues" and r["doc"]["moment_id"] == mo["moment_id"])
    cue = cue_row["doc"]
    manifest = open_cache(slug)
    call_entry = next(e for e in manifest.entries if e.get("key") == line["cache_key"])
    call = manifest.read(call_entry)
    nodes = []

    # Freeze
    seen = [p for p in m["players"] if p.get("source") != "prior"]
    nodes.append({"node": "Freeze", "what": f"the tracked frame at {m['clock']} (clip {clip_ms / 1000:.2f} s)",
                  "outputs": {"players_in_view": len(seen), "homography": (m.get("homography") or {}).get("source"),
                              "holder": m["ball"]["holder"], "actual": m["actual"]["kind"]},
                  "timing": _timing("not recorded", None, note="precomputed by tracking (track A) and the moment file")})

    # Scout
    lev_ms = None
    try:
        from footage.studio import leverage
        lev_ms, lev = _median_ms(lambda: leverage(slug, clip_ms), repeats=3)
    except Exception as exc:                      # noqa: BLE001 (reported, not hidden)
        lev = f"not computed: {type(exc).__name__}"
    nodes.append({"node": "Scout", "what": "flags a big chance; the Sliding Doors floor is waived for a producer-"
                  "selected moment", "outputs": {"kind": mo["kind"], "leverage": mo.get("leverage"),
                                                 "leverage_rerun": lev, "selected_by": mo.get("selected_by"),
                                                 "floor_waived": traces.get("director", {}).get("doc", {})
                                                 .get("floor_waived")},
                  "timing": _timing("measured re-run", lev_ms, note="leverage: GoalIn8sHead on two tracked frames")
                  if lev_ms is not None else _timing("not recorded", None)})

    # Proposer
    opts = [{k: o.get(k) for k in ("label", "name", "p_pass", "xg_receiver", "xg_after_pass", "onside_margin_m",
                                   "offside_risk")} for o in stored["alternatives"]]
    nodes.append({"node": "Proposer", "what": "every team-mate in view as a pass option", "outputs": {
        "options": opts, "rule": stored.get("best_rule"), "shown": (line["decision"]["alternative"] or {}).get("label")},
        "timing": _timing("not recorded", None, note="part of the model step below")})

    # Model
    model_ms, again = _median_ms(lambda: xg_decision(slug, clip_ms))
    same = all(abs((a.get("xg_after_pass_exact") or 0) - (b.get("xg_after_pass_exact") or 0)) < 1e-9
               for a, b in zip(again["alternatives"], stored["alternatives"], strict=True)) and \
        again["actual"]["xg_exact"] == stored["actual"]["xg_exact"]
    nodes.append({"node": "Model", "what": stored.get("formula"), "outputs": {
        "shot_xg_freeze": stored["actual"]["xg_exact"], "shot_xg_strike": stored["actual"].get("strike_xg"),
        "options_computed": len(stored["alternatives"]), "deterministic": stored.get("deterministic"),
        "rerun_matches_stored": same},
        "timing": _timing("measured re-run", model_ms, repeats=REPEATS)})

    # Tactician
    draft = call.get("json") or {}
    nodes.append({"node": "Tactician", "what": f"{call.get('model')} drafts the lower-third and the why",
                  "outputs": {"lower_third": draft.get("lower_third"), "why": draft.get("why"),
                              "claims": len(draft.get("claims", [])), "prompt": line.get("prompt_version")},
                  "timing": _timing("recorded live", call.get("latency_ms"), at=call_entry.get("created_at"),
                                    tokens_in=call.get("tokens_in"), tokens_out=call.get("tokens_out"),
                                    cost_usd=call.get("cost_usd"))})

    # Fact Checker (the final line's claims against their facts)
    facts, _ = facts_for(slug, clip_ms)
    by_id = {f["fact_id"]: f for f in facts}
    body = {"lower_third": line["lower_third"], "why": line["why"],
            "claims": [{k: c[k] for k in ("text", "kind", "value", "unit", "evidence_ids")} for c in line["claims"]]}
    fc_ms, res = _median_ms(lambda: fact_check(slug, body, facts, reviewed=True))
    claims = [{"text": c["text"], "kind": c["kind"], "value": c["value"], "verified": c["verified"],
               "reject_reason": c.get("reject_reason"),
               "evidence": [{"id": e, "label": by_id[e]["label"], "display": by_id[e]["display"],
                             "source": by_id[e]["source"]} if e in by_id else {"id": e} for e in c["evidence_ids"]]}
              for c in res["claims"]]
    nodes.append({"node": "Fact Checker", "what": "each claim against its evidence (rules 1-8); every number in the "
                  "line must be a verified claim", "outputs": {"verified": res["verified"], "claims": claims,
                                                               "diff": res["diff"]},
                  "timing": _timing("measured re-run", fc_ms, repeats=REPEATS)})

    # Producer review
    nodes.append({"node": "Producer review", "what": "hand review of the model draft (track B)", "outputs": {
        "draft": {"lower_third": draft.get("lower_third"), "why": draft.get("why")},
        "final": {"lower_third": line["lower_third"], "why": line["why"]}, "hand_reviewed": line["hand_reviewed"]},
        "timing": _timing("not recorded", None, note="human step")})

    # Director, On air
    d_row = traces.get("director", {}).get("doc", {})
    nodes.append({"node": "Director", "what": "places the cue and picks the layer and modes", "outputs": {
        "kind": cue["kind"], "layer": cue["layer"], "modes": cue["targets"]["modes"], "t_in_ms": cue["t_in_ms"],
        "t_out_ms": cue["t_out_ms"], "priority": cue["priority"], "floor_waived": d_row.get("floor_waived")},
        "timing": _timing("replay", d_row.get("latency_ms"), note="whole milliseconds; 0 = under 1 ms")})
    nodes.append({"node": "On air", "what": "the cue the studio shows", "outputs": {
        "cue_id": cue["cue_id"], "headline": cue["text"]["headline"], "body": cue["text"]["body"],
        "bar": cue["graphics"].get("bar"), "verified": cue["verified"], "clip_ms": cue_row["clip_ms"]},
        "timing": _timing("replay", traces.get("cuebus", {}).get("doc", {}).get("latency_ms"))})

    result = {"beat": "pipeline", "slug": slug, "match_id": CLIPS[slug]["match_id"], "clip_ms": clip_ms,
              "clock": m["clock"], "nodes": nodes, "measured_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "timing_sources": ["recorded live", "measured re-run", "replay", "not recorded"],
              "sources": {"line": f"cache/v5/lines_{clip_ms}.json", "decision": f"cache/v5/xg_decision_{clip_ms}.json",
                          "studio": "cache/studio/stream.jsonl", "model_call": call_entry["path"]}}
    v6.mkdir(exist_ok=True)
    register(slug, f"v6/pipeline_{clip_ms}.json", f"pipeline_{clip_ms}",
             {"$schema": "model_cache.schema.json", "schema_version": "1.0.0", "record": "tool_result", "result": result})
    return result


# ---------------------------------------------------------------------------------------------------- track C's view

def _clock(t_ms: int) -> str:
    return f"{t_ms // 60000:02d}:{t_ms // 1000 % 60:02d}"


def view(slug: str, clip_ms: int, rec: dict | None = None) -> dict:
    """Track C's format (track-c-v6-formats.md, 4): pipeline_<slug>_<moment>.json, agents scout to cuebus, each
    with what it said from the recorded run, its latency and that latency's source. Every number in a `says` is a
    fact in `facts` (display and source), so grounding binds it like a caption."""
    from footage.names import name_at, short
    from footage.v4_lines import moment as load_moment

    rec = rec or build(slug, clip_ms)
    n = {x["node"]: x for x in rec["nodes"]}
    line = json.loads((clip_dir(slug) / "cache" / "v5" / f"lines_{clip_ms}.json").read_text())["result"]
    m = load_moment(slug, clip_ms)
    facts: list[dict] = []

    def fact(display: str, value, source: str) -> str:
        if not any(f["display"] == display and f["source"] == source for f in facts):
            facts.append({"display": display, "value": value, "source": source})
        return display

    def who(label: str) -> str | None:
        name = name_at(slug, m, label)
        return short(name) if name else None        # a verified name or no label (never an internal one)

    holder = who(m["ball"]["holder"])
    d = line["decision"]
    F = {f["role"]: f for f in line["facts"]}
    shot_d = fact(F["distance"]["display"], F["distance"]["value"], f"v5 lines_{clip_ms} {F['distance']['fact_id']}")
    shot_xg = fact(F["actual"]["display"], F["actual"]["value"], f"v5 lines_{clip_ms} {F['actual']['fact_id']}")
    options = [{"label": "Shot", "xg": shot_xg}]
    for o in n["Proposer"]["outputs"]["options"]:
        nm = who(o["label"])
        options.append({"label": f"Pass to {nm}" if nm else "Pass", "xg_after_pass": fact(
            f"{o['xg_after_pass']:.2f}", o["xg_after_pass"], f"v5 xg_decision_{clip_ms} {o['label']} xg_after_pass"),
            "p_pass": fact(f"{round(o['p_pass'] * 100)}%", o["p_pass"], f"v5 xg_decision_{clip_ms} {o['label']} p_pass"),
            "offside_risk": o["offside_risk"]})
    k = n["Model"]["outputs"]["options_computed"]
    nodes = [
        {"agent": "scout", "t_ms": m["t_ms"], **_lat(n["Scout"]),
         "says": f"Big chance: {holder or 'the carrier'} shoots from {shot_d} (producer-selected)"},
        {"agent": "proposer", "options": options, **_lat(n["Proposer"]),
         "says": f"The shot and {fact(str(k), k, f'v5 xg_decision_{clip_ms} alternatives')} passes to team-mates "
                 "in view"},
        {"agent": "rollout", "n": k, **_lat(n["Model"]),
         "says": "Reference xG + pass model, deterministic (no rollouts)"},
    ]
    if d["alternative"]:
        a, b = F["actual"], F["alternative"]
        gap = round(b["value"] - a["value"], 2) if a["display"] != b["display"] else 0
        target = who(d["alternative"]["label"])
        src = f"v5 lines_{clip_ms}: {b['fact_id']} - {a['fact_id']}"
        says = (f"The pass{' to ' + target if target else ''} beats the shot by "
                f"{fact(f'{gap:.2f}', gap, src)} xG")
    else:
        says = f"No pass clears the rule: the shot alone, {shot_xg} xG"
    nodes.append({"agent": "tactician", **_lat(n["Tactician"]), "says": says,
                  "draft": n["Tactician"]["outputs"]["lower_third"], "model": "gemini-4-argon"})
    nodes.append({"agent": "factcheck", **_lat(n["Fact Checker"]),
                  "claims": [{"text": c["text"], "ok": c["verified"],
                              "evidence": "; ".join(f"{e.get('label', e['id'])} = {e.get('display', '?')}"
                                                    for e in c["evidence"])}
                             for c in n["Fact Checker"]["outputs"]["claims"]]})
    dr = n["Director"]["outputs"]
    secs = (dr["t_out_ms"] - dr["t_in_ms"]) // 1000
    nodes.append({"agent": "director", **_lat(n["Director"]),
                  "says": f"On air {fact(_clock(dr['t_in_ms']), dr['t_in_ms'], 'studio cue t_in_ms')}, "
                          f"{dr['layer'].replace('_', ' ')}, {fact(f'{secs} s', secs, 'studio cue t_out_ms - t_in_ms')}"})
    nodes.append({"agent": "cuebus", **_lat(n["On air"]), "line": line["lower_third"]})
    for f in line["facts"]:                          # the line's own numbers
        fact(f["display"], f["value"], f["source"])
    res = {"beat": "pipeline", "moment_id": "mo_00001", "slug": slug, "match_id": CLIPS[slug]["match_id"],
           "clip_ms": clip_ms, "clock": m["clock"], "nodes": nodes, "facts": facts,
           "timing_rule": "latency_source: recorded live | measured re-run | replay (cache-served, whole ms) | "
                          "not recorded (latency_ms null)", "record": f"cache/v6/pipeline_{clip_ms}.json"}
    register(slug, f"v6/pipeline_{slug}_{clip_ms}.json", f"pipeline_view_{clip_ms}",
             {"$schema": "model_cache.schema.json", "schema_version": "1.0.0", "record": "tool_result", "result": res})
    return res


def register(slug: str, rel: str, version: str, doc: dict) -> None:
    """Write a v6 file through the clip's cache manifest (loaded just before the save: other tracks write it too)."""
    from footage.featured import open_cache

    manifest = open_cache(slug)
    mid = CLIPS[slug]["match_id"]
    manifest.add(f"{mid}/match/v6@{version}/none/s{mid[2:]}", "analytics", doc, rel, producer="v6", version=version,
                 seed=int(mid[2:]))
    manifest.save()


def _lat(node: dict) -> dict:
    return {"latency_ms": node["timing"]["ms"], "latency_source": node["timing"]["source"]}


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "packages"))
    targets = [(sys.argv[1], int(sys.argv[2]))] if len(sys.argv) > 2 else DEFAULT
    for slug, ms in targets:
        r = build(slug, ms)
        print(slug, ms, [(n["node"], n["timing"]["source"], n["timing"]["ms"]) for n in r["nodes"]])
        view(slug, ms, r)
