# Capability Matrix

| Capability | State | Active | Notes |
|---|---|---:|---|
| read / glob / grep | ACTIVE_CERTIFIED | true | Enabled for all 13 canonical betting agents |
| Skills | ACTIVE_CERTIFIED | true | Project-local skills load from `.kilo/skills/` |
| task delegation | ACTIVE_CERTIFIED | true | `bet-orchestrator` only; exact 12-specialist allowlist |
| bet_artifact_write | ACTIVE_CERTIFIED | true | Only active artifact persistence path for orchestrator/builder |
| bet_script_run | FIXTURE_ONLY | true | `bet-engineer` only; fixture manifest unchanged |
| real script execution | DEFERRED | false | Pending independent certified script-onboarding phase |
| bet_sqlite_query | DEFERRED | false | Active tool quarantined from `.kilo/tool/`; unavailable in Phase 4A |
| real database | DEFERRED | false | No database requirement in Phase 4A |
| web research | DEFERRED | false | `webfetch`, `websearch`, Brave disabled for canonical betting agents |
| browser automation | PROHIBITED | false | `playwright_*` denied; MCP server disabled |
| MCP | PROHIBITED | false | memory, brave-search, context7, playwright all disabled |
| generic Bash / edit / write / apply_patch | PROHIBITED | false | Denied for all canonical betting agents |

## Betting-agent unavailable-capability contract

When a betting agent requires deferred database or web capability, it must return:

```text
STATUS: BLOCKED
DECISION: CAPABILITY_UNAVAILABLE
```

No agent may substitute Bash, Python, SQLite CLI, direct file scraping, MCP calls, or invented data.
