"""Win-probability river over a real clip (video v3): the engine's win-probability head (heads.WinProbHead) on the
real score and clock, every 15 s of match time, with the clip's key moments marked.

    python -m footage.river [<slug>]

The score comes from the T-106 tagged goals; the clock-to-video mapping from the score-bug readings of the tagged
events (piecewise linear). Context features the head also uses (15-minute xT/xG difference, chaos) are not
measured on real footage and are held neutral, so the curve moves with the score and the clock only; the head was
trained on 90-minute synthetic matches, so stoppage time is valued as minute 90. Markers: every goal, red card and
penalty foul, plus the featured Sliding Doors moment (its win-chance swing) and the Oracle window when cached.
No model call. Output: data/footage/<slug>/cache/river/wp_river.json (model_cache tool_result, data under
`result`).
"""

from __future__ import annotations

import json
import sys

import numpy as np

from footage.clips import CLIPS, ROOT, clip_dir, load_config

STEP_MS = 15_000
CHAOS_NEUTRAL = 50.0
MAX_MINUTE = 90.0


def clock(t_ms: int) -> str:
    """mm:ss from t_ms; past 99:59 the minutes take three digits (the event schema's clock caps at 99)."""
    return f"{t_ms // 60000:02d}:{t_ms // 1000 % 60:02d}"


def events(slug: str) -> list[dict]:
    return [json.loads(line) for line in (clip_dir(slug) / "events.jsonl").read_text().splitlines() if line]


def clock_to_clip(evs: list[dict]):
    """Match t_ms -> clip_ms, piecewise linear through the score-bug readings (monotone, outliers dropped)."""
    pts = sorted((e["t_ms"], e["attrs"]["clip_ms"]) for e in evs if e["attrs"].get("clock_source") == "score_bug")
    keep = []
    for t, c in pts:
        if not keep or (t > keep[-1][0] and c > keep[-1][1]):
            keep.append((t, c))
    ts, cs = np.array(keep, float).T

    def f(t_ms: float) -> int:
        if t_ms <= ts[0]:
            return int(cs[0] + (t_ms - ts[0]))
        if t_ms >= ts[-1]:
            return int(cs[-1] + (t_ms - ts[-1]))
        return int(np.interp(t_ms, ts, cs))
    return f


def goals(evs: list[dict]) -> list[dict]:
    """One goal per scoring event (a tagged shot with outcome goal and its goal event are the same goal)."""
    out = []
    for e in sorted((e for e in evs if e["type"] == "goal" or (e["type"] == "shot" and e["outcome"] == "goal")),
                    key=lambda e: e["t_ms"]):
        if out and out[-1]["team"] == e["team"] and e["t_ms"] - out[-1]["t_ms"] <= 30_000:
            continue
        out.append(e)
    return out


def score_at(gs: list[dict], t_ms: int) -> list[int]:
    s = [0, 0]
    for g in gs:
        if g["t_ms"] <= t_ms:
            s[0 if g["team"] == "home" else 1] += 1
    return s


def win_prob(rows: list[tuple[int, float]]) -> np.ndarray:
    """[N, 3] home, draw, away for (score_diff, minute) rows, second half, neutral context."""
    import pandas as pd

    from heads.features import WINPROB_FEATURES
    from rollout.futures import heads

    _, wp = heads()
    df = pd.DataFrame([{"score_diff": d, "minute": min(m, MAX_MINUTE), "period": 2, "red_card_diff": 0,
                        "xt_diff_15": 0.0, "xg_diff_15": 0.0, "chaos": CHAOS_NEUTRAL} for d, m in rows])
    return wp.predict(df[WINPROB_FEATURES])


def run(slug: str = "liverpool-mancity-2526") -> dict:
    from cache.manifest import CacheManifest
    from footage.featured import open_cache

    clip = CLIPS[slug]
    evs = events(slug)
    to_clip = clock_to_clip(evs)
    gs = goals(evs)
    start = (min(e["t_ms"] for e in evs) // 60_000) * 60_000
    end = max(e["t_ms"] for e in evs)
    ts = list(range(start, end + STEP_MS, STEP_MS))
    scores = [score_at(gs, t) for t in ts]
    P = win_prob([(s[0] - s[1], t / 60_000) for s, t in zip(scores, ts, strict=True)])
    samples = [{"t_ms": t, "clock": clock(t), "clip_ms": to_clip(t), "score": s,
                "wp": {"home": round(float(p[0]), 4), "draw": round(float(p[1]), 4), "away": round(float(p[2]), 4)}}
               for t, s, p in zip(ts, scores, P, strict=True)]

    def wp_at(t_ms: int, score: list[int]) -> dict:
        p = win_prob([(score[0] - score[1], t_ms / 60_000)])[0]
        return {"home": round(float(p[0]), 4), "draw": round(float(p[1]), 4), "away": round(float(p[2]), 4)}

    markers = []
    for g in gs:
        before, after = score_at(gs, g["t_ms"] - 1), score_at(gs, g["t_ms"])
        markers.append({"kind": "goal", "t_ms": g["t_ms"], "clock": clock(g["t_ms"]), "clip_ms": g["attrs"]["clip_ms"],
                        "team": g["team"], "player_name": g["attrs"].get("player_name"), "score_after": after,
                        "wp_before": wp_at(g["t_ms"], before), "wp_after": wp_at(g["t_ms"], after),
                        "event_id": g["id"]})
    for e in evs:
        note = (e["attrs"].get("note") or "").lower()
        if e["type"] == "card" and "red" in note:
            markers.append({"kind": "red_card", "t_ms": e["t_ms"], "clock": clock(e["t_ms"]), "clip_ms": e["attrs"]["clip_ms"],
                            "team": e["team"], "player_name": e["attrs"].get("player_name"), "event_id": e["id"]})
        if e["type"] == "foul" and ("in the box" in note or "penalty" in note) and "outside" not in note:
            markers.append({"kind": "penalty_foul", "t_ms": e["t_ms"], "clock": clock(e["t_ms"]),
                            "clip_ms": e["attrs"]["clip_ms"], "team": e["team"],
                            "player_name": e["attrs"].get("player_name"), "event_id": e["id"]})
    manifest = open_cache(slug)
    for f in load_config()["featured"]:
        if f["slug"] != slug:
            continue
        cf = manifest.read(manifest.find(moment_id=f["moment_id"], producer="rollout")[0])
        markers.append({"kind": "sliding_doors", "t_ms": cf["t_ms"], "clock": clock(cf["t_ms"]), "clip_ms": f["clip_ms"], "team": "home",
                        "delta_win_prob_home": cf["delta_win_prob_home"], "counterfactual_id": cf["counterfactual_id"]})
    oracle = manifest.find(producer="oracle")
    if oracle:
        w = manifest.read(oracle[0])["result"]
        markers.append({"kind": "oracle_window", "t_ms": w["samples"][0]["t_ms"], "clock": w["samples"][0]["clock"],
                        "clip_ms": w["start_clip_ms"], "end_clip_ms": w["end_clip_ms"],
                        "peak_p_shot_10s": max(s["p_shot_10s_smoothed"]["home"] for s in w["samples"])})
    markers.sort(key=lambda m: m["t_ms"])
    markers = [m for i, m in enumerate(markers)       # one incident tagged twice (fouler, then fouled player)
               if not any(o["kind"] == m["kind"] and 0 < m["t_ms"] - o["t_ms"] <= 30_000 for o in markers[:i])]
    doc = {"schema_version": "1.0.0", "match_id": clip["match_id"], "slug": slug, "home": clip["home"],
           "away": clip["away"], "step_ms": STEP_MS, "model": "heads.WinProbHead (engine corpus)",
           "notes": "score and clock only (xT/xG and chaos held neutral); stoppage time valued as minute 90",
           "samples": samples, "markers": markers}
    seed = int(clip["match_id"][2:])
    manifest.add(CacheManifest.key(clip["match_id"], None, "river", "wp_river@1", None, seed), "analytics",
                 {"$schema": "model_cache.schema.json", "schema_version": "1.0.0", "record": "tool_result",
                  "result": doc}, "river/wp_river.json", producer="river", version="wp_river@1", seed=seed)
    manifest.save()
    write_v3(slug, doc, CacheManifest.key(clip["match_id"], None, "river", "wp_river@1", None, seed))
    return doc


def _label(m: dict) -> str:
    who = (m.get("player_name") or "").split()[-1:] or [""]
    if m["kind"] == "goal":
        return f"{who[0]} {m['score_after'][0]}-{m['score_after'][1]}".strip()
    if m["kind"] == "red_card":
        return f"{who[0]} red card".strip()
    if m["kind"] == "penalty_foul":
        return "Penalty"
    if m["kind"] == "sliding_doors":
        return f"Sliding Doors {m['delta_win_prob_home'] * 100:+.0f} points"
    return f"Oracle {m['peak_p_shot_10s'] * 100:.0f}% shot chance"


def write_v3(slug: str, doc: dict, source_key: str) -> str:
    """Track C's win_prob_river beat (shared notes, beat 7)."""
    from footage.v3 import write_beat

    events = [{"clip_ms": m["clip_ms"], "clock": m["clock"], "label": _label(m), "kind": m["kind"],
               "source": m.get("event_id") or m.get("counterfactual_id") or "oracle/window_867000.json"}
              for m in doc["markers"]]
    result = {"home": doc["home"], "away": doc["away"], "engine": "heads.WinProbHead (deterministic, no rollouts)",
              "n": None, "source": source_key, "note": doc["notes"],
              "series": [{"clip_ms": s["clip_ms"], "clock": s["clock"], **s["wp"]} for s in doc["samples"]],
              "events": events}
    return write_beat(slug, "win_prob_river", doc["samples"][0]["clip_ms"], result)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "packages"))
    d = run(*(sys.argv[1:2]))
    for m in d["markers"]:
        print(m["clock"], m["kind"], m.get("player_name"), m.get("team"), m.get("score_after", ""),
              {k: m[k] for k in ("wp_before", "wp_after", "delta_win_prob_home", "peak_p_shot_10s") if k in m})
    print(len(d["samples"]), "samples", d["samples"][0]["clock"], "->", d["samples"][-1]["clock"])
