# Traps that have actually cost something

Read this before a rebuild, a re-read, a settle or a report. Each entry is a
measured incident; the rule it left is in bold.

## The product

- **`06_coupon.json`, `p_bar`, `required_odds`, `surplus` and VALUE are the
  old priced selector.** A `p_bar` beside a `confidence` is two different
  questions, not a disagreement to resolve.
- **`08_confidence.json` is not the coupon** - it lacks the sport legs,
  positions, blocks and locks. Read "what was printed" through
  `confidence.coupon_artifact()` and what the PDF rendered from
  `12_printed.json` / `printed/`.
- **Any PDF render is a print.** The next rebuild locks every printed leg
  whose match has started, whatever reads arrive later (shown in
  `locked_late_refusals`, never acted on). Early kickoffs lock unread legs
  (10-11: 22). **Render the PDF when the coupon is meant, and read a buffer of
  the next matches** (`read_set.py --buffer N`) so a rebuild that reshuffles
  the top 30 does not print unread legs (10-18: 101).
- **Positions shift after every rebuild.** Name a leg by `group_key` + market +
  line + direction, never by position, unless the request is against the
  build the operator is looking at.
- **A sport read is counted as `reads_sport`, never `UNMATCHED_READ`** -
  COUPON_ASSEMBLY applies it; check the leg's `reads` / `removed_by_reads` in
  `11_coupon.json`. An `UNMATCHED_READ` always did nothing - report it.
- **A WATCH on a builder leg rotates the builder:** the next unread leg of
  that fixture moves in and C3 fails again. Read a fixture's whole builder
  candidate set at once.
- **`ev_if_product_priced` is not an EV**, and `stakeable_builders` is not
  `builders` (one day: "3 stakeable" in CONFIDENCE, none staked after the haircut).
- **A locked leg keeps the `ladder_no` it was printed with**, which may name a
  ladder no longer in `ladders[]`. Read ladders from `ladders[]` and the PDF's
  `ta sama drabina: N`, not from a locked leg.
- **A mixed day has two rules.** A leg printed before a switch moment is the
  old rule and never a defect under the new one; judge a build by its own
  clock and compare days only inside one ledger group.

## Rebuilds

- **A stale offer empties the coupon.** CONFIDENCE on a > 45 min offer refuses
  everything `STALE_PRICE` and 08 shrinks to the locked legs - it reads like a
  modelling result. `rebuild_day.py` refreshes OFFER / SHADOW / CS2 first;
  never run CONFIDENCE by hand on an old offer.
- **A rebuild re-runs SHEET only when a rule marker is missing**
  (`rebuild_plan`): an estimator change without a marker, or a refit install,
  leaves the old `p_central` in the sheet and the new curves read it (a
  refit shows as `CONFIG_CHANGED`). Re-running SHEET then is the main
  session's call (`run_pipeline.py --only SHEET`, ~10 min).
- **Verify after every rebuild** - the verifier found a defect after each of
  four rebuilds in a row.
- **A scratch rebuild can clobber the real coupon.** A script given a scratch
  dir may still write the day's real files (`run_confidence.py
  --calibration` without `--runs-dir` overwrites the real 08). md5 the real
  files before and after, and read each script's output path.
- **Vetoes go stale when code changes.** A veto written against a defect or a
  thin sample stays in `vetoes.json` after the code fixed it; re-check such
  vetoes after a code change (SHEET and CONFIDENCE both read them).
- **Merge only this pass's reports, by name.** A glob over hand-off files once
  merged a stale pass's verdicts into today's legs. In zsh an unmatched glob
  aborts the whole command line (`no matches found`) - quote patterns or name
  files.

## Selection and measurement

- **Anti-selection is structural in the old selector:** surplus grows as p is
  overstated, so the rows most likely wrong sort to the top. A surplus above
  +0.40 is suspect; check whether VALUE concentrates in fourth tiers, youth
  leagues or thin samples (lack of data winning, not skill). Stale samples are
  selected for the same reason (`MAX_SAMPLE_AGE_DAYS` 60 closed it).
- **Half-match rows lean on the prior**: n / (n + 15) of the centre is the
  team. A stale `config/sofa_league_baselines.json` (corners priors 24-32% too
  high) was silent for two days - check `fitted_from` and
  `half_match_coherence` of a config file before trusting a sheet on it.
- **A curve must be fitted on the probability that ships.** Whenever SHEET's
  estimator changes, the replay that fits the curves must price the same
  estimator, or the curve describes another number. A p from an estimator no
  curve was fitted on is the first suspect when a bucket's realised rate sits
  far from its confidence.
- **Only ~half of ladders can be checked** (`sets_total`, `aces_*`: 0%).
  `NO_LADDER_CHECK` means the row passed without the test.
- **We read about a tenth of Superbet's screen** (`unmapped_markets` ~21-28k a
  day). A market with no row was never judged, not judged badly.
- **Two writers on one config file**: `calibrate_from_cache.py --out` does not
  own `sofa_market_reliability.json` (`fit_constants.py` does); once an empty
  file overwrote a measured one and reported success.
- **Yesterday's evidence is what a skipped refresh reads.** Without the
  morning `refresh_line_evidence.py --before <D>` no D-1 line counts; an
  evidence file without `games` makes a no-curve key `NO_LINE_EVIDENCE`.
  Check `fitted_from.before` against the day.
- **Sport history went stale 10-05..10-12**: game results were never
  re-fetched. `refresh_sport_history.py` runs first in the morning refresh;
  `day_status.py` WARNs `sport_history` below 80%.
- **Subagent numbers need verification** - one adversarial pass found 18
  errors in one file, two inverting the argument. Check what you can check locally.

## Clocks and calendars

- **Two clocks, and the error runs the wrong way.** On ITF tennis Sofascore
  publishes local time as UTC (gaps to 11 h) - a finished match looks
  upcoming. The start clock is the earliest of all clocks, deliberately.
- **RESOLVE's clock goes stale during the day** (Superbet moves a match);
  FIXTURE_CHECK re-reads `/event/{id}` before CONFIDENCE. Without the bridge
  the events are `UNVERIFIED` and the frozen clock stands.
- **Board size is the calendar**: 1,040 football fixtures on a Sunday, 102 on
  a Monday. The coverage floor is weekday-blind; **judge matching by the
  RESOLVE rate (72-90% is healthy)**.
- **Pipeline log timestamps are local (UTC+2)**; trust `date -u`.

## Environment and the bridge

- **`.venv` has two interpreters**: `.venv/bin/pip` installs where nothing
  imports. Use `.venv/bin/python -m pip`.
- **The bridge's health can lie**: `ok: true` with a dead tab. Read the poll
  age (`check_bridge.py`); it warns above 600 ms per request.
- **`SOFA_TARGET_RPS` (20) sits above what the tabs serve** (5 windows x 2.86
  = 14.3 req/s); **`SOFA_MAX_CONCURRENCY` equals the window count** (at 3 on
  five windows the bridge fell to 0.15 req/s); **`MIN_INTERVAL_MS` is never
  lowered** - capacity comes from more tabs. A tab opened without
  `launch_bridge_browser.py`'s flags is throttled to ~1 req/s.
- **Refusals happen** (403 bursts in long runs). A refusal means slow down and
  report - never refresh tokens to outrun it.
- **A refit never runs on the live database**: `rebuild-cache-rows` deletes
  and replays tens of millions of rows; it runs on a `VACUUM INTO` copy with
  `--db-path` and `--without-db-backup`, and `install` needs the operator's go.
- **A stale mypy cache gives false errors**: gate with `mypy --strict
  --no-incremental`. `ruff` does not catch a duplicate enum member.
- **Never `git stash`** - a pop once applied an old stash into a shared tree.

## Research hygiene

- **The web index runs ahead of the decision.** A snippet carrying a score has
  reached you. Fix the decision point (scheduled start in UTC, now, the delta)
  **before** any web tool runs; a started fixture is not a research subject;
  ask for the historical fact and its period, never the two names alone.
- **Tennis cannot really be verified externally** (no free game-level ITF
  statistics). Say "nie do zweryfikowania"; never manufacture a source.
