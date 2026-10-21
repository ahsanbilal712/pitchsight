# WHYLINE progress log

Newest entry first. Each session appends one entry when it finishes a piece of work: date, ticket, what was done,
files touched, verification run, open issues. Keep entries short; details live in the files they point to.

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
