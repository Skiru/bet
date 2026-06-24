from __future__ import annotations

from .contracts import ProofLevel, ProviderProfile, ProviderRole, SportKey

ALL_TEAM_SPORTS = (
    SportKey.BASKETBALL,
    SportKey.VOLLEYBALL,
    SportKey.HOCKEY,
    SportKey.TENNIS,
)

ALL_ESPORTS = (
    SportKey.CS2,
    SportKey.DOTA2,
    SportKey.VALORANT,
)


def build_provider_profiles() -> dict[str, ProviderProfile]:
    return {
        "sportdb": ProviderProfile(
            key="sportdb",
            roles=(ProviderRole.CURRENT_LIVE, ProviderRole.CURRENT_REFERENCE),
            sports_supported=ALL_TEAM_SPORTS,
            credential_env_names=("SPORTDB_API_KEY",),
            max_rps=2.5,
            docs_url="https://sportdb.dev/",
            allowed_proof_levels=(
                ProofLevel.REAL_LIVE_HTTP_PROOF,
                ProofLevel.REAL_REPLAY_CORPUS_PROOF,
                ProofLevel.BLOCKED_ACCESS_PROOF,
                ProofLevel.DOCS_CAPABILITY_ONLY,
            ),
            notes="Multisport REST/MCP provider; never mark mapped unless target participants are present in response.",
        ),
        "highlightly": ProviderProfile(
            key="highlightly",
            roles=(ProviderRole.CURRENT_LIVE, ProviderRole.CURRENT_REFERENCE),
            sports_supported=ALL_TEAM_SPORTS,
            credential_env_names=("HIGHLIGHTLY_API_KEY",),
            max_rps=2.0,
            docs_url="https://highlightly.net/sport-api/documentation/",
            allowed_proof_levels=(
                ProofLevel.REAL_LIVE_HTTP_PROOF,
                ProofLevel.REAL_REPLAY_CORPUS_PROOF,
                ProofLevel.BLOCKED_ACCESS_PROOF,
                ProofLevel.DOCS_CAPABILITY_ONLY,
            ),
            notes="All Sports API / dedicated sport APIs; capture only sanitized envelopes.",
        ),
        "api-sports-family": ProviderProfile(
            key="api-sports-family",
            roles=(ProviderRole.CURRENT_LIVE, ProviderRole.CURRENT_REFERENCE),
            sports_supported=(SportKey.BASKETBALL, SportKey.VOLLEYBALL, SportKey.HOCKEY),
            credential_env_names=(
                "API_BASKETBALL_KEY",
                "API_VOLLEYBALL_KEY",
                "API_HOCKEY_KEY",
                "API_SPORTS_KEY",
            ),
            max_rps=2.0,
            docs_url="https://api-sports.io/",
            allowed_proof_levels=(
                ProofLevel.REAL_LIVE_HTTP_PROOF,
                ProofLevel.REAL_REPLAY_CORPUS_PROOF,
                ProofLevel.BLOCKED_ACCESS_PROOF,
                ProofLevel.DOCS_CAPABILITY_ONLY,
            ),
            notes="Family of sport-specific APIs; use sport-specific env key first, then shared API_SPORTS_KEY.",
        ),
        "thesportsdb": ProviderProfile(
            key="thesportsdb",
            roles=(ProviderRole.CURRENT_REFERENCE, ProviderRole.HISTORICAL_REFERENCE),
            sports_supported=ALL_TEAM_SPORTS,
            credential_env_names=("THESPORTSDB_API_KEY", "THESPORTSDB_KEY"),
            max_rps=1.0,
            docs_url="https://www.thesportsdb.com/free_sports_api",
            allowed_proof_levels=(
                ProofLevel.REAL_LIVE_HTTP_PROOF,
                ProofLevel.REAL_REPLAY_CORPUS_PROOF,
                ProofLevel.BLOCKED_ACCESS_PROOF,
                ProofLevel.DOCS_CAPABILITY_ONLY,
            ),
            notes="Reference/fallback source; do not use as sole current truth for activation-ready status.",
        ),
        "pandascore": ProviderProfile(
            key="pandascore",
            roles=(ProviderRole.ESPORTS_LIVE, ProviderRole.ESPORTS_REFERENCE),
            sports_supported=ALL_ESPORTS,
            credential_env_names=("PANDASCORE_API_KEY",),
            max_rps=1.5,
            docs_url="https://www.pandascore.co/",
            allowed_proof_levels=(
                ProofLevel.REAL_LIVE_HTTP_PROOF,
                ProofLevel.REAL_REPLAY_CORPUS_PROOF,
                ProofLevel.BLOCKED_ACCESS_PROOF,
                ProofLevel.DOCS_CAPABILITY_ONLY,
            ),
            notes="Primary esports candidate; schedule/results/static data may pass as observation without betting use.",
        ),
        "liquipedia-reference": ProviderProfile(
            key="liquipedia-reference",
            roles=(ProviderRole.ESPORTS_REFERENCE, ProviderRole.DEFERRED_BY_ACCESS),
            sports_supported=ALL_ESPORTS,
            credential_env_names=(),
            max_rps=None,
            docs_url="https://liquipedia.net/api",
            allowed_proof_levels=(ProofLevel.DOCS_CAPABILITY_ONLY, ProofLevel.BLOCKED_ACCESS_PROOF),
            notes="Reference candidate only; no scraping or ToS-unsafe behavior in production prompts.",
        ),
    }


def provider_matrix() -> dict[str, list[str]]:
    providers = build_provider_profiles()
    return {
        sport.value: [key for key, provider in providers.items() if provider.supports(sport)]
        for sport in SportKey
    }
