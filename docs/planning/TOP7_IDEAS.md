# Top 7 Ideas — Unconstrained Ideation for "Inside the Game"

Companion to `WHYLINE_PROPOSAL.md`. This document ignores the Microsoft stack until the very end. The question is only: **what is the most impressive, most useful AI football intelligence product that a small team can actually demo by 27 October 2026?**

---

## 0. What the second research pass changed

| Finding | Source | Why it matters for ideation |
|---|---|---|
| **49% of UK football fans sometimes mute commentary; 22% often; 38% of 18–24s often.** They replace it with fan commentary (23%), their own music (26%), radio (9%). | [AO study of 2,002 UK consumers, July 2026](https://www.advanced-television.com/2026/07/08/study-half-of-uk-football-fans-mute-the-commentary/) | The single most validated audience pain point I found. Young fans want to *curate* the match audio. A product that lets them choose who talks, how much, in which language, is not speculative. |
| Google's Live API processes video at **1 fps** and its docs say it is "unsuitable for play-by-play in high-speed sports." | [Gemini Live API reference](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/models/multimodal-live) | Vision cannot be the live hot path. But **speech-to-speech** relays work: a public project reaches 3.9 s median latency translating live commentary into 32 languages with `gemini-3.8-live` ([repo](https://github.com/kkrishnan90/Gemini-Live-Commentary-Translation)). |
| **Gemini 4 Argon** (released 13 Oct 2026): video, audio, image input; structured outputs; agentic video understanding; 1M context; text-only output; no Live API. | [Model page](https://ai.google.dev/gemini-api/docs/models/gemini-4-argon) | Best available offline/near-line video brain for auto-eventing on rendered clips. Not for live. |
| **ElevenLabs v4 Turbo**: ~150 ms time-to-first-speech, 32+ languages, real-time. v3 is more expressive but not real-time. | [ElevenLabs v4](https://elevenlabs.io/v4) | Real-time personalised voice commentary is technically trivial now. The hard part is *what* to say, grounded. |
| **SoccerNet 2026** tasks: Ball Action *Anticipation*, player-centric action spotting, novel view synthesis (3D Gaussian splatting), VQA (winners used Gemini 3.1 Pro). The game-state-reconstruction baseline (`sn-gamestate` on TrackLab, pretrained YOLOv8 + re-ID + calibration) is open but fiddly. | [SoccerNet 2026 results](https://arxiv.org/html/2607.07320), [sn-gamestate](https://github.com/soccernet/sn-gamestate) | *Anticipation* is now an academic frontier. A broadcast product that shows danger *before* it happens is new. |
| **TacticAI** went live for open play at Palmeiras (June 2026), predicting 8 s ahead; **GenTac** and **TacticGen** (April 2026) generate tactics as diffusion over trajectories. None are open-weight. | [TacticAI Nature](https://www.nature.com/articles/s41467-024-45965-x), [TacticGen](https://arxiv.org/abs/2604.18210v1) | The "AI assistant manager" is real at club level but has never been put on a broadcast for fans. |
| IBM Wimbledon 2026 shipped **Key Moments** ("which plays are shaping the match") and **Match Chat**. Google's World Cup Gemini tie-in let fans ask "why was that goal disallowed?" | [SVG](https://www.sportsvideo.org/2026/06/29/wimbledon-introduces-ai-powered-fan-features-modernized-digital-platforms-for-2026-championships/) | Explain + chat is now a product category. To impress, we need to go past "chat about stats" into things only a simulator can do. |
| Veo 3.1 image-to-video costs ~$0.40 per second, 4–8 s clips, minutes of latency. | [Pricing roundups](https://invideo.io/blog/ai-video-model-pricing) | Generative video can only be a pre-rendered garnish, never a live feature. |
| The 433 competing entries converge on: sim → stats → LLM narrator → verifier → localizer → timed cues → React studio. | Repos read in pass 1 | Anything on that list earns zero differentiation. |

**The strategic insight that falls out of all of this:** every competitor treats the simulator as a *data source*. The highest-leverage move is to treat it as a **physics engine you can branch, forecast and search**. That single capability powers three of the seven ideas below, and no entry I found has it.

---

## 1. The seven ideas

Each idea is written as a product, then scored. Scores are my honest estimate on the five judging criteria (★ out of 5) plus a seven-day feasibility rating. "Wrapper" is what the Microsoft layer would be if you choose that idea.

---

### Idea 1 — SLIDING DOORS: the counterfactual moment engine

**One line.** Every key moment is explained by re-simulating what would have happened otherwise, 200 times, and reporting the swing in win probability.

**The insight.** "Why did this moment matter?" is a counterfactual question, and the only honest way to answer it is to simulate the alternative. Because the match is synthetic, we own the physics, so we can branch it at any instant. No broadcaster can do this with real matches; a hackathon with synthetic data is the one place it is possible, which makes it the perfect hackathon idea.

**What the viewer sees.** A shot goes wide. The overlay shows the actual xG (0.06), then a ghost trail to the unmarked teammate (0.31 xG), and a win-probability bar that drops nine points. Click "Why?" and 200 translucent futures flicker across the pitch. At half time the recap lists the three "sliding doors" of the half.

**Pipeline mapping.** Ingest: batched 22-player engine. Interpret: pitch control, xT, win probability. Explain: counterfactual branches with evidence. Render: ghost trails, swing bars, recap cards. Personalise: analyst sees the distribution; casual fan sees one sentence; club fan sees "what we should have done".

**Heavy lifting (any stack).** numpy batched engine (`S[B,23,6]`); logistic win-probability model fitted on 2,000 simulated matches; Gemini 4 Argon or Claude Opus 5.5 for explanation prose with structured claims; Three.js ghost-trail render.

**Wrapper.** Agent Framework workflow for the explain loop, Cosmos for the blackboard, ACA for the engine service, Foundry Evaluations to publish counterfactual calibration.

**Novelty vs field.** Zero entries do this. It is also *legible*: a judge understands it in five seconds of video.

**Risks.** Rollout speed in Python (mitigate: batch dimension, 60 s horizon, precompute for the golden match). Explaining a counterfactual badly can look like fiction (mitigate: always show n, horizon, seed; always pair with evidence IDs).

| Tech | Agentic | Impact | UX | Category | Feasibility (7 days) |
|---|---|---|---|---|---|
| ★★★★★ | ★★★★ | ★★★★ | ★★★★★ | ★★★★ | **High** (3 days for engine + counterfactual) |

---

### Idea 2 — THE ORACLE: anticipatory broadcast

**One line.** The screen shows danger rising *before* the shot: a forecast of the next 8 seconds, rendered as a live "threat front" on the pitch, with the commentary anticipating rather than reacting.

**The insight.** Human commentary is reactive; the best pundits are prized precisely because they see it coming. SoccerNet made *anticipation* an official 2026 task and TacticAI's open-play product predicts 8 s ahead for clubs. Nobody has put a forecast on a fan-facing broadcast. With a branchable engine, forecasting is the same operation as counterfactuals: roll 200 futures from *now* and summarise them.

**What the viewer sees.** A heat "front" grows on the right channel; a thin bar labelled "shot in next 10 s: 34%" climbs; the Narrator says "Reyes is pulling the full-back inside; watch the far post." Three seconds later the cross comes. When the forecast is wrong, the overlay says so ("the press broke it up"), which is itself a story.

**Pipeline mapping.** Ingest: tracking. Interpret: rolling Monte Carlo forecast every 2 s (P(shot), P(turnover), most likely zone, most likely player). Explain: "why the probability is rising" from pitch-control deltas. Render: threat front + probability bar. Personalise: Player-Cam gets "your player is the most likely next shooter"; kids get an excitement meter.

**Heavy lifting.** Same batched engine as Idea 1 (B=200, horizon 10 s, every 2 s is ~1,000 steps per cycle, trivial). Optional: a tiny PyTorch transformer trained on 300 synthetic matches to predict next action, to show a "learned model" alongside the simulator forecast and compare them live.

**Wrapper.** Forecast service on ACA with KEDA scaling; Foundry Routines to run the nightly model retrain; Web PubSub for 2 s pushes.

**Novelty vs field.** None of the entries forecast. The "before it happens" demo moment is extremely cinematic.

**Risks.** If the engine's decisions are too random, forecasts look like noise (mitigate: style profiles and role logic make the engine predictable at 10 s horizons; publish Brier score). Forecast on screen can be mistaken for betting (mitigate: no odds language, no money framing).

| Tech | Agentic | Impact | UX | Category | Feasibility |
|---|---|---|---|---|---|
| ★★★★★ | ★★★ | ★★★★ | ★★★★★ | ★★★ | **High** once Idea 1's engine exists (+1 day) |

---

### Idea 3 — DIRECTOR'S CUT: one match, a million broadcasts

**One line.** An AI producer agent controls an entire synthetic broadcast per viewer: camera, replays, overlays, audio mix, pacing. Two viewers watching the same minute see two different programmes.

**The insight.** Personalisation today means "toggle a stats panel". If the match is rendered in 3D from our own tracking data, the camera is ours, replays are a rewind, and the whole broadcast grammar (wide → close → replay → graphic) becomes a decision a Director agent can make per viewer. This is the maximal interpretation of Stage 4 and Stage 5 together.

**What the viewer sees.** Split screen. Left: "Tactical" viewer gets a high wide tactical camera, pitch-control heatmap, slow replays with ghost runs. Right: "Player-Cam, Reyes, Spanish" gets a tracking camera on one player, his sprint stats, his touches replayed, Spanish voice. Centre: "Kid mode" gets close action, celebrations, a big excitement meter, no numbers. All three cut their own replays at different moments.

**Pipeline mapping.** Ingest: tracking. Interpret: leverage, state, player stats. Explain: the Director's reasons are logged ("cut to replay because leverage 0.09 and viewer mode = tactical"). Render: Three.js/React-Three-Fiber 3D broadcast with camera rigs, scene state driven by a per-viewer Director. Personalise: everything.

**Heavy lifting.** React-Three-Fiber scene with stylised players (capsules with kits and numbers; no need for MetaHumans), camera rig library (wide, tactical, follow, behind-goal, replay dolly), a rules-plus-LLM Director, ElevenLabs v4 Turbo voice per viewer.

**Wrapper.** Director as an Agent Framework handoff orchestration (Producer → Camera → Graphics → Audio agents); viewer state in Cosmos; ACA; Speech as a voice alternative.

**Novelty vs field.** No entry controls the picture; they all overlay on a static pitch. "Each viewer gets their own cut" is the biggest wow of the seven.

**Risks.** Scope: a 3D broadcast with camera grammar is a week on its own for one person who knows R3F. Judges may read it as "a game" rather than broadcast tooling (mitigate: keep a broadcast look, score bug, lower thirds, and show the Cue Sheet alongside).

| Tech | Agentic | Impact | UX | Category | Feasibility |
|---|---|---|---|---|---|
| ★★★★ | ★★★★ | ★★★★ | ★★★★★ | ★★★★ | **Medium-Low** (needs one strong front-end dev for 5 days) |

---

### Idea 4 — UNMUTE: the commentator you choose

**One line.** Live, grounded, personalised voice commentary: pick the persona, language, intensity and stat density, interrupt it with a question, and it answers from the match state.

**The insight.** Half of fans mute commentary. They don't hate sound; they hate *that* sound. The product is a commentator that is yours: tactical nerd, hype caster, calm radio voice, your-club fan, bilingual, kid-friendly, "explain it like I'm new to football". With native speech-to-speech models and 150 ms TTS, the voice is solved; the value is grounding every sentence in the event stream and the counterfactual engine so it is never wrong about a number.

**What the viewer sees (hears).** The same 20-second passage, four commentators side by side: a Spanish hype voice, a calm English tactical voice citing pitch control, an Arabic club-fan voice, a Hindi kids voice. The user says "wait, why was that offside?" and the voice answers in one sentence with the line drawn on the pitch. A slider labelled "numbers" goes from none to analyst.

**Pipeline mapping.** Ingest: events. Interpret: stats. Explain: Narrator writes grounded lines with claims; Fact Checker verifies. Render: audio timeline + captions + ducking under crowd noise. Personalise: persona, language, density, club bias (with fairness guard), barge-in Q&A.

**Heavy lifting.** ElevenLabs v4 Turbo for TTS (or Gemini 3.8 Live for speech-to-speech with affective delivery); Gemini 3.8 Live or Claude for the barge-in Q&A agent with tool access to the blackboard; Silero VAD for the interrupt; a pacing controller so the voice never talks over a goal.

**Wrapper.** Azure Speech as the enterprise voice path (Voice Live API for the Q&A); Foundry prompt agents for personas; Content Safety; evaluation of groundedness.

**Novelty vs field.** Several entries have TTS; none have *interactive*, persona-controllable, barge-in commentary, and none frame it against the mute problem. The emotional impact on video is strong: voices are visceral.

**Risks.** Audio demos are hard to judge from a 2-minute video with a voice-over (mitigate: the video's own narration *is* Unmute). Latency of grounded line generation 2–4 s is fine for colour commentary, not for play-by-play (mitigate: event-driven template lines in <500 ms for goals, LLM lines for colour).

| Tech | Agentic | Impact | UX | Category | Feasibility |
|---|---|---|---|---|---|
| ★★★★ | ★★★★ | ★★★★★ | ★★★★★ | ★★★★ | **High** (2–3 days on top of a narrator) |

---

### Idea 5 — THE PANEL: three grounded pundits who disagree

**One line.** Three AI pundits with distinct, declared football philosophies debate every key moment live, moderated by a chair agent, with every claim grounded in the engine; fans pick whose feed to follow.

**The insight.** Explainability is not a single answer; it is an argument. Real punditry is valuable because of disagreement. A multi-agent system where disagreement is *structural* (a possession purist, a pressing evangelist, a data sceptic) produces richer explanations than one narrator, and it makes multi-agent collaboration visible and purposeful rather than decorative. Grounding keeps it honest: a pundit who asserts "they should have pressed" must call the counterfactual tool and show the number.

**What the viewer sees.** A moment card. Three short takes appear: "Pressing Evangelist: the trigger was there, +7 pts if they step up (cf_0812)". "Possession Purist: you'd expose the half-space; the sim says −3 pts". "Data Sceptic: n=200, horizon 60 s, spread is wide; call it a coin flip." The chair writes the one-line consensus for the overlay. The fan app lets you follow one pundit's feed, or the chair.

**Pipeline mapping.** Ingest/Interpret: as Idea 1. Explain: group-chat orchestration with tool grounding. Render: moment cards, consensus lower-third. Personalise: pick your pundit, language, and how much disagreement you want to see.

**Heavy lifting.** Group-chat orchestration (Agent Framework's `GroupChat` pattern or your own), three distinct system prompts with philosophies and *required* tool calls, a chair with a word budget, Claude Opus 5.5 / Gemini 4 Argon / GPT-6.1 Sol for the pundits (mixing providers per pundit is a nice touch), ElevenLabs voices per pundit.

**Wrapper.** Agent Framework group chat with Cosmos checkpoints; Foundry Tracing to show the debate graph; A2A to expose each pundit as an agent endpoint.

**Novelty vs field.** Nobody has structured disagreement. It is the most *agentic* idea of the seven in the judges' sense ("distinct roles, shared state, handoffs").

**Risks.** Token cost and latency of three LLM calls per moment (mitigate: only for moments with leverage > 0.05, ~15 per match). "Chatty agents" cliché if ungrounded (mitigate: hard rule that every take must cite a tool result or be dropped by the chair).

| Tech | Agentic | Impact | UX | Category | Feasibility |
|---|---|---|---|---|---|
| ★★★★ | ★★★★★ | ★★★ | ★★★★ | ★★★★★ | **High** (2 days on top of Idea 1) |

---

### Idea 6 — DUGOUT: the AI assistant manager, on air

**One line.** At any moment, a studio pundit (or fan) asks "what should they do now?" and the system searches tactical options by simulation and returns the top three with win-probability deltas and a rendered plan.

**The insight.** TacticAI exists for clubs, behind closed doors. Broadcasting it for fans ("the AI says switch to a back three, +6 pts") is new and irresistible studio content. Technically, it is the counterfactual engine applied to *parameters* (press height, line height, width, tempo, substitutions) instead of a single action: a small search over the style-profile space with Monte Carlo evaluation.

**What the viewer sees.** 60th minute, 0–1 down. A studio panel: "Options for Verdant FC: (1) press higher, +6.1 pts, risk: space in behind; (2) bring on Diallo for Keane, +3.4 pts; (3) go direct, +1.2 pts." Each has a 10-second rendered simulation. Ten minutes later the manager actually subs Diallo and the overlay says "Dugout called it."

**Pipeline mapping.** Ingest/Interpret: as Idea 1. Explain: why each option works, derived from pitch-control deltas across rollouts. Render: option cards with mini-sims. Personalise: club-fan mode ("what should *we* do"), analyst mode (full distribution), casual ("one thing to watch").

**Heavy lifting.** Batched engine with parameter overrides; a 3×3×3 grid search or a 30-sample Bayesian search; Gemini 4 Argon / Claude for the explanation and the studio copy.

**Wrapper.** Exposed as an MCP tool and a Foundry hosted agent "Dugout" the studio can call; Routines to pre-compute at 45', 60', 75'.

**Novelty vs field.** Entirely absent from the field. Strong "real-world impact" story for studios and for club-facing enterprise use.

**Risks.** Compute: 30 options × 200 rollouts × 10 min horizon is heavy (mitigate: 3 min horizon, 100 rollouts, pre-compute at fixed minutes). Credibility if options always look alike (mitigate: make style profiles strongly affect play, which also helps Idea 2).

| Tech | Agentic | Impact | UX | Category | Feasibility |
|---|---|---|---|---|---|
| ★★★★★ | ★★★ | ★★★★★ | ★★★★ | ★★★ | **Medium** (1–2 days on top of Idea 1, engine must be fast) |

---

### Idea 7 — PITCHWATCH: camera-to-intelligence

**One line.** Start from *video*, not events: a synthetic broadcast clip goes through a vision pipeline (Gemini 4 Argon agentic video and/or YOLO + game-state reconstruction) that auto-events passes, shots, tackles and speeds, which then feed the intelligence layer.

**The insight.** The rules explicitly list "auto-eventing: running a model over an incoming video feed." Real broadcasters have video first and data second. A team that can show "we tag the match from pixels" has the most *production-realistic* ingest story. Rendering our own 3D match gives us unlimited synthetic footage with perfect ground truth, so accuracy can be measured honestly.

**What the viewer sees.** Left: a rendered broadcast clip. Right: events appearing with timestamps and a live accuracy counter against ground truth ("passes 94%, shots 100%, tackles 71%"). The minimap reconstructs player positions from the video alone. Then the usual overlays follow.

**Pipeline mapping.** Ingest: video → Gemini 4 Argon (agentic, structured output in our event schema) for near-line tagging; YOLO26/RF-DETR + ByteTrack + pitch-keypoint homography (Roboflow sports datasets, `sn-gamestate` baseline) for live-ish tracking. Interpret onward: as Idea 1.

**Heavy lifting.** Three.js renderer with a broadcast camera to produce clips; Gemini 4 Argon agentic video for event JSON; Roboflow sports / YOLO26 fine-tuned on our rendered frames (we have perfect labels for free); homography to pitch coordinates.

**Wrapper.** Foundry Content Understanding as the enterprise alternative path; the vision adapter as an MCP tool; ACA GPU job for batch tagging.

**Novelty vs field.** One entry (the-ninety-labs) is attempting this and has not reached event detection; it is clearly the hardest route. Doing it *as an adapter* beside an event path, with published accuracy, is credible; doing it as the only path is suicidal in 7 days.

**Risks.** Highest risk of the seven. Gemini Live cannot do it live (1 fps); Argon is near-line (seconds to minutes per clip). YOLO on stylised renders generalises nowhere near real footage, and judges may ask. Occluded ball detection is weak everywhere.

| Tech | Agentic | Impact | UX | Category | Feasibility |
|---|---|---|---|---|---|
| ★★★★★ | ★★ | ★★★ | ★★★ | ★★★ | **Low** as the core; **Medium** as a 1-day stretch adapter |

---

## 2. Comparison

| # | Idea | Wow on video | Novel vs 433 entries | Judge fit (all 5) | 7-day feasibility | Depends on |
|---|---|---|---|---|---|---|
| 1 | Sliding Doors | ★★★★★ | ★★★★★ | ★★★★★ | High | batched engine |
| 2 | The Oracle | ★★★★★ | ★★★★★ | ★★★★ | High | engine (same rollouts as 1) |
| 3 | Director's Cut | ★★★★★ | ★★★★★ | ★★★★ | Medium-Low | 3D renderer, strong FE dev |
| 4 | Unmute | ★★★★ | ★★★★ | ★★★★★ | High | narrator + TTS |
| 5 | The Panel | ★★★★ | ★★★★ | ★★★★★ | High | engine + tools (grounding) |
| 6 | Dugout | ★★★★ | ★★★★★ | ★★★★ | Medium | fast engine |
| 7 | Pitchwatch | ★★★ | ★★★ | ★★★ | Low (core) | renderer + GPU time |

Two modules that are not standalone ideas but raise every option above: **Match Weather** (pitch control, pressure and chaos drawn as fronts and storms, a broadcast-friendly metaphor for "control vs chaos") and **Clip Factory** (auto-cut 15-second vertical explainer clips per language for social, rendered with Remotion/ffmpeg from the same scene graph).

---

## 3. What I recommend building (and why it is still one product)

Ideas 1, 2 and 6 are the **same engine** used three ways: branch at a past moment (Sliding Doors), branch from now (Oracle), branch with different parameters (Dugout). Build the engine once, batch-first, and all three cost one to two extra days combined. Ideas 4 and 5 are the **audience layer** on top. Idea 3 is the highest wow but the one most likely to sink the week; Idea 7 is a stretch adapter.

**Recommended stack: "Sliding Doors + Oracle" core, "Unmute" as the face, "The Panel" as the multi-agent story, Dugout as a studio mode if the engine is fast by Thursday.**

Concretely:

| Day | Build | Idea |
|---|---|---|
| Tue 21 | Batched engine, event + tracking schema, golden match, 2.5D renderer | 1 |
| Wed 22 | Pitch control, chaos, win probability, counterfactual branching, forecast loop | 1, 2 |
| Thu 23 | Blackboard, MCP tools, Narrator + Fact Checker, three Pundits + Chair | 5 |
| Fri 24 | Unmute: ElevenLabs/Gemini Live voices, personas, barge-in Q&A, pacing | 4 |
| Sat 25 | Overlay + Fan App + Studio, Match Weather layer, cloud deploy, evals | all |
| Sun 26 | Dugout studio mode (if engine < 1 s per 200×60 s), video edit | 6 |
| Mon 27 | Polish, submit (Pitchwatch adapter only if everything else is green) | 7 |

**The demo opening** writes itself: a fan mutes the TV. Unmute starts talking in her language. A shot goes wide; Sliding Doors shows what would have happened. The Oracle's threat front rises; the next cross comes. The Panel argues about it. At the hour, Dugout says what the manager should do, and ten minutes later the manager does it.

---

## 4. Open tool map for the recommended stack (choose best-of-breed, wrap later)

| Need | Best tool today | Alternative | Microsoft wrapper if desired |
|---|---|---|---|
| Physics engine, rollouts | numpy batched engine (own code) | JAX for 10× if needed | ACA service, KEDA |
| Explanation / pundit reasoning | Gemini 4 Argon (structured output, 1M ctx) or Claude Opus 5.5 | GPT-6.1 Sol | Foundry hosts GPT-6 / Claude; Agent Framework talks to any provider via OpenAI-compatible or Anthropic clients |
| High-volume lines (6 languages) | Gemini 3.8 Flash / GPT-6 Luna | Claude Haiku 5.5 | Foundry Model Router |
| Real-time voice | ElevenLabs v4 Turbo (~150 ms TTFS) | Gemini 3.8 Live speech-to-speech | Azure Speech / Voice Live API |
| Barge-in Q&A | Gemini 3.8 Live with tools | Claude + Scribe v2 realtime STT | Voice Live API |
| Vision auto-eventing (adapter) | Gemini 4 Argon agentic video | YOLO26 + ByteTrack + Roboflow pitch keypoints; `sn-gamestate` | Foundry Content Understanding |
| 3D/2.5D render | React-Three-Fiber / Canvas | Remotion for clip export | Static Web Apps |
| Agent orchestration | Microsoft Agent Framework (multi-provider) | LangGraph | this is the wrapper |
| State | Cosmos DB / Postgres | Redis for hot state | Cosmos |
| Push | Web PubSub / plain WebSockets | SSE | Web PubSub |
| Evals | own truth-based evaluator + promptfoo | Foundry Evaluations | Foundry Evaluations |

The judging rubric still rewards the Microsoft layer. The way to have both: Agent Framework as the orchestrator (it is genuinely provider-agnostic), Foundry for hosting, tracing and evaluation, Azure for runtime, and the best external model or voice behind each role where it visibly matters (Argon for video, ElevenLabs for voice). Say so plainly in the README; judges respect a reasoned choice more than a checklist.
