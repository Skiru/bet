#!/usr/bin/env python3
"""Hardened read-only SQLite query runner for the Kilo custom tool.

Input (stdin JSON): {"sql": "SELECT ...", "limit": 100, "db_path": "..."}
Output (stdout JSON): bounded columns/rows metadata.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

MAX_SQL_CHARS = 12_000
MAX_ROWS = 200
MAX_JSON_BYTES = 10 * 1024
MAX_VM_CALLBACKS = 4_000  # callback runs every 1,000 VM instructions

READ_PREFIX = re.compile(r"^\s*(?:--[^\n]*\n\s*)*(select|with)\b", re.IGNORECASE)

DENIED_ACTION_NAMES = (
    "SQLITE_INSERT",
    "SQLITE_UPDATE",
    "SQLITE_DELETE",
    "SQLITE_CREATE_INDEX",
    "SQLITE_CREATE_TABLE",
    "SQLITE_CREATE_TEMP_INDEX",
    "SQLITE_CREATE_TEMP_TABLE",
    "SQLITE_CREATE_TEMP_TRIGGER",
    "SQLITE_CREATE_TEMP_VIEW",
    "SQLITE_CREATE_TRIGGER",
    "SQLITE_CREATE_VIEW",
    "SQLITE_DROP_INDEX",
    "SQLITE_DROP_TABLE",
    "SQLITE_DROP_TEMP_INDEX",
    "SQLITE_DROP_TEMP_TABLE",
    "SQLITE_DROP_TEMP_TRIGGER",
    "SQLITE_DROP_TEMP_VIEW",
    "SQLITE_DROP_TRIGGER",
    "SQLITE_DROP_VIEW",
    "SQLITE_ALTER_TABLE",
    "SQLITE_REINDEX",
    "SQLITE_ANALYZE",
    "SQLITE_ATTACH",
    "SQLITE_DETACH",
    "SQLITE_TRANSACTION",
    "SQLITE_SAVEPOINT",
    "SQLITE_PRAGMA",
)
DENIED_ACTIONS = {
    value
    for name in DENIED_ACTION_NAMES
    if isinstance((value := getattr(sqlite3, name, None)), int)
}


def fail(message: str, code: str = "query_rejected") -> None:
    print(json.dumps({"ok": False, "error": code, "message": message}))
    raise SystemExit(2)


def json_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"type": "blob", "bytes": len(value), "hex_preview": value[:32].hex()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def bounded_payload(columns: list[str], rows: list[list[Any]], truncated: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": True,
        "columns": columns,
        "rows": rows,
        "returned_rows": len(rows),
        "truncated": truncated,
    }
    while rows and len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > MAX_JSON_BYTES:
        del rows[max(1, len(rows) // 2) :]
        payload["returned_rows"] = len(rows)
        payload["truncated"] = True
    return payload


def main() -> int:
    try:
        request = json.load(sys.stdin)
    except Exception as exc:
        fail(f"Invalid JSON input: {exc}", "invalid_input")

    sql = str(request.get("sql", "")).strip()
    if not sql:
        fail("SQL is required")
    if len(sql) > MAX_SQL_CHARS:
        fail(f"SQL exceeds {MAX_SQL_CHARS} characters")
    if not READ_PREFIX.match(sql):
        fail("Only SELECT or WITH queries are accepted")

    try:
        limit = int(request.get("limit", 100))
    except Exception:
        fail("limit must be an integer", "invalid_input")
    limit = max(1, min(limit, MAX_ROWS))

    project_root = Path(request.get("project_root") or os.getcwd()).resolve()
    configured = request.get("db_path") or os.environ.get("KILO_SQLITE_DB") or "betting/data/betting.db"
    db_path = Path(configured)
    if not db_path.is_absolute():
        db_path = project_root / db_path
    db_path = db_path.resolve()

    # Keep the tool project-scoped unless an explicit opt-out is set for diagnostics.
    if os.environ.get("KILO_SQLITE_ALLOW_EXTERNAL") != "1":
        try:
            db_path.relative_to(project_root)
        except ValueError:
            fail("Database path must remain inside the project root", "path_rejected")

    if not db_path.is_file():
        fail(f"Database not found: {db_path}", "db_not_found")

    uri = f"file:{quote(str(db_path))}?mode=ro"
    callbacks = 0

    try:
        connection = sqlite3.connect(uri, uri=True, timeout=5.0)
        connection.row_factory = None

        def authorizer(action: int, _arg1: str | None, _arg2: str | None, _db: str | None, _trigger: str | None) -> int:
            return sqlite3.SQLITE_DENY if action in DENIED_ACTIONS else sqlite3.SQLITE_OK

        def progress() -> int:
            nonlocal callbacks
            callbacks += 1
            return 1 if callbacks > MAX_VM_CALLBACKS else 0

        connection.set_authorizer(authorizer)
        connection.set_progress_handler(progress, 1_000)
        cursor = connection.execute(sql)
        columns = [item[0] for item in (cursor.description or [])]
        fetched = cursor.fetchmany(limit + 1)
        truncated = len(fetched) > limit
        rows = [[json_value(value) for value in row] for row in fetched[:limit]]
        payload = bounded_payload(columns, rows, truncated)
        payload["db"] = str(db_path.relative_to(project_root))
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except sqlite3.DatabaseError as exc:
        message = str(exc)
        code = "query_too_expensive" if "interrupted" in message.lower() else "sqlite_error"
        fail(message, code)
    finally:
        try:
            connection.close()  # type: ignore[name-defined]
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
