# ruff: noqa: E501
import hashlib
import json
import logging
from datetime import timedelta
from uuid import uuid4

from bet.enrichment.football.contracts import (
    BatchIdsCapability,
    BootstrapCommand,
    BuildSnapshotCommand,
    FootballFeatureSnapshotPayload,
    IncrementalCommand,
    InspectCommand,
    InspectResult,
    ReplayCommand,
    SnapshotResult,
    SyncResult,
    SystemClock,
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
from bet.integration.evidence import load_bundle_manifest

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
    def __init__(self, conn, provider: LiveAPIFootballAcquirer, sync_engine: FootballSyncEngine, repository: FootballHistoryRepository, feature_builder=None, clock=None):
        self.conn = conn
        self.provider = provider
        self.sync_engine = sync_engine
        self.repository = repository
        self.feature_builder = feature_builder
        self.persistence = CanonicalPersistence(conn)
        self.snapshot_service = SnapshotService(conn)
        self.clock = clock or SystemClock()
        self.sync_engine.clock = self.clock

    def bootstrap(self, cmd: BootstrapCommand) -> SyncResult:
        scope_key = compute_scope_key(cmd.competition_provider_id, cmd.season)
        lease_owner = uuid4().hex

        # 1. Acquire lease
        acquired = self.sync_engine.acquire_lease("api-football", "football", "completed-fixture-history", scope_key, lease_owner)
        if not acquired:
            return SyncResult(0, scope_key, None, None, {}, None, "LEASE_HELD", ("Lease is currently held by another process",))

        try:
            now_str = format_utc(self.clock.now_utc())

            # Find or create cursor
            cursor_row = self.conn.execute(
                """SELECT id, committed_through_date, coverage_json FROM sports_sync_cursor
                   WHERE provider='api-football' AND sport='football' AND operation='completed-fixture-history' AND scope_key=?
                """,
                (scope_key,)
            ).fetchone()

            coverage = {}
            if cursor_row:
                cursor_id, comm_date, coverage_str = cursor_row
                if coverage_str:
                    try:
                        coverage = json.loads(coverage_str)
                    except Exception:
                        pass
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

            # Load IDS capability cache
            batch_ids_cache = coverage.get("batch_ids", {})
            ids_state = batch_ids_cache.get("state", "UNKNOWN")
            checked_at_str = batch_ids_cache.get("checked_at")
            ttl_days = batch_ids_cache.get("ttl_days", 7)

            is_unexpired = False
            if ids_state == "UNSUPPORTED" and checked_at_str:
                checked_at = parse_canonical_or_offset_datetime(checked_at_str)
                if self.clock.now_utc() < checked_at + timedelta(days=ttl_days):
                    is_unexpired = True

            ids_capability = BatchIdsCapability.UNKNOWN
            if ids_state == "UNSUPPORTED" and is_unexpired:
                ids_capability = BatchIdsCapability.UNSUPPORTED
            elif ids_state == "SUPPORTED":
                ids_capability = BatchIdsCapability.SUPPORTED

            # Start Run
            run_identity = f"run_api-football_football_completed-fixture-history_{scope_key}_{now_str}"
            run_id = self.sync_engine.start_run(
                cursor_id, run_identity, "api-football", "football", "completed-fixture-history",
                scope_key, "BOOTSTRAP", cmd.from_date.isoformat(), cmd.to_date.isoformat(), cursor_before_json
            )

            # 2. Acquisition
            budget = PhysicalAttemptBudget(cmd.max_http_attempts)
            disc_res = self.provider.discover_completed_fixtures(
                competition_provider_id=cmd.competition_provider_id,
                season=cmd.season,
                from_date=cmd.from_date,
                to_date=cmd.to_date,
                max_fixtures=cmd.max_fixtures,
                attempt_budget=budget,
            )

            if disc_res.terminal_status != "COMPLETE":
                self.conn.commit()
                self.sync_engine.complete_run(run_id, disc_res.terminal_status, cursor_before_json, {
                    "physical_http_attempts": disc_res.physical_attempts,
                    "fallback_stats_calls": 0,
                    "discovered_count": 0,
                    "complete_count": 0,
                    "partial_count": 0,
                    "score_only_count": 0,
                    "permanently_unavailable_count": 0,
                    "transient_failed_count": 0,
                })
                return SyncResult(
                    sync_run_id=run_id,
                    scope_key=scope_key,
                    cursor_before=json.loads(cursor_before_json),
                    cursor_after=json.loads(cursor_before_json),
                    actual_counters={
                        "physical_http_attempts": disc_res.physical_attempts,
                        "fallback_stats_calls": 0,
                        "discovered_count": 0,
                        "complete_count": 0,
                        "partial_count": 0,
                        "score_only_count": 0,
                        "permanently_unavailable_count": 0,
                        "transient_failed_count": 0,
                    },
                    acquisition_result=None,
                    final_status=disc_res.terminal_status,
                    warnings=(),
                )

            # 3. Create sync items first as DISCOVERED
            for f in disc_res.completed_fixtures:
                self.conn.execute(
                    """INSERT INTO sports_sync_item
                       (provider, sport, scope_key, provider_fixture_id, state, first_seen_at, last_checked_at, created_at, updated_at)
                       VALUES ('api-football', 'football', ?, ?, 'DISCOVERED', ?, ?, ?, ?)
                       ON CONFLICT DO NOTHING
                    """,
                    (scope_key, f.provider_fixture_id, now_str, now_str, now_str, now_str)
                )
            self.conn.commit()

            # Selection rules
            provider_fixture_ids_to_enrich = []
            for f in disc_res.completed_fixtures:
                item_row = self.conn.execute(
                    """SELECT state FROM sports_sync_item
                       WHERE provider='api-football' AND sport='football' AND scope_key=? AND provider_fixture_id=?
                    """,
                    (scope_key, f.provider_fixture_id)
                ).fetchone()

                needs_enrich = True
                if item_row:
                    state = item_row[0]
                    kickoff_date = f.kickoff_at.date()
                    is_inside_correction = (cmd.from_date <= kickoff_date <= cmd.to_date)
                    if state in ("INGESTED_COMPLETE", "INGESTED_SCORE_ONLY", "INGESTED_PARTIAL"):
                        if not is_inside_correction:
                            needs_enrich = False

                if needs_enrich:
                    provider_fixture_ids_to_enrich.append(f.provider_fixture_id)

            acq_res = self.provider.acquire_fixture_facts(
                discovered_fixtures=disc_res.completed_fixtures,
                provider_fixture_ids_to_enrich=provider_fixture_ids_to_enrich,
                ids_capability=ids_capability,
                attempt_budget=budget,
                max_fallback_stats_calls=cmd.max_fallback_stats_calls,
                discovery_evidence_refs=disc_res.discovery_evidence_refs,
            )

            # 4. Persist and resolve transitions
            counters = {
                "physical_http_attempts": disc_res.physical_attempts + acq_res.physical_attempts,
                "fallback_stats_calls": acq_res.statistics_calls,
                "discovered_count": len(disc_res.completed_fixtures),
                "complete_count": len(disc_res.completed_fixtures) - len(acq_res.fixtures), # unchanged items treated as complete
                "partial_count": 0,
                "score_only_count": 0,
                "permanently_unavailable_count": 0,
                "transient_failed_count": 0,
            }

            for acq_fixture in acq_res.fixtures:
                p_res = self.persistence.persist_acquired_fixture(
                    acquired_fixture=acq_fixture,
                    scope_key=scope_key,
                    sync_run_id=run_id,
                )
                state = p_res.sync_item_state
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

            # Update cache state if we checked
            if acq_res.ids_capability != ids_capability:
                if acq_res.ids_capability == BatchIdsCapability.UNSUPPORTED:
                    coverage["batch_ids"] = {
                        "state": "UNSUPPORTED",
                        "checked_at": format_utc(self.clock.now_utc()),
                        "reason_code": "PLAN_RESTRICTED",
                        "ttl_days": 30
                    }
                elif acq_res.ids_capability == BatchIdsCapability.SUPPORTED:
                    coverage["batch_ids"] = {
                        "state": "SUPPORTED",
                        "checked_at": format_utc(self.clock.now_utc()),
                        "reason_code": "SUCCESS",
                        "ttl_days": 7
                    }
                self.conn.execute(
                    """UPDATE sports_sync_cursor
                       SET coverage_json = ?, updated_at = ?
                       WHERE id = ?
                    """,
                    (json.dumps(coverage, separators=(',', ':')), format_utc(self.clock.now_utc()), cursor_id)
                )

            # 5. Cursor advancement decision
            final_status = acq_res.terminal_status
            cursor_after_json = cursor_before_json

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
            now_str = format_utc(self.clock.now_utc())

            # Find cursor
            cursor_row = self.conn.execute(
                """SELECT id, committed_through_date, coverage_json FROM sports_sync_cursor
                   WHERE provider='api-football' AND sport='football' AND operation='completed-fixture-history' AND scope_key=?
                """,
                (scope_key,)
            ).fetchone()

            if not cursor_row:
                raise ValueError("No sync cursor exists. Run bootstrap first.")

            cursor_id, comm_date_str, coverage_str = cursor_row
            if not comm_date_str:
                raise ValueError("Cursor has never been bootstrapped. Run bootstrap first.")

            cursor_before_json = json.dumps({"committed_through_date": comm_date_str})

            coverage = {}
            if coverage_str:
                try:
                    coverage = json.loads(coverage_str)
                except Exception:
                    pass

            # Bounded lookback window
            comm_date = parse_canonical_or_offset_datetime(comm_date_str).date()
            from_date = comm_date - timedelta(days=cmd.correction_lookback_days)
            to_date = self.clock.today_utc()

            # Start sync run
            run_identity = f"run_api-football_football_completed-fixture-history_inc_{scope_key}_{now_str}"
            run_id = self.sync_engine.start_run(
                cursor_id, run_identity, "api-football", "football", "completed-fixture-history",
                scope_key, "INCREMENTAL", from_date.isoformat(), to_date.isoformat(), cursor_before_json
            )

            # Frozen incremental with 0 lookback days contract:
            if cmd.correction_lookback_days == 0 and comm_date == to_date:
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

            # Load IDS capability cache
            batch_ids_cache = coverage.get("batch_ids", {})
            ids_state = batch_ids_cache.get("state", "UNKNOWN")
            checked_at_str = batch_ids_cache.get("checked_at")
            ttl_days = batch_ids_cache.get("ttl_days", 7)

            is_unexpired = False
            if ids_state == "UNSUPPORTED" and checked_at_str:
                checked_at = parse_canonical_or_offset_datetime(checked_at_str)
                if self.clock.now_utc() < checked_at + timedelta(days=ttl_days):
                    is_unexpired = True

            ids_capability = BatchIdsCapability.UNKNOWN
            if ids_state == "UNSUPPORTED" and is_unexpired:
                ids_capability = BatchIdsCapability.UNSUPPORTED
            elif ids_state == "SUPPORTED":
                ids_capability = BatchIdsCapability.SUPPORTED

            # 2. Acquisition
            budget = PhysicalAttemptBudget(cmd.max_http_attempts)
            disc_res = self.provider.discover_completed_fixtures(
                competition_provider_id=cmd.competition_provider_id,
                season=cmd.season,
                from_date=from_date,
                to_date=to_date,
                max_fixtures=cmd.max_fixtures,
                attempt_budget=budget,
            )

            if disc_res.terminal_status != "COMPLETE":
                self.conn.commit()
                self.sync_engine.complete_run(run_id, disc_res.terminal_status, cursor_before_json, {
                    "physical_http_attempts": disc_res.physical_attempts,
                    "fallback_stats_calls": 0,
                    "discovered_count": 0,
                    "complete_count": 0,
                    "partial_count": 0,
                    "score_only_count": 0,
                    "permanently_unavailable_count": 0,
                    "transient_failed_count": 0,
                })
                return SyncResult(
                    sync_run_id=run_id,
                    scope_key=scope_key,
                    cursor_before=json.loads(cursor_before_json),
                    cursor_after=json.loads(cursor_before_json),
                    actual_counters={
                        "physical_http_attempts": disc_res.physical_attempts,
                        "fallback_stats_calls": 0,
                        "discovered_count": 0,
                        "complete_count": 0,
                        "partial_count": 0,
                        "score_only_count": 0,
                        "permanently_unavailable_count": 0,
                        "transient_failed_count": 0,
                    },
                    acquisition_result=None,
                    final_status=disc_res.terminal_status,
                    warnings=(),
                )

            # 3. Create / update sync items
            for f in disc_res.completed_fixtures:
                self.conn.execute(
                    """INSERT INTO sports_sync_item
                       (provider, sport, scope_key, provider_fixture_id, state, first_seen_at, last_checked_at, created_at, updated_at)
                       VALUES ('api-football', 'football', ?, ?, 'DISCOVERED', ?, ?, ?, ?)
                       ON CONFLICT DO NOTHING
                    """,
                    (scope_key, f.provider_fixture_id, now_str, now_str, now_str, now_str)
                )
            self.conn.commit()

            # Selection rules
            provider_fixture_ids_to_enrich = []
            for f in disc_res.completed_fixtures:
                item_row = self.conn.execute(
                    """SELECT state FROM sports_sync_item
                       WHERE provider='api-football' AND sport='football' AND scope_key=? AND provider_fixture_id=?
                    """,
                    (scope_key, f.provider_fixture_id)
                ).fetchone()

                needs_enrich = True
                if item_row:
                    state = item_row[0]
                    kickoff_date = f.kickoff_at.date()
                    is_inside_correction = (from_date <= kickoff_date <= to_date)
                    if state in ("INGESTED_COMPLETE", "INGESTED_SCORE_ONLY", "INGESTED_PARTIAL"):
                        if not is_inside_correction:
                            needs_enrich = False

                if needs_enrich:
                    provider_fixture_ids_to_enrich.append(f.provider_fixture_id)

            acq_res = self.provider.acquire_fixture_facts(
                discovered_fixtures=disc_res.completed_fixtures,
                provider_fixture_ids_to_enrich=provider_fixture_ids_to_enrich,
                ids_capability=ids_capability,
                attempt_budget=budget,
                max_fallback_stats_calls=cmd.max_fallback_stats_calls,
                discovery_evidence_refs=disc_res.discovery_evidence_refs,
            )

            # 4. Persist and evaluate transitions
            counters = {
                "physical_http_attempts": disc_res.physical_attempts + acq_res.physical_attempts,
                "fallback_stats_calls": acq_res.statistics_calls,
                "discovered_count": len(disc_res.completed_fixtures),
                "complete_count": len(disc_res.completed_fixtures) - len(acq_res.fixtures),
                "partial_count": 0,
                "score_only_count": 0,
                "permanently_unavailable_count": 0,
                "transient_failed_count": 0,
            }

            for acq_fixture in acq_res.fixtures:
                completed_facts = merge_completed_match_facts(
                    acq_fixture.fixture,
                    acq_fixture.statistics_by_provider_team_id,
                    "dummy_b",
                    "dummy_b"
                )
                from bet.enrichment.football.contracts import serialize_team_match_facts
                sorted_facts = sorted([completed_facts.home, completed_facts.away], key=lambda f: str(f.provider_team_id))
                facts_list = [serialize_team_match_facts(f) for f in sorted_facts]
                normalized_payload_json = json.dumps(facts_list, separators=(',', ':'), sort_keys=True)
                new_hash = hashlib.sha256(normalized_payload_json.encode('utf-8')).hexdigest().lower()

                row = self.conn.execute(
                    """SELECT normalized_payload_sha256 FROM sports_sync_item
                       WHERE provider='api-football' AND sport='football' AND scope_key=? AND provider_fixture_id=?
                    """,
                    (scope_key, acq_fixture.fixture.provider_fixture_id)
                ).fetchone()

                if row and row[0] == new_hash:
                    counters["complete_count"] += 1
                    continue

                p_res = self.persistence.persist_acquired_fixture(
                    acquired_fixture=acq_fixture,
                    scope_key=scope_key,
                    sync_run_id=run_id,
                )
                state = p_res.sync_item_state
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

            # Update cache state if we checked
            if acq_res.ids_capability != ids_capability:
                if acq_res.ids_capability == BatchIdsCapability.UNSUPPORTED:
                    coverage["batch_ids"] = {
                        "state": "UNSUPPORTED",
                        "checked_at": format_utc(self.clock.now_utc()),
                        "reason_code": "PLAN_RESTRICTED",
                        "ttl_days": 30
                    }
                elif acq_res.ids_capability == BatchIdsCapability.SUPPORTED:
                    coverage["batch_ids"] = {
                        "state": "SUPPORTED",
                        "checked_at": format_utc(self.clock.now_utc()),
                        "reason_code": "SUCCESS",
                        "ttl_days": 7
                    }
                self.conn.execute(
                    """UPDATE sports_sync_cursor
                       SET coverage_json = ?, updated_at = ?
                       WHERE id = ?
                    """,
                    (json.dumps(coverage, separators=(',', ':')), format_utc(self.clock.now_utc()), cursor_id)
                )

            # 5. Cursor advancement
            final_status = acq_res.terminal_status
            cursor_after_json = cursor_before_json

            # Incremental committed through date can advance up to clock.today_utc() - 1 day
            max_comm_date = to_date - timedelta(days=1)
            if counters["transient_failed_count"] == 0 and final_status == "COMPLETE":
                if max_comm_date >= from_date:
                    cursor_after_json = json.dumps({"committed_through_date": max_comm_date.isoformat()})
                    self.conn.execute(
                        """UPDATE sports_sync_cursor
                           SET committed_through_date = ?, last_success_at = ?, updated_at = ?
                           WHERE id = ?
                        """,
                        (max_comm_date.isoformat(), now_str, now_str, cursor_id)
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
        now_str = format_utc(self.clock.now_utc())

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

        if acq_res.fixtures:
            first_fixture = acq_res.fixtures[0].fixture
            scope_key = compute_scope_key(first_fixture.provider_competition_id, first_fixture.season)
        else:
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

            p_res = self.persistence.persist_acquired_fixture(
                acquired_fixture=acq_fixture,
                scope_key=scope_key,
                sync_run_id=run_id,
            )
            state = p_res.sync_item_state
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

    def inspect_fixture(self, cmd: InspectCommand) -> InspectResult:
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

        from bet.enrichment.football.contracts import FixtureInspectData, InspectResult

        if not row:
            return InspectResult(status="NOT_FOUND")

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

        fixture_data = FixtureInspectData(
            id=fix_id,
            provider_id=ext_id,
            status=status,
            score={"home": score_home, "away": score_away},
            kickoff=kickoff,
            observations=tuple(observations),
            projections=tuple(projections)
        )
        return InspectResult(status="SUCCESS", actual_data=fixture_data)

    def inspect_team(self, cmd: InspectCommand) -> InspectResult:
        if not cmd.team_id:
            raise ValueError("team_id must be provided")

        row = self.conn.execute(
            """SELECT id, name FROM teams WHERE id = ?""",
            (cmd.team_id,)
        ).fetchone()

        from bet.enrichment.football.contracts import InspectResult, TeamInspectData

        if not row:
            return InspectResult(status="NOT_FOUND")

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

        team_data = TeamInspectData(
            id=team_id,
            name=name,
            completed_fixtures_count=fix_count,
            latest_observations=tuple(latest_obs)
        )
        return InspectResult(status="SUCCESS", actual_data=team_data)


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

        # Get team provider IDs (require active references, fail closed if missing)
        h_prov = self.conn.execute(
            "SELECT provider_entity_id FROM source_entity_reference WHERE sport='football' AND entity_type='TEAM' AND provider='api-football' AND valid_to IS NULL AND canonical_entity_id=(SELECT id FROM sports_entity WHERE domain_table='teams' AND domain_entity_id=?)",
            (h_id,)
        ).fetchone()

        a_prov = self.conn.execute(
            "SELECT provider_entity_id FROM source_entity_reference WHERE sport='football' AND entity_type='TEAM' AND provider='api-football' AND valid_to IS NULL AND canonical_entity_id=(SELECT id FROM sports_entity WHERE domain_table='teams' AND domain_entity_id=?)",
            (a_t_id,)
        ).fetchone()

        if not h_prov:
            raise ValueError(f"Active api-football team reference not found for home team {h_id}")
        if not a_prov:
            raise ValueError(f"Active api-football team reference not found for away team {a_t_id}")

        h_prov_id = h_prov[0]
        a_prov_id = a_prov[0]

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
        missingness = set()

        for w in metric_windows:
            if w.available_count == 0:
                missingness.add(f"{w.metric}_{w.scope}")
            for s in w.samples:
                src_fixture_ids.add(s.provider_fixture_id)
                logical_ids.add(s.observation_logical_identity)

        # Collect stable evidence fingerprint hashes belonging to selected observations
        stable_hashes = set()
        for logical_id in logical_ids:
            manifest_row = self.conn.execute(
                "SELECT evidence_bundle_id FROM fixture_capability_observation WHERE logical_identity = ?",
                (logical_id,)
            ).fetchone()
            if manifest_row and manifest_row[0]:
                bundle_id = manifest_row[0]
                try:
                    manifest_dict = load_bundle_manifest(bundle_id)
                    for entry in manifest_dict.get("entries", []):
                        fingerprint = {
                            "operation": entry.operation,
                            "request_identity": entry.request_identity,
                            "source_event_id": entry.source_event_id,
                            "object_sha256": entry.object_sha256,
                            "byte_size": entry.byte_size,
                        }
                        canonical_bytes = json.dumps(fingerprint, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode("utf-8")
                        stable_hashes.add(hashlib.sha256(canonical_bytes).hexdigest())
                except Exception:
                    pass

        policy_config = {
            "provider": "api-football",
            "metrics": sorted(metrics_list),
            "windows": ["overall_l5", "overall_l10", "h2h_l5", "home_l5", "away_l5"],
            "accepted_observation_statuses": ["SUCCESS", "PARTIAL"],
            "rounding_version": "v1",
            "stable_evidence_provenance_version": "v1"
        }
        policy_config_json = json.dumps(policy_config, sort_keys=True, separators=(',', ':'))
        policy_config_hash = hashlib.sha256(policy_config_json.encode('utf-8')).hexdigest().lower()

        # Calculate max observed_at from selected samples as data_as_of_at
        selected_observed_ats = [s.observed_at for s in h_samples + a_samples]
        data_as_of_at = max(selected_observed_ats) if selected_observed_ats else None

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
            evidence_bundle_ids=tuple(sorted(stable_hashes)), # Populate with stable fingerprint hashes!
            missingness=tuple(sorted(missingness)),
            data_as_of_at=data_as_of_at
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

        # Load EVENT sports_entity ID to use as canonical_event_id
        se_id_row = self.conn.execute(
            """SELECT id FROM sports_entity
               WHERE entity_type = 'EVENT' AND domain_table = 'fixtures' AND domain_entity_id = ?
            """,
            (cmd.canonical_target_fixture_id,)
        ).fetchone()
        if not se_id_row:
            raise ValueError(f"EVENT sports_entity not found for target fixture {cmd.canonical_target_fixture_id}")
        canonical_event_id = se_id_row[0]

        # Run and snapshot persistence in one explicit transaction
        in_txn = self.conn.in_transaction
        if not in_txn:
            self.conn.execute("BEGIN TRANSACTION")
        try:
            # Check if run exists
            run_row = self.conn.execute("SELECT id FROM sports_enrichment_run WHERE run_identity = ?", (run_identity,)).fetchone()
            if run_row:
                run_id = run_row[0]
            else:
                now_str = format_utc(self.clock.now_utc())
                r_res = self.conn.execute(
                    """INSERT INTO sports_enrichment_run
                       (run_identity, sport, canonical_event_id, analysis_cutoff_at, started_at, status, policy_config_hash, requested_capabilities)
                       VALUES (?, 'football', ?, ?, ?, 'COMPLETE', ?, 'TEAM_MATCH_FACTS')
                    """,
                    (run_identity, canonical_event_id, format_utc(cmd.analysis_cutoff_at), now_str, policy_config_hash)
                )
                run_id = r_res.lastrowid

            snap_res = self.snapshot_service.build_and_persist(payload, run_id, cmd.canonical_target_fixture_id)
            if not in_txn:
                self.conn.commit()

            created_or_reused = "REUSED" if run_row else "CREATED"

            return SnapshotResult(
                run_id=run_id,
                snapshot_id=snap_res["snapshot_id"],
                snapshot_hash=snap_res["snapshot_hash"],
                created_or_reused=created_or_reused,
                deterministic_drift=False
            )
        except Exception as e:
            if not in_txn:
                try:
                    self.conn.execute("ROLLBACK")
                except Exception:
                    pass
            raise e
