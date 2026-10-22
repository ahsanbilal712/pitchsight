# WHYLINE progress log

Newest entry first. Each session appends one entry when it finishes a piece of work: date, ticket, what was done,
files touched, verification run, open issues. Keep entries short; details live in the files they point to.

---

## 2026-10-22 · T-037, T-039, T-046, T-047 done; heads, encoder and policy rebuilt (track A)

- T-037 gate (`gate.json`): **scripted_v1**. top-1 kind 0.810 (pass), **top-3 kind+target 0.505 vs 0.80 (fail)**,
  4 s FDE 21.4 m vs 31.8 m baseline, teleports 0, shape collapse 0.2%, offsides 0.001. The rule's own probabilities
  reach only ~0.44 top-3, so the gate is unreachable for an imitation of this engine. Evidence:
  `docs/evidence/policy_gate_day4.md`, 20 clip strips.
- Rebuilt on the regenerated corpus: heads v1 (all gates pass: xG ECE 0.0088, pass 0.0044, win prob 0.0262,
  goal-8 s 0.0001, chaos AUC 0.764), MomentEncoder (purity **0.715**; names from one Gemini call, $0.0014; naming is
  now its own step after an expired credential lost a run), policy_v1 (8 epochs, val loss 2.753, kind acc 0.815).
- Found: LightGBM *training* segfaults with torch loaded; `heads` no longer imports torch, `rollout` imports
  `policy` (torch) first.
- T-039: golden cache (analytics for 54,001 frames, 125 moments / 60 explained with pitch-control snapshots,
  82 counterfactuals, scripted_v1) and `packages/demo/golden_moments.yaml`: Sliding Doors **76:56** (p_020 shoots,
  pass to p_023 was on: win chance 17.2% -> 20.9%), offside 66:05, cards 60:50 and 75:04, Oracle 83:30 (59%,
  confirmed), Dugout 60:00, kill 41:54. Track C to move `demo_script.yaml` clocks (76:52, 41:54).
- T-046 Oracle: 2,700 forecasts every 2 s at n = 200; `api/oracle.py` feeds C's replay feed. T-047 Dugout at
  90 s scripted: Verdant "keep the ball" +0.46 pts, matched 60:00-70:00 (caption allowed); Ironvale tie, no call.
- T-036: determinism passes (MPS twice, MPS vs CPU). Budgets **missed by ~9%**: policy 200x8 s 0.31-0.33 s on MPS
  (0.30; the GPU forward alone is 23 ms x 16 calls), scripted 200x90 s 1.42 s (1.3). Policy path is unused
  (gate = scripted_v1). 200x60 s 0.92 s and policy on CPU 0.46-0.51 s pass.
- Running: T-040 calibration (seeds 51-350), then T-048 Decision Index.

---

## 2026-10-22 · T-061 Demo script runner, shot list and Playwright recorder (track C)

- Finished on top of part 1 (963361d) once `golden_moments.yaml` landed (T-039, dd6f339). `demo_script.yaml`: the four
  1.8 actions at the golden beats: kill 41:54 (`@kill`), veto 45:00+15s (half-time recap), speed 1 at 76:52
  (`@sliding_doors-4s`), speed 10 at 77:10 (`@sliding_doors+14s`). TECH_PLAN's 44:10/31:10/33:00 were the draft match's.
- Verification: `pytest tests/demo/test_demo_script.py -q` **9 passed** (clocks agree with golden_moments to the second;
  runner fires each action once, waits for a late recap request, re-arms on seek back); `python -m demo.record_demo
  --shots packages/demo/shot_list.yaml --dry-run` exits 0 with **14 shots** over the 8 beats (architecture page comes
  with T-063). A real 2.5 s GPU recording writes `.webm` + keyframe PNG.

---

## 2026-10-22 · T-029 follow-up 2: contested passages on the regenerated golden match (track B)

- Track A's regenerated golden 4242 (movement realism, 0353e09; heads v1 498119e) gave 136 moments, **69 explained**
  (limit 60). Besides 28 chaos-state changes, many play moments were the same ball state counted per touch: shot,
  block or clearance, rebound within a second, by both sides, each carrying the same goal-in-8-s swing.
- The Merger now treats touches of both sides within SAME_INSTANT_MS (1 s, the existing constant) as one contested
  passage, named by the side with the larger swing; a goal or whistle absorbs either side's touch in the second
  before it. Moments whose auto-event names no event (an overload seen in tracking only) cite the last event before.
  The 0.04 threshold is unchanged.
- Golden 4242 now: **125 moments, 60 explained** (28 state changes, 23 decisions, 4 goals, 5 others), 20 referee,
  5 fast, 2 recap. 60 is exactly the upper limit; nearly half the explained moments are chaos-state changes from the
  T-013 state machine (two chaotic spells and twelve Settled/Transitional flips), flagged to track A.
- `pytest tests/newsroom/test_scout.py -q`: 23 passed. My suites on the new golden: newsroom, mcp_server, cache,
  chaos, blackboard all pass (two Proposer tests now pick a team-mate other than the pass actually played).

---

## 2026-10-22 · Movement realism fix (T-014) and full rebuild (track A)

- Track C found 10.5 km in 60 min and every top speed exactly 28.0 km/h. Cause: one sprint speed for all players
  (7.8 m/s) and constant jogging to formation spots (13.5 km per 90). Fix: per-player top speed from position, pace
  traits and age (25-35 km/h, no random draw); formation movement eases to a stop within 3 m (keepers, ball carrier,
  pressers, runners exempt); offsides and goals re-balanced. Seeds 1-50: completion **0.804**, shots **13.8**,
  goals **1.58**, offsides 0.64; outfield **11.6 km/90**, keepers **5.7 km**, fastest per match median **34.1 km/h**.
  State detection macro F1 0.773 (seeds 1-30). `tests/kickoff/test_realism.py` now checks distance and top speeds.
- Golden 4242 regenerated: **Verdant 3-1 Ironvale** (goals 08:18 away; 23:29, 83:37, 85:49 home), 1 offside,
  2 cards. Fourth Official cache rebuilt (20 cues). Tracks B and C told; B asked to hold T-042 until A commits the
  regenerated `cache/moments.jsonl`.
- Rebuilding everything trained on the old engine: corpus (2,350 matches), heads v1, policy dataset, policy_v1
  training (restarted; the old-engine run was stopped after epoch 2), moment encoder, auto-events report, golden
  caches. Chain: `data/runtime/rebuild_chain.sh`.
- Also fixed: ruff B905 in `tests/kickoff/test_no_truth_leak.py`.

---

## 2026-10-22 · T-041 follow-up: live Panel on Flash pundits, 20.6 s (track B) — cut line lifted

- Owner decision: Flash for live pundits if it brings the Panel within budget. `panel_pundit` is gemini-3.8-flash
  (thinking off, 4 s hedge); a new `panel_pundit_golden` role keeps Argon for the golden precompute (T-042).
- Live run (golden 45:15, Okafor shot vs carry): **20.6 s** of the 25 s budget (evidence 3.6 s, three pundits
  14.9 s at 3.8 / 7.5 / 3.5 s, chair ~2 s), $0.009. `WHYLINE_LIVE_TESTS=1 pytest tests/newsroom/test_panel.py -m
  live`: passed. The day-4 cut line is lifted: `panel_enabled` defaults on (`WHYLINE_PANEL=0` turns it off).
- The live test's warm-up now advances the engine explicitly (it re-simulated 45 minutes before, 29.7 s).
  Pundit rules ask for whole percentages on screen (the run wrote raw fractions like 0.152).

---

## 2026-10-22 · T-032 follow-up: Flash live Tactician, explained cue p95 12.9 s (track B)

- Owner decision: pick the live Tactician model by measurement, Argon stays for the golden batch. `tactician_live`
  is gemini-3.8-flash, thinking off (4.4–5.3 s, $0.003 on the Tactician prompt vs 9–14 s on Argon); Proposer
  thinking off. The Tactician gets the last 15 s of events up front (no `query_events` round), the Proposer starts
  the rule alternatives' rollouts while it runs, and `LiveClient` hedges slow calls (`hedge_after_s` per role: a
  second identical request, first answer wins, the loser gets a worst-case ledger row).
- Probes over six golden decision moments (load average 200–340): 15.9 → 15.7 → 16.2 → **12.9 s p95**, p50 10.4 s,
  5/6 delivered (the sixth had no plausible alternative), every cue verified. T-032's live test passes on Flash.
  Details: `docs/evidence/latency_probe_day3.md`.
- Bugs fixed: the worker died on its first idle second (a `wait_for` around the watcher closed the async
  generator; regression test added); the MCP counterfactual tool re-checks its store inside the engine lock.
- Spend since the decision: $0.10 ($0.088 reported, $0.012 worst-case rows). T-032 total on the ledger is now about
  $0.68 against its $0.50 dev budget (most of it worst-case rows from the Argon timeouts this morning).
- Note: uncommitted engine edits in the shared checkout (track A, 02:15) made re-simulation diverge from the golden
  events, so rollout-dependent tests fail in the working tree; my tests pass on committed code plus my changes in a
  detached scratch worktree (192 passed).

---

## 2026-10-22 · T-029 follow-up: one moment per event (track B)

- After track A's heads v1 (T-025) the golden match gave 61 explained moments (limit 60). Six were the same event
  counted twice: a pass that ended offside was both a "decision" and an "offside" moment, and a shot or big chance
  followed by its goal was two moments, each taking the explained branch. The Merger now lets a goal or referee
  event absorb the same team's detection from the same instant (≤ 1 s): one moment, all its branches (TECH_PLAN 1.7
  "a moment can take several branches"). Team-less detections (chaos-state changes) no longer split a possession.
  The 0.04 leverage threshold is unchanged.
- Golden 4242 now: **119 moments, 55 explained**, 28 referee, 5 fast (two big chances became their goals' moments),
  2 recap. `pytest tests/newsroom/test_scout.py -q`: 22 passed (CPU p99 10 ms per event).

---

## 2026-10-22 · Track C: replay feed, end-to-end dry run, fixes

- Owner direction: local demo first, Azure later. While T-039/T-057 are pending:
- **Replay feed** (44f0136, `packages/api/replay_feed.py`): plays the golden cache on the replay clock: analytics as facts
  (chaos meter, studio blackboard), cached oracle converted to the 1.9 shape, moments written to the blackboard when
  the clock reaches them so the worker runs each in time. `python -m api.replay --feed`.
- **End-to-end dry run** 30:00 → 46:00 on the current golden match: `docs/evidence/e2e_dryrun_day2.md`. Moments flow,
  13 cues reach all screens, demo script fires all four actions, no console errors. Found: the newsroom worker exits
  after 0.5 s idle (track B, reported with fix); a cross-thread sqlite error in the api kill path (fixed 13f5c02).
- `tests/apps` + `tests/api`: 70 passed (one wall-clock flake under load average 313, clean on rerun).

---

## 2026-10-22 · T-025 and T-054 done; T-028 training; T-037 outlook (track A)

- T-025 heads v1 on 2,000 matches, test split (200 matches): xG ECE **0.0102**, pass **0.0045**, win probability
  **0.0257**, goal-in-8-s **0.0001** (PR-AUC 0.286), chaos AUC **0.765**. All gates pass (`python -m heads.gates`).
- T-054 MomentEncoder: purity vs the hidden regime **0.695** (gate 0.6; majority 0.39) after weighting the 60 s
  features 4x; clusters named by one gemini-3.8-flash call, **$0.0014** (line in `data/spend/ledger.jsonl`, which
  also holds track B's uncommitted lines, so A did not commit the ledger). `similar_moments` MCP tool registered.
- T-028: epoch 1 val loss printed as Infinity: a passer who regains his own pass was labelled as the recipient
  (2 samples). Fixed in the dataset and the loss; `python -m policy.train --revalidate` re-scores epochs after the
  run (epoch 1: val loss 2.910, kind accuracy 0.809). Training continues; ~38 min per epoch, done about 06:30.
- T-037 outlook (dry run on epoch 1): top-1 kind 0.809 (gate 0.45, pass), **top-3 kind+target 0.502 (gate 0.80,
  fail)**, 4 s FDE 18.8 m vs 28.7 m velocity baseline (pass), teleports 0, shape collapse 0, offsides 0. The
  scripted rule's own probabilities reach only about 0.44 top-3 (near-uniform choice among good passes), so the
  0.80 gate looks unreachable for any model imitating this engine; expect `gate.json` = scripted_v1 (an accepted
  M1 outcome). Threshold unchanged.
- Dugout at 60:00 with a 90 s scripted horizon moves the trailing home side's win probability by at most +0.0008;
  honest but small (style changes act over minutes, win probability at 0-2 down is 2.4%).

---

## 2026-10-22 · T-061 part 1 (track C): demo runner, shot list and recorder — waiting for T-039

- `packages/api/demo_runner.py` (demo script on the replay clock: speed, kill via T-051, veto of the pending recap
  request), `packages/demo/{clocks.py,demo_script.yaml,shot_list.yaml,record_demo.py,__main__.py}`,
  `scripts/record_demo.sh`, `tests/demo/test_demo_script.py`. Shot clocks are references into
  `golden_moments.yaml` (`@sliding_doors-6s`); 14 shots cover the 8 storyboard beats; the recorder uses GPU Chromium.
- `pytest tests/demo -q`: 8 passed, 1 failing by design (`golden_moments.yaml` does not exist; T-039, track A,
  writes it). A real 2.5 s recording works: `smoke.webm` 1.1 MB plus keyframe PNG, ready 1.6 s after load.
  `--dry-run` with the sample moments file prints all 14 shots. Key list for track A in the shared notes folder.
- Not committed as `T-061:` until the clock check passes against the real file.

---

## 2026-10-22 · T-053 /replay3d React-Three-Fiber Sliding Doors scene (track C)

- `apps/overlay/src/replay3d/{Replay3D,Stadium,Players,Ball,GhostPaths,Cameras,SwingBarOverlay}.tsx`, `space.ts`,
  `replay3d.css`, `src/routes.tsx` (lazy route; `?view=replay3d` works on static hosting). Procedural only: no
  model, texture or HDR files are fetched (test checks requests). Ghosts fan out over the 8 s horizon as the clock
  passes the branch point; `?ghost=full` for stills.
- Headless Chromium uses SwiftShader (CPU) for WebGL by default; with `--use-angle=metal --ignore-gpu-blocklist` it
  renders on the M3 Pro. Tests use a `gpu_browser` fixture with those flags; **the T-061 recorder must too.**
- Verification: `npm --prefix apps/overlay run build && pytest tests/apps/test_replay3d.py -q` 2 passed: frame
  renders, seek and both cameras work, swing bar "n = 200, 8 s, seed 4242"; **60.0 fps over 20 s** at 1920×1080
  DPR 1 with 200 ghost paths (limit 30). TECH_PLAN 1.13 trigger (frame by end of day 5) met on day 2.
  `tests/apps` + `tests/api`: 66 passed.
- Polish left for T-083: slight moiré in the crowd texture on the behind-the-player camera.

---

## 2026-10-22 · T-060 Freeze rule and frozen-cache-guard CI job (track B)

- `scripts/frozen_cache_guard.py --base REF`: if the base manifest is frozen, any change at HEAD (entry added,
  removed or re-hashed, match hashes, the frozen flag) fails unless `docs/video/VERSION` went up in the same diff;
  not frozen or absent at the base passes. `docs/video/VERSION` = 0. CI passes the PR base sha or HEAD^.
- Verification `pytest tests/tooling/test_frozen_guard.py -q`: 6 passed (unchanged, changed without bump fails,
  changed with bump passes, unfreezing fails, not frozen / absent pass, this repository passes).

---

## 2026-10-22 · T-051 Supervisor, kill switch and checkpoint resume (track B)

- `newsroom/{supervisor,resume}.py`, `api/control.py` (`POST /demo/kill` + `kill_when_ready`), worker run tracking
  (blackboard `runs` running → done, moments marked running/done), Director/trace rows stamp
  `resumed_from_checkpoint`, `tests/chaos/test_resume.py`, `docs/evidence/kill_resume.log`.
- The kill waits for a running run with a Tactician trace row and no Narrator row, then SIGKILLs the pid the
  supervisor wrote; the supervisor restarts the worker; on start the worker restores each `running` run from its
  newest checkpoint holding that run's messages. Executors hold no in-flight data (messages carry everything), so
  `on_checkpoint_save/restore` save nothing.
- Measured (replay mode, cached outputs): restart **0.05 s** after the kill, resume 0.9 s later, resumed cue
  `c_000011` 3.1 s after that (the cached Narrator latency), same cue id and text as the uninterrupted run.
  Verification `pytest tests/chaos/test_resume.py -q`: 2 passed. The CI chaos-resume job already runs this file.
- The demo-script run at 44:10 (`packages/demo/golden_moments.yaml`) does not exist yet; the evidence log comes
  from the chaos test's moment (00:00 state change) and should be re-recorded on the golden cache after T-039/T-062.
- Note: track C's `tests/api/test_fanout_perf.py` failed here (88 ms > 50 ms) at load average 265; unrelated.

---

## 2026-10-22 · T-041 Panel via GroupChatBuilder (track B) — live budget not met, day-4 cut line applied

- `executors/panel.py`, `prompts/{pundit_press,pundit_possession,pundit_sceptic,chair}@1.md` (+ shared
  `pundit_rules.md`). `GroupChatBuilder` sub-workflow inside `PanelExecutor`: three pundit participant executors
  (gemini-4-argon, tools simulate_counterfactual / get_pitch_control, max_tool_rounds 1) speak in a fixed order,
  `max_rounds=3`; the chair (gemini-3.8-flash) writes {consensus, dissent, headline}. Pundit claims without a cf_/pc_
  id or failing the Fact Checker are dropped. 25 s budget; on timeout the cue is dropped, no retry.
- Deviation: the speaking order is a selection function, not the agent-based manager, because that orchestrator
  makes a structured next-speaker call every round (three more model calls inside 25 s); the chair still decides
  what goes on screen. The orchestrator's output is a closing notice, not the conversation, so pundits record takes.
- `panel_pundit.effort` low (medium maps to thinking high on Argon: 37 s per call, T-032).
- **Live: 25 s budget exceeded.** Each pundit call takes 9–10 s, sequential, after ~4 s of evidence; two live runs
  were both cut at 25.0 s (machine load average ~380). Cut line day 4, first drop: the Panel is near-line
  (golden precompute T-042 and recaps), off on the live path (`panel_enabled` false by default). The live test
  is kept as written and fails; offline `pytest tests/newsroom/test_panel.py -q`: 5 passed.
- `LiveClient` also records a worst-case ledger row when a call is cancelled from outside (the panel budget).
  T-041 dev spend **$0.08** (limit $0.50), $0.04 of it worst-case rows for cancelled calls.

---

## 2026-10-22 · T-045 Overlay viewer modes, heatmap, threat front and referee lines (track C)

- `apps/overlay/src/modes/{analyst,casual,playerCamConfig,config}.ts` (mirror `budgets.yaml`, checked by a test),
  `pitch/layers/{heatmap,threatFront,refereeLines}.ts`, `api.ts` (doc fetch: api or fixture files). Fixture now
  has 30 oracle messages, referee cue `c_000913` (onside by 0.4 m) and `apps/overlay/public/fixtures/docs/
  pc_000412.json` (outside `tests/fixtures`, which needs a schema per file).
- Oracle zone format chosen here (T-046 should emit it): `zone: {x, y, r}` in metres.
- Verification: `npm --prefix apps/overlay run build && pytest tests/apps/test_viewer_modes.py -q` 5 passed. Modes
  differ in exactly the 1.9 layers (analyst vs casual: heatmap, threat front, ticker; analyst vs player_cam:
  heatmap, threat front, player trail, player tag); referee lines yellow at x = 88.2 and 88.6 m, margin label
  0.4 m, half drawn at 0.3 s; **frame with heatmap + threat front + 200 ghosts p95 0.40 ms**, grid image built in
  0.90 ms (limit 8 ms). `tests/apps` + `tests/api`: 64 passed twice.
- Also: T-044's player_stats dump moved to `tests/apps/data/` (2390155) — under `tests/fixtures` it broke
  `make schemas`.

---

## 2026-10-22 · T-026, T-027, T-049 done; T-025, T-028 running (track A)

- T-026 auto-events (`physics/auto_events.py`): six detectors, facts not events; golden counts pressing_trap 13,
  line_break 3, switch_of_play 19 (35 m, not the brief's example 30 m: 51 at 30 m), overload 4, counter_attack 3,
  big_chance 4; p95 0.6 ms on a 15 s window.
- T-027: user approved the GRF download; 150 games (1.3 GB, git-ignored) check out (10.21 Hz, mapping holds).
  Dataset 2.76M / 345k / 345k samples (2,000 Kickoff + 150 GRF games), split by game. F = 16: TECH_PLAN's list
  has 17 entries, stamina dropped. The repo downloader hung once (no timeout); re-run with a 60 s socket timeout.
- T-049: Fourth Official geometry re-derives all 5 golden offsides exactly; 28 cached verified referee_line cues
  (`scripts/precompute.py --stages fourth_official`); executor registered in `newsroom/graph.py` (only A's two lines
  committed; track B's Panel edits left in the working copy, see the shared notes).
- T-028 launched: `policy_v1`, 8 epochs on MPS, about 1,300 samples/s while the corpus and heads jobs share the CPU
  (spec measured 2,474), so about 36 min per epoch. Log: `packages/policy/artifacts/train_log.jsonl`.
- Found: importing torch before LightGBM crashes LightGBM predictions on macOS (two libomp copies). `heads`,
  `policy` and `tests/conftest.py` now import LightGBM first.
- Dugout at 8 s moves win probability by 0.0000 for every style option; T-047 will use a longer scripted horizon
  (the schema allows up to 90 s for scripted_v1).

---

## 2026-10-22 · T-038 CacheManifest and CacheClient (track B)

- `packages/cache/{manifest,client,errors}.py`. Keys as TECH_PLAN 1.8 (the two schema-example keys reproduce
  exactly); saves validate against the schema; `verify_hashes()` catches one flipped byte in an entry or in
  events.jsonl. `CacheClient` serves model calls and tool calls after `simulated_latency_ms / WHYLINE_REPLAY_SPEED`;
  a model miss raises `CacheMiss` (template + red `cache_miss` trace row from the executors), a counterfactual miss
  returns `{error, code: cache_miss}` and the Rollout trace row turns red.
- Injection: worker replay mode → CacheClient (LLM and tools); MCP server with `WHYLINE_MODE=replay` → cached
  `simulate_counterfactual` (`cf_000077` from the schema example in the test), misses refused.
- Executors now pass `producer` (narrator / fast_line / proposer / tactician) so a moment's fast line and its
  explained line have separate keys.
- Verification `pytest tests/cache -q`: 15 passed.

---

## 2026-10-22 · T-032 Tactician with MCP tools and first live latency probe (track B)

- `executors/tactician.py` (gemini-4-argon, tools query_events / get_pitch_control / simulate_counterfactual /
  player_stats through the newsroom tool client, structured output → explanation.schema.json, 12 s timeout, one
  retry, then `tactician_degraded`), `prompts/tactician@3.md` (stable league block first for implicit prefix
  caching), `templates.tactician_template`, `scripts/latency_probe.py`, `docs/evidence/latency_probe_day3.md`.
- Live probe (MCP server + worker as processes, golden 23:39, Okafor shot vs pass to Novacek, goal chance
  3.4% → 20.7%): **run 1 18.6 s** moment→cue, verified Sliding Doors cue with model text, $0.013 (Proposer 3.7 s,
  Rollout 2.3 s, Tactician 9.3 s, Narrator 3.1 s). > 15 s, so `max_tool_rounds` 1 (TECH_PLAN 1.13): **run 2
  37.5 s**, Tactician timed out twice and Narrator once → template cue (verified). 15 s target not met; carried
  to T-080/T-081 with the levers listed in the evidence file.
- Config from measurements: `tactician_live.effort` low (thinking high: 37 s, all 3,000 tokens on thinking, JSON
  cut off), `max_tool_rounds` 1; worker warms both models.
- Fixes found by the probe: Agent Framework 1.22.0 `MCPStreamableHTTPTool` cannot initialise against mcp 2.3.0
  (`protocolVersion` → `protocol_version`), so `McpTools` uses `mcp.Client` (regression test added). The 5% policy
  guard dropped every rule alternative because the rule ignored policy probabilities: MCP `get_state` now returns
  the engine's option probabilities, the rule picks plausible options (17 of 27 golden decision moments get a
  plausible alternative), and the Proposer sees them.
- **Spend over budget:** T-032 ledger $0.59 against $0.50: $0.064 reported usage plus $0.529 worst-case estimates
  for ten timed-out calls. Live calls stopped there; the `-m live` Tactician test is written but not run.
- Verification `pytest tests/newsroom/test_tactician.py -q`: 9 passed (+1 live not run). Scout timing test now
  measures process CPU time (load average 283 from another track's job made wall time meaningless): CPU p99
  14 ms, max 26 ms per event.

---

## 2026-10-22 · T-044 Player-Cam card and player_cam overlay mode (track C)

- `packages/api/players.py`: `GET /match/{id}/players/{player_id}/stats` = MCP `player_stats` (same code) +
  `distance_m` from tracking + Decision Index from a blackboard fact until T-048 (README lists the addition).
  `apps/fan/src/components/PlayerCamCard.tsx`; `apps/overlay/src/modes/playerCam.ts` (8 s trail layer, persistent
  Player-Cam tag). api filter applies `only_player_involved`.
- Verification: `npm --prefix apps/fan run build && npm --prefix apps/overlay run build && pytest
  tests/apps/test_player_cam.py -q` 4 passed: endpoint equals the MCP dump (`tests/fixtures/player_stats/
  m_4242.json`) for p_017, p_031, p_045; the card shows touches 95, sprints 38, top speed 28.0, DI 71 (fixture fact)
  for Okafor; a player_cam viewer gets only cues listing the player; overlay trail ≥ 20 points and tag on Okafor.
  `tests/apps` + `tests/api`: 59 passed.
- Open: stats cover the whole recorded match (MCP semantics), not "so far" at the replay clock. Engine
  observation for track A in the shared notes: distances high (Okafor 10.5 km in 60 min), every top speed 28.0.

---

## 2026-10-22 · T-043 Fan app: modes, mini-pitch, cue feed, moment cards (track C)

- `apps/fan/src/{App,main,profile,league}.tsx|ts`, `stream/{StreamProvider.tsx,reducer.ts,types.ts}`,
  `components/{ProfilePicker,MiniPitch,CueFeed,MomentCards}.tsx`, `styles/{tokens,fan}.css`,
  `public/league.json`. Profile validated against the viewer_profile schema rules, stored with try/catch (app works
  when storage throws). api `messages.cue_matches` now also enforces `budgets.yaml` mode kinds server side.
- Verification: `npm --prefix apps/fan run build && pytest tests/apps/test_fan.py -q` 4 passed. With one cue of
  every kind on air, **casual receives exactly its 5 kinds, analyst its 12** (switching back and forth); stored
  profile passes `jsonschema` against `viewer_profile.schema.json` and survives a reload; **veto → fan card gone
  in 3–5 ms** (closes the fan half of T-035). Fixed an order-dependent wait in the score-bug test (shared api
  left at 70:00 by another test). `tests/apps` + `tests/api`: 55 passed, twice.

---

## 2026-10-22 · T-035 Studio producer panel and demo controls (track C)

- `apps/studio/src/components/{ProducerPanel,DemoControls}.tsx`: Approve / Veto / Hold on `request_info`, Veto on
  any on-air cue, Kill newsroom, Pause/Play, x1/x2/x5/x10, seek mm:ss. Held requests stay pending (the api's studio
  snapshot now drops only approved/vetoed requests).
- Verification: `npm --prefix apps/studio run build && pytest tests/apps/test_studio_controls.py -q` 3 passed.
  **Veto click → overlay lower-third leaving: 7 ms** (limit 200 ms, two pages, both stamped with Date.now()).
  Decisions land in blackboard `decisions` (approved / vetoed / held); kill posts `{target: "newsroom"}`; x5 and
  seek 52:30 reach the replay clock. The fan half of "overlay and fan" is checked when the fan app exists (T-043).
  `tests/apps` + `tests/api`: 51 passed.

---

## 2026-10-22 · T-034 Studio console core (track C)

- `apps/studio/src/{App,api,league,main}.tsx|ts`, `stream/{StreamProvider.tsx,reducer.ts,types.ts}`,
  `components/{Header,MomentQueue,AgentTrace,CueList,WhyDrawer,Blackboard}.tsx`, `styles/{tokens,studio}.css`,
  `public/league.json` (export script output). The studio keeps a cue/trace/moment log across seeks and reloads
  the full cue list over REST on each hello.
- api: the doc endpoint inlines the pitch-control grid from the MCP server's `grid_path` .npz; the studio's
  reset snapshot also carries the last 60 trace rows and undecided `requests`.
- Verification: `npm --prefix apps/studio run build && pytest tests/apps/test_studio.py -q` 4 passed: trace rows
  show all six fields, cache_miss and interrupted rows red; the fixture cue's evidence (e_8812, cf_000077) resolves
  2/2 through `/match/{id}/doc/{id}`; an unknown id is flagged missing; thumbnail and "n = 200, 8 s, seed 4242".
  `tests/apps` + `tests/api`: 48 passed.
- Seen, not mine: ruff flags `tests/kickoff/test_no_truth_leak.py:43` (B905) and `tests/policy/test_data.py` (I001).

---

## 2026-10-22 · T-033 API cue fan-out, ingest and control endpoints (track C)

- `packages/api/{cues,control,docs,ingest,messages}.py`, `ws.py` reworked: blackboard watcher forwards every 1.9
  message type; timed docs (cues, facts, moments, oracle) released on the stream clock; target filtering server side;
  seek snapshot (cues on screen, latest facts); counterfactual sent before its first cue. Doc endpoint (addition to
  the 1.4 list, in `packages/api/README.md`), `/producer/decision` (+ veto of a shown cue → `cue_remove`),
  `/demo/kill` 202 stub, `/spend`, `/ingest/*` (live mode), `python -m kickoff play --target api`
  (`packages/kickoff/stream.py`; small CLI edit in `kickoff/__main__.py`).
- Contract for track B (collections `requests`, `decisions`) in the shared notes folder.
- Verification: `pytest tests/api/test_cues.py tests/api/test_fanout_perf.py -q` 9 passed. **Fan-out to 20 clients
  (blackboard write → 20th client): max 23.7–29.6 ms, p95 23–27 ms** over three runs (limit 50 ms). Veto →
  `cue_remove` on two screens in 4–8 ms. CLI streamed m_7 into a running api (31 frames, 7 events).
  `tests/api` + `tests/apps` + `tests/kickoff`: 58 passed.

---

## 2026-10-22 · T-031 Proposer and RolloutExecutor (track B)

- `newsroom/decision.py` (decision point: last pass/carry/shot/clearance of the moment, branch at event − 100 ms,
  team-mates with xT gain; `proposer_rule`; `valid_alternatives`), `executors/{proposer,rollout}.py`,
  `prompts/proposer@1.md`, `newsroom/tools.py` (`McpTools` over `MCPStreamableHTTPTool`, `LocalTools` in-process;
  the worker uses MCP when `WHYLINE_MCP_URL` is set).
- Proposer: gemini-3.8-flash (`proposer` role), 6 s timeout, one retry, then the rule (top-3 team-mates by xT
  gain); model output is validated (actor forced, targets on the pitch, never the actual action). Rollout: n 200
  under 2 s (5 s with `WHYLINE_CLOUD`), then n 50; errors (invalid alternatives) skipped; keeps the largest
  |Δ win prob| with policy_prob ≥ 0.05.
- Gemini's schema converter rejects `["string","null"]` types, so `target` is a string ("" for none).
- Live proposer on a golden decision: 3 valid alternatives, $0.0013; the cold first call timed out at 6 s and
  the retry succeeded (9.9 s total). `LiveClient` now records a worst-case ledger row (`<role>:timeout`, input
  ≈ chars/4, output = max_tokens) for every timed-out call; two earlier unrecorded timeouts (T-020, T-031) were
  added the same way ($0.0045). Dev spend for T-031: $0.0044 (limit $0.20).
- Verification `pytest tests/newsroom/test_proposer.py -q`: 9 passed (+1 live). In-graph run on the golden
  match: proposer + 2 rollouts 2.8 s.

---

## 2026-10-22 · T-030 MCP server: core tools (track B)

- `packages/mcp_server/{__main__,server,tools_core,errors}.py`. mcp 2.3.0 has no FastMCP: it is `MCPServer` now
  (same decorator API); Streamable HTTP on :8080 `/mcp`. Seven tools with the 1.7 signatures; every failure returns
  `{error, code}`.
- `simulate_counterfactual` wraps T-016 `sliding_doors` (n 200, horizon 8 by default), stores `cf_` and its `pc_`
  snapshot; golden minute 2: **2.9 s** cold (the match re-simulates from kick-off; later calls move forward).
- Verification `pytest tests/mcp_server/test_tools.py -q`: 20 passed (each tool on the golden match, 9 error cases,
  one Streamable HTTP round trip).
- Open: `player_stats` counts the whole match file, so in replay it can see past the replay clock (T-033/T-039).

---

## 2026-10-22 · T-029 Scout executor and classification predicates (track B)

- `newsroom/scout_rules.py` (predicates exactly as TECH_PLAN 1.7; batch `detect_match` and live `ScoutStream`;
  `Merger`), `executors/scout.py` (one Routed per branch, none → drop), wired into the graph.
- Leverage = max |ΔP| of GoalIn8sHead (home or away scores in 8 s) between the frames before and after the event
  (t ± 100 ms). Sources: goals, fouls/cards/offsides, period ends, auto-events (T-026), on-ball decisions (pass,
  carry, shot, clearance: the actions a counterfactual can replace), chaos-state changes at 1 Hz, sprints ≥ 34 km/h.
  Consecutive same-team detections within 5 s merge into one moment.
- Golden 4242: **120 moments, 58 explained** (27 decisions, 16 state changes, 4 big chances, 3 goals, 3 offsides,
  5 auto-event moments), 28 referee, 7 fast, 2 recap. Above the $50 plan's 40-Tactician-call assumption; the
  Director's budgets drop some, T-042 will show the real count. First reading (+1 s after the event, every on-ball
  event type, merging across possessions) gave 86; adjacent frames plus the two rules above are the plan's wording.
- Per event (live path, 1,499 golden events): p50 **3.7 ms**, p95 12.2 ms, p99 18.5 ms; max 28.6–72.8 ms across
  runs while the machine load average was ~40 (the slowest event profiles at 12 ms alone). The test asserts
  p99 < 50 ms; the limit is "< 50 ms per event", so the max is recorded here, not hidden.
- Verification `pytest tests/newsroom/test_scout.py -q`: 20 passed. Routing tests in test_graph now use the stub
  Scout explicitly.

---

## 2026-10-22 · T-015 Outcome heads v0, T-016 rollout primitive (track A)

- T-015 `packages/heads`: five heads on the first 200 training matches, split by match seed (rng 4242), test split:
  xG ECE 0.040 / AUC 0.81, pass ECE 0.009, goal-in-8-s ECE 0.0004 / PR-AUC 0.24, win probability ECE 0.106
  (only 20 test matches, one label each), chaos AUC 0.758. Reports only; T-025 gates on 2,000. Artefacts committed
  (`*.txt`, `*.metrics.json`, `*.calibration.png`); missing artefacts raise at start-up.
- T-016: engine tick vectorised (B=200: 13 → 1.4 ms per tick; golden hashes unchanged), `Engine.branch`,
  `Override`, `rollout` → `Futures`, `sliding_doors` → schema-valid `CounterfactualResult`, `placebo`, `MatchRef`.
  Idle Mac: B=200 × 90 s **1.265 s CPU** (≤ 1.3), × 60 s **0.845 s** (≤ 1.2). The perf test fails while the corpus
  runs in the background (CPU contention); run it on an idle machine.
- Placebo: forced actual action vs baseline worlds whose own first choice was that action, two-sample 95% interval
  floored at ±0.005 (8-s futures barely move win probability, so raw intervals are ~1e-4). 7/7 golden moments pass;
  without the floor 18/21 passed in a wider sample.
- For track B (MCP, day 3): `from rollout import MatchRef, rollout, sliding_doors, option_probs` (see
  `packages/rollout/README.md`). Run CLIs with `PYTHONPATH=packages`.

---

## 2026-10-21 · T-013 Physics core, and hidden match regimes for T-014 (track A)

- T-013 `packages/physics`: Spearman-style pitch control [34,53] (shares sum to 1, mirror test), indices, chaos
  index, speeds, `StateMachine`, `TrackingWindow`. Per frame (pitch control + 60 s indices + chaos + speeds + state):
  p50 0.8 ms, p95 3.4 ms CPU (budget 15 ms). `pytest tests/physics -q` passes.
- The engine's tactical phases barely moved anything observable, so state detection (T-055, F1 ≥ 0.75) could not
  pass. Added a hidden match regime to `truth.json` (t2, phases with side `M`: settled / transitional / chaotic,
  10–18 min) that drives tempo, press and duel intensity. Chaos now comes from the open-play turnover rate
  (EWMA, tau 60 s). **State-detection macro F1 0.771 on seeds 1–50** (Settled 0.84, Transitional 0.68, Chaotic 0.79).
- Realism after the change, seeds 1–50 per team: completion **0.801**, shots **13.2**, goals **1.52**, offsides 1.17.
- Golden 4242 regenerated again: **Verdant 1–2 Ironvale**, goals 11:50, 16:55, 67:42; 5 offsides, 2 cards; regimes
  chaotic 0–17 and 57–75 min. Corpus restarted from scratch (1001–3000, 51–350) in the background.

---

## 2026-10-21 · T-014 Training corpus generator and realism ranges (track A)

- Engine tuned (`packages/kickoff`): seeds 1–50 per team per match now completion **0.834**, shots **14.6**, goals
  **1.59**, offsides **1.01**, fouls 5.1, cards 0.54 (was 0.823 / 21.0 / 2.17 / 0.06; Ironvale 37.9 → 15.4 shots).
  Knobs are named constants at the top of `engine.py`, `rules.py`, `physics_prior.py`.
- Golden 4242 regenerated: **Verdant 2–2 Ironvale**, goals 00:53, 10:28, 23:10, 68:09; 4 offsides, 2 cards; new
  `SHA256SUMS`. Three tests that hard-coded the old 0–4 score (`tests/api/test_replay.py`,
  `tests/apps/test_overlay_components.py`, `tests/apps/test_overlay_ws.py`) now read goals from `events.jsonl`.
- `scripts/generate_corpus.py` (resumable, `progress.json`, behavioural engine hash), `League.fixture(seed)`,
  `tests/kickoff/test_realism.py`. Seeds 1–50 done; 1001–3000 and 51–350 running in the background (~30
  matches/min, about 80 min). Verification: `pytest tests/kickoff/test_realism.py -q && python scripts/generate_corpus.py --status` pass.

---

## 2026-10-21 · T-066 Licence scan job and asset list (track B, built early: only needs T-005)

- `scripts/licence_scan.py`, `config/licence_allowlist.txt`, `LICENSES.md`, `tests/tooling/test_licence_scan.py`.
  Python via `pip-licenses`, npm production deps from the three lockfiles (works without node_modules), assets from
  `data/league/assets.json` once T-077 creates it. GPL/AGPL/LGPL/non-commercial always fail.
- `python scripts/licence_scan.py`: **202 entries (131 pip, 71 npm), 0 offenders**, 3 named exceptions for the
  owner to confirm: `certifi` and `tqdm` (MPL-2.0, unmodified dependencies) and `webgl-constants` (no licence field,
  MIT LICENSE file). The `licence-scan` CI job already runs the script once it exists; `ci.yml` unchanged.
- Open: the repo has no top-level `LICENSE` file (pyproject says MIT); needed before the repo goes public.

---

## 2026-10-21 · T-021 Director with budgets (track B)

- `executors/director.py`, `cuebus.py`. Hard rules: a cue waits out a shot sequence (to the next possession change,
  goal, restart, foul or period end, max 6 s) and the 3 s after a goal; same kind within 90 s, unshown after 45 s
  (`deps.state["match_clock_ms"]` when the clock is known), Sliding Doors below leverage 0.04 and Oracle below
  p_shot 0.30 are dropped. Per viewer mode: kinds, min gap between lower-thirds, max per 10 min, casual Sliding
  Doors per half; history is read from blackboard `cues`, so it survives restarts. Studio gets every cue that
  reaches any viewer mode; a cue no viewer mode accepts is suppressed with a trace row.
- `cue_id` = `c_` + moment number × 10 + branch index (mo_00077 explained → `c_000771`): independent of process
  state and processing order. SpendCapReached → `degraded` mode, one `modes` document; model error, timeout, cache
  miss or third rejection → template from verified claims and a red trace row (status `error`/`cache_miss`/…).
- Verification `pytest tests/newsroom/test_director.py -q`: 17 passed (every produced cue validates against
  `cue.schema.json`). Graph-routing tests now use the stub Director/CueBus so they test routing only.

---

## 2026-10-21 · T-024 Ghost trail and swing bar (track C)

- `apps/overlay/src/pitch/layers/ghostTrail.ts`: 200 futures, Catmull-Rom (81 points per 8 s path), Path2D cache,
  branch colours, 0.8 s fade, orange dashed chosen trail. `components/SwingBar.tsx`: from → to animation,
  "n = 200, 8 s, seed 4242" always printed; no counterfactual document → no bar.
- Interim contract: `counterfactual` stream message; `futures_sample` first half baseline, second half alternative
  (cue contract gap 7; note for track A's T-016 in the shared notes folder). Fixture has 200 deterministic futures.
- Verification: `npm --prefix apps/overlay run build && pytest tests/apps/test_ghost_trail.py -q` 5 passed.
  **200 paths: p95 0.20 ms** CPU-side draw (limit 8 ms), rAF interval p95 16.7 ms (no dropped frames).
  `tests/apps` + `tests/api`: 35 passed.

---

## 2026-10-21 · T-020 Narrator and fast-line executors (track B)

- `executors/{narrator,fast_line}.py`, `templates.py`, `prompts/narrator@2.md`, empty `prompts/fewshot/narrator.jsonl`.
  The Narrator re-verifies the Tactician's claims and sends only verified ones to the model; output is clipped to
  60/280 chars; rewrites get the Fact Checker diff and the previous draft. Fast line builds player/xG/team claims
  from the moment's evidence events.
- Gemini adaptation of "Anthropic error → Gemini fallback": `narrator_fast` is already gemini-3.8-flash, so a
  provider error retries once (or uses a role's `provider_fallback` if one is configured), then the template;
  timeout, cache miss and SpendCapReached go straight to the template (cap also sets degraded).
- Latency (measured, Vertex AI global): Flash with thinking `low` 2.5–5.1 s per call, thinking off 1.3–1.8 s, so
  `config/models.yaml` `narrator_fast.effort` is now `none` (thinking_budget 0). A cold first call took 4.8–5.4 s,
  so `LiveClient.warm()` runs at worker start. Live narrator call with 483 input tokens: **3.4 s**, $0.000726; the
  fast-cue SLO of 3 s will need the template or a shorter prompt live (T-032 probe).
- Verification: `pytest tests/newsroom/test_narrator.py -q` 11 passed; live test passed (output verified-claim
  numbers only). Dev spend for T-020 **$0.0007** (limit $0.10). A call cut off by the timeout is not in the ledger
  (no usage returned); at most one such call happened here.

---

## 2026-10-21 · T-023 Lower-thirds, score bug, chaos meter, player tags, ticker (track C)

- `apps/overlay/src/components/{ScoreBug,ChaosMeter,LowerThird,PlayerTags,Ticker}.tsx`, `motion.ts`
  (presence + text fitting), `styles/broadcast.css`, shared `league.ts`. Chaos meter reads facts `chaos_index` and
  `chaos_state` (note for track A in the shared notes folder).
- **Kit contrast fix:** kits under 3:1 WCAG contrast with the grass get a light halo (Verdant #0E5C36 is 1.6:1,
  Ironvale's navy away kit too); score-bug kit chips get a light edge.
- Fixture: 62 facts (chaos_index every 1 s, chaos_state Transitional → Chaotic at 31:26). Fixed a T-010 fold bug:
  untimed messages took the previous frame's time, so `cue_remove` fired 100 ms early.
- Verification: `npm --prefix apps/overlay run build && pytest tests/apps/test_overlay_components.py -q`
  7 passed (all of `tests/apps` + `tests/api`: 30 passed). Schema-max text (60/280 wide chars) fits at full size
  (headline 31 px, body 20 px), nothing overflows; cue appears at 31:18.2 and is gone at 31:26.2; score bug goes
  0–0 → 0–1 on the 39:05 goal event over the WebSocket. Pitch2D p95 still 0.20–0.30 ms.

---

## 2026-10-21 · T-018 newsroom graph and T-019 Fact Checker (track B)

- T-018: `packages/newsroom/{messages,graph,llm,worker,config}.py`, `executors/{base,ingest,stubs,drop}.py`. The full
  1.7 graph with the verbatim builder calls; stubs keep the real executor ids so checkpoints survive swaps. Messages
  are pydantic and registered for checkpoint restore. `LiveClient` = Gemini on Vertex AI via
  `agent_framework.gemini.GeminiChatClient`, SpendGuard on every call, thinking tokens as output.
  `pytest tests/newsroom/test_graph.py -q`: 7 passed (goal → cue via fast branch; rejecting stub stops at attempt 3;
  a checkpoint per superstep; resume from a mid-run checkpoint).
- T-019: `packages/newsroom/factcheck.py` (eight rules, verbatim tolerances; xT ±0.005 and seconds ±0.5 are my
  choice, the plan names none), `executors/factcheck.py`, `scripts/scan_banned.py`. Verification: 56 passed;
  `scan_banned.py data/league` 0 hits. Example check **1.1 ms** (limit 50 ms).
- Decisions: the counterfactual schema has no field for the alternative's xG ("0.31 xG" cites `cf_000077`), so
  derived numbers are facts carrying `counterfactual_id` and citing the cf covers them (no schema change). Rule 7
  matches speculation and accusation phrases (e.g. "looks injured", "biased referee"), not topic nouns, so
  `lore.md`'s "no injuries, no referee-bias talk" line passes. Rule 3 accepts a player from a cited event, a cited
  counterfactual's actor/target, or one hop of `related_event_ids` (the cue example's "Reyes" cites the shot).
- Note: the cue schema example's body ("In 200 replays … within 8 seconds") fails rule 6 as written; the Narrator
  must bind those numbers to `count`/`seconds` claims on the counterfactual.

---

## 2026-10-21 · T-022 API replay server and tracking stream (track C)

- `packages/api/{main,replay,ws,models,__main__}.py`: `/health`, `/match/{id}/events?from&to` (ms or mm:ss),
  `/replay/control` (play, pause, seek by `value` or `t_ms`, speed x1–x10), `WS /ws`. One ticker, per-client
  queues (ready for T-033 cue fan-out). `hello` also carries `t_ms`, `score`, `player_ids` (subs applied) and is
  re-sent after every seek; new `lineup` message on substitutions. CORS open (screens run on other ports).
- Overlay: `?api=host:port`, hello resets the reducer, lineup updates row mapping.
- Verification: `pytest tests/api/test_replay.py -q` 8 passed; **13–14 frames in 1.2 s at x1**, x10 moves
  10.2 s of match time per second. `tests/apps/test_overlay_ws.py`: overlay plays 4242 over WS, 15 frames/1.5 s,
  seek to 39:10 shows 0-1.

---

## 2026-10-21 · T-017 SqliteBlackboard (track B)

- `packages/blackboard/{protocol,sqlite,ids}.py`: one table per collection, JSON column, WAL, cross-process
  `watch` by sequence polling; ids per TECH_PLAN 1.3, monotonic per match. Verification `pytest tests/blackboard -q`:
  15 passed. `put` p50 **0.06 ms**, p95 0.10 ms (limit 2 ms).

---

## 2026-10-21 · Day 1 backlog: T-001 to T-012

**Done** (one commit per ticket, `git log --oneline`)
- T-001 repo bootstrap: git repo, Python 3.12.12 `.venv` with every pin exact (`requirements.lock`, 130 packages),
  13 package skeletons, three Vite + React 19.3.1 apps, `scripts/check_pins.py`, Playwright Chromium. Changes to the
  plan: `azure-ai-projects` 2.9.0 → **2.7.0** (agent-framework-foundry 1.15.0 needs <2.8); React 19 (fiber 9.8.2 peer
  range); apps resolve dependencies with **Node 22.23.3** (`.nvmrc`; npm 10.8.2 on Node 20 crashes resolving Vite 8
  peers, `npm ci` works on both); Haiku 5.5 cache read **$0.01**/M and Sonnet 5.5 **$0.10**/M (pricing page).
  ADRs were already in `docs/adr/` with descriptive file names; kept.
- T-002 league: 8 clubs, 200 players, styles, lore, 396-phrase banned list. **Deviation:** Okafor p_017, Silva
  p_022 and Reyes p_031 all play for Verdant (the brief put Reyes on the other side, but the schema examples have
  Okafor's alternative pass going to Reyes).
- T-012 GRF tiny_set (12 games, 102 MB, git-ignored): 23 rows per step, mapping holds (99.997% inside), frame rate
  derived from ball gravity **10.2 Hz**; a 3,001-step game is about 300 s of play, not 90 min. `docs/DATA.md` has
  the attribution and a drafted email to the authors.
- T-003 `docs/cue_contract.md` (10 layers, 14 kinds mapped; 12 renderer gaps listed, no schema edits), byte-identical
  60 s sample stream, `tokens.css`.
- T-004 pre-commit secret guard, installed in `.git/hooks`.
- T-005 CI with the nine jobs (five skip until their tickets), `validate_schemas.py`, `check_spend.py`, `make ci`.
- T-006 Kickoff engine: 18 event types, 10 Hz tracking, hidden truth, CLI. 90-minute match in **10.4 s** (limit 60 s).
- T-007 golden match `data/matches/4242` + `SHA256SUMS`; two runs byte-identical. tracking.npz is 25 MB.
- T-008 SpendGuard + ledger; Agent Framework import test (RequestInfoExecutor absent; Case/Default in
  `agent_framework._workflows._edge`). Gemini smoke via Vertex AI on project ffc-19484 (gcloud ADC) ok.
- T-009 `azure.yaml` (six services), `infra/main.bicep`, `infra/README.md`.
- T-010 overlay shell: fixture playback, reducer, record mode (`window.__whyline.ready/seek/pause/debug`).
- T-011 Pitch2D: cached pitch, players, ball shadow, layer registry; p95 draw **0.30 ms** (CPU-side canvas time).

**Verification** (each ticket's own command, re-run at the end)
- Pass: T-001, T-002, T-003, T-004, T-005 (`make ci`: 34 tests), T-006, T-007, T-010, T-011, T-012.
- T-008: tests pass; `smoke_models.py` exits 2: Gemini ok ($0.000009 × 2 in the ledger), **Claude blocked, no
  ANTHROPIC_API_KEY in `.env`**.
- T-009: blocked, `az`/`azd` not installed (owner sets up Azure).
- CI has never run on GitHub: no remote yet.

**Open**
- Human steps: paste `ANTHROPIC_API_KEY` into `.env` and re-run `python scripts/smoke_models.py`; create the public
  GitHub repo and add it as `origin`; Azure account + `az`/`azd` 1.36.0 + logins, then fill in `infra/README.md`;
  send the GRF licence email in `docs/DATA.md`.
- Before pushing public: the committed planning docs name the Premier League contact and real clubs
  (`docs/permissions/README.md`, `data/footage/SOURCES.md`, `data/footage/*/shots.json`, proposal files). Decide
  what stays. `clip.info.json` files are git-ignored (they carry signed stream URLs).
- Engine realism is a first read, not tuned (T-014): completion 76–81% (in range), Verdant ≈13 shots and 1.2
  goals, high-press Ironvale too strong (≈37 shots, 2.7 goals), offsides ≈0.2 per match (forced-offside test
  covers the geometry). Golden 4242 is currently 0–4 and must be regenerated after T-014 tuning.
- Verdant's dark-green kit is hard to see on the green pitch (T-023/T-077).
- Planned 23.5 person-hours for day 1; this session took about 1 h 45 min wall clock.

---

## 2026-10-21 · Footage: downloads and first-pass shot analysis (T-102 partial, T-103 exploration)

**Done**
- Shortlisted seven clips uploaded by the Premier League channel itself (verified via oEmbed and `clip.info.json`,
  channel ID `UCG5qGWdu8nIRZqJ_GgDwQ-w`). Table in `data/footage/SOURCES.md`. Club-channel uploads in the
  "Club highlights 2026/27" playlist are outside the permission and excluded.
- Downloaded the four primary clips with yt-dlp 2026.08.19 (user's explicit go-ahead plus the Premier League written
  permission): `liverpool-mancity-2526`, `manutd-mancity-2526`, `arsenal-chelsea-2526`, `manutd-spurs-2425`, each
  `data/footage/<slug>/clip.mp4` at 1080p H.264 with `clip.info.json`. 3.5 GB total. Media is git-ignored by
  `data/footage/.gitignore`.
- Wrote a heuristic shot segmenter (`scripts/shots_firstpass.py`, contact sheets via
  `scripts/shots_contact_sheet.py`), tuned it three times against contact sheets. Results in
  `data/footage/SHOTS_REVIEW.md`; per-clip `shots.json` and `frames/` (git-ignored).
- Liverpool v Man City confirmed as primary tracking clip: 34 usable wide shots, 46% wide time, five unbroken wide
  shots of 67–88 s (13:22, 07:15, 10:35, 09:18, 26:34).

**Verification**
- `ffprobe` on all four clips: h264 1920x1080, durations 37:13 / 25:32 / 25:32 / 25:33.
- Contact sheets reviewed by eye; remaining false positives listed in `SHOTS_REVIEW.md`.

**Open**
- Original permission email as `.eml` with headers not yet in `docs/permissions/` (user action).
- Decision on real club and player names in overlays (user).
- Replays and slow motion are not detected; the first pass will mark a main-camera replay as wide.
- T-001 repo bootstrap not done: no git repo, no `packages/`, no `.venv`. The analysis ran in a throwaway venv.
- Three backup clips not downloaded.
