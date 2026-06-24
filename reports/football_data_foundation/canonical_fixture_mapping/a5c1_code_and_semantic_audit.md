# Code and Semantic Defect Audit (A5C1)

This audit documents physical code metrics and identified semantic defects in the baseline A5 implementation before applying the corrective hardening in this phase.

## 1. Physical Code Metrics

| File Path | Lines | Max Line Length | Minified | Individually Reviewable |
| :--- | :---: | :---: | :---: | :---: |
| `canonical_fixture_resolver.py` | 375 | 157 | No | Yes |
| `canonical_observation_writer.py` | 379 | 249 | No | Yes |
| `temp_sqlite_harness.py` | 50 | 90 | No | Yes |
| `cli.py` | 253 | 194 | No | Yes |
| `persistence_bridge.py` | 751 | 89 | No | Yes |
| `scanner_bridge.py` | 399 | 97 | No | Yes |
| `test_canonical_fixture_mapping.py` | 308 | 108 | No | Yes |
| `test_production_bridge.py` | 363 | 86 | No | Yes |

*Note: All files are human-readable standard Python, but several modules exceed optimal line lengths or contain hardcoded semantics.*

## 2. Identified Semantic Defects

1. **Hardcoded `"football"` in Generic Paths:** Generic resolver/writer paths hardcode `"football"` for sports_entity or source_entity_reference fields instead of utilizing `scanner_event.sport` or profile-derived sport.
2. **Lack of Freshness and Live-Status Drift Protection:** Evidence packages are reused blindly without checking TTL or live-to-final status transitions (e.g. from `STATUS_SECOND_HALF` to `STATUS_FULL_TIME`).
3. **Weak External ID Verification:** The resolver can silently accept a different `external_id` for an existing source mapping instead of raising an conflict/ambiguity status.
4. **Broad Team Alias Lookup:** Team aliases are resolved broadly across sports/providers without provider or competition context constraints.
5. **Competition Group Label Corruption:** The competitioncountry is stored as a group label (e.g., `Group D`) if country is unknown.
6. **Fixture Fact Duplication without Fact Scope:** General fixture-level facts are copied to both teams' observations without a clear `duplicated_for_schema_team_id_constraint=true` metadata or explicit `fact_scope` classification.
7. **Hardcoded CLI cutoff / proof:** The CLI uses a hardcoded `analysis_cutoff_at` and asserts `real_db_touched = False` without inspecting connections/metadata.
8. **Overstated Schema Sufficiency:** A5 reports complete schema readiness despite deferred production SQLite activation and inactive routing/matrix configurations.
