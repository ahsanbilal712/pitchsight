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
   this one);
4. shirt: a shirt number read consistently off several 1080p crops (footage.shirts) and found in the club's squad
   list for the season; one number per team per moment (the stronger read keeps it), never against a hand label.
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
CHAPTER_GOAL = re.compile(r"^(\d{1,2}):(\d{2})\s*[—–-]\s*(\d+)-(\d+)\s+(.+?)\s*$")   # "00:58 — 0-1 Mbappé"
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
    for side in ("home", "away"):          # the clubs' squad lists (footage.shirts), where the season has one
        y = slug.rsplit("-", 1)[1]
        sq = ROOT / "data" / "footage" / "squads" / f"{CLIPS[slug][f'{side}_id']}_20{y[:2]}-{y[2:]}.json"
        if sq.exists():
            out |= set(json.loads(sq.read_text())["numbers"].values())
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
        c = CHAPTER_GOAL.match(line.strip())
        if c:                              # a chapter line: clip time, score after the goal, scorer
            goals.append({"clip_s": int(c.group(1)) * 60 + int(c.group(2)), "score": [int(c.group(3)), int(c.group(4))],
                          "scorer": c.group(5), "own_goal": False, "minute": None})
            continue
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
        add(g["scorer"], None, {"kind": "description", "ref": f"description.json goal {g['minute']}'" if g.get("minute")
            else f"description.json chapter {g['clip_s'] // 60:02d}:{g['clip_s'] % 60:02d} ({g['score'][0]}-{g['score'][1]})"})
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

    # 4. shirt numbers read off the frames (footage.shirts) and mapped to the season's squad list
    shirts_path = clip_dir(slug) / "shirts.json"
    shirts = json.loads(shirts_path.read_text())["players"] if shirts_path.exists() else {}
    best: dict[tuple, tuple] = {}                  # (moment, team, number) -> the strongest read of that number
    for key, r in shirts.items():
        if r.get("name"):
            at = key.split(":", 1)[0]
            k = (at, r["team"], r["number"])
            if k not in best or r["agree"] > shirts[best[k][0]]["agree"]:
                best[k] = (key, r)
    for key, r in shirts.items():
        if not r.get("name"):
            continue
        at, label = key.split(":", 1)
        if best[(at, r["team"], r["number"])][0] != key:
            rejected.append({"name": r["name"], "label": label, "at": at,
                             "why": f"shirt {r['number']} also read for {best[(at, r['team'], r['number'])][0]} "
                                    "(stronger read); two players cannot share it"})
            continue
        if r.get("name_now") and not _same(r["name_now"], r["name"]):
            rejected.append({"name": r["name"], "label": label, "at": at,
                             "why": f"shirt read disagrees with the hand label {r['name_now']}"})
            continue
        if at.startswith("live"):          # a v6 live passage: the track, only inside its window
            link = {"live": f"live_{at[4:]}.json", "label": label.split("@")[0], "track_id": r.get("track_id"),
                    "from_clip_ms": round(r["window_s"][0] * 1000), "to_clip_ms": round(r["window_s"][1] * 1000)}
        elif at[:2] in ("e_", "s_"):       # a tagged shot, or a reviewed strike (strikes.json)
            link = {"event": at, "label": label, "clip_ms": round(r["at_s"] * 1000)}
        else:
            link = {"clip_ms": int(at), "label": label, "track_id": r.get("track_id")}
        again = f", confirmed by {r['confirm']['model']}" if r.get("confirm") else ""
        add(r["name"], r["team"], {"kind": "shirt", "ref": f"shirts.json {key}: #{r['number']} in {r['agree']} of "
                                   f"{r['crops']} crops{again}; squad {r['squad']['source']}"}, link)

    shots = shot_names(slug, names)
    ok = {n for n in names}
    rejected = [r for r in rejected if "label" in r or "event" in r or not any(_same(r["name"], n) for n in ok)] + \
               [{"name": n, "why": "tagger only"} for n in sorted(candidates(slug))
                if not any(_same(n, k) for k in ok) and not any(r["name"] == n for r in rejected)]
    doc = {"slug": slug, "names": dict(sorted(names.items())), "shots": shots, "rejected": rejected,
           "rule": "a name reaches the screen only with a hand, description, score_bug or shirt source (footage.names)"}
    (clip_dir(slug) / "names_verified.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    return doc


def shot_names(slug: str, names: dict[str, dict]) -> dict[str, dict]:
    """Who took each tagged shot, only where that shot is verified: a goal the score bug confirms for the tagger's
    scorer (a score_bug link to this event), or a hand-marked frame whose named holder shoots (moments/hand, the
    real action "shoot") within 3 s before the tagged shot. A verified player is not enough: the attribution of
    this shot has to be. Else the name is None and the shot is shown without one."""
    hand = []
    for path in sorted((clip_dir(slug) / "moments" / "hand").glob("*.json")):
        m = json.loads(path.read_text())
        holder = next((p for p in m["players"] if p.get("label") == m["ball"].get("holder")), None)
        if holder and holder.get("name") and (m.get("actual") or {}).get("kind") == "shoot":
            hand.append((int(path.stem), holder["name"], path.name))
    out = {}
    for e in _events(slug):
        a = e.get("attrs") or {}
        if e["type"] != "shot":
            continue
        name, source = None, None
        for n, entry in names.items():
            if any(lk.get("event") and abs(lk["clip_ms"] - a["clip_ms"]) <= 2000 for lk in entry["links"]) \
                    and any(s["kind"] == "score_bug" for s in entry["sources"]) and a.get("player_name") \
                    and _same(a["player_name"], n):
                name, source = n, "score_bug goal"
        for ms, n, f in hand:
            if name is None and 0 <= a["clip_ms"] - ms <= 3000 and a.get("player_name") and \
                    _same(a["player_name"], n):
                name, source = n, f"moments/hand/{f} (holder shoots)"
        if name is None:                       # a shirt number read at the strike
            for n, entry in names.items():
                if any(lk.get("event") == e["id"] for lk in entry["links"]) and \
                        any(src["kind"] == "shirt" for src in entry["sources"]):
                    name, source = n, next(src["ref"] for src in entry["sources"] if src["kind"] == "shirt"
                                           and e["id"] in src["ref"])
        out[e["id"]] = {"clip_ms": a["clip_ms"], "tagger_name": a.get("player_name"), "name": name,
                        "source": source}
    return out or strike_names(slug, names)


def strike_names(slug: str, names: dict[str, dict]) -> dict[str, dict]:
    """A clip without tagged events: who took each of track A's reviewed strikes (strikes.json). A goal is the
    description's scorer for the score the score bug next shows changed for that team; any other strike is named
    only by a consistent shirt read at the strike (footage.shirts). Else None."""
    path = clip_dir(slug) / "strikes.json"
    if not path.exists():
        return {}
    bug_path = clip_dir(slug) / "score_bug.json"
    bug = json.loads(bug_path.read_text())["readings"] if bug_path.exists() else []
    goals = description(slug).get("goals", [])
    out = {}
    doc = json.loads(path.read_text())
    for st in doc.get("result", doc)["strikes"]:
        name, source = None, None
        if st.get("goal"):
            r = next((r for r in sorted(bug, key=lambda r: r["clip_ms"])
                      if r["clip_ms"] >= st["clip_ms"] and r.get("changed")), None)
            g = next((g for g in goals if r and g["score"] == r["after"]), None)
            if r and g and r["changed"] == st["team"]:
                n = next((k for k in names if _same(k, g["scorer"])), g["scorer"])
                name, source = n, (f"score_bug.json {r['clip_ms']} ({r['after'][0]}-{r['after'][1]}, "
                                   f"{r['changed']}) + description.json chapter {g['clip_s'] // 60:02d}:"
                                   f"{g['clip_s'] % 60:02d}")
        else:
            for n, entry in names.items():
                if any(lk.get("event") == st["id"] for lk in entry["links"]):
                    name, source = n, next(src["ref"] for src in entry["sources"]
                                           if src["kind"] == "shirt" and st["id"] in src["ref"])
        out[st["id"]] = {"clip_ms": st["clip_ms"], "team": st["team"], "tagger_name": None, "name": name,
                         "source": source}
    return out


PARTICLES = {"mac", "van", "von", "de", "der", "den", "di", "da", "dos", "le", "la", "el", "al", "ter"}


def short(name: str) -> str:
    """The name as a caption shows it: the surname with its particle ("Mac Allister", "van de Ven", "Mbeumo")."""
    words = name.split()
    i = len(words) - 1
    while i > 0 and words[i - 1].lower() in PARTICLES:
        i -= 1
    return " ".join(words[i:])


def name_at(slug: str, m: dict, label: str) -> str | None:
    """The verified name of a moment-file player: his own (hand) name, a name verified for that label at that
    moment, or a live-passage shirt read of the same track in the same camera shot whose window covers the
    moment. None means no label on screen."""
    p = next((q for q in m["players"] if q.get("label") == label), None)
    if p is None:
        return None
    ok = verified(slug)
    if p.get("name") and any(_same(p["name"], k) for k in ok):
        return p["name"]
    shot = (m.get("homography") or {}).get("source", "").split(" ")[0].replace("calib/", "tracks/")
    for n, e in ok.items():
        for lk in e["links"]:
            if lk.get("clip_ms") == m.get("clip_ms") and lk.get("label") == label:
                return n
            if lk.get("live") and lk.get("track_id") == p.get("track_id") and \
                    lk["from_clip_ms"] <= m.get("clip_ms", -1) <= lk["to_clip_ms"]:
                live = clip_dir(slug) / "cache" / "v6" / lk["live"]
                if live.exists() and json.loads(live.read_text())["result"]["source"]["tracks"].endswith(shot):
                    return n
    return None


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
