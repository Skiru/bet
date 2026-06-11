# Pipeline Contracts — S0–S8 Canonical Mapping

> Source of truth for all pipeline phases, inputs, outputs, and delegation.
> Every active doc, prompt, and validator must reference this contract.

## S0 – Settlement & Learning (previous day)

| Field | Value |
|-------|-------|
| Scripts | `settle_on_finish.py`, `analyze_betclic_learning.py`, `evaluate_decisions.py`, `data_rotation.py`, `build_league_profiles.py` |
| Input | Previous day's betting data |
| Output DB | `decision_outcomes`, `settled bets`, `betclic_learning_summary`, `league_profiles` |
| Delegation | bet-settler (settlement + learning), bet-db-analyst (rotation) |
| Gate | S0.1 (previous day settled), S0.2 (decisions evaluated), S0.3 (learning current) |

## S1 – Discovery & Market Matrix

| Step | Script | Output |
|------|--------|--------|
| S1 scan | `discover_events.py` | `scan_results`, `fixtures` DB; `{date}_s1_events.json` |
| S1 matrix | `generate_market_matrix.py` | `market_matrix_{date}.json` (canonical market matrix producer) |
| S1b tipster | `tipster_aggregator.py` | `tipster_picks`, `tipster_consensus` DB |
| S1e shortlist | `build_shortlist.py` | `pipeline_candidates` DB; `{date}_s2_shortlist.json` |

- `generate_market_matrix.py` is the **canonical producer** of market matrix
- `build_shortlist.py` requires `market_matrix_{date}.json` unless `--allow-fixture-only-fallback` (degraded)
- D5 gate: fails on `source=fallback` or zero market coverage
- S1e audit must compare per-sport survival across `fixtures` DB → `market_matrix_events`/JSON → `pipeline_candidates`
- If a sport is present upstream and absent downstream, the pipeline must expose the first loss point and reason (kickoff filter, sport canonicalization, garbage filter, fixture-only filter, comp-score, dedup, cap)
- `selection_telemetry` in shortlist JSON is a required audit surface when present

## S2 – Tipster Cross-Reference

| Field | Value |
|-------|-------|
| Scripts | `tipster_xref.py`, `run_scrapers.py`, `data_enrichment_agent.py` |
| Input | `tipster_picks` DB, `pipeline_candidates` DB |
| Output | `pipeline_candidates.tipster_count`, `pipeline_candidates.tipster_support_json` |
| Canonical source | **DB `pipeline_candidates`** where `tipster_count > 0` |
| D7 gate | FAIL if 0 tipster_picks; FAIL if picks exist but 0 candidates matched; WARN if coverage <10% |

**Hard stop**: Raw `tipster_picks` alone is NOT sufficient. Candidate-level cross-reference required.

- `tipster_xref.py` must treat corrupted `tipster_picks` identities (odds fragments, page chrome, league text in team fields) as a source-quality defect and surface the first loss point explicitly.
- S2 audits must compare `tipster_picks` breadth by sport against `pipeline_candidates` breadth by sport; uncovered sports are a source-gap unless the shortlist sport count itself is zero.
- `pipeline_candidates` DB remains canonical. JSON shortlist mutation is compatibility-only and must not hide DB-vs-JSON parity issues.
- S2 reruns must clear prior `pipeline_candidates.tipster_count` / `tipster_support_json` for that date before re-matching. Stale positives after a rerun are a contract break.

## S2.5 – Shortlist-Scoped Enrichment

- Default enrichment scope is the **shortlist working set** (`pipeline_candidates` DB, JSON only as fallback). Broad fixture-level enrichment is degraded fallback and must be labeled as such.
- Team readiness is sport-aware. Presence of any `team_form` rows is not sufficient if the sport still lacks required rich keys or only has baseline-only coverage.
- Warehouse success from `run_scrapers.py` is upstream evidence only. S3 readiness depends on shortlist-visible `team_form`/rich coverage, not on `league_profiles` row counts alone.
- If a sport survives shortlist but loses usable depth in S2/S2.5, the pipeline must report the first loss point as one of: source acquisition, identity resolution, shortlist-scope drift, unsupported provider branch, bridge gap, or genuine external data gap.
- S2.6-S2.9 combo enrichers must default to shortlist-scoped team counts. Fixture-wide counts are degraded fallback telemetry and must not be presented as readiness.
- Budgeted enrichers must report team-level `attempted`, `completed`, `failed`, and `skipped` counts consistently; silently dropping unprocessed shortlist teams under budget exhaustion is a telemetry defect.

## S3 – Deep Stats Analysis

| Field | Value |
|-------|-------|
| Scripts | `deep_stats_report.py`, `normalize_stats.py`, `compute_safety_scores.py` |
| Input | `pipeline_candidates` DB |
| Output DB | `analysis_results` (primary), `analysis_raw_data` |
| Output files | `{date}_s3_deep_stats.json` (compatibility artifact) |
| S3 JSON parity | DB and JSON must match for production readiness |

## S4 – Odds & EV Pricing

| Field | Value |
|-------|-------|
| Scripts | `odds_evaluator.py` |
| Input | `analysis_results` DB |
| Output | EV/odds enrichment in `analysis_results.stats_summary_json` |

## S5 – Context Analysis

| Field | Value |
|-------|-------|
| Scripts | `context_checks.py` |
| Input | `analysis_results` DB |
| Output | Context flags in `analysis_results.stats_summary_json` |

## S6 – Upset Risk

| Field | Value |
|-------|-------|
| Scripts | `upset_risk.py` |
| Input | `analysis_results` DB |
| Output | Upset risk in `analysis_results.stats_summary_json` |

**Storage rule**: S4–S6 all write to `analysis_results.stats_summary_json`. No separate `upset_scores` or `context_flags` tables.

## S7 – Gate & Validation

| Sub-step | Script | Output |
|----------|--------|--------|
| S7 gate | `gate_checker.py` | `gate_results` DB; `{date}_s7_gate_results.json` |
| S7.5 Betclic | Manual sidecar (no default scrape) | `betclic_market_validation_{date}.json` |
| S7.6 repeats | `check_48h_repeats.py` | Repeat loss handoff |

**Gate status**: `APPROVED`, `EXTENDED`, `REJECTED` (bucket status)
**Advisory tier**: `STRONG`, `MODERATE`, `WEAK`, `FLAGGED` (confidence)
**Gate score**: 20-point checklist (1–20). Negative EV = hard reject.

## S8 – Coupon Build

| Field | Value |
|-------|-------|
| Scripts | `coupon_builder.py`, `validate_coupons.py`, `generate_coupon_pdf.py` |
| Input | `gate_results` DB, Betclic sidecar or DB fallback observations |
| Output | Coupon JSON/MD/PDF in `betting/coupons/` |
| Canonical input | `gate_results` DB primary; S7.5 sidecar preferred for Betclic validation, DB `betclic_markets` fallback allowed when sidecar missing |
| No-Bet | Valid outcome when 0 qualifying picks — explicit `NO_BET` with reasons |

## Delegation Map

| Agent | Primary Steps |
|-------|--------------|
| bet-settler | S0 (settlement, learning, decisions) |
| bet-scanner | S1 + S1e (discovery, matrix, shortlist coverage audit) |
| bet-scout | S2 (tipster consensus, cross-reference) |
| bet-enricher | S2.3/S2.5 (warehouse, enrichment readiness) |
| bet-statistician | S3 analysis, S7 gate statistics |
| bet-valuator | S4 odds/EV pricing |
| bet-challenger | S5/S6/S7 bear cases, gate audit |
| bet-builder | S8 coupon construction |
| bet-reconciler | Conflict resolution (P5 tri-agent conflicts) |
| bet-db-analyst | DB health, schema, migration readiness |

## Execution Order

```
S0 → S1 → S1 matrix → S1b → S1e → S2 → S2.3 → S2.5 → gate(data) → S3 → S4 → S5 → S6 → gate(analysis) → S7 → S7.5 → S7.6 → gate(build) → S8
```

22 steps total. Each step must complete before the downstream gate can pass.

## Key Design Decisions

1. **DB is canonical** for candidate state (S1e→S8). JSON artifacts are compatibility/render helpers.
2. **Market matrix** is produced by `generate_market_matrix.py`, NOT `discover_events.py`.
3. **S2 requires candidate-level xref**. Raw tipster_picks alone fails the data gate.
4. **Fallback matrix** is always degraded. D5 fails on `source=fallback`.
5. **Betclic is never scraped by default inside S8**. S7.5 produces the preferred sidecar; if it is missing but `betclic_markets` DB observations exist for the same date, S8 may consume the DB fallback and keep picks conditional.
6. **Negative EV is hard-rejected** in S7 for coupon safety.
7. **20-point gate** is canonical (gates 1–20). References to 18-point are stale.
8. **Dry-run uses temp file DB** with schema initialized. Never mutates production DB.
