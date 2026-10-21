# blackboard

Shared document store for the newsroom (SQLite locally, Cosmos in Azure).

Interface restated from `TECH_PLAN.md` section 1.4 "blackboard" (TECH_PLAN wins on conflict).
Tests live in `tests/blackboard/`.

```python
class Blackboard(Protocol):
    def put(self, collection: str, doc: dict) -> str; def get(self, collection, id) -> dict
    def query(self, collection, **filters) -> list[dict]; def watch(self, collection) -> AsyncIterator[dict]
class SqliteBlackboard(Blackboard)      # local; one table per collection, JSON column, indexes on match_id and t_ms
class CosmosBlackboard(Blackboard)      # Azure; azure-cosmos (pin at T-001); partition key /match_id
```

Performance: put < 2 ms locally. Tests: round-trip every schema example; `watch` delivers in insertion order.

## As built (T-017)

- `SqliteBlackboard(path=None)`: file `data/runtime/blackboard.sqlite` (or `WHYLINE_BLACKBOARD`), WAL mode.
  Each collection is a table `(seq AUTOINCREMENT, id, match_id, t_ms, doc JSON)` with `UNIQUE(match_id, id)`.
- `put` allocates the id when the document has none (`ids.ID_FIELDS` names the key field per collection:
  `fact_id`, `moment_id`, `snapshot_id`, `counterfactual_id`, `explanation_id`, `cue_id`, `trace_row_id`; events
  keep `id`). Replacing a document gives it a new `seq`, so watchers also see updates (a vetoed cue).
- `query(collection, **filters)`: equality on top-level fields, a list means "any of", plus `t_from_ms` / `t_to_ms`
  (on `t_ms`, or `t_in_ms` for cues) and `limit`.
- `watch(collection, match_id=None, from_start=True)`: async iterator polling `seq`, works across processes.
- `next_id(collection, match_id)`: allocate without writing; counters live in the `_counters` table.
- Measured: `put` p50 0.06 ms, p95 0.10 ms (limit 2 ms).
