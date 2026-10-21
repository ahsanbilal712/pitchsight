# ADR-008: 2.5D canvas for live overlays; one stylised 3D scene for Sliding Doors replays

## Status

Accepted, 2026-10-21

## Context

- No licence-clean React-Three-Fiber football replay viewer exists. `immament/football-match-viewer` has no LICENSE file. The scene has to be built in-house (audit A.1 row 61). The library versions are verified MIT: `three` 0.186.1, `@react-three/fiber` 9.8.2, `@react-three/drei` 10.7.9.
- Humanoid assets carry conditions. Mixamo needs an Adobe ID and forbids raw redistribution. Quaternius is now QAL v1.0, not CC0. Kenney is CC0 but blocky. There are no CC0 soccer player models on Sketchfab. Ready Player Me shut down on 31 Jan 2026 (audit A.1 row 62).
- The audit puts a full 3D broadcast ("Director's Cut") at about 15 person-days for a competent R3F developer and lists it first to cut at day 14 (C.3, D.3). It says to keep 2.5D and, if a developer has it nearly working, one 3D replay shot for the video.
- gfootball failed three install spikes on this Mac (ADR-001). The Docker route is untested and out of scope. Headless rendering is explicitly disclaimed by EnvPool (audit A.1 row 7).
- The generative opener is unavailable: Veo 3.1 is marked deprecated with shutdown on 22 Oct 2026 and no successor is confirmed. The opener is rendered in the project's own 3D scene (`DEMO_MASTERPLAN_50USD.md` section 3).
- Whether anyone on the team is comfortable in R3F is an open question (TECH_PLAN 1.14, question 2).

## Decision

The live overlay in `apps/overlay` is a Canvas 2D pitch (`Pitch2D`) with DOM lower-thirds (`ScoreBug`, `ChaosMeter`, `SwingBar`, `LowerThird`, `PlayerTags`, `Ticker`). There is no UI library beyond React.

Sliding Doors replays use the route `/replay3d?cf=cf_000077` in the same Vite app. It is an R3F scene with a stadium bowl, a pitch plane, capsule players in kit colours with number sprites, a ball, and two cameras (broadcast wide and behind-the-player). It draws the 200 ghost ball paths as translucent lines coloured by branch, the chosen alternative as an orange dashed trail, and the swing bar as a DOM overlay. `?record=1` disables the cursor, fixes DPR to 1 and exposes `window.__whyline.seek(clock)` for the Playwright recorder. The scene reads a `counterfactual.schema.json` document and uses no external humanoid assets.

## Alternatives rejected

- Full per-viewer 3D broadcast: about 15 person-days (audit C.3).
- gfootball rendered frames: it failed three install spikes on this Mac, the Docker route is untested and out of scope, and headless rendering is disclaimed by EnvPool.
- Mixamo or Quaternius humanoids: licence conditions (Adobe ID and no raw redistribution; QAL v1.0 and no standalone redistribution).
- A generative-video opener: Veo 3.1 is deprecated and shuts down on 22 Oct 2026.

## Consequences

- Positive: capsule players avoid asset-licence questions. One app and one deploy serve all views. The 3D scene only has to look good for about twenty seconds of video.
- Positive: the scene reuses the cached counterfactual, so it cannot fail at recording time (ADR-003).
- Negative: capsules may look crude next to a real broadcast. The video must lean on the ghost paths and the swing bar.
- Negative: `Futures` keeps ball paths at 1 Hz and only the final player positions (TECH_PLAN 1.5). The scene can show ball futures and end states, not player movement inside a future.
- Negative: the scene needs a developer comfortable with R3F. If it is not rendering a frame by day 5 (25 Oct), the 3D scene is cut and the video uses the 2.5D ghost trail (TECH_PLAN 1.13).
- Negative: WebGL recording through headless Chromium at DPR 1 has not been tested.

## Related

- TECH_PLAN 1.4 (front-end apps), 1.5 (Futures), 1.9 (overlay, recording), 1.13 ("3D scene late").
- ADR-001, ADR-003, ADR-007.
- Schemas: `schemas/counterfactual.schema.json`, `schemas/cue.schema.json` (`graphics.ghost_trail`, `graphics.pitch_control_snapshot`). Config: `config/pins.txt`.
- Audit: A.1 rows 7, 61 and 62, C.3, D.3.
