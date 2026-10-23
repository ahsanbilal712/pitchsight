"""Verified player names for the real clips (video v4): a name reaches the screen only when a source we can show
backs it. Never a guess.

    python -m footage.names        # -> data/footage/<slug>/names_verified.json for every clip

Sources, strongest first:
1. hand: a moment file's hand label (moments/hand/*.json, read off the 1080p frame), linked to its track where the
   tracked moment file (moments/<clip_ms>.json) matched it;
2. description: the clip's published description (frozen in description.json: goal lines with minute, score and
   scorer, and every candidate name it mentions);
3. score_bug: a goal the tagger (Gemini) names, where the score bug (score_bug.json, read by hand) changes for that
   team at that time, and no description goal line contradicts it (a description that lists the goals must list
   this one).
A Gemini name with none of these stays unverified and is listed under `rejected` with the reason. Names in moment
files outside moments/hand/ (set by a beat from one of the sources above) count only through that source.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata

from footage.clips import CLIPS, ROOT, clip_dir

GOAL_LINE = re.compile(r"\|\s*(\d+)(?:\+\d+)?'\s*(.+?)\s*$")
SCORE = re.compile(r"(\d+)\s*-\s*(\d+)\s*[^|]*\|")


def fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


def surname(name: str) -> str:
    return fold(name).replace("-", " ").split()[-1]


def _events(slug: str) -> list[dict]:
    path = clip_dir(slug) / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def candidates(slug: str) -> set[str]:
    """Every player name any source offers for the clip (verified or not): the detector's vocabulary."""
    out = {e["attrs"]["player_name"] for e in _events(slug) if (e.get("attrs") or {}).get("player_name")}
    for path in (clip_dir(slug) / "moments").glob("**/*.json"):
        if path.stem.isdigit():
            out |= {p["name"] for p in json.loads(path.read_text())["players"] if p.get("name")}
    return out


def description(slug: str) -> dict:
    """Facts from the published description, frozen in description.json (clip.info.json is git-ignored: it carries
    signed stream URLs). Only the title, the goal lines and the names it mentions are kept."""
    frozen = clip_dir(slug) / "description.json"
    info = clip_dir(slug) / "clip.info.json"
    if not info.exists():
        return json.loads(frozen.read_text()) if frozen.exists() else {"goals": [], "mentions": []}
    d = json.loads(info.read_text())
    text = d.get("description") or ""
    goals = []
    for line in text.splitlines():
        m, s = GOAL_LINE.search(line), SCORE.search(line)
        if m and s:
            scorer = m.group(2)
            goals.append({"minute": int(m.group(1)), "score": [int(s.group(1)), int(s.group(2))],
                          "scorer": re.sub(r"\s+OG$", "", scorer), "own_goal": scorer.endswith(" OG")})
    body = fold(d.get("title", "") + "\n" + text)
    mentions = sorted({n for n in candidates(slug) | {g["scorer"] for g in goals}
                       if re.search(rf"\b{re.escape(surname(n))}\b", body)})
    doc = {"slug": slug, "title": d.get("title"), "source": d.get("webpage_url"), "goals": goals,
           "mentions": mentions}
    frozen.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    return doc


def _same(a: str, b: str) -> bool:
    return surname(a) == surname(b) or fold(a) in fold(b) or fold(b) in fold(a)


def verify(slug: str) -> dict:
    names: dict[str, dict] = {}

    def add(name: str, team: str | None, source: dict, link: dict | None = None) -> None:
        key = next((k for k in names if _same(k, name) and names[k]["team"] in (team, None)), name)
        if key != name and len(name) > len(key):            # keep the fuller form ("Mohamed Salah" over "Salah")
            names[name] = names.pop(key)
            key = name
        e = names.setdefault(key, {"team": team, "sources": [], "links": []})
        e["team"] = e["team"] or team
        if source not in e["sources"]:
            e["sources"].append(source)
        if link and link not in e["links"]:
            e["links"].append(link)

    # 1. hand labels, linked to the tracked moment file's track id
    for path in sorted((clip_dir(slug) / "moments" / "hand").glob("*.json")):
        tracked_path = clip_dir(slug) / "moments" / path.name
        tracked = json.loads(tracked_path.read_text())["players"] if tracked_path.exists() else []
        for p in json.loads(path.read_text())["players"]:
            if not p.get("name"):
                continue
            t = next((q.get("track_id") for q in tracked if q.get("label") == p["label"] and q["team"] == p["team"]),
                     None)
            add(p["name"], p["team"], {"kind": "hand", "ref": f"moments/hand/{path.name}"},
                {"clip_ms": int(path.stem), "label": p["label"], "track_id": t})

    # 2. the description
    desc = description(slug)
    clip = CLIPS[slug]
    team_of = {fold(clip["home"]): "home", fold(clip["away"]): "away"}
    for g in desc.get("goals", []):
        add(g["scorer"], None, {"kind": "description", "ref": f"description.json goal {g['minute']}'"})
    for n in desc.get("mentions", []):
        add(n, None, {"kind": "description", "ref": "description.json mention"})

    # 3. tagger goals confirmed by the score bug
    bug_path = clip_dir(slug) / "score_bug.json"
    bug = json.loads(bug_path.read_text())["readings"] if bug_path.exists() else []
    rejected = []
    listed = [g["scorer"] for g in desc.get("goals", [])]
    for e in _events(slug):
        a = e.get("attrs") or {}
        if not (e["type"] == "goal" or e.get("outcome") == "goal") or not a.get("player_name"):
            continue
        r = next((r for r in bug if abs(r["clip_ms"] - a["clip_ms"]) <= 30_000), None)
        team = e["team"] if e["team"] in ("home", "away") else team_of.get(fold(a.get("team_name") or ""))
        why = None
        if r is None:
            why = "no score-bug reading"
        elif r["changed"] is None:
            why = f"score bug unchanged at {r['clip_ms']} ms ({r['before'][0]}-{r['before'][1]})"
        elif r["changed"] != team:
            why = f"score bug changed for {r['changed']}, tagger says {team}"
        elif listed and not any(_same(a["player_name"], s) for s in listed):
            why = "the description lists the goals and not this one"
        if why:
            if not any(r["name"] == a["player_name"] and r["why"] == why for r in rejected):
                rejected.append({"name": a["player_name"], "event": e["id"], "clip_ms": a["clip_ms"], "why": why})
            continue
        add(a["player_name"], team, {"kind": "score_bug", "ref": f"score_bug.json {r['clip_ms']} + {e['id']}"},
            {"clip_ms": a["clip_ms"], "event": e["id"]})

    ok = {n for n in names}
    rejected = [r for r in rejected if not any(_same(r["name"], n) for n in ok)] + \
               [{"name": n, "why": "tagger only"} for n in sorted(candidates(slug))
                if not any(_same(n, k) for k in ok) and not any(r["name"] == n for r in rejected)]
    doc = {"slug": slug, "names": dict(sorted(names.items())), "rejected": rejected,
           "rule": "a name reaches the screen only with a hand, description or score_bug source (footage.names)"}
    (clip_dir(slug) / "names_verified.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    return doc


def verified(slug: str) -> dict[str, dict]:
    path = clip_dir(slug) / "names_verified.json"
    return json.loads(path.read_text())["names"] if path.exists() else verify(slug)["names"]


def unverified_in(slug: str, text: str) -> list[str]:
    """Player names in `text` (any name a source offers for this clip, by surname) that are not verified."""
    ok = verified(slug)
    body = fold(text)
    return sorted({n for n in candidates(slug) if re.search(rf"\b{re.escape(surname(n))}\b", body)
                   and not any(_same(n, k) for k in ok)})


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "packages"))
    for s in CLIPS:
        d = verify(s)
        print(s, "verified:", ", ".join(f"{n} ({'+'.join(sorted({x['kind'] for x in e['sources']}))})"
                                        for n, e in d["names"].items()))
        for r in d["rejected"]:
            print("   rejected:", r["name"], "-", r["why"])
