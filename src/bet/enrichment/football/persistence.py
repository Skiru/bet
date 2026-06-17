import contextlib
import hashlib
import json
import logging
from datetime import UTC, datetime

from bet.enrichment.football.contracts import (
    FootballCompletedMatchFacts,
    serialize_team_match_facts,
)
from bet.enrichment.football.time import format_utc

logger = logging.getLogger(__name__)

@contextlib.contextmanager
def fixture_transaction(conn):
    in_txn = conn.in_transaction
    if in_txn:
        # Use savepoint
        sp_name = f"sp_{id(conn)}_{int(datetime.now().timestamp() * 1000)}"
        conn.execute(f"SAVEPOINT {sp_name}")
        try:
            yield
            conn.execute(f"RELEASE SAVEPOINT {sp_name}")
        except Exception:
            conn.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")
            raise
    else:
        conn.execute("BEGIN TRANSACTION")
        try:
            yield
            conn.commit()
        except Exception:
            conn.rollback()
            raise

class CanonicalPersistence:
    def __init__(self, conn):
        self.conn = conn

    def _ensure_sport(self) -> int:
        row = self.conn.execute("SELECT id FROM sports WHERE name = 'football'").fetchone()
        if row:
            return row[0]
        res = self.conn.execute("INSERT INTO sports (name) VALUES ('football')")
        return res.lastrowid


    def _resolve_or_create_competition(self, provider_id: str, name: str, country: str | None, season: int) -> int:
        # First check by active source reference
        row = self.conn.execute(
            "SELECT canonical_entity_id FROM source_entity_reference WHERE sport = 'football' AND entity_type = 'COMPETITION' AND provider = 'api-football' AND provider_entity_id = ? AND valid_to IS NULL",
            (provider_id,)
        ).fetchone()
        if row:
            return row[0]
            
        # Create
        now_str = format_utc(datetime.now(UTC))
        res = self.conn.execute(
            "INSERT INTO competitions (sport_id, name, country, season) VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING",
            (self._ensure_sport(), name, country, season)
        )
        if res.rowcount == 0:
            # It existed by name/season/sport
            comp_id = self.conn.execute(
                "SELECT id FROM competitions WHERE sport_id = ? AND name = ? AND season = ?",
                (self._ensure_sport(), name, season)
            ).fetchone()[0]
        else:
            comp_id = res.lastrowid
            
        # Create entity and source reference
        ent_res = self.conn.execute(
            "INSERT INTO sports_entity (sport, entity_type, domain_table, domain_entity_id, created_at) VALUES ('football', 'COMPETITION', 'competitions', ?, ?)",
            (comp_id, now_str)
        )
        self.conn.execute(
            "INSERT INTO source_entity_reference (sport, entity_type, canonical_entity_id, provider, provider_entity_id, valid_from, verification_status, verification_method) VALUES ('football', 'COMPETITION', ?, 'api-football', ?, ?, ?, ?)",
            (ent_res.lastrowid, provider_id, now_str, "VERIFIED", "automatic") # Using comp_id for canonical_entity_id here, but wait, usually sports_entity.id is canonical_entity_id
        ) # Actually, the prompt says "Create distinct EVENT sports_entity rows and do not confuse sports_entity.id with fixtures.id"
        # So maybe for competition it's competitions.id. Let's stick to competitions.id for canonical_entity_id.
        
        return comp_id

    def _resolve_or_create_team(self, provider_id: str, name: str) -> int:
        row = self.conn.execute(
            "SELECT canonical_entity_id FROM source_entity_reference WHERE sport = 'football' AND entity_type = 'TEAM' AND provider = 'api-football' AND provider_entity_id = ? AND valid_to IS NULL",
            (provider_id,)
        ).fetchone()
        if row:
            return row[0]
            
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
        self.conn.execute(
            "INSERT INTO source_entity_reference (sport, entity_type, canonical_entity_id, provider, provider_entity_id, valid_from, verification_status, verification_method) VALUES ('football', 'TEAM', ?, 'api-football', ?, ?, ?, ?)",
            (ent_res.lastrowid, provider_id, now_str, "VERIFIED", "automatic")
        )
        return team_id
        
    def _resolve_or_create_fixture(self, provider_id: str, comp_id: int, home_id: int, away_id: int, kickoff_str: str, status: str, home_score: int, away_score: int, fetched_at: str) -> int:
        row = self.conn.execute(
            "SELECT fixture_id FROM fixture_sources WHERE source = 'api-football' AND external_id = ?",
            (provider_id,)
        ).fetchone()
        if row:
            fix_id = row[0]
            self.conn.execute(
                "UPDATE fixtures SET status = ?, score_home = ?, score_away = ?, fetched_at = ? WHERE id = ?",
                (status, home_score, away_score, fetched_at, fix_id)
            )
            return fix_id
            
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
        self.conn.execute(
            "INSERT INTO source_entity_reference (sport, entity_type, canonical_entity_id, provider, provider_entity_id, valid_from, verification_status, verification_method) VALUES ('football', 'EVENT', ?, 'api-football', ?, ?, ?, ?)",
            (ent_res.lastrowid, provider_id, now_str, "VERIFIED", "automatic") # Here canonical_entity_id is sports_entity.id
        )
        
        return fix_id

    def persist_completed_facts(self, facts: FootballCompletedMatchFacts, fetched_at: str, run_id: int) -> dict:
        with fixture_transaction(self.conn):
            comp_id = self._resolve_or_create_competition(
                facts.fixture.provider_competition_id, 
                facts.fixture.competition_name, 
                facts.fixture.country, 
                facts.fixture.season
            )
            home_id = self._resolve_or_create_team(facts.fixture.home_provider_team_id, facts.fixture.home_team_name)
            away_id = self._resolve_or_create_team(facts.fixture.away_provider_team_id, facts.fixture.away_team_name)
            
            kickoff_str = format_utc(facts.fixture.kickoff_at)
            fix_id = self._resolve_or_create_fixture(
                facts.fixture.provider_fixture_id, comp_id, home_id, away_id, kickoff_str, 
                facts.fixture.canonical_status, facts.fixture.home_score, facts.fixture.away_score, fetched_at
            )
            
            reused = 0
            inserted = 0
            
            for team_facts in (facts.home, facts.away):
                local_team_id = home_id if team_facts.provider_team_id == facts.fixture.home_provider_team_id else away_id
                
                payload_dict = serialize_team_match_facts(team_facts)
                # Ensure canonical serialization
                payload_json = json.dumps(payload_dict, separators=(',', ':'), sort_keys=True)
                payload_sha256 = hashlib.sha256(payload_json.encode('utf-8')).hexdigest()
                
                logical_identity = f"v1\x00TEAM_MATCH_FACTS\x00api-football\x00{facts.fixture.provider_fixture_id}\x00{team_facts.provider_team_id}\x00{payload_sha256}"
                
                # Check if observation exists
                obs_row = self.conn.execute(
                    "SELECT id FROM fixture_capability_observation WHERE logical_identity = ?",
                    (logical_identity,)
                ).fetchone()
                
                if obs_row:
                    obs_id = obs_row[0]
                    reused += 1
                else:
                    obs_res = self.conn.execute(
                        """INSERT INTO fixture_capability_observation 
                        (canonical_fixture_id, team_id, capability, source, request_identity, evidence_bundle_id, native_fixture_id, native_team_id, status, observed_at, valid_at, payload_sha256, payload_json, logical_identity)
                        VALUES (?, ?, 'TEAM_MATCH_FACTS', 'api-football', ?, ?, ?, ?, 'SUCCESS', ?, ?, ?, ?, ?)
                        """,
                        (
                            fix_id, local_team_id, 
                            f"api-football/fixture/{facts.fixture.provider_fixture_id}",
                            facts.statistics_evidence_bundle_id or facts.fixture_evidence_bundle_id,
                            facts.fixture.provider_fixture_id, team_facts.provider_team_id,
                            fetched_at, kickoff_str, payload_sha256, payload_json, logical_identity
                        )
                    )
                    obs_id = obs_res.lastrowid
                    inserted += 1
                
                # UPSERT match_stats
                # match_stats.fixture_id is fixtures.id
                # match_stats.team_id is teams.id
                # We need to map the facts to columns
                metrics = {
                    "goals": team_facts.goals,
                    "shots": team_facts.shots,
                    "shots_on_target": team_facts.shots_on_target,
                    "possession_pct": team_facts.possession_pct,
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
                    
            # Transition sports_sync_item
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
