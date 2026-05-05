---
name: scan-day
description: "Run the complete data engine: 14-sport scan, stats/odds/weather enrichment, live quality validation, self-healing, and analysis-ready shortlist."
agent: bet-scanner
argument-hint: "run_date=2026-05-05" or just run for today
---

# SCAN DAY — Data Engine

Run the complete scan + enrichment + validation pipeline for a betting day.

## What This Does

1. **DISCOVERS** 40,000+ events across 14 sports from 35 domains (232 seed URLs → 1000+ via deep-link discovery)
2. **ENRICHES** every candidate with L10 stats, H2H history, multi-source odds, weather, tipster consensus
3. **VALIDATES** data quality at each phase — checks stats cache depth, odds coverage, sport diversity
4. **SELF-HEALS** gaps — if volleyball/handball cache is empty, runs targeted enrichment
5. **BUILDS** a ranked shortlist of 50-100 events ready for S3 deep statistical analysis

## Inputs

- **run_date** = {{run_date}} (default: today)
- All config loaded from `config/betting_config.json`
- URLs from `config/scan_urls.json` (single source of truth)

## Expected Duration

25-45 minutes for the automated pipeline + 5-10 minutes for validation checks.

## What You Get

After completion, these files are ready for the pipeline:
- `betting/data/scan_summary.json` — Raw scan results (40K+ events)
- `betting/data/{date}_s2_shortlist.json` — Ranked shortlist (50-100 events)
- `betting/data/market_matrix_{date}.md` — All events × all markets
- `betting/data/decision_matrix_{date}.md` — Approve/watchlist/reject decisions
- `betting/data/{date}_s1_scan_report.md` — Data quality report with known gaps

## After Scan

Use `/orchestrate-betting-day` to continue the pipeline from S3 (deep stats → odds → coupons).

<!-- BET:prompt:scan-day:v1 -->
