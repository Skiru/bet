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
| LIVE_PARTIAL | 9 |
| LIVE_BROKEN | 0 |
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
| `api-football::football::EVENT_AND_ENRICHMENT::default` | LICENSED_OR_OFFICIAL_API | ACTIVE_REACHABLE | E3 `cmd-live-001` = 98 fixtures | 0 | G1 PASS; G4 PASS; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 PARTIAL; G12 PASS | LIVE_PARTIAL | no retained raw evidence, replay, or idempotent rerun proof |
| `odds-api-io::football::EVENT_DISCOVERY::default` | LICENSED_OR_OFFICIAL_API | ACTIVE_REACHABLE | no preserved current proof | 0 | G1 PASS; G4 NOT_EXECUTED; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 NOT_EXECUTED; G12 PASS | IMPLEMENTED_UNVERIFIED | current discovery proof missing |
| `odds-api::football::EVENT_DISCOVERY::default` | LICENSED_OR_OFFICIAL_API | ACTIVE_REACHABLE | no preserved current proof | 0 | G1 PASS; G4 NOT_EXECUTED; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 NOT_EXECUTED; G12 PASS | IMPLEMENTED_UNVERIFIED | current discovery proof missing |
| `espn-football::football::ENRICHMENT_ONLY::default` | DOCUMENTED_PUBLIC_API | ACTIVE_REACHABLE | E4 `cmd-rem001-003` live proof: 10 fixtures on `2026-05-24`, validated event `740968`; `cmd-rem001-001` audited date now valid-empty without NameError | 19 | G1 PASS; G4 PASS; G7 PASS; G8 PASS; G10 PASS; G12 PASS | LIVE_PARTIAL | fallback team resolution remains provider-name-based; `team_form` projection does not persist source event IDs |
| `flashscore-football::football::ENRICHMENT_ONLY::default` | PUBLIC_XHR_OR_JSON | ACTIVE_REACHABLE | no preserved current proof | 21 | G1 PASS; G4 PARTIAL; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 PASS; G12 PASS | DETERMINISTIC_ONLY | parser tests exist; current proof absent |
| `fbref::football::HISTORICAL_DATASET::default` | STATIC_HTML | ACTIVE_REACHABLE | no preserved current proof | 0 | G1 PASS; G4 NOT_EXECUTED; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 NOT_EXECUTED; G12 PASS | IMPLEMENTED_UNVERIFIED | no variant-specific deterministic or current dataset proof |
| `understat::football::ENRICHMENT_ONLY::default` | PUBLIC_XHR_OR_JSON | ACTIVE_REACHABLE | no preserved current proof | 0 | G1 PASS; G4 NOT_EXECUTED; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 NOT_EXECUTED; G12 PASS | IMPLEMENTED_UNVERIFIED | no direct deterministic or current proof |
| `football-data-org::football::EVENT_DISCOVERY::default` | LICENSED_OR_OFFICIAL_API | ACTIVE_REACHABLE | no preserved current proof | 0 | G1 PASS; G4 NOT_EXECUTED; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 NOT_EXECUTED; G12 PASS | IMPLEMENTED_UNVERIFIED | no direct deterministic or current proof |
| `betclic::football::ODDS_ONLY::default` | BROWSER_AUTOMATION | ACTIVE_REACHABLE | no permitted repeatable current proof executed | 1 | G1 PASS; G4 PARTIAL; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 PASS; G12 PASS | DETERMINISTIC_ONLY | browser-required odds proof not executed |
| `api-basketball::basketball::EVENT_AND_ENRICHMENT::default` | LICENSED_OR_OFFICIAL_API | ACTIVE_REACHABLE | E3 `cmd-live-002` = 31 fixtures | 0 | G1 PASS; G4 PASS; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 PARTIAL; G12 PASS | LIVE_PARTIAL | no retained raw evidence, replay, or idempotent rerun proof |
| `nba-api::basketball::ENRICHMENT_ONLY::default` | DOCUMENTED_PUBLIC_API | ACTIVE_REACHABLE | no preserved current proof | 2 | G1 PASS; G4 PARTIAL; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 PASS; G12 PASS | DETERMINISTIC_ONLY | direct source tests exist; current proof absent |
| `espn-basketball::basketball::ENRICHMENT_ONLY::default` | DOCUMENTED_PUBLIC_API | ACTIVE_REACHABLE | no preserved current proof | 13 | G1 PASS; G4 PARTIAL; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 PASS; G12 PASS | DETERMINISTIC_ONLY | direct source tests exist; current proof absent |
| `flashscore-basketball::basketball::ENRICHMENT_ONLY::default` | PUBLIC_XHR_OR_JSON | ACTIVE_REACHABLE | no preserved current proof | 21 | G1 PASS; G4 PARTIAL; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 PASS; G12 PASS | DETERMINISTIC_ONLY | parser tests exist; current proof absent |
| `basketball-reference::basketball::HISTORICAL_DATASET::default` | STATIC_HTML | ACTIVE_REACHABLE | no preserved current proof | 2 | G1 PASS; G4 PARTIAL; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 PASS; G12 PASS | DETERMINISTIC_ONLY | direct source tests exist; current dataset proof absent |
| `odds-api-io::basketball::EVENT_DISCOVERY::default` | LICENSED_OR_OFFICIAL_API | ACTIVE_REACHABLE | no preserved current proof | 0 | G1 PASS; G4 NOT_EXECUTED; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 NOT_EXECUTED; G12 PASS | IMPLEMENTED_UNVERIFIED | current discovery proof missing |
| `api-volleyball::volleyball::EVENT_AND_ENRICHMENT::default` | LICENSED_OR_OFFICIAL_API | ACTIVE_REACHABLE | E3 `cmd-live-004` = 6 fixtures | 0 | G1 PASS; G4 PASS; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 PARTIAL; G12 PASS | LIVE_PARTIAL | no retained raw evidence, replay, or idempotent rerun proof |
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
| `api-hockey::hockey::EVENT_AND_ENRICHMENT::default` | LICENSED_OR_OFFICIAL_API | ACTIVE_REACHABLE | E3 `cmd-rcl-004` current window returned fixtures; `2026-06-11` valid empty | 0 | G1 PASS; G4 PASS; G7 NOT_EXECUTED; G8 NOT_EXECUTED; G10 PARTIAL; G12 PASS | LIVE_PARTIAL | no retained raw evidence, replay, or idempotent rerun proof |
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

1. No integration achieved `PRODUCTION_READY` because none had complete `E4_CURRENT_REPLAY_RERUN` proof.
2. `api-hockey` was corrected from a broken/off-season narrative to `LIVE_PARTIAL` after live reassessment showed valid-empty current-date behavior plus working nearby dates.
3. `bo3gg` was corrected from `STATIC_HTML` to `BROWSER_AUTOMATION` based on `_get_rendered(...)` usage in the active code path.
4. `betclic`, `hltv`, and both `bo3gg` integrations retain non-certifying browser status unless repeatable permitted proof is captured.
