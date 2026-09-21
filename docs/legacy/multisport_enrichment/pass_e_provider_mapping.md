# Pass E Provider Mapping Contracts

This document specifies the provider route contracts, mapping artifacts, status derivation, and safety invariants for Pass E of the multisport shadow foundation.

## Why Pass E Exists After Shadow Foundation

Following the implementation of the merged multisport shadow foundation, Pass E provides a rigorous mapping layer between target sports and provider route families. This mapping ensures that:
1. Every target sport is mapped to a explicit, well-defined API route structure.
2. Credentials and environment variables are strictly accounted for before any probe is allowed.
3. Access boundaries and terms gates are analyzed up-front, enforcing a fail-closed architecture.

## Transport-Free Safety: No Live Calls

Pass E is strictly transport-free. It does not introduce any real API clients, perform scrapings, make database writes, or issue real HTTP requests.
- `live_call_allowed` is hard-locked to `false`.
- `production_selectable` is hard-locked to `false`.
- `betting_decisions_enabled` is hard-locked to `false`.

No betting decisions/picks/stakes/edges or recommendations are enabled or selectable.

## Target Sport Routing Matrix

### Primary Route Mapping: API-Sports Family
The API-Sports route family serves as the primary data source for:
- **Basketball**: route `api_basketball_games` on endpoints family `games`. Required env keys: `API_BASKETBALL_KEY` or `API_SPORTS_KEY`. Proof fields required: `fixture_id`, `home_team`, `away_team`, `start_time`.
- **Volleyball**: route `api_volleyball_games` on endpoints family `games`. Required env keys: `API_VOLLEYBALL_KEY` or `API_SPORTS_KEY`. Proof fields required: `fixture_id`, `home_team`, `away_team`, `start_time`.
- **Hockey**: route `api_hockey_games` on endpoints family `games`. Required env keys: `API_HOCKEY_KEY` or `API_SPORTS_KEY`. Proof fields required: `fixture_id`, `home_team`, `away_team`, `start_time`.
- **Tennis**: route `api_tennis_fixtures` on endpoints family `fixtures`. Required env keys: `API_TENNIS_KEY` or `API_SPORTS_KEY`. Proof fields required: `fixture_id`, `player_or_team_a`, `player_or_team_b`, `start_time`.

### Esports Route Mapping: PandaScore
PandaScore serves as the esports candidate for:
- **CS2**: route `pandascore_cs2_matches` on endpoints family `matches`. Required env key: `PANDASCORE_TOKEN`. Proof fields required: `match_id`, `opponents`, `begin_at`.
- **Dota 2**: route `pandascore_dota2_matches` on endpoints family `matches`. Required env key: `PANDASCORE_TOKEN`. Proof fields required: `match_id`, `opponents`, `begin_at`.
- **Valorant**: route `pandascore_valorant_matches` on endpoints family `matches`. Required env key: `PANDASCORE_TOKEN`. Proof fields required: `match_id`, `opponents`, `begin_at`.

PandaScore is permanently blocked behind a terms/access gate review (`terms_or_access_review_required=true`) during this pass, preventing any automated probe.

### Reference & Deferred Candidates
- **SportDB**: Transfer-direct candidate for basketball/hockey/tennis but not a primary probe target in this pass.
- **Highlightly**: Transfer-direct candidate for basketball/hockey/volleyball but not a primary probe target in this pass.
- **TheSportsDB**: Reference transfer candidate only; never sole detailed current truth.
- **Liquipedia**: Reference-only/deferred probe target. Controlled MediaWiki/API rate limiting must be implemented before any live scraping, which is deferred and forbidden in this pass.

## Status Derivation

The status of each provider mapping artifact is deterministically derived using the following priority rules:

1. **Terms/Access Gated Check**
   If the route spec has `terms_or_access_review_required=true`:
   `status = BLOCKED_PROVIDER_TERMS_OR_SCOPE`
   Reason: `terms_or_access_review_required_before_probe`

2. **Credentials Presence Check**
   Else if none of the required environment keys (`required_env_keys`) is present in `os.environ` presence list:
   `status = BLOCKED_NO_CREDENTIALS`
   Reason: `no_acceptable_provider_credential_present`

3. **Fact Policy Check**
   Else if proof fields required list is empty:
   `status = BLOCKED_PROVIDER_MAPPING_NOT_FOUND`
   Reason: `route_has_no_minimum_fact_policy`

4. **Ready for Probe**
   Else:
   `status = MAPPING_READY_FOR_SANITIZED_PROBE`

## Next Pass F Requirements (Sanitized Probes)

Pass F will introduce highly restricted, single-flight, rate-limited sanitized probes for sports matching `MAPPING_READY_FOR_SANITIZED_PROBE` to verify connectivity and validate schema structures.
Requirements for Pass F include:
1. Hard-locked mock/replay fallbacks when environment credentials are not present.
2. Complete scrubbing of Authorization/Bearer tokens and raw API keys from all artifacts and files.
3. Continued strict enforcement of `production_selectable=false` and `betting_decisions_enabled=false`.
