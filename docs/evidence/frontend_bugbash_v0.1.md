# Front-end bug bash and clean-load check, v0.1 (T-070)

22 Oct 2026, track C. Local only: Azure is deferred by owner direction, so the hosted Static Web Apps check is not
run (see "Not done").

## Clean build

`rm -rf apps/<app>/dist && npm ci && npm run build` for overlay, studio and fan on Node 22.23.3: all three build;
lockfiles unchanged; no dependency changes.

## Tests

`pytest tests/apps -q`: **41 passed** (overlay shell, Pitch2D, components, ghost trail, viewer modes, Player-Cam,
/replay3d at 60 fps on the GPU, studio, studio controls, fan, overlay over WebSocket).

## Console sweep (`scripts/frontend_sweep.py`)

The api in replay mode with the replay feed, the newsroom supervisor, a fresh blackboard; 10 pages in GPU Chromium:
overlay fixture, overlay analyst / casual / player_cam, `/replay3d?cf=cf_000070` (api) and `cf_000077` (fixture),
studio, fan casual at 360 px, analyst at 390 px, player_cam at 430 px. Each storyboard beat of
`packages/demo/golden_moments.yaml` was played for 4 s: Sliding Doors 76:52, Fourth Official 66:02, Oracle 83:26,
Dugout 59:58, kill 41:48, half-time 45:00.

| Result | Count |
|---|---|
| Page errors (uncaught exceptions) | 0 |
| console.error | 0 |
| Failed requests or HTTP >= 400 | 0 |
| Horizontal overflow on phones (360/390/430) | 0 |
| console.warning | 1 kind, `/replay3d` only (P2 below) |

Every page was ready within 0.4 s of load (`window.__whyline.ready`).

## Fixed (P0/P1 found during the bash)

| Issue | Fix |
|---|---|
| `/replay3d` and the Why? drawer could not load golden counterfactuals or pitch-control grids in replay unless the newsroom had written them to the blackboard (doc endpoint 404) | doc endpoint and stream fall back to `data/matches/4242/cache` (71a20ce) |
| Fan app letterboxed on phones wider than 390 px (fixed 390 x 844 frame) | frame fills the phone up to 480 px wide and the full viewport height; mini-pitch scales |
| `/replay3d` warning: PCFSoftShadowMap removed in three r186 | `shadows="percentage"` (PCF) |
| Panel cache-miss trace rows (status `error`) not shown red in the studio | `error` rows red (2f1c0a9) |
| Studio Blackboard unit column clipped | fixed (67e363e) |

## Open (not P0)

| Priority | Issue | Owner, day |
|---|---|---|
| P1 | Few cues at the beats: model outputs are not cached yet, so explained runs end as cache_miss / template lines | B, T-042 (day 4) |
| P1 | Decision Index shows "–" on the Player-Cam card | A, T-048 (day 5) |
| P2 | `THREE.Clock: This module has been deprecated` from inside @react-three/fiber 9.8.2; needs a fiber upgrade, outside T-070's no-upgrade rule | C, revisit with T-083 3D polish |
| P2 | Slight moiré in the 3D crowd texture on the behind-the-player camera | C, T-083 |

## Not done

Hosted check (Static Web Apps load and connect to the hosted api): Azure is deferred by owner direction (22 Oct);
run `scripts/frontend_sweep.py` against the hosted URLs when the Azure tickets resume.
