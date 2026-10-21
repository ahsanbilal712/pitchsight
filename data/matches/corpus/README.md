# Kickoff corpus (git-ignored except this file)

Built by `scripts/generate_corpus.py` (T-014). `python scripts/generate_corpus.py --status` shows progress and
whether the corpus matches the current engine (`engine_hash` is a behavioural fingerprint: three minutes of seed
4242). Seed convention (TASKS.md): never mix the ranges.

| Seeds | Use | Files per seed (`<seed>/`) |
|---|---|---|
| 1–50 | evaluation, realism test | `events.jsonl`, `tracking.npz` (10 Hz), `truth.json` |
| 51–350 | calibration hold-out (T-040) | `events.jsonl.gz`, `truth.json` |
| 1001–3000 | training (heads T-015/T-025, policy T-027) | `events.jsonl.gz`, `truth.json`, `samples.npz` |

`samples.npz`: `t_ms`, `period`, `S` (float16 [N,23,6]), `ball_z`, `holder`, `possession`, `score` [N,2],
`is_decision` (the tick before a pass, shot or clearance is kicked), `player_ids` (starting XI row order). Frames are
every 1 s plus every decision tick. Fixtures come from `League.fixture(seed)`: 56 ordered pairings, stride 17.

`progress.json` holds per-seed status, the fixture, the run time and per-team match stats; the realism test
(`tests/kickoff/test_realism.py`) reads seeds 1–50 from it when the engine hash matches, else simulates them.

Realism on seeds 1–50 after T-014 tuning (per team per match): pass completion 0.834, shots 14.6, goals 1.59,
offsides 1.01, fouls 5.1, cards 0.54 (TECH_PLAN 1.4 ranges: 0.78–0.86, 8–16, 1.0–1.8).
