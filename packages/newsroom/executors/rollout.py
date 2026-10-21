"""RolloutExecutor: simulate each proposed alternative through the MCP tool `simulate_counterfactual` and keep the
largest |delta win probability| among alternatives the policy gives at least 5% (TECH_PLAN 1.7; audit B.2 guard 1;
T-031). An alternative the engine cannot play comes back as an error and is skipped, never shown. Each call has
`timeout_s` (2 s locally, 5 s in Azure) at n = 200, then one try at n = 50.
"""

from __future__ import annotations

import asyncio
import os
import time

from agent_framework import WorkflowContext, handler

from newsroom.executors.base import NewsroomExecutor
from newsroom.messages import Proposals, RolloutDone
from newsroom.tools import is_error

MIN_POLICY_PROB = 0.05
N, N_FALLBACK, HORIZON_S = 200, 50, 8.0


def timeout_s() -> float:
    return float(os.environ.get("WHYLINE_ROLLOUT_TIMEOUT_S") or (5.0 if os.environ.get("WHYLINE_CLOUD") else 2.0))


async def simulate(tools, match_id: str, t_ms: int, alt: dict, limit: float) -> tuple[dict, int]:
    """(result or {error, code}, n used)."""
    args = {"match_id": match_id, "t_ms": t_ms, "alternative": {k: alt[k] for k in ("kind", "actor", "target")},
            "horizon_s": HORIZON_S}
    for n, wait in ((N, limit), (N_FALLBACK, limit * 2.5)):
        try:
            return await asyncio.wait_for(tools.call("simulate_counterfactual", {**args, "n": n}), wait), n
        except TimeoutError:
            continue
    return {"error": f"timed out at n={N} and n={N_FALLBACK}", "code": "timeout"}, 0


def choose(results: list[dict]) -> dict | None:
    """Largest |delta_win_prob_home| among valid results whose alternative has policy_prob >= 0.05."""
    shown = [r for r in results if not is_error(r) and (r["alternative"].get("policy_prob") or 0) >= MIN_POLICY_PROB]
    return max(shown, key=lambda r: abs(r["delta_win_prob_home"]), default=None)


class RolloutExecutor(NewsroomExecutor):
    @handler
    async def roll(self, msg: Proposals, ctx: WorkflowContext[RolloutDone]) -> None:
        started = time.perf_counter()
        m, d = msg.moment, msg.decision
        results, summary = [], []
        if d and msg.alternatives and self.deps.rollout is not None:
            for alt in msg.alternatives:
                res, n = await simulate(self.deps.rollout, m.match_id, d["t_ms"], alt, timeout_s())
                results.append(res)
                if is_error(res):
                    summary.append({**alt, "skipped": res.get("code", "error")})
                else:
                    summary.append({**alt, "n": n, "counterfactual_id": res["counterfactual_id"],
                                    "policy_prob": res["alternative"].get("policy_prob"),
                                    "delta_win_prob_home": res["delta_win_prob_home"]})
        best = choose(results)
        if best is not None:
            best = {**best, "moment_id": m.moment_id}
            self.deps.bb.put("counterfactuals", best)
        out = RolloutDone(**msg.hop(self.id).model_dump(exclude={"alternatives"}), alternatives=summary,
                          counterfactual=best)
        self.trace(out, started, status="ok" if best else "no_counterfactual",
                   counterfactual_id=best and best["counterfactual_id"], tried=len(results))
        await ctx.send_message(out)
