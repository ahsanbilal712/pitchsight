"""Studio on a real clip, option (c) (video v3): the real newsroom executors run in-process over the real-clip
moments, and that run is cached for the studio to replay with real names in the trace and the Why? drawer.

    python -m footage.studio [<slug>...]

Per featured Sliding Doors moment (config/footage.yaml) the Tactician, Narrator, Fact Checker, Director and CueBus
executors run as in the newsroom, against the clip's evidence (tagged events, counterfactual, pitch control,
match_metadata with the roster and clubs). Their model calls are answered from the clip's cache by the reviewed
gemini-4-argon outputs (explanation, line), so the run is reproducible and costs nothing. The steps that ran in the
precompute (ingest, scout, proposer, rollout) are written as trace rows saying so. The Fourth Official cue
(footage.fourth) goes through the same Director and CueBus. Moments are producer-selected (the Director shows them
below the Sliding Doors leverage floor and says so in its trace row).

Output: data/footage/<slug>/cache/studio/stream.jsonl, one line per blackboard write in order:
{"seq", "clip_ms", "t_ms", "collection", "doc"} (collections: moments, traces, explanations, counterfactuals, cues).
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

from footage.clips import CLIPS, ROOT, clip_dir, load_config
from footage.freeze import load

PRECOMPUTED = ("ingest", "scout", "proposer", "rollout")


class Ctx:
    """Collects what an executor sends (WorkflowContext stand-in for an in-process run)."""

    def __init__(self) -> None:
        self.sent, self.outputs, self.requests = [], [], []

    async def request_info(self, request_data, response_type) -> None:
        self.requests.append(request_data)

    async def send_message(self, msg) -> None:
        self.sent.append(msg)

    async def yield_output(self, out) -> None:
        self.outputs.append(out)


class CachedAnswers:
    """LLM client for the replay of one moment: the reviewed model outputs from the clip's cache."""

    def __init__(self, explanation: dict, line: dict, model: str, keys: dict[str, str]) -> None:
        self.explanation, self.line, self.model, self.keys = explanation, line, model, keys

    async def complete(self, role: str, messages, tools=None, **ctx) -> dict:
        producer = ctx.get("producer")
        if producer == "tactician":
            claims = []
            for c in self.explanation["claims"]:
                numeric = c["kind"] in ("number", "minute")
                claims.append({"text": c["text"], "kind": c["kind"], "unit": c.get("unit") or "",
                               "evidence_ids": c["evidence_ids"],
                               **({"value_number": c["value"]} if numeric else {"value_text": str(c["value"])})})
            body = {"why": self.explanation["why"], "claims": claims, "confidence": self.explanation["confidence"]}
            key = self.keys["explanation"]
        else:
            body, key = self.line, self.keys["line"]
        return {"json": body, "text": json.dumps(body), "model": self.model, "cache_hit": True, "cache_key": key,
                "latency_ms": 0, "cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0}


class EvidenceTools:
    """Tool client over the clip's evidence in the blackboard (query_events, get_pitch_control)."""

    def __init__(self, bb) -> None:
        self.bb = bb

    async def call(self, name: str, args: dict):
        if name == "query_events":
            return [e for e in self.bb.query("events", match_id=args["match_id"], t_from_ms=args.get("t_from_ms"),
                                             t_to_ms=args.get("t_to_ms")) if e["type"] != "match_metadata"]
        if name == "get_pitch_control":
            docs = self.bb.query("pitch_control", match_id=args["match_id"])
            return docs[0] if docs else {"error": "no snapshot", "code": "cache_miss"}
        return {"error": f"{name} is not served in the real-clip replay", "code": "cache_miss"}


class Recording:
    """Blackboard wrapper that records every write with the clip time it belongs to."""

    def __init__(self, bb, clip_of) -> None:
        self.bb, self.clip_of, self.log = bb, clip_of, []

    def __getattr__(self, name):
        return getattr(self.bb, name)

    def put(self, collection: str, doc: dict) -> str:
        out = self.bb.put(collection, doc)
        if collection in ("moments", "traces", "explanations", "counterfactuals", "cues", "requests"):
            stored = self.bb.get(collection, out, doc.get("match_id"))
            t = stored.get("t_in_ms", stored.get("t_ms"))
            self.log.append({"collection": collection, "t_ms": t, "doc": stored})
        return out


def _trace(bb, env, executor: str, status: str, **extra) -> None:
    bb.put("traces", {"match_id": env.moment.match_id, "run_id": env.run_id, "moment_id": env.moment.moment_id,
                      "trace_id": env.trace_id, "executor": executor, "branch": env.branch, "t_ms": env.moment.t_ms,
                      "started_ms": int(time.time() * 1000), "latency_ms": 0, "model": extra.pop("model", None),
                      "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "cache_hit": extra.pop("cache_hit", True),
                      "status": status, "checkpoint_id": None, **extra})


def leverage(slug: str, clip_ms: int) -> float | None:
    """The Scout's leverage (newsroom.scout_rules.Leverage) on the real tracked frames: the largest change of the
    goal-in-8-s head between the moment and LEVERAGE_AFTER_MS later. None when the later frame cannot be built."""
    import numpy as np

    from footage.freeze import to_state
    from footage.from_tracks import moment_from_tracks
    from heads.features import state_features
    from heads.models import GoalIn8sHead
    from newsroom.scout_rules import LEVERAGE_AFTER_MS

    head = GoalIn8sHead()

    def p(m):
        st = to_state(m, seed=1)
        team = np.array([max(int(st.possession[0]), 0)])
        f = state_features(np.asarray(st.S), np.asarray(st.ball_z), np.asarray(st.holder), team,
                           np.array([st.period]), np.array([st.t_ms]), np.array([True]))
        return head.predict(f.assign(poss_team=team))[0]

    m = load(slug, clip_ms)
    base = {k: m[k] for k in ("period", "clock", "score", "home_attacks")}
    try:
        after = moment_from_tracks(slug, clip_ms + LEVERAGE_AFTER_MS,
                                   {**base, "t_ms": m["t_ms"] + LEVERAGE_AFTER_MS, "actual": None, "players": [],
                                    "ball": {k: m["ball"].get(k) for k in ("x", "y", "image")} | {"holder": None}})
    except (LookupError, FileNotFoundError, KeyError):
        return None
    return round(float(np.abs(p(after) - p(m)).max()), 4)


async def run_moment(deps, f: dict, cache, ros: dict) -> None:
    from newsroom.cuebus import CueBus
    from newsroom.executors.base import trace_id_for
    from newsroom.executors.director import DirectorExecutor
    from newsroom.executors.factcheck import FactCheckExecutor
    from newsroom.executors.narrator import NarratorExecutor
    from newsroom.executors.tactician import TacticianExecutor
    from newsroom.messages import Moment, RolloutDone

    m = load(f["slug"], f["clip_ms"])
    cf = cache.read(cache.find(moment_id=f["moment_id"], producer="rollout")[0])
    holder = m["ball"]["holder"]
    team = next(p["team"] for p in m["players"] if p.get("label") == holder)
    actor = cf["actual"]["actor"]
    moment = Moment(moment_id=f["moment_id"], match_id=m["match_id"], t_ms=m["t_ms"], clock=m["clock"],
                    period=m["period"], kind="big_chance", leverage=f.get("leverage"), team=team,
                    players=[p for p in (actor, cf["alternative"].get("target")) if p and p.startswith("p_")],
                    evidence_event_ids=cf["evidence_event_ids"], selected_by="producer", clip_ms=f["clip_ms"])
    deps.bb.put("moments", moment.model_dump())
    deps.bb.put("counterfactuals", cf)
    run_id = f"run_{m['match_id']}_{f['moment_id']}"
    env = RolloutDone(run_id=run_id, branch="explained", moment=moment, agent_path=list(PRECOMPUTED),
                      trace_id=trace_id_for(run_id), alternatives=[cf["alternative"]], counterfactual=cf,
                      decision={"t_ms": cf["t_ms"], "actor": actor, "actor_name": ros["names"].get(actor),
                                "team": team, "actual": cf["actual"], "anchor_event_id":
                                (cf["evidence_event_ids"] or [None])[0]})
    _trace(deps.bb, env, "ingest", "ok", note="real-clip moment from the frozen frame (tracking)")
    _trace(deps.bb, env, "scout", "routed", note="producer-selected real-clip moment")
    _trace(deps.bb, env, "proposer", "ok", note="alternative chosen in the precompute review", model="review")
    _trace(deps.bb, env, "rollout", "ok", model=cf["engine"], note=f"{cf['n']} worlds x {cf['horizon_s']:.0f} s, "
           f"seed {cf['seed']} (precomputed)", counterfactual_id=cf["counterfactual_id"])
    steps = [TacticianExecutor("tactician", deps), NarratorExecutor("narrator", deps),
             FactCheckExecutor("factcheck", deps), DirectorExecutor("director", deps), CueBus("cuebus", deps)]
    handlers = ["explain", "narrate", "check", "direct", "publish"]
    msg = env
    for ex, h in zip(steps, handlers, strict=True):
        ctx = Ctx()
        await getattr(ex, h)(msg, ctx)
        if not ctx.sent:
            break
        msg = ctx.sent[0]


async def run_fourth_official(deps, slug: str, cache) -> None:
    from newsroom.cuebus import CueBus
    from newsroom.executors.base import trace_id_for
    from newsroom.executors.director import DirectorExecutor
    from newsroom.messages import Draft, Moment

    entries = cache.find(producer="fourth_official", version="footage_772400")
    if not entries:
        return
    cue = cache.read(entries[0])
    beat = json.loads((clip_dir(slug) / "cache" / "v3" / "fourth_official_772400.json").read_text())["result"]
    moment = Moment(moment_id="mo_00002", match_id=cue["match_id"], t_ms=cue["t_in_ms"], clock=cue["clock"],
                    period=cue["period"], kind="foul", players=[beat["fouler"]["pid"], beat["fouled"]["pid"]],
                    evidence_event_ids=[beat["foul_event_id"]], selected_by="producer", clip_ms=beat["clip_ms"])
    deps.bb.put("moments", moment.model_dump())
    run_id = f"run_{cue['match_id']}_mo_00002"
    draft = Draft(run_id=run_id, branch="referee", moment=moment, agent_path=["ingest", "scout", "fourth_official"],
                  trace_id=trace_id_for(run_id), kind="fourth_official", layer="referee_line",
                  headline=cue["text"]["headline"], body=cue["text"]["body"], why=cue["explain"]["why"],
                  claims=cue["explain"]["claims"], graphics=cue["graphics"], verified=True, checked=True,
                  model=beat["caption"]["model"], prompt_version=beat["caption"]["prompt_version"])
    _trace(deps.bb, draft, "fourth_official", "ok", model="rules (tracking)",
           note=f"closing speed {beat['closing_speed_kmh']} km/h, contact outside the box (precomputed ruling)")
    for ex, h in ((DirectorExecutor("director", deps), "direct"), (CueBus("cuebus", deps), "publish")):
        ctx = Ctx()
        await getattr(ex, h)(draft, ctx)
        if not ctx.sent:
            break
        draft = ctx.sent[0]


async def run_recap(deps, slug: str, cache) -> None:
    """The reviewed full-time recap (footage.recap_beat + insights) through the Director, which holds it for the
    producer: the request is written to `requests` as the worker does (newsroom.resume.publish_requests)."""
    from newsroom.executors.base import trace_id_for
    from newsroom.executors.director import DirectorExecutor
    from newsroom.messages import Draft, Moment

    path = clip_dir(slug) / "cache" / "v3"
    files = sorted(path.glob("recap_*.json"))
    if not files:
        return
    beat = json.loads(files[0].read_text())["result"]
    cap = beat.get("caption")
    if not cap:
        raise SystemExit(f"{files[0].name} has no reviewed caption: run footage.insights first")
    moment = Moment(moment_id="mo_00009", match_id=beat["match_id"], t_ms=beat["t_ms"], clock=beat["clock"],
                    period=2, kind="period_end", players=[g["pid"] for g in beat["goals"] if g.get("pid")],
                    evidence_event_ids=[g["event_id"] for g in beat["goals"]], clip_ms=beat["clip_ms"])
    deps.bb.put("moments", moment.model_dump())
    run_id = f"run_{beat['match_id']}_mo_00009"
    draft = Draft(run_id=run_id, branch="recap", moment=moment, agent_path=["ingest", "scout", "recap"],
                  trace_id=trace_id_for(run_id), kind="recap", layer="recap_card", headline=cap["headline"],
                  body=cap["why"], why=cap["why"], claims=cap["claims"], verified=True, checked=True,
                  explanation={"cards": [{"clock": g["clock"], "name": g["name"], "team": g["team"],
                                          "score_after": g["score_after"]} for g in beat["goals"]]},
                  model=cap["model"], prompt_version=cap["prompt_version"])
    _trace(deps.bb, draft, "recap", "ok", model=cap["model"], note="full-time recap (reviewed Argon caption)")
    ctx = Ctx()
    await DirectorExecutor("director", deps).direct(draft, ctx)
    for i, req in enumerate(ctx.requests):
        rid = f"req_{beat['match_id']}_recap_{i}"
        deps.bb.put("requests", {"id": rid, "request_id": rid, "match_id": beat["match_id"],
                                 "moment_id": moment.moment_id, "run_id": run_id, "checkpoint_id": None,
                                 "cue": req.cue, "status": "waiting", "t_ms": req.cue["t_in_ms"]})


STEP_MS = 300          # replay timing: each trace row this long after the previous one, the cue after the last


def write_sqlite(slug: str, out: list[dict], evidence_lines: list[str], path) -> int:
    """One blackboard sqlite per clip in the api's shapes, docs timed on the match clock."""
    from blackboard import SqliteBlackboard

    path.unlink(missing_ok=True)
    bb = SqliteBlackboard(path)
    teams = json.loads((clip_dir(slug) / "teams.json").read_text())["teams"] if (clip_dir(slug) /
                                                                                  "teams.json").exists() else []
    n = 0
    for line in evidence_lines:
        doc = json.loads(line)
        coll = doc.pop("_collection")
        if coll == "events" and doc["type"] == "match_metadata" and len(teams) == 2:
            doc["attrs"]["kits"] = {"home": teams[0]["kit_rgb"], "away": teams[1]["kit_rgb"]}
        if coll == "counterfactuals":
            continue                                   # the run's own counterfactual docs come from the stream
        bb.put(coll, doc)
        n += 1
    for beat_file in ("fourth_official_772400.json", "recap_*.json"):   # facts the on-screen cues cite
        for f in (clip_dir(slug) / "cache" / "v3").glob(beat_file):
            for fact in (json.loads(f.read_text())["result"].get("caption") or {}).get("facts", []):
                bb.put("facts", fact)
                n += 1
    fo = clip_dir(slug) / "cache" / "fourth_official" / "evidence_772400.jsonl"
    if fo.exists():
        for line in fo.read_text().splitlines():
            doc = json.loads(line)
            if doc.pop("_collection") == "facts":
                bb.put("facts", doc)
                n += 1
    for rec in out:
        bb.put(rec["collection"], rec["doc"])
        n += 1
    bb.close()
    return n


def run(slug: str) -> dict:
    from blackboard import SqliteBlackboard
    from footage.featured import open_cache, roster
    from newsroom.executors.base import Deps

    cache = open_cache(slug)
    match_id = CLIPS[slug]["match_id"]
    featured = [f for f in load_config()["featured"] if f["slug"] == slug]
    raw = SqliteBlackboard(":memory:")
    ev = next(e for e in cache.find(producer="evidence") if e["path"] == "evidence.jsonl")
    for line in (cache.cache_dir / ev["path"]).read_text().splitlines():
        if line.strip():
            doc = json.loads(line)
            raw.put(doc.pop("_collection"), doc)
    bb = Recording(raw, None)
    ros = roster(slug)
    for f in featured:
        exp_entry = cache.find(moment_id=f["moment_id"], producer="explanation", version="explanation@reviewed")[0]
        line_entry = cache.find(moment_id=f["moment_id"], producer="narrator", version="footage_line@1")[0]
        line = cache.read(line_entry)["json"]
        llm = CachedAnswers(cache.read(exp_entry), line, exp_entry.get("model") or "gemini-4-argon",
                            {"explanation": exp_entry["key"], "line": line_entry["key"]})
        deps = Deps(bb=bb, llm=llm, rollout=EvidenceTools(raw), mode="replay",
                    state={"tactician_prompt": "tactician_footage@1"})
        f = {**f, "leverage": leverage(slug, f["clip_ms"])}
        asyncio.run(run_moment(deps, f, cache, ros))
    asyncio.run(run_fourth_official(Deps(bb=bb, mode="replay"), slug, cache))
    asyncio.run(run_recap(Deps(bb=bb, mode="replay"), slug, cache))
    t0 = {r["doc"]["moment_id"]: (r["doc"]["t_ms"], r["doc"]["clip_ms"]) for r in bb.log if r["collection"] == "moments"}
    out, step = [], {}
    for i, rec in enumerate(bb.log):     # replay timing: moment at its t_ms, traces after it, the cue after them
        doc = dict(rec["doc"])
        mid = doc.get("moment_id")
        base = t0[mid][0] if mid in t0 else rec["t_ms"]
        if rec["collection"] == "traces":
            step[mid] = step.get(mid, 0) + 1
            doc["t_ms"] = base + STEP_MS * step[mid]
        elif rec["collection"] == "cues":
            show = doc["t_out_ms"] - doc["t_in_ms"]
            doc["t_in_ms"] = max(doc["t_in_ms"], base + STEP_MS * (step.get(mid, 0) + 1))
            doc["t_out_ms"] = doc["t_in_ms"] + show
        elif rec["collection"] == "requests":
            doc["t_ms"] = base + STEP_MS * (step.get(mid, 0) + 1)
        t = doc["t_in_ms"] if rec["collection"] == "cues" else doc.get("t_ms", base)
        clip_ms = t0[mid][1] + (t - t0[mid][0]) if mid in t0 and t is not None else None
        out.append({"seq": i, "clip_ms": clip_ms, "t_ms": t, "collection": rec["collection"], "doc": doc})
    path = cache.cache_dir / "studio" / "stream.jsonl"
    path.parent.mkdir(exist_ok=True)
    path.write_text("".join(json.dumps(r, separators=(",", ":"), ensure_ascii=False) + "\n" for r in out))
    raw.close()
    evidence_lines = [line for line in (cache.cache_dir / ev["path"]).read_text().splitlines() if line.strip()]
    n_docs = write_sqlite(slug, out, evidence_lines, cache.cache_dir / "studio" / "blackboard.sqlite")
    cues = [r["doc"] for r in out if r["collection"] == "cues"]
    return {"slug": slug, "match_id": match_id, "lines": len(out), "cues": [(c["cue_id"], c["kind"], c["text"]["headline"],
            c["verified"]) for c in cues], "traces": sum(r["collection"] == "traces" for r in out),
            "path": str(path.relative_to(ROOT)), "sqlite_docs": n_docs,
            "requests": [(r["doc"]["request_id"], r["doc"]["cue"]["kind"], r["t_ms"]) for r in out
                         if r["collection"] == "requests"]}


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "packages"))
    for s in sys.argv[1:] or [f["slug"] for f in load_config()["featured"]]:
        print(json.dumps(run(s), indent=1, ensure_ascii=False))
