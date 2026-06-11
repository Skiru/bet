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
- `.venv/bin/pytest tests/ -v --tb=short` (full regression suite)
  - Outcome: `640 passed, 5 skipped` (2026-06-11T15:42:10Z)

Deterministic regression coverage added:
- exact former `get_fixtures()` path,
- valid empty response,
- malformed JSON,
- non-success HTTP response,
- no fabricated fixture identity,
- no missing-value-to-zero conversion,
- fallback orchestration idempotency.

### Test fixes (2026-06-11T15:42:10Z)
- `test_enrich_fixtures_espn_fallback_is_idempotent_and_preserves_missing_values`: Added missing `isolated_cache_dir` fixture to prevent production cache pollution; fixed mock to properly respect `exclude_event_ids` parameter using correct event ID format (`"740968"`).
- `test_enrich_fixtures_espn_skips_neither_side_and_both_side_matches`: Added missing `isolated_cache_dir` fixture; added mock for API-Sports fallback client to prevent false positives when ESPN fails.
- Ruff linting fixes: Reformatted list comprehensions, lambda functions, and monkeypatch calls in `tests/scrapers/test_espn_client.py` and `tests/scrapers/test_espn_football_live.py` for E501 compliance.

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
| 17. All changed deterministic tests pass | PASS | `640 passed, 5 skipped` (full regression suite) |
| 18. Final diff contains no unrelated refactor | PASS | changes limited to espn-football slice, tests, and audit artifacts |

## Remaining limitations
- `resolve_team_id()` still depends on provider-side fuzzy name matching.
- Persisted `team_form` enrichment output does not retain source fixture IDs or evidence references.
- Client capability APIs still encode several failure classes as `[]` rather than explicit capability statuses.

## Final state
- Matrix state: `LIVE_PARTIAL`
- Contract verdict: `FAIL`
- Rationale: the audited `NameError` is repaired and replay/rerun evidence now exists, but core contract gaps remain around deterministic provider-ID resolution and persisted evidence/source-ID linkage.
