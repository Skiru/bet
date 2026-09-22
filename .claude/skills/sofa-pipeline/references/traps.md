# Traps that have actually cost something

Every entry here is a measured incident, not a worry. They are ordered by how
often they recur.

## Vocabulary

**Reaching for `simple`'s stage names.** There is no DISCOVER, no ENRICH, no
ANALYZE, no TIPSTERS in `sofa`, and no mapping between the two vocabularies.
On 2026-09-21 the first fifteen minutes of a run went into looking for a stage
that does not exist. Read `DEFAULT_SEQUENCE`.

## The product

**`06_coupon.json` is not the coupon.** Three files on disk call themselves
one. The VALUE-singles selector returned **−20.4%** on 2026-09-20 while the
PDF's Bet Builders returned **+8.2%** the same day. Reporting `06_coupon` as
the day's result inverts the day.

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

**Anti-selection is structural.** The coupon ranks on `surplus /
required_odds`, and `surplus = offered − 1.10/p_bar` grows as `p` is
overstated, so the rows most likely to be wrong sort to the top. **A surplus
above +0.40 is suspect by definition.** Check the distribution of VALUE across
markets, leagues and `sample_size`: if it concentrates in the weakest
measurement, it is an artifact, not an edge. An over-representation of fourth
tiers and youth leagues means *lack of data* is winning, not skill.

**Stale samples are actively selected for.** A sample that has stopped tracking
a player disagrees with the current price more often, and the coupon ranks on
exactly that disagreement. On 2026-09-21 the day's highest-surplus single
(+2.741 at 5.90) rested on a sample whose newest match was 105 days old, and
one row reached the coupon on a sample 193 days old. `MAX_SAMPLE_AGE_DAYS = 60`
closed it; the *shape* of the error is the durable lesson.

**Half-match rows lean on a global prior.** At `K_CENTRE = 25` a sample of n=8
contributes 24% of its own centre. Before trusting a `*_1h_*` / `*_2h_*` row,
compute `n/(n+25)` and say how much of it is the league. `corners_2h_*` has 62
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

**Board size is the calendar, not a fault.** 2026-09-20: 1040 football
fixtures. 2026-09-21: 102.

## Measurement

**Only 52.4% of ladders can be checked at all.** `sets_total` and `aces_*` were
**0%**. `NO_LADDER_CHECK` on a row means it passed without that test, not that
it passed the test.

**We read about a tenth of Superbet's screen.** `unmapped_markets` was 21,290
on 2026-09-21. A market we generate no row for is not a market we judged badly;
it is one we never looked at.

**The confidence curve is fitted on a probability that does not ship.**
Open, measured 2026-09-21, **not fixed**. `run_sheet.py` shrinks the sample
mean toward the league baseline (`centre = w_c·mean + (1−w_c)·prior`,
`K_CENTRE = 25` for football) and prices `p_central` from that centre.
`fit_confidence.py` recomputes its own `p` from the **raw** `sample_mean` and
skips the shrinkage entirely. So every curve the count metrics are served from
is keyed on a model that never ships.

Replayed over a real sheet (3,398 non-derived count rows, derived markets
excluded because `derived.py` prices those and the recomputation says nothing
about them):

| | divergence `|p_fit − p_central|` |
|---|---|
| median | **0.0291** |
| p90 | 0.1322 |
| share above 0.025, one calibration bucket wide | **52.4%** |
| worst: `goals_for` | median 0.083, p90 0.212 |
| `games_total` (tennis, `K_CENTRE = 2`) | **0.0052** |

That last row is the proof rather than an aside: tennis barely shrinks, so
tennis barely diverges. The gap *is* the shrinkage.

Everything gated on `realised_lo95` inherits it — the 0.80 confidence floor,
`MAX_DISAGREEMENT`, `leg_is_ev_positive`, and the `ABOVE_MEASURED_CEILING`
drop on the singles. `fit_constants.py` was corrected for exactly this;
`fit_confidence.py` was not. **Treat a football market's measured ceiling as
approximate until it is.**

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

**Set `SOFA_TARGET_RPS` from a measurement, never above it.** The burst that
coincided with Sofascore closing `/api/v1/` on 2026-09-17 (~2800 requests in 15
minutes, peaking at 550 req/s) was **one** `curl_cffi` client with 100 workers
and no browser — not a shape the bridge can produce.
`scripts/sofa/measure_bridge_capacity.py` ramps the rate and reports the
plateau: **3.9 req/s on three tabs** (2026-09-22, 360 requests, zero non-200),
reached already at a target of 4. Asking for 14 delivered the same 3.9 and took
the bridge round trip from 605 ms to 5,603 ms — above the plateau you buy
queue, not speed.

**Never lower `MIN_INTERVAL_MS`.** That is the *per-connection* pace and the one
number that makes a tab look like a person. Capacity comes from more tabs.

**The browser is the binding limit, not Sofascore.** Three tabs served 3.9 req/s
and not the 8.6 the 350 ms floor allows, because Chrome throttles hidden tabs: a
throttled tab takes ~40 s to claim a job and answers the same routes in ~2,000 ms
instead of ~175 ms. `check_bridge.py` warns above 600 ms.

**Never re-fit constants mid-day.** `fit_constants.py` is outside
`DEFAULT_SEQUENCE` on purpose; re-fitting breaks comparability with yesterday.

**Two writers on one config file.** `calibrate_from_cache.py --out` does not
own `sofa_market_reliability.json`; `fit_constants.py` does, and applies a
confidence-interval gate the other does not. When both wrote it, an empty file
overwrote a measured one and reported success.

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
