# Post-Overhaul Audit — 2026-05-12

## Scope
68 files changed, 7193 lines added across adapters/clients for all 5 sports.
15 agents audited, 20 internal prompts audited, execution protocol verified.

## Critical Fixes Applied
1. **Protocol heredoc contradiction** — anti-pattern #16 recommended `python3 << 'EOF'` (heredoc) which is banned by fish shell rule #5. Fixed to: "create a temp .py file"
2. **bet-statistician NaturalStatTrick** — still referenced blocked source. Fixed to MoneyPuck
3. **Settlement prompt --verbose** — claimed settle_on_finish.py supports --verbose/AGENT_SUMMARY. It doesn't. Fixed
4. **Hockey scanner missing sources** — MoneyPuck, DailyFaceoff, NaturalStatTrick (blocked) added to Source Registry
5. **Tennis scanner stale Elo note** — said "NOT integrated" when Elo IS integrated into safety scores. Fixed
6. **Protocol version tag** — footer said v3, header said v5. Fixed to v5
7. **Duplicate nba-api registration** — registered twice in api_clients/__init__.py. Removed duplicate
8. **2 failing tests** — DB-first path bypassed test mocks. Fixed with proper DB mock patches

## Test Results
599 passed, 0 failed (was: 597 passed, 2 failed)

## Architecture Notes (From Audit)
- MoneyPuck client is NOT in CLIENT_REGISTRY — used directly by adapter via CSV. By design.
- Disabled clients (TheSportsDB, BallDontLie, API-Tennis) properly handled in __init__.py
- deep_link_discovery.py missing patterns for moneypuck/dailyfaceoff/atptour — non-issue (CSV/direct fetch, not crawled)
- scripts/api_clients/ vs src/bet/api_clients/ have drifted — ESPN adapter consolidated in scripts/ but split in src/

## Async Execution Status
- Protocol (agent-execution-protocol.instructions.md v5) correctly describes async patterns
- All 15 agents have terminal execution + monitoring tools
- All 15 agents include Python env tools (ms-python.python/*)
- Internal prompts don't explicitly teach async — rely on protocol inheritance. Acceptable.

## Remaining Non-Blocking Warnings
- bet-scan-all.prompt.md stale (11-scanner universe) — rarely used directly
- bet-validate.prompt.md missing --verbose — minor
- Hockey/tennis sport-specific prompts could reference new adapters more explicitly
