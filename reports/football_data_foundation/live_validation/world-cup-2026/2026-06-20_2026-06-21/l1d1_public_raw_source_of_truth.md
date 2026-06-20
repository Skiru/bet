# Live Validation L1D1 Public Raw Source of Truth Audit Report
**Exact SHA:** `841926ed754c770d3d556ad1055597059e59d361`
**Conclusion:** `PUBLIC_RAW_MATCHES_LOCAL_BLOB_AND_REVIEWABLE`
**Detail:** All hashes match and all files meet the reviewability / line-ending thresholds.

## 1. Local-vs-Public SHA256 Comparison Table
| Path | Local SHA256 | Public SHA256 | Hashes Match? |
|---|---|---|---|
| `src/bet/enrichment/football_data_foundation/live_validation.py` | `3b0aca13412728c8ec62aa137872b32c3441ca7ea90c304b6dffba59ef742173` | `3b0aca13412728c8ec62aa137872b32c3441ca7ea90c304b6dffba59ef742173` | **YES** |
| `tests/enrichment/football_data_foundation/test_live_validation.py` | `a43f6bb2a98e4bbb42c99f5f2ea59bcc432d32fbce77d8256f22059f350503a6` | `a43f6bb2a98e4bbb42c99f5f2ea59bcc432d32fbce77d8256f22059f350503a6` | **YES** |
| `reports/football_data_foundation/live_validation/world-cup-2026/2026-06-20_2026-06-21/validation_summary.md` | `76276ea4d9db2b473ea6cf09e839778d23a5ab73927de30941aec0b3c0074608` | `76276ea4d9db2b473ea6cf09e839778d23a5ab73927de30941aec0b3c0074608` | **YES** |
| `reports/football_data_foundation/live_validation/world-cup-2026/2026-06-20_2026-06-21/event_enrichment_results.json` | `838de575299e1e6382b6bda0e09a02171f6b8b30db05573caa8e0e6adaaa945b` | `838de575299e1e6382b6bda0e09a02171f6b8b30db05573caa8e0e6adaaa945b` | **YES** |
| `reports/football_data_foundation/live_validation/world-cup-2026/2026-06-20_2026-06-21/freshness_results.json` | `420d1b94598544297a52caa49575cb953c203738214f6f0d0cdf30486337a98a` | `420d1b94598544297a52caa49575cb953c203738214f6f0d0cdf30486337a98a` | **YES** |
| `reports/football_data_foundation/live_validation/world-cup-2026/2026-06-20_2026-06-21/canonical_mapping_results.json` | `4439e57af4191e44ff158820c8dab4ed7b95c8dd325a62475d6e71e95c9bb45e` | `4439e57af4191e44ff158820c8dab4ed7b95c8dd325a62475d6e71e95c9bb45e` | **YES** |
| `reports/football_data_foundation/live_validation/world-cup-2026/2026-06-20_2026-06-21/temp_sqlite_snapshot.json` | `375342740959497962bf7c695c2666e57b1e6e86c1bec4561ad503665df92314` | `375342740959497962bf7c695c2666e57b1e6e86c1bec4561ad503665df92314` | **YES** |
| `reports/football_data_foundation/live_validation/world-cup-2026/2026-06-20_2026-06-21/validation_manifest.json` | `59959f0c4609fb85d49d107fa4440c437bd9b6fafbc8c7eb42dda97d0921107f` | `59959f0c4609fb85d49d107fa4440c437bd9b6fafbc8c7eb42dda97d0921107f` | **YES** |
| `reports/football_data_foundation/live_validation/world-cup-2026/2026-06-20_2026-06-21/validation_manifest.sha256` | `c310db73562ef883f8f4cfa4fcb80629194f9d5360dff38377724c74f31e1454` | `c310db73562ef883f8f4cfa4fcb80629194f9d5360dff38377724c74f31e1454` | **YES** |

## 2. Byte Metrics & Reviewability Table
| Path | Local LF / CR / CRLF / MaxLine | Public LF / CR / CRLF / MaxLine | Reviewable? | Reasons if Unreviewable |
|---|---|---|---|---|
| `src/bet/enrichment/football_data_foundation/live_validation.py` | 1405 / 0 / 0 / 85 | 1405 / 0 / 0 / 85 | **YES** | N/A |
| `tests/enrichment/football_data_foundation/test_live_validation.py` | 511 / 0 / 0 / 87 | 511 / 0 / 0 / 87 | **YES** | N/A |
| `reports/football_data_foundation/live_validation/world-cup-2026/2026-06-20_2026-06-21/validation_summary.md` | 73 / 0 / 0 / 152 | 73 / 0 / 0 / 152 | **YES** | N/A |
| `reports/football_data_foundation/live_validation/world-cup-2026/2026-06-20_2026-06-21/event_enrichment_results.json` | 2398 / 0 / 0 / 97 | 2398 / 0 / 0 / 97 | **YES** | N/A |
| `reports/football_data_foundation/live_validation/world-cup-2026/2026-06-20_2026-06-21/freshness_results.json` | 86 / 0 / 0 / 68 | 86 / 0 / 0 / 68 | **YES** | N/A |
| `reports/football_data_foundation/live_validation/world-cup-2026/2026-06-20_2026-06-21/canonical_mapping_results.json` | 144 / 0 / 0 / 68 | 144 / 0 / 0 / 68 | **YES** | N/A |
| `reports/football_data_foundation/live_validation/world-cup-2026/2026-06-20_2026-06-21/temp_sqlite_snapshot.json` | 2664 / 0 / 0 / 150 | 2664 / 0 / 0 / 150 | **YES** | N/A |
| `reports/football_data_foundation/live_validation/world-cup-2026/2026-06-20_2026-06-21/validation_manifest.json` | 46 / 0 / 0 / 114 | 46 / 0 / 0 / 114 | **YES** | N/A |
| `reports/football_data_foundation/live_validation/world-cup-2026/2026-06-20_2026-06-21/validation_manifest.sha256` | 1 / 0 / 0 / 64 | 1 / 0 / 0 / 64 | **YES** | N/A |

## 3. First 20 Lines Line-by-Line Evidence

### `src/bet/enrichment/football_data_foundation/live_validation.py`
#### Local Git Blob (First 20 Lines)
```
01: from __future__ import annotations
02: 
03: import datetime
04: import hashlib
05: import json
06: import sqlite3
07: import sys
08: import urllib.request
09: from pathlib import Path
10: from typing import Any
11: from zoneinfo import ZoneInfo
12: 
13: import bet.enrichment.football_data_foundation.active_enrichment as active_enrichment
14: from bet.enrichment.football_data_foundation.active_enrichment import (
15:     ActiveEnrichmentOrchestrator,
16:     ActiveEnrichmentRequest,
17: )
18: from bet.enrichment.football_data_foundation.canonical_fixture_resolver import (
19:     CanonicalFixtureResolutionRequest,
20:     resolve_canonical_fixture,
```
#### Public GitHub Raw (First 20 Lines)
```
01: from __future__ import annotations
02: 
03: import datetime
04: import hashlib
05: import json
06: import sqlite3
07: import sys
08: import urllib.request
09: from pathlib import Path
10: from typing import Any
11: from zoneinfo import ZoneInfo
12: 
13: import bet.enrichment.football_data_foundation.active_enrichment as active_enrichment
14: from bet.enrichment.football_data_foundation.active_enrichment import (
15:     ActiveEnrichmentOrchestrator,
16:     ActiveEnrichmentRequest,
17: )
18: from bet.enrichment.football_data_foundation.canonical_fixture_resolver import (
19:     CanonicalFixtureResolutionRequest,
20:     resolve_canonical_fixture,
```

### `tests/enrichment/football_data_foundation/test_live_validation.py`
#### Local Git Blob (First 20 Lines)
```
01: from __future__ import annotations
02: 
03: import hashlib
04: import json
05: from pathlib import Path
06: from typing import Any
07: from unittest.mock import MagicMock, patch
08: 
09: import bet.enrichment.football_data_foundation.active_enrichment as active_enrichment
10: from bet.enrichment.football_data_foundation.active_enrichment import (
11:     ActiveEnrichmentResult,
12: )
13: from bet.enrichment.football_data_foundation.enrichment_freshness import (
14:     EvidenceFreshnessInput,
15:     EvidenceFreshnessPolicy,
16:     evaluate_freshness,
17: )
18: from bet.enrichment.football_data_foundation.live_validation import run_live_validation
19: 
20: 
```
#### Public GitHub Raw (First 20 Lines)
```
01: from __future__ import annotations
02: 
03: import hashlib
04: import json
05: from pathlib import Path
06: from typing import Any
07: from unittest.mock import MagicMock, patch
08: 
09: import bet.enrichment.football_data_foundation.active_enrichment as active_enrichment
10: from bet.enrichment.football_data_foundation.active_enrichment import (
11:     ActiveEnrichmentResult,
12: )
13: from bet.enrichment.football_data_foundation.enrichment_freshness import (
14:     EvidenceFreshnessInput,
15:     EvidenceFreshnessPolicy,
16:     evaluate_freshness,
17: )
18: from bet.enrichment.football_data_foundation.live_validation import run_live_validation
19: 
20: 
```

### `reports/football_data_foundation/live_validation/world-cup-2026/2026-06-20_2026-06-21/validation_summary.md`
#### Local Git Blob (First 20 Lines)
```
01: # FIFA World Cup 2026 Scanner Window Live Validation
02: 
03: - **Phase ID:** `FOOTBALL_DATA_FOUNDATION_L1_SCANNER_WINDOW_LIVE_VALIDATION_WORLD_CUP_2026_NO_ACTIVATION`
04: - **Validation Time:** `2026-06-20T18:10:20.260829+00:00`
05: - **Selected Events Count:** `6` / 6
06: - **Coverage Status:** `complete`
07: - **Manifest Sidecar Hash Check:** `validation_manifest.sha256` sidecar exists and is verified
08: 
09: ## Selected Events
10: 
11: | Scanner Event ID | Provider Event ID | Match Name | Kickoff Local | Status |
12: |---|---|---|---|---|
13: | `scanner-worldcup-20260620-20260621-760447` | `760447` | **Netherlands vs Sweden** | `2026-06-20T19:00:00+02:00` | `STATUS_HALFTIME` |
14: | `scanner-worldcup-20260620-20260621-760448` | `760448` | **Germany vs Ivory Coast** | `2026-06-20T22:00:00+02:00` | `STATUS_SCHEDULED` |
15: | `scanner-worldcup-20260620-20260621-760446` | `760446` | **Ecuador vs Curaçao** | `2026-06-21T02:00:00+02:00` | `STATUS_SCHEDULED` |
16: | `scanner-worldcup-20260620-20260621-760449` | `760449` | **Tunisia vs Japan** | `2026-06-21T06:00:00+02:00` | `STATUS_SCHEDULED` |
17: | `scanner-worldcup-20260620-20260621-760453` | `760453` | **Spain vs Saudi Arabia** | `2026-06-21T18:00:00+02:00` | `STATUS_SCHEDULED` |
18: | `scanner-worldcup-20260620-20260621-760451` | `760451` | **Belgium vs Iran** | `2026-06-21T21:00:00+02:00` | `STATUS_SCHEDULED` |
19: 
20: ## Enrichment Results
```
#### Public GitHub Raw (First 20 Lines)
```
01: # FIFA World Cup 2026 Scanner Window Live Validation
02: 
03: - **Phase ID:** `FOOTBALL_DATA_FOUNDATION_L1_SCANNER_WINDOW_LIVE_VALIDATION_WORLD_CUP_2026_NO_ACTIVATION`
04: - **Validation Time:** `2026-06-20T18:10:20.260829+00:00`
05: - **Selected Events Count:** `6` / 6
06: - **Coverage Status:** `complete`
07: - **Manifest Sidecar Hash Check:** `validation_manifest.sha256` sidecar exists and is verified
08: 
09: ## Selected Events
10: 
11: | Scanner Event ID | Provider Event ID | Match Name | Kickoff Local | Status |
12: |---|---|---|---|---|
13: | `scanner-worldcup-20260620-20260621-760447` | `760447` | **Netherlands vs Sweden** | `2026-06-20T19:00:00+02:00` | `STATUS_HALFTIME` |
14: | `scanner-worldcup-20260620-20260621-760448` | `760448` | **Germany vs Ivory Coast** | `2026-06-20T22:00:00+02:00` | `STATUS_SCHEDULED` |
15: | `scanner-worldcup-20260620-20260621-760446` | `760446` | **Ecuador vs Curaçao** | `2026-06-21T02:00:00+02:00` | `STATUS_SCHEDULED` |
16: | `scanner-worldcup-20260620-20260621-760449` | `760449` | **Tunisia vs Japan** | `2026-06-21T06:00:00+02:00` | `STATUS_SCHEDULED` |
17: | `scanner-worldcup-20260620-20260621-760453` | `760453` | **Spain vs Saudi Arabia** | `2026-06-21T18:00:00+02:00` | `STATUS_SCHEDULED` |
18: | `scanner-worldcup-20260620-20260621-760451` | `760451` | **Belgium vs Iran** | `2026-06-21T21:00:00+02:00` | `STATUS_SCHEDULED` |
19: 
20: ## Enrichment Results
```

### `reports/football_data_foundation/live_validation/world-cup-2026/2026-06-20_2026-06-21/event_enrichment_results.json`
#### Local Git Blob (First 20 Lines)
```
01: [
02:   {
03:     "profile_id": "world-cup-2026",
04:     "scanner_event_id": "scanner-worldcup-20260620-20260621-760447",
05:     "canonical_match_identity": {
06:       "home_team": "Netherlands",
07:       "away_team": "Sweden"
08:     },
09:     "status": "ENRICHED_COMPLETE",
10:     "fetch_decisions": [
11:       {
12:         "capability": "current_discovery",
13:         "decision": "FETCH_FORCED",
14:         "reason": "Explicit force_refresh flag requested.",
15:         "provider_priority": [
16:           "espn-fifa-worldcup",
17:           "soccerdata-espn-worldcup",
18:           "sportdb-worldcup"
19:         ],
20:         "force_refresh": true
```
#### Public GitHub Raw (First 20 Lines)
```
01: [
02:   {
03:     "profile_id": "world-cup-2026",
04:     "scanner_event_id": "scanner-worldcup-20260620-20260621-760447",
05:     "canonical_match_identity": {
06:       "home_team": "Netherlands",
07:       "away_team": "Sweden"
08:     },
09:     "status": "ENRICHED_COMPLETE",
10:     "fetch_decisions": [
11:       {
12:         "capability": "current_discovery",
13:         "decision": "FETCH_FORCED",
14:         "reason": "Explicit force_refresh flag requested.",
15:         "provider_priority": [
16:           "espn-fifa-worldcup",
17:           "soccerdata-espn-worldcup",
18:           "sportdb-worldcup"
19:         ],
20:         "force_refresh": true
```
