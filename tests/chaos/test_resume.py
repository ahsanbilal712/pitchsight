"""Kill switch and resume (TECH_PLAN 1.7, T-051): SIGKILL the worker between Tactician and Narrator, the supervisor
restarts it within 2 s, the run resumes from its checkpoint and delivers the same cue id as an uninterrupted run.
One run, replay mode (cached model outputs, no network): the CI chaos-resume job."""

import asyncio
import os
import re
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import pytest

from api.control import kill_when_ready
from blackboard import SqliteBlackboard
from cache import CacheClient, CacheManifest
from mcp_server.tools_core import MatchStore
from newsroom.executors.base import Deps
from newsroom.graph import build_workflow
from newsroom.worker import run_moment, start_message

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "data" / "matches" / "4242"
MOMENT = {"moment_id": "mo_00001", "match_id": "m_4242", "t_ms": 500, "clock": "00:00", "period": 1,
          "kind": "state_change", "leverage": None, "players": [], "team": None, "evidence_event_ids": ["e_0002"],
          "hypotheses": ["state:Transitional"], "fast": False, "status": "new"}
LINES = [r"kill target=newsroom run_id=(\S+) at_executor=tactician", r"restart pid=(\d+)",
         r"resume run_id=(\S+) checkpoint_id=(\S+)", r"cue (c_\d{6}) delivered resumed_from_checkpoint=(\S+)"]
NARRATOR_MS = 3000   # cached narrator latency: the window in which the kill lands


def arun(coro):
    """asyncio.run on a worker thread: Playwright's session-scoped sync API (tests/apps) keeps a loop running in
    the main thread, and asyncio.run refuses to start inside it."""
    with ThreadPoolExecutor(1) as pool:
        return pool.submit(asyncio.run, coro).result()


def build_cache(cache_dir: Path) -> CacheManifest:
    m = CacheManifest.new(GOLDEN, cache_dir=cache_dir, engine_hash="0" * 40)
    team = {"text": "Verdant", "kind": "team", "value_text": "verdant", "unit": "", "evidence_ids": ["e_0002"]}
    m.add(m.key("m_4242", "mo_00001", "tactician", "tactician@3", "gemini-4-argon", 4242), "explanation",
          {"json": {"why": "Verdant settle the opening minutes.", "claims": [team], "confidence": 0.6}},
          "explanations/ex_000001.json", moment_id="mo_00001", producer="tactician", version="tactician@3",
          model="gemini-4-argon", seed=4242, simulated_latency_ms=300)
    m.add(m.key("m_4242", "mo_00001", "narrator", "narrator@2", "gemini-3.8-flash", 4242), "fast_line",
          {"json": {"headline": "Verdant settle in", "body": "Verdant take control of the opening.",
                    "claims": ["Verdant"]}}, "lines/mo_00001.json", moment_id="mo_00001", producer="narrator",
          version="narrator@2", model="gemini-3.8-flash", seed=4242, simulated_latency_ms=NARRATOR_MS)
    m.save()
    return m


def uninterrupted_cue(tmp: Path, manifest: CacheManifest) -> dict:
    bb = SqliteBlackboard(tmp / "reference.sqlite")
    cache = CacheClient(manifest, speed=1e6)
    deps = Deps(bb=bb, llm=cache, rollout=cache, store=MatchStore(bb, runtime_dir=tmp))
    out = arun(run_moment(build_workflow(deps), start_message(MOMENT)))["outputs"]
    bb.close()
    assert len(out) == 1
    return out[0]


def stamp(line: str) -> datetime:
    return datetime.strptime(line.split(" ", 1)[0], "%Y-%m-%dT%H:%M:%S.%f")


def test_kill_between_tactician_and_narrator_resumes_with_same_cue(tmp_path, monkeypatch):
    manifest = build_cache(tmp_path / "cache")
    reference = uninterrupted_cue(tmp_path, manifest)
    log = tmp_path / "kill_resume.log"
    monkeypatch.setenv("WHYLINE_DEMO_LOG", str(log))     # the kill line is written by this process (the api's role)
    env = {**os.environ, "PYTHONPATH": str(ROOT / "packages"), "WHYLINE_MODE": "replay",
           "WHYLINE_BLACKBOARD": str(tmp_path / "bb.sqlite"), "WHYLINE_CHECKPOINT_DIR": str(tmp_path / "ckpt"),
           "WHYLINE_CACHE_DIR": str(tmp_path / "cache"), "WHYLINE_DEMO_LOG": str(log),
           "WHYLINE_WORKER_PIDFILE": str(tmp_path / "newsroom.pid"), "WHYLINE_REPLAY_SPEED": "1"}
    sup = subprocess.Popen([sys.executable, "-m", "newsroom.supervisor", "--mode", "replay", "--match", "m_4242"],
                           cwd=ROOT, env=env, stdout=open(tmp_path / "supervisor.out", "w"), stderr=subprocess.STDOUT)
    bb = SqliteBlackboard(tmp_path / "bb.sqlite")
    try:
        for _ in range(100):
            if (tmp_path / "newsroom.pid").exists():
                break
            time.sleep(0.1)
        bb.put("moments", MOMENT)
        killed = kill_when_ready(bb, timeout_s=90, pid_path=str(tmp_path / "newsroom.pid"))
        assert killed["killed"], killed
        cue = None
        for _ in range(600):
            cues = bb.query("cues", moment_id="mo_00001")
            if cues:
                cue = cues[0]
                break
            time.sleep(0.1)
    finally:
        sup.send_signal(signal.SIGTERM)
        sup.wait(15)
    worker_out = (tmp_path / "supervisor.out").read_text()
    assert cue is not None, worker_out[-3000:]
    assert cue["cue_id"] == reference["cue_id"] == "c_000011"
    assert cue["text"] == reference["text"] and cue["verified"] is True
    resumed = cue["provenance"]["resumed_from_checkpoint"]
    assert resumed and reference["provenance"]["resumed_from_checkpoint"] is None

    lines = log.read_text().splitlines()
    print("\n".join(lines))
    found = []
    for pattern in LINES:
        hit = next((i for i, line in enumerate(lines) if re.search(pattern, line)), None)
        assert hit is not None, f"missing log line {pattern!r}"
        found.append(hit)
    assert found == sorted(found)                       # the four lines, in order
    run_id = re.search(LINES[0], lines[found[0]]).group(1)
    assert re.search(LINES[2], lines[found[2]]).group(1) == run_id
    assert re.search(LINES[3], lines[found[3]]).group(2) == resumed == re.search(LINES[2], lines[found[2]]).group(2)
    restart_s = (stamp(lines[found[1]]) - stamp(lines[found[0]])).total_seconds()
    print(f"restart {restart_s:.2f} s after the kill")
    assert restart_s < 2.0
    assert bb.get("runs", run_id, "m_4242")["status"] == "done"
    red = [t for t in bb.query("traces", run_id=run_id) if t["status"] == "interrupted"]
    assert len(red) == 1 and red[0]["executor"] == "narrator"          # one red row for the studio, from the kill
    bb.close()
    out = os.environ.get("WHYLINE_KILL_LOG_OUT")
    if out:  # python -m pytest tests/chaos with WHYLINE_KILL_LOG_OUT=docs/evidence/kill_resume.log saves the demo log
        Path(out).write_text(log.read_text())


@pytest.mark.skipif(sys.platform == "win32", reason="SIGKILL")
def test_kill_waits_for_the_window(tmp_path):
    bb = SqliteBlackboard(tmp_path / "bb.sqlite")
    bb.put("runs", {"id": "run_x", "match_id": "m_1", "status": "running"})
    bb.put("traces", {"match_id": "m_1", "run_id": "run_x", "executor": "proposer"})
    out = kill_when_ready(bb, timeout_s=0.3, pid_path=str(tmp_path / "missing.pid"))
    assert out["killed"] is False                      # Tactician not finished: no kill
    bb.close()


def test_interrupted_row_written_once(tmp_path):
    from newsroom.resume import mark_interrupted

    bb = SqliteBlackboard(tmp_path / "bb.sqlite")
    run = {"id": "run_m_1_mo_00001", "match_id": "m_1", "moment_id": "mo_00001"}
    mark_interrupted(bb, run, at_executor="narrator")
    mark_interrupted(bb, run, checkpoint_id="cp")                     # the resume path: already marked
    rows = bb.query("traces", run_id=run["id"])
    assert [(r["executor"], r["status"]) for r in rows] == [("narrator", "interrupted")]
    bb.close()
