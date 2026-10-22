"""Cue fan-out to 20 WebSocket clients < 50 ms (TECH_PLAN 1.4 api, T-033).

A real uvicorn server and 20 asyncio websocket clients (analyst, casual and studio). Each trial writes one cue into
the blackboard, the way the newsroom's CueBus does, and times the moment the 20th client has it. That includes
the blackboard watch poll (20 ms) as well as the fan-out itself. The 50 ms limit is asserted on p95 over 20 cues,
as the plan's other timing limits are: the Mac is shared with model training (load average 30-300), and one
scheduler stall can push a single trial past 50 ms (seen: max 61-227 ms with p95 23-31 ms). The max is printed.
"""

import asyncio
import copy
import json
import socket
import statistics
import threading
import time
from pathlib import Path

import uvicorn

from api.main import create_app
from blackboard import SqliteBlackboard

ROOT = Path(__file__).resolve().parents[2]
CUE = json.loads((ROOT / "schemas" / "cue.schema.json").read_text())["examples"][0]
N_CLIENTS, TRIALS, LIMIT_MS = 20, 20, 50.0


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_off_loop(coro):
    """tests/apps leaves a Playwright loop running in the main thread; run asyncio code on a worker thread."""
    box = {}
    t = threading.Thread(target=lambda: box.update(result=asyncio.run(coro)))
    t.start()
    t.join(timeout=120)
    return box["result"]


async def trials(port: int, bb, hub) -> list[float]:
    from websockets.asyncio.client import connect

    modes = ["analyst", "casual", "studio"]
    clients = [await connect(f"ws://127.0.0.1:{port}/ws?viewer_id=v{i}&mode={modes[i % 3]}", max_size=2**24)
               for i in range(N_CLIENTS)]
    arrivals: dict[str, list[float]] = {}

    async def reader(ws):
        async for text in ws:
            now = time.perf_counter()
            for line in text.split("\n"):
                if '"type":"cue"' in line:
                    arrivals.setdefault(json.loads(line)["payload"]["cue_id"], []).append(now)

    readers = [asyncio.create_task(reader(ws)) for ws in clients]
    await asyncio.sleep(0.5)                                     # everyone connected and streaming frames
    latencies = []
    for k in range(TRIALS):
        cue = copy.deepcopy(CUE)
        cue_id = f"c_{100 + k:06d}"
        cue.update(cue_id=cue_id, t_in_ms=hub.now() - 100, t_out_ms=hub.now() + 8000)
        cue["targets"]["modes"] = modes
        t0 = time.perf_counter()
        bb.put("cues", cue)
        while len(arrivals.get(cue_id, [])) < N_CLIENTS:
            if time.perf_counter() - t0 > 2:
                raise AssertionError(f"{cue_id}: only {len(arrivals.get(cue_id, []))} clients got it")
            await asyncio.sleep(0.001)
        latencies.append(1000 * (max(arrivals[cue_id]) - t0))
        await asyncio.sleep(0.07)                                # trials land at different watch-poll phases
    for r in readers:
        r.cancel()
    for ws in clients:
        await ws.close()
    return latencies


def test_cue_fanout_to_20_clients_under_50ms(tmp_path):
    bb = SqliteBlackboard(tmp_path / "bb.sqlite")
    app = create_app(seed=4242, speed=1, bb=bb)
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while not server.started:
        assert time.time() < deadline, "api did not start"
        time.sleep(0.05)
    try:
        lat = sorted(run_off_loop(trials(port, bb, app.state.hub)))
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        bb.close()
    p95 = lat[int(0.95 * (len(lat) - 1))]
    print(f"\ncue fan-out to {N_CLIENTS} clients over {TRIALS} cues (blackboard write -> 20th client): "
          f"p50 {statistics.median(lat):.1f} ms, p95 {p95:.1f} ms, max {lat[-1]:.1f} ms")
    assert p95 < LIMIT_MS
