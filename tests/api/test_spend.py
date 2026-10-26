"""SpendGuard pricing, ledger format and caps."""

import json
import logging
from datetime import UTC, datetime

import pytest

from api.spend import LEDGER_FIELDS, SpendCapReached, SpendGuard

DAY = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


@pytest.fixture
def guard(tmp_path, monkeypatch):
    monkeypatch.delenv("WHYLINE_PER_MATCH_CAP_USD", raising=False)
    monkeypatch.delenv("WHYLINE_PER_DAY_CAP_USD", raising=False)
    return SpendGuard(ledger_path=tmp_path / "ledger.jsonl", clock=lambda: DAY)


def test_prices_from_budgets(guard):
    assert guard.price("claude-haiku-5-5", 1_000_000, 0) == pytest.approx(0.10)
    assert guard.price("claude-haiku-5-5", 0, 1_000_000) == pytest.approx(0.50)
    assert guard.price("claude-opus-5-5", 1_000_000, 1_000_000) == pytest.approx(24.0)
    assert guard.price("gemini-3.8-flash", 1_000_000, 1_000_000) == pytest.approx(4.50)


def test_batch_is_half_price_and_cache_reads_are_separate(guard):
    full = guard.price("claude-opus-5-5", 10_000, 2_000)
    assert guard.price("claude-opus-5-5", 10_000, 2_000, batch=True) == pytest.approx(full * 0.5)
    assert guard.price("claude-sonnet-5-5", 0, 0, cache_read=1_000_000) == pytest.approx(0.10)
    assert guard.price("claude-haiku-5-5", 0, 0, cache_read=1_000_000) == pytest.approx(0.01)


def test_unknown_model_is_an_error(guard):
    with pytest.raises(KeyError):
        guard.price("gpt-unknown", 1, 1)


def test_ledger_line_has_exactly_the_fields(guard):
    row = guard.record("narrator_fast", "claude-haiku-5-5", 1200, 80, "m_4242", "live", cache_read=800)
    lines = guard.ledger.read_text().splitlines()
    assert len(lines) == 1
    stored = json.loads(lines[0])
    assert tuple(sorted(stored)) == tuple(sorted(LEDGER_FIELDS))
    assert stored == row and stored["tokens_in"] == 2000
    assert stored["cost_usd"] == pytest.approx((1200 * 0.10 + 80 * 0.50 + 800 * 0.01) / 1e6)


def test_per_match_cap_raises(guard):
    guard.record("tactician_live", "claude-sonnet-5-5", 0, 250_000, "m_1", "live")   # $2.50
    with pytest.raises(SpendCapReached) as exc:
        guard.check("m_1")
    assert exc.value.scope == "match m_1"
    guard.check("m_2")                                                                # other matches unaffected


def test_per_day_cap_raises(guard):
    for i in range(5):
        guard.record("tactician_live", "claude-sonnet-5-5", 0, 200_000, f"m_{i}", "live")   # 5 x $2.00
    with pytest.raises(SpendCapReached) as exc:
        guard.check("m_new")
    assert exc.value.scope.startswith("day ")


def test_project_total_is_read_from_the_ledger_at_start_up(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    rows = [{"ts": f"2026-10-{d:02d}T10:00:00.000000Z", "role": "recap", "model": "claude-opus-5-5", "tokens_in": 0,
             "tokens_out": 0, "cost_usd": 9.99, "match_id": f"m_{d}", "mode": "live"} for d in range(1, 6)]
    rows.append({**rows[0], "ts": "2026-10-06T10:00:00.000000Z", "cost_usd": 0.06, "match_id": "m_6"})
    ledger.write_text("".join(json.dumps(r) + "\n" for r in rows))
    guard = SpendGuard(ledger_path=ledger, clock=lambda: DAY)
    assert guard.total == pytest.approx(50.01)
    with pytest.raises(SpendCapReached) as exc:
        guard.check("m_new")
    assert exc.value.scope == "project"


def test_warning_at_80_percent(guard, caplog):
    with caplog.at_level(logging.WARNING, logger="whyline.spend"):
        guard.record("tactician_live", "claude-sonnet-5-5", 0, 190_000, "m_9", "live")   # $1.90, 76%
        assert not caplog.records
        guard.record("tactician_live", "claude-sonnet-5-5", 0, 10_000, "m_9", "live")    # $2.00, 80%
    assert any("match m_9" in r.getMessage() for r in caplog.records)
