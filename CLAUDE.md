# Working agreement — `bet`

## OPEN DECISION (2026-10-02) - read before running or refitting anything

The operator's instruction, 2026-10-02 ~10:15Z:

- **Today's `/sofa-day` 2026-10-02 runs in a separate session, on the CURRENT
  config.** No refit is installed. Do **not** run `prepare_refit.py install`,
  `fit_constants.py` or `fit_confidence.py` against `config/`, and do not
  "fix" the config during the day run.
- **D-1 (2026-10-01) is already settled and recorded** (08:49-08:53Z:
  `run_settle --include-unpriced`, audit 7c/7d, D-5 re-settle, regrade, sport
  coupons, WSZYSTKIE, ledger 09-24..10-01). Re-running step 1 is harmless (it
  merges), not required.
- **A refit candidate is prepared and NOT installed:** `data/refit_2026-10-02/`
  (`config/`, `compare_report.md`); backups in `config/backup_2026-10-02/` and
  `data/backup_2026-10-02/sofa.db`. Do not delete or overwrite them. The DB's
  `cache-calibration` rows were rebuilt (25.8M -> 49.4M); today's SHEET and
  CONFIDENCE read `config/`, not those rows, so the day run is unaffected.
- **The install decision belongs to the main (audit) session, after the
  operator reports the day run done.** Replay of 09-30 + 10-01 on the new
  config (in-sample): official -1.66 u, WARIANT -6.76 u. Three checks are
  open first: (1) `*_total` confidence curves jumped (tackles 0.72 -> 0.93,
  throw-ins 0.65 -> 0.79, fouls 0.80 -> 0.92) - suspected replay-p vs SHEET-p
  mismatch after the pooled-totals replay fix; (2) tennis per-set markets
  (`games_set1/2_total`, `games_won_set1/2_for`) would get curves and leave
  AWAITING_OWN_CURVE - they were measured overconfident before; (3) half-match
  coherence worse (`goals_for` -15.5%, `fouls_for` -15.3%, `throw_ins_for`
  -27.9%).
- The first SHEET today re-parses the football history (~10 min; the listing
  index was filled this morning) - do not kill it.

**Update 2026-10-02 ~12:30Z:** the checks are done - do NOT install this
candidate (data/refit_2026-10-02/ is kept only as a reference). The fixes are on
main (9c420cf2): curves keyed on the stored p_central, the replay priced like
SHEET (NB, variance scale), tennis per-set games markets need
`admitted_tennis_set_markets`, half coherence on the same matches, regional
groups split into league units, second-squad matches out of the senior sample
and rating (HISTORY_PARSER_VERSION 2026-10-02.3 - the next SHEET re-parses).
**Next (2026-10-03 morning, before the run):** settle 10-02, then
`prepare_refit.py --date 2026-10-03` backup -> rebuild-cache-rows -> fit ->
compare --days 2026-09-30 2026-10-01 2026-10-02. Before install, decide
`shots_total` (UNDER legs realise ~9 pp under claim live) and fouls/tackles
totals (live -39 pp n=30 / -17 pp n=8): proposal - keep them off the coupon.

Remove this section when the decision is taken.

## The only pipeline in service is `sofa`

Sofascore statistics, Superbet prices, football and tennis. The product of a
day is **`runs/sofa/<date>/KUPON_<date>.pdf`**.

```
BOARD → RESOLVE → OFFER → SAMPLES → OFFER → SHEET → COUPON
                                          ↘ CONFIDENCE → PDF   ★ the product
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
| a full betting day - coupon, WARIANT, four sport coupons, WARIANT WSZYSTKIE, D-1 settled and recorded for all | `/sofa-day [dzisiaj\|wczoraj\|YYYY-MM-DD]` |
| the per-sport read over an existing sheet | `/sofa-analyze` |
| coupon + PDF from artifacts on disk | `/sofa-rebuild` |
| adversarial verification of a built day | `/sofa-verify` |
| settle D-1 and decide about constants | `/sofa-settle` |
| price a slip the operator screenshotted | the `bet-slip-audit` skill |

Agents: `sofa-runner`, `sofa-analyst-football`, `sofa-analyst-tennis`,
`sofa-verifier`, `sofa-settler`, `sofa-market-scout`, `sofa-sport-runner`
(one measured sport's experimental coupon; four run in parallel). Skills preloaded into
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
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_pdf.py --date <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_confidence.py --date <d> --profile wariant    # variant, beside the coupon
PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_coupon_pdf.py --date <d> --profile wariant  # -> KUPON_<d>_WARIANT.pdf
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
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_score_model.py --sport {hockey|basketball|volleyball} --date <d> [--date <d2>] [--rows-out f]   # score model vs Superbet's price on graded shadow lines (bootstrap over games); measurement only
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_score_history.py --sport <s> --start <d> --end <d> [--params '{...}']   # score model on the results history (proper scores, no prices)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_model_information.py --rows <rows.jsonl>   # does the model add to the price? b of logit(y) ~ model + price, bootstrap over games
PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_disagreement.py --from <d> --to <d> [--sport football|tennis|all] [--profile standard|wariant|both]   # MAX_DISAGREEMENT re-measured on settled rows: refused vs admitted per profile, gap bands, match bootstrap, event-id halves; measurement only; the threshold decision is the operator's, between days
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
PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_multi_coupon.py --date <d>        # WARIANT WSZYSTKIE: the official PDF + four sport coupons, verbatim, runs/sofa/multi/<d>/
PYTHONPATH=src:. .venv/bin/python scripts/sofa/settle_multi_coupon.py --from <d> --to <d>
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_variants.py --date <d>          # re-derive the sport coupons from raw snapshots; WSZYSTKIE vs its sources
PYTHONPATH=src:. .venv/bin/python scripts/sofa/record_results.py --from <D-8> --to <D-1>   # ledger: every variant + rule + measurement, runs/sofa/ledger/results.jsonl; D-2 too (legs after 00:00Z grade a day late)
PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_ledger.py --from <d> --to <d> [--variant sport:hockey]   # read the ledger: one table per variant, never pooled

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
- **`KUPON_<date>_WARIANT.pdf` is not the coupon either.** It is the
  operator's variant (floor 0.65, confidence x odds >= 0.90, and since
  2026-09-23 13:30 UTC a ladder margin up to 15% against the coupon's 10.5%),
  measured -3.2% per bet against the official -2.9% before it was added (with
  the 10.5% margin - the two settings are different experiments). It is built into its
  own files, settled beside the coupon (audit_settlement section 7d), and its
  result is never pooled with the coupon's.
- **CS2 is a measurement, not a coupon market.** `CS2` / `CS2_SETTLE` write
  only `runs/sofa/cs2/<date>/` and test whether Superbet's devigged CS2 price
  already matches the outcomes. Superbet `sportId=190` is *virtual* football
  and `75` is e-football - neither is a real sport; never add them.
- **Hockey, basketball and volleyball are a measurement too** (since
  2026-09-29): `SHADOW` / `SHADOW_SETTLE` write only
  `runs/sofa/shadow/<sport>/<date>/`, grade Superbet's lines (two-way, and
  since 2026-09-30 1X2 / odd-even / yes-no / exact score as whole groups) against
  Sofascore's score, and never feed or gate the coupon. Superbet `157`
  (e-hockey) and `70` (e-basketball) are simulations - never add them.
- **The per-sport experimental coupons are not the coupon** (since
  2026-09-30, the operator's order): `KUPON_<d>_{CS2,HOKEJ,KOSZYKOWKA,SIATKOWKA}.pdf`
  are built by `run_sport_coupon.py` into the measurement's own directory
  (`runs/sofa/cs2/<d>/`, `runs/sofa/shadow/<sport>/<d>/`), never into
  `runs/sofa/<d>/`. Price-only - the coupon reads no model (score_model.py and
  the CS2 engine are measurements), so the
  probability is Superbet's devigged price and EV at that price is minus the
  margin; singles only; graded by `settle_sport_coupon.py` per sport and never
  pooled with the coupon or with each other. The rule replayed on the one
  settled hockey day (09-29) went 33/46 against a mean fair p of 85.1%,
  ROI -17.7%. The CS2 / SHADOW rules above still hold: nothing from these
  sports feeds or gates the coupon.
- **`KUPON_<d>_WSZYSTKIE.pdf` is not the coupon either** (since 2026-09-30):
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
`.claude/legacy/`, `.kilo/legacy/`, `docs/legacy/`. They are kept because their
artifacts and database rows are still on disk. Do not take stage names,
quantities (`p_low`, CALL/LEAN/WEAK/DROP) or artifact names from them, and do
not "restore" one without reading `docs/legacy/README.md` first.
