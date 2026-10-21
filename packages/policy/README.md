# policy

Learned on-ball decision policy (decision-only, ADR-002).

Interface restated from `TECH_PLAN.md` section 1.4 "policy (learned decision model)" (TECH_PLAN wins on conflict).
Tests live in `tests/policy/`.

```python
class DecisionPolicy(torch.nn.Module):
    def forward(self, tokens: Tensor[B,23,F], ctx: Tensor[B,G]) -> PolicyOut    # kind_logits [B,5], pass_logits [B,11] (10 teammates + mask), carry_logits [B,8]
    def act(self, state: State, generator: torch.Generator) -> list[Action]       # samples per world
def build_dataset(grf_dir: Path, kickoff_dir: Path, out: Path, split_seed: int) -> DatasetReport
def train(config: TrainConfig) -> TrainReport
def evaluate(ckpt: Path, test: Path, n_rollouts: int = 20) -> EvalReport        # thresholds in 1.6
```

Device: `mps` when available. Checkpoints: `packages/policy/artifacts/policy_v1.pt` plus `metrics.json`. Failure behaviour: if `metrics.json` fails thresholds, `rollout` refuses to load it unless `WHYLINE_ALLOW_UNGATED_POLICY=1`. Libraries: torch 2.14.1, pandas (pin at T-001).
