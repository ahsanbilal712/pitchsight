"""Shirt numbers read off the 1080p broadcast, mapped to the club's published squad list (video v6: no placeholders).

    python -m footage.shirts [<slug>...] [--dry-run]    # -> data/footage/<slug>/shirts.json

For every player the videos label (the featured freezes' players in view, and the montage shooters without a
verified name), CROPS crops of his tracked box are taken within WINDOW_S of the moment the label applies to (the
freeze, or the strike: a track can switch to another player later in the shot) (tracks/<shot>.json, 1080p frames;
crops stay in the git-ignored frames/ folder) and read in one inline call to gemini-3.8-flash (SpendGuard, the clip's
match id). A number is accepted only when it is consistent: at least MIN_AGREE crops read it, it is at least two
thirds of the crops that show a number, and no other number is read more than once. The number is mapped to the
team's squad list for that season (data/footage/squads/<club>_<season>.json, with its source); a number that is not
in the list gives no name. A number that would give a name is read a second time, on the same crops, by CONFIRM
(gemini-4-argon), and needs the same consistent number there: a small, blurred digit can be misread consistently
(Barcelona v Real Madrid, a white #17 read "12" in 7 of 8 crops). footage.names reads shirts.json as the "shirt"
source.

    python -m footage.shirts <slug> --recheck           # the rules again on the reads already made (no new Flash call)
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
CONFIRM = "gemini-4-argon"         # the second read of a number that would name a player
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
                            "label": s["shooter"]["label"], "name_now": None,
                            "tracks": pos.split("/", 1)[1].split(" ")[0],       # "tracks/7.json frame 1164"
                            "track_id": int(s["shooter"]["label"][1:]), "at_s": s["clip_ms"] / 1000})
    return out


PASSAGES = {                       # track C's v6 live passages (clip ms)
    "manutd-mancity-2526": [(873000, 880000), (1075000, 1079400), (1409500, 1415000)], "liverpool-mancity-2526": [(867000, 875600)],
    "arsenal-chelsea-2526": [(829000, 836000)], "manutd-spurs-2425": [(679800, 683400)]}


REQUESTED = {                      # (camera shot, track, team the tracking gives, from ms, to ms): windows asked for by name
    "arsenal-chelsea-2526": [(109, 18, "away", 834400, 835600),       # track A v9: Palmer's cutback receiver
                             (177, 39, "home", 1299500, 1301100),     # track A v9: Eze's square option
                             (177, 20, "away", 1298200, 1298600)]}    # track A v9: who cut out Saka's pass (kit check)


def requested_targets(slug: str) -> list[dict]:
    """REQUESTED windows as live targets, keyed to the live file of the same camera shot that covers them."""
    out = []
    for shot, track, team, a, b in REQUESTED.get(slug, []):
        for path in sorted((clip_dir(slug) / "cache" / "v6").glob("live_[0-9]*.json")):
            r = json.loads(path.read_text())["result"]
            if str(r["shot_id"]) == str(shot) and r["start_clip_ms"] <= a and r["end_clip_ms"] >= b:
                out.append({"key": f"live{r['start_clip_ms']}:t{track}@{a}-{b}", "team": team, "label": f"t{track}",
                            "name_now": None, "tracks": r["source"]["tracks"].split("/", 1)[1], "track_id": track,
                            "window_s": [a / 1000, b / 1000], "at_s": (a + b) / 2000, "live": path.name,
                            "shot_id": r["shot_id"], "keeper": False})
    return out


def passages_from_edit(edit: Path) -> dict[str, list[tuple[int, int]]]:
    """The live passages an edit shows (its always_on / live_hud beats' t0-t1), by clip: a local-only cut keeps
    them in its own beats file, so they are read from the edit (footage.grounding._v6_beats)."""
    from footage.grounding import _v6_beats

    out: dict[str, list[tuple[int, int]]] = {}
    for b in _v6_beats(Path(edit)).values():
        if b.get("kind") in ("always_on", "live_hud") and b.get("clip") and b.get("t0") is not None:
            out.setdefault(b["clip"], []).append((round(b["t0"] * 1000), round(b["t1"] * 1000)))
    return out


def live_targets(slug: str) -> list[dict]:
    """Every track that carries the ball or is a pass option inside a v6 live passage (track A's live files)."""
    out = []
    for a, b in PASSAGES.get(slug, []):
        for path in sorted((clip_dir(slug) / "cache" / "v6").glob("live_[0-9]*.json")):
            r = json.loads(path.read_text())["result"]
            if r["start_clip_ms"] > b or r["end_clip_ms"] < a:
                continue
            when: dict[str, list[int]] = {}
            team: dict[str, str] = {}
            keeper: dict[str, bool] = {}
            for fr in r["frames"]:
                if not a <= fr["clip_ms"] <= b:
                    continue
                for p in fr.get("players") or []:
                    if p.get("team"):
                        team.setdefault(p["label"], p["team"])
                        keeper[p["label"]] = keeper.get(p["label"], False) or bool(p.get("keeper"))
                for who in [fr.get("holder")] + list(fr.get("options") or []):
                    if who and who["label"].startswith("t"):
                        when.setdefault(who["label"], []).append(fr["clip_ms"])
            for label, ts in when.items():
                if label in team:
                    out.append({"key": f"live{r['start_clip_ms']}:{label}@{min(ts)}-{max(ts)}", "team": team[label],
                                "label": label, "name_now": None, "tracks": r["source"]["tracks"].split("/", 1)[1],
                                "track_id": int(label[1:]), "window_s": [min(ts) / 1000, max(ts) / 1000],
                                "at_s": (min(ts) + max(ts)) / 2000, "live": path.name, "shot_id": r["shot_id"],
                                "keeper": keeper.get(label, False)})
    return out


def names_live(slug: str) -> dict:
    """For track A's live data: verified shirt and name per (camera shot, track, time window); one number per team
    per passage (the stronger read keeps it)."""
    doc = json.loads((clip_dir(slug) / "shirts.json").read_text())["players"]
    rows = [{"key": k, **r} for k, r in doc.items() if k.startswith("live")]
    best = {}
    for r in rows:
        if r.get("number") is not None:
            k = (r["key"].split(":")[0], r["team"], r["number"])
            if k not in best or r["agree"] > best[k]["agree"]:
                best[k] = r
    out = []
    for r in rows:
        owner = r.get("number") is not None and best[(r["key"].split(":")[0], r["team"], r["number"])] is r
        out.append({"live": f"live_{r['key'][4:].split(':')[0]}.json", "tracks": r["tracks"], "track_id": r["track_id"],
                    "label": r["label"], "team": r["team"], "from_clip_ms": round(r["window_s"][0] * 1000),
                    "to_clip_ms": round(r["window_s"][1] * 1000), "shirt": r["number"] if owner else None,
                    "name": r["name"] if owner else None, "agree": r.get("agree"), "crops": r.get("crops"),
                    "why_not": None if owner else (r.get("why") or "number owned by a stronger read"),
                    "squad": r["squad"]})
    out += hand_windows(slug, doc)
    res = {"beat": "names_live", "slug": slug, "rule": "shirt read on 8 crops spread over the window, 3+ agreeing, "
           "kit colour on the track's team, number in the season's squad list; or a hand label at a freeze, "
           f"+-{WINDOW_S[0]} s around it, when no read of that track over the window gives another number "
           "(source); null = no label", "players": out}
    from footage.pipeline import register

    register(slug, "v6/names_live_0.json", "names_live_0",
             {"$schema": "model_cache.schema.json", "schema_version": "1.0.0", "record": "tool_result", "result": res})
    return res


def hand_windows(slug: str, doc: dict) -> list[dict]:
    """A freeze's hand-labelled player (moments/hand, named) on his track, +-WINDOW_S[0] around the freeze, for the
    live file of the same camera shot: only when every shirt read of that track whose window overlaps reads his own
    number or none (a track that reads another number may have switched), and his own freeze read does not
    disagree."""
    from footage.clips import load_config

    out = []
    for f in load_config()["featured"]:
        if f["slug"] != slug:
            continue
        hand = clip_dir(slug) / "moments" / "hand" / f"{f['clip_ms']}.json"
        if not hand.exists():
            continue
        m = json.loads((clip_dir(slug) / "moments" / f"{f['clip_ms']}.json").read_text())
        tracks = "tracks/" + m["homography"]["source"].split("/")[1].split(" ")[0]
        a, b = f["clip_ms"] / 1000 - WINDOW_S[0], f["clip_ms"] / 1000 + WINDOW_S[0]
        for h in json.loads(hand.read_text())["players"]:
            p = next((q for q in m["players"] if q.get("label") == h.get("label") and q["team"] == h["team"]), None)
            if not h.get("name") or not p or p.get("track_id") is None or p.get("slot") == "GK":
                continue
            own = int(h["label"][1:]) if h["label"].startswith("#") else None
            reads = [r for r in doc.values() if r.get("track_id") == p["track_id"] and r.get("tracks") == tracks and
                     ((r.get("window_s") or [r["at_s"] - WINDOW_S[0], r["at_s"] + WINDOW_S[0]])[0] <= b) and
                     ((r.get("window_s") or [r["at_s"] - WINDOW_S[0], r["at_s"] + WINDOW_S[0]])[1] >= a)]
            if any(isinstance(x.get("number"), int) and x["number"] != own for r in reads for x in r["reads"]):
                continue                        # a crop of this track shows another number: it may have switched
            for path in sorted((clip_dir(slug) / "cache" / "v6").glob("live_[0-9]*.json")):
                live = json.loads(path.read_text())["result"]
                if live["source"]["tracks"].endswith(tracks) and live["start_clip_ms"] <= b * 1000 and \
                        live["end_clip_ms"] >= a * 1000:
                    out.append({"live": path.name, "tracks": tracks, "track_id": p["track_id"],
                                "label": f"t{p['track_id']}", "team": p["team"], "from_clip_ms": round(a * 1000),
                                "to_clip_ms": round(b * 1000), "shirt": own, "name": h["name"], "agree": None,
                                "crops": None, "why_not": None, "squad": None,
                                "source": f"hand label {h['label']} in moments/hand/{f['clip_ms']}.json; no read of "
                                          f"track {p['track_id']} over the window shows another number"})
    return out


def crops(slug: str, t: dict) -> list[Path]:
    tracks = json.loads((clip_dir(slug) / t["tracks"]).read_text())
    every = [(f["t"], p["bbox"]) for f in tracks["frames"] for p in f["players"]
             if p["track_id"] == t["track_id"] and p.get("bbox")]
    if t.get("window_s"):                                       # a live passage: wherever he carries or is an option
        a, b = t["window_s"]
        if b - a < 1.0:                                         # a moment, not a span: a second around it
            a, b = (a + b) / 2 - 0.5, (a + b) / 2 + 0.5
        seen = [s for s in every if a <= s[0] <= b]
    else:
        for w in WINDOW_S:                                      # the label holds at its moment, not the whole shot
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


def read(client, guard, slug: str, t: dict, paths: list[Path], model: str = MODEL) -> dict:
    from google.genai import types

    clip = CLIPS[slug]
    guard.check(clip["match_id"])
    kit = f"{clip[t['team']]} player"
    parts = []
    for i, pth in enumerate(paths, 1):
        parts += [f"crop {i}:", types.Part(inline_data=types.Blob(data=pth.read_bytes(), mime_type="image/png"))]
    fast = {"thinking_config": types.ThinkingConfig(thinking_budget=0), "max_output_tokens": 1500} \
        if model == MODEL else {"max_output_tokens": 8000}
    config = types.GenerateContentConfig(response_mime_type="application/json", response_json_schema=SCHEMA,
                                         temperature=0, **fast)
    t0 = time.perf_counter()
    resp = client.models.generate_content(model=model, config=config,
                                          contents=[*parts, PROMPT.format(n=len(paths), kit=kit)])
    latency = int((time.perf_counter() - t0) * 1000)
    u = resp.usage_metadata
    tin, tout = int(u.prompt_token_count or 0), int(u.candidates_token_count or 0) + int(u.thoughts_token_count or 0)
    row = guard.record("footage_shirts" if model == MODEL else "footage_shirts_confirm", model, tin, tout,
                       clip["match_id"], "precompute")
    try:
        reads = json.loads(resp.text or "{}").get("reads", [])
    except json.JSONDecodeError:
        reads = []
    return {"reads": reads, "tokens_in": tin, "tokens_out": tout, "cost_usd": row["cost_usd"], "latency_ms": latency,
            "model": model}


def kit_side(slug: str, path: Path) -> str:
    """The team whose kit colour (teams.json kit_rgb) is nearest the shirt: the median of the torso band of the
    player's own box inside the padded crop, grass pixels left out (a running player's box is mostly grass, and grass
    is nearer a dark kit than a white one)."""
    import numpy as np
    from PIL import Image

    im = np.asarray(Image.open(path).convert("RGB"), float)
    h, w = im.shape[:2]
    bx, by = PAD_X / (1 + 2 * PAD_X), PAD_Y / (1 + 2 * PAD_Y)          # the box inside the padded crop
    y0, y1 = by + (1 - 2 * by) * 0.15, by + (1 - 2 * by) * 0.5
    torso = im[int(y0 * h):int(y1 * h), int((bx + 0.1) * w):int((1 - bx - 0.1) * w)].reshape(-1, 3)
    shirt = torso[~((torso[:, 1] > torso[:, 0] + 8) & (torso[:, 1] > torso[:, 2] + 8))]
    med = np.median(shirt if len(shirt) >= 0.05 * len(torso) else torso, axis=0)
    kits = [t["kit_rgb"] for t in json.loads((clip_dir(slug) / "teams.json").read_text())["teams"]]
    d = [float(np.linalg.norm(med - np.asarray(k, float))) for k in kits]
    return ("home", "away")[int(np.argmin(d))]


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


def decide(client, guard, slug: str, t: dict, reads: list[dict], kit: list[str], paths: list[Path],
           confirm: dict | None = None) -> dict:
    """The rules on one player's reads: the vote, the kit colour, a goalkeeper's number on an outfield track, then the
    second read (CONFIRM) of a number that would give a name (kept from an earlier run when it read that number)."""
    v = vote(reads)
    kit_ok = sum(k == t["team"] for k in kit) > len(kit) / 2
    if v["number"] is not None and not kit_ok:              # the track's team label and the shirt disagree
        v = {**v, "number": None, "consistent": False, "why": f"kit: {kit} for a {t['team']} label"}
    sq = squad(slug, t["team"])
    if v["number"] is not None and str(v["number"]) in sq.get("goalkeepers", []) and not t.get("keeper"):
        v = {**v, "number": None, "consistent": False, "why": f"{v['number']} is a goalkeeper's number; an "
             "outfield track"}                              # a misread or another player: no name
    if v["number"] is not None and str(v["number"]) in sq["numbers"]:
        if not confirm or confirm.get("asked") != v["number"]:
            c = read(client, guard, slug, t, paths, CONFIRM)
            confirm = {"model": CONFIRM, "asked": v["number"], "reads": c["reads"], **vote(c["reads"]),
                       "cost_usd": c["cost_usd"]}
            print(f"  {CONFIRM}: {confirm.get('counts') or '-'} -> {confirm['number']} (${c['cost_usd']:.4f})")
        if confirm["number"] != v["number"]:
            v = {**v, "number": None, "consistent": False, "why": f"{CONFIRM} read {confirm.get('counts') or 'no '
                 'number'} on the same crops, not {v['number']}"}
    name = sq["numbers"].get(str(v["number"])) if v["number"] is not None else None
    return {**v, "name": name, "confirm": confirm, "squad": {"club": sq["club"], "season": sq["season"],
            "source": sq["source"], "retrieved": sq["retrieved"]}}


def _save(slug: str, done: dict) -> None:
    (clip_dir(slug) / "shirts.json").write_text(json.dumps(
        {"slug": slug, "rule": f"a number needs {MIN_AGREE}+ agreeing crops of {CROPS}, two thirds of the crops with "
         f"a number, no rival read twice, the kit colour of the track's team, and the same number read again by "
         f"{CONFIRM}", "players": done}, indent=1, ensure_ascii=False) + "\n")


def run(slug: str, dry_run: bool = False, recheck: bool = False) -> dict:
    out_path = clip_dir(slug) / "shirts.json"
    done = json.loads(out_path.read_text())["players"] if out_path.exists() else {}
    todo = [t for t in targets(slug) + live_targets(slug) + requested_targets(slug) if t["key"] not in done]
    if dry_run:
        return {"slug": slug, "todo": [t["key"] for t in todo], "done": list(done)}
    from api.spend import SpendGuard
    from footage.tag import sdk_client

    guard, client = SpendGuard(), sdk_client()
    if recheck:                                             # the rules again on the crops and reads already made
        for key, r in done.items():
            paths = sorted((clip_dir(slug) / r["crops_dir"]).glob("*.png"), key=lambda p: int(p.stem))
            t = {"key": key, **r}
            kit = [kit_side(slug, pth) for pth in paths]
            d = decide(client, guard, slug, t, r["reads"], kit, paths, r.get("confirm"))
            if (d["number"], d["name"]) != (r.get("number"), r.get("name")):
                print(f"{slug} {key}: {r.get('number')} {r.get('name')} -> {d['number']} {d['name']} ({d['why']})")
            done[key] = {**r, "kit": kit, **d}
            _save(slug, done)
    for t in todo:
        paths = crops(slug, t)
        r = read(client, guard, slug, t, paths)
        kit = [kit_side(slug, pth) for pth in paths]
        d = decide(client, guard, slug, t, r["reads"], kit, paths)
        done[t["key"]] = {**{k: t.get(k) for k in ("team", "label", "name_now", "tracks", "track_id", "at_s")},
                          "reads": r["reads"], "kit": kit, **d,
                          **({"window_s": t["window_s"]} if t.get("window_s") else {}),
                          "model": MODEL, "cost_usd": r["cost_usd"], "latency_ms": r["latency_ms"],
                          "crops_dir": str(paths[0].parent.relative_to(clip_dir(slug))) if paths else None}
        print(f"{slug} {t['key']}: {d['counts'] if d.get('counts') else '-'} -> {d['number']} {d['name']} "
              f"(${r['cost_usd']:.4f})")
        _save(slug, done)
    live = names_live(slug) if any(k.startswith("live") for k in done) else {"players": []}
    return {"slug": slug, "players": len(done), "named": sum(1 for p in done.values() if p.get("name")),
            "live_named": sum(1 for p in live["players"] if p["name"])}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slugs", nargs="*")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--recheck", action="store_true", help="the rules again on the reads already made")
    ap.add_argument("--edit", type=Path, help="read the live passages from this edit's beats (a local-only cut)")
    args = ap.parse_args(argv)
    if args.edit:
        for slug, spans in passages_from_edit(args.edit).items():
            PASSAGES[slug] = sorted(set(PASSAGES.get(slug, [])) | set(spans))
        args.slugs = args.slugs or list(passages_from_edit(args.edit))
    for slug in args.slugs or list(CLIPS):
        print(json.dumps(run(slug, args.dry_run, args.recheck), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "packages"))
    raise SystemExit(main())
