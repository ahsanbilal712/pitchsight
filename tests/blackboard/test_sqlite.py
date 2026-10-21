"""SqliteBlackboard: schema round-trips, ID rules, query, watch across processes, put latency (T-017)."""

import asyncio
import json
import multiprocessing as mp
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from blackboard import NotFound, SqliteBlackboard, format_id, parse_id
from blackboard.ids import collection_of


def arun(coro):
    """asyncio.run on a worker thread: Playwright's session-scoped sync API (tests/apps) keeps a loop running in
    the main thread, and asyncio.run refuses to start inside it."""
    with ThreadPoolExecutor(1) as pool:
        return pool.submit(asyncio.run, coro).result()


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_COLLECTIONS = {"cue": "cues", "explanation": "explanations", "counterfactual": "counterfactuals",
                      "event": "events", "viewer_profile": "viewer_profiles", "cache_manifest": "manifests"}


@pytest.fixture
def bb(tmp_path):
    board = SqliteBlackboard(tmp_path / "bb.sqlite")
    yield board
    board.close()


def _examples():
    for path in sorted((ROOT / "schemas").glob("*.schema.json")):
        name = path.name.removesuffix(".schema.json")
        for i, ex in enumerate(json.loads(path.read_text()).get("examples", [])):
            yield pytest.param(name, ex, id=f"{name}-{i}")


@pytest.mark.parametrize("schema,example", list(_examples()))
def test_every_schema_example_round_trips(bb, schema, example):
    collection = SCHEMA_COLLECTIONS[schema]
    doc_id = bb.put(collection, example)
    assert bb.get(collection, doc_id) == example
    assert bb.query(collection) == [example]


def test_ids_follow_tech_plan_and_are_monotonic_per_match(bb):
    assert [format_id(c, n) for c, n in [("facts", 1), ("moments", 77), ("pitch_control", 412),
                                         ("counterfactuals", 77), ("explanations", 77), ("cues", 912)]] == \
        ["f_000001", "mo_00077", "pc_000412", "cf_000077", "ex_000077", "c_000912"]
    a = [bb.put("facts", {"match_id": "m_1", "t_ms": i, "name": "x", "value": i}) for i in range(3)]
    b = [bb.put("facts", {"match_id": "m_2", "t_ms": i, "name": "x", "value": i}) for i in range(2)]
    assert a == ["f_000001", "f_000002", "f_000003"] and b == ["f_000001", "f_000002"]
    bb.put("moments", {"moment_id": "mo_00076", "match_id": "m_1", "t_ms": 5})
    assert bb.put("moments", {"match_id": "m_1", "t_ms": 6}) == "mo_00077"
    assert bb.next_id("cues", "m_1") == "c_000001" and bb.next_id("cues", "m_1") == "c_000002"
    assert collection_of("pc_000412") == "pitch_control" and collection_of("e_8812") == "events"
    assert parse_id("mo_00077") == ("mo", 77)


def test_get_missing_and_replace(bb):
    with pytest.raises(NotFound):
        bb.get("cues", "c_000001")
    bb.put("cues", {"cue_id": "c_000001", "match_id": "m_1", "t_in_ms": 10, "producer_status": "auto"})
    bb.put("cues", {"cue_id": "c_000001", "match_id": "m_1", "t_in_ms": 10, "producer_status": "vetoed"})
    assert bb.get("cues", "c_000001")["producer_status"] == "vetoed"
    assert len(bb.query("cues")) == 1


def test_query_filters(bb):
    for i in range(10):
        bb.put("events", {"id": f"e_{i + 1:04d}", "match_id": "m_1", "t_ms": i * 1000,
                          "type": "shot" if i % 3 == 0 else "pass", "player": f"p_00{i % 2 + 1}"})
    assert [e["id"] for e in bb.query("events", type="shot")] == ["e_0001", "e_0004", "e_0007", "e_0010"]
    assert len(bb.query("events", match_id="m_1", t_from_ms=2000, t_to_ms=5000)) == 4
    assert [e["id"] for e in bb.query("events", type=["shot"], player="p_002")] == ["e_0004", "e_0010"]
    assert bb.query("events", match_id="m_9") == [] and bb.query("nothing_here") == []


def _collect(bb, collection, n, **kw):
    async def run():
        out = []
        async for doc in bb.watch(collection, **kw):
            out.append(doc)
            if len(out) == n:
                return out
    return arun(asyncio.wait_for(run(), timeout=20))


def test_watch_yields_in_insertion_order(bb):
    for i in range(5):
        bb.put("moments", {"match_id": "m_1", "t_ms": 100 - i})
    docs = _collect(bb, "moments", 5)
    assert [d["moment_id"] for d in docs] == [f"mo_{i:05d}" for i in range(1, 6)]


def _writer(path: str, n: int) -> None:
    board = SqliteBlackboard(path)
    time.sleep(0.3)  # let the watcher start first
    for i in range(n):
        board.put("cues", {"match_id": "m_4242", "t_in_ms": i, "seq": i})
        time.sleep(0.002)
    board.close()


def test_watch_sees_another_process(tmp_path):
    path = str(tmp_path / "x.sqlite")
    bb = SqliteBlackboard(path)
    proc = mp.get_context("spawn").Process(target=_writer, args=(path, 60))
    proc.start()
    docs = _collect(bb, "cues", 60, match_id="m_4242")
    proc.join(10)
    assert proc.exitcode == 0
    assert [d["seq"] for d in docs] == list(range(60))
    assert [d["cue_id"] for d in docs] == [f"c_{i:06d}" for i in range(1, 61)]


def _allocate(path: str, n: int, q) -> None:
    board = SqliteBlackboard(path)
    q.put([board.next_id("cues", "m_1") for _ in range(n)])


def test_next_id_unique_across_processes(tmp_path):
    path = str(tmp_path / "ids.sqlite")
    SqliteBlackboard(path).close()
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    procs = [ctx.Process(target=_allocate, args=(path, 100, q)) for _ in range(2)]
    for p in procs:
        p.start()
    got = q.get(timeout=20) + q.get(timeout=20)
    for p in procs:
        p.join(10)
    assert len(set(got)) == 200 and max(got) == "c_000200"


def test_put_under_2ms(bb):
    doc = json.loads((ROOT / "schemas" / "cue.schema.json").read_text())["examples"][0]
    for _ in range(20):  # warm up
        bb.put("cues", {k: v for k, v in doc.items() if k != "cue_id"})
    times = []
    for _ in range(500):
        t0 = time.perf_counter()
        bb.put("cues", {k: v for k, v in doc.items() if k != "cue_id"})
        times.append((time.perf_counter() - t0) * 1000)
    p50 = statistics.median(times)
    print(f"put p50 {p50:.3f} ms, p95 {sorted(times)[474]:.3f} ms")
    assert p50 < 2.0


def test_shared_connection_is_thread_safe(bb):
    """Threads sharing one SqliteBlackboard (the api's kill thread, T-051) must not hit InterfaceError."""
    import threading

    errors = []

    def reader(i):
        try:
            for _ in range(200):
                bb.query(f"coll_{i % 4}", status="running")
                bb.put("runs", {"id": f"r{i}", "status": "running"})
        except Exception as exc:  # noqa: BLE001 - any error fails the test
            errors.append(exc)

    threads = [threading.Thread(target=reader, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
