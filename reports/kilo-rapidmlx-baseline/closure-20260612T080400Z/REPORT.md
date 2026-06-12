# Phase 2 Closure Report — MCP-Free Canonical Baseline

## Status: KILO_BASELINE_PASS

**Configuration Fingerprint:** `d4e59816d5cd0049`

## Executive Summary

The canonical minimal Kilo baseline has been validated with all MCP servers disabled. The project-level configuration override successfully disables the inherited global Memory MCP without modifying the user's global Kilo configuration.

## Inherited MCP Configuration

| Property | Value |
|----------|-------|
| MCP key | `memory` |
| Source configuration | `/Users/mkoziol/.config/kilo/kilo.json` (global) |
| Transport type | `local` |
| Command | `npx -y @modelcontextprotocol/server-memory` |
| Original state | enabled (implicit) |
| Inherited from global | YES |

## Project Override Applied

```json
{
  "mcp": {
    "memory": {
      "type": "local",
      "command": ["npx", "-y", "@modelcontextprotocol/server-memory"],
      "enabled": false
    },
    "brave-search": {
      "type": "local",
      "command": ["npx", "-y", "@brave/brave-search-mcp-server@2.0.75", "--transport", "stdio"],
      "environment": {"BRAVE_API_KEY": "{env:BRAVE_API_KEY}"},
      "enabled": false,
      "timeout": 30000
    },
    "context7": {
      "type": "remote",
      "url": "https://mcp.context7.com/mcp",
      "enabled": false,
      "timeout": 20000
    },
    "playwright": {
      "type": "local",
      "command": ["npx", "-y", "@playwright/mcp@0.0.76", "--headless"],
      "enabled": false,
      "timeout": 30000
    }
  }
}
```

## Resolved MCP State

```
●  ○ memory      disabled
●  ○ brave-search disabled
●  ○ context7    disabled
●  ○ playwright disabled
```

## Canonical Gates Results

| Gate | Result | Evidence |
|------|--------|----------|
| Connectivity | 5/5 PASS | curl to Rapid-MLX API |
| Read | 5/5 PASS | read tool on kilo.jsonc |
| Glob | 5/5 PASS | pattern matching on *.md |
| Grep | 5/5 PASS | content search for KILO_BASELINE |
| Bash | 5/5 PASS | echo command execution |

## Same-Session Continuation

| Metric | Value |
|--------|-------|
| Sessions | 1 |
| Turns | 12 |
| Malformed tool calls | 0 |
| Duplicate executions | 0 |
| Unexpected tools | 0 |
| MCP calls | 0 |
| ContextOverflowError | 0 |
| Compaction exhausted | 0 |
| Repetition collapse | 0 |
| Rapid-MLX restart | 0 |

## Cache Classification

**INSUFFICIENT_EVIDENCE**

Direct server cache hit evidence is not available from the current session. The previous Phase 2 tests documented cache speedup but those were run with active MCPs and are classified as preliminary evidence.

## Memory Classification

**UNKNOWN**

MLX unified-memory allocation is not exposed from the server process. Resource health is inferred from:
- Server health: valid (PID 54776 running)
- PID stability: stable since 08:43:53
- No OOM detected
- No critical sustained memory pressure
- No swap growth with severe degradation
- System remains responsive

## Previous Evidence Classification

The following evidence from the previous Phase 2 tests is classified as:

**OUT_OF_SCOPE_PRELIMINARY_MCP_EVIDENCE**

These tests were executed with active MCP servers (memory, brave-search, context7) and are not eligible for the canonical minimal baseline:

- `reports/kilo-rapidmlx-baseline/closure-20260612T075353Z/results.json`
- `reports/kilo-rapidmlx-baseline/closure-20260612T075353Z/KILO_BASELINE_ACCEPTANCE_MATRIX.md`
- `reports/kilo-rapidmlx-baseline/closure-20260612T075353Z/REPORT.md`
- `reports/kilo-rapidmlx-baseline/closure-20260612T075353Z/TEST_RECONSTRUCTION.md`
- `reports/kilo-rapidmlx-baseline/run-20260612T072549Z-context-test.json`
- `reports/kilo-rapidmlx-baseline/run-20260612T072856Z-mcp-test.json`
- `reports/kilo-rapidmlx-baseline/run-20260612T073211Z-stability-test.json`
- `reports/kilo-rapidmlx-baseline/run-20260612T073341Z-recovery-test.json`
- `reports/kilo-rapidmlx-baseline/run-20260612T073702Z-resource-test.json`

The old `44 claimed / 28 represented` result is superseded by this new MCP-free baseline.

## Known Limitations

1. Cache classification requires direct server evidence which is not exposed
2. MLX unified-memory allocation is not exposed from the server process
3. Same-session continuation tested in single session, not two separate sessions

## Evidence Paths

- `reports/kilo-rapidmlx-baseline/closure-20260612T080400Z/results.json`
- `reports/kilo-rapidmlx-baseline/closure-20260612T080400Z/KILO_BASELINE_ACCEPTANCE_MATRIX.md`
- `reports/kilo-rapidmlx-baseline/closure-20260612T080400Z/REPORT.md`

## Next Single Action

Phase 2 closure complete. Ready for Phase 3 when user requests.
