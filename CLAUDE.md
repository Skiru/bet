# Working agreement — `bet`

## Stats-only coupon epoch (2026-10-05 07:15Z, `bet.sofa.epochs.STATS_ONLY_FROM_UTC`)

Plan `docs/sofa/history/PLAN_2026-10-05_SETTLE_I_KUPON.md` (operator decisions D1-D7).
A build of a day >= 2026-10-05 made after 07:15Z is **stats-only**:
- **Confidence from the statistics alone.** SHEET keeps the price out of
  `p_central` (no tennis ladder centre, no rating blended with the price, no
  empirical shrink to the rung's price, no handicap centre on the ladder);
  the rating is published beside it as `forecast_p` ("model", uncalibrated,
  never a gate). The price is only the betting condition: x = confidence x
  odds >= 0.90, ladder margin <= 15%, ODDS_TOO_LOW, not started, fresh price;
  `MAX_DISAGREEMENT` and `UNREACHABLE_BAR` are off; a moved price re-prices
  the leg (x at the fresh odds). A thin direction bucket caps the `by_market`
  curve too (K13). Bet Builders are chosen and ordered by
  `combined_probability`, stakeable at combined p x odds after haircut >= 0.90.
- **One coupon artifact: `runs/sofa/<d>/11_coupon.json`** (`build_coupon.py`,
  COUPON_ASSEMBLY, from `08_confidence.json`), a superset of the 08 format;
  every reader goes through `confidence.coupon_artifact()`. Order: confidence,
  then the earlier start, legs of one match together (`coupon_order`),
  positions 1..N; legs locked from an earlier print first, unnumbered;
  builders B1.. on their own PDF pages. The PDF writes `12_printed.json`, the
  record the next rebuild locks from. CONFIDENCE refuses a SHEET not built
  under the rule (a rebuild starts at SHEET).
- **Reads at the end of the chain:** a leg that passed every gate and a
  WATCH / NO_BET (or the automatic MODEL_ABOVE_OWN_SAMPLE) removed is in
  `removed_by_reads`, graded on its own (audit_settlement 7i, ledger
  `removed:reads`), never in the coupon's result. Analysts read the first 30
  positions, every printed builder leg and whatever the operator adds to
  `read_requests.json` (`/sofa-analyze` "dodatkowo: ..."); C3 checks that set.
- **WARIANT and WARIANT WSZYSTKIE are retired** (refused, exit 2); their
  files up to the morning of 10-05 stay and are graded as before (D5). The
  separate sport coupons stop only when the sports go on the coupon (plan
  part 5, `SPORTS_ON_COUPON_FROM_UTC`).
- **FIXTURE_CHECK** (`run_fixture_check.py`, bridge) in a rebuild before
  CONFIDENCE: a fresh `/event` start replaces RESOLVE's frozen clock (K12); a
  postponed / cancelled / abandoned printed match is FIXTURE_NOT_AS_SCHEDULED
  (K14); no bridge = UNVERIFIED, nothing refused.
- **SETTLE:** a match moved > 48 h or awarded is a refund (0 u.), never a
  loss and never a `sofa_settled_row`; player props only from the player's
  own squad (PLAYER_AMBIGUOUS); a printed leg without a sheet row is graded
  into `07_settled_printed.json`. Shadow / CS2 identities are pinned, unique
  per day and checked by `audit_settle_identity.py`.
- **The ledger and the audits keep the epochs apart:** `official` (stats_only)
  / `official:pre_stats_only` (legs locked from the 10-05 morning print);
  `audit_ledger` groups do 10-04 / 10-05 rano / stats_only, never summed.
  The official coupon before and after 07:15Z on 10-05 is not one experiment.

## Operator decisions 2026-10-05 (morning, before the 10-05 day)

From the 10-05 coupon on (`docs/sofa/history/RAPORT_NOC_2026-10-05.md` section 4a):
the **official coupon** takes confidence x odds >= 0.90 and a ladder margin up
to 15% (until 10-04: x > 1.0, 10.5%) and prints every single in its artifact
(the 30-single page limit lifted the same morning: "don't limit to 30"); floor
0.70 and WATCH honoured - unchanged. Analysts read at most the best 30: C3
requires an analyst read on the first 30 printed singles (artifact order) and
every printed builder leg (`confidence.legs_requiring_read`); the rest print
unread, a WATCH/NO_BET on any printed leg still removes it. A 0.80 confidence floor was considered and declined ("many options").
Measured (football 09-24..10-04): 2574 rows -4.5% -> 8871 rows -4.8% - volume,
not edge. **Sport coupons** (`sport_coupon.rule_for`, `RULE_CUTOVER`): p x odds
>= 0.90, margin <= 15%; hockey and basketball print and gate on
p = a + c*logit(fair_p) (`config/sofa_sport_price_calibration.json`, fitted by
`fit_sport_price_calibration.py --before <d>`, never mid-day); a volleyball leg
needs a tournament with a SETTLED event in the last 14 days. **A leg printed
before its start counts**: a rebuild keeps (locked) the legs whose match had
started; a leg removed before its start stays removed. Unchanged by decision:
tennis retirements, the seven admitted player props. Before the next refit:
measure the tennis games population of replay matches without `/statistics`.
The official coupon before and after 10-05 is not one experiment.

## Refit epoch 2026-10-05 (installed 02:52Z, before the 10-05 day)

`6fea99fd`, fitted after settling 10-04 on a cache replay rebuilt with the
night's fixes (`docs/sofa/history/RAPORT_NOC_2026-10-05.md`: same-competition goal
samples for league fixtures only - measured worse on knockouts; a
self-contradicting score is no count; tennis games and tiebreaks off the set
score; retirements, walkovers, Coverage canceled and tennis exhibitions out of
the replay; HISTORY_PARSER_VERSION 2026-10-04.5). 1,089,163 replayed matches;
curves on 57.17M rows. K_CENTRE football 15 / tennis 5 unchanged; curves 92 ->
94, none removed; operator keys carried over. Report
`data/refit_2026-10-05/compare_report.md`; backups `config/backup_2026-10-05`,
`data/backup_2026-10-05/sofa.db`. Days before 10-05 are a different epoch.
Open operator decisions: section 4 of the night report.

## Refit epoch 2026-10-03 (installed 06:45Z, before the 10-03 day)

Fitted on 55.2M settled rows (cache replay rebuilt: 1.05M matches, 1.197M
football player rows), max_settled_run_date 2026-10-02. K_CENTRE football
25 -> 15, tennis 2 -> 5; K_PRICE NOT_FITTED; half_match_coherence OK. Days
before 10-03 are a different comparability epoch. Operator decisions taken
that morning (config/sofa_confidence_calibration.json, carried over by any
refit): `refused_markets = ["shots_total|UNDER", "fouls_total|UNDER", "shots_for|UNDER"]` (the last added 08:19Z after the 10-03 review: priced live rows at claimed ~0.69 realised 0.53, ROI -18.8%);
`admitted_player_markets` = all seven football player props (operator's
order, against the recommendation: one-sided prices, no ROI evidence - the
props now print at their OVER curve's realised rate, e.g. fouls/tackles
OVER claimed 0.725 realise 0.56). Report `data/refit_2026-10-03/compare_report.md`;
backups `config/backup_2026-10-03` (with the keys), `config/backup_2026-10-03_prekeys`
(the DB copy `data/backup_2026-10-03/sofa.db` was deleted 2026-10-05 on the operator's
order; only the current epoch's DB copy is kept). Measure the admitted props separately
before the next refit.

**Between 10-03 and 10-04 (night, ~22:35Z):** `config/sofa_tennis_tier_baselines.json`
refitted and installed (the 09-26 file predated the 09-29 match-tiebreak fix: ITF
games_total means -1.3; OOS from 09-27 games_total MSE -2.01 [-2.48, -1.56]); backup
`config/backup_2026-10-04_tennis/`. `tennis_rating.json` and `sofa_side_correlations.json`
NOT installed (no OOS gain / OOS worse). Also landed that night, changing what history
produces: the `ZERO_NOT_RECORDED` guard, cards read only from a card record
(`CARDS_NOT_RECORDED`: red-only incident lists had counted a 7-card match as 2), the per-half
full feed's omitted 0-0 restored for offsides/yellow cards, a partial feed's single corner
refused (HISTORY_PARSER_VERSION 2026-10-04.2), and competition 851 + six ids on the friendly
list. The ~67k cache-replay rows graded on fake zeros leave only at the next
`rebuild-cache-rows`. Evidence: `data/night_2026-10-03/` (RAPORT_NOC.md first).

**2026-10-04 (day, ~06:45Z):** operator added `goals_1h_total|UNDER` to `refused_markets`
from that day's coupon on (10-03: 6 printed went 3/6 at claimed 0.819, price 0.762; the
market has no curve of its own and read `pooled:football`); backup `config/backup_2026-10-04_g1h/`.
Props and WARIANT kept as they were (operator). Also that morning: Superbet's own start
signal is read. `superbet.odds_items` drops live-state odds (`offerStateId` 2) for every
reader; OFFER records `superbet_started_utc` (event `metadata.status` STARTED/FINISHED or a
live offer state) and `superbet_kickoff_seen_utc` (Superbet's current `utcDate`), and SHEET,
COUPON and CONFIDENCE gate on the earliest of the three clocks. The two RESOLVE clocks were
both late on matches Superbet had already started or moved (Seggerman - Tajima: 08:00Z frozen,
06:15Z live). Blind spot left: a suspended pre-match offer with no metadata (`{"1":"stop"}`)
says nothing; only the clocks see it.

**2026-10-04 (afternoon), history comparability - code changes what history produces from
10-05 on; no refit installed** (report `docs/sofa/history/RAPORT_2026-10-04_POROWNYWALNOSC_HISTORII.md`,
measurements `data/analysis_2026-10-04_history/`). After Farense - Chaves U3.5 lost 4-0:
- `bet.sofa.comparability` is the ONE "does this past match count" rule for every history
  reader (samples, football/tennis rating, tennis prior, cache replay - which had no friendly
  filter - player model + fit, shadow score model, CS2, stats backfill). +32 reviewed
  pre-season/exhibition ids (Torneio de Verao 36573 had leaked); `find_friendly_competitions.py`
  proposes candidates. Football friendlies stay keyed on ids; other sports on name markers.
- Goal samples (`goals_total`, `goals_for`, `goals_1h_for`, `goals_2h_for`) = the side's REGULAR
  matches of the fixture's competition when >= 5, else the usual newest ten
  (`SAME_COMPETITION_METRICS`); measured goals_for log-loss -0.0055, both halves. Corners/fouls/
  shots/cards untouched (no gain or worse); current-season-only was worse everywhere - do not
  "fix" it that way. Side effect: more goal legs hit SAMPLE_CROSSES_SEASON (10-03 replay: 44 -> 63).
  The confidence curves were fitted on old-rule replay rows: a refit (operator's) re-aligns them.
- `runs/sofa/<d>/reads.json` (`LegRead`): NO_BET removes everywhere; **WATCH removes from the
  official coupon, stays marked in WARIANT** (operator, 10-04); `audit_variants` C3 from 10-05:
  every printed official leg has an analyst read. Football `MODEL_ABOVE_OWN_SAMPLE` (model -
  own sample hit rate > 0.15, props excluded) is an automatic WATCH. Legs carry `sample_hit_rate`
  and `context_flags` (`MAKEUP_FIXTURE` only while the meeting is still owed, `LONG_LAYOFF`,
  `CONGESTED` - shown, never gated: a make-up fixture measured no bias).
- `SOFA_NOW` freezes `timeutil.now()` for as-of replays only; `run_pipeline.py` refuses it.

## The only pipeline in service is `sofa`

Sofascore statistics, Superbet prices, football and tennis. The product of a
day is **`runs/sofa/<date>/KUPON_<date>.pdf`**.

```
BOARD → RESOLVE → OFFER → SAMPLES → OFFER → SHEET → COUPON
                     (rebuild: FIXTURE_CHECK) ↘ CONFIDENCE → COUPON_ASSEMBLY (11_coupon.json) → PDF   ★ the product
                    deliberately separate:  SETTLE → FIT
```

**There is no `DISCOVER`, `ENRICH`, `ANALYZE`, `MARKET_CONTEXT` or `TIPSTERS`
stage.** Those are the retired `simple` pipeline's vocabulary. The two share no
code and no stage names, and there is no mapping between them. Reaching for the
old words is the most common way to start a session wrong — it cost fifteen
minutes on 2026-09-21. `sofa`'s discovery stage is **BOARD**, and it asks the
bookmaker, not a stats provider.

Source of truth for the order: `DEFAULT_SEQUENCE` in
`scripts/sofa/run_pipeline.py`.

## Entry points

| you want | use |
|---|---|
| a full betting day - the one coupon (11_coupon.json + PDF), the measured sports, D-1 settled and recorded for every variant | `/sofa-day [dzisiaj\|wczoraj\|YYYY-MM-DD]` |
| the analysts' read of an existing coupon (top 30 + builder legs; "dodatkowo: <pozycje>" adds to `read_requests.json`) | `/sofa-analyze` |
| coupon (11_coupon.json) + PDF from artifacts on disk (FIXTURE_CHECK, CONFIDENCE, COUPON_ASSEMBLY, PDF) | `/sofa-rebuild` |
| adversarial verification of a built day (11_coupon.json, sport legs via U3) | `/sofa-verify` |
| settle D-1 (7c per sport, 7i, refunds, identity audit) and decide about constants | `/sofa-settle` |
| price a slip the operator screenshotted | the `bet-slip-audit` skill |

Agents: `sofa-runner`, `sofa-analyst-football`, `sofa-analyst-tennis`,
`sofa-analyst-sport` (hockey / basketball / volleyball / CS2 legs on the one
coupon, one instance per sport, read-only), `sofa-verifier`, `sofa-settler`,
`sofa-market-scout`. (The per-sport coupon runner agent was retired
2026-10-05 with the separate sport coupons.) Skills preloaded into
them: `sofa-pipeline`, `sofa-analysis-core`, `football-analysis`,
`tennis-analysis`.

Full orchestration contract: `docs/sofa/AGENTIC_FLOW.md`.

## Commands

```bash
.venv/bin/python scripts/sofa/ensure_bridge.py                                   # always first: brings the bridge up if down, then check_bridge
.venv/bin/python scripts/sofa/check_bridge.py                                    # the grade alone
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --from-stage RESOLVE --run-id <id>
# SHEET parses the whole football history (913k matches since the 09-30 backfill): ~10 min the first time a day's listings change, ~30 s on a rebuild (pickle under data/cache/, keyed on the DB's listings/stats and the parser version). A SHEET that looks hung for 10 minutes is parsing - do not kill it.
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_settle.py --date <D-5> --refetch-stat-gaps   # every morning: statistic gaps (corners etc.) close days later; then regrade_settled.py --apply
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_fixture_check.py --date <d>   # FIXTURE_CHECK in a rebuild, before CONFIDENCE: /event status + fresh start of printed matches and moved clocks -> fixture_status.json (bridge; none = UNVERIFIED)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon.py --date <d>        # COUPON_ASSEMBLY: 11_coupon.json, the coupon of a stats-only day (exit 1 while 08_confidence_sports.json is absent)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_pdf.py --date <d>    # renders 11_coupon.json (08 on a day before the epoch); writes 12_printed.json
# --profile wariant (run_confidence / build_coupon_pdf) only rebuilds a day before 2026-10-05 07:15Z; refused after
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_coupon.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_boosts.py --date <d>        # Superbet boosts snapshot, not the coupon; a single boost now carries its EV at the devigged pre-boost market; run several times a day
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_boosts.py --from <d> --to <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_niches.py --from <d> --to <d> [--min-matches N]  # niche scanner: evidence, never a bet list (after SETTLE)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --only CS2          # CS2 price snapshot, not the coupon
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D-1> --only CS2_SETTLE # grade D-1's CS2 lines (bridge)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/settle_cs2.py --sweep-from <D-7> --sweep-to <D-2>   # CS2_SETTLE for every date whose settled.json still has a waiting series (decided offline from the files; bridge)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_cs2.py --from <d> --to <d> [--history]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_cs2.py --days 180    # CS2 history (results only; bridge)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_listings.py --sport {football|tennis|hockey|basketball|volleyball} --days 730 --max-minutes 7   # deepen every cached team/player (+ opponents, one hop) to --days, and re-fetch a page chain that no longer joins up (--dry-run: gapped / gapped_on_board); resumable, run in chunks (bridge)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_event_stats.py --sport {football|tennis} --days 365 [--board-days 7] --max-minutes 7   # statistics of matches the cache already lists, never asked; --board-days N: only the sides on the last N boards; resumable (bridge)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_football_lineups.py --days 365 --max-minutes 7   # football per-player /lineups for the leagues and teams Superbet prices player markets on (from 04_offer + 02_fixtures); an event with no stats row gets /statistics + /incidents first; resumable (bridge)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_score_model.py --sport {hockey|basketball|volleyball} --date <d> [--date <d2>] [--rows-out f]   # score model vs Superbet's price on graded shadow lines (bootstrap over games); measurement only
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_score_history.py --sport <s> --start <d> --end <d> [--params '{...}']   # score model on the results history (proper scores, no prices)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_model_information.py --rows <rows.jsonl>   # does the model add to the price? b of logit(y) ~ model + price, bootstrap over games
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_player_props.py --sport {basketball|hockey} [--date <d>] [--rows-out f]   # player model (bet.sofa.player_model, SHADOW pre-game forecasts in <sport>/<d>/player_model.jsonl, model_p on graded player lines) vs Superbet's price; measurement only
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_disagreement.py --from <d> --to <d> [--sport football|tennis|all] [--profile standard|wariant|both]   # MAX_DISAGREEMENT re-measured on settled rows: refused vs admitted per profile, gap bands, match bootstrap, event-id halves; measurement only; the threshold decision is the operator's, between days
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_sample_composition.py [--start <d>] [--end <d>] --metrics goals_for corners_total ...   # which past matches a sample should hold (newest ten vs no knockouts vs same competition vs season), log-loss on every cached league match; measurement only
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_own_sample_gap.py --from <d> --to <d> [--sport football|tennis]   # model - own sample hit rate bands on settled priced rows (MODEL_ABOVE_OWN_SAMPLE's evidence); measurement only
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_schedule_context.py [--start <d>] [--end <d>]   # make-up fixture / layoff / congestion vs the sample's centre; measurement only
PYTHONPATH=src:. .venv/bin/python scripts/sofa/find_friendly_competitions.py --out docs/sofa/evidence/friendly_candidates_<d>.json   # candidate friendly / pre-season ids by name and shape; a person decides
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/capture_closing.py --date <d> --loop &   # Superbet's closing price of every printed official/WARIANT leg -> runs/sofa/<d>/closing.jsonl (no bridge)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_clv.py --from <d> --to <d>   # closing line value per variant (sport coupons from their graded close), bootstrap by match
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_devig.py --from <d> --to <d>   # power vs proportional vs Shin against outcomes
PYTHONPATH=src:. .venv/bin/python scripts/sofa/find_women_competitions.py     # config/sofa_women_competitions.json from the cache (PRIOR_GLOBAL_WOMEN)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_confidence.py --classes-only  # refit only the by_class curves (women / tennis_women / tennis_team_cup); every other curve byte-for-byte
PYTHONPATH=src:. .venv/bin/python scripts/sofa/prepare_refit.py --date <d> {backup [--db <path>]|rebuild-cache-rows [--dry-run|--confirm]|fit|compare [--days <d> <d2>] [--with-sheet]|install --confirm|restore --confirm --backup <dir>}   # the between-days refit, one step at a time, into data/refit_<d>/; never mid-day (docs/sofa/CONFIG.md section 7)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/regrade_cs2_snapshots.py --from <d> --to <d> [--dry-run]   # one-off: drop CS2 sides graded from a replaced snapshot (settles before 2026-09-30; 09-29 had 22/302)
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/cs2_daily.py --date <d> --chain >> runs/sofa/cs2/daily_<d>.log 2>&1 &   # the whole CS2 day, unattended; morning settles D and D-1, sweeps D-7..D-2 for series still waiting, grades the CS2 coupons and records D-7..D; --chain starts D+1 at 23:30Z; a second loop for the date refuses
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --only SHADOW          # hockey/basketball/volleyball price snapshot, not the coupon
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D-1> --only SHADOW_SETTLE # grade D-1's shadow lines (bridge)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_shadow.py --from <d> --to <d> [--sport hockey]
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/shadow_daily.py --date <d> --chain >> runs/sofa/shadow/daily_<d>.log 2>&1 &   # the whole shadow day, unattended; morning settles D, D-1 and D-2 (a postponed game voids only 48 h on), grades their sport coupons, records them; --chain starts D+1 after the 05:15Z settle
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_sport_coupon.py --date <d> --sport {cs2|hockey|basketball|volleyball|all}   # experimental per-sport coupon, beside the measurement
PYTHONPATH=src:. .venv/bin/python scripts/sofa/settle_sport_coupon.py --from <d> --to <d> [--sport hockey]   # grade it at the printed price (after CS2_SETTLE / SHADOW_SETTLE)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_sport_price_calibration.py --before <d> [--dry-run]   # hockey/basketball price recalibration a + c*logit(fair_p) -> config/sofa_sport_price_calibration.json; between days only
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_sport_identity.py --date <d> [--sport hockey]   # pre-match Sofascore id of every hockey/basketball/volleyball/CS2 event of the day -> runs/sofa/<d>/sport_fixtures.json (bridge, one request per match; after SHADOW / CS2)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_sport_confidence.py --sport {hockey|basketball|volleyball|cs2|all} --before <d> [--dry-run] [--rows-out <dir>]   # statistics-only confidence curves of the sport legs (walk-forward, no price) -> config/sofa_sport_confidence_calibration.json; between days only
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_sport_confidence.py --date <d>   # the sport legs with a statistics confidence and the coupon's price filters -> runs/sofa/<d>/08_confidence_sports.json (no bridge)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_multi_coupon.py --date <d>        # WARIANT WSZYSTKIE (retired from 2026-10-05 07:15Z, refused; its older days stay graded)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/settle_multi_coupon.py --from <d> --to <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_variants.py --date <d>          # re-derive the sport coupons from raw snapshots; WSZYSTKIE vs its sources
PYTHONPATH=src:. .venv/bin/python scripts/sofa/record_results.py --from <D-8> --to <D-1>   # ledger: every variant + rule + measurement, runs/sofa/ledger/results.jsonl; D-2 too (legs after 00:00Z grade a day late)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_ledger.py --from <d> --to <d> [--variant sport:hockey]   # read the ledger: one table per variant, never pooled
PYTHONPATH=src:. .venv/bin/python scripts/sofa/purge_entity_alias.py --dry-run   # remove a wrongly verified team alias (B2, 2026-10-05: "u. de santiago" -> 233778); --list-suspects
PYTHONPATH=src:. .venv/bin/python scripts/sofa/regrade_settled.py --moved-void --dry-run   # (then --apply) a match moved > 48 h: row moved to the played day or deleted with a copy; --players: props regraded from the own squad
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_settle_identity.py --from <d> --to <d> [--sport all]   # offline, read-only: an id used twice, a >48 h move graded, names <= 82, ID_CHANGED / DUPLICATE_* / MOVED_TO; exit 1 on a finding (after D-1's settle)

.venv/bin/python -m pytest tests/sofa -q
.venv/bin/python -m ruff check src/bet/sofa scripts/sofa
.venv/bin/python -m mypy --strict src/bet/sofa scripts/sofa
```

`.venv/bin/python` is 3.12 and runs the pipeline. `.venv/bin/pip` belongs to
3.14 — install with `.venv/bin/python -m pip`, or the import still fails after
a successful-looking install.

Exit codes: **0 OK, 1 PARTIAL, 2 FAILED**. `PARTIAL` on RESOLVE / OFFER /
SAMPLES is the normal shape of a healthy run; only `FAILED` stops you.

## Hard rules

- **`06_coupon.json` is not the coupon. The PDF is.** The VALUE-singles
  selector returned −20.4% on 2026-09-20 while the PDF returned +8.2% the same
  day. Reporting the wrong file inverts the day.
- **Never invent** a number, a fixture, a price or an availability.
- **`11_coupon.json` and the PDF rendered from it are the coupon of a
  stats-only day; on an older day the PDF of `08_confidence.json` is.**
  `08_confidence.json` stays the football / tennis selection and the input of
  SETTLE and the refit; `06_coupon.json` and `p_bar` are priced and are not
  the coupon.
- **`KUPON_<date>_WARIANT.pdf` is not the coupon either** (retired with the
  stats-only epoch; history:). It was the
  operator's variant (floor 0.65, confidence x odds >= 0.90, and since
  2026-09-23 13:30 UTC a ladder margin up to 15% against the coupon's 10.5%;
  since 2026-10-05 the coupon shares both price dials and differs by its 0.70
  floor and honouring WATCH; both print every single),
  measured -3.2% per bet against the official -2.9% before it was added (with
  the 10.5% margin - the two settings are different experiments). It is built into its
  own files, settled beside the coupon (audit_settlement section 7d), and its
  result is never pooled with the coupon's.
- **CS2 / CS2_SETTLE are a measurement** (since 2026-09-28): they write only
  `runs/sofa/cs2/<date>/` and test whether Superbet's devigged CS2 price
  already matches the outcomes. From 2026-10-05 08:30Z
  (`epochs.SPORTS_ON_COUPON_FROM_UTC`) those snapshots are also what the
  coupon's CS2 legs are priced from and graded by: SPORT_IDENTITY pins the
  series' Sofascore id before the start, SPORT_CONFIDENCE reads the CS2
  engine through `config/sofa_sport_confidence_calibration.json` (fitted
  without prices, between days only) into `08_confidence_sports.json`, and
  COUPON_ASSEMBLY prints the legs that pass on `11_coupon.json`. The
  measurement itself still feeds and gates nothing. Superbet `sportId=190` is
  *virtual* football and `75` is e-football - neither is a real sport; never
  add them.
- **Hockey, basketball and volleyball: SHADOW / SHADOW_SETTLE stay a
  measurement too** (since 2026-09-29): they write only
  `runs/sofa/shadow/<sport>/<date>/` and grade Superbet's lines (two-way, and
  since 2026-09-30 1X2 / odd-even / yes-no / exact score as whole groups)
  against Sofascore's score. From 2026-10-05 08:30Z their calibrated legs
  (score model -> calibration, price only the condition: x >= 0.90, group
  margin <= 15%, a fresh pre-start snapshot) print on the one coupon exactly
  like CS2's above, graded at the printed price against the pinned id
  (`NOT_GRADED:ID_CHANGED` otherwise), in their own 7c table, never in
  `sofa_settled_row` or `fit_confidence`. A sport without a calibration is
  `NOT_CALIBRATED` (exit 1) and the rest of the coupon still builds.
  Superbet `157` (e-hockey) and `70` (e-basketball) are simulations - never
  add them.
- **The separate per-sport experimental coupons are retired** (history,
  2026-09-30 - 2026-10-05 08:30Z): `KUPON_<d>_{CS2,HOKEJ,KOSZYKOWKA,SIATKOWKA}.pdf`
  were price-only coupons built by `run_sport_coupon.py` into the measurement's
  own directory, graded by `settle_sport_coupon.py` per sport and never pooled
  (the rule replayed on the one settled hockey day, 09-29, went 33/46 against a
  mean fair p of 85.1%, ROI -17.7%). `run_sport_coupon.py` refuses a build
  after 08:30Z on 10-05; the files up to then stay and are graded as before
  (D5), and `config/sofa_sport_price_calibration.json` belongs to that history.
- **`KUPON_<d>_WSZYSTKIE.pdf` is not the coupon either** (2026-09-30 - the
  morning of 2026-10-05; retired, `run_multi_coupon.py` refuses newer days):
  an assembly in `runs/sofa/multi/<d>/` of what the official PDF and the four
  sport coupons printed, verbatim, at their prices - it selects nothing.
  Any rebuild of a source makes it stale (`audit_variants.py` M2), so it is
  re-assembled after every rebuild. Its result is its own.
- **Every day records every variant** (`record_results.py`, the ledger). It
  reproduces 7c / 7d exactly - it reads `sofa_settled_row` in the DB like 7c,
  so re-run it after any `regrade_settled.py` - and is the one place every
  variant's result is recorded side by side - read per variant, never pooled
  (`audit_ledger.py`). Its exit is 0 with legs merely pending (they are shown),
  1 only for a `MISMATCH` (two graders disagree on a leg - a defect) or an
  unreadable file, 2 for a crash or a missing DB; `settle_sport_coupon.py` and
  `settle_multi_coupon.py` exit the same way. A daily loop reads its plan when
  it starts, so a loop started before a code change keeps its old morning
  steps until it ends.
- **Never print a combined / Bet Builder / parlay price** outside what
  `confidence.py` computed, and never present `odds_if_product` as a price —
  Superbet does not price a slip as the product of its legs (measured markup
  8.8–19.6%).
- **No stake sizing, no automated placement.** The stake decision is the
  operator's.
- **Never read, echo or log `.env` values.**
- **Never re-fit constants mid-day.** `fit_constants.py` is outside the
  sequence on purpose; re-fitting breaks comparability with yesterday.
- **A pooled number must say what it pooled across** (since 2026-09-30, FK
  Aktobe - Ajax, women's Europa Cup: the rating carried Kazakh-league ratios
  into a European tie, and the leg's confidence came from a men's curve).
  Football ratings compare teams across leagues only through a measured
  league strength (`football_rating`, LINKED / LINKED_BY_STRENGTH /
  UNLINKED); an UNLINKED fixture is flagged `CROSS_LEAGUE_UNLINKED` in SHEET
  and refused by CONFIDENCE. A women's football, women's tennis or tennis
  team-cup leg reads only its class's curves (`by_class`) and is refused
  where its class has none (`NO_CLASS_CURVE` when only the class blocked it,
  else `NOT_CALIBRATED`); a women's league without a
  baseline shrinks to the women's pool (`PRIOR_GLOBAL_WOMEN`). Friendlies are
  out of samples and the rating (39 ids). "History is thin" is not an
  argument before `backfill_listings.py` has been run.
- **Never strip `UNFITTED_CONSTANTS`** from a row or a report to make it read
  better.
- **`MIN_INTERVAL_MS = 350` in the userscript is the safety mechanism, and it
  is never lowered.** It paces each *connection*, which is what keeps a tab
  looking like a person. Capacity comes from opening more tabs, never from
  making one tab faster. The 2026-09-17 incident was one `curl_cffi` client
  with 100 workers peaking at 550 req/s and no browser in the path; the bridge
  cannot produce that shape.
- **Open the windows with `launch_bridge_browser.py`, and they do NOT have to
  be visible.** Chrome clamps `setTimeout` in a hidden page to >=1000 ms, and
  the userscript's `pace()` waits on exactly that to hold `MIN_INTERVAL_MS`.
  So a background tab silently ran at ~1 req/s instead of 2.86, and the only
  symptom was a run that took four times as long. Three launch flags remove
  it; with five **minimised** windows the round trip p90 went from 9,436 ms to
  224 ms. They are process-creation flags, so Chrome must be fully quit first
  — the script refuses to launch rather than open a window whose flags were
  silently dropped. The old "tabs must be visible, three non-overlapping
  windows" rule was a workaround for this bug and is retired.
- **`SOFA_MAX_CONCURRENCY` is the window count — not a tuning knob, and never
  below it.** Measured 2026-09-22, five windows, 60 requests a step, zero
  non-200:

  | `SOFA_MAX_CONCURRENCY` | achieved | p50 | p90 |
  |---|---|---|---|
  | 3 | 0.15 req/s | 20,138 ms | 20,162 ms |
  | **5** | **11.67 req/s** | **354 ms** | **620 ms** |
  | 8 | 11.72 req/s | 668 ms | 704 ms |
  | 12 | 11.66 req/s | 1,010 ms | 1,056 ms |

  Throughput saturates at the window count and never moves again; only latency
  grows, which is queue depth and costs `STALE_PRICE`. Below it the failure is
  not gradual — two idle tabs fell back into what was then a 20 s `/pull`
  and the bridge collapsed 78x (`PULL_WAIT_S` is 1 s since 2026-09-23, and
  `/pull` answers within 50 ms while a job is out since 2026-09-29, which
  took a lone request from ~2 s to ~145 ms). `p50 = 354 ms` at five *is* `MIN_INTERVAL_MS`: the tab is
  pacing itself and nothing else is the limit. Change it together with
  `--windows`, and re-run `measure_bridge_capacity.py`.
- **`SOFA_TARGET_RPS` must sit above what the tabs can serve.** Five windows
  at 350 ms is 5 x 2.86 = 14.3 req/s, so the bucket is 20. Starving it is
  worse than opening it: if the bucket is the limiter the tabs idle between
  jobs and pay the same poll cycle. Defaults are 20 and 5.
- **The browser is the binding limit, not Sofascore.** Nothing measured across
  2026-09-22 was ever refused by Sofascore — every collapse that day was our
  own configuration or our own measurement. **First refusal on record:
  2026-09-28, CS2_BACKFILL** — 5 × 403 on `/esports-game/*/lineups` after
  ~8 min sustained at 13.8–14.2 req/s through five windows (per-minute p50
  265–297 ms, ~3.1 s at the end); the breaker opened and skipped 61% of the
  series. One event, not a measured limit — but a long single run at full
  width is no longer known to be safe. Backfills run short and resume.
  **Second: 2026-09-29 14:26:50Z, RESOLVE** — 5 × 403 in one instant on
  five different routes, 21 min after the windows were launched, in an
  ordinary day run; the breaker opened and a `--from-stage RESOLVE` re-run
  minutes later recovered it (recall 74.8% → 82.3%).
  **Third: 2026-09-30, backfill_listings** — 18:02Z a stale `x-captcha`
  (reloading the tabs fixed it); then 5 × 403 in one instant at 18:26:52Z,
  19:28Z and 20:05Z, each ~23-28 min after the tabs last minted a token,
  at ~8-12 pages/s in 7-minute chunks. At 19:28Z a reload did not help and
  the operator had to solve the challenge by hand. Working hypothesis
  (unmeasured): under sustained load a token lasts ~25 min. A refusal is a
  signal to slow down - never refresh tokens pre-emptively to outrun it.
- **Measure the round trip, not the wall clock around the client.** The token
  bucket sits *inside* `client.event_statistics()`, so timing that call
  reports our own rate limiting as if it were browser latency — it read a flat
  ~2,050 ms while the bridge was answering in 216 ms, and sent a whole
  diagnosis the wrong way. `measure_bridge_capacity.py` now reports `p50 net`
  from the request log, and gives every ramp its own `run_id`.
- A settled result is a fact about the day, **not about the decision that made
  it**. "It won" never enters the reasoning for the next one.

## Working style in this repo

- **Evidence or it did not happen.** A claim about the pipeline names the file
  and the line, or the artifact and the field. An unmeasured statement is
  marked as a suspicion, not stated as a fact.
- **Every fix ships a test.** `tests/sofa/` is offline and fast; there is no
  reason to skip it.
- **A skipped check is named.** Silence about a check reads as a passed check.
  If a run went clean, say a guard was *not tested* — never that it works.
- **Check a subagent's numbers** when you can check them locally. One
  adversarial pass over a single agent file once found eighteen errors, two of
  which inverted the argument.
- **Agent definitions and skills load at session start.** A rewritten agent
  cannot be exercised in the session that wrote it; say so rather than claiming
  the fix is live.
- Live runs are deliberate: they cost hours of bridge time and they are visible
  to a third party's production API.

## Language

Operator-facing documentation in `docs/sofa/` is **Polish** (so are the
analysts' reports). Code, tests and the `.claude/` contracts are **English**.
Keep that boundary.

## What is retired

`src/bet/simple_stats/`, `scripts/simple/`, `src/bet/tipsters/`, `legacy/`,
`.claude/legacy/`, `.kilo/legacy/`, `docs/legacy/`. The code and documents are kept as a
record; their databases (`betting/data/betting.db` and its backup, the
`reports/pipeline_runs/*/runtime_analysis_shadow.db` files) were deleted 2026-10-05 on the
operator's order, so the retired code no longer runs against real data. `data/sofa.db` is
the only working database; `data/backup_<epoch>/sofa.db` holds one copy for the current
refit epoch. Do not take stage names,
quantities (`p_low`, CALL/LEAN/WEAK/DROP) or artifact names from them, and do
not "restore" one without reading `docs/legacy/README.md` first.
