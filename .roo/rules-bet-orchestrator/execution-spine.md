# Execution Spine — Orchestrator Step-by-Step

## Pipeline Order (MANDATORY — never reorder)

| Phase | Script Command | Delegate To | Expected Output |
|-------|---------------|-------------|-----------------|
| S0 | `python3 scripts/settle_on_finish.py --betting-day {date}` | bet-settler | Settlement summary, PnL, bankroll update |
| S0.2 | `python3 scripts/analyze_betclic_learning.py` | (inline) | Advisory patterns, market hit rates |
| S1 | `env PYTHONPATH=src python3 scripts/discover_events.py --date {date} --verbose` | bet-scanner | AGENT_SUMMARY JSON, fixture count |
| S1.2 | `python3 scripts/ingest_scan_stats.py --date {date} --verbose` | (inline) | stats_cache + team_form DB populated |
| S1.5 | `python3 scripts/tipster_aggregator.py --date {date} --verbose` | bet-scout | Tipster consensus, picks |
| S1.8 | (fixture verification against ≥2 sources) | bet-scanner | Verified/unverified flags |
| S1.9 | `python3 scripts/generate_market_matrix.py --date {date} --stats-first` | (inline) | market_matrix files |
| S2 | `python3 scripts/build_shortlist.py --date {date} --stats-first --all-fixtures` | bet-scanner | s2_shortlist.json/.md |
| S2.3 | `python3 scripts/enrich_football_stats.py --date {date} --verbose` | bet-enricher | Football team_form enriched |
| S2.5 | `python3 scripts/data_enrichment_agent.py --date {date} --verbose` | bet-enricher | Generic enrichment |
| S2.7 | `python3 scripts/enrich_volleyball_stats.py --date {date} --verbose` | bet-enricher | Volleyball data |
| S2.8 | `python3 scripts/enrich_hockey_stats.py --date {date} --verbose` | bet-enricher | Hockey data |
| S2.9 | `python3 scripts/enrich_basketball_stats.py --date {date} --verbose` | bet-enricher | Basketball data |
| S3 | `python3 scripts/deep_stats_report.py --date {date} --verbose` | bet-statistician | s3_deep_stats.json/.md |
| S3B | (time-sensitive: lineups, weather, late injuries, odds movement) | bet-statistician | Updated context |
| S4 | (tipster deep-dive + odds evaluation) | bet-valuator | EV, fair odds, Kelly stakes |
| S5-S6 | (context + upset risk per candidate) | bet-challenger | Upset scores, bear cases |
| S7 | `python3 scripts/gate_checker.py --date {date} --verbose` | bet-challenger | gate_results, risk tiers |
| S8 | `python3 scripts/coupon_builder.py --date {date} --verbose` | bet-builder | Coupon files |
| S9 | (V1-V10 validation) | (inline) | Validation pass/fail |
| S10 | (artifact generation) | bet-builder | Final deliverables |

## Delegation Protocol
1. Run script → parse output (AGENT_SUMMARY or key metrics)
2. `new_task(mode, message)` — include: script output summary, file paths, specific questions
3. Receive verdict → check quality (≥3 metrics? original analysis? justified?)
4. If REJECTED or FLAGGED → investigate, potentially re-delegate or re-run
5. If APPROVED → advance to next phase

## Critical Gates
- S3 must process ≥20% of shortlist candidates. If fewer → re-run with correct shortlist.
- S7 must process ≥10 candidates. If fewer → investigate and expand.
- Post-S7: ≥3 sports in approved picks. If not → trigger expansion loop.
- Betclic learning history (DB `bets`+`coupons` tables) must be read before ANY analysis.

## Data Flow Verification (R18)
Before running ANY script:
1. READ its code — understand what it READS (JSON keys, DB tables) and WRITES (output format, paths)
2. TRACE connection to NEXT script — does consumer read same keys/tables the producer writes?
3. VERIFY with actual data — check real JSON files, query real DB tables
4. If mismatch found → FIX before running, never blindly re-run

## Anti-Patterns
- Never run `pipeline_orchestrator.py` (BANNED)
- Never advance without receiving specialist verdict
- Never paste raw terminal output as "analysis"
- Never skip sequentialthinking before decisions
- Never assume scripts "just work" — read code first (R18)
