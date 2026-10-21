"""Fact Checker: the eight deterministic rules of TECH_PLAN 1.7 (T-019). No model, no network.

    verify_claims(match_id, claims, bb, text=None) -> {verified, claims[], diff[]}

1. every evidence id resolves in the blackboard (events, counterfactuals, facts, pitch_control);
2. kind=number: the claim's value matches its evidence within tolerance (TOLERANCE), and the number shown in the
   claim text matches the value; win_prob_delta must equal the counterfactual's delta_win_prob_home;
3. kind=player/team: in the match lineups and in a cited evidence event (player), or one of the two clubs (team);
4. kind=minute: within 1 minute of a cited evidence t_ms;
5. kind=tactical: cites a pc_ snapshot or f_ fact whose zones or label contain the claimed pattern;
6. every number in why/headline/body appears in the text of a verified claim (else `unbound_number`);
7. no banned content (injury speculation, referee-bias accusations, betting language, real names);
8. rejections come back with a per-claim reject_reason and a `diff` for the Narrator's rewrite.

Numbers a rollout derives for a counterfactual but that the counterfactual schema has no field for (the xG of the
shot the alternative leads to) are written as facts carrying `counterfactual_id`; citing the cf_ id covers them.
The MCP tool `verify_claims` (T-030) calls this same function.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from blackboard.ids import collection_of
from blackboard.protocol import NotFound

ROOT = Path(__file__).resolve().parents[2]
LEAGUE = ROOT / "data" / "league"

TOLERANCE = {"xg": 0.005, "p_goal": 0.01, "win_prob": 0.01, "percent": 0.01, "win_prob_delta": 0.01,
             "metres": 0.5, "kmh": 1.0, "minute": 1.0, "xt": 0.005, "seconds": 0.5, "count": 0.0}
PROBABILITY_UNITS = {"p_goal", "win_prob", "percent", "win_prob_delta"}
UNIT_ALIASES = {"m": "metres", "meters": "metres", "km/h": "kmh", "kph": "kmh", "s": "seconds", "sec": "seconds",
                "%": "percent", "pct": "percent", "minutes": "minute", "min": "minute", "n": "count"}
EPS = 1e-9

NUMBER = re.compile(r"\d+(?:\.\d+)?(?:\s?%)?")

INJURY = [
    r"injur(?:y|ies)\s+(?:doubt|concern|scare|worry|blow|problem)s?",
    r"(?:is|was|looks|look|seems|appears|could be|may be|might be)\s+(?:injured|hurt|crocked)",
    r"(?:hamstring|groin|calf|knee|ankle|thigh|back|muscle)\s+(?:injury|strain|problem|issue|tweak|pull)",
    r"pulled up", r"limp(?:ing|ed|s)?\s+(?:off|away|badly)", r"fitness\s+(?:doubt|concern|test)",
]
REFEREE_BIAS = [
    r"(?:biased|bent|corrupt|crooked)\s+(?:ref|refs|referee|referees|official|officials|officiating)",
    r"(?:ref|referee|officials?)\s+(?:is|are|was|were)\s+(?:biased|bent|corrupt|crooked|cheating|bought)",
    r"(?:ref|referee)\s+(?:favours|favors|favoured|favored|hates|has it in for)", r"paid off",
    r"match[- ]fixing", r"rigged",
]
BETTING = [r"odds", r"bets?", r"bettors?", r"betting\s+(?:odds|tips?|markets?|lines?|slips?)", r"bookmakers?",
           r"bookies?", r"wager(?:s|ed)?", r"accas?", r"accumulators?", r"punters?"]


# ---------------------------------------------------------------------------------------------------- banned


class BannedMatcher:
    """Rule 7 matcher: whole phrase, case-insensitive. Reused by scripts/scan_banned.py on any file."""

    def __init__(self, names: list[str]) -> None:
        def rx(pattern: str) -> re.Pattern:
            return re.compile(r"(?<!\w)(?:" + pattern + r")(?!\w)", re.IGNORECASE)

        self.rules: list[tuple[str, re.Pattern]] = (
            [("injury_speculation", rx(p)) for p in INJURY]
            + [("referee_bias", rx(p)) for p in REFEREE_BIAS]
            + [("betting", rx(p)) for p in BETTING])
        # one alternation per 200 names keeps the scan fast
        for i in range(0, len(names), 200):
            alt = "|".join(re.escape(n) for n in sorted(names[i:i + 200], key=len, reverse=True))
            self.rules.append(("real_name", rx(alt)))

    def find(self, text: str) -> list[tuple[str, str]]:
        """[(category, matched phrase)] for every hit in `text`."""
        hits = []
        for category, pattern in self.rules:
            hits.extend((category, m.group(0)) for m in pattern.finditer(text))
        return hits


def load_banned_names(path: Path = LEAGUE / "banned_names.txt") -> list[str]:
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()]
    return [ln for ln in lines if ln and not ln.startswith("#")]


@lru_cache(maxsize=1)
def banned_matcher() -> BannedMatcher:
    return BannedMatcher(load_banned_names())


# ---------------------------------------------------------------------------------------------------- league


@lru_cache(maxsize=1)
def league_data() -> tuple[dict, dict]:
    players = {p["id"]: p for p in json.loads((LEAGUE / "players.json").read_text())}
    clubs = {c["id"]: c for c in json.loads((LEAGUE / "clubs.json").read_text())}
    return players, clubs


def _metadata(bb, match_id: str) -> dict:
    docs = bb.query("events", match_id=match_id, type="match_metadata", limit=1)
    return docs[0]["attrs"] if docs else {}


# ---------------------------------------------------------------------------------------------------- numbers


def _unit(u: str | None) -> str | None:
    return UNIT_ALIASES.get(u, u) if u else u


def _key_unit(key: str) -> str | None:
    k = key.lower()
    parts = k.split("_")
    if k == "delta_win_prob_home":
        return "win_prob_delta"
    if k.startswith("ci95") or k in ("t_ms", "seed", "compute_ms", "idx", "period"):
        return None
    if "xg" in parts:
        return "xg"
    if k.startswith("p_goal"):
        return "p_goal"
    if k.startswith("win_prob"):
        return "win_prob"
    if "xt" in parts:
        return "xt"
    if k.endswith("kmh"):
        return "kmh"
    if k.endswith("_m"):
        return "metres"
    if k.endswith("_s"):
        return "seconds"
    if k.endswith("_p") or k.endswith("share") or k.endswith("frac") or k in ("percent", "completion"):
        return "percent"
    if k == "n" or k.startswith("shots") or k.endswith("count") or k == "touches":
        return "count"
    return None


def _walk(obj, out: dict[str, list[float]], key: str = "") -> None:
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, int | float):
        if (u := _key_unit(key)) is not None:
            out.setdefault(u, []).append(float(obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k != "futures_sample":
                _walk(v, out, k)


def _candidates(doc: dict, collection: str) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    if collection == "events":
        _walk(doc.get("attrs", {}), out)
    elif collection == "facts":
        if isinstance(doc.get("value"), int | float) and doc.get("unit"):
            out.setdefault(_unit(doc["unit"]), []).append(float(doc["value"]))
        _walk({k: v for k, v in doc.items() if k not in ("value", "window_s")}, out)
    else:
        _walk(doc, out)
    return out


def _numbers(text: str) -> list[tuple[float, bool]]:
    """(value, is_percent) for every number in text."""
    out = []
    for tok in NUMBER.findall(text or ""):
        pct = tok.endswith("%")
        out.append((float(tok.rstrip("%").strip()), pct))
    return out


def _token_keys(text: str) -> set[str]:
    return {f"{v:g}{'%' if p else ''}" for v, p in _numbers(text)}


def _shown_value(num: float, pct: bool, unit: str) -> float:
    return num / 100.0 if (pct and unit in PROBABILITY_UNITS) else num


def _close(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol + EPS


# ---------------------------------------------------------------------------------------------------- rules


class _Evidence:
    def __init__(self, bb, match_id: str) -> None:
        self.bb, self.match_id = bb, match_id
        self.docs: dict[str, tuple[str, dict]] = {}

    def resolve(self, ids: list[str]) -> list[str]:
        """Load each id; return the ids that do not resolve (rule 1)."""
        missing = []
        for eid in ids:
            if eid in self.docs:
                continue
            try:
                coll = collection_of(eid)
                self.docs[eid] = (coll, self.bb.get(coll, eid, self.match_id))
            except (NotFound, ValueError):
                missing.append(eid)
        return missing

    def candidates(self, ids: list[str]) -> dict[str, list[float]]:
        out: dict[str, list[float]] = {}
        for eid in ids:
            coll, doc = self.docs[eid]
            for u, vals in _candidates(doc, coll).items():
                out.setdefault(u, []).extend(vals)
            if coll == "counterfactuals":
                for fact in self.bb.query("facts", match_id=self.match_id, counterfactual_id=eid):
                    for u, vals in _candidates(fact, "facts").items():
                        out.setdefault(u, []).extend(vals)
        return out


def _check_number(claim: dict, ev: _Evidence, ids: list[str]) -> str | None:
    unit = _unit(claim.get("unit"))
    value = claim.get("value")
    if unit == "minute":
        return _check_minute(claim, ev, ids)
    if unit not in TOLERANCE:
        return "unit_not_supported"
    if not isinstance(value, int | float) or isinstance(value, bool):
        return "value_not_numeric"
    tol = TOLERANCE[unit]
    shown = _numbers(claim.get("text", ""))
    if not shown:
        return "no_number_in_text"
    if unit == "win_prob_delta":
        cfs = [ev.docs[i][1] for i in ids if ev.docs[i][0] == "counterfactuals"]
        if not cfs:
            return "win_prob_delta_needs_counterfactual"
        if not any(_close(value, cf["delta_win_prob_home"], tol) for cf in cfs):
            return "value_out_of_tolerance"
        if len(shown) >= 2:  # "42% to 51%": both ends must be the cited win probabilities
            a, b = (_shown_value(n, p, unit) for n, p in shown[:2])
            ok = any(_close(a, cf["baseline"]["win_prob_home"], tol)
                     and _close(b, cf["alternative_outcome"]["win_prob_home"], tol) for cf in cfs)
            return None if ok and _close(b - a, value, 2 * tol) else "text_value_mismatch"
        n, pct = shown[0]  # "+9 points" or "+9%" or "0.09"
        delta = n / 100.0 if (pct or n > 1) else n
        return None if _close(delta, abs(value), tol) else "text_value_mismatch"
    if not any(_close(_shown_value(n, p, unit), value, tol) for n, p in shown):
        return "text_value_mismatch"
    cands = ev.candidates(ids)
    pool = list(cands.get(unit, []))
    if unit == "percent":
        for u in ("p_goal", "win_prob"):
            pool += cands.get(u, [])
    if not pool:
        return "no_evidence_for_unit"
    if not any(_close(value, c, tol) for c in pool):
        return "value_out_of_tolerance"
    return None


def _check_minute(claim: dict, ev: _Evidence, ids: list[str]) -> str | None:
    value = claim.get("value")
    if not isinstance(value, int | float):
        return "value_not_numeric"
    shown = _numbers(claim.get("text", ""))
    if shown and not any(_close(n, value, 0) for n, _ in shown):
        return "text_value_mismatch"
    times = [doc["t_ms"] for _, doc in (ev.docs[i] for i in ids) if isinstance(doc.get("t_ms"), int | float)]
    if not times:
        return "no_evidence_time"
    return None if any(_close(value, t / 60000.0, TOLERANCE["minute"]) for t in times) else "minute_out_of_range"


def _players_in(doc: dict, coll: str) -> set[str]:
    found: set[str] = set()
    if coll == "events":
        attrs = doc.get("attrs", {})
        for v in [doc.get("player"), *(attrs.get(k) for k in ("recipient", "fouled_player", "offside_player",
                                                               "last_defender", "player_off", "player_on"))]:
            if isinstance(v, str):
                found.add(v)
    elif coll == "counterfactuals":
        for a in (doc.get("actual") or {}, doc.get("alternative") or {}):
            found.update(v for v in (a.get("actor"), a.get("target")) if isinstance(v, str))
    else:
        found.update(p for p in doc.get("players", []) if isinstance(p, str))
    return found


def _check_player(claim: dict, ev: _Evidence, ids: list[str], meta: dict) -> str | None:
    pid = claim.get("value")
    players, _ = league_data()
    if not isinstance(pid, str) or pid not in players:
        return "unknown_player"
    lineups = meta.get("lineups", {})
    squad = {p for side in lineups.values() for group in side.values() for p in group}
    if pid not in squad:
        return "player_not_in_lineup"
    name = players[pid]["name"].lower()
    text = (claim.get("text") or "").strip().lower()
    if not text or text not in name:
        return "player_name_mismatch"
    involved: set[str] = set()
    for eid in ids:
        coll, doc = ev.docs[eid]
        involved |= _players_in(doc, coll)
        related = [r for r in doc.get("related_event_ids", []) if r not in ev.docs]
        ev.resolve(related)  # one hop: the pass that set up the cited shot
        for r in doc.get("related_event_ids", []):
            if r in ev.docs:
                r_coll, r_doc = ev.docs[r]
                involved |= _players_in(r_doc, r_coll)
    return None if pid in involved else "player_not_in_evidence"


def _check_team(claim: dict, meta: dict) -> str | None:
    _, clubs = league_data()
    value = claim.get("value")
    sides = {"home": meta.get("home"), "away": meta.get("away")}
    club_id = sides.get(value, value)
    if club_id not in (sides["home"], sides["away"]) or club_id not in clubs:
        return "team_not_in_match"
    club = clubs[club_id]
    text = (claim.get("text") or "").strip().lower()
    names = {club["name"].lower(), club["short_name"].lower()}
    return None if text and any(text in n or n in text for n in names) else "team_name_mismatch"


def _labels(doc: dict) -> list[str]:
    out: list[str] = []

    def walk(obj) -> None:
        if isinstance(obj, str):
            out.append(obj.lower())
        elif isinstance(obj, dict):
            for k, v in obj.items():
                out.append(str(k).lower())
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    for key in ("zones", "cluster", "label", "labels", "name", "value", "overloads"):
        if key in doc:
            walk(doc[key])
    return out


def _check_tactical(claim: dict, ev: _Evidence, ids: list[str]) -> str | None:
    pattern = claim.get("value")
    if not isinstance(pattern, str) or not pattern:
        return "tactical_pattern_missing"
    tactical = [ev.docs[i] for i in ids if ev.docs[i][0] in ("pitch_control", "facts")]
    if not tactical:
        return "tactical_needs_pc_or_fact"
    p = pattern.lower()
    return None if any(p in label for _, doc in tactical for label in _labels(doc)) else "tactical_pattern_not_found"


def verify_claims(match_id: str, claims: list[dict], bb, text: dict[str, str] | None = None) -> dict:
    """Apply rules 1-8. Returns {verified, claims (copies with verified/reject_reason), diff}."""
    ev = _Evidence(bb, match_id)
    meta: dict | None = None
    banned = banned_matcher()
    out_claims, diff = [], []
    for i, claim in enumerate(claims):
        ids = list(claim.get("evidence_ids") or [])
        reason: str | None = None
        if not ids:
            reason = "no_evidence"
        elif missing := ev.resolve(ids):
            reason = "evidence_not_found"
        else:
            kind = claim.get("kind")
            if kind == "number":
                reason = _check_number(claim, ev, ids)
            elif kind == "minute":
                reason = _check_minute(claim, ev, ids)
            elif kind in ("player", "team"):
                meta = meta if meta is not None else _metadata(bb, match_id)
                reason = _check_player(claim, ev, ids, meta) if kind == "player" else _check_team(claim, meta)
            elif kind == "tactical":
                reason = _check_tactical(claim, ev, ids)
            else:
                reason = "unknown_kind"
        if reason is None and banned.find(claim.get("text") or ""):
            reason = "banned_content"
        out = {**claim, "verified": reason is None, "reject_reason": reason}
        out_claims.append(out)
        if reason:
            entry = {"where": f"claims[{i}]", "text": claim.get("text"), "reject_reason": reason}
            if reason == "evidence_not_found":
                entry["missing"] = missing
            diff.append(entry)
    allowed: set[str] = set()
    for c in out_claims:
        if c["verified"]:
            allowed |= _token_keys(c.get("text", ""))
    for field, value in (text or {}).items():
        if not value:
            continue
        for tok in sorted(_token_keys(value) - allowed):
            diff.append({"where": field, "token": tok, "reject_reason": "unbound_number"})
        for category, phrase in banned.find(value):
            diff.append({"where": field, "phrase": phrase, "category": category, "reject_reason": "banned_content"})
    return {"verified": not diff, "claims": out_claims, "diff": diff}
