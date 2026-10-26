# heads

LightGBM outcome heads and the moment encoder.

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

Train: `PYTHONPATH=packages python -m heads.train --matches data/matches/corpus --out packages/heads/artifacts --seed 4242 [--limit N]`.

- `features.py`: feature tables from training matches 1001–3000 (`samples.npz` decision frames and 1 Hz frames).
  Column lists `SHOT_FEATURES`, `PASS_FEATURES`, `GOAL8_FEATURES`, `WINPROB_FEATURES`, `CHAOS_FEATURES`;
  `state_features(...)` builds goal-in-8-s features from raw arrays (used by the rollout hand-off).
- `models.py`: heads load `artifacts/<head>.txt` and `<head>.metrics.json` at construction and raise
  `HeadArtifactMissing` if absent. `GoalIn8sHead` is one model over (state, side); `ChaosHead` is logistic (JSON).
- `train.py`: split 80/10/10 by match seed with `default_rng(4242)`; numbers in `metrics.json` are on the test split.
- `calibration.py`: ECE (10 equal-width bins; class-wise mean for win probability) and reliability diagrams.
