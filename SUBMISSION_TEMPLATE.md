# Submission Template (short)

Rules 4.4 ask for: what you built, which Microsoft and Azure technologies, what it does, what problem it solves. Short sentences. No hype. Only measured numbers.

## WHYLINE: every line on screen has a why

**Problem.** Football broadcasts show numbers like "0.06 xG" but never say why a moment mattered, and one feed cannot fit every fan.

**What we built.** An AI system that freezes a key moment, replays it 200 times with one decision changed, and shows what that decision cost: "A pass to Reyes raises Verdant's win chance [X] points." Agents check every number before it reaches the screen. Viewers pick analyst, casual or player mode. Producers can veto any cue.

**How it works.** Match video and events go in. Code and small trained models compute pitch control, speeds and win chance. A neural network plays the alternative futures. Claude agents explain them. A Fact Checker verifies each claim. A Director decides what each viewer sees.

**Technologies.** Microsoft Agent Framework (agent workflow, human approval, crash recovery), MCP (agents' only data path), Azure Container Apps, Cosmos DB, Static Web Apps, Web PubSub, Application Insights. Also Claude, Gemini, PyTorch.

**Proof.** Calibration [X], planted errors caught [X of 500], cue latency [X s], cost per match [$X]. See `evals/results.md`.

**Limits.** English text only. Futures are simulated scenarios, not predictions. Ball tracking in video is unreliable when the ball is hidden.

**Links.** Video [URL] · Repo [URL] · Live demo [URL] · Permission note `docs/permissions/`
