"""Rules library (rules.yaml) and shared pitch geometry for the Fourth Official (TECH_PLAN 1.4, T-049)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

PITCH_L, PITCH_W, GOAL_Y = 105.0, 68.0, 34.0
RULES_PATH = Path(__file__).resolve().parent / "rules.yaml"


@lru_cache(maxsize=1)
def rules() -> dict:
    return yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))


def attack_dir(team: int, period: int) -> int:
    """+1 when team (0 home, 1 away) attacks +x in this period."""
    d = 1 if int(period) == 1 else -1
    return d if team == 0 else -d


def to_attacking(x: float, y: float, team: int, period: int) -> tuple[float, float]:
    """(u, v) with u the distance from the team's own goal line."""
    return (x, y) if attack_dir(team, period) > 0 else (PITCH_L - x, PITCH_W - y)


def in_penalty_area(x: float, y: float, defending_team: int, period: int) -> bool:
    """Inside the penalty area that `defending_team` defends."""
    box = rules()["penalty_area"]
    u, v = to_attacking(x, y, defending_team, period)
    return u <= box["depth_m"] and abs(v - GOAL_Y) <= box["half_width_m"]


def penalty_area_lines(defending_team: int, period: int) -> list[list[list[float]]]:
    """The three lines of that penalty area, in absolute metres (for the referee_line graphic)."""
    box = rules()["penalty_area"]
    d = attack_dir(defending_team, period)
    x0 = 0.0 if d > 0 else PITCH_L
    x1 = box["depth_m"] if d > 0 else PITCH_L - box["depth_m"]
    lo, hi = GOAL_Y - box["half_width_m"], GOAL_Y + box["half_width_m"]
    return [[[x0, lo], [x1, lo]], [[x1, lo], [x1, hi]], [[x1, hi], [x0, hi]]]
