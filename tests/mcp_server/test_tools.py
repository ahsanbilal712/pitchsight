"""MCP core tools against the golden match: results, stored evidence, {error, code} on every failure, and one
round trip over Streamable HTTP."""

import asyncio
import json
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from blackboard import SqliteBlackboard
from mcp_server import tools_core as core
from mcp_server.server import TOOLS, build_server

ROOT = Path(__file__).resolve().parents[2]
M = "m_4242"
EVENTS = [json.loads(line) for line in (ROOT / "data/matches/4242/events.jsonl").read_text().splitlines()]


def arun(coro):
    """asyncio.run on a worker thread: Playwright's session-scoped sync API (tests/apps) keeps a loop running in
    the main thread, and asyncio.run refuses to start inside it."""
    with ThreadPoolExecutor(1) as pool:
        return pool.submit(asyncio.run, coro).result()


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    d = tmp_path_factory.mktemp("mcp")
    s = core.MatchStore(SqliteBlackboard(d / "bb.sqlite"), runtime_dir=d)
    yield s
    s.bb.close()


@pytest.fixture(scope="module")
def server(store):
    return build_server(store)


def call(server, name, args):
    res = arun(server.call_tool(name, args))
    return res.structured_content


def test_server_lists_the_core_and_recap_tools(server):
    names = [t.name for t in arun(server.list_tools())]
    assert names == list(TOOLS)


def test_query_events(server, store):
    out = call(server, "query_events", {"match_id": M, "t_from_ms": 0, "t_to_ms": 600_000, "kinds": ["shot"]})
    shots = out["result"]
    expected = [e["id"] for e in EVENTS if e["type"] == "shot" and e["t_ms"] <= 600_000]
    assert [e["id"] for e in shots] == expected
    p17 = call(server, "query_events", {"match_id": M, "t_from_ms": 0, "t_to_ms": 10**8, "player": "p_017"})["result"]
    assert p17 and all("p_017" in (e["player"], e["attrs"].get("recipient")) for e in p17)
    assert store.bb.get("events", "e_0001", M)["type"] == "match_metadata"   # loaded for the Fact Checker


def test_get_state(server):
    t = 1_800_000
    st = call(server, "get_state", {"match_id": M, "t_ms": t})
    goals = [e for e in EVENTS if e["type"] == "goal" and e["t_ms"] <= t]
    assert st["score"] == {"home": sum(e["team"] == "home" for e in goals),
                           "away": sum(e["team"] == "away" for e in goals)}
    assert st["clock"] == "30:00" and st["state"] in ("Settled", "Transitional", "Chaotic")
    assert 0 <= st["chaos"] <= 100 and {"control_home", "tempo", "chaos"} <= set(st["indices"])


def test_get_pitch_control_stores_a_snapshot(server, store):
    pc = call(server, "get_pitch_control", {"match_id": M, "t_ms": 1_800_000})
    assert pc["snapshot_id"] == "pc_018000" and 0 <= pc["home_share"] <= 1 and 0 <= pc["contested_frac"] <= 1
    assert {"home_defensive_third", "middle_third", "home_attacking_third"} <= set(pc["zones"])
    assert len(pc["overloads"]) <= 3 and all(o["label"].startswith("overload_") for o in pc["overloads"])
    assert store.bb.get("pitch_control", "pc_018000", M)["home_share"] == pc["home_share"]
    grid = Path(pc["grid_path"]) if Path(pc["grid_path"]).is_absolute() else ROOT / pc["grid_path"]
    import numpy as np
    assert np.load(grid)["grid"].shape == (34, 53)


def test_overloads_count_outnumbering():
    import numpy as np
    S = np.zeros((23, 6))
    S[:11, 0], S[:11, 1] = 10.0, 34.0           # home team all deep, in the middle
    S[11:22, 0], S[11:22, 1] = 20.0, 34.0
    S[[8, 9], 0], S[[8, 9], 1] = 95.0, 10.0      # two home attackers on the right of the box (low v)
    S[20, 0], S[20, 1] = 96.0, 12.0              # one defender
    over = core.overloads(S, team=0, period=1)
    assert over[0]["label"] == "overload_right_attacking_third" and over[0]["count"] == "2v1"


def _pass_point():
    p = next(e for e in EVENTS if e["type"] == "pass" and e["t_ms"] > 120_000)
    return p["t_ms"] - 100, p


def test_simulate_counterfactual_defaults_and_schema(server, store):
    t, p = _pass_point()
    t0 = time.perf_counter()
    cf = call(server, "simulate_counterfactual", {"match_id": M, "t_ms": t,
                                                 "alternative": {"kind": "carry", "actor": p["player"],
                                                                 "target": "n"}})
    print(f"simulate_counterfactual at {t} ms: {time.perf_counter() - t0:.2f} s, compute_ms {cf['compute_ms']}")
    schema = json.loads((ROOT / "schemas/counterfactual.schema.json").read_text())
    assert not [e.message for e in Draft202012Validator(schema).iter_errors(cf)]
    assert cf["n"] == 200 and cf["horizon_s"] == 8
    assert cf["actual"] == {"kind": "pass", "actor": p["player"], "target": p["attrs"]["recipient"],
                            "policy_prob": cf["actual"]["policy_prob"]}
    assert store.bb.get("counterfactuals", cf["counterfactual_id"], M)["t_ms"] == t
    assert store.bb.get("pitch_control", cf["pitch_control_snapshot_id"], M)
    again = call(server, "simulate_counterfactual", {"match_id": M, "t_ms": t, "alternative": {
        "kind": "carry", "actor": p["player"], "target": "n"}})
    assert again["counterfactual_id"] == cf["counterfactual_id"]


def test_invalid_alternative_is_a_structured_error(server):
    t, p = _pass_point()
    out = call(server, "simulate_counterfactual", {"match_id": M, "t_ms": t, "alternative": {
        "kind": "pass", "actor": p["player"], "target": "p_199"}, "n": 20})
    assert out["code"] == "invalid_alternative" and "error" in out


def test_player_stats(server):
    st = call(server, "player_stats", {"match_id": M, "player_id": "p_017"})
    mine = [e for e in EVENTS if e.get("player") == "p_017"]
    assert st["passes"] == sum(e["type"] == "pass" for e in mine) and st["name"].endswith("Okafor")
    assert st["shots"] == sum(e["type"] == "shot" for e in mine) and 0 <= st["completion"] <= 1
    assert st["sprints"] >= 0 and st["decision_index"] is None


def test_verify_claims_uses_the_fact_checker(server):
    shot = next(e for e in EVENTS if e["type"] == "shot" and e["player"] == "p_017")
    xg = shot["attrs"]["xg"]
    good = {"text": f"{xg:.2f} xG", "kind": "number", "value": round(xg, 2), "unit": "xg",
            "evidence_ids": [shot["id"]], "verified": False}
    out = call(server, "verify_claims", {"match_id": M, "claims": [good, {**good, "evidence_ids": ["e_99999"]}]})
    assert [c["verified"] for c in out["claims"]] == [True, False]
    assert out["claims"][1]["reject_reason"] == "evidence_not_found"


def test_get_budget(server):
    b = call(server, "get_budget", {"mode": "casual"})
    assert b["min_gap_s"] == 60 and b["hard_rules"]["leverage_floor_for_sliding_doors"] == 0.04 and "spend" in b
    assert call(server, "get_budget", {"mode": "pundit"})["code"] == "unknown_mode"


@pytest.mark.parametrize("name,args,code", [
    ("query_events", {"match_id": "m_9", "t_from_ms": 0, "t_to_ms": 1}, "unknown_match"),
    ("query_events", {"match_id": M, "t_from_ms": 10, "t_to_ms": 1}, "bad_range"),
    ("get_state", {"match_id": "4242", "t_ms": 0}, "bad_match_id"),
    ("get_state", {"match_id": M, "t_ms": 10**9}, "t_out_of_range"),
    ("get_pitch_control", {"match_id": M, "t_ms": -5}, "t_out_of_range"),
    ("simulate_counterfactual", {"match_id": M, "t_ms": 1000, "alternative": {"kind": "dance"}}, "bad_alternative"),
    ("player_stats", {"match_id": M, "player_id": "p_999"}, "unknown_player"),
    ("player_stats", {"match_id": M, "player_id": "p_200"}, "player_not_in_match"),
    ("verify_claims", {"match_id": "m_9", "claims": []}, "unknown_match"),
])
def test_errors_never_raise(server, name, args, code):
    out = call(server, name, args)
    err = out["result"][0] if "result" in out else out
    assert err["code"] == code and err["error"]


def test_streamable_http_round_trip(server):
    import uvicorn
    from mcp import Client

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    http = uvicorn.Server(uvicorn.Config(server.streamable_http_app(streamable_http_path="/mcp"),
                                         host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=http.run, daemon=True)
    thread.start()
    for _ in range(100):
        if http.started:
            break
        time.sleep(0.05)

    async def go():
        async with Client(f"http://127.0.0.1:{port}/mcp") as client:
            tools = await client.list_tools()
            res = await client.call_tool("get_budget", {"mode": "analyst"})
            return [t.name for t in tools.tools], res.structured_content

    try:
        names, budget = arun(go())
    finally:
        http.should_exit = True
        thread.join(5)
    assert set(TOOLS) <= set(names) and budget["max_per_10min"] == 12


def test_newsroom_mcp_client_over_http(server):
    """The newsroom's McpTools (mcp.Client) against the real server; Agent Framework's MCPStreamableHTTPTool
    fails to initialise against mcp 2.3.0, which is why McpTools does not use it."""
    import uvicorn

    from newsroom.tools import McpTools

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    http = uvicorn.Server(uvicorn.Config(server.streamable_http_app(streamable_http_path="/mcp"),
                                         host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=http.run, daemon=True)
    thread.start()
    for _ in range(100):
        if http.started:
            break
        time.sleep(0.05)

    async def go():
        tools = McpTools(f"http://127.0.0.1:{port}/mcp")
        try:
            events = await tools.call("query_events", {"match_id": M, "t_from_ms": 0, "t_to_ms": 5000})
            err = await tools.call("get_budget", {"mode": "nobody"})
            return events, err
        finally:
            await tools.close()

    try:
        events, err = arun(go())
    finally:
        http.should_exit = True
        thread.join(5)
    assert isinstance(events, list) and events[0]["id"] == "e_0001" and err["code"] == "unknown_mode"
