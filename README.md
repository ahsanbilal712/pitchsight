# Pitchsight

Football broadcasts tell you what happened. Pitchsight shows why it mattered: on real Premier League broadcast footage it
draws the moments' alternatives on the pitch (200 replayed futures of the shot not taken, the pass that was on), prices
every option live, follows a sprint with a speed gun, explains a refereeing call from the tracking, and lets a
producer check and veto every line before it airs. Every number on screen is bound to verified evidence.

The data backbone is a synthetic league and match engine (the rules require synthetic data at the core); real
footage, used with the Premier League's permission, is the ingest and the presentation layer.

## The video

- **Video v3** (under two minutes, captions only, English, no voice, no music): real footage and real names only.
  Edit list `packages/demo/edit_v3.yaml`, captions `packages/demo/captions_v3.srt`. Every number in a caption is
  bound to a source listed at the bottom of the edit list, and the cut is checked by `python -m footage.grounding`
  (`data/footage/v3_grounding.json`: 75 of 75 on-screen numbers bound to verified evidence).
- The rendered file (`packages/demo/out/final_v3.mp4`) is git-ignored with all footage-derived media. The public link
  is added here after the owner uploads it (a human step).
- Earlier cuts, kept as fallbacks: v2 (`packages/demo/edit_v2.yaml`) and v1 on the synthetic league
  (`docs/video/v1.md`).

## Real footage: permission, sources and what never enters this repository

- **Permission.** The Premier League granted written permission for highlight clips from its official YouTube
  channel, club and player names, logos and crests, in the hackathon prototype, the hosted demonstration for judges
  and the public demo video, until 10 November 2026, with computer-vision analysis and AI overlays permitted. The
  scope and conditions are recorded in [docs/permissions/README.md](docs/permissions/README.md); the original email is
  held by the project owner for export there as `.eml`.
- **Sources.** Four clips, each an upload by the Premier League channel, are listed with their URLs in
  [data/footage/SOURCES.md](data/footage/SOURCES.md): Liverpool v Manchester City 2025/26, Manchester United v
  Manchester City 2025/26, Arsenal v Chelsea 2025/26, Manchester United v Tottenham Hotspur 2024/25. Nothing outside
  that list is used.
- **Not in the repository.** Video, frames and composites are git-ignored (`data/footage/.gitignore`,
  `packages/demo/out/`): the footage is shown only in the demo video and streamed to judges from the demo, never
  distributed as files. Only derived JSON (calibrations, tracks summaries, moments, counterfactuals, reviewed text)
  is committed.

## How a real clip becomes a Pitchsight graphic

1. **Shots, camera, players** (track A, `packages/evals/pitchwatch/`): steady wide shots are kept; a camera is fitted
   per frame to the pitch markings and refined against the painted lines with a lens term
   (`python -m demo.refine_calib <clip> <shot>`); RF-DETR detections and ByteTrack tracks put players in pitch metres.
2. **Moments and counterfactuals** (track B, `packages/footage/`): a tracked frame becomes a state of the synthetic
   engine, which replays it 200 times with the action taken and with the alternative; Gemini tags the events; every
   claim goes through the Fact Checker and a hand review.
3. **Drawing on the real frame** (track C, `packages/demo/composite.py`, `packages/demo/live.py`): everything on the
   grass is drawn in pitch metres through that frame's camera, so it sits on the painted lines: median drift 0.5 to
   0.8 px and p95 1.5 to 2.3 px on the frames with painted lines in view. The Fourth Official and keeper frames
   show little paint and use the tracking or hand-marked camera (p95 6.4 to 6.8 px). `python -m demo.composite
   <moment>` prints the measure for each moment.

Measured on the footage (`data/footage/insights/metrics.json`, track A): players found on 200 hand-checked frames
99.3%; position error over 20 checked points 0.32 m on average; track breaks per player-minute at most 0.97
(Liverpool v Manchester City).

## Limits, stated plainly

- Positions come from broadcast tracking: about 0.5 m per position, worse at the far side and in fast play; the ball
  is often hidden. A shot with no readable paint (the reverse angle in Manchester United v Spurs) keeps its unrefined
  camera.
- The counterfactuals run in the synthetic engine on states built from the tracking: they are model estimates, not
  facts about the real match. The pass X-ray uses outcome heads trained on the synthetic league.
- The Fourth Official card is an assessment from tracking, not a ruling. The keeper card is geometry (share of the goal
  covered under stated reach assumptions), not a save probability. The speed gun's distance crosses a close-up in a
  straight line, so it is a lower bound. The win-probability river uses score and clock only.
- Players are named only where the moment files identify them; others are labelled by role, never by a guess.
- English only, captions only. Live judges' matches are synthetic; the real clips are prepared moments.

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
  `python packages/demo/assemble.py packages/demo/edit_v3.yaml`.
