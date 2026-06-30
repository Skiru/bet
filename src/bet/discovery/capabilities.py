"""Provider Capability Registry and Sport Provider Routing Contract.

Defines active provider roles, supported sports, and routing contracts.
"""

from typing import TypedDict, List, Dict, Optional


class ProviderCapability(TypedDict):
    provider_name: str
    adapter_file: str
    configured_without_secret_value: bool
    is_default_source: bool
    supported_sports_declared: List[str]
    supported_sports_effective: List[str]
    capabilities_declared: Dict[str, bool]
    capabilities_actually_used_by_pipeline: Dict[str, bool]
    output_fields: List[str]
    error_behavior: str
    known_gaps: List[str]


class SportRouting(TypedDict):
    sport: str
    event_discovery_providers: List[str]
    odds_providers: List[str]
    line_providers: List[str]
    market_providers: List[str]
    stats_enrichment_providers: List[str]
    identity_bridge_providers: List[str]
    fallback_providers: List[str]
    unsupported_capabilities: List[str]
    routing_status: str


# Canonical Capability Registry
PROVIDER_CAPABILITY_REGISTRY: Dict[str, ProviderCapability] = {
    "odds-api-io": {
        "provider_name": "odds-api-io",
        "adapter_file": "src/bet/discovery/sources/odds_api_io.py",
        "configured_without_secret_value": True,
        "is_default_source": True,
        "supported_sports_declared": ["football", "volleyball", "basketball", "tennis", "hockey", "cs2", "dota2", "valorant"],
        "supported_sports_effective": ["football", "volleyball", "basketball", "tennis", "hockey", "cs2", "dota2", "valorant"],
        "capabilities_declared": {
            "events": True,
            "odds": True,
            "lines": True,
            "markets": True,
            "player_props": False,
            "team_stats": False,
            "player_stats": False,
            "h2h": False,
            "standings": False,
            "injuries_or_news": False
        },
        "capabilities_actually_used_by_pipeline": {
            "events": True,
            "odds": True
        },
        "output_fields": ["source", "external_id", "sport", "competition", "home_team", "away_team", "kickoff", "status"],
        "error_behavior": "silent_zero",
        "known_gaps": []
    },
    "odds-api": {
        "provider_name": "odds-api",
        "adapter_file": "src/bet/discovery/sources/odds_api.py",
        "configured_without_secret_value": True,
        "is_default_source": True,
        "supported_sports_declared": ["football", "basketball", "hockey", "tennis"],
        "supported_sports_effective": ["football", "basketball", "hockey", "tennis"],
        "capabilities_declared": {
            "events": True,
            "odds": True,
            "lines": True,
            "markets": True,
            "player_props": False,
            "team_stats": False,
            "player_stats": False,
            "h2h": False,
            "standings": False,
            "injuries_or_news": False
        },
        "capabilities_actually_used_by_pipeline": {
            "events": True,
            "odds": True
        },
        "output_fields": ["source", "external_id", "sport", "competition", "home_team", "away_team", "kickoff", "status", "odds", "raw_data"],
        "error_behavior": "partial",
        "known_gaps": ["No volleyball coverage."]
    }
}

# Canonical Sport Provider Routing Contract
SPORT_PROVIDER_ROUTING_CONTRACT: Dict[str, SportRouting] = {
    "football": {
        "sport": "football",
        "event_discovery_providers": ["odds-api-io", "odds-api", "api-football", "football-data", "espn"],
        "odds_providers": ["odds-api-io", "odds-api"],
        "line_providers": ["odds-api-io", "odds-api"],
        "market_providers": ["odds-api-io", "odds-api"],
        "stats_enrichment_providers": ["api-football"],
        "identity_bridge_providers": ["api-football"],
        "fallback_providers": ["espn", "football-data"],
        "unsupported_capabilities": [],
        "routing_status": "ROUTING_PASS"
    },
    "volleyball": {
        "sport": "volleyball",
        "event_discovery_providers": ["odds-api-io", "api-volleyball"],
        "odds_providers": ["odds-api-io"],
        "line_providers": ["odds-api-io"],
        "market_providers": ["odds-api-io"],
        "stats_enrichment_providers": ["api-volleyball"],
        "identity_bridge_providers": ["api-volleyball"],
        "fallback_providers": ["api-volleyball"],
        "unsupported_capabilities": [],
        "routing_status": "ROUTING_PASS"
    },
    "basketball": {
        "sport": "basketball",
        "event_discovery_providers": ["odds-api-io", "odds-api", "api-basketball"],
        "odds_providers": ["odds-api-io", "odds-api"],
        "line_providers": ["odds-api-io", "odds-api"],
        "market_providers": ["odds-api-io", "odds-api"],
        "stats_enrichment_providers": ["api-basketball"],
        "identity_bridge_providers": ["api-basketball"],
        "fallback_providers": ["api-basketball"],
        "unsupported_capabilities": [],
        "routing_status": "ROUTING_PASS"
    },
    "tennis": {
        "sport": "tennis",
        "event_discovery_providers": ["odds-api-io", "odds-api"],
        "odds_providers": ["odds-api-io", "odds-api"],
        "line_providers": ["odds-api-io", "odds-api"],
        "market_providers": ["odds-api-io", "odds-api"],
        "stats_enrichment_providers": [],
        "identity_bridge_providers": [],
        "fallback_providers": [],
        "unsupported_capabilities": ["stats_enrichment"],
        "routing_status": "ENRICHMENT_PROVIDER_GAP"
    },
    "hockey": {
        "sport": "hockey",
        "event_discovery_providers": ["odds-api-io", "odds-api", "api-hockey"],
        "odds_providers": ["odds-api-io", "odds-api"],
        "line_providers": ["odds-api-io", "odds-api"],
        "market_providers": ["odds-api-io", "odds-api"],
        "stats_enrichment_providers": ["api-hockey"],
        "identity_bridge_providers": ["api-hockey"],
        "fallback_providers": ["api-hockey"],
        "unsupported_capabilities": [],
        "routing_status": "ROUTING_PASS"
    },
    "cs2": {
        "sport": "cs2",
        "event_discovery_providers": ["odds-api-io"],
        "odds_providers": ["odds-api-io"],
        "line_providers": ["odds-api-io"],
        "market_providers": ["odds-api-io"],
        "stats_enrichment_providers": [],
        "identity_bridge_providers": [],
        "fallback_providers": [],
        "unsupported_capabilities": ["stats_enrichment"],
        "routing_status": "ENRICHMENT_PROVIDER_GAP"
    },
    "dota2": {
        "sport": "dota2",
        "event_discovery_providers": ["odds-api-io"],
        "odds_providers": ["odds-api-io"],
        "line_providers": ["odds-api-io"],
        "market_providers": ["odds-api-io"],
        "stats_enrichment_providers": [],
        "identity_bridge_providers": [],
        "fallback_providers": [],
        "unsupported_capabilities": ["stats_enrichment"],
        "routing_status": "ENRICHMENT_PROVIDER_GAP"
    },
    "valorant": {
        "sport": "valorant",
        "event_discovery_providers": ["odds-api-io"],
        "odds_providers": ["odds-api-io"],
        "line_providers": ["odds-api-io"],
        "market_providers": ["odds-api-io"],
        "stats_enrichment_providers": [],
        "identity_bridge_providers": [],
        "fallback_providers": [],
        "unsupported_capabilities": ["stats_enrichment"],
        "routing_status": "ENRICHMENT_PROVIDER_GAP"
    }
}
