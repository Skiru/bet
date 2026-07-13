# L2A Public Raw Reviewability Audit

This report documents the public raw reviewability of the Football Data Foundation L2A source and report files, checking them against their local representations.

| File Path | Public LF | Public CR | Public CRLF | Public Max Line | Local LF | Local CR | Local CRLF | Local Max Line | Reviewable | Contradiction |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `src/bet/enrichment/football_data_foundation/source_admission_benchmark.py` | 665 | 0 | 0 | 136 | 665 | 0 | 0 | 136 | Yes | No |
| `src/bet/enrichment/football_data_foundation/source_probe_runner.py` | 432 | 0 | 0 | 127 | 432 | 0 | 0 | 127 | Yes | No |
| `src/bet/enrichment/football_data_foundation/source_probe_contracts.py` | 32 | 0 | 0 | 100 | 32 | 0 | 0 | 100 | Yes | No |
| `tests/enrichment/football_data_foundation/test_source_admission_benchmark.py` | 177 | 0 | 0 | 126 | 177 | 0 | 0 | 126 | Yes | No |
| `reports/football_data_foundation/source_admission_benchmark/05_source_value_scorecard.json` | 757 | 0 | 0 | 63 | 757 | 0 | 0 | 63 | Yes | No |
| `reports/football_data_foundation/source_admission_benchmark/06_admission_decision_matrix.json` | 143 | 0 | 0 | 138 | 143 | 0 | 0 | 138 | Yes | No |
| `reports/football_data_foundation/source_admission_benchmark/07_next_implementation_plan.md` | 13 | 0 | 0 | 176 | 13 | 0 | 0 | 176 | Yes | No |

## Audit Status: **RAW_REVIEWABILITY_PASSED**

All files meet the mandated thresholds:
- Python files have LF >= 30, with specific targets met (`source_admission_benchmark.py` LF >= 300, `source_probe_runner.py` LF >= 200).
- JSON/Markdown reports are multi-line and not minified.
- No CR or CRLF line endings exist.
- Max line length constraints are strictly respected.
- No contradictions exist between the local files and GitHub's public raw state.
