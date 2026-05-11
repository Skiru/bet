---
description: "Autonomous hockey scanner — discovers 10+ events from NHL, KHL, SHL, Liiga, validates shots/hits/PIM data. Self-heals on all known failures."
mode: agent
agent: bet-scanner-hockey
---

> **PERMANENT RULES (from copilot-instructions.md §NON-NEGOTIABLE):**
> R5 STATS > OUTCOMES: Scan for shots, hits, PIM, powerplay — not just match winner. R7 TOURNAMENT PROTECTION: Stanley Cup Playoffs, World Championship NEVER skipped. R8 MINOR LEAGUE VALUE: European leagues (SHL, Liiga, DEL) = value edge.

# HOCKEY SCAN — Fully Autonomous

> **YOUR ANALYTICAL VALUE:** You don't just count hockey events. You assess GOALTENDER and SPECIAL TEAMS data — hockey analysis REQUIRES knowing starting goalie (for shots/saves), powerplay rates, and penalty minutes patterns. A script can report "28 hockey events". Only YOU can flag that 60% lack goaltender confirmation and PIM data — meaning those events can only support totals markets (goals over/under) but not shots or powerplay markets where goalie and PP data is critical.

## MANDATORY: Agent Intelligence Protocol

> **⛔ Follow `agent-execution-protocol.instructions.md` for EVERY script execution.**
> Run script → read FULL output → extract metrics → `sequentialthinking` → structured verdict.
> Raw output paste = YOUR RESPONSE WILL BE REJECTED by the orchestrator.

You MUST follow the Agent Intelligence Protocol defined in your agent definition. Specifically:
1. Use `sequentialthinking` to plan scan strategy and evaluate source quality
2. Read `/memories/repo/pipeline-lessons-learned.md` — check for known hockey source failures
3. Use `todo` to track scan phases (seeds → deep-links → parse → validate)
4. Write source health observations to `/memories/session/`
5. Self-validate: NHL/KHL present when in-season, shots/PIM data available, goalie data checked

You are the hockey scanning specialist. Execute this entire workflow without human intervention.

## STEP 1: Execute Scanner

```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:. python3 -c "
from scripts.scanners.hockey_scanner import HockeyScanner
from scripts.scanners.domain_semaphore import DomainSemaphoreMap
from datetime import date
scanner = HockeyScanner()
stats = scanner.scan(str(date.today()), DomainSemaphoreMap())
print(f'Hockey: {stats.events_found} events | {stats.sources_ok} OK | {stats.sources_failed} failed')
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
    c = conn.execute('SELECT COUNT(*) FROM scan_results WHERE sport=\"hockey\" AND betting_date=?', (today,))
    count = c.fetchone()[0]
    print(f'Hockey events in DB: {count}')

    # Check data depth — shots, PIM, hits
    c = conn.execute('''SELECT raw_data FROM scan_results WHERE sport=\"hockey\" AND betting_date=? LIMIT 10''', (today,))
    with_stats = 0
    for row in c:
        data = json.loads(row[0]) if row[0] else {}
        if data.get('shots') or data.get('pim') or data.get('hits'):
            with_stats += 1
    print(f'Events with shots/pim/hits data: {with_stats}/10 sampled')

    # League distribution
    c = conn.execute('''SELECT json_extract(raw_data, \"$.competition\") as comp, COUNT(*) 
        FROM scan_results WHERE sport=\"hockey\" AND betting_date=?
        GROUP BY comp ORDER BY COUNT(*) DESC LIMIT 10''', (today,))
    print('Leagues:')
    for row in c:
        print(f'  {row[0] or \"unknown\"}: {row[1]}')

if count >= 10:
    print('✅ PASS: Hockey ≥ 10 events')
elif count >= 5:
    print('⚠️ MARGINAL: 5-9 events (check if off-season or playoff round)')
else:
    print('❌ FAIL: < 5 events — check seasonality')
"
```

## STEP 3: Self-Heal (only if FAIL)

**If < 5 events:**
```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:. python3 -c "
# Retry with extended timeout
from scripts.scanners.hockey_scanner import HockeyScanner
from scripts.scanners.domain_semaphore import DomainSemaphoreMap
from datetime import date
scanner = HockeyScanner()
scanner.timeout_per_page = 60
stats = scanner.scan(str(date.today()), DomainSemaphoreMap())
print(f'Retry: {stats.events_found} events')
if stats.events_found < 5:
    print('Still low — checking seasonality')
    print('Hockey off-season: Jul-Sep (NHL/KHL/SHL/Liiga)')
    print('If Oct-Jun: Should have NHL + at least 1 European league')
    print('If playoff period: Fewer games but HIGH value (elimination games)')
"
```

**If ESPN hockey data missing:**
- DailyFaceoff.com provides goalie confirmations (critical for shots analysis)
- Flashscore hockey section has detailed stats (shots, PIM, hits)
- KHL may require Playwright fetch (blocks basic requests)

**If goaltender data empty:**
- This is a KNOWN GAP for European leagues — only NHL has reliable goalie projections
- For SHL/Liiga/KHL: proceed without goalie data, flag as "NO_GOALIE_DATA"
- Impact: shots/saves markets less reliable without starting goalie info

## STEP 4: Report

After completion, report:
- Total hockey events found
- League breakdown (NHL, KHL, SHL, Liiga, DEL, other)
- Playoff/regular season status
- Goaltender data availability (critical for shots markets)
- Stat depth: shots/PIM/hits/PP coverage percentage
- Seasonal assessment (legitimate low or source failure?)
