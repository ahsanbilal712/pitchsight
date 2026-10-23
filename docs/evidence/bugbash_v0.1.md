# Bug bash v0.1 (T-065, track A)

Run 23 Oct 2026 on the development Mac, HEAD at the time of each command. Every Verification command of T-001 to T-064 was run in order by a script (`PYTHONPATH=packages`, `OMP_NUM_THREADS=1`), adapted where the original would spend money, rewrite the frozen golden cache, re-run multi-hour jobs or needs Azure (deferred by owner direction); each adaptation is stated in the row. Results:

**52 pass, 2 fail (both machine load, not regressions), 2 not built (Azure), rest not run as listed.**

| Ticket | Owner | Command (as run) | Result | Time | Note |
|---|---|---|---|---|---|
| T-001 | B | `python scripts/check_pins.py && python -c "import agent_framework, mcp, anthropic, fastapi…` | pass | 6 s |  |
| T-002 | A | `python scripts/check_league.py` | pass | 0 s |  |
| T-003 | C | `python scripts/make_sample_stream.py --check` | pass | 0 s |  |
| T-004 | B | `pytest tests/tooling/test_secret_guard.py -q` | pass | 7 s |  |
| T-005 | B | — | not run |  |  skipped here: `make ci` is T-065's own verification, run separately below |
| T-006 | A | `pytest tests/kickoff -q` | pass | 77 s |  |
| T-007 | A | `pytest tests/kickoff/test_determinism.py -q && (cd data/matches/4242 && shasum -a 256 -c S…` | pass | 76 s |  |
| T-008 | B | `pytest tests/api/test_spend.py tests/newsroom/test_imports.py -q` | pass | 6 s | smoke_models.py (live model call) left out: no spend in a bug bash |
| T-009 | B | — | not run |  |  skipped: Azure deferred |
| T-010 | C | `npm --prefix apps/overlay run build && pytest tests/apps/test_overlay_smoke.py -q` | pass | 6 s |  |
| T-011 | C | `pytest tests/apps/test_pitch2d.py -q` | pass | 8 s | overlay build run once in T-010 |
| T-012 | A | `python packages/policy/grf_check.py data/grf/tiny_set && cat data/grf/coords_report.json |…` | pass | 5 s |  |
| T-013 | A | `pytest tests/physics -q` | pass | 6 s |  |
| T-014 | A | `pytest tests/kickoff/test_realism.py -q && python scripts/generate_corpus.py --status` | pass | 10 s |  |
| T-015 | A | `python -m heads.train --matches data/matches/corpus --out /private/tmp/claude-501/-Users-a…` | pass | 44 s | heads trained into a scratch folder (artefacts untouched) |
| T-016 | A | `pytest tests/rollout -q` | fail (load) | 117 s | perf budgets failed under machine load (GPU shared with tracking; load avg 90-160 from the Claude app and macOS services): MPS 1.33 s, scripted 90 s 1.84 s CPU. Passed idle at commit 3311003 (0.28 s, 1.26 s). Environmental, not a regression; re-run on an idle machine before v1.0. |
| T-017 | B | `pytest tests/blackboard -q` | pass (re-run) | 43 s | two cross-process tests fail only under the bug-bash runner's PYTHONPATH=packages (the child process cannot import tests.*); `pytest tests/blackboard -q` without it: 16 passed. |
| T-018 | B | `pytest tests/newsroom/test_graph.py -q` | pass | 4 s |  |
| T-019 | B | `pytest tests/newsroom/test_factcheck.py -q && python scripts/scan_banned.py data/league` | pass | 4 s |  |
| T-020 | B | `pytest tests/newsroom/test_narrator.py -q` | pass | 3 s | live-marked tests left out (model spend) |
| T-021 | B | `pytest tests/newsroom/test_director.py -q` | pass | 2 s |  |
| T-022 | C | `pytest tests/api/test_replay.py -q` | pass | 5 s |  |
| T-023 | C | `pytest tests/apps/test_overlay_components.py -q` | pass | 7 s |  |
| T-024 | C | `pytest tests/apps/test_ghost_trail.py -q` | pass | 30 s |  |
| T-025 | A | — | not run |  |  retrain left out (committed artefacts; heads tests run in T-015) |
| T-026 | A | `pytest tests/physics/test_auto_events.py -q` | pass | 10 s |  |
| T-027 | A | `pytest tests/policy/test_data.py -q` | pass | 13 s | dataset rebuild left out (hours); data tests run |
| T-028 | A | `pytest tests/policy/test_model.py -q && tail -n 3 packages/policy/artifacts/train_log.json…` | pass | 4 s |  |
| T-029 | B | `pytest tests/newsroom/test_scout.py -q` | pass | 25 s |  |
| T-030 | B | `pytest tests/mcp_server/test_tools.py -q` | pass | 14 s |  |
| T-031 | B | `pytest tests/newsroom/test_proposer.py -q` | pass | 6 s |  |
| T-032 | B | `pytest tests/newsroom/test_tactician.py -q` | pass | 2 s | live-marked tests left out |
| T-033 | C | `pytest tests/api/test_cues.py tests/api/test_fanout_perf.py -q` | pass | 12 s |  |
| T-034 | C | `npm --prefix apps/studio run build && pytest tests/apps/test_studio.py -q` | pass | 5 s |  |
| T-035 | C | `pytest tests/apps/test_studio_controls.py -q` | pass | 4 s |  |
| T-036 | A | `pytest tests/rollout/test_policy_perf.py tests/rollout/test_policy_determinism.py -q` | fail (load) | 19 s | same load as T-016: MPS 0.36-0.47 s vs 0.30 s budget; CPU path passes. |
| T-037 | A | — | not run |  |  policy evaluation re-run left out (hours; gate decision committed); gate.json read in T-056 |
| T-038 | B | `pytest tests/cache -q` | pass | 16 s |  |
| T-039 | A | `python scripts/validate_schemas.py` | pass | 4 s | precompute stages not re-run (frozen-cache rule; track B owns the cache); schemas validated |
| T-040 | A | — | not run |  |  calibration re-run left out (39 min; committed numbers read by T-056) |
| T-041 | B | `pytest tests/newsroom/test_panel.py -q` | pass | 2 s | live-marked tests left out |
| T-042 | B | `pytest tests/cache/test_batch.py -q && python scripts/check_spend.py` | pass | 14 s | model precompute not re-run (spend); batch tests and spend check run |
| T-043 | C | `npm --prefix apps/fan run build && pytest tests/apps/test_fan.py -q` | pass | 6 s |  |
| T-044 | C | `pytest tests/apps/test_player_cam.py -q` | pass | 4 s |  |
| T-045 | C | `pytest tests/apps/test_viewer_modes.py -q` | pass | 22 s |  |
| T-046 | A | `pytest tests/rollout/test_oracle.py -q` | pass | 10 s | oracle stage not re-run (cache) |
| T-047 | A | `pytest tests/rollout/test_dugout.py -q && python -m evals.dugout_log --seed 4242` | pass | 18 s |  |
| T-048 | A | `pytest tests/rollout/test_decision_index.py -q` | pass | 2 s | stage not re-run (cache) |
| T-049 | A | `pytest tests/fourth_official -q` | pass | 2 s | stage not re-run (cache) |
| T-050 | B | `pytest tests/newsroom/test_recap_veto.py -q` | pass | 18 s | recap stage not re-run (spend) |
| T-051 | B | `pytest tests/chaos/test_resume.py -q` | pass | 7 s |  |
| T-052 | B | — | not run |  |  skipped: Azure deferred |
| T-053 | C | — | not run |  |  no verification command in this range or not adapted |
| T-054 | A | `pytest tests/heads/test_moment_encoder.py -q` | pass | 2 s |  |
| T-055 | A | `python -m evals.state_detection --seeds 1..50 && python -m evals.planted_errors --n 500` | pass | 184 s |  |
| T-056 | A | `python -m evals.run_evals --seeds 1..50 --out packages/evals/results.md && python -m evals…` | pass | 186 s |  |
| T-057 | B | `python scripts/check_cue_evidence.py --seed 4242 && python scripts/validate_schemas.py && …` | pass | 4 s | import_review.py not re-run (writes the cache); evidence, schema and spend checks run |
| T-058 | B | `pytest tests/blackboard/test_cosmos.py -q` | not built | 2 s | not built (Azure deferred by owner direction): tests/blackboard/test_cosmos.py does not exist. |
| T-059 | B | `pytest tests/newsroom/test_telemetry.py -q` | not built | 1 s | not built (Azure telemetry deferred): tests/newsroom/test_telemetry.py does not exist. |
| T-060 | B | `pytest tests/tooling/test_frozen_guard.py -q` | pass | 2 s |  |
| T-061 | C | `pytest tests/demo/test_demo_script.py -q && python -m demo.record_demo --shots packages/de…` | pass | 7 s |  |
| T-062 | C | `python scripts/check_cue_evidence.py --seed 4242 && python scripts/scan_banned.py data/mat…` | pass | 3 s |  |
| T-063 | C | `python packages/demo/assemble.py packages/demo/edit_v1.yaml && ffprobe -v error -show_entr…` | pass | 39 s | assembles video (track C); run as given |
| T-064 | A | — | not run |  |  run separately below (clean replay) |

## T-065 verification: `make ci && bash scripts/clean_machine_replay.sh --runs 1`

- `make ci`: lint, schemas and spend pass; `unit` **465 passed, 3 failed, 3 errors** (386 s, load average 25-160 from the
  Claude app and macOS services). Failed: the three timing budgets (`test_fanout_perf` cue fan-out 50 ms,
  `test_perf` scripted 200 x 90 s, `test_policy_perf` MPS) — machine load, all passed idle. Errors: three
  `tests/cache/test_batch.py` tests, `asyncio.run() cannot be called from a running event loop` after the Playwright
  apps tests (the fixture calls `stage_newsroom` on the main thread; `pytest tests/cache` alone: 22 passed). Filed
  to track B with the fix.
- `clean_machine_replay.sh --runs 1`: **PASS**, cue-stream sha256 `b90e1e03...` (same as T-064), 55 cues all verified,
  0 refused connections.
- **T-065 not closed:** the verification command exits non-zero until the test_batch fix lands and the perf budgets
  are re-run on an idle machine.

## P0 / P1

- **No P0 open.**
- P1 (A, day 8): rollout perf budgets (`tests/rollout/test_perf.py`, `test_policy_perf.py`) fail whenever the machine is loaded; they measure process CPU / wall time against budgets with ~3% margin. Passed idle at T-036 (3311003). Re-run on an idle machine before v1.0; consider running them in CI only (ubuntu runner) or widening to a budget measured on the CI machine.
- P1 (A, day 8): T-104 reprojection gate open: 20 agent-marked points, refined calibration mean 0.32 m, max 2.21 m (far touchline at frame 41000) vs <= 1.5 m. Track C is adding the far touchline to its refinement.
- P1 (B, day 8): `tests/cache/test_batch.py` fixture runs `asyncio.run` on the main thread; errors in `make unit` after tests/apps. Fix sent to track B.
- P2 (B, when Azure resumes): T-058 / T-059 test files do not exist yet.

## Other findings during the bug bash (fixed)

- Fourth Official cues showed numbers no claim binds (closing speed, contact coordinates): fixed in 3193723.
- Clean-machine replay: one run stalled after mo_00020 (not recurred); harness now fails fast with stack dumps (3c9e478).
- Shot segmentation: highlight-package wipes were paired as replays and a pan to the bench was not a cut; reviewed overrides and wide-run trimming (1f7c839, 63c2534).
- Licence scanner rejected two permissive spellings (ISC, Apache 2.0): fixed by track B (73d7e40).
