---
description: "Beast Mode full scan orchestration: Sofascore API scan → ingest → enrich → shortlist. Single unified script, no per-sport agents needed."
mode: agent
agent: bet-scanner
---

> **PERMANENT RULES:** R7 TOURNAMENT PROTECTION. R8 MINOR LEAGUE VALUE. R9 SELF-HEALING.

# BEAST MODE SCAN ORCHESTRATION

> **YOUR ANALYTICAL VALUE:** You assess SOURCE QUALITY — Sofascore API returns events for all 5 sports but deep enrichment coverage varies. You determine whether form/H2H/odds depth is sufficient for S3 statistical analysis, flag sports with thin data, and ensure enrichment fills gaps.

## ⛔ Follow `agent-execution-protocol.instructions.md` for EVERY script execution.

## PHASE 1: BEAST MODE SCAN

```bash
python3 scripts/scan_events.py --date {YYYY-MM-DD} --verbose 2>&1
```

Single script scans ALL 5 sports via Sofascore REST API with deep enrichment.
Expected: 1000-2000 events, 30-40% deep-enriched, ~15 min runtime.

**Validation Gates:**
- All 5 sports represented
- Total events > 300
- No Tier 1 sport at ZERO
- Error rate < 5%

## PHASE 2: INGEST + ENRICH

```bash
python3 scripts/ingest_scan_stats.py --date {YYYY-MM-DD} --verbose 2>&1
python3 scripts/fetch_odds_multi.py --verbose 2>&1
python3 scripts/fetch_weather.py --date {YYYY-MM-DD}
```

## PHASE 3: BUILD SHORTLIST

```bash
python3 scripts/generate_market_matrix.py --date {YYYY-MM-DD} --stats-first
python3 scripts/build_shortlist.py --date {YYYY-MM-DD} --stats-first --verbose 2>&1
```

## PHASE 4: VALIDATE + HANDOFF

```bash
python3 scripts/db_report.py --report scan --date {YYYY-MM-DD}
python3 scripts/db_report.py --report quality
```

Report aggregate metrics and proceed to next pipeline step.
