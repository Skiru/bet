# Sport Provider Routing Contract

This document defines the provider mapping, capabilities, and expected diagnostic statuses for each supported sport in the pipeline.

## Expected Sports & Provider Routing Mapping

### Football
- **Event Discovery**: `odds-api-io`, `odds-api`, `api-football`, `football-data`, `espn`
- **Odds Providers**: `odds-api-io`, `odds-api`
- **Line Providers**: `odds-api-io`, `odds-api`
- **Market Providers**: `odds-api-io`, `odds-api`
- **Stats Enrichment**: `api-football`
- **Identity Bridge**: `api-football`
- **Fallback**: `espn`, `football-data`
- **Routing Status**: `ROUTING_PASS`

### Volleyball
- **Event Discovery**: `odds-api-io`, `api-volleyball`
- **Odds Providers**: `odds-api-io`
- **Line Providers**: `odds-api-io`
- **Market Providers**: `odds-api-io`
- **Stats Enrichment**: `api-volleyball`
- **Identity Bridge**: `api-volleyball`
- **Fallback**: `api-volleyball`
- **Routing Status**: `ROUTING_PASS`

### Basketball
- **Event Discovery**: `odds-api-io`, `odds-api`, `api-basketball`
- **Odds Providers**: `odds-api-io`, `odds-api`
- **Line Providers**: `odds-api-io`, `odds-api`
- **Market Providers**: `odds-api-io`, `odds-api`
- **Stats Enrichment**: `api-basketball`
- **Identity Bridge**: `api-basketball`
- **Fallback**: `api-basketball`
- **Routing Status**: `ROUTING_PASS`

### Tennis
- **Event Discovery**: `odds-api-io`, `odds-api`
- **Odds Providers**: `odds-api-io`, `odds-api`
- **Line Providers**: `odds-api-io`, `odds-api`
- **Market Providers**: `odds-api-io`, `odds-api`
- **Stats Enrichment**: *None*
- **Identity Bridge**: *None*
- **Fallback**: *None*
- **Unsupported Capabilities**: `stats_enrichment`
- **Routing Status**: `ENRICHMENT_PROVIDER_GAP`

### Hockey
- **Event Discovery**: `odds-api-io`, `odds-api`, `api-hockey`
- **Odds Providers**: `odds-api-io`, `odds-api`
- **Line Providers**: `odds-api-io`, `odds-api`
- **Market Providers**: `odds-api-io`, `odds-api`
- **Stats Enrichment**: `api-hockey`
- **Identity Bridge**: `api-hockey`
- **Fallback**: `api-hockey`
- **Routing Status**: `ROUTING_PASS`

### CS2
- **Event Discovery**: `odds-api-io`
- **Odds Providers**: `odds-api-io`
- **Line Providers**: `odds-api-io`
- **Market Providers**: `odds-api-io`
- **Stats Enrichment**: *None*
- **Identity Bridge**: *None*
- **Fallback**: *None*
- **Unsupported Capabilities**: `stats_enrichment`
- **Routing Status**: `ENRICHMENT_PROVIDER_GAP`

### Dota 2
- **Event Discovery**: `odds-api-io`
- **Odds Providers**: `odds-api-io`
- **Line Providers**: `odds-api-io`
- **Market Providers**: `odds-api-io`
- **Stats Enrichment**: *None*
- **Identity Bridge**: *None*
- **Fallback**: *None*
- **Unsupported Capabilities**: `stats_enrichment`
- **Routing Status**: `ENRICHMENT_PROVIDER_GAP`

### Valorant
- **Event Discovery**: `odds-api-io`
- **Odds Providers**: `odds-api-io`
- **Line Providers**: `odds-api-io`
- **Market Providers**: `odds-api-io`
- **Stats Enrichment**: *None*
- **Identity Bridge**: *None*
- **Fallback**: *None*
- **Unsupported Capabilities**: `stats_enrichment`
- **Routing Status**: `ENRICHMENT_PROVIDER_GAP`
