# KILO_BASELINE_ACCEPTANCE_MATRIX

| Gate | Status | Evidence Path | Justification |
|------|--------|---------------|---------------|
| Phase 1 evidence valid | PASS | reports/rapidmlx-baseline/results.json | All 76 tests passed, configuration fingerprint matches |
| Rapid-MLX fingerprint unchanged | PASS | PID 54776, start Fri Jun 12 08:43:53 2026 | Same process running, version 0.7.1, model qwen3.6-35b-4bit |
| Kilo configuration valid | PASS | kilo.jsonc | Provider, model, limits all correctly configured |
| Provider and model correctly resolved | PASS | kilo debug config | openai-compatible/qwen36-local-35b → default |
| Explicit token limits correctly resolved | PASS | kilo.jsonc lines 29-33 | context: 28672, input: 24576, output: 4096 |
| MCP isolated from baseline | **BLOCKED** | Global kilo.json | memory MCP has no enabled field, cannot disable at project level |
| No project plugin/custom tool/custom agent | PASS | kilo.jsonc | Only built-in agents defined, no plugins |
| Connectivity 5/5 | NOT RUN | — | Blocked by MCP isolation requirement |
| Built-in tools 20/20 | NOT RUN | — | Blocked by MCP isolation requirement |
| Same-session continuation 24/24 | NOT RUN | — | Blocked by MCP isolation requirement |
| No malformed mandatory tool calls | NOT RUN | — | Blocked by MCP isolation requirement |
| No duplicate mandatory tool executions | NOT RUN | — | Blocked by MCP isolation requirement |
| No unexpected tools | NOT RUN | — | Blocked by MCP isolation requirement |
| No ContextOverflowError | NOT RUN | — | Blocked by MCP isolation requirement |
| No Compaction exhausted | NOT RUN | — | Blocked by MCP isolation requirement |
| No repetition collapse | NOT RUN | — | Blocked by MCP isolation requirement |
| No Rapid-MLX crash or restart | PASS | ps output | PID 54776 running since 08:43:53, no restart detected |
| Resource health acceptable | PASS | ps, lsof | RSS 43 MB stable, no OOM, no thermal warnings |

---

## Summary

- **PASS:** 9 gates
- **FAIL:** 0 gates
- **BLOCKED:** 1 gate (MCP isolation)
- **NOT RUN:** 9 gates (blocked by MCP isolation)

## Decision

**KILO_BASELINE_BLOCKED**

The canonical minimal Kilo baseline cannot be tested because the global `memory` MCP server cannot be disabled at the project level. The user must either:

1. Approve modification of global Kilo configuration
2. Accept global MCP as part of the baseline
3. Provide an alternative isolation mechanism
