"""Validate the fictional league in data/league (T-002). Standard library only.

Usage: python3 scripts/check_league.py [LEAGUE_DIR]

Checks: 8 clubs, 200 players p_001..p_200 (25 per club, unique ids, names and shirts per club),
at least two goalkeepers per club, valid hex kit colours, rivalries that point at real league clubs,
style dials in [0, 1] for every club, Okafor, Silva and Reyes in the two golden clubs, and no phrase
from banned_names.txt (whole phrase, case-insensitive) in any league string or in lore.md.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

N_CLUBS, N_PLAYERS, PER_CLUB, MIN_GK = 8, 200, 25, 2
POSITIONS = {"GK", "DF", "MF", "FW"}
STYLE_KEYS = {"press_height", "tempo", "width", "directness", "line_height"}
GOLDEN_SURNAMES = ("Okafor", "Silva", "Reyes")
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def strings(obj):
    """Yield every string (keys and values) inside a JSON value."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v)


def load_banned(path: Path) -> list[str]:
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()]
    return [ln for ln in lines if ln and not ln.startswith("#")]


def banned_hits(texts: dict[str, str], banned: list[str]) -> list[str]:
    hits = []
    for phrase in banned:
        rx = re.compile(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", re.IGNORECASE)
        for where, text in texts.items():
            if rx.search(text):
                hits.append(f"banned phrase {phrase!r} in {where}")
    return hits


def check(league: Path) -> list[str]:
    errors: list[str] = []
    clubs = json.loads((league / "clubs.json").read_text(encoding="utf-8"))
    players = json.loads((league / "players.json").read_text(encoding="utf-8"))
    styles = json.loads((league / "styles.json").read_text(encoding="utf-8"))
    club_ids = [c["id"] for c in clubs]

    if len(clubs) != N_CLUBS:
        errors.append(f"{len(clubs)} clubs, expected {N_CLUBS}")
    if len(set(club_ids)) != len(club_ids):
        errors.append("duplicate club ids")
    for c in clubs:
        for field in ("id", "name", "short_name", "city", "home_kit", "away_kit", "rivalries", "history", "crest_brief"):
            if field not in c:
                errors.append(f"club {c.get('id')}: missing {field}")
        for kit in ("home_kit", "away_kit"):
            for part, colour in c.get(kit, {}).items():
                if not HEX.match(str(colour)):
                    errors.append(f"club {c['id']}: {kit}.{part} {colour!r} is not #RRGGBB")
        for r in c.get("rivalries", []):
            if r not in club_ids or r == c["id"]:
                errors.append(f"club {c['id']}: rivalry {r!r} is not another league club")

    ids = [p["id"] for p in players]
    if len(players) != N_PLAYERS:
        errors.append(f"{len(players)} players, expected {N_PLAYERS}")
    if sorted(ids) != [f"p_{i:03d}" for i in range(1, N_PLAYERS + 1)]:
        errors.append("player ids are not exactly p_001..p_200")
    for name, n in Counter(p["name"] for p in players).items():
        if n > 1:
            errors.append(f"player name {name!r} used {n} times")
    per_club = Counter(p["club"] for p in players)
    for cid in club_ids:
        if per_club[cid] != PER_CLUB:
            errors.append(f"club {cid}: {per_club[cid]} players, expected {PER_CLUB}")
        squad = [p for p in players if p["club"] == cid]
        gks = sum(p["position"] == "GK" for p in squad)
        if gks < MIN_GK:
            errors.append(f"club {cid}: {gks} goalkeepers, need {MIN_GK}+")
        for shirt, n in Counter(p["shirt"] for p in squad).items():
            if n > 1:
                errors.append(f"club {cid}: shirt {shirt} used {n} times")
    for p in players:
        if p["club"] not in club_ids:
            errors.append(f"{p['id']}: unknown club {p['club']!r}")
        if p["position"] not in POSITIONS:
            errors.append(f"{p['id']}: bad position {p['position']!r}")
        if not (isinstance(p["shirt"], int) and 1 <= p["shirt"] <= 99):
            errors.append(f"{p['id']}: bad shirt {p['shirt']!r}")

    golden = set(club_ids[:2])
    for surname in GOLDEN_SURNAMES:
        if not any(p["name"].split()[-1] == surname and p["club"] in golden for p in players):
            errors.append(f"no {surname} in the golden clubs {sorted(golden)}")

    if set(styles) != set(club_ids):
        errors.append("styles.json clubs differ from clubs.json")
    for cid, dials in styles.items():
        if set(dials) != STYLE_KEYS:
            errors.append(f"styles {cid}: keys {sorted(dials)} != {sorted(STYLE_KEYS)}")
        for k, v in dials.items():
            if not (isinstance(v, (int, float)) and 0 <= v <= 1):
                errors.append(f"styles {cid}.{k} = {v!r} not in [0, 1]")

    texts = {}
    for fname, obj in (("clubs.json", clubs), ("players.json", players), ("styles.json", styles)):
        texts[fname] = "\n".join(strings(obj))
    texts["lore.md"] = (league / "lore.md").read_text(encoding="utf-8")
    errors += banned_hits(texts, load_banned(league / "banned_names.txt"))
    return errors


def main() -> int:
    league = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "data" / "league"
    errors = check(league)
    if errors:
        print("check_league: FAIL")
        for e in errors:
            print("  " + e)
        return 1
    print(f"check_league: OK ({N_CLUBS} clubs, {N_PLAYERS} players, banned list clean)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
