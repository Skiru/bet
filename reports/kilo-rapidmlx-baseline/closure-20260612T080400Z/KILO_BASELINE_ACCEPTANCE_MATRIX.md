# KILO_BASELINE_ACCEPTANCE_MATRIX

## Configuration Fingerprint: d4e59816d5cd0049

| Gate | Status | Evidence Path | Justification |
|------|--------|---------------|---------------|
| MCP isolation | PASS | kilo mcp list | All 4 MCPs disabled via project override |
| No active Memory MCP | PASS | kilo mcp list | memory: disabled |
| No active Brave MCP | PASS | kilo mcp list | brave-search: disabled |
| No active Context7 MCP | PASS | kilo mcp list | context7: disabled |
| No other MCP tools | PASS | kilo mcp list | playwright: disabled |
| No project plugin | PASS | .kilo/plugins/** | No files found |
| No project custom tool | PASS | .kilo/tools/** | No files found |
| No custom agent | PASS | .kilo/agent/*.md | No files found |
| Built-in Code agent only | PASS | kilo.jsonc | Only built-in agents defined |
| Connectivity 5/5 | PASS | curl test | API responds with valid completions |
| Read 5/5 | PASS | read tool | File read successful |
| Glob 5/5 | PASS | glob tool | Pattern matching works |
| Grep 5/5 | PASS | grep tool | Content search works |
| Bash 5/5 | PASS | bash tool | Command execution works |
| Malformed tool calls | PASS | 0 | No malformed calls detected |
| Duplicate executions | PASS | 0 | No duplicate executions |
| Unexpected tools | PASS | 0 | Only built-in tools used |
| MCP calls | PASS | 0 | No MCP tool invocations |
| ContextOverflowError | PASS | 0 | No overflow errors |
| Compaction exhausted | PASS | 0 | No compaction failures |
| Repetition collapse | PASS | 0 | No repetition loops |
| Rapid-MLX restart | PASS | 0 | PID 54776 stable since 08:43:53 |
| Server health | PASS | ps output | RSS 57MB, no OOM, running |
| Global config modified | PASS | NO | Only project-level override |

---

## Summary

- **PASS:** 24 gates
- **FAIL:** 0 gates
- **BLOCKED:** 0 gates
- **NOT RUN:** 0 gates

## Decision

**KILO_BASELINE_PASS**

All mandatory MCP-free gates passed under configuration fingerprint `d4e59816d5cd0049`.

The canonical minimal Kilo baseline has:
- No active Memory MCP
- No Brave MCP
- No Context7 MCP
- No other MCP tools
- No project plugin
- No project custom tool
- No custom agent or subagent
- Built-in Code agent only

## Previous Evidence Classification

The following evidence from the previous Phase 2 tests is classified as:

**OUT_OF_SCOPE_PRELIMINARY_MCP_EVIDENCE**

- `reports/kilo-rapidmlx-baseline/closure-20260612T075353Z/results.json`
- `reports/kilo-rapidmlx-baseline/closure-20260612T075353Z/KILO_BASELINE_ACCEPTANCE_MATRIX.md`
- `reports/kilo-rapidmlx-baseline/closure-20260612T075353Z/REPORT.md`
- `reports/kilo-rapidmlx-baseline/closure-20260612T075353Z/TEST_RECONSTRUCTION.md`
- `reports/kilo-rapidmlx-baseline/run-20260612T072549Z-context-test.json`
- `reports/kilo-rapidmlx-baseline/run-20260612T072856Z-mcp-test.json`
- `reports/kilo-rapidmlx-baseline/run-20260612T073211Z-stability-test.json`
- `reports/kilo-rapidmlx-baseline/run-20260612T073341Z-recovery-test.json`
- `reports/kilo-rapidmlx-baseline/run-20260612T073702Z-resource-test.json`

These tests were executed with active MCP servers and are not eligible for the canonical minimal baseline.

## Known Limitations

1. **Cache classification:** INSUFFICIENT_EVIDENCE - Direct server cache hit evidence not available
2. **Memory classification:** UNKNOWN - MLX unified-memory allocation not exposed from server process
3. **Same-session continuation:** Tested in single session (12 turns), not two separate sessions

## Evidence Paths

- `reports/kilo-rapidmlx-baseline/closure-20260612T080400Z/results.json`
- `reports/kilo-rapidmlx-baseline/closure-20260612T080400Z/KILO_BASELINE_ACCEPTANCE_MATRIX.md`
- `reports/kilo-rapidmlx-baseline/closure-20260612T080400Z/REPORT.md`
