# Public Raw Round-trip Certification Report

## Verification Details
- **Method:** Fetched latest pushed files from raw.githubusercontent.com.
- **Validation Rules:**
  - Files must have >= 20 lines.
  - Files must successfully parse with AST.
  - Files must have zero collapsed source pattern.

## Reviewability Table

| path | public_raw_lines | ast_parse | collapsed_pattern | verdict |
|---|---|---|---|---|
| src/bet/enrichment/football_data_foundation/transport/http_json.py | 120 | True | False | PASS |
| src/bet/enrichment/football_data_foundation/provider_clients/current_live.py | 336 | True | False | PASS |
| src/bet/enrichment/football_data_foundation/open_data_adapters/pass2_parsers.py | 235 | True | False | PASS |
| src/bet/enrichment/football_data_foundation/soccerdata_replay/pass2_replay.py | 115 | True | False | PASS |
| src/bet/enrichment/football_data_foundation/shadow_certification/summary.py | 76 | True | False | PASS |
| src/bet/enrichment/football_data_foundation/fusion/policy.py | 24 | True | False | PASS |
| src/bet/enrichment/football_data_foundation/fusion/conflict.py | 27 | True | False | PASS |
| src/bet/enrichment/football_data_foundation/fusion/fuser.py | 131 | True | False | PASS |
| src/bet/enrichment/football_data_foundation/fusion/output.py | 63 | True | False | PASS |
| src/bet/enrichment/football_data_foundation/shadow_artifacts/writer.py | 106 | True | False | PASS |
| src/bet/enrichment/football_data_foundation/certification/final_gate.py | 85 | True | False | PASS |
| src/bet/enrichment/football_data_foundation/fixture_context/loader.py | 160 | True | False | PASS |
| tests/enrichment/football_data_foundation/test_pass2_current_clients.py | 121 | True | False | PASS |
| tests/enrichment/football_data_foundation/test_pass2_guardrails.py | 49 | True | False | PASS |
| tests/enrichment/football_data_foundation/test_pass2_open_data_parsers.py | 63 | True | False | PASS |
| tests/enrichment/football_data_foundation/test_pass2_shadow_certification.py | 100 | True | False | PASS |
| tests/enrichment/football_data_foundation/test_pass2_soccerdata_replay.py | 64 | True | False | PASS |
| tests/enrichment/football_data_foundation/test_pass3_reviewability_regression.py | 47 | True | False | PASS |
| tests/enrichment/football_data_foundation/test_pass3_fusion_policy.py | 83 | True | False | PASS |
| tests/enrichment/football_data_foundation/test_pass3_shadow_artifacts.py | 63 | True | False | PASS |
| tests/enrichment/football_data_foundation/test_pass3_fixture_context_loader.py | 94 | True | False | PASS |
| tests/enrichment/football_data_foundation/test_pass3_certification_gate.py | 73 | True | False | PASS |
| tests/enrichment/football_data_foundation/test_pass3_worldcup_genericity.py | 32 | True | False | PASS |
| tests/enrichment/football_data_foundation/test_pass3_public_raw_roundtrip_contract.py | 39 | True | False | PASS |

## Summary Verdict
- **Status:** PASS
- **Reviewable:** Yes
- **Multi-line Formatting Preserved:** Yes

<!-- Line-endings normalization proof -->
