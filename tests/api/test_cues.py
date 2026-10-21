"""Cue fan-out, target filtering, snapshots, producer decisions, docs, spend and live ingest (T-033)."""

import copy
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.replay import MatchData
from blackboard import SqliteBlackboard
from kickoff.stream import stream_match

ROOT = Path(__file__).resolve().parents[2]
CUE = json.loads((ROOT / "schemas" / "cue.schema.json").read_text())["examples"][0]
CF = json.loads((ROOT / "schemas" / "counterfactual.schema.json").read_text())["examples"][0]
START = 600_000  # 10:00


def make_cue(n: int, t_in: int, modes=("analyst", "casual", "studio"), clubs=("any",), players=(), kind="big_chance",
             layer="lower_third", cf=None) -> dict:
    c = copy.deepcopy(CUE)
    c.update({"cue_id": f"c_{n:06d}", "t_in_ms": t_in, "t_out_ms": t_in + 8000, "kind": kind, "layer": layer,
              "targets": {"modes": list(modes), "clubs": list(clubs), "players": list(players)}})
    c["explain"]["counterfactual_id"] = cf
    return c


@pytest.fixture
def env(tmp_path):
    bb = SqliteBlackboard(tmp_path / "bb.sqlite")
    opened: list[Screen] = []
    with TestClient(create_app(seed=4242, speed=1, bb=bb)) as client:
        client.post("/replay/control", json={"action": "seek", "value": START})
        deadline = time.monotonic() + 2
        while client.get("/health").json()["stream_t_ms"] < START:  # the ticker applies the seek
            assert time.monotonic() < deadline
            time.sleep(0.02)
        client.screens = opened
        try:
            yield client, bb
        finally:
            for s in opened:  # an open websocket would block the TestClient shutdown after a failure
                s.close()
    bb.close()


class Screen:
    """A websocket viewer; collects messages until a predicate holds (frames keep arriving at 10 Hz)."""

    def __init__(self, client, query):
        self.cm = client.websocket_connect(f"/ws?{query}")
        self.ws = self.cm.__enter__()
        self.seen: list[dict] = []
        self.cursor = 0
        self.closed = False
        client.screens.append(self)

    def _read(self) -> list[dict]:
        return [json.loads(x) for x in self.ws.receive_text().split("\n") if x.strip()]

    def until(self, pred, timeout=3.0):
        """First message (oldest unconsumed first) matching pred; everything read is kept in `seen`."""
        deadline = time.monotonic() + timeout
        while True:
            while self.cursor < len(self.seen):
                msg = self.seen[self.cursor]
                self.cursor += 1
                if pred(msg):
                    return msg
            if time.monotonic() > deadline:
                raise AssertionError(f"timed out; saw {[m['type'] for m in self.seen[-20:]]}")
            self.seen += self._read()

    def find(self, pred, timeout=3.0):
        """Any message seen so far (or arriving before the timeout) matching pred; order across collections
        is not guaranteed, since each blackboard collection has its own watcher."""
        deadline = time.monotonic() + timeout
        while True:
            hit = next((m for m in self.seen if pred(m)), None)
            if hit is not None:
                return hit
            if time.monotonic() > deadline:
                raise AssertionError(f"timed out; saw {[m['type'] for m in self.seen[-20:]]}")
            self.seen += self._read()

    def drain(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.seen += self._read()
        return self.seen

    def cue_ids(self):
        return {m["payload"]["cue_id"] for m in self.seen if m["type"] == "cue"}

    def close(self):
        if not self.closed:
            self.closed = True
            self.cm.__exit__(None, None, None)


def is_type(kind):
    return lambda m: m["type"] == kind


def test_target_filtering_per_viewer(env):
    client, bb = env
    screens = {name: Screen(client, q) for name, q in {
        "analyst": "viewer_id=a&mode=analyst", "casual_home": "viewer_id=b&mode=casual&club=home",
        "cam_reyes": "viewer_id=c&mode=player_cam&player=p_031", "cam_other": "viewer_id=d&mode=player_cam&player=p_017",
        "studio": "viewer_id=s&mode=studio"}.items()}
    for s in screens.values():
        s.until(is_type("tracking_frame"))
    now = client.get("/health").json()["stream_t_ms"]
    bb.put("cues", {**make_cue(1, now - 500), "match_id": "m_4242"})                         # analyst, casual
    bb.put("cues", make_cue(2, now - 500, modes=("analyst",)))                               # analyst only
    bb.put("cues", make_cue(3, now - 500, modes=("casual",), clubs=("away",)))               # casual away fans
    bb.put("cues", make_cue(4, now - 500, modes=("player_cam",), players=("p_031",), kind="player_tag",
                            layer="player_tag"))                                             # Reyes cam only
    bb.put("cues", make_cue(5, now - 500, modes=("player_cam", "casual"), kind="milestone", layer="ticker"))
    for s in screens.values():
        s.drain(0.6)
    got = {name: s.cue_ids() for name, s in screens.items()}
    assert got["analyst"] == {"c_000001", "c_000002"}
    assert got["casual_home"] == {"c_000001", "c_000005"}
    assert got["cam_reyes"] == {"c_000004", "c_000005"}
    assert got["cam_other"] == {"c_000005"}
    assert got["studio"] == {"c_000001", "c_000002", "c_000003", "c_000004", "c_000005"}
    rest = client.get("/match/m_4242/cues", params={"viewer": "player_cam", "player": "p_031"}).json()
    assert {c["cue_id"] for c in rest} == {"c_000004", "c_000005"}
    assert len(client.get("/match/4242/cues").json()) == 5                                   # studio default


def test_future_cue_is_released_on_the_clock_with_its_counterfactual(env):
    client, bb = env
    bb.put("counterfactuals", CF)
    screen = Screen(client, "viewer_id=a&mode=analyst")
    screen.until(is_type("tracking_frame"))
    now = client.get("/health").json()["stream_t_ms"]
    bb.put("cues", make_cue(7, now + 3000, cf="cf_000077"))
    screen.drain(0.5)
    assert "c_000007" not in screen.cue_ids()                  # 3 s ahead of the stream clock: held
    client.post("/replay/control", json={"action": "speed", "value": 10})
    cue = screen.until(lambda m: m["type"] == "cue" and m["payload"]["cue_id"] == "c_000007", timeout=3)
    client.post("/replay/control", json={"action": "speed", "value": 1})
    frames = [m["payload"]["t_ms"] for m in screen.seen if m["type"] == "tracking_frame"]
    assert frames[-1] >= cue["payload"]["t_in_ms"] - 600       # released when the clock got there
    i = screen.seen.index(cue)
    assert screen.seen[i - 1]["type"] == "counterfactual"      # the ghost/swing-bar document comes first
    assert screen.seen[i - 1]["payload"]["counterfactual_id"] == "cf_000077"


def test_seek_snapshot_replays_cues_on_screen_and_latest_facts(env):
    client, bb = env
    bb.put("counterfactuals", CF)
    bb.put("cues", make_cue(9, 700_000, cf="cf_000077"))
    bb.put("facts", {"match_id": "m_4242", "t_ms": 600_000, "kind": "state", "name": "chaos_state",
                     "value": "Chaotic"})
    bb.put("facts", {"match_id": "m_4242", "t_ms": 699_000, "kind": "index", "name": "chaos_index", "value": 71.0})
    bb.put("facts", {"match_id": "m_4242", "t_ms": 800_000, "kind": "index", "name": "chaos_index", "value": 12.0})
    screen = Screen(client, "viewer_id=a&mode=analyst")
    screen.until(is_type("tracking_frame"))
    client.post("/replay/control", json={"action": "seek", "value": 702_000})
    screen.until(lambda m: m["type"] == "hello" and m["payload"]["t_ms"] >= 702_000)
    screen.until(lambda m: m["type"] == "cue" and m["payload"]["cue_id"] == "c_000009", timeout=1)
    facts = {m["payload"]["name"]: m["payload"]["value"] for m in screen.seen if m["type"] == "fact"}
    assert facts == {"chaos_state": "Chaotic", "chaos_index": 71.0}


def test_veto_of_a_shown_cue_removes_it(env):
    client, bb = env
    screens = [Screen(client, "viewer_id=a&mode=analyst"), Screen(client, "viewer_id=s&mode=studio")]
    for s in screens:
        s.until(is_type("tracking_frame"))
    now = client.get("/health").json()["stream_t_ms"]
    bb.put("cues", make_cue(11, now - 100))
    for s in screens:
        s.until(lambda m: m["type"] == "cue" and m["payload"]["cue_id"] == "c_000011")
    started = time.monotonic()
    body = client.post("/producer/decision", json={"request_id": "c_000011", "decision": "veto"}).json()
    assert body == {"request_id": "c_000011", "decision": "vetoed", "cue_removed": True}
    for s in screens:
        s.until(lambda m: m["type"] == "cue_remove" and m["payload"]["cue_id"] == "c_000011", timeout=1)
    print(f"\nveto -> cue_remove on two screens in {1000 * (time.monotonic() - started):.0f} ms")
    assert bb.get("cues", "c_000011")["producer_status"] == "vetoed"
    assert bb.get("decisions", "c_000011")["decision"] == "vetoed"
    assert client.get("/match/m_4242/cues").json() == []
    assert client.post("/producer/decision", json={"request_id": "r_1", "decision": "maybe"}).status_code == 422


def test_studio_only_messages_and_mode(env):
    client, bb = env
    analyst, studio = Screen(client, "viewer_id=a&mode=analyst"), Screen(client, "viewer_id=s&mode=studio")
    for s in (analyst, studio):
        s.until(is_type("tracking_frame"))
    bb.put("traces", {"match_id": "m_4242", "executor": "tactician", "status": "ok", "cache_hit": True})
    bb.put("requests", {"id": "req_1", "request_id": "req_1", "match_id": "m_4242", "cue": make_cue(12, 0)})
    bb.put("modes", {"id": "mode_1", "match_id": "m_4242", "t_ms": 0, "mode": "degraded", "reason": "spend cap"})
    studio.find(lambda m: m["type"] == "trace" and m["payload"]["executor"] == "tactician")
    studio.find(lambda m: m["type"] == "request_info" and m["payload"]["request_id"] == "req_1")
    mode = studio.find(is_type("mode"))
    assert mode["payload"] == {"mode": "degraded", "reason": "spend cap"}
    analyst.find(is_type("mode"))
    analyst.drain(0.3)
    assert not [m for m in analyst.seen if m["type"] in ("trace", "request_info", "moment")]
    assert client.get("/health").json()["mode"] == "degraded"


def test_doc_endpoint_whitelist(env):
    client, bb = env
    bb.put("counterfactuals", CF)
    assert client.get("/match/m_4242/doc/counterfactuals/cf_000077").json()["n"] == 200
    assert client.get("/match/m_4242/doc/cf_000077").json()["counterfactual_id"] == "cf_000077"
    first = MatchData.load(4242).events[5]["id"]
    assert client.get(f"/match/m_4242/doc/{first}").json()["id"] == first           # events of the replayed match
    assert client.get("/match/m_4242/doc/cues/c_000001").status_code == 404          # not whitelisted
    assert client.get("/match/m_4242/doc/decisions/x").status_code == 404
    assert client.get("/match/m_4242/doc/explanations/ex_999999").status_code == 404


def test_spend_and_kill_stub(env):
    client, _ = env
    s = client.get("/spend").json()
    assert {"match_usd", "day_usd", "caps"} <= set(s) and s["caps"]["match"] == 2.5
    r = client.post("/demo/kill", json={"target": "newsroom"})
    assert r.status_code == 202 and r.json()["target"] == "newsroom"


def test_live_ingest_via_kickoff_stream(env):
    client, bb = env
    data = MatchData.load(4242)
    tracking = {"t_ms": data.t_ms, "period": data.period, "S": data.S, "ball_z": data.ball_z,
                "holder": data.holder, "possession": data.possession}
    live_events = [{**e, "match_id": "m_7"} for e in data.events]
    screen = Screen(client, "viewer_id=a&mode=analyst")
    screen.until(is_type("tracking_frame"))

    def post(url, body):
        r = client.post(url.removeprefix("http://testserver"), json=body)
        assert r.status_code == 200, r.text
        return r.json()

    sent = stream_match("m_7", live_events, tracking, api="http://testserver", speed=10, until_ms=3000, post=post)
    assert sent["frames"] == 31
    hello = screen.until(lambda m: m["type"] == "hello" and m["payload"]["match_id"] == "m_7")
    assert hello["payload"]["mode"] == "live" and len(hello["payload"]["player_ids"]) == 22
    assert hello["payload"]["clubs"] == data.clubs
    screen.until(lambda m: m["type"] == "tracking_frame" and m["payload"]["t_ms"] == 3000)
    assert any(m["type"] == "event" and m["payload"]["match_id"] == "m_7" for m in screen.seen)
    health = client.get("/health").json()
    assert (health["match_id"], health["mode"], health["stream_t_ms"]) == ("m_7", "live", 3000)
    assert len(bb.query("events", match_id="m_7")) == sent["events"]
    assert client.get("/match/m_7/events", params={"to": 3000}).json()
    assert client.post("/ingest/tracking?match_id=m_7", json={"t_ms": 1}).status_code == 422
