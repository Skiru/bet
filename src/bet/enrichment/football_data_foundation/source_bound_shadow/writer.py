import json
import sqlite3
from pathlib import Path
from typing import Any, Dict
from .contracts import NormalizedMatchSnapshot

def write_shadow_json(snapshot: NormalizedMatchSnapshot, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(snapshot.to_json(), indent=2, sort_keys=True) + "\n"
    path.write_text(content, encoding="utf-8")

def write_shadow_sqlite(
    snapshot: NormalizedMatchSnapshot,
    path: Path,
    diagnostics: Dict[str, Any]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    
    con = sqlite3.connect(path)
    try:
        # Create legacy/original tables to ensure writer tests pass
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

        # Create new required tables for PASS B2 activation-readiness
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
        
        # Insert snapshot metadata (original)
        con.execute(
            "INSERT OR REPLACE INTO shadow_match_snapshot VALUES (?, ?, ?, ?, ?)",
            (
                snapshot.fixture_slug,
                json.dumps(snapshot.to_json(), sort_keys=True),
                int(snapshot.production_selectable),
                int(snapshot.manual_authorization_required),
                snapshot.shadow_status
            )
        )
        
        # Insert provider IDs (original)
        for provider, provider_id in snapshot.provider_ids.items():
            con.execute(
                "INSERT OR REPLACE INTO shadow_provider_ids VALUES (?, ?, ?)",
                (snapshot.fixture_slug, provider, provider_id)
            )
            
        # Insert facts (original)
        con.execute("DELETE FROM shadow_facts WHERE fixture_slug = ?", (snapshot.fixture_slug,))
        for fact in snapshot.facts:
            con.execute(
                """
                INSERT INTO shadow_facts (fixture_slug, source, source_role, fact_type, key, value_json, body_sha256, source_file)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.fixture_slug,
                    fact.source,
                    fact.source_role,
                    fact.fact_type,
                    fact.key,
                    json.dumps(fact.value, sort_keys=True),
                    fact.body_sha256,
                    fact.source_file
                )
            )
            
        # Insert conflicts and diagnostics (original)
        con.execute(
            "INSERT OR REPLACE INTO shadow_conflicts_diagnostics VALUES (?, ?, ?)",
            (
                snapshot.fixture_slug,
                json.dumps(snapshot.conflicts, sort_keys=True),
                json.dumps(diagnostics, sort_keys=True)
            )
        )

        # Populate snapshot_metadata (new required)
        con.execute("INSERT OR REPLACE INTO snapshot_metadata VALUES (?, ?)", ("shadow_status", snapshot.shadow_status))
        con.execute("INSERT OR REPLACE INTO snapshot_metadata VALUES (?, ?)", ("fixture_slug", snapshot.fixture_slug))

        # Populate provider_ids (new required)
        con.execute("DELETE FROM provider_ids")
        for provider, provider_id in snapshot.provider_ids.items():
            con.execute("INSERT OR REPLACE INTO provider_ids VALUES (?, ?)", (provider, provider_id))

        # Populate facts (new required)
        con.execute("DELETE FROM facts")
        for fact in snapshot.facts:
            con.execute(
                "INSERT INTO facts (source, fact_type, key, value_json) VALUES (?, ?, ?, ?)",
                (fact.source, fact.fact_type, fact.key, json.dumps(fact.value, sort_keys=True))
            )

        # Populate conflicts (new required)
        con.execute("DELETE FROM conflicts")
        if snapshot.conflicts:
            for conflict in snapshot.conflicts:
                con.execute("INSERT INTO conflicts (value) VALUES (?)", (json.dumps(conflict, sort_keys=True),))
        else:
            # Let's ensure conflicts exists even if empty, no rows is allowed if no conflicts exist
            pass
        
        con.commit()
    finally:
        con.close()
