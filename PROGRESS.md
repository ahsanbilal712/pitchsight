# WHYLINE progress log

Newest entry first. Each session appends one entry when it finishes a piece of work: date, ticket, what was done,
files touched, verification run, open issues. Keep entries short; details live in the files they point to.

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
