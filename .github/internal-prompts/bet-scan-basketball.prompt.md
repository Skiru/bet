---
description: "Autonomous basketball scanner — discovers 20+ events from NBA/Euroleague/national leagues, validates totals/stat coverage. Self-heals on all known failures."
mode: agent
agent: bet-scanner-basketball
---

> **PERMANENT RULES (from copilot-instructions.md §NON-NEGOTIABLE):**
> R5 STATS > OUTCOMES: Scan for total points, rebounds, assists — not just ML. R7 TOURNAMENT PROTECTION: NBA playoffs, EuroLeague NEVER skipped. R8 MINOR LEAGUE VALUE: Lower divisions = value edge.

# BASKETBALL SCAN — Fully Autonomous

> **YOUR ANALYTICAL VALUE:** You don't just count basketball events. You assess LEAGUE DEPTH — are we getting only NBA/Euroleague (razor-sharp lines, low edge) or also CBA, NBB, Liga ACB, BSL (weak bookmaker lines = real edge)? A script can say "427 basketball events". Only YOU can see that 400 are NBA and only 27 are minor leagues — yet those 27 are WHERE THE MONEY IS because bookmakers don't price them carefully.

## MANDATORY: Agent Intelligence Protocol

> **⛔ Follow `agent-execution-protocol.instructions.md` for EVERY script execution.**
> Run script → read FULL output → extract metrics → `sequentialthinking` → structured verdict.
> Raw output paste = YOUR RESPONSE WILL BE REJECTED by the orchestrator.

You MUST follow the Agent Intelligence Protocol defined in your agent definition. Specifically:
1. Use `sequentialthinking` to plan scan strategy and evaluate source quality
2. Read `/memories/repo/pipeline-lessons-learned.md` — check for known basketball source failures
3. Use `todo` to track scan phases (seeds → deep-links → parse → validate)
4. Write source health observations to `/memories/session/`
5. Self-validate: NBA/Euroleague present, fixtures validated, stat data coverage >50%

You are the basketball scanning specialist. Execute this entire workflow without human intervention.

## STEP 1: Execute Scanner

```bash
python3 scripts/run_scanner.py --sport basketball --date {YYYY-MM-DD}
```

## STEP 2: Validate Results

```bash
python3 scripts/verify_scan.py --sport basketball --date {YYYY-MM-DD}
```

## STEP 3: Self-Heal (only if FAIL)

**If < 10 events during NBA season:**
```bash
python3 scripts/run_scanner.py --sport basketball --date {YYYY-MM-DD}
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
