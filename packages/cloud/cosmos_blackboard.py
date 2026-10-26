"""CosmosBlackboard: the Blackboard protocol on Azure Cosmos DB for NoSQL (serverless).

One container partitioned on /match_id holds every collection. Each item is
{id: "<collection>:<doc id>", collection, match_id, doc_id, t_ms, seq, doc}; `seq` is a nanosecond write stamp,
so `query` returns insertion order and `watch` polls `seq > last` the way SqliteBlackboard polls its sequence.
Ids are allocated from per-(collection, match) counter items with optimistic concurrency (ETag match), which is
safe across the api, the newsroom worker and the MCP server running as separate Container Apps.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncIterator

from blackboard.ids import PREFIXES, format_id, id_field, parse_id
from blackboard.protocol import NotFound

_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_COUNTERS = "_counters"


def _t(doc: dict) -> int | None:
    t = doc.get("t_ms", doc.get("t_in_ms"))
    return int(t) if isinstance(t, int | float) else None


class CosmosBlackboard:
    def __init__(self, container=None, *, endpoint: str | None = None, database: str | None = None,
                 container_name: str | None = None, credential=None, poll_s: float = 0.25) -> None:
        if container is None:
            from azure.cosmos import CosmosClient, PartitionKey

            from cloud.settings import credential as default_credential
            from cloud.settings import settings

            s = settings()
            client = CosmosClient(endpoint or s.cosmos_endpoint, credential=credential or default_credential())
            db = client.create_database_if_not_exists(database or s.cosmos_database)
            container = db.create_container_if_not_exists(container_name or s.cosmos_blackboard_container,
                                                          partition_key=PartitionKey(path="/match_id"))
        self._c = container
        self.poll_s = poll_s
        self._last_seq = 0

    # ------------------------------------------------------------------ ids
    def _seq(self) -> int:
        seq = max(time.time_ns(), self._last_seq + 1)
        self._last_seq = seq
        return seq

    def _bump(self, collection: str, match_id: str, n: int | None) -> int:
        from azure.core import MatchConditions
        from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosResourceNotFoundError

        key = f"{_COUNTERS}:{collection}"
        for _ in range(20):
            try:
                item = self._c.read_item(key, partition_key=match_id)
            except CosmosResourceNotFoundError:
                item = None
            cur = int(item["n"]) if item else 0
            new = cur + 1 if n is None else max(cur, n)
            body = {"id": key, "match_id": match_id, "collection": _COUNTERS, "n": new}
            try:
                if item is None:
                    self._c.create_item(body)
                elif new != cur:
                    self._c.replace_item(item, body, etag=item["_etag"], match_condition=MatchConditions.IfNotModified)
                return new
            except CosmosHttpResponseError as exc:  # 409 / 412: another process won the race; re-read and retry
                if exc.status_code not in (409, 412):
                    raise
        raise RuntimeError(f"id allocation for {collection}/{match_id} kept conflicting")

    def next_id(self, collection: str, match_id: str) -> str:
        return format_id(collection, self._bump(collection, match_id, None))

    # ------------------------------------------------------------------ protocol
    def _item(self, collection: str, doc_id: str, match_id: str, doc: dict) -> dict:
        return {"id": f"{collection}:{doc_id}", "collection": collection, "doc_id": doc_id, "match_id": match_id,
                "t_ms": _t(doc), "seq": self._seq(), "doc": doc}

    def put(self, collection: str, doc: dict) -> str:
        field = id_field(collection)
        match_id = str(doc.get("match_id") or "")
        doc_id = doc.get(field)
        if doc_id is None:
            if collection not in PREFIXES:
                raise ValueError(f"{collection} documents need an explicit {field!r}")
            doc_id = format_id(collection, self._bump(collection, match_id, None))
            doc = {**doc, field: doc_id}
        elif collection in PREFIXES:
            self._bump(collection, match_id, parse_id(doc_id)[1])
        self._c.upsert_item(self._item(collection, doc_id, match_id, doc))
        return doc_id

    def put_many(self, collection: str, docs: list[dict]) -> list[str]:
        return [self.put(collection, d) for d in docs]

    def get(self, collection: str, id: str, match_id: str | None = None) -> dict:
        if match_id is not None:
            from azure.cosmos.exceptions import CosmosResourceNotFoundError

            try:
                return self._c.read_item(f"{collection}:{id}", partition_key=match_id)["doc"]
            except CosmosResourceNotFoundError as exc:
                raise NotFound(f"{collection}/{id}") from exc
        rows = list(self._c.query_items(
            "SELECT TOP 1 c.doc FROM c WHERE c.collection = @c AND c.doc_id = @id ORDER BY c.seq DESC",
            parameters=[{"name": "@c", "value": collection}, {"name": "@id", "value": id}],
            enable_cross_partition_query=True))
        if not rows:
            raise NotFound(f"{collection}/{id}")
        return rows[0]["doc"]

    def _where(self, collection: str, filters: dict) -> tuple[list[str], list[dict]]:
        where, params = ["c.collection = @c"], [{"name": "@c", "value": collection}]
        t_from, t_to = filters.pop("t_from_ms", None), filters.pop("t_to_ms", None)
        if t_from is not None:
            where.append("c.t_ms >= @tf")
            params.append({"name": "@tf", "value": int(t_from)})
        if t_to is not None:
            where.append("c.t_ms <= @tt")
            params.append({"name": "@tt", "value": int(t_to)})
        for i, (key, value) in enumerate(filters.items()):
            if not _FIELD.match(key):
                raise ValueError(f"bad filter field {key!r}")
            col = "c.match_id" if key == "match_id" else ("c.doc_id" if key == id_field(collection) else
                                                         f"c.doc[\"{key}\"]")
            name = f"@f{i}"
            if isinstance(value, list | tuple | set):
                where.append(f"ARRAY_CONTAINS({name}, {col})")
                params.append({"name": name, "value": list(value)})
            elif value is None:
                where.append(f"(NOT IS_DEFINED({col}) OR IS_NULL({col}))")
            else:
                where.append(f"{col} = {name}")
                params.append({"name": name, "value": value})
        return where, params

    def query(self, collection: str, **filters) -> list[dict]:
        limit = filters.pop("limit", None)
        match_id = filters.get("match_id")
        where, params = self._where(collection, dict(filters))
        top = f"TOP {int(limit)} " if limit is not None else ""
        sql = f"SELECT {top}c.doc FROM c WHERE {' AND '.join(where)} ORDER BY c.seq"
        kwargs = {"partition_key": match_id} if isinstance(match_id, str) else {"enable_cross_partition_query": True}
        return [r["doc"] for r in self._c.query_items(sql, parameters=params, **kwargs)]

    def last_seq(self, collection: str) -> int:
        rows = list(self._c.query_items("SELECT VALUE MAX(c.seq) FROM c WHERE c.collection = @c",
                                        parameters=[{"name": "@c", "value": collection}],
                                        enable_cross_partition_query=True))
        return int(rows[0] or 0) if rows else 0

    def changes_since(self, collection: str, seq: int, match_id: str | None = None) -> list[tuple[int, dict]]:
        filters = {"match_id": match_id} if match_id is not None else {}
        where, params = self._where(collection, filters)
        where.append("c.seq > @s")
        params.append({"name": "@s", "value": seq})
        sql = f"SELECT c.seq, c.doc FROM c WHERE {' AND '.join(where)} ORDER BY c.seq"
        kwargs = {"partition_key": match_id} if match_id is not None else {"enable_cross_partition_query": True}
        return [(int(r["seq"]), r["doc"]) for r in self._c.query_items(sql, parameters=params, **kwargs)]

    async def watch(self, collection: str, match_id: str | None = None,
                    from_start: bool = True) -> AsyncIterator[dict]:
        seq = 0 if from_start else self.last_seq(collection)
        while True:
            batch = await asyncio.to_thread(self.changes_since, collection, seq, match_id)
            for s, doc in batch:
                seq = s
                yield doc
            if not batch:
                await asyncio.sleep(self.poll_s)

    def close(self) -> None:
        pass
