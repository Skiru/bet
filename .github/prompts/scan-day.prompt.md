---
name: scan-day
description: "Scan: Flashscore + ESPN → all 5 sports → deep enrichment → ingest → shortlist. Fully autonomous."
agent: bet-scanner
argument-hint: "run_date=2026-05-12" or just run for today
---

# SCAN DAY — Flashscore + ESPN

**YOU MUST COMPLETE THIS ENTIRE PIPELINE WITHOUT ASKING THE USER ANYTHING.**

## Architecture

```
STEP 1: Flashscore + ESPN scan (all 5 sports, ~15 min with deep enrichment)
    → global_events_api.json + DB (fixtures, scan_results, teams, competitions)
STEP 2: Ingest scan data into stats_cache + team_form
STEP 3: Enrichment (odds, weather)
STEP 4: Market matrix + shortlist
```

## Execution

### Step 1: Beast Mode Scan

```bash
python3 scripts/scan_events.py --date {{run_date}} --verbose 2>&1
```

Scans ALL 5 sports (football, tennis, basketball, hockey, volleyball) via Flashscore + ESPN fallback.
Deep enrichment fetches form/H2H per event.
Expected: 1000-2000 events, 30-40% deep-enriched.

Parse `AGENT_SUMMARY:{json}` for per-sport breakdown, deep_enriched count, errors.

### Step 2: Ingest to Stats Cache

```bash
python3 scripts/ingest_scan_stats.py --date {{run_date}} --verbose 2>&1
```

Transforms Beast Mode form/H2H/odds into stats_cache + team_form DB.

### Step 3: Enrichment

```bash
python3 scripts/fetch_odds_multi.py --verbose 2>&1
python3 scripts/fetch_weather.py --date {{run_date}}
```

### Step 4: Shortlist

```bash
python3 scripts/generate_market_matrix.py --date {{run_date}} --stats-first
python3 scripts/build_shortlist.py --date {{run_date}} --stats-first --verbose 2>&1
```

## Validation Gates

| Check | Gate |
|-------|------|
| All 5 sports in scan results | Required |
| Total events > 300 | Required |
| Tournament matches present (R7) | Required |
| Protected domestic leagues present (R13) | Required |
| Deep enrichment > 20% | Advisory |
