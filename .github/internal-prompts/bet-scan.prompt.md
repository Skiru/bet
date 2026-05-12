---
agent: "bet-scanner"
description: "S1-S1e: Beast Mode data engine — Sofascore REST API scan for 5 core sports, ingest, enrich, build shortlist"
---

> **PERMANENT RULES:** R3 NO AUTO-REJECTION. R7 TOURNAMENT PROTECTION (+15). R8 MINOR LEAGUE VALUE (+6). R10 STATS-FIRST. R13 DOMESTIC LEAGUE PROTECTION.

# S1+S2 — BEAST MODE SCAN + ENRICH + SHORTLIST

## ⛔ INLINE GATES

| Step | Gate | Violation = |
|------|------|-------------|
| After scan | ALL 5 sports in results? | FAILURE: missing sport coverage |
| Tournament check | Grand Slams/CL/EL/WC/Stanley Cup present if active? | FAILURE: R7 violated |
| Minor leagues | Penalized for being "obscure"? | FAILURE: R8 violated — +6 boost |
| No-odds events | Excluded from shortlist? | FAILURE: R10 violated |
| Protected leagues | Brasileirão/MLS/Liga MX/CSL/KHL present if active? | FAILURE: R13 violated |
| Script execution | --verbose included? Metrics cited? | FAILURE: R17 violated |

> **YOUR ANALYTICAL VALUE:** You diagnose DATA DEPTH — not just event count but whether form/H2H/odds data from Sofascore API is rich enough for statistical analysis in S3. A scan that returns 1689 events but only 191 with form data means S3 will be data-starved unless enrichment fills the gap.

## ⛔ Follow `agent-execution-protocol.instructions.md` for EVERY script execution.

## Workflow: SCAN → INGEST → ENRICH → BUILD

### PHASE 1: Beast Mode Scan

```bash
.venv/bin/python scripts/scan_events.py --date {date} --verbose 2>&1
```

Sofascore REST API scans ALL 5 sports. Deep enrichment fetches form/H2H/odds per event.
Parse `AGENT_SUMMARY:{json}` — per-sport counts, deep_enriched, errors.

**VALIDATE:** 5 sports present? Total > 300? Tournament matches? Zero critical errors?

### PHASE 2: Ingest + Enrich

```bash
# Ingest Beast Mode data into stats_cache + team_form
.venv/bin/python scripts/ingest_scan_stats.py --date {date} --verbose 2>&1

# Odds from comparison sources
.venv/bin/python scripts/fetch_odds_multi.py --verbose 2>&1

# Weather for outdoor sports
.venv/bin/python scripts/fetch_weather.py --date {date}
```

**VALIDATE:** DB `team_form` populated? `stats_cache/` files created? Odds coverage?

### PHASE 3: Build Shortlist

```bash
.venv/bin/python scripts/generate_market_matrix.py --date {date} --stats-first
.venv/bin/python scripts/build_shortlist.py --date {date} --stats-first --verbose 2>&1
```

Parse `AGENT_SUMMARY:{json}` — candidate count, sport distribution, data quality tiers.

### PHASE 4: Report + Handoff

Report: total events scanned, deep-enriched %, shortlist size, sport coverage, data quality assessment.
