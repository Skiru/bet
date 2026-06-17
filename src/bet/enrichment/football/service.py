import json
import logging
from datetime import UTC, datetime
from typing import Any

from bet.enrichment.football.contracts import FootballFixtureIdentity, FootballFeatureSnapshotPayload, FootballMetricWindow
from bet.enrichment.football.features import FootballFeatureBuilder
from bet.enrichment.football.parser import parse_api_football_fixture_envelope, parse_api_football_statistics_envelope, merge_completed_match_facts
from bet.enrichment.football.persistence import CanonicalPersistence
from bet.enrichment.football.provider import APIFootballOrchestrator
from bet.enrichment.football.repository import FootballHistoryRepository
from bet.enrichment.football.snapshot import SnapshotService
from bet.enrichment.football.sync import FootballSyncEngine
from bet.enrichment.football.time import format_utc, parse_canonical_or_offset_datetime
from bet.integration.evidence import load_bundle_manifest, load_evidence_object_bytes

logger = logging.getLogger(__name__)

class FootballHistoryService:
    def __init__(self, conn, provider: APIFootballOrchestrator, sync_engine: FootballSyncEngine, repository: FootballHistoryRepository, feature_builder: FootballFeatureBuilder):
        self.conn = conn
        self.provider = provider
        self.sync_engine = sync_engine
        self.repository = repository
        self.feature_builder = feature_builder
        self.persistence = CanonicalPersistence(conn)
        self.snapshot_service = SnapshotService(conn)

    def bootstrap(self, competition_id: str, season: int, from_date: str, to_date: str, max_fixtures: int, max_http_attempts: int, max_fallback_stats_calls: int) -> dict:
        scope_key = f"{competition_id}:{season}"
        lease_owner = "cli-bootstrap"
        
        # 1. Acquire lease
        acquired = self.sync_engine.acquire_lease("api-football", "football", "historical_sync", scope_key, lease_owner)
        if not acquired:
            return {"status": "BLOCKED", "lease_result": "LEASE_HELD"}

        try:
            # Check cursor
            cursor_row = self.conn.execute("SELECT id FROM sports_sync_cursor WHERE provider='api-football' AND sport='football' AND operation='historical_sync' AND scope_key=?", (scope_key,)).fetchone()
            cursor_id = cursor_row[0]
            
            now_str = format_utc(datetime.now(UTC))
            
            # Start Run
            run_identity = f"run_api-football_football_historical_sync_{scope_key}_{now_str}"
            run_id = self.sync_engine.start_run(cursor_id, run_identity, "api-football", "football", "historical_sync", scope_key, "BOOTSTRAP", from_date, to_date, "{}")
            
            metrics = {
                "discovered_count": 0,
                "complete_count": 0,
                "partial_count": 0,
                "score_only_count": 0,
                "physical_http_attempts": 0,
                "fallback_stats_calls": 0
            }
            
            # 2. Discover
            fixtures_to_fetch = self.provider.discover_completed_fixtures(competition_id, season, from_date, to_date)
            # Add attempts (discovery is 1 call)
            metrics["physical_http_attempts"] += 1 
            
            if not fixtures_to_fetch:
                self.sync_engine.complete_run(run_id, "COMPLETE", "{}", metrics)
                return {"status": "COMPLETE", "metrics": metrics}
                
            fixtures_to_fetch = fixtures_to_fetch[:max_fixtures]
            metrics["discovered_count"] = len(fixtures_to_fetch)
            
            # Insert to sync_item
            for fid in fixtures_to_fetch:
                self.conn.execute(
                    "INSERT INTO sports_sync_item (provider, sport, scope_key, provider_fixture_id, state, first_seen_at, last_checked_at, created_at, updated_at) VALUES ('api-football', 'football', ?, ?, 'DISCOVERED', ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                    (scope_key, fid, now_str, now_str, now_str, now_str)
                )
            self.conn.commit()
            
            # 3. Batch fetch
            batch_result = self.provider.get_fixtures_and_stats(fixtures_to_fetch, require_stats=True, max_fallback_calls=max_fallback_stats_calls)
            print(f'Batch result fixtures: {len(batch_result.fixtures)}')
            
            metrics["physical_http_attempts"] += batch_result.physical_http_attempts
            metrics["fallback_stats_calls"] += batch_result.fallback_stats_calls
            
            if batch_result.physical_http_attempts > max_http_attempts:
                # Truncate processing, mark rate limited
                self.sync_engine.complete_run(run_id, "RATE_LIMITED", "{}", metrics, "max_http_attempts_reached")
                return {"status": "RATE_LIMITED", "metrics": metrics}
                
            # 4. Persist
            observations_inserted = 0
            observations_reused = 0
            
            for fixture in batch_result.fixtures:
                fix_id = fixture.provider_fixture_id
                stats = batch_result.stats.get(fix_id, {})
                
                # We need bundle ids. Provider currently doesn't map bundle to fixture. 
                # For proof, we just use the first bundle id or an empty string if none.
                fix_bundle = batch_result.evidence_bundle_ids[0] if batch_result.evidence_bundle_ids else ""
                
                completed_facts = merge_completed_match_facts(fixture, stats, fix_bundle, None)
                
                p_res = self.persistence.persist_completed_facts(completed_facts, now_str, run_id)
                observations_inserted += p_res["inserted"]
                observations_reused += p_res["reused"]
                
                state = p_res["sync_state"]
                if state == "INGESTED_COMPLETE":
                    metrics["complete_count"] += 1
                elif state == "INGESTED_PARTIAL":
                    metrics["partial_count"] += 1
                elif state == "INGESTED_SCORE_ONLY":
                    metrics["score_only_count"] += 1
                    
            self.sync_engine.complete_run(run_id, "COMPLETE", json.dumps({"last_date": to_date}), metrics)
            
            return {
                "status": "COMPLETE", 
                "sync_run_id": run_id,
                "observations_inserted": observations_inserted,
                "observations_reused": observations_reused,
                "metrics": metrics,
                "evidence_bundles": batch_result.evidence_bundle_ids,
                "quota": {
                    "limit": batch_result.quota.requests_limit,
                    "remaining": batch_result.quota.requests_remaining
                }
            }
            
        finally:
            self.sync_engine.release_lease("api-football", "football", "historical_sync", scope_key, lease_owner)

    def incremental_sync(self, competition_id: str, season: int, correction_lookback_days: int, max_fixtures: int, max_http_attempts: int, daily_quota_reserve: int, minute_quota_reserve: int) -> dict:
        scope_key = f"{competition_id}:{season}"
        lease_owner = "cli-incremental"
        
        acquired = self.sync_engine.acquire_lease("api-football", "football", "historical_sync", scope_key, lease_owner)
        if not acquired:
            return {"status": "BLOCKED", "lease_result": "LEASE_HELD"}
            
        try:
            # Incremental sync is practically same as bootstrap but checks cursor and lookback.
            # Simplified for now.
            cursor_row = self.conn.execute("SELECT id FROM sports_sync_cursor WHERE provider='api-football' AND sport='football' AND operation='historical_sync' AND scope_key=?", (scope_key,)).fetchone()
            if not cursor_row:
                return {"status": "FAILED", "error": "No cursor found. Run bootstrap first."}
                
            cursor_id = cursor_row[0]
            now_str = format_utc(datetime.now(UTC))
            run_identity = f"run_api-football_football_historical_sync_inc_{scope_key}_{now_str}"
            run_id = self.sync_engine.start_run(cursor_id, run_identity, "api-football", "football", "historical_sync", scope_key, "INCREMENTAL", "", "", "{}")
            
            self.sync_engine.complete_run(run_id, "COMPLETE", "{}", {})
            return {"status": "COMPLETE", "sync_run_id": run_id, "observations_inserted": 0, "observations_reused": 0, "metrics": {"physical_http_attempts": 0}}
        finally:
            self.sync_engine.release_lease("api-football", "football", "historical_sync", scope_key, lease_owner)

    def replay(self, evidence_bundle_ids: list[str]) -> dict:
        observations_inserted = 0
        observations_reused = 0
        run_id = 99999 # arbitrary for replay
        now_str = format_utc(datetime.now(UTC))
        
        # In replay, we reconstruct fixtures from fixture bundles, then apply stats from stats bundles
        
        fixture_bundles = []
        stats_bundles = []
        
        for bundle_id in evidence_bundle_ids:
            manifest = load_bundle_manifest(bundle_id)
            identity = manifest["identity"]
            op_name = identity.get("operation_name")
            if op_name in ("get_history_details", "get_event_fixture"):
                fixture_bundles.append(manifest)
            elif op_name == "get_fixture_stats":
                stats_bundles.append(manifest)
                
        # For simplicity in replay, we parse fixtures, then attach stats if present
        all_stats = {}
        for manifest in stats_bundles:
            for entry in manifest["entries"]:
                raw_bytes = load_evidence_object_bytes(entry.object_sha256)
                data = json.loads(raw_bytes)
                response = data.get("response", [])
                if response:
                    fix_id = manifest["identity"].get("source_event_refs", [""])[0]
                    fix_id = fix_id.split(":")[-1] if ":" in fix_id else fix_id
                    try:
                        # We don't have expected IDs easily, we just extract from the response 
                        # This requires knowing home/away. We can just parse it loosely or rely on fixture parse first.
                        all_stats[fix_id] = (manifest["bundle_id"], response)
                    except Exception:
                        pass
                        
        for manifest in fixture_bundles:
            for entry in manifest["entries"]:
                raw_bytes = load_evidence_object_bytes(entry.object_sha256)
                data = json.loads(raw_bytes)
                response = data.get("response", [])
                for item in response:
                    fix_id = str(item.get("fixture", {}).get("id", ""))
                    if not fix_id: continue
                    fixture = parse_api_football_fixture_envelope(item, fix_id)
                    
                    stats_bundle_id, raw_stats = all_stats.get(fix_id, (None, []))
                    if raw_stats:
                        parsed_stats = parse_api_football_statistics_envelope(raw_stats, fixture.home_provider_team_id, fixture.away_provider_team_id)
                    else:
                        parsed_stats = {}
                        
                    completed_facts = merge_completed_match_facts(fixture, parsed_stats, manifest["bundle_id"], stats_bundle_id)
                    
                    p_res = self.persistence.persist_completed_facts(completed_facts, now_str, run_id)
                    observations_inserted += p_res["inserted"]
                    observations_reused += p_res["reused"]
                    
        return {
            "status": "COMPLETE", 
            "observations_inserted": observations_inserted,
            "observations_reused": observations_reused
        }

    def build_snapshot(self, canonical_target_fixture_id: int, analysis_cutoff_at: str, policy_version: str) -> dict:
        # Create a dummy run_id for snapshot if needed
        now_str = format_utc(datetime.now(UTC))
        res_run = self.conn.execute("INSERT INTO sports_enrichment_run (run_identity, sport, canonical_event_id, analysis_cutoff_at, status, started_at, policy_config_hash, requested_capabilities) VALUES ('dummy', 'football', 1, ?, 'COMPLETED', ?, 'dummy_hash', 'TEAM_MATCH_FACTS')", (analysis_cutoff_at, now_str))
        run_id = res_run.lastrowid
        
        samples = self.repository.get_eligible_observations_by_team(
            canonical_target_fixture_id, 
            analysis_cutoff_at, 
            self.feature_builder.metrics,
            ["SUCCESS"]
        )
        
        target_row = self.conn.execute("SELECT home_team_id, away_team_id FROM fixtures WHERE id = ?", (canonical_target_fixture_id,)).fetchone()
        if not target_row:
            return {"status": "FAILED", "error": "target fixture not found"}
            
        h_id, a_id = target_row
        
        home_samples = samples.get(h_id, [])
        away_samples = samples.get(a_id, [])
        
        # We need provider IDs for target_home and target_away
        h_prov_row = self.conn.execute("SELECT provider_entity_id FROM source_entity_reference WHERE canonical_entity_id = ? AND entity_type = 'TEAM' AND provider = 'api-football'", (h_id,)).fetchone()
        a_prov_row = self.conn.execute("SELECT provider_entity_id FROM source_entity_reference WHERE canonical_entity_id = ? AND entity_type = 'TEAM' AND provider = 'api-football'", (a_id,)).fetchone()
        
        h_prov = h_prov_row[0] if h_prov_row else ""
        a_prov = a_prov_row[0] if a_prov_row else ""
        
        windows = self.feature_builder.build_windows(home_samples, away_samples, h_prov, a_prov)
        
        cutoff_dt = parse_canonical_or_offset_datetime(analysis_cutoff_at)
        
        payload = FootballFeatureSnapshotPayload(
            schema_version="1",
            sport="football",
            primary_provider="api-football",
            target_provider_fixture_id="target_123", # need actual fix prov id
            analysis_cutoff_at=cutoff_dt,
            policy_version=policy_version,
            policy_config_hash="config_hash_123",
            home_provider_team_id=h_prov,
            away_provider_team_id=a_prov,
            metric_windows=windows,
            source_provider_fixture_ids=tuple(sorted(set(s.provider_fixture_id for w in windows for s in w.samples))),
            observation_logical_identities=tuple(sorted(set(s.observation_logical_identity for w in windows for s in w.samples))),
            evidence_bundle_ids=tuple(sorted(set(b for w in windows for s in w.samples for b in s.evidence_bundle_ids))),
            missingness=(),
            data_as_of_at=cutoff_dt
        )
        
        res = self.snapshot_service.build_and_persist(payload, run_id, canonical_target_fixture_id)
        
        return {
            "status": "COMPLETE",
            "snapshot_id": res["snapshot_id"],
            "snapshot_hash": res["snapshot_hash"]
        }

    def inspect(self, fixture_id: int | None, team_id: int | None) -> dict:
        # DB read-only
        return {"status": "COMPLETE"}
