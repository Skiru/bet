# Betting Pipeline — Project Rules

## THINKING LIMIT (ALL AGENTS — CRITICAL)

`<think>` block ≤200 tokens. 3 sentences max. Then OUTPUT.
Deep reasoning → `sequentialthinking_sequentialthinking` tool (unlimited, external).
Pattern: brief `<think>` → sequentialthinking FIRST → then data tools.

## Architecture

- Agent-driven pipeline: orchestrator calls individual scripts; `pipeline_orchestrator.py` is BANNED.
- DB-first: `betting/data/betting.db` via `from bet.db.connection import get_db`.
- Model: Qwen3.6-35B-A3B MoE 4-bit local (131K context, thinking ALWAYS ON).
- MCP: `sequentialthinking`, `sqlite` (betting.db), `brave-search`.
- Terminal: Fish shell. No bash. Use `set -x VAR value`.
- **OUTPUT RULE: ALL scripts → `/tmp/sN.txt 2>&1` then `tail -20`. >10 lines of terminal in chat = FAILED.**

## The ONE RULE

> If your response could be produced by piping terminal output to a file, you have FAILED.
> Your response MUST contain ORIGINAL ANALYSIS — insights, patterns, anomalies that NO script can produce.

## Constraints

- Bookmaker: Betclic. Picks CONDITIONAL until user verifies. Never scrape Betclic.
- Timezone: Europe/Warsaw. Betting day: 06:00–05:59.
- Settle previous day BEFORE generating new picks.
- NEVER invent odds, lineups, injuries, results, or stats.
- Coverage: Football, Volleyball, Basketball, Tennis, Hockey, CS2, Dota 2, Valorant.
- Statistical markets BEFORE outcome markets.
- Reruns create new versions. Never overwrite pending artifacts.

## Delegation Protocol (orchestrator only)

Pattern: `RUN script > /tmp/ → tail -20 → DELEGATE via task → PRESENT verdict → advance`

**Skipping delegation = FAILED SESSION.**

Mandatory delegations (cannot skip):
| After | Delegate To | Expect |
|-------|-------------|--------|
| S1e | bet-scanner | Coverage verdict |
| S2 | bet-scout | Tipster consensus — **NEVER SKIP** |
| S3 | bet-statistician | Edge validation |
| S7 | bet-challenger | Bear cases |
| S8 | bet-builder | Coupon validation |

## S2 is NEVER OPTIONAL

Source fusion (tipsters + stats + web) is the CORE VALUE.

**Two-script sequence (BOTH required, IN ORDER):**
1. `tipster_aggregator.py` (STEP 6 in execution-spine) → produces DB: tipster_picks
2. `tipster_xref.py` (STEP 8 in execution-spine) → cross-references tips against shortlist

If tipster_xref.py exits with code 2 → tipster_aggregator.py was NOT run. Go back to STEP 6.
If S2 returns 0 tips matched → brave-search tipster sites → if still 0 → **ASK USER** before continuing.
Without tipster data → coupons are worthless pure math.

## Anti-Hallucination

1. After every step → 3-line summary to `.kilocode/memory/session-state.md`
2. Before every analysis → re-read session-state.md
3. Cite numbers from DB/files only — never from memory
4. When in doubt → `sqlite_read_query` — don't guess

## Data Flow (R18)

Before running script B after A: verify A's output format matches B's input. Read code first. NEVER assume scripts "just work."
