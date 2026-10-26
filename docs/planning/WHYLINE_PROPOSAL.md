# WHYLINE — Winning Proposal for "Inside the Game: Developer Hackathon"

> **Every line on screen has a why.**
> A counterfactual match-intelligence engine run by an AI newsroom, delivered as broadcast-ready overlays and personalised for every fan in every language.

Prepared 20 October 2026. Submission deadline: **27 October 2026, 11:59 pm PT** (seven build days). Judging: 27 Oct – 10 Nov. Winners by 20 Nov.

---

## 0. Read this first: the strategic situation

| Fact | Consequence |
|---|---|
| 433 projects already created, 1,652 registrants | The field is crowded. Generic "events → LLM commentary → overlay" will not place. |
| Registration closed today; submission in 7 days | Scope must be ruthless. Everything below is sequenced for a 7-day build with 2–4 people using Claude Code and GitHub Copilot Agent Mode as force multipliers. |
| Five equally weighted criteria (Tech Implementation, Agentic Design, Real-World Impact, UX/Presentation, Category Adherence) | A project that is merely "complete" scores ~60%. The winner needs one unforgettable idea plus visible polish on every axis. |
| Grand Prize + one Category Prize max per project | Declare **Best Multi-Agent System** as the category (judges can reassign). Design to also be the obvious pick for Azure Cloud Native and Foundry. |
| Rules: synthetic data only, no trademarks, no copyrighted music, public GitHub repo, <2-min video, judges may test | Fictional clubs and players, generated music/none, public repo from day 1, deployed URL plus a zero-Azure replay mode for judges. |

### What the competition is building (verified from public repos)

I read four public entries ([matchroom](https://github.com/saisyalla96/matchroom), [livedesk](https://github.com/fahad-workspace/livedesk), [matchday-crew](https://github.com/timsheldon1/matchday-crew), [the-ninety-labs](https://github.com/KLKH7/the-ninety-labs)). They have converged on the same shape:

- Seeded synthetic match generator → deterministic stats engine → LLM Narrator → Fact Verifier → Localizer → SSE/React studio UI with timed JSON cues.
- Foundry Agent Service prompt agents, Azure Container Apps, managed identity, App Insights tracing, `azd up`.
- Momentum/pressure detection from events only. Reported accuracy is weak (one reports 53% precision on pressure surges; another r = 0.48 momentum correlation).
- Explanations are "here is the evidence" (event IDs), not "here is why it changed the match".
- Player positions are modelled from the ball, not simulated. Pitch views look fake.
- One team attempts computer vision on rendered footage and is clearly not finishing it.

**Implication:** the baseline (verifier, Foundry agents, ACA, timed cues) is now table stakes. We must ship all of it *and* add things nobody else has.

### The three things nobody else has

1. **Pitch Physics.** A real 22-player tracking simulation at 10 Hz and a Spearman-style **pitch-control field** computed live. "Control vs chaos" stops being a vibe and becomes a measured, visualised quantity: the entropy of who owns the pitch.
2. **The Sliding Doors Engine.** Because we own the simulator, every key moment is explained by **counterfactual re-simulation**: "Had Okafor squared it to Reyes (0.31 xG, unmarked) instead of shooting (0.06 xG), home win probability rises 9 points." Importance = win-probability swing, not xG alone. No other entry can do this because none of them has a physics engine that can branch.
3. **A Director agent with an attention budget.** The newsroom doesn't just generate text; a Director decides *what each viewer sees and when*, with screen-time budgets per persona, hard rules (never during a shot sequence), and leverage-based triage. That is the difference between a feed and a broadcast.

---

## 1. Executive summary and value proposition

### The problem

Football broadcasting has a data problem and an audience problem at the same time.

- **Fans are drowning in data, starved of wisdom.** Writers across the analytics community make the same complaint: xG appears on screen "without commentary" and feels soulless; fans are "bombarded by new metrics every week without the context to use them" ([xGuff](https://xguff.substack.com/p/football-fans-are-drowning-in-data), [Pulse9](https://pulse9post.substack.com/p/bridging-the-gap-between-the-fan)). Pundits and even players dismiss it; Morgan Rogers called xG "a whole load of nonsense" this year ([AOL](https://www.aol.com/articles/morgan-rogers-makes-divisive-xg-140444092.html)).
- **Broadcasters are bottlenecked on data integrity and latency.** Automated graphics (Viz Mosart at Sky, Viaplay) work only when "high-integrity data at the lowest possible latency" is available, and a mismatch between live action and on-screen data "immediately breaks viewer trust" ([SVG Europe](https://www.svgeurope.org/blog/headlines/automatic-for-the-people-live-graphics-evolve-to-transform-real-time-sports-storytelling/), [WASP3D](https://wasp3d.com/blogs/integrating-live-data-stats-into-sports-graphics-a-complete-guide/)).
- **One feed, one story, one language.** Premier League Productions distributes to hundreds of markets; personalisation today is a "Data Zone" toggle ([SportBusiness](https://www.sportbusiness.com/news/genius-sports-plp-roll-out-premier-league-data-zone-worldwide/)). A casual fan in Jakarta and an analyst in Manchester get the same lower-third.

### The breakthrough

WHYLINE turns a live stream of synthetic match events and tracking into **explained, verified, personalised intelligence** in under five seconds, using three ideas:

1. **Measure control, not possession.** Pitch control (space ownership), pressure, tempo and turnover rate produce a live **Control/Chaos state machine** (Settled → Transitional → Chaotic) with hysteresis, so the system can say "the game has been chaotic for 4 minutes and here is why" and prove it with a heatmap.
2. **Explain with counterfactuals.** The Sliding Doors Engine branches the simulation at any moment, rolls 200 futures per branch in under a second, and reports the swing in win probability. Judges have never seen a football AI that answers "what if?" with numbers.
3. **Broadcast it with an AI newsroom.** Seven specialised agents (Scout, Tactician, Narrator, Fact Checker, Localizer, Director, Recap Editor) coordinate over a shared Match Blackboard using Microsoft Agent Framework workflows with Cosmos DB checkpoints. Every cue carries evidence IDs, a verification flag, a trace ID and a counterfactual, and can be vetoed by a human producer.

### Why it scores across all five criteria

| Criterion (20% each) | How WHYLINE wins it |
|---|---|
| **Technological Implementation** | Optimised synthetic data: batch-vectorised 22-player engine with hidden tactical truth, LLM-authored fictional league, published realism calibration. Hero tech used *structurally*: Agent Framework workflows, Foundry Agent Service + Evaluations + Tracing, Azure MCP Server (dev), our own MCP server (runtime), Copilot Agent Mode custom agents, Container Apps, Event Hubs, Cosmos DB, Web PubSub, Functions, Speech. Bicep + azd, tests, CI. |
| **Agentic Design & Innovation** | Distinct roles with real handoffs, fan-out/fan-in, a rewrite loop, a Director that makes editorial decisions, checkpoint-resume after a killed agent (demoed live), MCP tools as the only way agents touch data. Counterfactual tool use is novel. |
| **Real-World Impact** | Solves the stated broadcaster problem (verified, timed, machine-readable cues) and the fan problem (made-for-me). Enterprise controls: producer veto, audit trail, content safety, managed identity, cost guard, evaluation dashboards. Clear path to PLP/OTT adoption. |
| **UX & Presentation** | Three front-ends: a keyed 1920×1080 **Broadcast Overlay** (drop into OBS/Vizrt as a browser source), a **Studio Console** for producers, a **Fan App** second screen. 2.5D pitch render with live pitch-control heatmap. Video storyboard in §7. |
| **Category Adherence** | Multi-Agent: "distinct roles, shared state, effective handoffs, recover from failures, outcome a single agent could not achieve" is literally our architecture. Also fully satisfies Azure Cloud Native and Foundry category text. |

---

## 2. End-to-end five-stage architecture

```
            ┌──────────────────────────────────────────────────────────────────────────┐
            │                            AZURE CONTAINER APPS                          │
            │                                                                          │
 ┌────────┐ │ ┌──────────┐   ┌───────────────┐   ┌──────────────────┐   ┌───────────┐ │   ┌────────────┐
 │Kickoff │─┼▶│ Event    │──▶│ Pitch Physics │──▶│  The Newsroom    │──▶│ Cue Bus   │─┼──▶│ Web PubSub │──▶ Broadcast Overlay
 │ engine │ │ │ Hubs     │   │ (analytics)   │   │ (Agent Framework │   │ (Director │ │   │            │──▶ Studio Console
 │ (sim)  │ │ │ ingest   │   │ 10 Hz         │   │  workflow)       │   │  output)  │ │   │            │──▶ Fan App
 └────────┘ │ └──────────┘   └───────┬───────┘   └────────┬─────────┘   └───────────┘ │   └────────────┘
     ▲      │                        │                    │                           │
     │      │                 ┌──────▼──────┐     ┌───────▼────────┐                  │
 Gemini     │                 │ Sliding     │     │ Match          │◀── Cosmos DB     │
 vision     │                 │ Doors MCP   │◀────│ Blackboard     │    (state +      │
 adapter    │                 │ server      │     │ (facts/claims) │     checkpoints) │
 (optional) │                 └─────────────┘     └────────────────┘                  │
            └──────────────────────────────────────────────────────────────────────────┘
                     Foundry: models · Agent Service · Evaluations · Tracing · Routines
                     Functions: half/full-time recap trigger · Speech: TTS · Translator: fallback
```

### Stage 1 — Ingest: the "Kickoff" synthetic engine

**Goal:** a football-realistic, seeded, batch-vectorised simulator that emits both an **event stream** (StatsBomb-like schema) and a **tracking stream** (22 players + ball, 10 Hz), with hidden ground truth for evaluation.

Design:

- **State tensor** `S[B, 23, 6]` = (x, y, vx, vy, stamina, orientation) for 22 players + ball, batched over `B` parallel worlds. One engine serves live play (B = 1) and counterfactual rollouts (B = 200) with the same code.
- **Team style profiles** (hidden truth): `press_height`, `tempo`, `directness`, `line_height`, `width`, `risk_appetite`. Styles drift with game state (chasing a goal → higher risk) and fatigue. Phases (high press, mid block, low block, counter) are logged as `truth.phases` and never exposed to the live path.
- **Decision model per possession tick:** candidate actions {pass to k receivers, carry, shot, clear} scored by a cheap utility (expected threat gain, completion probability from pass model, style weights, noise). Shots use an xG model with distance, angle, pressure, body part.
- **Events emitted:** `pass`, `carry`, `shot`, `tackle`, `interception`, `pressure` (continuous pressure events when an opponent is within 3 m closing), `possession_change`, `foul`, `card`, `substitution`, `set_piece`, `period_start/end`, plus `match_metadata` (lineups, kits, weather, venue). Each event has `id`, `t_ms`, `clock`, `period`, `team`, `player`, `location`, `end_location`, `outcome`, `under_pressure`, `related_events[]`.
- **LLM-authored league (data innovation):** a one-time Foundry job generates 8 fictional clubs (names, crests described in words, histories, rivalries, style identities) and 200 players (names from diverse name pools, ages, positions, traits, injury history, narrative hooks like "ex-academy returning to face his old club"). Stored as `data/league/*.json`. This makes narration richer and demonstrates "creativity in synthetic data creation."
- **Realism calibration:** `scripts/calibrate.py` runs 300 matches and prints distribution tables (pass completion 80–85%, 1.2–1.6 goals/team, 10–14 shots/team, 8–12 fouls, possession 40–60%, PPDA 8–14) versus public top-flight ranges. Committed as `docs/calibration.md`.
- **Transport:** live mode publishes to **Azure Event Hubs** (`match-events` and `tracking` hubs, partitioned by `match_id`); replay mode reads `data/matches/<seed>.jsonl` and `tracking.npz` at 1×/10× speed. Both feed the same consumer.
- **Optional vision adapter (auto-eventing):** `ingest/vision_adapter.py` uploads a rendered clip of the 2.5D pitch to **Gemini 3.8 Flash** with `processing: "agentic"`, asks for timestamped pass/shot/tackle events in our schema, and scores them against sim truth. This satisfies the rules' "auto-eventing from a video feed" bullet in a day because Gemini does the heavy lifting. Keep as Day 6 stretch.

### Stage 2 — Interpret: Pitch Physics

All deterministic, numpy, 10 Hz, no LLM. This is where the "measured, not vibed" story lives.

| Metric | Method |
|---|---|
| **Pitch control field** | Spearman-style: for each 2 m cell, each player's time-to-arrive from position + velocity + reaction time; logistic control probability; integrated per team. 1,785 cells × 22 players per tick, vectorised. Output `PC[t, 68, 105]` ∈ [0,1] home-share. |
| **Control index (per team)** | Possession-weighted pitch control in the attacking half + field tilt (share of final-third actions, last 5 min) + sustained possessions. 0–100. |
| **Chaos index (match)** | 0.5 × normalised entropy of the contested zone of PC + 0.3 × turnover rate (last 60 s) + 0.2 × transition share (possessions < 3 passes ending in shot/turnover). 0–100. |
| **Game state machine** | Settled / Transitional / Chaotic with hysteresis (enter Chaotic at > 65 for 20 s, exit at < 50 for 30 s). Emits `state_change` moments. This mirrors the hidden-Markov "match control states" in the momentum literature ([Ötting et al.](https://arxiv.org/abs/2002.01193)) but is fully explainable. |
| **Pressure index (team)** | PPDA over rolling 5 min + mean closing speed of pressure events + high turnovers. |
| **Rhythm/tempo** | Passes per minute of possession, mean time-on-ball, sequence length distribution; detects "tempo shift" when 2-min tempo deviates > 1.5σ from match mean. |
| **Pass quality** | Distance, angle, under-pressure flag, receiver's pitch control at target, progressive distance. **Pass difficulty** = 1 − P(complete) from a logistic model **fitted on 300 synthetic matches** (`models/pass_model.pkl`). Pass accuracy rolling per player. |
| **Speed metrics** | Ball speed from tracking deltas (km/h); shot speed at release; player speed with sprint threshold (> 25 km/h) and distance covered. Triggers `player_tag` cues when thresholds hit (rules bullet). |
| **xG / xT** | xG from the engine's own model (shared with sim, published); xT from a 12×8 grid fitted on synthetic data. Cumulative xG race for recaps. |
| **Auto-events** | Derived events not in the raw stream: `pressing_trap`, `line_break`, `switch_of_play`, `overload` (3v2 in a channel from PC), `counter_attack` (possession won → shot < 12 s), `big_chance` (xG > 0.3). |
| **Win probability** | Logistic on (score diff, minute, xG diff last 15 min, chaos state, red cards) fitted on 2,000 simulated matches; also computable by Monte Carlo from the engine for any live state. |

Every metric writes to the **Match Blackboard** (Cosmos DB, container `facts`, partition `/match_id`) as time-stamped documents with `evidence_event_ids`. Agents can only cite facts that exist here.

### Stage 3 — Explain: the Sliding Doors Engine and the Newsroom

#### 3a. Sliding Doors (counterfactual) engine

Exposed as an MCP tool and a REST endpoint.

```
simulate_counterfactual(match_id, t_ms, alternative) -> {
  baseline:    {p_goal_home_90s, p_goal_away_90s, win_prob_home},
  alternative: {...},
  delta_win_prob: +0.09,
  n_rollouts: 200, horizon_s: 90, seed: 4242,
  branch_summary: "Reyes unmarked at far post; 3v2 overload right channel",
  evidence_event_ids: [...], pitch_control_snapshot_id: "pc_000412"
}
```

- Alternatives are generated automatically for each candidate moment: `pass_to_best_xt_option`, `shoot_instead`, `hold_and_recycle`, `no_turnover` (for errors), `no_foul`.
- Horizon 90 s, 200 rollouts, batched in one engine call. Target < 800 ms on one ACA vCPU.
- **Moment leverage** = |win_prob_after − win_prob_before| for the actual event. The Director uses leverage to triage.
- The UI animates the alternative branch as a ghost trail on the pitch. This is the money shot of the demo.

#### 3b. The Newsroom (multi-agent)

Built with **Microsoft Agent Framework (Python) graph workflows**. Shared state is the Match Blackboard, not the chat transcript. Checkpoints go to **Cosmos DB** via `CosmosCheckpointStorage` so a killed container resumes mid-moment.

| Agent | Role | Model | Tools (via MCP) |
|---|---|---|---|
| **Scout** | Triage candidate moments from the analytics stream (state changes, leverage > 0.04, big chances, milestones, player-focus triggers). Outputs `Moment{kind, leverage, evidence_ids, hypotheses[]}`. 80% deterministic rules + LLM only for hypothesis framing. | GPT-6 Luna | `query_events`, `get_state` |
| **Tactician** | Explains *why* using pitch control + counterfactual. Must call `simulate_counterfactual` and `get_pitch_control` and return a structured `Explanation{claims[], counterfactual, confidence}`. | GPT-6.1 Sol (Model Router preview with fallback to Luna) | `simulate_counterfactual`, `get_pitch_control`, `player_stats` |
| **Narrator** | Writes persona-specific lines (Analyst / Casual / Kid / Player-Cam / Commentator-prep) as **structured JSON with claims[]** each bound to an evidence ID. English master. | GPT-6 Luna (Foundry Agent Service prompt agent, versioned) | none (reads blackboard snapshot in prompt) |
| **Fact Checker** | Deterministic code first: every number, unit, player, team, minute in `claims[]` must exist in the blackboard within tolerance; script check for target languages. Optional LLM judge for tactical plausibility against the Tactician's explanation. Rejects → loop back to Narrator with the diff (max 2 rewrites) → template fallback. | code + GPT-6 Luna | `verify_claims` |
| **Localizer** | One call produces all target languages with a football glossary (`data/glossary/*.json`) and RTL hints; re-verified by Fact Checker for numbers/names/scripts. Azure AI Translator as fallback. | GPT-6 Luna (Foundry prompt agent) | `glossary` |
| **Director** | Editorial scheduler. Inputs: verified cue candidates, viewer mode budgets, live state. Rules: ≤ 1 lower-third per 45 s per viewer mode; never overlay during an active shot sequence or within 3 s of a goal; prefer higher leverage; dedupe by topic; expire stale cues; chooses layer (lower-third, pitch, ticker, radar, tag). Emits the **Cue Sheet**. | code + GPT-6 Luna for tie-breaks and headline choice | `budget`, `state` |
| **Recap Editor** | At half/full time (triggered by Azure Function or Foundry Routine): narrative arc from top-leverage moments, xG race, chaos timeline, player of the match, "sliding doors of the match" section; per persona and language; TTS via Azure Speech. | GPT-6.1 Sol | `top_moments`, `timeline` |

**Workflow topology** (graph API):

```
AnalyticsEvent ──▶ Scout ──(moment)──▶ fan-out ┬──▶ Tactician ──┐
                                                └──▶ Narrator ──┤ fan-in ──▶ FactChecker ──(ok)──▶ Localizer ──▶ Director ──▶ CueBus
                                                                            └──(reject, ≤2)──▶ Narrator
HalfTime/FullTime trigger ──▶ RecapEditor ──▶ FactChecker ──▶ Localizer ──▶ Director(hold for producer approval, HITL) ──▶ CueBus
```

**Failure recovery (demoed):** per-agent timeouts (Narrator 3 s, Tactician 6 s), retries with jitter, circuit breaker to template lines after 3 consecutive failures, Cosmos checkpoints so a killed `newsroom` replica resumes the in-flight moment, and Director's "degraded mode" banner. The Studio Console has a **"Kill Tactician"** button for the demo.

**Why a single agent cannot do this:** one model cannot simultaneously hold a latency budget of 5 s, run 200 physics rollouts, verify its own numbers, translate into six scripts and make editorial scheduling decisions for five audiences. Decomposition is the only way the end-to-end SLA holds, and the Fact Checker is only meaningful because it is a different party from the Narrator.

### Stage 4 — Render: the Cue Sheet and three surfaces

**Cue Sheet schema** (`schemas/cue.schema.json`), designed so a rendering partner can consume it without reading our code:

```json
{
  "cue_id": "c_000912",
  "match_id": "m_4242",
  "t_in_ms": 1874200, "t_out_ms": 1882200,
  "clock": "31:14", "period": 1,
  "layer": "lower_third | pitch_overlay | heatmap | ticker | player_tag | radar | recap_card",
  "priority": 0.82, "leverage": 0.09,
  "kind": "sliding_doors | state_change | big_chance | goal | tempo_shift | player_tag | milestone | pressing_trap",
  "targets": {"modes": ["analyst", "casual"], "clubs": ["any"], "players": ["p_017"], "languages": ["en", "es", "ar", "ja", "sw", "hi"]},
  "text": {"en": "Okafor shoots from 0.06 xG; Reyes was free at the far post (0.31). Win chance −9 pts.", "es": "...", "ar": "..."},
  "audio": {"en": "https://.../c_000912_en.mp3"},
  "graphics": {"pitch_control_snapshot": "pc_000412", "ghost_trail": [[52.1, 34.0], [58.0, 30.2]], "players_highlight": ["p_017", "p_031"]},
  "explain": {"why": "...", "claims": [{"text": "0.31 xG", "evidence_id": "e_8812", "verified": true}], "counterfactual_id": "cf_000077"},
  "verified": true, "trace_id": "0af7...", "agent_path": ["scout", "tactician", "narrator", "factchecker", "localizer", "director"],
  "producer_status": "auto | approved | vetoed"
}
```

Delivery: Director publishes to **Azure Web PubSub** (hub `cues`, groups per `match_id` + viewer mode). Clients join groups; the overlay only receives cues targeted at its mode. Replay mode uses SSE from the API container so judges can run without Azure.

Surfaces (all Vite + React + TypeScript, deployed to Azure Static Web Apps):

1. **Broadcast Overlay** (`/overlay?match=&mode=`): transparent background, 1920×1080, lower-thirds, score bug, chaos meter, pitch-control heatmap toggle, player tags. Works as an OBS/Vizrt/CasparCG browser source. Behind it in the demo sits our **2.5D pitch renderer** (Canvas, tracking at 10 Hz interpolated to 60 fps) so overlays visibly sit "on the match".
2. **Studio Console** (`/studio`): live blackboard, moment queue with leverage, agent trace timeline (which agent did what, latency, tokens), evidence drawer ("Why?" opens the pitch-control snapshot and the ghost-trail counterfactual), producer approve/veto, kill-switch demo, cost meter, language matrix.
3. **Fan App** (`/fan`): phone-shaped second screen. Pick persona, club, player, favourite metric, language. Player-Cam mode follows one player with distance, top speed, sprints, pitch-control contribution and milestone cues. Audio narration via Azure Speech.

### Stage 5 — Personalize

Viewer profile `{mode, club, player, metric, language, accessibility}` lives client-side and as a Web PubSub group subscription. Personalisation is done at **three** levels so it is genuine, not cosmetic:

- **Selection (Director):** different budgets and kinds per mode. Analyst gets state changes, pressing traps, counterfactuals and heatmaps; Casual gets goals, big chances, milestones and one "did you know" per 10 min; Kid gets celebrations and simple cause/effect; Player-Cam gets threshold tags and touches; Commentator-prep gets a rolling fact sheet.
- **Expression (Narrator):** persona voice and vocabulary; club perspective ("we" framing for the chosen club, with the Fact Checker guarding against bias on numbers).
- **Language (Localizer + Speech):** six languages on day one (English, Spanish, Arabic, Japanese, Swahili, Hindi) including one RTL script to demonstrate script verification. Azure Speech neural voices per language for the Fan App and recap audio; audio-description mode for blind and low-vision fans prioritises spatial language.

Favourite-metric mode: pick "pressure", "pitch control", "ball speed" or "passing" and the ticker becomes a single-metric channel with threshold alerts.

---

## 3. Hybrid technology map (Microsoft-first, external where it genuinely wins)

My recommendation differs slightly from the "Gemini as the heavy-lifting backend" framing in the brief. The Grand Prize text says *"innovative use of the Microsoft AI platform product stack"* and the Foundry category rewards Foundry doing the orchestration and management. Putting Gemini at the centre of reasoning would cost points for no demo gain, because the reasoning quality difference is invisible on a 2-minute video. So: **Foundry models for all agent reasoning; Gemini in exactly one place where it is a visible differentiator (agentic video auto-eventing).** Everything is behind an adapter so either can be swapped.

| Layer | Choice | Why (and what it earns) |
|---|---|---|
| Agent runtime | **Microsoft Agent Framework 1.x (Python)** graph workflows: `WorkflowBuilder`, fan-out/fan-in edges, `RequestInfoExecutor` for producer approval, `CosmosCheckpointStorage` | Multi-Agent category. Visualisation export of the topology goes in the README. |
| Hosted agents | **Foundry Agent Service** prompt agents for Narrator, Localizer, Recap Editor (versioned, with Toolboxes) | Foundry category: "accelerates development, orchestration and management". |
| Models | **GPT-6 Luna** ($0.10/$0.50 per M) for high-volume lines; **GPT-6.1 Sol** for Tactician/Recap; **Model Router (preview)** with routing metadata surfaced in the Studio trace | Cost guard: a full match costs cents. Router metadata is a nice judge-visible detail. |
| Evaluation | **Foundry Evaluations**: groundedness + a custom evaluator that scores explanations against sim hidden truth; **Tracing** GA + **Insights** preview | Publish numbers in README. Judges reward evidence. |
| Scheduling | **Foundry Routines** (GA) or an **Azure Function** timer/Event Grid trigger for half/full-time recaps and the post-match report | Cloud-native category: event-driven. |
| MCP | **Our `whyline-mcp` server** (FastMCP, Streamable HTTP, on ACA) exposing `query_events`, `get_pitch_control`, `simulate_counterfactual`, `player_stats`, `verify_claims`. Used by agents at runtime *and* by Copilot Agent Mode during development. **Azure MCP Server** used by the team for Cosmos queries, Container Apps logs, Monitor queries and Bicep schema during the build; transcripts in `docs/copilot-log.md` | "MCP integration" is named in the Agentic criterion. Two MCP stories, one built, one consumed. |
| Dev agents | **GitHub Copilot Agent Mode** with custom agents in `.github/agents/`: `sim-engineer.agent.md`, `azure-ops.agent.md` (Azure MCP), `football-analyst.agent.md` (whyline-mcp); `AGENTS.md` at root; Copilot coding agent assigned to issues; **GitHub CLI** in scripts | Hero-tech checklist, plus Claude Code for the heavy lifting (not mentioned to judges). |
| Compute | **Azure Container Apps**: `kickoff` (sim), `physics`, `newsroom`, `api`, `mcp`; KEDA scale on Event Hubs lag; scale-to-zero outside demos | Cloud-native category. |
| Streaming | **Azure Event Hubs** (events, tracking) → **Web PubSub** (cues) | Event-driven architecture, named in category text. |
| State | **Azure Cosmos DB NoSQL**: `facts`, `moments`, `cues`, `claims`, `checkpoints`; change feed powers the Studio Console | "AI-optimised data platform". Also Agent Framework's Cosmos memory integration (preview) for Narrator continuity. |
| Speech/Translation | **Azure Speech** neural TTS (6 voices); **Azure AI Translator** fallback | Multi-language storytelling bullet. |
| Vision (optional) | **Gemini 3.8 Flash**, `processing: "agentic"`, via the adapter | Auto-eventing bullet; "models that scan video dynamically" is a demo line. |
| Ops | Bicep + `azd up`, GitHub Actions (test, build, deploy), **Application Insights** via OpenTelemetry GenAI attributes, **Key Vault** + user-assigned managed identity (no keys in cloud), **Content Safety / Prompt Shields** on Narrator output | Enterprise category: reliability, transparency, controls. |
| Optional | **Microsoft Fabric Eventhouse** mirror of Event Hubs for post-match KQL + Real-Time Dashboard | Only if a teammate has a free afternoon on Day 5. |

Enterprise readiness checklist (for the README "Enterprise" section): RBAC-only access, managed identity, no secrets in code, per-cue audit trail with trace ID, producer HITL veto, content safety, cost guard (max matches per day), evaluation gates in CI (groundedness ≥ 0.95 on golden set), replay mode for air-gapped testing, SLOs (cue p95 < 5 s from event), region-pinned data.

---

## 4. Implementation plan and directory layout

### 4.1 Repository

```
whyline/
├── AGENTS.md                      # instructions for Copilot / Claude Code
├── README.md                      # pitch, architecture diagram, eval table, run instructions
├── azure.yaml                     # azd project
├── infra/
│   ├── main.bicep                 # ACA env, Event Hubs, Cosmos, Web PubSub, Foundry project, Speech, KV, App Insights, SWA
│   └── modules/*.bicep
├── .github/
│   ├── workflows/ci.yml           # pytest + ruff + schema validation + eval gate
│   ├── workflows/deploy.yml       # azd provision + deploy on main
│   ├── agents/                    # Copilot custom agents
│   │   ├── sim-engineer.agent.md
│   │   ├── azure-ops.agent.md     # uses Azure MCP Server
│   │   └── football-analyst.agent.md  # uses whyline-mcp
│   └── copilot-instructions.md
├── packages/
│   ├── kickoff/                   # Stage 1: synthetic engine
│   │   ├── kickoff/engine.py      # batched state tensor, step(), decision model
│   │   ├── kickoff/models.py      # xG, pass completion, xT grids
│   │   ├── kickoff/league.py      # loads LLM-authored clubs/players
│   │   ├── kickoff/events.py      # StatsBomb-like event schema (pydantic)
│   │   ├── kickoff/publish.py     # Event Hubs producer / file writer
│   │   └── cli.py                 # kickoff play --seed 4242 --speed 1 --target eventhubs|file
│   ├── physics/                   # Stage 2
│   │   ├── physics/pitch_control.py
│   │   ├── physics/indices.py     # control, chaos, pressure, tempo, state machine
│   │   ├── physics/pass_quality.py
│   │   ├── physics/speeds.py
│   │   ├── physics/autoevents.py
│   │   ├── physics/winprob.py
│   │   └── consumer.py            # Event Hubs consumer → blackboard writer
│   ├── slidingdoors/              # Stage 3a
│   │   ├── slidingdoors/counterfactual.py
│   │   └── slidingdoors/alternatives.py
│   ├── mcp/                       # whyline-mcp server (FastMCP)
│   │   └── server.py
│   ├── newsroom/                  # Stage 3b
│   │   ├── newsroom/agents/{scout,tactician,narrator,factchecker,localizer,director,recap}.py
│   │   ├── newsroom/blackboard.py # Cosmos repository
│   │   ├── newsroom/workflow.py   # WorkflowBuilder graph
│   │   ├── newsroom/cues.py       # Cue Sheet builder + Web PubSub publisher
│   │   ├── newsroom/prompts/*.md  # versioned prompts (also pushed to Foundry Agent Service)
│   │   └── main.py
│   ├── api/                       # FastAPI: REST + SSE replay + health + eval endpoints
│   └── vision/                    # optional Gemini adapter
├── apps/
│   ├── overlay/                   # Broadcast Overlay (React)
│   ├── studio/                    # Studio Console (React)
│   └── fan/                       # Fan App (React)
├── schemas/
│   ├── event.schema.json
│   ├── cue.schema.json
│   └── explanation.schema.json
├── data/
│   ├── league/{clubs,players}.json
│   ├── glossary/{es,ar,ja,sw,hi}.json
│   └── matches/4242/{events.jsonl,tracking.npz,truth.json}   # golden replay match
├── evals/
│   ├── golden_moments.jsonl       # hand-checked moments for the demo match
│   ├── run_evals.py               # Foundry Evaluations + custom truth evaluator
│   └── results.md
├── scripts/
│   ├── calibrate.py
│   ├── fit_models.py              # pass completion, xT, win prob on synthetic data
│   ├── generate_league.py         # one-time Foundry call
│   └── record_demo.sh
├── docs/
│   ├── architecture.md            # + exported workflow visualisation
│   ├── calibration.md
│   ├── copilot-log.md             # Copilot Agent Mode + Azure MCP transcripts
│   └── enterprise.md
└── tests/
```

### 4.2 Critical script specifications

**Engine step (batched)** — `packages/kickoff/kickoff/engine.py`

```python
import numpy as np

class Engine:
    """Batched 22-player football simulation. S: [B, 23, 6] -> x, y, vx, vy, stamina, facing."""
    DT = 0.1  # 10 Hz

    def __init__(self, league, home, away, seed: int, batch: int = 1):
        self.rng = np.random.default_rng(seed)
        self.S = self._kickoff_positions(batch)
        self.styles = self._styles(home, away)          # hidden truth
        self.possession = np.zeros(batch, dtype=np.int8)  # 0 home, 1 away
        self.events, self.truth = [], {"phases": []}

    def step(self):
        self._move_offball()                             # role targets + style line heights + fatigue
        on_ball = self._ball_holder()
        actions = self._decide(on_ball)                  # pass/carry/shoot/clear via utility + noise
        self._apply(actions)                             # ball physics, duels, pressure events
        self._update_phases()                            # logs truth.phases, never exposed live
        return self._emit_events()                       # pydantic Event models, StatsBomb-like

    def branch(self, t_ms: int, batch: int, alternative: dict) -> "Engine":
        """Clone state at t_ms into `batch` worlds, apply the alternative first action."""
```

**Pitch control** — `packages/physics/physics/pitch_control.py`

```python
def pitch_control(S: np.ndarray, grid=(105, 68), cell=2.0, reaction=0.7, vmax=7.8, k=3.0):
    """Spearman-style control share for home team on a 2 m grid. S: [23, 6]."""
    gx, gy = np.meshgrid(np.arange(0, grid[0], cell), np.arange(0, grid[1], cell), indexing="ij")
    cells = np.stack([gx, gy], -1).reshape(-1, 2)                      # [C, 2]
    P = S[:22, :2] + S[:22, 2:4] * reaction                            # position after reaction
    t_arrive = np.linalg.norm(cells[:, None, :] - P[None], axis=-1) / vmax  # [C, 22]
    t_home, t_away = t_arrive[:, :11].min(1), t_arrive[:, 11:].min(1)
    share = 1 / (1 + np.exp(k * (t_home - t_away)))                    # P(home controls cell)
    return share.reshape(gx.shape)

def chaos_index(pc, turnovers_60s, transition_share):
    contested = pc[(pc > 0.2) & (pc < 0.8)]
    h = -(contested * np.log2(contested + 1e-9) + (1 - contested) * np.log2(1 - contested + 1e-9)).mean() if contested.size else 0
    return 100 * (0.5 * h + 0.3 * min(turnovers_60s / 6, 1) + 0.2 * transition_share)
```

**Counterfactual** — `packages/slidingdoors/slidingdoors/counterfactual.py`

```python
def simulate_counterfactual(match, t_ms, alternative, n=200, horizon_s=90, seed=4242):
    base = match.engine.branch(t_ms, n, alternative=None)
    alt = match.engine.branch(t_ms, n, alternative=alternative)
    for _ in range(int(horizon_s / Engine.DT)):
        base.step(); alt.step()
    pb, pa = base.goal_probs(), alt.goal_probs()         # [home, away] over n worlds
    return CounterfactualResult(
        baseline=pb, alternative=pa,
        delta_win_prob=winprob(match.state_at(t_ms), pa) - winprob(match.state_at(t_ms), pb),
        evidence_event_ids=match.events_near(t_ms, 5000), seed=seed, n_rollouts=n, horizon_s=horizon_s)
```

**MCP server** — `packages/mcp/server.py`

```python
from fastmcp import FastMCP
mcp = FastMCP("whyline")

@mcp.tool()
def query_events(match_id: str, t_from_ms: int, t_to_ms: int, kinds: list[str] | None = None) -> list[dict]: ...
@mcp.tool()
def get_pitch_control(match_id: str, t_ms: int) -> dict: ...          # snapshot id + team shares + contested zones
@mcp.tool()
def simulate_counterfactual(match_id: str, t_ms: int, alternative: str) -> dict: ...
@mcp.tool()
def player_stats(match_id: str, player_id: str) -> dict: ...
@mcp.tool()
def verify_claims(match_id: str, claims: list[dict]) -> dict: ...     # deterministic verifier

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8080)
```

**Newsroom workflow** — `packages/newsroom/newsroom/workflow.py`

```python
from agent_framework import WorkflowBuilder, Executor, handler, WorkflowContext, RequestInfoExecutor
from agent_framework.foundry import FoundryChatClient
from agent_framework_azure_cosmos import CosmosCheckpointStorage
from azure.identity.aio import DefaultAzureCredential

def build_workflow(cfg, checkpoint_storage):
    scout, tactician, narrator = ScoutExecutor(cfg), TacticianExecutor(cfg), NarratorExecutor(cfg)
    checker, localizer, director = FactCheckExecutor(cfg), LocalizerExecutor(cfg), DirectorExecutor(cfg)
    b = WorkflowBuilder(start_executor=scout, checkpoint_storage=checkpoint_storage, name="newsroom")
    b.add_fan_out_edges(scout, [tactician, narrator])
    b.add_fan_in_edges([tactician, narrator], checker)
    b.add_edge(checker, localizer, condition=lambda m: m.verified)
    b.add_edge(checker, narrator, condition=lambda m: not m.verified and m.attempts < 2)
    b.add_edge(localizer, director)
    return b.build()

class TacticianExecutor(Executor):
    @handler
    async def explain(self, moment: Moment, ctx: WorkflowContext[Explanation]):
        result = await self.agent.run(moment.prompt(), tools=self.mcp_tools)  # must call simulate_counterfactual
        await ctx.send_message(Explanation.model_validate_json(result.text))
    async def on_checkpoint_save(self): return {"inflight": self._inflight}
    async def on_checkpoint_restore(self, s): self._inflight = s.get("inflight", {})
```

**Fact Checker rule set** (deterministic, `factchecker.py`): numbers within ±2% or ±1 unit of a blackboard fact; player and club names must be in lineups; minute within ±1 of event; language script check via Unicode ranges; banned-claim list (injury speculation, referee bias); on failure return `{verified: false, diff: [...]}` to Narrator.

**Director budget table** (`director.py`):

| Mode | Lower-third min gap | Max cues / 10 min | Allowed kinds | Heatmap |
|---|---|---|---|---|
| analyst | 30 s | 12 | all | on |
| casual | 60 s | 6 | goal, big_chance, milestone, sliding_doors(top 2/half) | off |
| kid | 90 s | 4 | goal, big_chance, celebration | off |
| player_cam | 20 s | 15 | player_tag, touches, sprint, milestone | player trail |
| commentator_prep | 15 s | 20 | facts ticker | off |

### 4.3 Setup commands

```bash
# prerequisites: Python 3.12, Node 22, Azure CLI, azd, Docker
git clone https://github.com/<you>/whyline && cd whyline
uv sync                                        # or: pip install -e packages/*
npm install --prefix apps

# generate the fictional league once (Foundry)
az login && azd auth login
python scripts/generate_league.py --out data/league

# fit synthetic-data models and calibrate
python scripts/fit_models.py --matches 300
python scripts/calibrate.py --matches 300 --out docs/calibration.md

# local replay (no Azure needed): sim → physics → newsroom(templates) → SSE → UIs
docker compose up                              # api:8000 mcp:8080 overlay:5173 studio:5174 fan:5175
kickoff play --seed 4242 --speed 10 --target file

# cloud
azd up                                         # provisions infra/main.bicep and deploys 5 container apps + 3 SWAs
azd env get-values                             # WEB_PUBSUB_URL, FOUNDRY_PROJECT_ENDPOINT, ...
kickoff play --seed 4242 --speed 1 --target eventhubs

# evals
python evals/run_evals.py --match 4242 --out evals/results.md
```

Python packages: `agent-framework`, `agent-framework-azure-cosmos`, `azure-ai-projects`, `azure-ai-evaluation`, `azure-eventhub`, `azure-cosmos`, `azure-messaging-webpubsubservice`, `azure-cognitiveservices-speech`, `fastmcp`, `fastapi`, `numpy`, `pydantic`, `google-genai` (optional).

### 4.4 Seven-day build plan (Oct 21 → Oct 27)

Roles assume 3 people: **A** (engine + physics + counterfactual), **B** (agents + MCP + Azure), **C** (three front-ends + video). With 2 people, drop Fan App to a mode switch inside Overlay and drop the vision adapter. With 4, the fourth owns evals, docs, and Fabric.

| Day | A: Engine & Physics | B: Agents & Cloud | C: UX & Story |
|---|---|---|---|
| **Tue 21** | Engine v1 (batched state, roles, pass/shot/pressure events, event schema), file replay, seed 4242 golden match | Repo, `azd` skeleton, Bicep (ACA env, Cosmos, Event Hubs, Web PubSub, Foundry, KV, App Insights), CI, Copilot custom agents, AGENTS.md | 2.5D pitch renderer from tracking.npz; overlay shell; cue schema agreed by noon |
| **Wed 22** | Pitch control, chaos/control indices, state machine, pass quality, speeds, auto-events, blackboard writer | MCP server, blackboard repo, Scout + Narrator + Fact Checker, template fallback, SSE path | Overlay lower-thirds, score bug, chaos meter, heatmap layer; Studio skeleton with agent trace |
| **Thu 23** | Sliding Doors engine + alternatives + win prob; `fit_models.py`; `calibrate.py`; league generation | Tactician with MCP tools, Localizer (6 languages), Director + budgets, Web PubSub publish, Cosmos checkpoints | Studio evidence drawer with ghost-trail counterfactual; Fan App with profile + Player-Cam |
| **Fri 24** | Performance (rollouts < 800 ms), realism tuning, tracking interpolation, tests | `azd up` end-to-end on Azure; Foundry Agent Service prompt agents; Speech TTS; Recap Editor + Function trigger; kill-switch resilience | Polish all three UIs, RTL layout, audio playback, producer veto UI |
| **Sat 25** | Evals: Scout precision/recall vs truth, counterfactual calibration, latency p95; `evals/results.md` | Foundry Evaluations + Tracing + Model Router metadata in Studio; content safety; cost guard; copilot-log.md | Record b-roll; architecture diagram; README draft |
| **Sun 26** | Optional Gemini vision adapter + accuracy table | Hardening, replay-mode-without-Azure test on clean machine, judge instructions | Edit video v1; pitch text; screenshots |
| **Mon 27** | Bug bash | Final deploy, public repo check, licence, no trademarks audit | Final video upload (YouTube, unlisted is fine), submit form by 6 pm PT buffer |

Daily rule: the golden match (seed 4242) must play end to end on `main` every evening. Anything not demo-visible by Saturday is cut.

### 4.5 Evaluation table to publish (targets)

| Metric | Target | How measured |
|---|---|---|
| Scout precision / recall on state changes vs hidden truth | ≥ 0.75 / ≥ 0.70 | 50 synthetic matches |
| Counterfactual calibration | Brier ≤ 0.20 on P(goal in 90 s) | compare rollout prob to realised outcomes across 2,000 branch points |
| Fact Checker: planted false claims caught | 100% | 200 planted errors |
| Fact Checker: true claims wrongly rejected | ≤ 3% | golden set |
| Cue latency (event → verified cue on Web PubSub) | p50 < 3 s, p95 < 5 s | App Insights |
| Cost per 90-minute match (6 languages) | < $0.50 | Foundry usage |
| Foundry groundedness evaluator on 500 cues | ≥ 0.95 | `azure-ai-evaluation` |

These numbers are competitive advantages precisely because the public entries report weak or no evaluation.

---

## 5. Submission pitch (paste-ready, edit names)

**WHYLINE — every line on screen has a why.**

WHYLINE is a multi-agent match-intelligence platform that turns a live stream of synthetic football events and tracking into explained, verified, personalised broadcast cues in under five seconds. A batch-vectorised 22-player simulator produces the match; a Pitch Physics engine computes live pitch control, pressure, tempo and a Control/Chaos state machine; and a counterfactual "Sliding Doors" engine re-simulates every key moment 200 times to measure how much it changed the game. An AI newsroom built on Microsoft Agent Framework (Scout, Tactician, Narrator, Fact Checker, Localizer, Director, Recap Editor) coordinates through a shared Cosmos DB blackboard with checkpoint recovery, reaches data only through our MCP server, and publishes a machine-readable Cue Sheet over Azure Web PubSub to a keyed broadcast overlay, a producer console and a personalised fan app in six languages. Built with Microsoft Foundry (Agent Service, Evaluations, Tracing, Model Router), Azure Container Apps, Event Hubs, Cosmos DB, Web PubSub, Functions, Azure Speech, Azure MCP Server and GitHub Copilot Agent Mode. It solves the broadcaster's trust and latency problem and the fan's "data without wisdom" problem at once. Category: Best Multi-Agent System.

---

## 6. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Rollouts too slow in Python | Batch dimension first; numpy only; horizon 60 s if needed; precompute counterfactuals for the golden match as cache for the demo |
| LLM latency blows the 5 s budget | Luna for everything on the hot path; Tactician runs in parallel with Narrator; Director can ship a verified "fast line" and upgrade it with the counterfactual 3 s later |
| Azure quota/region issues | Provision on Day 1; keep `docker compose` replay path as judge fallback; document both |
| Judges cannot run cloud path | Replay mode with recorded agent outputs (cassette) and template fallback; hosted demo URL kept alive through Nov 10 with scale-to-zero |
| Hallucinated numbers | Structured claims + deterministic verifier + evidence IDs on every cue; blocked-line counter visible in Studio |
| Trademark/music rules | Fictional clubs, no league marks, no real player names, royalty-free or no music |
| Scope creep | Saturday cut line; vision adapter and Fabric are explicit stretch items |
| "Rendering partner" spec unknown | The Challenges tab on the hackathon site is behind sign-in and I could not read it. If it names a graphics partner or a cue format, paste it and I will align `cue.schema.json`; the adapter pattern makes this a one-file change |

---

## 7. Two-minute demo video storyboard

Format: 1920×1080, 24–30 fps, screen capture with light motion graphics, voice-over, no music or royalty-free only. Total **1:55**.

| Time | Scene | On screen | Voice-over |
|---|---|---|---|
| 0:00–0:08 | Cold open | Black. A lower-third slides in: "xG 0.06". Then it is struck through and replaced with: "Reyes was free at the far post. 0.31 xG. Win chance −9 pts." | "Football broadcasts tell you *what* happened. Nobody tells you *why it mattered*." |
| 0:08–0:18 | Title + problem | WHYLINE wordmark. Three quick quotes animate: "soulless numbers", "data without wisdom", "one feed for every fan". | "Fans are drowning in stats. Broadcasters can't trust automated data. And every market gets the same story." |
| 0:18–0:35 | The match is alive | 2.5D pitch, 22 players moving at 10 Hz, pitch-control heatmap fading in, chaos meter climbing, state flips Settled → Chaotic. | "WHYLINE starts with a physics simulation of the match. Live pitch control shows who owns the space. When the game turns chaotic, we can measure it, and prove it." |
| 0:35–0:58 | Sliding Doors moment | Shot event. Studio Console: Scout flags it, Tactician calls `simulate_counterfactual`, 200 ghost futures flicker on the pitch, ghost trail to Reyes, win-probability bar shifts. Cue appears on the overlay. | "Here's the breakthrough. Every key moment is re-simulated two hundred times. Had Okafor squared it, home win chance rises nine points. That's not a vibe. That's a counterfactual, with evidence IDs on every claim." |
| 0:58–1:18 | The Newsroom | Agent trace timeline: Scout → Tactician ∥ Narrator → Fact Checker rejects a line (wrong minute) → rewrite → Localizer (six languages pop in, Arabic RTL) → Director schedules. Click "Kill Tactician": banner "degraded", cues keep flowing, container restarts, checkpoint resumes mid-moment. | "Seven agents on Microsoft Agent Framework share a blackboard in Cosmos DB and reach data only through MCP. The Fact Checker blocks anything it can't verify. Kill an agent, and the newsroom recovers from its checkpoint." |
| 1:18–1:38 | Personalised | Split screen: Broadcast Overlay (analyst heatmap) / Fan App (casual, Spanish, audio playing) / Player-Cam following one player with sprint tag "32.1 km/h". Producer taps "veto" on a recap line in Studio. | "The same intelligence reaches an analyst, a casual fan in Madrid, and a kid following her favourite player, as three genuinely different experiences. A producer can veto anything before air." |
| 1:38–1:50 | Azure + numbers | Architecture diagram builds up: Event Hubs → Container Apps → Cosmos → Web PubSub; Foundry Evaluations panel: groundedness 0.97, p95 latency 4.2 s, cost $0.31/match. | "Cloud-native on Azure Container Apps, Event Hubs and Web PubSub. Foundry Agent Service, Evaluations and Tracing keep it measurable: 97% groundedness, under five seconds, cents per match." |
| 1:50–1:55 | Close | Wordmark + repo URL + "Built for Inside the Game". | "WHYLINE. Every line on screen has a why." |

Production notes: record each UI at 1080p with `scripts/record_demo.sh` (Playwright drives the golden match at 10×, then slows to 1× for the Sliding Doors scene). Use the Studio "demo script" button that triggers the kill-switch and the veto at fixed clock times so the take is repeatable. Captions burned in for accessibility.

---

## 8. Research notes and sources

**Fan and broadcaster pain points**
- [Football fans are drowning in data, starved of wisdom (xGuff)](https://xguff.substack.com/p/football-fans-are-drowning-in-data)
- [Bridging the gap between the fan and analyst (Pulse9)](https://pulse9post.substack.com/p/bridging-the-gap-between-the-fan)
- [Morgan Rogers: xG "a whole load of nonsense" (AOL)](https://www.aol.com/articles/morgan-rogers-makes-divisive-xg-140444092.html)
- [Automatic for the people: live graphics evolve (SVG Europe)](https://www.svgeurope.org/blog/headlines/automatic-for-the-people-live-graphics-evolve-to-transform-real-time-sports-storytelling/)
- [Integrating live data into sports graphics (WASP3D)](https://wasp3d.com/blogs/integrating-live-data-stats-into-sports-graphics-a-complete-guide/)
- [Genius Sports / PLP Data Zone rollout (SportBusiness)](https://www.sportbusiness.com/news/genius-sports-plp-roll-out-premier-league-data-zone-worldwide/)

**Analytics foundations**
- [Hidden Markov momentum states in football (Ötting, Langrock, Maruotti)](https://arxiv.org/abs/2002.01193)
- [Phases of play: control vs transition tagging (Hudl StatsBomb)](https://www.hudl.com/blog/phases-of-play-hudl-statsbomb)
- [SoccER synthetic event generator (ScienceDirect)](https://www.sciencedirect.com/science/article/pii/S2352711020303253)
- [StatsBomb open data schema (KU Leuven tutorial)](https://dtai.cs.kuleuven.be/tutorials/sports/ecml2024/notes/datasets/soccer/)

**Vision and models**
- [Roboflow sports repo (player, ball, pitch keypoint datasets)](https://github.com/roboflow/sports)
- [Roboflow football-players-detection (YOLO/RF-DETR)](https://universe.roboflow.com/roboflow-jvuqo/football-players-detection-3zvbc)
- [Gemini video understanding and agentic processing](https://ai.google.dev/gemini-api/docs/video-understanding)

**Microsoft stack (verified October 2026)**
- [Microsoft Agent Framework overview](https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview)
- [Agent Framework workflows and checkpoints (Cosmos storage)](https://learn.microsoft.com/en-us/agent-framework/workflows/checkpoints)
- [Agent Framework orchestrations](https://learn.microsoft.com/en-us/agent-framework/workflows/orchestrations/)
- [What's new in Microsoft Foundry, September 2026](https://devblogs.microsoft.com/foundry/whats-new-in-microsoft-foundry-september-2026/)
- [Azure MCP Server tools reference](https://learn.microsoft.com/en-us/azure/developer/azure-mcp-server/tools/)

**Competitor entries read**
- [matchroom](https://github.com/saisyalla96/matchroom), [livedesk](https://github.com/fahad-workspace/livedesk), [matchday-crew](https://github.com/timsheldon1/matchday-crew), [the-ninety-labs](https://github.com/KLKH7/the-ninety-labs)
