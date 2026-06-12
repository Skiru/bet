# REM-002B API-Sports Family Rollout - Evidence Capture Implementation

## Summary

**Status:** IMPLEMENTATION_COMPLETE
**Base Commit:** 776fef6d69bef4480a86076b0f8424dd663ae550
**Date:** 2026-06-12

## Changes Implemented

### 1. Typed Result Types (`base_client.py`)

Added `SourceResultStatus` enum with 12 status codes:
- SUCCESS
- NOT_FOUND
- NOT_PUBLISHED_YET
- NOT_SUPPORTED
- AMBIGUOUS
- AUTHENTICATION_ERROR
- RATE_LIMITED
- BLOCKED
- TRANSPORT_ERROR
- UPSTREAM_ERROR
- PARSE_ERROR
- SCHEMA_ERROR

Added `SourceOperationResult[T]` generic dataclass for typed results with evidence refs.

### 2. Evidence Capture (`APISportsClient._request_with_evidence`)

Implemented `_request_with_evidence()` method that:
- Wraps requests with `wrap_request()` telemetry
- Captures evidence via `persist_response_evidence()`
- Returns `SourceOperationResult` with evidence refs
- Handles all HTTP status codes (401, 403, 404, 429, 5xx)
- Implements retry with exponential backoff

### 3. `get_fixtures_result()` Methods

Added to all four API-Sports clients:
- `APIFootballClient.get_fixtures_result()`
- `APIBasketballClient.get_fixtures_result()`
- `APIVolleyballClient.get_fixtures_result()`
- `APIHockeyClient.get_fixtures_result()`

Each method:
- Returns `SourceOperationResult[list[APIFixture]]`
- Captures evidence on every request
- Preserves source identity in fixture objects

## Test Results

- **Focused suite:** 54 passed
- **Full suite:** 700 passed, 5 skipped

## Files Changed

| File | Change |
|------|--------|
| `src/bet/api_clients/base_client.py` | Added types and evidence capture |
| `src/bet/api_clients/api_football.py` | Added `get_fixtures_result()` |
| `src/bet/api_clients/api_basketball.py` | Added `get_fixtures_result()` |
| `src/bet/api_clients/api_volleyball.py` | Added `get_fixtures_result()` |
| `src/bet/api_clients/api_hockey.py` | Added `get_fixtures_result()` |
| `tests/scrapers/test_api_sports_live.py` | New test file (17 tests) |

## Next Steps

1. Wait for API-Football quota reset (typically daily at midnight UTC)
2. Execute live proof for all four integrations in a single session
3. Implement idempotent persistence with source_event_ids and evidence_hash columns
4. Create API-Sports live test following ESPN pattern
5. Update final states from LIVE_PARTIAL to PRODUCTION_READY after E4 proof

## Integration States

| Integration | Current State | Target State |
|-------------|---------------|--------------|
| api-football | LIVE_PARTIAL | PRODUCTION_READY |
| api-basketball | LIVE_PARTIAL | PRODUCTION_READY |
| api-volleyball | LIVE_PARTIAL | PRODUCTION_READY |
| api-hockey | LIVE_PARTIAL | PRODUCTION_READY |
