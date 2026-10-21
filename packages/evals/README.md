# evals

Evaluation harness producing evals/results.md.

Interface restated from `TECH_PLAN.md` section 1.4 "evals, demo" (TECH_PLAN wins on conflict).
Tests live in `tests/evals/`.

`evals/run_evals.py` produces `evals/results.md` (1.11). `demo/record_demo.py` (Playwright, pin at T-001) records the screens (1.9). `demo/demo_script.yaml` drives kill-switch and veto.
