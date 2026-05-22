---
agent: "bet-scanner"
description: "S1-S1e: Scan data engine — API-first discovery (Odds-API.io + API-Football) for 5 core sports, ingest, enrich, build shortlist"
---

> **PERMANENT RULES:** R3 NO AUTO-REJECTION. R7 TOURNAMENT PROTECTION (+15). R8 MINOR LEAGUE VALUE (+6). R10 STATS-FIRST. R13 DOMESTIC LEAGUE PROTECTION.

# S1+S2 — API-FIRST DISCOVERY + ENRICH + SHORTLIST

## ⛔ INLINE GATES

| Step | Gate | Violation = |
|------|------|-------------|
| After scan | ALL 5 sports in results? | FAILURE: missing sport coverage |
| Tournament check | Grand Slams/CL/EL/WC/Stanley Cup present if active? | FAILURE: R7 violated |
| Minor leagues | Penalized for being "obscure"? | FAILURE: R8 violated — +6 boost |
| No-odds events | Excluded from shortlist? | FAILURE: R10 violated |
| Protected leagues | Brasileirão/MLS/Liga MX/CSL/KHL present if active? | FAILURE: R13 violated |
| Script execution | --verbose included? Metrics cited? | FAILURE: R17 violated |

> **YOUR ANALYTICAL VALUE:** You diagnose COVERAGE BREADTH — not just event count but whether the fixture universe is COMPLETE across all 5 sports, whether cross-source dedup caught duplicates, and whether source diversity (≥2 sources per event) gives confidence in fixture accuracy. Deep data (form/H2H) is handled by enrichment — your job is fixture completeness.

## ⛔ Follow `agent-execution-protocol.instructions.md` for EVERY script execution.

## Workflow: DISCOVER → INGEST → ENRICH → BUILD

### PHASE 1: API-First Discovery

```bash
PYTHONPATH=src .venv/bin/python scripts/discover_events.py --date {date} --verbose 2>&1
```

API-first discovery from Odds-API.io (primary, all 5 sports) + The-Odds-API (secondary, 4 sports w/ odds) + API-Football (tertiary, football). SofaScore adapter disabled (403). No deep data (enrichment handles that).
Parse `AGENT_SUMMARY:{json}` — per-sport counts, source stats, dedup merges, errors.

**VALIDATE:** 5 sports present? Total > 300? odds-api-io responded for all sports? Tournament matches? Dedup reasonable (expect 10-15% merges from football overlap)?

### PHASE 2: Ingest + Enrich

```bash
# Ingest discovery data into stats_cache + team_form
python3 scripts/ingest_scan_stats.py --date {date} --verbose 2>&1

# Odds from comparison sources
python3 scripts/fetch_odds_multi.py --verbose 2>&1

# Weather for outdoor sports
python3 scripts/fetch_weather.py --date {date}
```

**VALIDATE:** DB `team_form` populated? `stats_cache/` files created? Odds coverage?

### PHASE 3: Build Shortlist

```bash
python3 scripts/generate_market_matrix.py --date {date} --stats-first
python3 scripts/build_shortlist.py --date {date} --stats-first --verbose 2>&1
```

Parse `AGENT_SUMMARY:{json}` — candidate count, sport distribution, data quality tiers.

### PHASE 4: Report + Handoff

Report: total events scanned, deep-enriched %, shortlist size, sport coverage, data quality assessment.
