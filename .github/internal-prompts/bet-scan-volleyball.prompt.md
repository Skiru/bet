---
description: "Autonomous volleyball scanner — discovers 15+ events from PlusLiga, Serie A, Bundesliga, V-League, validates set/point totals data. Self-heals on all known failures."
mode: agent
agent: bet-scanner-volleyball
---

> **PERMANENT RULES (from copilot-instructions.md §NON-NEGOTIABLE):**
> R5 STATS > OUTCOMES: Scan for total points, sets won, aces, blocks — not just match winner. R7 TOURNAMENT PROTECTION: World Championship, Nations League, Olympics NEVER skipped. R8 MINOR LEAGUE VALUE: Lower divisions = value edge.

# VOLLEYBALL SCAN — Fully Autonomous

> **YOUR ANALYTICAL VALUE:** You don't just count volleyball events. You assess STATISTICAL DEPTH — volleyball analysis REQUIRES knowing total points per set averages, ace/block rates, and set score patterns. A script can report "45 volleyball events". Only YOU can flag that 80% lack set-level scoring data — meaning those events can only support sets totals (over/under 3.5 sets) but not points totals or handicaps where per-set averages are critical.

## MANDATORY: Agent Intelligence Protocol

> **⛔ Follow `agent-execution-protocol.instructions.md` for EVERY script execution.**
> Run script → read FULL output → extract metrics → `sequentialthinking` → structured verdict.
> Raw output paste = YOUR RESPONSE WILL BE REJECTED by the orchestrator.

You MUST follow the Agent Intelligence Protocol defined in your agent definition. Specifically:
1. Use `sequentialthinking` to plan scan strategy and evaluate source quality
2. Read `/memories/repo/pipeline-lessons-learned.md` — check for known volleyball source failures
3. Use `todo` to track scan phases (seeds → deep-links → parse → validate)
4. Write source health observations to `/memories/session/`
5. Self-validate: Major leagues present (PlusLiga, Serie A, Bundesliga, V-League), set/point data available

You are the volleyball scanning specialist. Execute this entire workflow without human intervention.

## STEP 1: Execute Scanner

```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:. python3 -c "
from scripts.scanners.volleyball_scanner import VolleyballScanner
from scripts.scanners.domain_semaphore import DomainSemaphoreMap
from datetime import date
scanner = VolleyballScanner()
stats = scanner.scan(str(date.today()), DomainSemaphoreMap())
print(f'Volleyball: {stats.events_found} events | {stats.sources_ok} OK | {stats.sources_failed} failed')
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
    c = conn.execute('SELECT COUNT(*) FROM scan_results WHERE sport=\"volleyball\" AND betting_date=?', (today,))
    count = c.fetchone()[0]
    print(f'Volleyball events in DB: {count}')

    # Check data depth — do events have set/point totals?
    c = conn.execute('''SELECT raw_data FROM scan_results WHERE sport=\"volleyball\" AND betting_date=? LIMIT 10''', (today,))
    with_stats = 0
    for row in c:
        data = json.loads(row[0]) if row[0] else {}
        if data.get('sets') or data.get('total_points') or data.get('score'):
            with_stats += 1
    print(f'Events with score/stats data: {with_stats}/10 sampled')

    # League distribution
    c = conn.execute('''SELECT json_extract(raw_data, \"$.competition\") as comp, COUNT(*) 
        FROM scan_results WHERE sport=\"volleyball\" AND betting_date=?
        GROUP BY comp ORDER BY COUNT(*) DESC LIMIT 10''', (today,))
    print('Leagues:')
    for row in c:
        print(f'  {row[0] or \"unknown\"}: {row[1]}')

if count >= 15:
    print('✅ PASS: Volleyball ≥ 15 events')
elif count >= 8:
    print('⚠️ MARGINAL: 8-14 events (check if off-season)')
else:
    print('❌ FAIL: < 8 events — self-heal needed')
"
```

## STEP 3: Self-Heal (only if FAIL)

**If < 8 events:**
```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:. python3 -c "
# Retry with extended timeout for slow volleyball sources
from scripts.scanners.volleyball_scanner import VolleyballScanner
from scripts.scanners.domain_semaphore import DomainSemaphoreMap
from datetime import date
scanner = VolleyballScanner()
scanner.timeout_per_page = 60
stats = scanner.scan(str(date.today()), DomainSemaphoreMap())
print(f'Retry: {stats.events_found} events')
if stats.events_found < 8:
    print('Still low — checking if legitimate off-season')
    print('Volleyball off-season: Jun-Aug (Europe), varies for Asia/Americas')
    print('If May: should have PlusLiga playoffs, Serie A, Bundesliga')
"
```

**If Flashscore volleyball blocked:**
- Scores24 volleyball section provides backup coverage
- ESPN volleyball (limited but useful for international events)

**If point totals missing:**
- This is EXPECTED for lower-tier leagues — Flashscore shows only set scores (3-1, 3-2)
- Point totals available for top leagues (PlusLiga, Serie A) from detailed match pages
- Flag events without point-level data as "SETS_ONLY" in data_tier

## STEP 4: Report

After completion, report:
- Total volleyball events found
- League distribution (top leagues vs lower divisions)
- Set/point data availability (% with detailed stats)
- Seasonal context (playoffs? regular season? off-season?)
- Stat market readiness (which markets can be computed: sets totals, points totals, aces)
