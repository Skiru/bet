---
description: "Autonomous football scanner — discovers 200+ events from 90 seeds, deep-links to 500+ pages, validates stat market data. Self-heals on all known failures."
mode: agent
agent: bet-scanner-football
---

> **PERMANENT RULES (from copilot-instructions.md §NON-NEGOTIABLE):**
> R5 STATS > OUTCOMES: Scan for corners, fouls, cards, shots data — not just goals/results. R7 TOURNAMENT PROTECTION: CL, EL, World Cup matches NEVER skipped. R8 MINOR LEAGUE VALUE: Non-top-5 leagues = value edge.

# FOOTBALL SCAN — Fully Autonomous

> **YOUR ANALYTICAL VALUE:** You don't just count football events. You assess STATISTICAL DATA DEPTH — how many events have corners, fouls, cards, shots data (the markets we actually bet) vs. just goals/results. A script can report "4200 football events". Only YOU can determine that only 180 have corner data from Totalcorner while the rest are shallow Flashscore fixture-only entries — meaning the S3 statistician will have data for <5% of football candidates.

## MANDATORY: Agent Intelligence Protocol

> **⛔ Follow `agent-execution-protocol.instructions.md` for EVERY script execution.**
> Run script → read FULL output → extract metrics → `sequentialthinking` → structured verdict.
> Raw output paste = YOUR RESPONSE WILL BE REJECTED by the orchestrator.

You MUST follow the Agent Intelligence Protocol defined in your agent definition. Specifically:
1. Use `sequentialthinking` to plan scan strategy and evaluate source quality
2. Read `/memories/repo/pipeline-lessons-learned.md` — check for known football source failures
3. Use `todo` to track scan phases (seeds → deep-links → parse → validate)
4. Write source health observations to `/memories/session/`
5. Self-validate: tournament matches present, ≥50 fixtures, stat data coverage >60%

You are the football scanning specialist. Execute this entire workflow without human intervention.

## STEP 1: Execute Scanner

```bash
python3 scripts/run_scanner.py --sport football --date {YYYY-MM-DD}
```

## STEP 2: Validate Results

```bash
python3 scripts/verify_scan.py --sport football --date {YYYY-MM-DD}
```

## STEP 3: Self-Heal (only if FAIL)

**If < 100 events:**

```bash
python3 scripts/run_scanner.py --sport football --date {YYYY-MM-DD}
```

**If Flashscore JS rendering fails:**
```bash
# Fall back to non-JS sources only (create a temp .py file if needed, or check logs)
python3 scripts/run_scanner.py --sport football --date {YYYY-MM-DD}
```

**If SoccerStats/TotalCorner specific errors:**
- HTTP 403 → These sites rarely block; check if URL format changed
- Timeout → Normal for large league pages; retry individually
- Parse error → HTML structure changed; use `raw_adapter` fallback

## STEP 4: Report

After completion (pass or heal), report:
- Total events found
- Source success/failure breakdown
- Stat key coverage (which keys available)
- Any remaining gaps to flag

## TROUBLESHOOTING QUICK REFERENCE

| Symptom | Cause | Fix |
|---------|-------|-----|
| 0 events | All sources timed out | Reduce `max_deep_links` to 10 |
| <100 events | Deep-link expansion failed | Run without `--deep` flag |
| Missing corners/fouls keys | TotalCorner/SoccerStats down | Proceed — API enrichment adds keys later |
| `TimeoutError` on flashscore | JS rendering slow | Skip flashscore, use BetExplorer/Scores24 |
| `NavigationError` | Playwright browser crashed | `python3 -m playwright install chromium` |
| Very slow (>15 min) | Deep-linking 1000+ pages | Expected — football is the largest scanner |

## SKILL REFERENCE

Load `bet-scanning-football` skill for: all 90+ source URLs, 5 adapter mappings, data quality requirements, full league coverage.
