---
name: daily-betting-cycle
description: "DEPRECATED — use orchestrate-betting-day instead"
agent: bet-analyst
argument-hint: "Use: @workspace /prompt orchestrate-betting-day run_date=2026-04-27 session=full"
---

# ⚠️ DEPRECATED — Use `orchestrate-betting-day` instead

This prompt has been merged into `orchestrate-betting-day.prompt.md` which includes:
- Everything from this file (STEP -1 pre-flight, rerun versioning, session types)
- 4-pass error correction protocol (Discovery → Fixes → Polish → Final)
- §S8.FINAL mechanical verification
- Session parity enforcement

**Run instead:**
```
@workspace /prompt orchestrate-betting-day run_date=YYYY-MM-DD session=full
@workspace /prompt orchestrate-betting-day run_date=YYYY-MM-DD session=night
@workspace /prompt orchestrate-betting-day run_date=YYYY-MM-DD session=full rerun=true
```