"""Featured real-clip moments: counterfactual, explanation, Fact Checker, cache.

    python -m footage.featured [--only <slug>] [--no-model]

For every moment in config/footage.yaml `featured`:
1. the frozen frame (data/footage/<slug>/moments/<clip_ms>.json) becomes an engine state (footage.freeze);
2. Sliding Doors: n=200 rollouts over 8 s of the action the player really took (`actual`) and of the alternative,
   from the same state and seeds -> a counterfactual.schema.json document whose players carry footage ids (p_9xx);
3. the evidence a claim may cite goes into a blackboard: the clip's tagged events (the real action is the anchor
   event, its player resolved to his footage id), the counterfactual, distance facts, and a match_metadata event
   whose `roster` and `clubs` let the Fact Checker accept exactly these real names (rules 3 and 7);
4. gemini-4-argon (role tactician_golden) explains it with prompts/tactician_footage@1.md, live, through SpendGuard
   under the clip's match id, at most `max_usd_per_moment` per moment; the Fact Checker verifies every claim;
5. everything is written to the clip's cache, data/footage/<slug>/cache/ (manifest keyed
   <match_id>/<moment_id>/<producer>@<version>/<model>/s<seed>), with evidence.jsonl for replay.
A re-run reuses cached model results (no second payment). Hand review: footage.review.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import math
import sys

import numpy as np

from footage.clips import CLIPS, ROOT, clip_dir, load_config
from footage.freeze import PITCH_L, PITCH_W, load, to_state

N, HORIZON_S = 200, 8.0
PROMPT = "tactician_footage@1"
ROLE = "tactician_golden"
ID_BASE = 900                    # footage player ids p_900-p_999, 20 per clip in config order
GOAL_Y = PITCH_W / 2


# ---------------------------------------------------------------------------------------------------- roster

def roster(slug: str) -> dict:
    """{label_key: pid} for every labelled player in the clip's moment files, plus {pid: real name} for the named
    ones and the clubs. label_key is "<team>:<label>". Ids are frozen in data/footage/<slug>/roster.json once given
    (cached explanations cite them); a player labelled later gets the next free id. Tracking-only labels
    (t<track_id>) get no id unless they had one before."""
    from footage.freeze import moments_dir

    k = list(CLIPS).index(slug)
    seen: dict[str, str | None] = {}
    for path in sorted(moments_dir(slug).glob("*.json")):
        if not path.stem.isdigit():          # overrides.json
            continue
        for p in json.loads(path.read_text())["players"]:
            if p.get("label"):
                key = f"{p['team']}:{p['label']}"
                seen[key] = seen.get(key) or p.get("name")
    path = clip_dir(slug) / "roster.json"
    saved = json.loads(path.read_text()) if path.exists() else {}
    for key, name in (saved.get("named") or {}).items():   # players named outside the moment files (goal scorers)
        seen[key] = seen.get(key) or name
    ids = saved["ids"] if saved else \
        {key: f"p_{ID_BASE + 20 * k + i:03d}" for i, key in enumerate(sorted(seen))}
    for key in seen:
        if key not in ids and not key.split(":", 1)[1].startswith("t"):
            used = {int(v[2:]) for v in ids.values()}
            block = [n for n in range(ID_BASE + 20 * k, ID_BASE + 20 * (k + 1)) if n not in used]
            spare = [n for n in range(980, 1000) if n not in used]     # overflow: ids are unique per match
            if not block and not spare:
                raise ValueError(f"{slug}: no free player id")
            ids[key] = f"p_{(block or spare)[0]:03d}"
    if not path.exists() or saved.get("ids") != ids:
        path.write_text(json.dumps({"slug": slug, "ids": ids, **({"named": saved["named"]} if saved.get("named")
                                                                   else {})}, indent=1) + "\n")
    names = {ids[key]: name for key, name in seen.items() if name and key in ids}
    clip = CLIPS[slug]
    clubs = {clip["home_id"]: {"name": clip["home"], "short_name": clip["home_short"]},
             clip["away_id"]: {"name": clip["away"], "short_name": clip["away_short"]}}
    return {"ids": ids, "names": names, "clubs": clubs}


def surname_match(name: str | None, full: str) -> bool:
    if not name:
        return False
    a, b = name.lower().split(), full.lower().split()
    return bool(a) and (a[-1] == b[-1] or name.lower() in full.lower() or full.lower() in name.lower())


# ---------------------------------------------------------------------------------------------------- counterfactual

def engine_action(state, moment: dict, spec: dict):
    """A schema-level alternative (target by label; carry direction in the moment file's coordinates) -> Action."""
    from kickoff.rules import Action

    if spec["kind"] == "pass":
        return Action(kind="pass", target=state.labels[spec["target"]] % 11)
    if spec["kind"] == "carry":
        dx, dy = spec["direction"]
        if state.mirrored:
            dx, dy = -dx, -dy
        n = math.hypot(dx, dy)
        return Action(kind="carry", direction=(dx / n, dy / n))
    return Action(kind=spec["kind"])


def counterfactual(moment: dict, spec: dict, ids: dict, moment_id: str, cf_id: str, evidence: list[str],
                   seed: int) -> dict:
    from kickoff import Override
    from rollout.core import engine_hash, rollout
    from rollout.sliding_doors import _prob, direction_tag, option_probs

    state = to_state(moment, seed=seed)
    holder = moment["ball"]["holder"]
    holder_team = next(p["team"] for p in moment["players"] if p.get("label") == holder)
    pid = ids[f"{holder_team}:{holder}"]
    probs = option_probs(state.source)
    row_ids = state.source.worlds[0].row_ids

    def schema(action_spec: dict, engine) -> dict:
        target = None
        key = action_spec["kind"]
        if action_spec["kind"] == "pass":
            target = ids[f"{holder_team}:{action_spec['target']}"]
            key = row_ids[state.labels[action_spec["target"]]]
        elif action_spec["kind"] == "carry":
            dx, dy = action_spec["direction"]
            target = direction_tag(dx, dy)
        p = _prob(probs, {"kind": "pass", "target": key} if action_spec["kind"] == "pass" else action_spec)
        return {"kind": action_spec["kind"], "actor": pid, "target": target, "policy_prob": p}

    actual_spec = moment["actual"]
    base = rollout(state, Override(first_action=engine_action(state, moment, actual_spec)), N, HORIZON_S, seed,
                   events=[])
    alt = rollout(to_state(moment, seed=seed), Override(first_action=engine_action(state, moment, spec)), N,
                  HORIZON_S, seed, events=[])
    if base.invalid_reason or alt.invalid_reason:
        raise ValueError(base.invalid_reason or alt.invalid_reason)
    # ghost layer convention (overlay cue contract): first half the real action's futures, second half the
    # alternative's
    paths = np.concatenate([base.ball_paths[:N // 2], alt.ball_paths[:N // 2]]).astype(np.float64)
    if state.mirrored:                       # back into the moment file's coordinates (what the frame shows)
        paths = np.stack([PITCH_L - paths[..., 0], PITCH_W - paths[..., 1]], axis=-1)
    return {"schema_version": "1.0.0", "counterfactual_id": cf_id, "match_id": moment["match_id"],
            "moment_id": moment_id, "t_ms": int(moment["t_ms"]), "engine": "scripted_v1", "n": N,
            "horizon_s": HORIZON_S, "seed": seed, "actual": schema(actual_spec, base),
            "alternative": schema(spec, alt), "baseline": base.outcome(), "alternative_outcome": alt.outcome(),
            "delta_win_prob_home": round(alt.win_prob_home - base.win_prob_home, 4),
            "futures_sample": np.round(paths, 2).tolist(), "evidence_event_ids": evidence,
            "pitch_control_snapshot_id": f"pc_{int(moment_id[3:]):06d}", "compute_ms": None,
            "engine_hash": engine_hash()}


def pitch_control_doc(moment: dict, snapshot_id: str, seed: int) -> tuple[dict, np.ndarray]:
    """The frozen frame's pitch-control snapshot (same document as the MCP get_pitch_control tool), in the engine's
    coordinates for the period, and its grid."""
    from mcp_server.tools_core import overloads
    from physics.pitch_control import contested_fraction, pitch_control, zones

    state = to_state(moment, seed=seed)
    S = np.asarray(state.S[0], dtype=np.float64)
    pc = pitch_control(S)
    team = int(state.possession[0])
    over = overloads(S, team, state.period)
    z = zones(pc, home_attacks_right=state.period == 1)
    z.update({o["label"]: o["count"] for o in over})
    return {"snapshot_id": snapshot_id, "match_id": moment["match_id"], "t_ms": int(moment["t_ms"]),
            "period": state.period, "team_in_possession": "home" if team == 0 else "away",
            "home_share": round(float(pc.mean()), 4), "contested_frac": round(contested_fraction(pc), 4),
            "zones": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in z.items()}, "overloads": over,
            "grid_path": f"pitch_control/{snapshot_id}.npz", "mirrored": bool(state.mirrored)}, pc


# ---------------------------------------------------------------------------------------------------- evidence

def attacking_goal(moment: dict, team: str) -> tuple[float, float]:
    plus = (moment["home_attacks"] == "+x") == (team == "home")
    return (PITCH_L if plus else 0.0, GOAL_Y)


def evidence_docs(slug: str, featured: list[dict], ros: dict) -> dict[str, list[dict]]:
    """Blackboard documents per collection: match_metadata, the tagged events (real actions resolved to footage
    ids), and per moment the facts (distances) the explanation may cite. Counterfactuals are added later."""
    clip = CLIPS[slug]
    match_id = clip["match_id"]
    events = [json.loads(line) for line in (clip_dir(slug) / "events.jsonl").read_text().splitlines() if line]
    names = ros["names"]
    for e in events:
        pname = (e.get("attrs") or {}).get("player_name")
        hits = [pid for pid, n in names.items() if surname_match(pname, n)]
        if len(hits) == 1:
            e["player"] = hits[0]
    home = sorted(pid for key, pid in ros["ids"].items() if key.startswith("home:"))
    away = sorted(pid for key, pid in ros["ids"].items() if key.startswith("away:"))
    meta = {"schema_version": "1.0.0", "id": "e_0000", "match_id": match_id, "idx": 0, "t_ms": 0, "period": 1,
            "clock": "00:00", "type": "match_metadata", "team": "none", "player": None, "location": None,
            "outcome": "n/a", "attrs": {"home": clip["home_id"], "away": clip["away_id"], "seed": int(match_id[2:]),
                                        "lineups": {"home": {"starting": home, "bench": []},
                                                    "away": {"starting": away, "bench": []}},
                                        "roster": names, "clubs": ros["clubs"], "source": "footage"}}
    facts, n = [], 0
    for f in featured:
        m = load(slug, f["clip_ms"])
        holder = next(p for p in m["players"] if p.get("label") == m["ball"]["holder"])
        gx, gy = attacking_goal(m, holder["team"])
        n += 1
        facts.append({"fact_id": f"f_{n:06d}", "match_id": match_id, "moment_id": f["moment_id"],
                      "counterfactual_id": f["cf_id"], "label": "distance_to_goal", "unit": "metres",
                      "value": round(math.hypot(holder["x"] - gx, holder["y"] - gy), 1), "t_ms": m["t_ms"],
                      "players": [ros["ids"][f"{holder['team']}:{holder['label']}"]]})
        if f["alternative"]["kind"] == "pass":
            tgt = next(p for p in m["players"] if p.get("label") == f["alternative"]["target"])
            n += 1
            facts.append({"fact_id": f"f_{n:06d}", "match_id": match_id, "moment_id": f["moment_id"],
                          "counterfactual_id": f["cf_id"], "label": "pass_target_distance_to_goal",
                          "unit": "metres", "value": round(math.hypot(tgt["x"] - gx, tgt["y"] - gy), 1),
                          "t_ms": m["t_ms"], "players": [ros["ids"][f"{tgt['team']}:{tgt['label']}"]]})
    return {"events": [meta, *events], "facts": facts}


def anchor_event(events: list[dict], moment: dict, pid: str) -> str | None:
    """The tagged event of the real action: the holder's shot (or pass) closest after the frozen frame."""
    kind = {"shoot": "shot", "pass": "pass", "carry": "carry"}[moment["actual"]["kind"]]
    near = [e for e in events if e.get("type") == kind and e.get("player") == pid
            and -1000 <= e["attrs"].get("clip_ms", -10**9) - moment["clip_ms"] <= 4000]
    return near[0]["id"] if near else None


# ---------------------------------------------------------------------------------------------------- explanation

def footage_block(slug: str, ros: dict) -> str:
    clip = CLIPS[slug]
    lines = ["REAL MATCH CONTEXT (Premier League, used with permission; real names allowed only as listed here)",
             f"HOME: {clip['home']} ({clip['home_short']}, club id {clip['home_id']})",
             f"AWAY: {clip['away']} ({clip['away_short']}, club id {clip['away_id']})", "PLAYERS:"]
    for key, pid in sorted(ros["ids"].items(), key=lambda kv: kv[1]):
        team, label = key.split(":", 1)
        name = ros["names"].get(pid)
        shown = name or (f"number {label.lstrip('#')}" if label.startswith("#") else "unidentified player")
        lines.append(f"  {pid}: {shown} ({clip[team + '_short']})" + ("" if name else " [not a claim]"))
    return "\n".join(lines)


def explanation_messages(slug: str, ros: dict, moment: dict, f: dict, cf: dict, recent: list[dict],
                         facts: list[dict]) -> list[dict]:
    from newsroom import config
    from newsroom.executors.tactician import compact_event

    _, system = config.prompt(PROMPT)
    holder = moment["ball"]["holder"]
    team = next(p["team"] for p in moment["players"] if p.get("label") == holder)
    decision = {"t_ms": moment["t_ms"], "clock": moment["clock"], "actor": cf["actual"]["actor"], "team": team,
                "actual": moment["actual"]["kind"], "real_outcome": f.get("real_outcome"),
                "anchor_event_id": cf["evidence_event_ids"][0] if cf["evidence_event_ids"] else None}
    payload = {"MOMENT": {"match_id": moment["match_id"], "moment_id": f["moment_id"], "clock": moment["clock"],
                          "score": moment["score"], "period": moment["period"]},
               "DECISION": decision,
               "COUNTERFACTUAL": {k: v for k, v in cf.items() if k not in ("futures_sample", "engine_hash")},
               "FACTS": facts, "RECENT_EVENTS": [compact_event(e) for e in recent]}
    return [{"role": "system", "content": footage_block(slug, ros) + "\n\n" + system},
            {"role": "user", "content": json.dumps(payload, separators=(",", ":"), default=str)}]


async def explain(llm, match_id: str, moment_id: str, messages: list[dict]) -> dict:
    from newsroom import config
    from newsroom.executors.tactician import RESPONSE_SCHEMA

    role = config.role(ROLE)
    return await llm.complete(ROLE, messages, None, match_id=match_id, moment_id=moment_id, schema=RESPONSE_SCHEMA,
                              prompt_version=PROMPT, producer="tactician", timeout_s=role.timeout_s,
                              hedge_after_s=None)


def check(match_id: str, body: dict, bb) -> tuple[dict, dict]:
    """(explanation document with verified claims, Fact Checker result)."""
    from newsroom.executors.tactician import to_claim
    from newsroom.factcheck import verify_claims

    claims = [c for c in (to_claim(x) for x in body.get("claims", []) if isinstance(x, dict)) if c]
    result = verify_claims(match_id, claims, bb, {"why": body.get("why", "")})
    return {"why": body.get("why", ""), "claims": result["claims"],
            "confidence": float(body.get("confidence", 0.5) or 0.5)}, result


# ---------------------------------------------------------------------------------------------------- cache

def open_cache(slug: str):
    from cache.manifest import CacheManifest, now_iso, sha256_file
    from rollout.core import engine_hash

    cache_dir = clip_dir(slug) / "cache"
    if (cache_dir / "manifest.json").exists():
        return CacheManifest.load(cache_dir)
    clip = CLIPS[slug]
    h = hashlib.sha256()
    for p in sorted((clip_dir(slug) / "moments").glob("*.json")):
        h.update(p.read_bytes())
    events = clip_dir(slug) / "events.jsonl"
    if not events.exists():                     # a clip without tagged events: track A's reviewed strikes
        events = clip_dir(slug) / "strikes.json"
    data = {"schema_version": "1.0.0", "match_id": clip["match_id"], "match_seed": int(clip["match_id"][2:]),
            "events_sha256": sha256_file(events), "tracking_sha256": h.hexdigest(),
            "engine_hash": engine_hash(), "created_at": now_iso(), "frozen": False, "entries": [],
            "totals": {"entries": 0, "cost_usd": 0.0}}
    return CacheManifest(data, cache_dir)


def run(only: str | None = None, model: bool = True) -> list[dict]:
    from blackboard import SqliteBlackboard
    from cache.manifest import CacheManifest

    cfg = load_config()
    featured = [dict(f) for f in cfg["featured"] if only in (None, f["slug"])]
    out = []
    for slug in dict.fromkeys(f["slug"] for f in featured):
        clip = CLIPS[slug]
        match_id, seed = clip["match_id"], int(clip["match_id"][2:])
        mine = [f for f in featured if f["slug"] == slug]
        for f in mine:
            f["cf_id"] = f"cf_{int(f['moment_id'][3:]):06d}"
        ros = roster(slug)
        docs = evidence_docs(slug, mine, ros)
        manifest = open_cache(slug)
        bb = SqliteBlackboard(":memory:")
        bb.put_many("events", docs["events"])
        for fact in docs["facts"]:
            bb.put("facts", fact)
        llm = None
        for f in mine:
            moment = load(slug, f["clip_ms"])
            holder = moment["ball"]["holder"]
            team = next(p["team"] for p in moment["players"] if p.get("label") == holder)
            pid = ros["ids"][f"{team}:{holder}"]
            anchor = anchor_event(docs["events"], moment, pid)
            cf = counterfactual(moment, f["alternative"], ros["ids"], f["moment_id"], f["cf_id"],
                                [anchor] if anchor else [], seed)
            bb.put("counterfactuals", cf)
            pc_doc, grid = pitch_control_doc(moment, cf["pitch_control_snapshot_id"], seed)
            bb.put("pitch_control", pc_doc)       # the document goes to evidence.jsonl, the grid to the cache
            buf = io.BytesIO()
            np.savez_compressed(buf, grid=grid.astype(np.float16))
            manifest.add(CacheManifest.key(match_id, f["moment_id"], "pitch_control", "pc@1", None, seed),
                         "pitch_control", buf.getvalue(), pc_doc["grid_path"], moment_id=f["moment_id"],
                         producer="pitch_control", version="pc@1", seed=seed)
            manifest.add(CacheManifest.key(match_id, f["moment_id"], "rollout", "scripted_v1", "scripted", seed),
                         "counterfactual", cf, f"counterfactuals/{f['cf_id']}.json", moment_id=f["moment_id"],
                         producer="rollout", version="scripted_v1", model="scripted", seed=seed,
                         simulated_latency_ms=1200)
            recent = [e for e in docs["events"] if e["type"] != "match_metadata"
                      and moment["t_ms"] - 15000 <= e["t_ms"] <= moment["t_ms"] + 3000]
            facts = [x for x in docs["facts"] if x["moment_id"] == f["moment_id"]]
            key = CacheManifest.key(match_id, f["moment_id"], "tactician", PROMPT, None, seed)
            cached = [e for e in manifest.find(moment_id=f["moment_id"], producer="tactician", version=PROMPT)]
            row = {"slug": slug, "moment_id": f["moment_id"], "clock": moment["clock"], "anchor": anchor,
                   "actual": cf["actual"]["kind"], "alternative": f["alternative"],
                   "baseline_p_goal": cf["baseline"][f"p_goal_{team}"],
                   "alternative_p_goal": cf["alternative_outcome"][f"p_goal_{team}"],
                   "delta_win_prob_home": cf["delta_win_prob_home"]}
            if cached:
                res = manifest.read(cached[0])
            elif model:
                from api.spend import SpendGuard
                from newsroom.llm import LiveClient

                llm = llm or LiveClient(mode="precompute", guard=SpendGuard())
                guard = llm.guard
                before = guard.per_match[match_id]
                res = asyncio.run(explain(llm, match_id, f["moment_id"],
                                          explanation_messages(slug, ros, moment, f, cf, recent, facts)))
                if guard.per_match[match_id] - before > cfg["tagger"].get("max_usd_per_moment", 0.10):
                    raise SystemExit(f"{slug} {f['moment_id']}: over the per-moment budget")
                res = {"$schema": "model_cache.schema.json", "schema_version": "1.0.0", "record": "model_result",
                       "via": "live", **{k: res.get(k) for k in ("json", "text", "model", "tokens_in", "tokens_out",
                                                                  "cost_usd", "latency_ms")}}
                manifest.add(key.replace("/none/", f"/{res['model']}/"), "explanation", res,
                             f"explanations/r_{f['moment_id']}.json", moment_id=f["moment_id"], producer="tactician",
                             version=PROMPT, model=res["model"], seed=seed, cost_usd=res.get("cost_usd"),
                             tokens_in=res.get("tokens_in"), tokens_out=res.get("tokens_out"),
                             simulated_latency_ms=res.get("latency_ms") or 0)
            else:
                out.append({**row, "explanation": None})
                continue
            exp, result = check(match_id, res.get("json") or {}, bb)
            out.append({**row, "why": exp["why"], "verified": result["verified"],
                        "rejected": [d for d in result["diff"]], "cost_usd": res.get("cost_usd")})
        # evidence for replay and the Fact Checker (same documents)
        lines = [json.dumps({"_collection": "events", **e}, separators=(",", ":")) for e in docs["events"]]
        lines += [json.dumps({"_collection": "facts", **x}, separators=(",", ":")) for x in docs["facts"]]
        lines += [json.dumps({"_collection": "counterfactuals", **cf}, separators=(",", ":"))
                  for cf in bb.query("counterfactuals", match_id=match_id)]
        lines += [json.dumps({"_collection": "pitch_control", **pc}, separators=(",", ":"))
                  for pc in bb.query("pitch_control", match_id=match_id)]
        manifest.add(CacheManifest.key(match_id, None, "evidence", "factcheck", None, seed), "analytics",
                     ("\n".join(lines) + "\n").encode(), "evidence.jsonl", producer="evidence", version="factcheck",
                     seed=seed)
        manifest.save()
        bb.close()
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default=None)
    ap.add_argument("--no-model", action="store_true", help="counterfactuals and evidence only")
    args = ap.parse_args(argv)
    for row in run(args.only, model=not args.no_model):
        print(json.dumps(row, default=str))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "packages"))
    raise SystemExit(main())
