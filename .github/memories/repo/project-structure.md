# Bet Project — Key Facts

## Architecture
- Agent-driven pipeline: the orchestrator calls individual scripts one at a time; `pipeline_orchestrator.py` stays banned.
- Database-first: `betting/data/betting.db` is the primary store and `get_db()` is the canonical connection layer.
- Discovery lives in `src/bet/discovery/` and remains API-first for the 5 core sports.
- Existing `bet-` agents, prompts, skills, and instructions are the active customization surface.

## Core Facts
- Key output folders: `betting/data/`, `betting/coupons/`, `betting/reports/`, `betting/journal/`.
- Root memory is the long-lived memory layer; `.github/memories/` is only for short repo-local facts.
- Timezone is Europe/Warsaw and betting-day runs 06:00–05:59.
- All active bet agent models must be `GPT-5.4`.
