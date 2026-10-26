"""evals-gate and latency arithmetic: a measured miss fails, reported rows do not; event-to-cue
latency per tier from trace rows."""

from evals.gate import check
from evals.latency import cue_latencies, summarise


def _row(status, measured="x"):
    return {"id": "r", "measured": measured, "threshold": "t", "status": status}


def test_gate_statuses():
    assert check({"rows": [_row("pass"), _row("reported")]}) == []
    assert check({"rows": [_row("fail")]})
    assert check({"rows": [_row("pending")]})
    assert check({"rows": [_row(None)]})


def test_cue_latency_per_tier():
    rows = [{"run_id": "a", "executor": "ingest", "status": "ok", "branch": None, "started_ms": 1000, "latency_ms": 0},
            {"run_id": "a", "executor": "cuebus", "status": "delivered", "branch": "explained", "started_ms": 12_000,
             "latency_ms": 900},
            {"run_id": "b", "executor": "ingest", "status": "ok", "branch": None, "started_ms": 0, "latency_ms": 0},
            {"run_id": "b", "executor": "cuebus", "status": "delivered", "branch": "fast", "started_ms": 1500,
             "latency_ms": 0},
            {"run_id": "b", "executor": "director", "status": "suppressed", "branch": "explained", "started_ms": 9,
             "latency_ms": 0}]
    lat = cue_latencies(rows)
    assert lat["explained"] == [12.0] and lat["fast"] == [1.6]
    s = summarise(lat, "live")
    assert s["tiers"]["explained"]["passed"] and s["tiers"]["fast"]["passed"] and s["passed"]
    assert summarise(lat, "replay")["passed"] is None
