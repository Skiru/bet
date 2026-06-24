# L1C3 False Raw Pass Review

## Statement of Rejection
* START_SHA is rejected because public exact-SHA raw contradicts the agent output.
* Branch URL or local-only output is not proof.

## Pre-Fix Raw Analysis Transcript
Below is the verbatim command transcript of the analysis loop executed against the public GitHub raw URLs for START_SHA (commit `4960d2a348837082dc4d2d73a15efc3cbc8f56c5`).

```
PRE_FIX_RAW_BEGIN src/bet/enrichment/football_data_foundation/live_validation.py
URL=https://raw.githubusercontent.com/Skiru/bet/4960d2a348837082dc4d2d73a15efc3cbc8f56c5/src/bet/enrichment/football_data_foundation/live_validation.py
lf=1184 cr=0 crlf=0 max_lf=84
FIRST_40_LINES_BEGIN
from __future__ import annotations

import datetime
import hashlib
import json
import sqlite3
import sys
import urllib.request
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from bet.enrichment.football_data_foundation.active_enrichment import (
    ActiveEnrichmentOrchestrator,
    ActiveEnrichmentRequest,
)
from bet.enrichment.football_data_foundation.canonical_fixture_resolver import (
    CanonicalFixtureResolutionRequest,
    resolve_canonical_fixture,
    table_exists,
)
from bet.enrichment.football_data_foundation.canonical_observation_writer import (
    write_enrichment_observations,
)
from bet.enrichment.football_data_foundation.endpoint_verification import (
    parse_espn_scoreboard_payload,
)
from bet.enrichment.football_data_foundation.enrichment_freshness import (
    EvidenceFreshnessInput,
    EvidenceFreshnessPolicy,
    evaluate_freshness,
)
from bet.enrichment.football_data_foundation.enrichment_state import (
    EnrichmentCompletenessRecord,
)
from bet.enrichment.football_data_foundation.fingerprints import (
    compute_data_fingerprint,
    compute_schema_fingerprint,
)
from bet.enrichment.football_data_foundation.persistence_bridge import (

FIRST_40_LINES_END
PRE_FIX_RAW_END src/bet/enrichment/football_data_foundation/live_validation.py
PRE_FIX_RAW_BEGIN tests/enrichment/football_data_foundation/test_live_validation.py
URL=https://raw.githubusercontent.com/Skiru/bet/4960d2a348837082dc4d2d73a15efc3cbc8f56c5/tests/enrichment/football_data_foundation/test_live_validation.py
lf=247 cr=0 crlf=0 max_lf=87
FIRST_40_LINES_BEGIN
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from bet.enrichment.football_data_foundation.enrichment_freshness import (
    EvidenceFreshnessInput,
    EvidenceFreshnessPolicy,
    evaluate_freshness,
)
from bet.enrichment.football_data_foundation.live_validation import run_live_validation


def test_live_validation_runs_successfully(tmp_path: Path) -> None:
    """Run full live validation program and verify artifacts exist."""
    output_dir = tmp_path / "live_validation_test_output"

    try:
        run_live_validation(str(output_dir))
    except SystemExit as e:
        # A SystemExit is raised with exit code 1 if live sources are
        # completely down/unavailable, which is allowed.
        assert e.code == 1

    # In either case, provider_scoreboard_snapshot.json must exist.
    assert (output_dir / "provider_scoreboard_snapshot.json").exists()

    # If the fetch succeeded, let's verify all artifacts exist
    if (output_dir / "validation_manifest.json").exists():
        assert (output_dir / "provider_scoreboard_snapshot.md").exists()
        assert (output_dir / "scanner_event_batch.json").exists()
        assert (output_dir / "scanner_event_batch.md").exists()
        assert (output_dir / "out_of_window_events.json").exists()
        assert (output_dir / "event_enrichment_results.json").exists()
        assert (output_dir / "freshness_results.json").exists()
        assert (output_dir / "canonical_mapping_results.json").exists()
        assert (output_dir / "observation_projection_export.json").exists()
        assert (output_dir / "temp_sqlite_snapshot.json").exists()
        assert (output_dir / "validation_summary.md").exists()

FIRST_40_LINES_END
PRE_FIX_RAW_END tests/enrichment/football_data_foundation/test_live_validation.py
PRE_FIX_RAW_BEGIN reports/football_data_foundation/live_validation/world-cup-2026/2026-06-20_2026-06-21/validation_summary.md
URL=https://raw.githubusercontent.com/Skiru/bet/4960d2a348837082dc4d2d73a15efc3cbc8f56c5/reports/football_data_foundation/live_validation/world-cup-2026/2026-06-20_2026-06-21/validation_summary.md
lf=73 cr=0 crlf=0 max_lf=152
FIRST_40_LINES_BEGIN
# FIFA World Cup 2026 Scanner Window Live Validation

- **Phase ID:** `FOOTBALL_DATA_FOUNDATION_L1_SCANNER_WINDOW_LIVE_VALIDATION_WORLD_CUP_2026_NO_ACTIVATION`
- **Validation Time:** `2026-06-20T17:19:09.898916+00:00`
- **Selected Events Count:** `6` / 6
- **Coverage Status:** `complete`
- **Manifest Sidecar Hash Check:** `validation_manifest.sha256` sidecar exists and is verified

## Selected Events

| Scanner Event ID | Provider Event ID | Match Name | Kickoff Local | Status |
|---|---|---|---|---|
| `scanner-worldcup-20260620-20260621-760447` | `760447` | **Netherlands vs Sweden** | `2026-06-20T19:00:00+02:00` | `STATUS_IN_PROGRESS` |
| `scanner-worldcup-20260620-20260621-760448` | `760448` | **Germany vs Ivory Coast** | `2026-06-20T22:00:00+02:00` | `STATUS_SCHEDULED` |
| `scanner-worldcup-20260620-20260621-760446` | `760446` | **Ecuador vs Curaçao** | `2026-06-21T02:00:00+02:00` | `STATUS_SCHEDULED` |
| `scanner-worldcup-20260620-20260621-760449` | `760449` | **Tunisia vs Japan** | `2026-06-21T06:00:00+02:00` | `STATUS_SCHEDULED` |
| `scanner-worldcup-20260620-20260621-760453` | `760453` | **Spain vs Saudi Arabia** | `2026-06-21T18:00:00+02:00` | `STATUS_SCHEDULED` |
| `scanner-worldcup-20260620-20260621-760451` | `760451` | **Belgium vs Iran** | `2026-06-21T21:00:00+02:00` | `STATUS_SCHEDULED` |

## Enrichment Results

| Scanner Event ID | Provider ID | Discovery Status | Facts Count | Detailed Metrics |
|---|---|---|---|---|
| `scanner-worldcup-20260620-20260621-760447` | `espn-fifa-worldcup` | `ENRICHED_COMPLETE` | `25` | `available` |
| `scanner-worldcup-20260620-20260621-760448` | `espn-fifa-worldcup` | `ENRICHED_PARTIAL` | `13` | `missing_provider_data_or_identity_mismatch` |
| `scanner-worldcup-20260620-20260621-760446` | `espn-fifa-worldcup` | `ENRICHED_PARTIAL` | `13` | `missing_provider_data_or_identity_mismatch` |
| `scanner-worldcup-20260620-20260621-760449` | `espn-fifa-worldcup` | `ENRICHED_PARTIAL` | `13` | `missing_provider_data_or_identity_mismatch` |
| `scanner-worldcup-20260620-20260621-760453` | `espn-fifa-worldcup` | `ENRICHED_PARTIAL` | `13` | `missing_provider_data_or_identity_mismatch` |
| `scanner-worldcup-20260620-20260621-760451` | `espn-fifa-worldcup` | `ENRICHED_PARTIAL` | `13` | `missing_provider_data_or_identity_mismatch` |

## Freshness Status Table

| Scanner Event ID | Status State | Status Name | Freshness Decision | Must Refresh |
|---|---|---|---|---|
| `scanner-worldcup-20260620-20260621-760447` | `in` | `STATUS_IN_PROGRESS` | `FRESH_REUSABLE` | `False` |
| `scanner-worldcup-20260620-20260621-760448` | `pre` | `STATUS_SCHEDULED` | `FRESH_REUSABLE` | `False` |
| `scanner-worldcup-20260620-20260621-760446` | `pre` | `STATUS_SCHEDULED` | `FRESH_REUSABLE` | `False` |
| `scanner-worldcup-20260620-20260621-760449` | `pre` | `STATUS_SCHEDULED` | `FRESH_REUSABLE` | `False` |
| `scanner-worldcup-20260620-20260621-760453` | `pre` | `STATUS_SCHEDULED` | `FRESH_REUSABLE` | `False` |
| `scanner-worldcup-20260620-20260621-760451` | `pre` | `STATUS_SCHEDULED` | `FRESH_REUSABLE` | `False` |

FIRST_40_LINES_END
PRE_FIX_RAW_END reports/football_data_foundation/live_validation/world-cup-2026/2026-06-20_2026-06-21/validation_summary.md
PRE_FIX_RAW_BEGIN reports/football_data_foundation/live_validation/world-cup-2026/2026-06-20_2026-06-21/event_enrichment_results.json
URL=https://raw.githubusercontent.com/Skiru/bet/4960d2a348837082dc4d2d73a15efc3cbc8f56c5/reports/football_data_foundation/live_validation/world-cup-2026/2026-06-20_2026-06-21/event_enrichment_results.json
lf=1642 cr=0 crlf=0 max_lf=97
FIRST_40_LINES_BEGIN
[
  {
    "profile_id": "world-cup-2026",
    "scanner_event_id": "scanner-worldcup-20260620-20260621-760447",
    "canonical_match_identity": {
      "home_team": "Netherlands",
      "away_team": "Sweden"
    },
    "status": "ENRICHED_COMPLETE",
    "fetch_decisions": [
      {
        "capability": "current_discovery",
        "decision": "FETCH_FORCED",
        "reason": "Explicit force_refresh flag requested.",
        "provider_priority": [
          "espn-fifa-worldcup",
          "soccerdata-espn-worldcup",
          "sportdb-worldcup"
        ],
        "force_refresh": true
      },
      {
        "capability": "current_form",
        "decision": "FETCH_FORCED",
        "reason": "Explicit force_refresh flag requested.",
        "provider_priority": [
          "espn-fifa-worldcup"
        ],
        "force_refresh": true
      },
      {
        "capability": "detailed_metrics",
        "decision": "FETCH_FORCED",
        "reason": "Explicit force_refresh flag requested.",
        "provider_priority": [
          "espn-fifa-worldcup",
          "soccerdata-espn-worldcup"
        ],
        "force_refresh": true
      }

FIRST_40_LINES_END
PRE_FIX_RAW_END reports/football_data_foundation/live_validation/world-cup-2026/2026-06-20_2026-06-21/event_enrichment_results.json
```
