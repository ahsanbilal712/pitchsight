# Kickoff corpus (git-ignored except this file)

Built by `scripts/generate_corpus.py`. `python scripts/generate_corpus.py --status` shows progress and
whether the corpus matches the current engine (`engine_hash` is a behavioural fingerprint: three minutes of seed
4242). Never mix the ranges.

| Seeds | Use | Files per seed (`<seed>/`) |
|---|---|---|
| 1–50 | evaluation, realism test | `events.jsonl`, `tracking.npz` (10 Hz), `truth.json` |
| 51–350 | calibration hold-out | `events.jsonl.gz`, `truth.json` |
| 1001–3000 | training (heads, policy) | `events.jsonl.gz`, `truth.json`, `samples.npz` |

`samples.npz`: `t_ms`, `period`, `S` (float16 [N,23,6]), `ball_z`, `holder`, `possession`, `score` [N,2],
`is_decision` (the tick before a pass, shot or clearance is kicked), `player_ids` (starting XI row order). Frames are
every 1 s plus every decision tick. Fixtures come from `League.fixture(seed)`: 56 ordered pairings, stride 17.

`progress.json` holds per-seed status, the fixture, the run time and per-team match stats; the realism test
(`tests/kickoff/test_realism.py`) reads seeds 1–50 from it when the engine hash matches, else simulates them.

Realism on seeds 1–50 (engine of 22 Oct, per-player top speeds; per team per match): pass completion 0.804, shots
13.8, goals 1.58, offsides 0.64, fouls 9.1, cards 1.07 (TECH_PLAN 1.4 ranges: 0.78–0.86, 8–16, 1.0–1.8). Movement:
outfield players 11.6 km per 90, keepers 5.7 km, fastest outfield player per match median 34.1 km/h.

`truth.json` (truth_version t2) phases carry side `H`/`A` (tactical phases) and side `M`: the hidden match regime
(`state_settled`, `state_transitional`, `state_chaotic`, 10–18 min each) that drives tempo, press and duel intensity.
The physics state machine recovers it at macro F1 0.771 on seeds 1–50.
