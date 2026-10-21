"""SpendGuard: prices every model call, appends it to the ledger and enforces the caps (ADR-011, T-008).

Usage around each model call:

    guard = SpendGuard()
    guard.check(match_id)                       # raises SpendCapReached before spending more
    ... call the model ...
    guard.record(role, model, tokens_in, tokens_out, match_id, mode, cache_read=..., batch=...)

Prices are USD per 1M tokens from config/budgets.yaml. `tokens_in` counts uncached input; cache reads are
priced at the model's cache_read rate; batch calls are priced at batch_discount (0.5x). The ledger line
stores total input (uncached + cache reads) and exactly the fields
{ts, role, model, tokens_in, tokens_out, cost_usd, match_id, mode}. Totals are rebuilt from the ledger at
start-up, so the project cap holds across processes and days. The per-match cap applies to every mode.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BUDGETS = ROOT / "config" / "budgets.yaml"
LEDGER_FIELDS = ("ts", "role", "model", "tokens_in", "tokens_out", "cost_usd", "match_id", "mode")
log = logging.getLogger("whyline.spend")


class SpendCapReached(RuntimeError):
    """A cap is reached; the Director catches this and switches to degraded mode."""

    def __init__(self, scope: str, spent: float, cap: float) -> None:
        super().__init__(f"{scope} spend ${spent:.4f} reached cap ${cap:.2f}")
        self.scope, self.spent, self.cap = scope, spent, cap


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SpendGuard:
    def __init__(self, budgets_path: str | Path = BUDGETS, ledger_path: str | Path | None = None,
                 clock: Callable[[], datetime] = _utc_now) -> None:
        cfg = yaml.safe_load(Path(budgets_path).read_text())["spend"]
        self.prices = {k: v for k, v in cfg["prices_usd_per_1m"].items() if isinstance(v, dict)}
        self.batch_discount = float(cfg["prices_usd_per_1m"].get("batch_discount", 1.0))
        self.per_match_cap = float(os.environ.get("WHYLINE_PER_MATCH_CAP_USD") or cfg["per_match_cap"])
        self.per_day_cap = float(os.environ.get("WHYLINE_PER_DAY_CAP_USD") or cfg["per_day_cap"])
        self.project_cap = float(cfg["project_total_cap"])
        self.warn_at = float(cfg.get("warn_at_fraction", 0.8))
        path = ledger_path or os.environ.get("WHYLINE_SPEND_LEDGER") or cfg["ledger_path"]
        self.ledger = Path(path) if Path(path).is_absolute() else ROOT / path
        self.clock = clock
        self._lock = threading.Lock()
        self._warned: set[str] = set()
        self.total = 0.0
        self.per_match: dict[str, float] = defaultdict(float)
        self.per_day: dict[str, float] = defaultdict(float)
        if self.ledger.exists():
            for line in self.ledger.read_text().splitlines():
                if line.strip():
                    self._add(json.loads(line))

    # ------------------------------------------------------------------ pricing
    def price(self, model: str, tokens_in: int, tokens_out: int, cache_read: int = 0, batch: bool = False) -> float:
        if model not in self.prices:
            raise KeyError(f"no price for model {model!r} in config/budgets.yaml")
        p = self.prices[model]
        cost = (tokens_in * p["in"] + tokens_out * p["out"] + cache_read * p.get("cache_read", p["in"])) / 1e6
        return cost * (self.batch_discount if batch else 1.0)

    # ------------------------------------------------------------------ caps
    def _add(self, row: dict) -> None:
        cost = float(row["cost_usd"])
        self.total += cost
        if row.get("match_id"):
            self.per_match[row["match_id"]] += cost
        self.per_day[str(row["ts"])[:10]] += cost

    def _scopes(self, match_id: str | None) -> list[tuple[str, float, float]]:
        today = self.clock().strftime("%Y-%m-%d")
        scopes = [("project", self.total, self.project_cap), ("day " + today, self.per_day[today], self.per_day_cap)]
        if match_id:
            scopes.append(("match " + match_id, self.per_match[match_id], self.per_match_cap))
        return scopes

    def check(self, match_id: str | None = None) -> None:
        """Raise SpendCapReached if any cap that applies to the next call is already reached."""
        with self._lock:
            for scope, spent, cap in self._scopes(match_id):
                if spent >= cap:
                    raise SpendCapReached(scope, spent, cap)

    # ------------------------------------------------------------------ ledger
    def record(self, role: str, model: str, tokens_in: int, tokens_out: int, match_id: str | None, mode: str,
               cache_read: int = 0, batch: bool = False) -> dict:
        cost = self.price(model, tokens_in, tokens_out, cache_read=cache_read, batch=batch)
        row = {"ts": self.clock().strftime("%Y-%m-%dT%H:%M:%S.%fZ"), "role": role, "model": model,
               "tokens_in": int(tokens_in + cache_read), "tokens_out": int(tokens_out), "cost_usd": round(cost, 8),
               "match_id": match_id, "mode": mode}
        with self._lock:
            self.ledger.parent.mkdir(parents=True, exist_ok=True)
            with self.ledger.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, separators=(",", ":")) + "\n")
            self._add(row)
            for scope, spent, cap in self._scopes(match_id):
                if spent >= self.warn_at * cap and scope not in self._warned:
                    self._warned.add(scope)
                    log.warning("spend %s at $%.4f, %.0f%% of the $%.2f cap", scope, spent, 100 * spent / cap, cap)
        return row

    def summary(self, match_id: str | None = None) -> dict:
        today = self.clock().strftime("%Y-%m-%d")
        return {"project_usd": round(self.total, 6), "day_usd": round(self.per_day[today], 6),
                "match_usd": round(self.per_match[match_id], 6) if match_id else None,
                "caps": {"project": self.project_cap, "day": self.per_day_cap, "match": self.per_match_cap}}
