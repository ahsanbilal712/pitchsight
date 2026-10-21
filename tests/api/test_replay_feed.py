"""Replay feed: cached analytics, oracle and moments on the replay clock (api/replay_feed.py).

A small synthetic cache in a temp dir (same file shapes as scripts/precompute.py writes), so the test does not
depend on the golden cache being built.
"""

import json
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.replay import MATCHES, MatchData
from api.replay_feed import ReplayFeed
from blackboard import SqliteBlackboard

T = np.arange(0, 120_001, 100, dtype=np.int64)          # the first two minutes at 10 Hz


def write_cache(root):
    (root / "analytics").mkdir(parents=True)
    chaos = np.linspace(20, 80, len(T)).astype(np.float32)
    state = np.where(T < 40_000, 0, np.where(T < 90_000, 1, 2)).astype(np.int8)
    cols = {k: np.full(len(T), v, dtype=np.float32) for k, v in
            {"control_home": 0.55, "pressure_home": 0.4, "pressure_away": 0.3, "tempo": 12.0, "turnovers_60s": 3.0}.items()}
    np.savez_compressed(root / "analytics" / "frames.npz", t_ms=T, state=state,
                        state_names=np.array(["Settled", "Transitional", "Chaotic"]), chaos=chaos, **cols)
    (root / "analytics" / "oracle.json").write_text(json.dumps([
        {"t_ms": 30_000, "p_shot_10s": 0.34, "likely_zone": "box_central", "likely_shooter": "p_017", "n": 50,
         "horizon_s": 10, "seed": 4242},
        {"t_ms": 32_000, "p_shot_10s": 0.12, "likely_zone": "outside_box", "likely_shooter": None, "n": 50,
         "horizon_s": 10, "seed": 4242}]))
    (root / "moments.jsonl").write_text("".join(json.dumps(m) + "\n" for m in [
        {"moment_id": "mo_00001", "match_id": "m_4242", "t_ms": 20_000, "clock": "00:20", "kind": "big_chance"},
        {"moment_id": "mo_00002", "match_id": "m_4242", "t_ms": 70_000, "clock": "01:10", "kind": "state_change"}]))


@pytest.fixture
def feed(tmp_path):
    write_cache(tmp_path / "cache")
    bb = SqliteBlackboard(tmp_path / "bb.sqlite")
    yield ReplayFeed(MatchData.load(4242), tmp_path / "cache", bb), bb
    bb.close()


def test_facts_once_a_second_and_state_changes(feed):
    f, _ = feed
    msgs = [m for _, m in f.between(9_999, 12_000)]
    names = [m["payload"]["name"] for m in msgs if m["type"] == "fact"]
    assert names.count("chaos_index") == 3 and "control_home" in names and "tempo" in names
    states = [(t, m["payload"]["value"]) for t, m in f.between(0, 120_000) if m["payload"].get("name") == "chaos_state"]
    assert states == [(40_000, "Transitional"), (90_000, "Chaotic")]
    snap = {m["payload"]["name"]: m["payload"]["value"] for m in f.snapshot(95_500) if m["type"] == "fact"}
    assert snap["chaos_state"] == "Chaotic" and 67 < snap["chaos_index"] < 68


def test_oracle_converted_to_the_overlay_shape(feed):
    f, _ = feed
    (t, msg), = [(t, m) for t, m in f.between(29_000, 31_000) if m["type"] == "oracle"]
    o = msg["payload"]
    assert t == 30_000 and o["shooter"] == "p_017" and o["p_shot_away"] == 0.0 and o["p_shot_home"] == 0.34
    data = MatchData.load(4242)
    home_right = int(data.period[data.index_at(30_000)]) == 1     # home attacks +x in the first half
    assert o["zone"]["x"] == (97.0 if home_right else 8.0) and o["zone"]["r"] == 8.0
    assert any(m["type"] == "oracle" for m in f.snapshot(31_000))
    assert not any(m["type"] == "oracle" for m in f.snapshot(40_000))   # stale after 4 s


def test_moments_written_when_the_clock_reaches_them_once(feed):
    f, bb = feed
    assert f.release_moments(19_000) == 0
    assert f.release_moments(21_000) == 1
    assert bb.get("moments", "mo_00001")["status"] == "new"
    bb.put("moments", {**bb.get("moments", "mo_00001"), "status": "done"})
    assert f.release_moments(80_000) == 1 and bb.get("moments", "mo_00001")["status"] == "done"


def test_stream_carries_the_feed_and_studio_sees_moments(tmp_path, monkeypatch):
    write_cache(tmp_path / "data" / "4242" / "cache")
    for name in ("events.jsonl", "tracking.npz"):
        (tmp_path / "data" / "4242" / name).symlink_to(MATCHES / "4242" / name)
    monkeypatch.setattr("api.replay.MATCHES", tmp_path / "data")
    bb = SqliteBlackboard(tmp_path / "bb.sqlite")
    with TestClient(create_app(seed=4242, speed=10, bb=bb, feed=True)) as client:
        with client.websocket_connect("/ws?viewer_id=s&mode=studio") as ws:
            client.post("/replay/control", json={"action": "seek", "value": 15_000})
            seen, deadline = [], time.monotonic() + 4
            while time.monotonic() < deadline and not any(
                    m["type"] == "moment" and m["payload"]["moment_id"] == "mo_00001" for m in seen):
                seen += [json.loads(x) for x in ws.receive_text().split("\n") if x.strip()]
        assert {"fact", "moment"} <= {m["type"] for m in seen}
        assert any(m["type"] == "fact" and m["payload"]["name"] == "chaos_index" for m in seen)
        assert bb.get("moments", "mo_00001")["moment_id"] == "mo_00001"
    bb.close()
