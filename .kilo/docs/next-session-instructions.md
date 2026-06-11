# Next Session Instructions

## Current Status (2026-06-05)

The Kilo agent/MCP refactor is implemented and the system is ready for a real orchestrated pipeline session, with one important operational caveat:

- **MCP stack validated**: `sequentialthinking`, `sqlite`, and `brave-search` are the only required active MCPs.
- **Optional MCPs remain disabled**: `memory`, `context7`, `playwright`.
- **All 13 betting agents exist and load**.
- **All 13 prompts now include Tool Contract + Database Write Prohibition**.
- **Root permission leak from global config was neutralized** in project `kilo.jsonc`.
- **Critical Kilo runtime limitation discovered**: agent-level MCP deny rules for `sqlite_write_query` / `sqlite_create_table` are parsed but are not reliably enforced by Kilo 7.3.21 at runtime.

### Critical Safety Note

Because of the Kilo 7.3.21 MCP permission enforcement bug, treat the following as a hard runtime rule:

- No betting agent may use `sqlite_write_query`, `sqlite_create_table`, `write_query`, `create_table`, or any INSERT/UPDATE/DELETE/CREATE/DROP/ALTER SQL command.
- All agents were patched with explicit prompt-level prohibition. The orchestrator must still watch for violations.
- After any smoke test or pipeline session, verify no unexpected tables were created.

### Before Starting the Next Session

1. **Fully restart VS Code / Kilo daemon** before trusting MCP status. Earlier brave-search failures were caused by stale cached MCP processes.
2. Run the orchestrator smoke test prompt first:
   - `.kilo/docs/orchestrator-tool-smoke-test-prompt.md`
3. Review the latest reports if needed:
   - `.kilo/docs/kilo-agent-deep-review-report.md`
   - `.kilo/docs/kilo-mcp-skills-second-round-report.md`
   - `.kilo/docs/orchestrator-tool-smoke-test-report-2026-06-05.md`
4. Use the latest master pipeline prompt for real execution:
   - `.kilo/docs/master-pipeline-prompt-2026-06-05.md`

## What Changed (Architecture Improvements)

All the following were implemented and are ready for testing:

- **3-Phase structure** (GATHER → ANALYZE → VALIDATE) added to all 12 agent prompts
- **Self-validation** (THINK→ACT→REASON→SYNTHESIZE→VALIDATE→DELTA→FINALIZE) enforced for 5 agents
- **Tool Registry** in `tool-names.md` — 22 tools with permission levels and output protocol
- **MCP Recovery Protocol** — retry logic when MCP servers fail
- **bet-reconciler** — new agent for cross-domain P5 conflict resolution
- **bet-test-engineer** — new agent for production-readiness validation
- **Security**: `bash: deny` for 9/12 agents (least privilege)
- **Database write prohibition** added to all 13 prompts as a runtime workaround for Kilo MCP permission bypass
- **EV cap bug fixed**, duplicate seq-thinking rule removed, empty-result protocol added

## Phase 0: Toolchain Smoke Test (MANDATORY)

Before the test suite or real pipeline day, run the orchestrator smoke test first.

Use **bet-orchestrator** and send the prompt from:

- `.kilo/docs/orchestrator-tool-smoke-test-prompt.md`

### Expected Result

- `sequentialthinking_sequentialthinking` = PASS
- `sqlite_read_query` = PASS
- `brave-search_brave_web_search` = PASS
- `read`, `glob`, `grep`, `bash`, `webfetch`, `edit`, `task` = PASS
- **Important**: if any agent successfully executes `sqlite_write_query` or `sqlite_create_table`, do **not** trust config-only protection. Rely on prompt-level prohibition and record the incident.

## Phase 1: Run the Test Suite (1 session)

Start a new Kilo session with the **bet-test-engineer** agent:

```fish
# Verify the agent exists and prompt is loaded:
ls -la .kilo/prompts/bet-test-engineer.md

# The agent runs self-contained — just send:
# "Run the test suite for 2026-06-03. Produce a full verdict."
```

The test suite contains **15 traps** across 3 tasks:
1. **Linguistic Refinement** (5 traps — grammar, template, hallucination checks)
2. **Agentic Reasoning** (10 traps — domain boundaries, safety caps, self-validation, dead rubber)
3. **Meta-Evaluation** (self-reflection, protocol check, final confidence)

Expect ~15-20 minutes run time. The agent reads `betting.data.betting.db` and calls `sqlite`, `sequentialthinking`, `brave-search`.

### Pass Criteria

| Result | Score | What It Means |
|--------|-------|---------------|
| PASS_ALL | 15/15 | System is production-ready |
| PASS_MAJOR | 12-14/15 | Minor edge cases need tuning |
| PASS_MINOR | 10-11/15 | Multiple edge cases need tuning |
| FAIL_SOFT | 7-9/15 | Missed critical trap — architecture issue |
| FAIL_HARD | 0-6/15 | Fundamental flaw — re-review changes |

**If FAIL**: note which traps were missed, compare against the trap list in `bet-test-engineer.md`, then fix the underlying prompt issues.

## Phase 2: Run a Full Pipeline Day (1-3 sessions)

After the test suite passes, run a real pipeline for the live betting day. For the next session, use:

- `DATE = 2026-06-05`
- `YESTERDAY = 2026-06-04`

Run a real pipeline for `2026-06-05`:

```fish
set -x DATE (TZ=Europe/Warsaw date +%Y-%m-%d)
set -x YESTERDAY (TZ=Europe/Warsaw date -v-1d +%Y-%m-%d)
echo "Date: $DATE, YESTERDAY: $YESTERDAY"
```

Use **bet-orchestrator** as the primary agent. Follow the execution spine:

### Resume Contract

- Read `pipeline_runs` first and look for synthetic receipts `PHASE_A` through `PHASE_E`.
- If the latest receipt is `validated`, resume from the next phase.
- If a receipt is missing, malformed, failed, or references missing artifacts, restart that phase instead of guessing a sub-step.
- Planned rollover at a validated phase boundary is success, not failure.

Recommended production splits:

1. Session 1: complete Phase A + Phase B.
2. Session 2: complete Phase C + Phase D.
3. Session 3: complete Phase E.

### Step-by-step (orchestrator-runbook.md)

**⚠️ IMPORTANT — Pre-settlement backup:**
Before running S0, back up the production ledger:
```fish
cp betting/data/picks-ledger.csv betting/data/picks-ledger.bak.(date +%Y%m%d)
```
To restore: `cp betting/data/picks-ledger.bak.20260602 betting/data/picks-ledger.csv`

**⚠️ Gemini API cost warning:**
Steps S3 and S1b invoke paid Gemini API calls via `--gemini` / `--use-gemini` flags.
Run a dry pass WITHOUT those flags first to verify pipeline health.
Cost is per-call — monitor Gemini billing dashboard.

| Step | Command | Verify |
|------|---------|--------|
| S0 | `settle_on_finish.py --betting-day $YESTERDAY` + 4 scripts | tail -5 /tmp/s0.txt — no errors |
| → P0 | Delegate bet-settler + bet-db-analyst | Verdicts with confidence |
| S1 | `discover_events.py --date $DATE --verbose` | AGENT_SUMMARY ≥50 events, 5 sports |
| S1-ingest | `ingest_scan_stats.py --date $DATE --verbose` | stats_cache populated |
| S1a | `seed_espn_data.py --skip-players --verbose` | standings seeded |
| S1b ∥ | 4 parallel fetches + tipster_aggregator | tail: tipster_picks >0 |
| S1c | `generate_market_matrix.py --date $DATE --verbose` | market_matrix JSON + DB rows |
| S1e | `build_shortlist.py --date $DATE --stats-first` | ≥20 candidates |
| → P1 | Delegate bet-scanner ×2 | Coverage + shortlist verdicts |
| S2+S2.3 ∥ | `tipster_xref.py --date $DATE` + scoped `run_scrapers.py --shortlist-date $DATE --skip-player-stats` | matched tips, league_profiles |
| → P3 | Delegate bet-scout + bet-enricher | Consensus + readiness |
| S2.5 🕐 | `data_enrichment_agent.py --news --gamelogs` | yield >40% |
| → P4 | Delegate bet-enricher | Sport readiness verdicts |
| S3 🕐 | `deep_stats_report.py --gemini` | ≥20% of shortlist analyzed |
| S4 🕐 | `odds_evaluator.py` | EV calculated |
| S5+S6 | context_checks + upset_risk | context flags + upset scores |
| → **P5** | Delegate **ALL 3**: bet-statistician + bet-valuator + bet-challenger | **KEY TEST** — each must self-validate before returning |
| → P5conflict | If conflicts ≥2 → delegate bet-reconciler | Review CONFLICTED outputs |
| S7 🕐 | `gate_checker.py --strict` | ≥10 candidates processed |
| → P6 | Delegate bet-challenger (gate audit) | Bear cases + approval tiers |
| S7.5 | `validate_betclic_markets.py --date $DATE` | sidecar or DB observations ready |
| S7.6 | `check_48h_repeats.py --date $DATE --format json` | repeat-loss handoff or ledger fallback ready |
| S8+S9 🕐 | coupon_builder + validate_coupons + pdf | coupons built, validation passed |
| → **P7** | Delegate bet-builder + bet-challenger | **Coupons must self-validate** |
| S10 | Present results | PnL, matrix, coupons, extended pool |

### What to Watch For (New Features)

1. **Self-validation**: Watch that bet-statistician, bet-challenger, bet-valuator, bet-scout, and bet-builder ALL produce `validation_rounds: N` and `delta:` in their verdicts. If any don't, that agent's prompt hasn't been updated correctly.

2. **Confidence fields**: EVERY verdict should have `confidence: HIGH|MEDIUM|LOW`. If missing, the verdict template isn't being followed.

3. **P5 conflicts**: The orchestrator should compare stat/val/challenger output per-candidate. If ≥2 conflicts → bet-reconciler. Record how many conflicts arose and how reconciler resolved them.

4. **MCP failures**: If sqlite, brave-search, or sequentialthinking timeout, the MCP Recovery Protocol should handle it. Note any failures.
5. **webfetch proof**: validation-capable agents should use `webfetch`, not only search snippets, before claiming decisive external context.

6. **Domain boundaries**: No agent should recalculate another's metrics. Watch for agents staying in their lanes.

7. **Database write attempts**: No specialist should attempt DB writes. If any agent reports using `sqlite_write_query` or `sqlite_create_table`, treat it as a protocol violation even if the tool call technically succeeds.

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| bet-scanner says "mcp not available" | brave-search API key missing | `echo $BRAVE_API_KEY` — should be set |
| brave-search says "Not connected" even though config looks correct | stale Kilo MCP process / old daemon state | fully restart VS Code, then rerun smoke test |
| sqlite query returns 0 rows | Wrong date in DB | Check: `SELECT DISTINCT betting_date FROM pipeline_candidates` for real dates |
| Agent finishes without self-validation | Prompt's Phase 3 not being read | Verify `VALIDATE` step in execution-core.md is prominent enough |
| bet-reconciler not launching | Orchestrator doesn't detect conflicts | Check orchestrator prompt has the reconciliation section after P5 |
| Steps budget exhausted | Not enough `steps` in kilo.jsonc | Increase steps for that agent in kilo.jsonc |
| bet-builder writes Polish text with errors | Encoding issue | Ensure `.venv/bin/python3` and UTF-8 locale |

## Summary Checklist for Next Session

- [ ] Run bet-test-engineer test suite → PASS_MAJOR or better
- [ ] Run orchestrator smoke test first
- [ ] Run full pipeline for 2026-06-05
- [ ] Verify all 5 validation-capable agents self-validate (confidence + delta in output)
- [ ] Verify P5 conflicts → bet-reconciler (if any)
- [ ] Verify all 9 non-shell agents operate without bash (security check)
- [ ] Verify no unexpected DB write attempts occurred
- [ ] Log any MCP failures + recovery actions
- [ ] Log any domain boundary violations
- [ ] Report results: traps score, pipeline pass/fail, anomalies found
