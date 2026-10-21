# WHYLINE — Technical Plan

Version 1.0, 21 October 2026. This document is the engineering blueprint for the frozen scope in `DEMO_MASTERPLAN_50USD.md`: English only, no voice, Sliding Doors and the Fourth Official as headline features, replay-from-cache demo, live mode for judges, $50 cap. Every API name below was verified in `FEASIBILITY_AUDIT.md` Part A unless marked "pin at T-001" (meaning: install the current release in ticket T-001 and record the exact version in `config/pins.txt`). Every timing marked "measured" comes from the audit's spikes on this Mac (Apple Silicon, 11 cores, 18 GB, Metal GPU via PyTorch MPS).

Terms used throughout: a **moment** is a flagged instant worth explaining; a **cue** is one timed on-screen instruction (`schemas/cue.schema.json`); the **blackboard** is the shared store of facts, moments and cues; a **rollout** is a batch of simulated futures from a frozen state; **replay mode** serves precomputed outputs; **live mode** calls real models.

---

## 1.1 System overview

### Runtime components

| Component | Process | Port / location | Role |
|---|---|---|---|
| `kickoff` | CLI `python -m kickoff play` | writes `data/matches/<seed>/` or streams | Scripted 22-player engine; generates events, tracking, hidden truth |
| `whyline-api` | `uvicorn api.main:app` | :8000 | REST, WebSocket cue/track stream, replay controller, spend guard, demo-script runner |
| `whyline-mcp` | `python -m mcp_server` | :8080 (MCP Streamable HTTP) | The only data path for agents: events, pitch control, counterfactuals, stats, verification |
| `whyline-newsroom` | `python -m newsroom.worker` | no port; subscribes to the moment queue | Agent Framework workflow: one run per moment; checkpoints to `.checkpoints/` locally, Cosmos in Azure |
| `overlay` | Vite dev / static | :5173 | Broadcast overlay (2.5D canvas + DOM), route `/replay3d` for the 3D Sliding Doors scene |
| `studio` | Vite dev / static | :5174 | Producer console |
| `fan` | Vite dev / static | :5175 | Fan app (modes, club, Player-Cam) |
| Blackboard | SQLite `data/runtime/blackboard.sqlite` locally; Cosmos DB NoSQL in Azure | — | facts, moments, explanations, counterfactuals, cues, traces |
| Cache | `data/matches/4242/cache/` + `manifest.json` | — | every precomputed artefact for the golden match |
| Checkpoints | `FileCheckpointStorage(".checkpoints")` locally; `CosmosCheckpointStorage` in Azure | — | workflow state per superstep |
| Spend ledger | `data/spend/ledger.jsonl` | — | one line per model call; committed |
| Queue | `asyncio.Queue` in-process locally; Azure Event Hubs (Basic) in Azure | — | engine → api → newsroom moment hand-off |

### Data flow, replay mode (the demo)

```
data/matches/4242/{events.jsonl, tracking.npz, truth.json}        (frozen, hashed)
        │ replay clock (speed x1 … x10)
        ▼
whyline-api ──tracking_frame 10 Hz──────────────────────────────▶ overlay / fan / studio (WebSocket :8000/ws)
        │ events at their t_ms
        ▼
analytics (physics, heads)  ← cache hit: cache/analytics/*.npz, pitch_control/pc_*.npz
        │ moments (Scout)   ← cache hit: cache/moments.jsonl
        ▼
whyline-newsroom workflow (same graph as live)
        │ every LLM/rollout call → CacheClient.lookup(key) → sleep(simulated_latency_ms) → cached output
        │ trace events → studio agent-trace panel
        ▼
Director → cue (schemas/cue.schema.json) → api → WebSocket → screens
        ▲
demo_script.yaml: at 44:10 kill newsroom worker; at 45:00 producer veto on recap cue
```

### Data flow, live mode (judges)

```
kickoff play --seed <any> --target api  ──POST /ingest/events + /ingest/tracking──▶ whyline-api
        ▼
analytics computed on the fly (physics on CPU; heads via LightGBM)
        ▼
Scout → moment → asyncio.Queue (Event Hubs in Azure) → whyline-newsroom
        ▼
Proposer (Sonnet) → rollout via MCP simulate_counterfactual (scripted_v1 CPU, n=100, 8 s) → Tactician (Sonnet, tools over MCP :8080)
        → Narrator (Haiku) → FactChecker (code) → Director (code) → cue → api → screens
spend guard: every call appends to ledger; per-match cap $2.50, per-day cap $10; cap reached → mode=degraded (templates), badge on screens
```

Both modes run the same workflow graph, the same Director, the same screens. The only difference is which `LLMClient` and `RolloutClient` implementation is injected: `CacheClient` or `LiveClient`.

---

## 1.2 Architecture decision records

Each ADR is also a file under `docs/adr/`.

**ADR-001 Scripted Kickoff engine is the live world.** Context: a learned world model cannot be trusted on the live path by day 7 (audit B.1). Decision: a deterministic, batched numpy engine with hidden tactical truth is the source of events and tracking for both modes; the learned policy is an optional decision model inside it. Rejected: gfootball as the live world (not installable here; archived); a learned world model (horizons unproven). Consequences: realism is bounded by the engine's style profiles; the policy must be calibrated to it.

**ADR-002 Decision-only learned policy, 6–8 s horizon, hand-off to the goal-in-horizon head.** Context: per-tick learned rollouts cost 80 ms per step on CPU and 20 ms on MPS at batch 200 (measured); published soccer forecasters are stable to 4–6.4 s. Decision: the policy is called only at decision points (possession gain, or 1.0 s since last decision); physics and role-based movement advance between calls; learned horizons are capped at 8 s (the top of the audit's 6–8 s range; the 1.6 gates test ball error at 4 s and shape at 8 s); terminal states are valued by the goal-in-8-s head. Rejected: per-tick policy; 15 s horizons. Consequences: an 8 s horizon needs about 8–15 policy calls depending on possession changes; 15 calls at batch 200 measured 0.3 s on MPS and 1.2 s on CPU, so the 8 s budget is conservative; futures beyond 8 s are model estimates, labelled as such.

**ADR-003 Replay-from-cache is the demo mechanism.** Context: a two-minute video must be recorded without any live failure. Decision: every analytics, rollout and model output for the golden match is precomputed, verified, hashed and indexed in a manifest; the demo serves cache hits with simulated latency; the manifest is frozen after day 7. Rejected: live recording with retries. Consequences: a separate precompute script and a `CacheClient`; any change to engine or prompts after day 7 requires a new video.

**ADR-004 Claude model routing with Gemini as fallback and video tagger.** Decision: Opus 5.5 for the golden match's Tactician and recaps (Batch API), Sonnet 5.5 for the live Tactician, Panel and recap fallback, Haiku 5.5 for fast lines; Gemini 3.8 Flash for the optional video tagger and as the narrator fallback. Rejected: Foundry-hosted Claude (requires a paid pay-as-you-go subscription; trial gets 0 quota); Gemini Argon (no free tier, not needed). Consequences: `agent-framework-anthropic` (beta) and the `anthropic` SDK; prompt caching on the league block; server-side refusal fallback on every Opus/Sonnet call.

**ADR-005 Microsoft Agent Framework graph workflows with file checkpoints locally and Cosmos in Azure.** Decision: `WorkflowBuilder` graph, one run per moment, `FileCheckpointStorage` locally and for the recorded demo (the audit's recommended default), `CosmosCheckpointStorage` (beta) in the Azure deployment with `FileCheckpointStorage` on a mounted volume as its fallback; CI exercises the file store only; human-in-the-loop via `ctx.request_info()` and `@response_handler`. Rejected: `RequestInfoExecutor` (does not exist in Python 1.22.0); LangGraph (not a hero technology). Consequences: a resumable, inspectable graph; the kill-switch demo is a real checkpoint resume.

**ADR-006 The MCP server is the only data path for LLM agents.** Decision: LLM-backed agents read events, pitch control, counterfactuals and stats only through `whyline-mcp` tools; code executors (Scout, Rollout, Fact Checker, Director) write their outputs through the `Blackboard` client held by the newsroom worker, which is the only writer. Rejected: direct SQL from LLM agents. Consequences: the tool surface is the audit boundary for everything a model can see; the reuse by GitHub Copilot Agent Mode is a plan, not a verified feature.

**ADR-007 The Cue Sheet is the editorial product boundary.** Decision: everything below produces `cue.schema.json`; everything above renders it; a rendering partner integrates at that line. The world-state stream (tracking frames, facts, oracle) is a separate, non-editorial feed the screens also consume. Consequences: screens never read the blackboard directly; cues carry evidence, verification and provenance.

**ADR-008 2.5D canvas for live overlays; one stylised 3D scene for Sliding Doors replays.** Decision: the live overlay is a Canvas 2D pitch with DOM lower-thirds; the Sliding Doors replay is a React-Three-Fiber scene (fiber 9.8.2, drei 10.7.9, three 0.186.1) with capsule players and two cameras. Rejected: full per-viewer 3D broadcast (15 person-days); gfootball frames (gfootball failed three install spikes on this Mac; the Docker route is untested and out of scope). Consequences: the 3D scene is a route in the overlay app and only has to look good for twenty seconds of video.

**ADR-009 Azure free account hosting.** Decision: Static Web Apps (free) for three apps, Container Apps consumption (free grant) for api, mcp, newsroom, Cosmos DB free tier for blackboard, checkpoints and the spend ledger, Application Insights, Key Vault; Event Hubs Basic only during judging (trial credit). Tracking frames (10 Hz) and the world-state stream are served over the api container's own WebSocket; Web PubSub (free tier: 20 connections, 20,000 messages per day) carries cues only (about 200 per match), so the daily message cap is never approached. Rejected: GPU workload profiles (quota needs pay-as-you-go); tracking over Web PubSub (54,000 messages per client per match, an estimate, would exceed the free cap). Consequences: live counterfactuals in Azure run on CPU with n=100; idle cost ≈ $0; the Application Insights and Key Vault allowances are small but were not verified in the audit (estimate).

**ADR-010 English only, no voice.** Decision: no Localizer agent, no TTS, no audio in cues. Consequences: `cue.text` is a single English headline and body; the challenge's multi-language bullet is not addressed and the README says so.

**ADR-011 Spend caps in code.** Decision: every model call goes through `SpendGuard`, which prices tokens from `config/budgets.yaml`, appends to the ledger, and flips the system to degraded mode at the per-match, per-day or project-total cap, all three enforced at runtime (the project total is read from the ledger at start-up). Locally the ledger is `data/spend/ledger.jsonl`; in Azure it is the Cosmos `spend` collection (safe across scale-to-zero) and `scripts/pull_ledger.py` mirrors it into the committed file. Consequences: the ledger is committed; CI fails if the total exceeds $50; a run can never exceed $50 even over two weeks of judging.

**ADR-012 Pretrained models wherever one exists; one model needs a training run of its own.** Decision: the on-ball decision policy is the one model that needs an overnight run on the Mac GPU; the outcome heads (LightGBM, minutes on CPU), the chaos head (logistic) and the moment encoder (a small autoencoder, about 20 minutes on MPS) are trained too but are small; vision (optional adapter) uses COCO-pretrained RF-DETR. Consequences: $0 training; policy quality is gated at day 4 with a scripted fallback already wired.

---

## 1.3 Data contracts

All schemas are JSON Schema draft 2020-12 under `schemas/` and validate their own `examples` (checked). **Versioning rule:** every document carries `schema_version` (semver). A change that adds optional fields bumps the patch or minor number and consumers ignore unknown fields. A change that removes or retypes a field bumps the major number, gets a new `$id`, and the cache manifest for any match generated under the old major version is invalid. CI validates every fixture and every cache entry against the schema version it names.

| Contract | File | Purpose |
|---|---|---|
| Event | `schemas/event.schema.json` | StatsBomb-like event; 18 types; type-specific `attrs` documented in the schema description; two worked examples (the Silva→Okafor pass `e_8809`, the Okafor shot `e_8812` at 31:14) |
| Cue | `schemas/cue.schema.json` | timed on-screen instruction; layers, targets, text, graphics, explain, verified, producer_status, provenance |
| Explanation | `schemas/explanation.schema.json` | Tactician output; `claims[]` bound to evidence IDs; rewrite `attempt` 1–3 |
| CounterfactualResult | `schemas/counterfactual.schema.json` | rollout output; baseline vs alternative; n, horizon, seed, engine |
| ViewerProfile | `schemas/viewer_profile.schema.json` | mode, club, player, metric, high-contrast |
| CacheManifest | `schemas/cache_manifest.schema.json` | index of precomputed artefacts; key format and freeze flag |

### Tracking frame format

`data/matches/<seed>/tracking.npz` (numpy, compressed):

| Array | dtype | shape | Meaning |
|---|---|---|---|
| `t_ms` | int64 | [T] | match time per frame, 100 ms apart |
| `period` | int8 | [T] | 1 or 2 |
| `S` | float32 | [T, 23, 6] | rows 0–10 home, 11–21 away, 22 ball; columns x, y (m), vx, vy (m/s), stamina (0–1; ball: 0), facing (rad; ball: spin placeholder 0) |
| `ball_z` | float32 | [T] | ball height, m |
| `holder` | int16 | [T] | row index of the player in control, −1 if none |
| `possession` | int8 | [T] | 0 home, 1 away, −1 none |
| `player_ids` | str | [22] | `p_017` … in row order |

JSON equivalent (API stream message `tracking_frame`): `{"t_ms": 1874000, "period": 1, "p": [[x, y, vx, vy], …23 rows…], "ball_z": 0.3, "holder": 6, "possession": 0}`.

### Blackboard documents

| Collection | Key | Fields |
|---|---|---|
| `facts` | `f_000001` | `match_id, t_ms, kind (index|state|stat), name, value, unit, window_s, evidence_event_ids[]` |
| `moments` | `mo_00077` | `match_id, t_ms, clock, kind, leverage, players[], team, evidence_event_ids[], hypotheses[], fast (bool), status` |
| `pitch_control` | `pc_000412` | `match_id, t_ms, grid [34, 53] float16 (2 m cells), home_share, contested_frac, zones{}` (stored as `.npz` with a JSON stub) |
| `counterfactuals` | `cf_000077` | `counterfactual.schema.json` |
| `explanations` | `ex_000077` | `explanation.schema.json` |
| `cues` | `c_000912` | `cue.schema.json` |
| `traces` | `tr_…` | `run_id, moment_id, executor, started_ms, latency_ms, model, tokens_in, tokens_out, cost_usd, cache_hit, status, checkpoint_id` |

IDs are zero-padded, monotonic per match, and identical across runs of the same seed (determinism, 1.8).

---

## 1.4 Module specifications

Repository layout:

```
packages/kickoff  physics  heads  policy  rollout  blackboard  mcp_server  newsroom  fourth_official  cache  api  evals  demo
apps/overlay (incl. /replay3d)  studio  fan
schemas/  config/  data/{league,matches/4242,spend,runtime}  docs/adr  infra/  scripts/  tests/
```

Each package is a Python 3.12 package with `pyproject.toml`, tests under `tests/<package>/`, and a `README.md` that restates the interface below.

### kickoff (engine)

Purpose: generate a football-realistic synthetic match with events, 10 Hz tracking and hidden truth; expose a batched state for rollouts.

```python
class Engine:
    def __init__(self, league: League, home: str, away: str, seed: int, batch: int = 1,
                 decision_model: DecisionModel = ScriptedRule(), styles: dict | None = None) -> None
    def step(self) -> list[Event]            # advances 100 ms for all B worlds
    def state(self) -> State                 # S [B,23,6], ball_z [B], holder [B], possession [B], score [B,2], t_ms, period
    def branch(self, t_ms: int, batch: int, override: Override | None) -> "Engine"   # clone at t_ms into `batch` worlds
    def play(self, until_ms: int | None = None) -> MatchRecord                      # events, tracking, truth
class League: clubs, players (fictional), style profiles; loaded from data/league/*.json
class ScriptedRule(DecisionModel): def decide(self, state: State) -> Action        # utility + noise; deterministic given rng
@dataclass class Override: first_action: Action; styles: dict[str, StyleDelta] | None
```

Inputs: league JSON, seed. Outputs: `events.jsonl` (schema-valid), `tracking.npz`, `truth.json` (`phases[]`, `momentum[]`, `style_profiles`), `match_metadata` event first. Performance: a 90-minute match at B=1 in under 60 s on CPU (target); `branch` + 900 steps at B=200 in ≤ 1.3 s (measured 1.2 s warm). Failure behaviour: any NaN in `S` raises `EngineError` and the match is discarded. Tests: schema validity of every event; seed reproducibility (byte-identical `events.jsonl` across two runs); no truth leakage (no key from `truth.json` appears in events); realism ranges on 50 matches (pass completion 78–86%, 1.0–1.8 goals per team, 8–16 shots per team). Libraries: numpy 2.5.4, pydantic 2.14.1.

### physics (analytics)

```python
def pitch_control(S: np.ndarray, cell_m: float = 2.0) -> np.ndarray                # [34,53] home share, Spearman-style
def indices(window: TrackingWindow, events: list[Event]) -> dict[str, float]       # control_home, control_away, pressure_home/away, tempo, turnover_rate
def chaos_index(pc: np.ndarray, turnovers_60s: int, transition_share: float) -> float   # 0–100 fallback formula until the learned head exists
def speeds(window: TrackingWindow) -> SpeedReport                                   # ball_kmh, shot_kmh, sprints[(player, kmh, t_ms)]
def auto_events(window, events) -> list[Event]                                      # pressing_trap, line_break, switch_of_play, overload, counter_attack, big_chance
class StateMachine: def update(self, chaos: float, t_ms: int) -> str | None         # Settled/Transitional/Chaotic with hysteresis (enter >65 for 20 s, exit <50 for 30 s)
```

Performance: all of the above for one 100 ms frame in < 15 ms on CPU (target; 1,802 cells × 22 players vectorised). Tests: pitch control sums to 1 per cell; symmetry test (mirror the pitch, shares invert); state machine hysteresis unit tests. Libraries: numpy, scipy 1.18.1.

### heads (outcome models)

```python
class XGHead:        def predict(self, shots: pd.DataFrame) -> np.ndarray          # features in 1.6
class PassHead:      def predict(self, passes: pd.DataFrame) -> np.ndarray
class WinProbHead:   def predict(self, states: pd.DataFrame) -> np.ndarray          # [n,3] home/draw/away
class GoalIn8sHead:  def predict(self, states: pd.DataFrame) -> np.ndarray          # [n,2] home, away
class ChaosHead:     def predict(self, features) -> np.ndarray                      # P(possession change within 10 s)
class MomentEncoder: def encode(self, pc, features) -> np.ndarray[64]; def phase(self, z) -> str
def train_all(matches_dir: Path, out_dir: Path, seed: int) -> Report
```

All heads are LightGBM (pin at T-001) except `MomentEncoder` (torch autoencoder). Artefacts in `packages/heads/artifacts/*.txt|.pt` with a `calibration.png` and `metrics.json` each. Failure behaviour: a missing artefact raises at start-up (never silently falls back). Tests: calibration ECE ≤ 0.03 on held-out; monotonicity sanity (xG rises as distance falls).

### policy (learned decision model)

```python
class DecisionPolicy(torch.nn.Module):
    def forward(self, tokens: Tensor[B,23,F], ctx: Tensor[B,G]) -> PolicyOut    # kind_logits [B,5], pass_logits [B,11] (10 teammates + mask), carry_logits [B,8]
    def act(self, state: State, generator: torch.Generator) -> list[Action]       # samples per world
def build_dataset(grf_dir: Path, kickoff_dir: Path, out: Path, split_seed: int) -> DatasetReport
def train(config: TrainConfig) -> TrainReport
def evaluate(ckpt: Path, test: Path, n_rollouts: int = 20) -> EvalReport        # thresholds in 1.6
```

Device: `mps` when available. Checkpoints: `packages/policy/artifacts/policy_v1.pt` plus `metrics.json`. Failure behaviour: if `metrics.json` fails thresholds, `rollout` refuses to load it unless `WHYLINE_ALLOW_UNGATED_POLICY=1`. Libraries: torch 2.14.1, pandas (pin at T-001).

### rollout (the primitive and three callers)

See 1.5. Public interface:

```python
def rollout(state: State, overrides: Override | None, B: int, horizon_s: float, seed: int,
            engine: Literal["scripted_v1", "policy_v1"] = "scripted_v1") -> Futures
def sliding_doors(match: MatchRef, t_ms: int, alternative: Action, n: int = 200, horizon_s: float = 8, seed: int = 4242, engine=...) -> CounterfactualResult
def oracle(match: MatchRef, t_ms: int, n: int = 100, horizon_s: float = 8, seed=...) -> Forecast          # p_shot_10s per team, likely zone, likely shooter
def dugout(match: MatchRef, t_ms: int, team: str, options: list[StyleDelta], n: int = 100, horizon_s: float = 8, seed=...) -> list[OptionResult]
```

### blackboard

```python
class Blackboard(Protocol):
    def put(self, collection: str, doc: dict) -> str; def get(self, collection, id) -> dict
    def query(self, collection, **filters) -> list[dict]; def watch(self, collection) -> AsyncIterator[dict]
class SqliteBlackboard(Blackboard)      # local; one table per collection, JSON column, indexes on match_id and t_ms
class CosmosBlackboard(Blackboard)      # Azure; azure-cosmos (pin at T-001); partition key /match_id
```

Performance: put < 2 ms locally. Tests: round-trip every schema example; `watch` delivers in insertion order.

### mcp_server

Official MCP Python SDK (`mcp`, pin at T-001), FastMCP, Streamable HTTP on :8080. Tools (signatures in 1.7). Failure behaviour: every tool returns a structured error `{error, code}` and never raises into the agent. Tests: each tool against the golden match fixtures; `simulate_counterfactual` returns the cached `cf_000077` in replay mode.

### newsroom

Agent Framework `agent-framework-core==1.22.0`, `agent-framework-orchestrations==1.3.2`, `agent-framework-anthropic==1.0.0b261015` (`from agent_framework.anthropic import AnthropicClient`), `agent-framework-gemini==1.0.0b261015` (`from agent_framework.gemini import GeminiChatClient`). Executors are plain `Executor` subclasses with `@handler` methods; LLM-backed executors hold an `Agent` built on the client for their role from `config/models.yaml`. See 1.7.

### fourth_official

```python
def check_offside(frame: Frame, pass_event: Event) -> OffsideRuling | None     # margin_m, last_defender, line [[x,y1],[x,y2]]
def check_foul(events: list[Event], frames: TrackingWindow) -> FoulRuling | None  # contact point, closing speed, in_box
def ruling_to_cue(r: Ruling, t_ms: int) -> Cue                                  # layer referee_line, kind fourth_official, verified by construction
```

Rules library in `packages/fourth_official/rules.yaml` (offside, penalty area, handball zones, back-pass). Performance: < 5 ms per check. Tests: geometric unit tests with hand-built frames.

### cache (replay layer and precompute)

```python
class CacheManifest: load/save; key(match_id, moment_id, producer, version, model, seed) -> str; verify_hashes() -> bool
class CacheClient(LLMClient, RolloutClient):  # serves cache hits with simulated latency; misses raise CacheMiss in replay mode
def precompute(seed: int, mode: Literal["batch", "live"], roles: list[str], hand_review_top_k: int = 20) -> Report
```

### api

FastAPI (pin at T-001). Endpoints: `GET /health`, `GET /match/{id}/events?from&to`, `GET /match/{id}/cues?viewer=…`, `POST /ingest/events`, `POST /ingest/tracking`, `POST /replay/control {action: play|pause|seek|speed}`, `POST /producer/decision {request_id, decision}`, `POST /demo/kill {target}`, `GET /spend`, `WS /ws?viewer_id&mode&club&player` (messages in 1.9). `SpendGuard` middleware wraps every `LLMClient` call. Performance: cue fan-out to 20 clients < 50 ms.

### evals, demo

`evals/run_evals.py` produces `evals/results.md` (1.11). `demo/record_demo.py` (Playwright, pin at T-001) records the screens (1.9). `demo/demo_script.yaml` drives kill-switch and veto.

### Front-end apps

Vite + React + TypeScript (pins at T-001); `overlay` includes the R3F scene under `/replay3d`. No UI library beyond React; Canvas 2D for the pitch; CSS for lower-thirds.

---

## 1.5 The rollout primitive

```python
def rollout(state: State, overrides: Override | None, B: int, horizon_s: float, seed: int,
            engine: Literal["scripted_v1", "policy_v1"] = "scripted_v1") -> Futures
```

**State layout.** `State.S: float32 [23, 6]` (x, y, vx, vy, stamina, facing), `ball_z: float32`, `holder: int` (row index, −1 none), `possession: int`, `score: (int, int)`, `t_ms: int`, `period: int`, `attack_dir: (+1 | −1)` for home, `styles: dict`. `rollout` tiles it to `[B, 23, 6]` and keeps per-world copies of the scalars.

**Forcing the first action.** If `overrides.first_action` is set, the holder's first decision in every world is replaced by it: the engine executes the action's physics (pass: ball velocity toward the target with the engine's pass-speed model and the pass head's completion sampling; carry: holder velocity toward the direction; shoot: ball toward goal with the shot model; clear/hold likewise). From the next decision onward, the engine's decision model is used. If the holder cannot legally perform the action (target offside, ball not controllable), `rollout` returns `Futures.invalid_reason` and the caller must pick another alternative.

**Decision points.** `scripted_v1`: the rule evaluates at every tick where the holder is in control, with a 0.3 s reaction latency after gaining control. `policy_v1`: the policy is called when (a) a player gains control, or (b) 1.0 s has elapsed since the last policy call for the current holder; otherwise the previous action persists (a carry continues, a pass is in flight). Between decision points, off-ball players move toward role targets from the style profile with the physics prior; the ball follows ballistic physics; duels and interceptions resolve by the engine's deterministic rules. All B worlds advance in lock-step tensors.

**Horizon hand-off.** For each world, `goal_b ∈ {0,1}` is 1 if the attacking team scores within `horizon_s`. For worlds without a goal, the terminal state is valued by `GoalIn8sHead` to estimate the probability of a goal in the next 8 s. Reported `p_goal_team = mean_b[goal_b + (1 − goal_b) · head(terminal_b)]`. Win probability is `WinProbHead` applied to the terminal state with the expected score adjustment, averaged. The 95% interval is the normal approximation over B.

**Returns.** `Futures(S_end [B,23,6], goals [B,2], shots [B,2], ball_paths [B, horizon_s+1, 2] at 1 Hz, p_goal_home, p_goal_away, win_prob_home, ci95, xt_gain_mean, invalid_reason)`. `sliding_doors` runs `rollout` twice (baseline, alternative) and assembles `CounterfactualResult`.

**Determinism.** `numpy.random.default_rng(seed)` for engine noise; world `b` draws from a child generator `seed + b`; `torch.Generator().manual_seed(seed)` for policy sampling, with logits moved to CPU before `torch.multinomial` so device float differences cannot change samples. The same `(state, overrides, B, horizon_s, seed, engine, engine_hash)` always returns byte-identical `Futures`; CI asserts this on the golden moment.

**Budgets (measured on this Mac).** `scripted_v1`, B=200, 90 s: 1.2 s warm on CPU (≈ 0.2 s for 15 s). `policy_v1`, B=200, 8 s, decision-only (about 15 policy calls): 0.3 s on MPS, 1.2 s on CPU. Live mode in Azure (CPU only): `scripted_v1`, B=100, 8 s, target ≤ 0.5 s.

**Callers.** `sliding_doors` (two rollouts, one alternative, from a past state); `oracle` (one rollout from the current state every 2 s in replay, every 5 s live with B=50; returns `p_shot_10s`, most frequent shot zone, most frequent shooter); `dugout` (one rollout per option with `overrides.styles` set for one team; returns options ranked by `Δwin_prob`).

---

## 1.6 ML specification

### Datasets, licences, attribution

| Dataset | Use | Licence and attribution |
|---|---|---|
| `Dtradke/grf_tracking_data` (Radke & Tilbury, AAMAS 2025) — 150 games visible in the Drive folder, up to 3,000 via the downloader; CSV, 23 rows per timestep: `GAME_ID, TIMESTEP, TEAM_0_SCORE, TEAM_1_SCORE, PLAYER_ID, TEAM_ID, PLAYER_ROLE, LOCATION_X/Y/Z, VELOCITY_X/Y/Z, ON_BALL` | Policy pre-training | No LICENSE file in the repo; the arXiv listing shows CC0 for the paper. README attribution: "Simulating Tracking Data to Advance Sports Analytics Research, Radke & Tilbury, AAMAS 2025." Action: email the authors (T-012); until confirmed, derived weights are not published beyond the repo's own artefacts |
| Kickoff matches (ours) | Policy training, all heads | Generated; no licence needed |
| SkillCorner open data (MIT), DFL/Bassek 2025 (CC BY 4.0) | **Validation only** (distribution checks in `evals/realism.py`), never training | Attribution strings in `docs/DATA.md` |

### On-ball decision policy

**Pipeline** (`packages/policy/data.py`): (1) load CSVs; verify the coordinate convention on the first file (GRF normalised x ∈ [−1, 1], y ∈ [−0.42, 0.42] is expected; map to metres with x' = (x+1)·52.5, y' = (y+0.42)·(68/0.84)); flip so the team in possession always attacks +x; (2) derive the frame rate from `TIMESTEP` spacing (expected 10 Hz); (3) label decisions: at each frame where `ON_BALL` changes holder within the same team → `pass` to the new holder; holder displacement > 2 m over the next 1 s with ball → `carry` with direction quantised to 8 bins; ball speed > 15 m/s from the holder toward the goal within 1 s → `shoot`; ball travels > 25 m away from own goal under pressure → `clear`; else `hold`; (4) for Kickoff matches, labels come straight from events; (5) features per token: x, y, vx, vy, team flag, is_holder, role one-hot (8), stamina, distance to ball, angle to goal (F = 16); global token: score diff, clock fraction, period, possession team (G = 4); (6) split by `GAME_ID` 80/10/10 with `split_seed = 4242`; write `train.npz`, `val.npz`, `test.npz` and `dataset_report.json` (counts per class, games per split, coordinate sanity plots).

**Model.** Set transformer: input linear F→256, 6 encoder layers (d = 256, 8 heads, FFN 1024, no positional encoding; player identity is in the features), a global token; heads: kind (5 classes), pass target as a pointer over the 10 teammate tokens (masked for non-teammates), carry direction (8). ≈ 4.9M parameters (measured 4.7M for the encoder + head in the spike). Loss: CE(kind) + CE(pass target, only on pass samples) + CE(carry dir, only on carry samples).

**Training.** AdamW lr 3e-4, cosine decay, 1,000-step warm-up, batch 256, label smoothing 0.05, 8 epochs over ≈ 6M samples. Measured 2,474 samples/s on MPS → 0.7 h per epoch → ≈ 5.6 h. Checkpoint every epoch to `artifacts/policy_v1_epN.pt`; keep best by validation loss. One night.

**Evaluation and gates** (`policy/evaluate.py`, 20 rollouts of 8 s on held-out states):

| Metric | Pass threshold | Baseline |
|---|---|---|
| Top-1 kind accuracy (test) | ≥ 0.45 | majority class |
| Top-3 (kind + target) accuracy | ≥ 0.80 | "pass to nearest free teammate" heuristic |
| 4 s ball FDE on rollouts | ≤ velocity-extrapolation baseline | |
| Teleport count (player speed > 12 m/s) | 0 | |
| Shape-collapse rate (team hull area falls > 50% within 8 s) | ≤ 5% of rollouts | |
| Offside violations per rollout | ≤ 0.2 | |

Thresholds are estimates to be confirmed on the first run; they are recorded in `metrics.json` and enforced by `rollout` at load. **Fallback decision:** if any gate fails by the end of day 4, `scripted_v1` remains the engine for every cached counterfactual in the video, and the policy ships as a documented experiment with its metrics.

### Outcome heads

| Head | Features | Model | Data | Time | Check |
|---|---|---|---|---|---|
| xG | distance, angle, body part, defenders in cone, keeper distance to line, under_pressure, pitch control at shot location | LightGBM | ≈ 60k shots from 2,000 Kickoff matches | minutes | reliability diagram, ECE ≤ 0.03 |
| Pass completion | length, angle, height, pressure, receiver space (pitch control at target), progressive, opponents in lane | LightGBM | ≈ 2M passes | minutes | ECE ≤ 0.03 |
| Win probability | score diff, minute, period, red-card diff, xT diff last 15 min, chaos | LightGBM multiclass | states every 30 s from 2,000 matches, labelled by result | minutes | ECE ≤ 0.03; monotonic in score diff |
| Goal in 8 s | ball x,y, possession team, pitch-control summary (attacking third share), players in box, ball speed, holder angle | LightGBM | ≈ 2M states, base rate ≈ 1–2% | minutes | ECE ≤ 0.01 (rare event); PR-AUC reported |
| Chaos head | 12 features (contested share, turnovers 60 s, transition share, mean closing speed, tempo) | logistic | 2M states, label = possession change within 10 s | minutes | AUC ≥ 0.70 |
| Moment encoder | pitch-control grid downsampled to 21×14 + the 12 features → 64-d | autoencoder | 2M states | 20 min on MPS | k-means k = 6; cluster purity vs hidden phases ≥ 0.6; clusters named once by `cluster_namer` |

---

## 1.7 Agent and workflow specification

### Workflow graph (one run per moment)

```
IngestExecutor (start)
  └─▶ ScoutExecutor (code)  ── switch-case ──┬─ is_fast        ─▶ FastLineExecutor (Haiku)  ─▶ FactCheckExecutor ─▶ DirectorExecutor ─▶ CueBus
                                             ├─ is_explained   ─▶ ProposerExecutor (Sonnet) ─▶ RolloutExecutor (code, MCP) ─▶ TacticianExecutor (Sonnet/Opus, tools) ─▶ NarratorExecutor (Haiku) ─▶ FactCheckExecutor ─┬─ verified or attempt≥3 ─▶ DirectorExecutor
                                             │                                                                                                                         └─ rejected & attempt<3 ─▶ NarratorExecutor (with diff)
                                             ├─ is_panel       ─▶ PanelExecutor (GroupChat: 3 pundits + chair) ─▶ FactCheckExecutor ─▶ DirectorExecutor
                                             ├─ is_referee     ─▶ FourthOfficialExecutor (code) ─▶ DirectorExecutor
                                             ├─ is_recap       ─▶ RecapExecutor (Opus/Sonnet) ─▶ FactCheckExecutor ─▶ DirectorExecutor ──request_info──▶ producer ──response──▶ CueBus
                                             └─ default        ─▶ DropExecutor
```

Built with (verified names): `WorkflowBuilder(start_executor=ingest, checkpoint_storage=storage, name="newsroom")`, `add_edge`, `add_switch_case_edge_group(scout, [Case(condition=is_fast, target=fast_line), Case(condition=is_explained, target=proposer), Case(condition=is_panel, target=panel), Case(condition=is_referee, target=fourth_official), Case(condition=is_recap, target=recap), Default(target=drop)])`, `add_edge(factcheck, narrator, condition=lambda m: not m.verified and m.attempt < 3)`, `add_edge(factcheck, director, condition=lambda m: m.verified or m.attempt >= 3)`. Classification rules: `is_fast` = goal, big_chance (xG ≥ 0.3), milestone, player_tag threshold; `is_explained` = leverage ≥ 0.04 (from the goal-in-8-s head swing) or state change; `is_panel` = leverage ≥ 0.06 and `panel.enabled`; `is_referee` = offside/foul/card events; `is_recap` = period_end. A moment can take several branches (fan-out via multiple `Case` matches is not supported; the Scout emits one message per branch instead).

### Agents

| Agent | Executor | Model (config role) | Prompt file | Tools | Output schema | Timeout | Retry | Fallback |
|---|---|---|---|---|---|---|---|---|
| Scout | code | — | — | — | Moment | 50 ms | — | — |
| Proposer | LLM | `proposer` (Sonnet, low) | `prompts/proposer@1.md` | none | `{alternatives:[{kind,actor,target,reason}]}` (≤ 3) | 6 s | 1 | rule: top-3 teammates by xT gain |
| Rollout | code | — | — | MCP `simulate_counterfactual` per alternative; keeps the alternative with the largest |Δ| whose `policy_prob ≥ 0.05` | CounterfactualResult | 2 s local / 5 s Azure | — | n=50 |
| Tactician | LLM | `tactician_live` (Sonnet, medium) / `tactician_golden` (Opus, high, batch) | `prompts/tactician@3.md` | live: `query_events, get_pitch_control, simulate_counterfactual, player_stats, similar_moments` (MCP). Golden (Batch): the Batch API cannot run tool rounds, so `scripts/precompute.py` calls the same five tools itself and inlines their results in the prompt (`max_tool_rounds: 0`) | `explanation.schema.json` via structured output | 12 s | 1 | `tactician_degraded` template from the counterfactual numbers |
| Narrator | LLM | `narrator_fast` (Haiku, low) | `prompts/narrator@2.md` + `fewshot/narrator.jsonl` | none | `{headline, body, claims[]}` | 4 s | 1 | template; Gemini 3.8 Flash as provider fallback |
| Fact Checker | code | — | — | MCP `verify_claims` (same code) | Explanation with `verified` per claim + `diff` | 50 ms | — | — |
| Panel | GroupChat | `panel_pundit` ×3, `panel_chair` | `prompts/pundit_press@1.md`, `pundit_possession@1.md`, `pundit_sceptic@1.md`, `chair@1.md` | pundits: `simulate_counterfactual, get_pitch_control` | `{take, claims[], stance}`; chair `{consensus, dissent, headline}` | 25 s total | 0 | drop the panel cue |
| Fourth Official | code | — | `rules.yaml` | — | Cue (referee_line) | 5 ms | — | — |
| Recap | LLM | `recap` (Opus, batch) / `recap_live` (Sonnet) | `prompts/recap@2.md` | MCP `top_moments, timeline` | recap_card list | 90 s | 1 | template recap |
| Director | code (+ `panel_chair` model for headline tie-breaks only) | — | — | `get_budget` | Cue | 50 ms | — | — |
| Judge | LLM, CI only | `judge` (Sonnet) | `prompts/judge@1.md` | — | `{plausible, reason}` | — | — | — |

Panel orchestration uses `agent-framework-orchestrations` `GroupChatBuilder` with the chair as manager and a fixed three-round limit; it runs as a sub-workflow inside `PanelExecutor`.

### Fact Checker rules (deterministic, `newsroom/factcheck.py`)

1. Every `claim.evidence_ids` must resolve in the blackboard (event, counterfactual, fact, pitch-control snapshot).
2. `kind=number`: the value must match the evidence within tolerance: xG ±0.005; probabilities and percentages ±0.01 (±1 point); distances ±0.5 m; speeds ±1 km/h; minutes ±1; `win_prob_delta` must equal the counterfactual's `delta_win_prob_home` ±0.01.
3. `kind=player` / `team`: must exist in the match lineups and appear in at least one cited evidence event (player) or be one of the two clubs (team).
4. `kind=minute`: within ±1 of any cited evidence `t_ms`.
5. `kind=tactical`: must cite a `pc_` snapshot or `f_` fact whose `zones` or cluster label contains the claimed pattern (`overload_right`, `high_press`, …).
6. Every number appearing in `why`, `headline` or `body` (regex for digits, percent, decimals) must appear as the `text` of a verified claim; otherwise reject with `unbound_number`.
7. Banned content: injury speculation, referee-bias accusations, betting language ("odds", "bet"), any real club, league, player or broadcaster name from `data/league/banned_names.txt`.
8. On rejection: return `verified=false`, per-claim `reject_reason`, and a `diff` list the Narrator receives; after the third attempt the Director uses the template line built from verified claims only.

### Director budgets

From `config/budgets.yaml`: per-mode `min_gap_s`, `max_per_10min`, allowed kinds, heatmap default; hard rules: no overlay during an active shot sequence (shot event until the ball is dead, max 6 s), none within 3 s after a goal, dedupe the same kind within 90 s, expire unshown cues after 45 s, Sliding Doors only for leverage ≥ 0.04, Oracle only when `p_shot ≥ 0.30`.

### Producer veto (human-in-the-loop, verified API)

In `DirectorExecutor.handle_recap`:

```python
@handler
async def handle_recap(self, cue: Cue, ctx: WorkflowContext[Cue]) -> None:
    await ctx.request_info(request_data=ProducerApproval(cue=cue), response_type=ProducerDecision)

@response_handler
async def on_decision(self, original_request: ProducerApproval, response: ProducerDecision, ctx: WorkflowContext[Cue]) -> None:
    cue = original_request.cue.model_copy(update={"producer_status": response.status})
    if response.status != "vetoed":
        await ctx.send_message(cue)
```

The worker collects workflow events with `event.type == "request_info"`, publishes `{request_id, cue}` to the studio over the WebSocket, and resumes with `workflow.run(stream=True, responses={request_id: ProducerDecision(status=...)}, checkpoint_id=..., checkpoint_storage=storage)`. Non-recap cues are auto-approved; the studio can still veto a shown cue, which emits `cue_remove`.

### Checkpoints, resume and the kill-switch demo

Storage: `FileCheckpointStorage(WHYLINE_CHECKPOINT_DIR)` locally, `CosmosCheckpointStorage(endpoint=..., credential=DefaultAzureCredential(), database_name=..., container_name=...)` in Azure. Every executor that holds in-flight data implements `on_checkpoint_save` / `on_checkpoint_restore`. Checkpoints are written at superstep boundaries by the framework.

Kill-switch procedure (demo script at 44:10 of the golden match): (1) the API receives `POST /demo/kill {target: newsroom}` and sends SIGKILL to the worker while a Sliding Doors run is between `TacticianExecutor` and `NarratorExecutor`; (2) the studio shows the trace row for that run as `interrupted` and the mode badge as `degraded` for the gap; (3) the supervisor (`newsroom/supervisor.py`) restarts the worker within 2 s; (4) on start the worker calls `storage.list_checkpoints(workflow_name="newsroom")`, finds runs without a terminal cue, and resumes each with `workflow.run(checkpoint_id=cp.checkpoint_id, checkpoint_storage=storage, stream=True)`; (5) the resumed run completes and the cue arrives with `provenance.resumed_from_checkpoint = <checkpoint_id>`. The log must show, in order: `kill target=newsroom run_id=… at_executor=tactician`, `restart pid=…`, `resume run_id=… checkpoint_id=…`, `cue c_… delivered resumed_from_checkpoint=…`. The same sequence runs in CI (`tests/chaos/test_resume.py`) with the in-memory engine.

### MCP tool list (`packages/mcp_server/server.py`)

```python
@mcp.tool() def query_events(match_id: str, t_from_ms: int, t_to_ms: int, kinds: list[str] | None = None, player: str | None = None) -> list[dict]
@mcp.tool() def get_state(match_id: str, t_ms: int) -> dict               # score, clock, possession, state label, indices
@mcp.tool() def get_pitch_control(match_id: str, t_ms: int) -> dict       # snapshot_id, home_share, contested_frac, zones, top-3 overloads
@mcp.tool() def simulate_counterfactual(match_id: str, t_ms: int, alternative: dict, n: int = 200, horizon_s: float = 8) -> dict   # counterfactual.schema.json
@mcp.tool() def player_stats(match_id: str, player_id: str) -> dict       # touches, passes, completion, xT, sprints, decision_index
@mcp.tool() def similar_moments(match_id: str, t_ms: int, k: int = 3) -> list[dict]   # moment-encoder nearest neighbours (golden season)
@mcp.tool() def verify_claims(match_id: str, claims: list[dict]) -> dict  # Fact Checker
@mcp.tool() def top_moments(match_id: str, period: int | None = None, k: int = 5) -> list[dict]
@mcp.tool() def timeline(match_id: str) -> dict                           # chaos, control, xT series at 30 s
@mcp.tool() def get_budget(mode: str) -> dict
```

Agents attach the server with `MCPStreamableHTTPTool(name="whyline", url="http://localhost:8080/mcp")` (core 1.22.0).

### Prompt versioning and few-shots

Prompts live in `packages/newsroom/prompts/<agent>@<n>.md`; the version string is embedded in every output and every cache key. Few-shot examples live in `prompts/fewshot/<agent>.jsonl`. Mechanism: `scripts/precompute.py --hand-review 20` exports the twenty highest-leverage moments' explanations and lines to `review/*.md`; Claude Code (in a development session) edits them; `scripts/import_review.py` writes the edited versions back as cache entries flagged `hand_reviewed: true` and appends them to the few-shot files; the prompt version is bumped; the remaining moments are regenerated with the new few-shots.

---

## 1.8 Replay-from-cache and live mode

**Golden match.** `python -m kickoff play --seed 4242 --league data/league --out data/matches/4242`. CI asserts that two runs produce byte-identical `events.jsonl` and `tracking.npz`. Note: `numpy.savez_compressed` stamps the current time into the zip members, so the writer must emit the archive with fixed zip timestamps (T-007) or the hash will never match. SHA-256 of both files go into `manifest.json`; `engine_hash` is the git SHA. The pre-commit secret hook matches full key-shaped strings, not the bare `sk-ant-` / `AIza` prefixes, which appear in this document.

**Precompute** (`scripts/precompute.py --seed 4242 --mode batch`): (1) analytics for every frame → `cache/analytics/*.npz`, pitch-control snapshots for every moment → `cache/pitch_control/pc_*.npz`; (2) Scout moments → `cache/moments.jsonl`; (3) rollouts for every explained moment (and every on-ball decision for the Decision Index) → `cache/counterfactuals/cf_*.json`; (4) model calls built as Anthropic Batch API requests keyed by cache key, with every tool result the Tactician would have fetched (counterfactual, pitch control, player stats, similar moments) pre-resolved by the script and inlined in the prompt, submitted with `client.messages.batches.create(requests=[...])`, polled until `ended`, results keyed by `custom_id` (never by position); (5) Fact Checker over every output; rejected outputs re-queued with the diff (max two rewrites); (6) hand-review export and import (1.7); (7) `manifest.json` written with hashes, latencies (the measured live latency of the same call, or the Batch-estimated 4–8 s for Opus), tokens and costs. Everything is keyed `<match_id>/<moment_id>/<producer>@<version>/<model>/s<seed>`.

**Replay serving.** `CacheClient.complete(role, messages, tools)` computes the key from the role's prompt version and the moment, looks it up, sleeps `simulated_latency_ms × (1 / WHYLINE_REPLAY_SPEED)`, and returns the stored output. A miss in replay mode raises `CacheMiss`, which the Director turns into a template line and a red "cache miss" trace row (so a miss is visible in rehearsal, never silent). The trace panel therefore animates with real timings.

**Demo script** (`demo/demo_script.yaml`): `[{at_clock: "44:10", action: kill, target: newsroom}, {at_clock: "45:00+15s", action: veto, cue_kind: recap}, {at_clock: "31:10", action: speed, value: 1}, {at_clock: "33:00", action: speed, value: 10}]`. The API applies them on the replay clock.

**Live mode.** `WHYLINE_MODE=live` injects `LiveClient` (Anthropic SDK via `agent-framework-anthropic`, Gemini via `agent-framework-gemini`) and `LiveRollout`; identical graph, prompts and screens. `SpendGuard` prices every call and appends to the ledger; at the per-match or per-day cap the mode becomes `degraded`: Haiku and Sonnet calls are replaced by templates, the badge turns amber, and the ledger records the switch.

**Freeze rule.** After day 7, `manifest.frozen = true`. CI job `frozen-cache-guard` fails if `manifest.json`'s hashes differ from the committed ones unless `docs/video/VERSION` was bumped in the same commit.

---

## 1.9 Screens

### WebSocket messages (`/ws`, JSON, one per line)

| type | payload | consumer |
|---|---|---|
| `hello` | `{match_id, mode, replay_speed, viewer_profile}` | all |
| `tracking_frame` | 10 Hz, 1.3 above | overlay, fan, replay3d |
| `event` | event schema | studio, overlay (score bug) |
| `fact` | fact doc (indices every 1 s, state changes) | overlay chaos meter, studio |
| `moment` | moment doc | studio queue |
| `cue` | cue schema | all (filtered by targets server-side) |
| `cue_remove` | `{cue_id}` | all |
| `trace` | trace doc | studio |
| `request_info` | `{request_id, cue}` | studio |
| `mode` | `{mode: replay|live|degraded, reason}` | all |
| `spend` | `{match_usd, day_usd, caps}` | studio |
| `oracle` | `{t_ms, p_shot_home, p_shot_away, zone, shooter}` every 2 s | overlay threat front |

### Overlay (`apps/overlay`, 1920×1080, transparent body)

Component tree: `App → StreamProvider → Pitch2D (canvas: pitch, players with numbers, ball, heatmap layer, threat front, ghost trail, referee lines) → ScoreBug → ChaosMeter → SwingBar → LowerThird → PlayerTags → Ticker`. State: `{frame, cues[], facts, oracle, profile}` in a reducer; cues enter and leave on `t_in_ms/t_out_ms` against the stream clock. Viewer modes: analyst shows heatmap + threat front + all layers; casual hides heatmap, ticker and shows only its allowed kinds; player_cam draws the player trail and shows player tags. Route `/replay3d?cf=cf_000077`: R3F scene with a stadium bowl, pitch plane, capsule players in kit colours with number sprites, ball, two cameras (broadcast wide, behind-the-player), the 200 ghost ball paths as translucent lines coloured by branch, the chosen alternative as an orange dashed trail, and the swing bar as a DOM overlay. Recording: `?record=1` disables the cursor, fixes DPR = 1, and exposes `window.__whyline.seek(clock)`.

### Studio console (`apps/studio`)

`App → StreamProvider → Header(mode badge, spend) → MomentQueue → AgentTrace (rows per run: executor, model, latency, tokens, cache_hit, status; red for cache miss or interrupted) → CueList (verified flag, producer_status, Why? drawer: claims with evidence, pitch-control snapshot thumbnail, counterfactual mini-chart) → ProducerPanel (approve/veto on request_info; veto on any shown cue) → DemoControls (kill newsroom, speed, seek) → Blackboard (facts, state)`. Studio receives every cue regardless of mode.

### Fan app (`apps/fan`)

Phone-shaped: `ProfilePicker (mode, club, player, metric) → MiniPitch → CueFeed → PlayerCamCard (distance, top speed, sprints, touches, Decision Index) → MomentCards`. Same stream, server-side filtered by profile.

### Recording (`demo/record_demo.py`, Playwright)

Responsibilities: launch Chromium 1920×1080 DPR 1 with `record_video_dir`; open each app with `?record=1&viewer=<profile>`; set replay speed per segment from `demo/shot_list.yaml` (clock in, clock out, app, viewer, speed); wait for `window.__whyline.ready`; seek; record; export PNG keyframes at listed clocks; write `demo/out/<shot>.webm` and `<shot>_<clock>.png`. The video editor assembles shots in a free editor; no third-party media.

---

## 1.10 Infrastructure and operations

### Local

`docker-compose.yml`: services `api` (:8000), `mcp` (:8080), `newsroom` (supervisor + worker), `overlay` (:5173), `studio` (:5174), `fan` (:5175); volumes `./data`, `./.checkpoints`; `.env` passed through. `make demo` = `docker compose up` + `python -m api.replay --seed 4242`.

### Azure (free account)

| Service | Tier | Role | Idle cost | Judging cost (2 weeks) |
|---|---|---|---|---|
| Static Web Apps ×3 | Free | overlay, studio, fan | $0 | $0 |
| Container Apps (api, mcp, newsroom) | Consumption, scale to zero | free grant 180k vCPU-s + 360k GiB-s + 2M requests/month | $0 | ≈ $0–5 (estimate) |
| Cosmos DB NoSQL | Free tier 1,000 RU/s + 25 GB | blackboard, checkpoints | $0 | $0 |
| Web PubSub | Free: 20 connections, 20k messages/day | cue stream only (≈ 200 cues per match); tracking frames and facts stay on the api container's own WebSocket | $0 | $0 (a judge session is under 20 clients and far under 20k cues/day) |
| Application Insights + Log Analytics | free 5 GB/month ingestion | traces | $0 | $0 |
| Key Vault | Standard | API keys | ≈ $0 | ≈ $0 |
| Event Hubs | Basic, 1 TU | engine → api in Azure | $0.015/h ≈ $11/month | ≈ $5, from trial credit; optional (direct POST ingest is the default) |

All within the $200 trial credit; the project ledger counts Azure at $0.

Bicep modules (`infra/`): `main.bicep`, `modules/monitoring.bicep`, `modules/cosmos.bicep`, `modules/webpubsub.bicep`, `modules/aca-env.bicep`, `modules/aca-app.bicep` (×3), `modules/swa.bicep` (×3), `modules/keyvault.bicep`, `modules/eventhubs.bicep` (optional). `azure.yaml` declares services `api`, `mcp`, `newsroom` (containerapp) and `overlay`, `studio`, `fan` (staticwebapp). `azd 1.36.0`.

Secrets: local `.env` (git-ignored; `config/.env.example` lists names); Azure Key Vault references in Container Apps; Entra managed identity for Cosmos and Web PubSub; keys are never written to the repo or logs (a pre-commit hook greps for `sk-ant-` and `AIza`).

CI (`.github/workflows/ci.yml`): `lint` (ruff), `unit` (pytest), `schemas` (validate all examples and fixtures), `golden-determinism` (generate seed 4242 twice, compare hashes; replay the cue stream and compare to `tests/golden/cues.sha256`), `evals-gate` (thresholds from 1.11 on the committed artefacts), `licence-scan` (pip-licenses against the allow-list in `config/pins.txt`), `spend-ledger` (sum ≤ $50; per-match ≤ $2.50), `frozen-cache-guard`, `chaos-resume`.

Observability: OpenTelemetry (`opentelemetry-api 1.45.1`, exporter pin at T-001) spans `whyline.moment{moment_id, leverage, branch}`, `whyline.agent.<name>{model, prompt_version, tokens_in, tokens_out, cost_usd, cache_hit, latency_ms}`, `whyline.rollout{engine, n, horizon_s, ms}`, `whyline.cue{cue_id, mode, verified}`; console exporter locally, Azure Monitor exporter in Azure.

Spend guard: `api/spend.py` prices every call from `config/budgets.yaml`, appends `{ts, role, model, tokens_in, tokens_out, cost_usd, match_id, mode}` to `data/spend/ledger.jsonl`, exposes `GET /spend`, and raises `SpendCapReached` which the Director catches to switch mode.

---

## 1.11 Evaluation harness

`python evals/run_evals.py --seeds 1..50 --out evals/results.md`.

| Number | Script | Data | Pass threshold |
|---|---|---|---|
| State-detection precision/recall/F1 vs hidden truth | `evals/state_detection.py` | 50 Kickoff matches | F1 ≥ 0.75 |
| Counterfactual calibration (Brier, reliability diagram) | `evals/calibration.py` | 300 held-out matches, every explained moment, unforced branch vs realised outcome | Brier ≤ 0.18 (base rate ≈ 0.05); placebo test passes (forcing the actual action reproduces the baseline within CI) |
| Policy metrics | `policy/evaluate.py` | test split + 20 rollouts | table in 1.6 |
| Fact Checker planted errors caught | `evals/planted_errors.py` | 500 outputs with one injected error each: wrong number (±10%), wrong player, wrong minute, unbound number, banned word | 100% caught |
| Fact Checker false rejects | same | 500 golden verified outputs | ≤ 2% |
| Cue latency p50/p95 (live) | `evals/latency.py` from traces | 3 live matches | fast ≤ 3 s p95; explained ≤ 15 s p95 |
| Cost per match | ledger | same 3 matches | ≤ $2.50 |
| Groundedness | `evals/groundedness.py` (own evaluator: share of numbers bound to verified claims) and, if accessible on the free account, Foundry Evaluations `GroundednessEvaluator` from `azure-ai-evaluation 1.18.9` | 500 cues | ≥ 0.95 |
| Realism | `evals/realism.py` | Kickoff vs SkillCorner/DFL marginals (speeds, pass lengths, completion by distance) | plots published; no threshold |
| Resume | `tests/chaos/test_resume.py` | 20 runs | 0 cues lost |

Planted-error design: each injection is applied to a copy of a verified explanation; the test records which rule caught it; a catch-rate table per rule is published.

---

## 1.12 Rules compliance checklist

| Rule (OFFICIAL RULES.md) | Artefact that proves it |
|---|---|
| Synthetic, football-realistic data only (4.7) | `data/league/` fictional clubs and players; `evals/realism.md`; README statement; real datasets used for validation only (`docs/DATA.md`) |
| Third-party integrations licensed (4.3) | `config/pins.txt` with licences; `licence-scan` CI job output |
| New project after 29 Sep 2026 (4.3) | first commit date in the public repo |
| Public GitHub repository (4.4) | repo URL in the submission |
| Video under two minutes, shows the project functioning, no third-party marks or music (4.4) | `demo/out/final.mp4` 1:55; Lyria track; `docs/video/VERSION` |
| Project pitch naming Microsoft technologies (4.4) | README "Pitch" section |
| Judges can test (4.8) | hosted URL + `docs/JUDGES.md` with one-command replay on a laptop |
| Multiple submissions substantially different (4.5) | not applicable (one submission) |
| Category adherence: Multi-Agent (4.2) | `docs/architecture.md` with the workflow graph, checkpoint resume log, A2A note |
| No obscene, political, trademark content (4.4) | `data/league/banned_names.txt` and the Fact Checker banned-content rule |

---

## 1.13 Risk register

| Risk | Owner | Early-warning signal | Trigger date | Pre-decided response |
|---|---|---|---|---|
| Policy futures unconvincing | A | day-4 clip review: teleports, bunching, keeper frozen | 24 Oct | ship scripted_v1 in every cached counterfactual; policy as experiment |
| Explained-cue latency > 15 s live | B | first live run p95 | 25 Oct | Tactician `max_tool_rounds` 1; Panel near-line only |
| Claude refusal or outage during a judge run | B | fallback usage in ledger | ongoing | server-side fallback; template path; degraded badge |
| Gemini free-tier limits | B | 429s in logs | 23 Oct | paid tier (cents) or drop the adapter |
| Spend creep | B | ledger > 80% of a cap | ongoing | caps enforced in code; precompute via Batch only |
| Deadline is 27 Oct | all | Projects page countdown | 21 Oct | day-7 tag is the submission |
| gfootball temptation | A | any ticket referencing it | — | not a dependency; rejected at review |
| `grf_tracking_data` licence unresolved | A | no reply from authors by day 10 | 31 Oct | publish policy weights trained on Kickoff only; keep GRF-trained weights private |
| 3D scene late | C | not rendering a frame by day 5 | 25 Oct | video uses the 2.5D ghost trail; 3D cut |
| Web PubSub 20-connection cap | B | judge session > 20 clients | judging | SSE fallback from api; document |
| Cache miss during recording | C | red trace row in rehearsal | day 6 | fix precompute; never record with a miss |

---

## 1.14 Disagreements and open questions

Disagreements with the frozen plan (planned around, not changed):

1. The $50 plan's video line "ninety-seven percent grounded, measured in Foundry" depends on Foundry Evaluations being usable on a free account; the audit marked custom evaluators as preview and did not verify free-account access. The plan computes groundedness with its own evaluator and uses Foundry only if it works; the video caption should say "measured" without naming Foundry unless it does.
2. Running the Oracle every 2 s with 200 rollouts is too heavy for live CPU mode. Replay uses 2 s / n=200; live uses 5 s / n=50.
3. The Decision Index needs a rollout at every on-ball decision (≈ 1,500 per match). It is precomputed for the golden match only; live mode approximates it with the goal-in-8-s head swing.
4. The Panel adds 10–25 s; it is a near-line feature, never on the fast path, and the video shows it on a replayed moment.

Open questions only the user can answer:

1. The real submission deadline (27 October per the rules file, 21 November per the site banner).
2. Team size and whether anyone is comfortable in React-Three-Fiber (decides the 3D scene).
3. Whether the Gemini free tier's limits suffice (visible only in AI Studio for the key's project).
4. Whether the hackathon's "rendering partner" overlay specification is available behind the login; if so, `cue.schema.json` gains an adapter.
5. Azure subscription type (trial or pay-as-you-go); it does not affect this plan because Claude is called directly, but it decides whether Foundry Evaluations can be shown.
