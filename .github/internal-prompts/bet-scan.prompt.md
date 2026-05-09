---
agent: "bet-scanner"
description: "S1-S1e: Full data engine — scan 14 sports, enrich with stats/odds/weather, live-validate quality, self-heal gaps, build analysis-ready shortlist"
---

> **PERMANENT RULES (from copilot-instructions.md §NON-NEGOTIABLE):**
> R3 NO AUTO-REJECTION: ALL fixtures in shortlist. R7 TOURNAMENT PROTECTION: Major tournaments NEVER skipped (+15 boost). R8 MINOR LEAGUE VALUE: Non-top-5 = +6 boost, never penalize "obscure". R10 STATS-FIRST: Events without odds included.

# S1+S2 — SCAN + ENRICH + VALIDATE + SHORTLIST

## MANDATORY: Agent Intelligence Protocol

> **⛔ Follow `agent-execution-protocol.instructions.md` for EVERY script execution.**
> Run script → read FULL output → extract metrics → `sequentialthinking` → structured verdict.
> Raw output paste = YOUR RESPONSE WILL BE REJECTED by the orchestrator.

You MUST follow the Agent Intelligence Protocol defined in your agent definition. Specifically:
1. Use `sequentialthinking` to plan scan strategy and evaluate coverage quality
2. Read `/memories/repo/pipeline-lessons-learned.md` — check for known source failures and phantom patterns
3. Use `todo` to track per-sport scan progress (14 sports = 14 todos)
4. Use `askQuestions` when scan coverage is below threshold and re-scanning won't help
5. Write source health observations to `/memories/session/`
6. Self-validate: ALL 14 sports scanned, ≥6 with events, no phantom fixtures

## Required Skills

Load before starting:
- `bet-navigating-sources` — source tiers, fallback chains, blocked sources, URL formats
- `bet-reading-html` — load when reviewing S1-deep HTML deep parsing verdicts (20 domain profiles)

## Context (provided by orchestrator)

- **run_date**: `{date}` (today's betting day)
- **session**: `{session}` — full/day/night/morning (controls event time window)
- **14 sports**: football, tennis, basketball, hockey, baseball, volleyball, esports, snooker, darts, table_tennis, handball, mma, padel, speedway

## Workflow: DISCOVER → VALIDATE → ENRICH → VALIDATE → BUILD → VALIDATE

You follow a strict 3-phase workflow with INLINE VALIDATION after each phase. Don't blindly run scripts. Check data quality as you go and fix problems in real-time.

### PHASE 1: Event Discovery

Run the parallel sport scanner:
```bash
python3 scripts/scan_events.py --parallel-sport --urls-file config/scan_urls.json --deep --date {date}
```

This runs per-sport parallel scanning (11 sport groups, independent timeouts). If it times out, use `--resume` or run individual sport scanners manually.

**VALIDATE Phase 1** — Run these checks immediately after scan completes:

1. **Event count**: Query DB `scan_results` table for today's date. Check per-sport counts in `scan_run_stats` table.
2. **Source success**: Check `scan_run_stats.sources_ok` and `scan_run_stats.sources_failed` per sport.
3. **Error triage**: Read `scan_errors.json`. Separate critical errors from ignorable ones (BetExplorer empty pages for niche sports = normal).
4. **Sport coverage**: All 14 sports should have entries in `scan_run_stats`.

If gates fail → investigate and fix before proceeding. See Error Triage Playbook in agent definition.

### PHASE 2: Enrichment Validation

The pipeline already ran enrichment in parallel (stats, odds, weather). Now VALIDATE what it produced:

1. **Stats cache health** — Query DB `team_form` table for today's data:
   ```bash
   cd /Users/mkoziol/projects/bet && PYTHONPATH=src:. python3 -c "
   from bet.db.connection import get_db
   with get_db() as conn:
       c = conn.execute('SELECT sport, COUNT(DISTINCT team_name) FROM team_form GROUP BY sport')
       for row in c:
           print(f'{row[0]:15s}: {row[1]} teams')
   "
   ```
   Gates: Football ≥100, Tennis ≥100, Basketball ≥10, Hockey ≥10. **Flag volleyball/handball if 0.**

2. **Stats depth** — Sample 2-3 teams per KEY sport, check stat key count:
   - Football should have 28+ keys (ESPN source)
   - Tennis should have at least 3 keys (known gap: only sets_won/games_won/total_sets)
   - Basketball should have 17+ keys
   - If football has <10 keys → ESPN enrichment may have failed

3. **Odds coverage** — Check `odds_history` DB table and JSON files (`odds_multi_sources.json`, `odds_api_snapshot.json`). Count events with odds. In STATS-FIRST mode, acknowledge low coverage is expected.

4. **Weather** — Check `weather_{date}.json` exists for outdoor sports.

5. **DB population** — Count fixtures for today's date. Count teams with form data. Check `source_health` table failure rates.

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
| 01 | All 14 sports have entries in `scan_run_stats` | Required |
| 02 | Per-sport event counts reasonable (football ≥200, tennis ≥100) | Required |
| 03 | ≥ 6 sports with active events | Required |
| 04 | Every sport from ≥2 sources (`sources_ok` ≥ 2) | Required |
| 05 | KEY sports have deep tournament coverage | Required |
| 06 | DB `scan_results` populated for today's `betting_date` | Required |
| 07 | scan_errors.json reviewed, critical errors < 5 | Required |
| 08 | DB `team_form`: football ≥100, tennis ≥100 teams | Required |
| 09 | Stats depth: football ≥10 keys sampled | Required |
| 10 | Odds data exists (or STATS-FIRST acknowledged) | Required |
| 11 | Weather for outdoor events | Required |
| 12 | Shortlist: 50-100 events, ≥8 sports | Required |
| 13 | Football ≤50% of shortlist | Required |
| 14 | DB fixtures populated for today | Required |
| 15 | `source_health` failure rate <20% | Required |

## Pass/Fail

- **15/15** → S1 PASSED → hand off to S2
- **12-14** → S1 CONDITIONAL → document gaps, proceed with warnings
- **<12** → S1 FAILED → investigate, self-heal, re-validate

<!-- BET:internal-prompt:bet-scan:v3 -->
