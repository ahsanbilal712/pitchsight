# WHYLINE — Feasibility Audit

Audit date: 21 October 2026. Auditor stance: sceptical principal engineer, ML research lead and hackathon judge. Nothing was built. Every external dependency was checked against a primary source or by running a small spike in a scratch environment on this machine (macOS 27, Apple Silicon, 11 cores, 18 GB, no discrete GPU, no API keys, no Azure CLI). Four parallel verification passes covered (A1) Google Research Football and RL policies, (A2) data licences and trajectory models, (A3) the Microsoft stack and Azure, and (A4) vision, voice, broadcast and 3D. Their full reports with URLs and raw command output are in the session scratchpad under `audit/`; this document consolidates them.

Labels: **VERIFIED** = read in a primary source or produced by a command run here. **INFERRED** = reasoned from verified facts or taken from a secondary source.

---

## Executive summary (two pages)

### The verdict in one paragraph

**Go, with changes.** The core idea, counterfactual "Sliding Doors" explanations from a branchable football world, is sound, differentiated against the field, and buildable. Two of its load-bearing assumptions are wrong as written and must change. First, the "learned behaviour model rolling out 15 seconds of football for 200 parallel futures in under a second" does not hold: no public football behaviour model with weights exists, published soccer forecasters are only stable for 4 to 6.4 seconds, and my own timing shows a 5M-parameter policy at batch 200 costs 80 ms per step on CPU and 20 ms on an Apple GPU, so a per-tick 15-second rollout is 3 to 12 seconds, not under one. Second, the "two worlds" plan depends on Google Research Football, which is archived, ships no Linux or macOS wheels, fails a stock `pip install` on a clean machine because of a build-time bug, and whose "new game server" is a dead domain. Both problems have credible fixes (call the policy only at decisions, cap learned horizons at 6 to 8 seconds, run gfootball in Docker on Linux as a batch data source only), but they change the architecture and the schedule. Everything else in the plan is real: the Microsoft Agent Framework APIs exist (with four naming corrections), Foundry's services are mostly GA, the vision models, voice APIs and broadcast tools exist with the licences and prices now recorded, and the hackathon rules can be satisfied.

### Confidence levels

| Question | Confidence | Why |
|---|---|---|
| The ML core (as redesigned below) is achievable in 45 days | **Medium** | Behaviour cloning in gfootball is proven (TiKick's plain-BC baseline wins 83% against the built-in AI from 22k episodes). The risk is realism of play and rollout drift, not whether a model trains. |
| The ML core as written in `ML_CORE.md` is achievable in 45 days | **Low** | 15-second per-tick autoregressive rollouts at 10 Hz in under a second on CPU is contradicted by measurement and by every published horizon. |
| A credible demo exists by day 7 | **High** | Scripted engine, pitch control, scripted-physics Sliding Doors (200 × 90 s measured at 1.2 s on this CPU), one screen, replay mode. No learned model. |
| The rules are satisfied | **High if the synthetic-only path is kept; Medium if real data is used for pretraining** | Real-data pretraining is a grey area against "Projects must use synthetic, football-realistic data" and only two datasets are licence-clean. |
| The idea is differentiated against the field | **High** | Four public competitor repos share one template; none branches a simulator. |

### The three biggest risks

1. **Rollout realism and speed.** A learned policy that drifts, loses team shape or makes absurd passes turns every counterfactual into fiction, and the whole pitch with it. Published horizons are 4 to 6.4 s. Fix: learn on-ball decisions only, keep off-ball movement as a physics prior, cap the learned horizon at 6 to 8 s, hand off to a learned outcome head after that, and publish calibration.
2. **gfootball as a dependency.** Archived repository, 2022-era build, no wheels for Linux or macOS, `pip install` fails before cmake runs, headless rendering explicitly unsupported by the only active fork (EnvPool). Fix: a one-day Docker spike on Linux with a hard gate; if it fails, drop the second world and the rendered footage, and behaviour-clone from the team's own engine instead.
3. **Scope.** Fourteen ideas, eleven models, three front-ends, a 3D renderer, a fan study and a second submission for three people is a startup, not an entry. The 45-day plan needs about 160 person-days; three people have about 100 effective. Fix: the minimum viable version in Part E, with the cut lines in Part D.

### The three spikes to run first

| Spike | Hours | Kills or confirms |
|---|---|---|
| **gfootball in Docker on a Linux box** (Ubuntu 20.04 base, `pip install psutil` first, `--no-build-isolation`, `gym==0.21`), run one 11v11 match headless with GRF_MARL's `offensive_passer` policy, dump the `.dump` trace, time steps per second, attempt one `render(mode='rgb_array')` under `xvfb-run` | 6–8 | Whether the second world exists at all. Already known on this Mac: fails at build (no cmake, psutil shell-out bug). |
| **Decision-only rollout timing in PyTorch** on the target hardware (an A10 or T4 on Azure, or the Mac GPU): batch 200, 23 tokens, 6 layers, policy called once per second, physics in between, 8-second horizon | 2 | Whether live counterfactuals fit a 2-second budget. Measured here: 0.3 s on Apple GPU, 1.2 s on CPU for 15 calls. |
| **Behaviour-cloning sanity run** on 50 matches of the team's own scripted engine: train for 30 minutes, roll out 8 seconds, watch 20 clips, count teleports, offside violations and shape collapse | 4 | Whether a learned policy produces watchable football before any gfootball data exists. |

### What is wrong in the documents (headline list; full list in Part E)

- `ML_CORE.md`: "Inference for 200 parallel worlds: under 5 ms per step on a GPU, about 40 ms on CPU." Measured: 20 ms on an Apple GPU, 80 ms on CPU, for a 4.7M-parameter model.
- `ML_CORE.md`: "200 futures of the next 15 seconds in well under a second." Not with a per-tick policy. Achievable only with decision-only calls on a GPU (0.3 s measured).
- `WHYLINE_45DAY_MASTERPLAN.md`: a "successor game server exists" for gfootball. The domain `research-football.dev` does not resolve and was a 2019–2020 ELO matchmaking league, not a simulator.
- `WHYLINE_PROPOSAL.md`: `RequestInfoExecutor` for human-in-the-loop. It does not exist in the Python framework; the API is `ctx.request_info()` plus `@response_handler`.
- `WHYLINE_PROPOSAL.md` and `TOP7_IDEAS.md`: "Model Router (preview)". GA since 18 November 2025.
- `ML_CORE.md`: fine-tune "Phi-4-mini or GPT-4o-mini class" in Foundry. Phi-4-mini is not in Foundry's managed fine-tuning list; gpt-4.1-mini, gpt-4.1-nano and gpt-4o-mini are.
- `TOP7_IDEAS.md` and `THE_IDEA.md`: Google's docs say the Live API is "unsuitable for play-by-play in high-speed sports." No such official sentence exists. The verified facts are a 1 frame-per-second cap and a 2-minute cap on audio-plus-video sessions.
- `WHYLINE_45DAY_MASTERPLAN.md`: Singular.live free tier "10,000 daily calls". It is 5,000; Data Streams are "Trial" on Free.
- `TOP7_IDEAS.md`: a "YOLO26 variant" on the Roboflow football project. No YOLO26 model is published there.

---

## Part A — External dependencies verified

### A.1 Summary table

| # | Dependency | Exists | Verified how | Version / date | Licence | Blocks plan if missing | Notes |
|---|---|---|---|---|---|---|---|
| 1 | gfootball on PyPI | Yes, stale | PyPI JSON | 2.10.2, Jan 2022; Windows-only wheels; sdist for others | Apache-2.0; engine Unlicense | Yes for "two worlds" | Deps `gym>=0.11` on PyPI but master pins `gym<=0.21`; expect API breakage with modern gym. |
| 2 | gfootball GitHub repo | Yes, archived | GitHub API + HTML | Archived 19 Aug 2026; last code commit Apr 2022 | Apache-2.0 | — | Repo description points to `research-football.dev`. |
| 3 | `pip install gfootball` on this Mac | **Failed** | Three spikes run | — | — | Yes for local dev | Fails before cmake: `setup.py` shells out to `python3 -c "import psutil"` outside the build env. With psutil and `--no-build-isolation`, fails on missing `cmake` and SDL2 extras. |
| 4 | gfootball Docker route | Partial | Dockerfile read; daemon not running here | Ubuntu 20.04 base, installs cmake, SDL2, boost, xvfb | Apache-2.0 | Medium | Not built here. Only credible install path on Linux x86-64. |
| 5 | gfootball full positions in observations | **Yes** | `doc/observation.md` | — | — | — | `left_team`, `right_team` (x, y), directions, `ball` (x, y, z), tired factor, roles, `ball_owned_*`. 3000 steps per match at 10 steps/s. |
| 6 | gfootball `get_state` / `set_state` | **Yes** | `football_env_core.py` source | — | — | — | Opaque pickled engine state; `reset()` first; docs say it is for checking outcomes of different actions. Branching is real. |
| 7 | gfootball headless 3D render and video | Partial | `config.py`, `observation_processor.py`; EnvPool docs | 1280×720, avi/webm via OpenCV | — | Medium for footage | Rendering "slows down step significantly"; EnvPool refuses to support rendering: "does not produce reliable output across supported CI platforms." |
| 8 | gfootball steps per second | Partial | Paper figure | ~1,620 steps/s on 6 cores ≈ 270/core (INFERRED arithmetic) | — | — | One match ≈ 11 s per core headless. No single-core benchmark published. |
| 9 | `research-football.dev` successor | **No, dead** | DNS on three resolvers, Wayback | Last capture May 2020 | — | — | Was an ELO matchmaking server, never a simulator. |
| 10 | EnvPool gfootball | Yes, new | PyPI JSON, source | 1.2.7, 15 Sep 2026; wheels for py3.12–3.14 incl. macOS arm64 | Apache-2.0 | — | Proves the engine compiles in 2026, but exposes only a 72×96 minimap, one controlled player, no render, no state save. Not usable for tracking data. |
| 11 | GRF_MARL / Light-MALib 11v11 weights | **Yes, in repo** | Treeless clone, `git ls-tree`, pickle string inspection | last commit May 2024; Python 3.9, torch 1.13, `gym==0.22`, `ray==1.8` | Apache-2.0 | — | `light_malib/trained_models/gr_football/11_vs_11/{beat_bot, defensive_passer, flank_pass, group_pressure, offensive_passer}/actor.pt` (~400–510 KB each, MAPPO MLP 256-128-64, 19 actions). Controls 10 outfield players; keeper is built-in. |
| 12 | DB-Football weights | Partial | Repo listing + Drive folder | Jan 2024 | Apache-2.0 | — | No `.pt` in repo; on Google Drive. README: policies beat the bot "taking advantage of glitches in built-in logics." |
| 13 | TiZero weights | Yes | Repo + PyPI | `submission/tizero/actor.pt` 3.4 MB, Sept 2023 | Apache-2.0 | — | GRU policy; keeper rule-based; training code not released. Gameplay video on YouTube. |
| 14 | TiKick weights | Yes, off-repo | README + Drive | Aug 2022 | Apache-2.0 | — | Plain BC baseline reported at 0.834 win rate vs built-in AI. |
| 15 | SkillCorner open data | Yes | LICENSE, README, repo tree | 20 A-League matches (README says 10), 10 fps, Git-LFS ~90 MB each | **MIT** | — | Legally cleanest real tracking; broadcast tracking with extrapolated off-screen players. |
| 16 | DFL / Bassek 2025 | Yes | figshare API, PMC | 7 matches, 25 Hz, 2.6 GB XML | **CC BY 4.0** | — | Best full-pitch real tracking; attribution required. |
| 17 | StatsBomb / Hudl open data | Yes | LICENSE.pdf text | — | Bespoke: no commercial exploitation of "any analysis derived" | — | Events only; risky for a cash-prize product; useless for 10 Hz tracking. |
| 18 | Metrica sample data | Yes | README | 3 matches, 25 Hz | **No licence file** | — | Informal "acknowledge the source"; risky to redistribute derived models. |
| 19 | SoccerNet tracking / GSR data | Yes | NDA text | — | KAUST NDA: non-commercial research only, no distribution | — | **Do not use** for a product. |
| 20 | PFF FC 2022 World Cup | Yes, form-gated | Blog | — | No published terms | — | Unknown; assume all rights reserved. |
| 21 | Football behaviour model with public weights | **None** | Repos checked: FootBots, TranSPORTmer, TacticAI (no code), GenTac (empty repo), TacticGen (docs only), Ball Radar, MIDAS, CausalTraj (no LICENSE) | — | — | Yes: must train from scratch | Closest reusable code: Sports-Traj/UniTraj-pytorch (Apache-2.0, 1.77M params, checkpoints on Drive), MART (MIT), baller2vec++ (MIT). |
| 22 | Roboflow football-players-detection | Yes | Universe page (browser) | v20 RF-DETR Medium; 17 models | Dataset CC BY 4.0 | — | Needs account/API key for hosted or local inference. **No YOLO26 model.** |
| 23 | Roboflow pitch keypoints | Yes | Universe page | v17 RF-DETR keypoint preview, 317 images | CC BY 4.0 | — | — |
| 24 | `roboflow/sports` | Yes | GitHub API + raw files | main May 2025 | MIT; YOLOv8 weights AGPL-3.0 | Partial | Has homography (`ViewTransformer`), radar annotators, SigLIP team classifier; weights via gdown, no account. Uses `sv.ByteTrack`, removed in supervision 0.31.0 (Oct 2026): pin `<0.31` or use `trackers.ByteTrackTracker` (Apache-2.0). |
| 25 | RF-DETR | Yes | GitHub, PyPI | 1.11.2, Oct 2026 | Apache-2.0 (N/S/M/L); XL/2XL PML 1.0 | — | COCO weights auto-download; Python ≥3.10, torch ≥2.2. |
| 26 | `sn-gamestate` (SoccerNet GSR baseline) | Yes | GitHub, pyproject, Zenodo, HF | May 2026 | **GPL-3.0**; weights on Zenodo without registration; dataset ungated on HF | Partial | Pinned to Python 3.9, torch 1.13.1, mmcv 2.0.1: incompatible with RF-DETR in one env. The plan's "needs NDA" worry is wrong; the licence and pins are the real cost. |
| 27 | BroadTrack | Yes | arXiv, repo LICENSE | WACV 2025 | EVS non-commercial research licence | — | Not usable in a public demo without permission. |
| 28 | PnLCalib | Yes | repo | v1.0.0 | GPL-2.0, public weights | — | — |
| 29 | Sim-to-real evidence | Yes | SoccerSynth-Detection arXiv 2501.09281 v2 | Oct 2025 | — | — | Synthetic-only YOLOv8n transfers to real at AP50 88–89 in Unreal renders. Real-to-stylised-render direction unmeasured (INFERRED). |
| 30 | Gemini 4 Argon | Yes | ai.google.dev model + pricing | `gemini-4-argon`, Oct 2026 | Google ToS | — | Video in, structured output, agentic video; no Live API; $2/$10 per 1M until 30 Nov then $4/$20; no free tier. Video ≈ $0.012/min (low res) to $0.036/min (high). |
| 31 | Gemini 3.8 Flash | Yes | same | Sept 2026 | — | — | $0.75/$3.75 per 1M until 31 Dec then doubles; free tier exists; video ≈ $0.0045–0.0135/min. |
| 32 | Gemini Live 1 fps limit | **Yes** | Live docs | `gemini-3.8-live` stable | — | — | "max 1 frame per second" VERIFIED; audio+video sessions capped at 2 minutes. The "unsuitable for fast sports" quote is **not** official. Language count conflicts across pages (99/70/24). |
| 33 | ElevenLabs real-time TTS | Yes | elevenlabs.io/v4, pricing, help centre | `eleven_v4_turbo` ~100 ms; `eleven_flash_v2_5` ~75 ms | **Free tier is non-commercial and requires attribution**; Starter $6/mo is the floor for a public demo | Yes if on free tier | API ≈ $0.04 per 1K characters. |
| 34 | Azure Speech TTS / Voice Live | Yes, GA | Learn + Retail Prices API | api-version 2026-04-10 | Azure terms | — | Neural $15 per 1M chars; HD $22; free 0.5M chars/month. |
| 35 | Microsoft Agent Framework (Python) | Yes | `pip install` spike on Python 3.14 + `dir()` | `agent-framework-core` 1.22.0 (15 Oct 2026); GA 1.0 on 3 Apr 2026 | MIT | — | `WorkflowBuilder` with `add_edge`, `add_fan_out_edges`, `add_fan_in_edges`, `add_switch_case_edge_group`; `Executor`, `@handler`, `WorkflowContext`; `InMemoryCheckpointStorage`, `FileCheckpointStorage`; MCP tools in core. Metapackage `[all]` install stalled >16 min; install core plus named extras. |
| 36 | `RequestInfoExecutor` | **No** | import spike | — | — | Name wrong | HITL is `await ctx.request_info(...)` + `@response_handler`; resume with `workflow.run(responses={...})`. |
| 37 | Orchestrations (Sequential, Concurrent, Handoff, GroupChat, Magentic) | Yes | PyPI + Learn | `agent-framework-orchestrations` 1.3.2, separate package | MIT | — | Builders import from `agent_framework.orchestrations` once installed. |
| 38 | `CosmosCheckpointStorage` | Yes | PyPI + Learn | `agent-framework-azure-cosmos` 1.0.0b261015 (**beta**) | MIT | — | Pickle with restricted unpickler; partition key `/workflow_name`. |
| 39 | A2A, AG-UI, provider clients | Yes | PyPI + Learn | a2a beta; ag-ui 1.6.0 (labelled Preview); anthropic beta; gemini beta (native SDK, not OpenAI-compatible); openai 1.17.0 stable | MIT | — | `agent-framework-mcp` does not exist; `HostedMCPTool` not exported; use `client.get_mcp_tool()`. |
| 40 | Foundry Agent Service, hosted agents, Toolboxes | Yes, GA | Learn + devblogs | Hosted agents GA 9 Jul 2026 | — | — | Hosted vCPU $0.0994/h, memory $0.0118/GiB-h. `azure-ai-projects` 2.9.0. |
| 41 | Foundry Evaluations, custom evaluators | Yes | Learn | `azure-ai-evaluation` 1.18.9 | — | — | Custom evaluators carry a preview banner; created via `project_client.beta.evaluators`. |
| 42 | Foundry Tracing | Yes | Learn | — | — | — | GA for prompt and hosted agents; preview for workflow and external agents (which is what Agent Framework code is). |
| 43 | "Foundry Insights" | **No such product** | Learn | — | — | — | It is the Agent Monitoring Dashboard; metrics view is preview. |
| 44 | Routines | Yes, GA | devblogs 24 Sep 2026 | SDK still `project.beta.routines` | — | — | One trigger, one action; min recurrence 5 min. |
| 45 | Model Router | Yes, **GA** | Learn + Azure update | GA 18 Nov 2025 | — | — | Pool includes GPT-6 and Claude models (Claude deployed separately). |
| 46 | Fine-tuning small models | Partial | Learn fine-tuning overview, Retail API | — | — | Model names wrong | Fine-tunable: gpt-4.1, gpt-4.1-mini ($5/1M training tokens), gpt-4.1-nano ($1.50/1M), gpt-4o, gpt-4o-mini, gpt-oss, Llama-3.3-70B, Qwen3, Ministral-3B. **Not Phi-4-mini, not GPT-6.** Developer deployment has no hourly hosting fee (24 h lifetime). |
| 47 | Foundry Local | Yes, GA | devblogs 9 Apr 2026 | Windows, macOS arm, Linux x64 | — | — | `pip install foundry-local-sdk`; OpenAI-compatible server. |
| 48 | GPT-6 Luna / Sol / Astra, GPT-6.1 Sol in Foundry | Yes | Learn + Retail API | Sept 2026 | — | Quota | Luna $0.10/$0.50, Sol $2/$10, Astra $10/$50 per 1M. **Tier 0 (new) subscriptions have no GPT-6 quota.** |
| 49 | Claude Opus 5.5 in Foundry | Yes, GA | Learn | — | — | Subscription type | **Free-trial, student and credit-only subscriptions get 0 quota.** Paid pay-as-you-go required; billed via Marketplace. |
| 50 | Gemini in Foundry | **No** | Learn model lists | — | — | — | Use `GeminiChatClient` against Google directly. |
| 51 | Container Apps serverless GPU | Yes, GA | Learn + Retail API | — | — | Quota | T4 ≈ $0.26/h, A100 ≈ $1.90/h plus vCPU/memory; quota per managed environment; default only for PAYG/EA; may route to support. |
| 52 | Container Apps consumption | Yes | pricing page | — | — | — | Free grant 180k vCPU-s + 360k GiB-s + 2M requests/month; scale to zero. |
| 53 | Event Hubs, Cosmos DB, Web PubSub, Functions, Static Web Apps | Yes | pricing pages, Retail API | — | — | Web PubSub free tier too small | Event Hubs Basic $0.015/h, no free tier. Cosmos free tier 1,000 RU/s + 25 GB (not with serverless). **Web PubSub free: 20 connections, 20k messages/day**; Standard $1.61/unit/day. Functions 1M executions free. SWA free plan, Standard $9/mo. |
| 54 | Azure Load Testing | Yes, renamed **Azure App Testing** | pricing + Retail API | — | — | — | $10/resource/month plus $0.15 per virtual-user-hour; 10-VU minimum. |
| 55 | Azure MCP Server | Yes, GA | Learn, npm | npm `@azure/mcp` latest tag = 4.0.0-beta.1 | — | — | `npx -y @azure/mcp@latest server start`; pin a version. Needs `az login`. |
| 56 | azd | Yes | GitHub releases | 1.36.0, 15 Oct 2026 | MIT | — | — |
| 57 | Singular.live free plan | Yes | pricing page (rendered) | — | — | Partial | 1 user, 1 **watermarked** output, REST **5,000 calls/day**, Data Streams **"Trial"** on Free; Pro $150/mo. Data Stream API: WebSocket, "<300 ms", no rate limiters. |
| 58 | CasparCG Server | Yes | GitHub releases | 2.5.1-stable, 16 Sep 2026 | GPL-3.0 | — | HTML templates with `update(templatedata)` JSON. |
| 59 | OBS browser source | Yes | OBS kb | — | GPL-2.0 | — | Transparent by default. |
| 60 | HLS timed metadata via ffmpeg | **Partial** | ffmpeg docs + source | 8.0.1 here | — | Partial | **ffmpeg cannot author ID3 timed metadata**; it only passes through an existing `timed_id3` stream. The npm package `hls-timed-metadata` does not exist. hls.js has `FRAG_PARSING_METADATA` and metadata TextTrack cues; **`ID3_UPDATED` is not an event.** `DataCue` is Safari-only. |
| 61 | R3F / drei / three | Yes | npm | fiber 9.8.2, drei 10.7.9, three 0.186.1 | MIT | — | No licence-clean R3F football replay viewer exists; `immament/football-match-viewer` has no LICENSE file. Build the scene yourself. |
| 62 | Humanoid models and animations | Partial | licence pages | — | — | — | Mixamo: royalty-free commercial use, Adobe ID needed, no raw redistribution. Quaternius: now QAL v1.0 (free commercial, no standalone redistribution; pages still say CC0). Kenney: CC0 blocky characters. **No CC0 soccer player models on Sketchfab.** **Ready Player Me shut down 31 Jan 2026.** |
| 63 | Avatar presenters | Yes | pricing pages | — | — | — | Anam: commercial use not on Free; Starter $12. Tavus: Growth ~$0.31/min. HeyGen LiveAvatar: Free watermarked, 2-min sessions. D-ID: Launch $35/mo is the commercial floor. Gemini Live Avatar: no self-serve pricing (INFERRED). |

### A.2 Spikes run on this machine

| Spike | Result |
|---|---|
| `pip install gfootball`, Python 3.11, no deps | Fails at `build_ext` with `ModuleNotFoundError: psutil` inside the isolated build env (4 min, mostly download). |
| Same with psutil preinstalled and `--no-build-isolation` | Same error: `build_game_engine.sh` calls the literal `python3`, not the venv interpreter. With the venv first on PATH: `cmake: command not found`. |
| Full `pip install gfootball` on Python 3.14 | 32 minutes wall (60 kB/s network), same psutil failure; pip resolved `gym 0.26.2`, which gfootball's code does not target. |
| Docker | CLI 29.0.1 present, daemon not running. Image not built. |
| `pip install agent-framework` (metapackage) on Python 3.14 | Stalled >16 min resolving `[all]` extras; killed. `agent-framework-core` 1.22.0 plus named extras installed and imported cleanly. |
| Scripted physics rollout, numpy, B=200 | 150 steps (15 s): 4.2 s cold, ~0.2 s warm. 900 steps (90 s): 1.2 s warm. |
| Set transformer (4.7M params, 6 layers, d=256, batch 200 × 23 tokens), PyTorch 2.14.1 | CPU 80 ms per forward; Apple GPU (MPS) 20 ms. Per-tick 150 steps: 12 s CPU, 3 s GPU. Decision-only (15 calls): 1.2 s CPU, 0.3 s GPU. |
| API keys, `az`, `azd`, `gh` | None present on this machine. No API call was made. |

---

## Part B — The ML core, audited adversarially

### B.1 Behaviour model (set transformer, behaviour cloning)

**Will BC from RL agents yield plausible football?** Partly, with caveats a judge will notice.

- Evidence for: TiKick's plain multi-agent behaviour-cloning baseline, trained on 21,947 expert episodes from self-play, reaches a 0.834 win rate and +2.14 goal difference against the built-in AI (arXiv 2110.04507, VERIFIED). So a BC policy that plays competent gfootball is a solved problem given tens of thousands of episodes.
- Evidence against: the RL teams are optimised to win in gfootball, not to look like football. DB-Football's own README says its policies beat the bot "taking advantage of glitches in built-in logics" (VERIFIED). TiZero's goalkeeper is rule-based. The available GRF_MARL policies control 10 outfield players with the keeper built in. Expect a recognisable "RL style": relentless direct running, narrow shapes, repeated exploit patterns. Behaviour cloned from that inherits it.
- Autoregressive rollout stability: DAgger's Theorem 2.1 gives the classic bound, cost grows as T²ε under plain supervised imitation (VERIFIED). Le et al. 2017 report naive rollouts at "20–30 metres" error versus about 4 m with rollout-aware training on 3M frames at 10 Hz (VERIFIED). Published stable horizons: FootBots 4 s (ADE 2.04 m), TranSPORTmer 6.4 s one-shot, GenTac 5 s with 0.2 s causal windows, CausalTraj 4 s (VERIFIED). **The plan's 15 s per-tick horizon is 2.3 to 3.75 times longer than any published soccer result.**

**Data, size, time.** Published models: 2–20M parameters, 1–100M frames, ~100 epochs on one A100-class GPU (VERIFIED table in A2). 500 gfootball matches = 1.5M frames; 2,000 scripted-engine matches = 6M frames; together ~7.5M frames, a mid-range dataset. Training: 2–6 GPU-hours on an A10 for a 5–10M model (INFERRED). Data generation: one gfootball match ≈ 11 core-seconds headless (INFERRED from the paper's aggregate), so 500 matches ≈ 1.5 core-hours plus policy inference.

**Inference, measured.** 4.7M parameters, batch 200, 23 tokens: 80 ms per step on this CPU, 20 ms on the Apple GPU. An A10 would be perhaps 2–4× faster than MPS (INFERRED). Per-tick 15 s rollouts are therefore 3–12 s. Decision-only (policy called once per second, physics in between): 0.3 s on GPU, 1.2 s on CPU. **`ML_CORE.md`'s "under 5 ms per step on a GPU, about 40 ms on CPU" is wrong by 2–4×.**

**Most likely failure modes, ranked:** (1) loss of team shape and drift over >5 s, (2) implausible passes and teleporting ball handovers because actions and physics are learned separately, (3) off-policy collapse after a forced counterfactual action (see B.2), (4) RL-style play that an analyst immediately flags as "not football," (5) goalkeeper behaviour, which none of the open policies learn.

**Are the mitigations credible?** Yes, and they should become the design rather than the fallback:

- Learn on-ball decisions only (action type, target teammate, direction) from state; keep off-ball movement as a role-based physics prior with learned residuals at most. This is what makes decision-only inference possible and it removes the main drift source.
- Cap the learned horizon at 6–8 s, then hand off to a learned goal-in-horizon head. Decisions resolve within that window; the extra 7 s of rollout adds drift, not information.
- Train with rollout-aware loss (Le et al. 2017 style: schedule look-ahead from 1 to 10 steps) rather than pure teacher forcing.
- Measure and publish FDE at 4 s, shape-collapse rate, and a "teleport" count per rollout.

### B.2 Futures generator and counterfactual validity

**Is "force the first action, then sample" sound?** It is an intervention on the policy, which is the right object. The pitfall is covariate shift: after a forced action the state may be one the policy never saw, and its outputs there are undefined. The honest reading: the futures are **plausibility-weighted scenario samples**, not forecasts. Three guards make them defensible:

1. Only propose alternatives the policy itself assigns non-trivial probability to (say ≥ 5%). "Pass to the unmarked far-post runner" qualifies; "dribble through six defenders" does not. The Proposer LLM suggests; the policy's own probability filters.
2. A placebo test in CI: forcing the action that actually happened must reproduce the unforced branch's outcome distribution within noise. If it does not, the branching code is broken.
3. Report sample size, horizon and seed on screen, always.

**Exact evaluation protocol for calibration:**

- Hold out 300 matches. At every on-ball decision, run the unforced branch (n=200, horizon 8 s) and record P(goal for attacking team within horizon). Compare against the realised outcome in the held-out match. Report Brier score, log-loss, and a reliability diagram with 10 bins. Target Brier ≤ 0.18 against a base rate near 0.05 (INFERRED target; the plan's 0.18 is reasonable for this base rate).
- Sensitivity: n=50 vs 200 vs 1,000 on 100 moments; the swing estimate should stabilise by 200 or the number must rise.
- Cross-world agreement: run the same 100 moments in the scripted engine and the gfootball engine (if it exists); report correlation of the win-probability swing. Flag any explanation whose sign flips between worlds.
- Expert plausibility: 30 Sliding Doors cards rated 1–5 by two analysts, blind to world. TacticAI reported 45 of 50 suggestions rated favourable by Liverpool experts (VERIFIED); a comparable number is the credibility bar.

**A third option the plan missed.** gfootball itself can be the futures generator: `set_state` to the branch point, force the action, let the pretrained RL policies play 8 s, repeat. No learned model needed, no drift (the engine is the ground truth of that world). Cost: 200 branches × 80 steps = 16,000 env steps plus policy inference, ≈ 60 core-seconds at ~270 steps/s per core, so 5–10 s on a 12-core box (INFERRED). Too slow for a live 5-second cue; fine for near-line explanation 15 s after the moment, for half-time recaps, and for precomputing the demo. If the gfootball spike passes, this is the most honest counterfactual engine available and should be used for the headline numbers, with the learned model reserved for the live path.

### B.3 Outcome heads

Standard and low-risk. xG with defender geometry is what commercial providers do; pass completion, xT and win probability are textbook. Data: 2,000 scripted matches gives ~60k shots and ~2M passes, ample. Training: minutes with gradient-boosted trees.

Two ways a judge will notice they are wrong: (1) xG values that look nothing like public football (a 30 m shot at 0.25), because the simulator's shot model is miscalibrated; (2) win probability that ignores game state (0–1 down in the 89th minute at 40%). Mitigation: sanity-check the heads' marginal distributions against the SkillCorner and DFL event files (legal for validation) and publish the comparison.

### B.4 Moment embeddings and learned chaos

A full contrastive encoder is realistic in two days but not necessary. The simplest version that still counts as learned: a 128-dimensional autoencoder or a SimCLR-style encoder over the pitch-control grid plus hand-crafted features (team centroids, spreads, ball position, velocities), trained for an hour, followed by k-means with LLM-named clusters. Prior work exists for play-type embeddings in basketball and soccer (play2vec and similar; INFERRED, not verified in this audit). The learned chaos head (P(turnover within 10 s)) is a two-hour logistic model on the same features. Validate cluster labels against the engine's hidden phases; publish a confusion matrix.

### B.5 Fine-tuned narrator

Which models: gpt-4.1-mini (SFT $5 per 1M training tokens), gpt-4.1-nano ($1.50), gpt-4o-mini in Foundry's managed fine-tuning (VERIFIED). Phi-4-mini and GPT-6 are not fine-tunable there (VERIFIED). Cost for 20,000 lines × ~150 tokens × 3 epochs ≈ 9M tokens ≈ $45 on gpt-4.1-mini, plus a Developer deployment with no hourly fee for evaluation, or $1.70/h hosting for a live demo (VERIFIED prices). Generating 20,000 verified lines means a frontier model writing ~25,000 and the Fact Checker rejecting the rest: roughly $30–60 of tokens and a day of pipeline work.

Is it necessary? No. A few-shot frontier model with structured output and the Fact Checker gives the same verified lines at 2–4× the per-line cost, which is still cents per match. The fine-tune is a nice shipped artefact for the Foundry category and for the offline judge demo (Foundry Local can serve a Phi model but not this fine-tune; the fine-tune lives in Foundry). Keep it as a Sprint 5 item that can be cut without loss.

### B.6 The circularity objection, steelmanned

"You trained on synthetic play, so your counterfactuals only reflect synthetic football. The 'cost' of Okafor's shot is the cost inside a video game, not in the Premier League. Your 97% groundedness means the words match your own numbers, not reality. The hidden-truth evaluation is your simulator grading your simulator."

This is largely correct and cannot be fully refuted within the rules, because the rules forbid real match data in the project. What blunts it, in order of strength:

1. **Realism validation against real data, legally.** Compare the synthetic worlds' marginal statistics (player speeds, pass lengths, pass completion by distance, possession sequence lengths, shot locations, formation spreads) against SkillCorner (MIT) and DFL (CC BY 4.0). This uses real data to *validate*, not to train, which keeps "projects must use synthetic data" literally true. Publish the plots.
2. **Two independent worlds.** An explanation that holds in both the scripted engine and the RL-driven gfootball engine is not an artefact of either. This is the strongest argument for keeping the second world, if it installs.
3. **Expert ratings.** Two or three analysts rating explanations blind.
4. **Explicit framing on screen.** "In 200 simulated replays" rather than "would have." Honest language is also safer with judges from the Premier League.

Real-data pretraining would blunt it further but is **risky under the rules** (see C.4) and only two datasets are licence-clean. Do it only with written confirmation from the organisers.

### B.7 Compute and cost

| Item | Estimate | Basis |
|---|---|---|
| Behaviour policy training, 3 runs | 10–15 GPU-h | B.1 |
| Outcome heads, embeddings, chaos head | 2 GPU-h or CPU | B.3, B.4 |
| gfootball data generation, 500 matches + policy inference | ~3 core-hours per run; CPU only | A.1 row 8 |
| Vision fine-tune (RF-DETR Medium, 2,000 frames) | 3–5 GPU-h | A4 (INFERRED from RF-DETR docs) |
| Rollout calibration (held-out 300 matches × decisions) | 5–10 GPU-h | B.2 |
| **GPU total** | **25–35 GPU-h** | A10 serverless on Container Apps ≈ $1.90/h for A100, $0.26/h for T4 (VERIFIED) → **$10–70** |
| Frontier LLM tokens, development and evals | $150–300 | ~50M tokens mixed Luna/Sol/Claude (INFERRED) |
| Demo season, 6 languages, 10 matches | $10–30 | cents per match at Luna prices |
| Narrator fine-tune (optional) | $45 + $30–60 generation | B.5 |
| ElevenLabs Starter | $6/mo | A.1 row 33 |
| Azure runtime (ACA, Cosmos, Event Hubs, Web PubSub Standard, SWA) | $150–300 | A.1 rows 51–53; Web PubSub Standard needed for >20 clients |
| Fan study vouchers (40 × $10) | $400 | plan |
| **Total** | **$800–1,300** | consistent with the plan's own $800–1,350 |

Caveat: **new Azure subscriptions have no GPT-6 quota at Tier 0, no Claude quota on free or credit plans, and GPU quota only for pay-as-you-go** (VERIFIED). Confirm the subscription type before planning around Foundry models.

---

## Part C — System and plan audit

### C.1 Latency budget

| Stage | Realistic time | Notes |
|---|---|---|
| Event ingest to analytics (pitch control, heads) | 50–150 ms | numpy; fine |
| Scout (classifier + goal-in-horizon head) | 50 ms | code |
| Counterfactual, decision-only, GPU | 0.3–0.6 s | measured 0.3 s on Apple GPU for 15 calls |
| Counterfactual, decision-only, CPU | 1.2–2 s | measured 1.2 s |
| Counterfactual via gfootball engine | 5–10 s | INFERRED; near-line only |
| Proposer LLM (one call, Luna-class) | 0.8–2 s | INFERRED typical |
| Tactician LLM with 2–3 tool rounds (Sol/Claude-class) | 4–10 s | the budget killer |
| Narrator (Luna-class, structured) | 1–2 s | |
| Fact Checker | 50 ms | code |
| Localizer, 6 languages in one call | 2–4 s | |
| Director + Web PubSub publish | 150 ms | |
| **Full explained cue, serial** | **10–20 s p50; honest p95 ~25 s** | |

**The plan's "event to verified cue p95 under 5 s" is not realistic for the fully explained, localised cue.** It is realistic for a two-tier design: a **fast cue** in under 3 s (deterministic moment, template or Narrator-only line, English, verified) and an **explained cue** 10–20 s later that upgrades it with the counterfactual, the tactical story and the languages. Broadcasters already work this way (score bug instantly, analysis graphic a minute later). The plan should promise the two-tier SLO and demonstrate both numbers.

### C.2 Is it a multi-agent system or a pipeline with LLM calls?

A judge could argue pipeline, and for Scout → Narrator → Fact Checker → Localizer they would be right: that is a fixed DAG. What makes it legitimately multi-agent, and what to emphasise:

- **Tool-using Tactician** making its own decisions about which tools to call and how many rounds. This is agentic in the judges' sense. Keep it.
- **Director** making editorial decisions under constraints with state across viewers. Keep it, and log its reasons.
- **The Panel** (group chat with structured disagreement, mandatory tool citations, a chair). This is the only component where agents genuinely interact. Without it, the "Multi-Agent" category claim is thin.
- **Proposer**: fold into the Tactician unless the Panel exists; as a separate agent it is decorative.
- **Judge** (LLM story check): decorative on the live path; keep it as a CI evaluator.
- **Showrunner, Describer, Show Producer**: real only if the Living Season or Virtual Studio ship.

**Making failure recovery demonstrable, not theatre:** a chaos script that (1) starts a moment, (2) kills the `newsroom` replica between the Tactician's tool call and the Narrator step, (3) shows the Cosmos checkpoint ID, (4) restarts, (5) shows the same `cue_id` delivered with `resumed_from_checkpoint: true` in its metadata and the elapsed time. Run it in CI nightly and link the log from the README. Note that `CosmosCheckpointStorage` is a **beta** package (VERIFIED) and the file-backed store is the safer demo default.

### C.3 Person-days versus available

Assumptions: three people, 45 calendar days, five working days a week plus some weekends ≈ 38 working days each ≈ 114 person-days, minus ~15% for coordination, environment and video = **~97 effective person-days**.

| Sprint (plan) | Real person-days (my estimate) | Verdict |
|---|---|---|
| 1: 7-day product plus two spikes | 21 available; needs ~24 for everything listed | **At risk**; achievable if the Fan App is a mode switch and the Studio is minimal |
| 2: Two worlds, Oracle, Panel, A2A, AG-UI, HLS, Singular, CasparCG, OBS, eval harness | needs ~30 | **Unrealistic as listed**; HLS/CasparCG/Singular is a week on its own (ffmpeg cannot author ID3) |
| 3: Unmute, Director's Cut 3D, learned models, pilot study | needs ~35 | **Unrealistic**; Director's Cut alone is 15 person-days for a competent R3F developer |
| 4: Living Season, Pitchwatch, Virtual Studio, main study | needs ~35 | **Unrealistic** |
| 5: Open Pitch second submission, enterprise hardening | needs ~20 | **At risk** |
| 6: Evidence, video, submission | needs ~15 | Achievable |
| **Total** | **~160** | versus ~97 available |

**Seven-day horizon (21 person-days).** Minimum credible submission: scripted Kickoff engine with hidden truth, pitch control and indices, scripted-physics Sliding Doors (verified at 1.2 s for 200 × 90 s), one newsroom path (Scout → Tactician-lite → Narrator → Fact Checker → Director) with template fallback, one broadcast overlay page with the ghost trail and swing bar, replay mode without Azure, one Azure deploy, a 2-minute video. No learned models. This is `WHYLINE_PROPOSAL.md` and it is achievable.

**31-day horizon (~65 person-days).** Add: learned on-ball policy from the scripted engine (and gfootball if the spike passes), decision-only GPU rollouts with calibration plots, outcome heads, the Panel with grounding, Unmute voices on Starter-tier ElevenLabs, Fan App, kill-switch demo, evaluation tables. Skip: Director's Cut 3D (use a polished 2.5D with camera pans), HLS in-band metadata (use sidecar JSON over Web PubSub and an OBS browser source), Virtual Studio, Living Season, Pitchwatch vision, second submission.

**45-day horizon.** Add to the 31-day version: a stylised 3D replay for Sliding Doors moments only (not a full per-viewer broadcast), the Fourth Official (offside and foul geometry; high legibility for low cost), the fan study with n≈30, Pitchwatch as a measured adapter with Gemini 4 Argon tagging rendered clips, and the Open Pitch second submission only if a fourth person joins.

### C.4 Rules compliance

| Rule | Risk | Where the plan is exposed | Fix |
|---|---|---|---|
| Synthetic data only | **Medium** | Real-data pretraining (B.6); SkillCorner/DFL used for anything beyond validation | Validate only; ask organisers in writing before training on real data |
| Third-party licences | **Medium** | `roboflow/sports` YOLOv8 weights are AGPL-3.0; `sn-gamestate` is GPL-3.0; BroadTrack is non-commercial; ElevenLabs Free is non-commercial with attribution; Quaternius is QAL not CC0; GenTac data will be NC | Use RF-DETR (Apache) and `trackers` (Apache); avoid sn-gamestate and BroadTrack; ElevenLabs Starter; keep a LICENSES.md |
| No trademarks | Low | Fictional league from day 1; do not show Premier League marks in the video | Audit the video frame by frame |
| No copyrighted music | Low | — | Generated or none |
| Public GitHub repo | Low | — | Public from day 1; private branches fine |
| New project after 29 Sep 2026 | None | — | Folder is empty today |
| Judges may test | **Medium** | Cloud path needs the team's Azure; GPU rollouts need a GPU | Hosted demo kept alive through 10 Nov with scale-to-zero; replay mode with cached model outputs that runs on a laptop; written testing instructions |
| Multiple submissions "substantially different" | Medium | Open Pitch shares the engine | Separate repo, name, video, audience; state the relationship |
| Projects visible to all entrants | — | Nothing to hide; the moat is execution | — |
| Deadline | **Unresolved** | Rules say 27 Oct; banner says 21 Nov | Confirm on the Projects page today; tag a submission at day 7 regardless |

### C.5 Two worlds: worth it?

Value: emergent play from RL teams (not scripted by us), free rendered footage with ground truth, an independent world for cross-validation, and an honest counterfactual engine via `set_state` (B.2). Those are real and they answer the circularity objection better than anything else available.

Cost: archived repo; no Linux or macOS wheels; `pip install` fails on a clean machine before cmake runs (VERIFIED, three spikes); 2022-era pins (`gym<=0.21`, Python 3.9-era RL repos with `ray==1.8`); headless rendering explicitly disclaimed by the only active fork; Docker on Linux x86-64 is the only credible path; GRF_MARL policies need their own feature encoders and a Python 3.9 environment.

Verdict: **worth exactly one time-boxed day on a Linux machine with Docker.** If, by the end of that day, one 11v11 match runs headless with a GRF_MARL policy and dumps a trace, keep it as a batch data and footage source and as the near-line counterfactual engine. If not, drop it and never look back. It is a distraction only if it is allowed to bleed past the gate.

### C.6 Unproven claims and the artefact that would prove each

| Claim in the plan | Proving artefact |
|---|---|
| "200 futures in under a second" | Benchmark script, hardware named, p50/p95 table in README |
| Counterfactuals are calibrated | Reliability diagram and Brier score on 300 held-out matches |
| State detection F1 ≥ 0.75 in both worlds | Confusion matrices per world |
| Fact Checker catches 100% of planted errors | The planted-error test suite in CI with its log |
| Groundedness ≥ 0.95 | Foundry Evaluations run ID and exported table |
| Cue latency p95 < 5 s | App Insights query over 10 matches, two-tier numbers |
| Recovery from a killed agent | Chaos script output with checkpoint ID and cue ID |
| Overlay sync error ≤ 120 ms | Harness that stamps frame time vs cue time, 200 samples |
| Multilingual fidelity | Native-speaker rating sheet (5 languages, 2 raters) |
| Fans understood and trusted more | Pre-registered study protocol, raw responses, analysis notebook |
| "Dugout called it" | Log of recommendations vs subsequent events across the demo season |
| Vision accuracy on rendered footage | mAP and event P/R table on 50 labelled clips |

---

## Part D — Red team

### D.1 Ten ways it fails, ranked by probability × impact

| # | Failure | P | Impact | Early-warning signal |
|---|---|---|---|---|
| 1 | Learned rollouts look like a video game glitch; counterfactuals read as fiction | High | Critical | Day-14 clip review: teleports, players bunching, keeper frozen |
| 2 | Scope sprawl; nothing is polished by submission | High | Critical | Day 14 with more than four features in progress |
| 3 | Deadline is actually 27 Oct | Unknown | Critical | Projects page shows a countdown |
| 4 | gfootball never installs; week lost | Medium | High | Docker build not green by end of day 2 |
| 5 | Latency: explained cues arrive 20 s late and the demo feels sluggish | High | Medium | First end-to-end run above 10 s p50 |
| 6 | Azure quota blocks GPT-6, Claude or GPU | Medium | High | Portal shows Tier 0 or 0 TPM; GPU quota request pending |
| 7 | Licence breach in the public repo (AGPL weights, non-commercial TTS) | Medium | High | `pip freeze` and asset list not reviewed by day 7 |
| 8 | Demo recording fails because live LLM and GPU calls are flaky | Medium | Medium | No replay-with-cached-outputs mode by day 21 |
| 9 | Judges cannot run it (Azure creds, Python 3.9 pins for GSR) | Medium | Medium | No clean-machine test by day 35 |
| 10 | The real-data pretraining is judged non-compliant | Low–Medium | High | No written answer from organisers |

### D.2 Cheapest spikes, and what was already run

| Risk | Spike | Hours | Status |
|---|---|---|---|
| 1 | BC on 50 scripted matches, 8 s rollouts, eyeball 20 clips | 4 | Not run (needs the engine) |
| 1 | Decision-only rollout timing | 2 | **Run.** 0.3 s GPU, 1.2 s CPU for 15 calls at batch 200 |
| 4 | gfootball Docker build on Linux | 6–8 | **Partially run on macOS: fails** (psutil shell-out, no cmake). Docker daemon was not running here |
| 4 | Confirm GRF_MARL weights load | 1 | **Run.** In-repo `actor.pt` files verified by listing and pickle string inspection; not executed |
| 5 | Serial latency of one explained cue with real LLM calls | 1 | Not run (no API keys here) |
| 6 | Check subscription tier and GPU quota in the Azure portal | 0.5 | Not run (no Azure login here) |
| 7 | `pip freeze` plus asset licence list | 1 | Partially: all licences recorded in Part A |
| 2 | Scripted 200 × 90 s rollout cost | 0.5 | **Run.** 1.2 s warm on CPU |
| Framework | Agent Framework imports | 1 | **Run.** Core 1.22.0 and extras import; `RequestInfoExecutor` absent |

### D.3 What to cut at day 14 if behind

1. **First:** Director's Cut 3D broadcast, Virtual Studio, Living Season, Pitchwatch vision, Open Pitch. Keep 2.5D with camera pans and one 3D replay shot for the video if a developer has it nearly working.
2. **Second:** the learned behaviour model on the live path. Keep the scripted engine for live Sliding Doors and run the learned (or gfootball) counterfactuals near-line for the recap and the video. Keep outcome heads, which are cheap and visibly ML.
3. **Third:** the Panel and Unmute voices. Keep one narrator voice and the Tactician; the Multi-Agent story then rests on Tactician tool use, Director decisions and the kill-switch recovery.

Never cut: the Fact Checker, the replay mode, the evaluation tables, the video.

### D.4 The strongest rival approach, steelmanned

A rival team with the same brief builds "the perfect version of the template": a tight synthetic generator, a deterministic analytics layer, one excellent Tactician with tools, a code Fact Checker, six languages, and then spends 80% of its time on a broadcast-grade product: flawless 1080p overlays, a producer console with veto and audit, Foundry Agent Service for every agent, Evaluations in CI, Routines for recaps, hosted agents, A2A endpoints, Fabric Eventhouse for analytics, azd one-command deploy, and a cinematic video. No counterfactuals, no learned model, no risk. Every Microsoft hero technology, used visibly. Category: Best Enterprise or Best Foundry.

Does WHYLINE beat it? **On the Grand Prize, yes, if Sliding Doors works and is calibrated**, because the rival cannot answer "why did it matter" and the judges' own text asks for it. **On execution risk, the rival wins**, because WHYLINE's distinctive component is also its most fragile. The implication is not to drop Sliding Doors; it is to build the rival's product *first* (that is the 7-day plan) and add Sliding Doors on top, so that a failed learned model still leaves a top-quartile entry.

---

## Part E — Verdict

### E.1 Go / no-go

**Go with changes.** Build the 7-day product first, as the floor. Make Sliding Doors scripted-physics on the live path from day 3, so the headline feature exists before any model is trained. Replace the per-tick learned rollout with a decision-only policy, capped at 6–8 s, on a GPU, with calibration published. Treat gfootball as a one-day gated spike on Linux; if it passes, use it as the data, footage and near-line counterfactual source, never on the live path. Promise a two-tier latency SLO. Cut the 45-day plan to the minimum viable version below and add back features only when the previous one is polished. Confirm the deadline and the Azure subscription type today.

### E.2 Confidence

| Statement | Confidence |
|---|---|
| The ML core, redesigned (decision-only policy, 6–8 s, outcome heads, embeddings), is achievable in 45 days | Medium |
| The ML core as written in `ML_CORE.md` is achievable in 45 days | Low |
| A credible demo exists by day 7 | High |
| The rules are satisfied on the synthetic-only path | High |
| The rules are satisfied with real-data pretraining | Medium |
| The idea is differentiated against the field | High |

### E.3 The minimum viable version I would bet on

**Models.** (1) Scripted Kickoff engine with batched physics and hidden truth. (2) Learned on-ball decision policy (set transformer, ~5M params) trained by behaviour cloning on 2,000 scripted matches, plus 500 gfootball matches if the spike passes; called once per second; off-ball movement from the physics prior. (3) Outcome heads: xG with defender geometry, pass completion, win probability, goal-in-8-s. (4) A learned phase/chaos head over pitch-control features (autoencoder + k-means + logistic head). (5) Frontier LLM (Claude Opus 5.5 or GPT-6.1 Sol via Foundry on a pay-as-you-go subscription) for the Tactician and the Panel; GPT-6 Luna or Gemini 3.8 Flash for Narrator and Localizer. (6) ElevenLabs Starter for one commentator voice per language. No vision models, no fine-tune, no world model.

**Features, in build order.** Week 1: engine, pitch control, scripted Sliding Doors, Scout → Tactician → Narrator → Fact Checker → Director, overlay page with ghost trail and swing bar, replay mode, azd deploy, video v1, **tag v0.1**. Week 2: outcome heads, decision policy v1, decision-only GPU rollouts, calibration plot, Fourth Official (offside and foul geometry), Fan App modes. Week 3: the Panel with mandatory tool citations and a chair, Unmute voices, kill-switch chaos script, Web PubSub Standard, evaluation tables, **tag v0.3**. Week 4: gfootball-backed near-line counterfactuals for recaps if available, Oracle threat front from the same rollouts, stylised 3D replay for Sliding Doors moments only, expert ratings, fan pilot (n=6). Week 5: fan study (n≈30), realism validation against SkillCorner and DFL (validation only), polish, README with every artefact in C.6, **tag v0.5**. Week 6: video v2, clean-machine test, submission, buffer.

**Screens.** Broadcast overlay (OBS browser source), Studio console (blackboard, agent trace, Why? drawer, veto, kill switch), Fan App (mode, club, player, language, voice). Nothing else.

**Cut lines.** If the decision policy does not produce watchable 8-second rollouts by day 14, Sliding Doors stays scripted-physics and the learned model is dropped from the demo and kept as a documented experiment. If gfootball is not green by day 2, it is gone. If the Panel's latency exceeds 15 s by day 21, it becomes a half-time feature only. If fewer than 20 fans are recruited by day 28, the study becomes an expert panel of three.

### E.4 Claims in the documents that are wrong or unverifiable

| Document and quote | Status | Correction |
|---|---|---|
| `ML_CORE.md`: "Inference for 200 parallel worlds: under 5 ms per step on a GPU, about 40 ms on CPU." | Wrong | Measured 20 ms (Apple GPU) and 80 ms (CPU) for 4.7M params at batch 200. |
| `ML_CORE.md`: "200 futures of the next 15 seconds in well under a second." | Wrong as written | Per-tick: 3–12 s. Decision-only: 0.3 s GPU, 1.2 s CPU. |
| `ML_CORE.md`: "the simpler autoregressive version, which is enough for 10–20 second horizons" | Unsupported | Published stable horizons are 4–6.4 s; nothing beyond ~5 s is reported stable for soccer. |
| `ML_CORE.md`: fine-tune "Phi-4-mini or GPT-4o-mini class" in Foundry | Partly wrong | Phi-4-mini is not fine-tunable in Foundry; gpt-4o-mini and gpt-4.1-mini are. |
| `ML_CORE.md`: "Google Research Football with pretrained 11v11 RL teams (DB-Football / Light-MALib policies, TiZero-class play)" | Partly right | GRF_MARL has in-repo weights; DB-Football's are off-repo; the policies "take advantage of glitches" per their authors; keeper is built-in. |
| `WHYLINE_45DAY_MASTERPLAN.md`: "Google Research Football is archived but still installable, renders 3D frames, exposes full positions and supports state save/restore" | Partly right | Positions and state save/restore: verified. "Still installable": fails on a clean machine via pip; Docker on Linux only. 3D rendering headless: disclaimed by EnvPool, unverified. |
| `WHYLINE_45DAY_MASTERPLAN.md`: a "successor 'research-football.dev' game server exists" | Wrong | Dead domain; was a matchmaking league, not a simulator. |
| `WHYLINE_PROPOSAL.md`: "`RequestInfoExecutor` for producer approval" | Wrong | Use `ctx.request_info()` and `@response_handler`. |
| `WHYLINE_PROPOSAL.md`, `TOP7_IDEAS.md`: "Model Router (preview)" | Stale | GA since 18 Nov 2025. |
| `WHYLINE_PROPOSAL.md`: "Insights preview" | Wrong name | Agent Monitoring Dashboard; metrics view preview. |
| `WHYLINE_PROPOSAL.md`: "What's new in Microsoft Foundry, September 2026" cited as a source | Unverifiable | The audit agent found no such post as of 21 Oct 2026; the latest roundup is July–August (posted 9 Sep). An earlier fetch in this session returned content at that URL, so treat the September claims (GPT-6 pricing, Routines GA) as confirmed elsewhere but the post itself as unconfirmed. |
| `TOP7_IDEAS.md`, `THE_IDEA.md`: Google's docs say the Live API is "unsuitable for play-by-play in high-speed sports" | Wrong attribution | No official sentence. Verified: 1 fps cap and 2-minute audio+video session cap. |
| `WHYLINE_45DAY_MASTERPLAN.md`: Singular.live free tier "10,000 daily calls" | Wrong | 5,000 calls/day; Data Streams "Trial" on Free; output watermarked. |
| `WHYLINE_45DAY_MASTERPLAN.md`: "HLS packager (ffmpeg or a small Go service) that injects ID3/emsg" | Wrong for ffmpeg | ffmpeg cannot author ID3 timed metadata. Use sidecar JSON over Web PubSub, WebVTT metadata cues, or EXT-X-DATERANGE post-processing. |
| `TOP7_IDEAS.md`: "a YOLO26 variant was published" on the Roboflow football project | Wrong | No YOLO26 model on that project. |
| `WHYLINE_PROPOSAL.md`: "ByteTrack" via supervision examples | Stale | `sv.ByteTrack` removed in supervision 0.31.0; use `trackers.ByteTrackTracker`. |
| `WHYLINE_45DAY_MASTERPLAN.md`: `sn-gamestate` "open but fiddly" | Understated | GPL-3.0; Python 3.9 and torch 1.13.1 pins; incompatible with RF-DETR in one environment. |
| `ML_CORE.md`: "public open real tracking data (SkillCorner open data, Metrica sample) for a small fine-tune" | Partly wrong | Metrica has no licence; only SkillCorner (MIT) and DFL (CC BY 4.0) are clean; the hackathon-rules reading is risky either way. |
| `WHYLINE_PROPOSAL.md`: Kickoff target "200 × 60 s rollouts in < 800 ms on one vCPU" | Nearly right | Measured 1.2 s for 200 × 90 s warm on this CPU; 60 s would be ~0.8 s. |
| `WHYLINE_45DAY_MASTERPLAN.md`: ElevenLabs as the default voice | Risky | Free tier is non-commercial with attribution; budget Starter. |
| `WHYLINE_45DAY_MASTERPLAN.md`: "Foundry hosts GPT-6 / Claude" for a hackathon team | Conditional | True only on a paid pay-as-you-go subscription; Tier 0 and free/credit subscriptions have no GPT-6 or Claude quota. |
| `WHYLINE_45DAY_MASTERPLAN.md`: "Azure Load Testing" | Renamed | Azure App Testing. |

---

*Scratch artefacts for this audit (reports A1–A4 with URLs and raw command output, install logs, benchmark scripts, treeless clones, pickle string dumps) are in the session scratchpad under `audit/` and `spikes/`. Nothing other than this report was written to the project folder.*
