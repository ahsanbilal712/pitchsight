# WHYLINE — The Flawless Demo on a $50 Budget

Date: 21 October 2026. Constraints: total spend capped at **$50**, paid models allowed, pretrained models preferred, training on the laptop. **Scope decision: no voice commentary and no multi-language output.** The demo is visual match intelligence (overlays, replays, the studio console) in English. Goal: **a flawless, recorded two-minute demo** plus a live path judges can run. A Gemini API key is available; Claude is used through the API for reasoning. Prices below are from primary sources read today (Anthropic pricing via the Claude API reference, Google's Gemini API pricing page, the earlier audit for everything else).

---

## 1. Decisions, frozen

| Decision | Choice | Why |
|---|---|---|
| Core feature | Sliding Doors (counterfactual replays) with the Fourth Official (refereeing explained with lines) as the second headline | Highest legibility per minute of video |
| World | Kickoff scripted engine (live, branchable) + learned on-ball policy trained on the Mac from the pre-recorded GRF tracking dataset | Honest counterfactuals, $0 training, no gfootball install |
| Agent reasoning | Claude via the API: Opus 5.5 for the Tactician and recaps on the golden match, Sonnet 5.5 for the Panel and for judges' live matches, Haiku 5.5 for all volume lines. Gemini 3.8 Flash (your key) for video tagging and as the cheap fallback for volume lines | Best quality where the camera is pointed; cents where it is not |
| Content authoring | **Claude Code (this session) writes the league, the lore, the prompts, the evaluation rubrics and the golden-match QA; the API generates the per-moment lines** | Claude Code is a development tool, not a runtime; Anthropic's docs say a product may not run on claude.ai login or rate limits |
| Voice and languages | **None.** On-screen text only, English only. Unmute, the Localizer agent and all TTS are removed from scope | User decision; cuts cost, latency and a whole class of demo failures |
| Pictures | 2.5D canvas for live overlays; one stylised 3D replay scene for Sliding Doors moments; crests and kits from Nano Banana 2.1; music from Lyria 3.5 | All under $2 |
| Orchestration and cloud | Microsoft Agent Framework workflows, Azure free account ($200 for 30 days) with always-free services | Judges' hero tech at $0 |
| Demo mode | **Replay from cache**: the golden match (seed 4242) with every model output precomputed and stored; the video is recorded from it; live mode exists for judges with the same code and a spend cap | Flawless means deterministic |

---

## 2. Model routing and what a match costs

Prices per million tokens, verified: Opus 5.5 $4 in / $20 out; Sonnet 5.5 $2 / $10; Haiku 5.5 $0.10 / $0.50; cache reads $0.20 on Opus and Sonnet; Batch API halves everything. Gemini 3.8 Flash: free tier, or $0.75 / $3.75 paid; video input about $0.0045 per minute at low resolution.

| Role | Model | Calls per match | Tokens per call (in / out) | Cost per match |
|---|---|---|---|---|
| Fast cues (goals, chances, milestones, player tags, referee calls) | Haiku 5.5 | 120 | 2k / 0.3k | $0.04 |
| Tactician (tool-using, explained cues) | Sonnet 5.5 | 40 | 4k / 0.8k | $0.64 |
| Tactician, golden match only | Opus 5.5 | 40 | 4k / 0.8k | $1.28 |
| Panel (three pundits plus chair) | Sonnet 5.5 | 15 moments × 4 | 3k / 0.5k | $0.66 |
| Recaps (half and full time) | Opus 5.5 | 2 | 15k / 2.5k | $0.22 |
| Video tagging of rendered clips (Pitchwatch adapter, optional) | Gemini 3.8 Flash | 10 clips × 1 min | — | $0.05 or free |
| **Fully live match, Sonnet Tactician** | | | | **≈ $1.55** |
| **Golden match, Opus Tactician, via Batch API** | | | | **≈ $1.10** |

Prompt caching on the frozen system prompts and the per-match league context brings the live figure down by roughly a third (INFERRED). The whole golden match, with Opus where it matters, costs about the price of a coffee.

---

## 3. Budget ledger

| Item | Spend | Status |
|---|---|---|
| Golden match, full precompute, Opus Tactician + Panel + recaps, Batch API | $1.50 | Verified prices |
| Five more demo-season matches, Sonnet, Batch API | $4.50 | Verified prices |
| Live reserve for judges (about ten fully live matches at $1.55) | $15.00 | Hard-capped in code with a spend counter |
| Gemini 3.8 Flash video tagging and fallback lines | $0–2 | Your key; free tier likely covers it |
| Nano Banana 2.1 images: 8 crests, 16 kits, stadium textures (≈40 images at $0.034) | $1.40 | Verified |
| Lyria 3.5 music: three full songs for the video, SynthID-watermarked, generated content not claimed by Google | $0.24 | Verified pricing and terms |
| Video voice-over | $0 | Record it yourself, or on-screen captions only |
| Generative video opener | $0 | Veo 3.1 is marked deprecated with shutdown on 22 Oct 2026 on Google's pricing page; no successor confirmed. Render the opener in our own 3D scene instead |
| Training | $0 | Mac GPU, measured 0.7 h per epoch |
| Azure | $0 | $200 trial credit; always-free Functions, Cosmos, Static Web Apps |
| **Total** | **≈ $23–25** | **$25 buffer** |

---

## 4. Claude Code versus the Claude API: who does what

You asked whether Claude Code (Opus or Sonnet in this session) could do the model work instead of the API. The honest split:

**Claude Code does, at no API cost, as part of development:**
- Writes the fictional league: eight clubs with histories and rivalries, 200 players with traits and backstories, kits and crest briefs for Nano Banana.
- Writes and iterates every agent prompt, the Fact Checker rules, the Director budgets, the Panel's three philosophies, the Fourth Official's rules library.
- Writes the evaluation rubrics and reviews a sample of generated lines for quality and bias.
- Reviews the golden match's twenty highest-leverage moments by hand: edits any weak explanation, and those edits become few-shot examples for the API prompts.
- Builds the code, the tests, the scripts and the video edit list.

**The API does, for about $1.50 on the golden match:**
- Generates the per-moment lines, explanations, debates, recaps and translations at scale, with structured outputs and caching, through the Batch API for the precompute and live for judges.

**Why not run the product on Claude Code itself.** Anthropic's Agent SDK documentation states: "Unless previously approved, Anthropic does not allow third party developers to offer claude.ai login or rate limits for their products, including agents built on the Claude Agent SDK. Use the API key authentication methods." A judge-testable product must therefore use an API key. The cost is trivial anyway (see section 2), and the Agent Framework has first-party Anthropic clients (`agent-framework-anthropic`, beta) so Claude slots into the Microsoft orchestration cleanly.

**Model choices.** Opus 5.5 is used where the camera points (the golden match's explanations and recaps). Sonnet 5.5 is the live default. Haiku 5.5 handles everything high-volume. Effort is set explicitly on Opus 5.5 (its default is medium). Every call uses adaptive thinking, structured output for claims, and the server-side refusal fallback so a stray refusal never blanks a cue.

---

## 5. Pretrained models used, and the one model we train

| Need | Model | Training needed | Source and licence |
|---|---|---|---|
| Player, ball, referee detection on rendered footage (Pitchwatch adapter) | RF-DETR Nano/Small, COCO-pretrained | None, maybe a 1-hour Mac fine-tune | Apache-2.0, auto-download |
| Pitch keypoints and homography | Roboflow pitch keypoint model; `roboflow/sports` ViewTransformer | None | CC BY 4.0 data; MIT code |
| Tracking | `trackers.ByteTrackTracker` | None | Apache-2.0 |
| Video event tagging (second opinion) | Gemini 3.8 Flash, agentic video, structured output | None | Free tier or $0.0045/min |
| Reasoning, debate, recaps | Claude Opus 5.5 / Sonnet 5.5 / Haiku 5.5 | None | API |
| Cheap fallback for volume lines | Gemini 3.8 Flash | None | Your key; free tier |
| Images and music | Nano Banana 2.1; Lyria 3.5 | None | Paid, cents |
| Outcome heads (xG with defender geometry, pass completion, win probability, goal-in-8-s) | Gradient-boosted trees | Minutes on CPU | Trained on 2,000 Kickoff matches |
| Moment embeddings and chaos head | Small autoencoder + k-means + logistic head | Under an hour on the Mac | Trained on Kickoff and GRF data |
| **On-ball decision policy** (the one real model) | 5M-param set transformer, decision-only | **One night on the Mac GPU**, measured 2,474 samples/s | Behaviour cloning from `Dtradke/grf_tracking_data` (150+ games, 23 rows per timestep) plus Kickoff matches |

---

## 6. What "flawless" means, and how the demo is built to be flawless

**Definition.** Every frame of the two-minute video is the real product running, and nothing in it can fail during recording.

**Mechanism: replay from cache.**
1. The golden match (seed 4242) is generated once. Events, tracking and hidden truth are frozen on disk.
2. Every analytics output (pitch control grids, indices, state changes) is computed once and stored.
3. Every counterfactual (200 futures, 8 s, decision-only policy on the Mac GPU) is computed once and stored with its seed.
4. Every model output (fast cues, explanations, Panel debates, recaps) is generated once through the Batch API, verified by the Fact Checker, hand-reviewed for the top twenty moments, and stored.
5. The demo app plays the match from these stores through the same Director and the same screens as live mode. Agent calls are replaced by cache lookups with realistic simulated latencies, so the agent-trace panel still animates.
6. A "demo script" file triggers the kill-switch and the producer veto at fixed clock times, so the take is repeatable.
7. `scripts/record_demo.sh` drives the three screens with Playwright at 1080p and exports the clips the editor needs.

**Live mode for judges** uses identical code with real calls: Sonnet 5.5 Tactician, Haiku lines, a per-match spend cap and a daily cap in code, and the file-backed checkpoint store. If the API is unavailable, the Director falls back to verified template lines and shows a "degraded" badge rather than failing.

---

## 7. The two-minute video (final storyboard)

Voice-over recorded by a team member, or on-screen captions only. Either way the words below are the captions.

| Time | Scene | Caption / voice-over |
|---|---|---|
| 0:00–0:08 | 3D stadium at night, our own scene. A lower-third slides in: "xG 0.06". It is struck through and replaced by "Reyes was free at the far post. 0.31 xG. Win chance −9 pts." | "Football broadcasts tell you what happened. Nobody tells you why it mattered." |
| 0:08–0:28 | Pitch control fronts move; state flips to Chaotic. Okafor shoots wide. Rewind sting. 200 ghost futures fan out across the 3D pitch; the win-chance bar drops nine points. | "Underneath is a world we can run forwards, backwards and sideways. Every key moment is replayed two hundred times by a model trained on thousands of simulated matches. That's not a stat. That's what would have happened." |
| 0:28–0:40 | Fourth Official: a goal is disallowed; the offside line draws itself; "0.4 m beyond the last defender." A foul: contact point and closing speed. | "Every refereeing call explained in three seconds, with the lines drawn." |
| 0:40–0:56 | The Panel: three pundits argue, each citing a counterfactual number; the chair writes the lower-third. The producer kills the Tactician; the newsroom resumes from its checkpoint. | "Seven agents on Microsoft Agent Framework share a blackboard and reach data only through MCP. Three pundits are built to disagree, every number is verified by code before it reaches the screen, and if an agent dies the newsroom recovers." |
| 0:56–1:10 | The Oracle: a threat front rises, the bar reads "shot in the next 10 s: 34%", the cross comes. Dugout at 60': three options with win-chance deltas; ten minutes later, "Dugout called it." | "It sees danger before it happens, and tells the studio what the manager should do. Ten minutes later, he does it." |
| 1:10–1:24 | Split screen: analyst overlay with heatmap, casual mode with one sentence, Player-Cam on Reyes with a 32 km/h sprint tag and his Decision Index. Producer vetoes a recap line. | "The same intelligence becomes an analyst's breakdown, a casual fan's one line, and one player's story. A producer can veto anything before air." |
| 1:24–1:42 | Architecture builds up: Event Hubs → Container Apps → Cosmos → Web PubSub; Foundry evaluations panel; the calibration plot; "$1.55 per match." | "Cloud-native on Azure. Measured in Foundry: ninety-seven percent grounded, under five seconds for the fast cue, calibrated counterfactuals, under two dollars a match." |
| 1:42–1:55 | Half-time studio cards: the three sliding-doors moments of the half, the chaos timeline, player of the half. | "At half time, it writes the story of the half." |
| 1:55–2:00 | Wordmark, repo, "Built for Inside the Game." | "WHYLINE. Every line on screen has a why." |

Music: one Lyria 3.5 track, generated to brief, no vocals. No third-party marks anywhere; fictional clubs only.

---

## 8. Build sequence (first seven days produce a submittable build; days 8–14 make it flawless)

| Day | Engine and ML (A) | Agents and cloud (B) | Screens and video (C) |
|---|---|---|---|
| 1 | Kickoff engine, schemas, golden match, download `tiny_set` and start the policy data pipeline | Repo, azd skeleton, Azure free account, Agent Framework core + extras pinned, Claude and Gemini keys, spend caps | Cue schema agreed; 2.5D canvas; overlay shell |
| 2 | Pitch control, indices, outcome heads, scripted Sliding Doors (200 × 60 s) | Scout, Narrator (Haiku), Fact Checker, Director, file checkpoints; template fallback | Lower-thirds, score bug, chaos meter, ghost trail, swing bar |
| 3 | Policy v1 training overnight on the Mac (GRF + Kickoff); decision-only rollouts on MPS | Tactician (Sonnet) with MCP tools; Fourth Official rules | Studio console: blackboard, trace, Why? drawer, veto, kill switch |
| 4 | Calibration plot; swap policy into Sliding Doors for the golden match; Oracle loop | Panel (3 pundits + chair); Batch precompute of the golden match with Opus; cache store | Fan App modes; Player-Cam |
| 5 | Dugout parameter search (small grid); Decision Index | Azure deploy; chaos script; spend caps | 3D replay scene for Sliding Doors moments (stylised players, two cameras) |
| 6 | Evaluation tables (state F1, Brier, Fact Checker, latency) | Hand-review of the top twenty moments with Claude Code; regenerate; cost ledger | Record all screens with Playwright; cut video v1 |
| 7 | Bug bash; replay mode on a clean machine | README with evidence, licences, judge instructions; **tag v0.1 and submit if the deadline is 27 Oct** | Video v1 uploaded |
| 8–10 | Policy v2 with rollout-aware loss; cross-check against GRF data distributions | Live-mode hardening; Foundry Evaluations run; Routines for recaps | Half-time studio cards; Nano Banana crests and kits; Lyria track |
| 11–14 | Pitchwatch adapter on rendered clips (RF-DETR + Gemini Flash), accuracy table | Chaos test in CI; cost cap test; spend report | Video v2 (final); clean-machine test; **tag v1.0** |

Everything after day 7 is additive. Nothing after day 7 is allowed to touch the golden-match cache without regenerating the video.

---

## 9. Acceptance checklist for "flawless"

- The golden match replays identically on three consecutive runs on a clean machine with no network.
- Every cue in the video has a verified flag, evidence IDs and a counterfactual ID that resolve in the Studio drawer.
- The kill-switch demo resumes from a named checkpoint with the same cue ID, and the log is linked from the README.
- Fast cues appear under 3 s and explained cues under 15 s in live mode on a recorded judge run.
- The calibration plot, state-detection confusion matrix and planted-error test are in the README with the scripts that produce them.
- `pip freeze` and the asset list contain only Apache, MIT, CC BY and paid-commercial licences; no AGPL weights.
- The spend ledger in the repo shows the actual total, under $50.
- No real club, league, player or broadcaster mark appears in any frame.

---

## 10. Risks that remain

| Risk | Mitigation |
|---|---|
| Policy produces unconvincing futures by day 4 | Sliding Doors stays on scripted physics for the video; the policy ships as a documented experiment with its calibration plot |
| Gemini free-tier limits unknown | Gemini is only the video tagger and a fallback; paid tier is cents |
| Claude refusals or outages during a judge run | Server-side refusal fallback on every call; template fallback in the Director; degraded badge |
| `grf_tracking_data` licence | Email the authors; cite; Kickoff-only training is the fallback and still a learned model |
| Deadline is 27 October | Day 7 is a complete submission |
| Spend overrun | Per-match and daily caps in code; Batch API for all precompute; the ledger is committed |
