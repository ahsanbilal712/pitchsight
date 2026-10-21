"""Deterministic narrator_template lines (TECH_PLAN 1.7): built only from verified claims, so they always pass the
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
