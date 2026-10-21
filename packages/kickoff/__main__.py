"""Kickoff CLI: python -m kickoff play --seed N --league data/league --out DIR [--home ID --away ID].

`--target api` streams the match into whyline-api in real time instead of writing files (kickoff/stream.py).
"""

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
    play.add_argument("--out", default=None, help="match folder (required with --target file)")
    play.add_argument("--target", choices=["file", "api"], default="file")
    play.add_argument("--api", default="http://localhost:8000", help="whyline-api base URL for --target api")
    play.add_argument("--speed", type=float, default=1.0, help="stream speed for --target api")
    play.add_argument("--home", default=None, help="club id (default: League.fixture(seed))")
    play.add_argument("--away", default=None, help="club id (default: League.fixture(seed))")
    play.add_argument("--until-ms", type=int, default=None)
    args = ap.parse_args(argv)
    if args.target == "file" and not args.out:
        ap.error("--out is required with --target file")

    league = League.load(args.league)
    home, away = league.fixture(args.seed)
    home, away = args.home or home, args.away or away
    started = time.perf_counter()
    record = Engine(league, home, away, seed=args.seed).play(until_ms=args.until_ms)
    if args.target == "api":
        from .stream import stream_match

        print(f"{record.match_id}: simulated in {time.perf_counter() - started:.1f} s; streaming to {args.api}")
        sent = stream_match(record.match_id, record.events, record.tracking, api=args.api, speed=args.speed)
        print(f"{record.match_id}: posted {sent['events']} events and {sent['frames']} frames")
        return 0
    out = write_match(record, args.out)
    goals = [e for e in record.events if e["type"] == "goal"]
    score = (sum(g["team"] == "home" for g in goals), sum(g["team"] == "away" for g in goals))
    print(f"{record.match_id}: {home} {score[0]}-{score[1]} {away}, {len(record.events)} events, "
          f"{len(record.tracking['t_ms'])} frames, {time.perf_counter() - started:.1f} s -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
