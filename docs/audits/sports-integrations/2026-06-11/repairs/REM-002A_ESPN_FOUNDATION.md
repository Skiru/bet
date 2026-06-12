# REM-002A — ESPN Foundation

- Audit run: `SPORTS-AUDIT-20260611T093602Z-b6a3ced`
- Integration key: `espn-football::football::ENRICHMENT_ONLY::default`
- Final state: `PRODUCTION_READY`
- Branch/worktree: `main` @ `/Users/mkoziol/projects/bet`
- Baseline commit: `776fef6d69bef4480a86076b0f8424dd663ae550`
- Baseline git status: unrelated changes preserved; REM-002A production files already modified before audit closure
- Registered source key: `espn-football`
- Fallback path: `enrich_fixtures -> _try_espn_fetch -> _resolve_espn_fixture_identity -> ESPNClient.get_event_fixture_result/get_team_last_fixtures_result/get_fixture_stats_result`
- `fixture_sources` write/query: live proof inserts mapping in `tests/scrapers/test_espn_football_live.py::_seed_fixture`; enrichment queries `src/bet/stats/enrichment.py::_get_fixture_source_event_ids`
- Migration 014 already may exist in local/shared DBs: yes; semantics left immutable, runner made rerunnable at v14
- Reused runtime evidence abstraction: `src/bet/integration/evidence.py`
- Reused transport classification boundary: `src/bet/api_clients/espn.py::SourceOperationResult` / `SourceResultStatus`
- Changed production files: `src/bet/integration/evidence.py`, `src/bet/api_clients/espn.py`, `src/bet/stats/enrichment.py`, `src/bet/db/models.py`, `src/bet/db/repositories.py`, `src/bet/db/schema.py`, `src/bet/db/schema.sql`, `src/bet/discovery/repository.py`, `src/bet/discovery/models.py`
- Changed test files: `tests/scrapers/test_espn_client.py`, `tests/scrapers/test_espn_football_live.py`

## Command results

- focused deterministic: `tests/scrapers/test_espn_client.py` PASS
- shared ESPN suite: PASS
- changed-file lint/static: `ruff check --select E9,F63,F7,F82 <changed .py>` PASS; `py_compile <changed .py>` PASS
- live proof: `tests/scrapers/test_espn_football_live.py` PASS
- replay with network blocked: PASS via `build_replay_transport(...)` + socket/request sentinels
- migration coverage: `tests/scrapers/test_espn_client.py::test_migration_v14_handles_fresh_restart_partial_and_failure` PASS
- full suite: `646 passed, 5 skipped`

## Live identifiers

- canonical fixture: `1`
- canonical external id: `api-football-shadow-740968`
- ESPN event: `740968`
- provider participant ids: home `384`, away `359`
- bundle SHA-256: `32f075eb12a4a6aae53ca9e10c1e222359e45fa99a47a22b6115cb4843f3def0`

## Migration matrix

- fresh schema v14: PASS
- populated v13 -> v14: PASS
- restart after success: PASS
- partial migration with one evidence column present: PASS
- legacy rows remain readable: PASS
- fresh vs migrated schema equivalence: PASS
- injected failure preserves version 13 and reruns cleanly: PASS
- repository round-trip preserves namespaced refs + 64-char bundle hash: PASS

## Gate delta

- G3 `PARTIAL/FAIL -> PASS`: ESPN event resolved only through `fixture_sources`; zero mapping `NOT_FOUND`; multi-mapping `AMBIGUOUS`
- G5 `FAIL -> PASS`: explicit ESPN typed statuses now reach fallback path without collapsing to `[]`
- G11 `PARTIAL -> PASS`: persisted TeamForm rows reference replayable content-addressed bundle manifests and namespaced source refs
- Final-state delta: `PRODUCTION_CANDIDATE -> PRODUCTION_READY`

## Final state

- exact crosswalk resolution: PASS
- fail-closed duplicate/ambiguous identity handling: PASS
- provider-side identity and point-in-time invariants: PASS
- replayable content-addressed evidence linkage: PASS
- no-network replay + identical rerun: PASS
- audit artifacts agree: PASS
- remaining blocker: `NONE`
