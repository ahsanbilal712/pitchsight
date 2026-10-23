"""Featured real-clip moments (T-109): roster ids, the counterfactual from a committed moment file, the cached
explanations stay verified. Uses the committed JSON only (no media, no model call)."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from footage.clips import load_config
from footage.featured import counterfactual, footage_block, open_cache, roster, surname_match
from footage.freeze import load
from footage.review import evidence_board

ROOT = Path(__file__).resolve().parents[2]
SLUG = "liverpool-mancity-2526"


def validator(name):
    registry, schemas = Registry(), {}
    for p in (ROOT / "schemas").glob("*.schema.json"):
        s = json.loads(p.read_text())
        schemas[p.name] = s
        registry = registry.with_resource(s["$id"], Resource.from_contents(s))
    return Draft202012Validator(schemas[name], registry=registry)


def test_roster_ids_are_stable_and_named_players_only():
    ros = roster(SLUG)
    assert roster(SLUG)["ids"] == ros["ids"] and all(p.startswith("p_9") for p in ros["ids"].values())
    assert set(ros["names"].values()) == {"Dominik Szoboszlai", "Mohamed Salah"}
    block = footage_block(SLUG, ros)
    assert "Mohamed Salah" in block and "[not a claim]" in block


def test_surname_match():
    assert surname_match("Salah", "Mohamed Salah") and surname_match("Mo Salah", "Mohamed Salah")
    assert not surname_match("Silva", "Mohamed Salah") and not surname_match(None, "Mohamed Salah")


def test_counterfactual_from_the_frozen_frame_validates():
    m = load(SLUG, 875000)
    ros = roster(SLUG)
    cf = counterfactual(m, {"kind": "pass", "target": "#11"}, ros["ids"], "mo_00001", "cf_000001", ["e_0033"], 9001)
    assert not list(validator("counterfactual.schema.json").iter_errors(cf))
    assert cf["actual"]["actor"] == ros["ids"]["home:#8"] and cf["alternative"]["target"] == ros["ids"]["home:#11"]
    # futures are drawn in the frame's own coordinates: Liverpool attack +x, so the alternative heads for x = 105
    assert sum(path[-1][0] for path in cf["futures_sample"]) / len(cf["futures_sample"]) > 70


@pytest.mark.parametrize("f", load_config()["featured"], ids=lambda f: f["slug"])
def test_cached_reviewed_explanation_still_verifies(f):
    from newsroom.factcheck import verify_claims

    manifest = open_cache(f["slug"])
    entry = manifest.find(moment_id=f["moment_id"], producer="explanation", version="explanation@reviewed")[0]
    assert entry["hand_reviewed"]
    exp = manifest.read(entry)
    assert not list(validator("explanation.schema.json").iter_errors(exp))
    bb = evidence_board(manifest)
    result = verify_claims(manifest.data["match_id"], exp["claims"], bb, {"why": exp["why"]})
    bb.close()
    assert result["verified"], result["diff"]


def test_futures_are_half_real_action_half_alternative():
    m = load(SLUG, 875000)
    ros = roster(SLUG)
    cf = counterfactual(m, {"kind": "pass", "target": "#11"}, ros["ids"], "mo_00001", "cf_000001", ["e_0033"], 9001)
    shot, alt = cf["futures_sample"][:100], cf["futures_sample"][100:]
    assert len(shot) == len(alt) == 100 and shot != alt


def test_fourth_official_cue_is_an_assessment_and_verifies():
    from blackboard import SqliteBlackboard
    from newsroom.factcheck import verify_claims

    manifest = open_cache("manutd-spurs-2425")
    entry = manifest.find(producer="fourth_official", version="footage_772400")[0]
    cue = manifest.read(entry)
    assert not list(validator("cue.schema.json").iter_errors(cue))
    assert "not a ruling" in cue["text"]["body"] and "not a ruling" in cue["explain"]["why"]
    bb = SqliteBlackboard(":memory:")
    ev = manifest.find(producer="evidence", version="fourth_official_772400")[0]
    for line in (manifest.cache_dir / ev["path"]).read_text().splitlines():
        doc = json.loads(line)
        bb.put(doc.pop("_collection"), doc)
    result = verify_claims(cue["match_id"], cue["explain"]["claims"], bb,
                           {"headline": cue["text"]["headline"], "body": cue["text"]["body"],
                            "why": cue["explain"]["why"]})
    bb.close()
    assert result["verified"], result["diff"]
