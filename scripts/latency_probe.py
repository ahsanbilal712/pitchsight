"""Live latency probe: explained moments of the golden match through the real processes.

    python scripts/latency_probe.py --moment-t 2715600[,2905600,...] [--out data/runtime/latency_probe.json]

Starts `python -m mcp_server` (Streamable HTTP, live mode) and `python -m newsroom.worker --mode live` against a
fresh blackboard, then for each moment in turn: warms the MCP server's engine just before it (a live match is
already there), writes the Scout's moment into the blackboard and waits for its cue (or the Director's
suppression). Prints and saves wall-clock timings: moment written -> cue written, per executor from the trace
rows, p50/p95 over the delivered cues, and the spend. Model calls are real (Gemini on Vertex AI) and go through
SpendGuard.
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

import numpy as np  # noqa: E402

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
    ap.add_argument("--moment-t", default="2715600", help="comma-separated moment times (ms)")
    ap.add_argument("--match", default="data/matches/4242")
    ap.add_argument("--out", default="data/runtime/latency_probe.json")
    ap.add_argument("--timeout", type=float, default=120)
    args = ap.parse_args()
    times = [int(t) for t in args.moment_t.split(",")]

    tmp = Path(tempfile.mkdtemp(prefix="whyline_probe_"))
    env = {**os.environ, "PYTHONPATH": str(ROOT / "packages"), "WHYLINE_BLACKBOARD": str(tmp / "bb.sqlite"),
           "WHYLINE_CHECKPOINT_DIR": str(tmp / "ckpt"), "WHYLINE_LOG": "INFO", "WHYLINE_MODE": "live"}
    port = free_port()
    env["WHYLINE_MCP_PORT"] = str(port)
    env["WHYLINE_MCP_URL"] = f"http://127.0.0.1:{port}/mcp"

    moments = {m["t_ms"]: m for m in scout_rules.detect_match(ROOT / args.match)}
    bb = SqliteBlackboard(tmp / "bb.sqlite")
    spend0 = SpendGuard().total
    procs, runs = [], []
    try:
        procs.append(subprocess.Popen([sys.executable, "-m", "mcp_server"], env=env, cwd=ROOT,
                                      stdout=open(tmp / "mcp.log", "w"), stderr=subprocess.STDOUT))
        wait_port(port)
        procs.append(subprocess.Popen([sys.executable, "-m", "newsroom.worker", "--mode", "live", "--match",
                                       "m_4242"], env=env, cwd=ROOT,
                                      stdout=open(tmp / "worker.log", "w"), stderr=subprocess.STDOUT))
        log = tmp / "worker.log"
        end = time.time() + 90
        while time.time() < end and "worker ready" not in log.read_text():
            time.sleep(0.2)
        for t in times:
            moment = moments[t]
            warm_s = asyncio.run(warm_engine(env, tmp, moment))
            t_put = time.time()
            moment_id = bb.put("moments", moment)
            cue, end = None, time.time() + args.timeout
            while time.time() < end:
                cues = bb.query("cues", moment_id=moment_id)
                if cues:
                    cue = cues[0]
                    break
                if any(r["executor"] == "director" and r["status"] == "suppressed"
                       for r in bb.query("traces", moment_id=moment_id)):
                    break
                time.sleep(0.05)
            t_end = time.time()
            traces = bb.query("traces", moment_id=moment_id)
            runs.append({"moment": {k: moment[k] for k in ("t_ms", "clock", "kind", "leverage", "team")},
                         "moment_to_cue_s": round(t_end - t_put, 2), "engine_warm_s": round(warm_s, 2),
                         "delivered": cue is not None,
                         "executors": [{k: r.get(k) for k in ("executor", "branch", "status", "latency_ms", "model",
                                                              "cost_usd", "tool_calls", "reason")} for r in traces],
                         "cue": None if cue is None else {
                             "cue_id": cue["cue_id"], "kind": cue["kind"], "verified": cue["verified"],
                             "text": cue["text"], "model": cue["provenance"]["model"],
                             "claims": [x["text"] for x in cue["explain"]["claims"]]}})
            print(json.dumps(runs[-1]), flush=True)
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            p.wait(10)
    delivered = sorted(r["moment_to_cue_s"] for r in runs if r["delivered"])
    result = {"runs": runs, "delivered": len(delivered), "of": len(runs),
              "p50_s": round(float(np.percentile(delivered, 50)), 2) if delivered else None,
              "p95_s": round(float(np.percentile(delivered, 95)), 2) if delivered else None,
              "spend_usd": round(SpendGuard().total - spend0, 4), "logs": str(tmp)}
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1))
    print(json.dumps({k: v for k, v in result.items() if k != "runs"}))
    return 0 if delivered else 1


async def warm_engine(env: dict, tmp: Path, moment: dict) -> float:
    """Bring the MCP server's engine to just before the moment (in a live match it is already there)."""
    from mcp_server.tools_core import MatchStore
    from newsroom.decision import decision_point
    from newsroom.tools import McpTools

    store = MatchStore(SqliteBlackboard(tmp / "warm.sqlite"), runtime_dir=tmp)
    d = decision_point(store, moment)
    t0 = time.perf_counter()
    if d is None:
        return 0.0
    tools = McpTools(env["WHYLINE_MCP_URL"])
    await tools.call("get_state", {"match_id": moment["match_id"], "t_ms": d["t_ms"] - 30_000})
    await tools.call("simulate_counterfactual", {"match_id": moment["match_id"], "t_ms": d["t_ms"] - 2000,
                                                 "alternative": {"kind": "hold", "actor": d["actor"], "target": None},
                                                 "n": 10})
    await tools.close()
    return time.perf_counter() - t0


if __name__ == "__main__":
    sys.exit(main())
