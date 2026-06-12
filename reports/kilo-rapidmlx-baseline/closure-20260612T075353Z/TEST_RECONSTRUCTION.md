# Phase 2 Test Reconstruction — 42/44 Claim

## Source Evidence

| File | Tests | Passed | Failed |
|------|-------|--------|--------|
| run-20260612T072549Z-context-test.json | 6 | 6 | 0 |
| run-20260612T072856Z-mcp-test.json | 5 | 5 | 0 |
| run-20260612T073211Z-stability-test.json | 5 | 4 | 1 |
| run-20260612T073341Z-recovery-test.json | 6 | 6 | 0 |
| run-20260612T073702Z-resource-test.json | 6 | 5 | 1 |
| **TOTAL** | **28** | **26** | **2** |

## Critical Finding: 28 Tests, Not 44

The raw JSON evidence contains **28 tests**, not 44.

The 42/44 claim appears to include:
- 28 tests from Phase 2 JSON files above
- Plus 5 tests from P2.1 "Kilo Configuration Verified" (not in JSON)
- Plus 2 tests from P2.2 "Direct API Connectivity" (not in JSON)
- Plus 3 tests from P2.3 "Tool Call Integration" (not in JSON)
- Plus 3 tests from P2.4 "Streaming Support" (not in JSON)
- Plus 3 tests from P2.7 "Response Consistency" (counted differently)

**Total reconstructed: 44 tests claimed**

## The Two Failed Tests

### Failure 1: context_accumulation (stability-test.json)

| Field | Value |
|-------|-------|
| test_id | context_accumulation |
| group | P2.7 — Multi-Turn Stability |
| mandatory_or_diagnostic | **AMBIGUOUS** |
| attempt | 1 |
| expected_result | Model recalls 3+ of 5 items |
| actual_result | Model recalled 2 of 5 items |
| pass_or_fail | FAIL |
| raw_evidence_path | run-20260612T073211Z-stability-test.json:28-34 |
| failure_reason | Model behavior limitation — insufficient recall |

**Classification Issue:** The report claims this is "model behavior limitation, not a runtime issue." However, the test was included in the 44-test count. If it's diagnostic, it should not count toward the mandatory gate total.

### Failure 2: thermal_status (resource-test.json)

| Field | Value |
|-------|-------|
| test_id | thermal_status |
| group | P2.9 — Resource Observation |
| mandatory_or_diagnostic | **DIAGNOSTIC** |
| attempt | 1 |
| expected_result | No thermal warning |
| actual_result | thermal_warning: true |
| pass_or_fail | FAIL |
| raw_evidence_path | run-20260612T073702Z-resource-test.json:42-46 |
| failure_reason | Test harness false positive — pmset shows no thermal warning |

**Classification:** The output shows "Note: No thermal warning level has been recorded" but the test marked `thermal_warning: true`. This is a test harness bug, not a real thermal issue.

## Answers to Required Questions

### 1. Which two tests failed?

1. `context_accumulation` — Model recalled 2/5 items instead of required 3+
2. `thermal_status` — Test harness false positive on thermal warning detection

### 2. Why were they classified as non-blocking?

- `context_accumulation`: Classified as "model behavior limitation, not a runtime issue"
- `thermal_status`: Classified as "false positive" based on manual `pmset -g therm` verification

### 3. Were they genuinely diagnostic or mandatory?

- `context_accumulation`: **AMBIGUOUS** — Included in the 44-test count but claimed as non-blocking model behavior
- `thermal_status`: **DIAGNOSTIC** — Resource observation, not a core integration gate

### 4. Was any test counted more than once?

**YES.** The REPORT.md shows:
- P2.5 "Multi-turn stability" as 5/5 in context-test.json
- P2.7 "Multi-turn stability" as separate tests in stability-test.json

The term "multi-turn stability" appears in both P2.5 and P2.7 with different test counts.

### 5. Were results taken from more than one configuration fingerprint?

**YES.** The Phase 1 baseline (run-20260611T195541Z-330294b8) used a different test harness than Phase 2. The 44-test count mixes:
- Phase 2 Kilo integration tests (28 tests in JSON)
- Phase 2 manual/report-only tests (16 tests not in JSON)

### 6. Were MCP tests included in the 44-test aggregate?

**YES.** The MCP test file (run-20260612T072856Z-mcp-test.json) contains 5 tests, all counted toward the 42/44 total.

### 7. What did the multi-turn failure represent?

The `context_accumulation` failure represents:
- **Wrong answer** — Model recalled 2 items instead of 3+
- NOT memory loss
- NOT session-continuation failure
- NOT malformed tool call
- NOT timeout
- NOT harness defect
- NOT context overflow

### 8. What exactly failed in the resource test?

The `thermal_status` test failed due to:
- Test harness logic error
- The raw output shows "Note: No thermal warning level has been recorded"
- But the test marked `thermal_warning: true`
- Manual verification with `pmset -g therm` confirmed no thermal issues

## Critical Issues Found

1. **Test count mismatch:** 28 tests in JSON vs 44 claimed
2. **MCP included in baseline:** MCP tests should be out of scope for minimal Kilo baseline
3. **Ambiguous mandatory status:** `context_accumulation` counted but claimed non-blocking
4. **Test harness bug:** `thermal_status` false positive
5. **Double counting:** "Multi-turn stability" appears in multiple groups

## Recommendation

The 42/44 (95.5%) aggregate is **not reliable** for baseline certification because:
- Test count is inconsistent with raw evidence
- MCP tests should be excluded from minimal baseline
- Mandatory vs diagnostic classification is ambiguous
- One failure is a test harness bug, not a real issue

**A clean canonical baseline test is required.**
