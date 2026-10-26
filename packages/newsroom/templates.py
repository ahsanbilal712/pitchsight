"""Deterministic narrator_template lines: built only from verified claims, so they always pass the
Fact Checker. Used when the narrator model times out or fails twice, in degraded mode, on a cache miss, and by the
Director after the third rejected attempt.
"""

from __future__ import annotations

HEADLINE_MAX, BODY_MAX = 60, 280

HEADLINES = {
    "goal": "Goal", "big_chance": "Big chance", "milestone": "Milestone", "player_tag": "One to watch",
    "sliding_doors": "Sliding Doors", "state_change": "The game changes", "tempo_shift": "Tempo shift",
    "pressing_trap": "Pressing trap", "fourth_official": "Fourth Official", "recap": "Recap",
}
UNIT_LABELS = {"xg": "Chance quality", "p_goal": "Goal chance", "win_prob": "Win chance",
               "win_prob_delta": "Win chance swing", "metres": "Distance", "kmh": "Speed", "xt": "Threat added",
               "percent": "Share", "count": "Count", "seconds": "Time", "minute": "Minute"}


def clip(text: str, limit: int) -> str:
    """Trim to `limit` characters at a sentence end if possible, else at a word boundary."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if end >= limit // 2:
        return cut[:end + 1]
    return cut[:cut.rfind(" ")].rstrip(",;:") if " " in cut else cut


def template_line(kind: str, claims: list[dict]) -> dict:
    """{headline, body, claims} from verified claims only."""
    used = [c for c in claims if c.get("verified")]
    names = [c["text"] for c in used if c.get("kind") in ("player", "team")]
    head = HEADLINES.get(kind, "Key moment")
    if names:
        head = f"{head}: {names[0]}"
    parts = []
    for c in used:
        if c.get("kind") == "number":
            parts.append(f"{UNIT_LABELS.get(c.get('unit'), 'Value')}: {c['text']}.")
        elif c.get("kind") == "tactical":
            parts.append(f"{c['text'][0].upper()}{c['text'][1:]}.")
        elif c.get("kind") == "minute":
            parts.append(f"In the {c['text']}.")
    if len(names) > 1:
        parts.insert(0, f"{' and '.join(names[:3])} involved.")
    body = ""
    for part in parts:  # whole parts only, so a claim's number is never cut in half
        if len(body) + len(part) + 1 > BODY_MAX:
            break
        body = f"{body} {part}".strip()
    kept = [c for c in used if c["text"] in head or c["text"] in body]
    return {"headline": clip(head, HEADLINE_MAX), "body": clip(body, BODY_MAX), "claims": kept}


ACTION_WORDS = {"pass": "pass", "carry": "carry", "shoot": "shot", "clear": "clearance", "hold": "hold-up"}


def _pct(p: float) -> str:
    return f"{round(100 * p)}%"


def tactician_template(moment, counterfactual: dict | None, names: dict[str, str]) -> dict:
    """`tactician_degraded` (models.yaml): an explanation built only from the counterfactual's own numbers and the
    moment's players, every number a claim. `names` maps player ids to display surnames. Returns {why, claims,
    confidence}; the executor adds ids and provenance."""
    cf = counterfactual
    claims: list[dict] = []

    def claim(text, kind, value, unit, ids):
        claims.append({"text": text, "kind": kind, "value": value, "unit": unit, "evidence_ids": ids,
                       "verified": False, "reject_reason": None})

    if cf:
        cid = [cf["counterfactual_id"]]
        actual, alt = cf["actual"], cf["alternative"]
        actor = names.get(actual["actor"], actual["actor"])
        claim(actor, "player", actual["actor"], None, cid)
        b, a = cf["baseline"], cf["alternative_outcome"]
        side = "p_goal_home" if b["p_goal_home"] >= b["p_goal_away"] else "p_goal_away"
        base_t, alt_t = _pct(b[side]), _pct(a[side])
        claim(base_t, "number", round(b[side], 2), "p_goal", cid)
        if alt_t != base_t:
            claim(alt_t, "number", round(a[side], 2), "p_goal", cid)
        what = ACTION_WORDS.get(alt["kind"], alt["kind"])
        if alt["kind"] == "pass" and alt.get("target") in names:
            target = names[alt["target"]]
            claim(target, "player", alt["target"], None, cid)
            what = f"pass to {target}"
        why = f"{actor} chose the {ACTION_WORDS.get(actual['kind'], actual['kind'])}; goal chance {base_t}."
        if alt_t != base_t:
            why += f" The {what} instead: {alt_t}."
        wa, wb = _pct(b["win_prob_home"]), _pct(a["win_prob_home"])
        if wa != wb:
            claim(f"{wa} to {wb}", "number", round(cf["delta_win_prob_home"], 4), "win_prob_delta", cid)
            why += f" Home win chance {wa} to {wb}."
        return {"why": why, "claims": claims, "confidence": 0.5}
    m = moment
    ids = list(_get(m, "evidence_event_ids") or [])[:1]
    players = [p for p in _get(m, "players") or [] if p in names]
    if players and ids:
        claim(names[players[0]], "player", players[0], None, ids)
    kind = str(_get(m, "kind") or "moment").replace("_", " ")
    why = f"{names[players[0]]} at the centre of a {kind}." if players and ids else f"A {kind}."
    return {"why": why, "claims": claims, "confidence": 0.3}


def _get(m, key, default=None):
    return m.get(key, default) if isinstance(m, dict) else getattr(m, key, default)
