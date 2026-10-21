"""Export the league for the screens: apps/overlay/public/league.json (T-011). Standard library only.

Club kit colours and player id -> {shirt, name, club}. The engine and the stream carry ids only;
names are resolved here, at render time. Deterministic (sorted keys).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    league = ROOT / "data" / "league"
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "apps" / "overlay" / "public" / "league.json"
    clubs = json.loads((league / "clubs.json").read_text(encoding="utf-8"))
    players = json.loads((league / "players.json").read_text(encoding="utf-8"))
    data = {
        "golden": {"home": clubs[0]["id"], "away": clubs[1]["id"]},
        "clubs": {c["id"]: {"name": c["name"], "short_name": c["short_name"], "home_kit": c["home_kit"],
                            "away_kit": c["away_kit"]} for c in clubs},
        "players": {p["id"]: {"shirt": p["shirt"], "name": p["name"], "club": p["club"], "position": p["position"]}
                    for p in players},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, sort_keys=True, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}: {len(clubs)} clubs, {len(players)} players")
    return 0


if __name__ == "__main__":
    sys.exit(main())
