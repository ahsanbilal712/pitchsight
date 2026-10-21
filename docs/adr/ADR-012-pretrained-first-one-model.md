# ADR-012: Pretrained models wherever one exists; one model needs a training run of its own

## Status

Accepted, 2026-10-21

## Context

- No football behaviour model with public weights exists (audit A.1 row 21). The closest reusable code is Sports-Traj/UniTraj-pytorch (Apache-2.0, 1.77M parameters), MART (MIT) and baller2vec++ (MIT). The on-ball decision policy therefore has to be trained.
- Behaviour cloning in gfootball is proven: TiKick's plain BC baseline reaches a 0.834 win rate from 21,947 episodes (audit B.1). Published models are 2 to 20M parameters.
- Measured on this Mac: the set transformer is 4.7M parameters and trains at 2,474 samples/s on MPS, 0.7 h per epoch (audit A.2, `DEMO_MASTERPLAN_50USD.md` section 5). TECH_PLAN 1.6 plans 8 epochs over about 6M samples, about 5.6 h (estimate).
- Outcome heads are standard and low risk: 2,000 Kickoff matches give about 60k shots and about 2M passes, and gradient-boosted trees train in minutes (audit B.3).
- Budget: $50 total, with a rented GPU priced at about $0.26/h (T4) or $1.90/h (A100) as the alternative (audit A.1 row 51, B.7).
- Rules: projects must use synthetic data (rules 4.7). Real tracking is licence-clean only for SkillCorner (MIT) and DFL (CC BY 4.0), and the audit recommends validation use only (B.6, C.4).
- Training data for the policy is `Dtradke/grf_tracking_data` plus Kickoff matches. The repository has no LICENSE file; the arXiv listing shows CC0 for the paper (`config/pins.txt`, TECH_PLAN 1.6). This dataset is not in the audit's Part A table.
- Vision: RF-DETR 1.11.2 is Apache-2.0 with COCO weights that auto-download. `roboflow/sports` YOLOv8 weights are AGPL-3.0 (audit A.1 rows 24 and 25).

## Decision

`DecisionPolicy` (set transformer: input linear F to 256, six encoder layers, d=256, 8 heads, FFN 1024; about 4.9M parameters, 4.7M measured in the spike) is the one neural model trained for an overnight run. It is trained by `policy.train` on the Mac GPU (`mps`) with AdamW at 3e-4, batch 256, on Kickoff and GRF data, and gated by `policy/evaluate.py`. `rollout` enforces the gate from `metrics.json`. The scripted fallback (`ScriptedRule`) is already wired (ADR-002).

The other learned components are small and local: `XGHead`, `PassHead`, `WinProbHead` and `GoalIn8sHead` are LightGBM and train in minutes on CPU; `ChaosHead` is logistic; `MomentEncoder` is a small torch autoencoder (about 20 minutes on MPS, estimate) followed by k-means. Everything else is pretrained: Claude and Gemini (ADR-004), and for the optional Pitchwatch adapter RF-DETR (`rfdetr==1.11.2`, COCO-pretrained) with `trackers.ByteTrackTracker`. There is no fine-tuned narrator. SkillCorner and DFL are used in `evals/realism.py` for validation only.

## Alternatives rejected

- A learned world model or per-tick policy: see ADR-001 and ADR-002.
- GRF_MARL or TiZero weights as the behaviour model: they control 10 outfield players with a built-in keeper, need their own feature encoders and a Python 3.9 stack, and play in an "RL style" (audit B.1, C.5).
- A rented GPU for training: unnecessary at 5.6 h on the Mac, and it spends the $50.
- A fine-tuned narrator in Foundry: optional in the audit, about $45 plus $30 to $60 of generation, and a few-shot model with the Fact Checker gives the same verified lines (B.5).
- Training on SkillCorner or DFL: risky under rules 4.7; validation only.

## Consequences

- Positive: $0 training. A failed policy does not sink the project because the scripted fallback is already wired and the gate is automatic.
- Negative: the claim is "one model needs an overnight run", not "one model is trained". The heads, the chaos head and `MomentEncoder` are also trained, but each is small (minutes on CPU, or about 20 minutes on MPS), and each needs its own calibration or cluster check.
- Negative: the GRF licence is unresolved. Until the authors confirm (email in T-012), derived weights are not published beyond the repo's own artefacts. If there is no reply by day 10 (31 Oct), publish Kickoff-only weights (TECH_PLAN 1.13).
- Negative: "about 6M samples" is an estimate. The audit counts 6M frames for 2,000 matches, and TECH_PLAN 1.14 puts on-ball decisions at about 1,500 per match, so decision samples may be nearer 3M before GRF data. The training time would shrink accordingly.
- Negative: policy gates are estimates until the first run (TECH_PLAN 1.6). GRF labels come from heuristics, and RL-style play can carry into the policy (audit B.1).
- Negative: MPS float differences could change sampling, so logits move to CPU before `torch.multinomial` (TECH_PLAN 1.5).

## Related

- TECH_PLAN 1.4 (policy, heads), 1.5 (determinism), 1.6, 1.11, 1.13.
- ADR-001, ADR-002, ADR-004.
- Config: `config/pins.txt`. Schemas: `schemas/counterfactual.schema.json`.
- Audit: A.1 rows 21, 24, 25, 51, A.2, B.1, B.3, B.5, B.6, C.4.
