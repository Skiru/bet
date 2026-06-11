# Audit Reconciliation

**Audit Run:** SPORTS-AUDIT-20260611T093602Z-b6a3ced  
**Reconciled:** 2026-06-11T11:24:19Z  
**Mode:** read-only audit reconciliation; no production code changes

---

## 1. Scope and governing rule

This reconciliation supersedes inconsistent readiness/count claims in the original audit artifacts. Production code was not modified. The authoritative corrected state is the combination of:

- `AUDIT_RECONCILIATION.md`
- corrected `INTEGRATION_MATRIX.md`
- corrected `EVIDENCE_MANIFEST.json`
- corrected `REMEDIATION_BACKLOG.md`

The original `PORTFOLIO_AUDIT.md` and `AUDIT_COMMANDS.md` were preserved; exact worktree delta is available via git diff.

---

## 2. Reconciled inventory: all 45 integration keys

### Football (9)
1. `api-football::football::EVENT_AND_ENRICHMENT::default`
2. `odds-api-io::football::EVENT_DISCOVERY::default`
3. `odds-api::football::EVENT_DISCOVERY::default`
4. `espn-football::football::ENRICHMENT_ONLY::default`
5. `flashscore-football::football::ENRICHMENT_ONLY::default`
6. `fbref::football::HISTORICAL_DATASET::default`
7. `understat::football::ENRICHMENT_ONLY::default`
8. `football-data-org::football::EVENT_DISCOVERY::default`
9. `betclic::football::ODDS_ONLY::default`

### Basketball (6)
10. `api-basketball::basketball::EVENT_AND_ENRICHMENT::default`
11. `nba-api::basketball::ENRICHMENT_ONLY::default`
12. `espn-basketball::basketball::ENRICHMENT_ONLY::default`
13. `flashscore-basketball::basketball::ENRICHMENT_ONLY::default`
14. `basketball-reference::basketball::HISTORICAL_DATASET::default`
15. `odds-api-io::basketball::EVENT_DISCOVERY::default`

### Volleyball (5)
16. `api-volleyball::volleyball::EVENT_AND_ENRICHMENT::default`
17. `espn-volleyball::volleyball::ENRICHMENT_ONLY::default`
18. `flashscore-volleyball::volleyball::ENRICHMENT_ONLY::default`
19. `volleybox::volleyball::HISTORICAL_DATASET::default`
20. `odds-api-io::volleyball::EVENT_DISCOVERY::default`

### Tennis (6)
21. `tennis-abstract::tennis::EVENT_AND_ENRICHMENT::default`
22. `sackmann::tennis::HISTORICAL_DATASET::atp`
23. `sackmann::tennis::HISTORICAL_DATASET::wta`
24. `espn-tennis::tennis::ENRICHMENT_ONLY::default`
25. `flashscore-tennis::tennis::ENRICHMENT_ONLY::default`
26. `odds-api-io::tennis::EVENT_DISCOVERY::default`

### Hockey (8)
27. `api-hockey::hockey::EVENT_AND_ENRICHMENT::default`
28. `nhl-api::hockey::ENRICHMENT_ONLY::default`
29. `espn-hockey::hockey::ENRICHMENT_ONLY::default`
30. `flashscore-hockey::hockey::ENRICHMENT_ONLY::default`
31. `hockey-reference::hockey::HISTORICAL_DATASET::default`
32. `moneypuck::hockey::ENRICHMENT_ONLY::default`
33. `scrapernhl::hockey::ENRICHMENT_ONLY::default`
34. `odds-api-io::hockey::EVENT_DISCOVERY::default`

### CS2 (4)
35. `hltv::cs2::EVENT_AND_ENRICHMENT::default`
36. `bo3gg::cs2::EVENT_AND_ENRICHMENT::default`
37. `gosugamers::cs2::EVENT_DISCOVERY::default`
38. `odds-api-io::cs2::EVENT_DISCOVERY::esports`

### Dota 2 (3)
39. `opendota::dota2::EVENT_AND_ENRICHMENT::default`
40. `gosugamers::dota2::EVENT_DISCOVERY::default`
41. `odds-api-io::dota2::EVENT_DISCOVERY::esports`

### Valorant (4)
42. `vlr::valorant::EVENT_AND_ENRICHMENT::default`
43. `bo3gg::valorant::EVENT_AND_ENRICHMENT::default`
44. `gosugamers::valorant::EVENT_DISCOVERY::default`
45. `odds-api-io::valorant::EVENT_DISCOVERY::esports`

Result: **45 atomic integration keys**, each assigned exactly one corrected final state in the corrected matrix.

---

## 3. Why the original state totals were 42 instead of 45

The original audit mixed atomic integration-key accounting with grouped source-family reporting.

Root causes:

1. **The matrix already contained 45 rows**, but both `PORTFOLIO_AUDIT.md` and `EVIDENCE_MANIFEST.json` still claimed 42.
2. `EVIDENCE_MANIFEST.json.resume_state.integrations_completed` and `integrations_total` were both frozen at **42**, not 45.
3. The original readiness sections grouped multiple atomic rows into single source-family bullets, for example:
   - `odds-api-io (all sports)` compressed **8** integration keys into one line;
   - `sackmann::tennis (ATP/WTA)` compressed **2** integration keys into one line;
   - `bo3gg (cs2/valorant)` compressed **2** integration keys into one line;
   - `flashscore (all sports)` compressed **5** integration keys into one family reference.
4. The original matrix summary role counts were also arithmetically inconsistent with the actual 45 inventory.

Correct conclusion: the original 42-count was a **reporting/accounting defect**, not a repository inventory defect.

---

## 4. PRODUCTION_READY reassessment

### Corrected conclusion

**Zero integrations qualify for `PRODUCTION_READY`.**

The contract requires `PRODUCTION_READY` to satisfy:

- `E4_CURRENT_REPLAY_RERUN` role-appropriate proof;
- current role-appropriate proof;
- source identity preservation;
- raw evidence retention;
- deterministic no-network replay;
- temporal correctness;
- idempotent rerun where persistence applies;
- failure isolation;
- no unresolved critical or high finding.

### Why every original PRODUCTION_READY claim failed contract review

No originally claimed production-ready integration had full `E4_CURRENT_REPLAY_RERUN` evidence. The preserved audit artifacts did **not** provide all of the following for any integration:

- sanitized raw payload retained before normalization;
- deterministic no-network replay from retained evidence;
- semantic replay comparison hash;
- idempotent rerun proof for persisting flows;
- complete gate-level evidence linking in the manifest;
- variant-specific current proof for every claimed variant.

Additional downgrades:

- `espn-football::football::ENRICHMENT_ONLY::default` has a live `NameError` and remains broken.
- `api-hockey::hockey::EVENT_AND_ENRICHMENT::default` was misclassified as broken/off-season-like; re-testing showed valid-empty current date behavior plus working nearby in-window dates.
- `sackmann::tennis::HISTORICAL_DATASET::wta` lacked variant-specific current proof in the preserved audit evidence.
- `odds-api-io::*` rows had no preserved current live proof in the audit artifacts.

Corrected portfolio rule: current-live evidence without replay/rerun proof is at most `LIVE_PARTIAL`; deterministic-only proof without current-source proof is at most `DETERMINISTIC_ONLY`.

---

## 5. Deterministic test reconciliation: all 186 tests mapped

All 186 deterministic tests were accounted for in 19 test buckets.

| Test bucket | Count | Integration keys mapped | Capability focus |
|---|---:|---|---|
| `tests/scrapers/test_espn.py` | 13 | `espn-football`, `espn-basketball`, `espn-hockey`, `espn-volleyball` | standings ingestion, team season stats, player season stats, roster, DB writes |
| `tests/scrapers/test_flashscore.py` | 21 | `flashscore-football`, `flashscore-basketball`, `flashscore-tennis`, `flashscore-hockey`, `flashscore-volleyball` | HTML/XHR parsing, entity resolution, challenge/error handling, team stats persistence |
| `tests/scrapers/tennis/test_sackmann.py` | 3 | `sackmann::tennis::HISTORICAL_DATASET::atp` | CSV loader, player season stats, player match stats |
| `tests/scrapers/volleyball/test_volleybox.py` | 2 | `volleybox::volleyball::HISTORICAL_DATASET::default` | standings/player HTML extraction, DB writes |
| `tests/scrapers/hockey/test_nhl_api.py` | 3 | `nhl-api::hockey::ENRICHMENT_ONLY::default` | standings, player leaders, fixtures |
| `tests/scrapers/hockey/test_hockey_ref.py` | 2 | `hockey-reference::hockey::HISTORICAL_DATASET::default` | team/player HTML extraction |
| `tests/scrapers/basketball/test_nba_api.py` | 2 | `nba-api::basketball::ENRICHMENT_ONLY::default` | team/player season stat ingestion |
| `tests/scrapers/basketball/test_bball_ref.py` | 2 | `basketball-reference::basketball::HISTORICAL_DATASET::default` | team/player HTML extraction |
| `tests/discovery/test_dedup.py` | 12 | shared discovery pipeline affecting `api-football`, `odds-api`, source-reference merge logic | dedup, temporal windowing, fuzzy merge safety |
| `tests/discovery/test_repository.py` | 5 | shared discovery persistence affecting discovery sources | source-id persistence, upsert semantics, FK safety |
| `tests/scrapers/test_engine.py` | 2 | shared persistence layer | sqlite/wal/foreign-key configuration |
| `tests/scrapers/test_models.py` | 2 | shared scraper models | run metadata and player season stat persistence |
| `tests/test_basketball_enrichment.py` | 14 | basketball integrations as a shared capability family | stat validation, ranges, hallucination guards, comp tiers, fuzzy match |
| `tests/test_hockey_enrichment.py` | 15 | hockey integrations as a shared capability family | stat validation, ranges, hallucination guards, comp tiers, fuzzy match |
| `tests/test_volleyball_enrichment.py` | 18 | volleyball integrations as a shared capability family | stat validation, ranges, hallucination guards, comp tiers, fuzzy match |
| `tests/test_esports_enrichment.py` | 18 | esports integrations as a shared capability family (`hltv`, `bo3gg`, `opendota`, `vlr`, `gosugamers`) | stat semantics, value ranges, hallucination guards, comp tiers, fuzzy match |
| `tests/test_db_repositories.py` | 29 | shared persistence paths across persisting integrations | repository CRUD, append/update semantics, DB integrity |
| `tests/test_stat_validation.py` | 15 | all sports/integrations using normalized stat validation | stat-key allowlists, contamination detection |
| `tests/test_fuzzy_match.py` | 8 | all integrations using canonical matching | normalization, thresholds, esports strictness |

### Integrations with no direct deterministic test coverage

Direct source-specific deterministic tests were **absent** for these integration keys:

- `api-football::football::EVENT_AND_ENRICHMENT::default`
- `odds-api-io::football::EVENT_DISCOVERY::default`
- `odds-api::football::EVENT_DISCOVERY::default`
- `fbref::football::HISTORICAL_DATASET::default`
- `understat::football::ENRICHMENT_ONLY::default`
- `football-data-org::football::EVENT_DISCOVERY::default`
- `api-basketball::basketball::EVENT_AND_ENRICHMENT::default`
- `odds-api-io::basketball::EVENT_DISCOVERY::default`
- `api-volleyball::volleyball::EVENT_AND_ENRICHMENT::default`
- `odds-api-io::volleyball::EVENT_DISCOVERY::default`
- `tennis-abstract::tennis::EVENT_AND_ENRICHMENT::default`
- `sackmann::tennis::HISTORICAL_DATASET::wta`
- `espn-tennis::tennis::ENRICHMENT_ONLY::default`
- `odds-api-io::tennis::EVENT_DISCOVERY::default`
- `api-hockey::hockey::EVENT_AND_ENRICHMENT::default`
- `moneypuck::hockey::ENRICHMENT_ONLY::default`
- `scrapernhl::hockey::ENRICHMENT_ONLY::default`
- `odds-api-io::hockey::EVENT_DISCOVERY::default`
- `hltv::cs2::EVENT_AND_ENRICHMENT::default`
- `bo3gg::cs2::EVENT_AND_ENRICHMENT::default`
- `gosugamers::cs2::EVENT_DISCOVERY::default`
- `odds-api-io::cs2::EVENT_DISCOVERY::esports`
- `opendota::dota2::EVENT_AND_ENRICHMENT::default`
- `gosugamers::dota2::EVENT_DISCOVERY::default`
- `odds-api-io::dota2::EVENT_DISCOVERY::esports`
- `vlr::valorant::EVENT_AND_ENRICHMENT::default`
- `bo3gg::valorant::EVENT_AND_ENRICHMENT::default`
- `gosugamers::valorant::EVENT_DISCOVERY::default`
- `odds-api-io::valorant::EVENT_DISCOVERY::esports`

Count: **29 / 45** integration keys have no direct deterministic source-specific test proof in the 186 audited tests.

---

## 6. api-hockey reassessment

### Re-executed observations

- `cmd-rcl-002`: `get_fixtures()` returned **0** for `2026-06-11`, **0** for `2025-01-15`, **0** for `2025-06-11`.
- `cmd-rcl-003`: raw `/games?date=2025-01-15` returned explicit access limitation: `Free plans do not have access to this date, try from 2026-06-10 to 2026-06-12.`
- `cmd-rcl-003`: raw `/games?team=1&season=2024` returned **59** rows with valid structure, proving the client/parser path works.
- `cmd-rcl-004`: `/games?date=2026-06-10` returned **2** fixtures (NHL season 2025, ECHL season 2025).
- `cmd-rcl-004`: `/games?date=2026-06-12` returned **3** fixtures (NZIHL 2026, NHL 2025, ECHL 2025).
- Returned source timezone was `UTC` for the current accessible date window.

### Correct classification

`api-hockey::hockey::EVENT_AND_ENRICHMENT::default` is **not** an implementation failure and should **not** be treated as an assumed off-season failure.

Reconciled interpretation:

- `2026-06-11` = **VALID_EMPTY** current-date query result.
- `2025-01-15` = **AUTHENTICATION / PLAN LIMITATION** for historical-date access, not parser failure.
- team/season query with 59 rows = **implementation and parser confirmed working**.
- nearby accessible dates with returned fixtures = **current live capability confirmed**.

Required distinction set by the contract:

- valid empty: **yes** (`2026-06-11`)
- query mismatch: **no evidence**
- coverage gap: **not primary finding**
- parser failure: **rejected**
- authentication limitation: **yes, for historical-date access**
- implementation failure: **rejected**

Corrected final state for `api-hockey`: **LIVE_PARTIAL**, not broken.

---

## 7. Browser integrations reassessment

Manual inspection or browser-required code presence is **diagnostic only**. It is not production certification.

Corrected browser-automation integrations:

- `betclic::football::ODDS_ONLY::default`
- `hltv::cs2::EVENT_AND_ENRICHMENT::default`
- `bo3gg::cs2::EVENT_AND_ENRICHMENT::default`
- `bo3gg::valorant::EVENT_AND_ENRICHMENT::default`

Key correction:

- `bo3gg` had been classified as `STATIC_HTML` in the original matrix.
- Code inspection shows `search_team()`, `get_team_stats()`, `get_team_map_pool()` and `get_h2h()` rely on `_get_rendered(...)` and are therefore **BROWSER_AUTOMATION**, not static HTML.

Correct handling under the contract:

- retain `NOT_EXECUTED` on current-proof/replay gates unless there is permitted repeatable proof;
- do not upgrade browser integrations from code inspection alone;
- do not treat manual page inspection as readiness evidence.

Final-state impact:

- `betclic` remains `DETERMINISTIC_ONLY` because parser/market-detection tests exist, but current repeatable source proof was not executed;
- `hltv` remains `IMPLEMENTED_UNVERIFIED`;
- both `bo3gg` integrations remain `IMPLEMENTED_UNVERIFIED`.

---

## 8. Manifest-to-matrix referential integrity findings

Corrected defects found in the preserved artifacts:

1. manifest inventory count was **42**, matrix row count was **45**;
2. matrix summary role counts were wrong;
3. matrix summary access-method counts were wrong;
4. original `PRODUCTION_READY` claims lacked manifest support for `E4_CURRENT_REPLAY_RERUN`;
5. no manifest gate-results section supported the original readiness claims;
6. `bo3gg` access method was misclassified;
7. preserved audit evidence for `sackmann::wta` current proof was missing;
8. preserved audit evidence for `odds-api-io::*` current proof was missing;
9. original manifest had no completed `test_runs`, `live_operations`, or per-integration final states.

The corrected manifest now reconciles counts, evidence IDs, test buckets, live operations, access-method classification, and final states.

---

## 9. Corrected final-state distribution

| Final State | Count |
|---|---:|
| LIVE_PARTIAL | 8 |
| LIVE_BROKEN | 1 |
| DETERMINISTIC_ONLY | 14 |
| IMPLEMENTED_UNVERIFIED | 22 |
| **Total** | **45** |

There are **0** `PRODUCTION_READY` and **0** `PRODUCTION_CANDIDATE` integrations after contract-based reconciliation.

---

## 10. Corrected remediation priority

1. `espn-football::football::ENRICHMENT_ONLY::default` live NameError (HIGH)
2. portfolio-wide E4 evidence/replay/rerun gap blocking any production-ready claim (HIGH)
3. missing current proof for the 8 `odds-api-io::*` discovery integrations (MEDIUM)
4. browser-automation proof gap for `betclic`, `hltv`, and both `bo3gg` integrations (MEDIUM)
5. direct deterministic test gap for 29 integrations, especially all currently live integrations without source-specific tests (MEDIUM)

Recommended first repair remains: **espn-football NameError fix**.

---

## 11. Reconciliation decision

The audit is now reconciled at the artifact level. No production integrations were repaired in this run.
