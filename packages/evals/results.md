# WHYLINE evaluation results (TECH_PLAN 1.11)

Written by `python -m evals.run_evals --seeds 1..50 --out packages/evals/results.md`; `python -m evals.gate packages/evals/results.json` fails CI when a measured number misses its threshold. Pending rows name the ticket that measures them.

| Number | Measured | Threshold | Result | Script | Data |
|---|---|---|---|---|---|
| State-detection precision/recall/F1 vs hidden truth | F1 0.772 (P 0.771, R 0.774) (evals/out/state_confusion.png) | F1 >= 0.75 | pass | `evals/state_detection.py` | 50 Kickoff matches, seeds 1-50, 269,950 s |
| Counterfactual calibration (Brier, reliability diagram) | Brier 0.0629 (base rate 0.090, log-loss 0.213) (evals/out/calibration.png) | Brier <= 0.18 | pass | `evals/calibration.py` | 300 held-out matches, 9,226 explained moments, n=200, 8 s, scripted_v1 |
| Placebo test (forcing the actual action reproduces the baseline) | 0.987 of 8,420 moments within the 95% interval | >= 0.95 | pass | `evals/calibration.py` | same moments |
| Policy metrics (table in TECH_PLAN 1.6) | top3_kind_target_accuracy 0.5050 misses >= 0.8 (cut line applied (T-037): scripted_v1 serves every counterfactual; docs/evidence/policy_gate_day4.md) | TECH_PLAN 1.6 gates | cut line | `policy/evaluate.py` | test split + 20 rollouts |
| Fact Checker planted errors caught | 500/500 = 100.0% (per-rule catch table in evals/out/planted_errors.json; stress set (not gated): 86% of numbers moved just past tolerance) | 100% caught | pass | `evals/planted_errors.py` | 500 outputs, one injected error each (5 kinds x 100) from 43 verified golden explanations, sampled with replacement |
| Fact Checker false rejects | 0/500 = 0.0% | <= 2% | pass | `evals/planted_errors.py` | 500 golden verified outputs (43 unique, sampled with replacement) |
| Cue latency p50/p95 (live) | pending T-080 (3 live matches) (interim: explained p95 12.9 s over 6 golden moments (T-032 probe D, docs/evidence/latency_probe_day3.md)) | fast <= 3 s p95; explained <= 15 s p95 | pending | `evals/latency.py` | 3 live matches |
| Cue latency (replay, simulated) | fast n=5; explained n=21; panel n=16; referee n=13 | none (replay is not gated) | reported | `evals/latency.py --source replay` | golden match from the cache |
| Cost per match | pending T-080 (3 live matches) | <= $2.50 | pending | `evals/cost.py (ledger)` | same 3 matches |
| Cost, golden match (all modes) | $2.31 (dev $0.34, live $0.42, precompute $1.55) | <= $2.50 | pass | `evals/cost.py (ledger)` | m_4242 |
| Project spend | $3.40 over 691 calls | <= $50 | pass | `evals/cost.py (ledger)` | data/spend/ledger.jsonl |
| Groundedness (own evaluator: numbers on screen bound to verified claims) | 150/150 = 1.000 | >= 0.95 | pass | `evals/groundedness.py` | 55 golden cues (500 once the demo season lands, T-085); Foundry optional (T-086) |
| Realism (Kickoff vs SkillCorner/DFL marginals) | pending T-073 | plots published; no threshold | pending | `evals/realism.py` | SkillCorner/DFL marginals |
| Resume (kill switch) | pending T-091 (20-run chaos test) (interim: the one-run CI test (T-051) resumes with the same cue id; docs/evidence/kill_resume.log) | 0 cues lost in 20 runs | pending | `tests/chaos/test_resume.py` | 20 runs |
| CI judge plausibility (reported only) | 76% of 25 explained cues ($0.20) | none | reported | `evals/judge.py` | 30 random explained golden cues, prompts/judge@1.md |
