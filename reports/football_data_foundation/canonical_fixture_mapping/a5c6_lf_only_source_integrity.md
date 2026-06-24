# Phase: FOOTBALL_DATA_FOUNDATION_A5C6_LF_ONLY_SOURCE_INTEGRITY_FINALIZATION

## Background & Rationale
Previous phases reported hundreds of Python lines using Python's `.splitlines()`. However, some environments and git configurations could result in files rendering as huge physical lines on remote raw viewers (like GitHub Raw) due to non-LF line endings (CR-only or CRLF issues). While Python compiles CR-only files successfully, review tools, git diffs, and typical GitHub rendering do not recognize CR-only files properly.

To address this, we enforce a strict byte-level audit on all 5 required source and test files.

## Acceptance Criteria
- Files must be strictly LF-delimited.
- CR bytes (`b"\r"`) are strictly forbidden.
- CRLF (`b"\r\n"`) is strictly forbidden.
- LF count must be high enough to represent real physical lines.
- Byte-level LF count is the new acceptance criterion (as `.splitlines()` is insufficient since it splits on CR too).

## Pre-Fix Audit Results
Below are the results of auditing HEAD before conversion:

- `src/bet/enrichment/football_data_foundation/canonical_fixture_resolver.py`:
  - `lf_count`: 519
  - `cr_count`: 0
  - `crlf_count`: 0
  - `max_lf_line`: 113
- `src/bet/enrichment/football_data_foundation/canonical_observation_writer.py`:
  - `lf_count`: 564
  - `cr_count`: 0
  - `crlf_count`: 0
  - `max_lf_line`: 107
- `src/bet/enrichment/football_data_foundation/cli.py`:
  - `lf_count`: 368
  - `cr_count`: 0
  - `crlf_count`: 0
  - `max_lf_line`: 130
- `src/bet/enrichment/football_data_foundation/enrichment_freshness.py`:
  - `lf_count`: 278
  - `cr_count`: 0
  - `crlf_count`: 0
  - `max_lf_line`: 116
- `tests/enrichment/football_data_foundation/test_canonical_fixture_mapping.py`:
  - `lf_count`: 1033
  - `cr_count`: 0
  - `crlf_count`: 0
  - `max_lf_line`: 119
