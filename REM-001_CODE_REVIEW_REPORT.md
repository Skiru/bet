# REM-001 Code Review — ESPN Football

## Verdict

**Original NameError repair: accepted.**

**Recertification: not accepted as final.** The integration must remain `LIVE_PARTIAL` and the contract verdict remains `FAIL`.

The review found one critical temporal-correctness defect, two high identity/evidence defects, and several medium test/report-integrity issues.

## Reviewed material

- `REM-001.patch`
- `src/bet/api_clients/espn.py`
- `src/bet/stats/enrichment.py`
- `tests/scrapers/test_espn_client.py`
- `tests/scrapers/test_espn_football_live.py`
- `pyproject.toml`
- `REM-001_ESPN_FOOTBALL.md`
- `live_summary.json`
- `INTEGRATION_MATRIX.md`
- `EVIDENCE_MANIFEST.json`
- `REMEDIATION_BACKLOG.md`
- test output: 27 deterministic tests, 1 live test, targeted Ruff run

## Findings

### CRITICAL — CR-001: recent form is not point-in-time safe

`get_team_last_fixtures()` filters only for matches completed relative to the current clock. It accepts no analyzed-event start, analysis cutoff, or excluded event ID.

Consequences:

- a historical analysis can include matches played after the analyzed fixture;
- the analyzed event can appear in its own recent form;
- the repair report's Gate 7 `PASS` is unsupported.

The live artifact contains a summary request for event `740968`, the event selected as the live proof. This confirms that the selected event was fetched in the same recent-history execution rather than being explicitly excluded.

Required correction:

- pass an immutable target cutoff into the ESPN history path;
- exclude the analyzed source event ID;
- include only events with trustworthy start time strictly before the analyzed event;
- reject missing/unparseable event time and missing event ID rather than treating them as eligible history.

### HIGH — HI-001: side attribution silently defaults to away

In `_try_espn_fetch()`:

```python
if _is_home_team(team.name, ms.home_team_name):
    val = sides.get("home")
else:
    val = sides.get("away")
```

When the local team matches neither participant, the away side is silently attributed to it. A wrong or ambiguous `resolve_team_id()` result can therefore persist the opponent's statistics as the requested team's form.

Required correction:

- identify the participant by provider participant ID;
- verify exactly one side matches;
- if neither or both match, fail closed and persist no value;
- names may be used only as diagnostic data or an explicitly approved crosswalk fallback.

### HIGH — HI-002: participant identity claim is overstated

`get_fixtures()` now requires:

- a provider event ID;
- non-empty participant display names.

It does **not** require or retain provider participant IDs. The report says events without “participant identities” are skipped, but the implementation currently validates names only.

Required correction:

- retain ESPN team/participant IDs in the source event candidate or source-participant crosswalk;
- do not certify participant identity from `displayName` alone.

### HIGH — HI-003: live proof does not use one coherent event slice

The direct proof selected `Crystal Palace` vs `Arsenal`, event `740968`.

The fallback proof seeded a separate canonical fixture: `Arsenal` vs `Liverpool`.

This proves the client and fallback separately, but it does not prove:

- canonical matching for event `740968`;
- source event ID propagation into fallback persistence;
- exclusion of event `740968` from its own recent form;
- a complete target-event vertical slice.

The next live proof must use one event consistently from source discovery through canonical fixture, history filtering, persistence, replay, and rerun.

### MEDIUM — ME-001: evidence hashes in the report disagree with the artifact

The repair report lists:

- `/teams/359/schedule` → `322013...`
- `/teams/364/schedule` → `01bd58...`

`live_summary.json` lists:

- `/teams/359/schedule` → `e9016a...`
- `/teams/364/schedule` → `9ae43b...`

The report and artifact cannot both describe the same retained response set. Regenerate the report from the artifact or identify separate runs explicitly.

### MEDIUM — ME-002: raw response evidence is missing from the review bundle

The live test writes response bodies under `.kilo/artifacts/rem001_espn_football/`, but the review bundle contains only `live_summary.json`.

Therefore this review could validate the summary structure and hashes, but could not independently hash the raw bodies or replay them.

The next review bundle must include all sanitized response files referenced by the replay manifest.

### MEDIUM — ME-003: the replay does not enforce a process-wide network block

The test replaces `requests.get` with a replay function. That blocks unexpected requests made through that exact attribute, but it does not prove that all outbound transports are disabled.

Required correction:

- block sockets or the repository's complete transport boundary during replay;
- keep the current request-key assertion as an additional check.

### MEDIUM — ME-004: exact live event ID is not enforced

The live test uses:

```python
target = next((f for f in fixtures if f.external_id == "740968"), fixtures[0])
```

If `740968` is absent, the test silently validates a different fixture while the report still expects the named event.

Use either:

- `assert target is not None` for a pinned evidence test; or
- a fully dynamic event selection with the selected ID recorded and no hardcoded claim.

Do not combine the two modes.

### MEDIUM — ME-005: missing source IDs remain possible in recent-history events

`get_team_last_fixtures()` stores `event.get("id")` without validation. Later, `str(None)` becomes the truthy string `"None"` and may be sent to `/summary`.

Reject missing/blank event IDs before the event enters recent form.

### MEDIUM — ME-006: shared ESPN behavior changed beyond the recertified key

The modified `ESPNClient` is shared by football, basketball, hockey, tennis, and volleyball.

The patch changes:

- event filtering;
- missing-stat parsing;
- competition-name selection.

Only `espn-football` was recertified. The competition-name change is especially unrelated to the NameError and can alter matching in other sports.

Required action:

- revert unrelated shared behavior, or
- add shared cross-sport regression coverage and record affected integration keys.

### MEDIUM — ME-007: targeted Ruff execution omitted production files

The logged Ruff command checks only the two new test files. Run Ruff against both modified production modules as well.

### LOW — LO-001: malformed/HTTP errors still collapse to `[]`

The tests intentionally preserve the existing list/empty-list contract. This does not distinguish valid empty, malformed JSON, HTTP failure, not found, or blocked access.

Invalid JSON raises `JSONDecodeError`; the current broad exception handling converts it into the same empty-list result as valid no-data. This remains a known contract blocker and should be handled in a later focused slice.

### REPOSITORY HYGIENE

`GIT_STATUS.txt` shows the review bundle itself and several artifacts as untracked. Do not commit:

- `.kilo/artifacts/REM-001_REVIEW_BUNDLE/`
- temporary packaging output
- unsanitized raw responses

Commit the intended production files, deterministic/live tests, the focused repair report, and explicitly approved sanitized audit artifacts only.

## Accepted changes

The following changes are correct and should be retained:

- adding `import json`;
- rejecting events without an ESPN event ID in `get_fixtures()`;
- preserving blank/unparseable stat values as missing rather than zero;
- preserving missing side values in fallback aggregation;
- registering a separately selectable live-test marker;
- adding deterministic regression coverage for the original `NameError`;
- retaining `LIVE_PARTIAL` and contract `FAIL` rather than claiming readiness.

## Required audit corrections before commit

1. Change Gate 7 from `PASS` to `FAIL`.
2. Add CR-001 and the side-attribution defect to the repair report and backlog.
3. Correct the schedule evidence hashes or identify separate run IDs.
4. Remove the statement that participant IDs are validated; only names currently are.
5. State clearly that the live proof uses two different fixtures and is not a complete event vertical slice.
6. Do not advance `espn-football` beyond `LIVE_PARTIAL`.

## Recommended next slice

**REM-001B — ESPN football participant identity and point-in-time recent form**

Reasoning: `high`.

This slice should fix only:

- provider participant-ID resolution/crosswalk;
- exact side attribution;
- strict before-cutoff recent form;
- current-event exclusion;
- coherent single-event live proof;
- test/evidence corrections directly needed for those invariants.

Defer explicit capability status envelopes and persistent evidence linkage to a following slice unless the existing repository already provides a small reusable mechanism.
