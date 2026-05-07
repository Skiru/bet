---
description: "Autonomous niche sports scanner (snooker + darts + speedway) — handles highly seasonal schedule, specialist sources, zero-event tolerance."
mode: agent
agent: bet-scanner-niche
---

# NICHE SPORTS SCAN — Fully Autonomous

You scan snooker, darts, and speedway. These sports are HIGHLY SEASONAL — zero events on most days is NORMAL.

## STEP 1: Execute Scanner

```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:. python3 -c "
from scripts.scanners.niche_scanner import NicheScanner
from scripts.scanners.domain_semaphore import DomainSemaphoreMap
from datetime import date
scanner = NicheScanner()
stats = scanner.scan(str(date.today()), DomainSemaphoreMap())
print(f'Niche: {stats.events_found} events | {stats.sources_ok} OK | {stats.sources_failed} failed')
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
import json
today = str(date.today())
with get_db() as conn:
    # Check each niche sport separately
    for sport in ['snooker', 'darts', 'speedway']:
        c = conn.execute('SELECT COUNT(*) FROM scan_results WHERE sport=? AND date=?', (sport, today))
        count = c.fetchone()[0]
        print(f'{sport}: {count} events')

print()
print('SCHEDULE CONTEXT:')
print('  Snooker: Oct-May (World Championship in Apr-May)')
print('  Darts: Year-round PDC, peaks Dec-Jan (World Championship)')
print('  Speedway: Apr-Oct (European outdoor season)')
import datetime
month = datetime.date.today().month
if month in [6,7,8,9]:
    print('  → Summer: speedway active, snooker likely quiet')
elif month in [11,12,1]:
    print('  → Winter: darts peak, snooker active, speedway over')
else:
    print('  → Transition: check specific tournaments')
"
```

**Zero events is NOT a failure for niche sports.** Only flag as error if:
- PDC darts event clearly running today AND 0 darts events
- World Snooker Championship in progress AND 0 snooker events
- Ekstraliga speedway round day AND 0 speedway events

## STEP 3: Self-Heal (only if source errors, not empty schedule)

**If sources errored but events should exist:**
```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:. python3 -c "
# Try specialist sources directly
from scripts.scanners.niche_scanner import NicheScanner
from scripts.scanners.domain_semaphore import DomainSemaphoreMap
from datetime import date
scanner = NicheScanner()
scanner.timeout_per_page = 45  # Specialist sites are often slow
stats = scanner.scan(str(date.today()), DomainSemaphoreMap())
print(f'Retry with extended timeout: {stats.events_found} events')
"
```

## STEP 4: Report

After completion, report:
- Events per sub-sport (snooker/darts/speedway)
- Whether season is active for each
- Any source errors encountered
- Mark as `seasonal_empty` if zero events in off-season (NOT an error)

## TROUBLESHOOTING

| Symptom | Cause | Fix |
|---------|-------|-----|
| 0 events all three | Off-season or no tournament | NORMAL — report as seasonal |
| CueTracker timeout | Site slow during tournaments | Retry with 45s timeout |
| DartsOrakel 404 | URL structure changed | Check if they moved to new domain |
| Speedway 0 in summer | Ekstraliga off-week | Check schedule — rounds are bi-weekly |
| Source parse errors | Small sites change HTML often | Fall back to flashscore niche sections |

## SKILL REFERENCE

Load `bet-scanning-niche` skill for: specialist source URLs, tournament calendars, validation thresholds.
