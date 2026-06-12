# LOCAL_AGENT_SETUP_ACCEPTANCE_MATRIX

**Certification ID:** CERT-20260612T142200Z  
**Generated:** 2026-06-12T14:22:00Z  
**Closure Session:** ses_143d2959dffePsto7neSXSGS7z  
**Original Session:** ses_1442814d3ffeD3xwnS5pXzl1KX  
**Scenarios Rerun:** NO  
**Scenarios Preserved:** YES

---

## Acceptance Matrix

| Gate | Status | Evidence |
|------|--------|----------|
| 13 preserved scenarios complete | PASS | C01-C13 all documented in PRESERVED_SESSION_EVIDENCE.md |
| All canonical specialists represented | PASS | bet-settler, bet-db-analyst, bet-scanner, bet-scout, bet-enricher, bet-statistician, bet-valuator, bet-challenger, bet-reconciler, bet-builder, bet-engineer (x2), bet-test-engineer |
| bet-engineer represented twice | PASS | C12 (fixture operation) and C13 (mutation-required) |
| Actual canonical child-agent routing proven | PASS | Canary 2: requested=bet-scanner, actual=bet-scanner |
| All expected PASS outcomes matched | PASS | C03, C04, C05, C06, C07, C10, C11, C12 all PASS |
| Expected challenger FAIL matched | PASS | C08 returned FAIL/CANDIDATE_REJECTED |
| Expected capability BLOCKED outcomes matched | PASS | C01, C02, C09, C13 all BLOCKED |
| Output schemas valid | PASS | All 13 responses had STATUS, DECISION, EVIDENCE, CALCULATIONS, UNCERTAINTY, RISKS, NEXT_ACTION |
| Direct artifact tool Canary 1 passed | PASS | 68 bytes, SHA256: 771c44e1136d76d7933cbf08847a1b03762a009d8ec0dd43684fcecb9bf66ec6 |
| Canonical child Task Canary 2 passed | PASS | bet-scanner child completed, fixture F003 verified |
| Post-Task artifact Canary 3 passed | PASS | 93 bytes, SHA256: 82cfde2fcee8b2196bfbf860340da4d55b605da98e0809e427bf8b08472357e3 |
| Permission prompts zero | PASS | 0 permission prompts |
| Question calls zero | PASS | 0 question calls |
| Unauthorized Bash/write/edit/patch zero | PASS | 0 unauthorized mutations |
| Web/MCP/database bypass zero | PASS | 0 web, MCP, or database bypasses |
| Output exhaustion zero | PASS | 0 thinking output exhaustion occurrences |
| ContextOverflowError zero | PASS | 0 context overflow errors |
| Compaction exhausted zero | PASS | 0 compaction failures |
| Malformed tool calls zero | PASS | 0 malformed tool calls |
| Duplicated tool calls zero | PASS | 0 duplicate tool calls |

---

## Scenario Ledger

| Scenario | Requested Specialist | Actual Specialist | Child Session | Expected | Actual | Match |
|----------|---------------------|-------------------|---------------|----------|--------|-------|
| C01 | bet-settler | bet-settler | ses_14425edc6ffewxnxkyKuiKrC2m | BLOCKED | BLOCKED | ✓ |
| C02 | bet-db-analyst | bet-db-analyst | ses_1442374c1ffecLo2jDkl7tojoN | BLOCKED | BLOCKED | ✓ |
| C03 | bet-scanner | bet-scanner | ses_1442113acffeSYF9ImDUnpBeF0 | PASS | PASS | ✓ |
| C04 | bet-scout | bet-scout | ses_1441ea917ffeQTK3C7Eiskt4E3 | PASS | PASS | ✓ |
| C05 | bet-enricher | bet-enricher | ses_1441b238dffegWtBHHLqPNE0B8 | PASS | PASS | ✓ |
| C06 | bet-statistician | bet-statistician | ses_1441871d9ffeFMHAsRjNfWE9xg | PASS | PASS | ✓ |
| C07 | bet-valuator | bet-valuator | ses_144147741fferObTvDLAIcJZcb | PASS | PASS | ✓ |
| C08 | bet-challenger | bet-challenger | ses_144112f23ffeBJvpyYNS0BGWQH | FAIL | FAIL | ✓ |
| C09 | bet-reconciler | bet-reconciler | ses_1440e52beffe2iv6WDAm6ivaz5 | BLOCKED | BLOCKED | ✓ |
| C10 | bet-builder | bet-builder | ses_14408ade7ffehLZta5r4tvfstx | PASS | PASS | ✓ |
| C11 | bet-test-engineer | bet-test-engineer | ses_144056436ffe1KFPq2HHgxdGEB | PASS | PASS | ✓ |
| C12 | bet-engineer | bet-engineer | ses_14401f7b2ffe9A3Ew5o74fIHlN | PASS | PASS | ✓ |
| C13 | bet-engineer | bet-engineer | ses_143ff010cffeTUKXV2mNWeBTL0 | BLOCKED | BLOCKED | ✓ |

---

## Canary Verification

### Canary 1: Direct bet_artifact_write
- **Path:** `reports/betting-demo/runtime-canary/canary-1.json`
- **Bytes:** 68
- **SHA256:** `771c44e1136d76d7933cbf08847a1b03762a009d8ec0dd43684fcecb9bf66ec6`
- **Status:** PASS

### Canary 2: Child Task (bet-scanner)
- **Requested Agent:** bet-scanner
- **Actual Agent:** bet-scanner
- **Fixture:** f003-scanner-feed.json
- **Result:** Fixture F003_SCANNER_FEED verified, 3 synthetic matches
- **Status:** PASS

### Canary 3: Post-Task bet_artifact_write
- **Path:** `reports/betting-demo/runtime-canary/canary-3-summary.json`
- **Bytes:** 93
- **SHA256:** `82cfde2fcee8b2196bfbf860340da4d55b605da98e0809e427bf8b08472357e3`
- **Status:** PASS

---

## Runtime Metrics

```
thinking output exhaustion occurrences: 0
tool unavailable errors: 0
permission prompts: 0
```

---

## Canonical Routing Verification

- **Canary 2 Requested Agent:** bet-scanner
- **Canary 2 Actual Agent:** bet-scanner
- **Routing Gate:** PASS
- **Evidence:** Task tool invoked bet-scanner subagent per kilo.jsonc agent definition at line 289

---

## Deferred Capabilities

The following capabilities remain explicitly deferred and are NOT certified:

- `bet_sqlite_query` (database access)
- Real betting scripts (fixture-only operations)
- Web search (MCP disabled)
- Brave Search (MCP disabled)
- Context7 (MCP disabled)
- Playwright (MCP disabled)

---

## Evidence Paths

- Preserved session evidence: `reports/betting-demo/runtime-repair-evidence-20260612T155800Z/PRESERVED_SESSION_EVIDENCE.md`
- Original builder artifact: `reports/betting-demo/final-agent-certification-20260612T143920Z/coupon.json`
- Canary 1 artifact: `reports/betting-demo/runtime-canary/canary-1.json`
- Canary 3 artifact: `reports/betting-demo/runtime-canary/canary-3-summary.json`
- Agent config: `kilo.jsonc`
