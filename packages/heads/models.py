"""Outcome heads. Each head loads its artefact at construction and raises if it
is missing: there is no silent fallback."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .features import CHAOS_FEATURES, GOAL8_FEATURES, PASS_FEATURES, SHOT_FEATURES, WINPROB_FEATURES

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"


class HeadArtifactMissing(FileNotFoundError):
    pass


def _artifact(name: str, artifacts: Path | None, suffix: str = ".txt") -> Path:
    path = Path(artifacts or ARTIFACTS) / f"{name}{suffix}"
    if not path.exists():
        raise HeadArtifactMissing(f"{path} is missing; train it with python -m heads.train")
    return path


class _Isotonic:
    """Piecewise-linear isotonic map stored as JSON knots ({x: [...], y: [...]})."""

    def __init__(self, path: Path) -> None:
        knots = json.loads(path.read_text(encoding="utf-8"))
        self.x, self.y = np.asarray(knots["x"]), np.asarray(knots["y"])

    def __call__(self, p: np.ndarray) -> np.ndarray:
        return np.interp(p, self.x, self.y)


class _LGBHead:
    name = ""
    features: list[str] = []

    def __init__(self, artifacts: Path | None = None) -> None:
        import lightgbm as lgb

        self.booster = lgb.Booster(model_file=str(_artifact(self.name, artifacts)))
        meta = json.loads(_artifact(self.name, artifacts, ".metrics.json").read_text(encoding="utf-8"))
        self.metrics = meta
        self.calibrator = None
        if meta.get("calibration") == "isotonic":
            self.calibrator = _Isotonic(_artifact(self.name, artifacts, ".iso.json"))

    def _raw(self, df: pd.DataFrame) -> np.ndarray:
        missing = [f for f in self.features if f not in df.columns]
        if missing:
            raise KeyError(f"{self.name}: missing feature columns {missing}")
        return self.booster.predict(df[self.features].to_numpy(dtype=np.float64))

    def _binary(self, df: pd.DataFrame) -> np.ndarray:
        p = self._raw(df)
        return self.calibrator(p) if self.calibrator is not None else p


class XGHead(_LGBHead):
    name, features = "xg", SHOT_FEATURES

    def predict(self, shots: pd.DataFrame) -> np.ndarray:
        return self._binary(shots)


class PassHead(_LGBHead):
    name, features = "pass", PASS_FEATURES

    def predict(self, passes: pd.DataFrame) -> np.ndarray:
        return self._binary(passes)


class WinProbHead(_LGBHead):
    name, features = "winprob", WINPROB_FEATURES

    def predict(self, states: pd.DataFrame) -> np.ndarray:
        """[n, 3]: P(home win), P(draw), P(away win)."""
        return np.asarray(self._raw(states)).reshape(len(states), 3)


class GoalIn8sHead(_LGBHead):
    """One model over (state, side): side 0 = the team in possession scores within 8 s, side 1 = the other team."""
    name, features = "goal8s", GOAL8_FEATURES + ["side"]

    def predict(self, states: pd.DataFrame) -> np.ndarray:
        """[n, 2]: P(home scores within 8 s), P(away scores within 8 s). Needs `poss_team` (0 home, 1 away)."""
        att = self._binary(states.assign(side=0))
        dfn = self._binary(states.assign(side=1))
        home_poss = states["poss_team"].to_numpy() == 0
        return np.stack([np.where(home_poss, att, dfn), np.where(home_poss, dfn, att)], axis=1)


class ChaosHead:
    """Logistic P(possession changes hands within 10 s) over the 12 chaos features."""
    name, features = "chaos", CHAOS_FEATURES

    def __init__(self, artifacts: Path | None = None) -> None:
        model = json.loads(_artifact(self.name, artifacts).read_text(encoding="utf-8"))
        self.mean, self.scale = np.asarray(model["mean"]), np.asarray(model["scale"])
        self.coef, self.intercept = np.asarray(model["coef"]), float(model["intercept"])
        self.metrics = json.loads(_artifact(self.name, artifacts, ".metrics.json").read_text(encoding="utf-8"))

    def predict(self, features) -> np.ndarray:
        X = features[self.features].to_numpy(dtype=np.float64) if isinstance(features, pd.DataFrame) \
            else np.atleast_2d(np.asarray(features, dtype=np.float64))
        z = ((X - self.mean) / self.scale) @ self.coef + self.intercept
        return 1.0 / (1.0 + np.exp(-z))


HEADS = {"xg": XGHead, "pass": PassHead, "winprob": WinProbHead, "goal8s": GoalIn8sHead, "chaos": ChaosHead}


def load_all(artifacts: Path | None = None) -> dict[str, object]:
    """Every head; raises HeadArtifactMissing at start-up if any artefact is absent."""
    return {name: cls(artifacts) for name, cls in HEADS.items()}
