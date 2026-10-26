"""Fictional league loaded from data/league/*.json."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

STYLE_KEYS = ("press_height", "tempo", "width", "directness", "line_height")
# 4-3-3: GK, RB, RCB, LCB, LB, RCM, CM, LCM, RW, CF, LW (right side is low y when attacking +x)
FORMATION = ("GK", "DF", "DF", "DF", "DF", "MF", "MF", "MF", "FW", "FW", "FW")
GOLDEN_SEED = 4242
SLOTS = ("GK", "RB", "RCB", "LCB", "LB", "RCM", "CM", "LCM", "RW", "CF", "LW")


class Kit(BaseModel):
    model_config = ConfigDict(frozen=True)
    primary: str
    secondary: str


class Club(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    id: str
    name: str
    short_name: str
    city: str
    stadium: str
    home_kit: Kit
    away_kit: Kit
    rivalries: list[str]


class Player(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    id: str
    name: str
    club: str
    position: str
    shirt: int
    traits: list[str]
    age: int


class League:
    """Clubs, players and style profiles. Players are referenced by id only; names stay in the league files."""

    def __init__(self, clubs: list[Club], players: list[Player], styles: dict[str, dict[str, float]]) -> None:
        self.clubs = {c.id: c for c in clubs}
        self.club_order = [c.id for c in clubs]
        self.players = {p.id: p for p in players}
        self.styles = {cid: {k: float(v[k]) for k in STYLE_KEYS} for cid, v in styles.items()}

    @classmethod
    def load(cls, path: str | Path) -> League:
        path = Path(path)
        clubs = [Club(**c) for c in json.loads((path / "clubs.json").read_text(encoding="utf-8"))]
        players = [Player(**p) for p in json.loads((path / "players.json").read_text(encoding="utf-8"))]
        styles = json.loads((path / "styles.json").read_text(encoding="utf-8"))
        return cls(clubs, players, styles)

    def fixture(self, seed: int) -> tuple[str, str]:
        """(home, away) for a seed: the golden match is Verdant v Ironvale, every other seed walks the 56 ordered
        pairings with stride 17 so any 56 consecutive seeds play each pairing once."""
        if seed == GOLDEN_SEED:
            return "verdant", "ironvale"
        pairs = [(h, a) for h in self.club_order for a in self.club_order if h != a]
        return pairs[(seed * 17) % len(pairs)]

    def squad(self, club: str) -> list[Player]:
        return sorted((p for p in self.players.values() if p.club == club), key=lambda p: (p.shirt, p.id))

    def lineup(self, club: str) -> tuple[list[str], list[str]]:
        """Starting XI in FORMATION order (lowest shirt numbers per position) and the bench."""
        squad = self.squad(club)
        if club not in self.clubs:
            raise KeyError(club)
        starting: list[str] = []
        used: set[str] = set()
        for pos in FORMATION:
            pick = next(p for p in squad if p.position == pos and p.id not in used)
            starting.append(pick.id)
            used.add(pick.id)
        bench = [p.id for p in squad if p.id not in used]
        return starting, bench
