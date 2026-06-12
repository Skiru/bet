# Remediation Backlog (Reconciled)

**Audit Run:** SPORTS-AUDIT-20260611T093602Z-b6a3ced  
**Updated:** 2026-06-11T22:30:00Z

---

## Priority Order

Items are ordered by unresolved contract severity, then risk reduction, then information gain.

---

## Item: REM-001

### espn-football live NameError fix

| Field | Value |
|---|---|
| **Item ID** | REM-001 |
| **Integration Key** | `espn-football::football::ENRICHMENT_ONLY::default` |
| **Severity** | RESOLVED-HIGH |
| **Status** | CLOSED by REM-001 |

---

## Item: REM-001B

### espn-football identity and temporal safety verification

| Field | Value |
|---|---|
| **Item ID** | REM-001B |
| **Integration Key** | `espn-football::football::ENRICHMENT_ONLY::default` |
| **Severity** | RESOLVED-MEDIUM |
| **Status** | CLOSED by REM-001B |

---

## Item: REM-002A

### espn-football crosswalk, evidence, status, and migration foundation

| Field | Value |
|---|---|
| **Item ID** | REM-002A |
| **Integration Key** | `espn-football::football::ENRICHMENT_ONLY::default` |
| **Severity** | RESOLVED-HIGH |
| **Status** | PRODUCTION_READY — exact fixture-source crosswalk, content-addressed replayable evidence, explicit typed statuses, rerunnable migration safety, no-network replay, and duplicate-free rerun all proved |
| **Defect** | The ESPN football path previously assumed canonical fixture ownership for ESPN event IDs, persisted non-replayable/truncated evidence identifiers, collapsed source failures to list semantics, and left migration v14 rerun safety under-proved. |
| **Evidence IDs** | `ev-rem002a-001`, `ev-rem002a-002`, `ev-rem002a-003` |
| **Affected Capabilities** | source-event crosswalk resolution, recent-form enrichment persistence, explicit source failure classification, evidence replay, SQLite migration safety |
| **Affected Consumers** | `bet.stats.enrichment._resolve_espn_fixture_identity()`, `bet.stats.enrichment._try_espn_fetch()`, `bet.api_clients.espn.ESPNClient`, `bet.db.schema.migrate()` |
| **Verification** | canonical fixture `1` resolved only through `fixture_sources` to ESPN event `740968`; bundle SHA-256 `32f075eb12a4a6aae53ca9e10c1e222359e45fa99a47a22b6115cb4843f3def0`; replay matched live output with network blocked; second persistence run stayed `20 -> 20`; migration scenarios passed in deterministic coverage |
| **Acceptance Gates** | `G1 PASS`, `G3 PASS`, `G4 PASS`, `G5 PASS`, `G7 PASS`, `G8 PASS`, `G10 PASS`, `G11 PASS`, `G12 PASS` |
| **Dependencies** | REM-001, REM-001B |
| **Complexity** | M |
| **Recommended Reasoning** | high |
| **Follow-up** | none for `espn-football`; remaining portfolio evidence/replay work continues under REM-002 |

---

## Item: REM-002B

### API-Sports family typed discovery, evidence, and replay closure

| Field | Value |
|---|---|
| **Item ID** | REM-002B |
| **Integration Keys** | `api-football::football::EVENT_AND_ENRICHMENT::default`, `api-basketball::basketball::EVENT_AND_ENRICHMENT::default`, `api-volleyball::volleyball::EVENT_AND_ENRICHMENT::default`, `api-hockey::hockey::EVENT_AND_ENRICHMENT::default` |
| **Severity** | RESOLVED-MEDIUM |
| **Status** | CLOSED — api-football upgraded to PRODUCTION_READY (2026-06-12); other three remain LIVE_PARTIAL with provider-plan restrictions documented |
| **Defect** | API-Sports family previously lacked strict live/deterministic boundaries, typed production discovery wiring, retained replayable evidence, and duplicate-free rerun proof. |
| **Evidence IDs** | `.kilo/artifacts/rem002b_api_sports_summary.json`, `.kilo/artifacts/rem002c_fb/checkpoint.json`, `tests/scrapers/test_api_sports_family.py`, `tests/scrapers/test_api_sports_live.py`, `docs/audits/sports-integrations/2026-06-11/repairs/REM-002B_API_SPORTS_FAMILY.md` |
| **Affected Capabilities** | typed source status propagation, source participant identity retention, deterministic evidence bundles, no-network replay, discovery persistence idempotency, strict live test opt-in, enrichment production consumer wiring |
| **Verification** | focused suite `16 passed`; full non-live suite `662 passed, 4 skipped, 6 deselected`; live suite `5 passed`; family artifact proves replay + duplicate-free rerun for football=98, basketball=31, volleyball=6, hockey=3; api-football enrichment bundles `2b0ed4ba` (fixture stats) and `b01f22fb` (team fixtures) retained |
| **Acceptance Gates** | `G1 PASS`, `G3 PASS`, `G4 PASS`, `G5 PASS`, `G7 PASS`, `G8 PASS`, `G10 PASS`, `G11 PASS`, `G12 PASS` for api-football |
| **Complexity** | M |
| **Follow-up** | api-basketball, api-volleyball, api-hockey remain LIVE_PARTIAL due to provider-plan restrictions on enrichment endpoints (not code defects) |

---

## Item: REM-002

### Remaining portfolio E4 evidence/replay/rerun gap

| Field | Value |
|---|---|
| **Item ID** | REM-002 |
| **Integration Key** | multiple current-live integrations excluding `espn-football::football::ENRICHMENT_ONLY::default` |
| **Severity** | HIGH |
| **Defect** | Current-live integrations other than espn-football still lack retained raw evidence, deterministic no-network replay, or idempotent rerun proof sufficient for `E4_CURRENT_REPLAY_RERUN`. |
| **Evidence IDs** | corrected matrix + corrected manifest gate summaries |
| **Affected Consumers** | production-readiness decisions for `api-football`, `api-basketball`, `api-volleyball`, `api-hockey`, `tennis-abstract`, `sackmann::atp`, `opendota`, `vlr` |
| **Smallest Safe Repair** | extend the REM-002A evidence/replay pattern one live integration at a time |
| **Acceptance Gates** | `G7`, `G8`, `G10`, `G11`, `G12` |
| **Complexity** | L |
| **Update (REM-002C)** | API-Sports family enrichment assessed 2026-06-12: api-football enrichment fully functional; api-basketball, api-volleyball, api-hockey have provider-plan restrictions on enrichment endpoints. Provider limitation documented, not code defect. |

---

## Item: REM-006

### Multisport provider onboarding assessment

| Field | Value |
|---|---|
| **Item ID** | REM-006 |
| **Integration Key** | `sportdb.dev`, `thesportsdb` |
| **Severity** | LOW |
| **Status** | CLOSED |
| **Defect** | No working registered clients for SportDB.dev or TheSportsDB. |
| **Evidence** | TheSportsDB client exists in `src/bet/api_clients/thesportsdb.py` but marked DEPRECATED (97.8% failure rate) and NOT REGISTERED in CLIENT_REGISTRY. SportDB.dev client ABSENT. THESPORTSDB_KEY configured but unused. |
| **Resolution** | 2026-06-12: TheSportsDB free tier tested and verified for cross-reference capability (idESPN, idAPIfootball fields present). Classified as CROSS_REFERENCE_ONLY. SportDB.dev requires API key registration - blocked. No new provider implementation required for football vertical closure. |
| **Recommendation** | TheSportsDB useful for optional ID crosswalk enhancement. SportDB.dev requires API key if needed in future. |

---

## Item: REM-003

### Missing current proof for odds-api-io discovery portfolio

| Field | Value |
|---|---|
| **Item ID** | REM-003 |
| **Integration Key** | `odds-api-io::*::EVENT_DISCOVERY::*` (8 rows) |
| **Severity** | MEDIUM |
| **Defect** | Eight atomic discovery integrations still lack preserved role-appropriate current proof. |
| **Dependencies** | REM-002 recommended before renewed production-ready claims |

---

## Item: REM-004

### Browser-integration proof gap and access-method correction

| Field | Value |
|---|---|
| **Item ID** | REM-004 |
| **Integration Key** | `betclic::football::ODDS_ONLY::default`, `hltv::cs2::EVENT_AND_ENRICHMENT::default`, `bo3gg::cs2::EVENT_AND_ENRICHMENT::default`, `bo3gg::valorant::EVENT_AND_ENRICHMENT::default` |
| **Severity** | MEDIUM |
| **Defect** | Browser integrations remain below certification without repeatable permitted current proof. |

---

## Item: REM-005

### Direct deterministic source-test gap for 29 integrations

| Field | Value |
|---|---|
| **Item ID** | REM-005 |
| **Integration Key** | 29 uncovered keys listed in `AUDIT_RECONCILIATION.md` (now 25 after REM-002B) |
| **Severity** | MEDIUM |
| **Defect** | 25/45 integration keys still have no direct source-specific deterministic proof (reduced from 29 by REM-002B). |

---

## Summary

| Severity | Count |
|---|---:|
| CRITICAL | 0 |
| HIGH | 1 |
| MEDIUM | 3 |
| LOW | 1 |
| **Total** | **5** |

---

## First Repair Recommendation

**REM-002: Remaining portfolio E4 evidence/replay/rerun gap**

- **Risk Reduction:** HIGH
- **Information Gain:** HIGH
- **Complexity:** L
- **Reasoning Level:** high
