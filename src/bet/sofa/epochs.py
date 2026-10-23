"""Comparability epochs of the coupon rule.

From 2026-10-05 (docs/sofa/history/PLAN_2026-10-05_SETTLE_I_KUPON.md, part 3, K0) the
coupon's confidence comes from the statistics alone: the price no longer
enters `p_central`, the order or the choice of Bet Builders, and is only the
condition for placing the bet (confidence x odds >= 0.90, ladder margin <=
15%). A build is in the `stats_only` epoch when its day is 2026-10-05 or later
AND it was built at or after STATS_ONLY_FROM_UTC - the moment between the last
morning build of 10-05 (08_confidence.json created 2026-10-05T06:13:33Z) and
the stats-only rebuild of that day. Everything before reads exactly as it did.

`build_at` is `timeutil.now()`, which honours SOFA_NOW: an as-of replay of an
older day (prepare_refit) stays under the old rule.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from bet.sofa import timeutil

STATS_ONLY = "stats_only"
OLD = "old"

STATS_ONLY_DATE = "2026-10-05"
# Entered in the commit right before the 10-05 stats-only rebuild (K9):
# after the last morning build (08_confidence.json created
# 2026-10-05T06:13:33Z, WARIANT 06:13:34Z), before the rebuild started.
STATS_ONLY_FROM_UTC = datetime(2026, 10, 5, 7, 15, 0, tzinfo=UTC)


# The installation of plan part 5 (F7): from this build time the measured
# sports (hockey, basketball, volleyball, CS2) print on the one coupon and
# their separate experimental coupons (run_sport_coupon.py) stop. None until
# F7 is installed - until then the separate coupons are the only record of
# those sports, so they are not stopped earlier (K5).
# Installed 2026-10-05 08:30Z, with the 10-05 rebuild that put the first
# hockey legs on the coupon.
SPORTS_ON_COUPON_FROM_UTC: datetime | None = datetime(2026, 10, 5, 8, 30, 0, tzinfo=UTC)


def sports_on_coupon(date: str, build_at: datetime | None = None) -> bool:
    """Do the measured sports print on the coupon for this build (F7)?"""
    if SPORTS_ON_COUPON_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return date >= STATS_ONLY_DATE and at >= SPORTS_ON_COUPON_FROM_UTC


def stats_only(date: str, build_at: datetime | None = None) -> bool:
    """Is a build of `date` at `build_at` (default: now) in the stats-only epoch?"""
    at = build_at if build_at is not None else timeutil.now()
    return date >= STATS_ONLY_DATE and at >= STATS_ONLY_FROM_UTC


def epoch_name(date: str, build_at: datetime | None = None) -> str:
    return STATS_ONLY if stats_only(date, build_at) else OLD


def artifact_epoch(doc: Mapping[str, Any] | None) -> str:
    """The epoch an artifact (or a locked leg's `printed_under`) was built in;
    no key is the old rule."""
    if not doc:
        return OLD
    return str(doc.get("epoch") or OLD)


def sheet_epoch(rows: list[Mapping[str, Any]]) -> str | None:
    """The epoch every row of a 05_sheet.json carries, OLD for rows without
    one, None when the rows disagree (a sheet assembled from two builds)."""
    seen = {str(r.get("epoch") or OLD) for r in rows}
    if not seen:
        return None
    return seen.pop() if len(seen) == 1 else None


# Plan docs/sofa/PLAN_2026-10-05_PRODUCTION_GRADE.md F2.1: "a curve that fails
# stops printing". measure_calibration.py --write-config --before <d> lists the
# curves whose printed confidence measurably missed their realised rate in
# config/sofa_curve_status.json (bet.sofa.curve_status); CONFIDENCE and
# SPORT_CONFIDENCE refuse a leg read off a listed curve with
# CURVE_FAILED_CALIBRATION - but only for a build at or after this moment.
#
# None = disabled: the file may exist and nothing is refused. The operator
# enables it BETWEEN DAYS, never mid-day (a curve refused halfway through a
# day makes the morning and afternoon prints two experiments), by setting it
# to a UTC moment before that day's first build, in its own commit - like
# STATS_ONLY_FROM_UTC. The day it starts is a new epoch for the ledger.
CURVE_STATUS_FROM_UTC: datetime | None = None


def curve_status_enforced(date: str, build_at: datetime | None = None) -> bool:
    """Does a build of `date` at `build_at` (default: now) refuse the curves
    config/sofa_curve_status.json lists? False while CURVE_STATUS_FROM_UTC is
    None."""
    if CURVE_STATUS_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= CURVE_STATUS_FROM_UTC.strftime("%Y-%m-%d")
            and at >= CURVE_STATUS_FROM_UTC)


# Plan 2026-10-05 production grade, F4 (docs/sofa/PLAN_2026-10-05_PRODUCTION_GRADE.md).
# Two things that change WHICH legs / builders print, so never mid-day: they
# act only on a day >= COUPON_STRUCTURE_DATE built at or after the moment.
#
# * the coupon form (bet.sofa.coupon_form): the ladder form "one_rung" and a
#   per-match position cap - both OFF by default (operator decision, plan
#   section 5 point 1); a dial set before this moment is ignored and said so;
# * the builder screen price (bet.sofa.builder_screen, F4.4): a Bet Builder
#   prints only with a screen price recorded in 09_screen_prices.json, and is
#   stakeable at that price; without one it is refused BUILDER_NO_SCREEN_PRICE.
COUPON_STRUCTURE_DATE = "2026-10-06"
COUPON_STRUCTURE_FROM_UTC = datetime(2026, 10, 6, 0, 0, 0, tzinfo=UTC)
# Switched off by the operator on 2026-10-05 (~12:45Z, before it ever acted):
# "jeżeli chodzi o buildery to nie wyceniaj mi ich, sam będę widział". sofa
# prints a builder's legs and its combined probability; the price is the one
# the operator sees on Superbet's screen. A recorded screen price
# (09_screen_prices.json) is still carried as a note; nothing is refused for
# want of one. None = off.
BUILDER_SCREEN_PRICE_FROM_UTC: datetime | None = None


def coupon_form_active(date: str, build_at: datetime | None = None) -> bool:
    """May the coupon-form dials (ladder_form, max_positions_per_match) act?"""
    at = build_at if build_at is not None else timeutil.now()
    return date >= COUPON_STRUCTURE_DATE and at >= COUPON_STRUCTURE_FROM_UTC


def builder_screen_price_required(
    date: str, build_at: datetime | None = None
) -> bool:
    """Does a Bet Builder need a recorded screen price to print (F4.4)?
    False while BUILDER_SCREEN_PRICE_FROM_UTC is None (operator, 2026-10-05)."""
    if BUILDER_SCREEN_PRICE_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= BUILDER_SCREEN_PRICE_FROM_UTC.strftime("%Y-%m-%d")
            and at >= BUILDER_SCREEN_PRICE_FROM_UTC)


# Plan 2026-10-05_PRODUCTION_GRADE, F0.6: from this build time (and for a day
# from SETTLEABILITY_DATE on) CONFIDENCE refuses a leg whose (competition,
# market family) is listed in config/sofa_settleability.json -
# NOT_SETTLEABLE. 10-05 was live when the gate was written, so its coupon
# (and any rebuild of it) stays under the rule it was printed by.
SETTLEABILITY_DATE = "2026-10-06"
SETTLEABILITY_FROM_UTC = datetime(2026, 10, 6, 0, 0, 0, tzinfo=UTC)


def settleability_gate(date: str, build_at: datetime | None = None) -> bool:
    """Does a build of `date` at `build_at` (default: now) refuse NOT_SETTLEABLE?"""
    at = build_at if build_at is not None else timeutil.now()
    return date >= SETTLEABILITY_DATE and at >= SETTLEABILITY_FROM_UTC


# Model fixes measured offline on 2026-10-05 (plan F2.2,
# docs/sofa/evidence/model_defects_2026-10-05.md) that change p_central and
# so the quantity every confidence curve is keyed on. None = disabled: the
# curves of the 10-05 refit (6fea99fd) were fitted on the estimator without
# them, and a curve fitted on one p_central does not describe another. The
# operator sets this to the install time TOGETHER with the next refit
# (prepare_refit.py: backup, rebuild-cache-rows, fit, compare, install),
# between days - never mid-day.
#
# Read on the wall clock, not timeutil.now(): SOFA_NOW freezes the clock in
# the past for the refit's cache replay and for as-of SHEET replays, and both
# must price with the estimator the new curves will describe.
MODEL_FIXES_FROM_UTC: datetime | None = None


def model_fixes_enabled(at: datetime | None = None) -> bool:
    """Are the F2.2 model fixes on (MODEL_FIXES_FROM_UTC)?"""
    if MODEL_FIXES_FROM_UTC is None:
        return False
    return (at if at is not None else datetime.now(UTC)) >= MODEL_FIXES_FROM_UTC


# Tennis games families priced by the rating's neighbours (measured out of
# sample 2026-10-07, docs/sofa/evidence/tennis_rating_prices_2026-10-07.md):
# games_won_for / handicap_games / most_games from MatchForecast.read, and
# games_total as W_GAMES_TOTAL_RATING x rating + the rest x the NB. Changes
# p_central, so it goes live TOGETHER with the refit of the tennis curves
# (calibrate_from_cache replaying the rating) - never mid-day.
TENNIS_RATING_PRICES_DATE = "2026-10-07"
TENNIS_RATING_PRICES_FROM_UTC: datetime | None = datetime(
    2026, 10, 7, 14, 5, tzinfo=UTC)  # operator, 2026-10-07: now, curves refit later


def tennis_rating_prices(date: str, build_at: datetime | None = None) -> bool:
    if TENNIS_RATING_PRICES_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return date >= TENNIS_RATING_PRICES_DATE and at >= TENNIS_RATING_PRICES_FROM_UTC


# Football derived goals joints (both_over / most / handicap) built from the
# marginal rows' centres (K_CENTRE shrink + rating, variance scaled and
# inflated by 1 + 1/n) instead of the raw sample mean and variance. Measured
# walk-forward 2025-08..2026-09 (375,714 matches, bootstrap by match): BTTS
# Brier vs the competition base rate +0.0172 -> +0.0051, most / handicap
# -0.006..-0.009 better than now. It moves every derived football p, so never
# mid-day and the derived keys' line evidence restarts (fit_line_evidence).
# Read on the day being built and the build clock, like the other switches.
DERIVED_MARGINAL_CENTRES_FROM_UTC: datetime | None = datetime(
    2026, 10, 7, 14, 5, tzinfo=UTC)


DERIVED_MARGINAL_CENTRES_DATE = "2026-10-07"
# Measured (walk-forward, 2025-08..2026-09): the goals, corners, shots on
# target and cards joints. Fouls / shots / offsides were not measured and keep
# the raw sample.
DERIVED_MARGINAL_CENTRES_METRICS = frozenset(
    {"goals_for", "corners_for", "shots_on_target_for", "cards_points_for"})


def derived_marginal_centres_enabled(
    date: str, build_at: datetime | None = None
) -> bool:
    """The day being built and the build's clock, as every other switch (a
    rebuild of an earlier day keeps the rule it printed under)."""
    if DERIVED_MARGINAL_CENTRES_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= DERIVED_MARGINAL_CENTRES_DATE
            and at >= DERIVED_MARGINAL_CENTRES_FROM_UTC)


# Audit 2026-10-13 B3: a football joint (both_over_* / most_* / handicap_* of
# DERIVED_MARGINAL_CENTRES_METRICS) read its two margins from the marginal
# rows only when Superbet quoted BOTH sides' ladders; with one ladder missing
# both sides fell back to the raw sample - no prior, no rating, no opponent
# (Kyoto - Ratchaburi 2026-10-13: handicap_corners Kyoto -2.5 p 0.060,
# most_corners p 0.141). From this switch a side without a quoted ladder gets
# its centre from the same SHEET formula (run_sheet.sample_centre: prior,
# K_CENTRE shrink, W_FOOTBALL_RATING x rating), and a fixture whose metric is
# CROSS_LEAGUE_UNLINKED carries that note on its derived rows, so CONFIDENCE
# refuses them as it refuses the marginal rows. Needs
# DERIVED_MARGINAL_CENTRES on. Measured and pre-registered in
# docs/sofa/evidence/derived_margins_2026-10-13.md. None = off: SHEET
# byte-identical.
DERIVED_SHEET_MARGINS_RULE = "derived_sheet_margins_v1"
DERIVED_SHEET_MARGINS_FROM_UTC: datetime | None = datetime(2026, 10, 21, tzinfo=UTC)


def derived_sheet_margins(date: str, build_at: datetime | None = None) -> bool:
    """Is a derived football joint's missing side priced by the SHEET formula
    (DERIVED_SHEET_MARGINS_FROM_UTC)? The day being built and the build's
    clock, as every other switch."""
    if DERIVED_SHEET_MARGINS_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= DERIVED_SHEET_MARGINS_FROM_UTC.strftime("%Y-%m-%d")
            and at >= DERIVED_SHEET_MARGINS_FROM_UTC)


# The dispersion of football counts fitted on the history instead of the
# sample variance of 8-10 matches (bet.sofa.count_dispersion; track A2,
# docs/sofa/evidence/count_families_2026-10-08.md): variance = mu + alpha mu^2,
# alpha per (market, competition) from config/sofa_count_dispersion.json, the
# negative binomial for every fitted market but shots_total (the normal with
# that variance). Better log-loss out of sample on 52 of 52 football markets.
# It moves p_central, so it goes live only TOGETHER with a refit of the
# football curves replayed with it (calibrate_from_cache --count-dispersion),
# a new comparability epoch - never mid-day, and the operator moves it.
# None = waiting for the operator: the sample variance, byte for byte.
# Read on the day being built and the build clock, like the neighbours; rows
# priced this way carry `dispersion_rule` (COUNT_DISPERSION), so a rebuild
# re-runs SHEET on a sheet of the other rule (rebuild_plan).
COUNT_DISPERSION_DATE = "2026-10-09"
COUNT_DISPERSION_FROM_UTC: datetime | None = datetime(2026, 10, 9, 0, 0, tzinfo=UTC)
COUNT_DISPERSION = "count_dispersion"


def count_dispersion_enabled(date: str, at: datetime | None = None) -> bool:
    if COUNT_DISPERSION_FROM_UTC is None:
        return False
    at = at if at is not None else timeutil.now()
    return date >= COUNT_DISPERSION_DATE and at >= COUNT_DISPERSION_FROM_UTC


def sheet_count_dispersion(rows: Sequence[Mapping[str, Any]]) -> bool:
    """Was every row of a 05_sheet.json priced under COUNT_DISPERSION? An empty
    sheet has nothing to re-price."""
    return all(r.get("dispersion_rule") == COUNT_DISPERSION for r in rows)


# The tennis neighbour table cut by tier x gender (tier, then the pooled table,
# when a cell is thin) and the tier-initialised rating start (V5, feature
# lp_t, config "tier_start"); track A4, docs/sofa/evidence/
# tennis_calibration_2026-10-08.md: games_total -81e-4 [-90, -74] log-loss,
# games_won_for -37e-4, handicap -16e-4, sets -23e-4 against the pooled table
# on 48.6k matches, both test halves agreeing; V5 -10e-4 [-12.6, -8.3] on the
# win probability. It moves p_central, so it goes live only TOGETHER with
# config/tennis_rating.json refitted with V5 and the tennis curves replayed
# with it (calibrate_from_cache --tennis-scoped-table) - a new comparability
# epoch, never mid-day, and the operator moves it. None = waiting for the
# operator: the pooled table, byte for byte. Read on the day being built and
# the build clock; tennis rows priced this way carry `tennis_table_rule`
# (TENNIS_SCOPED_TABLE), so a rebuild re-runs SHEET on a sheet of the other rule.
TENNIS_SCOPED_TABLE_DATE = "2026-10-09"
TENNIS_SCOPED_TABLE_FROM_UTC: datetime | None = datetime(2026, 10, 9, 0, 0, tzinfo=UTC)
TENNIS_SCOPED_TABLE = "scoped_table"


def tennis_scoped_table_enabled(date: str, at: datetime | None = None) -> bool:
    if TENNIS_SCOPED_TABLE_FROM_UTC is None:
        return False
    at = at if at is not None else timeutil.now()
    return date >= TENNIS_SCOPED_TABLE_DATE and at >= TENNIS_SCOPED_TABLE_FROM_UTC


def sheet_tennis_scoped_table(rows: Sequence[Mapping[str, Any]]) -> bool:
    """Was every tennis row of a 05_sheet.json priced under
    TENNIS_SCOPED_TABLE? A sheet without tennis has nothing to re-price."""
    return all(r.get("tennis_table_rule") == TENNIS_SCOPED_TABLE
               for r in rows if r.get("sport") == "tennis")


# The two sides of a football CARDS joint (both_over_ / most_ / handicap_
# cards_points) were priced as independent: config/sofa_side_correlations.json
# holds null for cards_points (99 residual pairs when it was measured). The
# residual correlation measured on 34,027 train matches is +0.126, and pricing
# the joints with it gains log-loss out of sample (test 2026-06-01..10-07):
# +0.0016 [0.0009, 0.0022] both_over, +0.0028 [0.0024, 0.0031] handicap,
# +0.0011 [0.0007, 0.0015] most (docs/sofa/evidence/dependence_goals_
# 2026-10-08.md). It moves p_central of cards joints, so the number lives HERE,
# behind the switch (the config file is not touched: its null is what prints
# today). Goals / corners / shots-on-target correlations are not touched (that
# measurement was inconclusive for them). None = waiting for the operator:
# independent sides, byte for byte. Rows priced this way carry `cards_rule`
# (CARDS_CORRELATION), so a rebuild re-runs SHEET on a sheet of the other rule;
# the staged refit replays it (calibrate_from_cache --cards-correlation).
# the switch's day: a day built before it is never re-priced
CARDS_CORRELATION_DATE = "2026-10-21"
CARDS_CORRELATION_FROM_UTC: datetime | None = datetime(2026, 10, 21, tzinfo=UTC)
CARDS_CORRELATION = "cards_correlation"
CARDS_CORRELATION_RHO = 0.126
CARDS_CORRELATION_BASE = "cards_points"


def cards_correlation_enabled(date: str, at: datetime | None = None) -> bool:
    if CARDS_CORRELATION_FROM_UTC is None:
        return False
    at = at if at is not None else timeutil.now()
    return date >= CARDS_CORRELATION_DATE and at >= CARDS_CORRELATION_FROM_UTC


def sheet_cards_correlation(rows: Sequence[Mapping[str, Any]]) -> bool:
    """Was every row of a 05_sheet.json priced under CARDS_CORRELATION? An empty
    sheet has nothing to re-price."""
    return all(r.get("cards_rule") == CARDS_CORRELATION for r in rows)


# K_CENTRE per football market (bet.sofa.per_market_k): the sample's mean is
# shrunk toward the league prior with K from
# `K_CENTRE.by_market.football[<market>]` in config/sofa_engine_constants.json
# instead of the sport's 15, for the markets listed there (shots and fouls want
# 2-8; docs/sofa/evidence/k_under_dispersion_2026-10-08.md). It moves p_central
# of those markets, so it goes live only TOGETHER with a refit of the football
# curves replayed with it (calibrate_from_cache --per-market-k), a new
# comparability epoch - never mid-day, and the operator moves it. The measured
# gain was taken UNDER the fitted dispersion, so it belongs with
# COUNT_DISPERSION_FROM_UTC (without it the K would be tuned to the wrong
# spread: the operator sets the two together). None = waiting for the
# operator: the sport's K, byte for byte; the file's `by_market` is inert.
# Rows priced this way carry `k_rule` (PER_MARKET_K), so a rebuild re-runs
# SHEET on a sheet of the other rule.
PER_MARKET_K_DATE = "2026-10-09"
PER_MARKET_K_FROM_UTC: datetime | None = datetime(2026, 10, 9, 0, 0, tzinfo=UTC)
PER_MARKET_K = "per_market_k"


def per_market_k_enabled(date: str, at: datetime | None = None) -> bool:
    if PER_MARKET_K_FROM_UTC is None:
        return False
    at = at if at is not None else timeutil.now()
    return date >= PER_MARKET_K_DATE and at >= PER_MARKET_K_FROM_UTC


def sheet_per_market_k(rows: Sequence[Mapping[str, Any]]) -> bool:
    """Was every row of a 05_sheet.json priced under PER_MARKET_K? An empty
    sheet has nothing to re-price."""
    return all(r.get("k_rule") == PER_MARKET_K for r in rows)


# Basketball noise by freshness: games of a side with <= 2 / 3..9 games in the
# last 120 days simulate with every sd times SimParams.bb_fresh_mult (see
# there for the measurement). It moves basketball p, so never mid-day, and the
# basketball curves / line evidence are refitted on it.
BB_FRESHNESS_FROM_UTC: datetime | None = datetime(2026, 10, 7, 14, 5, tzinfo=UTC)


BB_FRESHNESS_DATE = "2026-10-07"


def bb_freshness_enabled(date: str, build_at: datetime | None = None) -> bool:
    """The day being built and the build's clock (the caller of the live
    forecaster asks; ScoreModel.noise_mult itself is pure)."""
    if BB_FRESHNESS_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return date >= BB_FRESHNESS_DATE and at >= BB_FRESHNESS_FROM_UTC


# Plan 2026-10-05_PRODUCTION_GRADE, F1.1 follow-up: a club whose name carries
# "&" (Dagenham & Redbridge, Havant & Waterlooville, H&W Welders) is a subject
# of its own per-team markets when the subject equals one of the listing's own
# participant names (market_mapper.subject_is_combination); before, every "&"
# was read as Superbet's combination operator and the club's goals_for /
# goals_1h_for / goals_2h_for went to unmapped_markets (37 occurrences on
# 2026-09-18..10-05, 0 combinations admitted by the rule on the same names).
# It ADDS rungs, and so legs, to OFFER - so never mid-day: an OFFER (or the
# closing capture) of a day >= AMPERSAND_SUBJECTS_DATE built at or after the
# moment. 10-05 was live when it was written.
AMPERSAND_SUBJECTS_DATE = "2026-10-06"
AMPERSAND_SUBJECTS_FROM_UTC: datetime | None = datetime(2026, 10, 6, tzinfo=UTC)


def ampersand_subjects(date: str, build_at: datetime | None = None) -> bool:
    """May OFFER read a "&" club name as a subject (AMPERSAND_SUBJECTS_FROM_UTC)?"""
    if AMPERSAND_SUBJECTS_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return date >= AMPERSAND_SUBJECTS_DATE and at >= AMPERSAND_SUBJECTS_FROM_UTC


# K13b (plan 2026-10-05_PRODUCTION_GRADE section 7, the verifier's open
# suspicion of 10-05): where a market's own curve has a hole at p - no market,
# direction or thin bucket there, but measured buckets elsewhere - the pool
# that stands in may not claim more than the market's own nearest bucket below
# p (confidence.Calibration.cap_pool_by_neighbour). Moss - Kongsvinger
# goals_1h_total O0.5 printed 0.815 off pooled:football at p 0.803 against its
# own 0.709 / 0.731 below. Measured before it was set (scripts/sofa/
# measure_pool_holes.py, settled rows p >= 0.70, 95% bootstrap over matches):
# the rows the cap moves are all live (57 rows, 48 matches; goals_1h_total
# OVER 0.80-0.825 and goals_2h_for OVER 0.70-0.75) - the pool claimed 0.775,
# they realised 0.649, -12.6 pp [-24.1, -1.2]; capped they claim 0.618,
# +3.1 pp [-8.4, +14.4]. Thin (two cells), but the interval excludes 0. A
# market with NO bucket of its own read off the pool over-claims too (-14.1
# pp [-21.0, -7.2], 290 rows) - not touched by this rule. It changes
# which legs print, so never mid-day: CONFIDENCE of a day >= POOL_NEIGHBOUR_
# CAP_DATE built at or after the moment. 10-05 was live when it was written.
POOL_NEIGHBOUR_CAP_DATE = "2026-10-06"
POOL_NEIGHBOUR_CAP_FROM_UTC: datetime | None = datetime(2026, 10, 6, tzinfo=UTC)


def pool_neighbour_cap(date: str, build_at: datetime | None = None) -> bool:
    """Does CONFIDENCE cap a pool's read of a hole by the market's own
    nearest bucket below (POOL_NEIGHBOUR_CAP_FROM_UTC)?"""
    if POOL_NEIGHBOUR_CAP_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return date >= POOL_NEIGHBOUR_CAP_DATE and at >= POOL_NEIGHBOUR_CAP_FROM_UTC


# 2026-10-05 night (docs/sofa/evidence/national_samples_2026-10-05.md): a
# national team plays ~10 matches a year, so a ten-match sample always reaches
# past MAX_BUILDER_SAMPLE_AGE_DAYS (180) and SAMPLE_CROSSES_SEASON refused 157
# national-team legs on 10-05 that had passed every price and curve gate (all
# 8 Nations League fixtures; France only through its World Cup). Measured on
# 21,209 competitive national-team matches: trimming the sample to 180 days
# makes goals_for WORSE (log-loss +0.022 [+0.018, +0.027]) and the cache
# calibration at p >= 0.70 is flat by sample age (+0.005 / +0.004 / +0.001 for
# 180-400 / 400-730 / >730 days). From this moment a fixture of two national
# teams is judged by the sample's count (THIN_SAMPLE_FOR_BUILDER) and its age
# is shown on the leg (NATIONAL_SAMPLE_AGE), never gated. Changes which legs
# print, so never mid-day: a day >= NATIONAL_SAMPLE_AGE_DATE built at or after
# the moment. 10-05 was live when it was written.
NATIONAL_SAMPLE_AGE_DATE = "2026-10-06"
NATIONAL_SAMPLE_AGE_FROM_UTC: datetime | None = datetime(2026, 10, 6, tzinfo=UTC)


def national_sample_by_count(date: str, build_at: datetime | None = None) -> bool:
    """Is a national-team fixture's sample judged by count, not age
    (NATIONAL_SAMPLE_AGE_FROM_UTC)?"""
    if NATIONAL_SAMPLE_AGE_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return date >= NATIONAL_SAMPLE_AGE_DATE and at >= NATIONAL_SAMPLE_AGE_FROM_UTC


# 2026-10-07 (hockey analyst, confirmed by the verifier from data/sofa.db):
# football_rating linked a pair when both sides had LINK_MIN_MATCHES in a
# competition that was the league (domain) of EITHER side. A promoted or
# relegated side keeps its old league as its domain for months, so three
# games into the new league it was LINKED with its new opponents and its
# old-league ratios were read 1:1, with no league strength - Visby/Roma
# (Ettan -> HockeyAllsvenskan), Leksand (SHL -> HockeyAllsvenskan), AZ
# Havirov (2. Liga -> Maxa Liga); 10 hockey legs of 10-07 removed by NO_BET
# reads. From this moment a pair is LINKED only when both domains belong to
# one competition and both sides played LINK_MIN_MATCHES in it; anything
# else is LINKED_BY_STRENGTH or UNLINKED (football_rating.RatingBook._linked).
# It moves every rating built on the history (SHEET's football rating, the
# measured sports' score model), so never mid-day.
#
# Read on the wall clock, like MODEL_FIXES_FROM_UTC: the refit's as-of
# replays (SOFA_NOW in the past) must rate with the rule the live day uses.
# A caller that knows the day it builds passes it, so a rebuild of a day
# before LINK_SHARED_LEAGUE_DATE keeps the rule it printed under.
#
# Moved to 2026-10-07 06:45Z by the operator ("nic nie postawiłem" - nothing
# of 10-07 was staked): after the day's last build (11_coupon.json 05:05Z),
# before the rebuild that re-rated it. 10-07 is one build under the new rule;
# the morning prints before 06:45Z were the old rule.
LINK_SHARED_LEAGUE_DATE = "2026-10-07"
LINK_SHARED_LEAGUE_FROM_UTC: datetime | None = datetime(
    2026, 10, 7, 6, 45, tzinfo=UTC)


LINK_SHARED_LEAGUE = "shared_league"


def link_shared_league(date: str | None = None, at: datetime | None = None) -> bool:
    """Does the rating link a pair only through a league both domains share
    (LINK_SHARED_LEAGUE_FROM_UTC)? `date` - the day being built, when known."""
    if LINK_SHARED_LEAGUE_FROM_UTC is None:
        return False
    if date is not None and date < LINK_SHARED_LEAGUE_DATE:
        return False
    return (at if at is not None else datetime.now(UTC)) >= LINK_SHARED_LEAGUE_FROM_UTC


def sheet_link_shared(rows: list[Mapping[str, Any]]) -> bool:
    """Was every row of a 05_sheet.json rated under the shared-league link
    rule? An empty sheet has nothing to re-rate."""
    return all(r.get("link_rule") == LINK_SHARED_LEAGUE for r in rows)


# Operator, 2026-10-07: sofa's job is to tell a good 1.20 from a bad 1.20 by
# the statistics, for every sport alike, and nothing that could win is cut by
# name. Measured that day (docs/sofa/evidence/discrimination_within_price_
# 2026-10-07.md): inside one price band, the top third of the stats-only p
# realised more than the bottom third - football +14.4 pp [+8.2, +19.6]
# (10-05..06), basketball +9.1 pp [+1.0, +15.4] (handicap +20.7) on
# 09-20..10-06 Superbet lines - while basketball sat NOT_CALIBRATED. From the
# moment below (bet.sofa.line_evidence): no market is refused by name
# (refused_markets, admitted_* lists, DERIVED_NOT_CALIBRATABLE, a sport key
# outside `admitted`); every key is read through its own settled Superbet
# lines instead - a curve they show overstating is lowered by the measured
# offset (never raised), and a key without a history curve reads the Wilson
# lower bound of its own settled lines (NO_LINE_EVIDENCE until it has them).
# A p-only curve overstated the long prices (basketball handicap p 0.70-0.80
# realised 0.79 at 1.30-1.60 and 0.62 at 1.60-2.20); the operator chose
# "krzywa per pasmo kursu" the same day: the price band may lower a confidence
# where its settled lines measured below it, never raise one. Planned for the
# next day's 00:00Z; moved by the operator to 2026-10-07 10:55Z ("dzisiejszy
# kupon przebudowany z nowymi zasadami"), as LINK_SHARED_LEAGUE was that
# morning: 10-07 is a mixed day - its prints before 10:55Z are the old rule,
# the rebuild after it the new one; legs locked before stay as printed.
LINE_EVIDENCE_DATE = "2026-10-07"
LINE_EVIDENCE_FROM_UTC: datetime | None = datetime(2026, 10, 7, 10, 55, tzinfo=UTC)


# Line evidence, second rules (operator, 2026-10-07, after the audit of the
# 10-07 evening: docs/sofa/history/AUDYT_MODELI_2026-10-07.md). Planned for the
# next day's 00:00Z; moved by the operator to the moment below ("przelicz
# dzisiejszy kupon") - 10-07 is a mixed day again. From then each of them
# only ever LOWERS a confidence or refuses a leg that guessed (except the CS2
# pooled offset, which the operator chose to fit without the one key that
# dominates it - that one can raise the other CS2 keys):
#   * a price-band cell widens downward INSIDE its band before the sport's or
#     the all-band cell stands in (a 12-line cell at p >= 0.80 and 2.20+ must
#     not fall back to the cheap band's lines);
#   * a key with no curve needs MIN_EVIDENCE_GAMES games in the bucket and
#     reads the Wilson bound of its lines divided by the sport's measured
#     design effect (lines of one game are not independent);
#   * the sport's pooled offset is measured without a key that holds more
#     than CONCENTRATION_MAX of its printable lines (that key keeps the full
#     pool);
#   * a CS2 fixture with no best_of is not guessed as best-of-3.
LINE_EVIDENCE_V2_DATE = "2026-10-07"
LINE_EVIDENCE_V2_FROM_UTC: datetime | None = datetime(2026, 10, 7, 13, 42, tzinfo=UTC)


def line_evidence_v2(date: str, build_at: datetime | None = None) -> bool:
    """Do the second line-evidence rules apply (LINE_EVIDENCE_V2_FROM_UTC)?"""
    if LINE_EVIDENCE_V2_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return date >= LINE_EVIDENCE_V2_DATE and at >= LINE_EVIDENCE_V2_FROM_UTC


# A derived joint (handicap_ / most_ / both_over_) reads its HISTORY curve -
# replayed by calibrate_from_cache (the tennis rating's handicap_games /
# most_games; football `--derived`) and fitted by fit_confidence - and its
# settled Superbet lines only LOWER it, as for every other key. Until then a
# derived joint has no curve and line evidence is its only source (a stand-in,
# NO_LINE_EVIDENCE below 50 lines a bucket). Off: it needs the refit that
# carries the replayed joints, measured first (out of sample, against the
# stand-in), and the operator's day. fit_line_evidence --derived-curves fits
# the offsets against the same curve.
# the switch's day: a day built before it is never re-priced
DERIVED_CURVES_DATE = "2026-10-21"
DERIVED_CURVES_FROM_UTC: datetime | None = datetime(2026, 10, 21, tzinfo=UTC)


def derived_curves(date: str, build_at: datetime | None = None) -> bool:
    if DERIVED_CURVES_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return date >= DERIVED_CURVES_DATE and at >= DERIVED_CURVES_FROM_UTC


# A derived football joint (both_over_ / most_ / handicap_) has no sample of
# its own market in SAMPLES, so CONFIDENCE's shape gates read an empty list and
# THIN_SAMPLE_FOR_BUILDER refused every such row (0 derived legs 10-09..10-13,
# model-state b). From this switch the sample gate of a football derived row
# reads its two sides' marginal samples (`derived_side_metric(base)`, side_a and
# side_b): each side needs MIN_BUILDER_SAMPLE values, the age gates read both
# sides; LINE_BEYOND_SAMPLE / MODE_LOSES / MODEL_ABOVE_OWN_SAMPLE do not apply
# (a side's count does not measure the joint's line) and the leg never joins a
# builder. Operator 2026-10-21 ("all markets must be taken into account"); on
# together with DERIVED_CURVES / CARDS_CORRELATION / DERIVED_SHEET_MARGINS.
# Rows lifted this way carry DERIVED_SAMPLE_MARKER.
DERIVED_SAMPLE_GATES_FROM_UTC: datetime | None = datetime(2026, 10, 21, tzinfo=UTC)
DERIVED_SAMPLE_MARKER = "derived_side_samples"


def derived_sample_gates(date: str, build_at: datetime | None = None) -> bool:
    """Does a football derived row's sample gate read its two sides'
    marginal samples (DERIVED_SAMPLE_GATES_FROM_UTC)?"""
    if DERIVED_SAMPLE_GATES_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= DERIVED_SAMPLE_GATES_FROM_UTC.strftime("%Y-%m-%d")
            and at >= DERIVED_SAMPLE_GATES_FROM_UTC)


def line_evidence(date: str, build_at: datetime | None = None) -> bool:
    """Is a key read through its settled Superbet lines rather than refused
    by name (LINE_EVIDENCE_FROM_UTC)?"""
    if LINE_EVIDENCE_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return date >= LINE_EVIDENCE_DATE and at >= LINE_EVIDENCE_FROM_UTC


# Peer choice and stakes (operator, 2026-10-08, after the 10-07 slip lost on
# Corinthians cards under 4.5 while the total cards over 3.5 stood beside it at
# a near price: "jak masz dwie nogi po 1.2 to musisz mi zaproponować tę która
# ma większą pewność wejścia"). Planned for the next day's 00:00Z; moved by
# the operator to the moment below ("przebudowa dzisiejszego kuponu z nowymi
# zasadami") - 10-08 is a mixed day: a coupon built before it carries no
# `peer`, one built after it does. Annotation only (bet.sofa.peer_choice,
# bet.sofa.stakes): no leg is added, removed or re-ranked and no confidence
# moves, so what prints is the same either way.
PEER_CHOICE_DATE = "2026-10-08"
PEER_CHOICE_FROM_UTC: datetime | None = datetime(2026, 10, 8, 8, 10, tzinfo=UTC)


def peer_choice(date: str, build_at: datetime | None = None) -> bool:
    """Does the coupon say which of two near-priced legs of a match is the
    surer one, and which fixtures are played for something (PEER_CHOICE_FROM_UTC)?"""
    if PEER_CHOICE_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return date >= PEER_CHOICE_DATE and at >= PEER_CHOICE_FROM_UTC


# A leg whose confidence sits more than price_gap.GAP above 1/odds carries a
# flag saying that such legs realised below their confidence, about at their
# price (operator, 2026-10-12, after the 10-11 slips; bet.sofa.price_gap).
# Annotation only: no leg is added, removed or re-ranked and no confidence
# moves. Moved by the operator to the moment below ("przebudowanie
# dzisiejszego kuponu z tymi flagami") - 10-12 is a mixed day: a coupon built
# before it carries no `price_gap`, one built after it does; what prints is
# the same either way.
PRICE_GAP_FLAG_DATE = "2026-10-12"
PRICE_GAP_FLAG_FROM_UTC: datetime | None = datetime(2026, 10, 12, 11, 51, tzinfo=UTC)


def price_gap_flag(date: str, build_at: datetime | None = None) -> bool:
    """Does the coupon flag the legs whose confidence is above their price
    (PRICE_GAP_FLAG_FROM_UTC)?"""
    if PRICE_GAP_FLAG_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return date >= PRICE_GAP_FLAG_DATE and at >= PRICE_GAP_FLAG_FROM_UTC


# CS2 legs carry the same flag (operator, 2026-10-20; price_gap.LATER_SPORTS,
# measured on settled Superbet CS2 lines by scripts/sofa/measure_cs2_price_gap.py).
# Annotation only, as above, but a flagged leg's confidence is capped in the
# analysts' read order (confidence.read_value), which changes which legs a read
# may remove - so next day 00:00Z.
CS2_PRICE_GAP_DATE = "2026-10-21"
CS2_PRICE_GAP_FROM_UTC: datetime | None = datetime(2026, 10, 21, 0, 0, tzinfo=UTC)


def price_gap_sports(date: str, build_at: datetime | None = None) -> frozenset[str]:
    """The price_gap.LATER_SPORTS the build flags (CS2_PRICE_GAP_FROM_UTC)."""
    if CS2_PRICE_GAP_FROM_UTC is None:
        return frozenset()
    at = build_at if build_at is not None else timeutil.now()
    if date >= CS2_PRICE_GAP_DATE and at >= CS2_PRICE_GAP_FROM_UTC:
        return frozenset({"cs2"})
    return frozenset()


# The analysts' read set counts EVENTS, not positions (operator, 2026-10-08:
# "30 analizowanych wydarzeń a nie 30 rynków - 30 wydarzeń może mieć 150
# rynków"): from the build below, `confidence.legs_requiring_read` takes every
# unlocked leg of the first READ_REQUIRED_EVENTS matches of the coupon (its own
# order: the match of the best leg first), not the first 30 positions. Every leg
# still prints. Default next day 00:00Z (changes which legs C3 asks a read on,
# and so which a read may remove); the build records its rule in the artifact
# (`read_unit`), so a rebuild and the audits read one rule.
READ_EVENTS_DATE = "2026-10-09"
READ_EVENTS_FROM_UTC: datetime | None = datetime(2026, 10, 9, 0, 0, tzinfo=UTC)


def read_by_event(date: str, build_at: datetime | None = None) -> bool:
    """Does the read set count events rather than positions (READ_EVENTS_FROM_UTC)?"""
    if READ_EVENTS_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return date >= READ_EVENTS_DATE and at >= READ_EVENTS_FROM_UTC


# The analysts' 30 matches are the matches of the best VALUE, not the best
# confidence (operator, 2026-10-13: "takie które mają i prawdopodobieństwo i
# cenę najlepszą z danego dnia"): `confidence.legs_requiring_read` ranks the
# matches by their best unlocked leg's confidence x odds, a football / tennis
# leg's confidence capped at 1/odds + price_gap.GAP (such legs realised about at
# their price, bet.sofa.price_gap). Still 30 matches, every unlocked leg of
# each; every leg still prints. Changes which legs a read may remove, so next
# day 00:00Z; the build records the rule in the artifact (`read_order`).
READ_BY_VALUE_DATE = "2026-10-14"
READ_BY_VALUE_FROM_UTC: datetime | None = datetime(2026, 10, 14, 0, 0, tzinfo=UTC)


def read_by_value(date: str, build_at: datetime | None = None) -> bool:
    """Are the read set's matches ranked by value (READ_BY_VALUE_FROM_UTC)?"""
    if READ_BY_VALUE_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return date >= READ_BY_VALUE_DATE and at >= READ_BY_VALUE_FROM_UTC


# A footballer Superbet writes under his full registered name ("Andrade,
# Matheus Araujo") and Sofascore under the name he plays by ("Matheus
# Araujo") scored under match_player's 85 and had no sample: 346 of the 680
# NO_ENTITY_FOUND players of 2026-10-08..10-10 were such near names, 263 of
# them priced at <= 1.60. From this moment SAMPLES falls back to
# players.match_player_by_tokens for a player match_player found in no squad
# (evidence and the identity check: docs/sofa/evidence/
# player_name_tokens_2026-10-11.md). It ADDS player samples, so rows and legs:
# never mid-day - a SAMPLES of a day >= PLAYER_NAME_TOKENS_DATE built at or
# after the moment. SETTLE grades the sample's own matched name whenever the
# sample says "tokens", whatever the day.
PLAYER_NAME_TOKENS_DATE = "2026-10-12"
PLAYER_NAME_TOKENS_FROM_UTC: datetime | None = datetime(2026, 10, 12, 0, 0, tzinfo=UTC)


def player_name_tokens(date: str, build_at: datetime | None = None) -> bool:
    """Does SAMPLES fall back to the token name match (PLAYER_NAME_TOKENS_FROM_UTC)?"""
    if PLAYER_NAME_TOKENS_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return date >= PLAYER_NAME_TOKENS_DATE and at >= PLAYER_NAME_TOKENS_FROM_UTC


# Superbet voids a footballer's player market unless he STARTS (operator,
# 2026-10-11; Walemark 2026-10-10: on for 30', 2 shots on target, "Zwrot").
# The bet is "given that he starts", so from this moment a player sample holds
# his starts only (samples.build_player_samples `starts_only`); SETTLE voids a
# bench appearance (PLAYER_NOT_STARTED) whatever the day - a correctness fix.
# Changes the forecasts of player rows: never mid-day. Measured before it was
# set (docs/sofa/evidence/player_starts_2026-10-11.md, history replay, 492,384
# starters' OVER rows of 4,114 matches): bucket-calibrated out of sample the
# starts sample beats the all-appearances one, log-loss -0.0027 [-0.0030,
# -0.0024], on 5 of 6 markets (assists level). The curves a day >= the moment
# reads are refitted on the same replay (config/
# sofa_confidence_calibration.next.json, effective_from the same moment).
PLAYER_STARTS_ONLY_FROM_UTC: datetime | None = datetime(2026, 10, 12, 0, 0, tzinfo=UTC)


def player_starts_only(date: str, build_at: datetime | None = None) -> bool:
    """Is a player sample his starts only (PLAYER_STARTS_ONLY_FROM_UTC)?"""
    if PLAYER_STARTS_ONLY_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= PLAYER_STARTS_ONLY_FROM_UTC.strftime("%Y-%m-%d")
            and at >= PLAYER_STARTS_ONLY_FROM_UTC)


# Superbet quotes a footballer's props on the OVER side only, so the ladder
# has no overround and confidence.single_is_fairly_priced (overround <=
# MAX_OVERROUND) refused every football player leg as a single, unnamed: the 5
# player legs of 2026-10-09..10-10 that passed every confidence gate never
# printed. With this switch a single with no overround because its market is
# one-sided prints when its confidence comes from a history curve with at
# least ONE_SIDED_MIN_CURVE_N rows (measure_calibration's PASS size); the
# confidence x odds and every other gate still apply, and the leg is marked
# one_sided_market. Switched on by the operator (2026-10-11) from the next
# day, after the re-measurement (docs/sofa/evidence/player_starts_2026-10-11.md:
# 49 would-print legs of 10-05..10-10, confidence 0.794, realised 0.755, ROI
# -10.3% [-27, +4] against -3.0% for the team legs at the same gates).
ONE_SIDED_SINGLES_FROM_UTC: datetime | None = datetime(2026, 10, 12, 0, 0, tzinfo=UTC)
ONE_SIDED_MIN_CURVE_N = 300


def one_sided_singles(date: str, build_at: datetime | None = None) -> bool:
    """May a one-sided market's leg print as a single (ONE_SIDED_SINGLES_FROM_UTC)?"""
    if ONE_SIDED_SINGLES_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= ONE_SIDED_SINGLES_FROM_UTC.strftime("%Y-%m-%d")
            and at >= ONE_SIDED_SINGLES_FROM_UTC)


# CONFIDENCE's sample-shape gates (LINE_BEYOND_SAMPLE, MODE_LOSES and
# THIN_SAMPLE_FOR_BUILDER's 10 values) were written for team samples. A
# footballer's sample is his starts in his team's last 10 matches
# (PLAYER_STARTS_ONLY), 5-10 values, so the 10-value gate admitted only a
# player who started all ten (2026-10-15: of the 57 player legs that cleared
# the curve, the line evidence and x at the sheet's price these gates
# refused 54; 5 printed, 2 clearing x only at a fresh price). The
# lineup-market player curves are fitted on the replay with a
# sample of PLAYER_MIN_SAMPLE starts and no shape gate. Measured 2026-10-16
# (docs/sofa/evidence/player_sample_gates_2026-10-16.md,
# player_line_evidence_2026-10-16.md): on the history (OVER rows at
# confidence >= 0.70) the refused groups realise on their curve (+0.5 ..
# +1.5 pp), together ~0.4 pp below the passing ones (LINE_BEYOND -0.9 pp
# [-1.8, +0.1], 5 starts -1.9 pp [-2.9, -0.8] vs OVER PASS); on Superbet's
# lines 10-12..10-15, with the line evidence,
# the gate-free legs read -5.9 pp [-15.9, +4.5] under their confidence, ROI
# -11.7% [-23.8, +1.2] (55 legs / 37 matches, the curve in sample). With the
# switch a football row on one of confidence.PLAYER_SHAPE_GATE_MARKETS (not
# the /shotmap shot-detail markets, whose curves come from their own
# estimator, nor interceptions - neither measured) needs only
# PLAYER_MIN_SAMPLE values; a leg a shape gate would have refused carries the
# first such gate (confidence.shape_gate_refusal's order) under
# PLAYER_SAMPLE_MARKER and never joins a builder (the measurement was of
# singles); the sample's age, the curve, the line evidence, the floor and x
# still apply. Operator 2026-10-16 ("włączymy od jutra"): from the next day.
PLAYER_SAMPLE_GATES_FROM_UTC: datetime | None = datetime(
    2026, 10, 17, 0, 0, tzinfo=UTC)
PLAYER_MIN_SAMPLE = 5  # config.min_sample, the replay's player sample floor
PLAYER_SAMPLE_MARKER = "player_sample_rule"


def player_sample_gates_off(date: str, build_at: datetime | None = None) -> bool:
    """Does a football player row skip the sample-shape gates
    (PLAYER_SAMPLE_GATES_FROM_UTC)? Judged on the day built and the build clock."""
    if PLAYER_SAMPLE_GATES_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= PLAYER_SAMPLE_GATES_FROM_UTC.strftime("%Y-%m-%d")
            and at >= PLAYER_SAMPLE_GATES_FROM_UTC)


# Night plan 2026-10-12 C1: OFFER reads the MAPPABLE Superbet families of
# bet.sofa.market_coverage - a statistic sofa already samples, a name nobody
# mapped (903 occurrences on 2026-10-12): "<club> strzeli gola" and its halves
# (goals_for / goals_1h_for / goals_2h_for at 0.5, tak = OVER, nie = UNDER),
# "Zostanie rozegrany N. set" (sets_total at N - 0.5), "<half> - obie
# drużyny strzelą" (both_over_goals_1h / _2h), "[<half> -] każda z drużyn
# powyżej X obronionych strzałów przez bramkarza" (both_over_saves / _1h),
# "N. połowa - rzuty rożne - handicap" (handicap_corners_1h / _2h) and
# "N. set - handicap gemy" (handicap_games_won_set1 / _set2)
# (market_mapper.classify_mappable_family). A yes/no answer to a rung a ladder
# already quotes never adds a second rung: the ladder's own rung is kept and
# the answer only fills a rung the ladder does not quote (offer.OfferFetcher).
# It ADDS rungs, and so rows and possibly legs (the goals_for / sets_total
# ones read existing curves), so never mid-day; None until the operator sets
# it. With None OFFER is byte-identical to before (test_mappable_families).
# Switched on by the operator 2026-10-13 ("Wszystkie rynki włączone"); E2E on
# 10-13's samples clean (docs/sofa/evidence/mappable_e2e_2026-10-14.md; the
# bridge leg of the E2E was refused by Sofascore - not tested).
MAPPABLE_FAMILIES_FROM_UTC: datetime | None = datetime(
    2026, 10, 14, 0, 0, tzinfo=UTC)


def mappable_families(date: str, build_at: datetime | None = None) -> bool:
    """Does OFFER read the MAPPABLE families (MAPPABLE_FAMILIES_FROM_UTC)?"""
    if MAPPABLE_FAMILIES_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= MAPPABLE_FAMILIES_FROM_UTC.strftime("%Y-%m-%d")
            and at >= MAPPABLE_FAMILIES_FROM_UTC)


def require_k_with_dispersion(date: str, at: datetime | None = None) -> None:
    """PER_MARKET_K and COUNT_DISPERSION were fitted jointly (the K gain was
    measured under the fitted dispersion, which itself was fitted around K=15
    centres): exactly one of them on for a day would price a model nobody
    measured. SHEET calls this before it prices; it raises (rc 2) rather than
    mix them."""
    at = at if at is not None else timeutil.now()
    dispersion = count_dispersion_enabled(date, at)
    k = per_market_k_enabled(date, at)
    if dispersion != k:
        raise ValueError(
            f"{'COUNT_DISPERSION' if dispersion else 'PER_MARKET_K'} is on for "
            f"{date} but {'PER_MARKET_K' if dispersion else 'COUNT_DISPERSION'} "
            "is not: the two were fitted jointly and go live together "
            "(epochs.COUNT_DISPERSION_FROM_UTC / PER_MARKET_K_FROM_UTC)")


# Audit 2026-10-13 A2 (operator O1): a competition with fewer than
# football_rating.MIN_LEAGUE_MATCHES matches had the mean of EVERY league as
# its rate - NBA Preseason (a friendly, so out of the history) was priced at
# 82.8 points a side against NBA's 118 / 112, and the printed 10-10
# Raptors - Clippers total UNDER 222.5 carried forecast_p 0.9998. From this
# moment (a forecast only; the rating's own updates are unchanged):
#   * SPORT_CONFIDENCE refuses a hockey / basketball / volleyball game whose
#     competition comparability.is_friendly_event calls a friendly or a
#     pre-season (FRIENDLY_FIXTURE - football's rule, run_confidence);
#   * a score-model game in a competition below MIN_LEAGUE_MATCHES has no
#     model p (NO_LEAGUE_RATE), never the all-league mean;
# No fallback to the teams' home league (operator O1). Changes what prints,
# so a day >= the moment's date built at or after the moment.
# Football has its own switch (FOOTBALL_LEAGUE_RATE_RULE_FROM_UTC below).
# Switched on by the operator's decision O1 (2026-10-13), a correctness fix -
# NOT by a measured gain: on Superbet's settled lines of 09-29..10-12 the
# games it refuses held 17 would-print lines in 16 games (hockey 0), too few
# to tell (basketball -3.1 pp [-38, +23], volleyball +11.3 pp [-13, +24];
# docs/sofa/evidence/league_rate_rule_2026-10-13.md).
LEAGUE_RATE_RULE = "league_rate_strict_v1"
LEAGUE_RATE_RULE_FROM_UTC: datetime | None = datetime(
    2026, 10, 14, 0, 0, tzinfo=UTC)


def league_rate_rule(date: str | None = None, build_at: datetime | None = None) -> bool:
    """Is a thin competition's rate withheld and a friendly sport game refused
    (LEAGUE_RATE_RULE_FROM_UTC)? `date` None: the wall clock alone (a
    history replay of the day it is building passes the day)."""
    if LEAGUE_RATE_RULE_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    if date is not None and date < LEAGUE_RATE_RULE_FROM_UTC.strftime("%Y-%m-%d"):
        return False
    return at >= LEAGUE_RATE_RULE_FROM_UTC


# Audit 2026-10-13 A4: a key with no curve reads the Wilson bound of its own
# settled lines divided by a design effect (lines of one game are not
# independent). Until this switch the divisor is the SPORT's (football 2.437
# on 10-13) even in buckets where every game gives one line - both_over_corners
# OVER p 0.75-0.80 realised 66/78 = 0.846 and read 0.6825. From this moment
# the bucket's own design effect (line_evidence.design_effect on the bucket's
# lines, written by the fit as `deff`; an older file without it reads the
# sport's). Raises some confidences, so it changes what prints: a day >= the
# date built at or after the moment. Switched on under the audit's standing
# go (O5): walk-forward 10-07..10-12, every sport's no-curve keys, log-loss of
# the read confidence -0.0351 [-0.0409, -0.0292] (1,898 lines / 682 games;
# docs/sofa/evidence/bucket_design_effect_2026-10-13.md).
BUCKET_DESIGN_EFFECT_FROM_UTC: datetime | None = datetime(
    2026, 10, 14, 0, 0, tzinfo=UTC)


def bucket_design_effect(date: str, build_at: datetime | None = None) -> bool:
    """Does a no-curve key read its bucket's own design effect
    (BUCKET_DESIGN_EFFECT_FROM_UTC)?"""
    if BUCKET_DESIGN_EFFECT_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= BUCKET_DESIGN_EFFECT_FROM_UTC.strftime("%Y-%m-%d")
            and at >= BUCKET_DESIGN_EFFECT_FROM_UTC)


# A2's football half: a football row of a competition below
# MIN_LEAGUE_MATCHES gets no rating centre (note NO_LEAGUE_RATE) and is priced
# from its sample. MEASURED AND NOT SWITCHED ON (audit implementation
# 2026-10-13, docs/sofa/evidence/league_rate_rule_2026-10-13.md): one step
# ahead on the history 2025-08-01..2026-10-12, in thin competitions the old
# centre (0.5 rating at the all-league rate + 0.5 own last ten) beat the
# sample alone - squared error per side -0.58 [-0.62, -0.54] in its favour,
# 65,550 sides, every rated metric the same sign. Stays None.
FOOTBALL_LEAGUE_RATE_RULE_FROM_UTC: datetime | None = None


def football_league_rate_rule(date: str, build_at: datetime | None = None) -> bool:
    """Does a thin competition's football row lose its rating centre
    (FOOTBALL_LEAGUE_RATE_RULE_FROM_UTC)?"""
    if FOOTBALL_LEAGUE_RATE_RULE_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= FOOTBALL_LEAGUE_RATE_RULE_FROM_UTC.strftime("%Y-%m-%d")
            and at >= FOOTBALL_LEAGUE_RATE_RULE_FROM_UTC)


# Audit 2026-10-13 A1: a competition whose season falls into regional groups
# (football_rating.assign_league_units) gets new league units, and each unit's
# league strength started from 0: J1 2026's units read 0.168 / 0.108 against
# the whole J1's 0.419 (2026-10-13: Cong An 2.10 - Kashima 0.97 goals, 1.63 -
# 1.24 with J1's strength). From this moment a unit starts from its
# competition's strength (RatingBook.unit_strength_from_parent). It changes the
# rating's book and so football centres: a day >= the date, built at or after
# the moment. MEASURED AND NOT SWITCHED ON (2026-10-13, one step ahead,
# goals 06-01..10-12, cross-league matches with a regional unit: Poisson
# log-loss -0.0010 [-0.0029, +0.0008] per match, 7,724 matches;
# docs/sofa/evidence/unit_strength_2026-10-13.md).
UNIT_STRENGTH_FROM_PARENT_FROM_UTC: datetime | None = None


def unit_strength_from_parent(date: str, build_at: datetime | None = None) -> bool:
    """Does a regional league unit start from its competition's strength
    (UNIT_STRENGTH_FROM_PARENT_FROM_UTC)?"""
    if UNIT_STRENGTH_FROM_PARENT_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= UNIT_STRENGTH_FROM_PARENT_FROM_UTC.strftime("%Y-%m-%d")
            and at >= UNIT_STRENGTH_FROM_PARENT_FROM_UTC)


# Audit 2026-10-13 B10: a CS2 team's rounds on a map ("X - liczba rund na N.
# mapie") were its own last maps' frequency shrunk to the base rate - no
# opponent, though a team reaches 13 rounds only by winning the map or in
# overtime. From this moment the line is priced from the map's score
# distribution (cs2_engine.team_rounds_from_race, the round race the round
# handicap already uses) in SPORT_CONFIDENCE, at CS2_SETTLE (model_p, the line
# evidence's input) and in the history replay of a fit for a day >= it. It
# changes p, so it needs the CS2 curve refitted on the same estimator.
# Switched on under the audit's standing go (O5 / O6): walk-forward on the
# history 2025-10-13..2026-10-13, 316,024 lines / 8,738 series, log-loss
# -0.0213 [-0.0237, -0.0188]; the CS2 curve refitted on the same estimator
# (copy of the DB, --before 2026-10-13) is staged in
# config/sofa_sport_confidence_calibration.next.json from 2026-10-14
# (docs/sofa/evidence/cs2_team_rounds_race_2026-10-13.md).
# Moved by the operator (2026-10-13) from 2026-10-14 00:00Z to the refit's
# rebuild of 10-13, with the staged CS2 curve: a mixed day.
CS2_TEAM_ROUNDS_RACE_FROM_UTC: datetime | None = datetime(
    2026, 10, 13, 18, 10, tzinfo=UTC)


def cs2_team_rounds_race(date: str, build_at: datetime | None = None) -> bool:
    """Is a CS2 team-rounds line priced from the round race
    (CS2_TEAM_ROUNDS_RACE_FROM_UTC)?"""
    if CS2_TEAM_ROUNDS_RACE_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= CS2_TEAM_ROUNDS_RACE_FROM_UTC.strftime("%Y-%m-%d")
            and at >= CS2_TEAM_ROUNDS_RACE_FROM_UTC)


# Operator 2026-10-14 ~18:55Z: CS2 series rounds - "Liczba rund (z dogrywką)"
# (rounds_total), "Handicap rund (z dogrywką)" (rounds_handicap), "<team>
# liczba rund (z dogrywką)" (team_rounds) over every map played. From this
# moment cs2_engine.model_probability prices them (series_rounds_side_p: the
# maps each team wins from series_distribution_mixed, each map's rounds from
# the round race given its winner) in SPORT_CONFIDENCE (the families allowed),
# at CS2_SETTLE (model_p, the line evidence's input) and in a fit's history
# replay for a day >= it. The CS2 snapshot read and graded them before
# (cs2.parse_line / actual_value): off is byte-identical. Gate (operator, one
# sided: holdout 2026-09-01..10-13 printable n >= 300, realised - curve >=
# -0.02, sport admission): rounds_handicap|TEAM, rounds_total|OVER and
# team_rounds|OVER pass; their curves are STAGED, not installed
# (data/refit_new_markets_2026-10-15/cs2_series_rounds/), so with the switch
# alone a leg reads its own settled Superbet lines (NO_LINE_EVIDENCE until a
# bucket holds 50). At Superbet's own lines (CS2_SETTLE 2026-09-28..10-13,
# 212 series) the passing keys' curve reached 0.70 on 21 sides / 19 series,
# which realised 0.33 at a curve of 0.74 - install only on the operator's
# go: docs/sofa/evidence/cs2_series_rounds_2026-10-15.md.
CS2_SERIES_ROUNDS_FROM_UTC: datetime | None = datetime(2026, 10, 15, 0, 0, tzinfo=UTC)


def cs2_series_rounds(date: str, build_at: datetime | None = None) -> bool:
    """Are CS2's series rounds priced (CS2_SERIES_ROUNDS_FROM_UTC)?"""
    if CS2_SERIES_ROUNDS_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= CS2_SERIES_ROUNDS_FROM_UTC.strftime("%Y-%m-%d")
            and at >= CS2_SERIES_ROUNDS_FROM_UTC)


# Audit 2026-10-13 B1: the favourite / outsider (game-state) term of a
# football side's centre. From this moment the centre of a market of
# game_state.GAME_STATE_MARKETS with a beta in config/sofa_game_state.json is
# multiplied by exp(beta x s), s the side's expected goal difference from the
# rating's goals book (FootballForecast.supremacy; the opponent reads -s).
# Changes p, so what prints: a day >= the date built at or after the moment.
# Evidence: docs/sofa/evidence/game_state_2026-10-13.md.
GAME_STATE = "game_state_v1"
# Switched on 2026-10-13 18:10Z with the football / tennis refit installed at
# 18:06Z (curves fitted on the replay carrying it; operator O6): 10-13 is a
# mixed day, its earlier prints stay locked.
GAME_STATE_FROM_UTC: datetime | None = datetime(
    2026, 10, 13, 18, 10, tzinfo=UTC)


def game_state_enabled(date: str, build_at: datetime | None = None) -> bool:
    """Does a football side's centre carry the game-state term
    (GAME_STATE_FROM_UTC)?"""
    if GAME_STATE_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= GAME_STATE_FROM_UTC.strftime("%Y-%m-%d")
            and at >= GAME_STATE_FROM_UTC)


# Audit 2026-10-13 B2 (1): the markets football_rating.UNRATED_MARKETS kept
# out of the rating (chosen on five days in sample, 2026-09-18..22) and
# measured again on the full history: from this moment the rating (attack x
# defence x league strength) enters the centre of those of them listed in
# football_rating.RATED_SCOPE_MARKETS at W_FOOTBALL_RATING, like every other
# rated market. A day >= the date built at or after the moment.
# Evidence: docs/sofa/evidence/unrated_markets_2026-10-13.md.
FOOTBALL_RATED_SCOPE = "rated_scope_v1"
# Switched on 2026-10-13 18:10Z with the football / tennis refit installed at
# 18:06Z (curves fitted on the replay carrying it; operator O6): 10-13 is a
# mixed day, its earlier prints stay locked.
FOOTBALL_RATED_SCOPE_FROM_UTC: datetime | None = datetime(
    2026, 10, 13, 18, 10, tzinfo=UTC)


def football_rated_scope(date: str, build_at: datetime | None = None) -> bool:
    """Does the rating price football_rating.RATED_SCOPE_MARKETS
    (FOOTBALL_RATED_SCOPE_FROM_UTC)?"""
    if FOOTBALL_RATED_SCOPE_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= FOOTBALL_RATED_SCOPE_FROM_UTC.strftime("%Y-%m-%d")
            and at >= FOOTBALL_RATED_SCOPE_FROM_UTC)


# Audit 2026-10-13 B2 (2): home / away as a league multiplier on a sample-only
# football centre (never a split of the sample - "venue is a prior"): the
# match competition's per-side rate at today's venue over the mean rate at the
# venues the sample was earned at (FootballForecast.venue_multiplier), for the
# markets of football_rating.VENUE_PRIOR_MARKETS whose row has no rating
# centre. A day >= the date built at or after the moment.
# Evidence: docs/sofa/evidence/unrated_markets_2026-10-13.md.
FOOTBALL_VENUE_PRIOR = "venue_prior_v1"
# Switched on 2026-10-13 18:10Z with the football / tennis refit installed at
# 18:06Z (curves fitted on the replay carrying it; operator O6): 10-13 is a
# mixed day, its earlier prints stay locked.
FOOTBALL_VENUE_PRIOR_FROM_UTC: datetime | None = datetime(
    2026, 10, 13, 18, 10, tzinfo=UTC)


def football_venue_prior(date: str, build_at: datetime | None = None) -> bool:
    """Does a sample-only football side centre read the league's venue
    multiplier (FOOTBALL_VENUE_PRIOR_FROM_UTC)?"""
    if FOOTBALL_VENUE_PRIOR_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= FOOTBALL_VENUE_PRIOR_FROM_UTC.strftime("%Y-%m-%d")
            and at >= FOOTBALL_VENUE_PRIOR_FROM_UTC)


# Audit 2026-10-13 A3 + C8 (basketball overtime; one path, score_model
# _basketball): a five-minute overtime is 5/12 of a quarter where quarters are
# 12 minutes (score_model.TWELVE_MINUTE_QUARTERS; it was 5/10 everywhere), and
# a regulation result within 3 points becomes a tie with probability
# score_model.BB_TIE_PULL (the "overtime spike"; the regulation draw was
# under-forecast ~0.024 against ~0.042). Live (SPORT_CONFIDENCE), in the
# line-evidence replay and in the history replay of a fit for a day >= it.
# Changes basketball p, so it goes live with the basketball curve refitted on
# it (audit stage 5).
BB_OVERTIME_FROM_UTC: datetime | None = None


def bb_overtime(date: str | None = None, build_at: datetime | None = None) -> bool:
    """Is basketball overtime simulated by the league's quarter and the tie
    pull (BB_OVERTIME_FROM_UTC)? `date` None: the wall clock alone."""
    if BB_OVERTIME_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    if date is not None and date < BB_OVERTIME_FROM_UTC.strftime("%Y-%m-%d"):
        return False
    return at >= BB_OVERTIME_FROM_UTC


# Audit 2026-10-13 B7: basketball's regulation points as pace x efficiency
# (score_model.PACE_METRICS: Oliver possessions and points per possession from
# the box score in sofa_event_stats, rated as-of like the points), where both
# sides have a fresh box-score rating; the points rating otherwise. Live
# (SPORT_CONFIDENCE), in the line-evidence replay and in the history replay of
# a fit for a day >= it (fit_sport_confidence --bb-pace). Changes basketball
# p, so it goes live only with a basketball curve refitted on it.
# Evidence: docs/sofa/evidence/basketball_pace_2026-10-13.md.
BB_PACE_FROM_UTC: datetime | None = None


def bb_pace(date: str | None = None, build_at: datetime | None = None) -> bool:
    """Is basketball's centre pace x efficiency (BB_PACE_FROM_UTC)? `date`
    None: the wall clock alone."""
    if BB_PACE_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    if date is not None and date < BB_PACE_FROM_UTC.strftime("%Y-%m-%d"):
        return False
    return at >= BB_PACE_FROM_UTC


# Audit 2026-10-13 B7b: basketball's box-score pace scales only the LEVEL of
# the points rating's centre - the total times (expected game possessions /
# the competition's possessions, as-of), the margin kept from the points
# rating, the spread fitted around the points centre - so winner and handicap
# stay as today up to rounding (score_model.ScoreModel.level_factor). Live, in
# the line-evidence replay and in a fit's history replay (fit_sport_confidence
# --bb-pace-level). Changes basketball totals, so it goes live only with a
# basketball curve refitted on it.
# Evidence: docs/sofa/evidence/basketball_pace_level_2026-10-13.md.
BB_PACE_LEVEL_FROM_UTC: datetime | None = None


def bb_pace_level(date: str | None = None, build_at: datetime | None = None
                  ) -> bool:
    """Does basketball's box-score pace scale the total
    (BB_PACE_LEVEL_FROM_UTC)? `date` None: the wall clock alone."""
    if BB_PACE_LEVEL_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    if date is not None and date < BB_PACE_LEVEL_FROM_UTC.strftime("%Y-%m-%d"):
        return False
    return at >= BB_PACE_LEVEL_FROM_UTC


# Audit 2026-10-13 B8: hockey's regulation goals as shots on goal x conversion
# (goals per shot: the side's finishing against 1 - the save% of the other
# side's goaltending as it played so far - the team's goalie mix, no pre-game
# starting goalie is known), each rated as-of in the goals' RatingBook from
# the box scores (score_model.SHOT_METRICS); HK_SHOTS_MODE "replace" takes the
# shots centre, "blend" its geometric mean with the goals centre. Falls back
# to the goals centre per game (score_model.ScoreModel.shots_expected). Live,
# in the line-evidence replay and in a fit's history replay
# (fit_sport_confidence --hk-shots). Changes hockey's p, so it goes live only
# with a hockey curve refitted on it.
# Evidence: docs/sofa/evidence/hockey_goalie_empty_net_2026-10-13.md.
HK_SHOTS_FROM_UTC: datetime | None = None
HK_SHOTS_MODE = "blend"


def hk_shots(date: str | None = None, build_at: datetime | None = None
             ) -> str | None:
    """HK_SHOTS_MODE when hockey's centre reads the shots (HK_SHOTS_FROM_UTC),
    else None. `date` None: the wall clock alone."""
    if HK_SHOTS_FROM_UTC is None:
        return None
    at = build_at if build_at is not None else timeutil.now()
    if date is not None and date < HK_SHOTS_FROM_UTC.strftime("%Y-%m-%d"):
        return None
    return HK_SHOTS_MODE if at >= HK_SHOTS_FROM_UTC else None


# Audit 2026-10-13 B8: hockey's late-game empty-net / extra-attacker goals
# by the lead (score_model.HK_EMPTY_NET, fitted on the history's final
# regulation margins) instead of one hand-picked pair for leads of 1 and 2.
# Live, in the line-evidence replay and in a fit's history replay
# (fit_sport_confidence --hk-empty-net); goes live only with a hockey curve
# refitted on it.
# Evidence: docs/sofa/evidence/hockey_goalie_empty_net_2026-10-13.md.
HK_EMPTY_NET_FROM_UTC: datetime | None = None


def hk_empty_net(date: str | None = None, build_at: datetime | None = None
                 ) -> bool:
    """Does hockey simulate the fitted empty-net probabilities
    (HK_EMPTY_NET_FROM_UTC)? `date` None: the wall clock alone."""
    if HK_EMPTY_NET_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    if date is not None and date < HK_EMPTY_NET_FROM_UTC.strftime("%Y-%m-%d"):
        return False
    return at >= HK_EMPTY_NET_FROM_UTC


# Audit 2026-10-13 B9 / C10: a volleyball set's length - its loser's points -
# drawn from the history's own distribution (score_model.SetLengthTable:
# gender x regular / fifth set x did the favourite win it x the rating's share
# gap, one step ahead over the 365 days before the model's cut) instead of the
# i.i.d. rally share, which made matches 4-6 points too short and too few sets
# on extra points. Who wins each set is the rally simulation's, bit for bit.
# Live (SPORT_CONFIDENCE), in the line-evidence replay and in a fit's history
# replay (fit_sport_confidence --vb-set-length). Changes volleyball's points
# and set-points p, so it goes live only with a volleyball curve refitted on
# it. Evidence: docs/sofa/evidence/volleyball_set_length_2026-10-13.md.
VB_SET_LENGTH_FROM_UTC: datetime | None = None


def vb_set_length(date: str | None = None, build_at: datetime | None = None
                  ) -> bool:
    """Is volleyball's set length drawn from the history's table
    (VB_SET_LENGTH_FROM_UTC)? `date` None: the wall clock alone."""
    if VB_SET_LENGTH_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    if date is not None and date < VB_SET_LENGTH_FROM_UTC.strftime("%Y-%m-%d"):
        return False
    return at >= VB_SET_LENGTH_FROM_UTC


# Audit 2026-10-13 C9 (operator O3: set markets come back after B9 and an
# out-of-sample measurement, through a switch): a volleyball fit for a day at
# or after this moment scores the set markets - set winner (744), set points
# total (782), set points parity (781), set on extra points (100077) - on the
# history's sets 1-5 (sport_confidence.history_markets / market_periods), so
# they get a history curve like the match markets instead of reading only
# settled Superbet lines (plan F4, operator 2026-10-07). Live it changes
# nothing but the curve a fit writes. Evidence: as B9.
VB_SET_HISTORY_FROM_UTC: datetime | None = None


def vb_set_history(date: str | None = None, build_at: datetime | None = None
                   ) -> bool:
    """Does a volleyball fit score the set markets on the history
    (VB_SET_HISTORY_FROM_UTC)? `date` None: the wall clock alone."""
    if VB_SET_HISTORY_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    if date is not None and date < VB_SET_HISTORY_FROM_UTC.strftime("%Y-%m-%d"):
        return False
    return at >= VB_SET_HISTORY_FROM_UTC


# Audit 2026-10-13 A7 (operator O2): the basketball history curve is fitted
# on lines placed where the market stood - each historical game's Sofascore
# total and spread (scripts/sofa/backfill_event_odds.py, cached without a
# price; bet.sofa.market_lines), the team totals at the split they imply -
# instead of quantiles of the model's own simulation, for those families
# (sport_confidence.MARKET_LINE_MARKETS); p stays the score model's. It acts
# in the history replay of a fit for a day >= it (fit_sport_confidence; a fit
# with the switch on and no --market-lines reads MARKET_LINES_CACHE) and goes
# live only with the curve refitted that way (O6). None = synthetic lines.
# Measured: docs/sofa/evidence/market_positioned_lines_2026-10-13.md.
# On with the A7 basketball curve staged from 2026-10-14 (audit standing go):
# log-loss -0.0622 [-0.0702, -0.0546] on Superbet lines 10-05..10-12.
MARKET_POSITIONED_LINES_FROM_UTC: datetime | None = datetime(
    2026, 10, 14, 0, 0, tzinfo=UTC)
MARKET_LINES_CACHE = "data/a7_odds/{sport}.jsonl"


def market_positioned_lines(date: str | None = None,
                            build_at: datetime | None = None) -> bool:
    """Is the history curve fitted on market-positioned lines
    (MARKET_POSITIONED_LINES_FROM_UTC)? `date` None: the wall clock alone."""
    if MARKET_POSITIONED_LINES_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    if (date is not None
            and date < MARKET_POSITIONED_LINES_FROM_UTC.strftime("%Y-%m-%d")):
        return False
    return at >= MARKET_POSITIONED_LINES_FROM_UTC


# Audit 2026-10-13 B5: the tennis per-set games (games_set1/2_total,
# games_won_set1/2/3_for) and sets_total were priced from the players' own
# samples shrunk to a global prior, with no opponent. From this moment they are
# read off the rating's neighbours (tennis_rating.SET_RATING_PRICED_MARKETS),
# as games_won_for has been since TENNIS_RATING_PRICES (it rides on that
# switch: off there, off here). It moves p_central, and the curves of these
# markets were fitted on the sample's p (calibrate_from_cache replays none of
# them), so it goes live only together with a refit replaying them - a new
# comparability epoch, never mid-day. None = the sample's estimator, byte for
# byte. Measured 2026-10-13 (walk-forward 03-01..10-12, ~54k matches, bootstrap
# by match): log-loss better in every market and both windows - set totals
# -0.017..-0.019, a player's set games -0.065..-0.068 (set three -0.088),
# sets_total -0.022 (docs/sofa/evidence/tennis_set_markets_2026-10-13.md).
# Switched on with that refit (2026-10-13 18:10Z, below).
# Switched on 2026-10-13 18:10Z with the football / tennis refit installed at
# 18:06Z (curves fitted on the replay carrying it; operator O6): 10-13 is a
# mixed day, its earlier prints stay locked.
TENNIS_SET_RATING_PRICES_FROM_UTC: datetime | None = datetime(
    2026, 10, 13, 18, 10, tzinfo=UTC)


def tennis_set_rating_prices(date: str, build_at: datetime | None = None) -> bool:
    """Are the per-set games and sets_total read off the rating's neighbours
    (TENNIS_SET_RATING_PRICES_FROM_UTC)? The day being built and the build
    clock, like every other switch."""
    if TENNIS_SET_RATING_PRICES_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= TENNIS_SET_RATING_PRICES_FROM_UTC.strftime("%Y-%m-%d")
            and at >= TENNIS_SET_RATING_PRICES_FROM_UTC)


# Audit 2026-10-13 B15 with A5 (Part 6 W1, W4, W7): a football side's sample
# rescaled to a neutral opponent (x / def(opponent), Maher 1982) and to the
# league domain of today's match (exp of the rating's log strength gap) before
# SHEET's centre (bet.sofa.opponent_correction), and CONFIDENCE's shape gates
# and MODEL_ABOVE_OWN_SAMPLE reading the same corrected values (the row's
# `corrected_sample`) - otherwise any move of p away from the raw sample is
# removed by the gates. Rows priced this way carry `opponent_rule`
# (SAMPLE_OPPONENT_CORRECTION), so a rebuild re-runs SHEET on a sheet of the
# other rule. Changes p_central, so it goes live only with the same
# correction in the cache replay (calibrate_from_cache) and a refit of the
# football curves. None: the raw sample, byte for byte.
# Measured: docs/sofa/evidence/sample_opponent_correction_2026-10-13.md.
SAMPLE_OPPONENT_CORRECTION = "sample_opponent_v1"
# On with the football refit installed 2026-10-14 05:31Z (curves fitted on the
# replay carrying it, audit standing go); 10-14 not yet built - not a mixed day.
# SAMPLES writes opponent_id from 2026-10-13 evening; older samples are raw.
SAMPLE_OPPONENT_CORRECTION_FROM_UTC: datetime | None = datetime(
    2026, 10, 14, 5, 45, tzinfo=UTC)


def sample_opponent_correction(date: str, build_at: datetime | None = None) -> bool:
    """Is the football sample corrected for its opponents and domain
    (SAMPLE_OPPONENT_CORRECTION_FROM_UTC)?"""
    if SAMPLE_OPPONENT_CORRECTION_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= SAMPLE_OPPONENT_CORRECTION_FROM_UTC.strftime("%Y-%m-%d")
            and at >= SAMPLE_OPPONENT_CORRECTION_FROM_UTC)


def sheet_sample_opponent_correction(rows: Sequence[Mapping[str, Any]]) -> bool:
    """Was every football row of a 05_sheet.json priced under
    SAMPLE_OPPONENT_CORRECTION? A sheet without football has nothing to
    re-price: SHEET switches the correction on only with a football rating
    book, which it builds only for a day with a football fixture, so a
    football-less sheet never carries the marker and would re-run SHEET on
    every rebuild."""
    return all(r.get("opponent_rule") == SAMPLE_OPPONENT_CORRECTION
               for r in rows if r.get("sport") == "football")


# Audit 2026-10-13 D2: the tennis match winner ("Zwycięzca", selections "1" /
# "2") read by OFFER as one two-sided rung (bet.sofa.tennis_winner:
# match_won_for, subject = the listing's first name, line 0.5, OVER = he
# wins), priced by SHEET from the as-of rating alone (MatchForecast.
# p_side_wins, no sample, no price) and read by CONFIDENCE from its own
# history curve (match_won_for in the calibration, fitted on the replay by
# scripts/sofa/fit_tennis_winner_curve.py). Adds legs, so changes what prints:
# a day >= the date built at or after the moment. Off (None): OFFER, SAMPLES,
# SHEET and CONFIDENCE byte-identical. Needs the curve installed - without it
# every such leg is NOT_CALIBRATED. Operator's go for the refit: 2026-10-13
# (O6). Evidence: docs/sofa/evidence/tennis_match_winner_2026-10-13.md.
TENNIS_MATCH_WINNER = "tennis_match_winner_v1"
# Switched on by the operator 2026-10-13 ("Włączamy!"), curve merged from
# data/refit_2026-10-13/d2 (calibration conservative: printed below realised).
TENNIS_MATCH_WINNER_FROM_UTC: datetime | None = datetime(
    2026, 10, 14, 0, 0, tzinfo=UTC)


def tennis_match_winner(date: str, build_at: datetime | None = None) -> bool:
    """Does OFFER read and SHEET price the tennis match winner
    (TENNIS_MATCH_WINNER_FROM_UTC)?"""
    if TENNIS_MATCH_WINNER_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= TENNIS_MATCH_WINNER_FROM_UTC.strftime("%Y-%m-%d")
            and at >= TENNIS_MATCH_WINNER_FROM_UTC)


# Audit 2026-10-13 C1: the season phase of a football league match (early /
# mid / late / final, as of the kickoff from the history: each side's
# matches of the competition-season so far against the previous season's
# length, bet.sofa.season_phase) multiplies the centre of the goals markets of
# season_phase.SEASON_PHASE_MARKETS by exp(c[market][phase]) from
# config/sofa_season_phase.json. Changes p, so what prints: a day >= the date
# built at or after the moment. The curves were fitted without the term: it
# goes on with the football refit that replays it.
# Evidence: docs/sofa/evidence/season_phase_2026-10-13.md.
SEASON_PHASE = "season_phase_v1"
# Switched on 2026-10-13 18:10Z with the football / tennis refit installed at
# 18:06Z (curves fitted on the replay carrying it; operator O6): 10-13 is a
# mixed day, its earlier prints stay locked.
SEASON_PHASE_FROM_UTC: datetime | None = datetime(
    2026, 10, 13, 18, 10, tzinfo=UTC)


def season_phase_enabled(date: str, build_at: datetime | None = None) -> bool:
    """Does a football goals centre carry the season-phase term
    (SEASON_PHASE_FROM_UTC)?"""
    if SEASON_PHASE_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= SEASON_PHASE_FROM_UTC.strftime("%Y-%m-%d")
            and at >= SEASON_PHASE_FROM_UTC)


# Audit 2026-10-13 B14: the football rating's weight per market. From this
# moment a rated football centre is W_m x rating + (1 - W_m) x the shrunk
# sample with W_m from config/sofa_rating_weight.json (bet.sofa.rating_weight;
# a market absent from the file keeps football_rating.W_FOOTBALL_RATING).
# Changes p, so what prints: a day >= the date built at or after the moment.
# The curves describe W = 0.5: it goes on with the football refit.
# Evidence: docs/sofa/evidence/rating_weight_2026-10-13.md.
FOOTBALL_RATING_WEIGHT = "rating_weight_v1"
# Switched on 2026-10-13 18:10Z with the football / tennis refit installed at
# 18:06Z (curves fitted on the replay carrying it; operator O6): 10-13 is a
# mixed day, its earlier prints stay locked.
FOOTBALL_RATING_WEIGHT_FROM_UTC: datetime | None = datetime(
    2026, 10, 13, 18, 10, tzinfo=UTC)


def football_rating_weight(date: str, build_at: datetime | None = None) -> bool:
    """Does a rated football centre read its market's own W
    (FOOTBALL_RATING_WEIGHT_FROM_UTC)?"""
    if FOOTBALL_RATING_WEIGHT_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= FOOTBALL_RATING_WEIGHT_FROM_UTC.strftime("%Y-%m-%d")
            and at >= FOOTBALL_RATING_WEIGHT_FROM_UTC)


# The rule markers of the audit 2026-10-13 SHEET switches (GAME_STATE,
# FOOTBALL_RATED_SCOPE, FOOTBALL_VENUE_PRIOR, SEASON_PHASE,
# FOOTBALL_RATING_WEIGHT on football rows; TENNIS_SET_RATING_PRICES on tennis
# rows): SHEET stamps the row field with the rule's name when the switch is on
# for the day built and the build clock, and leaves the field out when off, so
# rebuild_plan re-runs SHEET on a sheet built before the switch (on 2026-10-13
# the sheet of the morning had to be re-run by hand after 18:10Z). Only the
# rows the rule can apply to are read: a sheet without football (tennis) has
# nothing to re-price and would otherwise re-run SHEET on every rebuild.
TENNIS_SET_RATING_PRICES = "tennis_set_rating_v1"
# (row field, rule name, sport of the rows it applies to)
GAME_STATE_MARKER = ("game_state_rule", GAME_STATE, "football")
FOOTBALL_RATED_SCOPE_MARKER = ("rated_scope_rule", FOOTBALL_RATED_SCOPE, "football")
FOOTBALL_VENUE_PRIOR_MARKER = ("venue_prior_rule", FOOTBALL_VENUE_PRIOR, "football")
SEASON_PHASE_MARKER = ("season_phase_rule", SEASON_PHASE, "football")
FOOTBALL_RATING_WEIGHT_MARKER = (
    "rating_weight_rule", FOOTBALL_RATING_WEIGHT, "football")
TENNIS_SET_RATING_PRICES_MARKER = (
    "tennis_set_rule", TENNIS_SET_RATING_PRICES, "tennis")


# A tennis player's aces centre x today's returner's factor - the aces his
# own opponents served against him, shrunk with K toward the tier prior, over
# that prior (bet.sofa.tennis_aces_opponent): aces_for and the per-set
# aces_set1/2_for x f(other side); the aces totals x (c_A f(B) + c_B f(A)) /
# (c_A + c_B). Double faults are not corrected (measured worse). Changes
# p_central, so it goes live only with the correction in the cache replay
# (calibrate_from_cache --tennis-aces-opponent) and the aces curves refitted
# on it. Rows carry TENNIS_ACES_OPPONENT_MARKER (every tennis row of a sheet
# priced under it). None: the server's sample alone, byte for byte.
# Measured: docs/sofa/evidence/tennis_aces_opponent_2026-10-17.md.
TENNIS_ACES_OPPONENT = "tennis_aces_opponent_v1"
TENNIS_ACES_OPPONENT_FROM_UTC: datetime | None = None
TENNIS_ACES_OPPONENT_MARKER = ("tennis_aces_rule", TENNIS_ACES_OPPONENT, "tennis")


def tennis_aces_opponent(date: str, build_at: datetime | None = None) -> bool:
    """Is a tennis aces centre corrected for today's returner
    (TENNIS_ACES_OPPONENT_FROM_UTC)? The day being built and the build
    clock, like every other switch."""
    if TENNIS_ACES_OPPONENT_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= TENNIS_ACES_OPPONENT_FROM_UTC.strftime("%Y-%m-%d")
            and at >= TENNIS_ACES_OPPONENT_FROM_UTC)


def sheet_has_marker(rows: Sequence[Mapping[str, Any]],
                     marker: tuple[str, str, str]) -> bool:
    """Was every row of a 05_sheet.json the marker's rule applies to (its
    sport) priced under it? A sheet without such a row has nothing to
    re-price."""
    field_name, rule, sport = marker
    return all(r.get(field_name) == rule for r in rows if r.get("sport") == sport)


# Audit 2026-10-13 B11: every map of a CS2 series had the same p - the map
# number on the line ("X wygra N. mape") was never read and the history held
# no map name. Superbet's line knows only the number (the veto is minutes
# before the start; Sofascore names the map afterwards; the starting side and
# halves come after the veto), so what is knowable pre-match enters: a term
# per (format, map number) and the two teams' per-map Elo deviations mixed
# over their recent map pools (cs2_engine.MapPoolBook, RatingModel.p_map_nr).
# From this moment the map-level families (map_winner, map_rounds_handicap,
# the race's map_team_rounds) read the map's own p in SPORT_CONFIDENCE, at
# CS2_SETTLE and in the history replay of a fit for a day >= it. It changes
# p, so the CS2 curve must be refitted on the same estimator.
# Evidence: docs/sofa/evidence/cs2_map_identity_2026-10-13.md.
CS2_MAP_IDENTITY_FROM_UTC: datetime | None = None


def cs2_map_identity(date: str, build_at: datetime | None = None) -> bool:
    """Does a CS2 map-level line read its own map's p
    (CS2_MAP_IDENTITY_FROM_UTC)?"""
    if CS2_MAP_IDENTITY_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= CS2_MAP_IDENTITY_FROM_UTC.strftime("%Y-%m-%d")
            and at >= CS2_MAP_IDENTITY_FROM_UTC)


# Audit 2026-10-13 B12: a CS2 player's kills / deaths / assists / headshots
# and a team's kills were a negative binomial of the last 20 maps' values -
# blind to how many rounds the map is expected to last and to who wins them
# (kills correlate 0.592 with the map's rounds). From this moment the
# families in cs2_engine.EXPOSURE_FAMILIES are priced from the round race's
# (W, L) distribution x per-round rates (cs2_engine.ExposureBook) in
# SPORT_CONFIDENCE and at CS2_SETTLE (model_p, the line evidence's input);
# player_headshots stays on the sample (measured worse). No history curve
# reads these families (line evidence only).
# Evidence: docs/sofa/evidence/cs2_kills_exposure_2026-10-13.md.
# Switched on by the audit's standing go (CLAUDE.md, Changing the pipeline 4):
# out-of-sample log-loss better with an interval below zero on four families.
# Moved by the operator (2026-10-13) from 2026-10-14 00:00Z to the refit's
# rebuild of 10-13, with the staged CS2 curve: a mixed day.
CS2_COUNT_EXPOSURE_FROM_UTC: datetime | None = datetime(
    2026, 10, 13, 18, 10, tzinfo=UTC)


def cs2_count_exposure(date: str, build_at: datetime | None = None) -> bool:
    """Is a CS2 kills / deaths / assists / headshots line priced from the
    rounds' exposure (CS2_COUNT_EXPOSURE_FROM_UTC)?"""
    if CS2_COUNT_EXPOSURE_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= CS2_COUNT_EXPOSURE_FROM_UTC.strftime("%Y-%m-%d")
            and at >= CS2_COUNT_EXPOSURE_FROM_UTC)


# The exposure model's player share (B12) read the player's last MAX_SAMPLE
# (20) maps shrunk with K_SHARE 2 maps (unfitted): at lines placed like
# Superbet's it was overconfident (kills calibration slope 0.71), stars
# over- and low-share players under-predicted (kill-share terciles -3.3 /
# +2.9 pp), and headshots stayed on the sample because 239 impossible rows
# (headshots > kills, 2025-10-27) had inflated their dispersion. From this
# moment the share reads the last cs2_engine.SHARE_WINDOW (40) maps shrunk
# with cs2_engine.K_SHARE_BY_STAT (kills 8, deaths 8, assists 16, headshots 4,
# chosen walk-forward on history), and player_headshots joins the exposure
# families. Walk-forward 2026-04..09-27 (100,525 player-maps, 4,477 matches),
# log-loss at the emulated Superbet line: kills -0.00305 [-0.00357, -0.00253],
# deaths -0.00111, assists -0.00402, headshots -0.01018, every interval below
# zero. A calibration fix, not an edge: on Superbet's 20 settled days no
# variant adds anything over the devigged price (kills blend +0.00037
# [-0.0020, +0.0030]). docs/sofa/history/POMIAR_CS2_PLAYER_KILLS_2026-10-20.md.
# Operator's go 2026-10-20, from the next day's 00:00Z.
CS2_PLAYER_SHARE_FROM_UTC: datetime | None = datetime(2026, 10, 21, tzinfo=UTC)


def cs2_player_share(date: str, build_at: datetime | None = None) -> bool:
    """Does a CS2 player line read the 40-map share with per-stat shrinkage
    and headshots from the exposure (CS2_PLAYER_SHARE_FROM_UTC)?"""
    if CS2_PLAYER_SHARE_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= CS2_PLAYER_SHARE_FROM_UTC.strftime("%Y-%m-%d")
            and at >= CS2_PLAYER_SHARE_FROM_UTC)


# The hockey / basketball player model (bet.sofa.player_model) read a past
# game's squad from each lineup entry's `teamId` - the player's team when the
# box was downloaded, not his team in that game. A traded player's games for
# his old team AGAINST his new one landed in the new team's sample (and his
# other old-team games nowhere): Carlson model_n 5 of 85 appearances,
# McTavish 6 of 88 on 2026-10-13 (docs/sofa/evidence/
# sport_player_props_2026-10-13.md, "Odstępstwa"). From this moment a game's
# squad is the lineup SIDE (home / away) the team held in that event
# (player_model.appearances_from_lineups with `side`), in SHADOW's pre-game
# forecast (player_model.jsonl), in SHADOW_SETTLE's settle-time number and in
# measure_player_props; fit_player_model replays it with
# --player-team-from-side. A correctness fix of a wrong mapping, but it moves
# the player model's p, so it changes what prints: a day >= the date (the
# game's kickoff day, UTC - SHADOW's day key) computed at or after the moment.
# Rows carry `player_team_rule`. The line evidence reads the p SHADOW wrote
# before the game, so its replay follows the day's rule by construction.
PLAYER_TEAM_RULE = "player_team_from_side_v1"
PLAYER_TEAM_FROM_SIDE_FROM_UTC: datetime | None = datetime(
    2026, 10, 14, 0, 0, tzinfo=UTC)


def player_team_from_side(date: str, build_at: datetime | None = None) -> bool:
    """Is a past game's squad read from the team's lineup side rather than
    the entries' `teamId` (PLAYER_TEAM_FROM_SIDE_FROM_UTC)?"""
    if PLAYER_TEAM_FROM_SIDE_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= PLAYER_TEAM_FROM_SIDE_FROM_UTC.strftime("%Y-%m-%d")
            and at >= PLAYER_TEAM_FROM_SIDE_FROM_UTC)


# Men's national-team friendlies (uniqueTournament 851, on the friendly
# exclusion list since 2026-10-04; bet.sofa.men_friendly). Measured
# 2026-10-13 (docs/sofa/evidence/national_friendly_samples_2026-10-13.md,
# 2,209 men's friendlies 2015..2026-10-12, NB log-loss, match bootstrap, as-of
# prior): the goal sample of an 851 fixture is today the newest ten
# competitive matches (D); every pool match - friendlies included - inside the
# window of the newest ten 851 matches (C) is better on goals_total -0.0071
# [-0.0127, -0.0015] and goals_for -0.0140 [-0.0196, -0.0086]. Not covered by
# any standing go: the operator decides. Both change what prints: a day >= the
# date built at or after the moment. The history curves were fitted without
# either (851 is out of the replay); a refit that carries them must replay
# the 851 targets with this sample and prior.
#
# SAMPLES: an 851 fixture's goals_total / goals_for sample is variant C
# (men_friendly.pick_friendly_window; the pool admits 851 matches for that
# fixture only). Off: SAMPLES byte-identical. 852 (women) never.
# Switched on by the operator 2026-10-13 ("Wszystkie rynki włączone").
MEN_FRIENDLY_SAMPLE_WINDOW_FROM_UTC: datetime | None = datetime(
    2026, 10, 14, 0, 0, tzinfo=UTC)


def men_friendly_sample_window(date: str, build_at: datetime | None = None) -> bool:
    """Does an 851 fixture's goal sample read the friendly window
    (MEN_FRIENDLY_SAMPLE_WINDOW_FROM_UTC)?"""
    if MEN_FRIENDLY_SAMPLE_WINDOW_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= MEN_FRIENDLY_SAMPLE_WINDOW_FROM_UTC.strftime("%Y-%m-%d")
            and at >= MEN_FRIENDLY_SAMPLE_WINDOW_FROM_UTC)


# SHEET: the goals_total / goals_for prior of an 851 fixture is the as-of mean
# of 851's own matches before the day (men_friendly.FriendlyBaseline, 2.54
# goals over 2,365 matches on 2026-10-13) instead of the pooled chain, which
# ends at the global 3.26 (851 has no fitted baseline). Off: SHEET
# byte-identical. No rule marker: switched on mid-day, SHEET is re-run by hand.
# Switched on by the operator 2026-10-13 ("Wszystkie rynki włączone").
MEN_FRIENDLY_BASELINE_FROM_UTC: datetime | None = datetime(
    2026, 10, 14, 0, 0, tzinfo=UTC)


def men_friendly_baseline(date: str, build_at: datetime | None = None) -> bool:
    """Does an 851 fixture's goals centre shrink toward the men's friendly
    baseline (MEN_FRIENDLY_BASELINE_FROM_UTC)?"""
    if MEN_FRIENDLY_BASELINE_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= MEN_FRIENDLY_BASELINE_FROM_UTC.strftime("%Y-%m-%d")
            and at >= MEN_FRIENDLY_BASELINE_FROM_UTC)


# The entity map (identity plan K1, bet.sofa.entity_map,
# docs/sofa/history/RAPORT_K1_MAPA_ENCJI_2026-10-14.md): SPORT_IDENTITY
# learns the Superbet names it pinned by their own name (a name-checked
# method, score above NAME_MATCH_THRESHOLD) into sofa_entity, source
# `identity_names`; manual aliases (K4) are `manual`. Reading those rows
# identifies more events, so it changes what prints: a reader uses them only
# for a day >= the date AND at a clock at or after the moment
# (`entity_map`). The same moment ends the overwrite of a held verified id
# (cache.save_entity, entity_map.learn): another id for a held name is
# queued in sofa_entity_conflict instead. Measured on the pinned events of
# 2026-10-05..10-14 (K1 report): 477 names the resolver could not resolve
# become known (basketball 286, hockey 78, volleyball 107, CS2 6), 485 it
# resolved through the listing index are now held with the same id; 0 names
# pinned to two ids, 0 learned ids differing from the resolver's; 2 held CS2
# rows (backfill_cs2) contradict the pinned events and are queued. Upper
# bound of the direct gain: 32 not-identified events in 10 days had a side
# learned from an earlier game. Next day's 00:00Z by the default rule.
# Moved by the operator 2026-10-14 ("wlacz ... zeby te zmiany byly od dzisiaj")
# from 2026-10-15 00:00Z to 2026-10-14 11:30Z: 10-14 is a MIXED day (legs
# printed before stay locked; ledger group "10-14 mieszany").
ENTITY_MAP_FROM_UTC: datetime | None = datetime(2026, 10, 14, 11, 30, tzinfo=UTC)
# Stamped on a row whose teams a reader resolved with the map's learned rows
# (player_model's pre-game rows by name; absent when off).
ENTITY_MAP_RULE = "entity_map_v1"


def entity_map(date: str | None, build_at: datetime | None = None) -> bool:
    """Are learned entity-map rows read, and a held verified id never
    overwritten (ENTITY_MAP_FROM_UTC)? `date` None judges the clock alone
    (a reader with no day of its own: RESOLVE's / SHADOW_SETTLE's cache)."""
    if ENTITY_MAP_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    if at < ENTITY_MAP_FROM_UTC:
        return False
    return date is None or date >= ENTITY_MAP_FROM_UTC.strftime("%Y-%m-%d")


# DAY_ANCHOR (identity plan K2, sport_identity.match_shadow,
# docs/sofa/history/RAPORT_K2_DAY_ANCHOR_2026-10-14.md): with no listed game
# on both names, the anchor team's (a side's resolved id) ONLY game within
# MAX_START_GAP of Superbet's start is this hockey / basketball / volleyball
# event, whatever the other name says (a club does not play twice in an
# hour; CS2 is left out - series run late and a team plays several a day).
# Measured 2026-10-05..10-14 (scripts/sofa/measure_day_anchor.py, the ids
# the resolver had at identification, the opponent's name hidden): hockey
# 591/591, basketball 793/793, volleyball 194/194 IDENTIFIED games picked
# right; on NOT_IDENTIFIED events every pick the settle later found on its
# own rules agreed (79 of 79). Live gain on those days: the
# NO_MATCH_IN_LISTING events (hockey 2, basketball 6, volleyball 4); a
# replay on 10-13/10-14's cached listings identifies 8. A wider window adds
# one basketball game (2 h): the window stays 1 h. The opponent's name is
# never learned from it (entity_map.OPPONENT_METHODS: a candidate). Changes
# what prints: a day >= the date, built at or after the moment.
# Moved by the operator 2026-10-14 ("wlacz ... zeby te zmiany byly od dzisiaj")
# from 2026-10-15 00:00Z to 2026-10-14 11:30Z: 10-14 is a MIXED day (legs
# printed before stay locked; ledger group "10-14 mieszany").
DAY_ANCHOR_FROM_UTC: datetime | None = datetime(2026, 10, 14, 11, 30, tzinfo=UTC)


def day_anchor(date: str, build_at: datetime | None = None) -> bool:
    """Does SPORT_IDENTITY accept DAY_ANCHOR (DAY_ANCHOR_FROM_UTC)?"""
    if DAY_ANCHOR_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= DAY_ANCHOR_FROM_UTC.strftime("%Y-%m-%d")
            and at >= DAY_ANCHOR_FROM_UTC)


# Football players by surname + first-name prefix (identity plan K7,
# players.match_player_by_surname, SAMPLES' last fallback after the token
# rule): measured 2026-10-14 on 10-12..10-14 - 1,827 of 1,827 matched players
# picked the same person, 22 new players found (~7 a day; Trey Nyoni, Ben
# Chrisene, Evan Ndicka). Adds player samples: changes what prints - a day
# >= the date, built at or after the moment. The sample says
# `match_rule: "surname"`, the sheet row PLAYER_NAME_SURNAME, and SETTLE
# grades the matched name as it does a token match.
# Moved by the operator 2026-10-14 ("wlacz ... zeby te zmiany byly od dzisiaj")
# from 2026-10-15 00:00Z to 2026-10-14 11:30Z: 10-14 is a MIXED day (legs
# printed before stay locked; ledger group "10-14 mieszany").
PLAYER_NAME_SURNAME_FROM_UTC: datetime | None = datetime(
    2026, 10, 14, 11, 30, tzinfo=UTC)


def player_name_surname(date: str, build_at: datetime | None = None) -> bool:
    """Does SAMPLES fall back to the surname match (PLAYER_NAME_SURNAME_FROM_UTC)?"""
    if PLAYER_NAME_SURNAME_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= PLAYER_NAME_SURNAME_FROM_UTC.strftime("%Y-%m-%d")
            and at >= PLAYER_NAME_SURNAME_FROM_UTC)


# TOURNAMENT_DAY (identity plan K3, sport_identity.identify_event,
# bet.sofa.day_listing): hockey / basketball / volleyball events NEITHER side
# of which has an id are matched by both names inside their tournament's
# games of the day (unique-tournament/<ut>/scheduled-events/<day>, the
# entity map's tournament map; one request per tournament-day, cached).
# Measured 2026-10-14 (scripts/sofa/measure_tournament_day.py, 95
# tournament-days of 10-05..10-14, no refusal): 298 / 298 IDENTIFIED games
# right with the ids hidden; 24 of 42 such events identified, 15 confirmed
# by the settle, 0 contradicted. Identifies more events: changes what
# prints - a day >= the date, built at or after the moment.
# Moved by the operator 2026-10-14 ("wlacz ... zeby te zmiany byly od dzisiaj")
# from 2026-10-15 00:00Z to 2026-10-14 11:30Z: 10-14 is a MIXED day (legs
# printed before stay locked; ledger group "10-14 mieszany").
TOURNAMENT_DAY_FROM_UTC: datetime | None = datetime(2026, 10, 14, 11, 30, tzinfo=UTC)


def tournament_day(date: str, build_at: datetime | None = None) -> bool:
    """Does SPORT_IDENTITY match by the tournament's day (TOURNAMENT_DAY_FROM_UTC)?"""
    if TOURNAMENT_DAY_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= TOURNAMENT_DAY_FROM_UTC.strftime("%Y-%m-%d")
            and at >= TOURNAMENT_DAY_FROM_UTC)


# NOT_ON_SOFASCORE (identity plan K5, sport_identity.identify_event): a
# NO_GAME_WITHIN_1H read from a cached team page (events_ttl_min, 6 h) is
# asked again fresh within FRESH_RECHECK_WITHIN of the start (once per team
# a run), and a fresh page of a team resolved by id with no game of it within
# ABSENCE_WINDOW (12 h) is the proven absence NOT_ON_SOFASCORE, with its
# evidence on the record (still NOT_IDENTIFIED, still re-asked every run until
# the start). Measured 2026-10-14: of the 18 NO_GAME_WITHIN_1H verdicts of
# 10-13..10-14 17 were read from cache; until 10-12 the reason was mostly a
# game asked after its start (fixed 10-12, frozen_at_start). The re-ask can
# identify a game the cached page lacked: changes what prints.
# Moved by the operator 2026-10-14 ("wlacz ... zeby te zmiany byly od dzisiaj")
# from 2026-10-15 00:00Z to 2026-10-14 11:30Z: 10-14 is a MIXED day (legs
# printed before stay locked; ledger group "10-14 mieszany").
NOT_ON_SOFASCORE_FROM_UTC: datetime | None = datetime(2026, 10, 14, 11, 30, tzinfo=UTC)


def not_on_sofascore(date: str, build_at: datetime | None = None) -> bool:
    """K5's fresh re-ask and absence verdict (NOT_ON_SOFASCORE_FROM_UTC)?"""
    if NOT_ON_SOFASCORE_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= NOT_ON_SOFASCORE_FROM_UTC.strftime("%Y-%m-%d")
            and at >= NOT_ON_SOFASCORE_FROM_UTC)


# The football day anchor in RESOLVE (identity plan K8,
# resolve.football_day_anchor_event): measured 2026-10-14 3,458 / 3,459
# bridged fixtures of 10-05..10-14 with Superbet's orientation; ~11 more
# fixtures a day; the one unsettled case (Hapoel / Maccabi Petah Tikva U19
# 10-11) is accepted by the operator ("Tylko 1. wlacz", 2026-10-14), who also
# set the moment. A day >= the date, at a clock at or after the moment.
# Moved by the operator 2026-10-14 ("wlacz ... zeby te zmiany byly od dzisiaj")
# from 2026-10-15 00:00Z to 2026-10-14 11:30Z: 10-14 is a MIXED day (legs
# printed before stay locked; ledger group "10-14 mieszany").
FOOTBALL_DAY_ANCHOR_FROM_UTC: datetime | None = datetime(
    2026, 10, 14, 11, 30, tzinfo=UTC)


def football_day_anchor(date: str, build_at: datetime | None = None) -> bool:
    """Does RESOLVE accept the football day anchor (FOOTBALL_DAY_ANCHOR_FROM_UTC)?"""
    if FOOTBALL_DAY_ANCHOR_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= FOOTBALL_DAY_ANCHOR_FROM_UTC.strftime("%Y-%m-%d")
            and at >= FOOTBALL_DAY_ANCHOR_FROM_UTC)


# Audit 2026-10-13 D1, double chance only (DNB waits): OFFER reads the full-
# match "Podwójna szansa" (1X / X2 / 12) as market double_chance, the
# selection in `subject`, its price the OVER, and the "Mecz" 1X2 outcome it
# leaves out the UNDER (bet.sofa.football_result); SHEET prices the selection
# from independent NB goals on the PURE rating centres (FootballForecast.
# centre("goals_for", side), r from config/sofa_football_result.json, rows
# marked `result_rule`); SETTLE grades it on the 90-minute score. No curve is
# installed: CONFIDENCE reads the key's own Superbet lines, NO_LINE_EVIDENCE
# until a bucket holds enough of them - so nothing prints at first. Adds rows,
# so a day >= the date built at or after the moment. Off (None, until the
# operator sets it): OFFER, SAMPLES, SHEET and CONFIDENCE byte-identical.
# Evidence: docs/sofa/evidence/football_result_phase_2026-10-13.md (DC met
# the registered threshold: -0.0394 log-loss vs base, -0.91 pp after the
# training curve at p >= 0.70, n 121,589).
FOOTBALL_RESULT_MARKETS = "result_markets_v1"
# Operator 2026-10-14 ~14:10Z, "WŁĄCZ OD TERAZ": moved into the day built -
# 10-14 is mixed. No curve: CONFIDENCE reads the key's own Superbet lines
# (NO_LINE_EVIDENCE until a bucket holds enough), so nothing prints at first.
FOOTBALL_RESULT_MARKETS_FROM_UTC: datetime | None = datetime(
    2026, 10, 14, 14, 20, 0, tzinfo=UTC)


def football_result_markets(date: str, build_at: datetime | None = None) -> bool:
    """Does OFFER read and SHEET price the football double chance
    (FOOTBALL_RESULT_MARKETS_FROM_UTC)?"""
    if FOOTBALL_RESULT_MARKETS_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= FOOTBALL_RESULT_MARKETS_FROM_UTC.strftime("%Y-%m-%d")
            and at >= FOOTBALL_RESULT_MARKETS_FROM_UTC)


# Football 1X2 (home / away win) and draw no bet (bet.sofa.football_1x2_dnb;
# operator 2026-10-14 ~18:55Z): OFFER reads "Mecz" 1 / 2 as result_1x2 OVER
# (its UNDER the double chance leaving it out) and "Zakład bez remisu" as one
# draw_no_bet rung (OVER the home side, UNDER the away side); SHEET prices
# them from the double chance's NB goals on the pure rating centres and
# stamps the fixture's as-of season phase (`result_phase`); CONFIDENCE reads
# an early-phase men's leg from the curve class `season_early`
# (football_1x2_dnb.curve_class); SETTLE grades on the 90-minute score, a
# DNB draw a refund (DNB_DRAW_REFUND, a void leg). Adds rows, so a day >= the
# date built at or after the moment. Off (None): OFFER, SHEET and CONFIDENCE
# byte-identical. Evidence: docs/sofa/evidence/football_1x2_dnb_phase_2026-10-15.md.
FOOTBALL_RESULT_1X2_DNB = "result_1x2_dnb_v1"
# On from 2026-10-15 00:00Z (operator 2026-10-14 ~18:55Z: "ready for
# tomorrow if it passes"): draw_no_bet|OVER / |UNDER, season_early:
# draw_no_bet|OVER and women:draw_no_bet|OVER passed the one-sided holdout
# gate; every result_1x2 key failed. Until the staged curves are installed
# (operator's go) no such leg has a curve: NO_LINE_EVIDENCE, nothing prints.
FOOTBALL_RESULT_1X2_DNB_FROM_UTC: datetime | None = datetime(
    2026, 10, 15, 0, 0, tzinfo=UTC)


def football_result_1x2_dnb(date: str, build_at: datetime | None = None) -> bool:
    """Does OFFER read and SHEET price football 1X2 / draw no bet
    (FOOTBALL_RESULT_1X2_DNB_FROM_UTC)?"""
    if FOOTBALL_RESULT_1X2_DNB_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= FOOTBALL_RESULT_1X2_DNB_FROM_UTC.strftime("%Y-%m-%d")
            and at >= FOOTBALL_RESULT_1X2_DNB_FROM_UTC)


# Superbet's footballer shot-detail markets (bet.sofa.shot_detail): "Zawodnik
# - liczba (celnych) strzalow spoza pola karnego / glowa / lewa noga / prawa
# noga". OFFER reads the eight names as player markets (market_mapper.
# classify_player_market with shot_detail.MARKET_NAMES), SAMPLES asks each
# sample match's /shotmap beside its /lineups (players.squad_statistics:
# counted only where the player's shotmap shots equal his lineups
# totalShots, else a gap), SHEET prices a row with shot_detail.forecast (the
# player's last starts shrunk to his position's mean, Poisson) from the
# operator-installed config/sofa_shot_detail.json - absent: no row,
# NO_SHOT_DETAIL_FIT - rows marked `shot_detail_rule`; SETTLE grades from the
# match's shotmap. No curve is installed: CONFIDENCE reads the keys' own
# Superbet lines, NO_LINE_EVIDENCE until a bucket holds enough of them - so
# nothing prints at first. Adds rows, so a day >= the date built at or after
# the moment. Off (None, until the operator sets it): OFFER, SAMPLES, SHEET
# and SETTLE byte-identical. Evidence: docs/sofa/evidence/
# shot_detail_2026-10-14.md (staged fit data/refit_shot_detail_2026-10-14/).
SHOT_DETAIL_MARKETS = "shot_detail_v1"
# Operator 2026-10-14 ~14:10Z, "WŁĄCZ OD TERAZ": moved into the day built -
# 10-14 is mixed. The estimator file is installed (config/
# sofa_shot_detail.json), its history curve is NOT: CONFIDENCE refuses the
# legs NO_LINE_EVIDENCE until their own settled Superbet lines decide.
SHOT_DETAIL_MARKETS_FROM_UTC: datetime | None = datetime(
    2026, 10, 14, 14, 20, 0, tzinfo=UTC)


def shot_detail_markets(date: str, build_at: datetime | None = None) -> bool:
    """Does OFFER read, SAMPLES sample and SHEET price the footballer
    shot-detail markets (SHOT_DETAIL_MARKETS_FROM_UTC)?"""
    if SHOT_DETAIL_MARKETS_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= SHOT_DETAIL_MARKETS_FROM_UTC.strftime("%Y-%m-%d")
            and at >= SHOT_DETAIL_MARKETS_FROM_UTC)


# Football player props v2 (docs/sofa/evidence/
# football_player_props_v2_2026-10-21.md): OFFER reads "Zawodnik - liczba
# fauli na zawodniku" as `player_fouls_drawn_for` (players.PLAYER_METRICS,
# Sofascore /lineups `wasFouled`, a missing key a zero only where the
# opponent's team fouls bound the squad's sum - players.squad_statistics),
# SAMPLES samples his starts, SHEET prices the sample mean with the
# negative binomial (engine.NEGATIVE_BINOMIAL_METRICS), SETTLE grades from
# his own squad like every other player prop. Rows marked
# `player_props_v2_rule`. No curve is installed: CONFIDENCE reads the key's
# own Superbet lines - NO_LINE_EVIDENCE until a bucket holds enough of them
# (a staged history curve: data/refit_player_props_v2_2026-10-21/). Adds
# rows, so a day >= the date built at or after the moment. Off (None, until
# the operator sets it): OFFER, SAMPLES, SHEET and SETTLE byte-identical.
FOOTBALL_PLAYER_PROPS_V2 = "player_props_v2"
FOOTBALL_PLAYER_PROPS_V2_FROM_UTC: datetime | None = datetime(2026, 10, 21, tzinfo=UTC)


def football_player_props_v2(
    date: str, build_at: datetime | None = None
) -> bool:
    """Does OFFER read, SAMPLES sample and SHEET price the v2 footballer
    props (FOOTBALL_PLAYER_PROPS_V2_FROM_UTC)?"""
    if FOOTBALL_PLAYER_PROPS_V2_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= FOOTBALL_PLAYER_PROPS_V2_FROM_UTC.strftime("%Y-%m-%d")
            and at >= FOOTBALL_PLAYER_PROPS_V2_FROM_UTC)


# The measured sports' markets derived from the score model they already have
# (bet.sofa.shadow DERIVED_MARKETS; no new data source): hockey's double
# chance for the game and a period ("Podwójna szansa" 606, "N. tercja -
# podwójna szansa" 616 - regulation, as the 1X2 640 / 660), basketball's
# double chance for the game, a half and a quarter (regulation, as 777 / 763
# / 233400 / 779; read by name), volleyball's "<team> wygra seta", "<team>
# wygra dokładnie N set(y)" and "Dokładna liczba setów" (from the simulated
# set score, as exact_sets 785; read by name). SHADOW reads them into the
# snapshots (records marked `derived_rule`), SHADOW_SETTLE grades them,
# SPORT_CONFIDENCE prices them from the score model's simulation and reads
# the keys' own settled Superbet lines - no curve, so NO_LINE_EVIDENCE until
# a p bucket holds enough lines; nothing prints at first. Adds legs, so a day
# >= the date built at or after the moment. Off (None, until the operator
# sets it): SHADOW snapshots, SHADOW_SETTLE and SPORT_CONFIDENCE
# byte-identical. Evidence: docs/sofa/evidence/sport_derived_2026-10-14.md.
SPORT_DERIVED_MARKETS = "sport_derived_v1"
# Operator 2026-10-14 ~14:45Z ("1. 2. tak"): on from 14:50Z into the built
# day - 10-14 is mixed. No curve: these keys read only their own settled
# Superbet lines (NO_LINE_EVIDENCE until a bucket holds enough).
SPORT_DERIVED_MARKETS_FROM_UTC: datetime | None = datetime(
    2026, 10, 14, 14, 50, 0, tzinfo=UTC)


def sport_derived_markets(date: str, build_at: datetime | None = None) -> bool:
    """Do SHADOW read and SPORT_CONFIDENCE price the measured sports' derived
    markets (SPORT_DERIVED_MARKETS_FROM_UTC)?"""
    if SPORT_DERIVED_MARKETS_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= SPORT_DERIVED_MARKETS_FROM_UTC.strftime("%Y-%m-%d")
            and at >= SPORT_DERIVED_MARKETS_FROM_UTC)


# Basketball double chance as two-way pairs (defect found 2026-10-15): Superbet
# quotes basketball "Podwojna szansa" / "N. polowa - podwojna szansa" with
# only 1X and X2 (no 12; live probe 2026-10-15: 5 of 30 events, e.g. 14175125
# NBL), so the whole-group rule (cs2.complete_group "double") dropped every
# basketball double chance: 0 lines in 433 snapshots of 10-14/10-15 although
# SPORT_DERIVED_MARKETS was on and basketball:double_chance|TEAM has a curve.
# On: SHADOW pairs each quoted double-chance selection with the complementary
# outcome of the same scope's regulation 1X2 (777 / 763 / 233400 / 779; 1X
# against "2", X2 against "1", 12 against the draw) - a partition, so the
# pair is a two-way line devigged by fair_probability and its margin is
# 1/a + 1/b - 1 (football's double chance reads "Mecz" the same way,
# bet.sofa.football_result). The pair lives under its own synthetic market id
# (shadow.DC_PAIR_MARKETS, same family and scope as the double chance), the
# 1X2 outcome is never a leg nor a settled row. Records carry `dc_pair_rule`.
# Only where the double-chance group is NOT complete and only with
# SPORT_DERIVED_MARKETS on; hockey (606 / 616, all three quoted) never pairs.
# Adds legs, so a day >= the date built at or after the moment. Off: SHADOW
# snapshots, SHADOW_SETTLE and SPORT_CONFIDENCE byte-identical.
BASKETBALL_DC_PAIR = "basketball_dc_pair_v1"
BASKETBALL_DC_PAIR_FROM_UTC: datetime | None = datetime(
    2026, 10, 16, 0, 0, 0, tzinfo=UTC)


def basketball_dc_pair(date: str, build_at: datetime | None = None) -> bool:
    """Does SHADOW read a basketball double chance quoted without its whole
    group as pairs against the 1X2 (BASKETBALL_DC_PAIR_FROM_UTC)?"""
    if BASKETBALL_DC_PAIR_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= BASKETBALL_DC_PAIR_FROM_UTC.strftime("%Y-%m-%d")
            and at >= BASKETBALL_DC_PAIR_FROM_UTC)


# Nine more basketball player lines (shadow.PLAYER_V2_MARKETS; the operator
# staked "Beringer - liczba trafionych rzutów wolnych: powyżej 0.5" on 10-21,
# a market SHADOW never read): a player's free throws made / attempted, field
# goals made / attempted, two-pointers made / attempted, three-pointers
# attempted, personal fouls and turnovers - each one key of the /lineups box
# SHADOW_SETTLE already reads (shadow.player_stat_value). Posted on the NBA
# only (live probe 2026-10-22: ~14 players a game each; none on the European
# events probed). SHADOW reads them into the snapshots (records marked
# `player_v2_rule`), player_model prices them pre-game with the count model
# of every basketball player family (player_rate_v3, its installed constants
# - not fitted on these families), SHADOW_SETTLE grades them from the
# player's own row, SPORT_CONFIDENCE takes them as any player line: no
# history curve, so NO_LINE_EVIDENCE until a family's p bucket holds
# MIN_EVIDENCE_BUCKET settled pre-game lines of MIN_EVIDENCE_GAMES games
# (line_evidence.read reads no pooled offset without a curve) - nothing
# prints at first. Adds snapshot lines and SPORT_CONFIDENCE rows, so a day
# >= the date read at or after the moment. Off (None): SHADOW snapshots,
# SHADOW_SETTLE and SPORT_CONFIDENCE byte-identical. Not an epoch group of
# audit_ledger: no leg of the new families can print on its first day.
BASKETBALL_PLAYER_V2 = "basketball_player_v2"
BASKETBALL_PLAYER_V2_FROM_UTC: datetime | None = datetime(
    2026, 10, 23, 0, 0, 0, tzinfo=UTC)


def basketball_player_v2(date: str, build_at: datetime | None = None) -> bool:
    """Does SHADOW read the basketball player lines of
    shadow.PLAYER_V2_MARKETS (BASKETBALL_PLAYER_V2_FROM_UTC)?"""
    if BASKETBALL_PLAYER_V2_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= BASKETBALL_PLAYER_V2_FROM_UTC.strftime("%Y-%m-%d")
            and at >= BASKETBALL_PLAYER_V2_FROM_UTC)


# Football markets read off the incident list (bet.sofa.football_incidents):
# "1. gol" (which side scores first / nikt) as first_goal (subject "1" / "2" /
# "nikt", line 0.5, OVER only - one-sided), "Liczba czerwonych kartek" and
# "Liczba przyznanych rzutow karnych" O/U as red_cards_total /
# penalties_total. SHEET prices the first goal from the double chance's NB
# goals on the PURE rating centres (FootballForecast.centre("goals_for",
# side), r from config/sofa_football_result.json) and the counts from the
# competition's as-of full-feed rate shrunk to the gender's (no sample, no
# price; rows marked `incident_rule`); SETTLE grades from the match's
# regular-time incidents (a partial feed: no grade). The first-goal minute
# bands never reach 0.70 and are not read. No curve is installed: CONFIDENCE
# reads the keys' own Superbet lines, NO_LINE_EVIDENCE until a bucket holds
# enough of them - so nothing prints at first. Adds rows, so a day >= the
# date built at or after the moment. Off (None, until the operator sets it):
# OFFER, SAMPLES, SHEET and SETTLE byte-identical. Evidence: docs/sofa/
# evidence/football_incidents_tennis_sets_2026-10-14.md.
FOOTBALL_INCIDENT_MARKETS = "incident_markets_v1"
# Operator 2026-10-14 ~14:45Z ("1. 2. tak"): on from 14:50Z into the built
# day - 10-14 is mixed. No curve: these keys read only their own settled
# Superbet lines (NO_LINE_EVIDENCE until a bucket holds enough).
FOOTBALL_INCIDENT_MARKETS_FROM_UTC: datetime | None = datetime(
    2026, 10, 14, 14, 50, 0, tzinfo=UTC)


def football_incident_markets(date: str, build_at: datetime | None = None) -> bool:
    """Does OFFER read and SHEET price the football first goal, red cards and
    penalties (FOOTBALL_INCIDENT_MARKETS_FROM_UTC)?"""
    if FOOTBALL_INCIDENT_MARKETS_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= FOOTBALL_INCIDENT_MARKETS_FROM_UTC.strftime("%Y-%m-%d")
            and at >= FOOTBALL_INCIDENT_MARKETS_FROM_UTC)


# Tennis set winner and exact score in sets (bet.sofa.tennis_sets), the match
# winner's pattern: OFFER reads "X. set - zwyciezca" ("1. set - <name>" /
# "2. set - <name>") as set1_won_for / set2_won_for (subject the listing's
# first name, line 0.5, two-sided) and the tennis "Dokladny wynik" ("2:0" ..
# "0:2") as set_score (subject "<first name> a:b", OVER only - one-sided);
# SHEET prices them from the as-of rating's neighbours (best of three only;
# rows marked `set_market_rule`); SETTLE grades from the listing's set
# scores. No curve is installed: CONFIDENCE reads the keys' own Superbet
# lines, NO_LINE_EVIDENCE until a bucket holds enough of them. Adds rows, so
# a day >= the date built at or after the moment. Off (None, until the
# operator sets it): OFFER, SAMPLES, SHEET and SETTLE byte-identical.
# Evidence: docs/sofa/evidence/football_incidents_tennis_sets_2026-10-14.md.
TENNIS_SET_MARKETS = "tennis_set_markets_v1"
# Operator 2026-10-14 ~14:45Z ("1. 2. tak"): on from 14:50Z into the built
# day - 10-14 is mixed. No curve: these keys read only their own settled
# Superbet lines (NO_LINE_EVIDENCE until a bucket holds enough).
TENNIS_SET_MARKETS_FROM_UTC: datetime | None = datetime(
    2026, 10, 14, 14, 50, 0, tzinfo=UTC)


def tennis_set_markets(date: str, build_at: datetime | None = None) -> bool:
    """Does OFFER read and SHEET price the tennis set winner and exact sets
    score (TENNIS_SET_MARKETS_FROM_UTC)?"""
    if TENNIS_SET_MARKETS_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= TENNIS_SET_MARKETS_FROM_UTC.strftime("%Y-%m-%d")
            and at >= TENNIS_SET_MARKETS_FROM_UTC)


# Football league strength in international club competitions (operator go
# 2026-10-15; docs/sofa/history/RAPORT_SILA_PUCHAROW_2026-10-16.md). The
# rating's league-strength book links leagues mostly through their own lower
# divisions and orders top flights wrongly: on 3,740 cross-league matches of
# the UEFA / AFC / CONMEBOL / CAF / CONCACAF club cups from 2024-07 it
# under-rated the side from the stronger league by +5.2 pp P(win)
# [+3.6, +7.0] (docs/sofa/evidence/cross_league_cups_2026-10-15.md). From
# this moment the RatingBook SHEET prices with carries a per-(domestic
# competition, metric) correction learnt only from those cups' cross-league
# matches, inside the book's own update (football_rating.RatingBook
# cup_competitions / cup_eta; the cup list and step in
# config/sofa_cup_strength.json, bet.sofa.cup_strength), and a fixture of
# such a cup reads it on top of the domains' sigma. The cache replay carries
# the same rule (calibrate_from_cache --cup-strength) and the football curves
# are refitted on it. Rows priced under it carry `cup_strength_rule`, so a
# rebuild re-runs SHEET on a sheet of the other rule. None: the book as it
# was, byte for byte.
FOOTBALL_CUP_STRENGTH = "cup_strength_v1"
FOOTBALL_CUP_STRENGTH_FROM_UTC: datetime | None = datetime(
    2026, 10, 16, 0, 0, tzinfo=UTC)
FOOTBALL_CUP_STRENGTH_MARKER = (
    "cup_strength_rule", FOOTBALL_CUP_STRENGTH, "football")


def football_cup_strength(date: str, build_at: datetime | None = None) -> bool:
    """Does the football rating read the league strength learnt in
    international club cups (FOOTBALL_CUP_STRENGTH_FROM_UTC)?"""
    if FOOTBALL_CUP_STRENGTH_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= FOOTBALL_CUP_STRENGTH_FROM_UTC.strftime("%Y-%m-%d")
            and at >= FOOTBALL_CUP_STRENGTH_FROM_UTC)


# B15's sample correction read through the cup league strength: a past match
# of an international club cup in a football side's sample, and today's cup
# fixture, take the book's cup correction into the gaps
# (opponent_correction.SampleCorrector.cup_aware; the observation's and the
# fixture's competition). Rides on SAMPLE_OPPONENT_CORRECTION and
# FOOTBALL_CUP_STRENGTH; only shots_for / shots_total move (the corrected
# metrics with a cup step). MEASURED, NOT SWITCHED ON (2026-10-15,
# measure_sample_opponent_correction.py history --cup-strength --bases
# shots_for; docs/sofa/evidence/cross_league_cups_2026-10-15.md): shots_for
# calibrated log-loss K - C -0.00006 [-0.00012, -0.000003] on 26,384 rows,
# -0.00044 [-0.00088, -0.000004] on rows with a cup, shots_total zero. Better
# but small; it changes p, so it goes on with the football refit whose replay
# carries it (calibrate_from_cache --sample-cup-strength).
SAMPLE_CUP_STRENGTH = "sample_cup_v1"
# On from 2026-10-16 04:10Z with the football refit whose replay carries it
# (data/refit_2026-10-16b, installed before 10-16's build - not a mixed day;
# the operator's standing go of 2026-10-15 evening).
SAMPLE_CUP_STRENGTH_FROM_UTC: datetime | None = datetime(
    2026, 10, 16, 4, 10, tzinfo=UTC)
SAMPLE_CUP_STRENGTH_MARKER = ("sample_cup_rule", SAMPLE_CUP_STRENGTH, "football")


def sample_cup_strength(date: str, build_at: datetime | None = None) -> bool:
    """Does the football sample correction read the cup league strength
    (SAMPLE_CUP_STRENGTH_FROM_UTC)?"""
    if SAMPLE_CUP_STRENGTH_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= SAMPLE_CUP_STRENGTH_FROM_UTC.strftime("%Y-%m-%d")
            and at >= SAMPLE_CUP_STRENGTH_FROM_UTC)



# The goals stretch (bet.sofa.goals_stretch): SHEET's football goals centre
# (rating blended with the shrunk sample) pulls a mismatch toward the middle
# - the favourite's goals too low, the outsider's too high, a lopsided
# match's total too low. From this moment the centre of a market of
# goals_stretch.GOALS_STRETCH_MARKETS with coefficients in
# config/sofa_goals_stretch.json is multiplied by exp(beta x s) (a side's
# goals, s its expected goal difference from the rating's goals book,
# FootballForecast.supremacy) or exp(g1 x |s| + g2 x s^2) (a total, s the
# home side's), on the same blended centre GAME_STATE multiplies, in SHEET
# and in the cache replay (calibrate_from_cache --goals-stretch). Measured
# 2026-10-17 on the history replay, walk-forward NB log-loss better on all
# six markets with the interval below zero (goals_1h_for -0.0074 [-0.0078,
# -0.0070]); docs/sofa/evidence/goals_stretch_2026-10-17.md. It changes p,
# so what prints: the football curves are to be refitted on a replay
# carrying it. Rows priced under it carry `goals_stretch_rule` (every
# football row, like the other football markers), so a rebuild re-runs SHEET
# on a sheet of the other rule. None: the centre as it was, byte for byte -
# OFF, the operator decides the moment. goals_stretch_v2 (2026-10-17, before
# the switch was ever set): a market may carry one coefficient set per
# season phase (the phase SEASON_PHASE reads; goals_for's slope is 0.018
# early vs 0.056-0.064 later), a phase the file lacks - and a match with no
# phase, unless the file names `none` - reading the market's single set.
FOOTBALL_GOALS_STRETCH = "goals_stretch_v2"
FOOTBALL_GOALS_STRETCH_FROM_UTC: datetime | None = datetime(
    2026, 10, 17, 13, 37, tzinfo=UTC)
FOOTBALL_GOALS_STRETCH_MARKER = (
    "goals_stretch_rule", FOOTBALL_GOALS_STRETCH, "football")


def football_goals_stretch(date: str, build_at: datetime | None = None) -> bool:
    """Does a football goals centre carry the supremacy stretch
    (FOOTBALL_GOALS_STRETCH_FROM_UTC)?"""
    if FOOTBALL_GOALS_STRETCH_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= FOOTBALL_GOALS_STRETCH_FROM_UTC.strftime("%Y-%m-%d")
            and at >= FOOTBALL_GOALS_STRETCH_FROM_UTC)


# The count stretch (bet.sofa.count_stretch): the same mismatch compression
# in the football count centres GAME_STATE does not touch. From this moment
# the centre of a market of count_stretch.COUNT_STRETCH_MARKETS with
# coefficients in config/sofa_count_stretch.json (half corners, shots by
# half, shots on target, offsides, saves, throw-ins, goal kicks; the shots
# on target / saves / throw-ins totals) is multiplied by exp(beta x s [+
# beta2 x s^2]) (a side, s its expected goal difference) or exp(g1 |s| + g2
# s^2) (a total, s the home side's), after GAME_STATE and the venue prior,
# in SHEET and in the cache replay (calibrate_from_cache --count-stretch).
# Measured 2026-10-17 on the history replay of SHEET's count centre:
# walk-forward NB log-loss below zero on all 16; after the bucket curve both
# out-of-sample checks (pre-2026 fit -> 2026, 2026-H1 fit -> 2026-07..)
# below zero on all 16; the raw NB of a fixed fit not significant for
# shots_1h_for (pre-2026 fit) and offsides_for (2026-H1 fit);
# offsides_1h_for left out (after-curve 2026-H1 check not below zero);
# docs/sofa/evidence/count_stretch_2026-10-17.md. It changes p:
# the football curves are to be refitted on a replay carrying it. Rows
# priced under it carry `count_stretch_rule` (every football row), so a
# rebuild re-runs SHEET on a sheet without it. None: OFF, byte for byte.
FOOTBALL_COUNT_STRETCH = "count_stretch_v1"
FOOTBALL_COUNT_STRETCH_FROM_UTC: datetime | None = datetime(
    2026, 10, 17, 13, 37, tzinfo=UTC)
FOOTBALL_COUNT_STRETCH_MARKER = (
    "count_stretch_rule", FOOTBALL_COUNT_STRETCH, "football")


def football_count_stretch(date: str, build_at: datetime | None = None) -> bool:
    """Does a football count centre carry the supremacy stretch
    (FOOTBALL_COUNT_STRETCH_FROM_UTC)?"""
    if FOOTBALL_COUNT_STRETCH_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= FOOTBALL_COUNT_STRETCH_FROM_UTC.strftime("%Y-%m-%d")
            and at >= FOOTBALL_COUNT_STRETCH_FROM_UTC)


# The referee term (bet.sofa.referees): from this moment a football cards /
# fouls centre (the markets of config/sofa_referee_effect.json:
# cards_points_*, fouls_* and their halves) is multiplied by
# ratio ** beta, ratio the fixture referee's as-of shrunk ratio of his
# previous matches in our history (each match's count over its
# competition's as-of mean, (sum + K) / (n + K)), after GAME_STATE and the
# count stretch, in SHEET. The referee is the stored label
# (sofa_event_referee, backfill_referees.py) or the cached /event RESOLVE /
# FIXTURE_CHECK wrote; none named: multiplier 1, `referee_read.status`
# NO_REFEREE. Measured 2026-10-21 on the history replay of SHEET's centre
# (fit < 2026, test 2026): docs/sofa/evidence/referee_effect_2026-10-21.md.
# It changes p: the football curves are to be refitted on a replay carrying
# it (not wired into calibrate_from_cache yet - the evidence file says what
# a refit needs). Rows priced under it carry `referee_rule` (every football
# row). None: OFF, byte for byte.
FOOTBALL_REFEREE = "referee_v1"
FOOTBALL_REFEREE_FROM_UTC: datetime | None = datetime(2026, 10, 21, tzinfo=UTC)
FOOTBALL_REFEREE_MARKER = ("referee_rule", FOOTBALL_REFEREE, "football")


def football_referee(date: str, build_at: datetime | None = None) -> bool:
    """Does a football cards / fouls centre carry the referee term
    (FOOTBALL_REFEREE_FROM_UTC)?"""
    if FOOTBALL_REFEREE_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= FOOTBALL_REFEREE_FROM_UTC.strftime("%Y-%m-%d")
            and at >= FOOTBALL_REFEREE_FROM_UTC)


# The player shots stretch (bet.sofa.player_stretch): a footballer's centre
# is the mean of his starts against every kind of opponent. From this moment
# the centre of player_shots_for / player_shots_on_target_for with a beta in
# config/sofa_player_stretch.json is multiplied by exp(beta x s), s his own
# side's expected goal difference (FootballForecast.supremacy of the side
# his sample was matched in), in SHEET and in the cache replay of the player
# rows (calibrate_from_cache --player-stretch). Measured 2026-10-17 on the
# starts-only player rows (fit before 2026, tested on 2026): beta 0.126 /
# 0.117, log-loss better on the ladder lines;
# docs/sofa/evidence/player_stretch_2026-10-17.md. It changes p: the player
# curves are to be refitted on a replay carrying it. Rows priced under it
# carry `player_stretch_rule` (every football row), so a rebuild re-runs
# SHEET on a sheet without it. None: OFF, byte for byte.
FOOTBALL_PLAYER_STRETCH = "player_stretch_v1"
FOOTBALL_PLAYER_STRETCH_FROM_UTC: datetime | None = datetime(
    2026, 10, 17, 13, 37, tzinfo=UTC)
FOOTBALL_PLAYER_STRETCH_MARKER = (
    "player_stretch_rule", FOOTBALL_PLAYER_STRETCH, "football")


def football_player_stretch(date: str, build_at: datetime | None = None) -> bool:
    """Does a footballer's shots centre carry the supremacy stretch
    (FOOTBALL_PLAYER_STRETCH_FROM_UTC)?"""
    if FOOTBALL_PLAYER_STRETCH_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= FOOTBALL_PLAYER_STRETCH_FROM_UTC.strftime("%Y-%m-%d")
            and at >= FOOTBALL_PLAYER_STRETCH_FROM_UTC)


# The footballer share model (bet.sofa.player_share): from this moment the
# centre of a player market of config/sofa_player_share.json (shots, shots on
# target, fouls) is his shrunk share of his side's volume over his sampled
# starts x his side's team centre today (the centre SHEET prices the side's
# shots_for / fouls_for row with: rating, game state, opponent correction),
# x his shrunk accuracy
# for shots on target, in place of the mean of his starts x the player
# stretch. A player whose side has no team row (Superbet quotes no team
# shots) keeps the old centre and says so. Measured 2026-10-21 (history
# replay out of sample and Superbet's settled lines 10-12..10-19):
# docs/sofa/evidence/football_player_share_2026-10-21.md. It changes p of the
# player rows; the player curves were fitted on the old p. Rows priced under
# it carry `player_share_rule` (every football row), so a rebuild re-runs
# SHEET on a sheet without it. The fitted file is staged, not installed: it
# goes to config/ with the switch. None: OFF, byte for byte.
FOOTBALL_PLAYER_SHARE = "player_share_v1"
FOOTBALL_PLAYER_SHARE_FROM_UTC: datetime | None = datetime(2026, 10, 21, tzinfo=UTC)
FOOTBALL_PLAYER_SHARE_MARKER = (
    "player_share_rule", FOOTBALL_PLAYER_SHARE, "football")


def football_player_share(date: str, build_at: datetime | None = None) -> bool:
    """Is a footballer's shots / SOT / fouls centre his share of his side's team
    centre (FOOTBALL_PLAYER_SHARE_FROM_UTC)?"""
    if FOOTBALL_PLAYER_SHARE_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= FOOTBALL_PLAYER_SHARE_FROM_UTC.strftime("%Y-%m-%d")
            and at >= FOOTBALL_PLAYER_SHARE_FROM_UTC)


# The closeness stretch (bet.sofa.closeness_stretch): GAME_STATE and the
# count stretch move a count centre with the sign of the expected goal
# difference; nothing reads how close the match is. From this moment the
# centre of a market of closeness_stretch.CLOSENESS_MARKETS with
# coefficients in config/sofa_closeness_stretch.json (cards_points_for /
# cards_points_total |s| + s^2: bookings peak in a close match; shots_total /
# shots_1h_total |s|) is multiplied by exp(g1 |s| + g2 s^2), s the home
# side's expected goal difference, after
# GAME_STATE, the venue prior and the count stretch, in SHEET and in the
# cache replay (calibrate_from_cache --closeness-stretch). Measured
# 2026-10-21 on the history replay of SHEET's live count centre: walk-forward
# NB log-loss below zero on all four, not worse through the installed curves
# on two fixed splits (also at >= 0.70);
# docs/sofa/evidence/football_closeness_stretch_2026-10-21.md. It changes p:
# a refit should carry --closeness-stretch. Rows priced under it carry
# `closeness_rule` (every football row), so a rebuild re-runs SHEET on a
# sheet without it. None: OFF, byte for byte.
FOOTBALL_CLOSENESS_STRETCH = "closeness_stretch_v1"
FOOTBALL_CLOSENESS_STRETCH_FROM_UTC: datetime | None = datetime(
    2026, 10, 21, tzinfo=UTC)
FOOTBALL_CLOSENESS_STRETCH_MARKER = (
    "closeness_rule", FOOTBALL_CLOSENESS_STRETCH, "football")


def football_closeness_stretch(date: str, build_at: datetime | None = None) -> bool:
    """Does a football count centre carry the closeness term
    (FOOTBALL_CLOSENESS_STRETCH_FROM_UTC)?"""
    if FOOTBALL_CLOSENESS_STRETCH_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= FOOTBALL_CLOSENESS_STRETCH_FROM_UTC.strftime("%Y-%m-%d")
            and at >= FOOTBALL_CLOSENESS_STRETCH_FROM_UTC)


# Football "or" result markets, the underdog's European handicap and the
# double chance & goals pairs that clear their gate
# (bet.sofa.football_score_markets): OFFER reads "Mecz lub liczba goli",
# "<team> / Remis lub powyżej / poniżej X goli w meczu", "Obie drużyny
# strzelą gola lub powyżej L gola", "... lub obie drużyny strzelą gola",
# "... lub którakolwiek drużyna zachowa czyste konto", "Handicap" (+1.5 /
# +2.5 / +3.5) and "Podwójna szansa & liczba goli" 12 & powyżej / 1X &
# poniżej; SHEET prices the OVER of each from the double chance's NB goals
# on the pure rating centres (rows marked `score_market_rule`); CONFIDENCE
# reads each key's own history curve (rating-only); SETTLE grades the
# event on the 90-minute score at 0.5. Adds rows, so a day >= the date built
# at or after the moment. Off (None): OFFER, SHEET, CONFIDENCE byte-identical.
# Evidence: docs/sofa/evidence/football_score_markets_2026-10-16.md.
FOOTBALL_SCORE_MARKETS = "score_markets_v1"
# Moved by the operator into the built day 2026-10-16 ("Włącz od teraz",
# 07:46Z; CLAUDE.md "Changing the pipeline" 3): 10-16 is mixed - its legs
# printed before stay locked, a rebuild from 07:46Z re-reads OFFER and
# re-runs SHEET for the new rows (bet.sofa.rebuild_plan).
FOOTBALL_SCORE_MARKETS_FROM_UTC: datetime | None = datetime(
    2026, 10, 16, 7, 46, tzinfo=UTC)


def football_score_markets(date: str, build_at: datetime | None = None) -> bool:
    """Does OFFER read and SHEET price the football score markets
    (FOOTBALL_SCORE_MARKETS_FROM_UTC)?"""
    if FOOTBALL_SCORE_MARKETS_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= FOOTBALL_SCORE_MARKETS_FROM_UTC.strftime("%Y-%m-%d")
            and at >= FOOTBALL_SCORE_MARKETS_FROM_UTC)


# The complement of a tennis exact sets score (tennis_sets.SET_SCORE_NOT):
# OFFER reads "<X> wygra seta", "<X> wygra bez straty seta", "<X> liczba
# setów" 0.5 and "Handicap setowy" ±1.5 as one two-sided rung "<X> 0:2" /
# "<X> 2:0" (OVER = not that score); SHEET prices the OVER as 1 - the score's
# share of the rating's neighbours (rides on TENNIS_SET_MARKETS; best of
# three only; rows marked `set_complement_rule`); CONFIDENCE reads its own
# history curve; SETTLE grades it from the listing's set scores. Off (None):
# byte-identical. Evidence: docs/sofa/evidence/football_score_markets_2026-10-16.md.
TENNIS_SET_COMPLEMENTS = "set_complements_v1"
# with FOOTBALL_SCORE_MARKETS: 2026-10-16 07:46Z, 10-16 mixed
TENNIS_SET_COMPLEMENTS_FROM_UTC: datetime | None = datetime(
    2026, 10, 16, 7, 46, tzinfo=UTC)


def tennis_set_complements(date: str, build_at: datetime | None = None) -> bool:
    """Does OFFER read and SHEET price the tennis exact-score complements
    (TENNIS_SET_COMPLEMENTS_FROM_UTC; rides on TENNIS_SET_MARKETS)?"""
    if TENNIS_SET_COMPLEMENTS_FROM_UTC is None or not tennis_set_markets(
            date, build_at):
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= TENNIS_SET_COMPLEMENTS_FROM_UTC.strftime("%Y-%m-%d")
            and at >= TENNIS_SET_COMPLEMENTS_FROM_UTC)


# History curves per line (bet.sofa.line_curves): a men's football leg of a
# key in config/sofa_line_curves.json reads its direction's curve at its own
# line (Calibration.realised(..., line=)), a line bucket the fit did not fill
# the pooled direction curve as before. Measured 2026-10-18 on the
# 2026-10-17 replay, out of sample at Superbet's quoted lines and p >= 0.70:
# log-loss -6.4e-4 [-7.0, -5.8] over all keys, the 33 listed keys each below
# zero with the interval; on the live offered rows of 10-09..10-17 the
# printable gap -1.09 -> -0.57 pp, ROI unchanged (-4.54% / -4.53%), 1,823
# legs fewer and 596 more (docs/sofa/evidence/line_curves_2026-10-18.md).
# Changes what prints: planned for 2026-10-19 00:00Z (operator's standing go),
# moved by the operator into the built day 2026-10-18 at 12:48Z
# ("przebudować już dzisiaj kupon, włączyć to na dzisiaj"): 10-18 is mixed,
# its legs printed before stay locked. Off (None): byte-identical.
LINE_CURVES_FROM_UTC: datetime | None = datetime(2026, 10, 18, 12, 48, tzinfo=UTC)


def line_curves(date: str, build_at: datetime | None = None) -> bool:
    """Does CONFIDENCE read a men's football leg's curve at its own line
    (LINE_CURVES_FROM_UTC)? Judged on the day built and the build clock."""
    if LINE_CURVES_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= LINE_CURVES_FROM_UTC.strftime("%Y-%m-%d")
            and at >= LINE_CURVES_FROM_UTC)


# Football player-prop coverage (SAMPLES; docs/sofa/evidence/
# football_player_coverage_2026-10-21.md). Three fixes behind one switch:
#  (a) a missing `onTargetScoringAttempt` is proven zero by the shots
#      decomposition WITHOUT `hitWoodwork` (players.SHOTS_IDENTITY_PARTS):
#      213,047 of 213,047 appearing footballers close it, the old four-part
#      identity refused the 2,116 who hit the woodwork;
#  (b) a footballer with fewer than min_sample (5) starts in his team's last
#      sample_n (10) matches is sampled from his newest starts (at most
#      sample_n) in the team's last PLAYER_WIDE_SAMPLE_N (20): on the history
#      replay 08-01..10-19 those rows realise like today's at the installed
#      curve (-0.1 pp [-0.6, +0.5] at confidence >= 0.70, 24,531 rows) and
#      beat pricing his 3-4 starts of the last ten (log-loss -0.034
#      [-0.039, -0.029]);
#  (c) two name fallbacks after the surname rule, 0 wrong men on 23,666
#      matched (player, squad) pairs 10-12..10-20: the Polish / English
#      transliteration (players.match_player_by_transliteration) and the
#      surname in the middle of a full Spanish / Portuguese name
#      (players.match_player_by_inner_surname).
# Adds player samples: changes what prints - a day >= the date, built at or
# after the moment. Off (None): byte-identical.
FOOTBALL_PLAYER_COVERAGE_FROM_UTC: datetime | None = datetime(2026, 10, 21, tzinfo=UTC)


def football_player_coverage(date: str, build_at: datetime | None = None) -> bool:
    """Does SAMPLES widen a footballer's thin sample, prove a woodwork SOT
    zero and try the two extra name rules (FOOTBALL_PLAYER_COVERAGE_FROM_UTC)?"""
    if FOOTBALL_PLAYER_COVERAGE_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= FOOTBALL_PLAYER_COVERAGE_FROM_UTC.strftime("%Y-%m-%d")
            and at >= FOOTBALL_PLAYER_COVERAGE_FROM_UTC)


# Football statistic variants of metrics SHEET already samples
# (market_mapper.classify_stat_variant): OFFER reads "Każda drużyna powyżej X
# rzutów z autu" / "... wybić od bramki" and "Każda z drużyn powyżej X
# odbiorów" as both_over_throw_ins / both_over_goal_kicks / both_over_tackles,
# "Strzały - Handicap" as handicap_shots and "1. / 2. połowa - liczba strzałów
# - handicap" as handicap_shots_1h / handicap_shots_2h. SHEET prices them with
# the existing joint of the two sides' samples (bet.sofa.derived, as every
# both_over_ / handicap_ market), SETTLE grades them with the derived path
# (min of the sides / the side's margin, regular-time statistics). No curve:
# CONFIDENCE reads their own Superbet lines, NO_LINE_EVIDENCE until a bucket
# holds enough. A football fixture only, tried after every other classifier
# refused the odd. Adds rungs (and so SAMPLES asks the side metrics), rows
# and possibly legs: a day >= the date built at or after the moment. Off
# (None, until the main session / operator sets it): OFFER, SAMPLES, SHEET,
# CONFIDENCE byte-identical. Evidence:
# docs/sofa/evidence/football_stat_variants_2026-10-21.md.
FOOTBALL_STAT_VARIANTS_FROM_UTC: datetime | None = datetime(2026, 10, 21, tzinfo=UTC)


def football_stat_variants(date: str, build_at: datetime | None = None) -> bool:
    """Does OFFER read the football statistic variants
    (FOOTBALL_STAT_VARIANTS_FROM_UTC)? Judged on the day built and the build
    clock."""
    if FOOTBALL_STAT_VARIANTS_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= FOOTBALL_STAT_VARIANTS_FROM_UTC.strftime("%Y-%m-%d")
            and at >= FOOTBALL_STAT_VARIANTS_FROM_UTC)


# Football card points by half, red cards and penalties by side / half, both
# teams carded red (bet.sofa.football_card_halves): OFFER reads "1. / 2.
# połowa - [<T>] liczba kartek" (cards_points_1h_total / _1h_for / _2h_total /
# _2h_for), "1. / 2. połowa - najwięcej kartek" and "... - liczba kartek -
# handicap" (most_ / handicap_cards_points_1h / _2h), "Liczba czerwonych
# kartek <T>", "1.połowa - liczba czerwonych kartek [<T>]", "<T> - liczba
# przyznanych rzutów karnych", "1.połowa - [<T> -] liczba przyznanych rzutów
# karnych" and "Obie drużyny otrzymają czerwoną kartkę". SHEET prices the
# card halves as an NB count on the side's full-match card-points rating
# centre x the competition's as-of half share, the events from the
# competition's as-of rate (no sample, no price; rows marked
# `incident_rule` = FOOTBALL_CARD_HALVES); SETTLE grades through
# extract_metric (metrics.CARD_INCIDENT_SCOPES: each card in the half it was
# shown in - the documented assumption for a two-yellow dismissal across the
# interval). No curve is installed: CONFIDENCE reads the keys' own Superbet
# lines, NO_LINE_EVIDENCE until a bucket holds enough of them. Adds rows, so
# a day >= the date built at or after the moment. Off (None, until the main
# session sets it): OFFER, SAMPLES, SHEET and SETTLE byte-identical.
# Evidence: docs/sofa/evidence/football_card_halves_2026-10-21.md.
FOOTBALL_CARD_HALVES = "card_halves_v1"
FOOTBALL_CARD_HALVES_FROM_UTC: datetime | None = datetime(2026, 10, 21, tzinfo=UTC)


def football_card_halves(date: str, build_at: datetime | None = None) -> bool:
    """Does OFFER read and SHEET price the football card halves and the
    side / half red cards and penalties (FOOTBALL_CARD_HALVES_FROM_UTC)?"""
    if FOOTBALL_CARD_HALVES_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= FOOTBALL_CARD_HALVES_FROM_UTC.strftime("%Y-%m-%d")
            and at >= FOOTBALL_CARD_HALVES_FROM_UTC)


# --- Football card halves: the full-match terms and the side events' game
# state (2026-10-21, audit 2026-10-21) ---------------------------------------
# With FOOTBALL_CARD_HALVES on: a side's half card-points centre is its
# full-match LIVE cards_points_for centre (the sheet's: sample / rating blend
# x GAME_STATE x the referee term x the closeness stretch) x the half share,
# instead of the raw rating centre x the share (no cards_points_for row for
# the side: the rating centre x the same three terms); penalties_for /
# penalties_1h_for / red_cards_for at 0.5 scale the competition's intensity
# -ln(1 - p) by exp(beta x the side's expected goal difference)
# (football_card_halves.SIDE_EVENT_SUP_BETA). Measured walk forward, out of
# sample (fit 2025-08-01..02-28, test 03-01..10-13, match bootstrap): card
# halves side log-loss -0.0053 [-0.0065, -0.0039] (1H) / -0.0087 [-0.0105,
# -0.0067] (2H); penalties_for -0.0037 [-0.0043, -0.0031], penalties_1h_for
# -0.0018 [-0.0022, -0.0013], red_cards_for -0.0007 [-0.0010, -0.0003].
# Rows marked `incident_rule` = FOOTBALL_CARD_HALVES_TERMS. Changes p (and
# what prints), so from a day's 00:00Z; off (None): card_halves_v1 as it was.
# Evidence: docs/sofa/evidence/football_card_halves_terms_2026-10-21.md.
FOOTBALL_CARD_HALVES_TERMS = "card_halves_terms_v1"
FOOTBALL_CARD_HALVES_TERMS_FROM_UTC: datetime | None = datetime(
    2026, 10, 21, tzinfo=UTC)


def football_card_halves_terms(date: str, build_at: datetime | None = None) -> bool:
    """Do the card halves read the full-match live centre and the side
    events their game state (FOOTBALL_CARD_HALVES_TERMS_FROM_UTC)?"""
    if FOOTBALL_CARD_HALVES_TERMS_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= FOOTBALL_CARD_HALVES_TERMS_FROM_UTC.strftime("%Y-%m-%d")
            and at >= FOOTBALL_CARD_HALVES_TERMS_FROM_UTC)


# --- RESOLVE: a reserve / youth side searched again by its board name
# (2026-10-21) ---------------------------------------------------------------
# resolve.search_query strips our "(r)" marker, so "Atlas U21" was searched as
# "atlas", the senior Atlas FC filled the candidates and Atlas FC U21
# (1111909) never reached them. On: a side below the senior squad whose
# marker-free search matched nothing and held no candidate of its level is
# searched again with Superbet's name (resolve.squad_retry_queries) and only
# candidates of its own level are tried (resolve.squad_level_candidate); the
# fixture still needs the opponent and the kickoff, as every pair does.
# Measured live 2026-10-21 (scripts/sofa/measure_squad_search.py) on the 168
# distinct squad sides of 138 football board entries RESOLVE lost 10-07..10-21:
# the plain search held a candidate of the side's level for 71, the retry for
# 25 more; RESOLVE replayed on a DB copy, retry off vs on: +6 fixtures, each
# right by eye, 0 changed, 0 lost. Adds fixtures (and what prints), so from the
# next day's 00:00Z;
# SHADOW_SETTLE (resolve_entity with record_miss=False) reads it at once - a
# settle grades only the pinned id. Evidence:
# docs/sofa/history/RAPORT_RESOLVE_REZERWY_2026-10-21.md.
# Moved by the operator ("rob wszystko zeby zaczelo dzialac od dzisiaj",
# 2026-10-21) from 2026-10-22 00:00Z to 2026-10-21 09:20Z: 10-21 is mixed
# (ledger group "10-21 mieszany"); the late RESOLVE pass reads it.
SQUAD_SEARCH_RETRY_FROM_UTC: datetime | None = datetime(
    2026, 10, 21, 9, 20, tzinfo=UTC)


def squad_search_retry(date: str, build_at: datetime | None = None) -> bool:
    """Does RESOLVE search a reserve / youth side again by its board name
    (SQUAD_SEARCH_RETRY_FROM_UTC)?"""
    if SQUAD_SEARCH_RETRY_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= SQUAD_SEARCH_RETRY_FROM_UTC.strftime("%Y-%m-%d")
            and at >= SQUAD_SEARCH_RETRY_FROM_UTC)


# --- RESOLVE: a late pass for the board entries the morning could not bridge
# (2026-10-21) ---------------------------------------------------------------
# RESOLVE runs once, in the morning; an ITF match Sofascore creates after it
# never reached a fixture. Measured 2026-10-21 (main session, read-only):
# 65 tennis board entries 10-07..10-20 never bridged while their game later
# sat in a known player's listing, 39 of them with a Sofascore id above every
# id that day's RESOLVE bridged (created after the run; football 4); a live
# replay at 08:40Z resolved 2 of the day's not-started unbridged tennis
# entries with today's code and no alias. On: a rebuild while the day is live
# re-asks RESOLVE for the board entries with no fixture whose start is ahead
# (bet.sofa.late_resolve, scripts/sofa/run_late_resolve.py) - listings read
# fresh, an unverified name's miss still honoured - and carries only the NEW
# fixtures through OFFER -> SAMPLES -> SHEET (merged, old rows untouched).
# Adds fixtures (and what prints). Moved on by the operator into the built
# day 2026-10-21 ("Włączaj od razu!") at the minute below: 10-21 is mixed
# (audit_ledger "10-21 mieszany"); legs printed before stay locked.
# Evidence: docs/sofa/history/RAPORT_POZNY_RESOLVE_2026-10-21.md.
LATE_RESOLVE_FROM_UTC: datetime | None = datetime(2026, 10, 21, 8, 48, tzinfo=UTC)


def late_resolve(date: str, build_at: datetime | None = None) -> bool:
    """Does a rebuild re-ask RESOLVE for the day's unbridged board entries
    that have not started (LATE_RESOLVE_FROM_UTC)?"""
    if LATE_RESOLVE_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= LATE_RESOLVE_FROM_UTC.strftime("%Y-%m-%d")
            and at >= LATE_RESOLVE_FROM_UTC)


# --- RESOLVE: an entity miss counts for its own day only (2026-10-21) --------
# A name RESOLVE failed to find was not searched again for 7 days
# (entity_miss_ttl_min). Measured 2026-10-21 on the football board entries of
# 10-13..10-20 RESOLVE never bridged with neither side known (127): 11 were
# names a miss from an earlier fixture blocked while Sofascore had the game
# (Tripoli SC - Al Akhaa Ahli Aley 17182512, CS Hammam-Lif - JS Omrane
# 17314079, FK Istiklol - Al Arabi 16875760); and the late RESOLVE pass could
# not re-ask the ITF matches Sofascore listed after the morning (Ravasio -
# Bouchelaghem, Sharma - Aggarwal: misses of 10-20 05:40Z). On: a miss counts
# only when recorded on the fixture's kickoff day (UTC); in the late pass
# only when younger than late_resolve.LATE_LISTING_TTL_MIN. Costs a search per
# unbridged name per day (the gap list, ~30 names). Ordered on at once by the
# operator 2026-10-21; 10-21 is mixed. Evidence:
# docs/sofa/history/RAPORT_RESOLVE_PUDLA_2026-10-21.md.
ENTITY_MISS_PER_DAY_FROM_UTC: datetime | None = datetime(
    2026, 10, 21, 9, 20, tzinfo=UTC)


def entity_miss_per_day(date: str, build_at: datetime | None = None) -> bool:
    """Does an entity miss count for its own day only
    (ENTITY_MISS_PER_DAY_FROM_UTC)?"""
    if ENTITY_MISS_PER_DAY_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= ENTITY_MISS_PER_DAY_FROM_UTC.strftime("%Y-%m-%d")
            and at >= ENTITY_MISS_PER_DAY_FROM_UTC)


# --- RESOLVE: the searched anchor (2026-10-21) --------------------------------
# A football pair neither of whose sides is a verified entity was lost when the
# searched side's only game sat at Superbet's start but the opponent's name
# scored under 82 (Gabala - Sabah Baku as Qebele FK - Sabah FK, FK Jonava -
# Baltijos Futbolo Akademija; 28 board entries 10-13..10-20). On: the K8 day
# anchor for a SEARCHED side (resolve.searched_anchor_event: a candidate named
# as the side at part_score >= 90, same squad level, its one game within 60 min,
# F25 orientation, gender, not postponed) when the opponent agrees weakly
# (resolve.searched_anchor_agreement: its own search lands on the other side,
# or part_score >= 65, or a shared distinctive word within 15 min) and its own
# search names no OTHER team strongly (veto: Sutton Coldfield Town, Imigresen).
# Measured 2026-10-21 (scripts/sofa/measure_searched_anchor.py) on RESOLVE's
# bridged football fixtures 10-05..10-20, each side in turn as the searched
# one: with the board's own opponent 0 wrong picks; with a decoy opponent of
# the same tournament / day 16 of 29,109 accepted (namesakes: Olympique
# Marsylia for Olympique Lyon); on the 28 F1 entries 20 identified, the 4
# opponent-differs hazards refused. Adds fixtures (FUZZY,
# Fixture.match_rule "SEARCHED_ANCHOR:<how>"), so it changes what prints; on at
# 2026-10-21 10:00Z by the operator's "on at once" (10-21 mixed). Evidence:
# docs/sofa/history/RAPORT_RESOLVE_KOTWICA_WYSZUKANA_2026-10-21.md.
FOOTBALL_SEARCHED_ANCHOR_FROM_UTC: datetime | None = datetime(
    2026, 10, 21, 10, 0, tzinfo=UTC)


def football_searched_anchor(date: str, build_at: datetime | None = None) -> bool:
    """Does RESOLVE accept the searched anchor for a football pair
    (FOOTBALL_SEARCHED_ANCHOR_FROM_UTC)?"""
    if FOOTBALL_SEARCHED_ANCHOR_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= FOOTBALL_SEARCHED_ANCHOR_FROM_UTC.strftime("%Y-%m-%d")
            and at >= FOOTBALL_SEARCHED_ANCHOR_FROM_UTC)


# --- RESOLVE: one squad, two level names (2026-10-21) -------------------------
# Superbet and Sofascore write a youth / reserve squad's level apart, and the
# level gate refused the pair: Italy's Primavera 2 is "Cosenza U19" on Superbet
# and "Cosenza U20" on Sofascore, El Salvador's reserves "CD Fas (R)" /
# "CD FAS U20", India's "Kenkre FC II" / "Kenkre U19", MLS Next Pro's
# "Houston Dynamo II" / "Houston Dynamo 2" (Sofascore's trailing "2" is no
# marker to `names.normalize_name`); 23 board entries 10-13..10-20 with
# neither side known (class F2). On: a football pair nothing matched by name
# nor the searched anchor is tried last on the searched candidates' listings
# plus up to 3 search results of an alias level
# (resolve.squad_level_alias_event): one game within 60 min, both sides the
# board's by name with the level words removed (own side >= 90, opponent > 82),
# one pair-consistent level shift (U19<->U20 one year apart, a reserve side <->
# U19..U23, a trailing "2" = reserve; never the senior squad), F25 order,
# gender, not postponed; vetoed when a team the opponent's own search names
# plays another game then (resolve.squad_alias_veto). Fixture FUZZY,
# match_rule "SQUAD_LEVEL_ALIAS:<shift>", never cached as a verified name.
# Measured on the bridged football fixtures 10-05..10-20: with the real
# opponent 0 wrong picks (as is 1,698, board level shifted 3,429, one-sided
# 2,509 right); decoy opponents 10 of 9,022 accepted (the ordinary name gate
# 20 of 2,848); F2 recall 18 of 23. Evidence:
# docs/sofa/history/RAPORT_RESOLVE_POZIOM_2026-10-21.md
# (scripts/sofa/measure_squad_level_alias.py). Adds fixtures, so it changes
# what prints; on at 2026-10-21 10:30Z by the operator's "on at once" (10-21
# mixed).
FOOTBALL_SQUAD_LEVEL_ALIAS_FROM_UTC: datetime | None = datetime(
    2026, 10, 21, 10, 30, tzinfo=UTC)


def football_squad_level_alias(date: str, build_at: datetime | None = None) -> bool:
    """Does RESOLVE accept a football pair under a squad-level alias
    (FOOTBALL_SQUAD_LEVEL_ALIAS_FROM_UTC)?"""
    if FOOTBALL_SQUAD_LEVEL_ALIAS_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= FOOTBALL_SQUAD_LEVEL_ALIAS_FROM_UTC.strftime("%Y-%m-%d")
            and at >= FOOTBALL_SQUAD_LEVEL_ALIAS_FROM_UTC)


# RESOLVE's short-name search (bet.sofa.short_name_search): a football pair
# that the normal search, the reserve retry and the searched anchor left
# without a fixture is searched again by its sides' longest words ("Calcio
# Avola 1949" -> "avola"), and a game is accepted only when BOTH sides land on
# it - side A's candidates hold its home team, side B's its away team, within
# 60 min of Superbet's start, gender, squad levels, the one such game. Adds
# fixtures (FUZZY, Fixture.match_rule "SHORT_NAME:<how>"), so it changes what
# prints; on at 2026-10-21 11:00Z by the operator's "on at once" (10-21
# mixed). Evidence:
# docs/sofa/history/RAPORT_RESOLVE_KROTKA_NAZWA_2026-10-21.md.
FOOTBALL_SHORT_NAME_SEARCH_FROM_UTC: datetime | None = datetime(
    2026, 10, 21, 11, 0, tzinfo=UTC)


def football_short_name_search(date: str, build_at: datetime | None = None) -> bool:
    """Does RESOLVE search a lost football pair by its short names
    (FOOTBALL_SHORT_NAME_SEARCH_FROM_UTC)?"""
    if FOOTBALL_SHORT_NAME_SEARCH_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= FOOTBALL_SHORT_NAME_SEARCH_FROM_UTC.strftime("%Y-%m-%d")
            and at >= FOOTBALL_SHORT_NAME_SEARCH_FROM_UTC)


# --- RESOLVE: the squad-level alias without pair consistency (2026-10-21) ----
# FOOTBALL_SQUAD_LEVEL_ALIAS_FROM_UTC needs both non-senior board sides to
# shift the same way; on, each may shift on its own (resolve.squad_level_shift
# loose=True): "Pisa U19 - Ascoli U19" is Sofascore's "Pisa U19 - Ascoli U20",
# "Modena U19 - Cremonese U20" both U20. Measured 2026-10-21
# (scripts/sofa/measure_squad_level_alias.py --loose) on the bridged football
# fixtures 10-05..10-20: 0 wrong picks with the real opponent, the same 10
# decoys of 9,022 as the pair-consistent rule; F2 recall 20 of 23 (18). On at
# 2026-10-21 11:30Z by the operator's "Włącz!" (10-21 mixed). Evidence:
# docs/sofa/history/RAPORT_RESOLVE_POZIOM_2026-10-21.md.
FOOTBALL_SQUAD_LEVEL_ALIAS_LOOSE_FROM_UTC: datetime | None = datetime(
    2026, 10, 21, 11, 30, tzinfo=UTC)


def football_squad_level_alias_loose(
    date: str, build_at: datetime | None = None
) -> bool:
    """May each non-senior side of a squad-level alias pair shift on its own
    (FOOTBALL_SQUAD_LEVEL_ALIAS_LOOSE_FROM_UTC)?"""
    if FOOTBALL_SQUAD_LEVEL_ALIAS_LOOSE_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= FOOTBALL_SQUAD_LEVEL_ALIAS_LOOSE_FROM_UTC.strftime("%Y-%m-%d")
            and at >= FOOTBALL_SQUAD_LEVEL_ALIAS_LOOSE_FROM_UTC)


# --- SAMPLES: the identity gate per family (2026-10-21) ----------------------
# metrics.check_identities returned one verdict for the whole match and SAMPLES
# applied it to every metric: a match whose shot categories did not add up
# (Roma - Real Madrid 16938872 of 10-14: away shots 16 vs on 8 + off 8 +
# blocked 1, no woodwork) left every sample - corners, cards, goals - with
# INTERNAL_INCONSISTENT. On: each identity blocks only the metrics that read
# what it compares (metrics.identity_gap_for_metric): shots -> shot metrics;
# goal incidents vs score -> incident metrics (card points, reds, penalties);
# home period sum -> goals and the incident metrics reading the 90-minute
# score; tennis gamesWon vs the set score -> the whole match, as before.
# Read-only measurement: scripts/sofa/measure_identity_gate.py; evidence:
# docs/sofa/history/RAPORT_BRAMKA_TOZSAMOSCI_2026-10-21.md. Wider samples
# change what prints. The operator moved it into the built day 2026-10-21:
# on at 10:50Z (10-21 mixed, audit_ledger "10-21 mieszany"); a rebuild re-runs
# SAMPLES / SHEET --event-ids for the open football fixtures whose samples
# lack IDENTITY_GATE_MARKER (bet.sofa.rebuild_plan).
IDENTITY_GATE_PER_FAMILY_FROM_UTC: datetime | None = datetime(
    2026, 10, 21, 10, 50, tzinfo=UTC)
# FixtureSamples.identity_gate of a fixture sampled under the switch
IDENTITY_GATE_MARKER = "per_family"


def identity_gate_per_family(date: str, build_at: datetime | None = None) -> bool:
    """Does each internal identity block only the metrics of its family
    (IDENTITY_GATE_PER_FAMILY_FROM_UTC)?"""
    if IDENTITY_GATE_PER_FAMILY_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= IDENTITY_GATE_PER_FAMILY_FROM_UTC.strftime("%Y-%m-%d")
            and at >= IDENTITY_GATE_PER_FAMILY_FROM_UTC)


# --- Measured sports: the rolling day window (2026-10-23) --------------------
# A hockey / basketball / volleyball / CS2 leg belonged to the UTC day of its
# start, so the North American evening (NBA / NHL from ~23:00Z to ~04:00Z)
# fell into the NEXT day's coupon, whose morning build found those games
# already under way: 10-22's last SPORT_CONFIDENCE refused 276 hockey and
# 4,927 basketball sides KICKED_OFF (08_confidence_sports.json; 3,893
# basketball / hockey rows in the planning pass's build). On, day D's window
# is [end(D-1), end(D)) with end(D) = D+1 LATE_WINDOW_END_H:00Z - the games
# after midnight UTC belong to D, priced by the operator's manual evening
# rebuild (rebuild_day.py --date D, ~20:00-21:00Z), which appends them to D's
# coupon (morning legs stay locked). Football and tennis keep the UTC day.
# A scope change, not a pricing change, but it changes what prints: from
# 2026-10-23 00:00Z by the operator's decision of 2026-10-22; ledger group
# "od 10-23". Read by DATE only - the window must partition the timeline
# (10-22 = [10-22 00:00Z, 10-23 00:00Z), 10-23 = [10-23 00:00Z,
# 10-24 05:00Z), no gap, no overlap), so a build's clock never moves it.
SPORT_LATE_WINDOW_FROM_UTC: datetime | None = datetime(2026, 10, 23, tzinfo=UTC)
LATE_WINDOW_END_H = 5
# the stamp on a sport leg starting on D+1 (inside D's window)
LATE_WINDOW_MARKER = "late"


def sport_late_window(date: str) -> bool:
    """Does day D's measured-sport window run to D+1 LATE_WINDOW_END_H:00Z
    (SPORT_LATE_WINDOW_FROM_UTC)? By the day alone, never the build clock."""
    if SPORT_LATE_WINDOW_FROM_UTC is None:
        return False
    return date >= SPORT_LATE_WINDOW_FROM_UTC.strftime("%Y-%m-%d")


# --- Measured sports: the league rate restarts after an off-season (2026-10-23)
# The score model's league rate (football_rating._League, ALPHA_LEAGUE 0.02,
# ~ the last 50 matches) carried a season's last matches - for the NBA its
# playoffs, 215 / 206 points a game in May / June 2026 - into the next season:
# on 10-21 / 10-22 it read the NBA at 218.1 points against the 228.6 its first
# 14 matches of October 2026 averaged, the model's totals 13.2 points under
# Superbet's main line on 13 games, and 36 of the 42 NBA legs a replay let
# through were UNDERs on halves / quarters (data/refit_2026-10-22/nba_measure).
# On (RatingBook.season_restart): a league whose next match comes
# football_rating.SEASON_GAP_S (45 days) or more after its last one reads the
# plain mean of the season that ended, and its level restarts from that mean
# as if it were SEASON_PRIOR_MATCHES (10) matches old, the home share at the
# slow step (SEASON_RESTART_LEVEL_ONLY). A general estimator rule, every
# league of the sports in LEAGUE_SEASON_RESTART_SPORTS alike (no league or
# team is named). Live (SPORT_CONFIDENCE), in the line-evidence replay of a
# day >= it and in a fit's history replay for a day >= it.
# Measured out of sample (walk-forward as walk_forward_rows, both arms on the
# union of their synthetic lines, game bootstrap; 2024-09..2026-10-22):
# NBA log loss per game line -0.0006 [-0.0010, -0.0001] on 2,644 games, its
# first 30 days of a season -0.0030 [-0.0050, -0.0012] on 448 (totals
# -0.0125, team totals -0.0079); the 2026 start's level gap +10.3 -> +0.6
# points; other basketball -0.0001 [-0.0005, +0.0003] on 4,243 games (1 in 20
# thinned), no family worse; the printable rows' realised - confidence
# unchanged (NBA -2.0 pp both). Changes basketball p, so it changes what
# prints: from 2026-10-23 00:00Z by the operator's go of 2026-10-22 (~10:21Z)
# (docs/sofa/history/NBA_SEZON_STAWKA_LIGI_2026-10-22.md); ledger group
# "od 10-23" (the same day as SPORT_LATE_WINDOW). The installed basketball
# curve was fitted on the old rule and is not refitted (a refit needs its
# own go).
LEAGUE_SEASON_RESTART = "league_season_restart_v1"
LEAGUE_SEASON_RESTART_FROM_UTC: datetime | None = datetime(
    2026, 10, 23, 0, 0, 0, tzinfo=UTC)
# Basketball only: on the same replay hockey's game-line log loss was worse
# (+0.0005 [+0.0002, +0.0009] per line, 6,169 games 2024-09..2026-10-22) and
# volleyball's too (+0.0012 [+0.0005, +0.0020], 5,373 games) - measured with
# both sides at the fast step (SEASON_RESTART_LEVEL_ONLY False); the
# level-only form was not measured for them.
LEAGUE_SEASON_RESTART_SPORTS: frozenset[str] = frozenset({"basketball"})


def league_season_restart(sport: str, date: str | None = None,
                          build_at: datetime | None = None) -> bool:
    """Does the score model's league rate of `sport` restart after an
    off-season gap (LEAGUE_SEASON_RESTART_FROM_UTC)? `date` None: the wall
    clock alone."""
    if (LEAGUE_SEASON_RESTART_FROM_UTC is None
            or sport not in LEAGUE_SEASON_RESTART_SPORTS):
        return False
    at = build_at if build_at is not None else timeutil.now()
    if (date is not None
            and date < LEAGUE_SEASON_RESTART_FROM_UTC.strftime("%Y-%m-%d")):
        return False
    return at >= LEAGUE_SEASON_RESTART_FROM_UTC


# --- Football / tennis: no curve fitted from our settled days alone (2026-10-24)
# fit_confidence read every sofa_settled_row, the replay's ('cache-calibration')
# and SETTLE's live rows alike, so a market the history replay does not price
# got a curve from our settled days ALONE - against the rule that curves are
# fitted on the history and our days only audit them (found 2026-10-22,
# docs/sofa/history/REFIT_PILKA_2026-10-22.md "Znalezisko"). The fit now
# refuses such a key (bet.sofa.live_only_curves, `live_only_refused`). The
# installed curves predate that: the keys measured live-only on the DB they
# were fitted from (data/refit_2026-10-17/sofa_replay.db) are listed in
# config/sofa_live_only_curves.json, and from this moment CONFIDENCE and the
# line evidence's base of such a day read the calibration without them
# (live_only_curves.strip): the key has no curve and no pool stands in for
# it - its own Superbet lines or NO_LINE_EVIDENCE, like any market without a
# curve. Changes what prints; operator's go for fixes 2026-10-23, from
# 2026-10-24 00:00Z (nothing earlier); ledger group "od 10-24"
# (docs/sofa/history/KRZYWE_TYLKO_Z_NASZYCH_DNI_2026-10-23.md).
LIVE_ONLY_CURVE_REFUSED_FROM_UTC: datetime | None = datetime(
    2026, 10, 24, 0, 0, 0, tzinfo=UTC)


def live_only_curve_refused(date: str, build_at: datetime | None = None) -> bool:
    """Does CONFIDENCE read the football / tennis calibration without the
    installed curve keys fitted from live rows alone
    (LIVE_ONLY_CURVE_REFUSED_FROM_UTC)? By the day and the build clock."""
    if LIVE_ONLY_CURVE_REFUSED_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= LIVE_ONLY_CURVE_REFUSED_FROM_UTC.strftime("%Y-%m-%d")
            and at >= LIVE_ONLY_CURVE_REFUSED_FROM_UTC)


# --- Coverage audit 2026-10-23, plan P1-P14 (operator "ALL IN", 2026-10-23
# ~13:45Z; docs/sofa/history/AUDYT_POKRYCIA_2026-10-23.md, sections 7 and 14).
# Every switch below changes what prints and is read by the day and the build
# clock. A switch stays None (off) until its fix ships with a test; the
# measured ones (P1, P3, P4, P5, P6, P7) are set only when their out-of-sample
# measurement is better (operator: "włącz tylko lepsze"). On: from 2026-10-24
# 00:00Z, ledger group "od 10-24" (no mixed day). Each block is owned by the
# fix it names; its comment states the measurement once it is set.


def _audit_1023_on(switch: datetime | None, date: str,
                   build_at: datetime | None) -> bool:
    if switch is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return date >= switch.strftime("%Y-%m-%d") and at >= switch


# P1: ENTITY_CONFLICT cuts the sample at the conflict instead of emptying it.
SAMPLE_CONFLICT_CUT_FROM_UTC: datetime | None = None


def sample_conflict_cut(date: str, build_at: datetime | None = None) -> bool:
    """P1 (SAMPLE_CONFLICT_CUT_FROM_UTC)."""
    return _audit_1023_on(SAMPLE_CONFLICT_CUT_FROM_UTC, date, build_at)


# P2: SPORT_IDENTITY re-asks a fresh page on a cache miss near the start and
# asks the second team's page too (sport_identity.identify_event
# `fresh_all`: any refusal of a cached page within FRESH_RECHECK_WITHIN, not
# only K5's NO_GAME_WITHIN_1H; the other side's team - resolved id, else its
# query id - cached page first, fresh in the window). No measurement needed
# (operator); ON once code + tests passed. Cost (upper bound,
# scripts/sofa/measure_audit1023_p2_recheck_cost.py, the loops' run clocks):
# 179 / 123 / 156 extra listing requests on 10-21 / 10-22 / 10-23 (partial),
# ~15 s of bridge time a day; breaker / BRIDGE_ABORTED unchanged.
IDENTITY_FRESH_RECHECK_ALL_FROM_UTC: datetime | None = datetime(
    2026, 10, 24, 0, 0, 0, tzinfo=UTC)


def identity_fresh_recheck_all(date: str,
                               build_at: datetime | None = None) -> bool:
    """P2 (IDENTITY_FRESH_RECHECK_ALL_FROM_UTC)."""
    return _audit_1023_on(IDENTITY_FRESH_RECHECK_ALL_FROM_UTC, date, build_at)


# P3 (K7): a player's history from every team he played for. Each sport is
# judged on its own (PLAYER_HISTORY_ANY_TEAM_SPORTS: on only where its own
# measurement was better); a call without `sport` is football's
# (samples.py). Hockey / basketball: player_model.load_appearances(any_team)
# - the peers' games (opponents of the two teams in their loaded games),
# installed constants. Measured on Superbet's settled pre-game player lines
# 2026-09-29..10-22 (scripts/sofa/measure_audit1023_p3_player_any_team.py,
# DB copy data/refit_2026-10-23_allin, the box's player, side rule both
# readers, 1,000 game bootstraps):
#   hockey 24,838 sides / 155 games: p on 22,418 -> 24,294 sides; on the
#     22,418 both price, log loss -0.0018 [-0.0034, -0.0003], Brier -0.0007
#     [-0.0012, -0.0002]; the 2,240 sides whose p moved -0.0181 [-0.0354,
#     -0.0030]; the 938 added favoured sides claim 0.667, hit 0.647, hit -
#     claimed -0.020 [-0.055, +0.013] (calibrated) -> ON.
#   basketball 27,864 sides / 245 games: common log loss -0.0013 [-0.0045,
#     +0.0019]; the 2,015 added favoured sides claim 0.627, hit 0.544, -0.083
#     [-0.115, -0.052] (over-claim) -> OFF.
# A hockey refit on the any-team reader (fit_player_model.py --sport hockey
# --any-team) was no better than the installed constants on the same reader
# (log loss -0.0003 [-0.0008, +0.0001], Brier slightly worse) - not installed.
# Football (samples.any_team_sample: a thin sample topped up with the same
# player id's starts for the sample opponents' teams, cached lineups only;
# scripts/sofa/measure_audit1023_p3_any_team_football.py, target matches
# 2026-08-01..10-20, 3,371 matches, installed curves, match bootstrap): added
# printable rows 4,247 (458 matches) realise - confidence +0.52 pp
# [-0.68, +1.73], added minus base +0.36 pp [-0.92, +1.61]; rows that existed
# are unchanged by construction (top-up only below min_sample) -> ON.
PLAYER_HISTORY_ANY_TEAM_FROM_UTC: datetime | None = datetime(
    2026, 10, 24, 0, 0, 0, tzinfo=UTC)
PLAYER_HISTORY_ANY_TEAM_SPORTS: frozenset[str] = frozenset(
    {"hockey", "football"})


def player_history_any_team(date: str,
                            build_at: datetime | None = None,
                            sport: str = "football") -> bool:
    """P3 (PLAYER_HISTORY_ANY_TEAM_FROM_UTC) for `sport`, one of
    PLAYER_HISTORY_ANY_TEAM_SPORTS."""
    return (sport in PLAYER_HISTORY_ANY_TEAM_SPORTS
            and _audit_1023_on(PLAYER_HISTORY_ANY_TEAM_FROM_UTC, date,
                               build_at))


# P4: volleyball query-only anchor (one game at the exact start, weak
# opponent agreement), like FOOTBALL_SEARCHED_ANCHOR
# (sport_identity.match_query_anchor, QUERY_ANCHOR_SPORTS = volleyball).
# Backtest 10-05..10-23 (scripts/sofa/measure_audit1023_p4_query_anchor.py,
# DB copy, ids hidden): volleyball 1,308 picks with the true team as the
# query and 1,172 with today's query id (3 impostor ids, all refused) - 0
# wrong; decoy opponent (another board team of the tournament / day) 18 of
# 15,280 accepted; recall 11 of 96 query-only refusals (8 the settle's own
# event, 3 not settled, 0 contradicted; OK Maribor - ACH Lublana 10-23 one
# of them). Hockey (0 wrong of 4,985) and basketball (0 of 5,760) measured
# clean too but not in scope (QUERY_ANCHOR_SPORTS).
SPORT_QUERY_ANCHOR_FROM_UTC: datetime | None = datetime(
    2026, 10, 24, 0, 0, 0, tzinfo=UTC)


def sport_query_anchor(date: str, build_at: datetime | None = None) -> bool:
    """P4 (SPORT_QUERY_ANCHOR_FROM_UTC)."""
    return _audit_1023_on(SPORT_QUERY_ANCHOR_FROM_UTC, date, build_at)


# P5: football player slug read as a second name (players.match_player_by_slug,
# the last fallback of samples.build_player_samples; match_rule "slug", SETTLE
# grades it by matched_name). False-match test on the 15,423 newest football
# lineups (600,124 entries; scripts/sofa/measure_audit1023_p5_slug.py): the
# slug points at the same person 24,321 times, at another 0; recovered live
# 10-21..10-23: 4 / 4 / 6 names, each one Sofascore id -> ON.
PLAYER_SLUG_NAME_FROM_UTC: datetime | None = datetime(
    2026, 10, 24, 0, 0, 0, tzinfo=UTC)


def player_slug_name(date: str, build_at: datetime | None = None) -> bool:
    """P5 (PLAYER_SLUG_NAME_FROM_UTC)."""
    return _audit_1023_on(PLAYER_SLUG_NAME_FROM_UTC, date, build_at)


# P6: players' zero offsides from the team's rebuilt 0-0.
PLAYER_OMITTED_ZERO_FROM_UTC: datetime | None = None


def player_omitted_zero(date: str, build_at: datetime | None = None) -> bool:
    """P6 (PLAYER_OMITTED_ZERO_FROM_UTC)."""
    return _audit_1023_on(PLAYER_OMITTED_ZERO_FROM_UTC, date, build_at)


# P7: CS2 lineup rating without the team-id gate. A pair whose team ids are
# not both MIN_MAPS_RATED reads the lineup gap through its own calibration
# (cs2_engine.fit_unrated: the rated lineup intercept, the slope fitted on the
# unrated pairs' walk-forward points); rated pairs unchanged. Measured
# (measure_audit1023_p7_cs2_lineup_unrated.py, copy DB 2025-10-23..2026-10-22,
# walk-forward, 7-day refits, evaluated from 02-20, bootstrap over series):
# 567 series / 1,221 maps gain a number (111 series in the last 30 days),
# 8,575 rated series 0 rows changed. Maps: log loss 0.628 vs the home share's
# 0.690 (-0.062 [-0.078, -0.046]); realised - claimed (home) -0.8 pp
# [-3.6, +2.0], favourite +1.7 pp [-0.9, +4.3], slope 1.12 [0.95, 1.33];
# series winner: favourite +2.7 pp [-1.0, +6.3], home -0.9 pp [-4.6, +2.9].
# From 06-20 only: favourite -1.1 pp [-4.4, +2.3]. The calibration variant
# was chosen among three on these data (rated one alone: slope 1.83
# [1.54, 2.15]; free intercept: home -3.2 pp [-5.9, -0.3]).
CS2_LINEUP_ELO_UNRATED_FROM_UTC: datetime | None = datetime(2026, 10, 24, 0, 0,
                                                            0, tzinfo=UTC)


def cs2_lineup_elo_unrated(date: str,
                           build_at: datetime | None = None) -> bool:
    """P7 (CS2_LINEUP_ELO_UNRATED_FROM_UTC)."""
    return _audit_1023_on(CS2_LINEUP_ELO_UNRATED_FROM_UTC, date, build_at)


# P8: name rules - CS2 "prospect", the engine's nickname by prefix, hockey
# transliteration (ue -> u-umlaut, Yegor / Egor). No measurement (plan, section
# 7). CS2 part (agent D-cs2): cs2.ROSTER_MARKER_FOLD ("prospect" is the marker
# "prospects"; esports_score / pick_event / series_orientation `name_rules`)
# and cs2_engine.player_id's nickname by prefix (cs2.MapResult.player's rule,
# >= NICK_PREFIX_MIN letters, one player). The hockey part
# (player_model.names_agree) shares this switch. Read by the day the series /
# game was offered and the build clock.
NAME_RULES_1023_FROM_UTC: datetime | None = datetime(2026, 10, 24, 0, 0, 0,
                                                     tzinfo=UTC)


def name_rules_1023(date: str, build_at: datetime | None = None) -> bool:
    """P8 (NAME_RULES_1023_FROM_UTC)."""
    return _audit_1023_on(NAME_RULES_1023_FROM_UTC, date, build_at)


# P9: hockey / basketball - a game belongs to both teams' lists. No
# measurement (operator: P9 goes on with code + tests). The missing side of a
# game is written offline from its stored payload under its own list kind
# (sport_history.OPPONENT_KIND, list_both_sides: 42,892 sides in the index on
# 2026-10-23, 8,514 games of the last 400 days - hockey 1,241, basketball
# 7,273; Vancouver @ Florida 16546356 now in Vancouver's 3692 list too); the
# player model reads it only from this switch (sport_history.listing_kinds /
# listed_rows). Ledger group "od 10-24".
PLAYER_BOTH_SIDES_LISTED_FROM_UTC: datetime | None = datetime(
    2026, 10, 24, 0, 0, 0, tzinfo=UTC)


def player_both_sides_listed(date: str,
                             build_at: datetime | None = None) -> bool:
    """P9 (PLAYER_BOTH_SIDES_LISTED_FROM_UTC)."""
    return _audit_1023_on(PLAYER_BOTH_SIDES_LISTED_FROM_UTC, date, build_at)


# P11: basketball score model for leagues played in halves (NCAA). Off:
# Superbet's offer holds no NCAA basketball game yet (SHADOW snapshots
# 09-29..10-24: none; the by-date offer to 11-12 on 2026-10-23: none; its
# struct lists "USA - NCAA" tournaments 36 / 2108 / 33447 and "(K)" 2175 /
# 33361 with no sport named - 3348 / 35201 are hockey, 33224 volleyball, by
# our snapshots). The installed basketball curve was fitted without NCAA.
# Revisit when an NCAA basketball game is in a SHADOW snapshot (season from
# ~11-03), with settlement of halves games (shadow.build_result wants four
# quarters) done first.
BB_HALVES_LEAGUES_FROM_UTC: datetime | None = None


def bb_halves_leagues(date: str, build_at: datetime | None = None) -> bool:
    """P11 (BB_HALVES_LEAGUES_FROM_UTC)."""
    return _audit_1023_on(BB_HALVES_LEAGUES_FROM_UTC, date, build_at)


# P12: CS2 model_p for series settled from the result alone. No measurement
# (plan, section 7). Read by the SETTLE clock (settle_cs2.settle_one passes the
# run's own date and clock): model_p feeds only the next morning's line
# evidence, never a built coupon, so a 10-23 series settled on the 10-24
# morning gets one too. The series settled before the switch get theirs once
# through `settle_cs2.py --attach-series-only-model --sweep-from 2026-09-28
# --sweep-to <D-1>` (offline, refuses while this is off), run before the
# 10-24 refresh_line_evidence.py.
CS2_SERIES_ONLY_MODEL_P_FROM_UTC: datetime | None = datetime(2026, 10, 24, 0, 0,
                                                             0, tzinfo=UTC)


def cs2_series_only_model_p(date: str,
                            build_at: datetime | None = None) -> bool:
    """P12 (CS2_SERIES_ONLY_MODEL_P_FROM_UTC); `date` / `build_at` are the
    settle run's own day and clock."""
    return _audit_1023_on(CS2_SERIES_ONLY_MODEL_P_FROM_UTC, date, build_at)


# P13: volleyball golden set (AET / AGS) in the model; the settlement side is
# a correctness fix and needs no switch (shadow.GOLDEN_SET_DESCRIPTIONS:
# Superbet's Regulamin 5.D.3.a - the official result is the match's, the
# golden set decides the tie and is no part of it). On: such a match is read
# on its own sets (score_model.parse_event golden_set; 89 of the 90 cached
# AET / AGS games parse, 15670573 refused - its sets 3-0 disagree with
# `current` 3-1; measure_audit1023_p13_golden_set.py).
# Ledger group "od 10-24".
VB_GOLDEN_SET_FROM_UTC: datetime | None = datetime(
    2026, 10, 24, 0, 0, 0, tzinfo=UTC)


def vb_golden_set(date: str, build_at: datetime | None = None) -> bool:
    """P13 model side (VB_GOLDEN_SET_FROM_UTC)."""
    return _audit_1023_on(VB_GOLDEN_SET_FROM_UTC, date, build_at)


# P14: tennis rating - winner from the set score, player type 0.
# tennis_rating.parse_event(score_winner=True): an "Ended" match with no
# winnerCode takes its winner from a complete set score (winner_from_sets;
# Retired / Walkover never, winnerCode 3 never), and a type-0 side that is not
# a team (not national, no "/", no subTeams) is a player. Read by SHEET's
# load_tennis_rating (run_sheet passes the day's state) on the day being built
# and the build clock. No measurement required (operator 2026-10-23); the
# offline count is in scripts/sofa/measure_audit1023_p14_tennis_rating.py.
# The installed tennis curves were fitted on a replay without it
# (calibrate_from_cache RatingReplay.from_db): a later refit replays it.
TENNIS_RATING_SCORE_WINNER_FROM_UTC: datetime | None = datetime(
    2026, 10, 24, 0, 0, 0, tzinfo=UTC)


def tennis_rating_score_winner(date: str,
                               build_at: datetime | None = None) -> bool:
    """P14 (TENNIS_RATING_SCORE_WINNER_FROM_UTC)."""
    return _audit_1023_on(TENNIS_RATING_SCORE_WINNER_FROM_UTC, date, build_at)
