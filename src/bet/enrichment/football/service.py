# ruff: noqa: E501
import hashlib
import json
import logging
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from bet.enrichment.football.contracts import (
    BatchIdsCapability,
    BootstrapCommand,
    BuildSnapshotCommand,
    FootballFeatureSnapshotPayload,
    FootballTeamMatchFacts,
    IncrementalCommand,
    InspectCommand,
    ReplayCommand,
    SnapshotResult,
    SyncResult,
)
from bet.enrichment.football.parser import merge_completed_match_facts
from bet.enrichment.football.persistence import CanonicalPersistence
from bet.enrichment.football.provider import (
    LiveAPIFootballAcquirer,
    PhysicalAttemptBudget,
)
from bet.enrichment.football.replay import EvidenceReplayAcquirer
from bet.enrichment.football.repository import FootballHistoryRepository
from bet.enrichment.football.snapshot import SnapshotService
from bet.enrichment.football.sync import FootballSyncEngine
from bet.enrichment.football.time import format_utc, parse_canonical_or_offset_datetime

logger = logging.getLogger(__name__)

def compute_scope_key(competition_provider_id: str, season: int) -> str:
    scope_identity = {
        "version": 1,
        "provider": "api-football",
        "sport": "football",
        "operation": "completed-fixture-history",
        "competition_provider_id": str(competition_provider_id),
        "season": int(season)
    }
    canonical_bytes = json.dumps(scope_identity, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(canonical_bytes).hexdigest().lower()


class FootballHistoryService:
    def __init__(self, conn, provider: LiveAPIFootballAcquirer, sync_engine: FootballSyncEngine, repository: FootballHistoryRepository, feature_builder=None):
        self.conn = conn
        self.provider = provider
        self.sync_engine = sync_engine
        self.repository = repository
        self.feature_builder = feature_builder
        self.persistence = CanonicalPersistence(conn)
        self.snapshot_service = SnapshotService(conn)

    def bootstrap(self, cmd: BootstrapCommand) -> SyncResult:
        scope_key = compute_scope_key(cmd.competition_provider_id, cmd.season)
        lease_owner = uuid4().hex

        # 1. Acquire lease
        acquired = self.sync_engine.acquire_lease("api-football", "football", "completed-fixture-history", scope_key, lease_owner)
        if not acquired:
            return SyncResult(0, scope_key, None, None, {}, None, "LEASE_HELD", ("Lease is currently held by another process",))

        try:
            now_str = format_utc(datetime.now(UTC))

            # Find or create cursor
            cursor_row = self.conn.execute(
                """SELECT id, committed_through_date FROM sports_sync_cursor
                   WHERE provider='api-football' AND sport='football' AND operation='completed-fixture-history' AND scope_key=?
                """,
                (scope_key,)
            ).fetchone()

            if cursor_row:
                cursor_id, comm_date = cursor_row
            else:
                c_res = self.conn.execute(
                    """INSERT INTO sports_sync_cursor
                       (provider, sport, operation, scope_key, created_at, updated_at)
                       VALUES ('api-football', 'football', 'completed-fixture-history', ?, ?, ?)
                    """,
                    (scope_key, now_str, now_str)
                )
                cursor_id = c_res.lastrowid
                comm_date = None

            cursor_before_json = json.dumps({"committed_through_date": comm_date})

            # Start Run
            run_identity = f"run_api-football_football_completed-fixture-history_{scope_key}_{now_str}"
            run_id = self.sync_engine.start_run(
                cursor_id, run_identity, "api-football", "football", "completed-fixture-history",
                scope_key, "BOOTSTRAP", cmd.from_date.isoformat(), cmd.to_date.isoformat(), cursor_before_json
            )

            # 2. Acquisition
            budget = PhysicalAttemptBudget(cmd.max_http_attempts)
            acq_res = self.provider.acquire(
                competition_provider_id=cmd.competition_provider_id,
                season=cmd.season,
                from_date=cmd.from_date,
                to_date=cmd.to_date,
                max_fixtures=cmd.max_fixtures,
                max_fallback_stats_calls=cmd.max_fallback_stats_calls,
                attempt_budget=budget,
                ids_capability=BatchIdsCapability.UNKNOWN,
            )

            # 3. Create sync items first as DISCOVERED
            for acq_fixture in acq_res.fixtures:
                self.conn.execute(
                    """INSERT INTO sports_sync_item
                       (provider, sport, scope_key, provider_fixture_id, state, first_seen_at, last_checked_at, created_at, updated_at)
                       VALUES ('api-football', 'football', ?, ?, 'DISCOVERED', ?, ?, ?, ?)
                       ON CONFLICT DO NOTHING
                    """,
                    (scope_key, acq_fixture.fixture.provider_fixture_id, now_str, now_str, now_str, now_str)
                )
            self.conn.commit()

            # 4. Persist and resolve transitions
            counters = {
                "physical_http_attempts": acq_res.physical_attempts,
                "fallback_stats_calls": acq_res.statistics_calls,
                "discovered_count": len(acq_res.fixtures),
                "complete_count": 0,
                "partial_count": 0,
                "score_only_count": 0,
                "permanently_unavailable_count": 0,
                "transient_failed_count": 0,
            }

            for acq_fixture in acq_res.fixtures:
                # Merge into FootballCompletedMatchFacts
                # Calculate bundle ids from evidence refs
                fixture_bundle_id = ""
                if acq_fixture.fixture_evidence_refs:
                    fixture_bundle_id = acq_fixture.fixture_evidence_refs[0].object_sha256 # loosely use sha as bundle or we can construct it
                stats_bundle_id = None
                if acq_fixture.statistics_evidence_refs:
                    stats_bundle_id = acq_fixture.statistics_evidence_refs[0].object_sha256

                # To get home/away stats, let's build the expected dict
                stats_dict = acq_fixture.statistics_by_provider_team_id

                completed_facts = merge_completed_match_facts(
                    acq_fixture.fixture, stats_dict, fixture_bundle_id, stats_bundle_id
                )

                # Persist
                p_res = self.persistence.persist_completed_facts(completed_facts, now_str, run_id)
                state = p_res["sync_state"]
                if state == "INGESTED_COMPLETE":
                    counters["complete_count"] += 1
                elif state == "INGESTED_PARTIAL":
                    counters["partial_count"] += 1
                elif state == "INGESTED_SCORE_ONLY":
                    counters["score_only_count"] += 1
                elif state == "PERMANENTLY_UNAVAILABLE":
                    counters["permanently_unavailable_count"] += 1
                elif state == "TRANSIENT_FAILED":
                    counters["transient_failed_count"] += 1

            # 5. Cursor advancement decision
            final_status = acq_res.terminal_status
            cursor_after_json = cursor_before_json

            # Cursor only advances when all items are terminal (meaning no TRANSIENT_FAILED)
            # and no budget/quota exhaustion stopped completion of the window.
            if counters["transient_failed_count"] == 0 and final_status == "COMPLETE":
                cursor_after_json = json.dumps({"committed_through_date": cmd.to_date.isoformat()})
                self.conn.execute(
                    """UPDATE sports_sync_cursor
                       SET committed_through_date = ?, last_success_at = ?, updated_at = ?
                       WHERE id = ?
                    """,
                    (cmd.to_date.isoformat(), now_str, now_str, cursor_id)
                )

            self.conn.commit()

            # Complete sync run
            self.sync_engine.complete_run(run_id, final_status, cursor_after_json, counters)

            return SyncResult(
                sync_run_id=run_id,
                scope_key=scope_key,
                cursor_before=json.loads(cursor_before_json),
                cursor_after=json.loads(cursor_after_json),
                actual_counters=counters,
                acquisition_result=acq_res,
                final_status=final_status,
                warnings=(),
            )

        finally:
            self.sync_engine.release_lease("api-football", "football", "completed-fixture-history", scope_key, lease_owner)

    def incremental_sync(self, cmd: IncrementalCommand) -> SyncResult:
        scope_key = compute_scope_key(cmd.competition_provider_id, cmd.season)
        lease_owner = uuid4().hex

        # 1. Acquire lease
        acquired = self.sync_engine.acquire_lease("api-football", "football", "completed-fixture-history", scope_key, lease_owner)
        if not acquired:
            return SyncResult(0, scope_key, None, None, {}, None, "LEASE_HELD", ("Lease is currently held by another process",))

        try:
            now_str = format_utc(datetime.now(UTC))

            # Find cursor
            cursor_row = self.conn.execute(
                """SELECT id, committed_through_date FROM sports_sync_cursor
                   WHERE provider='api-football' AND sport='football' AND operation='completed-fixture-history' AND scope_key=?
                """,
                (scope_key,)
            ).fetchone()

            if not cursor_row:
                raise ValueError("No sync cursor exists. Run bootstrap first.")

            cursor_id, comm_date_str = cursor_row
            if not comm_date_str:
                raise ValueError("Cursor has never been bootstrapped. Run bootstrap first.")

            cursor_before_json = json.dumps({"committed_through_date": comm_date_str})

            # Bounded lookback window
            comm_date = parse_canonical_or_offset_datetime(comm_date_str).date()
            from_date = comm_date - timedelta(days=cmd.correction_lookback_days)
            # Forward to today
            to_date = date.today()

            # Start sync run
            run_identity = f"run_api-football_football_completed-fixture-history_inc_{scope_key}_{now_str}"
            run_id = self.sync_engine.start_run(
                cursor_id, run_identity, "api-football", "football", "completed-fixture-history",
                scope_key, "INCREMENTAL", from_date.isoformat(), to_date.isoformat(), cursor_before_json
            )

            # Frozen incremental with 0 lookback days contract:
            # "at most one discovery logical call; zero ids calls; zero statistics calls; zero new observations."
            if cmd.correction_lookback_days == 0 and comm_date == to_date:
                # No forward window exists, we just complete successfully with zero calls!
                counters = {
                    "physical_http_attempts": 0,
                    "fallback_stats_calls": 0,
                    "discovered_count": 0,
                    "complete_count": 0,
                    "partial_count": 0,
                    "score_only_count": 0,
                    "permanently_unavailable_count": 0,
                    "transient_failed_count": 0,
                }
                self.sync_engine.complete_run(run_id, "COMPLETE", cursor_before_json, counters)
                return SyncResult(
                    sync_run_id=run_id,
                    scope_key=scope_key,
                    cursor_before=json.loads(cursor_before_json),
                    cursor_after=json.loads(cursor_before_json),
                    actual_counters=counters,
                    acquisition_result=None,
                    final_status="COMPLETE",
                    warnings=(),
                )

            # 2. Acquisition
            budget = PhysicalAttemptBudget(cmd.max_http_attempts)
            acq_res = self.provider.acquire(
                competition_provider_id=cmd.competition_provider_id,
                season=cmd.season,
                from_date=from_date,
                to_date=to_date,
                max_fixtures=cmd.max_fixtures,
                max_fallback_stats_calls=cmd.max_fallback_stats_calls,
                attempt_budget=budget,
                ids_capability=BatchIdsCapability.UNKNOWN,
            )

            # 3. Create / update sync items
            for acq_fixture in acq_res.fixtures:
                self.conn.execute(
                    """INSERT INTO sports_sync_item
                       (provider, sport, scope_key, provider_fixture_id, state, first_seen_at, last_checked_at, created_at, updated_at)
                       VALUES ('api-football', 'football', ?, ?, 'DISCOVERED', ?, ?, ?, ?)
                       ON CONFLICT DO NOTHING
                    """,
                    (scope_key, acq_fixture.fixture.provider_fixture_id, now_str, now_str, now_str, now_str)
                )
            self.conn.commit()

            # 4. Persist and evaluate transitions
            counters = {
                "physical_http_attempts": acq_res.physical_attempts,
                "fallback_stats_calls": acq_res.statistics_calls,
                "discovered_count": len(acq_res.fixtures),
                "complete_count": 0,
                "partial_count": 0,
                "score_only_count": 0,
                "permanently_unavailable_count": 0,
                "transient_failed_count": 0,
            }

            for acq_fixture in acq_res.fixtures:
                fixture_bundle_id = ""
                if acq_fixture.fixture_evidence_refs:
                    fixture_bundle_id = acq_fixture.fixture_evidence_refs[0].object_sha256
                stats_bundle_id = None
                if acq_fixture.statistics_evidence_refs:
                    stats_bundle_id = acq_fixture.statistics_evidence_refs[0].object_sha256

                stats_dict = acq_fixture.statistics_by_provider_team_id
                completed_facts = merge_completed_match_facts(
                    acq_fixture.fixture, stats_dict, fixture_bundle_id, stats_bundle_id
                )

                # Check if item state is terminal and unchanged first to skip new observations!
                # We fetch current payload hash
                row = self.conn.execute(
                    """SELECT normalized_payload_sha256 FROM sports_sync_item
                       WHERE provider='api-football' AND sport='football' AND provider_fixture_id=?
                    """,
                    (acq_fixture.fixture.provider_fixture_id,)
                ).fetchone()

                # Calculate new payload hash
                payload_dict_home = serialize_team_match_facts_helper(completed_facts.home)
                payload_dict_away = serialize_team_match_facts_helper(completed_facts.away)
                payload_json = json.dumps([payload_dict_home, payload_dict_away], separators=(',', ':'), sort_keys=True)
                new_hash = hashlib.sha256(payload_json.encode('utf-8')).hexdigest().lower()

                if row and row[0] == new_hash:
                    # Unchanged! Reused!
                    counters["complete_count"] += 1 # loosely treat as complete for counters
                    continue

                p_res = self.persistence.persist_completed_facts(completed_facts, now_str, run_id)

                # Update payload hash inside sync item so later checks know it is unchanged!
                self.conn.execute(
                    """UPDATE sports_sync_item
                       SET normalized_payload_sha256 = ?
                       WHERE provider = 'api-football' AND sport = 'football' AND provider_fixture_id = ?
                    """,
                    (new_hash, acq_fixture.fixture.provider_fixture_id)
                )

                state = p_res["sync_state"]
                if state == "INGESTED_COMPLETE":
                    counters["complete_count"] += 1
                elif state == "INGESTED_PARTIAL":
                    counters["partial_count"] += 1
                elif state == "INGESTED_SCORE_ONLY":
                    counters["score_only_count"] += 1
                elif state == "PERMANENTLY_UNAVAILABLE":
                    counters["permanently_unavailable_count"] += 1
                elif state == "TRANSIENT_FAILED":
                    counters["transient_failed_count"] += 1

            # 5. Cursor advancement
            final_status = acq_res.terminal_status
            cursor_after_json = cursor_before_json

            if counters["transient_failed_count"] == 0 and final_status == "COMPLETE":
                cursor_after_json = json.dumps({"committed_through_date": to_date.isoformat()})
                self.conn.execute(
                    """UPDATE sports_sync_cursor
                       SET committed_through_date = ?, last_success_at = ?, updated_at = ?
                       WHERE id = ?
                    """,
                    (to_date.isoformat(), now_str, now_str, cursor_id)
                )

            self.conn.commit()

            # Complete sync run
            self.sync_engine.complete_run(run_id, final_status, cursor_after_json, counters)

            return SyncResult(
                sync_run_id=run_id,
                scope_key=scope_key,
                cursor_before=json.loads(cursor_before_json),
                cursor_after=json.loads(cursor_after_json),
                actual_counters=counters,
                acquisition_result=acq_res,
                final_status=final_status,
                warnings=(),
            )

        finally:
            self.sync_engine.release_lease("api-football", "football", "completed-fixture-history", scope_key, lease_owner)

    def replay(self, cmd: ReplayCommand) -> SyncResult:
        # Replay service:
        # - creates a real sports_sync_run in REPLAY mode;
        # - calls EvidenceReplayAcquirer;
        # - uses normal persistence;
        # - preserves observed_at;
        # - performs zero HTTP.
        now_str = format_utc(datetime.now(UTC))

        # Replay doesn't use a real cursor, but let's find or create a temporary cursor to satisfy FK
        scope_key = "replay_scope_key"
        cursor_row = self.conn.execute(
            """SELECT id FROM sports_sync_cursor
               WHERE provider='api-football' AND sport='football' AND operation='completed-fixture-history' AND scope_key=?
            """,
            (scope_key,)
        ).fetchone()

        if cursor_row:
            cursor_id = cursor_row[0]
        else:
            c_res = self.conn.execute(
                """INSERT INTO sports_sync_cursor
                   (provider, sport, operation, scope_key, created_at, updated_at)
                   VALUES ('api-football', 'football', 'completed-fixture-history', ?, ?, ?)
                """,
                (scope_key, now_str, now_str)
            )
            cursor_id = c_res.lastrowid

        run_identity = f"run_api-football_football_completed-fixture-history_replay_{uuid4().hex}_{now_str}"
        run_id = self.sync_engine.start_run(
            cursor_id, run_identity, "api-football", "football", "completed-fixture-history",
            scope_key, "REPLAY", "", "", "{}"
        )

        acquirer = EvidenceReplayAcquirer(bundle_ids=cmd.evidence_bundle_ids)
        acq_res = acquirer.acquire(
            competition_provider_id="",
            season=0,
            from_date=None,
            to_date=None,
            max_fixtures=1000,
            max_fallback_stats_calls=0,
            attempt_budget=None,
            ids_capability=BatchIdsCapability.UNKNOWN,
        )

        counters = {
            "physical_http_attempts": 0,
            "fallback_stats_calls": 0,
            "discovered_count": len(acq_res.fixtures),
            "complete_count": 0,
            "partial_count": 0,
            "score_only_count": 0,
            "permanently_unavailable_count": 0,
            "transient_failed_count": 0,
        }

        # Create sync items and persist
        for acq_fixture in acq_res.fixtures:
            self.conn.execute(
                """INSERT INTO sports_sync_item
                   (provider, sport, scope_key, provider_fixture_id, state, first_seen_at, last_checked_at, created_at, updated_at)
                   VALUES ('api-football', 'football', ?, ?, 'DISCOVERED', ?, ?, ?, ?)
                   ON CONFLICT DO NOTHING
                """,
                (scope_key, acq_fixture.fixture.provider_fixture_id, now_str, now_str, now_str, now_str)
            )

            fixture_bundle_id = cmd.evidence_bundle_ids[0] if cmd.evidence_bundle_ids else ""
            stats_bundle_id = cmd.evidence_bundle_ids[0] if len(cmd.evidence_bundle_ids) > 1 else None

            completed_facts = merge_completed_match_facts(
                acq_fixture.fixture, acq_fixture.statistics_by_provider_team_id, fixture_bundle_id, stats_bundle_id
            )

            p_res = self.persistence.persist_completed_facts(completed_facts, now_str, run_id)
            state = p_res["sync_state"]
            if state == "INGESTED_COMPLETE":
                counters["complete_count"] += 1
            elif state == "INGESTED_PARTIAL":
                counters["partial_count"] += 1
            elif state == "INGESTED_SCORE_ONLY":
                counters["score_only_count"] += 1

        self.conn.commit()
        self.sync_engine.complete_run(run_id, "COMPLETE", "{}", counters)

        return SyncResult(
            sync_run_id=run_id,
            scope_key=scope_key,
            cursor_before=None,
            cursor_after=None,
            actual_counters=counters,
            acquisition_result=acq_res,
            final_status="COMPLETE",
            warnings=(),
        )

    def inspect_fixture(self, cmd: InspectCommand) -> dict:
        if not cmd.fixture_id:
            raise ValueError("fixture_id must be provided")

        row = self.conn.execute(
            """SELECT f.id, f.status, f.score_home, f.score_away, f.kickoff, fs.external_id
               FROM fixtures f
               LEFT JOIN fixture_sources fs ON f.id = fs.fixture_id AND fs.source = 'api-football'
               WHERE f.id = ?
            """,
            (cmd.fixture_id,)
        ).fetchone()

        if not row:
            return {"status": "NOT_FOUND"}

        fix_id, status, score_home, score_away, kickoff, ext_id = row

        # Fetch observations
        obs_rows = self.conn.execute(
            """SELECT logical_identity, payload_json, observed_at, evidence_bundle_id
               FROM fixture_capability_observation
               WHERE canonical_fixture_id = ?
            """,
            (cmd.fixture_id,)
        ).fetchall()

        observations = []
        for obs in obs_rows:
            observations.append({
                "logical_identity": obs[0],
                "payload": json.loads(obs[1]),
                "observed_at": obs[2],
                "evidence_bundle_id": obs[3],
            })

        # Fetch projections
        proj_rows = self.conn.execute(
            """SELECT stat_key, stat_value, team_id FROM match_stats
               WHERE fixture_id = ?
            """,
            (cmd.fixture_id,)
        ).fetchall()

        projections = []
        for pr in proj_rows:
            projections.append({
                "stat_key": pr[0],
                "stat_value": pr[1],
                "team_id": pr[2]
            })

        return {
            "status": "SUCCESS",
            "fixture": {
                "id": fix_id,
                "provider_id": ext_id,
                "status": status,
                "score": {"home": score_home, "away": score_away},
                "kickoff": kickoff,
            },
            "observations": observations,
            "projections": projections,
        }

    def inspect_team(self, cmd: InspectCommand) -> dict:
        if not cmd.team_id:
            raise ValueError("team_id must be provided")

        row = self.conn.execute(
            """SELECT id, name FROM teams WHERE id = ?""",
            (cmd.team_id,)
        ).fetchone()

        if not row:
            return {"status": "NOT_FOUND"}

        team_id, name = row

        # Count completed fixtures
        fix_count = self.conn.execute(
            """SELECT COUNT(*) FROM fixtures
               WHERE (home_team_id = ? OR away_team_id = ?) AND status = 'finished'
            """,
            (cmd.team_id, cmd.team_id)
        ).fetchone()[0]

        # Latest observations
        obs_rows = self.conn.execute(
            """SELECT logical_identity, payload_json, observed_at
               FROM fixture_capability_observation
               WHERE team_id = ?
               ORDER BY observed_at DESC LIMIT 5
            """,
            (cmd.team_id,)
        ).fetchall()

        latest_obs = []
        for obs in obs_rows:
            latest_obs.append({
                "logical_identity": obs[0],
                "payload": json.loads(obs[1]),
                "observed_at": obs[2],
            })

        return {
            "status": "SUCCESS",
            "team": {
                "id": team_id,
                "name": name,
                "completed_fixtures_count": fix_count,
            },
            "latest_observations": latest_obs,
        }


    def build_snapshot(self, cmd: BuildSnapshotCommand) -> SnapshotResult:
        # 1. Resolve target fixture details and teams
        row = self.conn.execute(
            """SELECT f.id, fs.external_id, f.home_team_id, f.away_team_id, f.kickoff
               FROM fixtures f
               JOIN fixture_sources fs ON f.id = fs.fixture_id AND fs.source = 'api-football'
               WHERE f.id = ?
            """,
            (cmd.canonical_target_fixture_id,)
        ).fetchone()

        if not row:
            raise ValueError(f"Target fixture {cmd.canonical_target_fixture_id} not found in database.")

        fix_id, ext_id, h_id, a_t_id, kickoff_str = row

        # Get team provider IDs
        h_prov = self.conn.execute(
            "SELECT provider_entity_id FROM source_entity_reference WHERE sport='football' AND entity_type='TEAM' AND canonical_entity_id=(SELECT id FROM sports_entity WHERE domain_table='teams' AND domain_entity_id=?)",
            (h_id,)
        ).fetchone()

        a_prov = self.conn.execute(
            "SELECT provider_entity_id FROM source_entity_reference WHERE sport='football' AND entity_type='TEAM' AND canonical_entity_id=(SELECT id FROM sports_entity WHERE domain_table='teams' AND domain_entity_id=?)",
            (a_t_id,)
        ).fetchone()

        h_prov_id = h_prov[0] if h_prov else str(h_id)
        a_prov_id = a_prov[0] if a_prov else str(a_t_id)

        # 2. Query PIT observations
        metrics_list = ["goals", "shots", "shots_on_target", "possession_pct", "fouls", "yellow_cards", "red_cards", "offsides", "corners", "goalkeeper_saves"]

        samples_by_team = self.repository.get_eligible_observations_by_team(
            cmd.canonical_target_fixture_id,
            format_utc(cmd.analysis_cutoff_at),
            metrics_list,
            ["SUCCESS", "PARTIAL"]
        )

        h_samples = samples_by_team.get(h_id, [])
        a_samples = samples_by_team.get(a_t_id, [])

        # 3. Build features using FootballFeatureBuilder
        from bet.enrichment.football.features import FootballFeatureBuilder
        builder = FootballFeatureBuilder(metrics_list)
        metric_windows = builder.build_windows(h_samples, a_samples, h_prov_id, a_prov_id)

        src_fixture_ids = set()
        logical_ids = set()
        evidence_bundle_ids = set()
        missingness = set()

        for w in metric_windows:
            if w.available_count == 0:
                missingness.add(f"{w.metric}_{w.scope}")
            for s in w.samples:
                src_fixture_ids.add(s.provider_fixture_id)
                logical_ids.add(s.observation_logical_identity)
                evidence_bundle_ids.update(s.evidence_bundle_ids)

        policy_config = {
            "provider": "api-football",
            "metrics": sorted(metrics_list),
            "windows": ["overall_l5", "overall_l10", "h2h_l5", "home_l5", "away_l5"],
            "rounding_version": "v1"
        }
        policy_config_json = json.dumps(policy_config, sort_keys=True, separators=(',', ':'))
        policy_config_hash = hashlib.sha256(policy_config_json.encode('utf-8')).hexdigest().lower()

        payload = FootballFeatureSnapshotPayload(
            schema_version="football-feature-snapshot-v1",
            sport="football",
            primary_provider="api-football",
            target_provider_fixture_id=ext_id,
            analysis_cutoff_at=cmd.analysis_cutoff_at,
            policy_version=cmd.policy_version,
            policy_config_hash=policy_config_hash,
            home_provider_team_id=h_prov_id,
            away_provider_team_id=a_prov_id,
            metric_windows=metric_windows,
            source_provider_fixture_ids=tuple(sorted(src_fixture_ids)),
            observation_logical_identities=tuple(sorted(logical_ids)),
            evidence_bundle_ids=tuple(sorted(evidence_bundle_ids)),
            missingness=tuple(sorted(missingness)),
            data_as_of_at=cmd.analysis_cutoff_at
        )

        # Calculate run_identity
        run_dict = {
            "version": 1,
            "sport": "football",
            "provider": "api-football",
            "target_provider_fixture_id": ext_id,
            "analysis_cutoff_at": format_utc(cmd.analysis_cutoff_at),
            "policy_version": cmd.policy_version,
            "policy_config_hash": policy_config_hash,
        }
        run_identity = hashlib.sha256(json.dumps(run_dict, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest().lower()

        # Check if run exists
        run_row = self.conn.execute("SELECT id FROM sports_enrichment_run WHERE run_identity = ?", (run_identity,)).fetchone()
        if run_row:
            run_id = run_row[0]
        else:
            now_str = format_utc(datetime.now(UTC))
            r_res = self.conn.execute(
                """INSERT INTO sports_enrichment_run
                   (run_identity, sport, canonical_event_id, analysis_cutoff_at, started_at, status, policy_config_hash, requested_capabilities)
                   VALUES (?, 'football', ?, ?, ?, 'COMPLETE', ?, 'TEAM_MATCH_FACTS')
                """,
                (run_identity, cmd.canonical_target_fixture_id, format_utc(cmd.analysis_cutoff_at), now_str, policy_config_hash)
            )
            run_id = r_res.lastrowid

        snap_res = self.snapshot_service.build_and_persist(payload, run_id, cmd.canonical_target_fixture_id)

        created_or_reused = "REUSED" if run_row else "CREATED"

        from bet.enrichment.football.contracts import SnapshotResult
        return SnapshotResult(
            run_id=run_id,
            snapshot_id=snap_res["snapshot_id"],
            snapshot_hash=snap_res["snapshot_hash"],
            created_or_reused=created_or_reused,
            deterministic_drift=False
        )


def serialize_team_match_facts_helper(facts: FootballTeamMatchFacts) -> dict:
    return {
        "provider_fixture_id": facts.provider_fixture_id,
        "provider_team_id": facts.provider_team_id,
        "provider_opponent_team_id": facts.provider_opponent_team_id,
        "side": facts.side.value,
        "goals": facts.goals,
        "shots": facts.shots,
        "shots_on_target": facts.shots_on_target,
        "possession_pct": facts.possession_pct,
        "fouls": facts.fouls,
        "yellow_cards": facts.yellow_cards,
        "red_cards": facts.red_cards,
        "offsides": facts.offsides,
        "corners": facts.corners,
        "goalkeeper_saves": facts.goalkeeper_saves,
        "available_metrics": list(facts.available_metrics),
        "missing_metrics": list(facts.missing_metrics),
        "completeness": facts.completeness.value,
    }
