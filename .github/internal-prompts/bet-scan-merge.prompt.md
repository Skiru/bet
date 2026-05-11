---
description: "Post-scan merge — combines all sport scan results, validates coverage, runs enrichment, builds shortlist. Final gate before deep analysis."
mode: agent
agent: bet-scanner
---

> **PERMANENT RULES (from copilot-instructions.md §NON-NEGOTIABLE):**
> R3 NO AUTO-REJECTION: ALL events from all scanners merge into shortlist. R7 TOURNAMENT PROTECTION: Verify tournament matches present. R10 STATS-FIRST: Events without odds included. R13 MAJOR DOMESTIC LEAGUE PROTECTION: Verify protected domestic leagues present (Brasileirão, MLS, Liga MX, CSL, J-League, K-League, Saudi Pro, ISL, etc.). If any protected league is active today but missing → scan coverage FAILED → re-scan.

# SCAN MERGE + ENRICHMENT — Final Assembly

> **YOUR ANALYTICAL VALUE:** You don't just merge event lists. You assess DATA COMPLETENESS across the merge — which sports lost events during dedup, which enrichment sources failed silently, and whether the final shortlist has enough STATISTICAL DEPTH for S3 analysis. A script can merge 8000 events. Only YOU can spot that volleyball went from 250 scan events to 15 in the shortlist because all its events lacked kickoff times and got filtered as garbage — requiring a targeted re-scan with a different source.

## MANDATORY: Agent Intelligence Protocol

> **⛔ Follow `agent-execution-protocol.instructions.md` for EVERY script execution.**
> Run script → read FULL output → extract metrics → `sequentialthinking` → structured verdict.
> Raw output paste = YOUR RESPONSE WILL BE REJECTED by the orchestrator.

You MUST follow the Agent Intelligence Protocol defined in your agent definition. Specifically:
1. Use `sequentialthinking` to plan merge strategy and evaluate data completeness
2. Read `/memories/repo/pipeline-lessons-learned.md` — check for known merge/enrichment failures
3. Use `todo` to track merge phases (merge → enrich → validate → shortlist)
4. Write coverage and data quality observations to `/memories/session/`
5. Self-validate: all sport results merged, enrichment yield >60%, shortlist data quality assessed per R14

Run after all sport scanners complete. Merges results, enriches with APIs, validates coverage, produces shortlist.

## STEP 1: Merge All Sport Results

```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:. python3 scripts/ingest_scan_stats.py --verbose
```

Then validate with:
```bash
python3 scripts/validate_phase.py --date {YYYY-MM-DD} --phase data
```

## STEP 2: Run Enrichment Chain

```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:.

# Stats enrichment
python3 scripts/fetch_api_stats.py --date {YYYY-MM-DD}

# Odds from multiple sources
python3 scripts/fetch_odds_multi.py

# Weather for outdoor sports
python3 scripts/fetch_weather.py --date {YYYY-MM-DD}

# Ingest scan data into stats cache
python3 scripts/ingest_scan_stats.py --verbose 2>&1
```

**If fetch_api_stats fails:**
- Check if API rate limits exhausted: `cat scripts/api_clients/.rate_limit_state/*.json 2>/dev/null`
- ESPN is free/unlimited — should always work
- API-Sports (api_football, etc.) has 100/day shared limit

**If fetch_odds_multi fails:**
- STATS-FIRST mode: odds are OPTIONAL. Proceed without them.
- User checks Betclic app manually for odds.

## STEP 3: Generate Analysis Artifacts

```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:.

# Aggregation and analysis pool now handled by build_shortlist.py
python3 scripts/build_shortlist.py --date {YYYY-MM-DD} --stats-first --verbose 2>&1

# Generate market matrix (STATS-FIRST mode)
python3 scripts/generate_market_matrix.py --date {YYYY-MM-DD} --stats-first

# Build shortlist
python3 scripts/build_shortlist.py --date {YYYY-MM-DD} --stats-first --verbose 2>&1
```

Parse the `AGENT_SUMMARY:{json}` line from `build_shortlist.py` and `ingest_scan_stats.py` output — they contain candidate counts, sport distribution, and data quality tiers.

## STEP 4: Validate Final Outputs

```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:. python3 scripts/validate_phase.py --date {YYYY-MM-DD} --phase data
```

Also use `read_file` tool to inspect key output files:
- `betting/data/{YYYY-MM-DD}_s2_shortlist.json` — check event count, sport diversity
- `betting/data/market_matrix_{YYYY-MM-DD}.json` — check artifact exists
- `betting/data/scan_summary.json` — overall scan health

## STEP 5: Self-Heal Missing Artifacts

**If shortlist missing:**
```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:.
python3 scripts/build_shortlist.py --date {YYYY-MM-DD} --stats-first --force
```

**If market matrix missing:**
```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:.
python3 scripts/generate_market_matrix.py --date {YYYY-MM-DD} --stats-first --force
```

**If shortlist has <50 events:**
- This may be correct if few events today
- Check scan_summary total — if raw scan had 300+, aggregation thresholds may be too strict
- Proceed with what's available — user decides from market matrix

**If any core sport has 0 events in shortlist:**
- Check which sports are missing
- Seasonal gaps are acceptable for some sports on certain days
- If a Tier 1 sport (football, volleyball, basketball, tennis, hockey) is missing, that's a real problem — check its scanner report

## TROUBLESHOOTING

| Error | Cause | Fix |
|-------|-------|-----|
| `build_shortlist.py` crashes | Missing dependency file | Check scan_summary.json exists first |
| `generate_market_matrix.py` no output | Zero events after filtering | Add `--stats-first` to lower threshold |
| `build_shortlist.py` produces 0 | No events pass safety score | Use `--force` to include all events |
| `fetch_api_stats.py` timeout | API slow | Proceed without — scan data is primary |
| `ingest_scan_stats.py` error | scan_summary format mismatch | Check if using new sport-grouped format |

## SUCCESS CRITERIA

Merge is COMPLETE when:
1. `scan_summary.json` exists and has data
2. `{date}_s2_shortlist.json` exists with ≥ 30 events
3. `market_matrix_{date}.json` and `.md` exist
4. `decision_matrix_{date}.md` exists
5. Stats cache has data for at least 4 sports

Report completion to orchestrator with: event counts, sport breakdown, any gaps documented.
