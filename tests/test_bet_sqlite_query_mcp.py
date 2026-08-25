from __future__ import annotations

import sqlite3

import pytest

from scripts.mcp.bet_sqlite_query_server import query_database


def test_query_database_is_read_only_and_parameterized(tmp_path, monkeypatch):
    db_path = tmp_path / "betting.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE teams (name TEXT, sport TEXT)")
        conn.execute("INSERT INTO teams VALUES (?, ?)", ("Example FC", "football"))
    monkeypatch.setenv("BET_DB_PATH", str(db_path))

    result = query_database(
        "SELECT name, sport FROM teams WHERE sport = :sport", {"sport": "football"}
    )

    assert result["rows"] == [["Example FC", "football"]]
    assert result["receipt"]["row_count"] == 1

    with pytest.raises(ValueError, match="Mutating SQL"):
        query_database("DELETE FROM teams")


def test_query_database_rejects_multiple_statements_and_attach(tmp_path, monkeypatch):
    db_path = tmp_path / "betting.db"
    sqlite3.connect(db_path).close()
    monkeypatch.setenv("BET_DB_PATH", str(db_path))

    with pytest.raises(ValueError, match="Multiple SQL statements"):
        query_database("SELECT 1; SELECT 2")
    with pytest.raises(ValueError, match="Mutating SQL"):
        query_database("ATTACH DATABASE 'other.db' AS other")
