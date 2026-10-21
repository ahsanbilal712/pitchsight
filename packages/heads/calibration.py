"""Calibration metrics and reliability diagrams for the outcome heads (TECH_PLAN 1.6)."""

from __future__ import annotations

from pathlib import Path

import numpy as np


def ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    """Expected calibration error: equal-width bins on [0, 1], |mean(p) - mean(y)| weighted by bin share."""
    y, p = np.asarray(y, dtype=float), np.asarray(p, dtype=float)
    if y.size == 0:
        return float("nan")
    idx = np.minimum((p * bins).astype(int), bins - 1)
    total = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            total += m.mean() * abs(p[m].mean() - y[m].mean())
    return float(total)


def ece_multiclass(y: np.ndarray, P: np.ndarray, bins: int = 10) -> float:
    """Class-wise ECE averaged over classes (one-vs-rest)."""
    y = np.asarray(y, dtype=int)
    return float(np.mean([ece(y == k, P[:, k], bins) for k in range(P.shape[1])]))


def reliability_curve(y: np.ndarray, p: np.ndarray, bins: int = 10) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(mean predicted, observed rate, count) per non-empty equal-width bin."""
    y, p = np.asarray(y, dtype=float), np.asarray(p, dtype=float)
    idx = np.minimum((p * bins).astype(int), bins - 1)
    pred, obs, n = [], [], []
    for b in range(bins):
        m = idx == b
        if m.any():
            pred.append(p[m].mean())
            obs.append(y[m].mean())
            n.append(int(m.sum()))
    return np.array(pred), np.array(obs), np.array(n)


def reliability_diagram(curves: dict[str, tuple[np.ndarray, np.ndarray]], path: Path, title: str,
                        subtitle: str = "") -> None:
    """Reliability diagram (10 bins) with one line per curve label: {label: (y, p)}."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(5.2, 5.0), dpi=110)
    lim = 0.0
    for label, (y, p) in curves.items():
        pred, obs, n = reliability_curve(y, p)
        ax.plot(pred, obs, marker="o", label=f"{label} (ECE {ece(y, p):.4f})")
        lim = max(lim, float(np.max(pred, initial=0)), float(np.max(obs, initial=0)))
    lim = 1.0 if lim > 0.3 else min(1.0, lim * 1.15 + 0.005)
    ax.plot([0, lim], [0, lim], color="grey", linestyle="--", linewidth=1)
    ax.set_xlim(0, lim)
    ax.set_ylim(0, lim)
    ax.set_xlabel("predicted probability")
    ax.set_ylabel("observed frequency")
    ax.set_title(title + (f"\n{subtitle}" if subtitle else ""), fontsize=10)
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
