"""A pure-analytics cut of one match, generated from track A's indices (no intro, captions or cards).

    python packages/demo/match_cut.py <slug> <name> [--min-run 2.0]

Writes packages/demo/out/<name>_moments.yaml (the beats) and packages/demo/out/edit_<name>.yaml (the cut), both
git-ignored. The cut is the match's own footage in clip order, only where the layers cover it:
- every always-on run (track A cache/v7 always_index_0, >= 90% always-on) as an `always_on` beat (the v7 layer under
  v6's ball layer, the v8 look), split around each strike inside it;
- each strike (cache/v5 shots_0) as a `shot_xg` beat from the strike to its outcome (the cone, the strike xG, a tag);
everything else (replays, close-ups, celebrations) is cut. Kit colours and short names come from track A's tracks
(kit_rgb, short) matched to home/away through the live frames' track ids; names only from track B's names_live.
Render the beats with PITCHSIGHT_MOMENTS=<moments file> python -m demo.composite <beat>, then assemble the edit.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
FOOTAGE = ROOT / "data" / "footage"
OUT = ROOT / "packages" / "demo" / "out"
PRE_S = 0.3                    # always_on beats start this long before t0 (the edit cuts it off)
SHOT_TAIL_S = 1.4              # a shot beat runs this long past its outcome stamp


def _load(path: Path) -> dict:
    doc = json.loads(path.read_text())
    return doc.get("result", doc)


def teams(slug: str, live: dict) -> tuple[dict, dict]:
    """(kits, shorts) by home/away: track A's per-shot team colours and short names, matched to the live frames'
    home/away labels through shared track ids (a majority vote)."""
    tracks = _load(FOOTAGE / slug / "tracks" / f"{live['shot_id']}.json")
    by_id = {}
    for f in tracks["frames"]:
        for p in f.get("players") or []:
            if p.get("team") is not None:
                by_id.setdefault(p["track_id"], Counter())[str(p["team"])] += 1
    votes = {"home": Counter(), "away": Counter()}
    for f in live["frames"]:
        for p in f.get("players") or []:
            if p.get("team") in votes and p.get("track_id") in by_id:
                votes[p["team"]].update(by_id[p["track_id"]])
    kits, shorts = {}, {}
    for side, c in votes.items():
        if c:
            t = tracks["teams"][c.most_common(1)[0][0]]
            kits[side], shorts[f"{side}_short"] = list(t["kit_rgb"]), t["short"]
    return kits, shorts


def build(slug: str, name: str, min_run: float = 2.0) -> tuple[Path, Path]:
    cache = FOOTAGE / slug / "cache"
    index = _load(cache / "v7" / "always_index_0.json")
    shots_path = cache / "v5" / "shots_0.json"
    shots = _load(shots_path)["shots"] if shots_path.exists() else []
    shots = [s for s in shots if s.get("xg") is not None]     # an unmeasured shot would show bare footage: cut
    names = cache / "v6" / "names_live_0.json"
    race = cache / "v6" / "xg_running_0.json"
    rel = lambda p: str(p.relative_to(ROOT))                                    # noqa: E731
    moments, segs = {}, []
    for entry in index["shots"]:
        if not entry.get("runs"):
            continue
        always = cache / entry["path"]
        live_path = cache / "v6" / Path(entry["path"]).name.replace("always_", "live_")
        live = _load(live_path)
        kits, shorts = teams(slug, live)
        base = {"clip": slug, "kind": "always_on", "data": rel(live_path), "always": rel(always),
                "shot_id": entry["shot_id"], "team": "home", "kits": kits, "theme": "v8"}
        if names.exists():
            base["names_live"] = rel(names)
        if race.exists() and shorts:
            base["race"], base["race_labels"] = rel(race), shorts
        for r in entry["runs"]:
            a, b = r["start_clip_ms"] / 1000, r["end_clip_ms"] / 1000
            cuts = sorted(s["clip_ms"] / 1000 for s in shots if a < s["clip_ms"] / 1000 < b)
            edges = [a, *cuts, b]
            for x0, x1 in zip(edges[:-1], edges[1:], strict=True):
                if x0 in cuts:                                  # after a strike: from the end of its shot beat
                    x0 = next((x0 + _outcome(s) + SHOT_TAIL_S for s in shots if s["clip_ms"] / 1000 == x0), x0)
                if x1 - x0 >= min_run:
                    segs.append((x0, x1, {**base, "t0": round(x0, 2), "t1": round(x1, 2)}))
    cams = json.loads((FOOTAGE / slug / "shots.json").read_text())["shots"]
    nv = FOOTAGE / slug / "names_verified.json"                 # track B's verified shooters, by strike time
    shooters = list((_load(nv).get("shots") or {}).values()) if nv.exists() else []
    for s in shots:                                             # every strike, in or out of a run
        t = s["clip_ms"] / 1000
        cam_end = next((c["end"] for c in cams if c["start"] <= t <= c["end"]), t + 9)   # never past the cut
        team = s.get("team") or "home"
        kits = next((m["kits"] for *_, m in segs if m.get("kits")), {})
        segs.append((t - 0.15, min(t + _outcome(s) + SHOT_TAIL_S, cam_end - 0.05),
                     {"clip": slug, "kind": "shot_xg", "data": rel(shots_path), "clip_ms": s["clip_ms"], "team": team,
                      "kits": kits, "style": "v6", "pre_s": 0.4, "post_s": SHOT_TAIL_S,
                      **({"shooter_name": v["name"]} if (v := next((v for v in shooters if v.get("name") and abs(
                          v["clip_ms"] - s["clip_ms"]) <= 100), None)) else {})}))
    segs.sort(key=lambda x: x[0])
    clips, last_end = [], -1.0
    for k, (x0, x1, m) in enumerate(segs):
        if x0 < last_end - 0.05:                                # never show a second twice
            x0 = last_end
            if x1 - x0 < min_run and m["kind"] == "always_on":
                continue
            if m["kind"] == "always_on":
                m = {**m, "t0": round(x0, 2)}
        beat = f"{name}_{k:03d}_{'shot' if m['kind'] == 'shot_xg' else 'live'}"
        moments[beat] = m
        if m["kind"] == "always_on":
            clips.append({"shot": f"footage/{beat}", "from": PRE_S, "to": round(PRE_S + m["t1"] - m["t0"], 2)})
        else:
            pre = float(m["pre_s"])
            clips.append({"shot": f"footage/{beat}", "from": round(pre + (x0 - (m["clip_ms"] / 1000 - 0.15)) - 0.15, 2),
                          "to": round(pre + x1 - m["clip_ms"] / 1000, 2)})
        last_end = x1
    OUT.mkdir(parents=True, exist_ok=True)
    mpath = OUT / f"{name}_moments.yaml"
    mpath.write_text(yaml.safe_dump({"moments": moments}, sort_keys=False, width=200))
    edit = {"out": rel(OUT / f"{name}.mp4"), "size": [1920, 1080], "fps": 30, "caption_band": 0,
            "watermark": "PITCHSIGHT", "moments": rel(mpath), "version": "v8",
            "grounding_out": rel(OUT / f"{name}_grounding.json"), "clips": clips, "sources": {}}
    epath = OUT / f"edit_{name}.yaml"
    epath.write_text("# Generated by demo.match_cut: the match's own footage, analytics on every frame, no captions.\n"
                     + yaml.safe_dump(edit, sort_keys=False, width=200))
    return mpath, epath


def _outcome(s: dict) -> float:
    return (s["outcome_clip_ms"] - s["clip_ms"]) / 1000 if s.get("outcome_clip_ms") else 0.6


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("slug")
    ap.add_argument("name")
    ap.add_argument("--min-run", type=float, default=2.0)
    args = ap.parse_args()
    mpath, epath = build(args.slug, args.name, args.min_run)
    beats = yaml.safe_load(mpath.read_text())["moments"]
    edit = yaml.safe_load(epath.read_text())
    total = sum(c["to"] - c["from"] for c in edit["clips"])
    print(f"{len(beats)} beats, {total:.1f} s -> {epath.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
