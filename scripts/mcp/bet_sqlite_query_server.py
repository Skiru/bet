#!/usr/bin/env python3
"""Read-only MCP server exposing the repository's canonical SQLite database."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from bet.db.connection import get_readonly_db  # noqa: E402

READ_ONLY_START = re.compile(r"^\s*(select|with|explain|pragma)\b", re.IGNORECASE)
WRITE_WORD = re.compile(
    r"\b(insert|update|delete|replace|alter|create|drop|attach|detach|reindex|vacuum|pragma\s+[^(\s]+\s*=)\b",
    re.IGNORECASE,
)


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    return value


def _validate_query(query: str) -> str:
    normalized = query.strip()
    if WRITE_WORD.search(normalized):
        raise ValueError("Mutating SQL is not allowed")
    if not normalized or not READ_ONLY_START.match(normalized):
        raise ValueError(
            "Only SELECT, WITH, EXPLAIN, and read-only PRAGMA queries are allowed"
        )
    if ";" in normalized.rstrip(";"):
        raise ValueError("Multiple SQL statements are not allowed")
    return normalized.rstrip(";").strip()


def _authorizer(
    action: int,
    _arg1: str | None,
    _arg2: str | None,
    _db: str | None,
    _source: str | None,
) -> int:
    denied = {
        sqlite3.SQLITE_INSERT,
        sqlite3.SQLITE_UPDATE,
        sqlite3.SQLITE_DELETE,
        sqlite3.SQLITE_CREATE_INDEX,
        sqlite3.SQLITE_CREATE_TABLE,
        sqlite3.SQLITE_CREATE_TEMP_INDEX,
        sqlite3.SQLITE_CREATE_TEMP_TABLE,
        sqlite3.SQLITE_CREATE_TRIGGER,
        sqlite3.SQLITE_CREATE_VIEW,
        sqlite3.SQLITE_CREATE_TEMP_TRIGGER,
        sqlite3.SQLITE_CREATE_TEMP_VIEW,
        sqlite3.SQLITE_DROP_INDEX,
        sqlite3.SQLITE_DROP_TABLE,
        sqlite3.SQLITE_DROP_TEMP_INDEX,
        sqlite3.SQLITE_DROP_TEMP_TABLE,
        sqlite3.SQLITE_DROP_TRIGGER,
        sqlite3.SQLITE_DROP_VIEW,
        sqlite3.SQLITE_DROP_TEMP_TRIGGER,
        sqlite3.SQLITE_DROP_TEMP_VIEW,
        sqlite3.SQLITE_ATTACH,
        sqlite3.SQLITE_DETACH,
        sqlite3.SQLITE_ALTER_TABLE,
        sqlite3.SQLITE_TRANSACTION,
        sqlite3.SQLITE_PRAGMA,
    }
    return sqlite3.SQLITE_DENY if action in denied else sqlite3.SQLITE_OK


def query_database(
    query: str, parameters: dict[str, Any] | list[Any] | None = None
) -> dict[str, Any]:
    """Execute one bounded read-only query and return rows plus a provenance receipt."""
    sql = _validate_query(query)
    bind: dict[str, Any] | list[Any] = parameters or {}
    db_path = os.environ.get("BET_DB_PATH") or str(
        ROOT / "betting" / "data" / "betting.db"
    )
    with get_readonly_db(db_path) as conn:
        conn.set_authorizer(_authorizer)
        cursor = conn.execute(sql, bind)
        columns = [column[0] for column in cursor.description or ()]
        rows = [[_json_value(value) for value in row] for row in cursor.fetchall()]
    result = {"columns": columns, "rows": rows, "row_count": len(rows)}
    result_json = json.dumps(
        result, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    result["receipt"] = {
        "query_id": f"dbq_{uuid.uuid4().hex}",
        "query_purpose": "read_only_agent_database_query",
        "query_sql": sql,
        "row_count": len(rows),
        "executed_at": datetime.now().astimezone().isoformat(),
        "result_sha256": hashlib.sha256(result_json.encode()).hexdigest(),
        "provenance_level": "AGENT_ATTESTED_TOOL_RESULT",
    }
    return result


TOOL = {
    "name": "bet_sqlite_query",
    "description": (
        "Run one read-only, parameterized SQL query against the configured "
        "betting SQLite database."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "One SELECT/WITH/EXPLAIN/read-only PRAGMA statement.",
            },
            "parameters": {
                "type": "object",
                "additionalProperties": True,
                "description": (
                    "Named SQL parameters, for example {\"sport\": \"football\"}."
                ),
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}


def handle(message: dict[str, Any]) -> dict[str, Any] | None:
    request_id = message.get("id")
    method = message.get("method")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "bet-sqlite-query", "version": "1.0.0"},
            },
        }
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": [TOOL]}}
    if method == "tools/call":
        try:
            arguments = message.get("params", {}).get("arguments", {})
            result = query_database(arguments["query"], arguments.get("parameters"))
            text = json.dumps(result, ensure_ascii=True)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": text}],
                    "isError": False,
                },
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": f"DB_QUERY_BLOCKED: {exc}"}],
                    "isError": True,
                },
            }
    if request_id is not None:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }
    return None


def main() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        response = handle(json.loads(line))
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=True) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
