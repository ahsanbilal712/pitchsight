"""Policy dataset: GRF tracking games and Kickoff matches -> tokens, context, labels.

    python -m policy.data --grf data/grf --kickoff data/matches/corpus --out data/grf/dataset --split-seed 4242

Every sample is the state the player in control saw, flipped so the team in possession attacks +x.
Tokens [23, F=16]: possession team's 11 players (slot order), the opponents' 11, the ball. Per token:
  x/105, y/68, vx/10, vy/10, team (+1 in possession, -1 defending, 0 ball), is_holder, role one-hot (8 GRF roles),
  distance to ball / 50, angle to the attacked goal / pi.
The design lists stamina as well, which makes 17 entries for "F = 16"; stamina is left out (GRF has none and the
scripted rule never reads it), keeping F = 16.
Context [G=4]: score difference for the team in possession / 3, clock fraction, period - 1, team in possession is home.
Labels: kind (pass, carry, shoot, clear, hold), pass target (slot 0-10 of the team in possession, -1 otherwise),
carry direction (8 bins, -1 otherwise). Kickoff labels come from events; GRF labels from the rules of 1.6 step 3.
Split: GRF by GAME_ID and Kickoff by match seed, 80/10/10 with default_rng(split_seed).
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from multiprocessing import Pool
from pathlib import Path

import numpy as np

F, G = 16, 4
KINDS = ("pass", "carry", "shoot", "clear", "hold")
PASS, CARRY, SHOOT, CLEAR, HOLD = range(5)
ROLES = ("goalkeeper", "centre back", "left back", "right back", "central midfield", "left midfield",
         "right midfield", "central front")
# Kickoff 4-3-3 slot -> GRF role (GK, RB, RCB, LCB, LB, RCM, CM, LCM, RW, CF, LW)
KICKOFF_ROLE = np.array([0, 3, 1, 1, 2, 4, 4, 4, 6, 7, 5])
PITCH_L, PITCH_W, GOAL_Y = 105.0, 68.0, 34.0
GRF_HZ = 10.2                      # derived from ball gravity (docs/DATA.md)
GRF_X, GRF_Y = 52.5, 68.0 / 0.84   # metres per normalised unit (anisotropic)
KICKOFF_DECISION_EVENTS = {"pass": PASS, "shot": SHOOT, "clearance": CLEAR}
TRAIN_SEEDS = range(1001, 3001)


# ---------------------------------------------------------------------------------------------------- tokens
def carry_bin(dx: np.ndarray, dy: np.ndarray) -> np.ndarray:
    """8 direction bins in the attacking frame: 0 = straight at goal (+x), counter-clockwise in 45 degree steps."""
    return (np.round(np.arctan2(dy, dx) / (np.pi / 4)).astype(np.int64)) % 8


def tokens_from_arrays(pos: np.ndarray, vel: np.ndarray, roles: np.ndarray, holder: np.ndarray, poss: np.ndarray,
                       attack_sign: np.ndarray) -> np.ndarray:
    """Tokens [N, 23, F] from absolute positions/velocities [N, 23, 2] (rows 0-10 home or team 0, 11-21 the other
    team, 22 ball), roles [N, 22], holder row [N], team in possession [N] and attack_sign [N] (+1 when the team in
    possession attacks +x in absolute coordinates)."""
    N = pos.shape[0]
    s = attack_sign.astype(np.float64)[:, None]
    x = np.where(s > 0, pos[..., 0], PITCH_L - pos[..., 0])
    y = np.where(s > 0, pos[..., 1], PITCH_W - pos[..., 1])
    vx, vy = vel[..., 0] * s, vel[..., 1] * s
    # possession team first, then opponents, then the ball
    own = np.where(poss[:, None] == 0, np.arange(11)[None, :], np.arange(11, 22)[None, :])
    opp = np.where(poss[:, None] == 0, np.arange(11, 22)[None, :], np.arange(11)[None, :])
    order = np.concatenate([own, opp, np.full((N, 1), 22)], axis=1)                     # [N, 23]
    n = np.arange(N)[:, None]
    X, Y, VX, VY = x[n, order], y[n, order], vx[n, order], vy[n, order]
    out = np.zeros((N, 23, F), dtype=np.float32)
    out[..., 0], out[..., 1], out[..., 2], out[..., 3] = X / PITCH_L, Y / PITCH_W, VX / 10.0, VY / 10.0
    out[:, :11, 4], out[:, 11:22, 4] = 1.0, -1.0
    out[..., 5] = (order == holder[:, None]).astype(np.float32)
    r = np.concatenate([roles[n, order[:, :22]], np.full((N, 1), -1)], axis=1)
    for k in range(8):
        out[..., 6 + k] = (r == k)
    bx, by = X[:, 22:23], Y[:, 22:23]
    out[..., 14] = np.hypot(X - bx, Y - by) / 50.0
    out[..., 15] = np.arctan2(GOAL_Y - Y, PITCH_L - X) / np.pi
    return out


def context(score_diff: np.ndarray, t_frac: np.ndarray, period: np.ndarray, poss_home: np.ndarray) -> np.ndarray:
    return np.stack([np.clip(score_diff / 3.0, -2, 2), t_frac, period - 1.0, poss_home], axis=1).astype(np.float32)


def slot_of(holder_row: np.ndarray, poss: np.ndarray) -> np.ndarray:
    return holder_row - 11 * poss


# ---------------------------------------------------------------------------------------------------- Kickoff
@dataclass
class Samples:
    tokens: list = field(default_factory=list)
    ctx: list = field(default_factory=list)
    kind: list = field(default_factory=list)
    target: list = field(default_factory=list)
    carry: list = field(default_factory=list)
    group: list = field(default_factory=list)       # match seed or GRF game id + 1,000,000

    def arrays(self) -> dict[str, np.ndarray]:
        if not self.kind:
            return {"tokens": np.zeros((0, 23, F), np.float16), "ctx": np.zeros((0, G), np.float16),
                    "kind": np.zeros(0, np.int8), "pass_target": np.zeros(0, np.int8),
                    "carry_dir": np.zeros(0, np.int8), "group": np.zeros(0, np.int32)}
        return {"tokens": np.concatenate(self.tokens).astype(np.float16), "ctx": np.concatenate(self.ctx).astype(np.float16),
                "kind": np.concatenate(self.kind).astype(np.int8), "pass_target": np.concatenate(self.target).astype(np.int8),
                "carry_dir": np.concatenate(self.carry).astype(np.int8), "group": np.concatenate(self.group).astype(np.int32)}


def kickoff_match(match_dir: Path, hold_every_s: int = 3) -> dict[str, np.ndarray]:
    """Samples from one training match: every pass/shot/clearance decision tick, plus carry/hold labels at frames
    every `hold_every_s` seconds where the player in control keeps the ball for the next second."""
    with gzip.open(match_dir / "events.jsonl.gz", "rt", encoding="utf-8") as fh:
        events = [json.loads(line) for line in fh]
    with np.load(match_dir / "samples.npz", allow_pickle=False) as z:
        s = {k: z[k] for k in z.files}
    t = s["t_ms"].astype(np.int64)
    index = {int(v): i for i, v in enumerate(t)}
    S = s["S"].astype(np.float64)
    roles = np.tile(np.r_[KICKOFF_ROLE, KICKOFF_ROLE], (len(t), 1))
    rows, kinds, targets, carries = [], [], [], []
    ids = None
    for e in events:
        if e["type"] == "match_metadata":
            lineup = e["attrs"]["lineups"]
            ids = list(lineup["home"]["starting"]) + list(lineup["away"]["starting"])
    row_of = {pid: r for r, pid in enumerate(ids)}
    for e in events:                                  # substitutions keep the row of the player who left
        if e["type"] == "substitution":
            row_of[e["attrs"]["player_on"]] = row_of.get(e["attrs"]["player_off"], -1)
        kind = KICKOFF_DECISION_EVENTS.get(e["type"])
        if kind is None:
            continue
        i = index.get(e["t_ms"] - 100)
        if i is None or s["holder"][i] < 0:
            continue
        target = -1
        if kind == PASS:
            r = row_of.get(e["attrs"].get("recipient"), -1)
            poss = int(s["holder"][i] >= 11)
            if r < 0 or (r >= 11) != bool(poss):
                continue
            target = r - 11 * poss
            if r == int(s["holder"][i]):          # the passer won his own pass back: not a pass to a team-mate
                continue
        rows.append(i)
        kinds.append(kind)
        targets.append(target)
        carries.append(-1)
    release_t = np.array(sorted(e["t_ms"] - 100 for e in events if e["type"] in KICKOFF_DECISION_EVENTS))
    for i in np.flatnonzero((t % (hold_every_s * 1000) == 0) & (s["holder"] >= 0)):
        j = index.get(int(t[i]) + 1000)
        if j is None or s["holder"][j] != s["holder"][i]:
            continue
        k = np.searchsorted(release_t, t[i])
        if k < len(release_t) and release_t[k] <= t[i] + 1000:
            continue                                   # released within the second: not a carry or hold sample
        h = int(s["holder"][i])
        sign = _attack_sign(int(h >= 11), int(s["period"][i]))
        dx, dy = (S[j, h, 0] - S[i, h, 0]) * sign, (S[j, h, 1] - S[i, h, 1]) * sign
        rows.append(int(i))
        if math.hypot(dx, dy) > 2.0:
            kinds.append(CARRY)
            carries.append(int(carry_bin(np.array(dx), np.array(dy))))
        else:
            kinds.append(HOLD)
            carries.append(-1)
        targets.append(-1)
    if not rows:
        return Samples().arrays()
    rows = np.array(rows)
    holder = s["holder"][rows].astype(np.int64)
    poss = (holder >= 11).astype(np.int64)
    period = s["period"][rows].astype(np.int64)
    sign = np.array([_attack_sign(p, q) for p, q in zip(poss, period, strict=True)])
    tok = tokens_from_arrays(S[rows, :, 0:2], S[rows, :, 2:4], roles[rows], holder, poss, sign)
    score = s["score"][rows].astype(np.float64)
    diff = np.where(poss == 0, score[:, 0] - score[:, 1], score[:, 1] - score[:, 0])
    ctx = context(diff, t[rows] / 5_400_000.0, period.astype(np.float64), (poss == 0).astype(np.float64))
    seed = int(match_dir.name)
    smp = Samples([tok], [ctx], [np.array(kinds)], [np.array(targets)], [np.array(carries)],
                  [np.full(len(rows), seed)])
    return smp.arrays()


def _attack_sign(team: int, period: int) -> int:
    d = 1 if period == 1 else -1
    return d if team == 0 else -d


# ---------------------------------------------------------------------------------------------------- GRF
def grf_games(csv_path: Path) -> dict[int, dict[str, np.ndarray]]:
    """Per GAME_ID arrays from one CSV (3 games): pos/vel [T, 23, 2] in metres and m/s, team [23], roles [22],
    holder row [T] (-1 none), score [T, 2]. Rows: team 0 players by PLAYER_ID, team 1, ball last."""
    raw: dict[int, dict[int, list]] = {}
    with open(csv_path, newline="") as fh:
        for r in csv.DictReader(fh):
            g, step = int(r["GAME_ID"]), int(r["TIMESTEP"])
            raw.setdefault(g, {}).setdefault(step, []).append(r)
    games = {}
    for g, steps in raw.items():
        T = max(steps) + 1
        pos = np.zeros((T, 23, 2))
        vel = np.zeros((T, 23, 2))
        holder = np.full(T, -1, dtype=np.int64)
        score = np.zeros((T, 2))
        roles = np.zeros(22, dtype=np.int64)
        for step, rows in steps.items():
            players = sorted((r for r in rows if r["PLAYER_ID"] != "-1"), key=lambda r: (int(r["TEAM_ID"]), int(r["PLAYER_ID"])))
            ball = next(r for r in rows if r["PLAYER_ID"] == "-1")
            for k, r in enumerate(players[:22] + [ball]):
                pos[step, k] = ((float(r["LOCATION_X"]) + 1.0) * GRF_X, (float(r["LOCATION_Y"]) + 0.42) * GRF_Y)
                vel[step, k] = (float(r["VELOCITY_X"]) * GRF_X * GRF_HZ, float(r["VELOCITY_Y"]) * GRF_Y * GRF_HZ)
                if k < 22:
                    if step == 0:
                        roles[k] = ROLES.index(r["PLAYER_ROLE"])
                    if r["ON_BALL"] == "True":
                        holder[step] = k
            score[step] = (float(ball["TEAM_0_SCORE"]), float(ball["TEAM_1_SCORE"]))
        games[g] = {"pos": pos, "vel": vel, "holder": holder, "score": score, "roles": roles}
    return games


def grf_labels(game: dict[str, np.ndarray], hold_every: int = 3) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(frame, kind, pass target slot, carry bin) per labelled frame of one GRF game.
    A release frame is the last frame a player is in control before a different player is; the label is pass when
    the next holder is a team-mate, shoot when the ball leaves faster than 15 m/s toward the attacked goal within
    1 s, clear when it travels more than 25 m away from the own goal with an opponent within 3 m of the kicker;
    other releases are unlabelled. Frames every `hold_every` steps where the holder keeps the ball for 1 s are carry
    (moved > 2 m) or hold."""
    pos, holder = game["pos"], game["holder"]
    T = len(holder)
    step1 = int(round(GRF_HZ))
    frames, kinds, targets, carries = [], [], [], []
    held = np.flatnonzero(holder >= 0)
    for a, b in zip(held[:-1], held[1:], strict=True):
        if holder[b] == holder[a]:
            continue
        h, nxt = int(holder[a]), int(holder[b])
        team = int(h >= 11)
        sign = 1.0 if team == 0 else -1.0             # GRF teams keep their ends all game: team 0 attacks +x
        if (nxt >= 11) == bool(team):
            frames.append(a)
            kinds.append(PASS)
            targets.append(nxt - 11 * team)
            carries.append(-1)
            continue
        w = slice(a + 1, min(a + 1 + step1, T))
        bv = game["vel"][w, 22, 0] * sign
        travel = (pos[min(b, T - 1), 22, 0] - pos[a, 22, 0]) * sign
        opp = np.arange(11, 22) if team == 0 else np.arange(11)
        pressed = np.min(np.hypot(*(pos[a, opp] - pos[a, h]).T)) < 3.0
        own_u = pos[a, 22, 0] if team == 0 else PITCH_L - pos[a, 22, 0]
        if bv.size and bv.max() > 15.0 and own_u > 60.0:
            kind = SHOOT
        elif travel > 25.0 and pressed:
            kind = CLEAR
        else:
            continue
        frames.append(a)
        kinds.append(kind)
        targets.append(-1)
        carries.append(-1)
    for a in range(0, T - step1, hold_every):
        h = int(holder[a])
        if h < 0 or np.any(holder[a:a + step1 + 1] != h):
            continue
        sign = 1.0 if h < 11 else -1.0
        dx, dy = (pos[a + step1, h] - pos[a, h]) * sign
        frames.append(a)
        if math.hypot(dx, dy) > 2.0:
            kinds.append(CARRY)
            carries.append(int(carry_bin(np.array(dx), np.array(dy))))
        else:
            kinds.append(HOLD)
            carries.append(-1)
        targets.append(-1)
    order = np.argsort(frames, kind="stable")
    return (np.array(frames)[order], np.array(kinds)[order], np.array(targets)[order], np.array(carries)[order])


def grf_file(csv_path: Path) -> dict[str, np.ndarray]:
    smp = Samples()
    for g, game in sorted(grf_games(csv_path).items()):
        fr, kinds, targets, carries = grf_labels(game)
        if fr.size == 0:
            continue
        holder = game["holder"][fr]
        poss = (holder >= 11).astype(np.int64)
        sign = np.where(poss == 0, 1, -1)
        roles = np.tile(game["roles"], (fr.size, 1))
        tok = tokens_from_arrays(game["pos"][fr], game["vel"][fr], roles, holder, poss, sign)
        sc = game["score"][fr]
        diff = np.where(poss == 0, sc[:, 0] - sc[:, 1], sc[:, 1] - sc[:, 0])
        T = len(game["holder"])
        ctx = context(diff, fr / max(T - 1, 1), np.where(fr < T // 2, 1.0, 2.0), (poss == 0).astype(np.float64))
        for lst, val in ((smp.tokens, tok), (smp.ctx, ctx), (smp.kind, kinds), (smp.target, targets),
                         (smp.carry, carries), (smp.group, np.full(fr.size, 1_000_000 + g))):
            lst.append(val)
    return smp.arrays()


# ---------------------------------------------------------------------------------------------------- build
@dataclass
class DatasetReport:
    counts: dict
    games_per_split: dict
    samples_per_split: dict
    sources: dict
    F: int = F
    G: int = G


def _job(args: tuple[str, str]) -> dict[str, np.ndarray]:
    kind, path = args
    return grf_file(Path(path)) if kind == "grf" else kickoff_match(Path(path))


def split_groups(groups: list[int], split_seed: int) -> dict[str, set[int]]:
    order = np.random.default_rng(split_seed).permutation(sorted(groups))
    n = len(order)
    a, b = int(round(0.8 * n)), int(round(0.9 * n))
    return {"train": set(map(int, order[:a])), "val": set(map(int, order[a:b])), "test": set(map(int, order[b:]))}


def build_dataset(grf_dir: Path, kickoff_dir: Path, out: Path, split_seed: int, workers: int | None = None,
                  kickoff_limit: int | None = None) -> DatasetReport:
    grf_dir, kickoff_dir, out = Path(grf_dir), Path(kickoff_dir), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    grf_csv = sorted({p.name: p for p in grf_dir.rglob("gfootball_results_games_*.csv")}.values())
    seeds = [s for s in TRAIN_SEEDS if (kickoff_dir / str(s) / "samples.npz").exists()][:kickoff_limit]
    jobs = [("grf", str(p)) for p in grf_csv] + [("kickoff", str(kickoff_dir / str(s))) for s in seeds]
    print(f"building from {len(grf_csv)} GRF files and {len(seeds)} Kickoff matches", flush=True)
    with Pool(workers or max(1, (os.cpu_count() or 2) - 2)) as pool:
        parts = pool.map(_job, jobs, chunksize=4)
    data = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    del parts
    is_grf = data["group"] >= 1_000_000
    split = {}
    for name, mask in (("grf", is_grf), ("kickoff", ~is_grf)):
        split[name] = split_groups(sorted(set(data["group"][mask].tolist())), split_seed)
    counts, games, samples = {}, {}, {}
    for part in ("train", "val", "test"):
        keep = np.isin(data["group"], list(split["grf"][part] | split["kickoff"][part]))
        arrays = {k: v[keep] for k, v in data.items()}
        np.savez(out / f"{part}.npz", **arrays)
        samples[part] = int(keep.sum())
        games[part] = {"grf": len(split["grf"][part]), "kickoff": len(split["kickoff"][part])}
        counts[part] = {k: int(c) for k, c in sorted(Counter(KINDS[int(i)] for i in arrays["kind"]).items())}
    report = DatasetReport(counts=counts, games_per_split=games, samples_per_split=samples,
                           sources={"grf_files": len(grf_csv), "grf_games": len(set(data["group"][is_grf].tolist())),
                                    "kickoff_matches": len(seeds), "grf_samples": int(is_grf.sum()),
                                    "kickoff_samples": int((~is_grf).sum())})
    art = Path(__file__).resolve().parent / "artifacts"
    art.mkdir(exist_ok=True)
    (art / "dataset_report.json").write_text(json.dumps({**report.__dict__, "split_seed": split_seed,
                                                         "token_features": TOKEN_FEATURES, "context": CONTEXT},
                                                        indent=1, sort_keys=True) + "\n", encoding="utf-8")
    sanity_plot(data, art / "coord_sanity.png")
    return report


TOKEN_FEATURES = ["x/105", "y/68", "vx/10", "vy/10", "team", "is_holder"] + [f"role:{r}" for r in ROLES] + \
    ["dist_ball/50", "angle_goal/pi"]
CONTEXT = ["score_diff/3", "clock_fraction", "period-1", "possession_is_home"]


def sanity_plot(data: dict[str, np.ndarray], path: Path, n: int = 4000) -> None:
    """Ball position per kind and the holder's position, GRF vs Kickoff, in the attacking frame."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rng = np.random.default_rng(0)
    fig, axes = plt.subplots(2, 3, figsize=(12, 6.5), dpi=100)
    for r, (name, mask) in enumerate((("GRF", data["group"] >= 1_000_000), ("Kickoff", data["group"] < 1_000_000))):
        idx = np.flatnonzero(mask)
        idx = rng.choice(idx, min(n, idx.size), replace=False) if idx.size else idx
        tok = data["tokens"][idx].astype(np.float32)
        kind = data["kind"][idx]
        for c, kinds in enumerate(((PASS,), (SHOOT, CLEAR), (CARRY, HOLD))):
            ax = axes[r, c]
            m = np.isin(kind, kinds)
            hold = tok[m][:, :, 5].argmax(axis=1)
            ax.scatter(tok[m, hold, 0] * PITCH_L if m.any() else [], tok[m, hold, 1] * PITCH_W if m.any() else [],
                       s=2, alpha=0.4)
            ax.set_xlim(0, PITCH_L)
            ax.set_ylim(0, PITCH_W)
            ax.axvline(PITCH_L / 2, color="grey", linewidth=0.5)
            ax.set_title(f"{name}: holder at {'/'.join(KINDS[k] for k in kinds)} ({int(m.sum())})", fontsize=9)
    fig.suptitle("Policy samples in the attacking frame (team in possession attacks +x)", fontsize=10)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m policy.data")
    ap.add_argument("--grf", type=Path, default=Path("data/grf"))
    ap.add_argument("--kickoff", type=Path, default=Path("data/matches/corpus"))
    ap.add_argument("--out", type=Path, default=Path("data/grf/dataset"))
    ap.add_argument("--split-seed", type=int, default=4242)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--kickoff-limit", type=int, default=None)
    args = ap.parse_args(argv)
    rep = build_dataset(args.grf, args.kickoff, args.out, args.split_seed, args.workers, args.kickoff_limit)
    print(json.dumps(rep.__dict__, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
