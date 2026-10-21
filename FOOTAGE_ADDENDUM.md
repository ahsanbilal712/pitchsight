# Footage Addendum — Real Premier League Clips in the Demo

Date: 21 October 2026. Status: amendment to `DEMO_MASTERPLAN_50USD.md`, `TECH_PLAN.md` and `TASKS.md`, conditional on written permission.

## 1. The decision and its conditions

The user reports verbal permission from a Premier League representative to use real Premier League highlight clips and related material. The written Official Rules (4.4, 4.7, 11.4, 11.6) require written permission and say the rules prevail over other statements. Therefore:

| Condition | Artefact |
|---|---|
| Written permission naming: footage from the Premier League's official channels, club and player names and crests in overlays, use in the demo video and the hosted judges' demo | `docs/permissions/premier-league-permission.pdf` or `.eml`, referenced in the README |
| Clips sourced from the Premier League's own official channel only (the rights holder who granted permission) | `data/footage/SOURCES.md` listing each clip's URL, title, date and the permission it falls under |
| Footage never committed to the public repository | `data/footage/` in `.gitignore`; CI job `no-media-in-repo` fails on any `.mp4/.mov/.webm` outside `demo/out/` |
| Footage shown only in the demo video and streamed to judges from the hosted demo | `docs/JUDGES.md` states this |
| Synthetic data remains the data backbone (rule 4.7) | The engine, analytics and all counterfactuals run in the synthetic world; real footage is the ingest and presentation layer |

Nothing in this addendum is built until the permission artefact exists in `docs/permissions/`.

## 2. What changes in the product

Before: the match on screen was our own render. After: **the match on screen is a real Premier League clip**, and WHYLINE's intelligence is drawn on top of it.

The headline demo moment becomes: a real clip plays; at the decisive instant the frame freezes; the pitch lines and the 22 players are detected; the moment is handed to the synthetic engine, which replays it 200 times with one change; the 200 ghost futures and the alternative pass are drawn **on the real broadcast frame** through the recovered camera geometry; the win-chance bar drops; the clip resumes.

This is exactly the rules' "auto-eventing: running a model over an incoming video feed" bullet, done on real footage with permission.

## 3. Pipeline for a real clip (the "Pitchwatch" path becomes core)

```
clip.mp4 (user-provided, official PL channel)
  │ 1. Shot segmentation: keep steady wide broadcast shots; drop replays, close-ups, graphics (scene-cut detection + camera-height heuristic)
  ▼
  │ 2. Pitch calibration per frame: Roboflow pitch-keypoint model (CC BY 4.0) → homography (roboflow/sports ViewTransformer, MIT)
  ▼
  │ 3. Players and ball: RF-DETR Medium, COCO-pretrained (Apache-2.0) → trackers.ByteTrackTracker (Apache-2.0) → pitch coordinates via the homography
  │    team assignment by kit-colour clustering (roboflow/sports TeamClassifier, SigLIP + k-means); jersey numbers are NOT read (no OCR in scope)
  ▼
  │ 4. Event tagging: Gemini 3.8 Flash, agentic video, structured output in event.schema.json (passes, shots, tackles with timestamps); cross-checked against the tracking-derived events
  ▼
  │ 5. Moment freeze: at the chosen instant, the 22 positions and velocities (from 1 s of tracking) become a synthetic State; missing or occluded players are placed by role prior; the demo allows a hand-corrected positions file per moment (data/footage/<clip>/moments/<t>.json)
  ▼
  │ 6. Sliding Doors in the synthetic world: rollout(state, alternative, n=200, 8 s) exactly as in TECH_PLAN 1.5
  ▼
  │ 7. Render back onto the real frame: ghost ball paths, the alternative pass trail, player highlights and the referee line are projected from pitch metres to pixels with the inverse homography and composited over the frozen frame; the lower-third and swing bar are DOM overlays as before
```

Known limits, stated honestly in the README: the ball is often occluded in broadcast footage (the audit found ball recall near 0.49 when mostly hidden); camera cuts break tracks; velocities from 1 s of broadcast tracking are noisy. For the demo, every featured moment is checked and, where needed, hand-corrected, and the README says so. Live judges' matches remain synthetic.

## 4. What this replaces and what it costs

| Item | Before | After |
|---|---|---|
| 3D replay scene (`/replay3d`) | core for the video | **cut**; the real frame is the picture |
| Pitchwatch adapter | optional, days 11–14 | **core**, days 8–12, owner A with C on the compositing |
| 2.5D canvas overlay | the live picture | kept for synthetic live mode and the judges' demo |
| Demo moments | one golden synthetic match | 4–6 real clip moments (one per featured feature: Sliding Doors, Fourth Official, Oracle, Dugout) plus the synthetic golden match for everything else |
| Budget | ≈ $25 | + Gemini video tagging (≈ $0.01 per clip-minute at low resolution) + nothing else; still under $30 |
| Day-7 build | unchanged | unchanged (synthetic); the footage layer is days 8–12 |

Real club and player names appear in overlays only for the featured clips and only under the permission artefact; the synthetic league stays fictional.

## 5. New and changed tickets (append to TASKS.md)

| ID | Title | Owner | Day | Hours | Depends on | Acceptance |
|---|---|---|---|---|---|---|
| T-102 | Permission artefact and footage folder | B | 8 | 1 | T-001 | `docs/permissions/` contains the written permission; `data/footage/` git-ignored; `data/footage/SOURCES.md` template; CI `no-media-in-repo` job passes |
| T-103 | Shot segmentation | A | 8 | 4 | T-102 | `python -m pitchwatch.shots clip.mp4` writes `shots.json` with steady wide shots ≥ 4 s; manual review file |
| T-104 | Pitch calibration | A | 8–9 | 6 | T-103 | homography per frame; reprojection error ≤ 1.5 m on 20 hand-marked points; keypoint model CC BY 4.0 attribution in `docs/DATA.md` |
| T-105 | Detection, tracking, team assignment | A | 9 | 6 | T-104 | RF-DETR 1.11.2 + `trackers.ByteTrackTracker` 2.6.1; players → pitch metres; team labels; evaluation on 200 hand-labelled frames: player recall ≥ 0.9; ball recall reported, no threshold |
| T-106 | Gemini event tagging | B | 9 | 3 | T-102, T-008 | `gemini-3.8-flash` agentic video → `event.schema.json`; cost in ledger; agreement with tracking-derived events reported |
| T-107 | Moment freeze and hand-correction tool | A | 10 | 5 | T-105, T-016 | `moments/<t>.json` → synthetic `State`; a small web page to drag players on the freeze frame; role-prior fill for missing players |
| T-108 | Real-frame compositing | C | 10–11 | 8 | T-104, T-107, T-041 | ghost futures, alternative trail, highlights and referee line drawn on the frozen frame with ≤ 2 px drift against the pitch lines; export PNG and clip |
| T-109 | Featured moments: select and precompute | A+B | 11 | 6 | T-107, T-042 | 4–6 moments, each with counterfactual, explanation (Opus, batch), Fact Checker pass, hand review; cache entries keyed per clip |
| T-110 | Video v2 with real clips | C | 12–13 | 8 | T-108, T-109 | storyboard updated: scenes 2, 3 and 5 on real clips; no clip outside the permission; `docs/video/VERSION` bumped |
| T-111 | README and JUDGES update for footage | B | 13 | 2 | T-110 | permission referenced; limits stated; clips not in repo; judges' streaming note |

Removed: the `/replay3d` tickets (3D scene) are dropped from M2; their hours fund T-108. T-096/T-097-style Pitchwatch tickets (optional) are superseded by T-103 to T-106.

## 5b. Shortlisted clips (verified Premier League channel uploads, 21 Oct 2026)

See `data/footage/SOURCES.md` for the full table. Primary: Liverpool v Man City 2025/26 "Final 20 Minutes In Full" (37 min continuous) for Sliding Doors and the Oracle; Manchester United v Manchester City 2025/26 (25 min) for a second Sliding Doors moment and Dugout; Arsenal v Chelsea 2025/26 (25 min) for the Decision Index and the Panel; Manchester United v Spurs 2024/25 (25 min, red card) for the Fourth Official. Warning: the channel's "Club highlights 2026/27" playlist is club-channel uploads and is outside the permission.

## 6. What the user must provide

1. The written permission (section 1).
2. Four to six clips from the Premier League's official channel, each containing at least one steady wide shot of a decisive moment (a shot taken when a pass was on; a disallowed goal; a late tactical change). Drop them in `data/footage/<clip-slug>/clip.mp4` with the `SOURCES.md` entry.
3. Confirmation that real club and player names may appear in overlays, or we keep names off the real clips and let the picture speak.
