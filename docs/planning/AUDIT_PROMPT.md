# Prompt: Adversarial Feasibility Audit of WHYLINE

Paste everything below the line into the forked Claude Code session.

---

You are acting as a sceptical principal engineer, an ML research lead, and a hackathon judge rolled into one. Your job is NOT to build anything. Your job is to audit an idea before a single line of product code is written, and to tell me honestly whether it is achievable, what is missing, and what would make it fail.

## The idea

Read these files in this folder, in this order, completely:

1. `THE_IDEA.md` — the plain-language explanation of the whole concept (WHYLINE, with "Sliding Doors" at its core).
2. `ML_CORE.md` — the machine-learning design: a learned behaviour model of football, a futures generator, outcome heads, moment embeddings, a fine-tuned narrator, pretrained vision models, and LLM agents that steer the simulation.
3. `WHYLINE_45DAY_MASTERPLAN.md` — the 45-day build plan, two-worlds design (our numpy engine plus Google Research Football with pretrained RL teams), broadcast rendering, evaluation and fan-study plans.
4. `WHYLINE_PROPOSAL.md` — the original 7-day plan and architecture, including the Microsoft stack mapping.
5. `TOP7_IDEAS.md` and `NEW_IDEAS_45DAYS.md` — the wider idea list, for context only.
6. `/Users/ahsanbilal/Downloads/OFFICIAL RULES.md` — the hackathon's official rules. Compliance matters.

Context you need: this is for the Microsoft × Premier League "Inside the Game: Developer Hackathon." Judging criteria are five equally weighted items: Technological Implementation, Agentic Design & Innovation, Real-World Impact, UX & Presentation, Adherence to Category. The rules require synthetic data only, a public GitHub repo, a demo video under two minutes, and that judges may test the project. Today is 21 October 2026. The official rules say submissions close 27 October 2026; the hackathon website banner shows the event running to 21 November 2026. Treat the deadline as unresolved and audit for both a short and a 45-day horizon. The team is small (assume 3 people, one of whom is strong in ML, one in backend/cloud, one in front-end). We are free to use any tools, models, or APIs, not only Microsoft's.

## What I want from you

A complete, adversarial, evidence-backed feasibility audit. Think of it as due diligence before funding. Be harsh. Where the documents are hand-wavy, say so. Where a claim depends on something that may not exist, go and check whether it exists. Do not take the documents' word for anything.

### Part A — Verify every external dependency actually exists and is usable

For each item below, find the primary source (official docs, GitHub repo, paper, model card), confirm its current status as of October 2026, its licence, and whether it does what the plan assumes. Where it is cheap to do so, actually try it in a scratch virtual environment (install the package, import it, list the files) rather than trusting a README. Record exact versions, URLs and licences.

1. **Google Research Football (gfootball).** Is it installable today (pip, Docker, from source) on macOS and on Linux? Which Python versions? Does it still render 3D frames headlessly and dump video? Does it expose full player and ball positions in observations? Does it support `get_state` / `set_state` for branching mid-match? What is its headless steps-per-second on one CPU core? It was archived on GitHub in August 2026: does the archive matter? What is the "new game server" at research-football.dev and is it usable? Licence?
2. **Pretrained 11v11 RL football policies.** DB-Football / Light-MALib (Shanghai Digital Brain Lab), TiZero, GRF_MARL, or any other. Do the trained 11v11 weights actually exist in a public repo today? Can they be loaded and run against gfootball? What do they require? Are they open-licensed? How "football-like" is their play (find videos, papers, or run them)?
3. **Public football tracking and event data that could legally pretrain or fine-tune a behaviour model.** StatsBomb open data, SkillCorner open data, Metrica Sports sample data, SoccerNet tracking, PFF FC open data, anything else. For each: licence terms, whether use in a hackathon product or model training is permitted, and whether its use would violate the hackathon rule that projects must use synthetic data. Give a clear legal reading and a recommendation.
4. **Behaviour / trajectory prediction models for football with public code.** FootBots, Ball Radar, MIDAS, sMART, GenTac, TacticGen, TacticAI, CausalTraj, Sports-traj, TranSPORTmer, anything newer. Which have public code? Which have public weights? What data format do they expect? Could any be reused or must we train from scratch?
5. **Pretrained vision models.** Roboflow football player/ball/referee detection (RF-DETR, YOLO versions), Roboflow soccer pitch keypoint detection, the `roboflow/sports` repo, SoccerNet game-state-reconstruction baseline (`sn-gamestate` on TrackLab), ByteTrack, BroadTrack, PnLCalib. Licences, whether weights are downloadable without an account, and whether they would work on *rendered* (non-photoreal) footage.
6. **Video understanding APIs.** Gemini 4 Argon and Gemini 3.8 Flash video input and "agentic" processing: confirm model IDs, whether they accept uploaded video, output structured JSON, timestamp accuracy, pricing per minute of video, rate limits. Confirm the Gemini Live API's 1 fps video limit.
7. **Voice.** ElevenLabs v4 Turbo (or current real-time model), Gemini 3.8 Live speech-to-speech, Azure Speech / Voice Live API: latency, languages, pricing, commercial-use terms for a public demo video.
8. **Microsoft Agent Framework (Python).** Current package name and version, whether graph workflows, fan-out/fan-in, `RequestInfoExecutor` human-in-the-loop, `CosmosCheckpointStorage`, group-chat and handoff orchestrations, A2A, AG-UI, and MCP tools exist with those names today. Install it and confirm imports. Note anything in the plan that names an API incorrectly.
9. **Microsoft Foundry.** Agent Service, Evaluations (including custom evaluators), Tracing, Routines, Model Router, fine-tuning of small models (which models, cost, turnaround), Foundry Local. Confirm what is GA versus preview and whether a hackathon team with a normal Azure subscription can access each.
10. **Azure services in the plan.** Container Apps (GPU workload profiles for rollouts: availability, cost), Event Hubs, Cosmos DB, Web PubSub, Functions, Static Web Apps, Azure Load Testing. Any quota or regional gotchas for a new subscription.
11. **Broadcast rendering path.** Singular.live Data Stream API (free tier terms, watermark, rate limits, whether data streams are available on free), CasparCG HTML templates, OBS browser source, HLS timed metadata (ID3 / emsg) injection tools (ffmpeg capabilities, alternatives) and hls.js metadata events.
12. **3D rendering.** React-Three-Fiber / Three.js for a stylised football scene: find existing open-source football or sports pitch visualisers that could be adapted, and any free, licence-clean player models or animation sets.
13. **Avatar presenters** (optional feature): Anam, Tavus, HeyGen, Gemini Live Avatar: real pricing, latency, and terms for a public demo.

Produce a table: dependency, exists (yes/no/partial), verified how, version, licence, blocks the plan if missing (yes/no), notes.

### Part B — Audit the ML core adversarially

For each model in `ML_CORE.md`:

1. **Behaviour model (set transformer, behaviour cloning from gfootball RL agents + our engine).** Is behaviour cloning from RL agents likely to yield plausible football at 10 Hz over 15-second rollouts? Cite evidence (papers on imitation learning in GRF, covariate shift in autoregressive rollouts, FootBots-style results). Estimate data needed, parameters, training time on one GPU, inference time for 200 parallel rollouts on CPU and on a T4/A10 class GPU. Identify the most likely failure modes (drift, loss of team shape, implausible passes) and whether the proposed mitigations (on-ball decisions learned first, off-ball shape from a prior, 15 s horizon then hand-off) are credible.
2. **Futures generator / counterfactual validity.** Is "force the first action, then sample" a sound counterfactual? What are the known pitfalls (off-policy states the model never saw)? How would we know the counterfactual numbers are calibrated and not fiction? Propose the exact evaluation protocol.
3. **Outcome heads** (xG with defender geometry, xT, win probability, goal-in-horizon, pass completion). Standard or not? Data needed? Any reason they could be wrong in ways a judge would notice?
4. **Moment embeddings and learned chaos.** Is a contrastive encoder over match states realistic in this time? Is there prior work? What is the simplest version that still counts as learned?
5. **Fine-tuned narrator.** Which small models can be fine-tuned in Foundry today and at what cost? Is 20,000 lines achievable to generate and verify? Would a few-shot frontier model make it unnecessary?
6. **The circularity objection.** "You trained on synthetic play, so your counterfactuals only reflect synthetic football." Steelman this objection, then say what evidence would blunt it and whether that evidence is obtainable within the rules.
7. **Compute and cost.** Total GPU-hours, where to get them, total API spend for development, evaluation and a demo season, with a line-item estimate.

### Part C — Audit the system and plan

1. Latency budget: event to verified cue in under five seconds with LLM calls, rollouts, verification and translation in the path. Is it realistic? Where does it break? What is the honest p95?
2. The multi-agent design: is each agent justified, or could a judge argue it is a pipeline with LLM calls? Which agents are decorative? What would make the "recover from failure" claim demonstrable and not theatre?
3. The 45-day sprint plan: for each sprint, estimate the real person-days required versus available, assuming 3 people. Mark each deliverable as achievable / at risk / unrealistic. Then do the same for a 7-day and a 31-day horizon, and say what the minimum credible submission is for each.
4. Rules compliance: synthetic-only data, third-party licences, no trademarks, no copyrighted music, public repo, "new project after 29 September 2026," judges must be able to test it, multiple submissions must be "substantially different." Flag every place the plan is at risk.
5. The "two worlds" approach: is the value worth the cost, or is it a distraction?
6. Demo and judging: identify every claim in the plan that a judge could call unproven and say what artefact (table, plot, log, clip) would prove it.

### Part D — Red team

1. List the ten most likely ways this project fails, ranked by probability × impact, with early-warning signals for each.
2. For each, give the cheapest spike (hours, not days) that would confirm or kill the risk in the first week. Where the spike can be run now in a scratch environment without building the product (install a package, load a model, measure steps per second, call an API with a tiny input), run it and report the actual result.
3. Say what you would cut first, second and third if the team is behind at day 14.
4. Steelman the strongest competing approach a rival team could take with the same brief, and say whether WHYLINE beats it.

### Part E — Verdict

End with:

- A one-paragraph go / no-go / go-with-changes verdict.
- A confidence level (low / medium / high) for each of: "the ML core is achievable in 45 days," "a credible demo exists by day 7," "the rules are satisfied," "the idea is differentiated against the field."
- The minimum viable version that you would personally bet on, described in one page: exactly which models, which features, which screens, in which order, with what cut lines.
- A list of claims in the documents that are wrong or unverifiable, quoted, with corrections.

## How to work

- Use web search and fetching extensively. Prefer primary sources: official docs, GitHub repos, papers, model cards, pricing pages. Record the URL for every factual claim.
- Where a check can be done by running something small (pip install into a scratch venv, importing a package, listing a repo's model directory, timing a tiny loop, a single tiny API call if keys exist), do it, and report the real output. Keep all scratch work in your scratchpad directory, not in this project folder. Do not add files to this project except the final report.
- Do not build the product, the engine, the agents or the UI. Spikes only.
- Treat the planning documents as claims to be tested, not facts. Quote them when you disagree.
- Separate what you verified from what you inferred, and label confidence on each finding.
- Keep the final report readable by a non-specialist: short sentences, tables for data, no jargon without a one-line definition.

## Deliverable

Write the full audit to `FEASIBILITY_AUDIT.md` in this project folder, structured as Parts A–E above, with a two-page executive summary at the top that a non-engineer could read. Then give me a short summary in chat with the verdict, the three biggest risks, and the three spikes to run first.
