# S7 Hard Approval Blocker Inventory — 2026-06-28

This inventory documents all run artifacts located from the failed live session `TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A` on 2026-06-28.

## Session Run Metadata
- **Orchestrator ID**: pipeline_orchestrator_a
- **Session ID**: TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A
- **Betting Day**: 2026-06-28
- **Runtime Mode**: LIVE_SHADOW
- **Status**: BLOCK (Blocked at Step S7)

## Artifact Inventory

| Artifact Type | File Path | Status / Verdict |
|---|---|---|
| **Run Summary** | `/tmp/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/run_summary.json` | Captured BLOCK at S7 |
| **S0-S6 Evidence** | `/tmp/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/pipeline_runs/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/artifacts/` | S0.json, S1.json, S2.json, S3.json, S4.json, S6.json exists |
| **S1 Discovery** | `/tmp/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/data/market_matrix_2026-06-28.json` | Discovery market matrix |
| **S2 Shortlist** | `/tmp/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/data/2026-06-28_s2_shortlist.json` | 2 candidates shortlisted (football) |
| **S2 consensus** | `/tmp/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/data/2026-06-28_tipster_consensus.json` | Consensus JSON with 1 tipster |
| **S3 Deep Stats** | `/tmp/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/data/2026-06-28_s3_deep_stats.json` | Deep stats report JSON |
| **S3 Stats MD** | `/tmp/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/data/2026-06-28_s3_deep_stats.md` | Deep stats markdown report |
| **S4 Value Output** | `/tmp/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/data/2026-06-28_s4_valuation_candidates.json` | Valuation candidates (2 entries) |
| **S4 Odds Snapshot**| `/tmp/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/data/odds_api_snapshot.json` | Odds snapshot JSON |
| **S4 Odds Multi** | `/tmp/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/data/odds_multi_sources.json` | Multi-source odds JSON |
| **S5 Risk Output** | N/A | S5 execution mode was `agent_artifact`, no standalone output in run folder |
| **S6 Repeat Guard** | `/tmp/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/data/repeat_loss_handoff_2026-06-28.json` | Repeats checking handoff |
| **S7 Gate Output (JSON)**| `/tmp/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/data/2026-06-28_s7_gate_results.json` | Failure analysis (0 approved, 1 extended, 1 rejected) |
| **S7 Gate Output (MD)**| `/tmp/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/data/2026-06-28_s7_gate_results.md` | Markdown format of S7 results |
| **S7b Output** | N/A | Not produced (Blocked at S7) |
| **S7 stdout log** | `/tmp/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/logs/S7_stdout.log` | Capture of gate_checker run output |
| **S7 stderr log** | `/tmp/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/logs/S7_stderr.log` | Empty/no major errors (except return code 1) |
| **Daily Ledger** | `/tmp/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/daily_session_ledger.jsonl` | Ledger logging 2 candidate rejections |
| **Rich Coupon Package**| `/tmp/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/rich_coupon_package_report.json` | Status: FAIL, NO_BET package created |
| **Rich Coupon JSON** | `/tmp/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/rich_packages/2026-06-28_rich_coupon_package.json` | NO_BET_PACKAGE |
| **Rich Coupon MD** | `/tmp/2026-06-28/TODAY_FULL_LIVE_RICH_MANUAL_COUPON_SESSION_A/rich_packages/2026-06-28_rich_coupon_package.md` | Analysis summary & operator screening checklist |
