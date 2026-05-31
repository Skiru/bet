# Execution Spine — Mechanical Step-by-Step Runbook

## HOW TO READ THIS FILE

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
PYTHONPATH=src .venv/bin/python3 scripts/settle_on_finish.py --betting-day {prev_date} --no-poll > /tmp/s0.txt 2>&1
PYTHONPATH=src .venv/bin/python3 scripts/analyze_betclic_learning.py >> /tmp/s0.txt 2>&1
PYTHONPATH=src .venv/bin/python3 scripts/evaluate_decisions.py --date {prev_date} >> /tmp/s0.txt 2>&1
PYTHONPATH=src .venv/bin/python3 scripts/data_rotation.py --execute --days 30 >> /tmp/s0.txt 2>&1
PYTHONPATH=src .venv/bin/python3 scripts/build_league_profiles.py >> /tmp/s0.txt 2>&1
```
VERIFY: `tail -5 /tmp/s0.txt` — no errors, settlement complete
DELEGATE: → bet-settler (PnL validation, bankroll impact, learning signals)
IF FAIL: Check if prev_date has unsettled picks. If no picks → skip S0.

---

## STEP 2: S0.5 — DB Quality Check

PRE: S0 complete
CMD: (no script — delegation only)
DELEGATE: → bet-db-analyst (audit critical tables, freshness, coverage)
IF FAIL: Fix DB issues before proceeding to S1.

---

## STEP 3: S1 — Event Discovery

PRE: S0.5 complete (or fresh start)
CMD:
```fish
PYTHONPATH=src .venv/bin/python3 scripts/discover_events.py --date {date} --verbose > /tmp/s1.txt 2>&1
```
VERIFY: `tail -20 /tmp/s1.txt` — AGENT_SUMMARY with ≥50 events, 5 sports
DELEGATE: → bet-scanner (coverage quality, source failures, fixture count)
IF FAIL: Check API keys in config/. Retry with --sports filter for missing sport.

---

## STEP 4: S1-ingest — Stats Ingestion

PRE: S1 complete (fixtures exist in DB)
CMD:
```fish
PYTHONPATH=src .venv/bin/python3 scripts/ingest_scan_stats.py --date {date} --verbose > /tmp/s1_ingest.txt 2>&1
```
VERIFY: `tail -5 /tmp/s1_ingest.txt` — stats_cache populated, team_form rows created
DELEGATE: none (data transform only)
IF FAIL: Check if discover_events actually produced fixtures.

---

## STEP 5: S1a — ESPN Seeding (DO NOT SKIP)

PRE: S1 complete
CMD:
```fish
PYTHONPATH=src .venv/bin/python3 scripts/seed_espn_data.py --skip-players --verbose > /tmp/s1a.txt 2>&1
```
VERIFY: `tail -10 /tmp/s1a.txt` — standings, ATS/OU records seeded
DELEGATE: none (data seeding only)
IF FAIL: ESPN API may be down. Note gap for S5 (no injury/coach data). Continue.

---

## STEP 6: S1b — Odds + Weather + Tipster Fetch (DO NOT SKIP — ALL 5 SCRIPTS)

PRE: S1 complete, fixtures in DB
CMD (run ALL 5 in order):
```fish
PYTHONPATH=src .venv/bin/python3 scripts/fetch_odds_api.py --verbose > /tmp/s1b.txt 2>&1
PYTHONPATH=src .venv/bin/python3 scripts/fetch_odds_api_io.py --date {date} --verbose >> /tmp/s1b.txt 2>&1
PYTHONPATH=src .venv/bin/python3 scripts/fetch_esports_odds.py --date {date} --verbose >> /tmp/s1b.txt 2>&1
PYTHONPATH=src .venv/bin/python3 scripts/fetch_weather.py --date {date} >> /tmp/s1b.txt 2>&1
PYTHONPATH=src .venv/bin/python3 scripts/tipster_aggregator.py --date {date} --use-gemini --verbose >> /tmp/s1b.txt 2>&1
```
VERIFY:
```fish
PYTHONPATH=src .venv/bin/python3 -c "
from bet.db.connection import get_db
with get_db() as conn:
    c = conn.execute('SELECT COUNT(*) FROM tipster_picks WHERE betting_date=?', ('{date}',)).fetchone()[0]
    print(f'tipster_picks={c}')
    assert c > 0, 'FAILED: tipster_aggregator did not produce picks'
"
```
PRODUCES:
- DB: odds_history, tipster_picks, tipster_consensus (REQUIRED BY STEP 8 S2)
- File: betting/data/{date}_tipster_consensus.json
DELEGATE: none (data fetch only — analysis happens at S2)
IF FAIL: If tipster_aggregator fails → brave-search tipster sites. If odds APIs fail → note for S4.

⚠️ **CRITICAL**: Script 5 (tipster_aggregator.py) PRODUCES the tipster_picks DB rows that STEP 8 (S2) REQUIRES. If you skip this script, S2 will exit with code 2.

---

## STEP 7: S1e — Build Shortlist

PRE: S1 + S1-ingest complete, fixtures + team_form in DB
CMD:
```fish
PYTHONPATH=src .venv/bin/python3 scripts/build_shortlist.py --date {date} --stats-first --verbose > /tmp/s1e.txt 2>&1
```
VERIFY: `tail -20 /tmp/s1e.txt` — AGENT_SUMMARY with ≥20 candidates
PRODUCES:
- DB: pipeline_candidates (REQUIRED BY STEP 8 S2 and STEP 13 S3)
- File: betting/data/{date}_s2_shortlist.json
DELEGATE: → bet-scanner (shortlist quality, league diversity, data depth)
IF FAIL: Check if discover_events ran. Verify fixtures table has rows.

---

## STEP 8: S2 — Tipster Cross-Reference

PRE:
- ✅ S1b complete (STEP 6) — tipster_aggregator.py MUST have run
- ✅ DB: tipster_picks has >0 rows for {date} (produced by STEP 6)
- ✅ DB: pipeline_candidates has >0 rows for {date} (produced by STEP 7)
CMD:
```fish
PYTHONPATH=src .venv/bin/python3 scripts/tipster_xref.py --date {date} --verbose > /tmp/s2.txt 2>&1
```
VERIFY: `tail -20 /tmp/s2.txt` — matched >0 tips, tipster_support added to candidates
DELEGATE: → bet-scout (consensus quality, argument independence, contrarian angles)
IF FAIL exit=2: "PRECONDITION_FAILED" → go back and run tipster_aggregator.py (STEP 6 script 5)
IF FAIL 0 tips matched: → brave-search tipster sites → if still 0 → ASK USER

⚠️ **S2 IS NEVER OPTIONAL.** Source fusion (tipsters + stats + web) is the CORE VALUE.

---

## STEP 9: S2.3 — Scrapers (PARALLEL with STEP 8)

PRE: S1e complete (shortlist exists)
CMD:
```fish
PYTHONPATH=src .venv/bin/python3 scripts/run_scrapers.py --sport all --season 2425 --verbose > /tmp/s2_3.txt 2>&1
```
VERIFY: `tail -10 /tmp/s2_3.txt` — league_profiles populated
DELEGATE: → bet-enricher (scraper coverage, source health)
IF FAIL: Note which scrapers failed. Continue — enrichment step fills gaps.

---

## STEP 10: S2.5 — Data Enrichment

PRE: S2 + S2.3 BOTH complete
CMD:
```fish
PYTHONPATH=src .venv/bin/python3 scripts/data_enrichment_agent.py --date {date} --news --gamelogs --verbose > /tmp/s2_5.txt 2>&1
```
VERIFY: `tail -10 /tmp/s2_5.txt` — enrichment yield >40%
DELEGATE: → bet-enricher (yield %, per-sport quality, gap recoverability)
IF FAIL yield<40%: Escalate to user. May need manual source intervention.

---

## STEP 11: S2.6-S2.9 — Sport-Specific Deep Enrichment

PRE: S2.5 complete
CMD (run only for sports present in shortlist):
```fish
# Tennis (if tennis events exist):
PYTHONPATH=src .venv/bin/python3 scripts/fetch_tennis_elo.py --verbose > /tmp/s2_6.txt 2>&1
PYTHONPATH=src .venv/bin/python3 scripts/enrich_tennis_flashscore.py --date {date} --verbose >> /tmp/s2_6.txt 2>&1
PYTHONPATH=src .venv/bin/python3 scripts/tennis_h2h_warmup.py --date {date} --verbose >> /tmp/s2_6.txt 2>&1

# Volleyball (if volleyball events exist):
PYTHONPATH=src .venv/bin/python3 scripts/enrich_volleyball_stats.py --date {date} --verbose > /tmp/s2_7.txt 2>&1

# Hockey (if hockey events exist):
PYTHONPATH=src .venv/bin/python3 scripts/enrich_hockey_stats.py --date {date} --verbose > /tmp/s2_8.txt 2>&1

# Basketball (if basketball events exist):
PYTHONPATH=src .venv/bin/python3 scripts/enrich_basketball_stats.py --date {date} --verbose > /tmp/s2_9.txt 2>&1
```
VERIFY: Check enrichment logs — coverage improved for target sports
DELEGATE: → bet-enricher (per-sport readiness for S3)
IF FAIL: Note gaps. Continue to S3 with PARTIAL data flagged.

---

## STEP 12: ⛔ DATA PHASE GATE

PRE: S2.5 + sport enrichment complete
CMD:
```fish
PYTHONPATH=src .venv/bin/python3 scripts/validate_phase.py --date {date} --phase data --format json > /tmp/gate_data.txt 2>&1
```
VERIFY: Exit code 0. If exit code 1 → STOP.
DELEGATE: none
IF FAIL: Read validation errors. Fix data gaps before proceeding to S3.

---

## STEP 13: S3 — Deep Statistical Analysis

PRE:
- ✅ DATA GATE passed (STEP 12)
- ✅ DB: pipeline_candidates has >0 rows for {date}
CMD:
```fish
PYTHONPATH=src .venv/bin/python3 scripts/deep_stats_report.py --date {date} --gemini --verbose > /tmp/s3.txt 2>&1
```
VERIFY: `tail -20 /tmp/s3.txt` — AGENT_SUMMARY with candidates_analyzed ≥20% of shortlist
PRODUCES: DB: analysis_results (REQUIRED BY STEP 17 S7)
DELEGATE: → bet-statistician (edge validation, three-way cross-check, safety scores)
IF FAIL exit=2: "PRECONDITION_FAILED" → run build_shortlist.py first (STEP 7)
IF FAIL <20%: Verify correct shortlist was used. Re-run.

---

## STEP 14: S4 — Odds Evaluation

PRE: S3 complete (analysis_results in DB)
CMD:
```fish
PYTHONPATH=src .venv/bin/python3 scripts/odds_evaluator.py --date {date} --verbose > /tmp/s4.txt 2>&1
```
VERIFY: `tail -20 /tmp/s4.txt` — EV calculated for candidates
DELEGATE: → bet-valuator (EV per candidate, drift >8%, Kelly sizing)
IF FAIL: Check if odds_history has data. May need to re-run fetch_odds_api.

---

## STEP 15: S5+S6 — Context + Upset Risk

PRE: S3 + S4 complete
CMD:
```fish
PYTHONPATH=src .venv/bin/python3 scripts/context_checks.py --date {date} --verbose > /tmp/s5.txt 2>&1
PYTHONPATH=src .venv/bin/python3 scripts/upset_risk.py --date {date} --verbose > /tmp/s6.txt 2>&1
```
VERIFY: `tail -10 /tmp/s5.txt` + `tail -10 /tmp/s6.txt` — context flags + upset scores
DELEGATE: → bet-challenger (bear cases, injuries, weather, upset scoring)
IF FAIL: Context/upset are enrichment — if they fail, continue but note gap.

---

## STEP 16: ⛔ COMPLETENESS GATE

PRE: S3 + S4 + S5+S6 ALL have verdicts
VERIFY: Check that all three specialist verdicts (bet-statistician, bet-valuator, bet-challenger) were received.
IF ANY MISSING: Go back and run the missing step. Do NOT proceed.
DELEGATE: none

---

## STEP 17: S7 — Decision Gate

PRE:
- ✅ COMPLETENESS GATE passed (STEP 16)
- ✅ DB: analysis_results has >0 rows for {date}
CMD:
```fish
PYTHONPATH=src .venv/bin/python3 scripts/gate_checker.py --date {date} --verbose > /tmp/s7.txt 2>&1
```
VERIFY: `tail -20 /tmp/s7.txt` — ≥10 candidates processed, approved + extended counts
PRODUCES: DB: gate_results (REQUIRED BY STEP 20 S8)
DELEGATE: → bet-challenger (gate audit, strength tiers, bear cases)
IF FAIL exit=2: "PRECONDITION_FAILED" → run deep_stats_report.py first (STEP 13)
IF FAIL <10 candidates: Investigate. May need to expand with --no-strict.

---

## STEP 18: ⛔ ANALYSIS GATE

CMD:
```fish
PYTHONPATH=src .venv/bin/python3 scripts/validate_phase.py --date {date} --phase analysis --format json > /tmp/gate_analysis.txt 2>&1
```
VERIFY: Exit code 0. ≥3 STRONG+MODERATE candidates. If <3 → emergency expansion.
IF FAIL: Re-check gate with looser thresholds or expand candidate pool.

---

## STEP 19: S7.5+S7.6 — Betclic Validation + Repeat Check

PRE: S7 complete, gate_results in DB
CMD:
```fish
PYTHONPATH=src .venv/bin/python3 scripts/validate_betclic_markets.py --date {date} --verbose > /tmp/s7_5.txt 2>&1
PYTHONPATH=src .venv/bin/python3 scripts/check_48h_repeats.py --date {date} --format json --verbose > /tmp/s7_6.txt 2>&1
```
VERIFY: Markets validated, repeat-loss flags noted
DELEGATE: none (sidecar validation)
IF FAIL: Note unavailable markets for coupon builder.

---

## STEP 20: S8+S9 — Build + Validate Coupons

PRE:
- ✅ ANALYSIS GATE passed (STEP 18)
- ✅ DB: gate_results has >0 rows for {date}
CMD:
```fish
PYTHONPATH=src .venv/bin/python3 scripts/coupon_builder.py --date {date} --verbose > /tmp/s8.txt 2>&1
PYTHONPATH=src .venv/bin/python3 scripts/validate_coupons.py betting/coupons/{date}_coupon_*.md --verbose >> /tmp/s8.txt 2>&1
PYTHONPATH=src .venv/bin/python3 scripts/generate_coupon_pdf.py --date {date} >> /tmp/s8.txt 2>&1
```
VERIFY: `tail -20 /tmp/s8.txt` — coupons built, validation passed
DELEGATE: → bet-builder (portfolio quality, correlation, per-pick reasoning)
IF FAIL exit=2: "PRECONDITION_FAILED" → run gate_checker.py first (STEP 17)

---

## STEP 21: ⛔ BUILD GATE

CMD:
```fish
PYTHONPATH=src .venv/bin/python3 scripts/validate_phase.py --date {date} --phase build --format json > /tmp/gate_build.txt 2>&1
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

Pattern: RUN → VERIFY → DELEGATE → RECEIVE VERDICT → ADVANCE
1. Run script → redirect to /tmp/sN.txt → `tail -20`
2. `new_task` to specialist — include: output summary, metrics, specific questions
3. Receive verdict — check: ≥3 metrics? original analysis? justified?
4. If REJECTED → investigate, re-run, re-delegate
5. If APPROVED → advance to next step

**Skipping delegation = FAILED SESSION.**

---

## ANTI-PATTERNS (model has done ALL of these — STOP YOURSELF)

- ❌ Never run `pipeline_orchestrator.py` (BANNED)
- ❌ Never advance without specialist verdict
- ❌ Never paste raw terminal output as "analysis"
- ❌ Never skip sequentialthinking before decisions
- ❌ Never assume scripts "just work" — verify preconditions
- ❌ Never run tipster_xref.py without tipster_aggregator.py having run first
- ❌ Never proceed past a GATE with exit code 1
