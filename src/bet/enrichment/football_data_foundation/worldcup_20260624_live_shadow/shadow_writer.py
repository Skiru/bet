import json
import sqlite3
from pathlib import Path
from typing import Any, Dict

def write_shadow_json_and_sqlite(
    snapshot: Dict[str, Any],
    sqlite_path: Path,
    json_path: Path,
    diagnostics: Dict[str, Any]
) -> None:
    """
    Write normalized match snapshot to JSON and create/populate SQLite database
    in the exact same format and schema as source_bound_shadow/writer.py.
    """
    # 1. Write JSON
    json_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
    json_path.write_text(serialized, encoding="utf-8")

    # 2. Write SQLite
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(sqlite_path)
    try:
        # Create legacy tables
        con.execute("""
            CREATE TABLE IF NOT EXISTS shadow_match_snapshot (
                fixture_slug TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                production_selectable INTEGER NOT NULL,
                manual_authorization_required INTEGER NOT NULL,
                shadow_status TEXT NOT NULL
            )
        """)
        
        con.execute("""
            CREATE TABLE IF NOT EXISTS shadow_provider_ids (
                fixture_slug TEXT,
                provider TEXT NOT NULL,
                provider_match_id TEXT NOT NULL,
                PRIMARY KEY (fixture_slug, provider)
            )
        """)
        
        con.execute("""
            CREATE TABLE IF NOT EXISTS shadow_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fixture_slug TEXT,
                source TEXT NOT NULL,
                source_role TEXT NOT NULL,
                fact_type TEXT NOT NULL,
                key TEXT NOT NULL,
                value_json TEXT NOT NULL,
                body_sha256 TEXT NOT NULL,
                source_file TEXT NOT NULL
            )
        """)
        
        con.execute("""
            CREATE TABLE IF NOT EXISTS shadow_conflicts_diagnostics (
                fixture_slug TEXT PRIMARY KEY,
                conflicts_json TEXT NOT NULL,
                diagnostics_json TEXT NOT NULL
            )
        """)

        # Create required tables for PASS B2 activation-readiness
        con.execute("""
            CREATE TABLE IF NOT EXISTS snapshot_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS provider_ids (
                provider TEXT PRIMARY KEY,
                provider_id TEXT NOT NULL
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                fact_type TEXT NOT NULL,
                key TEXT NOT NULL,
                value_json TEXT NOT NULL
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS conflicts (
                value TEXT NOT NULL
            )
        """)

        fixture_slug = snapshot["fixture_slug"]
        shadow_status = snapshot["shadow_status"]
        prod_selectable = int(snapshot["production_selectable"])
        manual_auth = int(snapshot["manual_authorization_required"])

        # Insert shadow_match_snapshot (legacy)
        con.execute(
            "INSERT OR REPLACE INTO shadow_match_snapshot VALUES (?, ?, ?, ?, ?)",
            (
                fixture_slug,
                json.dumps(snapshot, sort_keys=True),
                prod_selectable,
                manual_auth,
                shadow_status
            )
        )

        # Insert shadow_provider_ids (legacy)
        for provider, provider_id in snapshot["provider_ids"].items():
            con.execute(
                "INSERT OR REPLACE INTO shadow_provider_ids VALUES (?, ?, ?)",
                (fixture_slug, provider, provider_id)
            )

        # Insert shadow_facts (legacy)
        con.execute("DELETE FROM shadow_facts WHERE fixture_slug = ?", (fixture_slug,))
        for fact in snapshot["facts"]:
            con.execute(
                """
                INSERT INTO shadow_facts (fixture_slug, source, source_role, fact_type, key, value_json, body_sha256, source_file)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fixture_slug,
                    fact["source"],
                    fact["source_role"],
                    fact["fact_type"],
                    fact["key"],
                    json.dumps(fact["value"], sort_keys=True),
                    fact["body_sha256"],
                    fact["source_file"]
                )
            )

        # Insert shadow_conflicts_diagnostics (legacy)
        con.execute(
            "INSERT OR REPLACE INTO shadow_conflicts_diagnostics VALUES (?, ?, ?)",
            (
                fixture_slug,
                json.dumps(snapshot["conflicts"], sort_keys=True),
                json.dumps(diagnostics, sort_keys=True)
            )
        )

        # Populate snapshot_metadata (new required)
        con.execute("INSERT OR REPLACE INTO snapshot_metadata VALUES (?, ?)", ("shadow_status", shadow_status))
        con.execute("INSERT OR REPLACE INTO snapshot_metadata VALUES (?, ?)", ("fixture_slug", fixture_slug))

        # Populate provider_ids (new required)
        con.execute("DELETE FROM provider_ids")
        for provider, provider_id in snapshot["provider_ids"].items():
            con.execute("INSERT OR REPLACE INTO provider_ids VALUES (?, ?)", (provider, provider_id))

        # Populate facts (new required)
        con.execute("DELETE FROM facts")
        for fact in snapshot["facts"]:
            con.execute(
                "INSERT INTO facts (source, fact_type, key, value_json) VALUES (?, ?, ?, ?)",
                (fact["source"], fact["fact_type"], fact["key"], json.dumps(fact["value"], sort_keys=True))
            )

        # Populate conflicts (new required)
        con.execute("DELETE FROM conflicts")
        if snapshot["conflicts"]:
            for conflict in snapshot["conflicts"]:
                con.execute("INSERT INTO conflicts (value) VALUES (?)", (json.dumps(conflict, sort_keys=True),))

        con.commit()
    finally:
        con.close()
