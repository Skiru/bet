# Kilo Prompt — REM-001B ESPN Football Identity and Temporal Safety

Use **GPT-5.4 with reasoning effort HIGH**.

You are the implementation owner and adversarial reviewer for `REM-001B` only.

## Binding inputs

Read completely before editing:

- `@/SPORTS_INTEGRATION_LIVE_REVIEW_CONTRACT.md`
- `@/docs/audits/sports-integrations/2026-06-11/AUDIT_RECONCILIATION.md`
- `@/docs/audits/sports-integrations/2026-06-11/INTEGRATION_MATRIX.md`
- `@/docs/audits/sports-integrations/2026-06-11/EVIDENCE_MANIFEST.json`
- `@/docs/audits/sports-integrations/2026-06-11/REMEDIATION_BACKLOG.md`
- `@/docs/audits/sports-integrations/2026-06-11/repairs/REM-001_ESPN_FOOTBALL.md`
- `@/src/bet/api_clients/espn.py`
- `@/src/bet/stats/enrichment.py`
- `@/tests/scrapers/test_espn_client.py`
- `@/tests/scrapers/test_espn_football_live.py`

## Scope

Repair only the remaining identity and point-in-time correctness blockers in:

`espn-football::football::ENRICHMENT_ONLY::default`

Do not repair another source. Do not start portfolio-wide REM-002. Do not introduce a universal integration framework.

## Confirmed review findings

1. `get_team_last_fixtures()` filters only by completed status relative to now. It has no analyzed-event cutoff and no excluded event ID.
2. The selected live event `740968` appeared among fetched summary event IDs, so current-event exclusion was not proved.
3. `_try_espn_fetch()` treats every non-home name match as away, allowing a mismatch to persist the opponent's values.
4. `resolve_team_id()` performs first-match fuzzy/containment resolution without an ambiguity zone.
5. `get_fixtures()` validates event ID and names, but does not retain provider participant IDs.
6. The direct live proof used `Crystal Palace` vs `Arsenal`, while fallback persistence used a different `Arsenal` vs `Liverpool` fixture.
7. The repair report contains schedule hashes inconsistent with `live_summary.json`.

## Phase 1 — Preflight and reproduction

1. Record branch, worktree and `git status --short`.
2. Preserve unrelated work.
3. Confirm the exact `espn-football` registration and shared ESPN call graph.
4. Reproduce and record:
   - event `740968` appearing in the recent-history/summary request set;
   - a unit case where a team matches neither side but currently receives away stats;
   - an ambiguous `resolve_team_id()` case or a deterministic synthetic equivalent.
5. Do not edit before reproduction evidence is recorded.

## Phase 2 — Define one coherent acceptance event

Use one real ESPN football event consistently from:

source fixture
→ source participant IDs
→ canonical fixture
→ enrichment
→ temporal filtering
→ persistence
→ replay
→ identical rerun

Prefer the existing event `740968` only if it remains available in retained/live evidence. Otherwise select another real event and record the replacement explicitly.

The canonical fixture used by the fallback proof must represent the same event and participants as the selected ESPN source event. Do not seed an unrelated fixture.

Define:

- `target_source_event_id`;
- `target_start_at`;
- `analysis_cutoff_at` at or before the target start;
- source participant IDs for both participants.

## Phase 3 — Provider participant identity

Inspect existing source-participant/crosswalk infrastructure before changing schemas.

Implement the smallest safe path that ensures:

1. ESPN participant IDs are extracted from source payloads.
2. The requested canonical team resolves through an existing source-ID crosswalk or an explicit deterministic mapping.
3. Names alone cannot produce an automatic ambiguous link.
4. Multiple candidates produce `AMBIGUOUS`/fail-closed behavior.
5. Missing provider participant ID cannot be represented as a valid source identity.

Do not add a global matcher abstraction unless an existing repository contract requires it.

## Phase 4 — Exact side attribution

Replace binary `home else away` attribution.

For every match-stat observation:

1. match the requested source participant ID against home and away source participant IDs;
2. require exactly one matching side;
3. if neither or both match, skip the observation and record an explicit diagnostic/status;
4. never infer away merely because home did not match;
5. keep names only for diagnostics or approved alias verification.

## Phase 5 — Point-in-time recent form

Extend the narrow ESPN fallback path so recent-history selection receives:

- target event start/cutoff;
- target source event ID or exclusion set.

An eligible recent-form event must:

- have a real non-empty ESPN event ID;
- have a trustworthy parseable event start;
- start strictly before `target_start_at`;
- not equal `target_source_event_id`;
- not be a postponed duplicate of the target event;
- be completed according to source semantics;
- have identifiable participants.

Do not use `datetime.now()` as the analysis cutoff.

If the current `team_form` architecture cannot represent different cutoffs for multiple fixtures in one batch, keep this slice to one acceptance event and fail closed for ambiguous multi-cutoff execution. Document the architectural limitation rather than silently using current data.

## Phase 6 — Deterministic tests

Add focused tests for:

1. target event excluded by source event ID;
2. event at the exact target start excluded;
3. event after the target excluded even when completed now;
4. event before target included;
5. missing/unparseable event ID or date excluded;
6. correct side selected by provider participant ID;
7. neither-side match persists nothing;
8. both-side/ambiguous match persists nothing;
9. ambiguous provider team resolution fails closed;
10. participant names may differ while provider IDs still select the correct side;
11. the exact selected live event remains one coherent source-to-persistence slice.

The pre-fix implementation must fail the key new regression tests.

## Phase 7 — Live proof and replay

Run a separately marked permitted live test.

The live artifact must record:

- selected event ID;
- both ESPN participant IDs and names;
- target start and analysis cutoff;
- all recent-form source event IDs and starts;
- explicit proof that the target ID is absent;
- explicit proof every included start is strictly before target start;
- side-selection identity evidence;
- response hashes;
- first-run and second-run logical row counts.

Use retained sanitized evidence for replay.

During replay, block outbound network at the complete transport/socket boundary, not only one `requests.get` attribute. Any attempted unrecorded network access must fail the test.

Require identical semantic output and zero new logical duplicates on the second run.

## Phase 8 — Shared-code blast-radius review

Because `ESPNClient` is shared by multiple sports:

1. identify every changed behavior affecting basketball, hockey, volleyball or tennis;
2. revert unrelated competition-name behavior unless required for this slice;
3. run existing shared ESPN tests;
4. add only the minimum cross-sport regression tests required by retained shared changes;
5. do not recertify other ESPN integration keys without their own live proof.

Run Ruff against all changed production and test files.

## Phase 9 — Audit correction

Correct the ESPN repair artifacts:

- Gate 7 must remain `FAIL` until strict cutoff/current-event exclusion is proved.
- Correct schedule hashes to match the authoritative artifact, or use distinct run IDs for distinct evidence sets.
- Do not claim participant-ID validation unless IDs are retained and used.
- State whether raw evidence bodies are retained and where.

Update only the `espn-football` entries in:

- `INTEGRATION_MATRIX.md`
- `EVIDENCE_MANIFEST.json`
- `REMEDIATION_BACKLOG.md`
- `repairs/REM-001_ESPN_FOOTBALL.md`

Create:

`docs/audits/sports-integrations/2026-06-11/repairs/REM-001B_ESPN_IDENTITY_TEMPORAL.md`

## Acceptance

PASS this slice only when:

1. one coherent real event is used end to end;
2. provider participant IDs select the team and side;
3. ambiguous identity fails closed;
4. the target event ID is excluded from recent form;
5. every included event starts strictly before the target;
6. no missing event ID/date is queried or persisted;
7. live evidence and report hashes agree;
8. offline replay cannot access the network;
9. second run adds zero logical duplicates;
10. shared ESPN regressions pass;
11. no unrelated integration is modified.

Even after this slice, keep the final integration state at `LIVE_PARTIAL` unless explicit capability statuses and persisted source-event/evidence linkage also satisfy the contract.

## Stop rule

Stop after REM-001B recertification. Do not start evidence-schema/status-taxonomy work or another source in this run.
