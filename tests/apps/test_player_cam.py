"""Player-Cam: stats endpoint vs MCP player_stats, the fan card, only-involved cues, the overlay trail.

Regenerate the fixture dump after the golden match changes: `PYTHONPATH=packages python tests/apps/test_player_cam.py`.
"""

import copy
import json
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DUMP = ROOT / "tests" / "apps" / "data" / "player_stats_m_4242.json"  # not under tests/fixtures: no schema
READY = "() => window.__whyline && window.__whyline.ready === true"
PID, OTHER = "p_017", "p_045"            # Okafor (Verdant) and an Ironvale midfielder, both starters


def dump() -> None:
    import tempfile

    from blackboard import SqliteBlackboard
    from mcp_server.tools_core import MatchStore, player_stats

    store = MatchStore(SqliteBlackboard(Path(tempfile.mkdtemp()) / "bb.sqlite"))
    out = {"_about": "MCP player_stats for golden m_4242; regenerate: "
                     "PYTHONPATH=packages python tests/apps/test_player_cam.py",
           "players": {p: player_stats(store, "m_4242", p) for p in ("p_017", "p_031", "p_045")}}
    DUMP.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")


def get(base: str, path: str):
    with urllib.request.urlopen(f"{base}{path}", timeout=20) as r:
        return json.load(r)


def post(base: str, path: str, body: dict) -> dict:
    req = urllib.request.Request(f"{base}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.load(r)


@pytest.fixture(scope="module")
def cam_setup(api_server):
    post(api_server.base, "/replay/control", {"action": "speed", "value": 1})
    post(api_server.base, "/replay/control", {"action": "play"})
    post(api_server.base, "/replay/control", {"action": "seek", "value": "20:00"})
    deadline = time.monotonic() + 3
    while not 1_200_000 <= get(api_server.base, "/health")["stream_t_ms"] < 1_210_000:
        assert time.monotonic() < deadline
        time.sleep(0.02)
    now = get(api_server.base, "/health")["stream_t_ms"]
    api_server.bb.put("facts", {"match_id": "m_4242", "t_ms": now - 1000, "kind": "stat", "name": "decision_index",
                                "player": PID, "value": 71, "unit": "index_0_100"})
    base = json.loads((ROOT / "schemas" / "cue.schema.json").read_text())["examples"][0]
    ids = {}
    for n, (kind, layer, players) in enumerate([("player_tag", "player_tag", [PID]),
                                                ("milestone", "ticker", [PID]),
                                                ("milestone", "ticker", [OTHER]),
                                                ("goal", "lower_third", [])]):
        cue = copy.deepcopy(base)
        cue_id = f"c_{850_000 + n:06d}"
        cue.update(cue_id=cue_id, kind=kind, layer=layer, t_in_ms=now - 100, t_out_ms=now + 300_000, moment_id=None)
        cue["explain"]["counterfactual_id"] = None
        cue["text"]["headline"] = "32 km/h sprint" if kind == "player_tag" else f"{kind} involving {players or 'nobody'}"
        cue["targets"] = {"modes": ["analyst", "casual", "player_cam", "studio"], "clubs": ["any"], "players": players}
        api_server.bb.put("cues", cue)
        ids[n] = cue_id
    return ids


def test_endpoint_matches_mcp_player_stats_dump(api_server):
    want = json.loads(DUMP.read_text())["players"]
    for pid, stats in want.items():
        got = get(api_server.base, f"/match/m_4242/players/{pid}/stats")
        same = [k for k in stats if k != "decision_index"]   # MCP has none yet; the api adds the cached one
        assert {k: got[k] for k in same} == {k: stats[k] for k in same}, pid
        print(f"\n{pid}: touches {got['touches']}, sprints {got['sprints']}, top {got['top_speed_kmh']} km/h, "
              f"distance {got['distance_m'] / 1000:.1f} km")
        assert 3_000 < got["distance_m"] < 14_000
    with pytest.raises(urllib.error.HTTPError):
        get(api_server.base, "/match/m_4242/players/p_999/stats")
    # no blackboard fact for this player: the golden cache's rollout Decision Index
    cache = json.loads((ROOT / "data" / "matches" / "4242" / "cache" / "analytics" / "decision_index.json")
                       .read_text())["players"]
    got = get(api_server.base, f"/match/m_4242/players/{OTHER}/stats")
    assert got["decision_index"] == cache[OTHER]["index"] and got["decision_index_source"] == "cache"


def test_card_numbers_equal_player_stats(browser, fan_url, api_server, cam_setup, out_dir):
    want = json.loads(DUMP.read_text())["players"][PID]
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1)
    page = ctx.new_page()
    try:
        page.goto(f"{fan_url}?api=127.0.0.1:{api_server.port}&mode=player_cam&player={PID}")
        page.wait_for_function(READY, timeout=5000)
        card = page.get_by_test_id("player-cam-card")
        page.wait_for_selector("[data-testid=player-cam-card][data-loaded=true]", timeout=10000)
        value = lambda s: card.locator(f"[data-stat='{s}'] dd").inner_text().split()[0]  # noqa: E731
        assert value("touches") == str(want["touches"])
        assert value("sprints") == str(want["sprints"])
        assert value("top speed") == f"{want['top_speed_kmh']:.1f}"
        assert value("Decision Index") == "71"                  # blackboard fact
        assert float(value("distance")) > 3
        page.wait_for_selector(f".player-cam .tag[data-cue-id={cam_setup[0]}]", timeout=3000)
        assert "32 km/h" in card.locator(".tag").inner_text()
        page.screenshot(path=str(out_dir / "fan_player_cam.png"))
    finally:
        ctx.close()


def test_player_cam_gets_only_cues_involving_the_player(browser, fan_url, api_server, cam_setup):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1)
    page = ctx.new_page()
    try:
        page.goto(f"{fan_url}?api=127.0.0.1:{api_server.port}&mode=player_cam&player={PID}")
        page.wait_for_function(READY, timeout=5000)
        page.wait_for_function(f"() => window.__whyline.debug().received.includes('{cam_setup[1]}')", timeout=5000)
        page.wait_for_timeout(300)
        received = set(page.evaluate("() => window.__whyline.debug().received"))
        mine = set(cam_setup.values())
        assert received & mine == {cam_setup[0], cam_setup[1]}  # not the other player's, not the nobody goal
    finally:
        ctx.close()


def test_overlay_player_cam_draws_trail_and_tag(browser, overlay_url, api_server, cam_setup, out_dir):
    ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
    page = ctx.new_page()
    try:
        page.goto(f"{overlay_url}?record=1&api=127.0.0.1:{api_server.port}&mode=player_cam&player={PID}")
        page.wait_for_function(READY, timeout=5000)
        page.wait_for_function("() => (window.__whyline.layerStats().player_trail || {}).points >= 20", timeout=6000)
        tag = page.locator(f".player-tag[data-player={PID}]")
        tag.wait_for(state="attached", timeout=3000)
        assert "Okafor" in tag.inner_text()
        page.screenshot(path=str(out_dir / "overlay_player_cam.png"))
    finally:
        ctx.close()


if __name__ == "__main__":
    dump()
