"""Validate every schema, its examples, the test fixtures and any match cache against the schemas (T-005).

Usage: python scripts/validate_schemas.py

TECH_PLAN 1.3 versioning rule: a document is validated against the schema it names, and the
`schema_version` it carries must be the version that schema defines. How a document names its schema:
- a `$schema` field holding a schema file name or `$id` (any JSON document);
- the stream envelope {"type", "payload"} of TECH_PLAN 1.9 (JSONL lines): the message type names it,
  e.g. `event` -> event.schema.json, `cue` -> cue.schema.json, `hello.payload.viewer_profile`;
- under data/matches/*/: `events.jsonl` lines are events; in `cache/`, `manifest.json` is a cache
  manifest and files named `cf_*`, `ex_*`, `c_*` are counterfactuals, explanations and cues.
A fixture JSON file that names no schema is an error, so nothing passes silently.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "schemas"
FIXTURES = ROOT / "tests" / "fixtures"
MATCHES = ROOT / "data" / "matches"

# TECH_PLAN 1.9 message types; those without a JSON schema are checked for shape only.
MESSAGE_SCHEMAS = {"event": "event.schema.json", "cue": "cue.schema.json", "counterfactual": "counterfactual.schema.json"}
SCHEMALESS_MESSAGES = {"hello", "tracking_frame", "fact", "moment", "cue_remove", "trace", "request_info", "mode",
                       "spend", "oracle"}
CACHE_PREFIXES = {"cf_": "counterfactual.schema.json", "ex_": "explanation.schema.json", "c_": "cue.schema.json"}


class Validators:
    def __init__(self) -> None:
        self.schemas: dict[str, dict] = {}
        registry = Registry()
        for path in sorted(SCHEMA_DIR.glob("*.schema.json")):
            schema = json.loads(path.read_text())
            self.schemas[path.name] = schema
            registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
        self.by_id = {s["$id"]: name for name, s in self.schemas.items()}
        self.validators = {name: Draft202012Validator(s, registry=registry) for name, s in self.schemas.items()}

    def resolve(self, ref: str) -> str | None:
        name = ref.rsplit("/", 1)[-1]
        return name if name in self.schemas else self.by_id.get(ref)

    def check(self, name: str, doc: dict, where: str) -> list[str]:
        errors = []
        version = self.schemas[name].get("properties", {}).get("schema_version", {}).get("const")
        if version and isinstance(doc, dict) and doc.get("schema_version") not in (None, version):
            return [f"{where}: names {name} version {doc.get('schema_version')}, schema is {version}"]
        for err in self.validators[name].iter_errors(doc):
            path = "/".join(str(p) for p in err.absolute_path) or "(root)"
            errors.append(f"{where}: {name} at {path}: {err.message}")
        return errors


def check_schemas(v: Validators) -> tuple[list[str], int]:
    errors, n = [], 0
    for name, schema in v.schemas.items():
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:  # noqa: BLE001 - report every malformed schema, keep going
            errors.append(f"{name}: not a valid draft 2020-12 schema: {exc}")
            continue
        for i, example in enumerate(schema.get("examples", [])):
            errors += v.check(name, example, f"{name} examples[{i}]")
            n += 1
    return errors, n


def check_message(v: Validators, msg: dict, where: str) -> list[str]:
    if not isinstance(msg, dict) or set(msg) != {"type", "payload"}:
        return [f"{where}: not a {{type, payload}} stream envelope"]
    typ, payload = msg["type"], msg["payload"]
    if typ in MESSAGE_SCHEMAS:
        return v.check(MESSAGE_SCHEMAS[typ], payload, f"{where} ({typ})")
    if typ == "hello" and isinstance(payload, dict) and payload.get("viewer_profile") is not None:
        return v.check("viewer_profile.schema.json", payload["viewer_profile"], f"{where} (hello.viewer_profile)")
    if typ in SCHEMALESS_MESSAGES:
        return []
    return [f"{where}: unknown message type {typ!r}"]


def check_document(v: Validators, doc, where: str, default: str | None = None) -> list[str]:
    if isinstance(doc, dict) and "$schema" in doc and doc["$schema"] not in (None, ""):
        name = v.resolve(str(doc["$schema"]))
        if name is None:
            return [f"{where}: names unknown schema {doc['$schema']!r}"]
        body = {k: val for k, val in doc.items() if k != "$schema"}
        return v.check(name, body, where)
    if isinstance(doc, dict) and set(doc) == {"type", "payload"}:
        return check_message(v, doc, where)
    if default:
        return v.check(default, doc, where)
    return [f"{where}: names no schema (add $schema or use a stream envelope)"]


def load_lines(path: Path):
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            yield n, line


def check_file(v: Validators, path: Path, default: str | None = None) -> tuple[list[str], int]:
    rel = path.relative_to(ROOT)
    errors, n = [], 0
    if path.suffix == ".jsonl":
        for lineno, line in load_lines(path):
            try:
                doc = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"{rel}:{lineno}: invalid JSON: {exc}")
                continue
            errors += check_document(v, doc, f"{rel}:{lineno}", default)
            n += 1
    else:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return [f"{rel}: invalid JSON: {exc}"], 0
        docs = doc if isinstance(doc, list) else [doc]
        for i, d in enumerate(docs):
            errors += check_document(v, d, f"{rel}[{i}]" if isinstance(doc, list) else str(rel), default)
            n += 1
    return errors, n


def main() -> int:
    v = Validators()
    errors, n_examples = check_schemas(v)
    n_docs = 0
    for path in sorted(FIXTURES.rglob("*")) if FIXTURES.exists() else []:
        if path.suffix in (".json", ".jsonl"):
            e, n = check_file(v, path)
            errors, n_docs = errors + e, n_docs + n
    for match in sorted(MATCHES.glob("*/")) if MATCHES.exists() else []:
        if (match / "events.jsonl").exists():
            e, n = check_file(v, match / "events.jsonl", default="event.schema.json")
            errors, n_docs = errors + e, n_docs + n
        cache = match / "cache"
        for path in sorted(cache.rglob("*.json")) if cache.exists() else []:
            default = "cache_manifest.schema.json" if path.name == "manifest.json" else next(
                (s for p, s in CACHE_PREFIXES.items() if path.name.startswith(p)), None)
            e, n = check_file(v, path, default)
            errors, n_docs = errors + e, n_docs + n
    if errors:
        print(f"validate_schemas: FAIL ({len(errors)} errors)")
        for e in errors[:200]:
            print("  " + e)
        return 1
    print(f"validate_schemas: OK ({len(v.schemas)} schemas, {n_examples} examples, {n_docs} fixture/cache documents)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
