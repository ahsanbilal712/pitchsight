# WHYLINE evaluation results

Written by `python -m evals.run_evals --seeds 1..50 --out packages/evals/results.md`; `python -m evals.gate packages/evals/results.json` fails CI when a measured number misses its threshold.

| Number | Measured | Threshold | Result | Script | Data |
|---|---|---|---|---|---|
| State-detection precision/recall/F1 vs hidden truth | F1 0.772 (P 0.771, R 0.774) (evals/out/state_confusion.png) | F1 >= 0.75 | pass | `evals/state_detection.py` | 50 Kickoff matches, seeds 1-50, 269,950 s |
| Counterfactual calibration (Brier, reliability diagram) | Brier 0.0629 (base rate 0.090, log-loss 0.213) (evals/out/calibration.png) | Brier <= 0.18 | pass | `evals/calibration.py` | 300 held-out matches, 9,226 explained moments, n=200, 8 s, scripted_v1 |
| Placebo test (forcing the actual action reproduces the baseline) | 0.987 of 8,420 moments within the 95% interval | >= 0.95 | pass | `evals/calibration.py` | same moments |
| Learned decision policy | top3_kind_target_accuracy 0.5050 misses >= 0.8 (counterfactuals use the scripted_v1 engine) | policy gates | reported | `policy/evaluate.py` | test split + 20 rollouts |
| Fact Checker planted errors caught | 500/500 = 100.0% (per-rule catch table in evals/out/planted_errors.json; stress set (not gated): 86% of numbers moved just past tolerance) | 100% caught | pass | `evals/planted_errors.py` | 500 outputs, one injected error each (5 kinds x 100) from 43 verified golden explanations, sampled with replacement |
| Fact Checker false rejects | 0/500 = 0.0% | <= 2% | pass | `evals/planted_errors.py` | 500 golden verified outputs (43 unique, sampled with replacement) |
| Cue latency (live, explained) | explained p95 12.9 s over 6 golden moments | explained <= 15 s p95 | pass | `evals/latency.py` | 6 golden moments, live model calls |
| Cue latency (replay, simulated) | fast n=5; explained n=21; panel n=16; referee n=13 | none (replay is not gated) | reported | `evals/latency.py --source replay` | golden match from the cache |
| Cost, golden match (all modes) | $2.31 (dev $0.34, live $0.42, precompute $1.55) | <= $2.50 | pass | `evals/cost.py (ledger)` | m_4242 |
| Project spend | $6.81 over 1403 calls | <= $50 | pass | `evals/cost.py (ledger)` | data/spend/ledger.jsonl |
| Groundedness (own evaluator: numbers on screen bound to verified claims) | 150/150 = 1.000 | >= 0.95 | pass | `evals/groundedness.py` | 55 golden cues |
| Resume (kill switch) | killed between Tactician and Narrator, resumed with the same cue id | 0 cues lost | pass | `tests/chaos/test_resume.py` | CI job chaos-resume |
| CI judge plausibility (reported only) | 76% of 25 explained cues ($0.20) | none | reported | `evals/judge.py` | 30 random explained golden cues, prompts/judge@1.md |
