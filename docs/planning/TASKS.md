# WHYLINE — Executable Backlog

Version 1.0, 21 October 2026. Sources: `TECH_PLAN.md` (sections 1.1–1.14), `DEMO_MASTERPLAN_50USD.md` (frozen decisions, §8 build sequence, §9 acceptance checklist), `FEASIBILITY_AUDIT.md` Part E (corrections), `ZERO_COST_ML.md` §2 and §7, `schemas/*.schema.json`, `config/{models.yaml,budgets.yaml,pins.txt,.env.example}`. If this file disagrees with TECH_PLAN, TECH_PLAN wins and this file gets fixed.

## How to use this file

1. Pick the lowest-numbered open ticket for your owner code whose "Depends on" tickets are all done.
2. Open a fresh Claude Code session at the repo root. Paste the ticket's **Brief**. The session reads the named documents first, then builds.
3. A ticket is done when every acceptance criterion holds and the **Verification** command exits 0 on a second machine or in CI. Commit as `T-NNN: <title>`.
4. Never lower a threshold to pass. Record the measured number in the ticket's report file, then apply that day's cut line (see "Cut lines").

| Code | Owner | Domain |
|---|---|---|
| A | Engine and ML | kickoff, physics, heads, policy, rollout, fourth_official, evals |
| B | Agents and cloud | blackboard, mcp_server, newsroom, cache, spend, infra, docs, CI |
| C | Screens and video | api replay/stream, apps/overlay, apps/studio, apps/fan, /replay3d, demo, video |

**IDs.** `T-NNN`, three digits, numbered in the order tickets appear. Every ticket depends only on lower IDs. "(optional)" marks tickets that can be dropped with no effect on M1 or M2. "Human step:" marks actions a person must do or approve (accounts, credentials, downloads, uploads, emails, submission).

**Milestones.** **M1** = day 7, Tue 27 Oct: submittable build, tag `v0.1`, video v1. **M2** = day 14, Tue 3 Nov: flawless build, tag `v1.0`, video v2. Everything after day 7 is additive; nothing after day 7 changes the golden cache without bumping `docs/video/VERSION` and re-recording (TECH_PLAN 1.8).

| Day | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Date | 21 Oct | 22 | 23 | 24 | 25 | 26 | **27 M1** | 28 | 29 | 30 | 31 | 1 Nov | 2 | **3 M2** |

**Conventions.**
- TECH_PLAN short paths (`evals/…`, `demo/…`, `policy/…`, `newsroom/…`, `api/…`) live under `packages/`, for example `packages/evals/results.md`, `packages/demo/demo_script.yaml`.
- Each `packages/<name>/` folder is the import package itself (`packages/mcp_server/server.py` imports as `mcp_server.server`). Root `pyproject.toml` sets pytest `pythonpath = ["packages"]`.
- Large downloads and corpora go in git-ignored `data/grf/` and `data/matches/corpus/`. The golden match `data/matches/4242/` is committed.
- Seeds: 1–50 evaluation (full tracking), 51–350 calibration hold-out, 1001–3000 training corpus, 4242 golden (`match_id = m_4242`). Never mix them.
- Live API tests carry `@pytest.mark.live` and run only when `WHYLINE_LIVE_TESTS=1`.
- Front-end commands: `npm --prefix apps/<app> run build`. Front-end smoke tests use Playwright for Python (`tests/apps/`), so no extra JS test runner is needed.

**Rules every session follows.**
- No secrets in files, logs or commits. Read keys only from the variable names in `config/.env.example` (`ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `AZURE_*`, `APPLICATIONINSIGHTS_CONNECTION_STRING`, `FOUNDRY_PROJECT_ENDPOINT`).
- Every model call goes through `SpendGuard` (T-008) and lands in `data/spend/ledger.jsonl`. Project cap $50, per match $2.50, per day $10 (`config/budgets.yaml`).
- English only. No voice, no TTS, no audio in cues, no Localizer (ADR-010).
- Never used: gfootball; `RequestInfoExecutor` (use `ctx.request_info()` + `@response_handler`); `sv.ByteTrack` (use `trackers.ByteTrackTracker`); ffmpeg for HLS ID3 metadata; the `agent-framework[all]` metapackage; `agent-framework-mcp` or `HostedMCPTool`; YOLOv8/ultralytics weights; sn-gamestate; Veo.
- Learned rollouts are decision-only and capped at 8 s (ADR-002, audit E.1). Futures past 8 s are valued by `GoalIn8sHead` and labelled as estimates.
- Runtime models are Gemini since 21 Oct 2026 (ADR-004 Revision 1): `gemini-4-argon` for reasoning roles, `gemini-3.8-flash` for volume roles, both on Vertex AI. Where a ticket below says Opus, Sonnet, Haiku or "Anthropic Batch API", read the role in `config/models.yaml` and Vertex AI batch prediction instead. Count thinking tokens as output; structured output via `response_json_schema` (`config/models.yaml` header).

## Dependency order

- The graph is acyclic by construction: every "Depends on" names a lower ID.
- Day 1 parallel start: **T-001 (B, 2.5 h), T-002 + T-012 (A, 2.5 h together) and T-003 (C, 2.5 h) depend on nothing**, so all three owners work from hour 0 and every other day-1 ticket starts when T-001 lands at hour 2.5.
- Cross-owner hand-offs inside a day are ordered morning to afternoon: day 2 (T-013 before T-016 before B's MCP work on day 3), day 4 (T-037 gate → T-038 manifest → T-039 rollouts → T-042 Batch), day 6 (T-054 and T-057 before T-062 recording).

**Critical path to day 7:** T-001 → T-006 → T-007 → T-013 → T-015 → T-016 → T-030 → T-031 → T-032 → T-041 → T-042 → T-050 → T-057 → T-062 → T-063 → T-069 → T-071.
Feeder chains that join it: policy (T-012 → T-027 → T-028 → T-036 → T-037 → T-039 → T-042; if the gate fails, T-037 still closes on day 4 with scripted_v1) and screens (T-010 → T-011 → T-022 → T-033 → T-034 → T-035 → T-061 → T-062).

**Planned hours per owner per day** (8 h available each day).

| Owner | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | D10 | D11 | D12 | D13 | D14 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 8 | 8 | 7.5 | 7.5 | 8 | 8 | 6.5 | 8 | 5 | 3 | 6 | 4 | 3 | 0 |
| B | 7.5 | 8 | 7 | 7.5 | 8 | 8 | 6.5 | 7 | 5 | 8 | 5 | 3 | 3 | 2 |
| C | 8 | 8 | 8 | 8 | 7 | 8 | 4 | 7 | 6 | 3 | 4 | 5 | 4 | 1.5 |

Unplanned hours are buffer. Days 8–14 carry deliberate slack because "flawless" means rework time.

---

## Day 1 — Wed 21 Oct

### T-001 Repo bootstrap, package skeletons and dependency pins
- **Owner:** B · **Day:** 1 · **Estimated hours:** 2.5
- **Depends on:** none
- **Files:** `pyproject.toml`, `requirements.lock`, `.gitignore`, `packages/{kickoff,physics,heads,policy,rollout,blackboard,mcp_server,newsroom,fourth_official,cache,api,evals,demo}/{pyproject.toml,__init__.py,README.md}`, `apps/{overlay,studio,fan}/package.json` + lockfiles, `config/pins.txt`, `config/budgets.yaml` (Haiku cache price only), `scripts/check_pins.py`, `docs/adr/ADR-001.md` … `ADR-012.md`, `data/{league,matches/4242,spend,runtime}/.gitkeep`, `tests/`, `infra/`
- **Scope:** In: git init, Python 3.12 venv, exact pins, package and app skeletons, ADR files. Out: any feature code; rfdetr/trackers/supervision/opencv (installed in T-090 only); gfootball (never).
- **Acceptance criteria:**
  - No non-comment line in `config/pins.txt` lacks an exact version; every "pin at T-001" item now has a version and licence.
  - `torch.backends.mps.is_available()` is True in `.venv`; `agent_framework`, `mcp`, `anthropic`, `fastapi`, `lightgbm` import.
  - `npm --prefix apps/overlay ci` succeeds with three 0.186.1, fiber 9.8.2, drei 10.7.9.
- **Verification:** `python scripts/check_pins.py && python -c "import agent_framework, mcp, anthropic, fastapi, lightgbm, torch; assert torch.backends.mps.is_available()"`
- **Brief:**
  ```text
  Read TECH_PLAN.md 1.2 (ADRs), 1.4 (repository layout and package rules), 1.10 (secrets, CI), config/pins.txt, config/.env.example, FEASIBILITY_AUDIT.md Part A row 35 (install agent-framework-core plus named extras; the [all] metapackage stalls).
  git init. .gitignore: .env, .venv, .checkpoints/, data/runtime/, data/grf/, data/matches/corpus/, node_modules/, packages/demo/out/, packages/policy/artifacts/*.pt (weights stay private until T-089 settles the GRF licence).
  Create the 13 packages under packages/ (folder = import package, own pyproject.toml, README restating the 1.4 interface) and root pyproject.toml (ruff config, pytest pythonpath = ["packages"], marker "live").
  Install every verified pin in config/pins.txt exactly. For each "pin at T-001" line (mcp, anthropic, google-genai, fastapi, uvicorn, websockets, jsonschema, lightgbm, scikit-learn, pandas, pytest, ruff, playwright, react, react-dom, vite, typescript) install the current release and write version + licence into pins.txt.
  Add, pinned the same way with licences: azure-cosmos and azure-monitor-opentelemetry-exporter (TECH_PLAN says pin at T-001), azure-identity, opentelemetry-sdk, azure-messaging-webpubsubservice, matplotlib, httpx, pytest-asyncio, pip-licenses.
  Node apps: Vite + React + TS skeletons with exact versions; three/fiber/drei in apps/overlay only. Check fiber 9.8.2's react peer range; if it needs React 19, pin React 19 and fix the "18.3.x" comment in pins.txt.
  Look up the Haiku 5.5 cache-read price on Anthropic's pricing page and correct config/budgets.yaml (its comment asks for this at T-001).
  scripts/check_pins.py: every non-comment pins.txt line has an exact version; pip freeze matches; gfootball absent. Write requirements.lock from pip freeze; run `python -m playwright install chromium`.
  Write docs/adr/ADR-001..012 from TECH_PLAN 1.2. Human step: approve the package downloads; create the public GitHub repo (rules 4.4) and add it as origin.
  Acceptance: python scripts/check_pins.py && python -c "import agent_framework, mcp, anthropic, fastapi, lightgbm, torch; assert torch.backends.mps.is_available()"
  ```

### T-002 Fictional league and banned-names list
- **Owner:** A · **Day:** 1 · **Estimated hours:** 1.5
- **Depends on:** none
- **Files:** `data/league/clubs.json`, `data/league/players.json`, `data/league/styles.json`, `data/league/lore.md`, `data/league/banned_names.txt`, `scripts/check_league.py`
- **Scope:** In: 8 clubs, 200 players, style profiles, lore, banned list, authored in this Claude Code session at $0. Out: images (T-077), any API call.
- **Acceptance criteria:**
  - 8 clubs, 200 players (`p_001`…`p_200`, 25 per club, ≥ 2 goalkeepers per club); Okafor, Silva and Reyes exist in the two golden clubs.
  - No league string matches a phrase in `banned_names.txt` (whole phrase, case-insensitive).
- **Verification:** `python3 scripts/check_league.py`
- **Brief:**
  ```text
  Read DEMO_MASTERPLAN_50USD.md §4 (Claude Code writes the league at no API cost) and §7 (storyboard names), TECH_PLAN 1.4 kickoff (League: clubs, players, style profiles loaded from data/league/*.json), 1.7 Fact Checker rule 7, 1.12 (no trademarks).
  Write, with no API calls: clubs.json (id, name, short_name, city, home/away kit hex colours, rivalries, history paragraph, crest brief), players.json (id p_001..p_200, name, club, position, shirt, traits, one-line backstory), styles.json (per club: press_height, tempo, width, directness, line_height, each 0-1), lore.md.
  Golden match = clubs[0] (home) v clubs[1] (away). Put Okafor and Silva on one side and Reyes on the other, as the §7 storyboard needs.
  banned_names.txt: real clubs, leagues, competitions, broadcasters and current top-flight players, one full phrase per line (e.g. full names, never bare surnames such as "Silva").
  scripts/check_league.py, stdlib only: counts, unique ids, 2+ goalkeepers per club, hex colours valid, no banned phrase in any league string.
  Acceptance: python3 scripts/check_league.py exits 0.
  ```

### T-003 Cue contract sign-off, sample stream fixture and broadcast design tokens
- **Owner:** C · **Day:** 1 · **Estimated hours:** 2.5
- **Depends on:** none
- **Files:** `docs/cue_contract.md`, `scripts/make_sample_stream.py`, `tests/fixtures/stream/sample_stream.jsonl`, `apps/overlay/src/styles/tokens.css`
- **Scope:** In: a renderer's review of `cue.schema.json` (every layer and kind mapped to a component), a 60 s hand-built stream so screens can start before the engine exists, CSS design tokens (colours, type scale, 5% title-safe area at 1920×1080). Out: schema changes (any change follows TECH_PLAN 1.3 versioning and needs B's agreement); tooling (T-001 installs it).
- **Acceptance criteria:**
  - `docs/cue_contract.md` maps all 10 `layer` values and 14 `kind` values to an overlay, studio or fan component.
  - Fixture has 1 `hello`, 600 `tracking_frame` (10 Hz, JSON shape of TECH_PLAN 1.3), ≥ 6 `event`, ≥ 1 `cue` (the schema example) and 1 `fact`; every line parses.
- **Verification:** `python3 scripts/make_sample_stream.py --check`
- **Brief:**
  ```text
  Read TECH_PLAN 1.2 ADR-007 (Cue Sheet is the product boundary), 1.3 (tracking frame JSON), 1.9 (WebSocket message table and screen component trees), schemas/cue.schema.json and schemas/counterfactual.schema.json (their examples).
  Write docs/cue_contract.md: for each cue layer and kind, the component that renders it (names from 1.9), and any field a renderer needs that the schema lacks (list only; do not edit schemas).
  Write apps/overlay/src/styles/tokens.css (plain CSS custom properties: palette, type scale, spacing, 5% title-safe insets for 1920x1080); no build step needed yet.
  Write scripts/make_sample_stream.py, stdlib only, deterministic: hello; 600 tracking_frame messages {t_ms, period, p:[[x,y,vx,vy] x23], ball_z, holder, possession}, two 4-4-2 blocks drifting, ball moving between holders; six event messages; the cue example from cue.schema.json timed inside the window; one fact {name: chaos_index}. Output tests/fixtures/stream/sample_stream.jsonl. --check re-parses every line and asserts the counts.
  Standard library only; the output must be byte-identical on every run (fixed seed, sorted keys).
  Acceptance: python3 scripts/make_sample_stream.py && python3 scripts/make_sample_stream.py --check
  ```

### T-004 Pre-commit secret guard
- **Owner:** B · **Day:** 1 · **Estimated hours:** 0.5
- **Depends on:** T-001
- **Files:** `scripts/hooks/pre-commit`, `scripts/install_hooks.sh`, `tests/tooling/test_secret_guard.py`
- **Scope:** In: a git hook that blocks staged content matching key-shaped patterns (`sk-ant-` or `AIza` followed by a key body), and any staged `.env`. Out: secret scanning of history (repo is new).
- **Acceptance criteria:**
  - A commit with a staged fake key is refused; a clean commit passes; committing `TECH_PLAN.md` and `TASKS.md` (which mention the bare prefixes) passes.
  - The test builds its fake key by string concatenation, so the test file itself never contains the pattern.
- **Verification:** `pytest tests/tooling/test_secret_guard.py -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.10 "Secrets" (pre-commit hook greps for sk-ant- and AIza) and config/.env.example.
  Write scripts/hooks/pre-commit (POSIX sh): scan `git diff --cached` added lines with grep -E for 'sk-ant-[A-Za-z0-9_-]{20,}' and 'AIza[0-9A-Za-z_-]{35}' (bare prefixes in docs must not trip it), and refuse any staged path named .env; exit 1 with the file name, never the matched value.
  scripts/install_hooks.sh copies it into .git/hooks. Run it.
  tests/tooling/test_secret_guard.py: create a temp git repo, install the hook, stage a file whose content is "sk-" + "ant-" + "x"*20, assert commit fails; stage a clean file, assert success.
  Acceptance: pytest tests/tooling/test_secret_guard.py -q
  ```

### T-005 CI skeleton with all nine jobs
- **Owner:** B · **Day:** 1 · **Estimated hours:** 1.5
- **Depends on:** T-001, T-004
- **Files:** `.github/workflows/ci.yml`, `Makefile`, `scripts/validate_schemas.py`, `scripts/check_spend.py`
- **Scope:** In: the nine jobs named in TECH_PLAN 1.10; `lint`, `unit`, `schemas`, `spend-ledger` live now; the other five skip cleanly until their inputs exist. Out: the job logic owned by later tickets (T-007, T-056, T-060, T-066, T-051).
- **Acceptance criteria:**
  - `ci.yml` defines exactly: lint, unit, schemas, golden-determinism, evals-gate, licence-scan, spend-ledger, frozen-cache-guard, chaos-resume.
  - `scripts/validate_schemas.py` validates every schema's own `examples` and every JSON/JSONL under `tests/fixtures/` against the schema it names.
  - `scripts/check_spend.py` fails if the ledger total > $50 or any live match > $2.50.
- **Verification:** `make ci`
- **Brief:**
  ```text
  Read TECH_PLAN 1.3 (versioning rule: CI validates every fixture and cache entry against the schema version it names), 1.10 (CI job list), 1.11 (thresholds the evals-gate will enforce), config/budgets.yaml (spend caps).
  Write .github/workflows/ci.yml with the nine jobs exactly as named in 1.10. Jobs whose scripts do not exist yet use an `if: hashFiles('<script>') != ''` guard and print "skipped: <ticket>".
  scripts/validate_schemas.py: jsonschema Draft 2020-12, a registry so explanation.schema.json $refs resolve; validate all six schema examples, tests/fixtures/**, and data/matches/*/cache/** when present.
  scripts/check_spend.py: read data/spend/ledger.jsonl (empty is fine); fail on total > project_total_cap or any live match_id > per_match_cap.
  Makefile target ci = ruff check . && pytest -q -m "not live" && python scripts/validate_schemas.py && python scripts/check_spend.py.
  CI runs on ubuntu-latest with CPU torch wheels; tests that need MPS skip when it is absent.
  Acceptance: make ci exits 0.
  ```

### T-006 Kickoff engine core
- **Owner:** A · **Day:** 1 · **Estimated hours:** 4.5
- **Depends on:** T-001, T-002
- **Files:** `packages/kickoff/{__main__.py,engine.py,league.py,rules.py,events.py,physics_prior.py,record.py,errors.py}`, `tests/kickoff/{test_events_schema.py,test_no_truth_leak.py,test_speed.py}`
- **Scope:** In: `Engine.__init__/step/state/play`, `League`, `ScriptedRule`, all 18 event types including fouls, offsides and cards, 10 Hz tracking, hidden truth, CLI. Out: `branch()` (T-016), policy decision model (T-036), `--target api` streaming (T-033).
- **Acceptance criteria:**
  - Every event validates against `schemas/event.schema.json`; `match_metadata` is first; events carry player IDs only, never names.
  - No key or value from `truth.json` appears in `events.jsonl`.
  - A 90-minute match at B=1 finishes in < 60 s on CPU (TECH_PLAN 1.4); a NaN in `S` raises `EngineError`.
- **Verification:** `pytest tests/kickoff -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.3 (tracking.npz arrays and dtypes, event contract), 1.4 kickoff (interface, outputs, performance, tests), 1.5 "State layout" and "Determinism", schemas/event.schema.json (18 types, attrs, coordinate convention: 105x68 m, origin bottom-left, home attacks +x in period 1).
  Implement exactly:
    class Engine: __init__(self, league: League, home: str, away: str, seed: int, batch: int = 1, decision_model: DecisionModel = ScriptedRule(), styles: dict | None = None); step(self) -> list[Event]; state(self) -> State; play(self, until_ms: int | None = None) -> MatchRecord
    class ScriptedRule(DecisionModel): def decide(self, state: State) -> Action   # utility + noise; deterministic given rng
  State holds S [B,23,6] (x, y, vx, vy, stamina, facing), ball_z [B], holder [B], possession [B], score [B,2], t_ms, period. Batched numpy, all worlds in lock-step.
  rng = numpy.random.default_rng(seed); world b uses child seed + b. Event ids e_0001.. monotonic; outputs events.jsonl, tracking.npz, truth.json (phases[], momentum[], style_profiles).
  Generate fouls, offsides and cards with frame geometry consistent with the event (the Fourth Official, T-049, re-derives them).
  CLI: python -m kickoff play --seed N --league data/league --out DIR. Libraries: numpy 2.5.4, pydantic 2.14.1.
  Acceptance: pytest tests/kickoff -q
  ```

### T-007 Golden match 4242 and determinism test
- **Owner:** A · **Day:** 1 · **Estimated hours:** 1
- **Depends on:** T-006
- **Files:** `packages/kickoff/record.py`, `data/matches/4242/{events.jsonl,tracking.npz,truth.json,SHA256SUMS}`, `tests/kickoff/test_determinism.py`
- **Scope:** In: byte-identical writers, the golden match on disk, the `golden-determinism` CI job body (generation half). Out: the cue-stream hash (T-071).
- **Acceptance criteria:**
  - Two runs of seed 4242 into different folders give identical SHA-256 for `events.jsonl` and `tracking.npz` (TECH_PLAN 1.8).
  - `SHA256SUMS` committed; CI job `golden-determinism` runs the test.
- **Verification:** `pytest tests/kickoff/test_determinism.py -q && (cd data/matches/4242 && shasum -a 256 -c SHA256SUMS)`
- **Brief:**
  ```text
  Read TECH_PLAN 1.8 "Golden match" (byte-identical events.jsonl and tracking.npz, SHA-256 into the manifest, engine_hash = git SHA) and 1.3 tracking table.
  numpy.savez_compressed stamps the current time into each zip entry, so two runs differ. Write tracking.npz with zipfile and a fixed ZipInfo.date_time (1980,1,1,0,0,0), deflate, entries in a fixed order.
  JSON: sort_keys=True, fixed separators, floats rounded to a fixed number of decimals before dumping, newline-terminated.
  Run: python -m kickoff play --seed 4242 --league data/league --out data/matches/4242; write SHA256SUMS.
  tests/kickoff/test_determinism.py: generate twice into tmp dirs, compare sha256. Fill in the golden-determinism job in .github/workflows/ci.yml.
  If later engine tuning (T-014) changes output, regenerate this folder and SHA256SUMS; allowed until T-039 caches it.
  Acceptance: pytest tests/kickoff/test_determinism.py -q
  ```

### T-008 Provider smoke test and SpendGuard with ledger
- **Owner:** B · **Day:** 1 · **Estimated hours:** 2
- **Depends on:** T-001
- **Files:** `packages/api/spend.py`, `scripts/smoke_models.py`, `tests/api/test_spend.py`, `tests/newsroom/test_imports.py`, `data/spend/ledger.jsonl`
- **Scope:** In: `SpendGuard` (pricing, ledger append, caps, `SpendCapReached`), Agent Framework import checks, one Haiku and one Gemini call. Out: `GET /spend` (T-033), degraded-mode switching (T-021).
- **Acceptance criteria:**
  - Ledger lines have exactly `{ts, role, model, tokens_in, tokens_out, cost_usd, match_id, mode}`; batch calls priced at 0.5×; cache reads priced separately.
  - `SpendCapReached` raised at per-match ($2.50) and per-day ($10) caps; warning logged at 80%.
  - Import test passes and asserts `RequestInfoExecutor` is absent. Smoke spend ≤ $0.01.
- **Verification:** `pytest tests/api/test_spend.py tests/newsroom/test_imports.py -q && python scripts/smoke_models.py`
- **Brief:**
  ```text
  Read TECH_PLAN 1.10 "Spend guard", ADR-011, config/budgets.yaml (spend block, prices_usd_per_1m, batch_discount), config/models.yaml header, config/.env.example.
  packages/api/spend.py: class SpendGuard(prices from budgets.yaml) with price(model, tokens_in, tokens_out, cache_read=0, batch=False), record(role, model, tokens_in, tokens_out, match_id, mode) appending one JSON line to WHYLINE_SPEND_LEDGER, and check(match_id) raising SpendCapReached at per_match_cap / per_day_cap / project_total_cap.
  tests/newsroom/test_imports.py: from agent_framework import WorkflowBuilder, Executor, handler, response_handler, WorkflowContext, FileCheckpointStorage, MCPStreamableHTTPTool; from agent_framework.anthropic import AnthropicClient; from agent_framework.gemini import GeminiChatClient; from agent_framework.orchestrations import GroupChatBuilder; locate Case and Default in the installed package and record the import path; assert not hasattr(agent_framework, "RequestInfoExecutor").
  scripts/smoke_models.py: load .env with python-dotenv; one claude-haiku-5-5 call (anthropic SDK, max_tokens 20) and one gemini-3.8-flash call (google-genai), both recorded through SpendGuard; print model, tokens, cost; never print keys.
  Human step: copy config/.env.example to .env and paste ANTHROPIC_API_KEY and GOOGLE_API_KEY yourself. A Gemini 429 here is the TECH_PLAN 1.13 early warning: note it in the PR.
  Acceptance: pytest tests/api/test_spend.py tests/newsroom/test_imports.py -q && python scripts/smoke_models.py
  ```

### T-009 Azure free account and azd skeleton
- **Owner:** B · **Day:** 1 · **Estimated hours:** 1
- **Depends on:** T-001
- **Files:** `azure.yaml`, `infra/main.bicep`, `infra/main.parameters.json`, `infra/README.md`
- **Scope:** In: account set-up (human), `azure.yaml` with six services, a `main.bicep` that compiles. Out: resource modules and deploy (T-052).
- **Acceptance criteria:**
  - `azure.yaml` declares `api`, `mcp`, `newsroom` (containerapp) and `overlay`, `studio`, `fan` (staticwebapp).
  - `infra/README.md` records subscription type (trial or pay-as-you-go, TECH_PLAN 1.14 open question 5) and region, no IDs or keys.
- **Verification:** `az bicep build --file infra/main.bicep --stdout > /dev/null && azd version`
- **Brief:**
  ```text
  Read TECH_PLAN ADR-009, 1.10 "Azure (free account)" (services, tiers, Bicep module list, azd 1.36.0), FEASIBILITY_AUDIT Part A rows 49 and 52-53 (quota and free tiers).
  Human step: the owner creates the Azure free account, installs az and azd 1.36.0, and runs `az login` and `azd auth login` personally. The session never types credentials.
  Write azure.yaml (name whyline; services api, mcp, newsroom -> host containerapp, docker context packages/<svc>; overlay, studio, fan -> host staticwebapp, dist apps/<app>/dist).
  Write infra/main.bicep (targetScope subscription, resource group, params environmentName and location, no resources yet) and main.parameters.json.
  infra/README.md: subscription type, region, and that Event Hubs is optional (direct POST ingest is default).
  Acceptance: az bicep build --file infra/main.bicep --stdout > /dev/null
  ```

### T-010 Overlay app shell
- **Owner:** C · **Day:** 1 · **Estimated hours:** 2
- **Depends on:** T-001, T-003
- **Files:** `apps/overlay/{index.html,vite.config.ts,tsconfig.json,src/main.tsx,src/App.tsx,src/stream/StreamProvider.tsx,src/stream/reducer.ts,src/record.ts}`, `tests/apps/test_overlay_smoke.py`
- **Scope:** In: Vite + React + TS app, 1920×1080 transparent body, `StreamProvider` (WebSocket or `?fixture=1` file playback), reducer state, record mode. Out: drawing (T-011), components (T-023).
- **Acceptance criteria:**
  - `?fixture=1` plays the T-003 stream; `window.__whyline.ready === true` within 5 s.
  - `?record=1` hides the cursor, forces DPR 1 and exposes `window.__whyline.seek(clock)` (TECH_PLAN 1.9).
- **Verification:** `npm --prefix apps/overlay run build && pytest tests/apps/test_overlay_smoke.py -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.4 "Front-end apps" (Vite + React + TS, no UI library, Canvas 2D, CSS lower-thirds), 1.9 (WebSocket messages, overlay component tree, reducer state {frame, cues[], facts, oracle, profile}, recording flags), docs/cue_contract.md.
  Build apps/overlay with the versions pinned in apps/overlay/package.json (T-001). Body transparent, fixed 1920x1080 stage.
  StreamProvider: default ws://localhost:8000/ws?viewer_id&mode&club&player; with ?fixture=1 replay tests/fixtures/stream/sample_stream.jsonl (copied to public/fixtures at build) on the same 10 Hz clock.
  Reducer handles every message type in 1.9 (unknown types ignored). Cues enter and leave on t_in_ms/t_out_ms against the stream clock.
  record.ts: ?record=1 -> cursor none, DPR 1, window.__whyline = {ready, seek(clock)}.
  tests/apps/test_overlay_smoke.py: Playwright (Python) serves dist, opens ?fixture=1&record=1, waits for __whyline.ready.
  Acceptance: npm --prefix apps/overlay run build && pytest tests/apps/test_overlay_smoke.py -q
  ```

### T-011 Pitch2D canvas renderer
- **Owner:** C · **Day:** 1 · **Estimated hours:** 3.5
- **Depends on:** T-010
- **Files:** `apps/overlay/src/pitch/{Pitch2D.tsx,geometry.ts,layers.ts,draw.ts}`, `apps/overlay/public/league.json` (generated), `scripts/export_league_web.py`, `tests/apps/test_pitch2d.py`
- **Scope:** In: pitch lines, players with numbers in kit colours, ball with height shadow, interpolation between 10 Hz frames, a layer registry (heatmap, threat front, ghost trail, referee lines as empty hooks). Out: layer content (T-024, T-045).
- **Acceptance criteria:**
  - Coordinates follow the event schema (origin bottom-left, 105×68 m) and render correctly flipped to canvas.
  - p95 draw time < 8 ms per animation frame at 1920×1080, logged by the smoke test; a PNG keyframe is saved.
- **Verification:** `npm --prefix apps/overlay run build && pytest tests/apps/test_pitch2d.py -q`
- **Brief:**
  ```text
  Read TECH_PLAN ADR-008 (2.5D canvas for live overlays), 1.3 (tracking rows 0-10 home, 11-21 away, 22 ball; ball_z), 1.9 overlay component tree (Pitch2D draws pitch, players with numbers, ball, heatmap layer, threat front, ghost trail, referee lines), schemas/event.schema.json description (coordinate convention).
  scripts/export_league_web.py writes apps/overlay/public/league.json (club colours, player id -> shirt number, name) from data/league; names are resolved only at render time.
  Pitch2D: requestAnimationFrame loop, linear interpolation between the two latest frames, ball shadow scaled by ball_z, holder ring. layers.ts: ordered registry; each layer gets (ctx, frame, cues, facts, toCanvas).
  tests/apps/test_pitch2d.py: Playwright on ?fixture=1&record=1, read performance marks for 300 frames, assert p95 < 8 ms, save tests/apps/out/pitch2d.png.
  Acceptance: npm --prefix apps/overlay run build && pytest tests/apps/test_pitch2d.py -q
  ```

### T-012 grf_tracking_data tiny_set, coordinate check and attribution
- **Owner:** A · **Day:** 1 · **Estimated hours:** 1
- **Depends on:** none
- **Files:** `packages/policy/grf_check.py`, `docs/DATA.md` (first draft), `data/grf/` (git-ignored)
- **Scope:** In: download `tiny_set` (12 games, ~100 MB), verify columns, coordinate ranges and frame rate, write attribution, draft the email to the authors. Out: the 150-game set and dataset build (T-027); sending the email (human).
- **Acceptance criteria:**
  - `data/grf/coords_report.json` records observed x/y ranges, `TIMESTEP` spacing and the derived frame rate (expected 10 Hz; TECH_PLAN 1.6) and whether the 1.6 metre mapping holds.
  - `docs/DATA.md` has the attribution string from TECH_PLAN 1.6 and the licence status "unconfirmed; email drafted".
- **Verification:** `python3 packages/policy/grf_check.py data/grf/tiny_set && cat data/grf/coords_report.json`
- **Brief:**
  ```text
  Read ZERO_COST_ML.md §2 (dataset, subsets, schema, caveats) and §7 step 1 only (steps 3 and 5 are out of scope: no Foundry Local, no TTS), TECH_PLAN 1.6 "Datasets" and "Pipeline" step 1-2 (expected GRF x in [-1,1], y in [-0.42,0.42]; x' = (x+1)*52.5, y' = (y+0.42)*(68/0.84); 10 Hz), 1.13 (licence risk).
  Human step: approve the download (github.com/Dtradke/grf_tracking_data, tiny_set about 100 MB). Clone into data/grf/repo. Read scripts/download_game_data.py before running it; run it with python -I; files land in data/grf/tiny_set.
  packages/policy/grf_check.py uses the csv module only (stdlib), so it runs before T-001's venv exists; T-027 adds pytest coverage. Check columns GAME_ID, TIMESTEP, TEAM_0_SCORE, TEAM_1_SCORE, PLAYER_ID, TEAM_ID, PLAYER_ROLE, LOCATION_X/Y/Z, VELOCITY_X/Y/Z, ON_BALL; 23 rows per timestep; ball PLAYER_ID -1; min/max of x, y; TIMESTEP spacing; write coords_report.json. If ranges differ from 1.6, record the real mapping there; T-027 uses it.
  docs/DATA.md: attribution "Simulating Tracking Data to Advance Sports Analytics Research, Radke & Tilbury, AAMAS 2025", status, and the email text asking the authors to confirm the data licence. Human step: a person sends it.
  Acceptance: python3 packages/policy/grf_check.py data/grf/tiny_set writes data/grf/coords_report.json and exits 0. Create data/grf/ and .gitignore it yourself if T-001 has not yet.
  ```

**End of day 1: done means** the golden match 4242 is on disk and byte-reproducible, CI runs, keys work through SpendGuard, the overlay draws the fixture pitch, and GRF coordinates are verified.

---
## Day 2 — Thu 22 Oct

### T-013 Physics core: pitch control, indices, chaos index, speeds, state machine
- **Owner:** A · **Day:** 2 · **Estimated hours:** 2.5
- **Depends on:** T-007
- **Files:** `packages/physics/{pitch_control.py,indices.py,speeds.py,state_machine.py,window.py}`, `tests/physics/{test_pitch_control.py,test_state_machine.py,test_perf.py}`
- **Scope:** In: `pitch_control`, `indices`, `chaos_index`, `speeds`, `StateMachine`, `TrackingWindow`. Out: `auto_events` (T-026); learned chaos head (T-015).
- **Acceptance criteria:**
  - Home share + away share = 1 per cell; mirroring the pitch inverts the shares; grid shape [34, 53].
  - Hysteresis tests: enter Chaotic only above 65 for 20 s, leave only below 50 for 30 s (TECH_PLAN 1.4).
  - All functions together < 15 ms per 100 ms frame on CPU.
- **Verification:** `pytest tests/physics -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.4 physics (interfaces, performance, tests), 1.3 tracking table and blackboard `facts` and `pitch_control` documents.
  Implement exactly:
    def pitch_control(S: np.ndarray, cell_m: float = 2.0) -> np.ndarray      # [34,53] home share, Spearman-style
    def indices(window: TrackingWindow, events: list[Event]) -> dict[str, float]   # control_home, control_away, pressure_home/away, tempo, turnover_rate
    def chaos_index(pc: np.ndarray, turnovers_60s: int, transition_share: float) -> float   # 0-100
    def speeds(window: TrackingWindow) -> SpeedReport                        # ball_kmh, shot_kmh, sprints[(player, kmh, t_ms)]
    class StateMachine: def update(self, chaos: float, t_ms: int) -> str | None   # Settled/Transitional/Chaotic
  Pitch control: time-to-intercept per player per cell plus a logistic control model, vectorised over 1,802 cells x 22 players. Implement from the published method; do not copy code from data/grf/repo (no licence file).
  Libraries: numpy 2.5.4, scipy 1.18.1.
  Acceptance: pytest tests/physics -q
  ```

### T-014 Training corpus generator and realism ranges
- **Owner:** A · **Day:** 2 · **Estimated hours:** 1
- **Depends on:** T-007
- **Files:** `scripts/generate_corpus.py`, `tests/kickoff/test_realism.py`, `data/matches/corpus/` (git-ignored), `data/matches/corpus/README.md`
- **Scope:** In: multiprocessing generator, seed partition, compact storage, realism test on seeds 1–50, overnight launch of seeds 1001–3000. Out: heads (T-015), policy dataset (T-027).
- **Acceptance criteria:**
  - Seeds 1–50 (full tracking) pass TECH_PLAN 1.4 realism: pass completion 78–86%, 1.0–1.8 goals per team, 8–16 shots per team.
  - Seeds 51–350 store events + truth only; seeds 1001–3000 store `events.jsonl.gz`, `truth.json` and `samples.npz` (state at every on-ball decision and at 1 Hz); first 200 training matches done within the day.
  - Overnight run of all 2,000 launched with a resumable progress file.
- **Verification:** `pytest tests/kickoff/test_realism.py -q && python scripts/generate_corpus.py --status`
- **Brief:**
  ```text
  Read TECH_PLAN 1.4 kickoff (realism ranges on 50 matches, 90-minute match < 60 s), 1.6 heads table (2,000 Kickoff matches, ~60k shots, ~2M passes, states every 30 s), this file's seed convention.
  scripts/generate_corpus.py --seeds A..B --workers 10 --out data/matches/corpus [--full] [--status]: multiprocessing, one seed per task, skip finished seeds, write progress.json.
  Full tracking for 2,000 matches is roughly 30 GB (estimate), so training seeds keep only samples.npz (S, ball_z, holder, possession, score, t_ms at decision points and at 1 Hz) plus events and truth.
  Run seeds 1..50 --full first; if realism fails, tune ScriptedRule or styles, then regenerate data/matches/4242 and its SHA256SUMS (T-007 test must still pass) before launching 1001..3000.
  Human step: keep the Mac awake overnight (caffeinate). Expect about 3-4 h with 10 workers (estimate).
  Acceptance: pytest tests/kickoff/test_realism.py -q && python scripts/generate_corpus.py --status
  ```

### T-015 Outcome heads v0
- **Owner:** A · **Day:** 2 · **Estimated hours:** 1.5
- **Depends on:** T-013, T-014
- **Files:** `packages/heads/{features.py,models.py,train.py,calibration.py}`, `packages/heads/artifacts/{xg,pass,winprob,goal8s,chaos}.txt` + `metrics.json` + `calibration.png` each, `tests/heads/test_heads.py`
- **Scope:** In: `train_all`, five heads (xG, pass, win probability, goal-in-8-s, chaos) trained on the first 200 training matches; reports, not gates. Out: `MomentEncoder` (T-054); gating on 2,000 matches (T-025).
- **Acceptance criteria:**
  - Artefacts and `metrics.json` exist for each head; loading a missing artefact raises at start-up (never a silent fallback).
  - Monotonicity tests pass: xG rises as distance falls; win probability rises with score difference.
- **Verification:** `python -m heads.train --matches data/matches/corpus --out packages/heads/artifacts --seed 4242 --limit 200 && pytest tests/heads -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.4 heads (interfaces, artefact paths, failure behaviour), 1.6 "Outcome heads" table (features, model, data, ECE thresholds).
  Implement exactly:
    class XGHead: def predict(self, shots: pd.DataFrame) -> np.ndarray
    class PassHead: def predict(self, passes: pd.DataFrame) -> np.ndarray
    class WinProbHead: def predict(self, states: pd.DataFrame) -> np.ndarray    # [n,3] home/draw/away
    class GoalIn8sHead: def predict(self, states: pd.DataFrame) -> np.ndarray   # [n,2] home, away
    class ChaosHead: def predict(self, features) -> np.ndarray                  # P(possession change within 10 s), logistic
    def train_all(matches_dir: Path, out_dir: Path, seed: int) -> Report
  LightGBM and scikit-learn at the versions T-001 pinned; split by match seed, never by row. Reliability diagram per head with matplotlib. ECE and (goal-in-8-s) PR-AUC go into metrics.json.
  Acceptance: python -m heads.train --matches data/matches/corpus --out packages/heads/artifacts --seed 4242 --limit 200 && pytest tests/heads -q
  ```

### T-016 Engine.branch, rollout primitive (scripted_v1) and sliding_doors
- **Owner:** A · **Day:** 2 · **Estimated hours:** 3
- **Depends on:** T-013, T-015
- **Files:** `packages/kickoff/engine.py` (branch), `packages/rollout/{core.py,sliding_doors.py,futures.py}`, `tests/rollout/{test_determinism.py,test_perf.py,test_placebo.py,test_schema.py}`
- **Scope:** In: `Engine.branch`, `Override`, `rollout`, `Futures`, `sliding_doors` with horizon hand-off to `GoalIn8sHead` and `WinProbHead`. Out: `policy_v1` path (T-036), `oracle` (T-046), `dugout` (T-047).
- **Acceptance criteria:**
  - Same `(state, overrides, B, horizon_s, seed, engine, engine_hash)` gives byte-identical `Futures` (TECH_PLAN 1.5).
  - B=200, 900 steps (90 s) scripted ≤ 1.3 s warm on CPU (TECH_PLAN 1.4); the $50 plan's 200 × 60 s case ≤ 1.2 s (`budgets.yaml` `scripted_200x60s_cpu`).
  - `sliding_doors` output validates against `schemas/counterfactual.schema.json`; forcing the actual action reproduces the baseline within the 95% interval (placebo).
- **Verification:** `pytest tests/rollout -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.5 in full (state layout, forcing the first action, decision points, horizon hand-off, returns, determinism, budgets), 1.4 rollout and kickoff (branch), schemas/counterfactual.schema.json.
  Implement exactly:
    def branch(self, t_ms: int, batch: int, override: Override | None) -> "Engine"
    @dataclass class Override: first_action: Action; styles: dict[str, StyleDelta] | None
    def rollout(state: State, overrides: Override | None, B: int, horizon_s: float, seed: int, engine: Literal["scripted_v1", "policy_v1"] = "scripted_v1") -> Futures
    def sliding_doors(match: MatchRef, t_ms: int, alternative: Action, n: int = 200, horizon_s: float = 8, seed: int = 4242, engine=...) -> CounterfactualResult
  branch from a past t_ms re-simulates the match deterministically from kick-off to t_ms (or uses stored snapshots); never reads truth.json.
  Futures fields: S_end, goals, shots, ball_paths [B, horizon_s+1, 2] at 1 Hz, p_goal_home, p_goal_away, win_prob_home, ci95, xt_gain_mean, invalid_reason.
  For scripted_v1, policy_prob of an alternative = softmax of ScriptedRule utilities at the branch point (the RolloutExecutor filter needs it, T-031).
  Acceptance: pytest tests/rollout -q
  ```

### T-017 SqliteBlackboard
- **Owner:** B · **Day:** 2 · **Estimated hours:** 1.5
- **Depends on:** T-001
- **Files:** `packages/blackboard/{protocol.py,sqlite.py,ids.py}`, `tests/blackboard/test_sqlite.py`
- **Scope:** In: the `Blackboard` protocol, SQLite implementation, ID allocation, cross-process `watch`. Out: `CosmosBlackboard` (T-058).
- **Acceptance criteria:**
  - Every schema example round-trips; `watch` yields documents in insertion order, including from another process.
  - `put` < 2 ms locally (TECH_PLAN 1.4); IDs follow 1.3 (`f_000001`, `mo_00077`, `pc_000412`, `cf_000077`, `ex_000077`, `c_000912`), monotonic per match.
- **Verification:** `pytest tests/blackboard -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.3 "Blackboard documents" (collections, keys, ID rules), 1.4 blackboard (interface, performance, tests), 1.1 (SQLite at data/runtime/blackboard.sqlite).
  Implement exactly:
    class Blackboard(Protocol):
        def put(self, collection: str, doc: dict) -> str; def get(self, collection, id) -> dict
        def query(self, collection, **filters) -> list[dict]; def watch(self, collection) -> AsyncIterator[dict]
    class SqliteBlackboard(Blackboard)   # one table per collection, JSON column, indexes on match_id and t_ms
  The api and the newsroom worker are separate processes, so watch() polls rowid (WAL mode) and is the local hand-off for moments and cues; the in-process asyncio.Queue in 1.1 is used only within one process.
  ids.py: next_id(collection, match_id) with the prefixes and widths above.
  Acceptance: pytest tests/blackboard -q
  ```

### T-018 Newsroom workflow graph, LLMClient and file checkpoints
- **Owner:** B · **Day:** 2 · **Estimated hours:** 2
- **Depends on:** T-008, T-017
- **Files:** `packages/newsroom/{messages.py,graph.py,llm.py,worker.py,config.py}`, `packages/newsroom/executors/{base.py,ingest.py,stubs.py,drop.py}`, `tests/newsroom/test_graph.py`
- **Scope:** In: message models, the full 1.7 graph with switch-case and the rewrite loop, stub executors for branches built later, `LLMClient` protocol, `LiveClient`, `FileCheckpointStorage`, worker loop. Out: real Scout, Narrator, Fact Checker, Director logic (T-019–T-021, T-029).
- **Acceptance criteria:**
  - A fixture goal moment reaches a cue through the fast branch; a fixture explained moment with a rejecting fact-check stub loops to the Narrator and stops at `attempt == 3`.
  - Checkpoint files appear in a temp `WHYLINE_CHECKPOINT_DIR` after each superstep.
- **Verification:** `pytest tests/newsroom/test_graph.py -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.7 "Workflow graph" (copy the builder calls verbatim), "Checkpoints, resume", 1.8 "Replay serving" (CacheClient.complete(role, messages, tools)), ADR-005, config/models.yaml, FEASIBILITY_AUDIT Part A rows 35-39.
  Build: WorkflowBuilder(start_executor=ingest, checkpoint_storage=storage, name="newsroom"); add_switch_case_edge_group(scout, [Case(condition=is_fast, ...), Case(is_explained), Case(is_panel), Case(is_referee), Case(is_recap), Default(target=drop)]); add_edge(factcheck, narrator, condition=lambda m: not m.verified and m.attempt < 3); add_edge(factcheck, director, condition=lambda m: m.verified or m.attempt >= 3).
  Executors are Executor subclasses with @handler methods. Use the Case/Default import path recorded in tests/newsroom/test_imports.py. Read the installed agent_framework source for WorkflowContext.send_message and run(stream=True) event types; do not guess.
  llm.py: class LLMClient(Protocol): complete(role, messages, tools) -> dict; LiveClient uses AnthropicClient (agent_framework.anthropic) or GeminiChatClient (agent_framework.gemini) per role in models.yaml, and records every call through SpendGuard.
  storage = FileCheckpointStorage(os.environ["WHYLINE_CHECKPOINT_DIR"]). worker.py: watch blackboard `moments`, one workflow run per moment.
  Acceptance: pytest tests/newsroom/test_graph.py -q
  ```

### T-019 Fact Checker with the eight rules
- **Owner:** B · **Day:** 2 · **Estimated hours:** 2
- **Depends on:** T-002, T-017
- **Files:** `packages/newsroom/factcheck.py`, `packages/newsroom/executors/factcheck.py`, `scripts/scan_banned.py`, `tests/newsroom/test_factcheck.py`
- **Scope:** In: the eight deterministic rules, tolerances, the `diff` for rewrites, a banned-phrase scanner reusable on any file. Out: the 500-sample planted-error suite (T-055).
- **Acceptance criteria:**
  - One passing and one failing unit test per rule (TECH_PLAN 1.7 rules 1–8), including `unbound_number` and every tolerance.
  - The `explanation.schema.json` example verifies against fixture evidence; check time < 50 ms.
- **Verification:** `pytest tests/newsroom/test_factcheck.py -q && python scripts/scan_banned.py data/league`
- **Brief:**
  ```text
  Read TECH_PLAN 1.7 "Fact Checker rules" (all eight, verbatim tolerances: xG ±0.005; probabilities ±0.01; metres ±0.5; km/h ±1; minutes ±1; win_prob_delta = counterfactual delta_win_prob_home ±0.01), schemas/explanation.schema.json ($defs.claim), schemas/cue.schema.json (verified), data/league/banned_names.txt.
  factcheck.py: def verify_claims(match_id: str, claims: list[dict], bb: Blackboard, text: dict[str, str] | None = None) -> dict returning {verified, claims[] with verified and reject_reason, diff[]}. The MCP tool verify_claims (T-030) calls this same function.
  Rule 6: regex every number (digits, percent, decimals) in why/headline/body; each must equal the text of a verified claim.
  Rule 7: banned content (injury speculation, referee-bias accusations, "odds", "bet", any phrase in banned_names.txt; whole-phrase, case-insensitive).
  scripts/scan_banned.py PATH...: scan text/JSON files with the rule-7 matcher; exit 1 on any hit.
  Acceptance: pytest tests/newsroom/test_factcheck.py -q
  ```

### T-020 Narrator and fast-line executors with template and Gemini fallback
- **Owner:** B · **Day:** 2 · **Estimated hours:** 1
- **Depends on:** T-018, T-019
- **Files:** `packages/newsroom/executors/{narrator.py,fast_line.py}`, `packages/newsroom/templates.py`, `packages/newsroom/prompts/narrator@2.md`, `packages/newsroom/prompts/fewshot/narrator.jsonl`, `tests/newsroom/test_narrator.py`
- **Scope:** In: Haiku narrator using only verified claims, rewrite with the fact-check diff, 4 s timeout with one retry, template fallback, Gemini 3.8 Flash provider fallback. Out: few-shot content (T-057).
- **Acceptance criteria:**
  - Output `{headline, body, claims[]}` fits cue limits (headline ≤ 60, body ≤ 280 chars).
  - Fake-client tests cover timeout → template and Anthropic error → Gemini. One live Haiku test passes; dev spend ≤ $0.10.
- **Verification:** `pytest tests/newsroom/test_narrator.py -q && WHYLINE_LIVE_TESTS=1 pytest tests/newsroom/test_narrator.py -q -m live`
- **Brief:**
  ```text
  Read TECH_PLAN 1.7 agent table rows Narrator and Scout-fast path (FastLineExecutor), "Prompt versioning and few-shots", config/models.yaml roles narrator_fast and narrator_template, schemas/cue.schema.json text limits.
  NarratorExecutor and FastLineExecutor hold an Agent on the narrator_fast client (claude-haiku-5-5, effort low, max_tokens 300). Input: verified claims only, plus the diff on rewrites. Output inline JSON {headline, body, claims[]}.
  templates.py: deterministic narrator_template lines built only from verified claims (also used by the Director on the third failed attempt).
  On Anthropic error use gemini_fallback gemini-3.8-flash through GeminiChatClient; on timeout or second failure use the template. Every call through SpendGuard.
  narrator@2.md: house style (present tense, one idea, numbers only from claims); fewshot/narrator.jsonl starts empty.
  Acceptance: pytest tests/newsroom/test_narrator.py -q
  ```

### T-021 Director with budgets
- **Owner:** B · **Day:** 2 · **Estimated hours:** 1.5
- **Depends on:** T-018
- **Files:** `packages/newsroom/executors/director.py`, `packages/newsroom/cuebus.py`, `tests/newsroom/test_director.py`
- **Scope:** In: per-mode budgets and hard rules from `budgets.yaml`, schema-valid cue construction, deterministic cue IDs, degraded switch on `SpendCapReached`, template on any model failure, `CueBus` writing to the blackboard. Out: recap approval (T-050).
- **Acceptance criteria:**
  - Timeline tests cover: no overlay during a shot sequence (max 6 s), none within 3 s after a goal, same-kind dedupe 90 s, expiry after 45 s, Sliding Doors only at leverage ≥ 0.04, Oracle only at p_shot ≥ 0.30.
  - Every produced cue validates against `schemas/cue.schema.json`; `cue_id` depends only on `(moment_id, branch)` order, not on process state.
- **Verification:** `pytest tests/newsroom/test_director.py -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.7 "Director budgets" and agent table row Director, 1.10 "Spend guard" (SpendCapReached), 1.8 "Live mode" (degraded behaviour), config/budgets.yaml director block, schemas/cue.schema.json.
  DirectorExecutor builds cues (layer, kind, targets.modes from the budgets, text, graphics, explain with explanation_id/counterfactual_id, verified, producer_status auto, provenance {mode, agent_path, trace_id, model, prompt_version, cache_key}).
  cue_id: allocated from the moment's position in the match and the branch, so a resumed run (T-051) emits the same id as an uninterrupted one.
  On SpendCapReached: set mode degraded, emit a mode message, use templates. On any LLM error or CacheMiss: template line and a red trace row (status cache_miss or error).
  cuebus.py: put cues into blackboard `cues`; the api (T-033) watches that collection.
  Acceptance: pytest tests/newsroom/test_director.py -q
  ```

### T-022 API replay server and tracking stream
- **Owner:** C · **Day:** 2 · **Estimated hours:** 3
- **Depends on:** T-007, T-010
- **Files:** `packages/api/{main.py,replay.py,ws.py,models.py,__main__.py}`, `tests/api/test_replay.py`
- **Scope:** In: `GET /health`, `GET /match/{id}/events?from&to`, `POST /replay/control`, `WS /ws` with `hello`, `tracking_frame` (10 Hz) and `event`, replay clock x1–x10, `python -m api.replay --seed 4242`. Out: cues, ingest, producer, demo, spend endpoints (T-033).
- **Acceptance criteria:**
  - WS test at x1 receives `hello` then ≥ 10 `tracking_frame` messages in 1.2 s, JSON shape per TECH_PLAN 1.3; seek and speed work.
  - The overlay plays the golden match from `ws://localhost:8000/ws` instead of the fixture.
- **Verification:** `pytest tests/api/test_replay.py -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.1 (whyline-api role, replay data flow), 1.4 api (endpoint list), 1.3 (tracking.npz and tracking_frame JSON), 1.9 (message table: hello, tracking_frame, event), config/.env.example (WHYLINE_API_PORT, WHYLINE_MATCH_SEED).
  FastAPI and uvicorn at the T-001 pins. app = FastAPI() in packages/api/main.py; run with uvicorn api.main:app --port 8000.
  replay.py: ReplayClock(speed 1..10, play/pause/seek) over data/matches/<seed>/tracking.npz and events.jsonl; WHYLINE_REPLAY_SPEED sets the default.
  POST /replay/control {action: play|pause|seek|speed, value}. WS /ws?viewer_id&mode&club&player sends hello {match_id, mode, replay_speed, viewer_profile} then frames and events on the clock.
  tests: FastAPI TestClient (httpx) for REST and the websocket.
  Acceptance: pytest tests/api/test_replay.py -q
  ```

### T-023 Lower-thirds, score bug, chaos meter, player tags, ticker
- **Owner:** C · **Day:** 2 · **Estimated hours:** 2.5
- **Depends on:** T-011, T-022
- **Files:** `apps/overlay/src/components/{ScoreBug.tsx,ChaosMeter.tsx,LowerThird.tsx,PlayerTags.tsx,Ticker.tsx}`, `apps/overlay/src/styles/broadcast.css`, `tests/apps/test_overlay_components.py`
- **Scope:** In: DOM components from the 1.9 tree with CSS enter/exit, driven by `event`, `fact` and `cue` messages. Out: ghost trail and swing bar (T-024), viewer-mode filtering (T-045).
- **Acceptance criteria:**
  - The fixture cue appears at `t_in_ms` and leaves at `t_out_ms` (checked by seeking); text never overflows at the schema maximum lengths.
  - Score bug follows goal events; chaos meter follows `fact` messages named `chaos_index`.
- **Verification:** `npm --prefix apps/overlay run build && pytest tests/apps/test_overlay_components.py -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.9 overlay component tree (App -> StreamProvider -> Pitch2D -> ScoreBug -> ChaosMeter -> SwingBar -> LowerThird -> PlayerTags -> Ticker), schemas/cue.schema.json (layers lower_third, player_tag, ticker; text limits), docs/cue_contract.md, data/league/clubs.json (colours via public/league.json).
  CSS only, no UI library. Lower-third: headline 60 chars, body 280 chars, verified tick, slide in/out 300 ms. Score bug: short names, clock, period. Chaos meter: 0-100 bar plus state label (Settled/Transitional/Chaotic).
  Add fact messages to the fixture if missing (T-003 script) so the test runs without the engine.
  Pins: React, Vite and TypeScript as recorded in apps/overlay/package.json (T-001); add no dependencies.
  Acceptance: npm --prefix apps/overlay run build && pytest tests/apps/test_overlay_components.py -q
  ```

### T-024 Ghost trail and swing bar
- **Owner:** C · **Day:** 2 · **Estimated hours:** 2.5
- **Depends on:** T-023
- **Files:** `apps/overlay/src/pitch/layers/ghostTrail.ts`, `apps/overlay/src/components/SwingBar.tsx`, `tests/apps/test_ghost_trail.py`
- **Scope:** In: canvas layer drawing up to 200 futures (`futures_sample`) and the cue's `graphics.ghost_trail` as an orange dashed line; swing bar from `graphics.bar` with n, horizon and seed shown. Out: 3D version (T-053).
- **Acceptance criteria:**
  - 200 paths draw with p95 frame time < 8 ms; paths are smoothed between 1 Hz points.
  - Swing bar always prints "n = …, … s, seed …" next to the number (counterfactual schema description).
- **Verification:** `npm --prefix apps/overlay run build && pytest tests/apps/test_ghost_trail.py -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.9 (overlay: ghost trail, swing bar), 1.5 "Returns" (ball_paths at 1 Hz), schemas/counterfactual.schema.json (futures_sample, delta_win_prob_home, n, horizon_s, seed), schemas/cue.schema.json graphics (ghost_trail, bar {label, from, to}).
  Until T-033 serves counterfactual documents, read the schema example counterfactual from the fixture.
  Ghost layer: translucent lines coloured by branch (baseline vs alternative), Catmull-Rom smoothing, fade-in over 0.8 s; the chosen alternative as an orange dashed trail.
  SwingBar: animated from -> to, label, and the n/horizon/seed line.
  Acceptance: npm --prefix apps/overlay run build && pytest tests/apps/test_ghost_trail.py -q
  ```

**End of day 2: done means** pitch control and heads exist, a scripted Sliding Doors counterfactual for any golden moment validates against the schema in ≤ 1.3 s, the newsroom graph runs fast and rewrite paths with file checkpoints, and the overlay plays the golden match from the API with lower-thirds, ghost trail and swing bar.

---

## Day 3 — Fri 23 Oct

### T-025 Outcome heads v1 on 2,000 matches with gates
- **Owner:** A · **Day:** 3 · **Estimated hours:** 1
- **Depends on:** T-014, T-015
- **Files:** `packages/heads/artifacts/*`, `packages/heads/gates.py`, `tests/heads/test_gates.py`
- **Scope:** In: retrain on all 2,000 training matches; enforce 1.6 thresholds. Out: new features (only if a gate fails).
- **Acceptance criteria:**
  - ECE ≤ 0.03 for xG, pass and win probability; ECE ≤ 0.01 for goal-in-8-s with PR-AUC reported; chaos head AUC ≥ 0.70 (TECH_PLAN 1.6).
  - `metrics.json` per head records data size, split seeds and the numbers.
- **Verification:** `python -m heads.train --matches data/matches/corpus --out packages/heads/artifacts --seed 4242 && pytest tests/heads -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.6 "Outcome heads" (thresholds), 1.4 heads (calibration ECE ≤ 0.03; artefacts and metrics.json), 1.13 (no silent fallbacks).
  Confirm the overnight corpus finished (python scripts/generate_corpus.py --status shows 2,000 seeds). Re-run train_all with no --limit.
  packages/heads/gates.py reads each metrics.json and fails with the head name and number if a 1.6 threshold is missed. If a head fails, fix features or calibration (isotonic is allowed); never change the threshold.
  Commit the .txt models, metrics.json and calibration.png; they are small and replay and CI need them.
  Acceptance: python -m heads.train --matches data/matches/corpus --out packages/heads/artifacts --seed 4242 && pytest tests/heads -q
  ```

### T-026 Auto-events
- **Owner:** A · **Day:** 3 · **Estimated hours:** 1.5
- **Depends on:** T-013
- **Files:** `packages/physics/auto_events.py`, `tests/physics/test_auto_events.py`
- **Scope:** In: `pressing_trap`, `line_break`, `switch_of_play`, `overload`, `counter_attack`, `big_chance`, stored as `facts`. Out: learned detectors; new event types.
- **Acceptance criteria:**
  - Each detector has a hand-built positive and negative frame test.
  - On the golden match each type fires at least once and at most 40 times; counts written to `data/matches/4242/auto_events_report.json`.
- **Verification:** `pytest tests/physics/test_auto_events.py -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.4 physics (def auto_events(window, events) -> list[Event] with the six kinds), 1.3 blackboard `facts`, 1.7 Scout classification (big_chance = xG ≥ 0.3), schemas/event.schema.json (its type enum has no auto-event kinds).
  Keep the signature. Returned objects carry auto_kind and related_event_ids; they are never written to events.jsonl (that would be a schema change under 1.3). Store each as a `facts` doc {kind: "state", name: <auto_kind>, evidence_event_ids}.
  Rules use pitch control, speeds and positions: e.g. line_break = pass crossing the opponents' defensive line with the receiver behind it; switch_of_play = lateral travel > 30 m in < 3 s; big_chance via XGHead.
  Performance: auto_events stays inside the physics budget of < 15 ms per 100 ms frame (TECH_PLAN 1.4).
  Acceptance: pytest tests/physics/test_auto_events.py -q
  ```

### T-027 GRF 150-game download and policy dataset build
- **Owner:** A · **Day:** 3 · **Estimated hours:** 3
- **Depends on:** T-012, T-014
- **Files:** `packages/policy/data.py`, `data/grf/` (git-ignored), `packages/policy/artifacts/dataset_report.json`, `packages/policy/artifacts/coord_sanity.png`, `tests/policy/{test_data.py,test_grf_coords.py}`
- **Scope:** In: the 150 games visible in the Drive folder (~1.25 GB), labelling, features, split, report. Out: the 3,000-game `full_set` (~25 GB; not needed); real tracking data (validation only, T-073).
- **Acceptance criteria:**
  - `build_dataset` writes `train.npz`, `val.npz`, `test.npz` split 80/10/10 by `GAME_ID` with `split_seed = 4242` (TECH_PLAN 1.6) and Kickoff samples split by match seed.
  - `dataset_report.json` lists counts per class (pass, carry, shoot, clear, hold), games per split, and sanity plots exist; F = 16 token features, G = 4 global.
- **Verification:** `python -m policy.data --grf data/grf --kickoff data/matches/corpus --out data/grf/dataset --split-seed 4242 && pytest tests/policy/test_data.py -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.6 "On-ball decision policy" Pipeline steps 1-6 (labels: pass on holder change within team; carry > 2 m in 1 s with ball, 8 direction bins; shoot ball > 15 m/s toward goal; clear > 25 m away from own goal under pressure; else hold), data/grf/coords_report.json (T-012), ZERO_COST_ML.md §2.
  Human step: approve the download of the 150 visible games (about 1.25 GB) into data/grf/raw; use the repo's downloader only after reading it, run with python -I.
  Implement exactly: def build_dataset(grf_dir: Path, kickoff_dir: Path, out: Path, split_seed: int) -> DatasetReport
  Flip so the team in possession always attacks +x. Kickoff labels come straight from events (samples.npz + events.jsonl.gz from T-014).
  Stream CSVs in chunks with pandas (18 GB RAM); write float16 features where precision allows.
  Acceptance: pytest tests/policy/test_data.py -q
  ```

### T-028 DecisionPolicy model and overnight training launch
- **Owner:** A · **Day:** 3 · **Estimated hours:** 2
- **Depends on:** T-027
- **Files:** `packages/policy/{model.py,train.py,config.py}`, `packages/policy/artifacts/policy_v1_epN.pt`, `packages/policy/artifacts/train_log.jsonl`, `tests/policy/test_model.py`
- **Scope:** In: the set transformer, losses, training loop on MPS, per-epoch checkpoints, a 10-minute smoke run, then the overnight launch. Out: evaluation and gate (T-037).
- **Acceptance criteria:**
  - Parameter count ≈ 4.9M (within ±10%); forward on [200, 23, 16] runs on `mps`.
  - Smoke run shows falling validation loss; overnight run launched with 8 epochs, checkpoints every epoch, best-by-val kept as `policy_v1.pt`.
- **Verification:** `pytest tests/policy/test_model.py -q && tail -n 3 packages/policy/artifacts/train_log.jsonl`
- **Brief:**
  ```text
  Read TECH_PLAN 1.4 policy (interface, device, artefact paths), 1.6 "Model" and "Training" (input F->256, 6 encoder layers, d 256, 8 heads, FFN 1024, no positional encoding, global token; heads: kind 5, pass pointer over 10 teammates, carry 8; loss CE sums; AdamW 3e-4 cosine, 1,000 warm-up, batch 256, label smoothing 0.05, 8 epochs; ~2,474 samples/s measured on MPS so ~0.7 h/epoch).
  Implement exactly:
    class DecisionPolicy(torch.nn.Module):
        def forward(self, tokens: Tensor[B,23,F], ctx: Tensor[B,G]) -> PolicyOut   # kind_logits [B,5], pass_logits [B,11], carry_logits [B,8]
        def act(self, state: State, generator: torch.Generator) -> list[Action]
    def train(config: TrainConfig) -> TrainReport
  torch 2.14.1, device from WHYLINE_DEVICE (mps). Resume from the last epoch file if interrupted.
  Weights (*.pt) are git-ignored until T-089 settles the GRF licence (TECH_PLAN 1.6, 1.13); commit metrics and logs only.
  Human step: keep the Mac awake and on power overnight (caffeinate); ~5.6 h expected.
  Acceptance: pytest tests/policy/test_model.py -q
  ```

### T-029 Scout executor and classification predicates
- **Owner:** B · **Day:** 3 · **Estimated hours:** 1
- **Depends on:** T-015, T-018, T-026
- **Files:** `packages/newsroom/executors/scout.py`, `packages/newsroom/scout_rules.py`, `tests/newsroom/test_scout.py`
- **Scope:** In: moment detection from engine events, auto-events and the goal-in-8-s head swing; `is_fast`, `is_explained`, `is_panel`, `is_referee`, `is_recap`; one message per branch. Out: precomputed moments (T-039).
- **Acceptance criteria:**
  - Predicates match TECH_PLAN 1.7 exactly (leverage ≥ 0.04 explained; ≥ 0.06 and `panel.enabled` for panel; xG ≥ 0.3 big chance).
  - Moment docs carry every 1.3 `moments` field; Scout runs in < 50 ms per event; on the golden match it yields 25–60 explained moments (report the number).
- **Verification:** `pytest tests/newsroom/test_scout.py -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.7 "Workflow graph" classification rules and agent table row Scout (code, 50 ms), 1.3 moments document, $50 plan §2 (40 Tactician calls per match is the cost assumption).
  Leverage = absolute swing of GoalIn8sHead between the frame before and after the event (heads from T-025; missing artefact raises).
  Multiple Case matches do not fan out, so Scout emits one message per matching branch (1.7).
  Write moments to the blackboard with mo_ ids (T-017 ids.py).
  Acceptance: pytest tests/newsroom/test_scout.py -q
  ```

### T-030 MCP server: core tools
- **Owner:** B · **Day:** 3 · **Estimated hours:** 2.5
- **Depends on:** T-013, T-016, T-017, T-019, T-021
- **Files:** `packages/mcp_server/{__main__.py,server.py,tools_core.py,errors.py}`, `tests/mcp_server/test_tools.py`
- **Scope:** In: FastMCP over Streamable HTTP on :8080 with `query_events`, `get_state`, `get_pitch_control`, `simulate_counterfactual`, `player_stats`, `verify_claims`, `get_budget`. Out: `top_moments`, `timeline` (T-050), `similar_moments` (T-054), cache hits (T-038).
- **Acceptance criteria:**
  - Each tool is tested against the golden match; errors return `{error, code}` and never raise into the agent.
  - `simulate_counterfactual` returns a schema-valid `CounterfactualResult` with n and horizon defaults 200 and 8.
- **Verification:** `pytest tests/mcp_server/test_tools.py -q`
- **Brief:**
  ```text
  Read TECH_PLAN ADR-006, 1.4 mcp_server, 1.7 "MCP tool list" (copy these signatures exactly):
    query_events(match_id: str, t_from_ms: int, t_to_ms: int, kinds: list[str] | None = None, player: str | None = None) -> list[dict]
    get_state(match_id: str, t_ms: int) -> dict
    get_pitch_control(match_id: str, t_ms: int) -> dict          # snapshot_id, home_share, contested_frac, zones, top-3 overloads
    simulate_counterfactual(match_id: str, t_ms: int, alternative: dict, n: int = 200, horizon_s: float = 8) -> dict
    player_stats(match_id: str, player_id: str) -> dict
    verify_claims(match_id: str, claims: list[dict]) -> dict      # calls newsroom.factcheck.verify_claims
    get_budget(mode: str) -> dict
  Official MCP Python SDK (`mcp`, version pinned at T-001), FastMCP, Streamable HTTP, port WHYLINE_MCP_PORT (8080), path /mcp.
  Pitch-control snapshots are stored as pc_ documents (+ .npz) so claims can cite them.
  Acceptance: pytest tests/mcp_server/test_tools.py -q
  ```

### T-031 Proposer and RolloutExecutor
- **Owner:** B · **Day:** 3 · **Estimated hours:** 1.5
- **Depends on:** T-030
- **Files:** `packages/newsroom/executors/{proposer.py,rollout.py}`, `packages/newsroom/prompts/proposer@1.md`, `tests/newsroom/test_proposer.py`
- **Scope:** In: Sonnet proposer (≤ 3 alternatives), rule fallback, rollout executor calling MCP per alternative and keeping the largest |Δ| with `policy_prob ≥ 0.05`. Out: Tactician (T-032).
- **Acceptance criteria:**
  - Timeout 6 s with one retry, then `proposer_rule` (top-3 teammates by xT gain); rollout timeout 2 s locally with fallback n = 50.
  - An alternative the engine marks invalid (`invalid_reason`) is skipped, never shown.
- **Verification:** `pytest tests/newsroom/test_proposer.py -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.7 agent table rows Proposer and Rollout, 1.5 "Forcing the first action" (invalid alternatives), FEASIBILITY_AUDIT B.2 guard 1 (only alternatives with policy probability ≥ 5%), config/models.yaml roles proposer and proposer_rule.
  ProposerExecutor: Agent on claude-sonnet-5-5, effort low, max_tokens 600, inline JSON {alternatives: [{kind, actor, target, reason}]} (≤ 3); no forced tool_choice; through SpendGuard.
  RolloutExecutor: for each alternative call MCP simulate_counterfactual via MCPStreamableHTTPTool(name="whyline", url="http://localhost:8080/mcp"); keep the largest |delta_win_prob_home| with policy_prob ≥ 0.05; store cf_ in the blackboard.
  Pins: agent-framework-core 1.22.0, agent-framework-anthropic 1.0.0b261015, mcp pinned at T-001. Dev spend ≤ $0.20 through SpendGuard.
  Acceptance: pytest tests/newsroom/test_proposer.py -q
  ```

### T-032 Tactician with MCP tools and first live latency probe
- **Owner:** B · **Day:** 3 · **Estimated hours:** 2
- **Depends on:** T-020, T-030, T-031
- **Files:** `packages/newsroom/executors/tactician.py`, `packages/newsroom/prompts/tactician@3.md`, `packages/newsroom/templates.py` (tactician_degraded), `tests/newsroom/test_tactician.py`, `docs/evidence/latency_probe_day3.md`
- **Scope:** In: tool-using Tactician (live role), structured explanation output, degraded template, prompt caching of the league block, one live end-to-end explained cue. Out: Opus golden runs (T-042), Panel (T-041).
- **Acceptance criteria:**
  - Output validates against `schemas/explanation.schema.json`; every claim cites evidence IDs; timeout 12 s with one retry, then the template.
  - One live explained cue on a golden moment passes the Fact Checker; its event-to-cue latency is recorded. If > 15 s, apply the TECH_PLAN 1.13 response (`max_tool_rounds` 1) and record both numbers. Dev spend ≤ $0.50.
- **Verification:** `pytest tests/newsroom/test_tactician.py -q && WHYLINE_LIVE_TESTS=1 pytest tests/newsroom/test_tactician.py -q -m live`
- **Brief:**
  ```text
  Read TECH_PLAN 1.7 agent table row Tactician and the Agents attach line (MCPStreamableHTTPTool(name="whyline", url="http://localhost:8080/mcp")), ADR-004, config/models.yaml tactician_live and header rules (effort explicit; thinking adaptive; no forced tool_choice; output_config.format; no prefill; server-side fallback beta), budgets.yaml tokens block (league block 1,500 tokens, cached).
  Tools: query_events, get_pitch_control, simulate_counterfactual, player_stats; max_tool_rounds 2.
  If AnthropicClient in agent-framework-anthropic does not expose output_config.format, run the tool rounds with the Agent and make the final structured turn with the anthropic SDK messages.parse (pins.txt note); read the installed source first.
  tactician@3.md: explain why the moment mattered using only tool results; every number a claim with evidence ids.
  For the probe run mcp_server and the worker locally (the api is not needed) and write the measured timings to docs/evidence/latency_probe_day3.md.
  Acceptance: pytest tests/newsroom/test_tactician.py -q
  ```

### T-033 API cue fan-out, ingest and control endpoints
- **Owner:** C · **Day:** 3 · **Estimated hours:** 2.5
- **Depends on:** T-008, T-017, T-021, T-022
- **Files:** `packages/api/{cues.py,ingest.py,control.py,docs.py,messages.py}`, `packages/kickoff/stream.py`, `tests/api/{test_cues.py,test_fanout_perf.py}`
- **Scope:** In: `GET /match/{id}/cues?viewer=…`, `POST /ingest/events`, `POST /ingest/tracking`, `POST /producer/decision`, `POST /demo/kill`, `GET /spend`, every 1.9 WebSocket message type, server-side target filtering, a read-only document endpoint, `kickoff play --target api`. Out: kill/restart mechanics (T-051), Web PubSub (T-075).
- **Acceptance criteria:**
  - Cue fan-out to 20 WebSocket clients < 50 ms (TECH_PLAN 1.4); each client receives only cues whose `targets` match its profile; studio receives all.
  - `GET /match/{id}/doc/{collection}/{doc_id}` returns blackboard docs (counterfactuals, explanations, pitch control) for the Why? drawer and `/replay3d`; documented as an addition to the 1.4 endpoint list in `packages/api/README.md`.
- **Verification:** `pytest tests/api/test_cues.py tests/api/test_fanout_perf.py -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.4 api (endpoint list), 1.9 WebSocket message table (hello, tracking_frame, event, fact, moment, cue, cue_remove, trace, request_info, mode, spend, oracle), 1.1 live data flow, schemas/viewer_profile.schema.json, schemas/cue.schema.json targets.
  Watch blackboard `cues`, `moments`, `facts`, `traces` (T-017 watch) and forward as messages. GET /spend reads SpendGuard totals {match_usd, day_usd, caps}.
  POST /producer/decision {request_id, decision} writes a decision doc the worker reads (T-050). POST /demo/kill {target} is a stub returning 202 until T-051.
  The doc endpoint is read-only and whitelists collections (counterfactuals, explanations, pitch_control, moments, facts).
  packages/kickoff/stream.py: `python -m kickoff play --seed N --target api` posts events and 10 Hz tracking to /ingest/* in real time.
  Acceptance: pytest tests/api/test_cues.py tests/api/test_fanout_perf.py -q
  ```

### T-034 Studio console core
- **Owner:** C · **Day:** 3 · **Estimated hours:** 4
- **Depends on:** T-033
- **Files:** `apps/studio/src/{App.tsx,stream/StreamProvider.tsx,components/{Header.tsx,MomentQueue.tsx,AgentTrace.tsx,CueList.tsx,WhyDrawer.tsx,Blackboard.tsx}}`, `tests/apps/test_studio.py`
- **Scope:** In: header with mode badge and spend, moment queue, agent trace rows, cue list with verified flag and producer status, Why? drawer (claims with evidence, pitch-control thumbnail, counterfactual mini-chart), blackboard facts panel. Out: producer and demo controls (T-035).
- **Acceptance criteria:**
  - Trace rows show executor, model, latency, tokens, cache_hit, status; rows are red for `cache_miss` or `interrupted`.
  - Clicking a cue opens the drawer and every evidence ID resolves through the doc endpoint (checked in the test on the fixture cue).
- **Verification:** `npm --prefix apps/studio run build && pytest tests/apps/test_studio.py -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.9 "Studio console" (component tree and contents), 1.3 traces document, schemas/explanation.schema.json and counterfactual.schema.json, docs/cue_contract.md.
  Vite + React + TS with the T-001 pins; port 5174; no UI library. Reuse the overlay StreamProvider pattern (copy, do not import across apps).
  Why? drawer: claim text, kind, value, unit, evidence ids as links; pitch-control thumbnail drawn from the pc_ doc grid [34,53]; counterfactual mini-chart baseline vs alternative with n, horizon, seed.
  Studio receives every cue regardless of mode (connect with mode=studio).
  Acceptance: npm --prefix apps/studio run build && pytest tests/apps/test_studio.py -q
  ```

### T-035 Studio producer panel and demo controls
- **Owner:** C · **Day:** 3 · **Estimated hours:** 1.5
- **Depends on:** T-034
- **Files:** `apps/studio/src/components/{ProducerPanel.tsx,DemoControls.tsx}`, `tests/apps/test_studio_controls.py`
- **Scope:** In: approve/veto on `request_info`, veto of any shown cue (emits `cue_remove`), kill newsroom, speed, seek. Out: the server-side kill and resume (T-051), recap approval logic (T-050).
- **Acceptance criteria:**
  - Approve and veto post `POST /producer/decision {request_id, decision}`; vetoing a shown cue removes it from overlay and fan within 200 ms (test with two pages).
  - Kill posts `POST /demo/kill {target: "newsroom"}`; speed and seek post `/replay/control`.
- **Verification:** `npm --prefix apps/studio run build && pytest tests/apps/test_studio_controls.py -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.7 "Producer veto" (request_info flow; non-recap cues auto-approved; the studio can still veto a shown cue, which emits cue_remove), 1.9 studio tree (ProducerPanel, DemoControls), 1.4 api endpoints.
  ProducerPanel lists pending request_info messages {request_id, cue} with Approve / Veto / Hold (producer_status values: approved, vetoed, held).
  DemoControls: Kill newsroom, speed x1/x2/x5/x10, seek to clock (mm:ss).
  Server must turn a veto of a shown cue into a cue_remove broadcast; add that to packages/api/control.py if T-033 did not.
  Acceptance: npm --prefix apps/studio run build && pytest tests/apps/test_studio_controls.py -q
  ```

**End of day 3: done means** heads pass their 1.6 gates, the policy is training overnight, the full explained path (Scout → Proposer → Rollout → Tactician → Narrator → Fact Checker → Director) produced one verified live cue with its latency recorded, and the studio shows moments, traces, cues and the Why? drawer with working veto and kill buttons.

---

## Day 4 — Sat 24 Oct

### T-036 policy_v1 decision-only rollout path and MPS performance test
- **Owner:** A · **Day:** 4 · **Estimated hours:** 1.5
- **Depends on:** T-016, T-028
- **Files:** `packages/rollout/policy_engine.py`, `packages/policy/loader.py`, `tests/rollout/{test_policy_perf.py,test_policy_determinism.py}`
- **Scope:** In: `engine="policy_v1"` in `rollout`, decision points per 1.5, the ungated-load guard, CPU sampling for determinism. Out: horizons > 8 s for the learned engine (rejected by ADR-002).
- **Acceptance criteria:**
  - B=200, 8 s, decision-only (~15 policy calls) ≤ 0.3 s on MPS and ≤ 1.2 s on CPU (`budgets.yaml` `policy_200x8s_decision_only_*`); `horizon_s > 8` with policy_v1 raises.
  - Same inputs give byte-identical `Futures` on MPS twice and on MPS vs CPU (logits moved to CPU before `torch.multinomial`).
  - Loading a checkpoint whose `metrics.json` fails the gates raises unless `WHYLINE_ALLOW_UNGATED_POLICY=1`.
- **Verification:** `pytest tests/rollout/test_policy_perf.py tests/rollout/test_policy_determinism.py -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.5 "Decision points" (policy called when a player gains control or 1.0 s since the last call; otherwise the action persists; off-ball players follow role targets with the physics prior), "Determinism", "Budgets", ADR-002, 1.4 policy (failure behaviour), FEASIBILITY_AUDIT B.1.
  Use the latest epoch checkpoint from the overnight run (T-028) for timing; the gate (T-037) decides what ships.
  Generator: torch.Generator().manual_seed(seed); move logits to CPU before torch.multinomial.
  Pins: torch 2.14.1, numpy 2.5.4. Device from WHYLINE_DEVICE; the CPU path must also pass because Azure has no GPU (ADR-009).
  Acceptance: pytest tests/rollout/test_policy_perf.py tests/rollout/test_policy_determinism.py -q
  ```

### T-037 Policy evaluation and day-4 gate decision
- **Owner:** A · **Day:** 4 · **Estimated hours:** 2
- **Depends on:** T-036
- **Files:** `packages/policy/evaluate.py`, `packages/policy/artifacts/{policy_v1.pt,metrics.json,gate.json}`, `docs/evidence/policy_gate_day4.md`, `docs/evidence/policy_clips/` (20 PNG strips)
- **Scope:** In: every 1.6 gate metric, 20 rollouts of 8 s on held-out states, clip review, the written decision. Out: policy v2 (T-072).
- **Acceptance criteria:**
  - `metrics.json` reports top-1 kind accuracy (≥ 0.45), top-3 kind+target (≥ 0.80), 4 s ball FDE (≤ velocity baseline), teleports (0), shape-collapse rate (≤ 5%), offside violations per rollout (≤ 0.2), each against its baseline (TECH_PLAN 1.6).
  - `gate.json` = `{"engine": "policy_v1" | "scripted_v1", "reasons": [...]}`; if any gate fails, `scripted_v1` is the engine for every cached counterfactual (1.6 fallback, 1.13 row 1).
- **Verification:** `python -m policy.evaluate --ckpt packages/policy/artifacts/policy_v1.pt --test data/grf/dataset/test.npz --n-rollouts 20 && python -c "import json;print(json.load(open('packages/policy/artifacts/gate.json')))"`
- **Brief:**
  ```text
  Read TECH_PLAN 1.6 "Evaluation and gates" (table and fallback decision), 1.13 row "Policy futures unconvincing" (trigger 24 Oct), FEASIBILITY_AUDIT B.1 failure modes and B.2 guards.
  Implement exactly: def evaluate(ckpt: Path, test: Path, n_rollouts: int = 20) -> EvalReport
  Baselines: majority class; "pass to nearest free teammate"; velocity extrapolation for FDE. Teleport = any player speed > 12 m/s. Shape collapse = team hull area falls > 50% within 8 s.
  Render 20 rollouts as PNG strips (matplotlib, 1 frame per second) for human review; note teleports, bunching, frozen keeper.
  Write gate.json and docs/evidence/policy_gate_day4.md with the numbers and the decision. Never edit thresholds.
  Acceptance: the verification command runs and gate.json exists.
  ```

### T-038 CacheManifest and CacheClient
- **Owner:** B · **Day:** 4 · **Estimated hours:** 2
- **Depends on:** T-018, T-030
- **Files:** `packages/cache/{manifest.py,client.py,errors.py}`, `tests/cache/{test_manifest.py,test_client.py}`
- **Scope:** In: manifest load/save/key/verify, `CacheClient` implementing `LLMClient` and `RolloutClient` with simulated latency, `CacheMiss`, MCP `simulate_counterfactual` cache hit in replay mode. Out: writing entries (T-039, T-042).
- **Acceptance criteria:**
  - Keys follow `<match_id>/<moment_id>/<producer>@<version>/<model>/s<seed>`; manifests validate against `schemas/cache_manifest.schema.json`; `verify_hashes()` detects one flipped byte.
  - Replay sleep = `simulated_latency_ms × (1 / WHYLINE_REPLAY_SPEED)`; a miss raises `CacheMiss` (never silent).
- **Verification:** `pytest tests/cache -q`
- **Brief:**
  ```text
  Read TECH_PLAN ADR-003, 1.4 cache, 1.8 "Precompute" (key format) and "Replay serving", schemas/cache_manifest.schema.json, config/.env.example (WHYLINE_MODE, WHYLINE_CACHE_DIR).
  Implement exactly:
    class CacheManifest: load/save; key(match_id, moment_id, producer, version, model, seed) -> str; verify_hashes() -> bool
    class CacheClient(LLMClient, RolloutClient)   # serves cache hits with simulated latency; misses raise CacheMiss in replay mode
  Manifest kinds are the schema enum; Oracle, Dugout and Decision Index entries use kind "analytics" with producer oracle/dugout/decision_index (no schema change).
  Inject CacheClient when WHYLINE_MODE=replay and LiveClient otherwise (newsroom config and mcp_server).
  Acceptance: pytest tests/cache -q
  ```

### T-039 Golden precompute, part 1: analytics, moments, counterfactuals
- **Owner:** A · **Day:** 4 · **Estimated hours:** 2
- **Depends on:** T-026, T-029, T-037, T-038
- **Files:** `scripts/precompute.py`, `data/matches/4242/cache/{analytics/,pitch_control/,moments.jsonl,counterfactuals/,manifest.json}`, `packages/demo/golden_moments.yaml`
- **Scope:** In: steps 1–3 of TECH_PLAN 1.8 with the engine from `gate.json`; selection of the storyboard moments. Out: model calls (T-042), Oracle/Dugout/Decision Index entries (T-046–T-048).
- **Acceptance criteria:**
  - Every explained moment has a cached `cf_*.json` valid against the counterfactual schema, n = 200, horizon 8 s, seed 4242, engine as in `gate.json`.
  - `golden_moments.yaml` names the Sliding Doors moment, the Fourth Official calls, Oracle and Dugout times and the 44:10 kill target with their IDs; IDs in schema examples (e.g. `cf_000077`) are illustrative.
  - `manifest.json` lists every file with SHA-256; `python scripts/validate_schemas.py` passes on the cache.
- **Verification:** `python scripts/precompute.py --seed 4242 --mode batch --stages analytics,moments,counterfactuals && python scripts/validate_schemas.py`
- **Brief:**
  ```text
  Read TECH_PLAN 1.8 "Precompute" steps 1-3 and "Golden match", 1.3 pitch_control document (grid [34,53] float16, .npz + JSON stub), ADR-003, packages/policy/artifacts/gate.json, DEMO_MASTERPLAN_50USD.md §7 (storyboard beats).
  scripts/precompute.py --seed 4242 --mode batch|live --stages ... --hand-review K (later stages are added by T-042 and T-057; keep the CLI open for them).
  Steps: analytics per frame -> cache/analytics/*.npz; pitch-control snapshot per moment -> cache/pitch_control/pc_*.npz; Scout over the match -> cache/moments.jsonl; sliding_doors for every explained moment -> cache/counterfactuals/cf_*.json.
  Storyboard names (Okafor, Silva, Reyes) may be re-assigned in data/league/players.json to the actual player ids of the chosen moment; events hold ids only, so hashes do not change.
  Acceptance: python scripts/precompute.py --seed 4242 --mode batch --stages analytics,moments,counterfactuals && python scripts/validate_schemas.py
  ```

### T-040 Counterfactual calibration plot and placebo test
- **Owner:** A · **Day:** 4 · **Estimated hours:** 2
- **Depends on:** T-016, T-025, T-037
- **Files:** `packages/evals/calibration.py`, `packages/evals/out/{calibration.png,calibration.json}`
- **Scope:** In: 300 held-out matches (seeds 51–350), every explained moment, unforced branch vs realised outcome, Brier, reliability diagram, placebo test. Out: n-sensitivity study (T-079).
- **Acceptance criteria:**
  - Brier ≤ 0.18 with base rate reported; 10-bin reliability diagram saved (TECH_PLAN 1.11).
  - Placebo: forcing the actual action reproduces the baseline within the 95% interval on ≥ 95% of moments.
- **Verification:** `python -m evals.calibration --seeds 51..350 --engine-from packages/policy/artifacts/gate.json --out packages/evals/out`
- **Brief:**
  ```text
  Read TECH_PLAN 1.11 row "Counterfactual calibration", FEASIBILITY_AUDIT B.2 "Exact evaluation protocol" (n=200, horizon 8 s, P(goal for attacking team within horizon) vs realised outcome; Brier, log-loss, reliability diagram, 10 bins), 1.5 horizon hand-off.
  Re-simulate each held-out match from its seed to reach branch states (T-016 branch). Run in background with multiprocessing on CPU (scripted) or MPS (policy); expect about an hour (estimate).
  Write calibration.json {brier, log_loss, base_rate, n_moments, placebo_pass_rate, engine} and calibration.png.
  Libraries: numpy, scikit-learn (Brier score, calibration curve) and matplotlib at the T-001 pins.
  Acceptance: the verification command exits 0 and calibration.json shows brier <= 0.18 and placebo_pass_rate >= 0.95.
  ```

### T-041 Panel via GroupChatBuilder
- **Owner:** B · **Day:** 4 · **Estimated hours:** 2.5
- **Depends on:** T-032
- **Files:** `packages/newsroom/executors/panel.py`, `packages/newsroom/prompts/{pundit_press@1.md,pundit_possession@1.md,pundit_sceptic@1.md,chair@1.md}`, `tests/newsroom/test_panel.py`
- **Scope:** In: three pundits with distinct philosophies and tools, chair as manager, three-round limit, sub-workflow inside `PanelExecutor`, structured outputs, drop-on-timeout. Out: Panel on the fast path (never; 1.14 #4).
- **Acceptance criteria:**
  - Pundit output `{take, claims[], stance}`; chair `{consensus, dissent, headline}`; every pundit claim cites a counterfactual or pitch-control ID and passes the Fact Checker.
  - 25 s total budget; on timeout the panel cue is dropped (no retry). Dev spend ≤ $0.50.
- **Verification:** `pytest tests/newsroom/test_panel.py -q && WHYLINE_LIVE_TESTS=1 pytest tests/newsroom/test_panel.py -q -m live`
- **Brief:**
  ```text
  Read TECH_PLAN 1.7 agent table row Panel and the GroupChatBuilder paragraph (chair as manager, fixed three-round limit, sub-workflow inside PanelExecutor), FEASIBILITY_AUDIT C.2 (the Panel is the genuinely multi-agent component), config/models.yaml panel_pundit and panel_chair.
  GroupChatBuilder comes from agent_framework.orchestrations (agent-framework-orchestrations 1.3.2). Read the installed source for the manager and round-limit parameters; do not guess.
  Pundits: claude-sonnet-5-5, effort medium, max_tokens 500, tools simulate_counterfactual and get_pitch_control over MCP, max_tool_rounds 1. Chair: effort low, max_tokens 300.
  Philosophies: press (pressing and transitions), possession (control and structure), sceptic (challenges the counterfactual's assumptions with its own number).
  Acceptance: pytest tests/newsroom/test_panel.py -q
  ```

### T-042 Golden precompute, part 2: model calls via batch (Vertex AI batch prediction since ADR-004 Revision 1)
- **Owner:** B · **Day:** 4 · **Estimated hours:** 3
- **Depends on:** T-038, T-039, T-041
- **Files:** `scripts/precompute.py` (stages fast_lines, tactician, narrator, panel, factcheck), `packages/cache/batch.py`, `data/matches/4242/cache/{explanations/,fast_lines/,panel/,batches.json}`, `tests/cache/test_batch.py`
- **Scope:** In: Batch requests per role, round-by-round batches for tool use and Panel turns, Fact Checker over every output with up to two rewrites, manifest entries with latencies, tokens and costs. Out: recaps (T-050), hand review (T-057).
- **Acceptance criteria:**
  - Results are matched by `custom_id`, never by position; `custom_id` is a hash of the cache key (letters, digits, `_`, `-`, ≤ 64 chars) with the mapping in `batches.json`.
  - Every cached explanation and line has `verified` set by the Fact Checker; rejected ones were re-queued with the diff at most twice.
  - Golden precompute spend ≤ $2.00 in the ledger (was $1.50, $50 plan §3; raised by the owner on 22 Oct: no new GCP resources, so no Vertex batch bucket, so live calls at full price with gemini-4-argon for the Tactician and pundits; still under the $2.50 per-match cap); `simulated_latency_ms` comes from the measured live latency of the same role, or 4–8 s for Opus (1.8).
- **Verification:** `python scripts/precompute.py --seed 4242 --mode batch --stages fast_lines,tactician,narrator,panel,factcheck && pytest tests/cache/test_batch.py -q && python scripts/check_spend.py`
- **Brief:**
  ```text
  Read TECH_PLAN 1.8 "Precompute" steps 4, 5 and 7, ADR-003, ADR-004, 1.7 agent table, config/models.yaml (tactician_golden Opus effort high batch; narrator_fast; panel_pundit; panel_chair), config/budgets.yaml (batch_discount 0.5), $50 plan §2-3.
  Submit with client.messages.batches.create(requests=[...]) (anthropic SDK pinned at T-001), poll until processing has ended, read results by custom_id.
  Tool use: run one batch per tool round; execute tool_use blocks locally against mcp_server in replay data, then submit the next round (max_tool_rounds 3). Panel: batch all moments' round-1 turns, then round 2, then round 3, then the chair.
  If a batch has not ended after 2 h, finish the remaining requests live (non-batch) through SpendGuard and record that in batches.json.
  Every response recorded through SpendGuard with batch=True. No temperature on Opus; effort explicit; no forced tool_choice.
  Acceptance: the verification command exits 0.
  ```

### T-043 Fan app: modes, mini-pitch, cue feed, moment cards
- **Owner:** C · **Day:** 4 · **Estimated hours:** 3.5
- **Depends on:** T-033
- **Files:** `apps/fan/src/{App.tsx,stream/StreamProvider.tsx,components/{ProfilePicker.tsx,MiniPitch.tsx,CueFeed.tsx,MomentCards.tsx}}`, `tests/apps/test_fan.py`
- **Scope:** In: phone-shaped app on :5175, viewer profile (mode, club, player, metric, high-contrast), server-side filtered stream. Out: Player-Cam card (T-044).
- **Acceptance criteria:**
  - Profile validates against `schemas/viewer_profile.schema.json` and is stored client-side (try/catch around storage).
  - Switching casual ↔ analyst changes the cue feed according to `budgets.yaml` mode kinds (test counts kinds received).
- **Verification:** `npm --prefix apps/fan run build && pytest tests/apps/test_fan.py -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.9 "Fan app" tree, schemas/viewer_profile.schema.json, config/budgets.yaml director.modes (kinds per mode), DEMO_MASTERPLAN_50USD.md §7 0:56-1:24.
  Vite + React + TS with the T-001 pins, 390x844 phone frame, no UI library. MiniPitch reuses the Pitch2D drawing approach at small scale (copy, do not import across apps).
  Subscribe with WS /ws?viewer_id&mode&club&player; the server filters cues by targets (T-033).
  Pins: React, Vite and TypeScript from apps/fan/package.json (T-001); port 5175.
  Acceptance: npm --prefix apps/fan run build && pytest tests/apps/test_fan.py -q
  ```

### T-044 Player-Cam card and player_cam overlay mode
- **Owner:** C · **Day:** 4 · **Estimated hours:** 2
- **Depends on:** T-023, T-043
- **Files:** `apps/fan/src/components/PlayerCamCard.tsx`, `apps/overlay/src/modes/playerCam.ts`, `packages/api/players.py`, `tests/apps/test_player_cam.py`
- **Scope:** In: card with distance, top speed, sprints, touches, Decision Index; overlay player trail and player tags for the chosen player. Out: computing the Decision Index (T-048; fixture until then).
- **Acceptance criteria:**
  - Card numbers equal `player_stats` from MCP for the golden match (test compares against a fixture dump).
  - In `player_cam` mode only cues involving the player are shown (`only_player_involved: true` in budgets.yaml).
- **Verification:** `npm --prefix apps/fan run build && npm --prefix apps/overlay run build && pytest tests/apps/test_player_cam.py -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.9 (Fan app PlayerCamCard; overlay player_cam mode draws the player trail and shows player tags), 1.7 MCP player_stats (touches, passes, completion, xT, sprints, decision_index), config/budgets.yaml modes.player_cam.
  Data: add GET /match/{id}/players/{player_id}/stats in packages/api/players.py calling the same code as MCP player_stats; record it as an addition to the 1.4 endpoint list in packages/api/README.md.
  Sprint tag text comes from speeds() sprints (e.g. a km/h tag) and must be a verified claim when shown as a cue.
  Pins: as recorded in apps/fan and apps/overlay package.json (T-001); add no dependencies.
  Acceptance: the verification command exits 0.
  ```

### T-045 Overlay viewer modes, heatmap, threat front and referee lines
- **Owner:** C · **Day:** 4 · **Estimated hours:** 2.5
- **Depends on:** T-023, T-033
- **Files:** `apps/overlay/src/modes/{analyst.ts,casual.ts}`, `apps/overlay/src/pitch/layers/{heatmap.ts,threatFront.ts,refereeLines.ts}`, `tests/apps/test_viewer_modes.py`
- **Scope:** In: analyst (heatmap + threat front + all layers), casual (no heatmap, no ticker, allowed kinds only), heatmap from pitch-control snapshots, threat front from `oracle` messages, referee lines from `graphics.lines`. Out: Oracle numbers (T-046) and rulings (T-049); fixtures until then.
- **Acceptance criteria:**
  - Screenshot tests for analyst, casual and player_cam differ in exactly the layers listed in TECH_PLAN 1.9.
  - A `referee_line` cue draws its lines in metres with the margin label; heatmap redraw ≤ 8 ms p95.
- **Verification:** `npm --prefix apps/overlay run build && pytest tests/apps/test_viewer_modes.py -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.9 (viewer modes; oracle message {t_ms, p_shot_home, p_shot_away, zone, shooter} every 2 s; referee lines), schemas/cue.schema.json graphics.lines and layers referee_line, threat_front, heatmap, config/budgets.yaml director.modes (heatmap, threat_front flags).
  Heatmap: draw the [34,53] home-share grid (2 m cells) with a diverging palette at 35% opacity. Threat front: contour where opponent threat is highest, alpha from p_shot.
  Referee lines: animate the line drawing over 0.6 s, label margin_m.
  Until T-046 and T-049 land, drive these layers from fixture oracle messages and a fixture referee_line cue added to the T-003 script.
  Acceptance: npm --prefix apps/overlay run build && pytest tests/apps/test_viewer_modes.py -q
  ```

**End of day 4: done means** the policy gate is decided in writing, every golden explained moment has a cached counterfactual and Opus explanation verified by the Fact Checker (≤ $1.50 spent), the Panel works, calibration is plotted, and the fan app and all three viewer modes render.

---
## Day 5 — Sun 25 Oct

### T-046 Oracle wrapper and replay loop
- **Owner:** A · **Day:** 5 · **Estimated hours:** 2
- **Depends on:** T-037, T-038
- **Files:** `packages/rollout/oracle.py`, `scripts/precompute.py` (stage oracle), `data/matches/4242/cache/oracle/`, `packages/api/oracle.py`, `tests/rollout/test_oracle.py`
- **Scope:** In: `oracle()`, precomputed every 2 s at n = 200 for the golden match, live every 5 s at n = 50, `oracle` WS messages from the api. Out: threat-front drawing (T-045).
- **Acceptance criteria:**
  - Returns `p_shot_10s` per team, most frequent shot zone and shooter; cached every 2 s of match time (TECH_PLAN 1.5, 1.14 #2).
  - Oracle cues are only allowed when `p_shot ≥ 0.30` (budgets.yaml); the storyboard Oracle beat in `golden_moments.yaml` has p_shot ≥ 0.30.
- **Verification:** `pytest tests/rollout/test_oracle.py -q && python scripts/precompute.py --seed 4242 --mode batch --stages oracle`
- **Brief:**
  ```text
  Read TECH_PLAN 1.5 "Callers" (oracle: one rollout from the current state every 2 s in replay, every 5 s live with B=50), 1.14 disagreement 2, 1.4 rollout, 1.9 oracle message, config/budgets.yaml hard_rules (oracle_min_p_shot 0.30, oracle_refresh_s 2), gate.json for the engine.
  Implement exactly: def oracle(match: MatchRef, t_ms: int, n: int = 100, horizon_s: float = 8, seed=...) -> Forecast   # p_shot_10s per team, likely zone, likely shooter
  A 10 s shot window with an 8 s learned cap: score seconds 8-10 with GoalIn8sHead-style hand-off and label the value an estimate.
  Cache entries kind "analytics", producer "oracle". packages/api/oracle.py streams them on the replay clock.
  Acceptance: the verification command exits 0.
  ```

### T-047 Dugout parameter search and "Dugout called it" log
- **Owner:** A · **Day:** 5 · **Estimated hours:** 2
- **Depends on:** T-037, T-038
- **Files:** `packages/rollout/dugout.py`, `scripts/precompute.py` (stage dugout), `data/matches/4242/cache/dugout/`, `packages/evals/dugout_log.py`, `tests/rollout/test_dugout.py`
- **Scope:** In: `dugout()` over a small grid of style deltas, ranking by Δwin probability, a log comparing the recommendation with what the team did in the following 10 minutes. Out: live Dugout in Azure beyond n = 100.
- **Acceptance criteria:**
  - At 60:00 of the golden match, 3 options with Δwin_prob, n, horizon and seed are cached as an `options_card` cue source.
  - `dugout_log.py` writes `packages/evals/out/dugout_log.json` with the recommendation, the observed style change and whether it matched; the "Dugout called it" caption is used only if it matched.
- **Verification:** `pytest tests/rollout/test_dugout.py -q && python -m evals.dugout_log --seed 4242`
- **Brief:**
  ```text
  Read TECH_PLAN 1.5 "Callers" (dugout: one rollout per option with overrides.styles for one team; ranked by Δwin_prob), 1.4 rollout, schemas/cue.schema.json (layer options_card, kind dugout), FEASIBILITY_AUDIT C.6 ("Dugout called it" needs a log), DEMO_MASTERPLAN §7 0:56-1:10.
  Implement exactly: def dugout(match: MatchRef, t_ms: int, team: str, options: list[StyleDelta], n: int = 100, horizon_s: float = 8, seed=...) -> list[OptionResult]
  Grid: 3 x 3 over press_height and directness deltas (±0.15), pick the top 3. Observed change = style features measured from tracking in 60:00-70:00 vs 50:00-60:00.
  Cache kind "analytics", producer "dugout".
  Acceptance: the verification command exits 0.
  ```

### T-048 Decision Index precompute
- **Owner:** A · **Day:** 5 · **Estimated hours:** 2
- **Depends on:** T-039
- **Files:** `packages/rollout/decision_index.py`, `scripts/precompute.py` (stage decision_index), `data/matches/4242/cache/decision_index.json`, `tests/rollout/test_decision_index.py`
- **Scope:** In: a rollout at every on-ball decision of the golden match (~1,500), per-player Decision Index, the live approximation from the goal-in-8-s head swing. Out: live per-decision rollouts (1.14 #3).
- **Acceptance criteria:**
  - Every on-ball decision in the golden match has a cached value; per-player index in [0, 100] with the formula documented in the module docstring.
  - Precompute finishes in < 30 min on this Mac (estimate from 1.5 budgets); live approximation correlates ≥ 0.5 (Spearman) with the precomputed index on the golden match (report the number).
- **Verification:** `pytest tests/rollout/test_decision_index.py -q && python scripts/precompute.py --seed 4242 --mode batch --stages decision_index`
- **Brief:**
  ```text
  Read TECH_PLAN 1.14 disagreement 3 (Decision Index precomputed for the golden match only; live uses the goal-in-8-s head swing), 1.8 precompute step 3 ("every on-ball decision for the Decision Index"), 1.5 budgets, 1.7 player_stats (decision_index field).
  Index per decision = p_goal of the chosen action minus the best alternative among the top-3 the engine considered, n=50, horizon 8 s; aggregate per player as a percentile.
  Cache kind "analytics", producer "decision_index". player_stats (T-030) reads it in replay mode.
  Run in the background with multiprocessing: scripted_v1 on CPU, or the gate.json policy on MPS.
  Acceptance: the verification command exits 0.
  ```

### T-049 Fourth Official rules engine and executor
- **Owner:** A · **Day:** 5 · **Estimated hours:** 2
- **Depends on:** T-013, T-018, T-021, T-038
- **Files:** `packages/fourth_official/{rules.py,offside.py,foul.py,cue.py,rules.yaml}`, `packages/newsroom/executors/fourth_official.py`, `scripts/precompute.py` (stage fourth_official), `tests/fourth_official/test_geometry.py`
- **Scope:** In: offside and foul geometry, rules library (offside, penalty area, handball zones, back-pass), ruling-to-cue, the newsroom executor, cached rulings for the golden match. Out: VAR-style video review.
- **Acceptance criteria:**
  - Hand-built frame tests: onside/offside by 0.4 m, level is onside, own-half exception, foul in/out of the box; each check < 5 ms (TECH_PLAN 1.4).
  - Every offside, foul and card in the golden match has a cached `referee_line` cue with `graphics.lines` and the margin; cues are `verified` by construction.
- **Verification:** `pytest tests/fourth_official -q && python scripts/precompute.py --seed 4242 --mode batch --stages fourth_official`
- **Brief:**
  ```text
  Read TECH_PLAN 1.4 fourth_official (copy exactly):
    def check_offside(frame: Frame, pass_event: Event) -> OffsideRuling | None     # margin_m, last_defender, line [[x,y1],[x,y2]]
    def check_foul(events: list[Event], frames: TrackingWindow) -> FoulRuling | None  # contact point, closing speed, in_box
    def ruling_to_cue(r: Ruling, t_ms: int) -> Cue                                  # layer referee_line, kind fourth_official, verified by construction
  Also 1.7 agent table row Fourth Official (code, 5 ms), schemas/event.schema.json attrs (offside: offside_player, margin_m, last_defender, pass_event_id; foul: contact_point, fouled_player), schemas/cue.schema.json graphics.lines.
  Offside line = second-last opponent (keeper counts) at the pass frame, attacking direction from period.
  Cue text numbers ("0.4 m beyond the last defender") are claims citing the offside event id, so the Fact Checker can also verify them.
  Acceptance: the verification command exits 0.
  ```

### T-050 Recap executor with producer approval; top_moments and timeline tools
- **Owner:** B · **Day:** 5 · **Estimated hours:** 2.5
- **Depends on:** T-030, T-033, T-042
- **Files:** `packages/newsroom/executors/{recap.py,director.py}`, `packages/newsroom/prompts/recap@2.md`, `packages/mcp_server/tools_recap.py`, `scripts/precompute.py` (stage recap), `tests/newsroom/test_recap_veto.py`
- **Scope:** In: Recap (Opus batch for the golden match, Sonnet live), `top_moments` and `timeline` MCP tools, `handle_recap` with `ctx.request_info` and `on_decision` with `@response_handler`, worker publishing `request_info` and resuming with responses. Out: half-time studio cards UI (T-076).
- **Acceptance criteria:**
  - A vetoed recap never reaches the CueBus; an approved one does with `producer_status = "approved"`; the test resumes with `workflow.run(stream=True, responses=..., checkpoint_id=..., checkpoint_storage=storage)`.
  - Half-time and full-time recaps are cached and verified; recap spend ≤ $0.30.
- **Verification:** `pytest tests/newsroom/test_recap_veto.py -q && python scripts/precompute.py --seed 4242 --mode batch --stages recap`
- **Brief:**
  ```text
  Read TECH_PLAN 1.7 "Producer veto" (copy handle_recap and on_decision verbatim), agent table row Recap, MCP list (top_moments(match_id: str, period: int | None = None, k: int = 5) -> list[dict]; timeline(match_id: str) -> dict), FEASIBILITY_AUDIT E.4 (RequestInfoExecutor does not exist), config/models.yaml recap and recap_live.
  The worker collects events with event.type == "request_info", writes {request_id, cue} for the api to broadcast, waits for POST /producer/decision (T-033), then resumes with responses={request_id: ProducerDecision(status=...)}.
  Recap output: recap_card list (three sliding-doors moments of the half, chaos timeline summary, player of the half), every number a verified claim.
  Pins: agent-framework-core 1.22.0 (ctx.request_info, @response_handler); anthropic pinned at T-001 for the Opus batch recap. Spend ≤ $0.30.
  Acceptance: the verification command exits 0.
  ```

### T-051 Supervisor, kill switch and checkpoint resume
- **Owner:** B · **Day:** 5 · **Estimated hours:** 2.5
- **Depends on:** T-018, T-033, T-038
- **Files:** `packages/newsroom/{supervisor.py,resume.py}`, `packages/api/control.py` (kill), `tests/chaos/test_resume.py`, `docs/evidence/kill_resume.log`, `.github/workflows/ci.yml` (chaos-resume)
- **Scope:** In: SIGKILL of the worker between Tactician and Narrator, restart within 2 s, resume of runs without a terminal cue, `on_checkpoint_save/restore`, the four log lines, a one-run chaos test. Out: the 20-run CI gate (T-091), Cosmos storage (T-058).
- **Acceptance criteria:**
  - The log shows, in order: `kill target=newsroom run_id=… at_executor=tactician`, `restart pid=…`, `resume run_id=… checkpoint_id=…`, `cue c_… delivered resumed_from_checkpoint=…` (TECH_PLAN 1.7).
  - The resumed cue has the same `cue_id` as an uninterrupted run and `provenance.resumed_from_checkpoint` set.
- **Verification:** `pytest tests/chaos/test_resume.py -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.7 "Checkpoints, resume and the kill-switch demo" (steps 1-5 and the log lines), ADR-005, FEASIBILITY_AUDIT C.2 (make recovery demonstrable), packages/demo/golden_moments.yaml (the 44:10 run).
  POST /demo/kill {target: newsroom}: the api waits until the trace shows the target run finished TacticianExecutor and has not started NarratorExecutor, then sends SIGKILL to the worker pid.
  supervisor.py restarts the worker within 2 s. On start: storage.list_checkpoints(workflow_name="newsroom"); for each run without a terminal cue, workflow.run(checkpoint_id=cp.checkpoint_id, checkpoint_storage=storage, stream=True).
  Executors holding in-flight data implement on_checkpoint_save / on_checkpoint_restore. Use FileCheckpointStorage(WHYLINE_CHECKPOINT_DIR).
  Save the demo log to docs/evidence/kill_resume.log. Fill in the chaos-resume CI job (one run, in-memory engine, as 1.7 says).
  Acceptance: pytest tests/chaos/test_resume.py -q
  ```

### T-052 Azure Bicep modules, containers and first azd deploy
- **Owner:** B · **Day:** 5 · **Estimated hours:** 3
- **Depends on:** T-009, T-030, T-033
- **Files:** `infra/main.bicep`, `infra/modules/{monitoring.bicep,aca-env.bicep,aca-app.bicep,swa.bicep,keyvault.bicep}`, `packages/{api,mcp_server,newsroom}/Dockerfile`, `infra/README.md`
- **Scope:** In: Log Analytics + App Insights, Container Apps environment and three apps (scale to zero), three Static Web Apps (free), Key Vault with references for `ANTHROPIC_API_KEY` and `GOOGLE_API_KEY`, managed identity, replay mode served from the image. Out: Cosmos (T-058), Web PubSub (T-075), Event Hubs (optional, not built).
- **Acceptance criteria:**
  - `azd up` completes; `GET https://<api>/health` returns 200; the hosted overlay plays the golden match in replay mode.
  - No secret value appears in Bicep, parameters, images or logs; Key Vault secret values are set by a person.
- **Verification:** `az bicep build --file infra/main.bicep --stdout > /dev/null && curl -fsS "$(azd env get-value API_URL)/health"`
- **Brief:**
  ```text
  Read TECH_PLAN ADR-009, 1.10 "Azure (free account)" (services table, Bicep module list, azure.yaml services, azd 1.36.0, secrets via Key Vault references and Entra managed identity), FEASIBILITY_AUDIT Part A rows 51-53 (no GPU quota; consumption free grant; Web PubSub free 20 connections).
  Dockerfiles: python:3.12-slim, install from requirements.lock, copy only the needed packages and data/matches/4242 (replay), run uvicorn api.main:app / python -m mcp_server / python -m newsroom.supervisor.
  Container Apps: consumption, min replicas 0, ingress for api and mcp only.
  Human step: run `azd up` yourself after `azd auth login`; set the Key Vault secret values in the portal or with `az keyvault secret set` typed by you. The session never sees key values.
  Acceptance: az bicep build --file infra/main.bicep --stdout > /dev/null && curl -fsS "$(azd env get-value API_URL)/health"
  ```

### T-053 /replay3d React-Three-Fiber Sliding Doors scene
- **Owner:** C · **Day:** 5 · **Estimated hours:** 7
- **Depends on:** T-024, T-033
- **Files:** `apps/overlay/src/replay3d/{Replay3D.tsx,Stadium.tsx,Players.tsx,Ball.tsx,GhostPaths.tsx,Cameras.tsx,SwingBarOverlay.tsx}`, `apps/overlay/src/routes.tsx`, `tests/apps/test_replay3d.py`
- **Scope:** In: route `/replay3d?cf=<id>`, stadium bowl, pitch plane, capsule players in kit colours with number sprites, ball, two cameras (broadcast wide, behind the player), 200 ghost ball paths coloured by branch, the alternative as an orange dashed trail, DOM swing bar, record mode. Out: humanoid models or animations (no licence-clean CC0 option; audit A.1 row 62); full 3D broadcast (ADR-008).
- **Acceptance criteria:**
  - A frame renders by end of day 5 (TECH_PLAN 1.13 trigger 25 Oct); 20 s at 1920×1080 records at ≥ 30 fps in `?record=1`.
  - `window.__whyline.seek(clock)` and camera switching work; no external 3D assets are loaded.
- **Verification:** `npm --prefix apps/overlay run build && pytest tests/apps/test_replay3d.py -q`
- **Brief:**
  ```text
  Read TECH_PLAN ADR-008, 1.9 overlay route /replay3d (full scene spec and recording flags), schemas/counterfactual.schema.json (futures_sample, alternative, n, horizon_s, seed), FEASIBILITY_AUDIT Part A rows 61-62 (R3F versions; no licence-clean viewer or CC0 player models).
  Pins: three 0.186.1, @react-three/fiber 9.8.2, @react-three/drei 10.7.9 (apps/overlay/package.json from T-001).
  Load the counterfactual via GET /match/{id}/doc/counterfactuals/{cf_id} (T-033) and positions at t_ms from the tracking stream or a seek.
  Ghost paths: up to 200 translucent lines, Catmull-Rom smoothed from 1 Hz points. Swing bar is a DOM overlay. Kit colours from public/league.json.
  If no frame renders by 18:00 today, stop: the video uses the 2.5D ghost trail and this route is cut (TECH_PLAN 1.13).
  Acceptance: npm --prefix apps/overlay run build && pytest tests/apps/test_replay3d.py -q
  ```

**End of day 5: done means** Oracle, Dugout, Decision Index and Fourth Official outputs are cached, recaps go through producer approval, the kill switch resumes from a named checkpoint with the same cue ID, the hosted Azure build serves replay mode, and the 3D replay renders (or is formally cut).

---

## Day 6 — Mon 26 Oct

### T-054 MomentEncoder, cluster names and similar_moments
- **Owner:** A · **Day:** 6 · **Estimated hours:** 2
- **Depends on:** T-025, T-030
- **Files:** `packages/heads/moment_encoder.py`, `packages/heads/artifacts/{moment_encoder.pt,clusters.json,metrics_encoder.json}`, `packages/mcp_server/tools_similar.py`, `tests/heads/test_moment_encoder.py`
- **Scope:** In: autoencoder over the downsampled pitch-control grid + 12 features → 64-d, k-means k = 6, one `cluster_namer` call, the `similar_moments` tool. Out: contrastive encoders.
- **Acceptance criteria:**
  - Cluster purity vs hidden phases ≥ 0.6 (TECH_PLAN 1.6); training ≈ 20 min on MPS.
  - `similar_moments(match_id, t_ms, k=3)` returns golden-season neighbours; naming spend ≤ $0.05.
- **Verification:** `pytest tests/heads/test_moment_encoder.py -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.6 heads table row "Moment encoder" (21x14 grid + 12 features -> 64-d; k-means k=6; purity ≥ 0.6; clusters named once by cluster_namer), 1.4 heads (class MomentEncoder: def encode(self, pc, features) -> np.ndarray[64]; def phase(self, z) -> str), 1.7 MCP similar_moments(match_id: str, t_ms: int, k: int = 3) -> list[dict], config/models.yaml cluster_namer.
  Purity uses truth.json phases (evaluation only; never an input feature).
  cluster_namer: one claude-sonnet-5-5 call with the six cluster centroids described in numbers; through SpendGuard; names stored in clusters.json.
  Pins: torch 2.14.1 on MPS; scikit-learn pinned at T-001 for k-means (k = 6, seed 4242).
  Acceptance: pytest tests/heads/test_moment_encoder.py -q
  ```

### T-055 Evals: state detection and planted-error suite
- **Owner:** A · **Day:** 6 · **Estimated hours:** 3
- **Depends on:** T-007, T-013, T-019, T-042
- **Files:** `packages/evals/{state_detection.py,planted_errors.py}`, `packages/evals/out/{state_confusion.png,state_detection.json,planted_errors.json}`
- **Scope:** In: state F1 vs hidden truth on seeds 1–50, confusion matrix, 500 planted errors (wrong number ±10%, wrong player, wrong minute, unbound number, banned word), 500 golden verified outputs for false rejects, catch table per rule. Out: latency and groundedness (T-056).
- **Acceptance criteria:**
  - State-detection F1 ≥ 0.75 (TECH_PLAN 1.11).
  - Planted errors caught 100%; false rejects ≤ 2%; per-rule catch table published.
- **Verification:** `python -m evals.state_detection --seeds 1..50 && python -m evals.planted_errors --n 500`
- **Brief:**
  ```text
  Read TECH_PLAN 1.11 rows "State-detection", "Fact Checker planted errors caught", "Fact Checker false rejects" and the planted-error design paragraph, 1.7 Fact Checker rules, FEASIBILITY_AUDIT C.6.
  State detection: StateMachine labels vs truth.json phases per 1 s, macro precision/recall/F1, confusion matrix PNG.
  Planted errors: copy a verified explanation from data/matches/4242/cache (or a golden-season one), inject exactly one error, run newsroom.factcheck.verify_claims, record which rule caught it. Use a fixed RNG seed.
  If more than 500 verified outputs are not yet available, sample with replacement from those that exist and say so in the JSON.
  Acceptance: the verification command exits 0 and both JSON files meet the thresholds.
  ```

### T-056 Evals: latency, groundedness, cost; run_evals and results.md; evals-gate
- **Owner:** A · **Day:** 6 · **Estimated hours:** 3
- **Depends on:** T-037, T-040, T-042, T-055
- **Files:** `packages/evals/{run_evals.py,latency.py,groundedness.py,cost.py,gate.py,judge.py}`, `packages/newsroom/prompts/judge@1.md`, `packages/evals/results.md`, `packages/evals/results.json`
- **Scope:** In: latency p50/p95 from traces, own groundedness evaluator, cost per match from the ledger, the CI judge sample, `run_evals.py` assembling every 1.11 number, the `evals-gate` CI job. Out: Foundry Evaluations (T-086), live judge run numbers (T-080), realism (T-073).
- **Acceptance criteria:**
  - `results.md` contains every 1.11 row with number, threshold, pass/fail, script and data; rows not yet measurable say "pending T-0xx", never blank.
  - Groundedness ≥ 0.95 on available golden cues; `evals-gate` fails CI if a measured number misses its threshold. Judge spend ≤ $0.50.
- **Verification:** `python -m evals.run_evals --seeds 1..50 --out packages/evals/results.md && python -m evals.gate packages/evals/results.json`
- **Brief:**
  ```text
  Read TECH_PLAN 1.11 (whole table and command), 1.10 CI evals-gate, 1.14 disagreement 1 (groundedness measured by our own evaluator; Foundry only if it works), 1.7 agent table row Judge (CI only, Sonnet, {plausible, reason}), config/budgets.yaml latency_slo.
  groundedness.py: share of numbers on screen that are bound to verified claims, over all cached cues (500 once T-085 adds the demo season).
  latency.py reads blackboard traces; replay traces measure simulated latency, so label them "replay"; live numbers come from T-032 and T-080.
  judge.py: 30 random explained cues -> judge@1.md -> plausibility rate, reported only (no threshold).
  Fill in the evals-gate job in .github/workflows/ci.yml.
  Acceptance: the verification command exits 0.
  ```

### T-057 Hand-review export/import, few-shots and regeneration
- **Owner:** B · **Day:** 6 · **Estimated hours:** 3
- **Depends on:** T-042, T-049, T-050, T-054
- **Files:** `scripts/precompute.py` (`--hand-review 20`), `scripts/import_review.py`, `review/*.md`, `packages/newsroom/prompts/fewshot/{narrator.jsonl,tactician.jsonl}`, `packages/newsroom/prompts/{tactician@4.md,narrator@3.md}`, `scripts/check_cue_evidence.py`, `data/matches/4242/cache/**`
- **Scope:** In: export the 20 highest-leverage moments, edit them in this Claude Code session, import as `hand_reviewed: true`, append few-shots, bump prompt versions, regenerate the rest via Batch with `similar_moments` available, assemble the full cached cue stream. Out: new features.
- **Acceptance criteria:**
  - 20 entries flagged `hand_reviewed: true` and all passing the Fact Checker; prompt versions bumped in files and cache keys.
  - `check_cue_evidence.py` resolves every evidence ID, explanation ID and counterfactual ID of every cached cue; regeneration spend ≤ $1.50.
- **Verification:** `python scripts/import_review.py review/ && python scripts/check_cue_evidence.py --seed 4242 && python scripts/validate_schemas.py && python scripts/check_spend.py`
- **Brief:**
  ```text
  Read TECH_PLAN 1.7 "Prompt versioning and few-shots" (the exact mechanism), 1.8 precompute step 6, DEMO_MASTERPLAN_50USD.md §4 (Claude Code reviews the top twenty moments; edits become few-shots), 1.13 row "Cache miss during recording".
  Export: scripts/precompute.py --seed 4242 --mode batch --hand-review 20 writes review/<moment_id>.md (claims, evidence, explanation, line).
  Edit each in this session: sharper why, same verified numbers, no new unverified numbers. Then scripts/import_review.py writes them back as cache entries with hand_reviewed true and appends to fewshot/*.jsonl.
  Bump tactician@3 -> @4 and narrator@2 -> @3; regenerate all other moments through the Batch path (T-042 stages), Fact Checker on every output.
  Build the full cue stream into the cache (kind "cue") so replay needs no model; check_cue_evidence.py fails on any unresolved id.
  Acceptance: the verification command exits 0.
  ```

### T-058 Cosmos blackboard and Cosmos checkpoint storage
- **Owner:** B · **Day:** 6 · **Estimated hours:** 2.5
- **Depends on:** T-017, T-051, T-052
- **Files:** `packages/blackboard/cosmos.py`, `packages/newsroom/storage.py`, `infra/modules/cosmos.bicep`, `infra/main.bicep`, `tests/blackboard/test_cosmos.py`
- **Scope:** In: `CosmosBlackboard` (partition key `/match_id`), `CosmosCheckpointStorage` in Azure when `WHYLINE_CLOUD=1`, Cosmos free tier, managed identity. Out: changing local defaults (file checkpoints stay the local and demo default).
- **Acceptance criteria:**
  - Same tests as T-017 pass against Cosmos when `AZURE_COSMOS_ENDPOINT` is set (skipped otherwise); the Azure kill-resume run completes with a Cosmos checkpoint ID in the log.
  - Cosmos account uses the free tier (1,000 RU/s, 25 GB) and not serverless.
- **Verification:** `pytest tests/blackboard/test_cosmos.py -q && az bicep build --file infra/main.bicep --stdout > /dev/null`
- **Brief:**
  ```text
  Read TECH_PLAN 1.4 blackboard (CosmosBlackboard, azure-cosmos pinned at T-001, partition key /match_id), 1.7 checkpoints (CosmosCheckpointStorage(endpoint=..., credential=DefaultAzureCredential(), database_name=..., container_name=...)), 1.10 Azure table, FEASIBILITY_AUDIT Part A row 38 (agent-framework-azure-cosmos 1.0.0b261015 is beta; partition key /workflow_name).
  storage.py picks FileCheckpointStorage(WHYLINE_CHECKPOINT_DIR) unless WHYLINE_CLOUD=1, then CosmosCheckpointStorage with AZURE_COSMOS_ENDPOINT, AZURE_COSMOS_DATABASE_NAME, AZURE_COSMOS_CONTAINER_NAME.
  CosmosBlackboard.watch polls the container ordered by _ts and id.
  Human step: run `azd provision` yourself to add the Cosmos module.
  Acceptance: the verification command exits 0.
  ```

### T-059 OpenTelemetry spans and Application Insights
- **Owner:** B · **Day:** 6 · **Estimated hours:** 1.5
- **Depends on:** T-018, T-052
- **Files:** `packages/newsroom/telemetry.py`, `packages/api/telemetry.py`, `tests/newsroom/test_telemetry.py`
- **Scope:** In: the four span families with their attributes, console exporter locally, Azure Monitor exporter when `APPLICATIONINSIGHTS_CONNECTION_STRING` is set. Out: dashboards beyond one saved query.
- **Acceptance criteria:**
  - Spans `whyline.moment`, `whyline.agent.<name>`, `whyline.rollout`, `whyline.cue` carry exactly the 1.10 attributes (test with an in-memory exporter).
  - One App Insights query for explained-cue p95 latency is saved in `infra/README.md`.
- **Verification:** `pytest tests/newsroom/test_telemetry.py -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.10 "Observability" (opentelemetry-api 1.45.1; exporter pinned at T-001; span names and attributes), FEASIBILITY_AUDIT Part A rows 42-43 (workflow tracing is preview; the product is the Agent Monitoring Dashboard, not "Foundry Insights").
  Spans: whyline.moment{moment_id, leverage, branch}; whyline.agent.<name>{model, prompt_version, tokens_in, tokens_out, cost_usd, cache_hit, latency_ms}; whyline.rollout{engine, n, horizon_s, ms}; whyline.cue{cue_id, mode, verified}.
  Never put prompt text or keys in span attributes.
  Pins: opentelemetry-api 1.45.1, opentelemetry-sdk and azure-monitor-opentelemetry-exporter pinned at T-001; the exporter is chosen by APPLICATIONINSIGHTS_CONNECTION_STRING.
  Acceptance: pytest tests/newsroom/test_telemetry.py -q
  ```

### T-060 Freeze rule and frozen-cache-guard CI job
- **Owner:** B · **Day:** 6 · **Estimated hours:** 1
- **Depends on:** T-005, T-038
- **Files:** `scripts/frozen_cache_guard.py`, `docs/video/VERSION`, `.github/workflows/ci.yml`, `tests/tooling/test_frozen_guard.py`
- **Scope:** In: the guard script and job; `docs/video/VERSION` starts at `0`. Out: setting `frozen = true` (T-071).
- **Acceptance criteria:**
  - With `frozen = true` in the base commit, a changed manifest hash fails the job unless `docs/video/VERSION` changed in the same commit (TECH_PLAN 1.8).
  - Unit test covers: unchanged, changed without bump (fail), changed with bump (pass).
- **Verification:** `pytest tests/tooling/test_frozen_guard.py -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.8 "Freeze rule" and 1.10 CI (frozen-cache-guard), ADR-003 consequences, schemas/cache_manifest.schema.json (frozen flag).
  scripts/frozen_cache_guard.py --base <ref>: compare data/matches/4242/cache/manifest.json entry sha256 values between base and HEAD; if base had frozen true and any differ, require a change to docs/video/VERSION in the same diff.
  CI uses the PR base or HEAD^ on main.
  The job must also pass while the manifest is not yet frozen (before T-071).
  Acceptance: pytest tests/tooling/test_frozen_guard.py -q
  ```

### T-061 Demo script runner, shot list and Playwright recorder
- **Owner:** C · **Day:** 6 · **Estimated hours:** 3
- **Depends on:** T-035, T-044, T-045, T-051, T-053
- **Files:** `packages/demo/{demo_script.yaml,shot_list.yaml,record_demo.py,__main__.py}`, `packages/api/demo_runner.py`, `scripts/record_demo.sh`, `tests/demo/test_demo_script.py`
- **Scope:** In: the four demo-script actions on the replay clock, a shot list covering the §7 storyboard, the recorder (1920×1080, DPR 1, `record_video_dir`, PNG keyframes). Out: editing (T-063).
- **Acceptance criteria:**
  - `demo_script.yaml` contains exactly the 1.8 entries (kill at 44:10, veto at 45:00+15s, speed 1 at 31:10, speed 10 at 33:00) with clocks taken from `golden_moments.yaml`.
  - The recorder writes `packages/demo/out/<shot>.webm` and `<shot>_<clock>.png` for every shot and waits for `window.__whyline.ready` before each.
- **Verification:** `pytest tests/demo/test_demo_script.py -q && python -m demo.record_demo --shots packages/demo/shot_list.yaml --dry-run`
- **Brief:**
  ```text
  Read TECH_PLAN 1.8 "Demo script", 1.9 "Recording" (responsibilities), DEMO_MASTERPLAN_50USD.md §6 step 6-7 and §7 storyboard, packages/demo/golden_moments.yaml.
  packages/api/demo_runner.py applies demo_script.yaml actions on the replay clock (kill -> T-051 path; veto -> producer decision vetoed on the recap request; speed).
  shot_list.yaml rows: {shot, app, route, viewer, clock_in, clock_out, speed, keyframes[]} for every storyboard beat (3D opener, Sliding Doors, Fourth Official, Panel + kill, Oracle + Dugout, split-screen modes + veto, architecture, half-time).
  record_demo.py: Playwright (Python, pinned at T-001), Chromium 1920x1080 DPR 1, record_video_dir, ?record=1&viewer=<profile>, seek, record, keyframes.
  Acceptance: the verification command exits 0.
  ```

### T-062 Rehearsal and v1 recording with zero cache misses
- **Owner:** C · **Day:** 6 · **Estimated hours:** 2.5
- **Depends on:** T-057, T-061
- **Files:** `packages/demo/out/` (git-ignored), `docs/evidence/rehearsal_day6.md`
- **Scope:** In: one full rehearsal of the golden match with the demo script, then recording every shot. Out: re-recording after the freeze (only with a VERSION bump).
- **Acceptance criteria:**
  - Rehearsal trace has zero red rows (no `cache_miss`, no unexpected `interrupted` besides the scripted kill) (TECH_PLAN 1.13 row "Cache miss during recording").
  - `scripts/check_cue_evidence.py` and `scripts/scan_banned.py` pass on the cache and all UI strings; every shot file exists.
- **Verification:** `python scripts/check_cue_evidence.py --seed 4242 && python scripts/scan_banned.py data/matches/4242/cache apps/*/src && ls packages/demo/out/*.webm`
- **Brief:**
  ```text
  Read TECH_PLAN 1.8 "Replay serving" (a miss is visible as a red trace row), 1.13 row "Cache miss during recording" (fix precompute; never record with a miss), DEMO_MASTERPLAN_50USD.md §6 and §9.
  Start the api, mcp_server and newsroom supervisor in replay mode (WHYLINE_MODE=replay), open overlay, studio and fan, and play 4242 with the demo script at the shot-list speeds.
  Write docs/evidence/rehearsal_day6.md: trace counts by status, any miss and the ticket that fixed it.
  If a miss appears, hand the moment id to B (T-057 owner) and re-run; do not record until the trace is clean. Then run record_demo.py for all shots.
  Acceptance: the verification command exits 0 and the rehearsal note shows zero misses.
  ```

### T-063 Video v1 edit
- **Owner:** C · **Day:** 6 · **Estimated hours:** 2.5
- **Depends on:** T-062
- **Files:** `packages/demo/edit_v1.yaml`, `packages/demo/assemble.py`, `packages/demo/captions_v1.srt`, `packages/demo/out/final_v1.mp4` (git-ignored)
- **Scope:** In: an edit decision list from the §7 storyboard, ffmpeg concat and caption burn-in, wordmark end card. Out: music (T-082), voice-over (out of scope unless a person records one), any third-party media.
- **Acceptance criteria:**
  - Duration < 120 s (rules 4.4, TECH_PLAN 1.12) by `ffprobe`.
  - Every number in the captions appears in `packages/evals/results.md`, the ledger or a verified cue; claims that are not measured are removed (e.g. "measured in Foundry" only if T-086 succeeded, 1.14 #1; "trained on thousands of matches" only if `gate.json` says policy_v1).
- **Verification:** `python packages/demo/assemble.py packages/demo/edit_v1.yaml && ffprobe -v error -show_entries format=duration -of csv=p=0 packages/demo/out/final_v1.mp4`
- **Brief:**
  ```text
  Read DEMO_MASTERPLAN_50USD.md §7 (storyboard and captions), TECH_PLAN 1.12 (video under two minutes, no third-party marks or music), 1.14 disagreement 1, packages/evals/results.md, packages/policy/artifacts/gate.json.
  edit_v1.yaml: ordered clips {file, in, out, caption}. assemble.py uses ffmpeg to trim, concat, burn captions from captions_v1.srt, add the end card "WHYLINE. Every line on screen has a why." (ffmpeg is used for cutting only; nothing here involves HLS metadata).
  Rewrite any caption whose number or claim is not backed by a measured artefact; keep a table of caption -> source in edit_v1.yaml.
  No music in v1 (the Lyria track arrives on day 9). Captions only, English only; a voice-over only if a team member records it.
  Acceptance: the verification command prints a duration below 120.
  ```

**End of day 6: done means** the evaluation table exists with real numbers, the golden cache is hand-reviewed and regenerated with zero misses, Cosmos and telemetry work in Azure, the freeze guard is live, and a complete rough cut under two minutes exists.

---

## Day 7 — Tue 27 Oct (M1)

### T-064 Clean-machine replay test and one-command demo
- **Owner:** A · **Day:** 7 · **Estimated hours:** 3.5
- **Depends on:** T-022, T-051, T-057
- **Files:** `scripts/replay_headless.py`, `scripts/clean_machine_replay.sh`, `docker-compose.yml`, `Makefile` (demo target), `docs/evidence/clean_replay_v0.1.md`
- **Scope:** In: a headless replay harness that records the cue stream, a socket guard that blocks non-localhost connections, three consecutive runs from a fresh clone and fresh venv with no `.env`, `make demo`, `docker-compose.yml` per 1.10. Out: the v1.0 repeat (T-099).
- **Acceptance criteria:**
  - Three consecutive runs produce identical cue-stream SHA-256 with networking blocked and no API keys set (§9 item 1).
  - `make demo` starts the six services and the replay in one command; `docs/JUDGES.md` (T-068) can cite it.
- **Verification:** `bash scripts/clean_machine_replay.sh --runs 3`
- **Brief:**
  ```text
  Read DEMO_MASTERPLAN_50USD.md §9 item 1, TECH_PLAN 1.8 (replay serving; golden-determinism replays the cue stream), 1.10 "Local" (docker-compose services and ports; make demo = docker compose up + python -m api.replay --seed 4242), 1.12 row "Judges can test".
  replay_headless.py --seed 4242 --speed 10 --out cues.jsonl: start api, mcp_server and the newsroom supervisor in replay mode as subprocesses, drive the clock to full time, dump cues sorted by cue_id with volatile fields (timestamps, pids) removed, print sha256.
  Network guard: a sitecustomize hook in the harness environment that refuses socket connections to anything but 127.0.0.1/::1.
  clean_machine_replay.sh: git clone into a temp dir, python3.12 -m venv, pip install -r requirements.lock, unset ANTHROPIC_API_KEY GOOGLE_API_KEY, run the harness N times, compare hashes.
  Acceptance: bash scripts/clean_machine_replay.sh --runs 3
  ```

### T-065 Day-7 bug bash (engine, ML, evals)
- **Owner:** A · **Day:** 7 · **Estimated hours:** 3
- **Depends on:** T-056, T-064
- **Files:** `docs/evidence/bugbash_v0.1.md` plus fixes in the packages concerned
- **Scope:** In: P0/P1 bugs found by running every verification command from T-006 to T-064, `make ci`, and the M1 checklist. Out: new features; any change that alters cache hashes without B's agreement before the freeze.
- **Acceptance criteria:**
  - Every Verification command for tickets T-001–T-064 exits 0 (list with results in the bug-bash note).
  - No open P0; open P1s listed with owner and day.
- **Verification:** `make ci && bash scripts/clean_machine_replay.sh --runs 1`
- **Brief:**
  ```text
  Read this file's M1 section and TECH_PLAN 1.10 (CI jobs), 1.11 (thresholds).
  Run every Verification command for T-001..T-064 in order; record pass/fail in docs/evidence/bugbash_v0.1.md.
  Fix P0 bugs in A-owned packages; file others to their owner with the failing command. Anything that would change data/matches/4242/cache must land before T-071 freezes it.
  Do not upgrade any dependency during the bug bash; config/pins.txt is fixed for v0.1.
  Acceptance: make ci && bash scripts/clean_machine_replay.sh --runs 1
  ```

### T-066 Licence scan job and asset list
- **Owner:** B · **Day:** 7 · **Estimated hours:** 1
- **Depends on:** T-005
- **Files:** `scripts/licence_scan.py`, `config/licence_allowlist.txt`, `LICENSES.md`, `.github/workflows/ci.yml`
- **Scope:** In: pip-licenses over the venv, npm licence fields for the three apps, an asset list (data, images, music, fonts) with licences. Out: legal review.
- **Acceptance criteria:**
  - Allow-list: MIT, Apache-2.0, BSD-2/3, ISC, PSF, CC BY 4.0, CC0, and named paid-commercial outputs; anything GPL, AGPL, LGPL or non-commercial fails the job (§9 item 6; BSD and PSF are read as part of the permissive set).
  - `LICENSES.md` lists every dataset and asset, including the GRF status from `docs/DATA.md`.
- **Verification:** `python scripts/licence_scan.py`
- **Brief:**
  ```text
  Read TECH_PLAN 1.10 CI (licence-scan: pip-licenses against the allow-list in config/pins.txt), 1.12 row "Third-party integrations licensed", config/pins.txt (licences and "Excluded on purpose"), FEASIBILITY_AUDIT C.4, DEMO_MASTERPLAN §9 item 6.
  scripts/licence_scan.py: run pip-licenses --format=json; read license fields from apps/*/node_modules/**/package.json (production deps only); check against config/licence_allowlist.txt; print offenders; exit 1 on any.
  LICENSES.md: packages summary, data (Kickoff, GRF with attribution and status, SkillCorner MIT and DFL CC BY 4.0 for validation only), assets.
  Fill in the licence-scan job in ci.yml.
  Acceptance: python scripts/licence_scan.py
  ```

### T-067 README with evidence and pitch
- **Owner:** B · **Day:** 7 · **Estimated hours:** 2
- **Depends on:** T-051, T-056, T-064, T-066
- **Files:** `README.md`, `scripts/check_readme_links.py`
- **Scope:** In: pitch naming the Microsoft technologies, what runs where, one-command replay, evidence table linking every 1.11 number and §9 item to its script and artefact, the kill-resume log, spend total, honest limits (English only, no voice, synthetic data). Out: marketing claims without an artefact.
- **Acceptance criteria:**
  - Links resolve to committed files: calibration plot, state confusion matrix, planted-error results, `kill_resume.log`, ledger, `results.md` (§9 items 3 and 5).
  - The README says the multi-language challenge bullet is not addressed (ADR-010) and that real datasets are validation only.
- **Verification:** `python scripts/check_readme_links.py README.md`
- **Brief:**
  ```text
  Read TECH_PLAN 1.11, 1.12 (README "Pitch" section naming Microsoft technologies; synthetic-data statement), ADR-010, DEMO_MASTERPLAN_50USD.md §1, §6, §9, packages/evals/results.md, docs/evidence/*.
  Sections: Pitch; What you will see; Run it in one command (make demo; replay, no keys); Architecture (link docs/architecture.md); Evidence table (number, threshold, artefact link, script); Spend (ledger total from scripts/check_spend.py); Limits; Data and licences; Credits.
  Add scripts/check_readme_links.py (relative links must exist). Every number must come from an artefact; write "pending" rather than a guess.
  Link the video from docs/video/v1.md once T-069 writes it; until then write "video: pending T-069".
  Acceptance: python scripts/check_readme_links.py README.md
  ```

### T-068 JUDGES, DATA and architecture docs
- **Owner:** B · **Day:** 7 · **Estimated hours:** 2
- **Depends on:** T-012, T-051, T-052
- **Files:** `docs/JUDGES.md`, `docs/DATA.md`, `docs/architecture.md`
- **Scope:** In: judge instructions (hosted URL, local replay, optional live mode with their own key and the spend cap), data provenance and attribution, architecture with the workflow graph, MCP boundary, checkpoint resume log, A2A note. Out: video.
- **Acceptance criteria:**
  - `docs/JUDGES.md` gets a judge from clone to playing replay in ≤ 5 commands with no key; live mode is optional and capped at $2.50 per match.
  - `docs/architecture.md` shows the 1.7 graph, the 1.1 data flows and the Azure services actually deployed (1.12 Multi-Agent row).
- **Verification:** `python scripts/check_readme_links.py docs/JUDGES.md docs/DATA.md docs/architecture.md`
- **Brief:**
  ```text
  Read TECH_PLAN 1.1, 1.7, 1.10, 1.12 (rows "Judges can test" and "Category adherence: Multi-Agent"), 1.6 datasets table, docs/DATA.md draft (T-012), infra/README.md.
  JUDGES.md: hosted URLs (from azd env), local replay commands, troubleshooting, how to watch the kill switch and veto, live mode steps using their own ANTHROPIC_API_KEY in .env (never ours).
  DATA.md: Kickoff (synthetic), GRF (training; attribution; licence status), SkillCorner and DFL (validation only, attribution strings).
  architecture.md: diagrams as Mermaid text; note Event Hubs is optional and not deployed unless it is.
  Acceptance: python scripts/check_readme_links.py docs/JUDGES.md docs/DATA.md docs/architecture.md
  ```

### T-069 Video v1 final pass and upload
- **Owner:** C · **Day:** 7 · **Estimated hours:** 2
- **Depends on:** T-063
- **Files:** `packages/demo/edit_v1.yaml`, `docs/video/VERSION` (= 1), `docs/video/v1.md`
- **Scope:** In: re-record only shots affected by day-7 fixes, final assemble, frame review for marks, upload, link. Out: music and polish (days 8–12).
- **Acceptance criteria:**
  - `final_v1.mp4` < 120 s; a person has watched it frame by frame for real marks and names (§9 item 8) and signed `docs/video/v1.md`.
  - `docs/video/VERSION` = 1 and `docs/video/v1.md` holds the public link, the cache manifest SHA-256 it was recorded from, and the caption → source table.
- **Verification:** `cat docs/video/VERSION && grep -E "manifest_sha256: [0-9a-f]{64}" docs/video/v1.md`
- **Brief:**
  ```text
  Read TECH_PLAN 1.8 (freeze rule), 1.12 (video row), DEMO_MASTERPLAN_50USD.md §7 and §9 item 8.
  Re-record any shot whose cache entries changed since T-062 (compare manifest hashes); re-assemble.
  Human step: a person uploads the video (YouTube unlisted or as a GitHub release asset) and pastes the link into docs/video/v1.md; the session does not upload.
  Run python scripts/scan_banned.py on the caption file before the final assemble.
  Acceptance: the verification command prints 1 and finds the manifest hash.
  ```

### T-070 Front-end bug bash and clean-load check
- **Owner:** C · **Day:** 7 · **Estimated hours:** 2
- **Depends on:** T-061
- **Files:** `docs/evidence/frontend_bugbash_v0.1.md` plus fixes in `apps/*`
- **Scope:** In: build all three apps from clean, load each hosted and local, fix P0s, check phone width for the fan app. Out: new screens.
- **Acceptance criteria:**
  - All `tests/apps/` pass; no console errors on load of overlay, studio, fan and `/replay3d` (Playwright collects console messages).
  - Hosted Static Web Apps load and connect to the hosted api.
- **Verification:** `for a in overlay studio fan; do npm --prefix apps/$a run build || exit 1; done && pytest tests/apps -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.9, this file's M1 section, docs/cue_contract.md.
  Run every tests/apps test, then a console-error sweep with Playwright (page.on("console")) on each route locally and on the hosted URLs from azd env.
  Fix P0s only; list P1s with owner and day in the note.
  No dependency upgrades; fixes stay inside apps/*.
  Acceptance: the verification command exits 0.
  ```

### T-071 Freeze golden cache, golden cue hash, tag v0.1 and submit
- **Owner:** B · **Day:** 7 · **Estimated hours:** 1.5
- **Depends on:** T-060, T-064, T-065, T-067, T-068, T-069, T-070
- **Files:** `data/matches/4242/cache/manifest.json` (`frozen: true`), `tests/golden/cues.sha256`, `.github/workflows/ci.yml` (golden-determinism cue half), `docs/SUBMISSION.md`
- **Scope:** In: freeze, cue-stream hash in CI, all nine CI jobs green, tag, submission text. Out: anything that changes the cache (needs a VERSION bump after this point).
- **Acceptance criteria:**
  - `manifest.frozen = true`; `tests/golden/cues.sha256` equals the T-064 hash; CI green on all nine jobs at the tagged commit.
  - Tag `v0.1` pushed; `docs/SUBMISSION.md` has repo URL, video link, hosted URL, category (Multi-Agent) and the Microsoft technologies used.
- **Verification:** `git tag --list v0.1 && python -c "import json;assert json.load(open('data/matches/4242/cache/manifest.json'))['frozen']" && make ci`
- **Brief:**
  ```text
  Read TECH_PLAN 1.8 (freeze rule), 1.10 (nine CI jobs), 1.12 (rules checklist), 1.13 row "Deadline is 27 Oct" (the day-7 tag is the submission), DEMO_MASTERPLAN §8 day 7.
  Set frozen true in the manifest, write tests/golden/cues.sha256 from scripts/replay_headless.py, extend the golden-determinism job to compare it.
  Confirm the M1 checklist below item by item; any unmet item goes into docs/SUBMISSION.md "Known limits" rather than being hidden.
  git tag -a v0.1 -m "WHYLINE v0.1 (M1)"; confirm with the owner, then push the tag.
  Human step: a person submits on the hackathon site using docs/SUBMISSION.md and accepts any terms there.
  Acceptance: the verification command exits 0.
  ```

**End of day 7: done means** tag `v0.1` is pushed with all nine CI jobs green, the golden cache is frozen, the video v1 is uploaded, judges can replay from a clean clone with no keys, and the submission has been made.

---
## Day 8 — Wed 28 Oct

### T-072 Policy v2 with rollout-aware loss; overnight launch
- **Owner:** A · **Day:** 8 · **Estimated hours:** 4
- **Depends on:** T-036, T-037
- **Files:** `packages/policy/{train_v2.py,rollout_loss.py}`, `packages/policy/artifacts/{policy_v2_epN.pt,train_v2_log.jsonl}`, `packages/rollout/policy_engine.py` (engine `policy_v2`), `tests/policy/test_rollout_loss.py`
- **Scope:** In: multi-step look-ahead loss (schedule 1 → 10 steps) on top of behaviour cloning, warm start from `policy_v1.pt`, `engine="policy_v2"` in `rollout`. Out: horizons > 8 s; per-tick policy calls (ADR-002).
- **Acceptance criteria:**
  - The loss unrolls the decision-only engine for k steps with gradients through the policy outputs only; unit test on a toy batch shows the k-step error falls over 50 steps.
  - Overnight run launched; `policy_v2` loads only if its own `metrics.json` passes the 1.6 gates (same guard as T-036).
- **Verification:** `pytest tests/policy/test_rollout_loss.py -q && tail -n 3 packages/policy/artifacts/train_v2_log.jsonl`
- **Brief:**
  ```text
  Read TECH_PLAN ADR-002, 1.5 (decision points, determinism), 1.6 (model, training, gates), FEASIBILITY_AUDIT B.1 ("Train with rollout-aware loss (Le et al. 2017 style: schedule look-ahead from 1 to 10 steps)"), DEMO_MASTERPLAN §8 days 8-10.
  Extend the rollout engine Literal with "policy_v2" (schemas/counterfactual.schema.json already allows it).
  Keep decision-only calls and the 8 s cap. Same data split (split_seed 4242). Weights stay git-ignored (T-089).
  Human step: keep the Mac awake overnight.
  Acceptance: pytest tests/policy/test_rollout_loss.py -q
  ```

### T-073 Realism validation against GRF, SkillCorner and DFL
- **Owner:** A · **Day:** 8 · **Estimated hours:** 4
- **Depends on:** T-014, T-027
- **Files:** `packages/evals/realism.py`, `packages/evals/realism.md`, `packages/evals/out/realism_*.png`, `data/grf/validation/` (git-ignored)
- **Scope:** In: marginal distributions (player speeds, pass lengths, completion by distance, possession sequence lengths, shot locations, formation spread) for Kickoff vs GRF vs SkillCorner (MIT) and one DFL match (CC BY 4.0). Out: training on real data (never; rules 4.7).
- **Acceptance criteria:**
  - Plots and a table of distances (e.g. Wasserstein) per marginal are published; no threshold (TECH_PLAN 1.11 row "Realism").
  - `docs/DATA.md` carries the SkillCorner and DFL attribution strings and states "validation only".
- **Verification:** `python -m evals.realism --kickoff data/matches/corpus --grf data/grf/raw --real data/grf/validation --out packages/evals/realism.md`
- **Brief:**
  ```text
  Read TECH_PLAN 1.6 datasets table (SkillCorner and DFL are validation only), 1.11 row "Realism", 1.12 row "Synthetic data", FEASIBILITY_AUDIT B.6 point 1 and Part A rows 15-16.
  Human step: approve the downloads (SkillCorner open data, 2-3 matches via Git LFS, about 90 MB each; DFL one match from the figshare deposit, multi-GB, optional). Store under data/grf/validation (git-ignored).
  Never feed real data into any training script; realism.py only reads it.
  Use scipy 1.18.1 for Wasserstein distances and matplotlib for plots; put all sources in metres (GRF mapping from data/grf/coords_report.json).
  Acceptance: the verification command writes realism.md with every plot linked.
  ```

### T-074 Live mode end to end
- **Owner:** B · **Day:** 8 · **Estimated hours:** 4
- **Depends on:** T-032, T-033, T-041, T-050
- **Files:** `packages/newsroom/live.py`, `packages/rollout/live_client.py`, `packages/api/analytics_live.py`, `tests/integration/test_live_match.py`
- **Scope:** In: `WHYLINE_MODE=live` with `LiveClient` and `LiveRollout` (scripted_v1, CPU, n = 100, 8 s), on-the-fly analytics, live Oracle (5 s, n = 50), mode badge, a full live local match. Out: Azure scale tests (T-080).
- **Acceptance criteria:**
  - `python -m kickoff play --seed 9001 --target api` drives a full match to cues on all three screens with the same graph and prompts as replay (TECH_PLAN 1.8).
  - Live rollout B=100, 8 s ≤ 0.5 s on CPU (1.5 target); the live match costs ≤ $2.50 in the ledger.
- **Verification:** `WHYLINE_LIVE_TESTS=1 pytest tests/integration/test_live_match.py -q -m live && python scripts/check_spend.py`
- **Brief:**
  ```text
  Read TECH_PLAN 1.1 "Data flow, live mode", 1.5 "Budgets" (live in Azure: scripted_v1, B=100, 8 s, ≤ 0.5 s), 1.8 "Live mode", 1.14 disagreements 2-4 (Oracle 5 s / n=50; Decision Index approximated by the head swing; Panel near-line only), config/models.yaml live roles, config/budgets.yaml caps.
  Live seeds 9001+ (outside every partition). Physics on CPU and heads via LightGBM on each frame batch; Scout runs as in replay.
  Every call through SpendGuard; per-match cap switches the system to degraded (templates, amber badge, ledger line).
  Pins: agent-framework-anthropic and agent-framework-gemini 1.0.0b261015 through LiveClient. Spend ≤ $2.50 for the match.
  Acceptance: the verification command exits 0.
  ```

### T-075 Web PubSub judge stream and Key Vault hardening
- **Owner:** B · **Day:** 8 · **Estimated hours:** 3
- **Depends on:** T-052, T-074
- **Files:** `infra/modules/webpubsub.bicep`, `infra/main.bicep`, `packages/api/pubsub.py`, `apps/*/src/stream/StreamProvider.tsx` (Web PubSub client path), `tests/api/test_pubsub.py`
- **Scope:** In: Web PubSub free tier for the judge stream, managed identity, api publishing cues and frames by group, Key Vault references for every secret the apps use. Out: Standard tier (only if > 20 clients are needed; 1.13 uses SSE instead, T-095).
- **Acceptance criteria:**
  - Hosted overlay, studio and fan receive the stream through Web PubSub; local mode still uses the api WebSocket.
  - Message volume for one replayed match fits the free 20,000 messages/day (frames batched; report the count).
- **Verification:** `pytest tests/api/test_pubsub.py -q && az bicep build --file infra/main.bicep --stdout > /dev/null`
- **Brief:**
  ```text
  Read TECH_PLAN 1.10 Azure table (Web PubSub free: 20 connections, 20k messages/day) and "Secrets" (managed identity for Web PubSub), 1.13 row "Web PubSub 20-connection cap", FEASIBILITY_AUDIT Part A row 53.
  azure-messaging-webpubsubservice pinned at T-001. 10 Hz frames would exceed 20k messages/day, so publish frames in 1 s batches (10 frames per message) and interpolate client-side; count messages per match.
  Locally, AZURE_WEBPUBSUB_CONNECTION_STRING may be used from .env; in Azure use DefaultAzureCredential.
  Human step: run `azd provision` and `azd deploy` yourself.
  Acceptance: the verification command exits 0.
  ```

### T-076 Half-time studio cards
- **Owner:** C · **Day:** 8 · **Estimated hours:** 4
- **Depends on:** T-034, T-050
- **Files:** `apps/overlay/src/components/RecapCards.tsx`, `apps/studio/src/components/HalfTime.tsx`, `tests/apps/test_recap_cards.py`
- **Scope:** In: `recap_card` layer: three sliding-doors moments of the half with their swing numbers, the chaos timeline from `timeline`, player of the half. Out: new recap content (T-050 owns it).
- **Acceptance criteria:**
  - Cards render only verified claims and show n, horizon and seed on each counterfactual number.
  - A vetoed recap card never renders (test drives a veto through the studio).
- **Verification:** `npm --prefix apps/overlay run build && pytest tests/apps/test_recap_cards.py -q`
- **Brief:**
  ```text
  Read DEMO_MASTERPLAN_50USD.md §7 1:42-1:55, TECH_PLAN 1.7 Recap row and MCP timeline (chaos, control, xT series at 30 s), schemas/cue.schema.json (layer recap_card, kind recap), 1.9 studio.
  Layout: three cards slide in left to right, each with a mini ghost trail and the swing bar; chaos timeline as a sparkline across the half; player of the half with Decision Index.
  Pins: React, Vite and TypeScript from each app's package.json (T-001); add no dependencies.
  Card text comes only from the cached recap (T-050); the component never formats new numbers.
  Acceptance: npm --prefix apps/overlay run build && pytest tests/apps/test_recap_cards.py -q
  ```

### T-077 Crests, kits and stadium textures with Nano Banana 2.1
- **Owner:** C · **Day:** 8 · **Estimated hours:** 3
- **Depends on:** T-002, T-008
- **Files:** `scripts/generate_images.py`, `apps/overlay/public/assets/{crests,kits,textures}/`, `data/league/assets.json`, `config/budgets.yaml` (image price line)
- **Scope:** In: 8 crests, 16 kits, stadium textures (≈ 40 images) from the crest briefs in `clubs.json`, priced through SpendGuard. Out: any image resembling a real club mark (rejected on review).
- **Acceptance criteria:**
  - ≈ 40 images, spend ≤ $1.40 ($50 plan §3, $0.034 per image), each listed in `assets.json` with prompt, model and licence note.
  - A person reviews every image for resemblance to real marks; `scripts/scan_banned.py` passes on prompts and file names.
- **Verification:** `python scripts/check_spend.py && python scripts/scan_banned.py data/league/assets.json`
- **Brief:**
  ```text
  Read DEMO_MASTERPLAN_50USD.md §1 (Pictures), §3 (Nano Banana 2.1, about 40 images at $0.034), config/pins.txt data section (Google does not claim ownership of outputs), data/league/clubs.json crest briefs, TECH_PLAN 1.12 (no trademarks).
  Use google-genai (pinned at T-001) with GOOGLE_API_KEY. Confirm the exact Nano Banana 2.1 model id in Google's model list at run time; do not guess it.
  Add images_usd_per_image: 0.034 to config/budgets.yaml and record each image in the ledger (tokens 0, cost per image).
  Human step: review every image before it is committed.
  Acceptance: the verification command exits 0.
  ```

**End of day 8: done means** policy v2 is training, realism plots exist, a full live match runs end to end under its cap, the hosted stream uses Web PubSub, and half-time cards and crests exist.

---

## Day 9 — Thu 29 Oct

### T-078 Policy v2 evaluation and gate against v1
- **Owner:** A · **Day:** 9 · **Estimated hours:** 2.5
- **Depends on:** T-072
- **Files:** `packages/policy/artifacts/{metrics_v2.json,gate_v2.json}`, `docs/evidence/policy_gate_v2.md`
- **Scope:** In: the same 1.6 metrics for v2, side-by-side with v1, 20 clip strips, decision. Out: swapping the cache (T-084 decides).
- **Acceptance criteria:**
  - `gate_v2.json` = pass only if every 1.6 gate passes and v2 beats v1 on 4 s FDE and shape-collapse rate without getting worse on the others.
  - The note states plainly which engine the video v2 will use.
- **Verification:** `python -m policy.evaluate --ckpt packages/policy/artifacts/policy_v2.pt --test data/grf/dataset/test.npz --n-rollouts 20 && cat packages/policy/artifacts/gate_v2.json`
- **Brief:**
  ```text
  Read TECH_PLAN 1.6 "Evaluation and gates", docs/evidence/policy_gate_day4.md, FEASIBILITY_AUDIT B.1 failure modes.
  Reuse policy/evaluate.py (T-037); write metrics_v2.json and gate_v2.json {engine: "policy_v2" | "keep", reasons}.
  Never edit thresholds.
  Render 20 v2 clip strips next to the v1 strips in docs/evidence/policy_clips/ for side-by-side review.
  Acceptance: the verification command exits 0.
  ```

### T-079 Counterfactual sensitivity and calibration refresh
- **Owner:** A · **Day:** 9 · **Estimated hours:** 2.5
- **Depends on:** T-040, T-078
- **Files:** `packages/evals/sensitivity.py`, `packages/evals/out/{sensitivity.json,sensitivity.png,calibration_v2.json,calibration_v2.png}`
- **Scope:** In: n = 50 vs 200 vs 1,000 on 100 held-out moments; calibration re-run with the engine `gate_v2.json` selects. Out: cross-world agreement (no second world; gfootball is out).
- **Acceptance criteria:**
  - The swing estimate's spread at n = 200 vs n = 1,000 is reported; if it has not stabilised by 200, the note says so and recommends a larger n (FEASIBILITY_AUDIT B.2).
  - Brier ≤ 0.18 and placebo pass ≥ 95% for the engine that will be cached.
- **Verification:** `python -m evals.sensitivity --seeds 51..350 --moments 100 && python -m evals.calibration --seeds 51..350 --engine-from packages/policy/artifacts/gate_v2.json --out packages/evals/out --tag v2`
- **Brief:**
  ```text
  Read FEASIBILITY_AUDIT B.2 (sensitivity: n=50 vs 200 vs 1,000 on 100 moments), TECH_PLAN 1.11 calibration row, packages/evals/calibration.py (T-040).
  If gate_v2 says "keep", run calibration for the day-4 engine again only if engine code changed since day 4.
  Write sensitivity.json {moments, n_values, swing_mean and swing_std per n} and a plot of swing against n.
  Run on CPU in the background; expect about an hour (estimate).
  Acceptance: the verification command exits 0.
  ```

### T-080 Recorded live judge run on Azure: three matches
- **Owner:** B · **Day:** 9 · **Estimated hours:** 3
- **Depends on:** T-056, T-059, T-074, T-075
- **Files:** `docs/evidence/live_judge_run.md`, `packages/evals/out/latency_live.json`, `packages/demo/out/live_judge_run.webm` (git-ignored)
- **Scope:** In: three live matches (seeds 9001–9003) on the hosted deployment, one recorded with the Playwright recorder, latency p50/p95 per tier from traces and App Insights, cost per match from the ledger. Out: tuning (T-081).
- **Acceptance criteria:**
  - Fast cue p95 ≤ 3 s and explained cue p95 ≤ 15 s (TECH_PLAN 1.11, `budgets.yaml` latency_slo; §9 item 4) or the miss is reported with numbers.
  - Each match ≤ $2.50; the day's total stays under the $10 per-day cap (so T-085 runs on another day).
- **Verification:** `python -m evals.latency --source live --matches 9001,9002,9003 --out packages/evals/out/latency_live.json && python scripts/check_spend.py`
- **Brief:**
  ```text
  Read TECH_PLAN 1.11 rows "Cue latency" and "Cost per match", 1.10 observability, 1.13 row "Explained-cue latency > 15 s live", DEMO_MASTERPLAN §9 item 4, config/budgets.yaml latency_slo and spend.
  Run kickoff --target api against the hosted api with WHYLINE_MODE=live. Record one match with packages/demo/record_demo.py (studio + overlay), keeping the trace panel visible.
  latency = event t_ms arrival at the api -> cue delivered on the stream, per tier (fast, explained); export the App Insights query result next to the trace-based number.
  Spend ≤ $7.50 for the three matches; run only on day 9 so T-085's Batch spend lands on another day.
  Acceptance: the verification command exits 0 and live_judge_run.md states pass or miss per SLO.
  ```

### T-081 Explained-latency tuning and degraded-mode drills
- **Owner:** B · **Day:** 9 · **Estimated hours:** 2
- **Depends on:** T-080
- **Files:** `config/models.yaml` (only if the 1.13 response is triggered), `packages/newsroom/faults.py`, `tests/integration/test_degraded.py`, `docs/evidence/degraded_drill.md`
- **Scope:** In: the pre-decided 1.13 responses if p95 > 15 s (Tactician `max_tool_rounds` 1; Panel near-line only), fault injection for an Anthropic outage and a refusal, the degraded badge. Out: new models or providers.
- **Acceptance criteria:**
  - With `WHYLINE_FAULT=anthropic_down` the system serves template lines, shows `mode: degraded` on all screens and writes the switch to the ledger; no cue is blank.
  - If tuning was applied, one live match is re-measured and the new p95 recorded (spend ≤ $2.50).
- **Verification:** `pytest tests/integration/test_degraded.py -q`
- **Brief:**
  ```text
  Read TECH_PLAN 1.13 rows "Explained-cue latency > 15 s live" and "Claude refusal or outage", 1.8 live mode (degraded), config/models.yaml header (server-side fallback beta) and fallback_role chains, docs/evidence/live_judge_run.md.
  faults.py: env-driven fault injection used only in tests and drills (anthropic_down, gemini_429, refusal).
  The 1.13 responses are config edits only (max_tool_rounds, Panel near-line); prompts do not change, so the frozen cache is untouched.
  Write docs/evidence/degraded_drill.md: fault, badge state on each screen, ledger line, first template cue id.
  Acceptance: pytest tests/integration/test_degraded.py -q
  ```

### T-082 Apply crests and kits; Lyria 3.5 music track
- **Owner:** C · **Day:** 9 · **Estimated hours:** 3
- **Depends on:** T-053, T-077
- **Files:** `apps/{overlay,fan,studio}/src/assets.ts`, `apps/overlay/src/replay3d/Stadium.tsx`, `scripts/generate_music.py`, `packages/demo/music/` (git-ignored), `LICENSES.md`
- **Scope:** In: crests in score bug and fan app, kit textures on 3D capsules, stadium textures, one Lyria 3.5 track (no vocals) for the video. Out: third-party music (rules 4.4).
- **Acceptance criteria:**
  - Screens use only `assets.json` images; `LICENSES.md` lists them with their source.
  - One instrumental track generated, spend ≤ $0.24 ($50 plan §3), SynthID watermark noted in `LICENSES.md`.
- **Verification:** `for a in overlay studio fan; do npm --prefix apps/$a run build || exit 1; done && python scripts/check_spend.py`
- **Brief:**
  ```text
  Read DEMO_MASTERPLAN_50USD.md §1 (Pictures), §3 (Lyria 3.5 pricing and terms), §7 (music: one track, no vocals), config/pins.txt data section, TECH_PLAN 1.12 (no copyrighted music).
  Confirm the exact Lyria 3.5 model id and API in Google's documentation at run time (google-genai pinned at T-001); do not guess. Record cost in the ledger.
  Brief for the track: 2 minutes, building tension, broadcast feel, no vocals.
  Pins: three 0.186.1, @react-three/fiber 9.8.2, @react-three/drei 10.7.9 for textures; add no npm packages.
  Acceptance: the verification command exits 0.
  ```

### T-083 3D opener scene and 3D polish
- **Owner:** C · **Day:** 9 · **Estimated hours:** 3
- **Depends on:** T-053, T-082
- **Files:** `apps/overlay/src/replay3d/{Opener.tsx,Lighting.tsx}`, `tests/apps/test_replay3d.py`
- **Scope:** In: the 0:00–0:08 night-stadium opener with the struck-through "xG 0.06" lower-third, lighting, camera moves, kit textures. Out: generated video (Veo is deprecated; $50 plan §3).
- **Acceptance criteria:**
  - `/replay3d?opener=1&record=1` records 8 s at ≥ 30 fps at 1920×1080.
  - The opener's numbers come from the golden cache (verified claims), not hard-coded text.
- **Verification:** `npm --prefix apps/overlay run build && pytest tests/apps/test_replay3d.py -q`
- **Brief:**
  ```text
  Read DEMO_MASTERPLAN_50USD.md §3 (Veo deprecated; render the opener in our own 3D scene) and §7 0:00-0:08, TECH_PLAN ADR-008 and 1.9 /replay3d, packages/demo/golden_moments.yaml.
  Pins: three 0.186.1, fiber 9.8.2, drei 10.7.9. No external models or HDRIs unless CC0 and listed in LICENSES.md.
  Seek and camera path are scripted so two recordings match frame for frame.
  Players stay capsules with number sprites (no humanoid models; FEASIBILITY_AUDIT Part A row 62).
  Acceptance: npm --prefix apps/overlay run build && pytest tests/apps/test_replay3d.py -q
  ```

**End of day 9: done means** the live judge run is recorded with honest latency and cost numbers, degraded mode is drilled, policy v2 has a written verdict, and the visuals (crests, kits, music, opener) are ready for video v2.

---

## Day 10 — Fri 30 Oct

### T-084 Golden cache v2 decision
- **Owner:** A · **Day:** 10 · **Estimated hours:** 3
- **Depends on:** T-060, T-078, T-079
- **Files:** `docs/evidence/cache_v2_decision.md`, `data/matches/4242/cache/**` (only if swapped), `docs/video/VERSION` (only if swapped)
- **Scope:** In: if `gate_v2.json` passes and calibration v2 is no worse, regenerate counterfactuals with `policy_v2`, re-run the affected Batch stages and hand-reviewed imports, re-freeze, bump VERSION; else keep the v0.1 cache unchanged. Out: any other cache change.
- **Acceptance criteria:**
  - Either "kept" (manifest unchanged, `frozen-cache-guard` green) or "swapped" (all 1.8 steps re-run, Fact Checker on every output, `docs/video/VERSION` = 2 in the same commit, spend ≤ $1.50).
  - `scripts/check_cue_evidence.py` and `scripts/clean_machine_replay.sh --runs 1` pass after the change; `tests/golden/cues.sha256` updated if swapped.
- **Verification:** `python scripts/frozen_cache_guard.py --base v0.1 && python scripts/check_cue_evidence.py --seed 4242 && bash scripts/clean_machine_replay.sh --runs 1`
- **Brief:**
  ```text
  Read TECH_PLAN 1.8 (precompute steps, freeze rule), ADR-003 consequences (any change after day 7 needs a new video), DEMO_MASTERPLAN §8 ("Nothing after day 7 is allowed to touch the golden-match cache without regenerating the video"), packages/policy/artifacts/gate_v2.json, packages/evals/out/calibration_v2.json.
  If swapping: set frozen false in a working commit, run scripts/precompute.py stages counterfactuals, oracle, dugout, decision_index, then the Batch stages for explanations whose counterfactual numbers changed, re-import review/ edits (re-check their numbers), set frozen true, bump docs/video/VERSION to 2, update tests/golden/cues.sha256, all in one commit.
  Tell C (T-088, T-093) the decision the same morning.
  No dependency changes; engine_hash must equal the git SHA recorded in the manifest.
  Acceptance: the verification command exits 0.
  ```

### T-085 Demo season: five more matches via Batch (Sonnet)
- **Owner:** B · **Day:** 10 · **Estimated hours:** 3
- **Depends on:** T-042, T-057, T-084
- **Files:** `data/matches/{4243,4244,4245,4246,4247}/` (events, tracking, truth, cache), `scripts/precompute.py` (`--tactician-role tactician_live`)
- **Scope:** In: five golden-season matches fully precomputed with Sonnet through the Batch API for `similar_moments`, the Dugout log across the season and the 500-cue groundedness sample. Out: Opus for these matches.
- **Acceptance criteria:**
  - Spend ≤ $4.50 ($50 plan §3) and run on a different day from T-080 (per-day cap $10).
  - All five caches validate, pass `check_cue_evidence.py`, and bring the verified-cue total to ≥ 500.
- **Verification:** `for s in 4243 4244 4245 4246 4247; do python scripts/check_cue_evidence.py --seed $s || exit 1; done && python scripts/check_spend.py`
- **Brief:**
  ```text
  Read DEMO_MASTERPLAN_50USD.md §3 row "Five more demo-season matches, Sonnet, Batch API", TECH_PLAN 1.8 precompute, 1.11 groundedness (500 cues), config/models.yaml tactician_live.
  Generate the matches with the frozen engine (same engine_hash as the golden cache), then run every precompute stage with --tactician-role tactician_live and the batch path.
  These matches are not frozen and not in the video; the frozen-cache guard covers 4242 only.
  Pins: anthropic pinned at T-001 (Batch API); model claude-sonnet-5-5 via tactician_live; custom_id hashing from T-042.
  Acceptance: the verification command exits 0.
  ```

### T-086 Foundry Evaluations groundedness run (optional)
- **Owner:** B · **Day:** 10 · **Estimated hours:** 3
- **Depends on:** T-052, T-056
- **Files:** `packages/evals/foundry_eval.py`, `docs/evidence/foundry_eval.md`
- **Scope:** In: if the trial subscription can create a Foundry project and a judge model deployment, run `GroundednessEvaluator` from `azure-ai-evaluation` 1.18.9 on the 500 cues and export the run ID and table. Out: anything that needs a paid pay-as-you-go subscription.
- **Acceptance criteria:**
  - Either a run ID and exported table, or a dated note "not accessible on this subscription" with the error; the video caption names Foundry only in the first case (TECH_PLAN 1.14 #1).
  - Ledger records $0 for Azure (trial credit), per the $50 plan.
- **Verification:** `test -s docs/evidence/foundry_eval.md`
- **Brief:**
  ```text
  Read TECH_PLAN 1.11 row "Groundedness", 1.14 disagreement 1 and open question 5, FEASIBILITY_AUDIT Part A rows 41 (custom evaluators are preview), 48-49 (Tier 0 and trial subscriptions lack GPT-6 and Claude quota), config/pins.txt (azure-ai-projects 2.9.0, azure-ai-evaluation 1.18.9).
  Use FOUNDRY_PROJECT_ENDPOINT from the environment and DefaultAzureCredential. Read the installed azure-ai-evaluation docs for the GroundednessEvaluator model_config; do not guess parameters.
  Human step: a person creates the Foundry project and any model deployment in the portal.
  Do not count Azure trial credit in the ledger; note it in docs/evidence/foundry_eval.md instead.
  Acceptance: test -s docs/evidence/foundry_eval.md
  ```

### T-087 Routines for recaps (optional)
- **Owner:** B · **Day:** 10 · **Estimated hours:** 2
- **Depends on:** T-050, T-052
- **Files:** `infra/routines/recap_routine.py`, `packages/api/recap_trigger.py`, `docs/evidence/routines.md`
- **Scope:** In: one Foundry Routine that triggers recap generation for demo-season matches through the hosted api, if Routines are usable on the subscription. Out: making Routines part of the demo path.
- **Acceptance criteria:**
  - Either a routine run log showing a recap produced and verified, or a dated "not available" note.
  - The trigger endpoint is authenticated and cannot spend beyond the per-day cap.
- **Verification:** `test -s docs/evidence/routines.md`
- **Brief:**
  ```text
  Read DEMO_MASTERPLAN §8 days 8-10 ("Routines for recaps"), FEASIBILITY_AUDIT Part A row 44 (Routines GA 24 Sep 2026; SDK still project.beta.routines; one trigger, one action; minimum recurrence 5 min), TECH_PLAN 1.7 Recap row.
  Read the azure-ai-projects 2.9.0 docs for the routines API and supported actions; do not guess. If no action can reach our api or an agent, stop and write the note.
  POST /recap/run requires a token held in Key Vault and refuses when SpendGuard reports the per-day cap.
  Human step: a person creates the routine in the portal if the SDK path is unavailable.
  Acceptance: test -s docs/evidence/routines.md
  ```

### T-088 Shot list v2 and high-contrast mode
- **Owner:** C · **Day:** 10 · **Estimated hours:** 3
- **Depends on:** T-061, T-076, T-083
- **Files:** `packages/demo/shot_list_v2.yaml`, `apps/{overlay,fan}/src/styles/high_contrast.css`, `tests/apps/test_high_contrast.py`
- **Scope:** In: a shot list for the full §7 storyboard with half-time cards and opener; the `high_contrast` viewer flag. Out: new beats beyond §7.
- **Acceptance criteria:**
  - Every §7 row maps to one or more shots with clocks from `golden_moments.yaml` (re-read after T-084).
  - `high_contrast: true` passes WCAG AA contrast on lower-thirds (checked in the test by computed colours).
- **Verification:** `python -m demo.record_demo --shots packages/demo/shot_list_v2.yaml --dry-run && pytest tests/apps/test_high_contrast.py -q`
- **Brief:**
  ```text
  Read DEMO_MASTERPLAN_50USD.md §7, TECH_PLAN 1.9 recording, schemas/viewer_profile.schema.json (high_contrast), docs/evidence/cache_v2_decision.md.
  Keep the total under 1:55 (TECH_PLAN 1.12) including the end card.
  Each shot row names its storyboard beat, app, viewer profile, clocks, speed and keyframes.
  high_contrast reads viewer_profile.high_contrast and swaps CSS variables only; the layout does not move.
  Acceptance: the verification command exits 0.
  ```

**End of day 10: done means** the golden cache v2 decision is made and committed, the demo season exists with ≥ 500 verified cues, optional Foundry and Routines results are recorded either way, and the v2 shot list is final.

---

## Day 11 — Sat 31 Oct

### T-089 GRF licence decision and weights publication
- **Owner:** A · **Day:** 11 · **Estimated hours:** 1
- **Depends on:** T-012
- **Files:** `docs/DATA.md`, `LICENSES.md`, `packages/policy/artifacts/PUBLICATION.md`
- **Scope:** In: apply TECH_PLAN 1.13 on the trigger date: if the authors confirmed the licence, publish weights; if not, keep GRF-trained weights private and, optionally, launch an overnight Kickoff-only training run for publishable weights. Out: changing the cached counterfactuals.
- **Acceptance criteria:**
  - `PUBLICATION.md` records the reply (or none), the decision and which weights, if any, are in the repo.
  - No GRF-trained `.pt` is committed without a confirmed licence.
- **Verification:** `test -s packages/policy/artifacts/PUBLICATION.md && ! git ls-files packages/policy/artifacts | grep -q "\.pt$" || grep -q "licence confirmed" packages/policy/artifacts/PUBLICATION.md`
- **Brief:**
  ```text
  Read TECH_PLAN 1.6 datasets row (email the authors; derived weights not published until confirmed), 1.13 row "grf_tracking_data licence unresolved" (trigger 31 Oct; publish Kickoff-only weights; keep GRF-trained weights private), docs/DATA.md.
  If launching a Kickoff-only run, reuse policy/train.py with the GRF loader disabled; it is an experiment and does not touch the cache.
  Human step: a person checks for the authors' reply and records it.
  Update LICENSES.md and README with the decision in one sentence each.
  Acceptance: the verification command exits 0.
  ```

### T-090 Pitchwatch adapter, part 1: rendered clips, RF-DETR and ByteTrackTracker (optional)
- **Owner:** A · **Day:** 11 · **Estimated hours:** 5
- **Depends on:** T-053
- **Files:** `packages/evals/pitchwatch/{render_clips.py,detect.py,track.py,project.py,score.py}`, `docs/evidence/pitchwatch.md`, `data/runtime/pitchwatch/` (git-ignored)
- **Scope:** In: 10 one-minute broadcast-camera clips from `/replay3d`, COCO-pretrained RF-DETR person detection, `trackers.ByteTrackTracker`, ground-truth boxes from tracking projected through the known camera, detection precision/recall and ID switches. Out: Roboflow hosted models or keypoint models (need an account), AGPL weights, sn-gamestate, fine-tuning beyond 1 h.
- **Acceptance criteria:**
  - Installs exactly `rfdetr==1.11.2`, `trackers==2.6.1`, `supervision==0.31.1` (annotators only), `opencv-python==5.0.0.93` from `config/pins.txt`; `sv.ByteTrack` is not referenced anywhere.
  - `pitchwatch.md` has a table: precision, recall at IoU 0.5, ID switches per clip, with the projection method described.
- **Verification:** `python -m evals.pitchwatch.score --clips data/runtime/pitchwatch && ! grep -rn "sv.ByteTrack" packages`
- **Brief:**
  ```text
  Optional ticket: drop it first if day 11 slips.
  Read DEMO_MASTERPLAN_50USD.md §5 (RF-DETR Nano/Small COCO, trackers.ByteTrackTracker), config/pins.txt optional adapter lines, FEASIBILITY_AUDIT Part A rows 24-26 and E.4 (sv.ByteTrack removed in supervision 0.31.0; YOLOv8 weights AGPL; sn-gamestate GPL).
  Render clips with packages/demo/record_demo.py on /replay3d broadcast camera; export the camera matrices per frame from the scene so ground truth projects exactly (no pitch-keypoint model needed).
  Read the rfdetr 1.11.2 and trackers 2.6.1 READMEs for the model class, predict call and tracker update call; do not guess.
  Human step: approve the RF-DETR weight download.
  Acceptance: the verification command exits 0.
  ```

### T-091 Chaos test in CI: 20 resume runs, zero cues lost
- **Owner:** B · **Day:** 11 · **Estimated hours:** 3
- **Depends on:** T-005, T-051
- **Files:** `tests/chaos/test_resume.py`, `tests/chaos/harness.py`, `.github/workflows/ci.yml` (chaos-resume)
- **Scope:** In: 20 runs with kills at random executor boundaries (not only Tactician), in-memory engine, cue-set comparison against an uninterrupted run. Out: Azure chaos (manual drill in T-058).
- **Acceptance criteria:**
  - 20/20 runs lose 0 cues and duplicate 0 cue IDs (TECH_PLAN 1.11 row "Resume").
  - `chaos-resume` CI job runs the 20-run test and finishes in < 10 min.
- **Verification:** `pytest tests/chaos -q --runs 20`
- **Brief:**
  ```text
  Read TECH_PLAN 1.7 kill-switch procedure, 1.11 row "Resume" (20 runs, 0 cues lost), 1.10 CI chaos-resume, DEMO_MASTERPLAN §8 days 11-14 ("Chaos test in CI").
  Harness: start the worker as a subprocess with FileCheckpointStorage in a temp dir and a fake LLMClient with fixed latencies; kill with SIGKILL at a seeded random superstep; restart via supervisor; compare the delivered cue set (ids and content hashes) with an uninterrupted run.
  Add a pytest option --runs (default 5 locally, 20 in CI).
  Pins: agent-framework-core 1.22.0 FileCheckpointStorage; pytest pinned at T-001.
  Acceptance: pytest tests/chaos -q --runs 20
  ```

### T-092 Cost cap test
- **Owner:** B · **Day:** 11 · **Estimated hours:** 2
- **Depends on:** T-008, T-021, T-074
- **Files:** `tests/api/test_spend_caps.py`, `.github/workflows/ci.yml` (spend-ledger runs it)
- **Scope:** In: fake-priced calls that cross the per-match, per-day and project caps; checks on degraded mode, badge message, templates, ledger line and refusal of further paid calls. Out: real spend.
- **Acceptance criteria:**
  - Crossing $2.50 per match flips the mode to degraded within one call; crossing $10 per day does the same for all matches; crossing $50 blocks every paid call.
  - Warning at 80% of each cap appears in logs and in the `spend` WS message.
- **Verification:** `pytest tests/api/test_spend_caps.py -q`
- **Brief:**
  ```text
  Read TECH_PLAN ADR-011, 1.10 "Spend guard", 1.8 "Live mode" (degraded switch), config/budgets.yaml spend (warn_at_fraction 0.8), DEMO_MASTERPLAN §8 days 11-14 ("cost cap test").
  Use a temp ledger path via WHYLINE_SPEND_LEDGER and a fake LLMClient that reports fixed token counts; never call a real API.
  Assert the badge through the mode message {mode: degraded, reason: spend_cap} and the ledger switch line.
  Run this test inside the spend-ledger CI job.
  Acceptance: pytest tests/api/test_spend_caps.py -q
  ```

### T-093 Record video v2 shots
- **Owner:** C · **Day:** 11 · **Estimated hours:** 4
- **Depends on:** T-084, T-088
- **Files:** `packages/demo/out/v2/` (git-ignored), `docs/evidence/rehearsal_v2.md`
- **Scope:** In: a fresh zero-miss rehearsal on the final cache, then every shot in `shot_list_v2.yaml`. Out: editing (T-096).
- **Acceptance criteria:**
  - Rehearsal trace has zero cache misses; `check_cue_evidence.py` and `scan_banned.py` pass.
  - Every shot and keyframe exists and was recorded from the manifest SHA-256 written in `rehearsal_v2.md`.
- **Verification:** `python scripts/check_cue_evidence.py --seed 4242 && python -m demo.record_demo --shots packages/demo/shot_list_v2.yaml --verify-outputs`
- **Brief:**
  ```text
  Read TECH_PLAN 1.8 replay serving, 1.9 recording, 1.13 row "Cache miss during recording", docs/evidence/cache_v2_decision.md, packages/demo/shot_list_v2.yaml.
  Same procedure as T-062 with the v2 shot list; record the manifest SHA-256 at the start.
  Run python scripts/scan_banned.py on all cue text and captions before recording.
  Hand any cache miss to the T-084 owner; never record past a red trace row.
  Acceptance: the verification command exits 0.
  ```

**End of day 11: done means** the licence decision is applied, resume is proven 20/20 in CI, caps are tested, and all v2 shots are recorded from the final cache.

---

## Day 12 — Sun 1 Nov

### T-094 Pitchwatch adapter, part 2: Gemini 3.8 Flash video tagging and accuracy table (optional)
- **Owner:** A · **Day:** 12 · **Estimated hours:** 4
- **Depends on:** T-090
- **Files:** `packages/evals/pitchwatch/tag_video.py`, `packages/newsroom/prompts/video_tagger@1.md`, `docs/evidence/pitchwatch.md`
- **Scope:** In: the `video_tagger` role tagging events on the 10 clips with structured output, precision/recall against engine events within ±1 s, the README table. Out: putting the tagger on the live path.
- **Acceptance criteria:**
  - Tagged events validate against `schemas/event.schema.json`; event P/R per type is in `pitchwatch.md`.
  - Spend ≤ $0.05 ($50 plan §2) recorded in the ledger; a Gemini 429 is handled with backoff and reported (1.13).
- **Verification:** `python -m evals.pitchwatch.tag_video --clips data/runtime/pitchwatch && python scripts/check_spend.py`
- **Brief:**
  ```text
  Optional ticket.
  Read config/models.yaml video_tagger (gemini-3.8-flash, video_processing agentic, output_format event.schema.json), DEMO_MASTERPLAN_50USD.md §2 and §5, TECH_PLAN 1.13 row "Gemini free-tier limits", config/pins.txt (google-genai; client.interactions.create).
  Use GOOGLE_API_KEY via google-genai pinned at T-001; read its docs for video input and structured output; do not guess. Record every call through SpendGuard.
  Use only the 10 rendered clips (our own synthetic footage; no third-party media).
  Acceptance: the verification command exits 0.
  ```

### T-095 Spend report and judging-period hardening
- **Owner:** B · **Day:** 12 · **Estimated hours:** 3
- **Depends on:** T-075, T-092
- **Files:** `scripts/spend_report.py`, `docs/spend.md`, `packages/api/sse.py`, `apps/*/src/stream/StreamProvider.tsx` (SSE fallback), `infra/README.md`
- **Scope:** In: spend by role, model and day from the ledger; SSE fallback from the api when Web PubSub hits 20 connections; scale-to-zero cold-start note; keep-alive plan through judging. Out: Web PubSub Standard.
- **Acceptance criteria:**
  - `docs/spend.md` total equals `scripts/check_spend.py` total and is < $50 (§9 item 7).
  - With Web PubSub disabled, the three apps stream over SSE (test); `infra/README.md` states who keeps the deployment alive and until when.
- **Verification:** `python scripts/spend_report.py --out docs/spend.md && pytest tests/api -q -k sse`
- **Brief:**
  ```text
  Read TECH_PLAN 1.10 (Azure idle costs, spend guard), 1.13 rows "Spend creep" and "Web PubSub 20-connection cap" (SSE fallback from api; document), DEMO_MASTERPLAN §3 ledger and §9 item 7.
  sse.py: GET /sse?viewer_id&mode&club&player emitting the same messages as /ws.
  spend_report.py groups the ledger by role, model, day and mode and writes a table plus the total.
  infra/README.md: minimum replicas, expected cold start, and who checks the hosted URL daily until judging ends.
  Acceptance: the verification command exits 0.
  ```

### T-096 Edit video v2
- **Owner:** C · **Day:** 12 · **Estimated hours:** 5
- **Depends on:** T-093
- **Files:** `packages/demo/edit_v2.yaml`, `packages/demo/captions_v2.srt`, `packages/demo/out/final_v2.mp4` (git-ignored)
- **Scope:** In: final cut of the §7 storyboard with the Lyria track, captions bound to evidence, end card. Out: third-party media, voice (unless a team member records it themselves).
- **Acceptance criteria:**
  - Duration ≤ 115 s (1:55, TECH_PLAN 1.12) by `ffprobe`.
  - Every caption number has a source row in `edit_v2.yaml` pointing to `results.md`, `docs/spend.md`, `live_judge_run.md` or a verified cue.
- **Verification:** `python packages/demo/assemble.py packages/demo/edit_v2.yaml && ffprobe -v error -show_entries format=duration -of csv=p=0 packages/demo/out/final_v2.mp4`
- **Brief:**
  ```text
  Read DEMO_MASTERPLAN_50USD.md §7 (storyboard and captions), TECH_PLAN 1.12 video row, 1.14 disagreement 1, packages/evals/results.md, docs/spend.md, docs/evidence/live_judge_run.md, docs/evidence/foundry_eval.md.
  Rewrite captions to the measured numbers (e.g. the measured groundedness, the measured cost per match, the measured fast-cue p95). Name Foundry only if T-086 produced a run ID.
  Music: the Lyria track from T-082 under the whole cut, ducked under captions; no other audio.
  Keep the caption -> source table in edit_v2.yaml; T-099 reviews it.
  Acceptance: the verification command prints a duration ≤ 115.
  ```

**End of day 12: done means** the spend report is final and under $50, the judging environment has a fallback past 20 clients, and the final cut exists with every caption backed by an artefact.

---

## Day 13 — Mon 2 Nov

### T-097 Final evaluation refresh
- **Owner:** A · **Day:** 13 · **Estimated hours:** 3
- **Depends on:** T-073, T-080, T-084, T-091
- **Files:** `packages/evals/results.md`, `packages/evals/results.json`
- **Scope:** In: `run_evals.py` on final artefacts with live latency (T-080), cost per match, realism, chaos 20/20, groundedness over ≥ 500 cues, the policy used. Out: re-running anything that changes the cache.
- **Acceptance criteria:**
  - No "pending" rows remain; every 1.11 row has a number and pass/fail.
  - `evals-gate` is green, or a failing row is stated plainly in the README with its number.
- **Verification:** `python -m evals.run_evals --seeds 1..50 --out packages/evals/results.md && python -m evals.gate packages/evals/results.json`
- **Brief:**
  ```text
  Read TECH_PLAN 1.11 (whole table), this file's M2 section, docs/evidence/*.md.
  Re-run packages/evals/run_evals.py with sources: live latency packages/evals/out/latency_live.json; cost from the ledger for seeds 9001-9003; groundedness over 4242-4247; resume from the chaos-resume CI artefact.
  The policy row names the engine actually used in the cache and shows both v1 and v2 metrics.
  Never edit a threshold; a miss is written as a miss.
  Acceptance: the verification command exits 0.
  ```

### T-098 README v1.0 evidence refresh and final licence audit
- **Owner:** B · **Day:** 13 · **Estimated hours:** 3
- **Depends on:** T-066, T-095, T-097
- **Files:** `README.md`, `LICENSES.md`, `docs/JUDGES.md`, `docs/architecture.md`, `requirements.lock`
- **Scope:** In: final numbers, links to every artefact, the live judge-run recording, spend report, optional Pitchwatch table if T-094 finished, final `pip freeze` and asset list. Out: new claims.
- **Acceptance criteria:**
  - `scripts/licence_scan.py` passes on the final lockfiles; every image and the music track appear in `LICENSES.md` (§9 item 6).
  - `scripts/check_readme_links.py` passes; every §9 item is linked from the README evidence table.
- **Verification:** `python scripts/licence_scan.py && python scripts/check_readme_links.py README.md docs/JUDGES.md docs/architecture.md`
- **Brief:**
  ```text
  Read DEMO_MASTERPLAN_50USD.md §9, TECH_PLAN 1.11 and 1.12, packages/evals/results.md, docs/spend.md, docs/evidence/*.
  Update numbers only from artefacts. If Pitchwatch was dropped, say so in one line.
  Add the live judge-run recording, the spend report and the 20/20 chaos result to the evidence table.
  Run scripts/licence_scan.py after a fresh pip install -r requirements.lock.
  Acceptance: the verification command exits 0.
  ```

### T-099 Clean-machine v1.0 test and frame-by-frame mark audit
- **Owner:** C · **Day:** 13 · **Estimated hours:** 4
- **Depends on:** T-084, T-096
- **Files:** `docs/evidence/clean_replay_v1.0.md`, `docs/video/v2.md` (audit section)
- **Scope:** In: three consecutive offline replays from a fresh clone (T-064 script), a frame-by-frame review of video v2 for real club, league, player or broadcaster marks, `scan_banned.py` on every UI string, cache text and asset manifest. Out: fixes that change the cache (would need T-084 again).
- **Acceptance criteria:**
  - Three identical cue-stream hashes with networking blocked and no keys, equal to `tests/golden/cues.sha256` (§9 item 1).
  - A person signs the frame audit in `docs/video/v2.md`; `scan_banned.py` passes (§9 item 8).
- **Verification:** `bash scripts/clean_machine_replay.sh --runs 3 && python scripts/scan_banned.py data/matches/4242/cache apps/*/src data/league/assets.json`
- **Brief:**
  ```text
  Read DEMO_MASTERPLAN_50USD.md §9 items 1 and 8, TECH_PLAN 1.12 row "No obscene, political, trademark content", scripts/clean_machine_replay.sh (T-064).
  Run on a second user account or a second machine if available; otherwise a fresh clone in a new directory with a new venv.
  Extract one frame per second from final_v2.mp4 with ffmpeg for the human review sheet.
  Record each run's hash and wall time in docs/evidence/clean_replay_v1.0.md.
  Acceptance: the verification command exits 0 and the audit is signed.
  ```

**End of day 13: done means** every evaluation number is final, the README links all evidence, the licence scan is clean, and the golden match replays identically three times offline on a clean clone.

---

## Day 14 — Tue 3 Nov (M2)

### T-100 Video v2 upload and VERSION
- **Owner:** C · **Day:** 14 · **Estimated hours:** 1.5
- **Depends on:** T-099
- **Files:** `docs/video/VERSION` (= 2), `docs/video/v2.md`
- **Scope:** In: final file, public link, manifest hash, caption source table. Out: further edits.
- **Acceptance criteria:**
  - `docs/video/VERSION` = 2; `v2.md` has the link, duration, manifest SHA-256 and the signed frame audit.
  - The README video link points to v2.
- **Verification:** `test "$(cat docs/video/VERSION)" = 2 && grep -E "manifest_sha256: [0-9a-f]{64}" docs/video/v2.md`
- **Brief:**
  ```text
  Read TECH_PLAN 1.8 freeze rule, 1.12 video row, docs/video/v1.md (same format).
  Human step: a person uploads final_v2.mp4 and pastes the link; the session does not upload.
  Record duration from ffprobe and the manifest SHA-256 from data/matches/4242/cache/manifest.json.
  Update the README video link to v2.
  Acceptance: the verification command exits 0.
  ```

### T-101 M2 sign-off and tag v1.0
- **Owner:** B · **Day:** 14 · **Estimated hours:** 2
- **Depends on:** T-097, T-098, T-099, T-100
- **Files:** `docs/SUBMISSION.md`, `CHANGELOG.md`
- **Scope:** In: walk the M2 checklist, all nine CI jobs green, tag `v1.0`, update the submission if the site allows it. Out: new work.
- **Acceptance criteria:**
  - Every M2 item below is checked with a link; CI green at the tagged commit.
  - Tag `v1.0` pushed after the owner confirms; `CHANGELOG.md` lists v0.1 → v1.0 changes.
- **Verification:** `git tag --list v1.0 && make ci`
- **Brief:**
  ```text
  Read this file's M2 section, TECH_PLAN 1.10 CI list, 1.12 rules checklist, DEMO_MASTERPLAN §9.
  Walk each M2 item, run its command, link the result in docs/SUBMISSION.md.
  git tag -a v1.0 -m "WHYLINE v1.0 (M2)"; confirm with the owner, then push. Human step: a person updates the submission on the hackathon site if the deadline is 21 Nov.
  CHANGELOG.md: one line per ticket closed after v0.1, grouped by owner.
  Acceptance: git tag --list v1.0 && make ci
  ```

**End of day 14: done means** tag `v1.0` is pushed, video v2 is public, every M2 item is green with a link, and the hosted demo stays up through judging.

---
## M1 — Day 7 submittable build (tag v0.1, Tue 27 Oct)

Every item must be ticked, with its command exiting 0, before T-071 tags. An item that cannot be met is written into `docs/SUBMISSION.md` "Known limits" with its measured number; it is never hidden.

| # | Item | Source | Evidence (ticket or named check) | Command |
|---|---|---|---|---|
| 1 | Golden match replays identically on three consecutive runs, clean machine, no network | §9.1 | T-064, check `clean-replay-x3` | `bash scripts/clean_machine_replay.sh --runs 3` |
| 2 | Every cue in the video has a verified flag, evidence IDs and a counterfactual ID that resolve in the Studio drawer | §9.2 | T-057, T-062, T-034; check `cue-evidence` | `python scripts/check_cue_evidence.py --seed 4242 && pytest tests/apps/test_studio.py -q` |
| 3 | Kill switch resumes from a named checkpoint with the same cue ID; log linked from README | §9.3 | T-051, T-067 | `pytest tests/chaos/test_resume.py -q && grep -q kill_resume.log README.md` |
| 4 | Fast cue < 3 s and explained cue < 15 s live | §9.4 | M1 level: T-032 single live probe, numbers in `docs/evidence/latency_probe_day3.md` and README; full recorded judge run is M2 | `test -s docs/evidence/latency_probe_day3.md` |
| 5 | Calibration plot, state-detection confusion matrix and planted-error test in the README with their scripts | §9.5 | T-040, T-055, T-056, T-067 | `python scripts/check_readme_links.py README.md` |
| 6 | Dependencies and assets carry only permissive (MIT, Apache, BSD, ISC, PSF), CC BY/CC0 or paid-commercial licences; no AGPL weights | §9.6 | T-066, check `licences` | `python scripts/licence_scan.py` |
| 7 | Spend ledger in the repo shows the actual total, under $50 | §9.7 | T-008, T-005 `spend-ledger` job | `python scripts/check_spend.py` |
| 8 | No real club, league, player or broadcaster mark in any frame | §9.8 | T-062 `banned-scan`, T-069 signed frame review | `python scripts/scan_banned.py data/matches/4242/cache apps/*/src` |
| 9 | Freeze rule active: `manifest.frozen = true`; guard green | TECH_PLAN 1.8 | T-060, T-071 | `python scripts/frozen_cache_guard.py --base HEAD^` |
| 10 | All nine CI jobs green: lint, unit, schemas, golden-determinism (match and cue hashes), evals-gate, licence-scan, spend-ledger, frozen-cache-guard, chaos-resume (1 run) | TECH_PLAN 1.10 | T-005, T-007, T-051, T-056, T-060, T-066, T-071 | `make ci` and the CI run on the tag |
| 11 | State-detection F1 ≥ 0.75 | TECH_PLAN 1.11 | T-055 | `python -m evals.gate packages/evals/results.json` |
| 12 | Counterfactual Brier ≤ 0.18 and placebo passes | TECH_PLAN 1.11 | T-040 | same |
| 13 | Planted errors caught 100%; false rejects ≤ 2% | TECH_PLAN 1.11 | T-055 | same |
| 14 | Groundedness ≥ 0.95 on all golden cues | TECH_PLAN 1.11 | T-056 | same |
| 15 | Policy metrics measured against the 1.6 table and a written engine decision | TECH_PLAN 1.6, 1.11 | T-037 (`gate.json`; scripted_v1 is an accepted outcome) | `cat packages/policy/artifacts/gate.json` |
| 16 | Outcome heads meet ECE and AUC gates | TECH_PLAN 1.6 | T-025 | `pytest tests/heads -q` |
| 17 | Rollout budgets: scripted 200 × 90 s ≤ 1.3 s CPU; policy 200 × 8 s ≤ 0.3 s MPS | TECH_PLAN 1.4, 1.5 | T-016, T-036 | `pytest tests/rollout -q` |
| 18 | Golden precompute ≤ $1.50; golden match cost per match ≤ $2.50 | $50 plan §3; TECH_PLAN 1.11 | T-042, T-050, T-057 | `python scripts/check_spend.py` |
| 19 | Video under two minutes, fictional marks only, captions bound to artefacts | TECH_PLAN 1.12 | T-063, T-069 | `ffprobe … final_v1.mp4` |
| 20 | Public repo, first commit after 29 Sep, pitch names Microsoft technologies, judge instructions, hosted URL, submission made | TECH_PLAN 1.12 | T-001, T-067, T-068, T-052, T-071 | `python scripts/check_readme_links.py docs/JUDGES.md` |

## M2 — Day 14 flawless build (tag v1.0, Tue 3 Nov)

M1 items stay green. These items replace or add to them.

| # | Item | Source | Evidence (ticket or named check) | Command |
|---|---|---|---|---|
| 1 | Three identical offline replays on a clean clone, equal to `tests/golden/cues.sha256` | §9.1 | T-099 | `bash scripts/clean_machine_replay.sh --runs 3` |
| 2 | Every cue in video v2 resolves in the Studio drawer | §9.2 | T-093, check `cue-evidence` | `python scripts/check_cue_evidence.py --seed 4242` |
| 3 | Kill switch: same cue ID after resume; 20/20 chaos runs lose 0 cues; log linked | §9.3; TECH_PLAN 1.11 "Resume" | T-091, T-098 | `pytest tests/chaos -q --runs 20` |
| 4 | Fast p95 ≤ 3 s and explained p95 ≤ 15 s on a recorded live judge run (3 matches, hosted) | §9.4; TECH_PLAN 1.11 | T-080, T-081, check `live-latency` | `python -m evals.latency --source live --matches 9001,9002,9003 --out packages/evals/out/latency_live.json` |
| 5 | Calibration, confusion matrix, planted-error results and realism plots in the README with scripts | §9.5; TECH_PLAN 1.11 | T-073, T-079, T-097, T-098 | `python scripts/check_readme_links.py README.md` |
| 6 | Final `pip freeze`, npm lockfiles and asset list (images, music) pass the licence scan | §9.6 | T-098 | `python scripts/licence_scan.py` |
| 7 | Spend report equals ledger total, under $50; each live match ≤ $2.50 | §9.7; TECH_PLAN 1.11 | T-095, T-080 | `python scripts/check_spend.py && python scripts/spend_report.py --out docs/spend.md` |
| 8 | Signed frame-by-frame audit of video v2; banned scan clean on cache, UI and assets | §9.8 | T-099 | `python scripts/scan_banned.py data/matches/4242/cache apps/*/src data/league/assets.json` |
| 9 | Freeze rule held: either the v0.1 cache is unchanged, or the change carries a VERSION bump and a new video | TECH_PLAN 1.8 | T-084, T-100 | `python scripts/frozen_cache_guard.py --base v0.1` |
| 10 | All nine CI jobs green at `v1.0`, chaos-resume at 20 runs, spend-ledger running the cap tests | TECH_PLAN 1.10 | T-091, T-092, T-101 | `make ci` and the CI run on the tag |
| 11 | Every 1.11 row has a final number and pass/fail; no "pending" rows; groundedness over ≥ 500 cues | TECH_PLAN 1.11 | T-085, T-097 | `python -m evals.gate packages/evals/results.json` |
| 12 | Policy v2 verdict written; the engine behind every cached counterfactual is named in README and video | TECH_PLAN 1.6, ADR-002 | T-078, T-084 | `cat packages/policy/artifacts/gate_v2.json` |
| 13 | GRF licence decision applied; no unlicensed weights in the repo | TECH_PLAN 1.6, 1.13 | T-089 | T-089 verification |
| 14 | Degraded mode drilled: outage → templates and amber badge, never a blank cue | TECH_PLAN 1.13 | T-081, T-092 | `pytest tests/integration/test_degraded.py tests/api/test_spend_caps.py -q` |
| 15 | Hosted demo reachable through judging; > 20 clients fall back to SSE | TECH_PLAN 1.10, 1.13 | T-075, T-095 | `curl -fsS "$(azd env get-value API_URL)/health"` |
| 16 | Video v2 ≤ 1:55, uploaded, `docs/video/VERSION` = 2 with manifest hash | TECH_PLAN 1.12, 1.8 | T-096, T-100 | T-100 verification |
| 17 | Optional items (T-086, T-087, T-090, T-094) either have evidence or a one-line "not done" in the README | $50 plan §8 days 8–14 | T-098 | `python scripts/check_readme_links.py README.md` |

## Cut lines

Pre-decided drops if a day slips, consistent with the $50 plan §10 risk table, TECH_PLAN 1.13 and FEASIBILITY_AUDIT D.3. **Never cut** (audit D.3): the Fact Checker (T-019), replay mode (T-038, T-039, T-042, T-057), the evaluation tables (T-055, T-056), the video (T-063, T-069), the clean-machine replay (T-064) and the day-7 tag (T-071).

| Day | Drop first | Drop second | Drop third | Basis |
|---|---|---|---|---|
| 3 | T-026 reduced to `big_chance` and `counter_attack`; the other four move to day 8 | T-031 LLM Proposer: ship `proposer_rule` only (models.yaml fallback) | T-028 launch slips one night: gate moves to day 5 morning and T-039 uses scripted_v1 | 1.13 row 1; audit C.2 (Proposer is decorative without the Panel) |
| 4 | T-041 Panel moves to day 8 as a near-line, recap-only feature | T-044 Player-Cam card (fan modes stay) | T-040 moves to day 6 beside T-056 (still in M1) | audit D.3 third cut; 1.13 row 2; 1.14 #4 |
| 5 | T-053 3D scene: video uses the 2.5D ghost trail | T-047 Dugout (storyboard keeps the Oracle beat) | T-048 Decision Index: show the live head-swing approximation | 1.13 row "3D scene late" (25 Oct); 1.14 #3 |
| 6 | T-059 OpenTelemetry: console exporter only | T-058 Cosmos: file checkpoints in the Azure container (Cosmos store is beta) | T-054 `similar_moments`: Tactician golden runs without that tool | audit C.2 (file store is the safer default); ADR-005 |
| 7 | T-070 reduced to P0 fixes | T-065 reduced to P0 fixes | T-068 `architecture.md` minimal (JUDGES.md still ships) | 1.13 row "Deadline is 27 Oct" |
| 8 | T-077 images: keep text crests and flat kit colours | T-073 DFL part: SkillCorner only | T-075 Web PubSub: hosted apps use the api WebSocket, SSE later | 1.13 row "Web PubSub 20-connection cap" |
| 9 | T-083 opener polish: reuse the v1 opener | T-079 sensitivity study | T-081 reduced to the outage drill | $50 plan §10 row "Claude refusals or outages" |
| 10 | T-087 Routines | T-086 Foundry Evaluations: own evaluator stands; captions do not name Foundry | T-085 demo season: groundedness reported on golden cues only | 1.14 #1; $50 plan §3 |
| 11 | T-090 Pitchwatch part 1 | T-092 cap test: keep T-021 unit tests and the spend-ledger job | T-093 re-record only shots whose cache or visuals changed | $50 plan §10 row "Gemini free-tier limits" |
| 12 | T-094 Pitchwatch part 2 | T-095 SSE fallback (spend report stays) | T-096: ship video v1 plus music and changed shots | 1.13 row "Spend creep" |
| 13 | T-098 limited to the numbers table and licence scan | T-097 refresh only rows whose inputs changed | none: T-099 is never cut | §9 items 1 and 8 |
| 14 | T-100: video v1 stays the official video | optional evidence removed from the README | T-101 tags `v1.0` with a known-issues list rather than slipping | 1.13 row "Deadline" |

## Notes on rebalancing and plan gaps

- **B's load in §8 exceeds 8 h on days 3–5.** Kept on the §8 days but moved owners: the api replay and control layer (not in §8) goes to C on days 2–3; the Fourth Official moves from B day 3 to A day 5 (still before the day-6 recording); Scout is B day 3; Recap with producer approval (needed for the 45:00 veto, not in §8) is B day 5; Azure is split across day 5 (deploy), day 6 (Cosmos, telemetry) and day 8 (Web PubSub, Key Vault hardening).
- **Day 9 per-day cap.** The live judge run (≤ $7.50) and the demo season (≤ $4.50) together would cross the $10 per-day cap, so the demo season runs on day 10 (T-085).
- **"200 × 60 s" in §8 day 2** is kept as a benchmark (T-016); counterfactual defaults stay at 8 s (TECH_PLAN 1.5).
- **React pin.** `config/pins.txt` says React 18.3.x while fiber 9.8.2 is pinned; T-001 checks the peer range and corrects the pin if fiber needs React 19.
- **Auto-events** have no type in `event.schema.json`; T-026 stores them as `facts` instead of changing the schema.
- **Two endpoints added** to the 1.4 list for the Why? drawer, `/replay3d` and Player-Cam: `GET /match/{id}/doc/{collection}/{doc_id}` (T-033) and `GET /match/{id}/players/{player_id}/stats` (T-044); T-095 adds `GET /sse`.
- **Pitchwatch** has no package in the 1.4 layout, so it lives in `packages/evals/pitchwatch/` as an evaluation adapter.
