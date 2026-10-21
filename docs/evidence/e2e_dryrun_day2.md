# End-to-end dry run on the current golden match (track C, 22 Oct 2026)

Local replay only (no Azure): api `python -m api.replay --seed 4242 --feed` with the demo script armed,
`python -m newsroom.supervisor --mode replay --match m_4242` on the same blackboard, overlay (analyst, casual),
studio and fan (Player-Cam on p_031) open in GPU Chromium, played 30:00 → 46:00 at x10 (speed 1 from 31:10 to 33:00
by the demo script). The golden cache had analytics, moments, pitch control, Fourth Official and dugout; no model
outputs (T-042) and no golden_moments.yaml (T-039) yet.

| Check | Result |
|---|---|
| Moments fed to the worker on the replay clock (new replay feed, 44f0136) | 64 of 64 up to 46:00 written on time; 51 done, 1 running, 12 queued (worker crash below) |
| Cues delivered to screens | 13 (state_change 3, fourth_official 5, big_chance 3, goal 2) |
| Chaos meter and studio blackboard from cached analytics | yes: chaos index, state, control, pressure, tempo, turnovers |
| Demo script | all four actions fired on the clock (speed 1 at 31:10, speed 10 at 33:00, kill at 44:10, veto at 45:15) |
| Kill at 44:10 | sent, but no run was between Tactician and Narrator (see worker crash) |
| Veto at 45:15 | waiting: no recap request exists yet (T-050) |
| Trace statuses | 124 cache_miss rows: expected until T-042 caches the model calls |
| Console or page errors on the four screens | none |

Defects found:
1. **newsroom worker exits after its first idle 0.5 s** (track B, `newsroom/worker.py:92`): `asyncio.wait_for(watcher.__anext__(), 0.5)`
   cancels the async generator on timeout, which closes it; the next `__anext__` raises StopAsyncIteration. The
   supervisor restarted it 61 times in three minutes. Reported to track B with the fix.
2. **sqlite3.InterfaceError in the api ticker** (track C, fixed in 13f5c02): the kill thread shared the api's sqlite
   connection; `SqliteBlackboard._exists` queries without its lock (reported to track B).
3. Studio Blackboard unit column clipped "passes_per_min" (fixed).

To repeat: the script used is in this session's scratchpad; the same steps are `scripts/record_demo.sh` plus the
supervisor command above.

## Re-run on HEAD after track B's fixes (076ea60, 72b0f55)

Same setup, 30:00 → 46:00 at x10.

| Check | Result |
|---|---|
| Worker restarts | none apart from the scripted kill (61 before the fix) |
| Kill at 44:10 | `kill target=newsroom run_id=run_m_4242_mo_00062 at_executor=tactician`, `restart pid=13292` 0.11 s later, `resume run_id=run_m_4242_mo_00062 checkpoint_id=4f3147bd-…` 0.67 s after that |
| Moments | 61 done, 2 running, 1 queued at 46:00 (x10) |
| Cues | 16 (state_change 4, fourth_official 6, big_chance 3, goal 2, recap 1) |
| Tracebacks in api or newsroom logs | none; no console errors on the four screens |
| Trace statuses | cache_miss 146 and Panel `error` 18 (CacheMiss): all expected until T-042 |

Still open for the recording:
- The resumed run's cue was suppressed by the Director, so the fourth evidence line (`cue c_… delivered
  resumed_from_checkpoint=…`) did not appear; the kill moment chosen in golden_moments.yaml (T-039) must be one whose
  cue is delivered.
- No `interrupted` trace row was written for the killed run, so the studio cannot show it red (T-051 step 2).
- The studio now colours `error` rows red as well as cache_miss and interrupted.
