"""Full-time recap beat for Liverpool v Manchester City (video v3, held for the producer's veto in the studio
replay): the goals, the red card and the final score from the tagged events, with event ids as sources.

    python -m footage.recap_beat
"""

from __future__ import annotations

import json
import sys

from footage.clips import CLIPS, ROOT, clip_dir

SLUG = "liverpool-mancity-2526"


def run() -> dict:
    from footage.river import clock, clock_to_clip, goals, score_at
    from footage.v3 import write_beat

    evs = [json.loads(line) for line in (clip_dir(SLUG) / "cache" / "evidence.jsonl").read_text().splitlines()
           if line.strip()]
    evs = [e for e in evs if e.pop("_collection") == "events" and e["type"] != "match_metadata"]
    gs = goals(evs)
    to_clip = clock_to_clip(evs)
    end = max(e["t_ms"] for e in evs)
    red = [e for e in evs if e["type"] == "card" and "red" in (e["attrs"].get("note") or "").lower()]
    clip = CLIPS[SLUG]
    beat = {"clip_ms": to_clip(end), "t_ms": end, "clock": clock(end), "home": clip["home"], "away": clip["away"],
            "final_score": score_at(gs, end),
            "goals": [{"clock": clock(g["t_ms"]), "team": g["team"], "pid": g.get("player"),
                       "name": g["attrs"].get("player_name"), "score_after": score_at(gs, g["t_ms"]),
                       "event_id": g["id"]} for g in gs],
            "red_cards": [{"clock": clock(e["t_ms"]), "team": e["team"], "pid": e.get("player"),
                           "name": e["attrs"].get("player_name"), "event_id": e["id"]} for e in red],
            "window": "the final 20 minutes in the clip (72:00 to full time)",
            "source": "events.jsonl via cache/evidence.jsonl"}
    write_beat(SLUG, "recap", beat["clip_ms"], beat)
    return beat


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "packages"))
    print(json.dumps(run(), indent=1, ensure_ascii=False))
