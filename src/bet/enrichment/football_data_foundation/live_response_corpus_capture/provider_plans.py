from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class ProviderDiscoveryPlan:
    provider: str
    purpose: str
    method: str
    url: str
    credential_env: str | None
    auth_header_name: str | None
    body_kind: str = "json"
    max_requests: int = 1
    provider_fixture_id_required: bool = False
    safe_without_mapping: bool = True


def build_provider_discovery_plans(fixture: Dict[str, Any]) -> List[ProviderDiscoveryPlan]:
    """
    Build bounded discovery/list/search requests that do not require provider fixture IDs.
    """
    kickoff = fixture.get("kickoff_at") or ""
    date = kickoff[:10] if kickoff else "2026-06-23"

    return [
        ProviderDiscoveryPlan(
            provider="football-data-org",
            purpose="date_range_match_discovery",
            method="GET",
            url=f"https://api.football-data.org/v4/matches?dateFrom={date}&dateTo={date}",
            credential_env="FOOTBALL_DATA_ORG_KEY",
            auth_header_name="X-Auth-Token",
        ),
        ProviderDiscoveryPlan(
            provider="api-football",
            purpose="date_fixture_discovery",
            method="GET",
            url=f"https://v3.football.api-sports.io/fixtures?date={date}",
            credential_env="API_FOOTBALL_KEY",
            auth_header_name="x-apisports-key",
        ),
        ProviderDiscoveryPlan(
            provider="sportdb",
            purpose="mcp_live_or_match_search_discovery",
            method="POST",
            url="https://api.sportdb.dev/mcp/",
            credential_env="SPORTDB_API_KEY",
            auth_header_name="X-API-Key",
            body_kind="mcp_jsonrpc",
        ),
        ProviderDiscoveryPlan(
            provider="highlightly",
            purpose="bounded_match_search_discovery",
            method="GET",
            url="https://soccer.highlightly.net/matches",
            credential_env="HIGHLIGHTLY_API_KEY",
            auth_header_name="x-rapidapi-key",
        ),
    ]
