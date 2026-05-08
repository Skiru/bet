---
description: "Autonomous basketball scanner — discovers 20+ events from NBA/Euroleague/national leagues, validates totals/stat coverage. Self-heals on all known failures."
mode: agent
agent: bet-scanner-basketball
---

> **PERMANENT RULES (from copilot-instructions.md §NON-NEGOTIABLE):**
> R5 STATS > OUTCOMES: Scan for total points, rebounds, assists — not just ML. R7 TOURNAMENT PROTECTION: NBA playoffs, EuroLeague NEVER skipped. R8 MINOR LEAGUE VALUE: Lower divisions = value edge.

# BASKETBALL SCAN — Fully Autonomous

## MANDATORY: Agent Intelligence Protocol

You MUST follow the Agent Intelligence Protocol defined in your agent definition. Specifically:
1. Use `sequentialthinking` to plan scan strategy and evaluate source quality
2. Read `/memories/repo/pipeline-lessons-learned.md` — check for known basketball source failures
3. Use `todo` to track scan phases (seeds → deep-links → parse → validate)
4. Write source health observations to `/memories/session/`
5. Self-validate: NBA/Euroleague present, fixtures validated, stat data coverage >50%

You are the basketball scanning specialist. Execute this entire workflow without human intervention.

## STEP 1: Execute Scanner

```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:. python3 -c "
from scripts.scanners.basketball_scanner import BasketballScanner
from scripts.scanners.domain_semaphore import DomainSemaphoreMap
from datetime import date
scanner = BasketballScanner()
stats = scanner.scan(str(date.today()), DomainSemaphoreMap())
print(f'Basketball: {stats.events_found} events | {stats.sources_ok} OK | {stats.sources_failed} failed')
print(f'Validation: {\"PASS\" if stats.validation_passed else \"FAIL\"}')
if not stats.validation_passed:
    print(f'  Gaps: {stats.gaps_description}')
"
```

## STEP 2: Validate Results

```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:. python3 -c "
from bet.db.connection import get_db
from datetime import date
import json, datetime
today = str(date.today())
with get_db() as conn:
    c = conn.execute('SELECT COUNT(*) FROM scan_results WHERE sport="basketball" AND betting_date=?', (today,))
    count = c.fetchone()[0]
    print(f'Basketball events in DB: {count}')
    
    # Check leagues represented
    c = conn.execute('SELECT raw_data FROM scan_results WHERE sport="basketball" AND betting_date=? LIMIT 20', (today,))
    leagues = set()
    for row in c:
        data = json.loads(row[0]) if row[0] else {}
        if data.get('league'):
            leagues.add(data['league'])
    print(f'Leagues: {leagues or \"unknown\"}')

# Season check
month = datetime.date.today().month
if month in [7, 8, 9]:
    print('⚠️ NBA off-season (Jul-Sep) — EU leagues (ACB, BSL, Euroleague) still active')
    print('   Also check: Summer League (Jul), FIBA windows')
elif month in [10, 11, 12, 1, 2, 3, 4, 5, 6]:
    print('NBA regular/playoffs active')

if count >= 20:
    print('✅ PASS: Basketball ≥ 20 events')
elif count >= 10:
    print('⚠️ MARGINAL: 10-19 events (might be off-day)')
else:
    print('❌ FAIL: < 10 events — self-heal needed')
"
```

## STEP 3: Self-Heal (only if FAIL)

**If < 10 events during NBA season:**
```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:. python3 -c "
from scripts.scanners.basketball_scanner import BasketballScanner
from scripts.scanners.domain_semaphore import DomainSemaphoreMap
from datetime import date
scanner = BasketballScanner()
scanner.timeout_per_page = 60
stats = scanner.scan(str(date.today()), DomainSemaphoreMap())
print(f'Retry: {stats.events_found} events')
if stats.events_found < 10:
    print('Check: NBA has off-days (Mon/Thu sometimes light)')
    print('Check: EU leagues may be in break')
"
```

**If NBA API source fails:**
- basketball-reference.com is the fallback for NBA schedule
- ESPN API covers NBA + WNBA + NCAAB
- Covers.com has NBA consensus lines

## STEP 4: Report

After completion, report:
- Total basketball events found
- League breakdown (NBA/Euroleague/national)
- Season context (regular/playoffs/off-season)
- Stat key coverage (rebounds, assists, blocks, fg_pct, etc.)

## TROUBLESHOOTING

| Symptom | Cause | Fix |
|---------|-------|-----|
| 0 events (Jul-Sep) | NBA off-season | Check EU leagues — may be correctly low |
| 0 events (Oct-Jun) | Source failure | Retry with extended timeout |
| <10 events on game day | Flashscore basketball section empty | Use ESPN API + basketball-reference |
| Missing stat keys | API enrichment not run yet | Proceed — fetch_api_stats adds keys later |
| nba_api rate limit | Too many requests | Wait 2s between calls, max 1/sec |

## SKILL REFERENCE

Load `bet-scanning-basketball` skill for: source URLs, league coverage, API client details, stat key requirements.
