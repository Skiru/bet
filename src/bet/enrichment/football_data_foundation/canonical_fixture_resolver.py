from __future__ import annotations

import datetime
import sqlite3
import json
from dataclasses import dataclass
from typing import Any, Mapping

from bet.enrichment.football_data_foundation.scanner_contracts import ScannerEventCandidate


@dataclass(frozen=True)
class CanonicalFixtureResolutionRequest:
    scanner_event: ScannerEventCandidate
    provider_id: str
    provider_event_id: str
    profile_id: str
    competition_scope: str
    season_scope: str
    evidence_identity: str
    schema_fingerprint: str


@dataclass(frozen=True)
class CanonicalFixtureResolutionResult:
    status: str
    scanner_event_id: str
    provider_event_id: str
    sport_id: int | None
    competition_id: int | None
    home_team_id: int | None
    away_team_id: int | None
    fixture_id: int | None
    sports_entity_event_id: int | None
    source_reference_ids: tuple[int, ...]
    fixture_source_ids: tuple[int, ...]
    diagnostics: Mapping[str, Any]


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    """Check if a table exists in the database."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def resolve_canonical_fixture(
    conn: sqlite3.Connection, request: CanonicalFixtureResolutionRequest
) -> CanonicalFixtureResolutionResult:
    """Resolve a scanner event and provider evidence to a canonical fixture,
    inserting or matching rows in a temporary SQLite store.
    """
    scanner_event = request.scanner_event
    scanner_event_id = scanner_event.scanner_event_id
    provider_event_id = request.provider_event_id
    provider_id = request.provider_id
    scanner_source = scanner_event.scanner_source

    diagnostics: dict[str, Any] = {}

    try:
        # 1. Sport
        cursor = conn.execute(
            "SELECT id FROM sports WHERE name = ?", (scanner_event.sport,)
        )
        row = cursor.fetchone()
        if row:
            sport_id = row[0]
        else:
            # Create sport
            cursor = conn.execute(
                "INSERT INTO sports (name, tier, stat_keys) VALUES (?, ?, ?)",
                (scanner_event.sport, 1, "[]"),
            )
            sport_id = cursor.lastrowid

        # 2. Competition
        # Query by name = competition_scope and season = season_scope
        cursor = conn.execute(
            "SELECT id FROM competitions WHERE sport_id = ? AND name = ? AND season = ?",
            (sport_id, request.competition_scope, request.season_scope),
        )
        row = cursor.fetchone()
        if row:
            competition_id = row[0]
        else:
            # Create competition
            cursor = conn.execute(
                "INSERT INTO competitions (sport_id, name, country, importance, season) VALUES (?, ?, ?, ?, ?)",
                (
                    sport_id,
                    request.competition_scope,
                    scanner_event.group_label or "World",
                    3,
                    request.season_scope,
                ),
            )
            competition_id = cursor.lastrowid

        # 3. Teams (Home/Away)
        # Helper to find or create a team
        def find_or_create_team(team_name: str) -> int:
            # Direct match
            cursor = conn.execute(
                "SELECT id FROM teams WHERE sport_id = ? AND name = ?",
                (sport_id, team_name),
            )
            team_row = cursor.fetchone()
            if team_row:
                return team_row[0]

            # Alias match if table exists
            if table_exists(conn, "team_source_aliases"):
                cursor = conn.execute(
                    "SELECT team_id FROM team_source_aliases WHERE sport_id = ? AND provider_team_name = ?",
                    (sport_id, team_name),
                )
                alias_row = cursor.fetchone()
                if alias_row:
                    return alias_row[0]

            # Otherwise, create team
            cursor = conn.execute(
                "INSERT INTO teams (sport_id, name, aliases, country, style_tags) VALUES (?, ?, ?, ?, ?)",
                (sport_id, team_name, "[]", None, "[]"),
            )
            return cursor.lastrowid

        home_team_id = find_or_create_team(scanner_event.home_team_name)
        away_team_id = find_or_create_team(scanner_event.away_team_name)

        if home_team_id == away_team_id:
            return CanonicalFixtureResolutionResult(
                status="TEAM_MAPPING_AMBIGUOUS",
                scanner_event_id=scanner_event_id,
                provider_event_id=provider_event_id,
                sport_id=sport_id,
                competition_id=competition_id,
                home_team_id=home_team_id,
                away_team_id=away_team_id,
                fixture_id=None,
                sports_entity_event_id=None,
                source_reference_ids=(),
                fixture_source_ids=(),
                diagnostics={"error": "Home and away teams mapped to the same ID"},
            )

        # 4. Resolve Canonical Fixture
        # Check fixture_sources mappings
        mapped_fixture_ids = set()

        # Scanner source ref lookup
        cursor = conn.execute(
            "SELECT fixture_id FROM fixture_sources WHERE source = ? AND external_id = ?",
            (scanner_source, scanner_event_id),
        )
        scanner_ref_row = cursor.fetchone()
        if scanner_ref_row:
            mapped_fixture_ids.add(scanner_ref_row[0])

        # Provider source ref lookup
        cursor = conn.execute(
            "SELECT fixture_id FROM fixture_sources WHERE source = ? AND external_id = ?",
            (provider_id, provider_event_id),
        )
        provider_ref_row = cursor.fetchone()
        if provider_ref_row:
            mapped_fixture_ids.add(provider_ref_row[0])

        if len(mapped_fixture_ids) > 1:
            # Different fixture_ids for scanner vs provider -> Ambiguous Match!
            return CanonicalFixtureResolutionResult(
                status="AMBIGUOUS_FIXTURE_MATCH",
                scanner_event_id=scanner_event_id,
                provider_event_id=provider_event_id,
                sport_id=sport_id,
                competition_id=competition_id,
                home_team_id=home_team_id,
                away_team_id=away_team_id,
                fixture_id=None,
                sports_entity_event_id=None,
                source_reference_ids=(),
                fixture_source_ids=(),
                diagnostics={"error": "Scanner and provider event mapped to different canonical fixtures"},
            )

        mapped_fixture_id = list(mapped_fixture_ids)[0] if mapped_fixture_ids else None

        # Look up by natural unique constraint (sport_id, home_team_id, away_team_id, kickoff)
        cursor = conn.execute(
            "SELECT id FROM fixtures WHERE sport_id = ? AND home_team_id = ? AND away_team_id = ? AND kickoff = ?",
            (sport_id, home_team_id, away_team_id, scanner_event.kickoff_utc),
        )
        natural_row = cursor.fetchone()
        natural_fixture_id = natural_row[0] if natural_row else None

        # Safety Check: Conflict between mapped_fixture_id and natural_fixture_id
        if (
            mapped_fixture_id is not None
            and natural_fixture_id is not None
            and mapped_fixture_id != natural_fixture_id
        ):
            return CanonicalFixtureResolutionResult(
                status="AMBIGUOUS_FIXTURE_MATCH",
                scanner_event_id=scanner_event_id,
                provider_event_id=provider_event_id,
                sport_id=sport_id,
                competition_id=competition_id,
                home_team_id=home_team_id,
                away_team_id=away_team_id,
                fixture_id=None,
                sports_entity_event_id=None,
                source_reference_ids=(),
                fixture_source_ids=(),
                diagnostics={
                    "error": "Source-mapped fixture ID does not match natural teams/kickoff fixture ID",
                    "mapped_fixture_id": mapped_fixture_id,
                    "natural_fixture_id": natural_fixture_id,
                },
            )

        fixture_id = mapped_fixture_id or natural_fixture_id
        
        if fixture_id is not None:
            cursor = conn.execute(
                "SELECT home_team_id, away_team_id FROM fixtures WHERE id = ?",
                (fixture_id,),
            )
            f_row = cursor.fetchone()
            if f_row:
                f_home, f_away = f_row[0], f_row[1]
                if f_home != home_team_id or f_away != away_team_id:
                    return CanonicalFixtureResolutionResult(
                        status="AMBIGUOUS_FIXTURE_MATCH",
                        scanner_event_id=scanner_event_id,
                        provider_event_id=provider_event_id,
                        sport_id=sport_id,
                        competition_id=competition_id,
                        home_team_id=home_team_id,
                        away_team_id=away_team_id,
                        fixture_id=None,
                        sports_entity_event_id=None,
                        source_reference_ids=(),
                        fixture_source_ids=(),
                        diagnostics={
                            "error": f"Mapped fixture {fixture_id} has teams ({f_home}, {f_away}) but request resolved to ({home_team_id}, {away_team_id})",
                            "mapped_fixture_id": fixture_id,
                        },
                    )

        status = "MATCHED_EXISTING_FIXTURE" if fixture_id is not None else "CREATED_CANONICAL_FIXTURE"

        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if fixture_id is None:
            # Create new canonical fixture
            cursor = conn.execute(
                "INSERT INTO fixtures (sport_id, competition_id, home_team_id, away_team_id, kickoff, status, fetched_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    sport_id,
                    competition_id,
                    home_team_id,
                    away_team_id,
                    scanner_event.kickoff_utc,
                    "scheduled",
                    now_str,
                ),
            )
            fixture_id = cursor.lastrowid

        # 5. Upsert fixture_sources rows
        fixture_source_ids: list[int] = []
        for src, ext_id in [
            (scanner_source, scanner_event_id),
            (provider_id, provider_event_id),
        ]:
            cursor = conn.execute(
                "SELECT id FROM fixture_sources WHERE fixture_id = ? AND source = ?",
                (fixture_id, src),
            )
            fs_row = cursor.fetchone()
            if fs_row:
                fixture_source_ids.append(fs_row[0])
            else:
                cursor = conn.execute(
                    "INSERT INTO fixture_sources (fixture_id, source, external_id, confidence, fetched_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (fixture_id, src, ext_id, 1.0, now_str),
                )
                fixture_source_ids.append(cursor.lastrowid)

        # 6. Upsert sports_entity row for canonical fixture event if table exists
        sports_entity_event_id = None
        if table_exists(conn, "sports_entity"):
            cursor = conn.execute(
                "SELECT id FROM sports_entity WHERE sport = ? AND entity_type = ? AND domain_table = ? AND domain_entity_id = ?",
                ("football", "fixture", "fixtures", fixture_id),
            )
            se_row = cursor.fetchone()
            if se_row:
                sports_entity_event_id = se_row[0]
            else:
                cursor = conn.execute(
                    "INSERT INTO sports_entity (sport, entity_type, domain_table, domain_entity_id, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    ("football", "fixture", "fixtures", fixture_id, now_str),
                )
                sports_entity_event_id = cursor.lastrowid

        # 7. Upsert source_entity_reference rows if table exists and sports_entity exists
        source_reference_ids: list[int] = []
        if sports_entity_event_id is not None and table_exists(conn, "source_entity_reference"):
            for provider, provider_entity_id in [
                (scanner_source, scanner_event_id),
                (provider_id, provider_event_id),
            ]:
                cursor = conn.execute(
                    "SELECT id FROM source_entity_reference "
                    "WHERE sport = ? AND entity_type = ? AND canonical_entity_id = ? AND provider = ? AND provider_entity_id = ?",
                    ("football", "fixture", sports_entity_event_id, provider, provider_entity_id),
                )
                ser_row = cursor.fetchone()
                if ser_row:
                    source_reference_ids.append(ser_row[0])
                else:
                    cursor = conn.execute(
                        "INSERT INTO source_entity_reference "
                        "(sport, entity_type, canonical_entity_id, provider, provider_entity_id, valid_from, verification_status, verification_method) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            "football",
                            "fixture",
                            sports_entity_event_id,
                            provider,
                            provider_entity_id,
                            now_str,
                            "verified",
                            "automated",
                        ),
                    )
                    source_reference_ids.append(cursor.lastrowid)

        return CanonicalFixtureResolutionResult(
            status=status,
            scanner_event_id=scanner_event_id,
            provider_event_id=provider_event_id,
            sport_id=sport_id,
            competition_id=competition_id,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            fixture_id=fixture_id,
            sports_entity_event_id=sports_entity_event_id,
            source_reference_ids=tuple(source_reference_ids),
            fixture_source_ids=tuple(fixture_source_ids),
            diagnostics=diagnostics,
        )

    except Exception as e:
        return CanonicalFixtureResolutionResult(
            status="DB_MAPPING_BLOCKED",
            scanner_event_id=scanner_event_id,
            provider_event_id=provider_event_id,
            sport_id=None,
            competition_id=None,
            home_team_id=None,
            away_team_id=None,
            fixture_id=None,
            sports_entity_event_id=None,
            source_reference_ids=(),
            fixture_source_ids=(),
            diagnostics={"error": str(e)},
        )
