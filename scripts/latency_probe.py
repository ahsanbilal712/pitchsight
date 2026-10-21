"""Live latency probe (T-032): one explained moment of the golden match through the real processes.

    python scripts/latency_probe.py --moment-t 1419200 [--out data/runtime/latency_probe.json]

Starts `python -m mcp_server` (Streamable HTTP) and `python -m newsroom.worker --mode live` against a fresh
blackboard, warms the MCP server's engine near the moment, writes the Scout's moment for t_ms into the
blackboard and waits for its cue. Prints and saves wall-clock timings: moment written -> cue written, per executor
from the trace rows, and the spend. Model calls are real (Gemini on Vertex AI) and go through SpendGuard.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from api.spend import SpendGuard  # noqa: E402
from blackboard import SqliteBlackboard  # noqa: E402
from newsroom import scout_rules  # noqa: E402


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_port(port: int, timeout: float = 30) -> None:
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.2)
    raise TimeoutError(f"port {port} never opened")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--moment-t", type=int, default=1_419_200)
    ap.add_argument("--match", default="data/matches/4242")
    ap.add_argument("--out", default="data/runtime/latency_probe.json")
    ap.add_argument("--timeout", type=float, default=180)
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="whyline_probe_"))
    env = {**os.environ, "PYTHONPATH": str(ROOT / "packages"), "WHYLINE_BLACKBOARD": str(tmp / "bb.sqlite"),
           "WHYLINE_CHECKPOINT_DIR": str(tmp / "ckpt"), "WHYLINE_LOG": "INFO"}
    port = free_port()
    env["WHYLINE_MCP_PORT"] = str(port)
    env["WHYLINE_MCP_URL"] = f"http://127.0.0.1:{port}/mcp"

    moments = scout_rules.detect_match(ROOT / args.match)
    moment = next(m for m in moments if m["t_ms"] == args.moment_t)
    bb = SqliteBlackboard(tmp / "bb.sqlite")
    guard = SpendGuard()
    spend0 = guard.total
    procs = []
    try:
        procs.append(subprocess.Popen([sys.executable, "-m", "mcp_server"], env=env, cwd=ROOT,
                                      stdout=open(tmp / "mcp.log", "w"), stderr=subprocess.STDOUT))
        wait_port(port)
        from newsroom.decision import decision_point
        from newsroom.tools import McpTools

        async def warm_engine() -> float:
            """Bring the MCP server's engine to just before the moment (a live match is already there)."""
            from mcp_server.tools_core import MatchStore

            store = MatchStore(SqliteBlackboard(tmp / "warm.sqlite"), runtime_dir=tmp)
            d = decision_point(store, moment)
            tools = McpTools(env["WHYLINE_MCP_URL"])
            t0 = time.perf_counter()
            earlier = d["t_ms"] - 30_000
            await tools.call("get_state", {"match_id": moment["match_id"], "t_ms": earlier})
            await tools.call("simulate_counterfactual", {"match_id": moment["match_id"], "t_ms": d["t_ms"] - 2000,
                                                         "alternative": {"kind": "hold", "actor": d["actor"],
                                                                         "target": None}, "n": 10})
            await tools.close()
            return time.perf_counter() - t0

        warm_s = asyncio.run(warm_engine())
        procs.append(subprocess.Popen([sys.executable, "-m", "newsroom.worker", "--mode", "live", "--match",
                                       moment["match_id"]], env=env, cwd=ROOT,
                                      stdout=open(tmp / "worker.log", "w"), stderr=subprocess.STDOUT))
        log = tmp / "worker.log"
        end = time.time() + 60
        while time.time() < end and "warm-up tactician_live" not in log.read_text():
            time.sleep(0.2)
        bb.query("events", limit=1)
        t_put = time.time()
        moment_id = bb.put("moments", moment)
        cues, end = [], time.time() + args.timeout
        while time.time() < end:
            cues = [c for c in bb.query("cues", moment_id=moment_id)]
            done = [t for t in bb.query("traces", moment_id=moment_id) if t["executor"] in ("cuebus", "director")]
            if cues or any(t["status"] == "suppressed" for t in done):
                break
            time.sleep(0.05)
        t_cue = time.time()
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            p.wait(10)
    traces = bb.query("traces", moment_id=moment_id)
    spend = SpendGuard().total - spend0
    result = {"moment": {k: moment[k] for k in ("t_ms", "clock", "kind", "leverage", "team", "evidence_event_ids")},
              "moment_to_cue_s": round(t_cue - t_put, 2), "engine_warm_s": round(warm_s, 2),
              "executors": [{k: t.get(k) for k in ("executor", "branch", "status", "latency_ms", "model", "cost_usd",
                                                    "tool_calls")} for t in traces],
              "cues": [{"cue_id": c["cue_id"], "kind": c["kind"], "verified": c["verified"], "text": c["text"],
                        "model": c["provenance"]["model"], "claims": [x["text"] for x in c["explain"]["claims"]]}
                       for c in cues],
              "spend_usd": round(spend, 4), "logs": str(tmp)}
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))
    return 0 if cues else 1


if __name__ == "__main__":
    sys.exit(main())
