# FIFA World Cup 2026 Scanner Window Live Validation

- **Phase ID:** `FOOTBALL_DATA_FOUNDATION_L1_SCANNER_WINDOW_LIVE_VALIDATION_WORLD_CUP_2026_NO_ACTIVATION`
- **Validation Time:** `2026-06-20T14:44:18.110518+00:00`
- **Selected Events Count:** `6` / 6
- **Coverage Status:** `complete`

## Selected Events

| Scanner Event ID | Provider Event ID | Match Name | Kickoff Local | Status |
|---|---|---|---|---|
| `scanner-worldcup-20260620-20260621-760447` | `760447` | **Netherlands vs Sweden** | `2026-06-20T19:00:00+02:00` | `STATUS_SCHEDULED` |
| `scanner-worldcup-20260620-20260621-760448` | `760448` | **Germany vs Ivory Coast** | `2026-06-20T22:00:00+02:00` | `STATUS_SCHEDULED` |
| `scanner-worldcup-20260620-20260621-760446` | `760446` | **Ecuador vs Curaçao** | `2026-06-21T02:00:00+02:00` | `STATUS_SCHEDULED` |
| `scanner-worldcup-20260620-20260621-760449` | `760449` | **Tunisia vs Japan** | `2026-06-21T06:00:00+02:00` | `STATUS_SCHEDULED` |
| `scanner-worldcup-20260620-20260621-760453` | `760453` | **Spain vs Saudi Arabia** | `2026-06-21T18:00:00+02:00` | `STATUS_SCHEDULED` |
| `scanner-worldcup-20260620-20260621-760451` | `760451` | **Belgium vs Iran** | `2026-06-21T21:00:00+02:00` | `STATUS_SCHEDULED` |

## Enrichment Results

| Scanner Event ID | Provider ID | Discovery Status | Facts Count | Detailed Metrics |
|---|---|---|---|---|
| `scanner-worldcup-20260620-20260621-760447` | `espn-fifa-worldcup` | `ENRICHED_PARTIAL` | `13` | `UNAVAILABLE: missing_provider_data_or_identity_mismatch` |
| `scanner-worldcup-20260620-20260621-760448` | `espn-fifa-worldcup` | `ENRICHED_PARTIAL` | `13` | `UNAVAILABLE: missing_provider_data_or_identity_mismatch` |
| `scanner-worldcup-20260620-20260621-760446` | `espn-fifa-worldcup` | `ENRICHED_PARTIAL` | `13` | `UNAVAILABLE: missing_provider_data_or_identity_mismatch` |
| `scanner-worldcup-20260620-20260621-760449` | `espn-fifa-worldcup` | `ENRICHED_PARTIAL` | `13` | `UNAVAILABLE: missing_provider_data_or_identity_mismatch` |
| `scanner-worldcup-20260620-20260621-760453` | `espn-fifa-worldcup` | `ENRICHED_PARTIAL` | `13` | `UNAVAILABLE: missing_provider_data_or_identity_mismatch` |
| `scanner-worldcup-20260620-20260621-760451` | `espn-fifa-worldcup` | `ENRICHED_PARTIAL` | `13` | `UNAVAILABLE: missing_provider_data_or_identity_mismatch` |

## Freshness Status Table

| Scanner Event ID | Status State | Status Name | Freshness Decision | Must Refresh |
|---|---|---|---|---|
| `scanner-worldcup-20260620-20260621-760447` | `pre` | `STATUS_SCHEDULED` | `FRESH_FROM_LIVE_PROVIDER` | `False` |
| `scanner-worldcup-20260620-20260621-760448` | `pre` | `STATUS_SCHEDULED` | `FRESH_FROM_LIVE_PROVIDER` | `False` |
| `scanner-worldcup-20260620-20260621-760446` | `pre` | `STATUS_SCHEDULED` | `FRESH_FROM_LIVE_PROVIDER` | `False` |
| `scanner-worldcup-20260620-20260621-760449` | `pre` | `STATUS_SCHEDULED` | `FRESH_FROM_LIVE_PROVIDER` | `False` |
| `scanner-worldcup-20260620-20260621-760453` | `pre` | `STATUS_SCHEDULED` | `FRESH_FROM_LIVE_PROVIDER` | `False` |
| `scanner-worldcup-20260620-20260621-760451` | `pre` | `STATUS_SCHEDULED` | `FRESH_FROM_LIVE_PROVIDER` | `False` |

## Canonical Mapping Status Table

| Scanner Event ID | Fixture ID | Sport ID | Competition ID | Home Team ID | Away Team ID | Resolution Status | Write Status |
|---|---|---|---|---|---|---|---|
| `scanner-worldcup-20260620-20260621-760447` | `1` | `1` | `1` | `1` | `2` | `CREATED_CANONICAL_FIXTURE` | `SUCCESS` |
| `scanner-worldcup-20260620-20260621-760448` | `2` | `1` | `1` | `3` | `4` | `CREATED_CANONICAL_FIXTURE` | `SUCCESS` |
| `scanner-worldcup-20260620-20260621-760446` | `3` | `1` | `1` | `5` | `6` | `CREATED_CANONICAL_FIXTURE` | `SUCCESS` |
| `scanner-worldcup-20260620-20260621-760449` | `4` | `1` | `1` | `7` | `8` | `CREATED_CANONICAL_FIXTURE` | `SUCCESS` |
| `scanner-worldcup-20260620-20260621-760453` | `5` | `1` | `1` | `9` | `10` | `CREATED_CANONICAL_FIXTURE` | `SUCCESS` |
| `scanner-worldcup-20260620-20260621-760451` | `6` | `1` | `1` | `11` | `12` | `CREATED_CANONICAL_FIXTURE` | `SUCCESS` |

## Missing / Deferred Data Table

| Scanner Event ID | Capability | Status / Reason | Deferred Fact Categories |
|---|---|---|---|
| `scanner-worldcup-20260620-20260621-760447` | `detailed_metrics` | `UNAVAILABLE: missing_provider_data_or_identity_mismatch` | `statistics, leaders` |
| `scanner-worldcup-20260620-20260621-760448` | `detailed_metrics` | `UNAVAILABLE: missing_provider_data_or_identity_mismatch` | `statistics, leaders` |
| `scanner-worldcup-20260620-20260621-760446` | `detailed_metrics` | `UNAVAILABLE: missing_provider_data_or_identity_mismatch` | `statistics, leaders` |
| `scanner-worldcup-20260620-20260621-760449` | `detailed_metrics` | `UNAVAILABLE: missing_provider_data_or_identity_mismatch` | `statistics, leaders` |
| `scanner-worldcup-20260620-20260621-760453` | `detailed_metrics` | `UNAVAILABLE: missing_provider_data_or_identity_mismatch` | `statistics, leaders` |
| `scanner-worldcup-20260620-20260621-760451` | `detailed_metrics` | `UNAVAILABLE: missing_provider_data_or_identity_mismatch` | `statistics, leaders` |

## Final Verification Verdict

**VERDICT:** `#LIVE_VALIDATION_PASS`

### Assurances Certified:
- No raw provider payload committed: **PASS**
- No config changes: **PASS**
- No real DB writes: **PASS**
- No DB schema/migration changes: **PASS**
- No betting decision changes: **PASS**
- No matrix/routing activation: **PASS**
