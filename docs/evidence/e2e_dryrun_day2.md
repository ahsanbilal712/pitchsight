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
