from __future__ import annotations

import datetime
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from bet.enrichment.football_data_foundation.scanner_contracts import (
    ScannerEventCandidate,
)


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
    inserting or matching rows in a temporary SQLite store. This resolver
    is physically normalized to satisfy strict schema constraints.
    """
    scanner_event = request.scanner_event
    scanner_event_id = scanner_event.scanner_event_id
    provider_event_id = request.provider_event_id
    provider_id = request.provider_id
    scanner_source = scanner_event.scanner_source
    sport_name = scanner_event.sport

    diagnostics: dict[str, Any] = {}

    try:
        # 1. Sport
        cursor = conn.execute(
            "SELECT id FROM sports WHERE name = ?", (sport_name,)
        )
        row = cursor.fetchone()
        if row:
            sport_id = row[0]
        else:
            # Create sport
            cursor = conn.execute(
                "INSERT INTO sports (name, tier, stat_keys) VALUES (?, ?, ?)",
                (sport_name, 1, "[]"),
            )
            sport_id = cursor.lastrowid

        # 2. Competition
        # competition.country must not store group_label such as Group D
        country_val = None
        if scanner_event.group_label and not (
            scanner_event.group_label.startswith("Group ")
            or (
                len(scanner_event.group_label) == 7
                and scanner_event.group_label.startswith("Group")
            )
        ):
            country_val = scanner_event.group_label

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
                "INSERT INTO competitions (sport_id, name, country, importance, season) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    sport_id,
                    request.competition_scope,
                    country_val,
                    3,
                    request.season_scope,
                ),
            )
            competition_id = cursor.lastrowid

        # 3. Teams (Home/Away)
        # Helper to find or create a team
        def find_or_create_team(team_name: str) -> int | str:
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
                    "SELECT team_id, source, status, provider_competition_hint "
                    "FROM team_source_aliases "
                    "WHERE sport_id = ? AND provider_team_name = ?",
                    (sport_id, team_name),
                )
                alias_rows = cursor.fetchall()
                if alias_rows:
                    # Filter by status: verified or accepted
                    status_filtered = [r for r in alias_rows if r[2] in ("verified", "accepted")]
                    if status_filtered:
                        alias_rows = status_filtered

                    # Filter by provider or competition hint
                    best_rows = []
                    for r in alias_rows:
                        t_id, src, stat, comp_hint = r
                        source_matches = (src == provider_id or src == scanner_source)
                        comp_matches = False
                        if comp_hint and request.competition_scope:
                            comp_matches = (
                                comp_hint in request.competition_scope
                                or request.competition_scope in comp_hint
                            )
                        if source_matches or comp_matches:
                            best_rows.append(r)

                    if best_rows:
                        alias_rows = best_rows

                    unique_ids = list(set(r[0] for r in alias_rows))
                    if len(unique_ids) > 1:
                        return "TEAM_ALIAS_AMBIGUOUS"
                    elif len(unique_ids) == 1:
                        return unique_ids[0]

            # Otherwise, create team (only under scanner context, which we have)
            cursor = conn.execute(
                "INSERT INTO teams (sport_id, name, aliases, country, style_tags) "
                "VALUES (?, ?, ?, ?, ?)",
                (sport_id, team_name, "[]", None, "[]"),
            )
            return cursor.lastrowid

        home_res = find_or_create_team(scanner_event.home_team_name)
        away_res = find_or_create_team(scanner_event.away_team_name)

        if home_res == "TEAM_ALIAS_AMBIGUOUS" or away_res == "TEAM_ALIAS_AMBIGUOUS":
            return CanonicalFixtureResolutionResult(
                status="TEAM_ALIAS_AMBIGUOUS",
                scanner_event_id=scanner_event_id,
                provider_event_id=provider_event_id,
                sport_id=sport_id,
                competition_id=competition_id,
                home_team_id=None,
                away_team_id=None,
                fixture_id=None,
                sports_entity_event_id=None,
                source_reference_ids=(),
                fixture_source_ids=(),
                diagnostics={
                    "error": "Team name resolves to ambiguous aliases",
                    "category": "TEAM_ALIAS_AMBIGUOUS",
                },
            )

        home_team_id: int = home_res  # type: ignore
        away_team_id: int = away_res  # type: ignore

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
                diagnostics={
                    "error": "Home and away teams mapped to the same ID",
                    "category": "TEAM_MAPPING_AMBIGUOUS",
                },
            )

        # 4. Resolve Canonical Fixture
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
                    "error": "Scanner and provider event mapped to different canonical fixtures",
                    "category": "COMPETITION_MAPPING_AMBIGUOUS",
                },
            )

        mapped_fixture_id = list(mapped_fixture_ids)[0] if mapped_fixture_ids else None

        # Look up by natural unique constraint (sport_id, home_team_id, away_team_id, kickoff)
        cursor = conn.execute(
            "SELECT id, competition_id FROM fixtures "
            "WHERE sport_id = ? AND home_team_id = ? AND away_team_id = ? AND kickoff = ?",
            (sport_id, home_team_id, away_team_id, scanner_event.kickoff_utc),
        )
        natural_rows = cursor.fetchall()
        if len(natural_rows) > 1:
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
                    "error": "Natural fixture lookup is ambiguous because of multi-competition match",
                    "category": "COMPETITION_MAPPING_AMBIGUOUS",
                },
            )

        natural_fixture_id = natural_rows[0][0] if natural_rows else None

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
                    "error": "Source-mapped fixture ID does not match natural fixture ID",
                    "mapped_fixture_id": mapped_fixture_id,
                    "natural_fixture_id": natural_fixture_id,
                    "category": "COMPETITION_MAPPING_AMBIGUOUS",
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
                            "error": f"Mapped fixture {fixture_id} has mismatched teams",
                            "mapped_fixture_id": fixture_id,
                            "category": "COMPETITION_MAPPING_AMBIGUOUS",
                        },
                    )

        status = "MATCHED_EXISTING_FIXTURE" if fixture_id is not None else "CREATED_CANONICAL_FIXTURE"

        now_str = datetime.datetime.now(datetime.UTC).isoformat()

        if fixture_id is None:
            # Create new canonical fixture
            cursor = conn.execute(
                "INSERT INTO fixtures (sport_id, competition_id, home_team_id, away_team_id, "
                "kickoff, status, fetched_at) "
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
                "SELECT id, external_id FROM fixture_sources WHERE fixture_id = ? AND source = ?",
                (fixture_id, src),
            )
            fs_row = cursor.fetchone()
            if fs_row:
                existing_ext_id = fs_row[1]
                if existing_ext_id != ext_id:
                    return CanonicalFixtureResolutionResult(
                        status="SOURCE_EXTERNAL_ID_CONFLICT",
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
                            "error": "Existing fixture_source maps to different external_id",
                            "category": "SOURCE_EXTERNAL_ID_CONFLICT",
                        },
                    )
                fixture_source_ids.append(fs_row[0])
            else:
                # Double-check that this (source, external_id) is not mapped to a different fixture
                cursor = conn.execute(
                    "SELECT fixture_id FROM fixture_sources WHERE source = ? AND external_id = ?",
                    (src, ext_id),
                )
                existing_fs = cursor.fetchone()
                if existing_fs and existing_fs[0] != fixture_id:
                    return CanonicalFixtureResolutionResult(
                        status="SOURCE_EXTERNAL_ID_CONFLICT",
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
                            "error": f"Source/external_id mapped to different fixture {existing_fs[0]}",
                            "category": "SOURCE_EXTERNAL_ID_CONFLICT",
                        },
                    )

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
                "SELECT id FROM sports_entity "
                "WHERE sport = ? AND entity_type = ? AND domain_table = ? AND domain_entity_id = ?",
                (sport_name, "fixture", "fixtures", fixture_id),
            )
            se_row = cursor.fetchone()
            if se_row:
                sports_entity_event_id = se_row[0]
            else:
                cursor = conn.execute(
                    "INSERT INTO sports_entity (sport, entity_type, domain_table, domain_entity_id, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (sport_name, "fixture", "fixtures", fixture_id, now_str),
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
                    "WHERE sport = ? AND entity_type = ? AND canonical_entity_id = ? "
                    "AND provider = ? AND provider_entity_id = ?",
                    (sport_name, "fixture", sports_entity_event_id, provider, provider_entity_id),
                )
                ser_row = cursor.fetchone()
                if ser_row:
                    source_reference_ids.append(ser_row[0])
                else:
                    cursor = conn.execute(
                        "INSERT INTO source_entity_reference "
                        "(sport, entity_type, canonical_entity_id, provider, provider_entity_id, "
                        "valid_from, verification_status, verification_method) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            sport_name,
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
            status="SCHEMA_CONSTRAINT_BLOCKED",
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
            diagnostics={
                "error": str(e),
                "category": "SCHEMA_CONSTRAINT_BLOCKED",
            },
        )
