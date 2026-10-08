# Traps that have actually cost something

Every entry here is a measured incident, not a worry. They are ordered by how
often they recur. The rules in force after 2026-10-07 are in `SKILL.md`,
"The 2026-10-07 rules"; an entry that names an older rule says so.

## Vocabulary

**Reaching for `simple`'s stage names.** There is no DISCOVER, no ENRICH, no
ANALYZE, no TIPSTERS in `sofa`, and no mapping between the two vocabularies.
On 2026-09-21 the first fifteen minutes of a run went into looking for a stage
that does not exist. Read `DEFAULT_SEQUENCE`.

## The product

**`06_coupon.json` is not the coupon.** The VALUE-singles selector returned
**−20.4%** on 2026-09-20 while the PDF's Bet Builders returned **+8.2%** the
same day. Reporting `06_coupon` as the day's result inverts the day.

**`06_coupon.json`, `p_bar`, `required_odds`, `surplus` and VALUE are still
priced.** The stats-only epoch took the price out of `p_central` and the
coupon, not out of the old selector: SHEET still computes the bar, COUPON
still selects on it, `audit_coupon.py` still audits it. None of it is the
coupon's confidence, order or price rule. A `p_bar` next to a stats-only
`confidence` is two different questions, not a disagreement to resolve.

**`08_confidence.json` is not the coupon on a stats-only day - `11_coupon.json`
is.** 08 holds only football and tennis, no positions, no blocks, no measured
sport legs and no sport locks; the PDF refuses a stats-only 08 without an 11.
Read "what was printed" through `confidence.coupon_artifact()` (11 where it
exists, else 08), and what the PDF actually rendered from `12_printed.json`.

**A provisional PDF locks legs.** A stats-only day's own PDF writes `12_printed.json`,
and the next rebuild carries over, unchanged, every printed leg whose match
has started (`locked_print`) - whatever reads or prices arrived since. So a
"quick look" PDF before the analysts' reads is a print: a leg on it that
starts before the rebuild stays on the coupon even if a read would have
removed it (shown in `locked_late_refusals`, never acted on). Render the PDF
when the coupon is meant.

**Positions shift after a rebuild.** `position` in `11_coupon.json` is
recomputed every assembly (a leg locks, a read removes one, a price moves).
Name a leg in `read_requests.json` by `{"group_key": "sofa:<id>", "market",
"line", "direction"}`, not by `{"position": n}`, unless the request is
written against the build the operator is looking at.

**`UNMATCHED_READ` for a sport read in `run_confidence.py` is expected.**
CONFIDENCE sees only football / tennis sheet rows, so a read for a hockey /
basketball / volleyball / CS2 leg matches nothing there and is printed on its
stderr. COUPON_ASSEMBLY applies it (`coupon_sports.apply_reads`): check the
leg's `reads` / `removed_by_reads` in `11_coupon.json`, not the CONFIDENCE
stderr.

**`ev_if_product_priced` is not an EV.** Superbet applies its own correlation
adjustment and that adjustment is the whole margin (measured 8.8–19.6%).
Select on `ev_after_haircut`.

**`stakeable_builders`, not `builders`.** They disagree, which is why both are
reported since 2026-09-21: CONFIDENCE said "3 stakeable" on a day the PDF
staked nothing, all three refused for negative EV after the haircut.

**The 2-, 3- and 4-leg builders on one fixture are subsets of each other.**
Staking all three stakes one opinion three times. On 2026-09-19 that dressed 54
fixtures up as 79 independent bets with 46 of 148 legs repeated.

## Selection

**Anti-selection is structural** - in the old VALUE selector. COUPON
(`06_coupon.json`) ranks on `surplus / required_odds`, and `surplus = offered − 1.10/p_bar` grows as `p` is
overstated, so the rows most likely to be wrong sort to the top. **A surplus
above +0.40 is suspect by definition.** Check the distribution of VALUE across
markets, leagues and `sample_size`: if it concentrates in the weakest
measurement, it is an artifact, not an edge. An over-representation of fourth
tiers and youth leagues means *lack of data* is winning, not skill.

**Stale samples are actively selected for.** A sample that has stopped tracking
a player disagrees with the current price more often, and the VALUE selector
ranks on exactly that disagreement. On 2026-09-21 the day's highest-surplus single
(+2.741 at 5.90) rested on a sample whose newest match was 105 days old, and
one row reached the coupon on a sample 193 days old. `MAX_SAMPLE_AGE_DAYS = 60`
closed it; the *shape* of the error is the durable lesson.

**Half-match rows lean on a global prior.** At football `K_CENTRE = 15`
(since the 2026-10-03 refit; 25 before) a sample of n=8 contributes 35% of
its own centre. Before trusting a `*_1h_*` / `*_2h_*` row, compute
`n/(n+15)` and say how much of it is the league. `corners_2h_*` has 62
matches in the entire settled history.

**A stale baselines file is silent.** `config/sofa_league_baselines.json`
carried corners priors 24–32% too high for two days. Fixing it took VALUE from
142 to 99 on one day, `corners_2h_*` from 12 to 1, `shots_on_target_total`
from 3 to 0 — and the rows that vanished were precisely the ones independent
external verification had already rejected. Check `fitted_from` and
`half_match_coherence`.

## Clocks and calendars

**Two clocks, and the disagreement is structural.** Superbet posts a nominal
"not before" time for ITF matches, Sofascore publishes what appears to be the
tournament's local time as UTC. Gaps reach 11 h and the error runs the wrong
way — **a finished match looks upcoming**. COUPON takes the earlier of the two
and thereby refuses some un-started matches; that is deliberate. On 2026-09-18
six fixtures would have passed the gate with the result already known, saved
only by the bookmaker delisting them, which is protection by accident.

**The coverage floor is weekday-blind.** Its median is built from whatever runs
are recent, so a Monday (~100 football fixtures) against three weekends (~1000)
trips "matching regression" every time. **Check the RESOLVE rate instead** —
72–90% is normal — before believing it.

**RESOLVE's clock goes stale during the day.** 2026-10-05, Shanghai: RESOLVE
read 06:20Z, Superbet moved the match to 07:30Z, and a 06:12Z rebuild refused
three singles as "starting soon" and took their closing prices ~80 min early.
FIXTURE_CHECK (`run_fixture_check.py`, bridge) re-reads `/event/{id}` for the
printed matches and the moved clocks before CONFIDENCE; without the bridge
the events are `UNVERIFIED` and the frozen clock stands.

**Board size is the calendar, not a fault.** 2026-09-20: 1040 football
fixtures. 2026-09-21: 102.

## Measurement

**Only 52.4% of ladders can be checked at all.** `sets_total` and `aces_*` were
**0%**. `NO_LADDER_CHECK` on a row means it passed without that test, not that
it passed the test.

**We read about a tenth of Superbet's screen.** `unmapped_markets` was 21,290
on 2026-09-21. A market we generate no row for is not a market we judged badly;
it is one we never looked at.

**The confidence curve must be fitted on the probability that ships.**
Measured 2026-09-21 and **fixed 2026-10-02** (`fit_confidence.py` keys every
row on its STORED `p_central`; the cache replay calls SHEET's own estimator;
8cfdd50e): `fit_confidence.py` had recomputed `p` from the RAW `sample_mean`
with no shrinkage, so a curve was keyed on a model that never shipped (median
divergence from SHEET's `p_central` 0.0291, 52.4% of rows above one bucket
width, football `goals_for` worst; tennis `games_total` 0.0052 because tennis
barely shrinks - the gap *is* the shrinkage). The durable lesson: whenever
SHEET's estimator changes (tennis rating prices, football joints from marginal
centres, basketball freshness - 2026-10-07 14:05Z) the replay that fits the
curves must price the same estimator, or the curve describes another number.
The 2026-10-07 refit did that for tennis and basketball; football goals joints
were NOT replayed (`--derived` off), so derived joints have no curve and read
their Superbet lines only. A p from an estimator no curve was fitted on is the
first suspect when a bucket's realised rate sits far from its confidence.

**`UNFITTED_CONSTANTS` is the row telling the truth.** `K_PRICE` and
`MAX_LADDER_SIGMA` are not fitted. Never remove the note to make a report read
better.

**Subagent numbers need verification.** One adversarial pass over a single
agent file found **eighteen** errors, two of which inverted the argument.
Check any claim you can check locally.

## Environment

**`.venv` has two interpreters.** `.venv/bin/python` is 3.12 and runs the
pipeline; `.venv/bin/pip` belongs to 3.14. Installing with the latter reports
success and the import still fails. Use `.venv/bin/python -m pip`.

**Sofascore answers 403 to every non-browser client.** Everything except BOARD
and the offline stages needs the browser bridge. `ok: true` is not enough — a
dead tab still reports ok; read the poll age.

**`SOFA_TARGET_RPS` (20) must sit ABOVE what the tabs can serve** (5 windows
x 2.86 = 14.3 req/s) — starving it is worse than opening it: if the bucket is
the limiter the tabs idle between jobs and pay the poll cycle.
**`SOFA_MAX_CONCURRENCY` (5) equals the window count and is never below it**
(CLAUDE.md's table: at 3 on five windows the bridge fell to 0.15 req/s).
Open the windows with `launch_bridge_browser.py` (or `ensure_bridge.py`);
they need not be visible. The old "3.9 req/s plateau on three tabs" was a
measurement artefact (the ramp held `max_concurrency` at 3 and timed its own
token bucket as latency). The burst that coincided with Sofascore closing
`/api/v1/` on 2026-09-17 (~2800 requests in 15 minutes, peaking at 550 req/s)
was **one** `curl_cffi` client with 100 workers and no browser — not a shape
the bridge can produce.

**Never lower `MIN_INTERVAL_MS`.** That is the *per-connection* pace and the one
number that makes a tab look like a person. Capacity comes from more tabs.

**The browser is the binding limit, not Sofascore.** A tab Chrome has
throttled (one opened without `launch_bridge_browser.py`'s flags) takes ~40 s
to claim a job and answers the same routes in ~2,000 ms instead of ~175 ms.
`check_bridge.py` warns above 600 ms.

**Never re-fit or install constants from a day's run.** `fit_constants.py` is
outside `DEFAULT_SEQUENCE` on purpose; re-fitting breaks comparability with
yesterday, so it runs on a copy of the DB and installs only on the operator's go.

**Two writers on one config file.** `calibrate_from_cache.py --out` does not
own `sofa_market_reliability.json`; `fit_constants.py` does, and applies a
confidence-interval gate the other does not. When both wrote it, an empty file
overwrote a measured one and reported success.

## Process (each one cost a rebuild or a misread, 2026-10-05..07)

**A rebuild does not re-run SHEET.** `rebuild_day.py` runs SHEET only when
`05_sheet.json`'s `epoch` is not `stats_only` or its `link_rule` is not
`shared_league` (`rebuild_plan`) - and, once a staged package is on
(`COUNT_DISPERSION`, `TENNIS_SCOPED_TABLE`, `CARDS_CORRELATION`, `PER_MARKET_K`;
all OFF today), when the sheet lacks its row marker. A change of the estimator - tennis rating
prices, football joints from marginal centres, basketball freshness, a refit -
leaves the old `p_central` in the sheet and the new curves read it: the
mismatch is silent. After such a change run `run_pipeline.py --date <d> --only
SHEET --run-id <id>` (minutes to ~10 min), then the rebuild.

**A glob that matches nothing aborts a zsh command line.** In zsh
`rm -f /tmp/*_reads.json /tmp/*_vetoes.json` stops with `no matches found`
before `rm` runs, so nothing is removed and everything after it in the line is
skipped; the same for an unquoted `--include=*.py`. Quote the pattern, name the
files, or use `find` (no nomatch). Clearing hand-off files is done by name.

**A glob merges what it should not.** Merging `/tmp/*_reads.json` into
`reads.json` took in a stale or foreign file (old sport reads, an earlier
pass's tmp files) and its verdicts applied to today's legs. Merge only the
files of THIS pass, by name (`/sofa-analyze` Step 2-3), and read the merged
file back.

**A stale mypy cache gives false errors.** After files change under a running
tree `mypy --strict` can report errors that are not there (or hide ones that
are). Gate with `mypy --strict --no-incremental` (and `--cache-dir=/dev/null`
to leave nothing behind); a green run is then 172 files, 0 issues (2026-10-07).

**A locked leg keeps the `ladder_no` it was printed with.** `build_coupon.
coupon_structure` sets `ladder_no` on a leg that stands on a ladder of two or
more rungs and never clears it; a leg locked from an earlier print arrives
with its old field, so after the other rungs left (removed before their start)
it can carry a `ladder_no` whose ladder is not in `ladders[]`. Read the
ladders from `ladders[]` and the PDF's `ta sama drabina: N` (counted per
`confidence.ladder_key` on the legs of the render), not from a locked leg's
carried number.

**A mixed day has two rules.** 2026-10-07 had four switches inside it
(06:45Z, 10:55Z, 13:42Z, 14:05Z): a leg printed at 09:00Z and locked is the
old rule and is never a defect under the new one; judge a build by the epoch
of its own clock. Compare days only inside one epoch; a refit install (config
content, 2026-10-07 17:51Z) is an epoch too although no `epochs` constant
names it.

**Yesterday's evidence is what a skipped refresh reads.** Without the morning
`refresh_line_evidence.py --before <D>` no settled line of D-1 counts, and an
evidence file written before the `games` field (or by an earlier day's rows
after a failed sport fit - exit 1) makes a key with no curve `NO_LINE_EVIDENCE`
under the v2 rules. Check `fitted_from.before` of the file against the day.

**A refit never runs on the live database.** `prepare_refit.py
rebuild-cache-rows` deletes the cache-replay rows (tens of millions, in chunks)
and replays them for tens of minutes (~27 min measured 2026-10-02, peak RSS
~25 GB); on `data/sofa.db` the daily loops' writers wait between chunks, the
delete is not undoable without a full DB copy, and without
`--allow-other-holders` the script refuses while another process holds the DB.
The rule (CLAUDE.md, "Changing the pipeline" 4): take a `VACUUM INTO` copy and
point `--db-path` at it with `--without-db-backup` (SKILL.md, "Between days").
`install` is the only step that touches `config/`, behind `--confirm`, and
only on the operator's go.

## Research hygiene

**The web index runs ahead of the decision.** A search result's *title and
snippet* are content: if a scoreline reaches you in a snippet, it has reached
you. The later in the day an analysis runs, the more of the index is
post-decision, and the contamination arrives dressed as a confident read. On
2026-09-07 a query about a player's tie-break record returned headlines
carrying that day's result; the searches were abandoned, which is the correct
recovery, and two factual questions still ended `CANNOT VERIFY`.

Establish the decision point — the fixture's scheduled start in UTC, `now`, the
delta — **before** any web tool runs. A fixture that has started is not a bet
and is not a research subject. Construct queries that cannot return a
scoreline: ask for the historical fact and its period, never the two
participants' names alone.

**Tennis cannot really be verified externally.** Game-level statistics for ITF
events are not available free, and tennis is usually two thirds of the board.
Say "unverified"; do not manufacture a source.
