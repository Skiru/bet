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
