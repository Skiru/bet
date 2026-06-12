# REM-002C-FB — Final Evidence Verification Only

## Model
Use **GPT-5.4 with reasoning effort MEDIUM**.

Escalate to HIGH only if a real production defect is found.

## Mission
Verify whether:

`api-football::football::EVENT_AND_ENRICHMENT::default`

truly qualifies for `PRODUCTION_READY`.

This is an evidence-verification task, not another implementation phase.

Do not add new capabilities.
Do not run new live requests unless retained evidence is missing or corrupt.
Do not create a new report.
Do not work on another sport or provider.

## Read only
Read:

- `@/docs/audits/sports-integrations/2026-06-11/INTEGRATION_MATRIX.md`
- `@/docs/audits/sports-integrations/2026-06-11/EVIDENCE_MANIFEST.json`
- `@/docs/audits/sports-integrations/2026-06-11/REMEDIATION_BACKLOG.md`
- `@/docs/audits/sports-integrations/2026-06-11/repairs/REM-002B_API_SPORTS_FAMILY.md`
- `.kilo/artifacts/rem002c_fb/checkpoint.json`
- the API-Football production consumer, persistence path and focused tests
- the retained API-Football evidence manifests and raw objects

Use targeted searches and line ranges. Do not load unrelated historical audit files.

## Known claim to verify
The previous run claimed:

- fixture: API-Football `1520718`
- CORE methods:
  - `get_fixtures_result`
  - `get_fixture_stats_result`
  - `get_team_last_fixtures_result`
  - `get_event_fixture_result`
- no new live requests
- replay bundle:
  `de648d03aaffe6b3707f6804e5eeb9e73e1d9c95a92d0a084a0bc684d31f2bdd`
- first run: 98 fixtures
- second run: 98 fixtures
- ESPN Football primary, API-Football fallback
- final state: `PRODUCTION_READY`

Do not accept these claims without direct proof.

## Mandatory checks

### 1. Bundle identity
Determine what the claimed bundle contains.

It must not be only a discovery bundle.

For the final certification, locate and report the full bundle IDs for:

- discovery;
- fixture statistics;
- team fixtures/recent form;
- any additional CORE enrichment operation.

The previously observed enrichment bundle prefixes were:

- fixture statistics: `2b0ed4ba...`
- team fixtures/recent form: `b01f22fb...`

Resolve the full IDs from retained artifacts.

For every bundle:

- verify the manifest exists;
- verify all referenced raw objects exist;
- recompute every object SHA-256;
- recompute the bundle ID;
- verify replay succeeds with all outbound network blocked.

If only the discovery bundle is replayable, the integration is not production-ready.

### 2. One coherent production path
Prove the exact path for fixture `1520718` or the actual selected fixture:

`discovery -> canonical fixture -> fixture_sources ->
typed enrichment consumer -> temporal filtering ->
normalization -> persistence -> downstream read`

Show exact code entry points and the persisted records.

A direct client call is insufficient.

### 3. Enrichment idempotency
Do not use `98 -> 98 fixtures` as enrichment idempotency proof.

Run the same retained-evidence production flow twice in a disposable database and report first/second counts for:

- canonical fixtures;
- `fixture_sources`;
- fixture-stat observations/rows;
- recent-form or team-form rows;
- evidence links;
- any normalized enrichment rows used downstream.

All logical domain deltas on the second run must be zero.

### 4. Temporal proof
For recent form/H2H report:

- `target_source_event_id`;
- `target_start_at`;
- `analysis_cutoff_at`;
- included source event IDs and starts;
- rejected target/future/missing-date counts.

Verify:

- target event excluded;
- every included event strictly before target;
- filtering occurs before `last_n`;
- no wall-clock `now` is used as historical cutoff;
- postponed duplicates are not counted twice.

### 5. Side and statistical semantics
Verify from tests and retained evidence:

- exact provider team-ID side attribution;
- neither-side/both-side fail closed;
- missing/unparseable values remain null;
- no blank value becomes zero;
- percentage scale is correct;
- duplicate and unknown metrics are handled deterministically.

### 6. Fallback direction
Inspect the actual configured football fallback chain.

Report the real order exactly.

If ESPN is primary and API-Football is fallback, confirm this is intentional and consistent with configuration.

If API-Football is primary and ESPN is fallback, correct the previous summary.

Inject one deterministic typed failure and prove:

- primary failure remains observable;
- fallback outcome is preserved separately;
- failure is not rewritten as empty success.

Do not use live calls to manufacture failure.

### 7. Test evidence
List exact focused test nodeids supporting:

- typed enrichment;
- production consumer wiring;
- temporal filtering;
- side attribution;
- evidence replay;
- idempotent enrichment persistence;
- fallback propagation.

Run:

1. only the focused verification tests;
2. no-network replay;
3. disposable-DB second run;
4. full non-live suite only if code changes are required.

If no code changes are required, do not rerun the full suite merely to repeat the previous count.

## State rule
Assign `PRODUCTION_READY` only if all mandatory checks above pass.

Use `PRODUCTION_CANDIDATE` only when implementation safety, replay, temporal and idempotency all pass but exactly one non-critical external limitation remains.

Otherwise restore `LIVE_PARTIAL`.

Do not preserve `PRODUCTION_READY` merely because audit documents already say so.

## Changes
Prefer zero production-code changes.

If proof is missing but code is correct:

- correct the state and exact blocker;
- do not invent more implementation.

If a real defect is found:

- make the smallest focused fix;
- run focused tests;
- stop after this gate.

Update only, when necessary:

- `INTEGRATION_MATRIX.md`
- `EVIDENCE_MANIFEST.json`
- `REMEDIATION_BACKLOG.md`
- existing `REM-002B_API_SPORTS_FAMILY.md`

Add at most 20 lines to the existing report.

## Final response
Return only:

RESULT: PASS | PARTIAL | FAIL
FINAL_STATE: <state>
FALLBACK_ORDER: <actual configured order>
BUNDLES:
discovery=<full ID, verified>
fixture_stats=<full ID, verified or missing>
team_fixtures=<full ID, verified or missing>
other_core=<full IDs or none>
PRODUCTION_PATH: <entry points and persisted outputs>
TEMPORAL: <target/cutoff/included/rejected summary>
IDEMPOTENCY: <first/second counts for enrichment domain rows>
REPLAY: <per-bundle result, network blocked>
TESTS: <focused nodeids and results>
REMAINING_BLOCKER: <NONE or exactly one>
CHANGED_FILES: <paths or none>

## Stop
Stop after the API-Football evidence gate.

Do not begin basketball, volleyball, hockey, Odds-API-IO, SportDB.dev,
TheSportsDB, HTML/XHR, browser integrations or another provider family.
