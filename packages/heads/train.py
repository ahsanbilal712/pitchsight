"""Train the five outcome heads on Kickoff training matches.

    python -m heads.train --matches data/matches/corpus --out packages/heads/artifacts --seed 4242 [--limit 200]

Uses training seeds 1001-3000 that have samples.npz, first `--limit` by seed. Splits
80/10/10 by match seed (never by row) with numpy.random.default_rng(seed). LightGBM trains on the train split with
early stopping on val; every reported number is on the test split. Per head: <head>.txt, <head>.metrics.json,
<head>.calibration.png; plus metrics.json with all heads. Per-match feature tables are cached under
<matches>/_features/<FEATURE_VERSION>/ so a rerun on more matches only extracts the new ones.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

from .calibration import ece, ece_multiclass, reliability_diagram
from .features import (
    CHAOS_FEATURES,
    FEATURE_VERSION,
    GOAL8_FEATURES,
    PASS_FEATURES,
    SHOT_FEATURES,
    WINPROB_FEATURES,
    match_tables,
)

TRAIN_SEEDS = range(1001, 3001)
TABLES = ("shots", "passes", "goal8s", "chaos", "winprob")
# Gate thresholds (reported in v0)
THRESHOLDS = {"xg": {"ece_max": 0.03}, "pass": {"ece_max": 0.03}, "winprob": {"ece_max": 0.03},
              "goal8s": {"ece_max": 0.01}, "chaos": {"auc_min": 0.70}}
LGB_PARAMS = {"learning_rate": 0.05, "num_leaves": 31, "min_data_in_leaf": 100, "feature_fraction": 0.9,
              "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0, "verbose": -1, "deterministic": True,
              "force_row_wise": True, "num_threads": 4}


@dataclass
class Report:
    heads: dict[str, dict] = field(default_factory=dict)
    n_matches: int = 0
    split: dict[str, list[int]] = field(default_factory=dict)


def training_seeds(matches_dir: Path, limit: int | None) -> list[int]:
    seeds = [s for s in TRAIN_SEEDS if (matches_dir / str(s) / "samples.npz").exists()]
    return seeds[:limit] if limit else seeds


def _tables_for(args: tuple[str, str]) -> dict[str, pd.DataFrame]:
    match_dir, cache = args
    path = Path(cache)
    if path.exists():
        return pd.read_pickle(path)
    tables = match_tables(match_dir)
    tmp = path.with_suffix(".tmp")
    pd.to_pickle(tables, tmp)
    tmp.replace(path)
    return tables


def load_tables(matches_dir: Path, seeds: list[int], workers: int) -> dict[str, pd.DataFrame]:
    cache = matches_dir / "_features" / FEATURE_VERSION
    cache.mkdir(parents=True, exist_ok=True)
    jobs = [(str(matches_dir / str(s)), str(cache / f"{s}.pkl")) for s in seeds]
    with Pool(workers) as pool:
        parts = pool.map(_tables_for, jobs, chunksize=4)
    return {k: pd.concat([p[k] for p in parts if len(p[k])], ignore_index=True) for k in TABLES}


def split_seeds(seeds: list[int], seed: int) -> dict[str, list[int]]:
    order = np.random.default_rng(seed).permutation(sorted(seeds))
    n = len(order)
    a, b = int(round(0.8 * n)), int(round(0.9 * n))
    return {"train": sorted(map(int, order[:a])), "val": sorted(map(int, order[a:b])), "test": sorted(map(int, order[b:]))}


def _parts(df: pd.DataFrame, split: dict[str, list[int]]) -> dict[str, pd.DataFrame]:
    return {k: df[df["seed"].isin(v)].reset_index(drop=True) for k, v in split.items()}


def _auc(y, p) -> float:
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(y, p)) if len(set(np.asarray(y).tolist())) > 1 else float("nan")


def _binary_metrics(y, p) -> dict:
    from sklearn.metrics import average_precision_score, brier_score_loss, log_loss
    y, p = np.asarray(y), np.clip(np.asarray(p), 1e-7, 1 - 1e-7)
    return {"ece": ece(y, p), "auc": _auc(y, p), "brier": float(brier_score_loss(y, p)),
            "log_loss": float(log_loss(y, p, labels=[0, 1])), "pr_auc": float(average_precision_score(y, p)),
            "base_rate": float(y.mean()), "mean_pred": float(p.mean())}


def _lgb_train(X_tr, y_tr, X_va, y_va, params: dict, seed: int, monotone: list[int] | None = None):
    import lightgbm as lgb
    params = {**LGB_PARAMS, **params, "seed": seed}
    if monotone:
        params["monotone_constraints"] = monotone
    dtr = lgb.Dataset(X_tr, y_tr)
    dva = lgb.Dataset(X_va, y_va, reference=dtr)
    return lgb.train(params, dtr, num_boost_round=3000, valid_sets=[dva],
                     callbacks=[lgb.early_stopping(100, verbose=False)])


def _data_block(parts: dict[str, pd.DataFrame], split: dict[str, list[int]], seed: int) -> dict:
    return {"rows": {k: int(len(v)) for k, v in parts.items()}, "matches": {k: len(v) for k, v in split.items()},
            "split_seed": seed, "test_seeds": split["test"], "val_seeds": split["val"],
            "train_seed_range": [min(split["train"]), max(split["train"])]}


def _write(out: Path, name: str, booster, metrics: dict) -> None:
    if booster is not None:
        booster.save_model(str(out / f"{name}.txt"))
    (out / f"{name}.metrics.json").write_text(json.dumps(metrics, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def _train_binary_head(name: str, df: pd.DataFrame, features: list[str], split, seed: int, out: Path,
                       title: str, monotone: list[int] | None = None) -> dict:
    parts = _parts(df, split)
    booster = _lgb_train(parts["train"][features].to_numpy(float), parts["train"]["label"].to_numpy(),
                         parts["val"][features].to_numpy(float), parts["val"]["label"].to_numpy(), {
                             "objective": "binary"}, seed, monotone)
    p = booster.predict(parts["test"][features].to_numpy(float))
    y = parts["test"]["label"].to_numpy()
    m = {"head": name, "model": "lightgbm", "features": features, "feature_version": FEATURE_VERSION,
         "calibration": "none", "best_iteration": int(booster.best_iteration), "data": _data_block(parts, split, seed),
         "test": _binary_metrics(y, p), "thresholds": THRESHOLDS[name]}
    reliability_diagram({"test": (y, p)}, out / f"{name}.calibration.png", title,
                        f"{len(y):,} test rows from {len(split['test'])} held-out matches")
    _write(out, name, booster, m)
    return m


def train_all(matches_dir: Path, out_dir: Path, seed: int, limit: int | None = None, workers: int | None = None) -> Report:
    matches_dir, out = Path(matches_dir), Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    seeds = training_seeds(matches_dir, limit)
    if len(seeds) < 20:
        raise RuntimeError(f"only {len(seeds)} training matches with samples.npz in {matches_dir}")
    workers = workers or max(1, (os.cpu_count() or 2) - 2)
    print(f"extracting features from {len(seeds)} matches with {workers} workers", flush=True)
    t = load_tables(matches_dir, seeds, workers)
    split = split_seeds(seeds, seed)
    rep = Report(n_matches=len(seeds), split=split)

    rep.heads["xg"] = _train_binary_head("xg", t["shots"], SHOT_FEATURES, split, seed, out, "xG head",
                                         monotone=[-1, 1, 0, -1, 0, 0, 0, 0])
    rep.heads["pass"] = _train_binary_head("pass", t["passes"], PASS_FEATURES, split, seed, out, "Pass completion head")

    # goal in 8 s: one model over (state, side)
    g = t["goal8s"]
    stacked = pd.concat([g.assign(side=0, label=g["label_att"]), g.assign(side=1, label=g["label_def"])],
                        ignore_index=True)
    rep.heads["goal8s"] = _train_binary_head("goal8s", stacked, GOAL8_FEATURES + ["side"], split, seed, out,
                                             "Goal within 8 s head")

    # win probability: multiclass
    parts = _parts(t["winprob"], split)
    booster = _lgb_train(parts["train"][WINPROB_FEATURES].to_numpy(float), parts["train"]["label"].to_numpy(),
                         parts["val"][WINPROB_FEATURES].to_numpy(float), parts["val"]["label"].to_numpy(),
                         {"objective": "multiclass", "num_class": 3, "min_data_in_leaf": 50}, seed)
    P = booster.predict(parts["test"][WINPROB_FEATURES].to_numpy(float))
    y = parts["test"]["label"].to_numpy()
    from sklearn.metrics import log_loss
    m = {"head": "winprob", "model": "lightgbm multiclass", "features": WINPROB_FEATURES,
         "feature_version": FEATURE_VERSION, "calibration": "none", "best_iteration": int(booster.best_iteration),
         "data": _data_block(parts, split, seed), "thresholds": THRESHOLDS["winprob"],
         "test": {"ece": ece_multiclass(y, P), "ece_per_class": [ece(y == k, P[:, k]) for k in range(3)],
                  "log_loss": float(log_loss(y, np.clip(P, 1e-7, 1), labels=[0, 1, 2])),
                  "accuracy": float(np.mean(P.argmax(1) == y)), "class_rates": [float(np.mean(y == k)) for k in range(3)]}}
    reliability_diagram({c: (y == k, P[:, k]) for k, c in enumerate(("home win", "draw", "away win"))},
                        out / "winprob.calibration.png", "Win probability head",
                        f"{len(y):,} test states from {len(split['test'])} held-out matches")
    _write(out, "winprob", booster, m)
    rep.heads["winprob"] = m

    # chaos head: logistic regression
    from sklearn.linear_model import LogisticRegression
    parts = _parts(t["chaos"], split)
    Xtr = parts["train"][CHAOS_FEATURES].to_numpy(float)
    mean, scale = Xtr.mean(axis=0), Xtr.std(axis=0) + 1e-9
    lr = LogisticRegression(C=1.0, max_iter=2000)
    lr.fit((Xtr - mean) / scale, parts["train"]["label"].to_numpy())
    Xte = (parts["test"][CHAOS_FEATURES].to_numpy(float) - mean) / scale
    p = lr.predict_proba(Xte)[:, 1]
    y = parts["test"]["label"].to_numpy()
    (out / "chaos.txt").write_text(json.dumps({"model": "logistic", "features": CHAOS_FEATURES, "mean": mean.tolist(),
                                               "scale": scale.tolist(), "coef": lr.coef_[0].tolist(),
                                               "intercept": float(lr.intercept_[0])}, indent=1) + "\n",
                                   encoding="utf-8")
    m = {"head": "chaos", "model": "logistic", "features": CHAOS_FEATURES, "feature_version": FEATURE_VERSION,
         "calibration": "none", "data": _data_block(parts, split, seed), "test": _binary_metrics(y, p),
         "thresholds": THRESHOLDS["chaos"]}
    reliability_diagram({"test": (y, p)}, out / "chaos.calibration.png", "Chaos head: possession change within 10 s",
                        f"{len(y):,} test states from {len(split['test'])} held-out matches")
    _write(out, "chaos", None, m)
    rep.heads["chaos"] = m

    summary = {name: {"test": h["test"], "rows": h["data"]["rows"], "thresholds": h["thresholds"]}
               for name, h in rep.heads.items()}
    summary["_data"] = {"n_matches": rep.n_matches, "split_seed": seed, "feature_version": FEATURE_VERSION,
                        "matches_per_split": {k: len(v) for k, v in split.items()}}
    (out / "metrics.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m heads.train")
    ap.add_argument("--matches", type=Path, default=Path("data/matches/corpus"))
    ap.add_argument("--out", type=Path, default=Path("packages/heads/artifacts"))
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=None)
    args = ap.parse_args(argv)
    rep = train_all(args.matches, args.out, args.seed, args.limit, args.workers)
    for name, h in rep.heads.items():
        t = h["test"]
        line = ", ".join(f"{k} {t[k]:.4f}" for k in ("ece", "auc", "pr_auc", "base_rate", "accuracy") if k in t)
        print(f"{name:8s} rows {h['data']['rows']['train']:>9,} train | {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
