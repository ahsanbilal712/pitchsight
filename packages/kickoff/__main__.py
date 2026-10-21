"""Kickoff CLI: python -m kickoff play --seed N --league data/league --out DIR [--home ID --away ID]."""

from __future__ import annotations

import argparse
import sys
import time

from .engine import Engine
from .league import League
from .record import write_match


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m kickoff")
    sub = ap.add_subparsers(dest="cmd", required=True)
    play = sub.add_parser("play", help="simulate one match and write events.jsonl, tracking.npz, truth.json")
    play.add_argument("--seed", type=int, required=True)
    play.add_argument("--league", default="data/league")
    play.add_argument("--out", required=True)
    play.add_argument("--home", default=None, help="club id (default: League.fixture(seed))")
    play.add_argument("--away", default=None, help="club id (default: League.fixture(seed))")
    play.add_argument("--until-ms", type=int, default=None)
    args = ap.parse_args(argv)

    league = League.load(args.league)
    home, away = league.fixture(args.seed)
    home, away = args.home or home, args.away or away
    started = time.perf_counter()
    record = Engine(league, home, away, seed=args.seed).play(until_ms=args.until_ms)
    out = write_match(record, args.out)
    goals = [e for e in record.events if e["type"] == "goal"]
    score = (sum(g["team"] == "home" for g in goals), sum(g["team"] == "away" for g in goals))
    print(f"{record.match_id}: {home} {score[0]}-{score[1]} {away}, {len(record.events)} events, "
          f"{len(record.tracking['t_ms'])} frames, {time.perf_counter() - started:.1f} s -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
