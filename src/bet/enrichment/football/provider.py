# ruff: noqa: E501
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime

from bet.api_clients.api_football import APIFootballClient
from bet.api_clients.base_client import SourceResultStatus
from bet.enrichment.football.contracts import (
    AcquiredFixture,
    AcquisitionMode,
    AcquisitionResult,
    BatchIdsCapability,
    FootballFixtureIdentity,
)
from bet.enrichment.football.parser import (
    parse_api_football_fixture_envelope,
    parse_api_football_statistics_envelope,
)
from bet.enrichment.football.time import format_utc, parse_canonical_or_offset_datetime

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
        physical_attempts = 0
        retry_attempts = 0
        discovery_calls = 0
        ids_calls = 0
        statistics_calls = 0
        quota_metadata = {}

        # 1. Discovery
        if attempt_budget.remaining < 2:
            return AcquisitionResult((), 0, 0, 0, 0, 0, {}, ids_capability, "RATE_LIMITED")

        res_id = attempt_budget.reserve(2)
        disc_res = self.client.get_history_discovery(
            competition_provider_id, season, from_date.isoformat(), to_date.isoformat()
        )
        actual_att = disc_res.retry_count + 1
        attempt_budget.commit(res_id, actual_att)
        physical_attempts += actual_att
        retry_attempts += disc_res.retry_count
        discovery_calls += 1
        if disc_res.quota_metadata:
            quota_metadata.update(disc_res.quota_metadata)

        if disc_res.status != SourceResultStatus.SUCCESS or not disc_res.value:
            term_status = "FAILED"
            if disc_res.status == SourceResultStatus.RATE_LIMITED:
                term_status = "RATE_LIMITED"
            return AcquisitionResult((), physical_attempts, retry_attempts, discovery_calls, 0, 0, quota_metadata, ids_capability, term_status)

        raw_items = disc_res.value.get("response", [])
        completed_raw = []
        for item in raw_items:
            status_short = item.get("fixture", {}).get("status", {}).get("short", "")
            if status_short in ("FT", "AET", "PEN"):
                completed_raw.append(item)

        # Limit count
        completed_raw = completed_raw[:max_fixtures]

        # Parse basic identities
        fixtures_map = {} # provider_fixture_id -> (FootballFixtureIdentity, EvidenceRef)
        for item in completed_raw:
            fix_id = str(item.get("fixture", {}).get("id", ""))
            if fix_id:
                try:
                    fixture_obj = parse_api_football_fixture_envelope(item, fix_id)
                    fixtures_map[fix_id] = (fixture_obj, disc_res.evidence_refs)
                except Exception as e:
                    logger.warning(f"Failed to parse discovery fixture {fix_id}: {e}")

        # 2. Batch Details (IDs optimization)
        stats_by_fixture = {} # fixture_id -> (stats_by_team, EvidenceRef)
        fixture_provenance = {} # fixture_id -> tuple[EvidenceRef, ...] (the details call evidence refs)

        if ids_capability in (BatchIdsCapability.UNKNOWN, BatchIdsCapability.SUPPORTED) and fixtures_map:
            fixture_ids_list = sorted(list(fixtures_map.keys()))
            chunks = [fixture_ids_list[i:i+20] for i in range(0, len(fixture_ids_list), 20)]

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

                if details_res.status == SourceResultStatus.SUCCESS and details_res.value:
                    ids_capability = BatchIdsCapability.SUPPORTED
                    resp_items = details_res.value.get("response", [])
                    for item in resp_items:
                        fix_id = str(item.get("fixture", {}).get("id", ""))
                        if fix_id in fixtures_map:
                            fixture_provenance[fix_id] = details_res.evidence_refs
                            # Parse detailed statistics if embedded
                            stats_list = item.get("statistics", [])
                            if isinstance(stats_list, list) and stats_list:
                                try:
                                    fix_obj = fixtures_map[fix_id][0]
                                    parsed_stats = parse_api_football_statistics_envelope(
                                        stats_list, fix_obj.home_provider_team_id, fix_obj.away_provider_team_id
                                    )
                                    stats_by_fixture[fix_id] = (parsed_stats, details_res.evidence_refs)
                                except Exception as e:
                                    logger.warning(f"Failed to parse embedded stats for {fix_id}: {e}")

        # 3. Statistics Fallback
        for fix_id, (fix_obj, disc_refs) in fixtures_map.items():
            if fix_id not in stats_by_fixture:
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
                    try:
                        parsed_stats = parse_api_football_statistics_envelope(
                            resp_stats, fix_obj.home_provider_team_id, fix_obj.away_provider_team_id
                        )
                        stats_by_fixture[fix_id] = (parsed_stats, stats_res.evidence_refs)
                    except Exception as e:
                        logger.warning(f"Failed to parse fallback stats for {fix_id}: {e}")

        # 4. Assemble AcquiredFixtures
        acquired_fixtures = []
        for fix_id, (fix_obj, disc_refs) in fixtures_map.items():
            details_refs = fixture_provenance.get(fix_id, ())
            stats_tuple = stats_by_fixture.get(fix_id)

            stats_by_team = {}
            stats_refs = ()
            if stats_tuple:
                stats_by_team, stats_refs = stats_tuple

            combined_refs = list(disc_refs) + list(details_refs) + list(stats_refs)
            max_captured = None
            for ref in combined_refs:
                if ref.captured_at:
                    if max_captured is None or ref.captured_at > max_captured:
                        max_captured = ref.captured_at

            observed_at_dt = parse_canonical_or_offset_datetime(max_captured or format_utc(datetime.now(UTC)))

            # Determine mode
            if stats_refs:
                mode = AcquisitionMode.PER_FIXTURE_STATS
            elif details_refs:
                mode = AcquisitionMode.BATCH_IDS
            else:
                mode = AcquisitionMode.DISCOVERY_ENVELOPE

            warnings = []
            if not stats_by_team:
                warnings.append("No statistics available")

            acquired = AcquiredFixture(
                fixture=fix_obj,
                statistics_by_provider_team_id=stats_by_team,
                fixture_evidence_refs=tuple(disc_refs) + tuple(details_refs),
                statistics_evidence_refs=tuple(stats_refs),
                observed_at=observed_at_dt,
                acquisition_mode=mode,
                warnings=tuple(warnings),
            )
            acquired_fixtures.append(acquired)

        term_status = "COMPLETE" if len(acquired_fixtures) == len(fixtures_map) else "DEGRADED"
        if not acquired_fixtures and fixtures_map:
            term_status = "FAILED"

        return AcquisitionResult(
            fixtures=tuple(acquired_fixtures),
            physical_attempts=physical_attempts,
            retry_attempts=retry_attempts,
            discovery_calls=discovery_calls,
            ids_calls=ids_calls,
            statistics_calls=statistics_calls,
            quota_metadata=quota_metadata,
            ids_capability=ids_capability,
            terminal_status=term_status, # Wait, the DTO uses terminal_status but the keyword here is term_status? Let's verify!
        )


@dataclass
class ProviderQuota:
    requests_limit: int | None
    requests_remaining: int | None

@dataclass
class OrchestratedBatchResult:
    fixtures: list[FootballFixtureIdentity]
    stats: dict[str, dict[str, dict[str, int | float | None]]]
    physical_http_attempts: int
    fallback_stats_calls: int
    quota: ProviderQuota
    evidence_bundle_ids: list[str]

class APIFootballOrchestrator:
    def __init__(self, client: APIFootballClient, quota_reserve: int = 10):
        self.client = client
        self.quota_reserve = quota_reserve

    def get_coverage(self, league_id: str, season: int) -> bool:
        res = self.client.get_leagues_coverage(league_id, season)
        if res.status != SourceResultStatus.SUCCESS or not res.value:
            return False
        try:
            leagues = res.value.get("response", [])
            if not leagues:
                return False
            coverage = leagues[0].get("seasons", [{}])[0].get("coverage", {})
            return bool(coverage.get("fixtures", {}).get("statistics_fixtures", False))
        except Exception:
            return False

    def discover_completed_fixtures(self, league_id: str, season: int, from_date: str, to_date: str) -> list[str]:
        res = self.client.get_history_discovery(league_id, season, from_date, to_date)
        if res.status != SourceResultStatus.SUCCESS or not res.value:
            return []
        fixtures = []
        for item in res.value.get("response", []):
            status = item.get("fixture", {}).get("status", {}).get("short", "")
            if status in ("FT", "AET", "PEN"):
                fix_id = str(item.get("fixture", {}).get("id", ""))
                if fix_id:
                    fixtures.append(fix_id)
        return fixtures

    def get_fixtures_and_stats(self, fixture_ids: list[str], require_stats: bool = True, max_fallback_calls: int = 100) -> OrchestratedBatchResult:
        all_fixtures = []
        all_stats = {}
        all_bundles = []
        http_attempts = 0
        fallback_calls = 0

        clean_ids = sorted(list(set(str(i).strip() for i in fixture_ids if str(i).strip())))
        chunks = [clean_ids[i:i + 20] for i in range(0, len(clean_ids), 20)]
        quota = ProviderQuota(None, None)

        for chunk in chunks:
            if quota.requests_remaining is not None and quota.requests_remaining <= self.quota_reserve:
                break

            res = self.client.get_history_details(chunk)
            http_attempts += res.retry_count + 1

            if res.quota_metadata:
                quota.requests_limit = res.quota_metadata.get("requests_limit")
                quota.requests_remaining = res.quota_metadata.get("requests_remaining")

            if res.bundle_id:
                all_bundles.append(res.bundle_id)

            if res.status != SourceResultStatus.SUCCESS or not res.value:
                continue

            response_items = res.value.get("response", [])
            for item in response_items:
                fix_id = str(item.get("fixture", {}).get("id", ""))
                if not fix_id:
                    continue
                try:
                    fixture = parse_api_football_fixture_envelope(item, fix_id)
                except Exception as e:
                    logger.error(f"Failed to parse fixture {fix_id}: {e}")
                    continue
                all_fixtures.append(fixture)

                has_embedded_stats = False
                stats_list = item.get("statistics", [])
                if isinstance(stats_list, list) and len(stats_list) > 0:
                    try:
                        parsed_stats = parse_api_football_statistics_envelope(stats_list, fixture.home_provider_team_id, fixture.away_provider_team_id)
                        if any(parsed_stats.values()):
                            has_embedded_stats = True
                            all_stats[fix_id] = parsed_stats
                    except Exception as e:
                        logger.error(f"Failed to parse embedded stats for {fix_id}: {e}")

                if require_stats and not has_embedded_stats:
                    if fallback_calls >= max_fallback_calls:
                        continue
                    if quota.requests_remaining is not None and quota.requests_remaining <= self.quota_reserve:
                        continue

                    fallback_res = self.client.get_history_statistics(fix_id)
                    http_attempts += fallback_res.retry_count + 1
                    fallback_calls += 1

                    if fallback_res.quota_metadata:
                        quota.requests_limit = fallback_res.quota_metadata.get("requests_limit")
                        quota.requests_remaining = fallback_res.quota_metadata.get("requests_remaining")

                    if fallback_res.bundle_id:
                        all_bundles.append(fallback_res.bundle_id)

                    if fallback_res.status == SourceResultStatus.SUCCESS and fallback_res.value:
                        fallback_stats_list = fallback_res.value.get("response", [])
                        try:
                            parsed_fallback = parse_api_football_statistics_envelope(fallback_stats_list, fixture.home_provider_team_id, fixture.away_provider_team_id)
                            all_stats[fix_id] = parsed_fallback
                        except Exception as e:
                            logger.error(f"Failed to parse fallback stats for {fix_id}: {e}")

        return OrchestratedBatchResult(
            fixtures=all_fixtures,
            stats=all_stats,
            physical_http_attempts=http_attempts,
            fallback_stats_calls=fallback_calls,
            quota=quota,
            evidence_bundle_ids=all_bundles
        )
