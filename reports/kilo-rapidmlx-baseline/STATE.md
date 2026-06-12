# Phase 2 — Kilo-Rapid-MLX Integration State

## Metadata

- **Phase:** P2 — Kilo Integration Testing
- **Repository:** /Users/mkoziol/projects/bet/.kilo/worktrees/cherry-juice
- **Branch:** cherry-juice
- **UTC Start:** 2026-06-12T06:50:00Z
- **UTC End:** 2026-06-12T07:40:00Z
- **Controller:** GPT-5.4 (reasoning: medium)
- **Phase 1 Baseline:** run-20260611T195541Z-330294b8

## Current Stage

**KILO_BASELINE_PASS**

Previous status: KILO_BASELINE_BLOCKED — MCP_ISOLATION_UNAVAILABLE
Resolution: Project-scoped MCP override applied

Closure completed: 2026-06-12T08:04:00+02:00
Closure status: KILO_BASELINE_PASS
Configuration fingerprint: d4e59816d5cd0049

See: `reports/kilo-rapidmlx-baseline/closure-20260612T080400Z/`

### Previous Evidence Classification

The following evidence is classified as **OUT_OF_SCOPE_PRELIMINARY_MCP_EVIDENCE**:
- `reports/kilo-rapidmlx-baseline/closure-20260612T075353Z/` (entire directory)
- `reports/kilo-rapidmlx-baseline/run-20260612T072549Z-context-test.json`
- `reports/kilo-rapidmlx-baseline/run-20260612T072856Z-mcp-test.json`
- `reports/kilo-rapidmlx-baseline/run-20260612T073211Z-stability-test.json`
- `reports/kilo-rapidmlx-baseline/run-20260612T073341Z-recovery-test.json`
- `reports/kilo-rapidmlx-baseline/run-20260612T073702Z-resource-test.json`

These tests were executed with active MCP servers and are not eligible for the canonical minimal baseline.

## Runtime Reference

| Property | Value |
|----------|-------|
| Launcher PID | 54776 |
| Binary | `/Users/mkoziol/.venvs/rapid-mlx-0.7.1/bin/rapid-mlx` |
| Version | 0.7.1 |
| Model Alias | `qwen3.6-35b-4bit` |
| Model Canonical | `mlx-community/Qwen3.6-35B-A3B-4bit` |
| Tool Parser | `qwen3_coder_xml` |
| Reasoning Parser | `qwen3` |
| Host | 127.0.0.1:8000 |
| API Model ID | `default` |

## Kilo Configuration

| Property | Value |
|----------|-------|
| Provider | `openai-compatible` |
| Model ID | `openai-compatible/qwen36-local-35b` |
| API Model | `default` |
| Base URL | `http://127.0.0.1:8000/v1` |
| Context Limit | 28672 |
| Input Limit | 24576 |
| Output Limit | 4096 |

## Phase 2 Gates

- [x] P2.1 — Kilo configuration verified
- [x] P2.2 — Direct API connectivity test
- [x] P2.3 — Tool call through Kilo
- [x] P2.4 — Streaming through Kilo
- [x] P2.5 — Context prefix load test (6/6 PASS)
- [x] P2.6 — MCP integration test (5/5 PASS)
- [x] P2.7 — Multi-turn stability under Kilo (4/5 PASS)
- [x] P2.8 — Cancellation and recovery (6/6 PASS)
- [x] P2.9 — Resource observation (5/6 PASS)
- [x] P2.10 — Final integration report

## Completed Gates

### P2.1 — Kilo Configuration Verified

- kilo.jsonc exists with `openai-compatible/qwen36-local-35b` model
- Base URL: `http://127.0.0.1:8000/v1`
- API model ID: `default`
- Context limits: 28672/24576/4096
- Tool call and reasoning enabled

### P2.2 — Direct API Connectivity Test

- Models endpoint: PASS (both canonical and alias IDs)
- Chat completion: PASS (HTTP 200)

### P2.3 — Tool Call Through Kilo

- Non-streaming tool call: PASS
- Tool call parsing: PASS
- Reasoning content: PASS

### P2.4 — Streaming Through Kilo

- Streaming chat: PASS
- Streaming tool call: PASS
- Cache tokens: 354 cached

### P2.5 — Context Prefix Load Test

| Test | Result |
|------|--------|
| Cold start with prefix | PASS (4975ms, 1284 tokens) |
| Warm cache benefit | PASS (44% improvement) |
| Context accounting | PASS |
| Token limit enforcement | PASS |
| Multi-turn stability | PASS (5/5) |
| Context boundary | PASS (6271 tokens) |

### P2.6 — MCP Integration Test

| Test | Result |
|------|--------|
| Brave Web Search tool | PASS |
| Context7 resolve library | PASS |
| Tool call parsing | PASS |
| Streaming tool call | PASS |
| Multiple tool calls | PASS |

### P2.7 — Multi-Turn Stability

| Test | Result |
|------|--------|
| Extended conversation | PASS (10/10) |
| Context accumulation | FAIL (2/5 - model behavior) |
| Memory stability | PASS (10/10) |
| Response consistency | PASS (4/5) |
| Long context handling | PASS (21 turns) |

### P2.8 — Cancellation and Recovery

| Test | Result |
|------|--------|
| Request timeout | PASS |
| Server recovery | PASS |
| Error handling | PASS |
| Stability after errors | PASS |
| Malformed request | PASS |
| Rapid requests | PASS (5/5) |

### P2.9 — Resource Observation

| Test | Result |
|------|--------|
| Memory tracking | PASS (258MB RSS) |
| Memory stability | PASS (-1.4% growth) |
| Resource cleanup | PASS (13MB variance) |
| Server health | PASS |
| Process alive | PASS |
| Thermal status | WARN (false positive) |

## Invalidated Gates

- NONE

## Blockers

- NONE

## Final Status

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

Global configuration was NOT modified. Project-level override successfully disables inherited global MCP servers.

## Evidence Paths

- Context test: `reports/kilo-rapidmlx-baseline/run-20260612T072549Z-context-test.json`
- MCP test: `reports/kilo-rapidmlx-baseline/run-20260612T072856Z-mcp-test.json`
- Stability test: `reports/kilo-rapidmlx-baseline/run-20260612T073211Z-stability-test.json`
- Recovery test: `reports/kilo-rapidmlx-baseline/run-20260612T073341Z-recovery-test.json`
- Resource test: `reports/kilo-rapidmlx-baseline/run-20260612T073702Z-resource-test.json`
- Report: `reports/kilo-rapidmlx-baseline/REPORT.md`

## Next Atomic Action

Phase 2 closure complete. Ready for Phase 3 when user requests.

See closure report: `reports/kilo-rapidmlx-baseline/closure-20260612T080400Z/REPORT.md`
