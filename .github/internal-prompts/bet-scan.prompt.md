---
agent: "bet-scanner"
description: "S1-S1e: Full data engine — scan 14 sports, enrich with stats/odds/weather, live-validate quality, self-heal gaps, build analysis-ready shortlist"
---

# S1+S2 — SCAN + ENRICH + VALIDATE + SHORTLIST

## Required Skills

Load before starting:
- `bet-navigating-sources` — source tiers, fallback chains, blocked sources, URL formats

## Context (provided by orchestrator)

- **run_date**: `{date}` (today's betting day)
- **session**: `{session}` — full/day/night/morning (controls event time window)
- **14 sports**: football, tennis, basketball, hockey, baseball, volleyball, esports, snooker, darts, table_tennis, handball, mma, padel, speedway

## Workflow: DISCOVER → VALIDATE → ENRICH → VALIDATE → BUILD → VALIDATE

You follow a strict 3-phase workflow with INLINE VALIDATION after each phase. Don't blindly run scripts. Check data quality as you go and fix problems in real-time.

### PHASE 1: Event Discovery

Run the full scan pipeline:
```bash
bash scripts/run_full_scan_and_prepare.sh
```

This takes 25-45 minutes (232 seed URLs → 1000+ via deep-link discovery). If it times out, run sub-steps manually as documented in the agent definition.

**VALIDATE Phase 1** — Run these checks immediately after scan completes:

1. **Event count**: Read `scan_summary.json`, sum all event lists. Gate: ≥ 40,000 events.
2. **URL expansion**: Count keys in scan_summary.json. Gate: ≥ 800 URLs from 232 seeds.
3. **Error triage**: Read `scan_errors.json`. Separate critical errors from ignorable ones (BetExplorer empty pages for niche sports = normal).
4. **Domain spread**: Count unique domains. Gate: ≥ 30 domains.

If gates fail → investigate and fix before proceeding. See Error Triage Playbook in agent definition.

### PHASE 2: Enrichment Validation

The pipeline already ran enrichment in parallel (stats, odds, weather). Now VALIDATE what it produced:

1. **Stats cache health** — Count team files per sport:
   ```bash
   for sport in football tennis basketball volleyball hockey baseball handball; do
     count=$(find betting/data/stats_cache/$sport -maxdepth 1 -name "*.json" 2>/dev/null | wc -l)
     echo "$sport: $count files"
   done
   ```
   Gates: Football ≥100, Tennis ≥100, Basketball ≥10, Hockey ≥10. **Flag volleyball/handball if 0.**

2. **Stats depth** — Sample 2-3 teams per KEY sport, check stat key count:
   - Football should have 28+ keys (ESPN source)
   - Tennis should have at least 3 keys (known gap: only sets_won/games_won/total_sets)
   - Basketball should have 17+ keys
   - If football has <10 keys → ESPN enrichment may have failed

3. **Odds coverage** — Check `odds_multi_sources.json` and `odds_api_snapshot.json` exist. Count events with odds. In STATS-FIRST mode, acknowledge low coverage is expected.

4. **Weather** — Check `weather_{date}.json` exists for outdoor sports.

5. **DB population** — Count fixtures for today's date. Count teams with form data. Check source health failure rates.

### PHASE 2b: Self-Healing

If enrichment validation found gaps:
- **Volleyball cache empty**: Run `python3 scripts/fetch_api_stats.py --date {date} --sports volleyball`
- **Handball cache empty**: Run `python3 scripts/fetch_api_stats.py --date {date} --sports handball`
- **Stats too shallow (< 10 keys for football)**: Check API source — ESPN should give 28+, API-Football only 10
- **All enrichment failed**: Check API rate limits at `scripts/api_clients/.rate_limit_state/`

### PHASE 3: Shortlist & Matrix

Verify the final artifacts exist and have quality content:

1. **Shortlist**: Read `{date}_s2_shortlist.json`. Gates: 50-100 events, ≥8 sports, football ≤50%.
2. **Market matrix**: Check `market_matrix_{date}.md` exists and has >100 lines.
3. **Decision matrix**: Check `decision_matrix_{date}.md` exists.

## Output

Save to: `betting/data/{date}_s1_scan_report.md`

Include all sections from the agent's report format:
1. Scan Summary (events, URLs, domains, errors, duration)
2. Sport Coverage table (14 rows: events, sources, cache files, stat keys, H2H, status)
3. Enrichment Health (stats/odds/weather coverage percentages)
4. Data Quality Issues (every issue found with severity and workaround)
5. Shortlist Summary (count, sports, top events)
6. Known Gaps flagged for S3 (what the statistician needs to know)

## Self-Verification (V-S1-01 to V-S1-15)

| # | Check | Gate |
|---|-------|------|
| 01 | All 14 sports listed in scan | Required |
| 02 | ≥ 40,000 events discovered | Required |
| 03 | ≥ 6 sports with active events | Required |
| 04 | Every sport from ≥2 sources | Required |
| 05 | KEY sports have deep tournament coverage | Required |
| 06 | scan_summary.json exists and fresh (>10MB) | Required |
| 07 | scan_errors.json reviewed, critical errors < 5 | Required |
| 08 | Stats cache: football ≥100, tennis ≥100 files | Required |
| 09 | Stats depth: football ≥10 keys sampled | Required |
| 10 | Odds data exists (or STATS-FIRST acknowledged) | Required |
| 11 | Weather for outdoor events | Required |
| 12 | Shortlist: 50-100 events, ≥8 sports | Required |
| 13 | Football ≤50% of shortlist | Required |
| 14 | DB fixtures populated for today | Required |
| 15 | Source health <20% failure rate | Required |

## Pass/Fail

- **15/15** → S1 PASSED → hand off to S2
- **12-14** → S1 CONDITIONAL → document gaps, proceed with warnings
- **<12** → S1 FAILED → investigate, self-heal, re-validate

<!-- BET:internal-prompt:bet-scan:v3 -->
