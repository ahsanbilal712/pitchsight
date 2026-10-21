"""SqliteBlackboard: one table per collection, JSON column, indexes on match_id and t_ms (TECH_PLAN 1.4, T-017).

The api and the newsroom worker are separate processes, so `watch` polls an AUTOINCREMENT sequence in WAL mode;
that is the local hand-off for moments and cues. A replaced document gets a new sequence number, so watchers see
updates (a vetoed cue) as well as inserts. Default file: data/runtime/blackboard.sqlite (WHYLINE_BLACKBOARD).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
import threading
from collections.abc import AsyncIterator
from pathlib import Path

from blackboard.ids import PREFIXES, format_id, id_field, parse_id
from blackboard.protocol import NotFound

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / "data" / "runtime" / "blackboard.sqlite"
_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _t(doc: dict) -> int | None:
    t = doc.get("t_ms", doc.get("t_in_ms"))
    return int(t) if isinstance(t, int | float) else None


class SqliteBlackboard:
    def __init__(self, path: str | Path | None = None, poll_s: float = 0.02) -> None:
        path = path or os.environ.get("WHYLINE_BLACKBOARD") or DEFAULT_PATH
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.poll_s = poll_s
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False, timeout=10)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.execute("CREATE TABLE IF NOT EXISTS _counters (collection TEXT, match_id TEXT, n INTEGER,"
                         " PRIMARY KEY (collection, match_id))")
        self._tables: set[str] = set()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # ------------------------------------------------------------------ tables
    def _table(self, collection: str) -> str:
        if collection in self._tables:
            return collection
        if not _NAME.match(collection) or collection.startswith("_"):
            raise ValueError(f"bad collection name {collection!r}")
        with self._lock:
            self._db.execute(
                f"CREATE TABLE IF NOT EXISTS {collection} (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL,"
                " match_id TEXT NOT NULL, t_ms INTEGER, doc TEXT NOT NULL, UNIQUE (match_id, id))")
            self._db.execute(f"CREATE INDEX IF NOT EXISTS {collection}_match ON {collection} (match_id, seq)")
            self._db.execute(f"CREATE INDEX IF NOT EXISTS {collection}_t ON {collection} (match_id, t_ms)")
            self._db.execute(f"CREATE INDEX IF NOT EXISTS {collection}_id ON {collection} (id)")
        self._tables.add(collection)
        return collection

    def _exists(self, collection: str) -> bool:
        if collection in self._tables:
            return True
        row = self._db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (collection,)).fetchone()
        return row is not None

    # ------------------------------------------------------------------ ids
    def _bump(self, collection: str, match_id: str, n: int | None) -> int:
        row = self._db.execute("SELECT n FROM _counters WHERE collection=? AND match_id=?",
                               (collection, match_id)).fetchone()
        cur = row[0] if row else 0
        new = cur + 1 if n is None else max(cur, n)
        self._db.execute("INSERT OR REPLACE INTO _counters VALUES (?, ?, ?)", (collection, match_id, new))
        return new

    def next_id(self, collection: str, match_id: str) -> str:
        """Allocate the next id without writing a document (cross-process safe)."""
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                n = self._bump(collection, match_id, None)
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        return format_id(collection, n)

    # ------------------------------------------------------------------ protocol
    def put(self, collection: str, doc: dict) -> str:
        table = self._table(collection)
        field = id_field(collection)
        match_id = str(doc.get("match_id") or "")
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                doc_id = doc.get(field)
                if doc_id is None:
                    if collection not in PREFIXES:
                        raise ValueError(f"{collection} documents need an explicit {field!r}")
                    doc_id = format_id(collection, self._bump(collection, match_id, None))
                    doc = {**doc, field: doc_id}
                elif collection in PREFIXES:
                    self._bump(collection, match_id, parse_id(doc_id)[1])
                self._db.execute(f"INSERT OR REPLACE INTO {table} (id, match_id, t_ms, doc) VALUES (?, ?, ?, ?)",
                                 (doc_id, match_id, _t(doc), json.dumps(doc, separators=(",", ":"))))
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        return doc_id

    def put_many(self, collection: str, docs: list[dict]) -> list[str]:
        """Bulk insert (one transaction) for loading a match's events."""
        table = self._table(collection)
        field = id_field(collection)
        rows = [(d[field], str(d.get("match_id") or ""), _t(d), json.dumps(d, separators=(",", ":"))) for d in docs]
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._db.executemany(f"INSERT OR REPLACE INTO {table} (id, match_id, t_ms, doc) VALUES (?, ?, ?, ?)",
                                     rows)
                if collection in PREFIXES:
                    for r in rows:
                        self._bump(collection, r[1], parse_id(r[0])[1])
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        return [r[0] for r in rows]

    def get(self, collection: str, id: str, match_id: str | None = None) -> dict:
        if not self._exists(collection):
            raise NotFound(f"{collection}/{id}")
        sql, args = f"SELECT doc FROM {collection} WHERE id=?", [id]
        if match_id is not None:
            sql += " AND match_id=?"
            args.append(match_id)
        with self._lock:
            row = self._db.execute(sql + " ORDER BY seq DESC LIMIT 1", args).fetchone()
        if row is None:
            raise NotFound(f"{collection}/{id}")
        return json.loads(row[0])

    def query(self, collection: str, **filters) -> list[dict]:
        if not self._exists(collection):
            return []
        where, args = [], []
        t_from, t_to = filters.pop("t_from_ms", None), filters.pop("t_to_ms", None)
        limit = filters.pop("limit", None)
        if t_from is not None:
            where.append("t_ms >= ?")
            args.append(int(t_from))
        if t_to is not None:
            where.append("t_ms <= ?")
            args.append(int(t_to))
        for key, value in filters.items():
            if not _FIELD.match(key):
                raise ValueError(f"bad filter field {key!r}")
            col = "match_id" if key == "match_id" else ("id" if key == id_field(collection) else
                                                       f"json_extract(doc, '$.{key}')")
            if isinstance(value, list | tuple | set):
                values = list(value)
                where.append(f"{col} IN ({','.join('?' * len(values))})")
                args.extend(values)
            elif value is None:
                where.append(f"{col} IS NULL")
            else:
                where.append(f"{col} = ?")
                args.append(int(value) if isinstance(value, bool) else value)
        sql = f"SELECT doc FROM {collection}" + (f" WHERE {' AND '.join(where)}" if where else "") + " ORDER BY seq"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        with self._lock:
            rows = self._db.execute(sql, args).fetchall()
        return [json.loads(r[0]) for r in rows]

    def last_seq(self, collection: str) -> int:
        if not self._exists(collection):
            return 0
        with self._lock:
            row = self._db.execute(f"SELECT MAX(seq) FROM {collection}").fetchone()
        return row[0] or 0

    def changes_since(self, collection: str, seq: int, match_id: str | None = None) -> list[tuple[int, dict]]:
        if not self._exists(collection):
            return []
        sql, args = f"SELECT seq, doc FROM {collection} WHERE seq > ?", [seq]
        if match_id is not None:
            sql += " AND match_id = ?"
            args.append(match_id)
        with self._lock:
            rows = self._db.execute(sql + " ORDER BY seq", args).fetchall()
        return [(s, json.loads(d)) for s, d in rows]

    async def watch(self, collection: str, match_id: str | None = None,
                    from_start: bool = True) -> AsyncIterator[dict]:
        seq = 0 if from_start else self.last_seq(collection)
        while True:
            batch = self.changes_since(collection, seq, match_id)
            for s, doc in batch:
                seq = s
                yield doc
            if not batch:
                await asyncio.sleep(self.poll_s)
