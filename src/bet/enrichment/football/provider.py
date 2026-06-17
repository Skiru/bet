# ruff: noqa: E501
import logging
from datetime import date
from typing import Any

from bet.api_clients.api_football import APIFootballClient
from bet.api_clients.base_client import SourceResultStatus
from bet.enrichment.football.contracts import (
    AcquiredFixture,
    AcquisitionMode,
    AcquisitionResult,
    BatchIdsCapability,
    DiscoveredFixtureRecord,
    DiscoveryResult,
    FootballFixtureIdentity,
)
from bet.enrichment.football.parser import (
    FootballParserError,
    parse_api_football_fixture_envelope,
    parse_api_football_statistics_envelope,
)
from bet.enrichment.football.time import parse_canonical_or_offset_datetime

logger = logging.getLogger(__name__)

class PhysicalAttemptBudget:
    def __init__(self, limit: int):
        self._limit = limit
        self._reserved = 0
        self._committed = 0

    @property
    def remaining(self) -> int:
        return max(0, self._limit - self._committed - self._reserved)

    def reserve(self, max_possible_attempts: int) -> int:
        self._reserved += max_possible_attempts
        return max_possible_attempts

    def commit(self, reservation: int, actual_attempts: int):
        self._reserved -= reservation
        self._committed += actual_attempts

    def cancel(self, reservation: int):
        self._reserved -= reservation


class LiveAPIFootballAcquirer:
    def __init__(self, client: APIFootballClient):
        self.client = client

    def discover_completed_fixtures(
        self,
        *,
        competition_provider_id: str,
        season: int,
        from_date: date,
        to_date: date,
        max_fixtures: int,
        attempt_budget: PhysicalAttemptBudget,
    ) -> DiscoveryResult:
        physical_attempts = 0
        retry_attempts = 0
        quota_metadata = {}

        if attempt_budget.remaining < 2:
            return DiscoveryResult((), (), (), False, 0, 0, {}, "RATE_LIMITED")

        res_id = attempt_budget.reserve(2)
        disc_res = self.client.get_history_discovery(
            competition_provider_id, season, from_date.isoformat(), to_date.isoformat()
        )
        actual_att = disc_res.retry_count + 1
        attempt_budget.commit(res_id, actual_att)
        physical_attempts += actual_att
        retry_attempts += disc_res.retry_count

        if disc_res.quota_metadata:
            quota_metadata.update(disc_res.quota_metadata)

        if disc_res.status != SourceResultStatus.SUCCESS or not disc_res.value:
            term_status = "FAILED"
            if disc_res.status == SourceResultStatus.RATE_LIMITED:
                term_status = "RATE_LIMITED"
            return DiscoveryResult((), (), (), False, physical_attempts, retry_attempts, quota_metadata, term_status)

        raw_items = disc_res.value.get("response", [])
        completed_fixtures = []
        invalid_records = []
        for item in raw_items:
            status_short = item.get("fixture", {}).get("status", {}).get("short", "")
            if status_short in ("FT", "AET", "PEN"):
                fix_id = str(item.get("fixture", {}).get("id", ""))
                try:
                    if not fix_id:
                        raise ValueError("Missing provider_fixture_id in discovery item")

                    fixture_obj = parse_api_football_fixture_envelope(item, fix_id)

                    # Validate that identity, kickoff time and score are fully present/valid
                    if (not fixture_obj.provider_fixture_id or
                        not fixture_obj.home_provider_team_id or
                        not fixture_obj.away_provider_team_id or
                        fixture_obj.kickoff_at is None or
                        fixture_obj.home_score is None or
                        fixture_obj.away_score is None):
                        raise ValueError("Malformed completed fixture identity, kickoff, or score")

                    completed_fixtures.append(fixture_obj)
                except Exception as e:
                    logger.warning(f"Failed to parse discovery fixture {fix_id}: {e}")
                    rec = DiscoveredFixtureRecord(
                        fixture=None,
                        provider_fixture_id=fix_id or None,
                        state="INVALID",
                        error_code=f"PARSING_ERROR: {str(e)}",
                        evidence_refs=disc_res.evidence_refs
                    )
                    invalid_records.append(rec)

        completed_fixtures = completed_fixtures[:max_fixtures]

        term_status = "COMPLETE"
        if invalid_records:
            term_status = "DEGRADED"

        return DiscoveryResult(
            valid_fixtures=tuple(completed_fixtures),
            invalid_records=tuple(invalid_records),
            discovery_evidence_refs=disc_res.evidence_refs,
            paging_completed=True,
            physical_attempts=physical_attempts,
            retry_attempts=retry_attempts,
            quota_metadata=quota_metadata,
            terminal_status=term_status,
        )

    def acquire_fixture_facts(
        self,
        *,
        discovered_fixtures: tuple[FootballFixtureIdentity, ...],
        provider_fixture_ids_to_enrich: list[str],
        ids_capability: BatchIdsCapability,
        attempt_budget: PhysicalAttemptBudget,
        max_fallback_stats_calls: int,
        discovery_evidence_refs: tuple[Any, ...] = (),
    ) -> AcquisitionResult:
        physical_attempts = 0
        retry_attempts = 0
        ids_calls = 0
        statistics_calls = 0
        quota_metadata = {}

        fixtures_map = {f.provider_fixture_id: f for f in discovered_fixtures}

        stats_by_fixture = {}
        fixture_provenance = {}
        fixture_errors = {}
        fixture_diagnostics = {}

        if ids_capability in (BatchIdsCapability.UNKNOWN, BatchIdsCapability.SUPPORTED) and provider_fixture_ids_to_enrich:
            chunks = [provider_fixture_ids_to_enrich[i:i+20] for i in range(0, len(provider_fixture_ids_to_enrich), 20)]

            for chunk in chunks:
                if attempt_budget.remaining < 2:
                    break

                res_id = attempt_budget.reserve(2)
                details_res = self.client.get_history_details(chunk)
                actual_att = details_res.retry_count + 1
                attempt_budget.commit(res_id, actual_att)
                physical_attempts += actual_att
                retry_attempts += details_res.retry_count
                ids_calls += 1
                if details_res.quota_metadata:
                    quota_metadata.update(details_res.quota_metadata)

                if details_res.status == SourceResultStatus.PLAN_RESTRICTED:
                    ids_capability = BatchIdsCapability.UNSUPPORTED
                    break

                if details_res.status == SourceResultStatus.RATE_LIMITED:
                    for fid in chunk:
                        fixture_errors[fid] = "RATE_LIMITED"
                    ids_capability = BatchIdsCapability.UNSUPPORTED
                    break
                elif details_res.status in (SourceResultStatus.TIMEOUT, SourceResultStatus.TRANSPORT_ERROR, SourceResultStatus.UPSTREAM_ERROR):
                    for fid in chunk:
                        fixture_errors[fid] = "TRANSIENT_FAILED"
                    ids_capability = BatchIdsCapability.UNSUPPORTED
                    break

                if details_res.status == SourceResultStatus.SUCCESS and details_res.value:
                    ids_capability = BatchIdsCapability.SUPPORTED
                    resp_items = details_res.value.get("response", [])
                    for item in resp_items:
                        fix_id = str(item.get("fixture", {}).get("id", ""))
                        if fix_id in fixtures_map:
                            fixture_provenance[fix_id] = details_res.evidence_refs
                            stats_list = item.get("statistics", [])
                            if isinstance(stats_list, list) and stats_list:
                                try:
                                    fix_obj = fixtures_map[fix_id]
                                    parsed_stats = parse_api_football_statistics_envelope(
                                        stats_list, fix_obj.home_provider_team_id, fix_obj.away_provider_team_id
                                    )
                                    stats_by_fixture[fix_id] = (parsed_stats, details_res.evidence_refs)
                                except FootballParserError as e:
                                    logger.error(f"Failed to parse embedded stats for {fix_id}: {e}")
                                    fixture_errors[fix_id] = "TRANSIENT_FAILED"
                                except Exception as e:
                                    logger.error(f"Unexpected error parsing embedded stats for {fix_id}: {e}")
                                    fixture_errors[fix_id] = "TRANSIENT_FAILED"

        for fix_id in provider_fixture_ids_to_enrich:
            if fix_id in fixtures_map and fix_id not in stats_by_fixture and fix_id not in fixture_errors:
                if statistics_calls >= max_fallback_stats_calls:
                    continue
                if attempt_budget.remaining < 2:
                    break

                res_id = attempt_budget.reserve(2)
                stats_res = self.client.get_history_statistics(fix_id)
                actual_att = stats_res.retry_count + 1
                attempt_budget.commit(res_id, actual_att)
                physical_attempts += actual_att
                retry_attempts += stats_res.retry_count
                statistics_calls += 1
                if stats_res.quota_metadata:
                    quota_metadata.update(stats_res.quota_metadata)

                if stats_res.status == SourceResultStatus.SUCCESS and stats_res.value:
                    resp_stats = stats_res.value.get("response", [])
                    if isinstance(resp_stats, list) and not resp_stats:
                        # VALID EMPTY RESPONSE
                        stats_by_fixture[fix_id] = ({}, stats_res.evidence_refs)
                    else:
                        try:
                            fix_obj = fixtures_map[fix_id]
                            parsed_stats = parse_api_football_statistics_envelope(
                                resp_stats, fix_obj.home_provider_team_id, fix_obj.away_provider_team_id
                            )
                            stats_by_fixture[fix_id] = (parsed_stats, stats_res.evidence_refs)
                        except FootballParserError as e:
                            logger.error(f"Failed to parse fallback stats for {fix_id}: {e}")
                            fixture_errors[fix_id] = "TRANSIENT_FAILED"
                        except Exception as e:
                            logger.error(f"Unexpected error parsing fallback stats for {fix_id}: {e}")
                            fixture_errors[fix_id] = "TRANSIENT_FAILED"
                elif stats_res.status in (SourceResultStatus.PLAN_RESTRICTED, SourceResultStatus.NOT_SUPPORTED, SourceResultStatus.UNSUPPORTED):
                    stats_by_fixture[fix_id] = ({}, stats_res.evidence_refs)
                    fixture_diagnostics[fix_id] = "PLAN_RESTRICTED"
                elif stats_res.status == SourceResultStatus.VALID_EMPTY:
                    stats_by_fixture[fix_id] = ({}, stats_res.evidence_refs)
                elif stats_res.status == SourceResultStatus.RATE_LIMITED:
                    fixture_errors[fix_id] = "RATE_LIMITED"
                elif stats_res.status in (SourceResultStatus.TIMEOUT, SourceResultStatus.TRANSPORT_ERROR, SourceResultStatus.UPSTREAM_ERROR):
                    fixture_errors[fix_id] = "TRANSIENT_FAILED"
                else:
                    fixture_errors[fix_id] = "TRANSIENT_FAILED"

        acquired_fixtures = []
        for fix_id in provider_fixture_ids_to_enrich:
            if fix_id in fixtures_map:
                fix_obj = fixtures_map[fix_id]
                details_refs = fixture_provenance.get(fix_id, ())
                stats_tuple = stats_by_fixture.get(fix_id)

                stats_by_team = {}
                stats_refs = ()
                if stats_tuple:
                    stats_by_team, stats_refs = stats_tuple

                combined_refs = list(discovery_evidence_refs) + list(details_refs) + list(stats_refs)
                max_captured = None
                for ref in combined_refs:
                    if getattr(ref, "captured_at", None):
                        if max_captured is None or ref.captured_at > max_captured:
                            max_captured = ref.captured_at

                if not max_captured:
                    raise ValueError("MISSING_EVIDENCE_TIMESTAMP")

                observed_at_dt = parse_canonical_or_offset_datetime(max_captured)

                if fix_id in fixture_errors:
                    mode = AcquisitionMode(fixture_errors[fix_id])
                    warnings = [f"Acquisition failed: {fixture_errors[fix_id]}"]
                elif stats_refs:
                    mode = AcquisitionMode.PER_FIXTURE_STATS
                    warnings = []
                elif details_refs:
                    mode = AcquisitionMode.BATCH_IDS
                    warnings = []
                else:
                    mode = AcquisitionMode.DISCOVERY_ENVELOPE
                    warnings = []

                if not stats_by_team and fix_id not in fixture_errors:
                    warnings.append("No statistics available")

                acquired = AcquiredFixture(
                    fixture=fix_obj,
                    statistics_by_provider_team_id=stats_by_team,
                    fixture_evidence_refs=tuple(discovery_evidence_refs) + tuple(details_refs),
                    statistics_evidence_refs=tuple(stats_refs),
                    observed_at=observed_at_dt,
                    acquisition_mode=mode,
                    warnings=tuple(warnings),
                )
                acquired_fixtures.append(acquired)

        term_status = "COMPLETE"
        if any(v == "RATE_LIMITED" for v in fixture_errors.values()):
            term_status = "RATE_LIMITED"
        elif any(v == "TRANSIENT_FAILED" for v in fixture_errors.values()):
            term_status = "TRANSIENT_FAILED"
        elif len(acquired_fixtures) < len(provider_fixture_ids_to_enrich):
            term_status = "DEGRADED"

        return AcquisitionResult(
            fixtures=tuple(acquired_fixtures),
            physical_attempts=physical_attempts,
            retry_attempts=retry_attempts,
            discovery_calls=0,
            ids_calls=ids_calls,
            statistics_calls=statistics_calls,
            quota_metadata=quota_metadata,
            ids_capability=ids_capability,
            terminal_status=term_status,
        )

    def acquire(
        self,
        *,
        competition_provider_id: str,
        season: int,
        from_date: date,
        to_date: date,
        max_fixtures: int,
        max_fallback_stats_calls: int,
        attempt_budget: PhysicalAttemptBudget,
        ids_capability: BatchIdsCapability,
    ) -> AcquisitionResult:
        disc_res = self.discover_completed_fixtures(
            competition_provider_id=competition_provider_id,
            season=season,
            from_date=from_date,
            to_date=to_date,
            max_fixtures=max_fixtures,
            attempt_budget=attempt_budget,
        )
        if disc_res.terminal_status != "COMPLETE":
            return AcquisitionResult(
                fixtures=(),
                physical_attempts=disc_res.physical_attempts,
                retry_attempts=disc_res.retry_attempts,
                discovery_calls=1,
                ids_calls=0,
                statistics_calls=0,
                quota_metadata=disc_res.quota_metadata,
                ids_capability=ids_capability,
                terminal_status=disc_res.terminal_status,
            )

        ids_to_enrich = [f.provider_fixture_id for f in disc_res.completed_fixtures]

        acq_res = self.acquire_fixture_facts(
            discovered_fixtures=disc_res.completed_fixtures,
            provider_fixture_ids_to_enrich=ids_to_enrich,
            ids_capability=ids_capability,
            attempt_budget=attempt_budget,
            max_fallback_stats_calls=max_fallback_stats_calls,
            discovery_evidence_refs=disc_res.discovery_evidence_refs,
        )

        return AcquisitionResult(
            fixtures=acq_res.fixtures,
            physical_attempts=disc_res.physical_attempts + acq_res.physical_attempts,
            retry_attempts=disc_res.retry_attempts + acq_res.retry_attempts,
            discovery_calls=1,
            ids_calls=acq_res.ids_calls,
            statistics_calls=acq_res.statistics_calls,
            quota_metadata={**disc_res.quota_metadata, **acq_res.quota_metadata},
            ids_capability=acq_res.ids_capability,
            terminal_status=acq_res.terminal_status,
        )
