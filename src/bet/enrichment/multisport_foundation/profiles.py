from __future__ import annotations

from .contracts import FactRequirement, SportKey, SportProfile

COMMON_TEAM_FACTS = (
    FactRequirement(
        name="fixture_identity",
        required_for_shadow_ready=True,
        unknown_allowed=False,
        description="Provider-specific match or fixture identity mapped to canonical participants.",
    ),
    FactRequirement(
        name="status_or_clock",
        required_for_shadow_ready=True,
        unknown_allowed=True,
        description="Scheduled/live/final status or sport-specific clock/state.",
    ),
    FactRequirement(
        name="score_or_result",
        required_for_shadow_ready=False,
        unknown_allowed=True,
        description="Score or final result when present; UNKNOWN is valid before availability.",
    ),
    FactRequirement(
        name="participants",
        required_for_shadow_ready=True,
        unknown_allowed=False,
        description="Canonical team/player participants with provider aliases.",
    ),
)

TEAM_SPORT_PROVIDERS = (
    "sportdb",
    "highlightly",
    "api-sports-family",
    "thesportsdb",
)

ESPORTS_PROVIDERS = (
    "pandascore",
    "liquipedia-reference",
    "sportdb",
)


def build_sport_profiles() -> dict[SportKey, SportProfile]:
    tennis_facts = COMMON_TEAM_FACTS + (
        FactRequirement(
            name="surface_or_court_context",
            required_for_shadow_ready=False,
            unknown_allowed=True,
            description="Surface, tournament context, round and best-of format when available.",
        ),
    )
    esports_facts = COMMON_TEAM_FACTS + (
        FactRequirement(
            name="roster_or_lineup_context",
            required_for_shadow_ready=False,
            unknown_allowed=True,
            description="Team roster, players, substitutes, map pool or agent/meta context when available.",
        ),
        FactRequirement(
            name="game_patch_or_version_context",
            required_for_shadow_ready=False,
            unknown_allowed=True,
            description="Game patch/version context; UNKNOWN is valid unless provided by source.",
        ),
    )

    return {
        SportKey.BASKETBALL: SportProfile(
            sport=SportKey.BASKETBALL,
            identity_keys=("league", "season", "home_team", "away_team", "tipoff"),
            fixture_terms=("game", "match", "fixture"),
            minimum_real_mapped_providers=2,
            required_facts=COMMON_TEAM_FACTS,
            provider_candidates=TEAM_SPORT_PROVIDERS,
        ),
        SportKey.VOLLEYBALL: SportProfile(
            sport=SportKey.VOLLEYBALL,
            identity_keys=("competition", "season", "home_team", "away_team", "start_time"),
            fixture_terms=("match", "fixture"),
            minimum_real_mapped_providers=2,
            required_facts=COMMON_TEAM_FACTS,
            provider_candidates=("highlightly", "api-sports-family", "thesportsdb"),
        ),
        SportKey.HOCKEY: SportProfile(
            sport=SportKey.HOCKEY,
            identity_keys=("league", "season", "home_team", "away_team", "puck_drop"),
            fixture_terms=("game", "match", "fixture"),
            minimum_real_mapped_providers=2,
            required_facts=COMMON_TEAM_FACTS,
            provider_candidates=TEAM_SPORT_PROVIDERS,
        ),
        SportKey.TENNIS: SportProfile(
            sport=SportKey.TENNIS,
            identity_keys=("tournament", "season", "player_one", "player_two", "start_time"),
            fixture_terms=("match", "fixture"),
            minimum_real_mapped_providers=2,
            required_facts=tennis_facts,
            provider_candidates=("sportdb", "highlightly", "thesportsdb"),
        ),
        SportKey.CS2: SportProfile(
            sport=SportKey.CS2,
            identity_keys=("tournament", "series", "team_one", "team_two", "start_time"),
            fixture_terms=("match", "series", "map"),
            minimum_real_mapped_providers=1,
            required_facts=esports_facts,
            provider_candidates=ESPORTS_PROVIDERS,
        ),
        SportKey.DOTA2: SportProfile(
            sport=SportKey.DOTA2,
            identity_keys=("tournament", "series", "team_one", "team_two", "start_time"),
            fixture_terms=("match", "series", "game"),
            minimum_real_mapped_providers=1,
            required_facts=esports_facts,
            provider_candidates=ESPORTS_PROVIDERS,
        ),
        SportKey.VALORANT: SportProfile(
            sport=SportKey.VALORANT,
            identity_keys=("tournament", "series", "team_one", "team_two", "start_time"),
            fixture_terms=("match", "series", "map"),
            minimum_real_mapped_providers=1,
            required_facts=esports_facts,
            provider_candidates=ESPORTS_PROVIDERS,
        ),
    }
