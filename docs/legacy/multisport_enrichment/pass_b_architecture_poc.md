# Multisport Pass B Architecture POC

Pass B implements the foundational layer for provider-bound sanitized corpus contracts and per-sport source-bound shadow artifacts. It preserves full backward compatibility with Pass A, prevents "fake success" claims, and enforces strict fail-closed security properties.

## Reference POC Policy
- **Reference POC Path:** `/Users/mkoziol/projects/prototypes/multisport_pass_b_poc_v3_verified`
- **Adaptation Rationale:** The POC was adapted into the current repository with zero direct copy of conflicting code. We implemented clean imports, lazy parent exports inside `src/bet/enrichment/__init__.py` to eliminate heavy `pandas` dependencies during multisport-only startup, and resolved a truthy assertion bug in the Pass A test suite.

## 1. Inventory Carry-Forward Rationale
Every single football-era source must be accounted for exactly once in the inventory to prevent silent drop of historical contexts, maintain structured transition tracing, and support multi-sport extension audits.

## 2. Source Classifications
All 25 sources are classified into precise transfer decisions to govern safe reuse boundaries:
- **`transfer_direct`**: Directly applicable to target sports (e.g., `sportdb`, `api-sports-family`, `pandascore`, `highlightly`). Requires sport-specific proof model and environment credentials.
- **`transfer_as_pattern` / Reference**: Used to model cross-reference styles or basic schedules (e.g., `thesportsdb`, `espn-baseline`). Never used as the sole detailed current truth.
- **`football_only_reference`**: Retained solely for football compatibility (e.g., `api-football`, `football-data-org`, `statsbomb`, all `soccerdata-*` libraries). Does not block multisport pipeline runs.
- **`deferred_probe_only`**: Rich unofficial scrapers/probes (e.g., `fotmob-probe`, `sofascore-rich-probe`, `scraperfc-sofascore-bridge`). These are terms/access-gated and strictly forbidden from production selection.

## 3. Source-Bound Shadow Policy
- **Shadow Artifact Integrity:** `SourceBoundShadowArtifact` has hard invariants. `manual_authorization_required` is always `True`, `production_selectable` is always `False`, and `betting_decisions_enabled` is always `False`.
- **Mapping Verification:** `SOURCE_BOUND_SHADOW_READY` is disallowed unless at least one valid, unblocked provider corpus record with participant evidence is present.

## 4. Blocked Statuses as Valid Outcomes
Blocked states are correct, valid, and expected Pass B statuses. They protect against fake success claims when credentials or mapping details are missing:
- `SOURCE_BOUND_SHADOW_READY`
- `REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT`
- `BLOCKED_PROVIDER_ACCESS`
- `BLOCKED_NO_CREDENTIALS`
- `BLOCKED_PROVIDER_TERMS_OR_SCOPE`
- `BLOCKED_PROVIDER_MAPPING_NOT_FOUND`

### Status Precedence Correction
To preserve explicit blocked statuses in source-bound shadow artifacts and avoid mislabeling them as mapping-insufficient, deterministic status precedence is enforced when resolving shadow status:
1. `SOURCE_BOUND_SHADOW_READY` (if non-empty participant evidence exists)
2. `REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT`
3. `BLOCKED_NO_CREDENTIALS`
4. `BLOCKED_PROVIDER_TERMS_OR_SCOPE`
5. `BLOCKED_PROVIDER_ACCESS`
6. `BLOCKED_PROVIDER_MAPPING_NOT_FOUND`

## 5. No Fake Success Policy
- **Redaction of Secrets:** Every generated report/corpus record must redact `Authorization`, `Cookie`, `Bearer` tokens, `x-api-key`, `x-apisports-key`, `x-rapidapi-key`, and other secret-like values (replacing them with `<redacted>`). No raw headers are persisted.
- **Verification Gates:** Automated verification predicates ensure that no placeholder, default, or fallback values (IDs, scores, statuses, rosters, venues, or winners) can slip into success artifacts.

## 6. No Betting Decisions & No Production Activation
No production routing or automated betting activation can happen during Pass B. All evaluations remain strictly isolated, manual-authorization-bound, and purely conditional.
