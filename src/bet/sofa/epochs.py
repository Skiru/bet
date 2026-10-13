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
DERIVED_SHEET_MARGINS_FROM_UTC: datetime | None = None


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
CARDS_CORRELATION_DATE = "2026-10-09"
CARDS_CORRELATION_FROM_UTC: datetime | None = None
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
DERIVED_CURVES_DATE = "2026-10-09"
DERIVED_CURVES_FROM_UTC: datetime | None = None


def derived_curves(date: str, build_at: datetime | None = None) -> bool:
    if DERIVED_CURVES_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return date >= DERIVED_CURVES_DATE and at >= DERIVED_CURVES_FROM_UTC


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
MAPPABLE_FAMILIES_FROM_UTC: datetime | None = None


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
CS2_TEAM_ROUNDS_RACE_FROM_UTC: datetime | None = datetime(
    2026, 10, 14, 0, 0, tzinfo=UTC)


def cs2_team_rounds_race(date: str, build_at: datetime | None = None) -> bool:
    """Is a CS2 team-rounds line priced from the round race
    (CS2_TEAM_ROUNDS_RACE_FROM_UTC)?"""
    if CS2_TEAM_ROUNDS_RACE_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= CS2_TEAM_ROUNDS_RACE_FROM_UTC.strftime("%Y-%m-%d")
            and at >= CS2_TEAM_ROUNDS_RACE_FROM_UTC)


# Audit 2026-10-13 B1: the favourite / outsider (game-state) term of a
# football side's centre. From this moment the centre of a market of
# game_state.GAME_STATE_MARKETS with a beta in config/sofa_game_state.json is
# multiplied by exp(beta x s), s the side's expected goal difference from the
# rating's goals book (FootballForecast.supremacy; the opponent reads -s).
# Changes p, so what prints: a day >= the date built at or after the moment.
# Evidence: docs/sofa/evidence/game_state_2026-10-13.md.
GAME_STATE = "game_state_v1"
GAME_STATE_FROM_UTC: datetime | None = None


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
FOOTBALL_RATED_SCOPE_FROM_UTC: datetime | None = None


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
FOOTBALL_VENUE_PRIOR_FROM_UTC: datetime | None = None


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
MARKET_POSITIONED_LINES_FROM_UTC: datetime | None = None
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
# NOT switched on: it needs the refit above first.
TENNIS_SET_RATING_PRICES_FROM_UTC: datetime | None = None


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
SAMPLE_OPPONENT_CORRECTION_FROM_UTC: datetime | None = None


def sample_opponent_correction(date: str, build_at: datetime | None = None) -> bool:
    """Is the football sample corrected for its opponents and domain
    (SAMPLE_OPPONENT_CORRECTION_FROM_UTC)?"""
    if SAMPLE_OPPONENT_CORRECTION_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= SAMPLE_OPPONENT_CORRECTION_FROM_UTC.strftime("%Y-%m-%d")
            and at >= SAMPLE_OPPONENT_CORRECTION_FROM_UTC)


def sheet_sample_opponent_correction(rows: Sequence[Mapping[str, Any]]) -> bool:
    """Was every row of a 05_sheet.json priced under SAMPLE_OPPONENT_CORRECTION?
    An empty sheet has nothing to re-price."""
    return all(r.get("opponent_rule") == SAMPLE_OPPONENT_CORRECTION for r in rows)


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
TENNIS_MATCH_WINNER_FROM_UTC: datetime | None = None


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
SEASON_PHASE_FROM_UTC: datetime | None = None


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
FOOTBALL_RATING_WEIGHT_FROM_UTC: datetime | None = None


def football_rating_weight(date: str, build_at: datetime | None = None) -> bool:
    """Does a rated football centre read its market's own W
    (FOOTBALL_RATING_WEIGHT_FROM_UTC)?"""
    if FOOTBALL_RATING_WEIGHT_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= FOOTBALL_RATING_WEIGHT_FROM_UTC.strftime("%Y-%m-%d")
            and at >= FOOTBALL_RATING_WEIGHT_FROM_UTC)


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
CS2_COUNT_EXPOSURE_FROM_UTC: datetime | None = datetime(
    2026, 10, 14, 0, 0, tzinfo=UTC)


def cs2_count_exposure(date: str, build_at: datetime | None = None) -> bool:
    """Is a CS2 kills / deaths / assists / headshots line priced from the
    rounds' exposure (CS2_COUNT_EXPOSURE_FROM_UTC)?"""
    if CS2_COUNT_EXPOSURE_FROM_UTC is None:
        return False
    at = build_at if build_at is not None else timeutil.now()
    return (date >= CS2_COUNT_EXPOSURE_FROM_UTC.strftime("%Y-%m-%d")
            and at >= CS2_COUNT_EXPOSURE_FROM_UTC)
