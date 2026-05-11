---
description: "Autonomous tennis scanner — discovers 30+ events from ATP/WTA/ITF, integrates Elo ratings, validates surface data. Self-heals on all known failures."
mode: agent
agent: bet-scanner-tennis
---

> **PERMANENT RULES (from copilot-instructions.md §NON-NEGOTIABLE):**
> R5 STATS > OUTCOMES: Scan for aces, double faults, games, sets — not just match winner. R7 TOURNAMENT PROTECTION: Grand Slams, Masters NEVER skipped. R8 MINOR LEAGUE VALUE: Challenger/ITF = value edge.

# TENNIS SCAN — Fully Autonomous

> **YOUR ANALYTICAL VALUE:** You don't just count tennis events. You assess H2H and SURFACE coverage — tennis analysis REQUIRES knowing surface type (clay/hard/grass) and head-to-head history. A script can report "163 tennis events". Only YOU can flag that 90% are ITF Futures with zero H2H data and no Elo ratings — meaning those events can only support games totals markets (where form data alone drives the edge), not match winner or sets markets.

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
python3 scripts/run_scanner.py --sport tennis --date {YYYY-MM-DD}
```

## STEP 2: Validate Results

```bash
python3 scripts/verify_scan.py --sport tennis --date {YYYY-MM-DD}
```

## STEP 3: Self-Heal (only if FAIL)

**If < 15 events:**
```bash
python3 scripts/run_scanner.py --sport tennis --date {YYYY-MM-DD}
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
