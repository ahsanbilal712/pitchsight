# Pitchsight

Football broadcasts tell you what happened. Pitchsight shows why it mattered: on real Premier League broadcast footage it
draws the moments' alternatives on the pitch (200 replayed futures of the shot not taken, the pass that was on), prices
every option live, follows a sprint with a speed gun, explains a refereeing call from the tracking, and lets a
producer check and veto every line before it airs. Every number on screen is bound to verified evidence.

The data backbone is a synthetic league and match engine (the rules require synthetic data at the core); real
footage, used with the Premier League's permission, is the ingest and the presentation layer.

## The video

- **Video v10**, the submission cut: `packages/demo/out/final_v10_submit.mp4`, 1:48. It opens with what Pitchsight
  is and how it works (the architecture below, narrated), then plays real Premier League attacks with the analytics
  on every frame: the player on the ball, the xG of a shot now, the best pass and its xG, the threat, pitch control
  and the team shape. A voice explains each decision (pass, through ball, shot) by kit colour; the broadcast sound
  is off.
- Edit list `packages/demo/edit_v10_submit.yaml`, captions `captions_v10*.srt`, narration
  script `docs/video/narration_v10.md` (voice: Gemini TTS) and `narration_v9.md` (intro and architecture).
- **Every number is checked.** `python -m footage.grounding --edit packages/demo/edit_v10_submit.yaml` binds every
  on-screen and spoken number to its evidence (tracking, the xG model, the pass model):
  `data/footage/v10_submit_grounding.json` shows 1,106 of 1,106 numbers bound, and every spoken number is on screen
  while it is said.
- Rendered files are git-ignored with all footage-derived media.

## Architecture

```
broadcast clip ─▶ Ingest ─▶ Scout ─▶ Proposer ─▶ Rollout ─▶ Tactician ─▶ Narrator ⇄ Fact Checker ─▶ Director ─▶ CueBus ─▶ screens
                  vision     rules    Gemini      engine     Gemini       Gemini     evidence        rules        blackboard
                                                                                     binding                      + Web PubSub
```

- **Vision** (`packages/evals/pitchwatch/`): wide-shot segmentation with replay-wipe detection; RF-DETR Medium
  (Apache-2.0) players and ball, with tiled inference for the ball; ByteTrack (`trackers`); team by kit colour
  (k-means); a per-frame camera fitted to the pitch markings and refined on the painted lines.
- **Measure** (`packages/heads/`, `packages/footage/`): xG from the published Soccermatics logistic model (8,451
  Premier League 2017/18 non-penalty shots; penalties 0.76); xG after a pass = P(complete) from a LightGBM pass
  model × xG at the receiver's spot; pitch control; the onside-margin check.
- **Agents** (`packages/newsroom/`): a Microsoft Agent Framework workflow graph (WorkflowBuilder) with
  checkpoints and resume; tools over MCP (`packages/mcp_server/`). Only the Proposer, Tactician and Narrator call a
  model (Gemini on Vertex AI, `config/models.yaml`); Scout, Rollout, Fact Checker and Director are code. Every call
  goes through SpendGuard (`packages/api/spend.py`, caps in `config/budgets.yaml`, ledger `data/spend/ledger.jsonl`).
- **Screens** (`apps/`): the broadcast overlay, the producer studio (trace, Why? drawer, veto) and the fan app.

## Azure

The same services deploy to Azure with `azd up` (`azure.yaml`, `infra/main.bicep`, `infra/resources.bicep`):
Container Apps for the api, the MCP server and the newsroom; Static Web Apps for the three screens; Cosmos DB for
the blackboard and the workflow checkpoints; Web PubSub for cue fan-out; Application Insights for the agent traces;
Azure AI Foundry for the model roles. The code path is `packages/cloud/`. It is switched on by `WHYLINE_CLOUD=1`
and reads every endpoint from the environment (`config/.env.example`). Authentication is managed identity, with no
keys in configuration. `WHYLINE_LLM_PROVIDER=foundry` routes the Gemini roles to the Foundry deployments. See
[infra/README.md](infra/README.md). With `WHYLINE_CLOUD=0` (the default) the identical services run locally on
SQLite, file checkpoints and the api's own WebSocket.

## Real footage: permission, sources and what never enters this repository

- **Permission.** The Premier League granted written permission for highlight clips from its official YouTube
  channel, club and player names, logos and crests, in the hackathon prototype, the hosted demonstration for judges
  and the public demo video, until 10 November 2026, with computer-vision analysis and AI overlays permitted. The
  scope and conditions are recorded in [docs/permissions/README.md](docs/permissions/README.md).
- **Sources.** Four clips, each an upload by the Premier League channel, are listed with their URLs in
  [data/footage/SOURCES.md](data/footage/SOURCES.md): Liverpool v Manchester City 2025/26, Manchester United v
  Manchester City 2025/26, Arsenal v Chelsea 2025/26, Manchester United v Tottenham Hotspur 2024/25. Nothing outside
  that list is used.
- **Not in the repository.** Video, frames and composites are git-ignored (`data/footage/.gitignore`,
  `packages/demo/out/`): the footage is shown in the demo video and never distributed as files. Only derived JSON
  (calibrations, tracks summaries, moments, counterfactuals, reviewed text) is committed.

## How a real clip becomes a Pitchsight graphic

1. **Shots, camera, players** (`packages/evals/pitchwatch/`): steady wide shots are kept; a camera is fitted
   per frame to the pitch markings and refined against the painted lines with a lens term
   (`python -m demo.refine_calib <clip> <shot>`); RF-DETR detections and ByteTrack tracks put players in pitch metres.
2. **Moments and counterfactuals** (`packages/footage/`): a tracked frame becomes a state of the synthetic
   engine, which replays it 200 times with the action taken and with the alternative; Gemini tags the events; every
   claim goes through the Fact Checker and a hand review.
3. **Drawing on the real frame** (`packages/demo/composite.py`, `packages/demo/live.py`): everything on the
   grass is drawn in pitch metres through that frame's camera, so it sits on the painted lines: median drift 0.5 to
   0.8 px and p95 1.5 to 2.3 px on the frames with painted lines in view. The Fourth Official and keeper frames
   show little paint and use the tracking or hand-marked camera (p95 6.4 to 6.8 px). `python -m demo.composite
   <moment>` prints the measure for each moment.

Measured on the footage (`data/footage/insights/metrics.json`): players found on 200 hand-checked frames
99.3%; position error over 20 checked points 0.32 m on average; track breaks per player-minute at most 0.97
(Liverpool v Manchester City).

## Method notes

- Positions come from broadcast tracking: about 0.5 m per position, worse at the far side and in fast play; the ball
  is often hidden. A shot with no readable paint (the reverse angle in Manchester United v Spurs) keeps its unrefined
  camera.
- The counterfactuals run in the synthetic engine on states built from the tracking: they are model estimates, not
  facts about the real match. The pass X-ray uses outcome heads trained on the synthetic league.
- The Fourth Official card is an assessment from tracking, not a ruling. The keeper card is geometry (share of the goal
  covered under stated reach assumptions), not a save probability. The speed gun's distance crosses a close-up in a
  straight line, so it is a lower bound. The win-probability river uses score and clock only.
- Players are named only where the moment files identify them; others are labelled by role, never by a guess.
- English only. The voice and the captions describe decisions; they never name a team or a player. Live judges'
  matches are synthetic; the real clips are prepared moments.

## Run it

Pitchsight was developed under the working name WHYLINE; code identifiers and environment variables (`WHYLINE_*`)
keep it.

- Judges: see [docs/JUDGES.md](docs/JUDGES.md).
- Replay of the synthetic golden match, no keys: `make demo` (docker compose) or `make clean-replay`.
- The producer studio on a real clip's recorded newsroom run: `sh scripts/record_v3_studio.sh` records it;
  `PYTHONPATH=packages WHYLINE_BLACKBOARD=<copy of data/footage/liverpool-mancity-2526/cache/studio/blackboard.sqlite>
  python -m api.replay --match m_9001` serves it.
- Rendering the real-clip beats needs the clips locally (they are not distributed): `python -m demo.composite
  <moment>` for each moment in `packages/demo/footage_moments.yaml`, then
  `python packages/demo/assemble.py packages/demo/edit_v10_submit.yaml`.
