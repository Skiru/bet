# REM-002B Bundle Code Review

## Verdict

**REM-002B foundation accepted conditionally; family certification rejected as incomplete.**

Current safe states remain:

- api-football: LIVE_PARTIAL
- api-basketball: LIVE_PARTIAL
- api-volleyball: LIVE_PARTIAL
- api-hockey: LIVE_PARTIAL

Do not begin REM-003 yet.

## Critical findings

### C1 — Live tests are false-positive and run inside the normal suite

`@pytest.mark.live` is not registered. Pytest emitted `PytestUnknownMarkWarning`.
The four live tests were collected and executed in the 54-test focused run.

They accept `RATE_LIMITED` and `AUTHENTICATION_ERROR` as passing outcomes, so they
can pass without one successful source response. `LIVE_OUTPUT.txt` is only a
placeholder and confirms that the required certification live run did not occur.

### C2 — New typed result methods are not wired into production

The bundle contains no production consumer of `get_fixtures_result()`.
Repository search within the bundle shows use only in tests and documentation.

Consequences:

- the discovery coordinator can still call legacy `get_fixtures()`;
- typed statuses can still collapse to `[]`;
- evidence refs do not reach orchestration or persistence;
- adding methods does not improve the running pipeline.

### C3 — Provider participant identity is not populated

`APIFixture` has `home_participant_id` and `away_participant_id`, but all four
new `get_fixtures_result()` parsers leave them empty.

The implementation therefore does not satisfy source participant identity or
safe canonical matching.

### C4 — No E4 proof exists

The bundle has:

- no successful family live certification output;
- no per-sport evidence bundle IDs;
- no no-network replay per sport;
- no persistence rerun deltas;
- no canonical/source-reference idempotency proof.

The report itself says these are next steps.

## High findings

### H1 — Evidence capture failure is swallowed

`persist_response_evidence()` exceptions are ignored and the operation may
return `SUCCESS` with no evidence. A certifiable evidence-required path must
fail closed or return an explicit internal/evidence error.

### H2 — HTTP 200 provider errors are treated as success

`_request_with_evidence()` verifies only that the top-level payload is a dict.
It does not inspect API-Sports provider error payloads and does not require
`response` to be a list. A payload containing `errors` or missing/malformed
`response` can become `SUCCESS + []`.

### H3 — Retry and quota accounting are incomplete

- transport exceptions can produce three total attempts, exceeding the intended
  single retry;
- 5xx responses are not retried despite being marked retryable;
- no jitter is used;
- only successful responses call the local rate limiter's `record_request`;
- API-Sports quota headers are not propagated into the typed result;
- retry attempt numbers are not reflected in retained evidence.

### H4 — No deterministic bundle is created by the new operation

The request creates individual `EvidenceRef` objects, but no operation bundle ID
is written or returned. Therefore downstream persistence cannot point to a
complete, deterministic replay unit.

### H5 — Invalid event rows are accepted

The parsers create fixtures with:

- blank event IDs;
- blank participant IDs;
- blank or `"Unknown"` participants;
- blank/unvalidated kickoff;
- no competition/season identity.

Those rows can be returned under `SUCCESS`.

### H6 — Bundle is incomplete for review and commit

`REM-002B.patch` contains only five tracked production files. It excludes:

- `tests/scrapers/test_api_sports_live.py`;
- `tests/scrapers/test_api_sports_family.py`;
- audit artifact changes;
- marker configuration.

`test_api_sports_family.py` was used in test output but is missing from the ZIP,
so its 37 tests could not be reviewed.

### H7 — Dirty worktree mixes multiple remediation slices

The worktree includes previous ESPN/database changes, prompt files, ZIP bundles,
Kilo artifacts, `.DS_Store`, and current changes. A clean checkpoint is required
before final REM-002B certification.

## Medium findings

- `evidence_refs` is untyped.
- `SourceOperationResult` has no bundle ID, quota metadata, retry count, or
  diagnostics.
- Live-test `tmp_path` evidence roots are unused by real client calls.
- Test/report counts conflict: 54 vs 101 focused and 700 vs 683 full.
- The report closes REM-002B deterministic coverage but does not contain the
  role wiring, replay, or idempotency required by the rollout contract.
- API-Basketball's declared `EVENT_AND_ENRICHMENT` role remains unproved in the
  actual discovery coordinator.

## Accepted parts

- The typed result direction is correct.
- Statuses cover the principal source failure classes.
- Evidence is captured before parsing.
- Sanitized response objects use full SHA-256.
- The result parsers preserve provider event IDs.
- Current matrix/backlog truthfully retain all four states as `LIVE_PARTIAL`.
- Deterministic test coverage has improved.

## Required next step

Run **REM-002B-CLOSURE** only. Do not start Odds-API-IO or another provider
family until the four integrations have independent truthful final states.
