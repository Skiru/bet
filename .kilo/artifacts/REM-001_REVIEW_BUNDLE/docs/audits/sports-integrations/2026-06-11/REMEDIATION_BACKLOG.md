# Remediation Backlog (Reconciled)

**Audit Run:** SPORTS-AUDIT-20260611T093602Z-b6a3ced  
**Reconciled:** 2026-06-11T11:24:19Z

---

## Priority Order

Items are ordered by contract severity, then risk reduction, then information gain.

---

## Item: REM-001

### espn-football live NameError fix

| Field | Value |
|---|---|
| **Item ID** | REM-001 |
| **Integration Key** | `espn-football::football::ENRICHMENT_ONLY::default` |
| **Severity** | RESOLVED-HIGH |
| **Status** | REPAIRED — direct `get_fixtures()` NameError removed; recertified from `LIVE_BROKEN` to `LIVE_PARTIAL` |
| **Defect** | `_request()` in `src/bet/api_clients/espn.py` called `json.loads(...)` without importing `json`; the same slice also fabricated empty fixture identities and coerced missing values to zero in direct/fallback flows. |
| **Evidence IDs** | `cmd-live-003`, `cmd-rem001-001`, `cmd-rem001-003`, `ev-rem001-001`, `ev-rem001-003` |
| **Affected Capabilities** | football fixture lookup, fallback enrichment, source observation ingestion |
| **Affected Consumers** | `bet.stats.fetcher.StatFetcher`, football fallback chain |
| **Smallest Safe Repair** | import `json`; reject fixtures without provider event IDs; preserve missing stat values as missing in both direct parsing and fallback aggregation; add deterministic + live replay/idempotency coverage |
| **Required Live Proof** | satisfied via `tests/scrapers/test_espn_football_live.py` using ESPN football `eng.1` event `740968` plus disposable-DB fallback replay |
| **Acceptance Gates** | `G1 PASS`, `G4 PASS`, `G7 PASS`, `G8 PASS`, `G10 PASS`, `G12 PASS`; still below contract `PASS` because fallback team resolution is names-based and `team_form` does not persist source event IDs |
| **Dependencies** | none |
| **Complexity** | S |
| **Recommended Reasoning** | high |
| **Follow-up** | production-readiness work should address provider-ID resolution ambiguity and evidence/source-ID linkage in the persisted enrichment projection |

---

## Item: REM-002

### Portfolio-wide E4 evidence/replay/rerun gap

| Field | Value |
|---|---|
| **Item ID** | REM-002 |
| **Integration Key** | multiple current-live integrations |
| **Severity** | HIGH |
| **Defect** | No integration had retained raw evidence, deterministic no-network replay, or idempotent rerun proof sufficient for `E4_CURRENT_REPLAY_RERUN`; this invalidated every original `PRODUCTION_READY` claim. |
| **Evidence IDs** | corrected matrix + corrected manifest gate summaries |
| **Affected Capabilities** | readiness certification, replay safety, provenance, persistence verification |
| **Affected Consumers** | all production-readiness decisions; especially `api-football`, `api-basketball`, `api-volleyball`, `api-hockey`, `tennis-abstract`, `sackmann::atp`, `opendota`, `vlr` |
| **Smallest Safe Repair** | add sanitized raw-evidence retention and deterministic replay harness for one current-live integration first, then extend to the remaining live integrations |
| **Required Live Proof** | one current live capture + one no-network replay + one idempotent rerun where persistence applies |
| **Acceptance Gates** | `G7`, `G8`, `G10`, `G11`, `G12` |
| **Dependencies** | none |
| **Complexity** | L |
| **Recommended Reasoning** | high |

---

## Item: REM-003

### Missing current proof for odds-api-io discovery portfolio

| Field | Value |
|---|---|
| **Item ID** | REM-003 |
| **Integration Key** | `odds-api-io::*::EVENT_DISCOVERY::*` (8 rows) |
| **Severity** | MEDIUM |
| **Defect** | Eight atomic discovery integrations were claimed as production-ready/source-ready in the original audit without preserved role-appropriate current proof. |
| **Evidence IDs** | corrected matrix; corrected manifest inventory |
| **Affected Capabilities** | event discovery across football, basketball, volleyball, tennis, hockey, cs2, dota2, valorant |
| **Affected Consumers** | `EventDiscoveryCoordinator` primary discovery path |
| **Smallest Safe Repair** | execute one deterministic current discovery proof per sport/variant with evidence retention and source identity capture |
| **Required Live Proof** | one date/window-scoped discovery request per audited `odds-api-io` integration key |
| **Acceptance Gates** | `G1`, `G2`, `G4`, `G6`, `G7`, `G10`, `G12` |
| **Dependencies** | REM-002 recommended before any renewed production-ready claim |
| **Complexity** | M |
| **Recommended Reasoning** | high |

---

## Item: REM-004

### Browser-integration proof gap and access-method correction

| Field | Value |
|---|---|
| **Item ID** | REM-004 |
| **Integration Key** | `betclic::football::ODDS_ONLY::default`, `hltv::cs2::EVENT_AND_ENRICHMENT::default`, `bo3gg::cs2::EVENT_AND_ENRICHMENT::default`, `bo3gg::valorant::EVENT_AND_ENRICHMENT::default` |
| **Severity** | MEDIUM |
| **Defect** | Browser integrations remained `NOT_EXECUTED`; `bo3gg` was also misclassified as `STATIC_HTML` despite active `_get_rendered(...)` browser dependence. |
| **Evidence IDs** | `ev-rcl-002`, `ev-rcl-003`, corrected matrix |
| **Affected Capabilities** | CS2/Valorant team stats and H2H; football odds proof |
| **Affected Consumers** | esports enrichment flows; odds verification flows |
| **Smallest Safe Repair** | first correct access-method metadata and proof policy, then add one permitted repeatable proof strategy or explicitly freeze these integrations below certification states |
| **Required Live Proof** | repeatable sanitized browser proof or sanctioned alternative non-browser proof where allowed |
| **Acceptance Gates** | `G1`, `G4`, `G7`, `G9`, `G10`, `G12` |
| **Dependencies** | REM-002 recommended for replay/evidence framework |
| **Complexity** | M |
| **Recommended Reasoning** | high |

---

## Item: REM-005

### Direct deterministic source-test gap for 29 integrations

| Field | Value |
|---|---|
| **Item ID** | REM-005 |
| **Integration Key** | 29 uncovered keys listed in `AUDIT_RECONCILIATION.md` |
| **Severity** | MEDIUM |
| **Defect** | 186 deterministic tests exist, but 29/45 integration keys still have no direct source-specific deterministic proof. Shared sport-level and persistence tests do not replace source-level verification. |
| **Evidence IDs** | `cmd-rcl-001`, `ev-rcl-005`, `AUDIT_RECONCILIATION.md` |
| **Affected Capabilities** | source adapters, live-path parser semantics, source-specific failure isolation |
| **Affected Consumers** | all portfolio consumers that rely on unproven sources |
| **Smallest Safe Repair** | add focused source-specific golden/mock tests first for all current-live integrations lacking direct coverage, then for remaining discovery-only and historical integrations |
| **Required Live Proof** | none for deterministic test addition itself; live proof remains separate |
| **Acceptance Gates** | `G4`, `G5`, `G10` |
| **Dependencies** | none |
| **Complexity** | L |
| **Recommended Reasoning** | high |

---

## Summary

| Severity | Count |
|---|---:|
| CRITICAL | 0 |
| HIGH | 1 |
| MEDIUM | 3 |
| LOW | 0 |
| **Total** | **4** |

---

## First Repair Recommendation

**REM-002: Portfolio-wide E4 evidence/replay/rerun gap**

- **Risk Reduction:** HIGH — still blocks every production-ready claim after REM-001 repair
- **Information Gain:** HIGH — adds the missing replay/rerun contract evidence to current-live integrations
- **Complexity:** L
- **Reasoning Level:** high
*** Add File: /Users/mkoziol/projects/bet/docs/audits/sports-integrations/2026-06-11/repairs/REM-001_ESPN_FOOTBALL.md
# REM-001 — ESPN Football

## Target
- Source: `espn-football`
- Integration key: `espn-football::football::ENRICHMENT_ONLY::default`
- Role: `ENRICHMENT_ONLY`
- Branch / worktree: `main` @ `/Users/mkoziol/projects/bet`
- Audited failure input: `.venv/bin/python3 -c "from bet.api_clients import get_client, RateLimiter; rl = RateLimiter(); client = get_client('espn-football', rl); fixtures = client.get_fixtures('2026-06-11'); print(len(fixtures))"`
- Registered entry point: `CLIENT_REGISTRY["espn-football"] -> _espn_factory("football", "eng.1") -> ESPNClient`
- Direct client path: `get_client("espn-football") -> ESPNClient.get_fixtures() -> ESPNClient._request() -> wrap_request() -> json.loads(...)`
- Football fallback orchestration path: `enrich_fixtures() -> _enrich_team() -> _try_api_fetch() -> _try_espn_fetch() -> ESPNClient.resolve_team_id() / get_team_last_fixtures() / get_fixture_stats()`

## Root cause
`src/bet/api_clients/espn.py` used `json.loads(response.text)` inside `_request()` without importing `json`.

Additional verified defects in the same slice:
- `get_fixtures()` accepted events with missing provider IDs.
- `_parse_flat_stats()` converted blank/unparseable values to `0.0`.
- `bet.stats.enrichment._try_espn_fetch()` converted missing side values to `0` during aggregation.

## Exact changed files
- `src/bet/api_clients/espn.py` — import fix, fixture identity guard, missing-value preservation.
- `src/bet/stats/enrichment.py` — fallback aggregation no longer converts missing values to zero.
- `pyproject.toml` — registered `espn_live` marker.
- `tests/scrapers/test_espn_client.py` — deterministic regression coverage.
- `tests/scrapers/test_espn_football_live.py` — live proof, offline replay, idempotent rerun.
- `docs/audits/sports-integrations/2026-06-11/INTEGRATION_MATRIX.md` — espn-football recertification row.
- `docs/audits/sports-integrations/2026-06-11/EVIDENCE_MANIFEST.json` — espn-football evidence updates.
- `docs/audits/sports-integrations/2026-06-11/REMEDIATION_BACKLOG.md` — REM-001 status update.

## Before / after failure evidence
### Before
- `cmd-live-003` (`2026-06-11T10:10:00Z`): `espn-football get_fixtures(2026-06-11)`
- Failure: `NameError: name 'json' is not defined`
- Reproduced pre-fix in this run from `_request("/scoreboard", params={"dates": "20260611"})`
- Exception class: `NameError`
- Stack anchor: `src/bet/api_clients/espn.py:428`
- Failure location: direct client path; fallback path shared the same broken `_request()` primitive and silently failed closed through `resolve_team_id()` / `get_team_last_fixtures()`

### After
- `cmd-rem001-001` (`2026-06-11T12:07:06Z`): reran audited input
- Result: `0 fixtures; no NameError`
- Same executed code path completed successfully and returned valid empty data for `eng.1` on `2026-06-11`

## Deterministic test commands and outcomes
- `env PYTHONPATH=src:scripts .venv/bin/python3 -m pytest tests/scrapers/test_espn.py tests/scrapers/test_espn_client.py tests/test_fuzzy_match.py -q`
  - Outcome: `27 passed`
- `env PYTHONPATH=src:scripts .venv/bin/python3 -m ruff check tests/scrapers/test_espn_client.py tests/scrapers/test_espn_football_live.py`
  - Outcome: `All checks passed!`

Deterministic regression coverage added:
- exact former `get_fixtures()` path,
- valid empty response,
- malformed JSON,
- non-success HTTP response,
- no fabricated fixture identity,
- no missing-value-to-zero conversion,
- fallback orchestration idempotency.

## Direct live proof
- Command: `env BET_RUN_LIVE_ESPN=1 PYTHONPATH=src:scripts .venv/bin/python3 -m pytest tests/scrapers/test_espn_football_live.py -q`
- Outcome: `1 passed`
- Primary live request: `ESPNClient(sport="football", league="eng.1").get_fixtures("2026-05-24")`
- Real source event ID: `740968`
- Source participants: `Crystal Palace` vs `Arsenal`
- Scheduled time: `2026-05-24T15:00Z`
- Competition: normalized result currently emits `2025-26-english-premier-league`
- HTTP outcome: `200`
- Scoreboard evidence hash: `b86db235acc74f3885c44337f3d8351918e01a4edf3e16c38c71b4cb59292478`
- Evidence summary: `.kilo/artifacts/rem001_espn_football/live_summary.json`

## Fallback proof
- Real application path invoked: `enrich_fixtures()` on a disposable SQLite DB
- Seeded canonical fixture for fallback proof: `Arsenal` vs `Liverpool`, competition `Premier League`
- Result: `fetched=2`, `failed=0`
- Orchestration accepted the returned contract and persisted `20` logical `team_form` rows
- Recorded fallback evidence hashes include:
  - `/teams` → `fbf75ac0612ea96c38d7576bf04c5b6e37d1ab8a70251a0f5c5e6a153103faa5`
  - `/teams/359/schedule` → `32201301819ec7c191bfbb0036bffbd9dd6f7e865f90915ef877f0ad85b8596a`
  - `/teams/364/schedule` → `01bd58b791788b927cda9ff95c54afd9cf13fe3c898f079f3ade8f328d2a5ece`
- Source identity preserved in direct client/live evidence, but **not persisted** in the `team_form` projection. This remains a contract limitation.
- Names-only matching is still present in `resolve_team_id()`. No ambiguous live case was promoted to success in this run.

## Replay and idempotency
- Sanitized raw evidence retained under `.kilo/artifacts/rem001_espn_football/`
- Offline replay ran with outbound network disabled by replaying recorded ESPN responses
- Replay result: semantic normalized output matched the live result (`semantic_match_live=true`)
- First replay persistence count: `20` logical `team_form` rows
- Second replay persistence count: `20` logical `team_form` rows
- Duplicate assertion: zero new logical duplicates on the second identical run

## Gate table
| Gate | Status | Evidence |
|---|---|---|
| 1. Real live response fetched | PASS | `cmd-rem001-003`, scoreboard hash `b86db235...` |
| 2. Real source event ID validated | PASS | event `740968` captured in live proof |
| 3. Event matching deterministic / not ambiguous | FAIL | fallback still resolves provider teams by fuzzy provider name |
| 4. Discovery not via participant-profile lookup | PASS | direct proof used `/scoreboard` |
| 5. Capability statuses distinguish empty / unsupported / parse failure | FAIL | client API still returns list/empty-list semantics rather than explicit status taxonomy |
| 6. No missing value converted to zero | PASS | deterministic tests in `tests/scrapers/test_espn_client.py` |
| 7. Current/future events absent from recent form/H2H | PASS | `get_team_last_fixtures()` filters through `_is_game_finished()` |
| 8. No post-cutoff observation enters analysis snapshot | N/A | no snapshot/cutoff projection in this integration slice |
| 9. Predicted vs confirmed lineups separated | N/A | not in scope for this repair |
| 10. Historical membership event-effective | N/A | not in scope for this repair |
| 11. Every persisted observation references retained evidence | FAIL | `team_form` rows do not store evidence/source-event linkage |
| 12. Offline replay deterministic | PASS | live replay summary `semantic_match_live=true` |
| 13. Identical second run creates zero duplicates | PASS | `20 -> 20` rows on second replay run |
| 14. One capability failure preserves successful results | PASS | deterministic fallback test kept successful stats when one fixture returned empty |
| 15. Live tests separate from deterministic CI | PASS | `espn_live` marker + `BET_RUN_LIVE_ESPN=1` opt-in |
| 16. Secrets absent from logs/evidence/diff | PASS | only public ESPN endpoints and sanitized JSON retained |
| 17. All changed deterministic tests pass | PASS | `27 passed` |
| 18. Final diff contains no unrelated refactor | PASS | changes limited to espn-football slice, tests, and audit artifacts |

## Remaining limitations
- `resolve_team_id()` still depends on provider-side fuzzy name matching.
- Persisted `team_form` enrichment output does not retain source fixture IDs or evidence references.
- Client capability APIs still encode several failure classes as `[]` rather than explicit capability statuses.

## Final state
- Matrix state: `LIVE_PARTIAL`
- Contract verdict: `FAIL`
- Rationale: the audited `NameError` is repaired and replay/rerun evidence now exists, but core contract gaps remain around deterministic provider-ID resolution and persisted evidence/source-ID linkage.
