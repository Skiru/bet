---
description: "Post-scan: ingest Beast Mode data, run enrichment, generate market matrix, build shortlist."
mode: agent
agent: bet-scanner
---

> **PERMANENT RULES:** R3 NO AUTO-REJECTION. R7 TOURNAMENT PROTECTION. R10 STATS-FIRST. R13 MAJOR DOMESTIC LEAGUE PROTECTION.

# SCAN MERGE + ENRICHMENT — Beast Mode Post-Processing

> **YOUR ANALYTICAL VALUE:** You assess DATA COMPLETENESS after ingestion — which sports have rich form/H2H from Flashscore, which are data-thin, and whether enrichment filled the gaps. You ensure the shortlist has enough statistical depth for S3 analysis.

## ⛔ Follow `agent-execution-protocol.instructions.md` for EVERY script execution.

## STEP 1: Ingest Beast Mode Data

```bash
python3 scripts/ingest_scan_stats.py --date {YYYY-MM-DD} --verbose 2>&1
```

Transforms scan form/H2H data from `global_events_api.json` into `stats_cache/` JSON files + DB `team_form` table. Parse `AGENT_SUMMARY:{json}`.

## STEP 2: Run Enrichment Chain

```bash
# Odds from multiple comparison sources
python3 scripts/fetch_odds_multi.py --verbose 2>&1

# Weather for outdoor sports
python3 scripts/fetch_weather.py --date {YYYY-MM-DD}
```

**In STATS-FIRST mode:** odds are OPTIONAL. Proceed without them. User checks Betclic app.

## STEP 3: Generate Analysis Artifacts

```bash
# Market matrix
python3 scripts/generate_market_matrix.py --date {YYYY-MM-DD} --stats-first

# Build shortlist
python3 scripts/build_shortlist.py --date {YYYY-MM-DD} --stats-first --verbose 2>&1
```

Parse `AGENT_SUMMARY:{json}` from `build_shortlist.py`.

## STEP 4: Validate Final Outputs

```bash
python3 scripts/db_report.py --report scan --date {YYYY-MM-DD}
python3 scripts/db_report.py --report quality
```

Check: `{YYYY-MM-DD}_s2_shortlist.json` exists, `market_matrix_{YYYY-MM-DD}.json` exists, sport diversity in shortlist.
