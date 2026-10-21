# Latency probe, day 3 (T-032)

One explained moment of the golden match, end to end through the real processes: `python -m mcp_server`
(Streamable HTTP) and `python -m newsroom.worker --mode live` on a fresh blackboard, models on Vertex AI
(gemini-3.8-flash for Proposer and Narrator, gemini-4-argon for the Tactician), every call through SpendGuard.
Script: `python scripts/latency_probe.py --moment-t 1419200`. Machine: the development Mac, with two other
sessions running (load average 25–40). Measured 22 Oct 2026 (local time).

**Moment.** 23:39, Verdant. Okafor (p_017) shoots; Scout leverage 0.056. The rule-proposed pass to Novacek
(p_020, policy probability 5.75%) raises the 8-second goal chance from 3.4% to 20.7% and the home win chance by
1.8 points (`cf` from 200 replays of 8 s, scripted_v1).

**Event to cue = 0.1 s (the Scout waits for the frame after the event) + Scout (3.7 ms p50, T-029) + the
pipeline below.** The pipeline is timed from the moment written to the blackboard to the cue written by the CueBus.

| Run | Config | Moment → cue | Proposer | Rollout | Tactician | Narrator | Cue | Spend |
|---|---|---|---|---|---|---|---|---|
| 1 | `max_tool_rounds` 2, Argon thinking low | **18.6 s** | 3.7 s | 2.3 s | 9.3 s (no tool calls) | 3.1 s | Verified Sliding Doors cue, model text | $0.013 |
| 2 | `max_tool_rounds` 1 (TECH_PLAN 1.13 response) | **37.5 s** | 5.2 s | 4.1 s | 24.0 s: two 12 s timeouts → template | 4.0 s: timeout → template | Verified template cue | $0.136* |

\* Run 2's spend is almost all worst-case estimates for the timed-out calls (`<role>:timeout` ledger rows: input
≈ characters / 4, output = `max_tokens` per possible round); the provider returns no usage for an abandoned call.

Run 1's cue (`c_000011`, verified by all eight Fact Checker rules):

> **Tobi Okafor creates dangerous opening** — A 2v1 overload on the left in the middle third yields 3.4%, while an
> option to Oren Novacek offers 20.65% and a 1.81% shift.

**Result on 22 Oct morning (Argon): the 15 s explained-cue target is not met** (superseded by the Flash update
below). Both runs exceed it. Run 1 is over by 3.6 s with the
Tactician making no tool calls; run 2 shows the variance: the same prompt that took 9.3 s timed out twice at 12 s.
`max_tool_rounds` is now 1 in `config/models.yaml` as TECH_PLAN 1.13 prescribes, but tool rounds were not the cost
here: one Argon call is. M1 item 4 records this number; the recorded judge run (T-080) and the latency work
(T-081) carry it.

## Update 22 Oct, after the owner's decision: Flash for the live Tactician

Owner decision: either Gemini model for the live Tactician, chosen by measurement; Argon stays for the golden batch
and recaps. On the Tactician prompt (2,422 input tokens) gemini-3.8-flash took 4.4–5.3 s at $0.003 (thinking off or
low made no difference), against 9–14 s for gemini-4-argon at thinking low. Probes over six golden decision moments
with a counterfactual (18:05, 24:57, 29:08, 45:15, 66:39, 83:07), `python scripts/latency_probe.py --moment-t
1085800,1497500,1748000,2715600,3999600,4987900`, machine load average 200–340 throughout:

| Probe | Change | Delivered | p50 | p95 (all delivered) | Spend |
|---|---|---|---|---|---|
| A | Flash Tactician (thinking off), Proposer thinking off | 6/6 | 14.5 s | 15.9 s | $0.038 |
| B | + the last 15 s of events in the Tactician prompt (no `query_events` round) | 6/6 | 11.0 s | 15.7 s | $0.037 |
| C | + rule alternatives' rollouts start while the Proposer runs | 5/6 | 11.5 s | 16.2 s | $0.042 |
| D | + hedged requests (a second identical call after 2.5 s Proposer/Narrator, 5 s Tactician) | 5/6 | **10.4 s** | **12.9 s** | $0.073 |

Per stage in D: Proposer 2.1–6.5 s, Rollout 0.02–2.8 s (prefetched), Tactician 3.5–4.4 s, Narrator 1.6–2.4 s. Every
delivered cue is verified by the Fact Checker. The undelivered moment (24:57) is not a timeout: the Proposer's output
was invalid twice and the rule found no alternative the engine gives at least 5%, so there is no Sliding Doors to
show. Probes C and D ran in a detached worktree of the committed code, because uncommitted engine edits in the shared
checkout made re-simulation diverge from the golden events at the time.

**Result: explained cue p95 12.9 s, under the 15 s target**, with five delivered cues in one probe; hedging costs
about $0.006 more per cue (the abandoned call gets a worst-case ledger row). The recorded judge run (T-080) measures
the p95 over three matches.

Fixes along the way: the worker's moment loop wrapped the blackboard watcher in a 0.5 s `wait_for`, which closed the
async generator on the first idle second and killed the worker (regression test added); the MCP counterfactual tool
re-checks its store inside the engine lock, so a prefetched rollout is never computed twice. T-032's live test
(`WHYLINE_LIVE_TESTS=1 pytest tests/newsroom/test_tactician.py -m live`) passes on Flash: $0.0034, schema-valid,
every claim cited.

## What else was measured

| Measurement | Number |
|---|---|
| gemini-4-argon, Tactician prompt (2,668 input tokens), thinking **high** (the models.yaml "medium → high" mapping) | 37 s, all 3,000 output tokens spent thinking, JSON cut off, $0.035 |
| same, thinking **low** | 14.4 s, 652 output tokens, valid explanation with 8 cited claims, $0.012 |
| Tactician in run 1 (thinking low, prompt asks for ≤ 6 claims) | 9.3 s |
| gemini-3.8-flash Narrator, thinking off (T-020) | 1.3–1.8 s warm in isolation; 3.1–3.4 s in the pipeline |
| gemini-3.8-flash Proposer, thinking low | 3.7–5.2 s; a cold first call exceeded its 6 s timeout |
| Cold first call to either model (worker start warms both) | 3–12.6 s |
| MCP `get_state` at minute 23, engine cold (re-simulates from kick-off) | 7.2 s; warmed before the probe (8.4–9.4 s) |
| MCP `simulate_counterfactual`, n 200, horizon 8 s, warm engine | 0.7–1.9 s per alternative |
| Implicit prefix caching of the league block | not observed: no cached tokens in any reported usage |

Changes made from these numbers: `tactician_live.effort` low (was medium → high), `max_tool_rounds` 1,
`narrator_fast.effort` none (T-020), both models warmed at worker start, worst-case ledger rows for timeouts.

## Levers not yet pulled (for T-081)

- Run the Proposer and the Tactician's league context in parallel with the rollouts, or skip the Proposer when
  `proposer_rule` already has three plausible alternatives (−3.7 s).
- Flash for the Tactician in live mode (Argon stays for the golden batch): one Flash call is 2–4 s.
- Shorter Tactician output (≤ 4 claims) and a shorter Narrator prompt.
- Narrator timeout 4 s is below its measured in-pipeline time on a loaded machine; the template then fills in.

## Spend

T-032 development spend on the ledger: **$0.59** (budget $0.50): $0.064 reported usage and $0.529 worst-case
estimates for ten timed-out calls (seven of them in two earlier attempts: an in-process trial with Argon thinking
high, and a probe run hit by the MCP client defect below, where every rollout failed and the Tactician timed out). The budget is exceeded on the ledger's conservative accounting; live calls for T-032
stopped there, so the live pytest (`-m live`) was not re-run after the probe.

## Defect found and fixed during the probe

Agent Framework 1.22.0's `MCPStreamableHTTPTool` cannot initialise against the pinned `mcp` 2.3.0
(`InitializeResult.protocolVersion` is `protocol_version` in mcp 2). Every MCP call from the worker failed. The
newsroom's `McpTools` now uses `mcp.Client`; `tests/mcp_server/test_tools.py::test_newsroom_mcp_client_over_http`
covers it.
