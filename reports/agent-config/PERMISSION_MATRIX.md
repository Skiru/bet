# Permission Matrix

## Specialist Permissions

| Permission | bet-settler | bet-db-analyst | bet-scanner | bet-scout | bet-enricher | bet-statistician | bet-valuator | bet-challenger | bet-reconciler | bet-builder | bet-test-engineer | bet-engineer |
|------------|-------------|----------------|-------------|-----------|--------------|-------------------|--------------|----------------|----------------|-------------|-------------------|-------------|
| read | allow | allow | allow | allow | allow | allow | allow | allow | allow | allow | allow | allow |
| glob | allow | allow | allow | allow | allow | allow | allow | allow | allow | allow | allow | allow |
| grep | allow | allow | allow | allow | allow | allow | allow | allow | allow | allow | allow | allow |
| skill | allow | allow | allow | allow | allow | allow | allow | allow | allow | allow | allow | allow |
| edit | deny | deny | deny | deny | deny | deny | deny | deny | deny | bounded | deny | ask |
| write | deny | deny | deny | deny | deny | deny | deny | deny | deny | bounded | deny | ask |
| bash | deny | deny | deny | deny | deny | deny | deny | deny | deny | deny | bounded | ask |
| task | deny | deny | deny | deny | deny | deny | deny | deny | deny | deny | deny | deny |
| webfetch | deny | deny | allow | allow | allow | deny | allow | allow | deny | deny | deny | allow |
| websearch | deny | deny | deny | deny | deny | deny | deny | deny | deny | deny | deny | deny |
| bet_sqlite_query | allow | allow | allow | allow | allow | allow | allow | allow | allow | allow | allow | allow |
| brave-search_* | deny | deny | limited | limited | limited | deny | limited | limited | deny | deny | deny | limited |
| context7_* | deny | deny | deny | deny | deny | deny | deny | deny | deny | deny | deny | allow |
| playwright_* | deny | deny | deny | deny | deny | deny | deny | deny | deny | deny | deny | deny |
| bet_script_run | deny | deny | deny | deny | deny | deny | deny | deny | deny | deny | deny | allow |

## Orchestrator Permissions

| Permission | Value |
|------------|-------|
| read | allow |
| glob | allow |
| grep | allow |
| skill | allow |
| todowrite | allow |
| todoread | allow |
| question | allow |
| edit | bounded (.kilo/artifacts/**, .kilo/state/**) |
| write | bounded (.kilo/artifacts/**, .kilo/state/**) |
| bash | deny |
| webfetch | deny |
| websearch | deny |
| bet_sqlite_query | deny |
| brave-search_* | deny |
| context7_* | deny |
| playwright_* | deny |
| task | allowlist (12 specialists only) |

## Task Allowlist

Orchestrator may delegate to:
- bet-settler
- bet-db-analyst
- bet-scanner
- bet-scout
- bet-enricher
- bet-statistician
- bet-valuator
- bet-challenger
- bet-reconciler
- bet-builder
- bet-test-engineer
- bet-engineer

## Bounded Write Paths

bet-builder and bet-orchestrator may write to:
- `.kilo/artifacts/**`
- `.kilo/state/**`

## Legend

- `allow`: Full access
- `deny`: No access
- `ask`: Requires user approval
- `bounded`: Limited to specific paths
- `limited`: Specific tools only (e.g., brave-search_brave_web_search)
