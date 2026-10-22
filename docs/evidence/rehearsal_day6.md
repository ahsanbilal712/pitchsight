# T-062 rehearsal and v1 recording

22 Oct 2026, track C. **Provisional:** recorded on the golden cache at 405fd91 (aba00ab plus the T-057 hand
reviews in 72bfb4a and 405fd91), before the T-057 prompt bump and regeneration (tactician@4, narrator@3). That
regeneration waits on the owner's per-match cap decision. If it is approved, re-record only the shots whose cue text
changed; the frozen-cache guard and the manifest diff show which (coordinator, 22 Oct).

## Rehearsal (full golden match, local replay)

Setup: `python -m api.replay --seed 4242 --feed` with `WHYLINE_DEMO_SCRIPT=packages/demo/demo_script.yaml`,
`python -m newsroom.supervisor --mode replay --match m_4242` on the same fresh blackboard, overlay (analyst, casual),
studio and fan (Player-Cam) open in GPU Chromium. Played 00:00 → 90:00 at x10, with the demo script's x1 from 76:52 to
77:10.

| Measure | Result |
|---|---|
| Moments run | 123 done + 2 in flight at 90:00 (the last moment and the held full-time recap) of 125 |
| Cues | 55 delivered, 55/55 verified, 0 template |
| Trace rows by status | awaiting_producer 1, delivered 55, dropped 43, interrupted 1, invalid_output 26, no_counterfactual 27, ok 438, producer_vetoed 1, rejected 23, routed 152, suppressed 52, verified 88 |
| **cache_miss** | **0** |
| **error** | **0** |
| interrupted | 1: the scripted kill (narrator on mo_00060, "newsroom worker killed; the run resumes from its last checkpoint") |
| Producer | half-time recap request vetoed by the demo script at 45:15; full-time recap held |
| Tracebacks (api, newsroom) / screen console errors | 0 / 0 |

Kill-switch evidence (TECH_PLAN 1.7, the four lines in order):

```
2026-10-22T17:41:34.330 kill target=newsroom run_id=run_m_4242_mo_00060 at_executor=tactician
2026-10-22T17:41:34.442 restart pid=98774
2026-10-22T17:41:35.391 resume run_id=run_m_4242_mo_00060 checkpoint_id=85c16c9c-01f5-4762-b247-7cd1d294e7d9
2026-10-22T17:41:35.650 cue c_000601 delivered resumed_from_checkpoint=85c16c9c-01f5-4762-b247-7cd1d294e7d9
```

No miss appeared, so no moment went back to track B.

## Checks

- `python scripts/check_cue_evidence.py --seed 4242`: OK (57 cues, 201 claims, 0 problems).
- `python scripts/scan_banned.py data/matches/4242/cache apps/*/src`: 889 files, 0 hits (one cached Panel headline
  with a banned betting word was hand-reviewed by track B first, 405fd91).

## Recording (packages/demo/out, git-ignored)

`scripts/record_t062_sessions.sh <rehearsal dir> packages/demo/out` (GPU Chromium, DPR 1, `record_video_dir`):
- **Session 1**, fresh blackboard with the demo script armed and the newsroom running, so the beats happen in the
  take: `panel_kill_studio` (kill at 41:37 → `kill target=newsroom run_id=run_m_4242_mo_00060 at_executor=tactician`,
  restart, resume, `c_000601` delivered with resumed_from_checkpoint; the studio's one red row is that run's
  `interrupted`) and `veto_studio` (half-time recap request vetoed by the demo script). Each live beat has its own
  fresh session: a first veto take after the kill take found the worker still busy with the 41:51 Panel run, so
  the recap request arrived after the take; re-taken alone, the request shows on the producer panel at 45:22
  (Approve / Veto / Hold, trace `awaiting_producer`) and the demo script vetoes it after 3 s of match time.
- **Session 2**, the rehearsed blackboard, no newsroom, demo script off: every other shot, with each cue on screen at
  its time.

| Shot | Size | Take (play → end) | Keyframes |
|---|---|---|---|
| `dugout.webm` | 1920x1080 | 10.1 s | dugout_6002.png |
| `fourth_official.webm` | 1920x1080 | 9.1 s | fourth_official_6606.png |
| `halftime.webm` | 1920x1080 | 10.1 s | halftime_4505.png |
| `opener_3d.webm` | 1920x1080 | 7.1 s | opener_3d_7652.png |
| `oracle.webm` | 1920x1080 | 12.0 s | oracle_8330.png |
| `panel_kill_studio.webm` | 1920x1080 | 40.1 s | panel_kill_studio_4139.png, panel_kill_studio_4157.png |
| `sliding_doors_2d.webm` | 1920x1080 | 16.1 s | sliding_doors_2d_7656.png, sliding_doors_2d_7701.png |
| `sliding_doors_3d_player.webm` | 1920x1080 | 5.1 s | sliding_doors_3d_player_7659.png |
| `sliding_doors_3d_wide.webm` | 1920x1080 | 7.1 s | sliding_doors_3d_wide_7704.png |
| `split_analyst.webm` | 1920x1080 | 12.1 s | split_analyst_7700.png |
| `split_casual.webm` | 1920x1080 | 12.1 s | split_casual_7700.png |
| `split_player_cam.webm` | 390x844 | 12.0 s | split_player_cam_7700.png |
| `veto_studio.webm` | 1920x1080 | 37.8 s (re-take) | veto_studio_4522.png, veto_studio_4532.png |

The `.webm` files run longer than the take: the page load before `ready` and, under load (average 73), a slow
`ctx.close()` that keeps filming the paused page. `<shot>.json` holds `ready_s`, `play_s` and `end_s`; the edit (T-063)
cuts each clip to play → end. `architecture` is a page the edit writes and records (T-063).

Fixed while recording (all re-recorded): `/replay3d` never reported ready while the replay was paused (the
recorder pauses before each shot); a single-line offside call had no margin label (now from its verified metres
claim, "1.1 m"); the 2D ghost futures are clipped to the pitch plus 2 m; the Player-Cam card read no Decision Index
(now the golden cache's rollout index, T-048); the Player-Cam shot follows the Sliding Doors actor (Novacek), whom
the Director lists in targets.players; fan cards label Panel debates "the panel", not "recap".

## Verification

`python scripts/check_cue_evidence.py --seed 4242 && python scripts/scan_banned.py data/matches/4242/cache apps/*/src
&& ls packages/demo/out/*.webm`: exit 0 (57 cues, 201 claims, 0 problems; 889 files, 0 hits; 13 shots).
