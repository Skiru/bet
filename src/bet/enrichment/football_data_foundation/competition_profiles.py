from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProviderScopeHint:
    provider_id: str
    source_family: str
    provider_league_slug: str | None
    provider_competition_id: str | None
    provider_season: str | None
    support_status: str
    discovery_required: bool
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalCompetitionScope:
    sport: str
    competition_scope: str
    season_scope: str
    human_label: str
    timezone: str
    provider_scope_hints: tuple[ProviderScopeHint, ...]
    fixture_seed_policy: str
    active_capability_targets: tuple[str, ...]


@dataclass(frozen=True)
class CompetitionProfile:
    profile_id: str
    canonical_scope: CanonicalCompetitionScope
    source_priority: tuple[str, ...]
    endpoint_verification_policy: Mapping[str, Any]
    identity_mapping_policy: Mapping[str, Any]
    active_certification_policy: Mapping[str, Any]
    blocked_source_policy: Mapping[str, Any]
    completeness_policy: Mapping[str, Any]


# ---------------------------------------------------------------------------
# Acceptance Profile: FIFA World Cup 2026
# ---------------------------------------------------------------------------

WorldCup2026Scope = CanonicalCompetitionScope(
    sport="football",
    competition_scope="football:world:8/world-championship:lvUBR5F8",
    season_scope="2026",
    human_label="FIFA World Cup 2026",
    timezone="Europe/Warsaw",
    provider_scope_hints=(
        ProviderScopeHint(
            provider_id="espn-fifa-worldcup",
            source_family="espn",
            provider_league_slug="fifa.world",
            provider_competition_id=None,
            provider_season="2026",
            support_status="active",
            discovery_required=True,
        ),
        ProviderScopeHint(
            provider_id="soccerdata-espn-worldcup",
            source_family="soccerdata",
            provider_league_slug="fifa.world",
            provider_competition_id=None,
            provider_season="2026",
            support_status="active",
            discovery_required=True,
        ),
        ProviderScopeHint(
            provider_id="sportdb-worldcup",
            source_family="sportdb",
            provider_league_slug=None,
            provider_competition_id="football:world:8/world-championship:lvUBR5F8",
            provider_season="2026",
            support_status="active",
            discovery_required=False,
        ),
        ProviderScopeHint(
            provider_id="openfootball-worldcup",
            source_family="openfootball",
            provider_league_slug=None,
            provider_competition_id=None,
            provider_season="2026",
            support_status="reference_only",
            discovery_required=False,
        ),
        ProviderScopeHint(
            provider_id="understat-worldcup",
            source_family="understat",
            provider_league_slug=None,
            provider_competition_id=None,
            provider_season=None,
            support_status="unsupported",
            discovery_required=False,
        ),
    ),
    fixture_seed_policy="worldcup_seed_expansion",
    active_capability_targets=("current_discovery", "detailed_metrics", "current_form"),
)

WorldCup2026Profile = CompetitionProfile(
    profile_id="world-cup-2026",
    canonical_scope=WorldCup2026Scope,
    source_priority=(
        "espn-fifa-worldcup",
        "soccerdata-espn-worldcup",
        "sportdb-worldcup",
    ),
    endpoint_verification_policy={
        "espn": {
            "endpoint_url": "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard",
            "max_calls": 2,
            "timeout_seconds": 20,
        }
    },
    identity_mapping_policy={
        "time_tolerance_seconds": 18000,  # 5 hours
        "require_team_match": True,
        "name_normalization": "strict_lowercased_trimmed_normalized",
    },
    active_certification_policy={
        "allowed_certification_level": "CERTIFIED_SELECTABLE_ACTIVE_ENRICHMENT",
        "active_enrichment": True,
        "selectable_as_projection": True,
        "production_betting_decision": False,
    },
    blocked_source_policy={
        "understat": "Understat does not support World Cup xG/detailed metrics - fail-closed required",
        "browser_heavy_sources": "all browser-heavy sources deferred by default to avoid selector drift",
    },
    completeness_policy={
        "always_verify_event_identity": True,
        "heavy_fetch_mode": "missing_or_stale",
        "force_refresh_supported": True,
        "default_team_data_ttl_hours": 24,
        "default_event_metadata_ttl_minutes": 30,
    },
)


# ---------------------------------------------------------------------------
# Test & Future Extensibility Profiles
# ---------------------------------------------------------------------------

ExampleFootballLeagueProfile = CompetitionProfile(
    profile_id="example-football-league-profile",
    canonical_scope=CanonicalCompetitionScope(
        sport="football",
        competition_scope="football:eng.1",
        season_scope="2024",
        human_label="English Premier League 2024/25",
        timezone="Europe/London",
        provider_scope_hints=(
            ProviderScopeHint(
                provider_id="espn-epl",
                source_family="espn",
                provider_league_slug="eng.1",
                provider_competition_id=None,
                provider_season="2024",
                support_status="active",
                discovery_required=True,
            ),
        ),
        fixture_seed_policy="league_standard",
        active_capability_targets=(
            "current_discovery",
            "detailed_metrics",
            "current_form",
        ),
    ),
    source_priority=("espn-epl",),
    endpoint_verification_policy={},
    identity_mapping_policy={},
    active_certification_policy={},
    blocked_source_policy={},
    completeness_policy={},
)

ExampleTennisTournamentProfile = CompetitionProfile(
    profile_id="example-tennis-tournament-profile",
    canonical_scope=CanonicalCompetitionScope(
        sport="tennis",
        competition_scope="tennis:world:grand-slam/wimbledon:wimb",
        season_scope="2026",
        human_label="Wimbledon 2026",
        timezone="Europe/London",
        provider_scope_hints=(
            ProviderScopeHint(
                provider_id="tennis-api-wimbledon",
                source_family="tennis-api",
                provider_league_slug=None,
                provider_competition_id="wimbledon",
                provider_season="2026",
                support_status="active",
                discovery_required=False,
            ),
        ),
        fixture_seed_policy="tournament_knockout",
        active_capability_targets=("player_stats", "draw_metadata"),
    ),
    source_priority=("tennis-api-wimbledon",),
    endpoint_verification_policy={},
    identity_mapping_policy={},
    active_certification_policy={},
    blocked_source_policy={},
    completeness_policy={},
)

ExampleEsportsMatchProfile = CompetitionProfile(
    profile_id="example-esports-match-profile",
    canonical_scope=CanonicalCompetitionScope(
        sport="esports",
        competition_scope="esports:lol/lck-spring:lck",
        season_scope="2026",
        human_label="LCK Spring 2026",
        timezone="Asia/Seoul",
        provider_scope_hints=(
            ProviderScopeHint(
                provider_id="pandascore-lck",
                source_family="pandascore",
                provider_league_slug=None,
                provider_competition_id="lck-spring",
                provider_season="2026",
                support_status="active",
                discovery_required=True,
            ),
        ),
        fixture_seed_policy="esports_match_stream",
        active_capability_targets=("game_stats", "kills_metadata"),
    ),
    source_priority=("pandascore-lck",),
    endpoint_verification_policy={},
    identity_mapping_policy={},
    active_certification_policy={},
    blocked_source_policy={},
    completeness_policy={},
)


# Registry of known competition profiles
_PROFILES: dict[str, CompetitionProfile] = {
    "world-cup-2026": WorldCup2026Profile,
    "example-football-league-profile": ExampleFootballLeagueProfile,
    "example-tennis-tournament-profile": ExampleTennisTournamentProfile,
    "example-esports-match-profile": ExampleEsportsMatchProfile,
}


def get_competition_profile(profile_id: str) -> CompetitionProfile:
    """Retrieve competition profile by ID or fail-closed."""
    profile = _PROFILES.get(profile_id)
    if profile is None:
        raise KeyError(f"Unknown competition profile: {profile_id}. Failed closed.")
    return profile
