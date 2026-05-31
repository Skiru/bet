# Betting Pipeline — Project Rules

## THINKING LIMIT (ALL AGENTS — CRITICAL)

`<think>` block: 3 sentences max for PLANNING. But `<think>` for REASONING BETWEEN QUERIES is unlimited.
Deep reasoning → `sequentialthinking_sequentialthinking` tool (unlimited, external).

Two valid uses of `<think>`:
1. **Planning** (before first tool): ≤3 sentences. "What hypothesis? What ONE query?"
2. **Reasoning** (between tools): unlimited. "What did I learn? Does this confirm or deny? Need more?"

Pattern: brief planning `<think>` → sequentialthinking → data tool → reasoning `<think>` → next decision.

## Deliberation Loop (ALL SUBAGENTS — MANDATORY)

Subagents are ANALYSTS, not query machines.

**Pattern:** THINK → ACT(1) → REASON → ACT(1) → SYNTHESIZE

- ⛔ NEVER fire >2 tool calls without `<think>` reasoning between them
- ⛔ After EACH query: reason about what you LEARNED before deciding next action
- ⛔ "Get all data first, analyze later" = DRIFT = FAILED
- Budget: max 4-5 tool calls total, with reasoning between EVERY pair
- If you find yourself querying without a hypothesis → STOP → `sequentialthinking`
- If budget exhausted but question unanswered → SYNTHESIZE with "INCOMPLETE: [what's missing]" — NEVER silently keep querying

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
