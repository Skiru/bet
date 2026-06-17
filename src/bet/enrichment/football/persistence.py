# ruff: noqa: E501
import hashlib
import json
import logging
import sqlite3
from datetime import UTC, datetime

from bet.enrichment.football.contracts import (
    FootballCompletedMatchFacts,
    serialize_team_match_facts,
)
from bet.enrichment.football.time import format_utc
from bet.integration.evidence import load_bundle_manifest

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

    def persist_completed_facts(self, facts: FootballCompletedMatchFacts, fetched_at: str, run_id: int) -> dict:
        def do_persist():
            comp_id, _ = self._resolve_or_create_competition(
                facts.fixture.provider_competition_id,
                facts.fixture.competition_name,
                facts.fixture.country,
                facts.fixture.season
            )
            home_id, _ = self._resolve_or_create_team(facts.fixture.home_provider_team_id, facts.fixture.home_team_name)
            away_id, _ = self._resolve_or_create_team(facts.fixture.away_provider_team_id, facts.fixture.away_team_name)

            kickoff_str = format_utc(facts.fixture.kickoff_at)
            fix_id, _ = self._resolve_or_create_fixture(
                facts.fixture.provider_fixture_id, comp_id, home_id, away_id, kickoff_str,
                facts.fixture.canonical_status, facts.fixture.home_score, facts.fixture.away_score, fetched_at
            )

            # Resolve observed_at from evidence manifest (max captured_at)
            max_captured_at = None
            bundle_ids = [facts.fixture_evidence_bundle_id, facts.statistics_evidence_bundle_id]
            for b_id in bundle_ids:
                if b_id:
                    try:
                        manifest = load_bundle_manifest(b_id)
                        for entry in manifest.get("entries", []):
                            if entry.captured_at:
                                if max_captured_at is None or entry.captured_at > max_captured_at:
                                    max_captured_at = entry.captured_at
                    except Exception:
                        pass
            observed_at_str = max_captured_at or fetched_at

            reused = 0
            inserted = 0

            for team_facts in (facts.home, facts.away):
                local_team_id = home_id if team_facts.provider_team_id == facts.fixture.home_provider_team_id else away_id

                payload_dict = serialize_team_match_facts(team_facts)
                payload_json = json.dumps(payload_dict, separators=(',', ':'), sort_keys=True)
                payload_sha256 = hashlib.sha256(payload_json.encode('utf-8')).hexdigest().lower()

                raw_identity_str = f"v1\x00TEAM_MATCH_FACTS\x00api-football\x00{facts.fixture.provider_fixture_id}\x00{team_facts.provider_team_id}\x00{payload_sha256}"
                logical_identity = hashlib.sha256(raw_identity_str.encode('utf-8')).hexdigest().lower()

                obs_row = self.conn.execute(
                    "SELECT id FROM fixture_capability_observation WHERE logical_identity = ?",
                    (logical_identity,)
                ).fetchone()

                if obs_row:
                    reused += 1
                else:
                    self.conn.execute(
                        """INSERT INTO fixture_capability_observation
                        (canonical_fixture_id, team_id, capability, source, request_identity, evidence_bundle_id, native_fixture_id, native_team_id, status, observed_at, valid_at, payload_sha256, payload_json, logical_identity)
                        VALUES (?, ?, 'TEAM_MATCH_FACTS', 'api-football', ?, ?, ?, ?, 'SUCCESS', ?, ?, ?, ?, ?)
                        """,
                        (
                            fix_id, local_team_id,
                            f"api-football/fixture/{facts.fixture.provider_fixture_id}",
                            facts.statistics_evidence_bundle_id or facts.fixture_evidence_bundle_id,
                            facts.fixture.provider_fixture_id, team_facts.provider_team_id,
                            observed_at_str, kickoff_str, payload_sha256, payload_json, logical_identity
                        )
                    )
                    inserted += 1

                # Compatibility projection names mapping
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
                            (fix_id, local_team_id, k, v, fetched_at)
                        )

            sync_state = "INGESTED_COMPLETE" if facts.home.completeness.value == "COMPLETE" and facts.away.completeness.value == "COMPLETE" else "INGESTED_PARTIAL"
            if facts.home.completeness.value == "SCORE_ONLY" and facts.away.completeness.value == "SCORE_ONLY":
                sync_state = "INGESTED_SCORE_ONLY"

            self.conn.execute(
                """UPDATE sports_sync_item
                   SET canonical_fixture_id = ?, state = ?, fixture_evidence_bundle_id = ?, statistics_evidence_bundle_id = ?, last_success_at = ?, last_sync_run_id = ?, updated_at = ?
                   WHERE provider = 'api-football' AND sport = 'football' AND provider_fixture_id = ?
                """,
                (fix_id, sync_state, facts.fixture_evidence_bundle_id, facts.statistics_evidence_bundle_id, fetched_at, run_id, fetched_at, facts.fixture.provider_fixture_id)
            )
            return {"inserted": inserted, "reused": reused, "sync_state": sync_state}

        sp_name = f"football_fixture_{facts.fixture.provider_fixture_id}"
        in_txn = self.conn.in_transaction
        if in_txn:
            self.conn.execute(f"SAVEPOINT {sp_name}")
            try:
                res_dict = do_persist()
                self.conn.execute(f"RELEASE SAVEPOINT {sp_name}")
                return res_dict
            except Exception as e:
                self.conn.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")
                self.conn.execute(f"RELEASE SAVEPOINT {sp_name}")
                raise e
        else:
            self.conn.execute("BEGIN TRANSACTION")
            try:
                res_dict = do_persist()
                self.conn.commit()
                return res_dict
            except Exception as e:
                self.conn.rollback()
                raise e
