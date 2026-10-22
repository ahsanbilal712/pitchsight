"""Replay server: REST, replay clock and the WebSocket tracking stream (T-022)."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.replay import MatchData, ReplayClock, parse_clock
from blackboard import SqliteBlackboard


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    bb = SqliteBlackboard(tmp_path_factory.mktemp("bb") / "bb.sqlite")
    with TestClient(create_app(seed=4242, speed=1, bb=bb)) as c:
        yield c
    bb.close()


def lines(ws) -> list[dict]:
    return [json.loads(line) for line in ws.receive_text().split("\n") if line.strip()]


def assert_frame_shape(f: dict) -> None:
    assert set(f) == {"t_ms", "period", "p", "ball_z", "holder", "possession"}
    assert len(f["p"]) == 23 and all(len(r) == 4 for r in f["p"])
    assert f["period"] in (1, 2) and -1 <= f["holder"] <= 22 and f["possession"] in (-1, 0, 1)
    assert isinstance(f["t_ms"], int) and f["t_ms"] % 100 == 0


# ---------------------------------------------------------------- clock
def test_clock_speed_pause_seek_with_a_fake_wall():
    now = [0.0]
    clock = ReplayClock(5_400_000, speed=1, wall=lambda: now[0])
    now[0] = 2.0
    assert clock.now() == 2000
    clock.set_speed(10)
    now[0] = 3.0
    assert clock.now() == 12_000
    clock.pause()
    now[0] = 9.0
    assert clock.now() == 12_000
    clock.seek(parse_clock("31:10"))
    assert clock.now() == 1_870_000 and clock.generation == 1
    clock.play()
    now[0] = 10.0
    assert clock.now() == 1_880_000
    clock.seek(10**9)
    assert clock.now() == 5_400_000
    with pytest.raises(ValueError):
        clock.set_speed(11)


def test_match_data_lineup_and_score():
    d = MatchData.load(4242)
    assert d.match_id == "m_4242" and d.end_ms == 5_400_000
    assert d.index_at(1_874_050) == 18_740
    assert d.lineup_at(0) == d.player_ids
    after = d.lineup_at(d.subs[0][0])
    assert after[d.subs[0][1]] == d.subs[0][2]
    goals = [e for e in d.events if e["type"] == "goal"]
    assert sum(d.score_at(d.end_ms)) == len(goals)


# ---------------------------------------------------------------- REST
def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["match_id"] == "m_4242"


def test_events_window(client):
    evs = client.get("/match/m_4242/events", params={"from": "31:00", "to": "31:30"}).json()
    assert evs and all(1_860_000 <= e["t_ms"] <= 1_890_000 for e in evs)
    assert [e["idx"] for e in evs] == sorted(e["idx"] for e in evs)
    assert client.get("/match/4242/events", params={"from": 0, "to": 0}).json()[0]["type"] == "match_metadata"
    assert client.get("/match/m_9999/events").status_code == 404


def test_control_validates(client):
    assert client.post("/replay/control", json={"action": "speed", "value": 20}).status_code == 422
    assert client.post("/replay/control", json={"action": "seek"}).status_code == 422
    assert client.post("/replay/control", json={"action": "rewind"}).status_code == 422


# ---------------------------------------------------------------- WebSocket
def test_ws_hello_then_10hz_frames(client):
    client.post("/replay/control", json={"action": "speed", "value": 1})
    client.post("/replay/control", json={"action": "play"})
    with client.websocket_connect("/ws?viewer_id=t1&mode=casual&club=home") as ws:
        first = lines(ws)
        assert first[0]["type"] == "hello"
        hello = first[0]["payload"]
        assert hello["match_id"] == "m_4242" and hello["mode"] == "replay" and hello["replay_speed"] == 1
        assert hello["viewer_profile"]["mode"] == "casual" and hello["viewer_profile"]["club"] == "home"
        assert len(hello["player_ids"]) == 22
        frames = [m for m in first if m["type"] == "tracking_frame"]
        started = time.perf_counter()
        while time.perf_counter() - started < 1.2:
            frames += [m for m in lines(ws) if m["type"] == "tracking_frame"]
        print(f"\n{len(frames)} tracking_frame messages in 1.2 s at x1")
        assert len(frames) >= 10
        ts = [f["payload"]["t_ms"] for f in frames]
        assert ts == sorted(ts) and len(set(ts)) == len(ts)
        assert all(b - a == 100 for a, b in zip(ts[1:], ts[2:], strict=False))
        for f in frames:
            assert_frame_shape(f["payload"])


def test_ws_seek_resets_and_speed_x10(client):
    # seek to 5 s before a golden-match goal (derived from the events, so a regenerated golden match still works)
    goals_all = [e for e in MatchData.load(4242).events if e["type"] == "goal"]
    goal = next(g for g in goals_all if g["t_ms"] >= 600_000)
    target = (goal["t_ms"] - 5000) // 1000 * 1000
    expected = [sum(g["team"] == side and g["t_ms"] <= target for g in goals_all) for side in ("home", "away")]
    with client.websocket_connect("/ws?viewer_id=t2") as ws:
        lines(ws)
        client.post("/replay/control", json={"action": "seek", "value": f"{target // 60000:02d}:{target // 1000 % 60:02d}"})
        hello = None
        while hello is None:
            hello = next((m["payload"] for m in lines(ws) if m["type"] == "hello"), None)
        assert target <= hello["t_ms"] < target + 500 and hello["score"] == expected  # clock keeps playing
        client.post("/replay/control", json={"action": "speed", "value": 10})
        seen: list[dict] = []
        started = time.perf_counter()
        while time.perf_counter() - started < 1.0:
            seen += lines(ws)
        client.post("/replay/control", json={"action": "speed", "value": 1})
        frames = [m["payload"]["t_ms"] for m in seen if m["type"] == "tracking_frame"]
        print(f"\nx10: {len(frames)} frames, {frames[-1] - frames[0]} ms of match time in 1.0 s")
        assert frames[-1] - frames[0] >= 8_000  # x10 moves about 10 s of match time per second
        goals = [m["payload"] for m in seen if m["type"] == "event" and m["payload"]["type"] == "goal"]
        assert goals and goals[0]["t_ms"] == goal["t_ms"]  # the goal arrives on the clock


def test_ws_seek_by_t_ms_alias_and_pause(client):
    with client.websocket_connect("/ws?viewer_id=t3") as ws:
        lines(ws)
        client.post("/replay/control", json={"action": "pause"})
        client.post("/replay/control", json={"action": "seek", "t_ms": 4_000_000})
        hello = None
        while hello is None:
            hello = next((m["payload"] for m in lines(ws) if m["type"] == "hello"), None)
        assert hello["t_ms"] == 4_000_000
        assert hello["player_ids"] != MatchData.load(4242).player_ids  # substitutions applied
        assert client.get("/health").json()["clock"]["t_ms"] == 4_000_000
        client.post("/replay/control", json={"action": "play"})


def test_clock_is_published_to_the_blackboard(client):
    """Other processes (the newsroom's simulated latencies) follow speed changes through blackboard `replay`."""
    client.post("/replay/control", json={"action": "speed", "value": 7})
    doc = client.app.state.bb.get("replay", "m_4242")
    assert doc["speed"] == 7 and doc["playing"] is True
    client.post("/replay/control", json={"action": "speed", "value": 1})
    assert client.app.state.bb.get("replay", "m_4242")["speed"] == 1
