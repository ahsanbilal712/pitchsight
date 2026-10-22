"""Headless replay harness: the cue stream of a full golden replay, as a SHA-256 (T-064, DEMO_MASTERPLAN §9 item 1).

    python scripts/replay_headless.py --seed 4242 --speed 10 --out cues.jsonl

Starts the three backend processes as the demo does (`python -m mcp_server`, `python -m newsroom.supervisor --mode
replay`, `python -m api.replay --feed`) on free localhost ports, with a fresh blackboard, checkpoint folder and spend
ledger in a temporary folder (the repository's runtime files and ledger are never touched). The API's replay clock
plays the match to full time; the replay feed hands each moment to the newsroom worker as the clock passes it, and the
worker answers from the committed cache (no model call). When the clock is at full time and every moment has been
run, the cues are dumped sorted by cue_id with volatile fields removed, and their SHA-256 is printed.

Network guard: every process gets a `sitecustomize` that refuses socket connections to anything but 127.0.0.1 / ::1
and logs each refused address; the harness fails if any was refused. Recaps wait for a producer decision (none is
sent), so they are not in the stream.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOLATILE = {"ts", "created_at", "updated_at", "started_ms", "pid", "latency_ms", "wall_ms"}

GUARD = '''"""WHYLINE network guard (scripts/replay_headless.py): loopback only; SIGUSR1 dumps every thread's stack."""
import faulthandler
import ipaddress
import os
import signal
import socket

faulthandler.register(signal.SIGUSR1, all_threads=True)

_connect, _connect_ex = socket.socket.connect, socket.socket.connect_ex
_LOG = os.environ.get("WHYLINE_NET_GUARD_LOG")


def _allowed(address):
    if not isinstance(address, tuple):
        return True                                    # AF_UNIX
    host = str(address[0]).split("%")[0]
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _refuse(address):
    if _LOG:
        with open(_LOG, "a") as f:
            f.write(f"{os.getpid()} {address!r}\\n")
    raise ConnectionRefusedError(f"whyline network guard: {address!r} is not loopback")


def connect(self, address):
    if not _allowed(address):
        _refuse(address)
    return _connect(self, address)


def connect_ex(self, address):
    if not _allowed(address):
        _refuse(address)
    return _connect_ex(self, address)


socket.socket.connect, socket.socket.connect_ex = connect, connect_ex
'''


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def strip(obj):
    if isinstance(obj, dict):
        return {k: strip(v) for k, v in obj.items() if k not in VOLATILE}
    if isinstance(obj, list):
        return [strip(v) for v in obj]
    return obj


def get_json(url: str, timeout: float = 2.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def dump_stacks(procs: dict) -> None:
    """SIGUSR1 to every harness process and its children: faulthandler writes their stacks to the logs."""
    pids = [p.pid for p in procs.values() if p.poll() is None]
    for pid in list(pids):
        r = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True)
        pids += [int(x) for x in r.stdout.split()]
    for pid in pids:
        try:
            os.kill(pid, signal.SIGUSR1)
        except OSError:
            pass
    time.sleep(1.0)


def wait_for(cond, timeout_s: float, what: str, procs: dict, progress=None, stall_s: float = 180) -> None:
    """Poll cond(); fail on timeout, on a dead process, or when progress() has not changed for stall_s."""
    deadline = time.monotonic() + timeout_s
    last, since = None, time.monotonic()
    while time.monotonic() < deadline:
        if progress is not None:
            now = progress()
            if now != last:
                last, since = now, time.monotonic()
            elif time.monotonic() - since > stall_s:
                dump_stacks(procs)
                raise SystemExit(f"stalled: no progress ({now}) for {stall_s:.0f} s waiting for {what}")
        for name, p in procs.items():
            if p.poll() is not None and name != "newsroom":
                raise SystemExit(f"{name} exited with {p.returncode} while waiting for {what}")
        try:
            if cond():
                return
        except OSError:
            pass
        time.sleep(0.25)
    dump_stacks(procs)
    raise SystemExit(f"timed out after {timeout_s:.0f} s waiting for {what}")


def run(seed: int, speed: float, out: Path, work: Path, timeout_s: float, python: str) -> dict:
    from api.replay import MatchData
    from blackboard import SqliteBlackboard

    match_id = f"m_{seed}"
    guard = work / "guard"
    guard.mkdir(parents=True, exist_ok=True)
    (guard / "sitecustomize.py").write_text(GUARD)
    api_port, mcp_port = free_port(), free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "GOOGLE_", "GEMINI_"))}
    env.update({
        "PYTHONPATH": os.pathsep.join([str(guard), str(ROOT / "packages")]),
        "WHYLINE_MODE": "replay", "WHYLINE_MATCH_SEED": str(seed), "WHYLINE_REPLAY_SPEED": str(speed),
        "WHYLINE_BLACKBOARD": str(work / "blackboard.sqlite"), "WHYLINE_CHECKPOINT_DIR": str(work / "checkpoints"),
        "WHYLINE_WORKER_PIDFILE": str(work / "newsroom.pid"), "WHYLINE_DEMO_LOG": str(work / "demo.log"),
        "WHYLINE_SPEND_LEDGER": str(work / "ledger.jsonl"), "WHYLINE_NET_GUARD_LOG": str(work / "refused.log"),
        "WHYLINE_API_PORT": str(api_port), "WHYLINE_MCP_PORT": str(mcp_port),
        "WHYLINE_MCP_URL": f"http://127.0.0.1:{mcp_port}/mcp", "CLOUDSDK_CONFIG": str(work / "no-gcloud"),
        "NO_PROXY": "*", "OMP_NUM_THREADS": "1"})
    logs = {n: open(work / f"{n}.log", "w") for n in ("mcp", "newsroom", "api")}
    cmds = {"mcp": [python, "-m", "mcp_server"],
            "newsroom": [python, "-m", "newsroom.supervisor", "--mode", "replay", "--match", match_id],
            "api": [python, "-m", "api.replay", "--seed", str(seed), "--speed", str(speed), "--port", str(api_port),
                    "--feed"]}
    procs: dict[str, subprocess.Popen] = {}
    started = time.monotonic()
    try:
        procs["mcp"] = subprocess.Popen(cmds["mcp"], cwd=ROOT, env=env, stdout=logs["mcp"], stderr=subprocess.STDOUT)
        wait_for(lambda: socket.create_connection(("127.0.0.1", mcp_port), 0.5).close() or True, 120, "mcp", procs)
        procs["newsroom"] = subprocess.Popen(cmds["newsroom"], cwd=ROOT, env=env, stdout=logs["newsroom"],
                                             stderr=subprocess.STDOUT, start_new_session=True)
        wait_for(lambda: "worker ready" in (work / "newsroom.log").read_text(), 300, "the newsroom worker", procs)
        procs["api"] = subprocess.Popen(cmds["api"], cwd=ROOT, env=env, stdout=logs["api"], stderr=subprocess.STDOUT)
        base = f"http://127.0.0.1:{api_port}"
        wait_for(lambda: get_json(f"{base}/health")["status"] == "ok", 120, "the api", procs)
        end_ms = MatchData.load(seed).end_ms
        bb = SqliteBlackboard(work / "blackboard.sqlite")
        expected = sum(1 for line in (ROOT / "data" / "matches" / str(seed) / "cache" / "moments.jsonl")
                       .read_text().splitlines() if line.strip())

        def finished() -> bool:
            if get_json(f"{base}/health")["stream_t_ms"] < end_ms:
                return False
            moments = bb.query("moments", match_id=match_id)
            return len(moments) >= expected and all(m.get("status") in ("done",) for m in moments)

        def progress() -> int:              # moments run; the longest quiet gap at x10 is ~90 s
            return sum(1 for m in bb.query("moments", match_id=match_id) if m.get("status") == "done")

        wait_for(finished, timeout_s, "full time and every moment run", procs, progress=progress, stall_s=240)
        cues = sorted((strip(c) for c in bb.query("cues", match_id=match_id)), key=lambda c: c["cue_id"])
        bb.close()
    finally:
        for name in ("api", "newsroom", "mcp"):
            p = procs.get(name)
            if p is not None and p.poll() is None:
                if name == "newsroom":
                    os.killpg(p.pid, signal.SIGTERM)
                else:
                    p.terminate()
                try:
                    p.wait(10)
                except subprocess.TimeoutExpired:
                    p.kill()
        for f in logs.values():
            f.close()
    body = "".join(json.dumps(c, sort_keys=True, separators=(",", ":")) + "\n" for c in cues)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body)
    refused = (work / "refused.log").read_text().splitlines() if (work / "refused.log").exists() else []
    return {"sha256": hashlib.sha256(body.encode()).hexdigest(), "cues": len(cues), "moments": expected,
            "verified": sum(1 for c in cues if c.get("verified")), "refused_connections": len(refused),
            "seconds": round(time.monotonic() - started, 1), "speed": speed, "out": str(out), "work": str(work)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="scripts/replay_headless.py")
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--speed", type=float, default=10.0)
    ap.add_argument("--out", type=Path, default=Path("cues.jsonl"))
    ap.add_argument("--work", type=Path, default=None, help="temporary folder (default: a new one)")
    ap.add_argument("--timeout-s", type=float, default=3600)
    args = ap.parse_args(argv)
    sys.path.insert(0, str(ROOT / "packages"))
    work = args.work or Path(tempfile.mkdtemp(prefix="whyline_replay_"))
    res = run(args.seed, args.speed, args.out.resolve(), work, args.timeout_s, sys.executable)
    print(json.dumps(res))
    if res["refused_connections"]:
        print(f"network guard refused {res['refused_connections']} non-loopback connection(s): {work}/refused.log",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
