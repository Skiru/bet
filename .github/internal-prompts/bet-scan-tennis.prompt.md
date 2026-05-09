---
description: "Autonomous tennis scanner — discovers 30+ events from ATP/WTA/ITF, integrates Elo ratings, validates surface data. Self-heals on all known failures."
mode: agent
agent: bet-scanner-tennis
---

> **PERMANENT RULES (from copilot-instructions.md §NON-NEGOTIABLE):**
> R5 STATS > OUTCOMES: Scan for aces, double faults, games, sets — not just match winner. R7 TOURNAMENT PROTECTION: Grand Slams, Masters NEVER skipped. R8 MINOR LEAGUE VALUE: Challenger/ITF = value edge.

# TENNIS SCAN — Fully Autonomous

## MANDATORY: Agent Intelligence Protocol

> **⛔ Follow `agent-execution-protocol.instructions.md` for EVERY script execution.**
> Run script → read FULL output → extract metrics → `sequentialthinking` → structured verdict.
> Raw output paste = YOUR RESPONSE WILL BE REJECTED by the orchestrator.

You MUST follow the Agent Intelligence Protocol defined in your agent definition. Specifically:
1. Use `sequentialthinking` to plan scan strategy and evaluate source quality
2. Read `/memories/repo/pipeline-lessons-learned.md` — check for known tennis source failures
3. Use `todo` to track scan phases (seeds → deep-links → parse → validate)
4. Write source health observations to `/memories/session/`
5. Self-validate: Grand Slam/ATP/WTA present, fixtures validated, H2H data coverage >40%

You are the tennis scanning specialist. Execute this entire workflow without human intervention.

## STEP 1: Execute Scanner

```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:. python3 -c "
from scripts.scanners.tennis_scanner import TennisScanner
from scripts.scanners.domain_semaphore import DomainSemaphoreMap
from datetime import date
scanner = TennisScanner()
stats = scanner.scan(str(date.today()), DomainSemaphoreMap())
print(f'Tennis: {stats.events_found} events | {stats.sources_ok} OK | {stats.sources_failed} failed')
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
import json, os
today = str(date.today())
with get_db() as conn:
    c = conn.execute('SELECT COUNT(*) FROM scan_results WHERE sport="tennis" AND betting_date=?', (today,))
    count = c.fetchone()[0]
    print(f'Tennis events in DB: {count}')

# Check Elo data availability
elo_dir = 'betting/data/tennisabstract.com'
if os.path.exists(elo_dir):
    files = os.listdir(elo_dir)
    print(f'TennisAbstract Elo files: {len(files)}')
else:
    print('⚠️ No TennisAbstract Elo data directory')

# Check surface detection
with get_db() as conn:
    c = conn.execute('''SELECT raw_data FROM scan_results WHERE sport="tennis" AND betting_date=? LIMIT 10''', (today,))
    surfaces = set()
    for row in c:
        data = json.loads(row[0]) if row[0] else {}
        if data.get('surface'):
            surfaces.add(data['surface'])
    print(f'Surfaces detected: {surfaces or \"NONE\"}')

if count >= 30:
    print('✅ PASS: Tennis ≥ 30 events')
elif count >= 15:
    print('⚠️ MARGINAL: 15-29 events (check if tournament break)')
else:
    print('❌ FAIL: < 15 events — self-heal needed')
"
```

## STEP 3: Self-Heal (only if FAIL)

**If < 15 events:**
```bash
cd /Users/mkoziol/projects/bet && PYTHONPATH=src:. python3 -c "
# Retry with extended timeout for slow tennis sources
from scripts.scanners.tennis_scanner import TennisScanner
from scripts.scanners.domain_semaphore import DomainSemaphoreMap
from datetime import date
scanner = TennisScanner()
scanner.timeout_per_page = 60
stats = scanner.scan(str(date.today()), DomainSemaphoreMap())
print(f'Retry: {stats.events_found} events')
if stats.events_found < 15:
    print('Still low — checking if legitimate (tournament break, off-day)')
    print('Tennis has events 51 weeks/year. Only Christmas week is truly empty.')
"
```

**If TennisExplorer blocked (403):**
- Flashscore tennis section + Scores24 tennis detail pages provide sufficient coverage
- TennisExplorer is primarily for surface detection (also available from ATP/WTA sites)

**If H2H data empty:**
- This is a KNOWN GAP: ESPN tennis API returns only sets_won/games_won/total_sets
- H2H from Scores24 detail pages is the workaround
- Not a blocker — proceed without H2H, flag in report

## STEP 4: Report

After completion, report:
- Total tennis events found
- Tournament/level breakdown (ATP/WTA/ITF/Challenger)
- Surface distribution (clay/hard/grass/indoor)
- Elo coverage (% of players with ratings)
- H2H coverage (expected to be low — known gap)

## TROUBLESHOOTING

| Symptom | Cause | Fix |
|---------|-------|-----|
| 0 events | All sources failed | Check if ATP off-season (mid-Nov to early Jan only) |
| <15 events | Tournament break between events | Verify on flashscore — if indeed few matches, this is correct |
| No surface data | TennisExplorer blocked | Use tournament name heuristics (Roland Garros=clay) |
| Elo dir empty | TennisAbstract scrape not run | Proceed without Elo — safety scores still work |
| H2H always empty | ESPN tennis limitation | Known — flag in report, not a failure |

## SKILL REFERENCE

Load `bet-scanning-tennis` skill for: all source URLs, adapter mappings, surface detection rules, Elo integration notes.
