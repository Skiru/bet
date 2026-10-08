# Working agreement — `bet`

This file describes the system **as it is now**: one pipeline, `sofa`, and one
coupon a day. It is not a changelog. A change to the rules edits the section
it belongs to; the story of how it got here lives in `docs/sofa/history/` and
in git.

## The pipeline: `sofa`

Sofascore statistics, Superbet prices, one coupon a day for every sport —
football, tennis, hockey, basketball, volleyball, CS2. The product of a day is
**`runs/sofa/<date>/KUPON_<date>.pdf`**, rendered from **`11_coupon.json`**.

```
BOARD → RESOLVE → OFFER → SAMPLES → OFFER → SHEET → COUPON
                                          ↘ CONFIDENCE ─────────────┐
   SHADOW / CS2 → SPORT_IDENTITY → SPORT_CONFIDENCE ────────────────┤
                                   COUPON_ASSEMBLY (11_coupon.json) → PDF   ★ the product
   in a rebuild, before CONFIDENCE: FIXTURE_CHECK
   deliberately separate:           SETTLE → FIT
```

Source of truth for the order: `DEFAULT_SEQUENCE` in `scripts/sofa/run_pipeline.py`.
There is no other pipeline and no other coupon. Stage names like `DISCOVER`,
`ENRICH`, `ANALYZE`, `MARKET_CONTEXT`, `TIPSTERS` do not exist here; discovery
is BOARD, and it asks the bookmaker.

Reference (Polish): `docs/sofa/PIPELINE.md` every stage, field and gate;
`docs/sofa/RUNBOOK.md` the day's order and "what if"; `docs/sofa/AGENTIC_FLOW.md`
agents and hand-offs; `docs/sofa/CONFIG.md` config files and the refit loop.

### Artifacts of a day (`runs/sofa/<d>/`)

| file | what it is |
|---|---|
| `08_confidence.json` | football / tennis legs with confidence and gates; SETTLE's and the refit's input |
| `08_confidence_sports.json` | hockey / basketball / volleyball / CS2 legs (SPORT_CONFIDENCE) |
| `11_coupon.json` | **the coupon**; read it through `confidence.coupon_artifact()` |
| `KUPON_<d>.pdf`, `printed/<ts>.json`, `12_printed.json` | the product and its append-only print record (a rebuild locks from the first print) |
| `KUPON_<d>.html` | the same legs as a filterable page (time window in Europe/Warsaw, confidence, sport, competition, market, odds, sortable; a start the FIXTURE_CHECK read differently is flagged). A **view**, not a coupon - `bet.sofa.coupon_html`, written by `build_coupon_pdf.py` after every PDF render, so a rebuilt PDF always brings its HTML (HTML failure: PDF kept, exit 1); alone: `build_coupon_html.py --date <d>` |
| `reads.json`, `vetoes.json`, `read_requests.json` | analysts' per-leg verdicts, vetoes, the operator's extra positions |
| `fixture_status.json`, `sport_fixtures.json` | FIXTURE_CHECK's fresh starts / statuses; the pinned Sofascore ids of sport games |
| `06_coupon.json` | the priced VALUE selector - **not the coupon** (2026-09-20: -20.4% vs the PDF's +8.2%) |

## How the coupon is built

**Confidence comes from the statistics; the price is only the condition for
the bet and may only lower a confidence** (from 2026-10-07 10:55Z). The
yardstick (operator): the statistics must tell a good 1.20 from a bad 1.20, in
every sport alike, and nothing that could win is cut by name.

### Confidence

- **Curves are fitted on the history** of events and statistics, replayed as of
  each match with the estimator SHEET prices with today (operator, 2026-10-07).
  Our own settled days are an audit of a curve, never its source.
  `config/sofa_confidence_calibration.json` (football / tennis) and
  `config/sofa_sport_confidence_calibration.json` (the four measured sports;
  a staged `.next.json` is read from its `effective_from`,
  `sport_confidence.calibration_path_for`) are the curves.
- SHEET keeps the price out of `p_central`. The rating is published beside it
  as `forecast_p` ("model", uncalibrated, never a gate). CONFIDENCE maps the
  statistics to a calibrated confidence through the curves.
- **Line evidence** (`bet.sofa.line_evidence`,
  `config/sofa_superbet_line_evidence.json`; from `LINE_EVIDENCE_FROM_UTC`
  2026-10-07 10:55Z): every key - football, tennis and the four measured
  sports - is also read through its own settled Superbet lines. The confidence
  is the lowest of
  - the history curve lowered by the key's **offset** (its measured
    realised-minus-confidence on printable lines; needs `MIN_OFFSET_ROWS` 50
    lines and `MIN_OFFSET_GAMES` 30 games, else the sport's pooled offset with
    `MIN_SPORT_OFFSET_GAMES` 20; never above 0), and
  - the **price-band cap**: what lines of the key at this `p` realised in this
    band of Superbet's price (`PRICE_BANDS`: 1.30 / 1.60 / 2.20; cell of
    `MIN_CAP_CELL` 20), applied only where measured below the confidence
    (operator, "krzywa per pasmo kursu"). A band cell without enough lines
    widens downward inside its band; with none, the key's own lines over every
    band from its `p` down (to 0.70) bound it.

  A key without a curve reads the Wilson bound of its own lines divided by the
  sport's measured design effect (`design_effect` in the evidence file; lines
  of one game are not independent), needs `MIN_EVIDENCE_BUCKET` 50 settled
  lines and `MIN_EVIDENCE_GAMES` 15 games in the bucket, else
  `NO_LINE_EVIDENCE`. The sport's pooled offset is measured without a key
  holding more than `CONCENTRATION_MAX` (50%) of its printable lines; this can
  **raise** another CS2 key's confidence (operator's choice). A CS2 fixture
  with no `best_of` is not guessed as best-of-3. Rules after
  `LINE_EVIDENCE_V2_FROM_UTC` (2026-10-07 13:42Z) are `LineEvidence.v2`.
  Legs carry `line_offset` / `price_band_cap` when lowered. The evidence is
  refitted every morning by `refresh_line_evidence.py` (it never touches a
  curve); the v2 rules need its `games` field - an older file reads nothing for a key without a curve.
  Evidence: `docs/sofa/evidence/discrimination_within_price_2026-10-07.md`.
- **Model packages** (switches in `bet.sofa.epochs`, all from 2026-10-07
  14:05Z, measured out of sample on the history,
  `docs/sofa/history/AUDYT_MODELI_2026-10-07.md`):
  `TENNIS_RATING_PRICES_FROM_UTC` (`games_won_for`, `handicap_games`,
  `most_games` - not its draw - priced by the rating alone, no price;
  `games_total` is the 50/50 mix of the NB and the rating);
  `DERIVED_MARGINAL_CENTRES_FROM_UTC` (football goals / corners /
  shots-on-target / cards joints built from the marginal rows' centres);
  `BB_FRESHNESS_FROM_UTC` (basketball simulation noise x1.085 when the thinner
  side has <= 2 games in 120 days, x1.026 for 3..9 - live forecaster and
  history replay alike). The history replay (`calibrate_from_cache.py`) prices
  the same estimator as SHEET (`tennis_rating.AsOfRating`; best-of-five
  skipped); football goals joints are **not** replayed (no football rating in
  the replayed centre) and `DERIVED_CURVES_FROM_UTC` is off. Curves refitted
  that way were installed 2026-10-07 17:51Z: a new comparability epoch.
  Hockey / volleyball / CS2 curves are the staged `.next.json`'s.
- **Wait for a measurement, not a name:** a market with no curve and no
  evidence is `NO_LINE_EVIDENCE`. Before `LINE_EVIDENCE_FROM_UTC` (rebuilds of
  older days only) the by-name refusals still apply: `refused_markets`,
  `admitted_player_markets`, `admitted_tennis_set_markets` in the football /
  tennis calibration (carried over by every refit),
  `DERIVED_NOT_CALIBRATABLE`, and the sports' `admitted` keys.

### What prints

- **A leg prints** when confidence >= 0.70, confidence x odds >= 0.90, ladder
  (group) margin <= 15% (`COUPON_PROFILE`), not ODDS_TOO_LOW, not started,
  fresh price (STALE_PRICE otherwise; a moved price re-prices the leg). Every
  passing single prints - no page limit.
- **Refusals worth knowing** (each named on the row):
  - `CROSS_LEAGUE_UNLINKED`: football ratings compare leagues only through a
    measured league strength; a pair is LINKED only when both sides' leagues
    are the competition they share (`LINK_SHARED_LEAGUE_FROM_UTC`, 2026-10-07
    06:45Z; the hockey / basketball / volleyball score model reads the same
    book; sheet rows carry `link_rule`, a rebuild re-runs SHEET on an
    old-rule sheet). A promoted side is cross-league until its new league is
    its modal one;
  - women's football, women's tennis and tennis team cups read only their
    class's curves (`NO_CLASS_CURVE`);
  - `NOT_SETTLEABLE`: (competition, family) cells in `config/sofa_settleability.json`;
  - K13 / K13b: a thin direction bucket caps the curve; a pooled read is capped
    by the market's nearest own bucket below;
  - `SAMPLE_CROSSES_SEASON` (180 days; `MAX_BUILDER_SAMPLE_AGE_DAYS`) - except
    national-team fixtures, judged by count (`NATIONAL_SAMPLE_AGE`);
  - CS2 team-rounds line outside 9.5-12.5: `LINE_OUTSIDE_FIT`.
- **Start clock** = the earliest of RESOLVE's clock, Superbet's start signal
  (`superbet_started_utc`, `superbet_kickoff_seen_utc`; in-play odds are
  dropped for every reader) and FIXTURE_CHECK's fresh `/event` start. A
  postponed / cancelled printed match is FIXTURE_NOT_AS_SCHEDULED; no bridge =
  UNVERIFIED, nothing refused. Blind spot: a suspended pre-match offer with no
  metadata says nothing; only the clocks see it.
- **Peer choice and stakes** (from `PEER_CHOICE_FROM_UTC` 2026-10-08
  08:10Z, operator: "jak masz dwie nogi po 1.2 to zaproponuj tę z większą
  pewnością"; 10-08 is a mixed day; **annotation only** - no leg is added,
  removed or re-ranked, no confidence moves): two legs of one match on
  different variables priced within `PEER_BAND` 0.06 are peers
  (`bet.sofa.peer_choice`); the surer by confidence is starred (★ on the PDF,
  `peer.preferred`), a weaker one names it. The edge is measured and small:
  of 57,791 decided pairs (football / tennis, 20 days) the more confident leg
  won 53.4% [52.2, 54.7]; **no** sample statistic (hit rate, size, near
  misses, margin, venue, last 5), tournament metadata (popularity, reserve /
  women / cup / national) or its combination improved the confidence out of
  sample; hockey / basketball / volleyball show no measurable edge. Tournament
  rank and sample depth therefore do not re-rank peers. Match **stakes**
  (`bet.sofa.stakes`: `STAKES_SIX_POINTER`, `STAKES_TOP4`, from the football
  history's league table as of the kickoff) are a context flag on the leg with
  the direction of the measured effect (six-pointer: +0.2 cards, +0.9 fouls,
  -0.15 goals, -1.0 shots per match, 0.08-0.16 sd; top-4: +0.2 cards, -0.2 goals; not corrected
  for the weakness of relegation-zone clubs): shown, never gated, never a
  correction. Evidence: `docs/sofa/evidence/peer_choice_2026-10-08.md`
  (`scripts/sofa/measure_peer_choice.py`); pre-registered check on new data:
  `T-PEER-CHOICE-edge`.
- **Bet Builders:** one per fixture, by best `combined_probability`; an
  internal haircut x >= 0.90 decides stakeable and is never printed. **sofa
  does not price a builder**: the PDF shows its legs with Superbet's single
  prices, the combined p and "kurs buildera: sprawdź na ekranie Superbetu". A
  screen price the operator records in `09_screen_prices.json` is shown back
  as his note.
- **Assembly** (`build_coupon.py`): order by confidence, then earlier start,
  one match's legs together; legs locked from an earlier print come first,
  unnumbered; builders B1.. on their own pages; ladders under "ta sama
  zmienna"; an exposure-per-match section. A leg printed before its start
  stays (locked); a leg removed before its start stays removed.
  `ladder_form` / `max_positions_per_match` are OFF unless
  `config/sofa_coupon_form.json` sets them (operator's call).
- **Reads:** analysts read the first 30 unlocked positions (from 2026-10-09 00:00Z the unit is the match: every unlocked leg of the first 30 matches of the coupon, `read_unit: "event"` in the artifact; operator, "30 wydarzeń, nie 30 rynków"), every printed
  builder leg and whatever is in `read_requests.json`
  (`confidence.legs_requiring_read`, `READ_REQUIRED_SINGLES`; audit C3 checks
  it; a rebuild moves positions, so re-read until C3 is clean); the rest
  prints unread. WATCH or NO_BET in `reads.json` - or the automatic football
  `MODEL_ABOVE_OWN_SAMPLE` (model - own sample hit rate >
  `MAX_OWN_SAMPLE_GAP` 0.15, props excluded) - moves a leg to
  `removed_by_reads`, graded on its own, never in the coupon's result.
  `context_flags` (`MAKEUP_FIXTURE`, `LONG_LAYOFF`, `CONGESTED`) are shown,
  never gated.

### Measured sports (hockey, basketball, volleyball, CS2)

SHADOW / CS2 snapshot Superbet -> SPORT_IDENTITY pins the Sofascore id before
the start -> SPORT_CONFIDENCE reads the sport calibration (fitted without
prices) and corrects it with line evidence. SHADOW / CS2 themselves stay a
measurement of Superbet's price and feed nothing else.

- Every fitted key of all four prints on the same rules as football and
  tennis. Volleyball still needs a tournament with a settled event in the
  last 14 days. A sport without a usable calibration is `NOT_CALIBRATED`
  (exit 1, the rest still builds).
- `sport_confidence.EXTENDED_MARKETS`: basketball quarters, second half, dnb,
  odd/even; hockey period dnb (score model, from the history). Volleyball adds
  exact set score, points / set parity, "set on extra points". CS2 adds
  `CS2_EXTENDED_FAMILIES` (map round handicap / total, team kills, player
  kills / deaths / assists / headshots; box-score families graded from
  CS2_SETTLE's own row) and the series families (maps_total, maps_handicap,
  team_maps, exact_maps) from a Beta-mixed series distribution
  (`cs2_engine.SERIES_KAPPA`). Still unpriced: CS2 series rounds (rounds_*,
  team_rounds) and round parity.
- Hockey / basketball player lines: p = player_model's pre-game number in
  SHADOW's `player_model.jsonl` (reads SPORT_IDENTITY's pinned teams before
  names, `teams_source`); no history curve, so `NO_LINE_EVIDENCE` until a
  family's p bucket holds 50 settled pre-game lines; graded from
  SHADOW_SETTLE's own player row.
- Basketball second half / Q4 grade on the regulation periods - overtime does
  not count (operator, 2026-10-07); full-game basketball markets include it.

## Settlement and the ledger

- **SETTLE:** a refund (0 u.), never a loss, when the match moved > 48 h
  (`VOID_AFTER`), was awarded, retired (Sofascore code 92, `RETIRED`) or a
  walkover (`WALKOVER`) - `settle.REFUND_REASONS` (operator, 2026-10-07:
  Superbet's rules). Player props grade only from the player's own squad
  (PLAYER_AMBIGUOUS); a printed leg without a sheet row goes to
  `07_settled_printed.json`. Sport legs grade at the printed price against the
  pinned id (`NOT_GRADED:ID_CHANGED` otherwise), in their own 7c table, never
  in `sofa_settled_row` or `fit_confidence`. Statistic gaps close days later:
  `resettle_sweep.py` every morning.
- **Ledger** (`record_results.py` -> `runs/sofa/ledger/results.jsonl`, read
  with `audit_ledger.py`): the coupon's result, the legs removed by reads and
  each sport kept side by side, never pooled. It reads `sofa_settled_row`, so
  re-run it after any `regrade_settled.py`. Exit 0 with legs pending, 1 on a
  `MISMATCH` (two graders disagree - a defect), 2 on a crash.
- **Comparability:** the current rules apply from 2026-10-06; a refit install
  or an epoch switch starts a new epoch. Earlier days ran under other rules
  and are other experiments - the ledger keeps them in their own groups and
  they are never summed with the current ones. Days up to the morning of
  2026-10-05 also hold rows of variants whose code is gone (`wariant`,
  `multi`, `sport:<sport>`, `rule:<sport>`): kept as recorded, never rebuilt.

## Changing the pipeline

The shape above stays; it is improved, not rebuilt.

1. **Measure first.** A change comes with a measurement on settled rows or
   history (match bootstrap, out of sample) or it is a suspicion. `measure_*.py`
   scripts are read-only evidence.
2. **Correctness fixes** (a misgrade, a wrong mapping, a crash) go live at once,
   with a test.
3. **Anything that changes what prints** gets a switch in `bet.sofa.epochs`,
   by default effective from the next day's 00:00Z. Only the operator moves it
   earlier, to an exact time (the day is then mixed and says so); never on
   your own mid-day.
4. **Refits and calibration fits** (`prepare_refit.py`, `fit_*`) run on a
   **copy** of the database (SQLite `VACUUM INTO`, then `--db-path <copy>`
   with `--without-db-backup`; scratch in `data/refit_<date>/`), never
   against live rows, so the daily loops stay up. `install` runs
   `tests/sofa` and restores on failure. Installing changes what prints, so
   it needs the operator's go - and no refit without it, mid-day included.
5. **Every fix ships a test** in `tests/sofa/` (offline, fast); run the gates.
6. **Update this file's section** and the Polish doc in `docs/sofa/`; a run or
   a night gets a report in `docs/sofa/history/`.

Daily loops spawn each step through `run_pipeline.py` (fresh code per step);
only the loop's own orchestration is old code until it ends.

**Waiting for the operator** (switches off, `None` in `bet.sofa.epochs`):
`CURVE_STATUS_FROM_UTC` (a curve failing `measure_calibration.py` stops
printing), `MODEL_FIXES_FROM_UTC` (tennis NB dispersion; with the next refit),
`BUILDER_SCREEN_PRICE_FROM_UTC` (switched off 2026-10-05: sofa does not price
builders), `DERIVED_CURVES_FROM_UTC` (derived joints read a history curve;
needs a refit carrying the replayed joints), the coupon form dials. Open
questions: Superbet's game count of a tennis match tiebreak; how strict the
price-band cap is.
**Before the next refit:** measure the admitted football props separately;
measure the tennis games population of replay matches without `/statistics`;
queued: CS2 `map_team_rounds` from the round race, football joints with the
football rating in their centre.
Current backups: `config/backup_2026-10-05`,
`config/backup_2026-10-06_sport_calibration/`, `config/backup_2026-10-08`,
`data/backup_2026-10-05/sofa.db`.

**Not modelled yet** (operator 10-07: every market that could win; the next
work, each through a curve and its own Superbet lines): football / tennis
outcome markets - 1X2, double chance, draw-no-bet, both teams to score, goals
parity, half-time/full-time, exact score; tennis match / set winner, set
score, games parity (OFFER's `unmapped_markets`, ~27,800 lines on 10-07,
part of them Superbet's own combinations); CS2 series rounds and round
parity; derived football / tennis joints and women's tennis per-set markets
above their measured range wait for 50 settled lines a bucket
(`NO_LINE_EVIDENCE`).

**Measured and declined - do not re-propose without new evidence:**
- a second coupon or a variant (operator: one coupon, many sports);
- a 0.80 confidence floor (operator: "many options");
- current-season-only samples (worse on every metric); same-competition
  samples for corners / fouls / shots / cards (no gain) or for knockouts (worse);
- trimming national-team samples to 180 days (worse log-loss);
- blending the price into confidence or gating on disagreement with it
  (disagreement is an anti-signal; every weight moved to the price only
  copies the price) - the price-band cap is not a blend: it only lowers, and
  only where a band's settled lines measured below the curve (operator,
  2026-10-07);
- league selection / gate tuning (anti-selects out of sample);
- re-ranking peer legs by own-sample size, hit rate, near misses, venue or
  recent form, or by tournament popularity / reserve / women / cup flags
  (2026-10-08: no out-of-sample gain on 62k legs; the pipeline's confidence
  is already the best-measured order).

## Entry points

| you want | use |
|---|---|
| a full betting day - D-1 settled and recorded, the coupon + PDF, reads, verification | `/sofa-day [dzisiaj\|wczoraj\|YYYY-MM-DD]` |
| the analysts' read of an existing coupon ("dodatkowo: <pozycje>" adds to `read_requests.json`) | `/sofa-analyze` |
| coupon + PDF from artifacts on disk (`rebuild_day.py`) | `/sofa-rebuild` |
| adversarial verification of a built day | `/sofa-verify` |
| settle D-1 and decide about constants | `/sofa-settle` |
| price a slip the operator screenshotted | the `bet-slip-audit` skill |

Agents: `sofa-runner`, `sofa-analyst-football`, `sofa-analyst-tennis`,
`sofa-analyst-sport` (one instance per measured sport, read-only),
`sofa-verifier`, `sofa-settler`, `sofa-market-scout`. Skills preloaded into
them: `sofa-pipeline`, `sofa-analysis-core`, `football-analysis`,
`tennis-analysis`. Agent definitions and skills load at session start: an
edited one is live only in the next session.

## Commands

Python runs as `PYTHONPATH=src:. .venv/bin/python ...`. `.venv/bin/python` is
3.12; `.venv/bin/pip` belongs to 3.14 - install with `.venv/bin/python -m pip`.
Exit codes: **0 OK, 1 PARTIAL, 2 FAILED**; PARTIAL on RESOLVE / OFFER /
SAMPLES is the normal shape of a healthy run.

**The day**
```bash
.venv/bin/python scripts/sofa/ensure_bridge.py                                   # always first: brings the bridge up if down, then check_bridge
.venv/bin/python scripts/sofa/check_bridge.py                                    # the grade alone
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --from-stage RESOLVE --run-id <id>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --only SHEET --run-id <id>   # after a change of the SHEET estimator: a rebuild re-runs SHEET only on an old-rule sheet (p_central lives in 05_sheet.json)
# SHEET parses the whole football history: ~10 min when the day's listings changed, ~30 s on a rebuild (pickle in data/cache/). A SHEET quiet for 10 min is parsing - do not kill it.
PYTHONPATH=src:. .venv/bin/python scripts/sofa/rebuild_day.py --date <d> [--dry-run] [--skip-audits]   # THE rebuild, never the stage scripts by hand: stale prices first (OFFER near 45 min, SHADOW / CS2 near 3 h), SPORT_IDENTITY, SHEET only if refused, FIXTURE_CHECK, CONFIDENCE, SPORT_CONFIDENCE, COUPON_ASSEMBLY, PDF, audits; a finished day refreshes nothing
PYTHONPATH=src:. .venv/bin/python scripts/sofa/day_status.py --date <d>        # one status report: snapshot ages, loops alive, ledger MISMATCH, CLV coverage, UNVERIFIED; no network; exit 0 / 1 WARN / 2 broken
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/shadow_daily.py --date <d> --chain >> runs/sofa/shadow/daily_<d>.log 2>&1 &   # hockey/basketball/volleyball day, unattended: snapshots + SPORT_IDENTITY for D and D+1, morning settles D, D-1, D-2
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/cs2_daily.py --date <d> --chain >> runs/sofa/cs2/daily_<d>.log 2>&1 &         # the CS2 day, unattended; a second loop for the date refuses
PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/capture_closing.py --date <d> --loop &   # closing price of every printed leg -> closing.jsonl; stops after 12 failed passes
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_boosts.py --date <d>        # Superbet boosts snapshot (not the coupon), several times a day
```
A daily loop reads its plan when it starts: one started before a code change
runs its old steps until it ends.

**Single stages** (`rebuild_day.py` runs them in order; by hand only to debug)
```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_fixture_check.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --only SHADOW
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <d> --only CS2
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_sport_identity.py --date <d> [--sport hockey]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_sport_confidence.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon.py --date <d>        # exit 1 while 08_confidence_sports.json is absent
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_pdf.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_coupon.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_variants.py --date <d>
```

**Settle and record**
```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D-1> --only SHADOW_SETTLE
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_pipeline.py --date <D-1> --only CS2_SETTLE
PYTHONPATH=src:. .venv/bin/python scripts/sofa/settle_cs2.py --sweep-from <D-7> --sweep-to <D-2>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/refresh_line_evidence.py --before <D> [--dry-run] [--skip-sport-rows]   # EVERY morning after D-1 is settled and recorded, before D's build: four sport row fits (--dry-run inside, no curve touched, ~15-20 min) + fit_line_evidence; rows in data/line_evidence/rows_before_<D>; exit 1 = a sport's row fit failed, its earlier rows reused
PYTHONPATH=src:. .venv/bin/python scripts/sofa/resettle_sweep.py --from <D-14> --to <D-2> --include-day <D-5>   # every morning; bridge (none: exit 1, nothing done)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_settle_identity.py --from <d> --to <d> [--sport all]   # after D-1's settle; exit 1 on a finding
PYTHONPATH=src:. .venv/bin/python scripts/sofa/record_results.py --from <D-8> --to <D-1>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_ledger.py --from <d> --to <d> [--variant official]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/regrade_settled.py --moved-void --dry-run   # then --apply; --players regrades props from the own squad
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_shadow.py --from <d> --to <d> [--sport hockey]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_cs2.py --from <d> --to <d> [--history]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_clv.py --from <d> --to <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_boosts.py --from <d> --to <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_niches.py --from <d> --to <d> [--min-matches N]   # evidence, never a bet list
PYTHONPATH=src:. .venv/bin/python scripts/sofa/purge_entity_alias.py --dry-run   # a wrongly verified team alias; --list-suspects
```

**Refit - on a copy of the DB, installed only with the operator's go** ("Changing the pipeline" 4; `docs/sofa/CONFIG.md` section 7)
```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/prepare_refit.py --date <d> [--db-path <copy>] {backup [--db <path>]|rebuild-cache-rows [--dry-run|--confirm] [--without-db-backup] [--derived ...] [--no-tennis-rating]|fit|compare [--days <d> <d2>] [--with-sheet]|install --confirm|restore --confirm --backup <dir>}
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_confidence.py --classes-only   # only the by_class curves
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_sport_confidence.py --sport {hockey|basketball|volleyball|cs2|all} --before <d> [--dry-run] [--rows-out <dir>] [--bb-freshness auto|on|off]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_settleability.py --before <d> [--dry-run]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_sport_confidence.py --sport all --before <d> --dry-run --rows-out <dir> --out <dir>/cal.json   # ~15 min a sport: the Superbet rows line evidence reads
PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_line_evidence.py --before <d> --sport-rows-dir <dir> [--dry-run]   # after every curve refit (refresh_line_evidence.py does it daily); without the dir: no price-band cap for the sports
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_calibration.py --from <d> --to <d> [--epoch stats_only] [--write-config --before <d>]   # PASS n>=300 and |gap|<=2 pp
PYTHONPATH=src:. .venv/bin/python scripts/sofa/find_women_competitions.py
PYTHONPATH=src:. .venv/bin/python scripts/sofa/find_friendly_competitions.py --out docs/sofa/evidence/friendly_candidates_<d>.json   # candidates; a person decides
```

**History backfill** (bridge; short chunks, resumable)
```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_listings.py --sport {football|tennis|hockey|basketball|volleyball} --days 730 --max-minutes 7
PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_event_stats.py --sport {football|tennis} --days 365 [--board-days 7] --max-minutes 7
PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_football_lineups.py --days 365 --max-minutes 7
PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_cs2.py --days 180
```

**Measurement** (read-only evidence for a decision, never a gate)
```bash
PYTHONPATH=src:. .venv/bin/python scripts/sofa/report_market_coverage.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_settleability.py --from <d> --to <d> [--with-fit] [--json-out f] [--md-out f]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_blocked_families.py [--from <d>] [--to <d>]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_sport_identity.py --from <d> --to <d> [--sport hockey]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_model_defects.py [--start <d>] [--end <d>]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_own_sample_gap.py --from <d> --to <d> [--sport football|tennis]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_sample_composition.py [--start <d>] [--end <d>] --metrics goals_for corners_total
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_schedule_context.py [--start <d>] [--end <d>]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_score_model.py --sport {hockey|basketball|volleyball} --date <d> [--date <d2>] [--rows-out f]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_score_history.py --sport <s> --start <d> --end <d> [--params '{...}']
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_model_information.py --rows <rows.jsonl>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_player_props.py --sport {basketball|hockey} [--date <d>] [--rows-out f]
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_devig.py --from <d> --to <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/probe_lineup_availability.py --date <d> [--dry-run] [--summary]   # not yet run
```

**Gates before a commit**
```bash
.venv/bin/python -m pytest tests/sofa -q
.venv/bin/python -m ruff check src/bet/sofa scripts/sofa
.venv/bin/python -m mypy --strict --no-incremental src/bet/sofa scripts/sofa   # a stale mypy cache gives false errors
PYTHONPATH=src:. .venv/bin/python scripts/sofa/check_test_registry.py
```

## Hard rules

- **The PDF rendered from `11_coupon.json` is the coupon.** Reporting
  `06_coupon.json`, `p_bar` or `08_confidence.json` as the coupon inverts the day.
- **Never invent** a number, a fixture, a price or an availability.
- **Never print a combined / Bet Builder / parlay price**, and never present
  `odds_if_product` as one - Superbet does not price a slip as the product of
  its legs (measured markup 8.8–19.6%).
- **No stake sizing, no automated placement.** The stake is the operator's.
- **Never read, echo or log `.env` values.**
- **Curves are fitted on the history of events and statistics** (operator,
  2026-10-07: "nasze źródło to historia statystyk"), replayed as of each match
  with the estimator the sheet uses today (rating included). Our own settled
  days are an audit of a curve, never its source; line evidence (offsets, price
  bands) is a guard that only lowers, and any number it holds is reported as
  measured on N days.
- **Never re-fit or install constants or calibrations without the operator's
  go**, and never into a day already built: a refit runs on a copy of the DB,
  installs only after `tests/sofa` pass.
- **A pooled number must say what it pooled across.** Friendlies are out of
  samples and ratings (`bet.sofa.comparability` is the one "does this past
  match count" rule). "History is thin" is not an argument before
  `backfill_listings.py` has run.
- **Never strip `UNFITTED_CONSTANTS`** from a row or a report.
- **Sofascore and Superbet only** - no other data provider in the pipeline.
  Superbet `190` (virtual football), `75` (e-football), `157` (e-hockey) and
  `70` (e-basketball) are simulations - never add them.
- A settled result is a fact about the day, **not about the decision that made
  it**. "It won" never enters the reasoning for the next one.

## The bridge (Sofascore through a real browser)

- **`MIN_INTERVAL_MS = 350` in the userscript is the safety mechanism and is
  never lowered.** It paces each connection; capacity comes from more tabs,
  never a faster tab. (2026-09-17: one `curl_cffi` client, 100 workers,
  550 req/s, no browser - the shape the bridge exists to prevent.)
- **Open the windows with `launch_bridge_browser.py`;** they may be minimised.
  Its launch flags stop Chrome clamping a hidden page's timers to >= 1000 ms
  (which silently cut a tab to ~1 req/s). They are process-creation flags, so
  Chrome must be fully quit first; the script refuses otherwise.
- **`SOFA_MAX_CONCURRENCY` is the window count — never below it.** Measured
  2026-09-22, five windows:

  | `SOFA_MAX_CONCURRENCY` | achieved | p50 | p90 |
  |---|---|---|---|
  | 3 | 0.15 req/s | 20,138 ms | 20,162 ms |
  | **5** | **11.67 req/s** | **354 ms** | **620 ms** |
  | 8 | 11.72 req/s | 668 ms | 704 ms |
  | 12 | 11.66 req/s | 1,010 ms | 1,056 ms |

  Above the window count only latency grows (queue depth → `STALE_PRICE`);
  below it the bridge collapses. Change it together with `--windows` and
  re-run `measure_bridge_capacity.py`.
- **`SOFA_TARGET_RPS` sits above what the tabs serve** (5 x 2.86 = 14.3 req/s,
  so 20). A starved bucket idles the tabs.
- **Measure the round trip, not the wall clock around the client** - the token
  bucket is inside the client; use `p50 net` from `measure_bridge_capacity.py`.
- **Refusals happen.** Sofascore has answered 403 bursts (5 x 403 in one
  instant) during long runs at full width (2026-09-28, -29, -30; once only a
  hand-solved challenge helped). Unmeasured suspicion: a token lasts ~25 min
  under sustained load. Backfills run short and resume; a refusal means slow
  down - never refresh tokens pre-emptively to outrun it.
- **Superbet has a breaker too:** 3 failures (403 / 429 / 5xx / timeout; a 404
  is an answer) open it (`SOFA_BREAKER_*`). OFFER keeps the unasked fixtures'
  old entries (CONFIDENCE refuses them STALE_PRICE); an all-refused SHADOW /
  CS2 snapshot is FAILED.
- `SOFA_NOW` freezes `timeutil.now()` for as-of replays only; `run_pipeline.py`
  refuses it.

## Working style

- **Evidence or it did not happen.** A claim about the pipeline names the file
  and line, or the artifact and field. An unmeasured statement is marked as a
  suspicion.
- **A skipped check is named.** If a run went clean, a guard was *not tested* -
  never "it works".
- **Check a subagent's numbers** when you can check them locally.
- Live runs are deliberate: hours of bridge time, visible to a third party's
  production API.

## Language and repository

Operator-facing documentation in `docs/sofa/` is **Polish** (so are the
analysts' reports). Code, tests, this file and the `.claude/` contracts are
**English**. `data/sofa.db` is the only working database. The slip calculator
is `scripts/sofa/audit_slip.py` (`bet.sofa.slip_audit`); the operator's builder
method is `docs/sofa/SUPERBET_BET_BUILDER_METHOD_v3.md`.
