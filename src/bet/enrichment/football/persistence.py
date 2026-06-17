# ruff: noqa: E501
import hashlib
import json
import logging
import sqlite3
from datetime import UTC, datetime

from bet.enrichment.football.contracts import (
    AcquiredFixture,
    PersistFixtureResult,
    serialize_team_match_facts,
)
from bet.enrichment.football.parser import merge_completed_match_facts
from bet.enrichment.football.time import format_utc
from bet.integration.evidence import write_bundle_manifest

logger = logging.getLogger(__name__)

def resolve_domain_entity(
    conn: sqlite3.Connection,
    *,
    provider: str,
    sport: str,
    entity_type: str,
    provider_entity_id: str,
    expected_domain_table: str,
) -> int | None:
    res = resolve_domain_and_sports_entity(
        conn,
        provider=provider,
        sport=sport,
        entity_type=entity_type,
        provider_entity_id=provider_entity_id,
        expected_domain_table=expected_domain_table,
    )
    if res is None:
        return None
    return res[0]

def resolve_domain_and_sports_entity(
    conn: sqlite3.Connection,
    *,
    provider: str,
    sport: str,
    entity_type: str,
    provider_entity_id: str,
    expected_domain_table: str,
) -> tuple[int, int] | None:
    row = conn.execute(
        """SELECT se.domain_table, se.domain_entity_id, se.id
           FROM source_entity_reference ser
           JOIN sports_entity se ON ser.canonical_entity_id = se.id
           WHERE ser.provider = ?
             AND ser.provider_entity_id = ?
             AND ser.entity_type = ?
             AND ser.sport = ?
             AND ser.valid_to IS NULL
        """,
        (provider, provider_entity_id, entity_type, sport)
    ).fetchone()

    if not row:
        return None

    domain_table, domain_entity_id, sports_entity_id = row
    if domain_table != expected_domain_table:
        raise ValueError(f"Domain table mismatch: expected {expected_domain_table}, got {domain_table}")

    if expected_domain_table not in ("competitions", "teams", "fixtures"):
        raise ValueError(f"Unexpected domain table: {expected_domain_table}")

    exists = conn.execute(
        f"SELECT 1 FROM {expected_domain_table} WHERE id = ?",
        (domain_entity_id,)
    ).fetchone()

    if not exists:
        return None

    return domain_entity_id, sports_entity_id


class CanonicalPersistence:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _ensure_sport(self) -> int:
        row = self.conn.execute("SELECT id FROM sports WHERE name = 'football'").fetchone()
        if row:
            return row[0]
        res = self.conn.execute("INSERT INTO sports (name) VALUES ('football')")
        return res.lastrowid

    def _resolve_or_create_competition(self, provider_id: str, name: str, country: str | None, season: int) -> tuple[int, int]:
        res_ids = resolve_domain_and_sports_entity(
            self.conn,
            provider="api-football",
            sport="football",
            entity_type="COMPETITION",
            provider_entity_id=provider_id,
            expected_domain_table="competitions",
        )
        if res_ids is not None:
            return res_ids

        now_str = format_utc(datetime.now(UTC))
        res = self.conn.execute(
            "INSERT INTO competitions (sport_id, name, country, season) VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING",
            (self._ensure_sport(), name, country, season)
        )
        if res.rowcount == 0:
            comp_id = self.conn.execute(
                "SELECT id FROM competitions WHERE sport_id = ? AND name = ? AND season = ?",
                (self._ensure_sport(), name, season)
            ).fetchone()[0]
        else:
            comp_id = res.lastrowid

        ent_res = self.conn.execute(
            "INSERT INTO sports_entity (sport, entity_type, domain_table, domain_entity_id, created_at) VALUES ('football', 'COMPETITION', 'competitions', ?, ?)",
            (comp_id, now_str)
        )
        sports_ent_id = ent_res.lastrowid
        self.conn.execute(
            "INSERT INTO source_entity_reference (sport, entity_type, canonical_entity_id, provider, provider_entity_id, valid_from, verification_status, verification_method) VALUES ('football', 'COMPETITION', ?, 'api-football', ?, ?, 'VERIFIED', 'automatic')",
            (sports_ent_id, provider_id, now_str)
        )
        return comp_id, sports_ent_id

    def _resolve_or_create_team(self, provider_id: str, name: str) -> tuple[int, int]:
        res_ids = resolve_domain_and_sports_entity(
            self.conn,
            provider="api-football",
            sport="football",
            entity_type="TEAM",
            provider_entity_id=provider_id,
            expected_domain_table="teams",
        )
        if res_ids is not None:
            return res_ids

        now_str = format_utc(datetime.now(UTC))
        res = self.conn.execute(
            "INSERT INTO teams (sport_id, name) VALUES (?, ?)",
            (self._ensure_sport(), name)
        )
        team_id = res.lastrowid

        ent_res = self.conn.execute(
            "INSERT INTO sports_entity (sport, entity_type, domain_table, domain_entity_id, created_at) VALUES ('football', 'TEAM', 'teams', ?, ?)",
            (team_id, now_str)
        )
        sports_ent_id = ent_res.lastrowid
        self.conn.execute(
            "INSERT INTO source_entity_reference (sport, entity_type, canonical_entity_id, provider, provider_entity_id, valid_from, verification_status, verification_method) VALUES ('football', 'TEAM', ?, 'api-football', ?, ?, 'VERIFIED', 'automatic')",
            (sports_ent_id, provider_id, now_str)
        )
        return team_id, sports_ent_id

    def _resolve_or_create_fixture(self, provider_id: str, comp_id: int, home_id: int, away_id: int, kickoff_str: str, status: str, home_score: int, away_score: int, fetched_at: str) -> tuple[int, int]:
        res_ids = resolve_domain_and_sports_entity(
            self.conn,
            provider="api-football",
            sport="football",
            entity_type="EVENT",
            provider_entity_id=provider_id,
            expected_domain_table="fixtures",
        )
        if res_ids is not None:
            fix_id, sports_ent_id = res_ids
            self.conn.execute(
                "UPDATE fixtures SET status = ?, score_home = ?, score_away = ?, fetched_at = ? WHERE id = ?",
                (status, home_score, away_score, fetched_at, fix_id)
            )
            return fix_id, sports_ent_id

        res = self.conn.execute(
            "INSERT INTO fixtures (sport_id, competition_id, home_team_id, away_team_id, kickoff, status, score_home, score_away, source, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'api-football', ?)",
            (self._ensure_sport(), comp_id, home_id, away_id, kickoff_str, status, home_score, away_score, fetched_at)
        )
        fix_id = res.lastrowid

        self.conn.execute(
            "INSERT INTO fixture_sources (fixture_id, source, external_id, confidence, fetched_at) VALUES (?, 'api-football', ?, 1.0, ?)",
            (fix_id, provider_id, fetched_at)
        )

        now_str = format_utc(datetime.now(UTC))
        ent_res = self.conn.execute(
            "INSERT INTO sports_entity (sport, entity_type, domain_table, domain_entity_id, created_at) VALUES ('football', 'EVENT', 'fixtures', ?, ?)",
            (fix_id, now_str)
        )
        sports_ent_id = ent_res.lastrowid
        self.conn.execute(
            "INSERT INTO source_entity_reference (sport, entity_type, canonical_entity_id, provider, provider_entity_id, valid_from, verification_status, verification_method) VALUES ('football', 'EVENT', ?, 'api-football', ?, ?, 'VERIFIED', 'automatic')",
            (sports_ent_id, provider_id, now_str)
        )

        return fix_id, sports_ent_id

    def persist_acquired_fixture(
        self,
        *,
        acquired_fixture: "AcquiredFixture",
        scope_key: str,
        sync_run_id: int,
    ) -> "PersistFixtureResult":
        sp_name = f"persist_fixture_{acquired_fixture.fixture.provider_fixture_id}"
        self.conn.execute(f"SAVEPOINT {sp_name}")

        try:
            if acquired_fixture.acquisition_mode in ("TRANSIENT_FAILED", "RATE_LIMITED"):
                sync_state = acquired_fixture.acquisition_mode.value
                observed_at_str = format_utc(acquired_fixture.observed_at)
                self.conn.execute(
                    """UPDATE sports_sync_item
                       SET state = ?, last_sync_run_id = ?, updated_at = ?
                       WHERE provider = 'api-football' AND sport = 'football' AND scope_key = ? AND provider_fixture_id = ?
                    """,
                    (sync_state, sync_run_id, observed_at_str, scope_key, acquired_fixture.fixture.provider_fixture_id)
                )
                self.conn.execute(f"RELEASE SAVEPOINT {sp_name}")
                return PersistFixtureResult(
                    canonical_fixture_id=0,
                    canonical_event_entity_id=0,
                    canonical_home_team_id=0,
                    canonical_away_team_id=0,
                    observations_inserted=0,
                    observations_reused=0,
                    corrections_appended=0,
                    projections_updated=0,
                    sync_item_state=sync_state,
                    fixture_bundle_id=""
                )

            comp_id, comp_sports_ent_id = self._resolve_or_create_competition(
                acquired_fixture.fixture.provider_competition_id,
                acquired_fixture.fixture.competition_name,
                acquired_fixture.fixture.country,
                acquired_fixture.fixture.season
            )

            home_id, home_sports_ent_id = self._resolve_or_create_team(
                acquired_fixture.fixture.home_provider_team_id,
                acquired_fixture.fixture.home_team_name
            )
            away_id, away_sports_ent_id = self._resolve_or_create_team(
                acquired_fixture.fixture.away_provider_team_id,
                acquired_fixture.fixture.away_team_name
            )

            kickoff_str = format_utc(acquired_fixture.fixture.kickoff_at)
            observed_at_str = format_utc(acquired_fixture.observed_at)

            fix_id, sports_ent_id = self._resolve_or_create_fixture(
                acquired_fixture.fixture.provider_fixture_id,
                comp_id,
                home_id,
                away_id,
                kickoff_str,
                acquired_fixture.fixture.canonical_status,
                acquired_fixture.fixture.home_score,
                acquired_fixture.fixture.away_score,
                observed_at_str
            )

            evidence_refs = list(acquired_fixture.fixture_evidence_refs) + list(acquired_fixture.statistics_evidence_refs)

            local_bundle_id, _ = write_bundle_manifest(
                registered_source_key="api-football",
                projection_name="api-football-team-facts-v1",
                canonical_fixture_id=fix_id,
                parser_version="api-football-team-facts-v1",
                source_event_refs=[f"api-football:{acquired_fixture.fixture.provider_fixture_id}"],
                evidence_refs=evidence_refs
            )

            completed_facts = merge_completed_match_facts(
                acquired_fixture.fixture,
                acquired_fixture.statistics_by_provider_team_id,
                local_bundle_id,
                local_bundle_id
            )

            observations_inserted = 0
            observations_reused = 0
            corrections_appended = 0

            for team_facts in (completed_facts.home, completed_facts.away):
                local_team_id = home_id if team_facts.provider_team_id == acquired_fixture.fixture.home_provider_team_id else away_id

                payload_dict = serialize_team_match_facts(team_facts)
                payload_json = json.dumps(payload_dict, separators=(',', ':'), sort_keys=True)
                payload_sha256 = hashlib.sha256(payload_json.encode('utf-8')).hexdigest().lower()

                raw_identity_str = chr(0).join(["v1", "TEAM_MATCH_FACTS", "api-football", acquired_fixture.fixture.provider_fixture_id, team_facts.provider_team_id, payload_sha256])
                logical_identity = hashlib.sha256(raw_identity_str.encode('utf-8')).hexdigest().lower()


                obs_row = self.conn.execute(
                    "SELECT id FROM fixture_capability_observation WHERE logical_identity = ?",
                    (logical_identity,)
                ).fetchone()

                if obs_row:
                    observations_reused += 1
                else:
                    prior_row = self.conn.execute(
                        "SELECT id FROM fixture_capability_observation WHERE canonical_fixture_id = ? AND team_id = ? AND capability = 'TEAM_MATCH_FACTS'",
                        (fix_id, local_team_id)
                    ).fetchone()
                    if prior_row:
                        corrections_appended += 1
                    else:
                        observations_inserted += 1

                    obs_status = "SUCCESS"
                    parser_diagnostics = {}
                    if team_facts.completeness == "PARTIAL":
                        obs_status = "PARTIAL"
                    elif team_facts.completeness == "SCORE_ONLY":
                        obs_status = "PARTIAL"
                        parser_diagnostics = {"completeness": "SCORE_ONLY"}

                    parser_diagnostics_json = json.dumps(parser_diagnostics, separators=(',', ':'))

                    self.conn.execute(
                        """INSERT INTO fixture_capability_observation
                        (canonical_fixture_id, team_id, capability, source, request_identity, evidence_bundle_id, native_fixture_id, native_team_id, status, observed_at, valid_at, payload_sha256, payload_json, logical_identity, parser_version, parser_diagnostics_json)
                        VALUES (?, ?, 'TEAM_MATCH_FACTS', 'api-football', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'api-football-team-facts-v1', ?)
                        """,
                        (
                            fix_id, local_team_id,
                            f"api-football/fixture/{acquired_fixture.fixture.provider_fixture_id}",
                            local_bundle_id,
                            acquired_fixture.fixture.provider_fixture_id, team_facts.provider_team_id,
                            obs_status, observed_at_str, kickoff_str, payload_sha256, payload_json, logical_identity, parser_diagnostics_json
                        )
                    )

                metrics = {
                    "goals": team_facts.goals,
                    "shots": team_facts.shots,
                    "shots_on_target": team_facts.shots_on_target,
                    "possession": team_facts.possession_pct,
                    "fouls": team_facts.fouls,
                    "yellow_cards": team_facts.yellow_cards,
                    "red_cards": team_facts.red_cards,
                    "offsides": team_facts.offsides,
                    "corners": team_facts.corners,
                    "saves": team_facts.goalkeeper_saves,
                }

                for k, v in metrics.items():
                    if v is not None:
                        self.conn.execute(
                            """INSERT INTO match_stats (fixture_id, team_id, stat_key, stat_value, source, fetched_at)
                               VALUES (?, ?, ?, ?, 'api-football', ?)
                               ON CONFLICT(fixture_id, team_id, stat_key, source) DO UPDATE SET
                               stat_value=excluded.stat_value,
                               fetched_at=excluded.fetched_at,
                               source=excluded.source
                            """,
                            (fix_id, local_team_id, k, v, observed_at_str)
                        )

            # Sort facts by provider_team_id
            sorted_facts = sorted([completed_facts.home, completed_facts.away], key=lambda f: str(f.provider_team_id))
            facts_list = [serialize_team_match_facts(f) for f in sorted_facts]
            normalized_payload_json = json.dumps(facts_list, separators=(',', ':'), sort_keys=True)
            normalized_payload_sha256 = hashlib.sha256(normalized_payload_json.encode('utf-8')).hexdigest().lower()

            home_comp = completed_facts.home.completeness.value
            away_comp = completed_facts.away.completeness.value
            if home_comp == "COMPLETE" and away_comp == "COMPLETE":
                sync_state = "INGESTED_COMPLETE"
            elif home_comp == "SCORE_ONLY" and away_comp == "SCORE_ONLY":
                sync_state = "INGESTED_SCORE_ONLY"
            else:
                sync_state = "INGESTED_PARTIAL"

            self.conn.execute(
                """UPDATE sports_sync_item
                   SET canonical_fixture_id = ?, state = ?, fixture_evidence_bundle_id = ?, statistics_evidence_bundle_id = ?, normalized_payload_sha256 = ?, last_success_at = ?, last_sync_run_id = ?, updated_at = ?
                   WHERE provider = 'api-football' AND sport = 'football' AND scope_key = ? AND provider_fixture_id = ?
                """,
                (fix_id, sync_state, local_bundle_id, local_bundle_id, normalized_payload_sha256, observed_at_str, sync_run_id, observed_at_str, scope_key, acquired_fixture.fixture.provider_fixture_id)
            )

            self.conn.execute(f"RELEASE SAVEPOINT {sp_name}")

            return PersistFixtureResult(
                canonical_fixture_id=fix_id,
                canonical_event_entity_id=sports_ent_id,
                canonical_home_team_id=home_id,
                canonical_away_team_id=away_id,
                observations_inserted=observations_inserted,
                observations_reused=observations_reused,
                corrections_appended=corrections_appended,
                projections_updated=1,
                sync_item_state=sync_state,
                fixture_bundle_id=local_bundle_id
            )

        except Exception as e:
            self.conn.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")
            self.conn.execute(f"RELEASE SAVEPOINT {sp_name}")
            raise e
