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
