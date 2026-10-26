"""MomentEncoder: a 64-d embedding of a match moment, its phase cluster and nearest neighbours.

    python -m heads.moment_encoder train [--matches 400] [--epochs 6]      # train, cluster, name, index
    MomentEncoder().encode(pc, features) -> np.ndarray[64];  .phase(z) -> str

Input: the pitch-control grid [34, 53] average-pooled to 14 x 21 (home share, flipped to the team in possession) plus
the 12 chaos features (heads.features.CHAOS_FEATURES), standardised, the features scaled up by sqrt(294 / 12) so both
blocks carry the same total variance. An autoencoder (306 -> 256 -> 128 -> 64 ->
128 -> 256 -> 306) is trained on states every 4 s of training matches; k-means (k = 6, seed 4242) on the codes
gives the phase clusters. Purity is measured against the hidden match regime of truth.json (phases with side "M")
on held-out matches: evaluation only, never an input. One cluster_namer call (models.yaml, through SpendGuard)
names the six clusters from their centroids described in numbers. The golden-season index (evaluation seeds 1-50
and the golden match, every 10 s) backs the MCP tool similar_moments.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

from .features import CHAOS_FEATURES, load_match
from .models import ARTIFACTS, HeadArtifactMissing

GRID = (14, 21)
D_IN = GRID[0] * GRID[1] + len(CHAOS_FEATURES)
D_Z = 64
K = 6
FEATURE_WEIGHT = float(np.sqrt(GRID[0] * GRID[1] / 12))
# a phase of play is a 60 s pattern: the windowed features count more than the instantaneous ones
PHASE_FEATURES = ("turnovers_60s", "transition_share", "tempo", "since_turnover_s")
PHASE_WEIGHT = 4.0
ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "data" / "matches" / "corpus"


def pool_grid(pc: np.ndarray, poss_team: int) -> np.ndarray:
    """[34, 53] home share -> [14, 21] share of the team in possession (block average)."""
    import torch
    share = pc if poss_team == 0 else 1.0 - pc
    t = torch.from_numpy(np.ascontiguousarray(share, dtype=np.float32))[None, None]
    return torch.nn.functional.adaptive_avg_pool2d(t, GRID)[0, 0].numpy()


def _net():
    import torch
    from torch import nn

    class AE(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.enc = nn.Sequential(nn.Linear(D_IN, 256), nn.GELU(), nn.Linear(256, 128), nn.GELU(), nn.Linear(128, D_Z))
            self.dec = nn.Sequential(nn.Linear(D_Z, 128), nn.GELU(), nn.Linear(128, 256), nn.GELU(), nn.Linear(256, D_IN))

        def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
            z = self.enc(x)
            return z, self.dec(z)
    return AE()


class MomentEncoder:
    def __init__(self, artifacts: Path | None = None, device: str = "cpu") -> None:
        import torch
        art = Path(artifacts or ARTIFACTS)
        for name in ("moment_encoder.pt", "clusters.json"):
            if not (art / name).exists():
                raise HeadArtifactMissing(f"{art / name} is missing; train it with python -m heads.moment_encoder train")
        ck = torch.load(art / "moment_encoder.pt", map_location="cpu", weights_only=False)
        self.net = _net()
        self.net.load_state_dict(ck["model"])
        self.net.eval()
        self.mean, self.scale = np.asarray(ck["mean"]), np.asarray(ck["scale"])
        c = json.loads((art / "clusters.json").read_text(encoding="utf-8"))
        self.centroids = np.asarray(c["centroids"])
        self.z_mean, self.z_scale = np.asarray(c["z_mean"]), np.asarray(c["z_scale"])
        self.names = c["names"]

    def inputs(self, pooled: np.ndarray, features: np.ndarray) -> np.ndarray:
        x = np.concatenate([np.asarray(pooled, dtype=np.float64).reshape(len(features), -1), features], axis=1)
        return ((x - self.mean) / self.scale).astype(np.float32)

    def encode(self, pc: np.ndarray, features, poss_team: int = 0) -> np.ndarray:
        """64-d code for one moment: pc [34, 53] home share, features the 12 chaos features (dict or array)."""
        f = np.array([[features[k] for k in CHAOS_FEATURES]]) if isinstance(features, dict) else np.atleast_2d(features)
        return self.encode_batch(pool_grid(pc, poss_team)[None], f)[0]

    def encode_batch(self, pooled: np.ndarray, features: np.ndarray) -> np.ndarray:
        import torch
        with torch.no_grad():
            z, _ = self.net(torch.from_numpy(self.inputs(pooled, np.asarray(features, dtype=np.float64))))
        return z.numpy().astype(np.float64)

    def cluster(self, z: np.ndarray) -> np.ndarray:
        zz = (np.atleast_2d(z) - self.z_mean) / self.z_scale
        return np.argmin(((zz[:, None, :] - self.centroids[None]) ** 2).sum(-1), axis=1)

    def phase(self, z: np.ndarray) -> str:
        return self.names[int(self.cluster(z)[0])]


# ---------------------------------------------------------------------------------------------------- data
def match_states(args: tuple[str, int]) -> dict[str, np.ndarray]:
    """Pooled grids, chaos features and the hidden regime label for states every `step_s` of one match."""
    from physics.pitch_control import pitch_control

    from .features import _carry_possession, state_rows

    match_dir, step_s = args
    m = load_match(Path(match_dir))
    _, chaos, _ = state_rows(m, step_s=step_s, winprob_every_s=10**9)
    s = m.samples
    index = {int(t): i for i, t in enumerate(s["t_ms"])}
    team = _carry_possession(s["possession"])
    regimes = [p for p in m.truth["phases"] if p.get("side") == "M"]
    pooled, feats, labels, t_out = [], [], [], []
    for row in chaos:
        i = index[row["t_ms"]]
        pc = pitch_control(s["S"][i].astype(np.float64))
        pooled.append(pool_grid(pc, int(max(team[i], 0))))
        feats.append([row[k] for k in CHAOS_FEATURES])
        labels.append(next((p["label"] for p in regimes if p["start_ms"] <= row["t_ms"] < p["end_ms"]), ""))
        t_out.append(row["t_ms"])
    return {"pooled": np.array(pooled, dtype=np.float32), "features": np.array(feats), "label": np.array(labels),
            "t_ms": np.array(t_out), "seed": np.full(len(t_out), m.seed)}


def _collect(dirs: list[Path], step_s: int, workers: int) -> dict[str, np.ndarray]:
    with Pool(workers) as pool:
        parts = pool.map(match_states, [(str(d), step_s) for d in dirs], chunksize=2)
    return {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}


def purity(clusters: np.ndarray, labels: np.ndarray) -> float:
    total = 0
    for c in np.unique(clusters):
        _, counts = np.unique(labels[clusters == c], return_counts=True)
        total += counts.max()
    return float(total / len(labels))


def describe_centroids(raw: np.ndarray, clusters: np.ndarray) -> list[dict]:
    """Per cluster: size and the mean of the chaos features and of the possession team's grid by thirds."""
    out = []
    for c in range(K):
        m = clusters == c
        x = raw[m]
        grid = x[:, :GRID[0] * GRID[1]].reshape(-1, *GRID)
        thirds = np.array_split(np.arange(GRID[1]), 3)
        d = {"cluster": c, "share": round(float(m.mean()), 3),
             "control_own_third": round(float(grid[:, :, thirds[0]].mean()), 3),
             "control_middle_third": round(float(grid[:, :, thirds[1]].mean()), 3),
             "control_attacking_third": round(float(grid[:, :, thirds[2]].mean()), 3)}
        for j, k in enumerate(CHAOS_FEATURES):
            d[k] = round(float(x[:, GRID[0] * GRID[1] + j].mean()), 3)
        out.append(d)
    return out


def name_clusters(described: list[dict], use_model: bool = True) -> tuple[list[str], dict]:
    """One cluster_namer call (Gemini, through SpendGuard) naming the six clusters; returns names and the record."""
    fallback = [f"phase_{c['cluster']}" for c in described]
    if not use_model:
        return fallback, {"model": None, "reason": "model call skipped"}
    from newsroom.llm import LiveClient
    schema = {"type": "object", "properties": {"names": {"type": "array", "items": {"type": "string"},
                                                         "minItems": K, "maxItems": K}}, "required": ["names"]}
    prompt = ("These are six clusters of football match moments from a tracking-data model. For each cluster you get "
              "its share of moments, the attacking team's pitch control by third (0-1), and chaos features "
              "(turnovers_60s = open-play turnovers per minute, transition_share, holder_pressure_m = nearest "
              "defender to the ball carrier in metres, tempo = passes per minute, ball_u = ball distance from the "
              "attacking team's own goal line in metres). Give each cluster a short broadcast-style name of 2-4 words "
              "(for example 'patient build-up', 'end-to-end chaos'), distinct, plain English, no club or player names. "
              "Reply as JSON {\"names\": [six names in cluster order]}.\n\n" + json.dumps(described, indent=1))
    res = asyncio.run(LiveClient(mode="batch").complete("cluster_namer", [{"role": "user", "content": prompt}],
                                                         schema=schema, match_id=None))
    names = (res.get("json") or {}).get("names") or []
    if len(names) != K or len(set(names)) != K:
        raise RuntimeError(f"cluster_namer returned {names!r}")
    return [str(n) for n in names], {"model": res["model"], "cost_usd": res["cost_usd"],
                                     "tokens_in": res["tokens_in"], "tokens_out": res["tokens_out"]}


def train(n_matches: int = 400, epochs: int = 6, step_s: int = 4, workers: int = 6, device: str | None = None,
          seed: int = 4242, use_model: bool = True, out: Path = ARTIFACTS, data: dict | None = None,
          feature_weight: float | None = None) -> dict:
    import time

    import torch
    from sklearn.cluster import KMeans

    from policy.config import default_device

    device = device or default_device()
    rng = np.random.default_rng(seed)
    seeds = sorted(int(p.name) for p in CORPUS.iterdir() if p.name.isdigit() and 1001 <= int(p.name) <= 3000
                   and (p / "samples.npz").exists())
    if data is not None:                         # preloaded states (tuning runs)
        chosen = sorted(set(data["seed"].tolist()))
    else:
        chosen = sorted(rng.choice(seeds, min(n_matches, len(seeds)), replace=False).tolist())
    n_test = max(1, len(chosen) // 10)
    test_seeds, train_seeds = chosen[:n_test], chosen[n_test:]
    started = time.perf_counter()
    if data is None:
        data = _collect([CORPUS / str(s) for s in chosen], step_s, workers)
    is_test = np.isin(data["seed"], test_seeds)
    raw = np.concatenate([data["pooled"].reshape(len(data["seed"]), -1), data["features"]], axis=1)
    mean, scale = raw[~is_test].mean(0), raw[~is_test].std(0) + 1e-6
    # give the 12 features the same total weight as the 294 grid cells, or the codes only describe the grid
    weights = np.array([PHASE_WEIGHT if k in PHASE_FEATURES else 1.0 for k in CHAOS_FEATURES])
    scale[GRID[0] * GRID[1]:] /= (FEATURE_WEIGHT if feature_weight is None else feature_weight) * weights
    X = torch.from_numpy(((raw - mean) / scale).astype(np.float32))
    torch.manual_seed(seed)
    net = _net().to(device)
    opt = torch.optim.Adam(net.parameters(), lr=1e-3)
    train_idx = np.flatnonzero(~is_test)
    log = []
    for epoch in range(epochs):
        perm = rng.permutation(train_idx)
        tot = 0.0
        for a in range(0, len(perm), 1024):
            xb = X[perm[a:a + 1024]].to(device)
            _, rec = net(xb)
            loss = torch.nn.functional.mse_loss(rec, xb)
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot += float(loss.detach()) * len(xb)
        net.eval()
        with torch.no_grad():
            test_loss = float(torch.nn.functional.mse_loss(net(X[is_test].to(device))[1], X[is_test].to(device)))
        net.train()
        log.append({"epoch": epoch + 1, "train_mse": tot / len(perm), "test_mse": test_loss})
        print(log[-1], flush=True)
    net = net.cpu().eval()
    with torch.no_grad():
        Z = net(X)[0].numpy().astype(np.float64)
    z_mean, z_scale = Z[~is_test].mean(0), Z[~is_test].std(0) + 1e-6
    km = KMeans(n_clusters=K, random_state=seed, n_init=10).fit((Z[~is_test] - z_mean) / z_scale)
    clusters = km.predict((Z - z_mean) / z_scale)
    labels = data["label"]
    p_test, p_train = purity(clusters[is_test], labels[is_test]), purity(clusters[~is_test], labels[~is_test])
    majority = float(max(np.mean(labels[is_test] == lab) for lab in np.unique(labels[is_test])))
    described = describe_centroids(raw[~is_test], clusters[~is_test])
    names, naming = name_clusters(described, False)        # placeholders; `name` asks cluster_namer afterwards
    out.mkdir(parents=True, exist_ok=True)
    torch.save({"model": net.state_dict(), "mean": mean, "scale": scale, "grid": GRID, "features": CHAOS_FEATURES},
               out / "moment_encoder.pt")
    (out / "clusters.json").write_text(json.dumps({"k": K, "seed": seed, "names": names, "centroids":
                                                   km.cluster_centers_.tolist(), "z_mean": z_mean.tolist(),
                                                   "z_scale": z_scale.tolist(), "described": described,
                                                   "naming": naming}, indent=1) + "\n", encoding="utf-8")
    metrics = {"purity_test": round(p_test, 4), "purity_train": round(p_train, 4), "purity_threshold": 0.6,
               "majority_label_rate_test": round(majority, 4), "labels": "truth.json phases side M (hidden regime)",
               "states_train": int((~is_test).sum()), "states_test": int(is_test.sum()), "matches_train":
               len(train_seeds), "matches_test": len(test_seeds), "test_seeds": test_seeds, "step_s": step_s,
               "epochs": epochs, "device": device, "train_log": log, "minutes": round((time.perf_counter() - started)
                                                                                         / 60, 1), "naming": naming}
    (out / "metrics_encoder.json").write_text(json.dumps(metrics, indent=1) + "\n", encoding="utf-8")
    if use_model:
        metrics["naming"] = name(out)
    return metrics


def name(out: Path = ARTIFACTS) -> dict:
    """The one cluster_namer call (Gemini through SpendGuard): replaces the placeholder names in clusters.json and
    records the call in clusters.json and metrics_encoder.json."""
    c = json.loads((out / "clusters.json").read_text(encoding="utf-8"))
    names, naming = name_clusters(c["described"], True)
    c["names"], c["naming"] = names, naming
    (out / "clusters.json").write_text(json.dumps(c, indent=1) + "\n", encoding="utf-8")
    m = json.loads((out / "metrics_encoder.json").read_text(encoding="utf-8"))
    m["naming"] = naming
    (out / "metrics_encoder.json").write_text(json.dumps(m, indent=1) + "\n", encoding="utf-8")
    return naming


def build_index(out: Path = ARTIFACTS, step_s: int = 10, workers: int = 6) -> dict:
    """Golden-season index: codes every 10 s for evaluation seeds 1-50 and the golden match (similar_moments)."""
    from .features import Match  # noqa: F401  (load_match handles events.jsonl or .gz)
    enc = MomentEncoder(out)
    dirs = [CORPUS / str(s) for s in range(1, 51)]
    data = _index_collect(dirs + [ROOT / "data" / "matches" / "4242"], step_s, workers)
    z = enc.encode_batch(data["pooled"], data["features"])
    np.savez_compressed(out / "moment_index.npz", z=z.astype(np.float32), seed=data["seed"], t_ms=data["t_ms"],
                        cluster=enc.cluster(z).astype(np.int8))
    return {"moments": int(len(z)), "matches": len(dirs) + 1}


def _index_collect(dirs: list[Path], step_s: int, workers: int) -> dict[str, np.ndarray]:
    with Pool(workers) as pool:
        parts = pool.map(_tracking_states, [(str(d), step_s) for d in dirs], chunksize=2)
    return {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}


def _tracking_states(args: tuple[str, int]) -> dict[str, np.ndarray]:
    """States every step_s of a full-tracking match folder (events.jsonl + tracking.npz)."""
    from physics.pitch_control import pitch_control
    from physics.window import TrackingWindow

    from .features import moment_features
    d, step_s = Path(args[0]), args[1]
    events = [json.loads(line) for line in (d / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    w = TrackingWindow.load(d)
    seed = int(events[0]["attrs"]["seed"])
    pooled, feats, ts = [], [], []
    for t in range(step_s * 1000, 5_400_000, step_s * 1000):
        f, team = moment_features(w, events, t)
        pooled.append(pool_grid(pitch_control(w.S[w.index_at(t)].astype(np.float64)), team))
        feats.append([f[k] for k in CHAOS_FEATURES])
        ts.append(t)
    return {"pooled": np.array(pooled, dtype=np.float32), "features": np.array(feats), "t_ms": np.array(ts),
            "seed": np.full(len(ts), seed)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m heads.moment_encoder")
    ap.add_argument("cmd", choices=("train", "index", "name"))
    ap.add_argument("--matches", type=int, default=400)
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--no-model", action="store_true", help="skip the cluster_namer call")
    args = ap.parse_args(argv)
    if args.cmd == "name":
        print(json.dumps(name(), indent=1))
        return 0
    if args.cmd == "train":
        print(json.dumps(train(args.matches, args.epochs, workers=args.workers, use_model=False), indent=1))
    print(json.dumps(build_index(workers=args.workers)))
    if args.cmd == "train" and not args.no_model:
        print(json.dumps(name(), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
