---
name: scan-day
description: "Scan: API-first discovery (SofaScore + Odds API + API-Football) → all 5 sports → ingest → enrich → shortlist. Fully autonomous."
agent: bet-scanner
argument-hint: "run_date=2026-05-12" or just run for today
---

# SCAN DAY — API-First Discovery

**YOU MUST COMPLETE THIS ENTIRE PIPELINE WITHOUT ASKING THE USER ANYTHING.**

## Architecture

```
STEP 1: API-first discovery (all 5 sports, ~30s via SofaScore + Odds API + API-Football)
    → {date}_s1_events.json + DB (fixtures, scan_results, teams, competitions, fixture_sources)
STEP 2: Ingest scan data into stats_cache + team_form
STEP 3: Enrichment (odds, weather)
STEP 4: Market matrix + shortlist
```

## Execution

### Step 1: API-First Discovery

```bash
PYTHONPATH=src .venv/bin/python scripts/discover_events.py --date {{run_date}} --verbose 2>&1
```

Discovers ALL 5 sports (football, tennis, basketball, hockey, volleyball) via SofaScore + Odds API + API-Football.
No deep data — that's enrichment's job.
Expected: 1500-2000 events, cross-source dedup merges ~3-5%.

Parse `AGENT_SUMMARY:{json}` for per-sport breakdown, deep_enriched count, errors.

### Step 2: Ingest to Stats Cache

```bash
python3 scripts/ingest_scan_stats.py --date {{run_date}} --verbose 2>&1
```

Transforms discovery data into stats_cache + team_form DB.

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
| Source diversity (≥2 sources for key events) | Advisory |
