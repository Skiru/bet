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
python3 scripts/run_scanner.py --sport hockey --date {YYYY-MM-DD}
```

## STEP 2: Validate Results

```bash
python3 scripts/verify_scan.py --sport hockey --date {YYYY-MM-DD}
```

## STEP 3: Self-Heal (only if FAIL)

**If < 5 events:**
```bash
python3 scripts/run_scanner.py --sport hockey --date {YYYY-MM-DD}
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
