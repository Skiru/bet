# Integration Matrix — Sports Integrations Portfolio Audit (Reconciled)

**Audit Run:** SPORTS-AUDIT-20260611T093602Z-b6a3ced  
**Schema Version:** 2.0  
**Reconciled:** 2026-06-11T11:24:19Z

---

## Reconciled Summary Statistics

- **Total Sports Found:** 8
- **Total Integration Keys:** 45
- **Original 42-count status:** superseded; see `AUDIT_RECONCILIATION.md`

### By Role

| Role | Count |
|---|---:|
| EVENT_AND_ENRICHMENT | 10 |
| EVENT_DISCOVERY | 13 |
| ENRICHMENT_ONLY | 15 |
| ODDS_ONLY | 1 |
| HISTORICAL_DATASET | 6 |
| **Total** | **45** |

### By Access Method

| Access Method | Count |
|---|---:|
| LICENSED_OR_OFFICIAL_API | 14 |
| DOCUMENTED_PUBLIC_API | 10 |
| STATIC_HTML | 9 |
| PUBLIC_XHR_OR_JSON | 6 |
| BROWSER_AUTOMATION | 4 |
| LOCAL_OR_OPEN_DATASET | 2 |
| **Total** | **45** |

### Corrected Final States

| Final State | Count |
|---|---:|
| PRODUCTION_READY | 1 |
| PRODUCTION_CANDIDATE | 0 |
| LIVE_PARTIAL | 8 |
| DETERMINISTIC_ONLY | 14 |
| IMPLEMENTED_UNVERIFIED | 22 |
| **Total** | **45** |

### Gate Legend

- `G1` runtime reachable
- `G4` declared core capability evidence
- `G7` raw evidence + replay
- `G8` idempotent persistence
- `G10` deterministic test separation
- `G12` access / secret / untrusted-data safety

---

## Reconciled Rows

| integration_key | access | reachability | current proof | direct E2 in audited 186 | gate summary | final state | top blocker |
|---|---|---|---|---:|---|---|---|
| `api-football::football::EVENT_AND_ENRICHMENT::default` | LICENSED_OR_OFFICIAL_API | ACTIVE_REACHABLE | E3 discovery proved: 98 fixtures on `2026-06-11`, bundle `de648d03`, replay/rerun passed; enrichment for historical seasons (2022-2024) works; current-season (2026) enrichment classified as `PLAN_RESTRICTED` with `fallback_eligible=true`; ESPN is primary enrichment source for current season | 11 | G1 PASS; G4 PASS; G7 PASS; G8 PASS; G10 PASS; G12 PASS | PRODUCTION_READY | NONE |
| `odds-api-io::football::EVENT_DISCOVERY::default` | LICENSED_OR_OFFICIAL_API | ACTIVE_REACHABLE | no preserved current proof | 0 | G1 PASS; G4 NOT_EXECUTED; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 NOT_EXECUTED; G12 PASS | IMPLEMENTED_UNVERIFIED | current discovery proof missing |
| `odds-api::football::EVENT_DISCOVERY::default` | LICENSED_OR_OFFICIAL_API | ACTIVE_REACHABLE | no preserved current proof | 0 | G1 PASS; G4 NOT_EXECUTED; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 NOT_EXECUTED; G12 PASS | IMPLEMENTED_UNVERIFIED | current discovery proof missing |
| `espn-football::football::ENRICHMENT_ONLY::default` | DOCUMENTED_PUBLIC_API | ACTIVE_REACHABLE | E4 current replay/rerun proof in `.kilo/artifacts/rem002a_espn_football/live_summary.json`: canonical fixture `1` resolved only through `fixture_sources` to ESPN event `740968`; bundle `32f075eb12a4a6aae53ca9e10c1e222359e45fa99a47a22b6115cb4843f3def0`; no-network replay matched live output; second run stayed `20 -> 20` rows | 20 | G1 PASS; G3 PASS; G4 PASS; G5 PASS; G7 PASS; G8 PASS; G10 PASS; G11 PASS; G12 PASS | PRODUCTION_READY | NONE |
| `flashscore-football::football::ENRICHMENT_ONLY::default` | PUBLIC_XHR_OR_JSON | ACTIVE_REACHABLE | no preserved current proof | 21 | G1 PASS; G4 PARTIAL; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 PASS; G12 PASS | DETERMINISTIC_ONLY | parser tests exist; current proof absent |
| `fbref::football::HISTORICAL_DATASET::default` | STATIC_HTML | ACTIVE_REACHABLE | no preserved current proof | 0 | G1 PASS; G4 NOT_EXECUTED; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 NOT_EXECUTED; G12 PASS | IMPLEMENTED_UNVERIFIED | no variant-specific deterministic or current dataset proof |
| `understat::football::ENRICHMENT_ONLY::default` | PUBLIC_XHR_OR_JSON | ACTIVE_REACHABLE | no preserved current proof | 0 | G1 PASS; G4 NOT_EXECUTED; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 NOT_EXECUTED; G12 PASS | IMPLEMENTED_UNVERIFIED | no direct deterministic or current proof |
| `football-data-org::football::EVENT_DISCOVERY::default` | LICENSED_OR_OFFICIAL_API | ACTIVE_REACHABLE | no preserved current proof | 0 | G1 PASS; G4 NOT_EXECUTED; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 NOT_EXECUTED; G12 PASS | IMPLEMENTED_UNVERIFIED | no direct deterministic or current proof |
| `betclic::football::ODDS_ONLY::default` | BROWSER_AUTOMATION | ACTIVE_REACHABLE | no permitted repeatable current proof executed | 1 | G1 PASS; G4 PARTIAL; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 PASS; G12 PASS | DETERMINISTIC_ONLY | browser-required odds proof not executed |
| `api-basketball::basketball::EVENT_AND_ENRICHMENT::default` | LICENSED_OR_OFFICIAL_API | ACTIVE_REACHABLE | E3 current live proof refreshed 2026-06-12: 31 fixtures on `2026-06-11`; retained bundle `67fd9aa52935ad62add8c4dc66dac96cea19a767c28da8ad3ddd0e142254ac80`; registered discovery adapter now uses typed operation; replay and duplicate-free rerun passed on disposable DB; enrichment endpoints blocked by provider plan: stats UPSTREAM_ERROR, team fixtures AUTHENTICATION_ERROR (plan_restricted) | 11 | G1 PASS; G4 PARTIAL; G7 PASS; G8 PASS; G10 PASS; G12 PASS | LIVE_PARTIAL | provider plan restricts enrichment endpoints; discovery proved but enrichment requires higher-tier subscription |
| `nba-api::basketball::ENRICHMENT_ONLY::default` | DOCUMENTED_PUBLIC_API | ACTIVE_REACHABLE | no preserved current proof | 2 | G1 PASS; G4 PARTIAL; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 PASS; G12 PASS | DETERMINISTIC_ONLY | direct source tests exist; current proof absent |
| `espn-basketball::basketball::ENRICHMENT_ONLY::default` | DOCUMENTED_PUBLIC_API | ACTIVE_REACHABLE | no preserved current proof | 13 | G1 PASS; G4 PARTIAL; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 PASS; G12 PASS | DETERMINISTIC_ONLY | direct source tests exist; current proof absent |
| `flashscore-basketball::basketball::ENRICHMENT_ONLY::default` | PUBLIC_XHR_OR_JSON | ACTIVE_REACHABLE | no preserved current proof | 21 | G1 PASS; G4 PARTIAL; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 PASS; G12 PASS | DETERMINISTIC_ONLY | parser tests exist; current proof absent |
| `basketball-reference::basketball::HISTORICAL_DATASET::default` | STATIC_HTML | ACTIVE_REACHABLE | no preserved current proof | 2 | G1 PASS; G4 PARTIAL; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 PASS; G12 PASS | DETERMINISTIC_ONLY | direct source tests exist; current dataset proof absent |
| `odds-api-io::basketball::EVENT_DISCOVERY::default` | LICENSED_OR_OFFICIAL_API | ACTIVE_REACHABLE | no preserved current proof | 0 | G1 PASS; G4 NOT_EXECUTED; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 NOT_EXECUTED; G12 PASS | IMPLEMENTED_UNVERIFIED | current discovery proof missing |
| `api-volleyball::volleyball::EVENT_AND_ENRICHMENT::default` | LICENSED_OR_OFFICIAL_API | ACTIVE_REACHABLE | E3 current live proof refreshed 2026-06-12: 6 fixtures on `2026-06-11`; retained bundle `15cb3a3aed1d119f5e29fbdcc8ee2e4951e747654b143a9325075c12d1cc194c`; replay and duplicate-free rerun passed on disposable DB; enrichment: team fixtures SUCCESS bundle `313905db`, fixture stats UPSTREAM_ERROR (plan-restricted) | 11 | G1 PASS; G4 PARTIAL; G7 PASS; G8 PASS; G10 PASS; G12 PASS | LIVE_PARTIAL | provider plan restricts fixture stats endpoint; team fixtures works |
| `espn-volleyball::volleyball::ENRICHMENT_ONLY::default` | DOCUMENTED_PUBLIC_API | ACTIVE_REACHABLE | no preserved current proof | 13 | G1 PASS; G4 PARTIAL; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 PASS; G12 PASS | DETERMINISTIC_ONLY | direct source tests exist; current proof absent |
| `flashscore-volleyball::volleyball::ENRICHMENT_ONLY::default` | PUBLIC_XHR_OR_JSON | ACTIVE_REACHABLE | no preserved current proof | 21 | G1 PASS; G4 PARTIAL; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 PASS; G12 PASS | DETERMINISTIC_ONLY | parser tests exist; current proof absent |
| `volleybox::volleyball::HISTORICAL_DATASET::default` | STATIC_HTML | ACTIVE_REACHABLE | no preserved current proof | 2 | G1 PASS; G4 PARTIAL; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 PASS; G12 PASS | DETERMINISTIC_ONLY | direct source tests exist; current dataset proof absent |
| `odds-api-io::volleyball::EVENT_DISCOVERY::default` | LICENSED_OR_OFFICIAL_API | ACTIVE_REACHABLE | no preserved current proof | 0 | G1 PASS; G4 NOT_EXECUTED; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 NOT_EXECUTED; G12 PASS | IMPLEMENTED_UNVERIFIED | current discovery proof missing |
| `tennis-abstract::tennis::EVENT_AND_ENRICHMENT::default` | STATIC_HTML | ACTIVE_REACHABLE | E3 `cmd-live-006` = 5 matches | 0 | G1 PASS; G4 PASS; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 PARTIAL; G12 PASS | LIVE_PARTIAL | no retained raw evidence, replay, or idempotent rerun proof |
| `sackmann::tennis::HISTORICAL_DATASET::atp` | LOCAL_OR_OPEN_DATASET | ACTIVE_REACHABLE | E3 `cmd-live-009` = HTTP 200 | 3 | G1 PASS; G4 PASS; G7 PARTIAL; G8 NOT_APPLICABLE; G10 PASS; G12 PASS | LIVE_PARTIAL | current revision reachable but checksum/replay evidence absent |
| `sackmann::tennis::HISTORICAL_DATASET::wta` | LOCAL_OR_OPEN_DATASET | ACTIVE_REACHABLE | no preserved current proof | 0 | G1 PASS; G4 NOT_EXECUTED; G7 NOT_EXECUTED; G8 NOT_APPLICABLE; G10 NOT_EXECUTED; G12 PASS | IMPLEMENTED_UNVERIFIED | WTA variant lacked current proof and direct test |
| `espn-tennis::tennis::ENRICHMENT_ONLY::default` | DOCUMENTED_PUBLIC_API | ACTIVE_REACHABLE | no preserved current proof | 0 | G1 PASS; G4 NOT_EXECUTED; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 NOT_EXECUTED; G12 PASS | IMPLEMENTED_UNVERIFIED | no direct deterministic or current proof |
| `flashscore-tennis::tennis::ENRICHMENT_ONLY::default` | PUBLIC_XHR_OR_JSON | ACTIVE_REACHABLE | no preserved current proof | 21 | G1 PASS; G4 PARTIAL; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 PASS; G12 PASS | DETERMINISTIC_ONLY | parser tests exist; current proof absent |
| `odds-api-io::tennis::EVENT_DISCOVERY::default` | LICENSED_OR_OFFICIAL_API | ACTIVE_REACHABLE | no preserved current proof | 0 | G1 PASS; G4 NOT_EXECUTED; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 NOT_EXECUTED; G12 PASS | IMPLEMENTED_UNVERIFIED | current discovery proof missing |
| `api-hockey::hockey::EVENT_AND_ENRICHMENT::default` | LICENSED_OR_OFFICIAL_API | ACTIVE_REACHABLE | E3 current live proof refreshed 2026-06-12: `2026-06-11` valid empty and `2026-06-12` returned 3 fixtures; retained bundle `2f746c13aa9c91f880fe89a6911efddef5cf1949298558ddd39174b1fa9d1f53`; replay and duplicate-free rerun passed on disposable DB; enrichment: team fixtures SUCCESS bundle `fe495768`, fixture stats UPSTREAM_ERROR (plan-restricted) | 11 | G1 PASS; G4 PARTIAL; G7 PASS; G8 PASS; G10 PASS; G12 PASS | LIVE_PARTIAL | provider plan restricts fixture stats endpoint; team fixtures works; historical-date plan restriction remains distinct |
| `nhl-api::hockey::ENRICHMENT_ONLY::default` | DOCUMENTED_PUBLIC_API | ACTIVE_REACHABLE | no preserved current proof | 3 | G1 PASS; G4 PARTIAL; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 PASS; G12 PASS | DETERMINISTIC_ONLY | direct source tests exist; current proof absent |
| `espn-hockey::hockey::ENRICHMENT_ONLY::default` | DOCUMENTED_PUBLIC_API | ACTIVE_REACHABLE | no preserved current proof | 13 | G1 PASS; G4 PARTIAL; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 PASS; G12 PASS | DETERMINISTIC_ONLY | direct source tests exist; current proof absent |
| `flashscore-hockey::hockey::ENRICHMENT_ONLY::default` | PUBLIC_XHR_OR_JSON | ACTIVE_REACHABLE | no preserved current proof | 21 | G1 PASS; G4 PARTIAL; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 PASS; G12 PASS | DETERMINISTIC_ONLY | parser tests exist; current proof absent |
| `hockey-reference::hockey::HISTORICAL_DATASET::default` | STATIC_HTML | ACTIVE_REACHABLE | no preserved current proof | 2 | G1 PASS; G4 PARTIAL; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 PASS; G12 PASS | DETERMINISTIC_ONLY | direct source tests exist; current dataset proof absent |
| `moneypuck::hockey::ENRICHMENT_ONLY::default` | DOCUMENTED_PUBLIC_API | ACTIVE_REACHABLE | no preserved current proof | 0 | G1 PASS; G4 NOT_EXECUTED; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 NOT_EXECUTED; G12 PASS | IMPLEMENTED_UNVERIFIED | no direct deterministic or current proof |
| `scrapernhl::hockey::ENRICHMENT_ONLY::default` | DOCUMENTED_PUBLIC_API | ACTIVE_REACHABLE | no preserved current proof | 0 | G1 PASS; G4 NOT_EXECUTED; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 NOT_EXECUTED; G12 PASS | IMPLEMENTED_UNVERIFIED | no direct deterministic or current proof |
| `odds-api-io::hockey::EVENT_DISCOVERY::default` | LICENSED_OR_OFFICIAL_API | ACTIVE_REACHABLE | no preserved current proof | 0 | G1 PASS; G4 NOT_EXECUTED; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 NOT_EXECUTED; G12 PASS | IMPLEMENTED_UNVERIFIED | current discovery proof missing |
| `hltv::cs2::EVENT_AND_ENRICHMENT::default` | BROWSER_AUTOMATION | ACTIVE_REACHABLE | no permitted repeatable current proof executed | 0 | G1 PASS; G4 NOT_EXECUTED; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 NOT_EXECUTED; G12 PASS | IMPLEMENTED_UNVERIFIED | browser automation required; repeatable proof absent |
| `bo3gg::cs2::EVENT_AND_ENRICHMENT::default` | BROWSER_AUTOMATION | ACTIVE_REACHABLE | no permitted repeatable current proof executed | 0 | G1 PASS; G4 NOT_EXECUTED; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 NOT_EXECUTED; G12 PASS | IMPLEMENTED_UNVERIFIED | access method originally misclassified; browser proof absent |
| `gosugamers::cs2::EVENT_DISCOVERY::default` | STATIC_HTML | ACTIVE_REACHABLE | no preserved current proof | 0 | G1 PASS; G4 NOT_EXECUTED; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 NOT_EXECUTED; G12 PASS | IMPLEMENTED_UNVERIFIED | no direct deterministic or current proof |
| `odds-api-io::cs2::EVENT_DISCOVERY::esports` | LICENSED_OR_OFFICIAL_API | ACTIVE_REACHABLE | no preserved current proof | 0 | G1 PASS; G4 NOT_EXECUTED; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 NOT_EXECUTED; G12 PASS | IMPLEMENTED_UNVERIFIED | current discovery proof missing |
| `opendota::dota2::EVENT_AND_ENRICHMENT::default` | DOCUMENTED_PUBLIC_API | ACTIVE_REACHABLE | E3 `cmd-live-007` = 5 matches | 0 | G1 PASS; G4 PASS; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 PARTIAL; G12 PASS | LIVE_PARTIAL | no retained raw evidence, replay, or idempotent rerun proof |
| `gosugamers::dota2::EVENT_DISCOVERY::default` | STATIC_HTML | ACTIVE_REACHABLE | no preserved current proof | 0 | G1 PASS; G4 NOT_EXECUTED; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 NOT_EXECUTED; G12 PASS | IMPLEMENTED_UNVERIFIED | no direct deterministic or current proof |
| `odds-api-io::dota2::EVENT_DISCOVERY::esports` | LICENSED_OR_OFFICIAL_API | ACTIVE_REACHABLE | no preserved current proof | 0 | G1 PASS; G4 NOT_EXECUTED; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 NOT_EXECUTED; G12 PASS | IMPLEMENTED_UNVERIFIED | current discovery proof missing |
| `vlr::valorant::EVENT_AND_ENRICHMENT::default` | STATIC_HTML | ACTIVE_REACHABLE | E3 `cmd-live-008` = 50 matches | 0 | G1 PASS; G4 PASS; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 PARTIAL; G12 PASS | LIVE_PARTIAL | no retained raw evidence, replay, or idempotent rerun proof |
| `bo3gg::valorant::EVENT_AND_ENRICHMENT::default` | BROWSER_AUTOMATION | ACTIVE_REACHABLE | no permitted repeatable current proof executed | 0 | G1 PASS; G4 NOT_EXECUTED; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 NOT_EXECUTED; G12 PASS | IMPLEMENTED_UNVERIFIED | access method originally misclassified; browser proof absent |
| `gosugamers::valorant::EVENT_DISCOVERY::default` | STATIC_HTML | ACTIVE_REACHABLE | no preserved current proof | 0 | G1 PASS; G4 NOT_EXECUTED; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 NOT_EXECUTED; G12 PASS | IMPLEMENTED_UNVERIFIED | no direct deterministic or current proof |
| `odds-api-io::valorant::EVENT_DISCOVERY::esports` | LICENSED_OR_OFFICIAL_API | ACTIVE_REACHABLE | no preserved current proof | 0 | G1 PASS; G4 NOT_EXECUTED; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 NOT_EXECUTED; G12 PASS | IMPLEMENTED_UNVERIFIED | current discovery proof missing |

---

## Corrected classification notes

1. Only `espn-football::football::ENRICHMENT_ONLY::default` achieved `PRODUCTION_READY` after REM-002A direct proof; every other integration still lacks complete `E4_CURRENT_REPLAY_RERUN` evidence.
2. `api-hockey` was corrected from a broken/off-season narrative to `LIVE_PARTIAL` after live reassessment showed valid-empty current-date behavior plus working nearby dates.
3. `bo3gg` was corrected from `STATIC_HTML` to `BROWSER_AUTOMATION` based on `_get_rendered(...)` usage in the active code path.
4. `betclic`, `hltv`, and both `bo3gg` integrations retain non-certifying browser status unless repeatable permitted proof is captured.
5. REM-002B closure now has strict live-test separation plus 11 direct deterministic API-Sports contract tests, 4 live certification tests, replay/rerun artifact proof in `.kilo/artifacts/rem002b_api_sports_summary.json`, and typed discovery wiring for all four family members including `api-basketball`.
6. REM-002C enrichment assessment (2026-06-12) confirmed: api-football enrichment fully functional; api-basketball, api-volleyball, api-hockey have provider-plan restrictions on enrichment endpoints (team fixtures works for volleyball/hockey; stats endpoints blocked).
