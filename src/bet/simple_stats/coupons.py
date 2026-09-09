"""Assemble one betting day's stats sheet into singles and Bet Builder slips.

This is the last computation in the chain, and it is code rather than an agent's
prose for the same reason ``wilson_lower_bound`` is: the numbers it produces are
thresholds a human bets money against. A threshold free-handed in a report
cannot be audited, reproduced, or caught when it slips by a decimal place.

What it does **not** do, and cannot be made to
----------------------------------------------
* **No combined price.** ``BetBuilderDraft.combined_price`` is still typed
  ``None``: no endpoint serves Superbet's Bet Builder price, and it cannot be
  derived from the legs because the book's combination margin is not
  observable from them. The operator reads it off the screen.

  What *is* computed, since 2026-09-03, is the **bar** for that price --
  ``min_acceptable_combined_odds``. The reason it could not be computed before
  was a claim about correlation that has since been measured and did not hold:
  over 12,555 same-fixture leg pairs settled against real results, legs land
  together 1.009x as often as independence implies (95% CI [1.005, 1.013]),
  and 1.006x for non-nested markets. See ``bet_builder_draft`` for the table.
  A coefficient that small is a coefficient, not a reason to refuse the
  arithmetic.
* **No stake.** Not a size, not a fraction of a bankroll, not a Kelly figure.
* **No EV.** EV needs a price, and the only real price is on the operator's own
  screen.

Every coupon is therefore *conditional*: "this lean is worth taking **if** the
screen shows at least X.XX". The operator supplies the price and the decision.

The one number that ranks everything
------------------------------------
``p_low`` -- the Wilson lower bound already on every row. Never ``hit_rate``:
4/4 is a hit rate of 1.00 and a ``p_low`` of 0.51, which is the whole point of
using it. Nothing in this module recomputes it; it is read from the artifact.

**Ranking and the price bar are two different questions, and since 2026-09-03
they are answered by two different numbers.** ``p_low`` still orders the file:
between two rows it is the honest statement of which is better evidenced, and
a lower bound is the right tool for that. It is the wrong tool for dividing
into 1 to get a price, because it is wrong by +16 to +22pp in one direction on
every row -- so ``bar_basis`` now defaults to ``p_central``, which measures
-0.000 against realised results. See ``bet_builder_draft.BAR_BASES``.
"""
from __future__ import annotations

import json
import math
import threading
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Mapping
from typing import Literal
from pydantic import Field

from collections import defaultdict

from bet.simple_stats.bet_builder_draft import (
    scope_sibling,
    required_odds,
    TIER_MARGIN,
    AnalystVeto,
    BetBuilderDraft,
    Tier,
    VetoIndex,
    BarComponents,
    MIN_REPORTABLE_CALIBRATION,
    bar_components,
    draft_legs,
    mechanism_family,
    shrink_k_for_market,
    is_trivial_under,
    step_tier_down,
    tier_for_row,
)
from bet.discovery.team_aliases import resolve_team_alias
from bet.simple_stats.analyze import drifted_markets
from bet.simple_stats.contracts import (
    EventListV1,
    MarketContextV1,
    StatsSheetRow,
    StatsSheetV1,
    SuperbetOfferV1,
)
from bet.simple_stats.superbet_offer import (
    devigged_ladder,
    devigged_probability,
    ladder_centre,
    lookup_line,
    player_alias_index,
)
from bet.simple_stats.tipster_consensus import TipsterConsensus
from bet.strict_model import StrictBaseModel
from bet.utils import normalize_team_name

# docs/PLAN_BOGATE_STATYSTYKI.md Faza 5d.
_COMPETITION_TIER_MAP_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "competition_tier_map.json"
)
_COMPETITION_TIER_CACHE: dict[str, str] | None = None
_COMPETITION_TIER_LOCK = threading.Lock()


def _competition_tier_map() -> dict[str, str]:
    """``{competition: tier}`` from config/competition_tier_map.json, read once.

    Exact-name pin only, matching the same rule the ESPN and SportDB
    competition maps already follow (discover.py). A missing or malformed file
    yields an empty map rather than raising -- a config problem must not
    exclude every fixture from the coupon.
    """
    global _COMPETITION_TIER_CACHE
    with _COMPETITION_TIER_LOCK:
        if _COMPETITION_TIER_CACHE is not None:
            return _COMPETITION_TIER_CACHE
    tiers: dict[str, str] = {}
    try:
        document = json.loads(_COMPETITION_TIER_MAP_PATH.read_text(encoding="utf-8"))
        tiers = {
            str(name): str(tier)
            for name, tier in (document.get("tiers") or {}).items()
        }
    except (OSError, ValueError, AttributeError):
        tiers = {}
    with _COMPETITION_TIER_LOCK:
        if _COMPETITION_TIER_CACHE is None:
            _COMPETITION_TIER_CACHE = tiers
        return _COMPETITION_TIER_CACHE


def reset_competition_tier_cache() -> None:
    """Forget the cached competition-tier map. For tests only."""
    global _COMPETITION_TIER_CACHE
    with _COMPETITION_TIER_LOCK:
        _COMPETITION_TIER_CACHE = None


def competition_tier(competition: str) -> str | None:
    """This competition's tier, or None when it is not in the map at all.

    None is deliberately not TIER_3 or any other guess: an unclassified
    competition is left alone rather than excluded on a pattern match, exactly
    the overconfident-mapping mistake the pinned ESPN competition map was
    fixed for on 2026-08-28.
    """
    return _competition_tier_map().get(competition)

# Human-readable market labels. Sourced from the row's own ``market`` field
# rather than from STANDARD_MARKET_LINES, because that table is keyed by display
# name ("Corners Total") while a row carries the canonical name
# ("corners_total") -- and the mapping between them is not one-to-one for the
# per-team family.
MARKET_LABELS: dict[str, str] = {
    "corners_total": "rożne (mecz)",
    # "punkty kartkowe" and not "kartki": the label has to say that the number
    # is not a count of cards, or the operator reads a 7.5 line as seven
    # yellows. Superbet's own market is called "Liczba kartek" and settles a
    # red as two, which is the confusion this wording exists to break.
    "cards_points_total": "punkty kartkowe (mecz)",
    "cards_points_for": "punkty kartkowe (drużyna)",
    "cards_total": "żółte kartki (mecz)",
    "fouls_total": "faule (mecz)",
    "shots_on_target_total": "strzały celne (mecz)",
    "shots_total": "strzały (mecz)",
    "goals_total": "gole (mecz)",
    "goals_1h_total": "gole (1. połowa)",
    "goals_2h_total": "gole (2. połowa)",
    "corners_for": "rożne drużyny",
    "cards_for": "żółte kartki drużyny",
    "fouls_for": "faule drużyny",
    "shots_on_target_for": "strzały celne drużyny",
    "shots_for": "strzały drużyny",
    "goals_for": "gole drużyny",
    "offsides_total": "spalone (mecz)",
    "offsides_for": "spalone drużyny",
    "red_cards_total": "czerwone kartki (mecz)",
    "player_total_shots": "strzały zawodnika",
    "player_shots_on_target": "strzały celne zawodnika",
    "player_fouls": "faule zawodnika",
    "player_was_fouled": "faulowany",
    "player_cards": "kartka zawodnika",
    "player_tackles": "odbiory zawodnika",
    "player_assists": "asysty zawodnika",
    "player_offsides": "spalone zawodnika",
    "total_games": "gemy (mecz)",
    "aces_total": "asy (mecz)",
    "total_sets": "sety",
    "double_faults_total": "podwójne błędy (mecz)",
    "breaks_total": "przełamania",
    "aces_for": "asy zawodnika",
    "double_faults_for": "podwójne błędy zawodnika",
    "games_won": "gemy zawodnika",
}

# A single must clear this before it is worth an operator's attention.
#
# 0.50 is not arbitrary and is not a probability threshold in disguise: below it
# the fair odds exceed 2.00, and once the tier margin is applied the required
# price passes what these markets realistically pay. A row at p_low 0.35 needs
# 3.14 on a corners line that is quoted near 2.30 -- reporting it as a "bet" is
# reporting something unplaceable.
MIN_SINGLE_P_LOW = 0.50

# How far under its own threshold a price may sit and still lead the file.
#
# The bar is ``tier_margin / p_shrunk``, and a row whose price misses it by one
# percent was being filed with rows that miss it by twenty. That is not a
# distinction the arithmetic supports and it is not one the settled record
# supports either. Measured over 1,269 settled, priced match-total rows from
# the slates in ``runs/``, bucketed by how far the posted price sat from the
# threshold, with ROI bootstrapped over fixtures:
#
#     gap >= 0% (the old VALUE rule)   n=  52  win 63.5%  ROI -0.8%  [-35.6, +28.3]
#     gap >= -2%                       n=  71  win 66.2%  ROI +0.5%  [-28.2, +25.7]
#     gap >= -5%                       n= 144  win 72.9%  ROI +1.3%  [-13.8, +15.8]
#     gap >= -8%                       n= 277  win 78.3%  ROI +0.2%  [ -9.6,  +9.5]
#     gap >= -10%                      n= 472  win 82.2%  ROI -0.7%  [ -7.0,  +5.2]
#     gap >= -15%                      n= 993  win 85.5%  ROI -1.6%  [ -5.6,  +2.0]
#
# The finding is the first line against the third. Insisting on a non-negative
# gap threw away 92 of 144 rows and bought nothing measurable -- its own point
# estimate is *worse*, on a sample too small to say anything at all. -5% is the
# best point estimate on the curve and the last floor whose interval is still
# mostly positive.
#
# Every interval here contains zero, so this is not a claim that -5% is
# profitable. It is a claim that the 0% line was arbitrary, cost most of the
# candidates, and was never measured. Nothing is deleted either way: a row past
# the tolerance is still written, still ranked, and still carries its gap.
#
# Note which way the win rate runs. It climbs monotonically as the gap gets
# worse -- 63.5% at the top, 92.6% past -20% -- because a worse gap means a
# shorter price. High-probability reads live structurally *below* the
# threshold, which is why a file gated at 0% can never show one.
PRICE_TOLERANCE_PCT = 5.0

# Where the measured edge actually lives, by posted price. Used to *label* a
# row, never to remove one -- the operator has said the decision is his and the
# bands are what he needs to make it.
#
# Measured over 668 settled, priced coupon singles from the slates in ``runs/``,
# rebuilt at ``max_singles=400`` so the whole candidate set is scored, against
# each row's own posted price. "edge" is realised hit rate minus the price's
# implied probability, so it is the part that is not vig:
#
#     price        n    win    implied    edge      ROI
#     1.00-1.05  239  97.5%      98.5%   -1.0%    -1.1%
#     1.05-1.10   75  89.3%      93.6%   -4.3%    -4.7%
#     1.10-1.20  119  84.9%      87.6%   -2.7%    -3.2%
#     1.20-1.35  128  78.1%      79.4%   -1.3%    -1.6%
#     1.35-1.60   86  76.7%      69.4%   +7.3%   +10.8%
#     1.60-2.00   19  63.2%      57.1%   +6.1%   +11.0%
#
# This is the answer to "a near-certain leg is worth having as a top-up". It is
# not: at 1.00-1.05 the sheet realises 97.5% against an implied 98.5%, so such a
# row is priced *above* what it actually does and adding it to anything the book
# multiplies costs about a point of EV per leg. Certainty is real there and it
# is already in the price.
#
# The band that pays is 1.35-1.60, where a 76.7% realised rate meets a 69.4%
# implied one. High confidence and a takeable price are not opposites -- they
# meet in the middle of the ladder, which is exactly where a sheet gated on
# "must clear the threshold" never looked.
CERTAINTY_PRICE_FLOOR = 1.30

# How many singles the file may carry.
#
# It was 15 from the first version and nothing had ever measured what the cap
# was protecting. On 2026-09-07 it excluded 262 rows, and the operator's
# objection was the right one: a row he would not stake alone can still be the
# thing he wants to see, and the cap was making that call for him.
#
# Measured by rebuilding every slate in ``runs/`` at ``max_singles=400`` and
# settling each single:
#
#     rank      n    win    priced    ROI
#      1-15    67  73.1%       52   +13.4%
#     16-25    47  93.6%       28   +14.1%
#     26-50   135  84.4%       57    -7.0%
#     51-100  254  85.8%       66    +1.6%
#    101-400  1302  87.8%      465    -1.8%
#
# The deep ranks *win more* -- 87.4% past rank 15 against 73.1% inside it --
# and return less, because winning more is what a short price buys. So the cap
# was not protecting the file from bad rows; it was hiding the safe ones, which
# are the ones the operator asked for by name.
#
# 40 rather than 400: past rank 50 the rows are near-certain trivia at 1.02 and
# a file nobody finishes reading is not a longer file, it is a shorter one. The
# ordering already puts every priced, takeable row ahead of every unpriced one
# (see ``_append_singles``), so raising the cap cannot push a VALUE row out --
# it only lets the tail through behind them. Pass ``--max-singles`` for more.
MAX_SINGLES = 40

# How many singles one fixture may contribute, per mechanism family and in
# total. Both exist because raising the cap to 40 exposed what the cap had been
# hiding rather than protecting.
#
# On 2026-09-07 the first 40-single file drew **14 of 34 fixtures**, with 22 of
# the 40 rows coming from five of them: Universitatea Craiova 5, Mjällby 5,
# Malmö 4, Barracas 4, Midtjylland 4. Craiova's five were ``goals_total`` 5.5
# UNDER, ``goals_1h_total`` 3.5 UNDER, ``goals_2h_total`` 3.5 UNDER,
# ``goals_for`` 2.5 UNDER and ``corners_total`` 11.5 UNDER -- four readings of
# "do goals happen in this match" presented as four rows. The operator asked
# for more *events*; row-level deduplication by (event, market, subject) cannot
# give him that, because those four are four different markets.
#
# ``mechanism_family`` already exists and the Bet Builder has used it since
# 2026-09-03 (``duplicate_mechanism_family``, 85 exclusions on the 2026-09-06
# slate). The singles list simply never asked it.
#
# One per family, three per fixture: three is what a fixture can say that is
# not a restatement -- scoring, attacking, discipline -- and a fourth row from
# the same match is a fourth line on one of them.
MAX_SINGLES_PER_FAMILY = 1
MAX_SINGLES_PER_EVENT = 3

# The price bands above, as (floor, label, measured edge). Read by
# ``_price_band`` and printed beside every priced single.
_PRICE_BANDS: tuple[tuple[float, str, float], ...] = (
    (1.60, "1.60+", 0.061),
    (1.35, "1.35-1.60", 0.073),
    (1.20, "1.20-1.35", -0.013),
    (1.10, "1.10-1.20", -0.027),
    (1.05, "1.05-1.10", -0.043),
    (0.0, "1.00-1.05", -0.010),
)

# How far above the operator's own book this sheet may claim to be before the
# row stops being a lean and starts being a question about the sample.
#
# The gate it guards is not symmetric, and that asymmetry is the point. p_low is
# a *lower* bound, so sitting below the market is expected and harmless. Sitting
# far above it means one of two things: an edge the book has not priced, or a
# sample that is not measuring this fixture -- and the 2026-09-01 file is a
# clean experiment on which of those is more common. The one row where the gap
# was largest (Superbet 2.27 against a min of 1.38) was the ATP best-of-five
# tie priced off best-of-three data, and it was ranked first precisely because
# it disagreed most.
#
# 0.25, and the number changed meaning before it changed value -- see
# ``disagreement``, which now measures ``p_central`` rather than ``p_low``.
#
# Against ``p_low`` no threshold could work, and 2026-09-01 is the arithmetic
# proof rather than the anecdote. VALUE means ``price >= margin/p_low``, which
# devigs to ``p_low - implied >= p_low*(1 - 1/(margin*overround))`` -- +0.081 for
# a LEAN at p_low 0.50, +0.130 at 0.80. Every VALUE row therefore disagreed with
# the book by at least that much *by construction*, whatever its sample held. A
# threshold above the band (0.15, which is what shipped) is a no-op; one below
# it (0.08, which is where the losses appear to point) is a blanket ban on ever
# outbidding the book. There is no third setting. The gate was measuring our own
# conservatism.
#
# Against ``p_central`` it measures the disagreement itself, and the run-wide
# distribution says so: over that day's 3928 two-sided rows the median gap is
# -0.000 -- the sheet and the devigged book agree, on average, which is the
# calibration check the old number could never have passed. p75 is +0.081, p90
# +0.173, p95 +0.239.
#
# 0.25 is that p95, chosen from the distribution and not from the casualties.
# What it does to the casualties is the check, not the input: the seven singles
# that day's file admitted came out at +0.504, +0.487, +0.418, +0.357, +0.316,
# +0.263 and +0.129, and the eight it rejected at +0.256 or less. So 0.25 flags
# six of the seven losers and three rejected rows that were already unbettable
# on price -- and the seventh, Lincoln, is caught upstream by
# ``count_model_bound`` instead, which is the right place for it: at ladder
# ratio 1.135 it agreed with the book about where the market sat and was simply
# priced too short.
#
# **What this threshold does changed on 2026-09-02: it annotates, it no longer
# demotes.** The sentence above -- flagging a good row costs it its rank -- was
# true and the trade it described was not. A row whose floor sits far above the
# book's devigged price at its own rung is not a broken sample; that gap *is*
# what a bet worth taking looks like from the inside. Demoting on it, against a
# 15-single cap, deletes value from the file in the name of caution: it took
# the day's one real row (WTA aces_total 5.5 OVER at 2.07 vs a 1.8146 floor)
# off the end. The *centre* disagreement -- MAX_LADDER_SIGMA below -- is the
# one with settled evidence behind it and the one that still demotes.
# Whether a player prop may be offered to the operator as a bet.
#
# **Off by default since 2026-09-06, on the first measurement the family has
# ever had against a price.** Every prop row on the five slates with an offer
# artifact, joined to its own posted Superbet price and settled against the
# fixture box scores: 19,154 priced rows over 85 fixtures.
#
#     in the band the coupon bets (p_central 0.50-0.80)
#     ROI -30.5%, clustered CI [-34.0%, -27.1%], n=3056
#
# against -6% to -14% for the team and match markets on the same slates. All
# seven prop markets are negative with a CI clear of zero.
#
# It is not a calibration fault, and that is why no threshold fixes it:
#
#     p_central bucket    ALL props          PRICED props
#     [0.50,0.60)         n=15178  -0.010    n=1421  -0.125
#     [0.60,0.70)         n=12852  -0.004    n=1012  -0.133
#     [0.70,0.80)         n=10867  -0.006    n= 623  -0.132
#     [0.80,0.90)         n=10369  -0.005    n= 270  -0.132
#
# Props in general are calibrated to within a point. Props *the book chooses to
# post* run 12-13 points under their claim at every level of confidence. The
# book is selecting, and it is selecting on the one thing this pipeline does
# not model: playing time. The gap is -0.36 for players who saw under 30
# minutes, -0.18 for 30-70 and -0.08 for 70+.
#
# Three ways out were measured and none of them work:
#
# * **Wait for the teamsheet.** Rows on a *confirmed* lineup measured worse
#   (-0.254, n=280) than rows on a predicted one (-0.117, n=2776).
# * **Raise the bar.** ``PLAYER_PROP_BIAS`` cuts the props clearing a LEAN bar
#   from 596 to 284 and the survivors return -36.7% against the original
#   -36.2%. The bias is flat across the range, so cutting harder removes rows
#   at random with respect to outcome.
# * **Shrink toward the price.** Props are posted OVER-only, so there is no
#   second side to devig and ``bar_components`` returns before the market prior
#   -- 0 of the 12 props ever shipped carried a market probability. The raw
#   ``1/price`` is 0.610 in band against a realised 0.488, so pulling toward it
#   moves the bar the wrong way.
#
# Breaking even in band needs a price near 2.05; the mean posted price is 1.64.
# The arithmetic does not close, so the family does not ship. What would change
# it is an availability model -- P(prop) = P(plays enough) x P(hits | plays) --
# and the second factor is the only one this sheet estimates.
#
# Kept as a flag rather than deleted because the measurement is five slates
# old, the fix is a model this repo could acquire, and a constant that can be
# flipped back is how the next measurement gets made. Props still reach the
# stats sheet in full; this gate is about the coupon.
ALLOW_PLAYER_PROPS = False


def is_player_prop(row: StatsSheetRow) -> bool:
    """Whether this row's subject is one footballer rather than a team or a match."""
    return row.market.startswith("player_")


MAX_MARKET_DISAGREEMENT = 0.25

# How far the sample's own centre may sit from the centre the book's ladder
# implies before the sample stops being a description of this fixture --
# measured in the sample's own standard deviations.
#
# This is the check 2026-09-01 needed and did not have. The pipeline downloads
# Superbet's whole ladder and reads it only one rung at a time, to ask "is this
# price above my threshold". Read *whole*, the ladder is a devigged
# distribution, and it contradicted the losing samples outright:
#
#     Sheffield United corners   mean  2.80  ladder median  5.76   z -1.77  ->  5
#     Birmingham shots           mean  8.20  ladder median 13.18   z -1.74  -> 16
#     Preston shots on target    mean  2.00  ladder median  3.88   z -1.33  ->  4
#     Torino/Monza corners       mean  6.33  ladder median  8.60   z -0.90  -> 16
#     Lincoln shots on target    mean  9.60  ladder median  8.46   z +0.37  ->  3
#
# The last column is what the match returned. In the four losing UNDERs the
# book's median was the better estimate and our sample was the one betting
# against it. No internal statistic can catch that: those samples are
# self-consistent, tight and unanimous. They are simply not measuring the
# quantity being priced -- venue, competition and five observations of it will
# do that.
#
# **In standard deviations and not as a ratio.** The first version of this gate
# compared ``mean/ladder_median`` against a 0.75-1.35 band, and that is the
# wrong shape: it fired on 29.6% of the day's 382 comparable samples, but
# unevenly -- 53% of ``goals_for`` and 0% of ``corners_total``, because a
# 0.3-goal gap is a third of a half-time total and a thirtieth of a shots
# total. It was measuring the size of the mean, not the size of the
# disagreement. Divided by ``row.dispersion`` the median |z| is 0.13-0.58 in
# every market on the board, so one threshold means the same thing everywhere.
#
# 1.25 sits near p97 of that distribution (p50 0.267, p95 0.954, p99 1.738) and
# fires on 3.1% of samples. It takes Sheffield, Birmingham and Preston.
# Torino and Lincoln are left to ``count_model_bound``, which is the right
# layer for them: Lincoln at z +0.37 *agreed* with the book about where the
# market sat and was simply priced too short, and a gate that flagged it would
# be punishing the sample for being correct.
MAX_LADDER_SIGMA = 1.25

# A ladder has to have at least two devigged rungs straddling even money
# before it implies a median at all. One rung gives a probability, not a
# location; a ladder entirely on one side of 0.5 puts the median outside the
# range the book posted, where interpolating it would be invention.
_LADDER_MIN_RUNGS = 2

# What ``ladder_sigma`` reports for a zero-dispersion sample whose mean is not
# the ladder's median: the true value is unbounded, but Infinity is not strict
# JSON and every value past MAX_LADDER_SIGMA reads the same to the gate. Large
# enough that no real sample reaches it (2026-09-01's worst was under 2σ).
_LADDER_SIGMA_SATURATED = 99.0

# Which analyst verdicts change the *weight* the sample gets, rather than the
# margin on top of it. See ``AnalystVeto.reason_class``.
#
# A DOWNGRADE used to mean "one tier step", worth 5% on the price. These two
# classes are not statements about how much headroom a row needs: they say the
# sample is not evidence about this fixture. So the sample's weight goes to
# zero and the row is priced on the book's own devigged number plus the tier
# margin -- which it will almost never beat, because a book does not sell its
# own price at a 10% markup. That is the intended outcome: a row whose evidence
# has been declared uninformative survives only if the operator is being
# offered a price the market itself disagrees with.
#
# Note what this is *not*: it is not a veto. A VETO removes the row. These
# leave it in the file, ranked and annotated, priced off the only number left
# standing. The 2026-09-03 Grenal fouls rows are the case -- three of them,
# downgraded with "conditional on this match the record is 1/3, not 19/21",
# printed as value at 1.78-1.92.
VETO_CLASS_ZERO_WEIGHT = frozenset({"SAMPLE_NOT_REPRESENTATIVE", "ESTIMAND_WRONG"})

# How a fixture's several rungs of one market are told apart, and why they
# needed telling apart at all.
#
# A fixture contributes one single per (market, subject). Which rung it
# contributes used to be decided by the ranking sort -- price surplus, then
# p_low -- and on 2026-09-03 that picked Grêmio-Internacional's cards 7.5 over
# its 8.5. The 8.5 row was 20/20 with the sample's own maximum *below* the
# line; the 7.5 sat on the sample's mode, which is the single worst place to
# put a line. The 8.5 was recorded as ``duplicate_market_for_event``.
#
# The score is expected value at the book's own price -- ``p x price - 1`` --
# with two penalties, both in the same units so they can be read against it.
#
# **A line on the mode is the least informative rung of a ladder.** The mode is
# where the count process piles up, so a half-point either side of it is where
# a small sample's hit rate moves most and means least. One unit, because these
# are counts and the neighbouring integer is the nearest place the sample can
# actually land.
#
# **A sample that has crossed the line has shown it can.** For an UNDER, a
# sample maximum above the line is a demonstrated failure at that rung; for an
# OVER it is a minimum below it. The plan's wording names only the maximum;
# the mirror is written out because a one-sided penalty would push every OVER
# toward the rung its sample has already failed.
#
# 0.05 each, in EV. Unmeasured -- there is no settled ladder-choice experiment
# to set them from -- and deliberately small enough that a 20-point EV gap
# still wins on EV. They break ties between rungs a price cannot separate,
# which is the job.
RUNG_PENALTY_LINE_ON_MODE = 0.05
RUNG_PENALTY_SAMPLE_CROSSES_LINE = 0.05

# Verdicts that halve the sample's weight rather than deleting it, by doubling
# k. A card market with no referee assigned is not measuring nothing -- the two
# clubs' own histories are real -- it is missing the one input with no
# corroborating provider at all, and a referee is worth about a third of the
# spread in a cards line (Bankes 4.15 yellows a match against Oliver's 3.10,
# measured 2026-08-30 in one league).
VETO_CLASS_DOUBLE_K = frozenset({"MISSING_REFEREE"})

# The structural ceiling that also doubles k, for the same reason: ANALYZE sets
# it when the fixture has no ``referee_id`` at all, which is the same fault the
# analyst would write down by hand.
CEILING_DOUBLE_K = frozenset({"MISSING_REFEREE"})

# The structural ceiling that zeroes the sample's weight outright, pricing the
# row off Superbet's own devigged number instead. Mirrors
# ``VETO_CLASS_ZERO_WEIGHT``'s "SAMPLE_NOT_REPRESENTATIVE": ANALYZE sets
# ``context_flags.CEILING_KNOCKOUT_ROUND`` when
# ``fixture_context.round_name`` names a cup/knockout round, and a domestic
# sample does not describe that fixture -- exactly the reasoning an analyst
# wrote by hand for two of 2026-09-08's cup fixtures (Fluminense-Platense's
# ``cards_points_for``, Bournemouth-Lincoln City's ``cards_points_total``)
# and never got to write for the other two, including the fixture that lost
# the day's other VALUE single (Independiente Santa Fe-Vasco da Gama,
# ``goals_2h_total``). See ``runs/2026-09-08/2026-09-08_coupon_review.md``.
CEILING_ZERO_WEIGHT = frozenset({"KNOCKOUT_ROUND"})


class CouponSingle(StrictBaseModel):
    """One standalone bet, with the price that would justify it."""

    rank: int
    event_id: str
    match: str
    competition: str
    kickoff: str
    sport: str
    market: str
    market_label: str
    line: float
    direction: str
    subject: str | None = None
    # Whether ``subject`` names a team or a person. ``_subject`` returns
    # ``player_name or team_name`` and the two are indistinguishable in the
    # artifact, so every machine consumer had to re-derive it from the market
    # taxonomy -- ``*_for`` is a team, ``player_*`` is a person, everything
    # else names nobody. ``settle.py`` needs exactly this distinction and
    # getting it backwards settles a player's shots against his team's, so it
    # is stated here rather than inferred there.
    subject_kind: Literal["team", "player"] | None = None
    # The provider's own id for a player subject, so the artifact names one
    # human. ``subject`` is a display name and a squad can contain two of
    # them -- see ``_ambiguous_player_names``. None for a team, whose name is
    # its identity in this pipeline.
    subject_id: str | None = None
    tier: str
    p_low: float
    # The sheet's own estimate with no bound and no margin in it, carried so
    # ``market_disagreement`` can be checked by hand: the gap is exactly this
    # minus the devigged Superbet price at the same rung. Without it the
    # operator reads a gap he cannot reconstruct, which is how the old
    # p_low-based version of that number went four days unquestioned.
    p_central: float | None = None
    hit_rate: float
    hits: int
    sample_size: int
    cross_provider_agreement: str
    # The evidence behind the word. ``AGREE`` used to be printed alone and
    # covered anything from 2 corroborated matches out of 23 to 23 out of 23.
    corroborated_matches: int = 0
    fair_odds: float
    min_acceptable_odds: float
    # Which probability ``min_acceptable_odds`` was computed from, and what
    # capped it. ``bar_basis`` is the run's setting ("p_central" or "p_low");
    # ``bar_basis_reason`` is None when nothing capped it, and otherwise names
    # the cap -- ZERO_MISS_LAPLACE_CAP or SMALL_SAMPLE_P_LOW.
    #
    # Printed because the minimum is the number the operator acts on and a
    # minimum that moved for a reason he cannot see is a number he has to take
    # on trust. On 2026-09-03 the same 5/5 sample produced a 1.14 bar and a
    # 1.95 bar depending on this field alone.
    bar_basis: str = "p_low"
    bar_basis_reason: str | None = None
    # Which probability the *bar* actually divided into 1, after the caps and
    # the market prior. Not the same as ``p_central`` or ``p_low``: on a shrunk
    # row it is neither, and on a row with no readable market price it is
    # ``bar_sample_probability``.
    bar_probability: float | None = None
    # The sample's own claim after the caps and before the market prior. The
    # gap between this and ``bar_probability`` is how much of the bar is the
    # book's opinion rather than ours.
    bar_sample_probability: float | None = None
    # How much this market's own settled record took off the claim before the
    # book's price entered, and the sentence that says what such rows realised.
    # A separate field rather than another value of ``bar_basis_reason``,
    # because it is not a cap on the sample and can fire alongside one -- and
    # because a bar that moved for two reasons must be able to name both. See
    # ``bet_builder_draft.market_record_correction``.
    bar_calibration: float | None = None
    bar_calibration_note: str | None = None
    # Superbet's own devigged probability for this exact outcome. None when the
    # book posted only one side of the line, which is also when no shrinkage
    # happened. Same number as ``SuperbetComparisonRow.superbet_implied_probability``.
    market_probability: float | None = None
    # ``n / (n + k)``: how much of ``bar_probability`` is the sample's. 0.0
    # means the analyst declared the sample uninformative
    # (``AnalystVeto.reason_class``), not that the sample is empty.
    sample_weight: float | None = None
    # The ``k`` this market family uses, printed so ``w`` can be checked
    # against ``n``. Note this is the *market's* k before any doubling a
    # missing referee or an analyst class applied; ``sample_weight`` is the
    # number that was actually used.
    shrink_k: float | None = None
    market_verdict: str | None = None
    market_price: float | None = None
    market_bookmaker: str | None = None
    tipster: str | None = None
    caveats: list[str] = Field(default_factory=list)
    # --- the operator's own book (SUPERBET, 2026-08-31) --------------------
    #
    # ``min_acceptable_odds`` above has always been a number the operator had
    # to go and check by hand. These fields are that check, done: the price on
    # Superbet for this exact (market, line, direction, subject), or the reason
    # there isn't one.
    #
    # ``superbet_verdict`` is VALUE when a live, active Superbet price is at or
    # above ``min_acceptable_odds``, WITHIN_TOLERANCE when it misses by no more
    # than ``PRICE_TOLERANCE_PCT``, and PRICED_BELOW_THRESHOLD past that. It is
    # not a probability and it never touches p_low; it answers "can this be
    # taken, and how close is the screen to what the bar asks".
    superbet_availability: str | None = None
    superbet_verdict: str | None = None
    superbet_price: float | None = None
    # price - min_acceptable_odds, in odds. Positive is the whole point.
    superbet_surplus: float | None = None
    # The same distance as a percentage of the threshold, which is the form the
    # tolerance is set in and the only form comparable across prices: 0.06 of
    # surplus is 4.6% at 1.30 and 2.2% at 2.70. See PRICE_TOLERANCE_PCT.
    superbet_price_gap_pct: float | None = None
    # Which measured price band this row's price falls in, and what that band
    # has realised. Not a gate and not derived from this row -- it is the
    # settled record of every row ever priced there, attached so a 97%-certain
    # row at 1.03 cannot be mistaken for a free one. See _PRICE_BANDS.
    price_band: str | None = None
    price_band_measured_edge: float | None = None
    # Set when the market exists but our line does not: the closest rung of
    # Superbet's ladder, so a systematic line mismatch is visible in the file
    # a human reads rather than only in an audit artifact.
    superbet_nearest_line: float | None = None
    superbet_nearest_price: float | None = None
    # p_low minus the market-implied probability. Set only when both numbers
    # exist for this exact row (Faza 5c) -- never interpolated, never derived
    # from a different line. None is what puts a row in the "no market
    # reference" section: not excluded, just not comparable to the market.
    edge: float | None = None
    # p_low minus Superbet's own devigged probability for this exact outcome,
    # set when both sides of the line are on the operator's screen. Different
    # from ``edge`` on purpose: ``edge`` compares against a reference book out
    # of bzzoiro's ~88 and exists for only two markets, this compares against
    # the book the operator actually bets into and works on every market it
    # prices both ways.
    #
    # Positive is not automatically good. Past MAX_MARKET_DISAGREEMENT it is
    # the reason the row is *not* at the top of the file.
    market_disagreement: float | None = None
    # ``(mean - ladder_median) / dispersion``: how far the sample's own centre
    # sits from the centre the book's whole devigged ladder implies, in the
    # sample's own standard deviations. 0.0 is agreement about where this
    # market sits, and the sign says which way we lean. The disagreement that
    # matters is here rather than in ``market_disagreement``, which compares
    # one rung's price. Reported even when inside the band, because a reader
    # checking a row needs to see the number that cleared it, not only the
    # ones that did not.
    #
    # None when the book posted fewer than two two-sided rungs for the sample,
    # or a ladder that never crosses even money -- then no median can be read
    # and the gate is inert for that row.
    ladder_sigma: float | None = None
    # True when ``market_disagreement`` exceeded the threshold. Such a row is
    # kept and ranked last rather than dropped: "we and the book are far apart
    # here" is information the operator should have, and deleting it would hide
    # the one class of row most worth a second look.
    needs_review: bool = False
    # The rung the scorer ranked second for this same (fixture, market,
    # subject), printed under the single as "alternatywny szczebel".
    #
    # Printed because the choice between two rungs of one ladder is the part of
    # this file an operator is most likely to disagree with, and before it he
    # could not see that a choice had been made -- the other rung was silently
    # counted as ``duplicate_market_for_event``.
    alternative_line: float | None = None
    alternative_direction: str | None = None
    alternative_price: float | None = None
    alternative_min_acceptable_odds: float | None = None
    # ``p x price - 1`` after penalties, for this rung and for the runner-up.
    rung_score: float | None = None
    alternative_rung_score: float | None = None
    analyst_action: str | None = None
    analyst_reason_class: str | None = None
    analyst_reason: str | None = None


class CouponSlip(StrictBaseModel):
    """One match's Bet Builder draft, with its match identity resolved."""

    rank: int
    event_id: str
    match: str
    competition: str
    kickoff: str
    draft: BetBuilderDraft
    # Slips are ranked by their weakest leg, not their average or their best.
    # A four-leg slip settles on every leg, so its evidence is the evidence of
    # the leg you are least sure about -- averaging would let three strong legs
    # carry a fourth nobody should be betting.
    weakest_leg_p_low: float


class CouponSet(StrictBaseModel):
    """COUPONS artifact for one betting day."""

    run_id: str = ""
    date: str = ""
    generated_at: str
    singles: list[CouponSingle] = Field(default_factory=list)
    slips: list[CouponSlip] = Field(default_factory=list)
    # Deliberately typed None, never a number. See the module docstring.
    combined_price: None = None
    rows_considered: int = 0
    events_considered: int = 0
    # The kickoff cutoff this set was built against, or None when the caller
    # asked for every fixture regardless of clock. Recorded so a file can still
    # be audited after the fact: "why is that match missing" has an answer here.
    not_before: str | None = None
    excluded: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    # What the tipster community picked repeatedly, as an appendix. Typed as a
    # separate model that carries no probability and no price, and nothing in
    # this module reads it -- it cannot reach ranking, tiering or the value
    # test. See ``tipster_consensus``. None means the artifact was not passed.
    tipster_consensus: TipsterConsensus | None = None


def _price_band(price: float | None) -> tuple[str | None, float | None]:
    """``(band label, that band's measured edge)`` for one posted price.

    The edge is a property of the *band* over 668 settled rows, not of this row
    -- attaching it is how "97% certain at 1.03" stops reading as free money.
    See ``_PRICE_BANDS``.
    """
    if not isinstance(price, (int, float)) or price <= 1.0:
        return None, None
    for floor, label, edge in _PRICE_BANDS:
        if price >= floor:
            return label, edge
    return None, None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def market_label(market: str) -> str:
    return MARKET_LABELS.get(market, market.replace("_", " "))


def _subject(row: StatsSheetRow) -> str | None:
    """Whose line this is: a player, a team, or nobody (a match total)."""
    if row.player_name:
        return row.player_name
    if row.team_name:
        return row.team_name
    return None


def _subject_key(row: StatsSheetRow) -> tuple[str | None, str | None]:
    """Whose line this is, as an *identity* rather than as a display name.

    The one-per-market-per-fixture rule dedupes on this, and it used to dedupe
    on ``_subject`` -- the display name. Juventude fielded two players called
    Marcos Paulo on 2026-09-01 (bzzoiro ids 187 and 17556, ten appearances
    each, means of 1.3 and 0.8 shots), so their rows were indistinguishable:
    the second was counted as ``duplicate_market_for_event`` and dropped, and
    which of the two survived depended on the ranking order. 46 rows on that
    slate collided this way.

    Teams keep the name, because a team name *is* its identity here -- the
    dossier has exactly two of them and ``_side_for_team`` matches on the name.
    """
    if row.player_id or row.player_name:
        return (row.player_id, row.player_name)
    return (None, row.team_name)


def _ambiguous_player_names(rows: list[StatsSheetRow]) -> set[tuple[str, str]]:
    """``{(event_id, player_name)}`` naming more than one person.

    A bet the operator cannot identify is not a bet. Superbet's ladder is
    keyed by *its* spelling of a player and ``player_alias_index`` resolves
    ours to theirs by name, so with two Marcos Paulos in one squad both of our
    rows join to whichever single line Superbet posted -- one of them is
    certainly being priced against the other's market. That is the
    Benoit-Paire failure shape: real numbers, real table, wrong human.

    So the rows are kept on the sheet, where the analyst can see them, and
    refused a place in the coupon.
    """
    by_name: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        if not row.player_name:
            continue
        by_name.setdefault((row.event_id, row.player_name), set()).add(row.player_id or "")
    return {key for key, ids in by_name.items() if len(ids) > 1}


def _subject_kind(row: StatsSheetRow) -> str | None:
    """Whether ``_subject`` returned a person or a team.

    Read off the row's own identity fields, not off the market name: a market
    taxonomy is a naming convention and this is a fact the row carries.
    """
    if row.player_name:
        return "player"
    if row.team_name:
        return "team"
    return None


def _has_market_reference(row: StatsSheetRow) -> bool:
    """Whether this row can be ranked against a price rather than just p_low.

    Not the same question as "does market_signal exist": a NO_MARKET_DATA
    verdict still carries a MarketSignalColumn, just with
    ``market_implied_probability`` unset. Today only corners_total and
    goals_total (SIGNAL_MARKETS) can ever answer True.
    """
    return (
        row.market_signal is not None
        and row.market_signal.market_implied_probability is not None
    )


def required_price(
    row: StatsSheetRow,
    tier: str,
    *,
    basis: str = "p_low",
    market_probability: float | None = None,
    shrink_k: float | None = None,
    force_weight: float | None = None,
) -> float:
    """``min_acceptable_odds`` for one row, in exactly one place.

    The arithmetic is ``1/p`` times the tier margin, rounded to four decimals --
    and it used to be written out three separate times inside
    ``build_coupons``: once in the ``require_superbet_value`` probe, once in the
    body that fills ``CouponSingle.min_acceptable_odds``, and once in
    ``_superbet_surplus`` for the ranking. Three copies of the number the
    operator actually acts on, one of which decides the ordering and another of
    which is printed. They agreed; nothing made them agree.

    ``p`` is no longer just ``p_low`` or ``p_central``: see
    ``bet_builder_draft.bar_components`` for the two caps and the market prior
    that sit between the sheet and this number.
    """
    return required_odds(
        row,
        tier,
        basis=basis,
        market_probability=market_probability,
        shrink_k=shrink_k,
        force_weight=force_weight,
    )


def _edge(row: StatsSheetRow) -> float:
    """This row's own probability minus the market's, for this exact row.

    Measured on ``p_central`` and not ``p_low``, for the same reason
    ``disagreement`` is (see its docstring). ``market_implied_probability`` is
    a *devigged* number -- a central estimate -- and ``p_low`` is a lower
    bound, so subtracting one from the other compared two different kinds of
    quantity and called the remainder an edge. It is the ranking key for the
    whole second group of singles and it is printed in the coupon file as
    "Przewaga", so the mismatch reached the operator twice over: Torino/Monza's
    corners went out on 2026-09-01 labelled +9.7pp when this row's actual
    disagreement with the devigged market was +31.6pp.

    Understating it is not the safe direction. The number is read as "how much
    of an edge is here", and a floor-versus-centre subtraction makes a large
    disagreement look like a small one -- which is the reading that gets a
    broken sample staked.

    Ranking by it descending is legitimate because it is *comparable*: the
    run-wide median gap between ``p_central`` and the devigged price is -0.000,
    so the sheet is not systematically on either side of the market.

    It is **not** bounded, and this docstring used to claim it was -- that
    ``over_disagreement`` "removes everything past ``MAX_MARKET_DISAGREEMENT``
    first". It does not, and never did: that predicate is computed for every
    row and then used for exactly two things, the row's ``needs_review`` flag
    and a caveat line. Nothing has ever been removed or demoted by it, so the
    stated justification for this sort rested on a safety property no code
    implemented.

    The claim is corrected rather than the code, because the measurement says
    the bound would cost money. Over 16,352 settled sides of 8,176 two-sided
    Superbet rungs on the six slates with an offer artifact, bucketed by how
    far ``p_central`` sits above the *devigged* price:

        gap [+0.05,+0.15)   n=2957   ROI  -1.4%   [ -7.7%,  +5.1%]
        gap [+0.15,+0.25)   n= 675   ROI  -9.3%   [-24.2%,  +6.1%]
        gap [+0.25,+0.40)   n= 229   ROI +29.6%   [ -6.0%, +71.3%]

    The widest disagreements are the *only* bucket on the board with a positive
    point estimate. The interval is wide and contains zero, so this is not
    evidence that they are good -- it is evidence that they are not reliably
    bad, which is all a demotion needs to be wrong. ``MAX_LADDER_SIGMA`` is the
    gate with settled evidence behind it and it already removes the broken
    samples; see its comment, and the ``MAX_MARKET_DISAGREEMENT`` comment above
    for the day a demotion on this gap took the file's one real row off the
    end.

    Ranking an unbounded disagreement descending *is* what put six losers at
    the top of 2026-09-01's file -- but what they had in common was a sample
    whose centre was two standard deviations off the book's, which is the
    ladder gate's business, not this one's.

    Falls back to ``p_low`` on a row written before ``p_central`` existed,
    which reproduces the old number rather than inventing one. Never called on
    a row without a market reference; see ``_has_market_reference``.
    """
    ours = row.p_central if row.p_central is not None else row.p_low
    return ours - row.market_signal.market_implied_probability


def unreviewed_sibling_note(
    row: StatsSheetRow, veto_index, vetoes: list[AnalystVeto] | None
) -> str | None:
    """Say so when the analyst struck this metric at the *other* scope.

    A per-team row and a match-total row are the same quantity read twice: if
    a team's own shots on target are understated, so is the match's. The
    analyst writes vetoes per market, so an objection to the estimand lands on
    whichever scope he happened to be reading, and the sibling ships unmarked.

    Live on 2026-09-06: Corinthians-Chapecoense had ``shots_on_target_for``,
    ``shots_for``, ``goals_for`` and ``cards_points_for`` all downgraded --
    "the sample measures Corinthians in any match, the market settles
    Corinthians at home against the worst defence in the league" -- while
    ``shots_on_target_total`` 9.5 UNDER, the only *bettable* row on that
    fixture, carried no mark at all. On the analyst's own revised centre it
    still cleared its price (0.666 against a 0.592 break-even), so nothing was
    lost that day; nothing had noticed either.

    **This reports and never widens.** Extending a veto by rule is how the
    analyst's own picks were once inverted -- see the note on stripping a
    player key from a prop veto -- and a per-team objection genuinely does not
    always carry: the opponent's half of a match total is untouched by it. The
    operator gets told the asymmetry exists and decides.
    """
    if not vetoes:
        return None
    sibling = scope_sibling(row.market)
    if sibling is None or veto_index.for_row(row) is not None:
        return None
    struck = {
        veto.market for veto in vetoes
        if veto.event_id == row.event_id and veto.market == sibling
    }
    if not struck:
        return None
    return (
        f"analityk obniżył `{sibling}` na tym meczu, a tego wiersza nie objął "
        "— to ta sama wielkość czytana w innym zakresie, więc jego zastrzeżenie "
        "może się przenosić; sprawdź jego uzasadnienie, zanim weźmiesz ten kurs"
    )


def _caveats(row: StatsSheetRow) -> list[str]:
    notes: list[str] = []
    if row.cross_provider_agreement == "SINGLE_SOURCE":
        notes.append("jedno źródło — nic tego nie potwierdza")
    if row.cross_provider_agreement == "PARTIAL_AGREE":
        notes.append(
            f"drugie źródło widziało tylko {row.corroborated_matches}/"
            f"{row.sample_size} meczów tej próby — to nie jest potwierdzona próba"
        )
    if row.cross_provider_agreement == "DISAGREE":
        notes.append("providerzy się nie zgadzają — wartości nieuśrednione")
    if row.player_id and (row.lineup_status or "") != "confirmed":
        notes.append(f"skład {row.lineup_status or 'nieznany'} — premisa to zgadywanka")
    if row.sample_size < 8:
        notes.append(f"mała próba (n={row.sample_size})")
    if row.hits >= row.sample_size and row.sample_size > 0:
        # No miss in the sample, so the *Wilson* half of p_low is a function of
        # n alone. It used to say that p_low was therefore identical on every
        # line above the sample's maximum and that only the price could rank
        # the rungs -- which was true, was the 2026-09-01 defect, and is no
        # longer true: ``count_model_bound`` caps Wilson with the line's own
        # distance from the sample, so the rungs are ordered again. What
        # survives is the narrower and still important warning: a sample with
        # no miss reports no observed failure rate, so everything separating
        # these rungs is now model rather than measurement.
        notes.append(
            f"brak pudła w próbie ({row.hits}/{row.sample_size}) — próba nie "
            "pokazuje ani jednej porażki, więc szczeble tego rynku rozdziela "
            "rozkład dopasowany do próby, nie zmierzony odsetek trafień"
        )
    if is_trivial_under(row):
        notes.append("niska linia UNDER — łatwa do trafienia i zwykle wyceniana ~1.05")
    drift = drifted_markets().get(row.market)
    if drift:
        notes.append(_drift_caveat(row.direction, drift))
    for reason in row.lean_ceiling_reasons:
        notes.append(_LEAN_CEILING_TEXT.get(reason, f"ograniczenie do LEAN: {reason}"))
    for reason, count in (row.observation_flags or {}).items():
        notes.append(
            _OBSERVATION_FLAG_TEXT.get(reason, f"{reason} w {count} obserwacjach")
            .format(count=count)
        )
    return notes


def _drift_caveat(direction: str, drift: Mapping[str, object]) -> str:
    """The caveat every row of a drifted market carries, naming the side.

    On the 2026-09-07 coupon this market put four rows on the file and three of
    them were UNDERs -- the overstated side -- with nothing anywhere saying so:
    the measurement existed only in a script's stdout.

    ``overstated_side`` is read from the config rather than re-derived from the
    sign of ``delta``, because that derivation is the one this whole path exists
    to get right and doing it twice is how the two copies come to disagree. It
    is a statement and not a discount: no probability, centre or threshold on
    this row has been moved by it.
    """
    delta = float(drift.get("delta") or 0.0)
    side = str(drift.get("overstated_side") or "")
    magnitude = (
        f"{abs(delta):.2f} na mecz {'nisko' if delta > 0 else 'wysoko'} "
        f"({int(drift.get('fixtures') or 0)} rozliczonych meczów, "
        f"z={float(drift.get('z') or 0.0):+.2f})"
    )
    if direction == side:
        return (
            f"dryf próbki: biegnie {magnitude} wobec tego, co bukmacher "
            f"rozlicza — a {side} to właśnie strona, którą taki dryf zawyża, "
            f"czyli ten wiersz wygląda pewniej, niż jest. Nigdzie nie "
            f"skorygowane (wymaga dowodu out-of-sample)"
        )
    return (
        f"dryf próbki: biegnie {magnitude} wobec tego, co bukmacher rozlicza "
        f"— zawyża {side} na tym rynku, więc ten {direction} jest raczej "
        f"zaniżony. Nigdzie nie skorygowane (wymaga dowodu out-of-sample)"
    )


# Why a row cannot be a CALL, in the coupon file's own words. Keyed by the
# codes ANALYZE writes into ``StatsSheetRow.lean_ceiling_reasons``.
_LEAN_CEILING_TEXT: dict[str, str] = {
    "RUNG_SEPARATED_BY_MODEL": (
        "sąsiedni szczebel ma identyczną liczbę trafień — to, co je rozdziela, "
        "to rozkład dopasowany do próby, nie obserwacja"
    ),
    "KNOCKOUT_SECOND_LEG": (
        "rewanż dwumeczu przy wyrównanym dwumeczu — ten mecz nie musi wyglądać "
        "jak żaden z próby"
    ),
    "KNOCKOUT_ROUND": (
        "runda pucharowa (nazwa rundy bez \"Matchday\") — próba jest ligowa, "
        "kierunek błędu nieznany, cena wyłącznie z rynku"
    ),
    "DERBY": "derby — kartki i faule zachowują się inaczej niż w próbie",
    "MISSING_REFEREE": "brak przypisanego sędziego — rynek kartek bez sędziego to zgadywanka",
    "NO_REFERENCE_SOURCE": (
        "brak dostawcy referencyjnego dla tego sportu (bzzoiro-tennis = HTTP 402) "
        "— żaden wiersz tenisowy nie może być CALL"
    ),
}

# Caveats about observations that were *used* but are less than certain --
# ``sample_excluded`` covers the ones that were removed instead.
_OBSERVATION_FLAG_TEXT: dict[str, str] = {
    "RED_TYPE_UNKNOWN": (
        "w {count} obserwacjach nie dało się ustalić rodzaju czerwonej kartki — "
        "każda policzona jako bezpośrednia (2 pkt), co zawyża drugą żółtą o 1 pkt"
    ),
    "RED_COUNT_CONFLICT": (
        "w {count} obserwacjach dwa źródła podały różną liczbę czerwonych — "
        "wzięta większa"
    ),
}


def _veto_class_effect(veto: AnalystVeto) -> str:
    """What the class did to the arithmetic, in the header's own words.

    The tier step is printed already and is the smaller half of the effect: the
    classes that matter change the sample's *weight*, and a header that showed
    only "CALL→LEAN" would understate a downgrade that took the sample out of
    the price entirely.
    """
    if veto.action != "DOWNGRADE":
        return ""
    if veto.reason_class in VETO_CLASS_ZERO_WEIGHT:
        return ", waga próby = 0 (cena wyłącznie z rynku)"
    if veto.reason_class in VETO_CLASS_DOUBLE_K:
        return ", k podwojone (próba waży o połowę mniej)"
    return ""


def _veto_scope(veto: AnalystVeto) -> str:
    """How wide this veto is, in the coupon file's own words.

    A market-wide veto printed as "cards_total 4.5 UNDER" would read as though
    the analyst had struck one line, which is the misreading that let a second
    line of the same broken market ship as a Bet Builder leg.
    """
    line = "wszystkie linie" if veto.line is None else f"{veto.line}"
    direction = veto.direction or "OVER+UNDER"
    return f"{veto.market} {line} {direction}"


def _kickoff_passed(kickoff: str, not_before: datetime | None) -> bool:
    """True when this fixture has already started and is no longer bettable.

    An unparseable or missing kickoff returns False. Not knowing when a match
    starts is not evidence that it started -- dropping it would silently hide a
    live fixture, which is the failure this check exists to prevent.
    """
    if not_before is None or not kickoff:
        return False
    try:
        start = datetime.fromisoformat(kickoff)
    except ValueError:
        return False
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return start <= not_before


def _tipster_summary(row: StatsSheetRow) -> str | None:
    """Agreement on this row, or -- failing that -- presence on this fixture.

    The two are different claims and are written differently on purpose. "2/3"
    means three tipsters addressed *this bet* and two took this side. Nothing
    else in this cell ever reads as a ratio.

    A ratio is also the rare case. Tipsters price goals, corners and games; the
    rows that reach a coupon are per-team shots and corners, so the two land on
    the same row only by coincidence -- zero of fifteen singles on 2026-09-01.
    What is far from rare is a tipster having covered the fixture at all, which
    on the same day was true of nine of those fifteen. That is worth showing,
    and showing it as "mecz: 4" rather than as a fraction is what stops it being
    mistaken for agreement the row does not have.
    """
    column = row.tipster
    if column is None:
        return None
    if column.verdict != "NO_COVERAGE":
        cell = f"{column.agree}/{column.agree + column.oppose}"
        # A ratio says how many agreed. It does not say whether the ones who
        # agreed have ever been right, and an unqualified "2/3" is exactly what
        # lets a tipster on 25% from eight bets read as support. So when the
        # backers published a record, the floor on it joins the cell as
        # "2/3 · rek. 61%", and a record that does not clear a coin flip is
        # named rather than quietly averaged in.
        #
        # The opposing side gets the same treatment under a "przeciw" label,
        # and only when nobody agreed. A credible tipster arguing against the
        # row is news of the same size as one arguing for it; on a split cell
        # the agreement is what the row is claiming, so that is what the
        # record qualifies.
        parts = []
        if column.agree_record_low is not None:
            parts.append(f"rek. {column.agree_record_low * 100:.0f}%")
        if column.agree_unproven:
            parts.append(f"{column.agree_unproven} bez rekordu")
        if not parts and column.agree == 0:
            if column.oppose_record_low is not None:
                parts.append(f"przeciw rek. {column.oppose_record_low * 100:.0f}%")
            if column.oppose_unproven:
                parts.append(f"przeciw: {column.oppose_unproven} bez rekordu")
        return " · ".join([cell, *parts])
    if not column.considered:
        return None
    # Nobody addressed this bet. Say who was there and, if the fixture drew a
    # 1X2 or BTTS lean, what it was -- a different market, never this one.
    lean = " ".join(f"{side} {count}" for side, count in column.lean.items())
    return f"mecz: {column.considered}" + (f" · {lean}" if lean else "")


# Values that mean "nothing to report" for the entitlement header note below:
# ENTITLED is healthy, and NOT_ATTEMPTED alone (never probed, or the run's
# call budget ran out before reaching it) already surfaces as its own
# data_gap message per event -- it is not evidence the entitlement is gone.
_ENTITLEMENT_HEALTHY = frozenset({"ENTITLED", "NOT_ATTEMPTED"})


def _entitlement_note(market_context: MarketContextV1 | None) -> str | None:
    """docs/PLAN_BOGATE_STATYSTYKI.md 3bis.6.

    A lapsed or missing "Football Unlimited" entitlement takes goals' and
    corners' market price *and* model reference at once -- the two families
    Faza 5c ranks by edge -- and until now that only showed up buried in
    per-event ``data_gaps``. Read straight from ``EventMarketContext.
    comparison_entitlement`` (not the coarser run-level bool, which cannot
    distinguish "never probed" from "probed and errored") so an ERROR state
    is caught too, not just a confirmed NOT_ENTITLED.
    """
    if market_context is None or not market_context.events:
        return None
    seen = sorted({e.comparison_entitlement for e in market_context.events})
    if set(seen) <= _ENTITLEMENT_HEALTHY:
        return None
    return (
        'UWAGA: uprawnienie "Football Unlimited" nie jest w pełni aktywne w tym '
        f"runie (comparison_entitlement: {', '.join(seen)}) — część lub cały "
        "ten kupon powstał BEZ kursu i modelu rynkowego na gole/rożne, więc "
        "ranking po przewadze (edge, Faza 5c) go tam nie widział. Sprawdź "
        "subskrypcję bzzoiro przed obstawieniem."
    )


def _stale_sheet_note(
    stats_sheet: StatsSheetV1, superbet_offer: SuperbetOfferV1 | None
) -> str | None:
    """Say so when the coupon priced from a *newer* offer than the sheet on disk.

    ``--refresh-offer`` re-fetches the board and prices the coupon from it, but
    it does not rewrite ``<date>_event_dossiers_stats_sheet.json`` -- that file
    keeps the ``row.superbet.price`` column from whenever ANALYZE last ran. The
    two then disagree, silently, and the sheet is what every downstream reader
    opens: the analyst agents, ``diff_stats_sheet.py``, and any hand check of
    "is this price real".

    Measured on 2026-09-06: the coupon was built at 18:51Z from an offer fetched
    at 18:51Z while the sheet on disk carried prices from 16:00Z. Remo-Flamengo
    10.5 UNDER read 1.60 in the coupon and 1.58 in the sheet, and the devigged
    market probability behind the bar differed in the third decimal -- small,
    but it is the number the threshold is derived from, and a reader reconciling
    the two has no way to tell which is current.

    Reported rather than repaired here because repairing it means rewriting a
    164 MB artifact from inside a function that is documented pure. The note
    names the gap in minutes so the reader knows which file to trust.
    """
    if superbet_offer is None:
        return None
    sheet_at = _moment_utc(getattr(stats_sheet, "generated_at", None))
    offer_at = _moment_utc(getattr(superbet_offer, "generated_at", None))
    if sheet_at is None or offer_at is None or offer_at <= sheet_at:
        return None
    minutes = int((offer_at - sheet_at).total_seconds() // 60)
    if minutes < 1:
        return None
    return (
        f"Oferta użyta do wyceny tego kuponu jest o {minutes} min świeższa niż "
        f"kolumna cen w arkuszu na dysku (oferta {offer_at:%H:%M}Z, arkusz "
        f"{sheet_at:%H:%M}Z). Ceny i progi **w tym pliku** pochodzą z tej "
        "świeższej oferty; `row.superbet.price` w arkuszu jest za nimi i nie "
        "zgodzi się z tabelami powyżej. Przy sprawdzaniu ceny ufaj temu plikowi "
        "albo samemu ekranowi, nie arkuszowi."
    )


def _moment_utc(value: object) -> datetime | None:
    """An ISO timestamp as an aware UTC datetime, or None if it is not one."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def build_coupons(
    stats_sheet: StatsSheetV1,
    event_list: EventListV1 | None = None,
    *,
    max_singles: int = MAX_SINGLES,
    max_slips: int = 8,
    max_legs: int = 4,
    min_p_low: float = MIN_SINGLE_P_LOW,
    not_before: datetime | None = None,
    vetoes: list[AnalystVeto] | None = None,
    market_context: MarketContextV1 | None = None,
    superbet_offer: SuperbetOfferV1 | None = None,
    require_superbet_value: bool = False,
    bar_basis: str = "p_central",
    shrink_k: float | None = None,
    allow_player_props: bool = ALLOW_PLAYER_PROPS,
    price_tolerance_pct: float = PRICE_TOLERANCE_PCT,
    max_per_family: int = MAX_SINGLES_PER_FAMILY,
    max_per_event: int = MAX_SINGLES_PER_EVENT,
) -> CouponSet:
    """Turn a finished stats sheet into the day's singles and slips.

    Pure: no network, no DB, no clock. Given the same artifact *and the same*
    ``not_before`` it returns the same coupons, which is what makes a bad call
    reviewable after the fact -- the cutoff is an argument, never a call to
    ``now()`` inside, precisely so that property survives.

    ``not_before`` drops fixtures that have already kicked off. A coupon file
    is read hours after it is written, and a match in the past is not a bet at
    any price, however good its ``p_low`` looks. Pass ``None`` to keep the
    whole day, which is what a post-hoc review of yesterday wants.

    ``vetoes`` is bet-analyst's read (Faza 5e), applied by exact
    ``(event_id, market, line, direction)`` match. A row with no matching veto
    is unaffected -- an empty or absent list is the default healthy state, not
    a degraded one.

    ``market_context`` is optional and read for exactly one thing: whether the
    "Football Unlimited" entitlement was confirmed missing or erroring
    anywhere in the run (Faza 3bis.6). Absent, it stays silent -- the same
    "unknown is not degraded" rule ``vetoes`` follows.

    ``superbet_offer`` is the operator's own book. It changes the *order* of
    the file and never its arithmetic: a row Superbet actually prices at or
    above ``min_acceptable_odds`` is ranked above one it does not, because that
    is the difference between a bet and a target. Rows the book does not carry
    are kept and labelled rather than dropped -- "Superbet has no 4.5 line for
    shots on target" is the single most useful sentence this pipeline can
    print on a day like 2026-08-31, and dropping those rows would delete it.
    Absent, every superbet_* field stays None and the file is byte-identical
    to the pre-Superbet one.

    ``shrink_k`` overrides the per-market ``k`` in the market prior for every
    row, which is what the backtest's arm comparison varies. None uses each
    market's own value (``bet_builder_draft.shrink_k_for_market``), and a run
    that does not pass it behaves exactly as the day's coupon did. ``0``
    disables the prior outright, which is the pre-2026-09-03 arm.

    ``require_superbet_value`` narrows the file to only what the book will
    actually pay for. Off by default and deliberately so: on a normal day it
    empties the file, and "no coupon" is strictly less information than "a
    coupon in which every row is labelled unbettable and says why".
    """
    events = {e.event_id: e for e in (event_list.events if event_list else [])}
    superbet_events = {
        offer.event_id: offer
        for offer in (superbet_offer.events if superbet_offer else [])
        if offer.event_id
    }
    # Superbet spells players its own way, so a prop row cannot find its price
    # without this. Built from the sheet's own player names -- the exact set the
    # lookups below will ask about -- and shared by singles and slip legs so the
    # two can never resolve the same prop to different humans.
    our_players: dict[str, set[str]] = {}
    for sheet_row in stats_sheet.rows:
        if sheet_row.player_name:
            our_players.setdefault(sheet_row.event_id, set()).add(sheet_row.player_name)
    player_aliases = (
        player_alias_index(superbet_offer, our_players) if superbet_offer else {}
    )

    def superbet_for(
        row: StatsSheetRow, minimum: float | None
    ) -> dict[str, object]:
        """Superbet's answer for one row, in the shape CouponSingle wants.

        Returns an empty dict when no offer artifact was passed, so the fields
        stay None and a pre-Superbet coupon is reproduced exactly.
        """
        if superbet_offer is None:
            return {}
        availability, exact, near_line, near_price = lookup_line(
            superbet_events.get(row.event_id),
            market=row.market,
            line=row.line,
            direction=row.direction,
            team_name=row.team_name,
            player_name=row.player_name,
            player_aliases=player_aliases.get(row.event_id, {}),
        )
        verdict: str | None = None
        surplus: float | None = None
        gap_pct: float | None = None
        if availability == "OFFERED" and exact is not None and minimum is not None:
            surplus = round(exact.price - minimum, 4)
            gap_pct = round((exact.price / minimum - 1.0) * 100.0, 2)
            if exact.price >= minimum:
                verdict = "VALUE"
            elif gap_pct >= -price_tolerance_pct:
                verdict = "WITHIN_TOLERANCE"
            else:
                verdict = "PRICED_BELOW_THRESHOLD"
        elif availability != "OFFERED":
            verdict = availability
        band, band_edge = _price_band(exact.price if exact else None)
        return {
            "superbet_availability": availability,
            "superbet_verdict": verdict,
            "superbet_price": exact.price if exact else None,
            "superbet_surplus": surplus,
            "superbet_price_gap_pct": gap_pct,
            "price_band": band,
            "price_band_measured_edge": band_edge,
            "superbet_nearest_line": near_line,
            "superbet_nearest_price": near_price,
        }

    _implied_cache: dict[tuple, float | None] = {}

    def superbet_implied(row: StatsSheetRow) -> float | None:
        """Superbet's own probability for this outcome, margin removed.

        One implementation, in ``superbet_offer.devigged_probability``: the
        SUPERBET comparison artifact records the same number and the bar now
        shrinks toward it, so a second copy here would be a second answer to
        the question that decides a minimum price.

        Returns None when the opposite side is not posted, which is common on
        one-way markets. None disables the disagreement gate *and* the market
        prior for that row: we cannot say the book disagrees with us, or move
        toward it, if we cannot read what it thinks.
        """
        if superbet_offer is None:
            return None
        key = (row.event_id, row.market, row.line, row.direction,
               row.team_name, row.player_name)
        if key not in _implied_cache:
            _implied_cache[key] = devigged_probability(
                superbet_events.get(row.event_id),
                market=row.market,
                line=row.line,
                direction=row.direction,
                team_name=row.team_name,
                player_name=row.player_name,
                player_aliases=player_aliases.get(row.event_id, {}),
            )
        return _implied_cache[key]

    def disagreement(row: StatsSheetRow) -> float | None:
        """How far this row's own opinion sits above the operator's book.

        Measured against ``p_central`` and not ``p_low``. The floor is a lower
        bound and ``min_acceptable_odds`` stacks a 5-10% tier margin on top of
        it, so ``p_low - implied`` is dominated by our own conservatism: it is
        pinned above +0.08 for *every* row that clears its price, whatever the
        sample says. A gate on that number can be a no-op or a blanket ban and
        nothing in between, which is how 2026-09-01 shipped with the threshold
        at 0.15 -- above six of its seven losers -- and looked calibrated.

        ``p_central`` carries no margin and no bound, so the difference is a
        disagreement about the outcome and nothing else. Rows written before
        the field existed fall back to ``p_low``, which reproduces the old
        number exactly rather than inventing one.
        """
        implied = superbet_implied(row)
        if implied is None:
            return None
        ours = row.p_central if row.p_central is not None else row.p_low
        return round(ours - implied, 4)

    # Where the book puts this market's centre, from the offer and deliberately
    # not from the sheet.
    #
    # The sheet is the wrong source and would make the check unreliable in
    # exactly the cases it is for: ``select_lines`` trims an offer-driven
    # ladder to ``MAX_OFFERED_LINES_PER_SAMPLE`` rungs closest to the sample's
    # own median, so a sample sitting far from the book's centre -- the defect
    # being hunted -- is the one whose sheet rows cover least of the ladder.
    # Reading the sheet would have let the gate go quietly inert on the worst
    # rows and left no trace that it had.
    _ladder_centre_cache: dict[tuple, float | None] = {}

    def ladder_median(row: StatsSheetRow) -> float | None:
        """The centre Superbet's own devigged ladder implies for this sample.

        Two or more two-sided rungs give it by interpolation; a single rung
        gives it from the pivot and the sample's own spread. Both live in
        ``superbet_offer.ladder_centre`` -- see its docstring for why the second
        path was added and what it assumes.

        Keyed on the sample, not the row, so every rung of one market shares
        one answer. ``dispersion`` is part of the key because it feeds the
        single-rung path.
        """
        key = (row.event_id, row.market, row.team_name, row.player_name,
               row.dispersion)
        if key in _ladder_centre_cache:
            return _ladder_centre_cache[key]
        cdf = devigged_ladder(
            superbet_events.get(row.event_id),
            market=row.market,
            team_name=row.team_name,
            player_name=row.player_name,
            player_aliases=player_aliases.get(row.event_id, {}),
        ) if superbet_offer is not None else {}
        result = ladder_centre(cdf, dispersion=row.dispersion)
        _ladder_centre_cache[key] = result
        return result

    def ladder_sigma(row: StatsSheetRow) -> float | None:
        """``(sample mean - ladder median) / dispersion``, signed.

        Signed rather than absolute because the direction is the diagnosis: a
        negative z is a sample that thinks this market runs colder than the
        book does, which is what every one of 2026-09-01's losing UNDERs was.

        A zero dispersion does not disable the check. The floor is
        ``sqrt(mean)``, so dispersion is 0 exactly when the sample is all
        zeros -- the provider-fabrication class from 2026-09-01 -- and such a
        sample sitting away from a readable ladder median is *infinitely* far
        from the book in its own units, not unreadable. Returning None here
        made the most broken sample possible the only one the gate could not
        touch, and it shipped at rank 1. Saturated to a finite value so the
        artifact stays strict JSON; anything past MAX_LADDER_SIGMA reads the
        same to the gate.
        """
        centre = ladder_median(row)
        if centre is None or row.mean is None:
            return None
        if not row.dispersion:
            if row.mean == centre:
                return 0.0
            return math.copysign(_LADDER_SIGMA_SATURATED, row.mean - centre)
        return round((row.mean - centre) / row.dispersion, 4)

    def off_ladder(row: StatsSheetRow) -> bool:
        """Whether the sample and the book disagree about *where* the
        distribution is, as opposed to how heavy its tail is.

        Only the first disagreement is disqualifying. A sample that agrees
        with the book about the centre and differs about the tail is the shape
        a real edge has; a sample whose centre is nearly two of its own
        standard deviations from the book's is describing another fixture,
        another venue or another competition, and its tail is not evidence
        about anything.
        """
        sigma = ladder_sigma(row)
        return sigma is not None and abs(sigma) > MAX_LADDER_SIGMA

    def over_disagreement(row: StatsSheetRow) -> bool:
        """Whether this row disagrees with the operator's own book too much to
        lead the file -- on the price of its line, or on where its market sits.

        **The saturation exemption is gone, and it is why 2026-09-01 lost.**
        It read: a row that has not missed once carries a ``p_low`` that
        depends only on ``n``, identical at every line above the sample's
        maximum -- Sheffield United's corners scored 0.565508505247919 at 4.5,
        5.5, 6.5 and 7.5 alike off a sample whose highest value was 4 -- so
        ``p_low - market`` tracked the price and nothing else, and the gate
        would have fired hardest on whichever rung paid best. All of that was
        true. The conclusion drawn from it was to stop gating those rows.

        What it should have been was to stop ``p_low`` being constant, because
        the constancy was the defect and the gate was the alarm. Exempting the
        saturated rows disabled the alarm on precisely the rows that had it:
        five of the seven singles that day were saturated, every one of them
        cleared the gate, and every one of them lost.

        ``p_low`` is now line-aware -- ``analyze.count_model_bound`` caps
        Wilson with a bound that reads the line's distance from the sample -- so
        a saturated row no longer carries the same number down the ladder and
        the gap means what the gate always assumed it meant. The exemption has
        nothing left to correct for.

        The ladder check is the second half, and it is independent. A row can
        sit within ``MAX_MARKET_DISAGREEMENT`` on its own rung and still be
        built on a sample whose centre is nowhere near the book's; four of that
        day's six losers were exactly that.
        """
        if off_ladder(row):
            return True
        gap = disagreement(row)
        return gap is not None and gap > MAX_MARKET_DISAGREEMENT

    veto_index = VetoIndex(vetoes)
    applied_vetoes: list[str] = []
    # One note per analyst *decision*, not per row it lands on. The sheet holds
    # several rows with the same (event_id, market, line, direction) -- that is
    # what ``duplicate_market_for_event`` counts -- so appending inside the row
    # loop printed the same downgrade twice in the coupon header. On 2026-09-01
    # Leicester's ``goals_for 1.5 UNDER`` appeared as two identical DOWNGRADE
    # notes, which reads as two separate findings against one fixture.
    reported_vetoes: set[tuple[str, str, float | None, str | None, str, str | None]] = set()

    def note_veto_once(veto: AnalystVeto, note: str, *, variant: str | None = None) -> None:
        # ``variant`` distinguishes DOWNGRADE notes whose printed "X→Y" differs
        # by which row triggered them. A market-wide veto (``line=None``) can
        # match rows on both teams and every rung; those rows do not all start
        # at the same tier -- a per-team row that a *different* structural cap
        # has already pinned to LEAN steps to WEAK, while the row that actually
        # reaches the coupon may still have started at CALL and stepped to
        # LEAN. Deduping on the veto alone printed whichever row the loop
        # reached first as if it were the only one: live on 2026-09-06,
        # Corinthians-Chapecoense's ``shots_on_target_for`` veto was reported as
        # "LEAN→WEAK" from a ``RUNG_SEPARATED_BY_MODEL``-capped 6.5 line, while
        # the 5.5 line that actually shipped as a Bet Builder leg went
        # "CALL→LEAN" -- a caveat an operator reading that leg could not have
        # matched to what happened to it. Keying on the starting tier too
        # prints one note per distinct transition instead of one arbitrary one.
        key = (veto.event_id, veto.market, veto.line, veto.direction, veto.action, variant)
        if key in reported_vetoes:
            return
        reported_vetoes.add(key)
        applied_vetoes.append(note)

    for ignored, why in veto_index.ignored:
        applied_vetoes.append(
            f"POMINIĘTE WETO: {_veto_scope(ignored)} "
            f"({ignored.event_id[:12]}) — {why}; {ignored.reason}"
        )

    # A veto naming a row this sheet does not have applies to nothing, and
    # until 2026-09-04 it said so to nobody: ``VetoIndex`` reports the entries
    # it *refuses* (``ignored``) precisely because a written-down decision must
    # never be dropped in silence, and a decision addressed to an event_id the
    # sheet has never heard of was the one way through that rule.
    #
    # It is not hypothetical. ``event_id`` is a hash over the fixture's
    # competition name among other things, so anything that renames a
    # competition -- a canonical-map entry, the country qualification bzzoiro's
    # league names gained on 2026-09-04 -- re-mints every id on the day. Rebuild
    # the coupon after that with the morning's vetoes file and the file reads as
    # reviewed while every one of the analyst's kills quietly no-ops. Measured
    # on the 2026-09-04 rebuild: 3 of 4 vetoes on disk addressed ids from the
    # earlier run, and the build reported 15 singles without a word.
    #
    # Reported, not repaired: matching such an entry to "the same fixture under
    # a new id" would be a guess at which row the analyst meant, and a veto
    # applied to the wrong row is worse than one applied to none.
    #
    # The *diagnosis*, though, does not have to be a guess. A stale id and a
    # fixture that simply produced no rows are two different situations with
    # two different follow-ups -- re-read the day versus accept the fixture is
    # gone -- and the event list settles which one this is: an id the list
    # still knows was minted by this very run, so nothing was renamed. Until
    # 2026-09-08 the message asserted the stale-id hypothesis either way, and
    # on that day it was wrong about all three of the day's unapplied vetoes:
    # two ATP Challenger fixtures that had kicked off at 10:10Z and so reached
    # the sheet with zero rows, reported to the operator as a renaming problem
    # that had not happened.
    sheet_event_ids = {row.event_id for row in stats_sheet.rows}
    sheet_event_markets = {(row.event_id, row.market) for row in stats_sheet.rows}
    for veto in vetoes or ():
        if veto.event_id not in sheet_event_ids:
            known = events.get(veto.event_id)
            if known is not None:
                # ``identity`` is defined further down this function body, so
                # the two names are read straight off the record here.
                if known.sport == "tennis":
                    match = f"{known.player_one or '?'} – {known.player_two or '?'}"
                else:
                    match = f"{known.home_team or '?'} – {known.away_team or '?'}"
                why = (
                    f"mecz jest w liście wydarzeń ({match}"
                    f"{', ' + known.competition if known.competition else ''}"
                    f"{', start ' + known.start_time if known.start_time else ''}), "
                    "ale nie wniósł do arkusza ani jednego wiersza "
                    "(zablokowany albo niewzbogacony) — id jest aktualne, "
                    "nic nie zostało przemianowane"
                )
            else:
                why = (
                    "arkusz nie zawiera tego event_id i liście wydarzeń też "
                    "jest on nieznany (weto z innego przebiegu? event_id "
                    "zmienia się przy zmianie nazwy rozgrywek)"
                )
            applied_vetoes.append(
                f"NIEZASTOSOWANE WETO: {_veto_scope(veto)} "
                f"({veto.event_id[:12]}) — {why}; {veto.reason}"
            )
        elif (veto.event_id, veto.market) not in sheet_event_markets:
            applied_vetoes.append(
                f"NIEZASTOSOWANE WETO: {_veto_scope(veto)} "
                f"({veto.event_id[:12]}) — arkusz nie ma rynku "
                f"'{veto.market}' dla tego meczu; {veto.reason}"
            )

    def bar_for(row: StatsSheetRow, tier: str) -> tuple[float, BarComponents]:
        """``(min_acceptable_odds, the parts it was built from)`` for one row.

        One place, called by the ranking, by the ``require_superbet_value``
        probe and by the body that fills ``CouponSingle`` -- the same
        collapse ``required_price`` was created for, now that the bar has four
        moving parts instead of one and three copies would drift on any of
        them.
        """
        market_probability = superbet_implied(row)
        k = shrink_k_for_market(row.market) if shrink_k is None else shrink_k
        force_weight: float | None = None

        veto = veto_index.for_row(row)
        if veto is not None and veto.action == "DOWNGRADE":
            if veto.reason_class in VETO_CLASS_ZERO_WEIGHT:
                force_weight = 0.0
            elif veto.reason_class in VETO_CLASS_DOUBLE_K:
                k *= 2.0
        if set(row.lean_ceiling_reasons) & CEILING_DOUBLE_K:
            k *= 2.0
        if set(row.lean_ceiling_reasons) & CEILING_ZERO_WEIGHT:
            force_weight = 0.0

        components = bar_components(
            row,
            bar_basis,
            market_probability=market_probability,
            shrink_k=k,
            force_weight=force_weight,
        )
        if components.probability <= 0:
            return float("inf"), components
        return round((1.0 / components.probability) * TIER_MARGIN[tier], 4), components

    def identity(event_id: str) -> tuple[str, str, str]:
        event = events.get(event_id)
        if event is None:
            # The sheet alone cannot name a fixture; saying so beats printing a
            # hash at a human.
            return (f"[nieznany mecz {event_id[:12]}]", "", "")
        if event.sport == "tennis":
            match = f"{event.player_one or '?'} – {event.player_two or '?'}"
        else:
            match = f"{event.home_team or '?'} – {event.away_team or '?'}"
        return match, event.competition, event.start_time

    def fixture_key(event_id: str) -> tuple:
        """What real-world match this row is about, independent of event_id.

        Two dossiers can describe one fixture: discovery merges on names, and
        two feeds that spell a club differently produce two events. DISCOVER
        now merges far more of them, but the coupon is the artifact somebody
        *bets from*, so it does not rely on that. On 2026-08-28 a surviving
        pair put Nautico - Athletic Club on the list twice, same market, same
        line, same direction, at two different ranks -- an operator working
        down the file would have staked one bet twice while believing he was
        diversifying.

        Keyed on kickoff plus the two participants, order-insensitive and
        alias-resolved, because that is what identifies a match when the ids
        disagree. An event the sheet cannot name falls back to its event_id,
        which is no worse than today.
        """
        event = events.get(event_id)
        if event is None:
            return ("unknown", event_id)
        if event.sport == "tennis":
            sides = (event.player_one or "", event.player_two or "")
        else:
            sides = (event.home_team or "", event.away_team or "")
        names = tuple(sorted(
            normalize_team_name(resolve_team_alias(name)) for name in sides
        ))
        # The *day*, not the timestamp: two feeds publish the same kickoff a
        # minute or a timezone-spelling apart ("Z" vs "+00:00"), and a raw
        # string here would give one match two keys and the coupon the same
        # bet at two ranks. (bucket, day) is the identity rule the rest of
        # simple_stats already matches fixtures by.
        return (event.sport, (event.start_time or "")[:10], names)

    # Resolved once, before either the singles loop or draft_legs sees a row:
    # both paths must refuse the same rows, which is the invariant the whole
    # 2026-09-01 Bet Builder failure came from breaking.
    ambiguous_players = _ambiguous_player_names(stats_sheet.rows)
    # ``draft_legs`` takes a sheet, not a row, so the refusal has to be applied
    # to the sheet it takes. "Every gate a single passes, a leg passes too" is
    # the invariant, and it is the one the 2026-09-01 Bet Builder failure came
    # from breaking -- thirty legs went out that day past gates the singles
    # loop applied and the leg path did not.
    buildable = stats_sheet
    if not allow_player_props:
        # The invariant this file is built on: every gate a single passes, a
        # leg passes too. It was broken once already -- thirty legs went out on
        # 2026-09-01 past gates the singles loop applied and the leg path did
        # not -- and a prop leg is the same row, priced the same way, off the
        # same unanchored sample as a prop single.
        buildable = buildable.model_copy(update={
            "rows": [r for r in buildable.rows if not is_player_prop(r)]
        })
    if ambiguous_players:
        buildable = buildable.model_copy(update={
            "rows": [
                row for row in buildable.rows
                if not (
                    row.player_name
                    and (row.event_id, row.player_name) in ambiguous_players
                )
            ]
        })

    excluded: dict[str, int] = {}

    def exclude(reason: str) -> None:
        excluded[reason] = excluded.get(reason, 0) + 1

    # --- singles ----------------------------------------------------------
    candidates: list[tuple[StatsSheetRow, str]] = []
    for row in stats_sheet.rows:
        tier: Tier = tier_for_row(row)
        veto = veto_index.for_row(row)
        # DOWNGRADE is applied before the tier gate below, not after: a CALL
        # the analyst steps to WEAK is excluded by that same check, exactly
        # like a context flag's downgrade would be -- no second exclusion path
        # needed for it.
        #
        # A hard VETO is checked *first*, before both the downgrade and the
        # tier gate. It used to sit after them, and the effect was that the
        # analyst's strongest verdict was the only one that could vanish
        # without trace: a row already at WEAK left through ``tier_weak`` and
        # never reached this branch, so no note was written and ``excluded``
        # carried no ``analyst_veto`` at all. On 2026-09-07 the file recorded
        # nine notes for ten vetoes and reported zero hard vetoes while the
        # veto artifact held two -- Cerundolo-Blockx aces and double faults,
        # both struck outright, neither mentioned. The two artifacts disagreed
        # about what the analyst had done, and the coupon was the one the
        # operator reads.
        #
        # Attribution follows the same logic: a row that is both thin and
        # vetoed was removed *because the analyst removed it*, and counting it
        # as a tier casualty hides a judgement behind a threshold.
        if veto is not None and veto.action == "VETO":
            exclude("analyst_veto")
            note_veto_once(
                veto,
                f"WETO analityka [{veto.reason_class}]: {_veto_scope(veto)} "
                f"({row.event_id[:12]}) — {veto.reason}",
            )
            continue
        if veto is not None and veto.action == "DOWNGRADE":
            new_tier = step_tier_down(tier)
            # ``variant`` is the *incoming* tier, so one veto covering rows at
            # two different tiers renders once per tier -- which is right when
            # the step differs and pure noise when it does not. A row already
            # at WEAK steps to WEAK, changes nothing, and used to emit a second
            # full copy of a 1,500-character reason: on 2026-09-07 the
            # Gea-van de Zandschulp games_won note appeared twice, once as
            # LEAN→WEAK and once as WEAK→WEAK, identical but for the arrow.
            # A transition that is a no-op is not a second finding.
            if new_tier != tier:
                note_veto_once(
                    veto,
                    f"DOWNGRADE analityka [{veto.reason_class}]: {_veto_scope(veto)} "
                    f"({row.event_id[:12]}) {tier}→{new_tier}"
                    f"{_veto_class_effect(veto)} — {veto.reason}",
                    variant=tier,
                )
            tier = new_tier
        if tier in ("WEAK", "DROP"):
            exclude(f"tier_{tier.lower()}")
            continue
        if not allow_player_props and is_player_prop(row):
            exclude("player_prop_unpriceable")
            continue
        if row.p_low < min_p_low:
            exclude("p_low_below_threshold")
            continue
        if row.player_name and (row.event_id, row.player_name) in ambiguous_players:
            exclude("ambiguous_player_name")
            continue
        # Faza 5d: youth and reserve/friendly fixtures stay on the full stats
        # sheet but never reach the coupon -- their stats describe a slate
        # nobody is pricing. An unmapped competition is left alone, never
        # guessed at (see competition_tier's own docstring).
        event = events.get(row.event_id)
        if event is not None and competition_tier(event.competition) in ("YOUTH", "FRIENDLY"):
            exclude("competition_youth_or_friendly")
            continue
        candidates.append((row, tier))

    # A fixture contributes at most one single per market family, so one match
    # with a strong corners read cannot occupy six rows of the file at four
    # different lines -- they are the same read, and only the best line of it is
    # a distinct bet.
    #
    # *Which* line is now scored rather than left to the sort order; see
    # RUNG_PENALTY_LINE_ON_MODE.
    seen: set[tuple[tuple, str, str | None]] = set()
    singles: list[CouponSingle] = []
    # Per-fixture budgets. See MAX_SINGLES_PER_EVENT.
    per_family: dict[tuple[tuple, str], int] = defaultdict(int)
    per_event: dict[tuple, int] = defaultdict(int)

    def rung_score(row: StatsSheetRow, tier: str) -> float | None:
        """Expected value at the book's own price, penalised for a bad rung.

        None when the book does not price this rung: a line the operator cannot
        take has no expected value, and scoring it against the sheet alone
        would let an unbettable rung win the slot.
        """
        minimum, bar = bar_for(row, tier)
        price = superbet_for(row, minimum).get("superbet_price")
        if not isinstance(price, (int, float)):
            return None
        score = bar.probability * float(price) - 1.0
        if row.mode is not None and abs(row.line - row.mode) <= 1.0:
            score -= RUNG_PENALTY_LINE_ON_MODE
        crossed = (
            row.sample_max is not None and row.sample_max > row.line
            if row.direction == "UNDER"
            else row.sample_min is not None and row.sample_min < row.line
        )
        if crossed:
            score -= RUNG_PENALTY_SAMPLE_CROSSES_LINE
        return score

    def _alternative_fields(entry) -> dict[str, object]:
        if entry is None:
            return {}
        score, other, other_tier = entry
        minimum = bar_for(other, other_tier)[0]
        return {
            "alternative_line": other.line,
            "alternative_direction": other.direction,
            "alternative_price": superbet_for(other, minimum).get("superbet_price"),
            "alternative_min_acceptable_odds": minimum,
            "alternative_rung_score": round(score, 4),
        }

    def _rung_key(row: StatsSheetRow) -> tuple:
        return (fixture_key(row.event_id), row.market, _subject_key(row))

    # Scored once, before any ranking, so every list below sees the same
    # winner and the loser is excluded for the right reason.
    scored_by_key: dict[tuple, list[tuple[float, StatsSheetRow, str]]] = {}
    for _row, _tier in candidates:
        _score = rung_score(_row, _tier)
        if _score is None:
            continue
        scored_by_key.setdefault(_rung_key(_row), []).append((_score, _row, _tier))
    chosen_rung: dict[tuple, str] = {}
    runner_up: dict[tuple, tuple[float, StatsSheetRow, str]] = {}
    for _key, _rungs in scored_by_key.items():
        _rungs.sort(key=lambda item: (-item[0], item[1].line, item[1].direction))
        chosen_rung[_key] = f"{_rungs[0][1].line}:{_rungs[0][1].direction}"
        if len(_rungs) > 1:
            runner_up[_key] = _rungs[1]

    def _append_singles(ordered: list[tuple[StatsSheetRow, str]]) -> None:
        for row, tier in ordered:
            if require_superbet_value:
                probe = superbet_for(row, bar_for(row, tier)[0])
                if probe.get("superbet_verdict") != "VALUE":
                    exclude("superbet_not_value")
                    continue
            key = _rung_key(row)
            if key in seen:
                exclude("duplicate_market_for_event")
                continue
            # A priced ladder picks its rung by score, not by whichever one the
            # sort happened to reach first.
            wanted = chosen_rung.get(key)
            if wanted is not None and wanted != f"{row.line}:{row.direction}":
                exclude("rung_not_chosen")
                continue
            # Diversity, checked before the slot is spent and for the same
            # reason ``kickoff_passed`` is: a fourth reading of one fixture's
            # scoring must not push another fixture off the end of the list.
            #
            # Both counters are per real-world fixture rather than per
            # ``event_id``, because two dossiers can describe one match when two
            # feeds spell a club differently -- the same key ``fixture_key``
            # already dedups the slips by.
            fixture = fixture_key(row.event_id)
            family = mechanism_family(row)
            if per_family[(fixture, family)] >= max_per_family:
                exclude("duplicate_mechanism_family")
                continue
            if per_event[fixture] >= max_per_event:
                exclude("over_max_per_event")
                continue
            seen.add(key)
            match, competition, kickoff = identity(row.event_id)
            # Checked before the max_singles slot is spent: a started match
            # must not push a bettable one off the end of the list.
            if _kickoff_passed(kickoff, not_before):
                exclude("kickoff_passed")
                continue
            if len(singles) >= max_singles:
                exclude("over_max_singles")
                continue
            if row.p_low <= 0:
                # Same refusal ``draft_legs`` makes: 1/0 is not a price, and a
                # row whose lower bound is zero is making no claim to rank.
                exclude("p_low_not_positive")
                continue
            minimum, bar = bar_for(row, tier)
            # The fair price on the probability the bar is computed from, so
            # that ``fair_odds`` and ``min_acceptable_odds`` describe the same
            # row. It was ``1.0 / row.p_low``, the basis the bar moved off when
            # it went to p_central, which left the two fields disagreeing and
            # printed absurd magnitudes wherever Wilson's bound underflows -- a
            # sample with no hit reported fair odds of 4.9e+16 next to a
            # min_acceptable_odds of 22.0.
            fair = 1.0 / bar.probability if bar.probability > 0 else 0.0
            per_family[(fixture, family)] += 1
            per_event[fixture] += 1
            sb_info = superbet_for(row, minimum)
            veto = veto_index.for_row(row)
            if veto is not None and veto.action == "DOWNGRADE" and sb_info.get("superbet_verdict") == "VALUE":
                sb_info["superbet_verdict"] = "DOWNGRADE"
            singles.append(
                CouponSingle(
                    rank=len(singles) + 1,
                    event_id=row.event_id,
                    match=match,
                    competition=competition,
                    kickoff=kickoff,
                    sport=row.sport,
                    market=row.market,
                    market_label=market_label(row.market),
                    line=row.line,
                    direction=row.direction,
                    subject=_subject(row),
                    subject_kind=_subject_kind(row),
                    subject_id=row.player_id,
                    tier=tier,
                    p_low=row.p_low,
                    p_central=row.p_central,
                    hit_rate=row.hit_rate,
                    hits=row.hits,
                    sample_size=row.sample_size,
                    cross_provider_agreement=row.cross_provider_agreement,
                    corroborated_matches=row.corroborated_matches,
                    fair_odds=round(fair, 4),
                    min_acceptable_odds=minimum,
                    bar_basis=bar_basis,
                    bar_basis_reason=bar.reason,
                    bar_probability=round(bar.probability, 4),
                    bar_sample_probability=round(bar.p_bar, 4),
                    bar_calibration=(
                        round(bar.calibration, 4) if bar.calibration else None
                    ),
                    bar_calibration_note=bar.calibration_note,
                    market_probability=(
                        round(bar.p_market, 4) if bar.p_market is not None else None
                    ),
                    sample_weight=(
                        round(bar.weight, 4) if bar.weight is not None else None
                    ),
                    shrink_k=(
                        shrink_k_for_market(row.market) if shrink_k is None else shrink_k
                    ),
                    market_verdict=row.market_signal.verdict if row.market_signal else None,
                    market_price=row.market_signal.market_price if row.market_signal else None,
                    market_bookmaker=(
                        row.market_signal.market_bookmaker if row.market_signal else None
                    ),
                    tipster=_tipster_summary(row),
                    caveats=_caveats(row) + (
                        [
                            f"weto analityka [{veto.reason_class}]: {veto.reason}"
                        ] if (veto is not None and veto.action == "DOWNGRADE") else []
                    ) + (
                        # The bar's third stage, on the row it moved. The
                        # header counts them; this says which row and by how
                        # much, because the amount is per claim and the note
                        # carries what such rows actually realised.
                        [
                            f"próg podniesiony o zmierzoną historię rynku — "
                            f"{bar.calibration_note}"
                        ] if (
                            bar.calibration >= MIN_REPORTABLE_CALIBRATION
                            and bar.calibration_note
                        ) else []
                    ) + (
                        [
                            "rynek wycenia to znacznie niżej niż my — najpierw "
                            "sprawdź próbkę, potem kurs"
                        ] if over_disagreement(row) and not off_ladder(row) else []
                    ) + (
                        [note] if (
                            note := unreviewed_sibling_note(row, veto_index, vetoes)
                        ) else []
                    ) + (
                        [
                            "próbka opisuje inny środek rozkładu niż cała "
                            f"drabinka Superbetu (średnia {row.mean:.2f} vs "
                            f"mediana rynku {ladder_median(row):.2f}, "
                            f"{ladder_sigma(row):+.2f}σ) — to nie jest spór o "
                            "ogon, to spór o to, gdzie ten rynek leży"
                        ] if off_ladder(row) else []
                    ),
                    **_alternative_fields(runner_up.get(key)),
                    rung_score=(
                        round(scored, 4)
                        if (scored := rung_score(row, tier)) is not None else None
                    ),
                    edge=round(_edge(row), 4) if _has_market_reference(row) else None,
                    market_disagreement=disagreement(row),
                    ladder_sigma=ladder_sigma(row),
                    needs_review=over_disagreement(row),
                    analyst_action=veto.action if veto is not None else None,
                    analyst_reason_class=veto.reason_class if veto is not None else None,
                    analyst_reason=veto.reason if veto is not None else None,
                    **sb_info,
                )
            )

    # Three rankings now, never merged into one sorted list.
    #
    # Group one is new (SUPERBET, 2026-08-31) and outranks both of the others:
    # a row the operator's own book prices at or above its minimum acceptable
    # odds is a bet he can place at a price worth placing it at. Everything
    # below is a target he still has to go and check, and on a bad day none of
    # it is takeable at all -- which is exactly what the 2026-08-31 night slate
    # turned out to be, with three of 505 comparable rows clearing the bar.
    #
    # Groups two and three are the Faza 5c split, unchanged: a row this sheet
    # can price against bzzoiro's market reference outranks one it cannot,
    # however high the second row's own p_low climbs. max_singles is one shared
    # budget, spent in this order.
    def _superbet_surplus(pair: tuple[StatsSheetRow, str]) -> float | None:
        """Whether this row is takeable at Superbet's price -- membership only.

        Returns the artifact's own ``superbet_surplus`` so a caller can test it
        for None, and it is deliberately **not** what orders the group; see
        ``_value_rank_key``.

        ``WITHIN_TOLERANCE`` counts as membership. The group means "a price the
        operator can act on today", and the settled record says a price a few
        percent under the bar belongs in it: over 1,269 settled priced rows the
        rows at ``gap >= -5%`` went 72.9% for +1.3%, against 63.5% for -0.8% on
        the 52 rows that cleared the bar outright. Insisting on a non-negative
        gap was throwing away nine of every fourteen candidates for a point
        estimate that was worse. See ``PRICE_TOLERANCE_PCT``.
        """
        row, tier = pair
        veto = veto_index.for_row(row)
        if veto is not None and veto.action == "DOWNGRADE":
            return None
        info = superbet_for(row, bar_for(row, tier)[0])
        if info.get("superbet_verdict") not in ("VALUE", "WITHIN_TOLERANCE"):
            return None
        return info.get("superbet_surplus")

    def _value_rank_key(pair: tuple[StatsSheetRow, str]) -> float:
        """How far above the book this row is, in probability, capped.

        Two things were wrong with ranking the group on ``superbet_surplus``,
        and it is the group that outranks every other row in the file.

        **It was in odds units.** ``superbet_surplus`` is ``price - minimum``,
        a difference of two odds, and the odds scale stretches as the price
        lengthens: the same 5-point probability disagreement is worth 0.06 at
        1.30 and 0.30 at 2.70. Over the 33 VALUE rows ever shipped,
        ``corr(price, surplus)`` is **+0.78** -- the key was three-quarters a
        proxy for "how long is this price", so group one was in practice sorted
        longest-price-first. Those rows went 1 for 6 at prices of 2.00 and up,
        for -65.5%, against 74.3% for the rows that reached ranks 8-15.

        It also reordered rows outright rather than merely stretching them.
        Carrasco's shots-on-target OVER 0.5 at 1.72 carried the third largest
        odds surplus in the whole history (+0.333) with a probability gap of
        **-0.052**: ``p_low`` below even the vigged implied price. It led the
        2026-09-04 file.

        **It was unbounded.** ``_edge`` -- the key for group *two* -- says in
        its own docstring that ranking a disagreement descending is only
        legitimate because it is bounded first, and names the day six unbounded
        ones led the file and lost. That reasoning applies with more force
        here, where a wider gap is more likely to be our error than the book's:
        our estimate carries the larger variance, so sorting on the difference
        sorts on our own noise. The measured shape is exactly that -- past
        +0.40 in odds, 0 for 2; every VALUE bucket at or below 57%.

        So: measured in probability, against the devigged price where the book
        posts both sides and the raw implied price where it posts one (props
        are OVER-only, which is why the devigged number is missing on all nine
        props ever shipped and on every ``cards_total`` row -- 75 of 130).

        **Not capped**, though the first version of this function was. The 33
        shipped VALUE rows read as though the widest disagreements were the
        worst -- 0 for 2 past +0.40 in odds -- and 33 rows is not enough to act
        on. Measured instead over 16,352 settled sides of 8,176 two-sided rungs,
        the +0.25 to +0.40 bucket is the only one on the board with a positive
        point estimate (+29.6%, n=229). That does not make those rows good; it
        makes a cap unjustified. See ``_edge`` for the full table and
        ``MAX_MARKET_DISAGREEMENT`` for the day a demotion on this gap cost the
        file its one real row.

        Ties fall through to ``p_low`` in the sort below, as before.
        """
        row, tier = pair
        info = superbet_for(row, bar_for(row, tier)[0])
        price = info.get("superbet_price")
        if not isinstance(price, (int, float)) or price <= 0:
            return 0.0
        implied = superbet_implied(row)
        if implied is None:
            implied = 1.0 / price
        ours = row.p_central if row.p_central is not None else row.p_low
        return ours - implied

    def _no_reference_rank_key(pair: tuple[StatsSheetRow, str]) -> tuple:
        """Order for the group this sheet cannot price against a market.

        It used to be ``(is_trivial_under, -p_low)`` and ``-p_low`` was the
        problem: inside this group a high ``p_low`` *is* a short price, so
        sorting on it descending sorted the group by how little the book pays.
        Raising ``max_singles`` to 40 made that visible -- the first 40-single
        file put eleven rows in the 1.00-1.05 band, every one of them at the
        ``p_central`` clamp of 0.950, things like "under 4.5 goals in the second
        half at 1.004".

        Two keys go in front of it, both measured:

        **A row the book does not carry goes last.** It is information, not a
        candidate: the operator cannot place it at any price, and it was taking
        a slot from a fixture he could bet. Thirteen of the first forty were
        ``MARKET_NOT_OFFERED``.

        **Then the band's measured edge, descending.** Over 668 settled priced
        rows the 1.35-1.60 band realised 76.7% against a 69.4% implied rate
        (+7.3%) while 1.00-1.05 realised 97.5% against 98.5% (-1.0%). Certainty
        and a takeable price meet in the middle of the ladder, and this is the
        key that looks there first.

        ``is_trivial_under`` stays in front of all of it, unchanged: a low UNDER
        line at 10/10 is its own separate objection and already has a home.
        ``p_low`` remains the tie-break, so nothing about the old order survives
        except where the new keys are equal.
        """
        row, tier = pair
        info = superbet_for(row, bar_for(row, tier)[0])
        price = info.get("superbet_price")
        unpriced = not isinstance(price, (int, float)) or price <= 1.0
        _, band_edge = _price_band(price if not unpriced else None)
        return (
            is_trivial_under(row),
            unpriced,
            -(band_edge if band_edge is not None else 0.0),
            -row.p_low,
            row.event_id,
        )

    # The ladder gate, and it is a *demotion*, not an exclusion.
    #
    # Nothing is deleted, because the gate cannot tell an edge from a broken
    # sample and must not pretend to. What it can do is stop the file
    # presenting the second as the first, ranked number one.
    #
    # Only the *ladder* disagreement demotes. The per-rung one annotates.
    #
    # They were one gate and they are not one finding. ``off_ladder`` says the
    # sample's centre is nowhere near the centre the book's whole devigged
    # ladder implies -- four of 2026-09-01's six losers were exactly that, and
    # a sample measuring another venue or another competition has a tail that
    # is not evidence about anything. ``disagreement`` says our floor sits more
    # than MAX_MARKET_DISAGREEMENT above the devigged price *at this row's own
    # rung*, and that is not a defect at all: it is the definition of value. A
    # gate that demotes on it demotes the thing the file exists to find.
    #
    # It cost exactly that on 2026-09-02. Of the day's 82 bettable rows, 78
    # were the best-of-five artifact and one -- WTA ``aces_total`` 5.5 OVER at
    # 2.07 against a 1.8146 floor -- was real. It disagreed with the book by
    # more than 25%, which is why it was worth taking, was demoted to the tail
    # for it, and fell off the far side of the 15-single cap. The file shipped
    # with nothing.
    #
    # Both still carry their caveat onto the row, so nothing is quieter than
    # before; what changed is which of the two moves a row's rank.
    flagged = [c for c in candidates if off_ladder(c[0])]
    flagged_ids = {id(c) for c in flagged}
    trusted = [c for c in candidates if id(c) not in flagged_ids]

    superbet_value = [c for c in trusted if _superbet_surplus(c) is not None]
    value_ids = {id(c) for c in superbet_value}
    rest = [c for c in trusted if id(c) not in value_ids]
    with_reference = [c for c in rest if _has_market_reference(c[0])]
    without_reference = [c for c in rest if not _has_market_reference(c[0])]

    # Group one holds two kinds of row -- ``VALUE``, which clears its bar, and
    # ``WITHIN_TOLERANCE``, which does not -- and it is appended before every
    # other group, so it is where ``MAX_SINGLES_PER_FAMILY`` is actually spent.
    # That slot must go to a row the file will print as bettable.
    #
    # It did not. The order inside the group is ``_value_rank_key``, a pure
    # probability gap that never asks whether the price clears the bar, so a
    # row priced *under* its threshold could outrank one priced *over* it,
    # claim the family's only slot, and leave the bettable row excluded as
    # ``duplicate_mechanism_family``. On 2026-09-08 that happened on
    # Ilves-FF Jaro: family ``scoring`` shipped ``goals_for 2.5 UNDER`` at 1.38
    # against a 1.4181 bar (-2.7%, rank key 0.195) and struck
    # ``goals_total 3.5 UNDER`` at 1.50 against a 1.4585 bar (+2.8%, rank key
    # 0.101). Two of the day's ten VALUE rows were lost that way.
    #
    # Split rather than re-sorted, deliberately. ``_superbet_surplus`` admits
    # the tolerance band on measured evidence -- rows at gap >= -5% went 72.9%
    # for +1.3% against 63.5% for -0.8% on the 52 rows that cleared the bar
    # outright -- so a tolerance row is *not* a worse bet and its rank inside
    # its own subgroup is untouched. What it must not do is spend a slot the
    # file then tells the operator not to stake.
    clears_bar = [
        c for c in superbet_value
        if superbet_for(c[0], bar_for(c[0], c[1])[0]).get("superbet_verdict") == "VALUE"
    ]
    clears_ids = {id(c) for c in clears_bar}
    within_tolerance = [c for c in superbet_value if id(c) not in clears_ids]
    for _group in (clears_bar, within_tolerance):
        _append_singles(
            sorted(
                _group,
                key=lambda pair: (
                    pair[1] != "CALL",
                    bool(veto_index.for_row(pair[0]) and veto_index.for_row(pair[0]).action == "DOWNGRADE"),
                    -_value_rank_key(pair),
                    -pair[0].p_low,
                    pair[0].event_id,
                ),
            )
        )
    _append_singles(
        sorted(with_reference, key=lambda pair: (-_edge(pair[0]), -pair[0].p_low, pair[0].event_id))
    )
    _append_singles(
        sorted(
            without_reference,
            key=_no_reference_rank_key,
        )
    )
    # Last, and only if the budget above did not run out. Ranked by how far the
    # sample's centre sits from the book's, widest first -- read as a to-check
    # list, not a shortlist. On |sigma| rather than on the price gap, because
    # the price gap no longer puts anything in this group.
    _append_singles(
        sorted(
            flagged,
            key=lambda pair: (
                -abs(ladder_sigma(pair[0]) or 0.0), -pair[0].p_low, pair[0].event_id
            ),
        )
    )

    # --- slips ------------------------------------------------------------
    #
    # Every gate the singles loop above applies, this loop applies too. Before
    # 2026-09-01 it applied two of eight, and the file gave no sign of it: the
    # analyst's vetoes, the ``min_p_low`` floor, the Superbet price check and
    # the duplicate-fixture guard all stopped at the singles list, while the
    # slips were drafted straight off the raw sheet. They are passed *into*
    # ``draft_legs`` rather than re-checked afterwards, because a leg excluded
    # after drafting would still have consumed one of ``max_legs``.
    def leg_price(row: StatsSheetRow) -> tuple[str | None, float | None]:
        if superbet_offer is None:
            return (None, None)
        # Same lookup as the singles, so a leg and a single on the same
        # (market, line, direction) can never disagree about whether the book
        # carries it.
        availability, exact, _, _ = lookup_line(
            superbet_events.get(row.event_id),
            market=row.market,
            line=row.line,
            direction=row.direction,
            team_name=row.team_name,
            player_name=row.player_name,
            player_aliases=player_aliases.get(row.event_id, {}),
        )
        return (availability, exact.price if exact else None)

    slips: list[CouponSlip] = []
    # Deduplicated by real-world fixture, not by event_id. Two dossiers can
    # describe one match (two feeds spelling a club differently), and the
    # singles list has resolved that since 2026-08-28 while this loop still
    # keyed on the raw id -- so the same match could occupy two slips and an
    # operator working down the file would have staked it twice believing he
    # had diversified. ``fixture_key`` is the same resolver the singles use.
    seen_fixtures: set[tuple] = set()
    for event_id in sorted({row.event_id for row in stats_sheet.rows}):
        fixture = fixture_key(event_id)
        if fixture in seen_fixtures:
            exclude("duplicate_fixture_for_slip")
            continue
        draft = draft_legs(
            buildable,
            event_id,
            max_legs=max_legs,
            vetoes=veto_index,
            min_p_low=min_p_low,
            price_for=leg_price if superbet_offer is not None else None,
            # **Always**, from 2026-09-03, and not only when the caller asked
            # for a value-only file.
            #
            # A single below its bar is information: the row is printed,
            # labelled, and the operator can see the price is wrong. A *leg*
            # below its bar is not: a slip is placed as one unit, so the leg
            # cannot be read separately and cannot be declined separately -- it
            # simply lowers the slip's expectation while making the coupon look
            # fuller. On 2026-09-03, 6 of 25 legs were kept below their own
            # minimum "as context".
            require_value=superbet_offer is not None,
            bar_basis=bar_basis,
            bar_for=bar_for,
        )
        # A one-leg "slip" is a single wearing a different hat, and printing it
        # in both sections would double-count the same read.
        if len(draft.legs) < 2:
            continue
        # docs/SUPERBET_BET_BUILDER_METHOD_v3.md §44. The draft is kept on the
        # record with its score and its parts; it just does not become a coupon.
        if draft.builder_score_refused:
            exclude("builder_score_below_minimum")
            continue
        match, competition, kickoff = identity(event_id)
        if _kickoff_passed(kickoff, not_before):
            exclude("kickoff_passed_slip")
            continue
        if competition_tier(competition) in ("YOUTH", "FRIENDLY"):
            exclude("competition_youth_or_friendly_slip")
            continue
        seen_fixtures.add(fixture)
        slips.append(
            CouponSlip(
                rank=0,
                event_id=event_id,
                match=match,
                competition=competition,
                kickoff=kickoff,
                draft=draft,
                weakest_leg_p_low=min(leg.p_low for leg in draft.legs),
            )
        )

    def _slip_value_legs(slip: CouponSlip) -> int:
        """How many of this slip's legs the operator's own book prices at or
        above their own threshold."""
        return sum(
            1
            for leg in slip.draft.legs
            if leg.superbet_price is not None
            and leg.superbet_price >= leg.min_acceptable_odds
        )

    # Value first, one level up from the legs and for the same reason. Ranking
    # slips on ``weakest_leg_p_low`` alone actively undid the leg ranking below
    # it: promoting the one leg worth its price *lowers* a slip's weakest
    # ``p_low``, so the slip carrying it sank in this sort and was cut by
    # ``max_slips``. Measured 2026-09-01: fixing the leg order alone dropped the
    # Sheffield United and Preston slips out of the file entirely and replaced
    # them with slips made of 1.01-priced near-certainties. A slip with a leg
    # that can pay outranks one where nothing can, whatever its weakest leg's
    # certainty; within each group the weakest leg still decides.
    slips.sort(
        key=lambda s: (-_slip_value_legs(s), -s.weakest_leg_p_low, s.event_id)
    )
    slips = [s.model_copy(update={"rank": i + 1}) for i, s in enumerate(slips[:max_slips])]

    notes = []
    entitlement_note = _entitlement_note(market_context)
    if entitlement_note is not None:
        notes.append(entitlement_note)
    notes += [
        "Kurs łączny Bet Buildera (nogi z JEDNEGO meczu) nie jest liczony i nie "
        "może być — marża bukmachera za połączenie jest nieobserwowalna; "
        "liczony jest tylko próg, który ten kurs musi pobić. Kupon z RÓŻNYCH "
        "meczów to inna sprawa: bukmacher mnoży kursy nóg, więc my też — patrz "
        "sekcja „Gdy złożysz je w kupon”.",
        "Pewność w tabeli to dolna granica Wilsona 95% (p_low) — celowo "
        "ostrożna i zmierzona jako zaniżona o ok. 22pp wobec tego, co się "
        "faktycznie dzieje. Progi cenowe i arytmetyka kuponu NIE są z niej "
        "liczone: te biorą prawdopodobieństwo po korekcie o rynek (kolumna "
        "„Min. kurs”). Nie mnóż p_low z tej tabeli między sobą — zaniżysz "
        "kupon dwukrotnie. "
        "sample_size liczy mecze, nie obserwacje: drużyna gra najwyżej jeden "
        "mecz dziennie, więc powtórzenia między obiema drużynami, h2h i "
        "dostawcami są zwijane do jednego meczu. Potwierdzenie przez drugiego "
        "dostawcę nie podnosi już pewności — mówi tylko, że wartość jest "
        "wiarygodna. Obserwacje bez czytelnej daty nie dają się przypisać do "
        "meczu i zostają osobno, więc próba może być w rzadkich przypadkach "
        "zawyżona. To podłoga na dowody, nie gwarancja.",
        "Brak stawek i brak EV — celowo. Typ poniżej minimalnego kursu nie jest typem.",
    ]
    stale_note = _stale_sheet_note(stats_sheet, superbet_offer)
    if stale_note is not None:
        notes.append(stale_note)
    if excluded.get("kickoff_passed"):
        notes.append(
            f"Odrzucono {excluded['kickoff_passed']} pozycji, których mecz już "
            f"się rozpoczął (odcięcie {not_before:%H:%M} UTC). Mecz w przeszłości "
            "nie jest typem, choćby jego p_low wyglądało najlepiej w pliku."
        )
    if any(is_trivial_under(r) for r, _ in candidates):
        notes.append(
            "Niskie linie UNDER (≤1.5) zepchnięto na koniec — i listy singli, "
            "i kolejności nóg w Bet Builderach: przy 10/10 wychodzą wysoko w "
            "p_low, ale rynek wycenia je ~1.05."
        )
    if flagged:
        # Reported from the *candidates*, not from the rows that made the file.
        # max_singles is 15 against thousands of candidates, so a demoted row is
        # almost always pushed off the end -- and a row removed from the top of
        # the coupon without a word is the same silent edit this gate exists to
        # stop. One line per fixture+market: the same read at four lines is one
        # thing to go and check, not four.
        worst: dict[tuple, tuple[StatsSheetRow, float]] = {}
        for row, _tier in flagged:
            gap = abs(ladder_sigma(row) or 0.0)
            key = (fixture_key(row.event_id), row.market, _subject_key(row))
            if key not in worst or gap > worst[key][1]:
                worst[key] = (row, gap)
        listed = sorted(worst.values(), key=lambda pair: -pair[1])
        shown = listed[:8]
        detail = "; ".join(
            f"{identity(row.event_id)[0]} {market_label(row.market)} {row.line} "
            f"{row.direction} ({gap:.2f}σ)"
            for row, gap in shown
        )
        notes.append(
            f"{len(listed)} czytań zepchnięto na koniec listy, bo środek próbki "
            f"leży dalej niż {MAX_LADDER_SIGMA:.2f} jej własnego odchylenia od "
            "środka, który implikuje cała odmarżowiona drabinka Superbetu — przy "
            f"limicie {max_singles} singli zwykle znaczy to, że w ogóle nie "
            "weszły. To nie jest spór o ogon rozkładu, tylko o to, gdzie ten "
            "rynek leży, a taka próbka opisuje inny mecz, inny teren albo inne "
            "rozgrywki. Najszersze rozjazdy: "
            + detail
            + (f" (+{len(listed) - len(shown)} więcej)" if len(listed) > len(shown) else "")
            + ". Sprawdź próbkę, zanim sprawdzisz kurs."
        )
    scoped: dict[str, int] = {}
    for row in stats_sheet.rows:
        for reason, count in (row.sample_excluded or {}).items():
            scoped[reason] = scoped.get(reason, 0) + count
    if scoped:
        notes.append(
            "Obserwacje odrzucone z prób PRZED policzeniem p_low: "
            + ", ".join(f"{count}× {reason}" for reason, count in sorted(scoped.items()))
            + ". Sparing przedsezonowy i mecz z poprzedniego sezonu nie są próbą "
            "dzisiejszych rozgrywek; do 2026-09-01 liczyły się na równi z meczem "
            "ligowym i podnosiły p_low. MATCH_FORMAT_MISMATCH to mecz do dwóch "
            "wygranych setów w próbce meczu do trzech, a MATCH_FORMAT_UNKNOWN — "
            "mecz, o którym dostawca nie powiedział, z jakiej drabinki pochodzi; "
            "oba dotyczą wyłącznie rynków zależnych od długości meczu (gemy, "
            "sety, asy, podwójne błędy) w meczach ATP."
        )
    slip_legs = [leg for slip in slips for leg in slip.draft.legs]
    if slip_legs:
        below = [leg for leg in slip_legs if leg.superbet_price is not None
                 and leg.superbet_price < leg.min_acceptable_odds]
        notes.append(
            f"Bet Builder: {len(slip_legs)} nóg, każda z linią realnie wystawioną "
            f"na Superbecie"
            + (
                f"; {len(below)} z nich poniżej własnego progu — to nie są typy, "
                "trzymane tylko jako kontekst dla reszty kuponu."
                if below else " i każda powyżej swojego progu."
            )
        )
    # Superbet coverage, said in the header rather than left to be inferred
    # from a column of dashes. The order is deliberate: what is takeable first,
    # then the reason most of it is not.
    if superbet_offer is not None:
        value = [s for s in singles if s.superbet_verdict == "VALUE"]
        no_line = [s for s in singles if s.superbet_availability == "LINE_NOT_OFFERED"]
        # Every single lands in exactly one bucket, and the buckets are printed
        # in full. A note that accounts for 3 of 15 rows and leaves 12
        # unexplained reads as a bug in the count rather than as a fact about
        # the day -- which is what happened the first time this note shipped.
        buckets = {
            f"w tolerancji (do {price_tolerance_pct:.0f}% pod progiem)": "WITHIN_TOLERANCE",
            "wystawionych taniej niż próg": "PRICED_BELOW_THRESHOLD",
            "z rynkiem, ale bez naszej linii": "LINE_NOT_OFFERED",
            "bez tego rynku u bukmachera": "MARKET_NOT_OFFERED",
            "których mecz już trwa (oferta zdjęta)": "OFFER_EMPTY",
            "bez meczu w ofercie": "EVENT_NOT_MATCHED",
            "zablokowanych": "SUSPENDED",
            "których nie czytamy (propy zawodników)": "SCOPE_NOT_SUPPORTED",
            "objętych wetem analityka (DOWNGRADE)": "DOWNGRADE",
        }
        counted = {
            label: sum(
                1 for s in singles
                if (s.superbet_verdict == key or s.superbet_availability == key)
                and s.superbet_verdict != "VALUE"
            )
            for label, key in buckets.items()
        }
        breakdown = ", ".join(
            f"{count} {label}" for label, count in counted.items() if count
        )
        notes.append(
            f"Superbet: {len(value)} z {len(singles)} singli osiąga swój minimalny "
            f"kurs na ekranie operatora"
            + (f"; pozostałe: {breakdown}" if breakdown else "")
            + f". Ceny zdjęte {superbet_offer.generated_at[:16]}Z z publicznej "
            "oferty superbet.pl — sprawdź kurs na ekranie, bo się rusza."
        )
        if no_line:
            worst = sorted(
                {(s.market, s.line, s.superbet_nearest_line) for s in no_line
                 if s.superbet_nearest_line is not None}
            )[:6]
            if worst:
                pairs = ", ".join(
                    f"{market} {line}→{nearest}" for market, line, nearest in worst
                )
                notes.append(
                    "Linie, których Superbet nie wystawia (nasza→najbliższa jego): "
                    f"{pairs}. To nie jest zły kurs, to brak rynku — takiego typu "
                    "nie postawisz."
                )
        near = [s for s in singles if s.superbet_verdict == "WITHIN_TOLERANCE"]
        if near:
            closest = sorted(
                near, key=lambda s: -(s.superbet_price_gap_pct or -99.0)
            )[:5]
            listed = "; ".join(
                f"{s.match} {market_label(s.market)} {s.line} {s.direction} "
                f"@{s.superbet_price} ({s.superbet_price_gap_pct:+.1f}% vs próg "
                f"{s.min_acceptable_odds})"
                for s in closest
            )
            notes.append(
                f"W tolerancji ({price_tolerance_pct:.0f}% pod progiem): {len(near)} "
                f"singli. Zmierzone na 1 269 rozliczonych wierszach z ceną: "
                f"wiersze z luką ≥ −5% trafiły 72,9% przy ROI +1,3%, a same wiersze "
                f"nad progiem 63,5% przy −0,8% na próbie 52 — trzymanie się progu "
                f"co do groszа wyrzucało 9 z 14 kandydatów i nic za to nie kupowało. "
                f"Najbliżej progu: {listed}."
            )
        # The "na dobicie" section, and it exists to price the idea rather than
        # to refuse it. A near-certain leg feels free -- it barely moves the
        # joint probability and it multiplies the price -- and the settled
        # record says it is not. See _PRICE_BANDS.
        certain = [
            s for s in singles
            if s.superbet_price and (s.p_central or 0) >= 0.75
        ]
        if certain:
            by_band: dict[str, list] = {}
            for single in certain:
                by_band.setdefault(single.price_band or "?", []).append(single)
            lines = []
            for band, rows_in in sorted(
                by_band.items(), key=lambda kv: -(kv[1][0].price_band_measured_edge or 0)
            ):
                edge = rows_in[0].price_band_measured_edge
                lines.append(
                    f"{band}: {len(rows_in)} "
                    f"(zmierzony edge {edge:+.1%})" if edge is not None else band
                )
            notes.append(
                "Pewne czytania (p_central ≥ 75%) z ceną, po zmierzonym pasmie "
                "kursu: " + " · ".join(lines) + ". Zmierzone na 668 rozliczonych "
                "wierszach z ceną: w pasmie 1.00–1.05 arkusz realizuje 97,5% "
                "przeciw 98,5% implikowanym (edge −1,0%), a w 1.05–1.10 89,3% "
                "przeciw 93,6% (−4,3%). **Noga „na dobicie\" po 1.03 nie jest "
                "darmowa — pewność jest realna i już siedzi w cenie**, a "
                "bukmacher mnoży kursy, więc każda taka noga zabiera około "
                "punktu EV. Pasmo, które płaci, to 1.35–1.60: 76,7% przeciw "
                f"69,4% implikowanym, edge +7,3%. Dlatego lista jest sortowana "
                f"tak, by szukać najpierw tam (próg pewności: "
                f"{CERTAINTY_PRICE_FLOOR:.2f})."
            )
        if singles and not value and not near:
            notes.append(
                "Żaden single nie osiąga minimalnego kursu na Superbecie ani nie "
                "mieści się w tolerancji. To jest odpowiedź o dniu, nie awaria — "
                "wysokie p_low nie jest przewagą, jeśli rynek stoi wyżej niż ono."
            )
    # Every veto/downgrade the analyst applied, with its reason -- visible in
    # the coupon file's header, not just as an exclusion count (Faza 5e).
    notes.extend(applied_vetoes)

    return CouponSet(
        run_id=stats_sheet.run_id,
        date=stats_sheet.date,
        generated_at=_now_iso(),
        singles=singles,
        slips=slips,
        rows_considered=len(stats_sheet.rows),
        events_considered=len({row.event_id for row in stats_sheet.rows}),
        not_before=not_before.isoformat() if not_before else None,
        excluded=dict(sorted(excluded.items())),
        notes=notes,
    )
