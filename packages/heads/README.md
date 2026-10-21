# heads

LightGBM outcome heads and the moment encoder.

Interface restated from `TECH_PLAN.md` section 1.4 "heads (outcome models)" (TECH_PLAN wins on conflict).
Tests live in `tests/heads/`.

```python
class XGHead:        def predict(self, shots: pd.DataFrame) -> np.ndarray          # features in 1.6
class PassHead:      def predict(self, passes: pd.DataFrame) -> np.ndarray
class WinProbHead:   def predict(self, states: pd.DataFrame) -> np.ndarray          # [n,3] home/draw/away
class GoalIn8sHead:  def predict(self, states: pd.DataFrame) -> np.ndarray          # [n,2] home, away
class ChaosHead:     def predict(self, features) -> np.ndarray                      # P(possession change within 10 s)
class MomentEncoder: def encode(self, pc, features) -> np.ndarray[64]; def phase(self, z) -> str
def train_all(matches_dir: Path, out_dir: Path, seed: int) -> Report
```

All heads are LightGBM (pin at T-001) except `MomentEncoder` (torch autoencoder). Artefacts in `packages/heads/artifacts/*.txt|.pt` with a `calibration.png` and `metrics.json` each. Failure behaviour: a missing artefact raises at start-up (never silently falls back). Tests: calibration ECE ≤ 0.03 on held-out; monotonicity sanity (xG rises as distance falls).
