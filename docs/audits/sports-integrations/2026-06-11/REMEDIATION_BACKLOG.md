# Remediation Backlog

**Audit Run:** SPORTS-AUDIT-20260611T093602Z-b6a3ced  
**Generated:** 2026-06-11T10:30:00Z

---

## Priority Order

Items ordered by severity, then risk reduction, then information gain.

---

## Item: REM-001

### espn-football NameError fix

| Field | Value |
|---|---|
| **Item ID** | REM-001 |
| **Integration Key** | espn-football::football::ENRICHMENT_ONLY::default |
| **Severity** | HIGH |
| **Defect** | `NameError: name 'json' is not defined` in `get_fixtures()` |
| **Evidence IDs** | cmd-live-003 |
| **Affected Capabilities** | Football enrichment fallback |
| **Affected Consumers** | StatFetcher fallback chain |
| **Smallest Safe Repair** | Add `import json` to src/bet/api_clients/espn.py |
| **Required Live Proof** | get_fixtures() returns non-empty list |
| **Acceptance Gates** | G4_DECLARED_CORE_CAPABILITIES: PASS |
| **Dependencies** | None |
| **Complexity** | S |
| **Recommended Reasoning** | medium |

---

## Item: REM-002

### HLTV browser automation resilience

| Field | Value |
|---|---|
| **Item ID** | REM-002 |
| **Integration Key** | hltv::cs2::EVENT_AND_ENRICHMENT::default |
| **Severity** | MEDIUM |
| **Defect** | Cloudflare protection requires Playwright stealth; may be blocked |
| **Evidence IDs** | ev-001 |
| **Affected Capabilities** | CS2 H2H, team stats |
| **Affected Consumers** | Esports enrichment |
| **Smallest Safe Repair** | Add circuit breaker + bo3.gg fallback documentation |
| **Required Live Proof** | get_team_stats() returns valid data OR fallback activates |
| **Acceptance Gates** | G9_FAILURE_ISOLATION_AND_BUDGETS: PASS |
| **Dependencies** | None |
| **Complexity** | M |
| **Recommended Reasoning** | medium |

---

## Item: REM-003

### api-hockey empty fixtures investigation

| Field | Value |
|---|---|
| **Item ID** | REM-003 |
| **Integration Key** | api-hockey::hockey::EVENT_AND_ENRICHMENT::default |
| **Severity** | MEDIUM |
| **Defect** | get_fixtures(2026-06-11) returned 0 fixtures |
| **Evidence IDs** | cmd-live-006 |
| **Affected Capabilities** | Hockey event discovery |
| **Affected Consumers** | EventDiscoveryCoordinator |
| **Smallest Safe Repair** | Verify date format, season status, API quota |
| **Required Live Proof** | get_fixtures() returns fixtures for in-season date |
| **Acceptance Gates** | G4_DECLARED_CORE_CAPABILITIES: PASS |
| **Dependencies** | None |
| **Complexity** | S |
| **Recommended Reasoning** | low |

---

## Item: REM-004

### Betclic odds verification documentation

| Field | Value |
|---|---|
| **Item ID** | REM-004 |
| **Integration Key** | betclic::football::ODDS_ONLY::default |
| **Severity** | MEDIUM |
| **Defect** | Browser automation required; live verification not executed |
| **Evidence IDs** | ev-001 |
| **Affected Capabilities** | Odds verification |
| **Affected Consumers** | bet-scanner |
| **Smallest Safe Repair** | Document manual verification workflow in BetclicBoundary rule |
| **Required Live Proof** | Manual user verification per contract |
| **Acceptance Gates** | G12_ACCESS_SECRET_AND_UNTRUSTED_DATA_SAFETY: PASS |
| **Dependencies** | None |
| **Complexity** | S |
| **Recommended Reasoning** | low |

---

## Item: REM-005

### Esports enrichment test coverage

| Field | Value |
|---|---|
| **Item ID** | REM-005 |
| **Integration Key** | Multiple esports integrations |
| **Severity** | LOW |
| **Defect** | No dedicated tests for hltv, vlr, opendota live operations |
| **Evidence IDs** | tests/ inventory |
| **Affected Capabilities** | Esports enrichment reliability |
| **Affected Consumers** | bet-enricher |
| **Smallest Safe Repair** | Add integration tests with mocked responses |
| **Required Live Proof** | pytest passes with mocked fixtures |
| **Acceptance Gates** | G10_TEST_SEPARATION: PASS |
| **Dependencies** | None |
| **Complexity** | M |
| **Recommended Reasoning** | low |

---

## Summary

| Severity | Count |
|---|---|
| CRITICAL | 0 |
| HIGH | 1 |
| MEDIUM | 3 |
| LOW | 1 |
| **Total** | 5 |

---

## First Repair Recommendation

**REM-001: espn-football NameError fix**

- **Risk Reduction:** HIGH — Fixes broken enrichment fallback
- **Information Gain:** HIGH — Unblocks football enrichment verification
- **Complexity:** S — Single import statement
- **Reasoning Level:** medium
