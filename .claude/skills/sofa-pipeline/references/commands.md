# Command catalogue - sofa

Every command once, one comment each. Python runs as
`PYTHONPATH=src:. .venv/bin/python ...` (3.12; install with
`.venv/bin/python -m pip`). Exit codes: 0 OK, 1 PARTIAL, 2 FAILED; PARTIAL on
RESOLVE / OFFER / SAMPLES is the normal shape of a healthy run. Read this when
you need a command beyond those in `SKILL.md`.

## The day

```bash
.venv/bin/python scripts/sofa/ensure_bridge.py                                   # always first: brings the bridge up if down, then check_bridge
.venv/bin/python scripts/sofa/check_bridge.py                                    # the bridge grade alone
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d>        # the full day (DEFAULT_SEQUENCE)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --from-stage RESOLVE --run-id <id>   # resume a run from a stage
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --only SHEET --run-id <id>   # after a SHEET estimator change (a rebuild re-runs SHEET only on an old-rule sheet); ~10 min parsing when listings changed, ~30 s on a rebuild - do not kill a quiet SHEET
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <d> [--dry-run] [--skip-audits]   # THE rebuild: stale prices, SPORT_IDENTITY, SHEET if refused, FIXTURE_CHECK .. PDF, audits; a finished day refreshes nothing
PYTHONPATH=src:. .venv/bin/python scripts/sofa/day_status.py --date <d>         # one status report, no network; exit 0 / 1 WARN / 2 broken
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/shadow_daily.py --date <d> --chain >> runs/sofa/shadow/daily_<d>.log 2>&1 &   # hockey / basketball / volleyball loop: snapshots + SPORT_IDENTITY for D and D+1, settles D, D-1, D-2
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/cs2_daily.py --date <d> --chain >> runs/sofa/cs2/daily_<d>.log 2>&1 &   # the CS2 loop; a second loop for the date refuses
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/capture_closing.py --date <d> --loop >> runs/sofa/<d>/capture_closing.log 2>&1 &   # closing prices -> closing.jsonl; normally started by the loops (capture_closing.ensure_loop), not by hand; stops after 12 failed passes; started before the build it waits for 11_coupon.json
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_boosts.py --date <d>         # Superbet boosts snapshot (not the coupon); exit 2 on an open breaker
PYTHONPATH=src:. .venv/bin/python scripts/sofa/read_set.py --date <d> [--buffer N] [--unread] [--split K] [--out-dir <dir>] [--no-dossier] [--db-path <db>]   # C3's read set as compact per-sport files under runs/sofa/<d>/read_set/; also each match's dossier (runs/sofa/<d>/dossier/, bet.sofa.dossier, offline) and the leg's `dossier` path
PYTHONPATH=src:. .venv/bin/python scripts/sofa/check_analyst_report.py --report <md> [--report <md>]   # depth check of an analyst report (Kontekst (web), dossier, KEEP reasons); exit 1 = rewrite; the PostToolUse hook (.claude/hooks/check_analyst_report.py) runs it on every report written
PYTHONPATH=src:. .venv/bin/python scripts/sofa/merge_reads.py --date <d> --report <md> [--author analyst] [--dry-run]   # merge a report's json vetoes / reads arrays into vetoes.json / reads.json; exit 2 = refused
PYTHONPATH=src:. .venv/bin/python scripts/sofa/verify_legs.py --date <d> [--all] [--live [--limit-fixtures N]] [--out-dir <dir>]   # deterministic per-leg defect screen (sheet row, side, notes, own sample, clocks, sport identity, live price); --all = every printed leg; exit 1 = findings
```

## Single stages (rebuild_day.py runs them in order; by hand only to debug)

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_fixture_check.py --date <d>   # fresh starts / statuses -> fixture_status.json
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <d>      # CONFIDENCE -> 08_confidence.json
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --only SHADOW   # hockey / basketball / volleyball snapshot
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --only CS2      # CS2 snapshot
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_sport_identity.py --date <d> [--sport hockey] [--if-snapshot]   # pin Sofascore ids; --if-snapshot: no snapshot = exit 0
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_sport_confidence.py --date <d>   # SPORT_CONFIDENCE -> 08_confidence_sports.json
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon.py --date <d>        # COUPON_ASSEMBLY -> 11_coupon.json; exit 1 while 08_confidence_sports.json is absent
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_pdf.py --date <d>    # KUPON_<d>.pdf + .html
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_html.py --date <d>   # the HTML view alone
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_family_record.py --date <d>  # family_record.json for the HTML filter
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_coupon.py --date <d>        # the old VALUE selector (06_coupon.json): structure, arithmetic, anti-selection
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_variants.py --date <d>      # 11_coupon.json: C1-C3, U1-U3
```

## Settle and record

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D-1> --only SHADOW_SETTLE   # settle the hockey / basketball / volleyball day
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D-1> --only CS2_SETTLE      # settle the CS2 day
PYTHONPATH=src:. .venv/bin/python scripts/sofa/settle_cs2.py --sweep-from <D-7> --sweep-to <D-2>   # CS2 re-settle sweep
PYTHONPATH=src:. .venv/bin/python scripts/sofa/refresh_sport_history.py [--days 14] [--dry-run]   # bridge; the sports' finished games enter the history (run first by refresh_line_evidence.py)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/refresh_line_evidence.py --before <D> [--dry-run] [--skip-sport-rows] [--skip-history]   # every morning, bridge up first (step 0 refreshes the sports' history), after D-1 is recorded, before D's CONFIDENCE (sofa-day 1a: bridge part first, fits with --skip-history beside RESOLVE); ~15-20 min, the sport fits in parallel; exit 1 = a sport's row fit failed, earlier rows reused
PYTHONPATH=src:. .venv/bin/python scripts/sofa/resettle_sweep.py --from <D-14> --to <D-2> --include-day <D-5>   # every morning; statistic gaps close days later; no bridge = exit 1
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_settle_identity.py --from <d> --to <d> [--sport all]   # after D-1's settle; exit 1 on a finding
PYTHONPATH=src:. .venv/bin/python scripts/sofa/record_results.py --from <D-8> --to <D-1>   # the ledger; also marks each day's KUPON pdf / html (--no-mark: not); exit 1 = MISMATCH
PYTHONPATH=src:. .venv/bin/python scripts/sofa/mark_coupon_results.py --from <d> --to <d> [--force] [--no-render]   # 13_results.json + KUPON coloured by result; offline
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_ledger.py --from <d> --to <d> [--variant official]   # read the ledger by epoch group
PYTHONPATH=src:. .venv/bin/python scripts/sofa/regrade_settled.py --moved-void --dry-run   # then --apply; --players regrades props from the own squad; --cards-bench, --player-not-started
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_shadow.py --from <d> --to <d> [--sport hockey]   # measured sports' settle audit
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_cs2.py --from <d> --to <d> [--history]   # CS2 audit
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_clv.py --from <d> --to <d>   # closing-line value
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_boosts.py --from <d> --to <d>   # boosts audit
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_niches.py --from <d> --to <d> [--min-matches N]   # evidence, never a bet list
PYTHONPATH=src:. .venv/bin/python scripts/sofa/purge_entity_alias.py --dry-run   # a wrongly verified team alias; --list-suspects
PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_entity_map.py [--dry-run] [--reteach]   # identity K1: entity map learns from every day on disk; --apply backs up sofa_entity first
PYTHONPATH=src:. .venv/bin/python scripts/sofa/report_entity_queue.py --date <d>   # identity K4: NEEDS_ALIAS queue -> runs/sofa/<d>/entity_queue.md; no network
```

## Refit (on a copy of the DB; install only with the operator's go)

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/prepare_refit.py --date <d> [--db-path <copy>] {backup [--db <path>]|rebuild-cache-rows [--dry-run|--confirm] [--without-db-backup] [--derived ...] [--no-tennis-rating]|fit|compare [--days <d> <d2>] [--with-sheet]|install --confirm|restore --confirm --backup <dir>}   # the refit driver; install runs tests/sofa and restores on failure
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_confidence.py --classes-only   # only the by_class curves
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_confidence.py --db-path <replay copy> --out <staged copy of the installed calibration> --line-curves-only   # only the per-line curves; every other key byte for byte
PYTHONPATH=src:. .venv/bin/python scripts/sofa/install_line_curves.py --staged <staged file> (--dry-run | --confirm) [--backup-dir config/backup_<d>_line_curves]   # installs only by_market_direction_line; backup, tests, restore on failure
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_tennis_serve_curves.py --before <d> --out-dir data/refit_tennis_serve_<d> [--played-cache f.pkl]   # tennis serve curves, staged; NOT installed (model-state.md)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_score_market_curves.py --out-dir data/refit_new_markets_<d> --football-rows <1x2/dnb fit rows.csv.gz> --tennis-rows <tennis_sets rows.csv>   # score-market slice curves + set_score_not, staged
PYTHONPATH=src:. .venv/bin/python scripts/sofa/install_new_market_curves.py --dir data/refit_new_markets_<d> --confirm   # install staged new-market curves
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_sport_confidence.py --sport {hockey|basketball|volleyball|cs2|all} --before <d> [--dry-run] [--rows-out <dir>] [--bb-freshness auto|on|off]   # sport curves
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_sport_confidence.py --sport all --before <d> --dry-run --rows-out <dir> --out <dir>/cal.json   # ~15 min a sport: the Superbet rows line evidence reads
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_settleability.py --before <d> [--dry-run]   # config/sofa_settleability.json
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_line_evidence.py --before <d> --sport-rows-dir <dir> [--dry-run]   # after every curve refit; without the dir no price-band cap for the sports
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_count_dispersion.py --before <d> --cases <dir> [--write]   # without --write a dry run
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_calibration.py --from <d> --to <d> [--epoch stats_only] [--write-config --before <d>]   # PASS n >= 300 and abs gap <= 2 pp
PYTHONPATH=src:. .venv/bin/python scripts/sofa/find_women_competitions.py   # candidates for the women's class
PYTHONPATH=src:. .venv/bin/python scripts/sofa/find_friendly_competitions.py --out docs/sofa/evidence/friendly_candidates_<d>.json   # candidates; a person decides
```

## History backfill (bridge; short chunks, resumable)

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_listings.py --sport {football|tennis|hockey|basketball|volleyball} --days 730 --max-minutes 7   # listings history
PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_event_stats.py --sport {football|tennis} --days 365 [--board-days 7] --max-minutes 7   # event statistics
PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_football_lineups.py --days 365 --max-minutes 7   # football lineups
PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_cs2.py --days 180       # CS2 history
PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_event_extra.py --kind {shotmap|point_by_point|incidents} --sport {football|tennis|hockey|basketball|volleyball} --days 120 --max-minutes 7   # sofa_event_extra
```

## Measurement (read-only evidence, never a gate)

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_count_families.py        # distribution family per count market (flags: evidence doc)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_pooling.py               # pooling / per-market K / league effect
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_k_under_dispersion.py    # per-market K under the fitted dispersion
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_dependence_goals.py      # copulas, side correlations, goals model
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_tennis_calibration.py    # tennis rating scopes, calibration method
PYTHONPATH=src:. .venv/bin/python scripts/sofa/report_market_coverage.py --date <d> [--sports|--sports-only] [--sports-raw-dir <dir>] [--sports-out-dir <dir>]   # unread market names; --sports probes Superbet live
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_settleability.py --from <d> --to <d> [--with-fit] [--json-out f] [--md-out f]   # settleability cells
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_blocked_families.py [--from <d>] [--to <d>]   # blocked families
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_sport_identity.py --from <d> --to <d> [--sport hockey]   # sport identity rates
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_model_defects.py [--start <d>] [--end <d>]   # model defects
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_own_sample_gap.py --from <d> --to <d> [--sport football|tennis]   # model vs own sample
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_sample_composition.py [--start <d>] [--end <d>] --metrics goals_for corners_total   # sample composition
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_schedule_context.py [--start <d>] [--end <d>]   # schedule context flags
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_score_model.py --sport {hockey|basketball|volleyball} --date <d> [--date <d2>] [--rows-out f]   # score model on a day
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_score_history.py --sport <s> --start <d> --end <d> [--params '{...}']   # score model on the history
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_model_information.py --rows <rows.jsonl>   # information in the model's p
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_player_props.py --sport {basketball|hockey} [--date <d>] [--rows-out f]   # sport player props
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_devig.py --from <d> --to <d>   # devig methods
PYTHONPATH=src:. .venv/bin/python scripts/sofa/probe_lineup_availability.py --date <d> [--dry-run] [--summary]   # not yet run
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_league_rate_rule.py [--from <d>] [--to <d>] [--skip-football]   # audit A2 (T-A2-league-rate-refusals)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_bucket_design_effect.py --rows-dir <dir> --days <d>...   # audit A4 walk-forward
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_unit_strength.py [--from <d>] [--to <d>]   # audit A1
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_sport_derived.py --sport all --start <d> --end <d> [--max-games 4000] [--json-out f] [--md-out f]   # sport DC / volleyball sets keys walk-forward
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_settled_by_market.py --from <d> --to <d> [--p-min 0.70] [--min-n 20] [--md-out f] [--json-out f]   # every market x direction: hit, p, 1/odds, ROI; sports never pooled
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_team_identity.py [--from <d>] [--to <d>] [--sport all|football|...] [--md-out f] [--json-out f]   # identity K0 (T-IDENTITY-unexplained)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_day_anchor.py [--from <d>] [--to <d>] [--md-out f] [--json-out f]   # identity K2 precision
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_tournament_day.py --from <d> --to <d> [--precision-days 60] [--offline]   # identity K3; ASKS THE BRIDGE once per uncached (tournament, day)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_sport_incidents.py --sport {hockey|basketball} [--json-out f] [--md-out f]   # "1. gol" / race to X walk-forward
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_tennis_aces_opponent.py --cut 2026-01-01 [--played-cache f.pkl] [--md-out f]   # TENNIS_ACES_OPPONENT replay; ~25 min
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_line_curves.py --db data/refit_2026-10-17/sofa_replay.db [--md-out f] [--json-out f]   # per-line vs pooled curve (~3 min)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_selection_walk_forward.py --from <d> --to <d> [--md-out f]   # T-FAMILY-SELECTION
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_read_value.py --from <d> --to <d> [--md-out f]   # do analyst / verifier reads improve the coupon: KEEP vs removed legs, match bootstrap
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_red_flags.py --from <d> --to <d> [--md-out f]   # red flags on printed legs; offline, ~20 s (T-RED-FLAG-SCRIPT)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_tennis_serve_market_line.py --from <d> --to <d> --staged data/refit_tennis_serve_2026-10-17 [--md-out f]   # T-TENNIS-SERVE-MARKET-LINE
```

## Chat slip to a target price (outside the pipeline; read-only, no network)

```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_slip.py --date <d> --target 4 [--start-from 10:00 --start-to 12:00] [--slips N] --allow-rest [--reserve 1] --read-set-dir runs/sofa/<d>/read_set_slip   # bet.sofa.slip_builder: exact knapsack, refused reads drop out; loop: bet-slip-audit skill; exit 0 / 1 fewer supported / 2 no coupon, no family record or bad arguments
```

## Gates before a commit

```bash
.venv/bin/python -m pytest tests/sofa -q                                          # offline tests
.venv/bin/python -m ruff check src/bet/sofa scripts/sofa                          # lint
.venv/bin/python -m mypy --strict --no-incremental src/bet/sofa scripts/sofa      # types; a stale cache gives false errors
PYTHONPATH=src:. .venv/bin/python scripts/sofa/check_test_registry.py             # test registry
```
