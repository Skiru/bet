# R3 Pre-Fix Public Raw Audit

| Path | HTTP | Bytes | SHA256 | LF | CR | CRLF | Max Line | Reviewable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| src/bet/enrichment/football_data_foundation/source_admission_benchmark.py | 200 | 67041 | 1161e311... | 1447 | 0 | 0 | 136 | True |
| src/bet/enrichment/football_data_foundation/source_probe_runner.py | 200 | 18819 | cfa35410... | 444 | 0 | 0 | 131 | True |
| src/bet/enrichment/football_data_foundation/source_probe_contracts.py | 200 | 1143 | 1e7e6bf3... | 32 | 0 | 0 | 100 | True |
| tests/enrichment/football_data_foundation/test_source_admission_benchmark.py | 200 | 20298 | 3f91be69... | 454 | 0 | 0 | 132 | True |
| reports/football_data_foundation/source_admission_benchmark_l2b/05_corrected_source_value_scorecard.json | 200 | 14182 | 7366457b... | 365 | 0 | 0 | 111 | True |
| reports/football_data_foundation/source_admission_benchmark_l2b/06_corrected_admission_decision_matrix.json | 200 | 6194 | 61a4a74b... | 143 | 0 | 0 | 136 | True |
| reports/football_data_foundation/source_admission_benchmark_l2b/07_corrected_next_implementation_plan.md | 200 | 3254 | 19c5dae7... | 31 | 0 | 0 | 201 | True |
| reports/football_data_foundation/source_admission_benchmark_l2b/r2_consistency_validation.json | 200 | 1922 | 53b108a4... | 56 | 0 | 0 | 134 | True |
| reports/football_data_foundation/source_admission_benchmark_l2b/l2b_corrected_admission_manifest.json | 200 | 2756 | a78e3552... | 59 | 0 | 0 | 118 | True |

## Details

### `src/bet/enrichment/football_data_foundation/source_admission_benchmark.py`
- **URL**: https://raw.githubusercontent.com/Skiru/bet/df487b2fced1da6bc72a66754a9e2793d8de084d/src/bet/enrichment/football_data_foundation/source_admission_benchmark.py
- **SHA256**: 1161e3115a347e8346db5e6bd1495ecde2f5665dd494c68104cd5d5851ae122b
- **Reviewable**: True
- **First 10 lines**:
```
from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

```

### `src/bet/enrichment/football_data_foundation/source_probe_runner.py`
- **URL**: https://raw.githubusercontent.com/Skiru/bet/df487b2fced1da6bc72a66754a9e2793d8de084d/src/bet/enrichment/football_data_foundation/source_probe_runner.py
- **SHA256**: cfa3541080abf4315b17c3990b646aee50b083beef1b0a33485fef6ad5b313b4
- **Reviewable**: True
- **First 10 lines**:
```
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from bet.enrichment.football_data_foundation.source_probe_contracts import (
    SourceProbeResult,
)

```

### `src/bet/enrichment/football_data_foundation/source_probe_contracts.py`
- **URL**: https://raw.githubusercontent.com/Skiru/bet/df487b2fced1da6bc72a66754a9e2793d8de084d/src/bet/enrichment/football_data_foundation/source_probe_contracts.py
- **SHA256**: 1e7e6bf3d8d1026d5008fc730ba0086a55efeef70cdea7a3a18c2eed7465c967
- **Reviewable**: True
- **First 10 lines**:
```
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceProbeResult:
    source_family: str
    import_status: str  # IMPORT_OK, IMPORT_FAILED
```

### `tests/enrichment/football_data_foundation/test_source_admission_benchmark.py`
- **URL**: https://raw.githubusercontent.com/Skiru/bet/df487b2fced1da6bc72a66754a9e2793d8de084d/tests/enrichment/football_data_foundation/test_source_admission_benchmark.py
- **SHA256**: 3f91be6908b35c99fef0e9a918463af8efcb6a72ae23fc9958da958ba2e2da70
- **Reviewable**: True
- **First 10 lines**:
```
from __future__ import annotations

import json
from pathlib import Path

BENCHMARK_DIR = Path("reports/football_data_foundation/source_admission_benchmark")


def test_inventory_completeness() -> None:
    # All known source families appear in inventory
```

### `reports/football_data_foundation/source_admission_benchmark_l2b/05_corrected_source_value_scorecard.json`
- **URL**: https://raw.githubusercontent.com/Skiru/bet/df487b2fced1da6bc72a66754a9e2793d8de084d/reports/football_data_foundation/source_admission_benchmark_l2b/05_corrected_source_value_scorecard.json
- **SHA256**: 7366457b7810f05c62bc81b48a64efb576874cb6b616764d5c9bcd1cb9d39c82
- **Reviewable**: True
- **First 10 lines**:
```
{
  "schema_version": "2.0",
  "scorecards": [
    {
      "source_family": "espn_live_baseline",
      "l2a_decision": "ADMIT_NEXT_PHASE_CURRENT_SHADOW",
      "l2a_problem": "None",
      "l2b_probe_result": "SUCCESS",
      "proof_level": "REAL_ACCEPTED_ARTIFACT_PROOF",
      "real_value_facts_count": 156,
```

### `reports/football_data_foundation/source_admission_benchmark_l2b/06_corrected_admission_decision_matrix.json`
- **URL**: https://raw.githubusercontent.com/Skiru/bet/df487b2fced1da6bc72a66754a9e2793d8de084d/reports/football_data_foundation/source_admission_benchmark_l2b/06_corrected_admission_decision_matrix.json
- **SHA256**: 61a4a74b382de91ac7ab5ac0de5586ae85a16997f521dd5738e38fe415455a7a
- **Reviewable**: True
- **First 10 lines**:
```
{
  "schema_version": "2.0",
  "decisions": [
    {
      "source_family": "espn_live_baseline",
      "corrected_decision": "ADMIT_NEXT_PHASE_CURRENT_SHADOW",
      "exact_reason": "Official live validation baseline.",
      "next_phase_kind": "current shadow fusion"
    },
    {
```

### `reports/football_data_foundation/source_admission_benchmark_l2b/07_corrected_next_implementation_plan.md`
- **URL**: https://raw.githubusercontent.com/Skiru/bet/df487b2fced1da6bc72a66754a9e2793d8de084d/reports/football_data_foundation/source_admission_benchmark_l2b/07_corrected_next_implementation_plan.md
- **SHA256**: 19c5dae7cd50bcce2ed082784c636ecc4699d37e4dbebbd90928a9651fead4ff
- **Reviewable**: True
- **First 10 lines**:
```
# Football Data Foundation - Corrected L2B Next Implementation Plan

Strict sequence of subsequently scheduled implementation phases based solely on corrected L2B decisions.
The following schedule enforces proof-strength ordered progression, separating synthetic contract validation
and docs-only capabilities from actual implementation readiness.

| Sequence | Source Family | Decision | Next Phase Kind | Rationale |
| :---: | :--- | :--- | :--- | :--- |
| 1 | **espn_live_baseline** | ADMIT_NEXT_PHASE_CURRENT_SHADOW | current shadow fusion | Official live validation baseline. |
| 2 | **statsbomb_open_data** | ADMIT_NEXT_PHASE_HISTORICAL_ENRICHMENT | historical enrichment backfill | Measured offline open data values exist. |
```

### `reports/football_data_foundation/source_admission_benchmark_l2b/r2_consistency_validation.json`
- **URL**: https://raw.githubusercontent.com/Skiru/bet/df487b2fced1da6bc72a66754a9e2793d8de084d/reports/football_data_foundation/source_admission_benchmark_l2b/r2_consistency_validation.json
- **SHA256**: 53b108a4b0f210e16968074ebf06c52388902d124f4e6fff69f95c7b0d1daa94
- **Reviewable**: True
- **First 10 lines**:
```
{
  "schema_version": "2.0",
  "validation_status": "PASSED",
  "checks": [
    {
      "check": "scorecard_completeness",
      "status": "PASSED",
      "details": "All 23 evaluated families are present in the scorecard."
    },
    {
```

### `reports/football_data_foundation/source_admission_benchmark_l2b/l2b_corrected_admission_manifest.json`
- **URL**: https://raw.githubusercontent.com/Skiru/bet/df487b2fced1da6bc72a66754a9e2793d8de084d/reports/football_data_foundation/source_admission_benchmark_l2b/l2b_corrected_admission_manifest.json
- **SHA256**: a78e35528109fc8fa5136ef646f09c9eb5931f2293ca2a6bde21006e841c543a
- **Reviewable**: True
- **First 10 lines**:
```
{
  "schema_version": "2.0",
  "generated_at": "2026-06-21T06:45:19.897729+00:00",
  "phase_id": "FOOTBALL_SOURCE_ADMISSION_L2B_R2_PUBLIC_RAW_AND_DECISION_CONSISTENCY_CORRECTION",
  "no_production_activation": true,
  "no_source_promoted": true,
  "source_families_evaluated": [
    "espn_live_baseline",
    "sportdb",
    "football-data.org",
```

