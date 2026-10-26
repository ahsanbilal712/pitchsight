"""Studio console: header, moment queue, agent trace, cue list, Why? drawer, blackboard.

The api's blackboard is seeded the way the newsroom fills it (the fixture cue c_000912 with its explanation,
counterfactual, pitch-control snapshot and evidence events), then the studio is opened against that api.
"""

import copy
import json
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "stream" / "sample_stream.jsonl"
READY = "() => window.__whyline && window.__whyline.ready === true"


def example(name: str) -> dict:
    return copy.deepcopy(json.loads((ROOT / "schemas" / name).read_text())["examples"][0])


def control(base: str, **body) -> dict:
    req = urllib.request.Request(f"{base}/replay/control", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.load(r)


def seed_newsroom(bb) -> None:
    """What the newsroom leaves in the blackboard after explaining moment mo_00077."""
    events = [json.loads(line)["payload"] for line in FIXTURE.read_text().splitlines()
              if json.loads(line)["type"] == "event"]
    bb.put_many("events", events)                               # e_8809, e_8811, e_8812, …
    bb.put("counterfactuals", example("counterfactual.schema.json"))
    bb.put("explanations", example("explanation.schema.json"))
    # 34 x 53 home share: Verdant (home) controls the right half where the overload is
    grid = [[round(0.25 + 0.5 * c / 52, 2) for c in range(53)] for _r in range(34)]
    bb.put("pitch_control", {"snapshot_id": "pc_000412", "match_id": "m_4242", "t_ms": 1_874_000,
                             "home_share": 0.5, "contested_frac": 0.31, "grid": grid})
    bb.put("moments", {"moment_id": "mo_00077", "match_id": "m_4242", "t_ms": 1_874_000, "clock": "31:14",
                       "kind": "big_chance", "leverage": 0.09, "players": ["p_017", "p_031"], "status": "explained"})
    bb.put("facts", {"match_id": "m_4242", "t_ms": 1_875_000, "kind": "index", "name": "chaos_index",
                     "value": 67.4, "unit": "index_0_100"})
    run = {"match_id": "m_4242", "run_id": "run_m_4242_mo_00077", "moment_id": "mo_00077", "branch": "explained"}
    for executor, model, latency, tin, tout, hit, status in [
        ("scout", None, 3, 0, 0, None, "ok"),
        ("proposer", "gemini-3.8-flash", 1420, 2100, 180, True, "ok"),
        ("tactician", "gemini-4-argon", 5200, 9100, 640, False, "cache_miss"),
        ("narrator", "gemini-3.8-flash", 0, 0, 0, None, "interrupted"),
        ("panel", None, 48, 0, 0, None, "error"),
    ]:
        bb.put("traces", {**run, "executor": executor, "model": model, "latency_ms": latency, "tokens_in": tin,
                          "tokens_out": tout, "cache_hit": hit, "status": status, "started_ms": 0})
    bb.put("cues", example("cue.schema.json"))


@pytest.fixture
def studio(page, studio_url, api_server):
    if not api_server.bb.query("cues", match_id="m_4242", cue_id="c_000912"):
        seed_newsroom(api_server.bb)
    control(api_server.base, action="speed", value=1)
    control(api_server.base, action="seek", value="31:20")
    page.goto(f"{studio_url}?api=127.0.0.1:{api_server.port}")
    page.wait_for_function(READY, timeout=5000)
    return page


def test_trace_rows_show_fields_and_red_for_miss_or_interrupted(studio, out_dir):
    rows = studio.locator("[data-testid=agent-trace] tbody tr")
    rows.first.wait_for(timeout=3000)
    studio.wait_for_function("() => document.querySelectorAll('[data-testid=agent-trace] tbody tr').length >= 5")
    tactician = studio.locator("[data-testid=agent-trace] tr[data-executor=tactician]")
    cells = tactician.locator("td").all_inner_texts()
    assert cells == ["mo_00077", "tactician", "gemini-4-argon", "5200 ms", "9100 / 640", "miss", "cache_miss"]
    assert "red" in tactician.get_attribute("class")
    assert "red" in studio.locator("tr[data-executor=narrator]").get_attribute("class")
    assert "red" in studio.locator("tr[data-executor=panel]").get_attribute("class")
    assert studio.locator("tr[data-executor=proposer]").get_attribute("class") is None
    assert studio.locator("tr[data-executor=proposer] td").nth(5).inner_text() == "hit"
    studio.screenshot(path=str(out_dir / "studio.png"))
    assert not studio.errors, studio.errors


def test_cue_list_moments_blackboard_and_header(studio):
    row = studio.locator("[data-testid=cue-list] li[data-cue-id=c_000912]")
    row.wait_for(timeout=3000)
    assert "Okafor shoots. Reyes was free." in row.inner_text()
    assert row.locator("[data-testid=cue-verified]").inner_text() == "✓"
    assert row.locator("[data-testid=cue-status]").inner_text() == "auto"
    studio.locator("[data-moment-id=mo_00077]").wait_for(timeout=3000)
    assert "Okafor" in studio.locator("[data-moment-id=mo_00077]").inner_text()
    studio.locator("[data-fact=chaos_index]").wait_for(timeout=3000)
    assert "67.4" in studio.locator("[data-fact=chaos_index]").inner_text()
    assert studio.get_by_test_id("mode-badge").inner_text().lower().startswith("replay")
    assert "m_4242" in studio.get_by_test_id("match").inner_text()


def test_drawer_resolves_every_evidence_id(studio, out_dir):
    studio.locator("[data-testid=cue-list] li[data-cue-id=c_000912]").click(timeout=3000)
    drawer = studio.get_by_test_id("why-drawer")
    drawer.wait_for(timeout=2000)
    links = drawer.locator("a.evidence")
    ids = sorted(set(links.evaluate_all("els => els.map(e => e.dataset.evidence)")))
    assert ids == ["cf_000077", "e_8812"]                        # the fixture cue's claims
    studio.wait_for_function("""() => [...document.querySelectorAll('[data-testid=why-drawer] a.evidence')]
        .every(a => a.dataset.status === 'ok')""", timeout=5000)
    resolved = drawer.get_by_test_id("evidence-resolved").inner_text()
    assert resolved.startswith("2/2")
    links.filter(has_text="e_8812").first.click()
    assert '"type": "shot"' in drawer.get_by_test_id("evidence-doc").inner_text()
    # thumbnail from the pc_ grid and the counterfactual mini-chart with n, horizon, seed
    drawer.get_by_test_id("pc-thumb").wait_for(timeout=3000)
    assert drawer.get_by_test_id("pc-thumb").get_attribute("data-has-grid") == "true"
    assert drawer.get_by_test_id("cf-provenance").inner_text() == "n = 200, 8 s, seed 4242"
    studio.screenshot(path=str(out_dir / "studio_drawer.png"))
    drawer.get_by_test_id("drawer-close").click()
    drawer.wait_for(state="detached", timeout=1000)
    assert not studio.errors, studio.errors


def test_missing_evidence_is_flagged(studio, api_server):
    cue = example("cue.schema.json")
    cue.update(cue_id="c_000913", t_in_ms=1_878_300, t_out_ms=1_886_000)
    cue["explain"]["claims"][0]["evidence_ids"] = ["e_9999"]   # nothing has this id
    api_server.bb.put("cues", cue)
    row = studio.locator("[data-testid=cue-list] li[data-cue-id=c_000913]")
    row.wait_for(timeout=3000)
    row.click()
    studio.wait_for_function("""() => document.querySelector(
        '[data-testid=why-drawer] a.evidence[data-evidence=e_9999]')?.dataset.status === 'missing'""", timeout=5000)
    api_server.bb.put("cues", {**cue, "producer_status": "vetoed"})  # leave the shared api as it was
