"""Verify the grf_tracking_data CSVs before anything trains on them (T-012).

Usage: python3 packages/policy/grf_check.py data/grf/tiny_set [--out data/grf/coords_report.json]

Standard library only, so it runs without the project venv. Checks the column set, 23 rows per
timestep (22 players plus the ball, PLAYER_ID -1), TIMESTEP spacing, observed x/y/z ranges for
players and ball, whether the TECH_PLAN 1.6 metre mapping holds, and derives the frame rate from
the data itself: the ball's vertical acceleration in flight must equal g, so the step length is
dt = sqrt(-d2z / g) where d2z is the second difference of LOCATION_Z per step.
Writes coords_report.json beside the data folder and exits 1 if a hard check fails.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

COLUMNS = ["GAME_ID", "TIMESTEP", "TEAM_0_SCORE", "TEAM_1_SCORE", "PLAYER_ID", "TEAM_ID", "PLAYER_ROLE",
           "LOCATION_X", "LOCATION_Y", "LOCATION_Z", "VELOCITY_X", "VELOCITY_Y", "VELOCITY_Z", "ON_BALL"]
ROWS_PER_STEP = 23
BALL_ID = "-1"
# TECH_PLAN 1.6: GRF normalised x in [-1, 1], y in [-0.42, 0.42]; x' = (x+1)*52.5, y' = (y+0.42)*(68/0.84)
X_RANGE, Y_RANGE = (-1.0, 1.0), (-0.42, 0.42)
MAPPING_TOL = 0.02          # normalised units a player may stand beyond the line (keepers on the goal line)
MAPPING_MIN_SHARE = 0.999   # share of player positions inside the tolerant box for the mapping to hold
EXPECTED_HZ = 10.0
HZ_TOL = 0.5
G = 9.81
AIRBORNE_Z = 0.5            # metres; both neighbours above this so bounces are excluded


def to_metres(x: float, y: float) -> tuple[float, float]:
    return (x + 1.0) * 52.5, (y + 0.42) * (68.0 / 0.84)


class Range:
    def __init__(self) -> None:
        self.lo, self.hi = math.inf, -math.inf

    def add(self, v: float) -> None:
        self.lo, self.hi = min(self.lo, v), max(self.hi, v)

    def as_list(self) -> list[float]:
        return [round(self.lo, 4), round(self.hi, 4)]


def scan(files: list[Path]) -> dict:
    errors: list[str] = []
    rng = {k: Range() for k in ("player_x", "player_y", "ball_x", "ball_y", "ball_z")}
    inside = total_players = 0
    step_rows: dict[tuple[str, int], int] = Counter()
    ball_rows: dict[tuple[str, int], int] = Counter()
    ball_z: dict[str, dict[int, float]] = defaultdict(dict)
    player_step_dx: list[float] = []   # |dx| per step in metres, a sample for a sprint-speed sanity check
    last_x: dict[tuple[str, str], tuple[int, float]] = {}
    roles: Counter = Counter()
    for path in files:
        with path.open(newline="") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames != COLUMNS:
                errors.append(f"{path.name}: columns {reader.fieldnames} != expected")
                continue
            for row in reader:
                game = f"{path.name}:{row['GAME_ID']}"
                t = int(row["TIMESTEP"])
                x, y, z = float(row["LOCATION_X"]), float(row["LOCATION_Y"]), float(row["LOCATION_Z"])
                step_rows[(game, t)] += 1
                if row["PLAYER_ID"] == BALL_ID:
                    ball_rows[(game, t)] += 1
                    rng["ball_x"].add(x), rng["ball_y"].add(y), rng["ball_z"].add(z)
                    ball_z[game][t] = z
                    continue
                roles[row["PLAYER_ROLE"]] += 1
                rng["player_x"].add(x), rng["player_y"].add(y)
                total_players += 1
                if (X_RANGE[0] - MAPPING_TOL <= x <= X_RANGE[1] + MAPPING_TOL
                        and Y_RANGE[0] - MAPPING_TOL <= y <= Y_RANGE[1] + MAPPING_TOL):
                    inside += 1
                key = (game, row["PLAYER_ID"])
                if key in last_x and last_x[key][0] == t - 1:
                    player_step_dx.append(abs(x - last_x[key][1]) * 52.5)
                last_x[key] = (t, x)

    games = sorted({g for g, _ in step_rows})
    steps_by_game = defaultdict(list)
    for g, t in step_rows:
        steps_by_game[g].append(t)
    spacing = Counter()
    for g in games:
        ts = sorted(steps_by_game[g])
        spacing.update(b - a for a, b in zip(ts, ts[1:], strict=False))
    bad_rows = sum(1 for n in step_rows.values() if n != ROWS_PER_STEP)
    bad_ball = sum(1 for k in step_rows if ball_rows.get(k, 0) != 1)
    if bad_rows:
        errors.append(f"{bad_rows} timesteps without exactly {ROWS_PER_STEP} rows")
    if bad_ball:
        errors.append(f"{bad_ball} timesteps without exactly one ball row (PLAYER_ID {BALL_ID})")
    if set(spacing) != {1}:
        errors.append(f"TIMESTEP spacing is not always 1: {dict(spacing)}")

    # frame interval from gravity: -d2z = g * dt^2 while the ball is in flight
    accel = []
    for zs in ball_z.values():
        for t in sorted(zs):
            a, b, c = zs.get(t - 1), zs.get(t), zs.get(t + 1)
            if a is None or c is None or min(a, b, c) <= AIRBORNE_Z:
                continue
            accel.append(-(c - 2 * b + a))
    dt = math.sqrt(statistics.median(accel) / G) if accel else float("nan")
    hz = 1.0 / dt if accel else float("nan")
    if not abs(hz - EXPECTED_HZ) <= HZ_TOL:
        errors.append(f"derived frame rate {hz:.2f} Hz is not {EXPECTED_HZ} +/- {HZ_TOL}")

    share = inside / total_players if total_players else 0.0
    mapping_holds = share >= MAPPING_MIN_SHARE
    p99_dx = sorted(player_step_dx)[int(0.99 * (len(player_step_dx) - 1))] if player_step_dx else float("nan")
    lo_m, hi_m = to_metres(rng["player_x"].lo, rng["player_y"].lo), to_metres(rng["player_x"].hi, rng["player_y"].hi)
    return {
        "files": [p.name for p in files],
        "games": len(games),
        "timesteps_per_game": sorted({len(v) for v in steps_by_game.values()}),
        "rows_per_timestep_ok": bad_rows == 0,
        "one_ball_row_per_timestep_ok": bad_ball == 0,
        "timestep_spacing": {str(k): v for k, v in sorted(spacing.items())},
        "player_roles": dict(sorted(roles.items())),
        "observed_ranges_normalised": {k: r.as_list() for k, r in rng.items()},
        "observed_player_range_metres": {"x": [round(lo_m[0], 2), round(hi_m[0], 2)],
                                          "y": [round(lo_m[1], 2), round(hi_m[1], 2)]},
        "frame_rate": {
            "method": "ball in flight (z > 0.5 m at t-1, t, t+1): dt = sqrt(median(-d2z) / 9.81)",
            "airborne_samples": len(accel),
            "dt_s": round(dt, 4),
            "derived_hz": round(hz, 2),
            "expected_hz": EXPECTED_HZ,
            "matches_expected": abs(hz - EXPECTED_HZ) <= HZ_TOL,
            "player_p99_dx_m_per_step": round(p99_dx, 3),
            "player_p99_speed_x_m_s_at_derived_hz": round(p99_dx * hz, 2),
        },
        "mapping_tech_plan_1_6": {
            "x_m": "(x + 1) * 52.5",
            "y_m": "(y + 0.42) * (68 / 0.84)",
            "expected_x": list(X_RANGE),
            "expected_y": list(Y_RANGE),
            "tolerance_normalised": MAPPING_TOL,
            "player_share_inside": round(share, 5),
            "holds": mapping_holds,
            "notes": ("LOCATION_Z and VELOCITY_Z are -1 placeholders for players; ball LOCATION_Z is in metres "
                      "(rest height 0.11 m). VELOCITY_X/Y are displacement per step in normalised units "
                      "(median |dpos|/|v| = 1.0, measured on game 0 during T-012), not per second. One normalised "
                      "unit is 52.5 m along x but 80.95 m along y, so the mapping is anisotropic: convert "
                      "velocities per axis, never by a single scale. 3,001 steps at the derived rate is about "
                      "300 s of play per game, not 90 minutes."),
        },
        "errors": errors,
        "ok": not errors and mapping_holds,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("data_dir", type=Path)
    ap.add_argument("--out", type=Path, default=None, help="default: <data_dir>/../coords_report.json")
    args = ap.parse_args()
    files = sorted(args.data_dir.glob("*.csv"))
    if not files:
        print(f"grf_check: no CSV files in {args.data_dir}")
        return 1
    report = scan(files)
    out = args.out or args.data_dir.parent / "coords_report.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    fr = report["frame_rate"]
    print(f"grf_check: {report['games']} games, {fr['derived_hz']} Hz derived, mapping holds={report['mapping_tech_plan_1_6']['holds']}, "
          f"errors={len(report['errors'])} -> {out}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
