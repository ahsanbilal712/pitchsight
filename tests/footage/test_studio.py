"""Real-clip studio replay, option (c) (video v3): the real executors over a real-clip moment from the cache."""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from footage.studio import run

ROOT = Path(__file__).resolve().parents[2]


def test_real_executors_give_a_verified_cue_with_only_real_names(restore_clip_cache):
    restore_clip_cache("liverpool-mancity-2526")
    with ThreadPoolExecutor(1) as pool:            # run() uses asyncio.run: off the main thread (Playwright loop)
        out = pool.submit(run, "liverpool-mancity-2526").result()
    assert [c[1:] for c in out["cues"]] == [("sliding_doors", "Szoboszlai: shot 1.1%, pass 3.3% (goal in 10 s)", True)]
    lines = [json.loads(line) for line in (ROOT / out["path"]).read_text().splitlines()]
    execs = [r["doc"]["executor"] for r in lines if r["collection"] == "traces" and r["doc"]["moment_id"] == "mo_00001"]
    assert execs == ["ingest", "scout", "proposer", "rollout", "tactician", "narrator", "factcheck", "director",
                     "cuebus"]
    exp = next(r["doc"] for r in lines if r["collection"] == "explanations")
    cue = next(r["doc"] for r in lines if r["collection"] == "cues")
    assert exp["prompt_version"] == "insight_footage@4" and exp["counterfactual_id"] is None      # video v4
    assert cue["graphics"]["bar"] == {"label": "Liverpool goal chance, next 10 s", "from": 0.011, "to": 0.033}
    assert "win" not in json.dumps([r["doc"] for r in lines if r["doc"].get("moment_id") == "mo_00001"]).lower()
    league = json.loads((ROOT / "data" / "league" / "players.json").read_text())
    surnames = {p["name"].split()[-1] for p in league if len(p["name"].split()[-1]) > 3}
    shown = " ".join([cue["text"]["headline"], cue["text"]["body"], cue["explain"]["why"], exp["why"]])
    assert not [s for s in surnames if re.search(rf"\b{re.escape(s)}\b", shown)]
    assert out["requests"] and out["requests"][0][1] == "recap"          # the full-time recap waits for the producer
    held = next(r["doc"] for r in lines if r["collection"] == "requests")
    assert held["status"] == "waiting" and held["cue"]["text"]["headline"] == "Manchester City rally past Liverpool"
    sd = [r for r in lines if r["doc"].get("moment_id") == "mo_00001"]
    assert all(r["clip_ms"] >= 875000 for r in sd)
    ts = [r["t_ms"] for r in sd if r["collection"] in ("traces", "cues")]
    assert ts == sorted(ts) and sd[-1]["collection"] in ("cues", "traces")      # traces, then the cue
