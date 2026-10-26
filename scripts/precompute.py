"""Golden-match precompute into the replay cache.

    python scripts/precompute.py --seed 4242 --mode batch --stages fourth_official
    python scripts/precompute.py --seed 4242 --mode batch --stages analytics,moments,counterfactuals

Every stage writes files under data/matches/<seed>/cache/ and indexes them in cache/manifest.json (CacheManifest)
with their SHA-256. Stages are idempotent: re-running replaces their entries. `--mode live` is accepted for
the CLI contract (later stages call models); the code-only stages behave the same in both modes. Later stages add
stages to STAGES: analytics, moments, counterfactuals, model calls, oracle, dugout,
decision_index, hand review.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from cache.manifest import CacheManifest  # noqa: E402
from cache.precompute_models import (  # noqa: E402
    NEWSROOM_STAGES,
    stage_cue_stream,
    stage_newsroom,
    stage_recap,
    stage_replay_check,
)

RULES_VERSION = "rules1"


def load_match(seed: int):
    from physics.window import TrackingWindow
    d = ROOT / "data" / "matches" / str(seed)
    events = [json.loads(line) for line in (d / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    return d, events, TrackingWindow.load(d)


def open_manifest(match_dir: Path) -> CacheManifest:
    cache = match_dir / "cache"
    if (cache / "manifest.json").exists():
        return CacheManifest.load(cache)
    return CacheManifest.new(match_dir, cache)


# ---------------------------------------------------------------------------------------------------- stages
def stage_fourth_official(seed: int, manifest: CacheManifest, events: list[dict], window, args) -> dict:
    """A referee_line cue for every offside, foul and card; keyed by the referee event id."""
    from newsroom.executors.fourth_official import REFEREE, rule_event

    match_id = events[0]["match_id"]
    stale = [e["key"] for e in manifest.entries if e.get("producer") == "fourth_official"]
    manifest.data["entries"] = [e for e in manifest.entries if e["key"] not in stale]
    counts, missing = {k: 0 for k in REFEREE}, []
    for ev in events:
        if ev["type"] not in REFEREE:
            continue
        cue = rule_event(ev, events, window, match_id)
        if cue is None:
            missing.append(ev["id"])
            continue
        key = CacheManifest.key(match_id, ev["id"], "fourth_official", RULES_VERSION, None, seed)
        manifest.add(key, "fourth_official", cue, f"fourth_official/{cue['cue_id']}.json", moment_id=None,
                     producer="fourth_official", version=RULES_VERSION, model=None, seed=seed,
                     simulated_latency_ms=5)
        counts[ev["type"]] += 1
    if missing:
        raise SystemExit(f"fourth_official: could not rebuild the geometry for {missing}")
    return counts


def gate_engine() -> str:
    """The engine the day-4 gate chose (packages/policy/artifacts/gate.json); required for model stages."""
    path = ROOT / "packages" / "policy" / "artifacts" / "gate.json"
    if not path.exists():
        raise SystemExit(f"{path} is missing: run python -m policy.evaluate first")
    return json.loads(path.read_text(encoding="utf-8"))["engine"]


def _oracle_chunk(args: tuple[int, list[int], int, float, str]) -> list[dict]:
    from rollout import MatchRef
    from rollout.oracle import oracle

    seed, times, n, horizon_s, engine = args
    match = MatchRef(seed, match_dir=ROOT / "data" / "matches" / str(seed))
    return [oracle(match, t, n=n, horizon_s=horizon_s, seed=seed, engine=engine).to_doc(match.match_id) for t in times]


ORACLE_EVERY_MS, ORACLE_N, ORACLE_HORIZON_S = 2000, 200, 8.0


def stage_oracle(seed: int, manifest: CacheManifest, events: list[dict], window, args) -> dict:
    """Oracle forecasts every 2 s of match time at n = 200: one analytics file for the whole match."""
    from multiprocessing import Pool

    engine = gate_engine()
    times = [t for t in range(ORACLE_EVERY_MS, int(window.t_ms[-1]) + 1, ORACLE_EVERY_MS)]
    chunks = [times[i::args.workers] for i in range(args.workers)]
    with Pool(args.workers) as pool:
        parts = pool.map(_oracle_chunk, [(seed, sorted(c), ORACLE_N, ORACLE_HORIZON_S, engine) for c in chunks])
    docs = sorted((d for p in parts for d in p), key=lambda d: d["t_ms"])
    match_id = events[0]["match_id"]
    key = CacheManifest.key(match_id, None, "oracle", "oracle@1", engine, seed)
    manifest.add(key, "analytics", {"$schema": "analytics.schema.json", "schema_version": "1.0.0", "producer": "oracle",
                                    "match_id": match_id,
                                    "every_ms": ORACLE_EVERY_MS, "n": ORACLE_N, "horizon_s": ORACLE_HORIZON_S,
                                    "engine": engine, "seed": seed, "forecasts": docs},
                 "analytics/oracle.json", producer="oracle", version="oracle@1", model=engine, seed=seed,
                 simulated_latency_ms=300)
    best = max(docs, key=lambda d: max(d["p_shot_10s"].values()))
    return {"forecasts": len(docs), "max_p_shot": max(best["p_shot_10s"].values()), "at_ms": best["t_ms"],
            "above_0.30": sum(1 for d in docs if max(d["p_shot_10s"].values()) >= 0.30)}


DUGOUT_T_MS, DUGOUT_N, DUGOUT_HORIZON_S = 3_600_000, 100, 90.0


def stage_dugout(seed: int, manifest: CacheManifest, events: list[dict], window, args) -> dict:
    """Dugout options at 60:00 for both teams. Style changes act over minutes, so the scripted engine runs the
    longest horizon the counterfactual schema allows (90 s); learned engines are capped at 8 s."""
    from dataclasses import asdict

    from rollout import MatchRef
    from rollout.dugout import dugout, top_options

    match = MatchRef(seed, match_dir=ROOT / "data" / "matches" / str(seed))
    match_id = events[0]["match_id"]
    out = {}
    manifest.data["entries"] = [e for e in manifest.entries if e.get("producer") != "dugout"]
    for team in ("home", "away"):
        options = dugout(match, DUGOUT_T_MS, team, n=DUGOUT_N, horizon_s=DUGOUT_HORIZON_S, seed=seed)
        top = [asdict(o) for o in top_options(options)]
        key = CacheManifest.key(match_id, None, "dugout", f"dugout@1-{team}", "scripted_v1", seed)
        manifest.add(key, "analytics", {"$schema": "analytics.schema.json", "schema_version": "1.0.0",
                                        "producer": "dugout", "match_id": match_id,
                                        "t_ms": DUGOUT_T_MS, "team": team, "n": DUGOUT_N,
                                        "horizon_s": DUGOUT_HORIZON_S, "seed": seed, "engine": "scripted_v1",
                                        "options": top, "all_options": [asdict(o) for o in options]},
                     f"dugout/dugout_{team}_{DUGOUT_T_MS}.json", producer="dugout", version=f"dugout@1-{team}",
                     model="scripted_v1", seed=seed, simulated_latency_ms=800)
        out[team] = [(o["label"], o["delta_win_prob"]) for o in top]
    return out


def stage_analytics(seed: int, manifest: CacheManifest, events: list[dict], window, args) -> dict:
    """Indices, chaos and the game state for every 100 ms frame -> analytics/frames.npz."""
    import io

    import numpy as np

    from physics import StateMachine, indices

    t = window.t_ms
    keys = ("control_home", "pressure_home", "pressure_away", "tempo", "turnover_rate", "turnovers_60s",
            "transition_share", "contested_frac", "chaos")
    cols = {k: np.zeros(len(t), dtype=np.float32) for k in keys}
    state = np.zeros(len(t), dtype=np.int8)
    names = ("Settled", "Transitional", "Chaotic")
    sm = StateMachine()
    for i, ti in enumerate(t):
        ti = int(ti)
        ix = indices(window.slice(max(0, ti - 60_000), ti), [e for e in events if ti - 600_000 <= e["t_ms"] <= ti])
        for k in keys:
            cols[k][i] = ix[k]
        sm.update(ix["chaos"], ti)
        state[i] = names.index(sm.state)
    buf = io.BytesIO()
    np.savez_compressed(buf, t_ms=t, state=state, state_names=np.array(names), **cols)
    match_id = events[0]["match_id"]
    key = CacheManifest.key(match_id, None, "analytics", "frames@1", None, seed)
    manifest.add(key, "analytics", buf.getvalue(), "analytics/frames.npz", producer="analytics", version="frames@1",
                 seed=seed)
    changes = int(np.sum(state[1:] != state[:-1]))
    return {"frames": int(len(t)), "state_changes": changes, "chaotic_share": round(float(np.mean(state == 2)), 3)}


def stage_moments(seed: int, manifest: CacheManifest, events: list[dict], window, args) -> dict:
    """Scout over the whole match (newsroom.scout_rules) -> moments.jsonl with mo_ ids, and a pitch-control snapshot
    (pc_<t/100>.npz + JSON stub) at every moment."""
    import io

    import numpy as np

    from newsroom.scout_rules import detect_match
    from physics.pitch_control import contested_fraction, pitch_control, zones
    from physics.window import home_dir

    match_dir = ROOT / "data" / "matches" / str(seed)
    match_id = events[0]["match_id"]
    moments = detect_match(match_dir)
    for i, m in enumerate(moments, 1):
        m["moment_id"] = f"mo_{i:05d}"
    body = "".join(json.dumps(m, sort_keys=True) + "\n" for m in moments).encode()
    manifest.data["entries"] = [e for e in manifest.entries if e.get("producer") not in ("scout", "pitch_control")]
    manifest.add(CacheManifest.key(match_id, None, "scout", "scout@1", None, seed), "analytics", body,
                 "moments.jsonl", producer="scout", version="scout@1", seed=seed)
    snaps = set()
    for m in moments:
        t = int(m["t_ms"])
        sid = f"pc_{t // 100:06d}"
        if sid in snaps:
            continue
        snaps.add(sid)
        i = window.index_at(t)
        pc = pitch_control(window.S[i].astype(np.float64))
        stub = {"snapshot_id": sid, "match_id": match_id, "t_ms": t, "grid_path": f"pitch_control/{sid}.npz",
                "home_share": round(float(pc.mean()), 4), "contested_frac": round(contested_fraction(pc), 4),
                "zones": {k: round(v, 4) for k, v in zones(pc, home_dir(int(window.period[i])) > 0).items()}}
        buf = io.BytesIO()       # the JSON stub travels inside the .npz (no schema covers a pitch_control .json)
        np.savez_compressed(buf, grid=pc.astype(np.float16), stub=np.array(json.dumps(stub, sort_keys=True)))
        manifest.add(CacheManifest.key(match_id, m["moment_id"], "pitch_control", "pc@1", None, seed), "pitch_control",
                     buf.getvalue(), f"pitch_control/{sid}.npz", moment_id=m["moment_id"], producer="pitch_control",
                     version="pc@1", seed=seed)
    kinds = {}
    for m in moments:
        kinds[m["kind"]] = kinds.get(m["kind"], 0) + 1
    return {"moments": len(moments), "snapshots": len(snaps), "kinds": kinds}


CF_N, CF_HORIZON_S = 200, 8.0


def stage_counterfactuals(seed: int, manifest: CacheManifest, events: list[dict], window, args) -> dict:
    """sliding_doors for every explained moment: the rule proposer's alternatives at the
    moment's decision point, n = 200, 8 s, seed, engine from gate.json -> counterfactuals/cf_*.json."""
    from blackboard import SqliteBlackboard
    from kickoff import BranchError
    from mcp_server.tools_core import MatchStore, _options
    from newsroom.decision import attach_options, decision_point, proposer_rule
    from newsroom.scout_rules import is_explained
    from rollout import MatchRef, sliding_doors

    engine = gate_engine()
    match_dir = ROOT / "data" / "matches" / str(seed)
    match_id = events[0]["match_id"]
    entry = manifest.find(producer="scout")
    if not entry:
        raise SystemExit("run the moments stage first")
    lines = (manifest.cache_dir / entry[0]["path"]).read_text(encoding="utf-8").splitlines()
    moments = [json.loads(line) for line in lines if line.strip()]
    explained = [m for m in moments if is_explained(m)]
    runtime = ROOT / "data" / "runtime" / "precompute"
    runtime.mkdir(parents=True, exist_ok=True)
    store = MatchStore(SqliteBlackboard(runtime / f"bb_{seed}.sqlite"), runtime_dir=runtime)
    ref = MatchRef(seed, match_dir=match_dir)
    # replace this stage's own entries; keep the extra alternatives the model stage adds (counterfactuals/x_*.json)
    manifest.data["entries"] = [e for e in manifest.entries if e.get("producer") != "rollout"
                                or e["path"].startswith("counterfactuals/x_")]
    made, skipped, n_cf = 0, [], 0
    for m in sorted(explained, key=lambda m: m["t_ms"]):
        dec = decision_point(store, m)
        if dec is None:
            skipped.append(m["moment_id"])
            continue
        dec = attach_options(dec, _options(store, store.match(match_id), dec["t_ms"]))
        for alt in proposer_rule(dec):
            n_cf += 1
            cf_id = f"cf_{n_cf:06d}"
            try:
                cf = sliding_doors(ref, dec["t_ms"], {k: alt[k] for k in ("kind", "actor", "target")}, n=CF_N,
                                   horizon_s=CF_HORIZON_S, seed=seed, engine=engine, counterfactual_id=cf_id,
                                   moment_id=m["moment_id"])
            except BranchError:
                n_cf -= 1
                continue
            key = CacheManifest.key(match_id, m["moment_id"], "rollout", f"rollout@{engine}", engine, seed) + \
                f"/{alt['kind']}-{alt.get('target') or 'none'}"
            manifest.add(key, "counterfactual", cf, f"counterfactuals/{cf_id}.json", moment_id=m["moment_id"],
                         producer="rollout", version=f"rollout@{engine}", model=engine, seed=seed,
                         simulated_latency_ms=1200)
            made += 1
    return {"explained_moments": len(explained), "counterfactuals": made, "skipped_no_decision": skipped,
            "engine": engine}


ORACLE_BAND = (0.30, 0.60)          # oracle_min_p_shot (budgets.yaml) up to a forecast worth calling a forecast
KILL_BY_MS, KILL_AFTER_MS = 2_650_000, 3_000


def _clock(t_ms: int) -> str:
    s = int(t_ms) // 1000
    return f"{s // 60:02d}:{s % 60:02d}"


def stage_storyboard(seed: int, manifest: CacheManifest, events: list[dict], window, args) -> dict:
    """packages/demo/golden_moments.yaml: the storyboard beats chosen from the cache. Sliding
    Doors = the home team's counterfactual with the largest win-probability gain whose alternative the engine gives
    >= 5%, preferring "shot, but the pass was on"; Fourth Official = every offside, then fouls with a card; Oracle =
    the highest forecast in 0.30-0.60 that the match then confirms with a shot by that side within 10 s (home
    preferred); Dugout = 60:00, the home team; kill = 3 s after the last explained decision moment before 44:10 whose
    cue survives the Director's same-kind dedupe, so the worker dies while that run is in flight."""
    import yaml

    from newsroom.scout_rules import is_explained

    cfs = [manifest.read(e) for e in manifest.find(producer="rollout")]
    home = [c for c in cfs if (c["alternative"].get("policy_prob") or 0) >= 0.05
            and c["actual"]["actor"] in _side_players(events, "home")]
    if not home:
        raise SystemExit("storyboard: no home counterfactual with policy_prob >= 0.05")
    shots = [c for c in home if c["actual"]["kind"] == "shoot" and c["alternative"]["kind"] == "pass"
             and c["delta_win_prob_home"] > 0]
    sd = max(shots or home, key=lambda c: c["delta_win_prob_home"])
    by_id = {e["id"]: e for e in events}
    fo = []
    for entry in sorted(manifest.find(producer="fourth_official"), key=lambda e: e["key"]):
        cue = manifest.read(entry)
        ev = by_id[entry["key"].split("/")[1]]
        if ev["type"] == "offside" or (ev["type"] == "card"):
            fo.append({"clock": _clock(ev["t_ms"]), "t_ms": int(ev["t_ms"]), "cue_kind": ev["type"],
                       "event_id": ev["id"], "cue_id": cue["cue_id"]})
    fo.sort(key=lambda r: (r["cue_kind"] != "offside", r["t_ms"]))
    oracle_doc = manifest.read(manifest.find(producer="oracle")[0])
    shots = [(e["t_ms"], e["team"]) for e in events if e["type"] == "shot"]
    called = [(f, side) for f in oracle_doc["forecasts"] for side, p in f["p_shot_10s"].items()
              if ORACLE_BAND[0] <= p <= ORACLE_BAND[1]
              and any(f["t_ms"] < t <= f["t_ms"] + 10_000 and s == side for t, s in shots)]
    if not called:
        raise SystemExit("storyboard: no Oracle forecast in the band that the match confirmed")
    best, side = max(called, key=lambda c: (c[1] == "home", c[0]["p_shot_10s"][c[1]]))
    lines = (manifest.cache_dir / manifest.find(producer="scout")[0]["path"]).read_text(encoding="utf-8").splitlines()
    moments = [json.loads(line) for line in lines if line.strip()]
    kill = _kill_moment(moments, is_explained)
    dug = manifest.read(manifest.find(producer="dugout", version="dugout@1-home")[0])
    out = {
        "sliding_doors": {"clock": _clock(sd["t_ms"] + 100), "t_ms": int(sd["t_ms"]) + 100, "branch_t_ms": int(sd["t_ms"]),
                          "moment_id": sd["moment_id"], "counterfactual_id": sd["counterfactual_id"],
                          "actor": sd["actual"]["actor"], "actual_kind": sd["actual"]["kind"],
                          "alternative_kind": sd["alternative"]["kind"],
                          "alternative_target": sd["alternative"]["target"],
                          "delta_win_prob_home": sd["delta_win_prob_home"],
                          "policy_prob": sd["alternative"]["policy_prob"], "engine": sd["engine"]},
        "fourth_official": fo,
        "oracle": {"clock": _clock(best["t_ms"]), "t_ms": int(best["t_ms"]), "team": side,
                   "p_shot_10s": best["p_shot_10s"][side], "likely_shooter": best["likely_shooter"][side],
                   "likely_zone": best["likely_zone"][side]},
        "dugout": {"clock": _clock(dug["t_ms"]), "t_ms": int(dug["t_ms"]), "team": "home",
                   "recommendation": dug["options"][0]["label"]},
        "kill": {"clock": _clock(kill["t_ms"] + KILL_AFTER_MS), "t_ms": int(kill["t_ms"]) + KILL_AFTER_MS,
                 "moment_id": kill["moment_id"], "moment_clock": kill["clock"], "target": "newsroom"},
    }
    header = ("# Written by scripts/precompute.py --stages storyboard. Storyboard beats of the golden match,\n"
              "# chosen from the cache; the demo script and shot list reference them as @key (packages/demo/clocks.py).\n")
    path = ROOT / "packages" / "demo" / "golden_moments.yaml"
    path.write_text(header + yaml.safe_dump(out, sort_keys=False, width=110), encoding="utf-8")
    return {k: (v["clock"] if isinstance(v, dict) else [x["clock"] for x in v]) for k, v in out.items()}


def _kill_moment(moments: list[dict], is_explained) -> dict:
    """The last explained decision moment before 44:10 whose Sliding Doors cue reaches the screen: the Director drops
    a cue of the same kind within dedupe_same_kind_window_s of the last one it showed (budgets.yaml), so walk the
    explained decisions in time order keeping the ones that would be shown (a kill on a dropped cue shows nothing)."""
    import yaml
    window_ms = int(yaml.safe_load((ROOT / "config" / "budgets.yaml").read_text())["director"]["hard_rules"]
                    ["dedupe_same_kind_window_s"]) * 1000
    shown, last = [], -10**9
    for m in sorted((m for m in moments if is_explained(m) and m["kind"] == "decision"), key=lambda m: m["t_ms"]):
        if m["t_ms"] - last >= window_ms:
            shown.append(m)
            last = m["t_ms"]
    return max((m for m in shown if m["t_ms"] <= KILL_BY_MS), key=lambda m: m["t_ms"])


def _side_players(events: list[dict], side: str) -> set[str]:
    meta = next(e for e in events if e["type"] == "match_metadata")["attrs"]["lineups"][side]
    subs = {e["attrs"]["player_on"] for e in events if e["type"] == "substitution" and e["team"] == side}
    return set(meta["starting"]) | subs


def _decision_chunk(args: tuple[int, list[dict], str]) -> list[dict]:
    from dataclasses import asdict

    from rollout import MatchRef
    from rollout.decision_index import decision_values

    seed, chunk, engine = args
    match = MatchRef(seed, match_dir=ROOT / "data" / "matches" / str(seed))
    return [asdict(v) for v in decision_values(match, chunk, seed=seed, engine=engine)]


def stage_decision_index(seed: int, manifest: CacheManifest, events: list[dict], window, args) -> dict:
    """A rollout value for every on-ball decision of the match and the per-player Decision Index."""
    from multiprocessing import Pool

    from rollout.decision_index import DECISIONS, HORIZON_S, N, live_values, player_index, spearman

    engine = gate_engine()
    started = time.perf_counter()
    dec = sorted((e for e in events if e["type"] in DECISIONS and e.get("player")), key=lambda e: e["t_ms"])
    k = max(1, args.workers * 3)
    chunks = [dec[i * len(dec) // k:(i + 1) * len(dec) // k] for i in range(k)]
    with Pool(args.workers) as pool:
        values = [v for part in pool.map(_decision_chunk, [(seed, c, engine) for c in chunks]) for v in part]
    values.sort(key=lambda v: v["t_ms"])
    index = player_index([(v["player"], v["value"]) for v in values])
    live = player_index(live_values(events, window))
    rho = spearman(index, live)
    match_id = events[0]["match_id"]
    doc = {"$schema": "analytics.schema.json", "schema_version": "1.0.0", "producer": "decision_index",
           "match_id": match_id, "seed": seed, "engine": engine, "n": N, "horizon_s": HORIZON_S,
           "formula": "value = p_goal(actual) - max p_goal(engine's top-3 other options); index = percentile of the "
                      "player's mean value among players with >= 5 decisions",
           "decisions": values, "players": index, "live_players": live, "spearman_live_vs_rollout": round(rho, 4),
           "minutes": round((time.perf_counter() - started) / 60, 1)}
    key = CacheManifest.key(match_id, None, "decision_index", "decision_index@1", engine, seed)
    manifest.data["entries"] = [e for e in manifest.entries if e.get("producer") != "decision_index"]
    manifest.add(key, "analytics", doc, "analytics/decision_index.json", producer="decision_index",
                 version="decision_index@1", model=engine, seed=seed, simulated_latency_ms=50)
    return {"decisions": len(dec), "valued": len(values), "players": sum(1 for p in index.values() if p["index"] is not None),
            "spearman_live_vs_rollout": round(rho, 3), "minutes": doc["minutes"]}


STAGES = {"decision_index": stage_decision_index, "storyboard": stage_storyboard, "analytics": stage_analytics, "moments": stage_moments, "counterfactuals": stage_counterfactuals,
          "fourth_official": stage_fourth_official, "oracle": stage_oracle, "dugout": stage_dugout,
          **dict.fromkeys(NEWSROOM_STAGES, stage_newsroom),       # model calls (cache/precompute_models.py)
          "recap": stage_recap,                                   # half-time and full-time recaps
          "replay_check": stage_replay_check,                     # replay from the cache, count misses
          "cue_stream": stage_cue_stream}                         # every cached cue, no model needed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="scripts/precompute.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--mode", choices=("batch", "live"), default="batch")
    ap.add_argument("--stages", default="", help=f"comma list of {', '.join(STAGES)}")
    ap.add_argument("--hand-review", type=int, default=0, help="top K moments for hand review")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--bucket", default=None, help="gs:// bucket for Vertex AI batch input/output")
    ap.add_argument("--moments", default=None, help="comma list of moment ids (partial model stages)")
    ap.add_argument("--repair", action="store_true", help="replay_check: cache what no model call is needed for")
    args = ap.parse_args(argv)
    stages = [s for s in args.stages.split(",") if s]
    if args.hand_review:   # export the top moments for hand review (review/<moment_id>.md)
        from cache.review import export_fast_lines, export_review

        match_dir = ROOT / "data" / "matches" / str(args.seed)
        manifest = open_manifest(match_dir)
        written = export_review(manifest, args.hand_review, ROOT / "review") + \
            export_fast_lines(manifest, ROOT / "review")
        print(f"hand review: {len(written)} files in review/")
        if not stages:
            return 0
    if not stages:
        ap.error("--stages is required (or --hand-review N)")
    unknown = [s for s in stages if s not in STAGES]
    if unknown:
        ap.error(f"unknown stage(s) {unknown}; available: {sorted(STAGES)}")
    match_dir, events, window = load_match(args.seed)
    manifest = open_manifest(match_dir)
    for name in stages:
        started = time.perf_counter()
        result = STAGES[name](args.seed, manifest, events, window, args)
        manifest.save()
        print(f"{name}: {json.dumps(result)} in {time.perf_counter() - started:.1f} s")
    problems = manifest.problems(match_dir)
    if problems:
        print("manifest problems:", problems[:5])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
