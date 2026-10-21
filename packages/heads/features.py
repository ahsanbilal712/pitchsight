"""Feature tables for the outcome heads (TECH_PLAN 1.6 "Outcome heads").

Inputs are Kickoff training matches (seeds 1001-3000): `events.jsonl.gz`, `samples.npz` (the state at every on-ball
decision and at 1 Hz) and `truth.json`. Coordinates are turned into the frame of the team that matters (the shooter,
the passer, the team in possession) so every head sees "own goal at u = 0, attacked goal at u = 105".

Tables (one row each):
  shots   at the decision tick of every shot           -> XGHead
  passes  at the decision tick of every pass           -> PassHead
  states  every `step_s` of match time (1 Hz frames)   -> GoalIn8sHead, ChaosHead; every 30 s -> WinProbHead

`state_features` builds the goal-in-8-s and win-probability features from raw arrays, batched over worlds, so the
rollout engine (T-016) values terminal states with exactly the features the heads were trained on.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from kickoff.physics_prior import (
    BOX_DEPTH,
    BOX_HALF,
    GOAL_Y,
    PITCH_L,
    goal_angle,
    goal_distance,
    threat,
    to_team,
)
from physics.indices import chaos_index, open_play_turnovers, transition_share_at, turnover_rate
from physics.pitch_control import control_at, grid, pitch_control

FEATURE_VERSION = "f1"
BODY = {"right_foot": 0, "left_foot": 1, "head": 2}
SHOT_FEATURES = ["distance_m", "angle_rad", "body_part", "defenders_in_cone", "keeper_line_m", "under_pressure",
                 "control_at_shot", "penalty"]
PASS_FEATURES = ["length_m", "angle_rad", "lofted", "under_pressure", "receiver_space", "progressive_m",
                 "opponents_in_lane", "start_u", "nearest_opp_m"]
GOAL8_FEATURES = ["ball_u", "ball_dv", "ball_z", "has_holder", "ball_speed", "ball_goal_dist", "ball_goal_angle",
                  "att_in_box", "def_in_box", "att_third_control", "nearest_def_m", "in_play", "minute"]
WINPROB_FEATURES = ["score_diff", "minute", "period", "red_card_diff", "xt_diff_15", "xg_diff_15", "chaos"]
CHAOS_FEATURES = ["contested_frac", "turnovers_60s", "transition_share", "closing_speed", "tempo", "holder_pressure_m",
                  "ball_u", "ball_speed", "has_holder", "since_turnover_s", "att_third_control", "minute"]
HORIZON_MS = 8000
CHAOS_HORIZON_MS = 10_000


def attack_dir(team: int, period: int) -> int:
    """+1 when team (0 home, 1 away) attacks +x in this period."""
    d = 1 if period == 1 else -1
    return d if team == 0 else -d


@dataclass
class Match:
    seed: int
    events: list[dict]
    samples: dict[str, np.ndarray]
    truth: dict

    @property
    def result(self) -> int:
        """0 home win, 1 draw, 2 away win."""
        goals = [e["team"] for e in self.events if e["type"] == "goal"]
        h, a = goals.count("home"), goals.count("away")
        return 0 if h > a else (1 if h == a else 2)


def load_match(match_dir: str | Path) -> Match:
    d = Path(match_dir)
    events_path = d / "events.jsonl.gz"
    if events_path.exists():
        with gzip.open(events_path, "rt", encoding="utf-8") as fh:
            events = [json.loads(line) for line in fh]
    else:
        events = [json.loads(line) for line in (d / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    with np.load(d / "samples.npz", allow_pickle=False) as z:
        samples = {k: z[k] for k in z.files}
    truth = json.loads((d / "truth.json").read_text(encoding="utf-8"))
    return Match(seed=int(d.name), events=events, samples=samples, truth=truth)


class _Frames:
    """Frame lookup by t_ms over a match's samples."""

    def __init__(self, samples: dict[str, np.ndarray]) -> None:
        self.s = samples
        self.index = {int(t): i for i, t in enumerate(samples["t_ms"])}

    def at(self, t_ms: int) -> int | None:
        return self.index.get(int(t_ms))

    def S(self, i: int) -> np.ndarray:
        return self.s["S"][i].astype(np.float64)


def _team_uv(S: np.ndarray, team: int, period: int) -> tuple[np.ndarray, np.ndarray]:
    return to_team(S[:, 0], S[:, 1], attack_dir(team, period))


def _rows(team: int) -> np.ndarray:
    return np.arange(11 * team, 11 * team + 11)


def shot_features(e: dict, S: np.ndarray) -> dict:
    """SHOT_FEATURES for one shot event given the frame the shooter saw (the tick before the shot)."""
    team, period = (0 if e["team"] == "home" else 1), e["period"]
    S = np.asarray(S, dtype=np.float64)
    U, _ = _team_uv(S, team, period)
    share = float(control_at(S, [e["location"]])[0])
    a = e["attrs"]
    return {"distance_m": a["distance_m"], "angle_rad": np.radians(a["angle_deg"]),
            "body_part": BODY.get(a.get("body_part"), 0), "defenders_in_cone": a["defenders_in_cone"],
            "keeper_line_m": float(PITCH_L - U[11 * (1 - team)]), "under_pressure": int(e["under_pressure"]),
            "control_at_shot": share if team == 0 else 1.0 - share, "penalty": int(bool(a.get("penalty")))}


def shot_rows(m: Match) -> list[dict]:
    fr = _Frames(m.samples)
    out = []
    for e in m.events:
        if e["type"] != "shot":
            continue
        i = fr.at(e["t_ms"] - 100)
        if i is None:
            continue
        out.append({"seed": m.seed, "t_ms": e["t_ms"], **shot_features(e, fr.S(i)),
                    "label": int(e["outcome"] == "goal")})
    return out


def pass_rows(m: Match) -> list[dict]:
    fr = _Frames(m.samples)
    out = []
    for e in m.events:
        if e["type"] != "pass":
            continue
        i = fr.at(e["t_ms"] - 100)
        if i is None:
            continue
        team, period = (0 if e["team"] == "home" else 1), e["period"]
        d = attack_dir(team, period)
        a = e["attrs"]
        x0, y0 = e["location"]
        ang = np.radians(a["angle_deg"])
        tx, ty = x0 + d * a["length_m"] * np.cos(ang), y0 + d * a["length_m"] * np.sin(ang)
        S = fr.S(i)
        share = float(control_at(S, [[tx, ty]])[0])
        opp = S[_rows(1 - team), 0:2]
        seg = np.array([tx - x0, ty - y0])
        L2 = max(float(seg @ seg), 1e-9)
        s = np.clip(((opp - [x0, y0]) @ seg) / L2, 0, 1)
        lane = np.hypot(*(opp - ([x0, y0] + s[:, None] * seg)).T)
        u0, _ = to_team(np.float64(x0), np.float64(y0), d)
        out.append({
            "seed": m.seed, "t_ms": e["t_ms"], "length_m": a["length_m"], "angle_rad": ang,
            "lofted": int(a["height"] == "lofted"), "under_pressure": int(e["under_pressure"]),
            "receiver_space": share if team == 0 else 1.0 - share, "progressive_m": a["progressive_m"],
            "opponents_in_lane": int(np.sum(lane < 2.0)), "start_u": float(u0),
            "nearest_opp_m": float(np.min(np.hypot(opp[:, 0] - x0, opp[:, 1] - y0))),
            "label": int(e["outcome"] == "complete"),
        })
    return out


def _carry_possession(possession: np.ndarray) -> np.ndarray:
    pos = np.asarray(possession).astype(np.int64)
    idx = np.where(pos >= 0, np.arange(len(pos)), -1)
    np.maximum.accumulate(idx, out=idx)
    return np.where(idx >= 0, pos[np.maximum(idx, 0)], -1)


def state_features(S: np.ndarray, ball_z: np.ndarray, holder: np.ndarray, team: np.ndarray, period: np.ndarray,
                   t_ms: np.ndarray, in_play: np.ndarray, pcs: np.ndarray | None = None) -> pd.DataFrame:
    """GOAL8_FEATURES for N states (batched over worlds or frames). `team` is the team in possession (0/1);
    `pcs` [N, 34, 53] home-share grids, computed here when not given."""
    S = np.asarray(S, dtype=np.float64)
    N = S.shape[0]
    gx, _ = grid()
    rows = []
    for k in range(N):
        tm, per = int(team[k]), int(period[k])
        d = attack_dir(tm, per)
        U, V = to_team(S[k, :23, 0], S[k, :23, 1], d)
        bu, bv = U[22], V[22]
        pc = pitch_control(S[k]) if pcs is None else pcs[k]
        share = pc if tm == 0 else 1.0 - pc
        ux, _ = to_team(gx, np.zeros_like(gx), d)
        att, dfn = _rows(tm), _rows(1 - tm)
        in_box = (U[:22] > PITCH_L - BOX_DEPTH) & (np.abs(V[:22] - GOAL_Y) < BOX_HALF)
        rows.append({
            "ball_u": bu, "ball_dv": abs(bv - GOAL_Y), "ball_z": float(ball_z[k]), "has_holder": int(holder[k] >= 0),
            "ball_speed": float(np.hypot(S[k, 22, 2], S[k, 22, 3])), "ball_goal_dist": float(goal_distance(bu, bv)),
            "ball_goal_angle": float(goal_angle(bu, bv)), "att_in_box": int(in_box[att].sum()),
            "def_in_box": int(in_box[dfn].sum()), "att_third_control": float(share[:, ux > 70.0].mean()),
            "nearest_def_m": float(np.min(np.hypot(U[dfn] - bu, V[dfn] - bv))), "in_play": int(in_play[k]),
            "minute": float(t_ms[k]) / 60000.0,
        })
    return pd.DataFrame(rows, columns=GOAL8_FEATURES)


def xt_xg_15(events: list[dict], t_ms: int) -> tuple[float, float]:
    """Home minus away over the last 15 minutes: expected threat added by completed passes, and shot xG."""
    xt, xgd = 0.0, 0.0
    for e in events:
        if not (t_ms - 900_000 < e["t_ms"] <= t_ms) or e["team"] not in ("home", "away"):
            continue
        sign = 1.0 if e["team"] == "home" else -1.0
        if e["type"] == "shot":
            xgd += sign * e["attrs"]["xg"]
        elif e["type"] == "pass" and e["outcome"] == "complete" and e["end_location"]:
            d = attack_dir(0 if e["team"] == "home" else 1, e["period"])
            u0, v0 = to_team(np.float64(e["location"][0]), np.float64(e["location"][1]), d)
            u1, v1 = to_team(np.float64(e["end_location"][0]), np.float64(e["end_location"][1]), d)
            xt += sign * float(threat(u1, v1) - threat(u0, v0))
    return xt, xgd


def state_rows(m: Match, step_s: int = 2, winprob_every_s: int = 30) -> tuple[list[dict], list[dict], list[dict]]:
    """(goal8s rows, chaos rows, winprob rows) from the 1 Hz frames of one match."""
    s = m.samples
    t = s["t_ms"].astype(np.int64)
    keep = np.flatnonzero((t % (step_s * 1000) == 0) & (t > 0))
    team_all = _carry_possession(s["possession"])
    goals = [(e["t_ms"], 0 if e["team"] == "home" else 1) for e in m.events if e["type"] == "goal"]
    turn_t = open_play_turnovers(m.events, 0, 10**9)
    passes_t = np.array([e["t_ms"] for e in m.events if e["type"] == "pass"], dtype=np.int64)
    handover = [(e["t_ms"], e["team"]) for e in m.events if e["type"] in ("possession_change", "set_piece")]
    keep = keep[team_all[keep] >= 0]
    pcs = np.stack([pitch_control(s["S"][i].astype(np.float64)) for i in keep]) if keep.size else np.zeros((0, 34, 53))
    g8 = state_features(s["S"][keep], s["ball_z"][keep], s["holder"][keep], team_all[keep], s["period"][keep], t[keep],
                        s["possession"][keep] >= 0, pcs=pcs)
    g8_rows, chaos_rows, wp_rows = [], [], []
    for j, i in enumerate(keep):
        ti, tm = int(t[i]), int(team_all[i])
        f = g8.iloc[j].to_dict()
        f.update(seed=m.seed, t_ms=ti, poss_team=tm,
                 label_att=int(any(ti < gt <= ti + HORIZON_MS and gteam == tm for gt, gteam in goals)),
                 label_def=int(any(ti < gt <= ti + HORIZON_MS and gteam != tm for gt, gteam in goals)))
        g8_rows.append(f)
        S = s["S"][i].astype(np.float64)
        pc = pcs[j]
        rate = turnover_rate(m.events, ti)
        trans = transition_share_at(m.events, ti)
        h = int(s["holder"][i])
        if h >= 0:
            opp = _rows(1 - (h >= 11))
            rel = S[h, 0:2] - S[opp, 0:2]
            dist = np.hypot(rel[:, 0], rel[:, 1])
            kk = int(np.argmin(dist))
            closing = float(max(0.0, np.dot(S[opp[kk], 2:4] - S[h, 2:4], rel[kk] / max(dist[kk], 1e-6))))
            press = float(dist[kk])
        else:
            closing, press = 0.0, 30.0
        last_turn = turn_t[turn_t <= ti]
        other = "away" if tm == 0 else "home"
        chaos_rows.append({
            "seed": m.seed, "t_ms": ti, "contested_frac": float(np.mean(np.abs(pc - 0.5) < 0.15)),
            "turnovers_60s": rate, "transition_share": trans, "closing_speed": closing,
            "tempo": float(np.sum((passes_t > ti - 60_000) & (passes_t <= ti))), "holder_pressure_m": press,
            "ball_u": f["ball_u"], "ball_speed": f["ball_speed"], "has_holder": f["has_holder"],
            "since_turnover_s": float(min((ti - last_turn[-1]) / 1000.0, 60.0)) if last_turn.size else 60.0,
            "att_third_control": f["att_third_control"], "minute": f["minute"],
            "label": int(any(ti < ht <= ti + CHAOS_HORIZON_MS and hteam == other for ht, hteam in handover)),
        })
        if ti % (winprob_every_s * 1000) == 0:
            xt, xgd = xt_xg_15(m.events, ti)
            score = s["score"][i]
            wp_rows.append({
                "seed": m.seed, "t_ms": ti, "score_diff": int(score[0]) - int(score[1]), "minute": ti / 60000.0,
                "period": int(s["period"][i]), "red_card_diff": 0, "xt_diff_15": xt, "xg_diff_15": xgd,
                "chaos": chaos_index(pc, rate, trans), "label": m.result,
            })
    return g8_rows, chaos_rows, wp_rows


def match_tables(match_dir: str | Path, step_s: int = 2) -> dict[str, pd.DataFrame]:
    m = load_match(match_dir)
    g8, chaos, wp = state_rows(m, step_s=step_s)
    return {"shots": pd.DataFrame(shot_rows(m)), "passes": pd.DataFrame(pass_rows(m)), "goal8s": pd.DataFrame(g8),
            "chaos": pd.DataFrame(chaos), "winprob": pd.DataFrame(wp)}


def moment_features(window, events: list[dict], t_ms: int) -> tuple[dict, int]:
    """The 12 chaos features at t_ms from full 10 Hz tracking (same formulas as `state_rows`), and the team in
    possession (carried over loose balls). Used by the moment encoder index and similar_moments."""
    i = window.index_at(t_ms)
    pos = np.asarray(window.possession[: i + 1])
    held = np.flatnonzero(pos >= 0)
    team = int(pos[held[-1]]) if held.size else 0
    S = np.asarray(window.S[i], dtype=np.float64)
    pc = pitch_control(S)
    g = state_features(S[None], np.array([window.ball_z[i]]), np.array([window.holder[i]]), np.array([team]),
                       np.array([window.period[i]]), np.array([t_ms]), np.array([window.possession[i] >= 0]),
                       pcs=pc[None]).iloc[0]
    turn_t = open_play_turnovers(events, 0, t_ms)
    passes = sum(1 for e in events if e["type"] == "pass" and t_ms - 60_000 < e["t_ms"] <= t_ms)
    h = int(window.holder[i])
    if h >= 0:
        opp = _rows(1 - (h >= 11))
        rel = S[h, 0:2] - S[opp, 0:2]
        dist = np.hypot(rel[:, 0], rel[:, 1])
        k = int(np.argmin(dist))
        closing = float(max(0.0, np.dot(S[opp[k], 2:4] - S[h, 2:4], rel[k] / max(dist[k], 1e-6))))
        press = float(dist[k])
    else:
        closing, press = 0.0, 30.0
    return {"contested_frac": float(np.mean(np.abs(pc - 0.5) < 0.15)), "turnovers_60s": turnover_rate(events, t_ms),
            "transition_share": transition_share_at(events, t_ms), "closing_speed": closing, "tempo": float(passes),
            "holder_pressure_m": press, "ball_u": float(g["ball_u"]), "ball_speed": float(g["ball_speed"]),
            "has_holder": int(g["has_holder"]),
            "since_turnover_s": float(min((t_ms - turn_t[-1]) / 1000.0, 60.0)) if turn_t.size else 60.0,
            "att_third_control": float(g["att_third_control"]), "minute": t_ms / 60000.0}, team
