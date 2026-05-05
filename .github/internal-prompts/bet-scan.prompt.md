---
agent: "bet-scanner"
description: "S1: Exhaustive 14-sport event scan with source cross-validation"
---

# S1 — COMPLETE EVENT SCAN

## Required Skills

Load these skills before starting:
- `bet-navigating-sources` — source tiers, fallback chains, sport-specific URLs, blocked sources

## Context (provided by orchestrator)

- **run_date**: The current betting day
- **session**: full/day/night/morning (controls event time window)
- **Event window**: full=06:00→05:59+1, day=06:00→21:59, night=22:00→05:59+1, morning=06:00→14:59
- **14 sports**: football, tennis, basketball, hockey, baseball, volleyball, esports, snooker, darts, table_tennis, handball, mma, padel, speedway

## Workflow

### 1. Pre-Scan: API Fixture Discovery

Check if `run_full_scan_and_prepare.sh` already ran:
1. Read `betting/data/fixtures_{date}.json` — API-discovered fixtures
2. Read `betting/data/analysis_pool_{date}.json` — pre-analyzed events with safety scores
3. Read `betting/data/market_matrix_{date}.json` — consolidated view with odds
4. Use these as FOUNDATION — merge with web-scanned events, don't duplicate

If not yet run: `bash scripts/run_full_scan_and_prepare.sh`

### 2. Per-Sport Scanning

For each of the 14 sports:
1. Open primary source (see sport order table in `bet-navigating-sources` skill)
2. Click into EVERY active tournament/league — NOT just landing page
3. Count ALL matches in betting-day window
4. Record: sport | tournament | match | kickoff CEST | odds | source
5. Cross-validate with secondary source — note discrepancies
6. If source fails → try next in fallback chain

### 3. Tipster Pre-Fetch (§1.5)

Fetch HTML snapshots for: zawodtyper, typersi, sportsgambler, pickswise, betideas using Playwright.

## Output

Save to: `betting/data/{date}_s1_master_events.md`

Sections: Scan Completeness Table (14 rows), Events by Sport (14 sections), Major Tournaments Flagged, Source Failures.

## Self-Verification (V-S1-01 to V-S1-11)

Key gates: all 14 sports listed, ≥50 unique events, ≥6 sports with events, every sport from ≥2 sources.

## Pass/Fail Gate

ALL 11 checks pass → "S1 PASSED" → orchestrator proceeds to S2.

<!-- BET:internal-prompt:bet-scan:v1 -->
