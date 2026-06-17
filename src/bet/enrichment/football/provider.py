import json
import logging
from dataclasses import dataclass
from datetime import datetime

from bet.api_clients.api_football import APIFootballClient
from bet.api_clients.base_client import SourceResultStatus
from bet.enrichment.football.parser import (
    FootballFixtureIdentity,
    parse_api_football_fixture_envelope,
    parse_api_football_statistics_envelope,
)

logger = logging.getLogger(__name__)

@dataclass
class ProviderQuota:
    requests_limit: int | None
    requests_remaining: int | None
    
@dataclass
class OrchestratedBatchResult:
    fixtures: list[FootballFixtureIdentity]
    stats: dict[str, dict[str, dict[str, int | float | None]]]  # fixture_id -> team_id -> stat_type -> value
    physical_http_attempts: int
    fallback_stats_calls: int
    quota: ProviderQuota
    evidence_bundle_ids: list[str]

class APIFootballOrchestrator:
    def __init__(self, client: APIFootballClient, quota_reserve: int = 10):
        self.client = client
        self.quota_reserve = quota_reserve

    def get_coverage(self, league_id: str, season: int) -> bool:
        # Implement coverage retrieval and caching
        res = self.client.get_leagues_coverage(league_id, season)
            if res.status != SourceResultStatus.SUCCESS or not res.value:
            return False # Conservative fallback
        try:
            leagues = res.value.get("response", [])
            if not leagues:
                return False
            coverage = leagues[0].get("seasons", [{}])[0].get("coverage", {})
            return bool(coverage.get("fixtures", {}).get("statistics_fixtures", False))
        except Exception:
            return False

    def discover_completed_fixtures(self, league_id: str, season: int, from_date: str, to_date: str) -> list[str]:
        # Completed fixture discovery
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
        
        # Deduplicate and sort deterministically
        clean_ids = sorted(list(set(str(i).strip() for i in fixture_ids if str(i).strip())))
        
        # Chunk into groups of at most 20
        chunks = [clean_ids[i:i + 20] for i in range(0, len(clean_ids), 20)]
        
        quota = ProviderQuota(None, None)
        
        for chunk in chunks:
            # Check quota reserve if we have quota info
            if quota.requests_remaining is not None and quota.requests_remaining <= self.quota_reserve:
                logger.warning("Quota reserve reached. Stopping batch retrieval.")
                break
                
            res = self.client.get_history_details(chunk)
            print(f'Batch call returned {res.status}, val: {len(res.value.get("response", [])) if res.value else 0}')
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
                    
                # 1. Parse Fixture
                try:
                    fixture = parse_api_football_fixture_envelope(item, fix_id)
                except Exception as e:
                    print(f'Failed to parse fixture {fix_id}: {e}')
                    logger.error(f"Failed to parse fixture {fix_id}: {e}")
                    continue
                    
                all_fixtures.append(fixture)
                
                # 2. Check Embedded Stats
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
                
                # 3. Fallback Stats
                if require_stats and not has_embedded_stats:
                    if fallback_calls >= max_fallback_calls:
                        logger.warning(f"Max fallback calls reached. Skipping stats for {fix_id}")
                        continue
                        
                    if quota.requests_remaining is not None and quota.requests_remaining <= self.quota_reserve:
                        logger.warning("Quota reserve reached during fallback. Stopping.")
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
