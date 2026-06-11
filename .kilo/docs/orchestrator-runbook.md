# Execution Spine — Mechanical Step-by-Step Runbook

## HOW TO READ THIS FILE

This runbook is executed inside five resumable production phases:

| Phase | Step span | Resume rule |
|------|-----------|-------------|
| A | startup, smoke, pre-flight, S0, P0 | if receipt missing/invalid, restart Phase A |
| B | S1, S1-ingest, S1a, S1b, S1c, S1e, P1, P2 | if shortlist or matrix parity is ambiguous, restart Phase B |
| C | S2, S2.3, P3, S2.5, S2.6-S2.9, P4, data gate | if matched tips or enrichment receipts are ambiguous, restart Phase C |
| D | S3, S4, S5, S6, P5, optional reconciler, S7, P6, analysis gate | if approved pool / gate state is ambiguous, restart Phase D |
| E | S7.5, S7.6, S8, S9, P7, build gate, S10 | if controls or coupon artifacts drift, restart Phase E |

Phase receipts are written as synthetic `pipeline_runs.step` values `PHASE_A` through `PHASE_E`. They are the primary resume authority. `.kilocode/memory/session-state.md` remains an operator summary, not the source of truth.
Use `scripts/record_phase_receipt.py` at phase start and phase completion/failure so the resume contract is durable in `pipeline_runs`.

## PRE-FLIGHT (RUN BEFORE STEP 1)

1. Fully trust MCP state only after a fresh VS Code / Kilo daemon restart if config changed recently.
2. Confirm required MCPs are live:
   - `sequentialthinking`
   - `sqlite`
   - `brave-search`
3. Run the orchestrator smoke test prompt before the first real pipeline session of the day:
   - `.kilo/docs/orchestrator-tool-smoke-test-prompt.md`
4. Remember the current Kilo runtime limitation:
   - agent-level MCP deny rules for SQLite write/create are not reliably enforced in Kilo 7.3.21
   - rely on prompt-level prohibition as the real guardrail
   - if any agent attempts DB writes, stop and record a protocol violation
5. Before S0, back up `betting/data/picks-ledger.csv`.

## DATE VARIABLES
- `{date}` = today (YYYY-MM-DD, Europe/Warsaw)
- `{prev_date}` = previous betting day
Always run `date +%Y-%m-%d` to verify before execution.

## BACKGROUND EXECUTION (CRITICAL — prevents timeouts)
Steps marked with `🕐 BACKGROUND` must run via `background_process start`, NOT via `bash`.
The agent should use bounded supervision: one start event, one or two progress checks, one completion receipt.
Scripts with `ProgressTracker` emit: status, progress_pct, current_item, total/completed.
See `bet-orchestrator.md` BACKGROUND EXECUTION section for the full pattern.

Each step is a card. Follow cards IN ORDER. Never skip. Never reorder.
- **PRE**: What MUST exist before you run this step. If missing → run the step named in the fix.
- **CMD**: Exact command. Copy-paste it. Always use `.venv/bin/python3`.
- **VERIFY**: How to confirm the step succeeded. Run this AFTER the script.
- **DELEGATE**: Which agent to invoke. MANDATORY — never skip delegation.
- **IF FAIL**: What to do if exit code ≠ 0 or verify fails.

---

## STEP 1: S0 — Settlement

PRE: Previous betting day has pending picks in DB
CMD:
```fish
env PYTHONPATH=src .venv/bin/python3 scripts/settle_on_finish.py --betting-day {prev_date} --no-poll > /tmp/s0.txt 2>&1
env PYTHONPATH=src .venv/bin/python3 scripts/analyze_betclic_learning.py >> /tmp/s0.txt 2>&1
env PYTHONPATH=src .venv/bin/python3 scripts/evaluate_decisions.py --date {prev_date} >> /tmp/s0.txt 2>&1
env PYTHONPATH=src .venv/bin/python3 scripts/data_rotation.py --execute --days 30 >> /tmp/s0.txt 2>&1
env PYTHONPATH=src .venv/bin/python3 scripts/build_league_profiles.py >> /tmp/s0.txt 2>&1
```
VERIFY: `tail -5 /tmp/s0.txt` — no errors, settlement complete
DELEGATE: **P0** — after S0 scripts, launch `task` bet-settler + bet-db-analyst simultaneously (covers both S0 and S0.5 analysis)
IF FAIL: Check if prev_date has unsettled picks. If no picks → skip S0.

Post-step integrity check (recommended after smoke tests or any suspicious agent behavior):
```fish
sqlite3 betting/data/betting.db "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '__%';"
```
Expected: no unexpected temporary tables.

---

## STEP 2: S0.5 — DB Quality Check

PRE: S0 complete
CMD: (no script)
DELEGATE: Covered by P0 (launched at STEP 1) — no separate delegation needed
IF FAIL: Fix DB issues before proceeding to S1.

---

## STEP 3: S1 — Event Discovery

PRE: S0.5 complete (or fresh start)
CMD:
```fish
env PYTHONPATH=src .venv/bin/python3 scripts/discover_events.py --date {date} --verbose > /tmp/s1.txt 2>&1
```
VERIFY: `tail -20 /tmp/s1.txt` — AGENT_SUMMARY with ≥50 events, 5 sports
DELEGATE: **P1 (deferred)** — bet-scanner launches alongside S1e analysis after STEP 7 (S1e) completes
IF FAIL: Check API keys in config/. Retry with --sports filter for missing sport.

---

## STEP 4: S1-ingest — Stats Ingestion

PRE: S1 complete (fixtures exist in DB)
CMD:
```fish
env PYTHONPATH=src .venv/bin/python3 scripts/ingest_scan_stats.py --date {date} --verbose > /tmp/s1_ingest.txt 2>&1
```
VERIFY: `tail -5 /tmp/s1_ingest.txt` — stats_cache populated, team_form rows created
DELEGATE: none (data transform only)
IF FAIL: Check if discover_events actually produced fixtures.

---

## STEP 5: S1a — ESPN Seeding (DO NOT SKIP)

PRE: S1 complete
CMD:
```fish
env PYTHONPATH=src .venv/bin/python3 scripts/seed_espn_data.py --skip-players --verbose > /tmp/s1a.txt 2>&1
```
VERIFY: `tail -10 /tmp/s1a.txt` — standings, ATS/OU records seeded
DELEGATE: none (data seeding only)
IF FAIL: ESPN API may be down. Note gap for S5 (no injury/coach data). Continue.

---

## STEP 5.5: S1c — Market Matrix (DO NOT SKIP)

PRE: S1 complete, odds/stats enrichment artifacts available
CMD:
```fish
env PYTHONPATH=src .venv/bin/python3 scripts/generate_market_matrix.py --date {date} > /tmp/s1c.txt 2>&1
```
VERIFY: `tail -10 /tmp/s1c.txt` — `market_matrix_{date}.json` created and DB persistence logged
DELEGATE: none (data transform only)
IF FAIL: Fix matrix generation before S1e. Do not run `build_shortlist.py` without a matrix unless degraded mode is explicit.

---

## STEP 6: S1b — Odds + Weather + Tipster Fetch (DO NOT SKIP — ALL 5 SCRIPTS) ∥ PARALLEL-CAPABLE

PRE: S1 complete, fixtures in DB

**Scripts 1-4 are independent and can run in PARALLEL. Script 5 (tipster_aggregator) requires fixtures but is independent of scripts 1-4.**

CMD (PARALLEL MODE — preferred):
```fish
# Fire ALL 4 independent fetch scripts concurrently:
env PYTHONPATH=src .venv/bin/python3 scripts/fetch_odds_api.py --date {date} --verbose > /tmp/s1b_odds.txt 2>&1 &
env PYTHONPATH=src .venv/bin/python3 scripts/fetch_odds_api_io.py --date {date} --verbose > /tmp/s1b_oddsio.txt 2>&1 &
env PYTHONPATH=src .venv/bin/python3 scripts/fetch_esports_odds.py --date {date} --verbose > /tmp/s1b_esports.txt 2>&1 &
env PYTHONPATH=src .venv/bin/python3 scripts/fetch_weather.py --date {date} > /tmp/s1b_weather.txt 2>&1 &
wait
# Then run tipster_aggregator (longest — 3-5 min):
env PYTHONPATH=src .venv/bin/python3 scripts/tipster_aggregator.py --date {date} --use-gemini --verbose >> /tmp/s1b.txt 2>&1
# Merge outputs:
cat /tmp/s1b_odds.txt /tmp/s1b_oddsio.txt /tmp/s1b_esports.txt /tmp/s1b_weather.txt >> /tmp/s1b.txt 2>&1
```

CMD (SEQUENTIAL MODE — fallback if parallel mode fails):
```fish
env PYTHONPATH=src .venv/bin/python3 scripts/fetch_odds_api.py --date {date} --verbose > /tmp/s1b.txt 2>&1
env PYTHONPATH=src .venv/bin/python3 scripts/fetch_odds_api_io.py --date {date} --verbose >> /tmp/s1b.txt 2>&1
env PYTHONPATH=src .venv/bin/python3 scripts/fetch_esports_odds.py --date {date} --verbose >> /tmp/s1b.txt 2>&1
env PYTHONPATH=src .venv/bin/python3 scripts/fetch_weather.py --date {date} >> /tmp/s1b.txt 2>&1
env PYTHONPATH=src .venv/bin/python3 scripts/tipster_aggregator.py --date {date} --use-gemini --verbose >> /tmp/s1b.txt 2>&1
```
VERIFY:
Use sqlite_read_query to verify:
```
SELECT COUNT(*) FROM tipster_picks WHERE betting_date='{date}'
```
→ Expect > 0 rows. If 0, tipster_aggregator did not produce picks.
PRODUCES:
- DB: odds_history, tipster_picks, tipster_consensus (REQUIRED BY STEP 8 S2)
- File: betting/data/{date}_tipster_consensus.json
DELEGATE: **P2 (optional)** — `task` bet-scanner (odds coverage) + bet-scout (tipster prep) simultaneously for early analysis; main tipster analysis happens at P3 after S2+S2.3
IF FAIL: If tipster_aggregator fails → brave-search tipster sites. If odds APIs fail → note for S4.

⚠️ **CRITICAL**: Script 5 (tipster_aggregator.py) PRODUCES the tipster_picks DB rows that STEP 8 (S2) REQUIRES. If you skip this script, S2 will exit with code 2.

---

## STEP 7: S1 matrix — Generate Market Matrix

PRE: S1 complete, fixtures in DB
CMD:
```fish
env PYTHONPATH=src .venv/bin/python3 scripts/generate_market_matrix.py --date {date} > /tmp/s1_matrix.txt 2>&1
```
VERIFY: `tail -20 /tmp/s1_matrix.txt` — matrix written and `market_matrix_events` DB persisted
PRODUCES:
- DB: `market_matrix_events`, `market_matrix_runs`
- File: `betting/data/market_matrix_{date}.json`
IF FAIL: If JSON exists but DB persist fails, treat as a production defect and fix before S1e.

Audit checklist before proceeding:
- Compare sport counts across `fixtures` → `market_matrix_events`
- Confirm no supported sport was dropped by non-canonical sport labels
- Check `data_tier_breakdown`; if overwhelmingly `FIXTURE_ONLY`, proceed with warning

---

## STEP 8: S1e — Build Shortlist

PRE: S1 + S1-ingest complete, fixtures + team_form in DB
CMD:
```fish
env PYTHONPATH=src .venv/bin/python3 scripts/build_shortlist.py --date {date} --stats-first --verbose > /tmp/s1e.txt 2>&1
```
VERIFY: `tail -20 /tmp/s1e.txt` — AGENT_SUMMARY with ≥20 candidates
PRODUCES:
- DB: pipeline_candidates (REQUIRED BY STEP 9 S2 and STEP 14 S3)
- File: betting/data/{date}_s2_shortlist.json
DELEGATE: **P1** — launch `task` bet-scanner (coverage) + bet-scanner (shortlist) simultaneously after S1e completes (S1+S1a+S1b+S1e all done now)
IF FAIL: Check if `generate_market_matrix.py` ran. Verify `market_matrix_events` has rows.

Audit checklist before proceeding:
- Compare sport counts across `fixtures` → `market_matrix_events` → `pipeline_candidates`
- For any sport that becomes 0, identify first loss point and exact filter responsible
- Inspect shortlist telemetry: `active_sports_zeroed`, `fixture_only_dropped_by_sport`, `garbage_filtered_by_sport`
- If football survives mainly via fixture-only while other active sports die, treat as shortlist logic defect

---

## STEP 9: S2 — Tipster Cross-Reference

PRE:
- ✅ S1b complete (STEP 6) — tipster_aggregator.py MUST have run
- ✅ DB: tipster_picks has >0 rows for {date} (produced by STEP 6)
- ✅ DB: pipeline_candidates has >0 rows for {date} (produced by STEP 8)

**S2 and S2.3 run in PARALLEL via STEP 10 CMD.** If running sequentially, use the CMD below. If parallel → skip this CMD, proceed to STEP 10.

CMD (SEQUENTIAL MODE ONLY):
```fish
env PYTHONPATH=src .venv/bin/python3 scripts/tipster_xref.py --date {date} --verbose > /tmp/s2.txt 2>&1
```
VERIFY: `tail -20 /tmp/s2.txt` — matched >0 tips, tipster_support added to candidates
DELEGATE: See STEP 10 — P3 launches at end of STEP 10 after both scripts complete
IF FAIL exit=2: "PRECONDITION_FAILED" → go back and run tipster_aggregator.py (STEP 6 script 5)
IF FAIL 0 tips matched: → brave-search tipster sites → if still 0 → ASK USER

⚠️ **S2 IS NEVER OPTIONAL.** Source fusion (tipsters + stats + web) is the CORE VALUE.

---

## STEP 10: S2.3 — Scrapers (PARALLEL with STEP 9 S2 — run them TOGETHER) ∥ PARALLEL-CAPABLE

PRE: S1e complete (shortlist exists)
**S2.3 (scrapers) and S2 (tipster_xref) are INDEPENDENT.** Use `&` to run both scripts concurrently:
```fish
env PYTHONPATH=src .venv/bin/python3 scripts/tipster_xref.py --date {date} --verbose > /tmp/s2.txt 2>&1 &
env PYTHONPATH=src .venv/bin/python3 scripts/run_scrapers.py --season 2425 --shortlist-date {date} --skip-player-stats --verbose > /tmp/s2_3.txt 2>&1 &
wait
```
VERIFY: `tail -10 /tmp/s2_3.txt` — league_profiles populated
DELEGATE: **P3** — launch `task` bet-scout + bet-enricher simultaneously after STEP 9 `wait` (both scripts done)
IF FAIL: Note which scrapers failed. Continue — enrichment step fills gaps.

---

## STEP 11: S2.5 — Data Enrichment 🕐 BACKGROUND

PRE: S2 + S2.3 BOTH complete
CMD:
```fish
env PYTHONPATH=src .venv/bin/python3 scripts/data_enrichment_agent.py --date {date} --news --gamelogs --verbose > /tmp/s2_5.txt 2>&1
```
VERIFY: `tail -10 /tmp/s2_5.txt` — enrichment yield >40%
DELEGATE: `task` bet-enricher solo — enrichment yield review (separate from P3 which already evaluated scraper warehouse)
IF FAIL yield<40%: Escalate to user. May need manual source intervention.

---

## STEP 12: S2.6-S2.9 — Sport-Specific Deep Enrichment ∥ PARALLEL-CAPABLE

PRE: S2.5 complete
**All 4 sports are INDEPENDENT — run them in PARALLEL:**
CMD:
```fish
# All four sports run concurrently:
env PYTHONPATH=src .venv/bin/python3 scripts/fetch_tennis_elo.py --verbose > /tmp/s2_6_elo.txt 2>&1 &
env PYTHONPATH=src .venv/bin/python3 scripts/enrich_tennis_flashscore.py --date {date} --verbose > /tmp/s2_6_flash.txt 2>&1 &
env PYTHONPATH=src .venv/bin/python3 scripts/tennis_h2h_warmup.py --date {date} --verbose > /tmp/s2_6_h2h.txt 2>&1 &
env PYTHONPATH=src .venv/bin/python3 scripts/enrich_volleyball_stats.py --date {date} --verbose > /tmp/s2_7.txt 2>&1 &
env PYTHONPATH=src .venv/bin/python3 scripts/enrich_hockey_stats.py --date {date} --verbose > /tmp/s2_8.txt 2>&1 &
env PYTHONPATH=src .venv/bin/python3 scripts/enrich_basketball_stats.py --date {date} --verbose > /tmp/s2_9.txt 2>&1 &
wait
# Merge tennis outputs:
cat /tmp/s2_6_elo.txt /tmp/s2_6_flash.txt /tmp/s2_6_h2h.txt >> /tmp/s2_6.txt 2>&1
```
VERIFY: Check enrichment logs — coverage improved for target sports
DELEGATE: → bet-enricher (per-sport readiness for S3)
IF FAIL: Note gaps. Continue to S3 with PARTIAL data flagged.

---

## STEP 13: ⛔ DATA PHASE GATE

PRE: S2.5 + sport enrichment complete
CMD:
```fish
env PYTHONPATH=src .venv/bin/python3 scripts/validate_phase.py --date {date} --phase data --format json > /tmp/gate_data.txt 2>&1
```
VERIFY: Exit code 0. If exit code 1 → STOP.
DELEGATE: none
IF FAIL: Read validation errors. Fix data gaps before proceeding to S3.

---

## STEP 14: S3 — Deep Statistical Analysis 🕐 BACKGROUND

PRE:
- ✅ DATA GATE passed (STEP 12)
- ✅ DB: pipeline_candidates has >0 rows for {date}
CMD:
```fish
env PYTHONPATH=src .venv/bin/python3 scripts/deep_stats_report.py --date {date} --gemini --verbose > /tmp/s3.txt 2>&1
```
VERIFY: `tail -20 /tmp/s3.txt` — AGENT_SUMMARY with candidates_analyzed ≥20% of shortlist
PRODUCES: DB: analysis_results (REQUIRED BY STEP 17 S7)
DELEGATE: **P5 (deferred)** — all three analysis agents launch together AFTER S5+S6 completes in STEP 15
IF FAIL exit=2: "PRECONDITION_FAILED" → run build_shortlist.py first (STEP 7)
IF FAIL <20%: Verify correct shortlist was used. Re-run.

---

## STEP 14: S4 — Odds Evaluation 🕐 BACKGROUND

PRE: S3 complete (analysis_results in DB)
CMD:
```fish
env PYTHONPATH=src .venv/bin/python3 scripts/odds_evaluator.py --date {date} --verbose > /tmp/s4.txt 2>&1
```
VERIFY: `tail -20 /tmp/s4.txt` — EV calculated for candidates
DELEGATE: **P5 (deferred)** — tri-agent launch happens at STEP 15 after S5+S6 completes
IF FAIL: Check if odds_history has data. May need to re-run fetch_odds_api.

---

## STEP 15: S5+S6 — Context + Upset Risk

PRE: S3 + S4 complete
Run as separate verified commands; do not rely on shell `&` shortcuts in orchestrator sessions.
CMD:
```fish
env PYTHONPATH=src .venv/bin/python3 scripts/context_checks.py --date {date} --verbose > /tmp/s5.txt 2>&1
env PYTHONPATH=src .venv/bin/python3 scripts/upset_risk.py --date {date} --verbose > /tmp/s6.txt 2>&1
```
VERIFY: `tail -10 /tmp/s5.txt` + `tail -10 /tmp/s6.txt` — context flags + upset scores
DELEGATE: **Launch P5 NOW** — `task` bet-statistician + bet-valuator + bet-challenger simultaneously in ONE message (all analysis scripts completed: S3+S4+S5+S6 done)
IF FAIL: Context/upset are enrichment — if they fail, continue but note gap.

---

## STEP 16: ⛔ COMPLETENESS GATE

PRE: P5 tri-agent launch complete (S3 + S4 + S5+S6 scripts all done, then launched as parallel group)
VERIFY: All three specialist verdicts (bet-statistician, bet-valuator, bet-challenger) returned from P5 launch.
IF ANY MISSING: Re-launch the missing agent individually. Do NOT proceed without all three.
**CHECK FOR CONFLICTS**: Compare per-candidate verdicts across all 3 agents. If ≥2 candidates have conflicting verdicts (e.g., statistician safety=0.70 STRONG vs challenger WEAK) → delegate bet-reconciler before proceeding to S7. Review reconciler output: SIDE_WITH → adopt; CONFLICTED → pass both to builder; ≥3 CONFLICTED → HARD STOP.
DELEGATE: none — P5 already delivered all three verdicts. If conflicts ≥2 → bet-reconciler.

---

## STEP 17: S7 — Decision Gate 🕐 BACKGROUND

PRE:
- ✅ COMPLETENESS GATE passed (STEP 16)
- ✅ DB: analysis_results has >0 rows for {date}
CMD:
```fish
env PYTHONPATH=src .venv/bin/python3 scripts/gate_checker.py --date {date} --strict --verbose > /tmp/s7.txt 2>&1
```
VERIFY: `tail -20 /tmp/s7.txt` — ≥10 candidates processed, approved + extended counts
PRODUCES: DB: gate_results (REQUIRED BY STEP 20 S8)
DELEGATE: **P6** — `task` bet-challenger solo (gate audit: bear cases, strength tiers, assumption audit)
IF FAIL exit=2: "PRECONDITION_FAILED" → run deep_stats_report.py first (STEP 13)
IF FAIL <10 candidates: Investigate. May need to rerun with relaxed criteria (adjust top-N or min-sports).

---

## STEP 18: ⛔ ANALYSIS GATE

CMD:
```fish
env PYTHONPATH=src .venv/bin/python3 scripts/validate_phase.py --date {date} --phase analysis --format json > /tmp/gate_analysis.txt 2>&1
```
VERIFY: Exit code 0. ≥3 STRONG+MODERATE candidates. If <3 → emergency expansion.
IF FAIL: Re-check gate with looser thresholds or expand candidate pool.

---

## STEP 19: S7.5+S7.6 — Betclic Validation + Repeat Check

PRE: S7 complete, gate_results in DB
CMD:
```fish
env PYTHONPATH=src .venv/bin/python3 scripts/validate_betclic_markets.py --date {date} --verbose > /tmp/s7_5.txt 2>&1
env PYTHONPATH=src .venv/bin/python3 scripts/check_48h_repeats.py --date {date} --format json --verbose > /tmp/s7_6.txt 2>&1
```
VERIFY: Markets validated or DB fallback available; repeat-loss flags noted or ledger fallback computed
DELEGATE: none (sidecar validation)
IF FAIL: If S7.5 JSON missing but `betclic_markets` DB rows exist for {date}, record `mode=db_fallback` and continue. For S7.6, exit `1` means repeat-loss findings were produced successfully; only exit `2` or a missing/malformed artifact is a true failure. If the handoff is missing but ledger exists, compute `ledger_fallback` before S8.

---

## STEP 20: S8+S9 — Build + Validate Coupons 🕐 BACKGROUND

PRE:
- ✅ ANALYSIS GATE passed (STEP 18)
- ✅ DB: gate_results has >0 rows for {date}
- ✅ S7.5/S7.6 controls present OR explicit fallback mode recorded in session-state
CMD:
```fish
env PYTHONPATH=src .venv/bin/python3 scripts/coupon_builder.py --date {date} --verbose > /tmp/s8.txt 2>&1
env PYTHONPATH=src .venv/bin/python3 scripts/validate_coupons.py betting/coupons/{date}*.md --verbose >> /tmp/s8.txt 2>&1
env PYTHONPATH=src .venv/bin/python3 scripts/generate_coupon_pdf.py --date {date} >> /tmp/s8.txt 2>&1
```
VERIFY: `tail -20 /tmp/s8.txt` — coupons built, validation passed
DELEGATE: **P7** — `task` bet-builder + bet-challenger simultaneously after S8+S9 scripts complete (BEFORE Build Gate in STEP 21)
IF FAIL exit=2: "PRECONDITION_FAILED" → run gate_checker.py first (STEP 17)

---

## STEP 21: ⛔ BUILD GATE

CMD:
```fish
env PYTHONPATH=src .venv/bin/python3 scripts/validate_phase.py --date {date} --phase build --format json > /tmp/gate_build.txt 2>&1
```
VERIFY: Exit code 0.
IF FAIL: Re-check coupon artifacts.

---

## STEP 22: S10 — Present Results

Present to user:
1. Settlement Summary (PnL, rolling 7-day, bankroll)
2. FULL STATISTICAL MATRIX (ALL candidates)
3. Final Coupons (per-leg: WHY + L10/H2H data + mechanism + bear case)
4. Extended Pool (gate-failed with EV>0)
5. Watchlist (picks awaiting triggers)

---

## DELEGATION PROTOCOL

Delegation syntax: `task(description="S0 settlement", prompt="...", subagent_type="bet-settler")`

Pattern: RUN → VERIFY → DELEGATE (parallel when possible) → RECEIVE VERDICTS → ADVANCE

1. Run script → redirect to /tmp/sN.txt → `tail -20`
2. `<think>`: which agents assess? Can multiple analyze independently?
3. **If parallel group available → launch ALL agents in ONE message with multiple `task` calls**
4. Receive verdicts → check: ≥3 metrics? original analysis? justified?
5. If REJECTED → investigate, re-run, re-delegate
6. If APPROVED → advance to next step

**Skipping delegation = FAILED SESSION.**
**Skipping parallel launch when available = WASTED SESSION.**

### Parallel Delegation Points

| When | Launch in Parallel | Group |
|------|-------------------|-------|
| After S0 | bet-settler + bet-db-analyst | P0 |
| After S1+S1e | bet-scanner (coverage) + bet-scanner (shortlist) | P1 |
| After S1b | bet-scanner (odds) + bet-scout (tipster prep) | P2 |
| After S2+S2.3 | bet-scout + bet-enricher | P3 |
| After S2.6-S2.9 | bet-enricher (all sports) | P4 |
| After S3+S4+S5+S6 | bet-statistician + bet-valuator + bet-challenger | P5 ⚡ BIGGEST WIN |
| After P5 (if conflicts) | bet-reconciler | P5conflict |
| After S8+S9 | bet-challenger + bet-builder | P7 |

---

## ANTI-PATTERNS (model has done ALL of these — STOP YOURSELF)

- ❌ Never run `pipeline_orchestrator.py` (BANNED)
- ❌ Never advance without specialist verdict
- ❌ Never paste raw terminal output as "analysis"
- ❌ Never skip native `<think>` before decisions
- ❌ Never assume scripts "just work" — verify preconditions
- ❌ Never run tipster_xref.py without tipster_aggregator.py having run first
- ❌ Never proceed past a GATE with exit code 1
- ❌ Never delegate agents sequentially when PARALLEL group (P0-P7) is available
- ❌ Never launch >4 parallel agents in one message
- ❌ Never fire parallel script groups without `wait` to confirm all finished
