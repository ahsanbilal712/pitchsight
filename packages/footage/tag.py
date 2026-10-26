"""Gemini event tagging of a real clip.

    python -m footage.tag <slug> [--segments 0,1] [--dry-run]

The clip is cut with ffmpeg into short low-resolution segments (data/footage/<slug>/segments/, git-ignored media),
and each segment goes inline to gemini-3.8-flash on Vertex AI (no bucket, no Files API: project rule) at low media
resolution and 1 frame per second, with a JSON schema for the answer. Every call is checked and recorded by
SpendGuard under the clip's own match id (config/footage.yaml); a clip stops at `max_usd_per_clip`.
The raw answer per segment is kept in data/footage/<slug>/tags/ (a re-run reads it instead of paying again), and
the merged, de-duplicated events are written to data/footage/<slug>/events.jsonl in event.schema.json form:
real players have no p_ ids, so `player` is null and `attrs.player_name` carries the name the broadcast gives.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from footage.clips import CLIPS, ROOT, clip_dir, load_config

log = logging.getLogger("whyline.footage")

TYPES = ["pass", "shot", "goal", "save", "tackle", "interception", "clearance", "foul", "card", "offside",
         "set_piece", "substitution"]
OUTCOMES = ["complete", "incomplete", "goal", "saved", "blocked", "off_target", "won", "lost", "committed",
            "awarded", "n/a"]
RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["events"],
    "properties": {"events": {"type": "array", "items": {
        "type": "object",
        "required": ["clip_time", "match_clock", "type", "team", "player", "outcome", "replay"],
        "properties": {
            "clip_time": {"type": "string", "description": "mm:ss from the start of this video"},
            "match_clock": {"type": "string", "description": "mm:ss on the score bug at that instant, '' if hidden"},
            "type": {"type": "string", "enum": TYPES},
            "team": {"type": "string", "description": "club of the player making the action, '' if unclear"},
            "player": {"type": "string", "description": "name given by commentary or graphics, '' if unknown"},
            "outcome": {"type": "string", "enum": OUTCOMES},
            "replay": {"type": "boolean", "description": "true for replays, slow motion and alternative angles"},
            "note": {"type": "string", "description": "at most 12 words"},
        }}}},
}
PROMPT = """You tag football events in a segment of a Premier League broadcast: {home} (home) v {away} (away).
List every shot, goal, save, tackle, interception, clearance, foul, card, offside, set piece and substitution, and
only those passes that create a chance: the pass just before a shot, a through ball or a cross into the box.
For each event give the video time from the start of THIS segment (mm:ss), the match clock on the score bug if
visible, the club of the player making the action, and the player's name only if the commentary or an on-screen
graphic says it. Mark replays, slow motion and alternative camera angles with replay=true: they repeat an event
already seen. Do not guess: omit what you cannot see."""


# ---------------------------------------------------------------------------------------------------- segments

def duration_s(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def segments(slug: str, cfg: dict | None = None) -> list[dict]:
    """[{i, path, start_s, dur_s}]: cut once, reused afterwards."""
    cfg = cfg or load_config()["tagger"]
    src = clip_dir(slug) / "clip.mp4"
    out_dir = clip_dir(slug) / "segments"
    out_dir.mkdir(exist_ok=True)
    total, step = duration_s(src), float(cfg["segment_s"])
    segs, i, start = [], 0, 0.0
    while start < total - 1:
        dur = min(step, total - start)
        path = out_dir / f"seg_{i:03d}.mp4"
        if not path.exists():
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(src),
                            "-vf", f"scale=-2:{cfg['height_px']},fps={cfg['fps_encode']}", "-c:v", "libx264",
                            "-preset", "veryfast", "-crf", "34", "-ac", "1", "-b:a", "24k", str(path)], check=True)
        segs.append({"i": i, "path": path, "start_s": start, "dur_s": dur})
        i, start = i + 1, start + step
    return segs


# ---------------------------------------------------------------------------------------------------- model call

def sdk_client():
    from dotenv import load_dotenv
    from google import genai

    load_dotenv(ROOT / ".env")
    if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true", "yes"):
        return genai.Client(vertexai=True, project=os.environ["GOOGLE_CLOUD_PROJECT"],
                            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"))
    return genai.Client(api_key=os.environ["GOOGLE_API_KEY"])


def tag_segment(client, guard, slug: str, seg: dict, cfg: dict) -> dict:
    """One inline-video call; returns {events, usage, cost_usd, latency_ms}. SpendCapReached propagates."""
    from google.genai import types

    clip = CLIPS[slug]
    guard.check(clip["match_id"])
    video = types.Part(inline_data=types.Blob(data=seg["path"].read_bytes(), mime_type="video/mp4"),
                       video_metadata=types.VideoMetadata(fps=cfg["fps_sample"]))
    config = types.GenerateContentConfig(
        response_mime_type="application/json", response_json_schema=RESPONSE_SCHEMA, temperature=0,
        media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW,
        thinking_config=types.ThinkingConfig(thinking_budget=0), max_output_tokens=8000)
    t0 = time.perf_counter()
    resp = client.models.generate_content(model=cfg["model"], config=config,
                                          contents=[video, PROMPT.format(home=clip["home"], away=clip["away"])])
    latency = int((time.perf_counter() - t0) * 1000)
    u = resp.usage_metadata
    tokens_in = int(u.prompt_token_count or 0)
    tokens_out = int(u.candidates_token_count or 0) + int(u.thoughts_token_count or 0)
    row = guard.record("footage_tagger", cfg["model"], tokens_in, tokens_out, clip["match_id"], "precompute")
    try:
        events = json.loads(resp.text or "{}").get("events", [])
    except json.JSONDecodeError:
        events = []
        log.warning("%s segment %d: answer is not JSON (%d chars)", slug, seg["i"], len(resp.text or ""))
    return {"segment": seg["i"], "start_s": seg["start_s"], "dur_s": seg["dur_s"], "events": events,
            "usage": {"tokens_in": tokens_in, "tokens_out": tokens_out}, "cost_usd": row["cost_usd"],
            "latency_ms": latency, "model": cfg["model"]}


# ---------------------------------------------------------------------------------------------------- events

_MMSS = re.compile(r"^\s*(\d{1,3}):(\d{2})\s*$")


def mmss_ms(text: str) -> int | None:
    m = _MMSS.match(text or "")
    return (int(m.group(1)) * 60 + int(m.group(2))) * 1000 if m else None


def side(team: str, clip: dict) -> str:
    """home | away | none from a club name as the model wrote it."""
    t = (team or "").lower().replace("spurs", "tottenham")
    for key in ("home", "away"):
        words = [w for w in clip[key].lower().replace("hotspur", "").split() if len(w) > 2]
        if t and (t in clip[key].lower() or any(w in t for w in words if w not in ("manchester", "united", "city"))
                  or (("utd" in t or "united" in t) and "united" in clip[key].lower())
                  or ("city" in t and "city" in clip[key].lower())):
            return key
    return "none"


def to_events(slug: str, tags: list[dict]) -> tuple[list[dict], dict]:
    """event.schema.json documents (live-action events only, replays dropped) and counts."""
    clip = CLIPS[slug]
    raw = []
    for tag in sorted(tags, key=lambda t: t["segment"]):
        for ev in tag["events"]:
            at = mmss_ms(ev.get("clip_time", ""))
            if at is None or ev.get("type") not in TYPES:
                continue
            raw.append({**ev, "clip_ms": int(tag["start_s"] * 1000) + at})
    live = sorted((e for e in raw if not e.get("replay")), key=lambda e: e["clip_ms"])
    # clock: read off the score bug, else carried from the nearest read clock (play runs 1:1 between reads)
    reads = [(e["clip_ms"], mmss_ms(e.get("match_clock", ""))) for e in live]
    reads = [(c, m) for c, m in reads if m is not None]
    out, last = [], None
    for e in live:
        clock_ms, source = mmss_ms(e.get("match_clock", "")), "score_bug"
        if clock_ms is None and reads:
            c, m = min(reads, key=lambda r: abs(r[0] - e["clip_ms"]))
            clock_ms, source = m + (e["clip_ms"] - c), "carried"
        if clock_ms is None:
            continue
        key = (e["type"], e.get("player") or "", round(e["clip_ms"] / 3000))   # a segment boundary repeats it
        if key == last:
            continue
        last = key
        n = len(out) + 1
        secs = max(clock_ms, 0) // 1000
        out.append({"schema_version": "1.0.0", "id": f"e_{n:04d}", "match_id": clip["match_id"], "idx": n,
                    "t_ms": max(clock_ms, 0), "period": 1 if secs < 45 * 60 else 2,
                    "clock": f"{min(secs // 60, 99):02d}:{secs % 60:02d}", "type": e["type"],
                    "team": side(e.get("team", ""), clip), "player": None, "location": None,
                    "outcome": e.get("outcome") or "n/a", "under_pressure": False, "related_event_ids": [],
                    "attrs": {"player_name": e.get("player") or None, "team_name": e.get("team") or None,
                              "clip_ms": e["clip_ms"], "clock_source": source, "note": e.get("note") or "",
                              "source": "gemini_tagger"}})
    return out, {"tagged": len(raw), "replays_dropped": len(raw) - len(live), "events": len(out)}


# ---------------------------------------------------------------------------------------------------- run

def run(slug: str, only: list[int] | None = None, dry_run: bool = False) -> dict:
    from api.spend import SpendGuard

    cfg = load_config()["tagger"]
    tags_dir = clip_dir(slug) / "tags"
    tags_dir.mkdir(exist_ok=True)
    segs = segments(slug, cfg)
    guard, client = SpendGuard(), None
    spent, tags = 0.0, []
    for seg in segs:
        path = tags_dir / f"seg_{seg['i']:03d}.json"
        if path.exists():
            tags.append(json.loads(path.read_text()))
            continue
        if (only is not None and seg["i"] not in only) or dry_run:
            continue
        if spent >= cfg["max_usd_per_clip"]:
            log.warning("%s: stopped at $%.4f (max_usd_per_clip)", slug, spent)
            break
        client = client or sdk_client()
        tag = tag_segment(client, guard, slug, seg, cfg)
        spent += tag["cost_usd"]
        path.write_text(json.dumps(tag, indent=1) + "\n")
        tags.append(tag)
        print(f"{slug} seg {seg['i']:03d}: {len(tag['events'])} events, {tag['usage']['tokens_in']} in / "
              f"{tag['usage']['tokens_out']} out, ${tag['cost_usd']:.4f}, {tag['latency_ms'] / 1000:.1f} s")
    events, counts = to_events(slug, tags)
    with (clip_dir(slug) / "events.jsonl").open("w") as fh:
        for e in events:
            fh.write(json.dumps(e, separators=(",", ":")) + "\n")
    cost = sum(t["cost_usd"] for t in tags)
    return {"slug": slug, "match_id": CLIPS[slug]["match_id"], "segments": len(segs), "tagged_segments": len(tags),
            "spent_now_usd": round(spent, 4), "clip_cost_usd": round(cost, 4), **counts}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slugs", nargs="*", default=sorted(CLIPS))
    ap.add_argument("--segments", default=None, help="comma list of segment numbers to call (default all)")
    ap.add_argument("--dry-run", action="store_true", help="cut segments and rebuild events.jsonl; no model call")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    only = [int(s) for s in args.segments.split(",")] if args.segments else None
    for slug in args.slugs:
        print(json.dumps(run(slug, only, args.dry_run)))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "packages"))
    raise SystemExit(main())
