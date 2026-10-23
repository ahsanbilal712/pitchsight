"""Shirt numbers read off the 1080p broadcast, mapped to the club's published squad list (video v6: no placeholders).

    python -m footage.shirts [<slug>...] [--dry-run]    # -> data/footage/<slug>/shirts.json

For every player the videos label (the featured freezes' players in view, and the montage shooters without a
verified name), CROPS crops of his tracked box are taken within WINDOW_S of the moment the label applies to (the
freeze, or the strike: a track can switch to another player later in the shot) (tracks/<shot>.json, 1080p frames;
crops stay in the git-ignored frames/ folder) and read in one inline call to gemini-3.8-flash (SpendGuard, the clip's
match id). A number is accepted only when it is consistent: at least MIN_AGREE crops read it, it is at least two
thirds of the crops that show a number, and no other number is read more than once. The number is mapped to the
team's squad list for that season (data/footage/squads/<club>_<season>.json, with its source); a number that is not
in the list gives no name. footage.names reads shirts.json as the "shirt" source.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from footage.clips import CLIPS, ROOT, clip_dir

MODEL = "gemini-3.8-flash"
CROPS, MIN_AGREE = 8, 3
WINDOW_S = (1.5, 3.0)              # crops within this of the moment the label applies to (a track can switch later)
PAD_X, PAD_Y, CROP_H = 0.35, 0.12, 360
SCHEMA = {"type": "object", "required": ["reads"], "properties": {"reads": {"type": "array", "items": {
    "type": "object", "required": ["crop", "number", "confidence"], "properties": {
        "crop": {"type": "integer"}, "number": {"type": ["integer", "null"]},
        "confidence": {"type": "number"}, "side": {"type": "string", "enum": ["back", "front", "side", "none"]}}}}}}
PROMPT = ("These {n} numbered crops show the same football player ({kit}) in consecutive moments of a broadcast. "
          "For each crop, read the shirt number printed on his shirt or shorts if you can actually see digits; if "
          "the number is hidden, blurred or not visible, give null. Do not guess from position or appearance. "
          "Return JSON: {{\"reads\": [{{\"crop\": i, \"number\": int or null, \"confidence\": 0-1, \"side\": "
          "\"back\"|\"front\"|\"side\"|\"none\"}}]}}.")


def season(slug: str) -> str:
    y = slug.rsplit("-", 1)[1]
    return f"20{y[:2]}-{y[2:]}"


def squad(slug: str, team: str) -> dict:
    club = CLIPS[slug][f"{team}_id"]
    return json.loads((ROOT / "data" / "footage" / "squads" / f"{club}_{season(slug)}.json").read_text())


def targets(slug: str) -> list[dict]:
    """The attacking team's labelled players at the featured freezes (with a track: the carrier and the pass
    targets) and the montage shooters without a verified name."""
    from footage.clips import load_config

    out = []
    for f in load_config()["featured"]:
        if f["slug"] != slug:
            continue
        m = json.loads((clip_dir(slug) / "moments" / f"{f['clip_ms']}.json").read_text())
        shot = int(m["homography"]["source"].split("/")[1].split(".")[0])
        attacking = next(p["team"] for p in m["players"] if p.get("label") == m["ball"]["holder"])
        for p in m["players"]:                  # the ball carrier and his team-mates (the pass targets)
            if p.get("track_id") is not None and p.get("label") and not p["label"].startswith("t") \
                    and p.get("slot") != "GK" and p["team"] == attacking:
                out.append({"key": f"{f['clip_ms']}:{p['label']}", "team": p["team"], "label": p["label"],
                            "name_now": p.get("name"), "tracks": f"tracks/{shot}.json", "track_id": p["track_id"],
                            "at_s": f["clip_ms"] / 1000})
    shots = clip_dir(slug) / "cache" / "v5" / "shots_0.json"
    if shots.exists():
        for s in json.loads(shots.read_text())["result"]["shots"]:
            pos = (s.get("source") or {}).get("position") or ""
            if s.get("xg") is not None and not s["shooter"].get("name") and s["shooter"].get("label") and \
                    pos.startswith(f"{slug}/tracks/"):
                out.append({"key": f"{s['event_id']}:{s['shooter']['label']}", "team": s["team"],
                            "label": s["shooter"]["label"], "name_now": None, "tracks": pos.split("/", 1)[1],
                            "track_id": int(s["shooter"]["label"][1:]), "at_s": s["clip_ms"] / 1000})
    return out


def crops(slug: str, t: dict) -> list[Path]:
    tracks = json.loads((clip_dir(slug) / t["tracks"]).read_text())
    every = [(f["t"], p["bbox"]) for f in tracks["frames"] for p in f["players"]
             if p["track_id"] == t["track_id"] and p.get("bbox")]
    for w in WINDOW_S:                                          # the label holds at its moment, not the whole shot
        seen = [s for s in every if abs(s[0] - t["at_s"]) <= w]
        if len(seen) >= CROPS:
            break
    seen.sort(key=lambda s: -(s[1][3] - s[1][1]))              # the largest boxes first: digits are biggest there
    pick = sorted(seen[:max(CROPS * 3, CROPS)], key=lambda s: s[0])
    pick = [pick[round(i * (len(pick) - 1) / max(CROPS - 1, 1))] for i in range(min(CROPS, len(pick)))]
    folder = clip_dir(slug) / "frames" / "shirts" / t["key"].replace(":", "_").replace("#", "n")
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for i, (ts, (x0, y0, x1, y1)) in enumerate(pick, 1):
        w, h = x1 - x0, y1 - y0
        cx0, cy0 = max(0, x0 - PAD_X * w), max(0, y0 - PAD_Y * h)
        cw, ch = w * (1 + 2 * PAD_X), h * (1 + 2 * PAD_Y)
        path = folder / f"{i}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{ts:.3f}", "-i", str(clip_dir(slug) / "clip.mp4"),
                        "-frames:v", "1", "-vf", f"crop={cw:.0f}:{ch:.0f}:{cx0:.0f}:{cy0:.0f},"
                        f"scale=-2:{CROP_H}:flags=lanczos", str(path)], check=True)
        out.append(path)
    return out


def read(client, guard, slug: str, t: dict, paths: list[Path]) -> dict:
    from google.genai import types

    clip = CLIPS[slug]
    guard.check(clip["match_id"])
    kit = f"{clip[t['team']]} player"
    parts = []
    for i, pth in enumerate(paths, 1):
        parts += [f"crop {i}:", types.Part(inline_data=types.Blob(data=pth.read_bytes(), mime_type="image/png"))]
    config = types.GenerateContentConfig(response_mime_type="application/json", response_json_schema=SCHEMA,
                                         temperature=0, thinking_config=types.ThinkingConfig(thinking_budget=0),
                                         max_output_tokens=1500)
    t0 = time.perf_counter()
    resp = client.models.generate_content(model=MODEL, config=config,
                                          contents=[*parts, PROMPT.format(n=len(paths), kit=kit)])
    latency = int((time.perf_counter() - t0) * 1000)
    u = resp.usage_metadata
    tin, tout = int(u.prompt_token_count or 0), int(u.candidates_token_count or 0) + int(u.thoughts_token_count or 0)
    row = guard.record("footage_shirts", MODEL, tin, tout, clip["match_id"], "precompute")
    try:
        reads = json.loads(resp.text or "{}").get("reads", [])
    except json.JSONDecodeError:
        reads = []
    return {"reads": reads, "tokens_in": tin, "tokens_out": tout, "cost_usd": row["cost_usd"], "latency_ms": latency}


def vote(reads: list[dict]) -> dict:
    nums = [r["number"] for r in reads if isinstance(r.get("number"), int)]
    if not nums:
        return {"number": None, "consistent": False, "why": "no crop shows a number"}
    (top, k), *rest = Counter(nums).most_common()
    others = max((c for _, c in rest), default=0)
    ok = k >= MIN_AGREE and k >= 2 * len(nums) / 3 and others <= 1
    return {"number": top if ok else None, "consistent": ok, "agree": k, "with_number": len(nums),
            "crops": len(reads), "counts": dict(Counter(nums)),
            "why": None if ok else f"{top} read {k} of {len(nums)} times, another number {others} times"}


def run(slug: str, dry_run: bool = False) -> dict:
    out_path = clip_dir(slug) / "shirts.json"
    done = json.loads(out_path.read_text())["players"] if out_path.exists() else {}
    todo = [t for t in targets(slug) if t["key"] not in done]
    if dry_run:
        return {"slug": slug, "todo": [t["key"] for t in todo], "done": list(done)}
    from api.spend import SpendGuard
    from footage.tag import sdk_client

    guard, client = SpendGuard(), sdk_client()
    for t in todo:
        paths = crops(slug, t)
        r = read(client, guard, slug, t, paths)
        v = vote(r["reads"])
        sq = squad(slug, t["team"])
        name = sq["numbers"].get(str(v["number"])) if v["number"] is not None else None
        done[t["key"]] = {**{k: t[k] for k in ("team", "label", "name_now", "tracks", "track_id", "at_s")},
                          "reads": r["reads"], **v, "name": name,
                          "squad": {"club": sq["club"], "season": sq["season"], "source": sq["source"],
                                    "retrieved": sq["retrieved"]},
                          "model": MODEL, "cost_usd": r["cost_usd"], "latency_ms": r["latency_ms"],
                          "crops_dir": str(paths[0].parent.relative_to(clip_dir(slug))) if paths else None}
        print(f"{slug} {t['key']}: {v['counts'] if v.get('counts') else '-'} -> {v['number']} {name} "
              f"(${r['cost_usd']:.4f})")
        out_path.write_text(json.dumps({"slug": slug, "rule": f"a number needs {MIN_AGREE}+ agreeing crops of "
                                        f"{CROPS}, two thirds of the crops with a number, and no rival read twice",
                                        "players": done}, indent=1, ensure_ascii=False) + "\n")
    return {"slug": slug, "players": len(done), "named": sum(1 for p in done.values() if p.get("name"))}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slugs", nargs="*")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    for slug in args.slugs or list(CLIPS):
        print(json.dumps(run(slug, args.dry_run), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "packages"))
    raise SystemExit(main())
