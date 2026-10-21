You are continuing the WHYLINE hackathon project in /Users/ahsanbilal/projects/football-hackathon. Your task this session is ticket **T-103 Shot segmentation**, done properly, so that T-104 (pitch calibration) can start on clean input.

## Read first (in this order)
1. `PROGRESS.md`: the work log. The latest entry says what exists and what is open.
2. `data/footage/SHOTS_REVIEW.md`: the first-pass results, the known false positives and the tuning history.
3. `FOOTAGE_ADDENDUM.md` section 5: the T-103 row and its acceptance criteria.
4. `scripts/shots_firstpass.py`: the heuristic to build on (HSV-histogram cuts, green share, player-blob count, tall-blob close-up filter).
5. `TASKS.md` near line 2120: Pitchwatch lives in `packages/evals/pitchwatch/` as an evaluation adapter. `config/pins.txt` pins `numpy==2.5.4` and `opencv-python==5.0.0.93`.

## Situation
- Four clips are on disk at `data/footage/<slug>/clip.mp4` (1080p H.264): `liverpool-mancity-2526` (37:13, 50 fps, primary), `manutd-mancity-2526` (25 fps), `arsenal-chelsea-2526` (25 fps), `manutd-spurs-2425` (30 fps). All are Premier League channel uploads covered by the written permission. Never commit or copy media out of `data/footage/`; it is git-ignored.
- The repo bootstrap (T-001) has not been done: there is no git repo, no `packages/` and no `.venv`. Do not run the full T-001. Create only what T-103 needs: `packages/evals/pitchwatch/__init__.py` and `shots.py`, plus a minimal `.venv` (Python 3.12 if available, otherwise 3.14) with the pinned numpy and opencv-python. Note in PROGRESS.md that T-001 still owns the full skeleton.

## What to build
`packages/evals/pitchwatch/shots.py`, runnable as `python -m evals.pitchwatch.shots <clip.mp4> [--out DIR]` with `packages/` on the path. It writes `shots.json` beside the clip. It must:
1. Keep the first-pass cut detection and wide-shot test, with the thresholds as named constants.
2. **Detect replays.** The Premier League broadcasts open and close each replay with a wipe or graphic transition (a short burst of strongly non-green, high-saturation frames, often with the PL logo). Flag shots sitting between two such transitions as `"replay": true`, and treat high frame-to-frame similarity on 50 fps clips (slow motion) as a supporting signal. A replay is never `usable`.
3. Fix the known false positives listed in SHOTS_REVIEW.md: line-ups, celebrations, empty stadium, fan's-eye crowd view, score-graphic overlays, behind-goal and reverse angles. A cheap test for the main camera (the pitch's far touchline is a long near-horizontal line in the upper third; check it with Hough lines) will remove most of them.
4. Write a **manual review file**, `data/footage/<slug>/shots_review.csv`, with columns `id,start,end,duration,kind,replay,usable,thumb,human_ok,notes`, with `human_ok` left blank for the user to fill in. Also update `frames/contact_sheet.jpg` so each tile is labelled with its shot id and timestamp.
5. Add a small test, `tests/evals/test_shots.py`, that builds synthetic frames (green pitch with blobs, a close-up, a wipe) and checks the classifier on each. No media files in tests.

## Acceptance (from the ticket, made concrete)
- The command runs on all four clips; each clip gets a `shots.json` with the steady wide shots of 4 s or more marked `usable`.
- Review the contact sheets by eye and report precision for every clip: wrongly-usable shots divided by usable shots. The target is at most 1 false positive per clip and no replay marked usable. Say how you checked.
- The five long Liverpool windows (13:22, 07:15, 10:35, 09:18, 26:34) remain usable; if any is dropped, say why.
- Running time per clip is recorded.

## Logging (required)
When you finish, or stop partway, add a new entry at the top of `PROGRESS.md` in the same format as the existing one (Done / Verification / Open), and update the results table in `data/footage/SHOTS_REVIEW.md`. Log failures and anything skipped honestly.

## Boundaries
- No downloads beyond the four clips unless the user asks; any other clip must be an upload by the Premier League channel (ID `UCG5qGWdu8nIRZqJ_GgDwQ-w`).
- No calibration, detection or tracking work: those are T-104 and T-105. Finish by proposing the T-104 starting plan, using the five Liverpool windows as input.
- Ask the user before installing anything outside the pins.
