import math
from typing import Literal

from bet.sofa.contracts import Direction

MAX_LADDER_SIGMA = 1.25
K_PRICE = 10.0


def normal_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


# Metrics that are NOT counts of independent events. The Poisson variance floor
# max(variance, mean) is a sensible guard against an over-tight sample of a
# count; for these it is nonsense. Measured over all 30 metrics at n=10: the
# floor never binds once for the 26 where it is justified — football and tennis
# event counts are overdispersed, so max() never picks the mean — and binds hard
# only where it makes no sense. sets_total's sd was inflated 3.34x, xg_total's
# 1.53x (F30).
NON_COUNT_METRICS = frozenset(
    {
        "sets_total",  # bounded: on BO3 it is 2 or 3, nothing else
        "tiebreaks_total",
        "xg_total",  # continuous, not a count
        "xg_for",
    }
)

# Metrics that take a handful of distinct values, where integrating a bell
# curve is the wrong model no matter what its width is. Removing the floor
# takes sets_total's error from +16.0 pp to +4.0 pp; the remaining 4 pp are the
# normal CDF itself, applied to a variable with two bars and no shoulders.
# For these the sample's own frequency above the winning boundary is the
# honest estimator, and it is available for free — run_sheet and settle both
# already count hits for the Laplace cap.
EMPIRICAL_FREQUENCY_METRICS = frozenset({"sets_total", "games_won_for"})

# games_won_for joined the set on 2026-09-18 (F49). It is not few-valued like
# sets_total, but it is violently **bimodal**, and for the same reason: in a
# best-of-three a player who wins in straight sets has won at least twelve
# games, so the distribution has a loser mode spread over 0-11 and a winner
# mode stacked on 12+. Across 570 observations in one day's samples the counts
# run ... 10:17, 11:10, **12:159**, 13:84 ... — a trough at eleven and a wall
# at twelve.
#
# Superbet's line sits at 11.5, in the trough. A normal CDF puts smooth
# density exactly where the real distribution has almost none, and it does so
# in one direction: measured on 7,926 settled rows, UNDER at the lines
# straddling the cliff ran predicted 0.404 against realised 0.320 (n=862) and
# 0.569 against 0.505 (n=837).
#
# Replayed out of the cache, 1,293 rungs, the two estimators score:
#
#     normal CDF   OVER 1.07   UNDER 0.93
#     empirical    OVER 1.01   UNDER 0.98
#
# Better on both sides, which is what a real fix looks like as against noise.


# Counts are right-skewed, and the normal CDF is symmetric. Integrating a bell
# curve over a skewed count overstates the upper tail near the centre, where
# almost every posted line sits, and it does so in ONE direction: every OVER
# rung is inflated and every UNDER rung is deflated by the same amount.
#
# Replayed over all 1,868,474 settled count rows out of the cache, scoring each
# rung the way run_sheet does and against `actual_value`:
#
#                        Brier     mean p   realised   bias
#     normal            0.17278    0.5000    0.5000   +0.0469  (OVER)
#     negative binomial 0.16865    0.5000    0.5000   -0.0055  (OVER)
#
# The bias is what matters more than the Brier: +4.7 pp on every OVER rung on
# the board is not noise, it is the reason a coupon comes out 88.8% OVER. On
# 2026-09-19 the shipping model claimed 0.4371 across its 428 OVER positions
# where those positions' own samples said 0.3465.
#
# A negative binomial with the same mean and predictive variance is the natural
# fix: it is discrete, supported on 0,1,2,..., and overdispersed by
# construction. Being discrete it also needs no support floor and no continuity
# fudge — the atom at zero is an atom, not a sliver of a bell curve.
#
# It is NOT applied everywhere. Measured per metric at n>=2000 and validated on
# an event-id split half, it wins on twelve metrics and loses on the high-mean
# shot and foul families, whose distributions are near enough symmetric that
# added skew is a cost. A metric not on this list keeps the normal: an unlisted
# metric must not silently change behaviour.
#
#     metric                  n        dBrier    half A     half B
#     goals_for          676040      -0.00818  -0.00806  -0.00830
#     goals_total        782237      -0.00239  -0.00212  -0.00266
#     corners_for         41950      -0.00251  -0.00270  -0.00232
#     offsides_total      23312      -0.00198  -0.00130  -0.00272
#     ... and, against it:
#     shots_on_target_total 35969   +0.00188  +0.00199  +0.00177
#     shots_total         34152      +0.00142  +0.00134  +0.00151
#
# The per-half variants carry only 190-352 settled rows each, too few for the
# n>=2000 bar, so they are listed on their own measurement from the one live
# settled day, where every one of them with n>=150 improved — most of all
# goals_1h_for at -0.03612, the largest gain in the whole study. That is the
# expected direction: a shorter window means a lower mean and more skew.
NEGATIVE_BINOMIAL_METRICS = frozenset(
    {
        # full match: n >= 2000, sign stable across an event-id split half
        "goals_for",
        "goals_total",
        "corners_for",
        "offsides_for",
        "offsides_total",
        "cards_points_for",
        "cards_points_total",
        "aces_for",
        "aces_total",
        "double_faults_for",
        "double_faults_total",
        "games_total",
        # per half: measured on the live settled day at n >= 150
        "goals_1h_total",
        "goals_1h_for",
        "goals_2h_total",
        "goals_2h_for",
        "corners_1h_total",
        "corners_1h_for",
    }
)


def uses_negative_binomial(market: str) -> bool:
    """True when this metric is priced from a negative binomial, not a normal.

    See NEGATIVE_BINOMIAL_METRICS. Unlisted metrics keep the normal CDF, so a
    metric nobody has measured cannot change behaviour by being added upstream.
    """
    return market in NEGATIVE_BINOMIAL_METRICS


def nb_survival(mean: float, variance: float, k: int) -> float:
    """P(X > k) for a count with this mean and variance, k an integer.

    Negative binomial when the variance exceeds the mean, which is the case
    that matters — football and tennis counts are overdispersed, which is why
    the Poisson floor in `predictive_sd` never binds for them. When it does
    not, the distribution is Poisson and this returns that instead of solving
    for a negative r.

    Summed rather than evaluated through a regularised incomplete beta: the
    counts here are small (lines run to about 30) so the sum is short and
    exact, and it needs no dependency this project does not already have.
    """
    if mean <= 0.0:
        return 0.0
    if k < 0:
        return 1.0
    if variance <= mean * (1.0 + 1e-9):
        # Poisson: P(X<=k) = e^-m sum_{i<=k} m^i / i!
        term = math.exp(-mean)
        acc = term
        for i in range(1, k + 1):
            term *= mean / i
            acc += term
        return max(0.0, 1.0 - min(acc, 1.0))

    r = mean * mean / (variance - mean)
    p = r / (r + mean)
    log_p = math.log(p)
    log_1mp = math.log1p(-p)
    lgamma_r = math.lgamma(r)
    acc = 0.0
    for i in range(0, k + 1):
        acc += math.exp(
            math.lgamma(i + r) - lgamma_r - math.lgamma(i + 1) + r * log_p + i * log_1mp
        )
        if acc >= 1.0:
            break
    return max(0.0, 1.0 - min(acc, 1.0))


def calc_p_central_nb_raw(
    centre: float, sd: float, boundary: float, direction: Direction
) -> float:
    """The negative-binomial estimate, unclamped. See nb_survival.

    `boundary` is the winning boundary, so OVER at line 2.5 asks for P(X >= 3)
    and the integer below the boundary is the last losing count.
    """
    survival = nb_survival(centre, sd * sd, math.floor(boundary))
    return survival if direction == "OVER" else 1.0 - survival


def predictive_sd(
    variance: float, mean: float, n: int, *, apply_poisson_floor: bool = True
) -> float:
    if n == 0:
        raise ValueError("n must be greater than 0")
    var_sample = max(variance, mean) if apply_poisson_floor else variance
    var_pred = var_sample * (1.0 + 1.0 / n)
    return math.sqrt(var_pred)


def uses_poisson_floor(market: str) -> bool:
    return market not in NON_COUNT_METRICS


def uses_empirical_frequency(market: str) -> bool:
    return market in EMPIRICAL_FREQUENCY_METRICS


P_FLOOR = 0.05
P_CEILING = 0.95


def outside_model_resolution(p_raw: float) -> bool:
    """True when an estimate lands outside the band this model can resolve.

    The [0.05, 0.95] clamp was introduced so that a unanimous sample of ten
    could not claim certainty. That is a sound reason to refuse to *report* a
    number, and an unsound reason to report the nearest one instead: a clamped
    value is not an estimate, it is the model saying the question is past its
    resolution. Priced as though it were an estimate it becomes a claim that
    every impossible thing happens one time in twenty, and since the coupon
    ranks by surplus, those are precisely the rows it selects (F35).

    So the clamp is kept as a guard for callers that need a number in band,
    and this predicate is what decides whether a rung may be priced at all.
    """
    return p_raw < P_FLOOR or p_raw > P_CEILING


def p_empirical_raw(hits: int, n: int) -> float:
    """The sample's own frequency, unclamped. See outside_model_resolution."""
    if n <= 0:
        raise ValueError("n must be greater than 0")
    return hits / n


def p_empirical(hits: int, n: int) -> float:
    """The sample's own frequency above the winning boundary.

    For a variable with two possible values this is the estimator with the
    right shape. It is clamped to the same [0.05, 0.95] band as calc_p_central,
    so a sample of ten that happens to be unanimous does not claim certainty.
    """
    return max(P_FLOOR, min(P_CEILING, p_empirical_raw(hits, n)))


def winning_boundary(line: float, direction: Direction) -> float:
    if line.is_integer():
        if direction == "OVER":
            return math.floor(line) + 0.5
        else:
            return math.ceil(line) - 0.5
    return line


# A count of k occupies the interval [k-0.5, k+0.5] under a continuous
# approximation, so the support of a non-negative count starts at -0.5, not at
# 0.0. The difference is not pedantry: it is the whole outcome "exactly zero".
#
# Both were measured against 516,883 settled rows out of the cache, scoring
# each rung the way run_sheet does. In the tail the coupon actually selects
# (p < 0.10), predicted vs realised came out:
#
#     no floor      0.0738 vs 0.0684   ratio 0.93
#     floor  0.0    0.0741 vs 0.1083   ratio 1.46   <- worse than no floor
#     floor -0.5    0.0729 vs 0.0724   ratio 0.99
#
# Clamping at 0.0 was the obvious fix and it is the wrong one: it deletes the
# mass below zero that, for a low-mean count, was standing in for the atom at
# zero, and the low tail goes from mildly overconfident to badly
# underconfident. -0.5 removes the impossible region *and* keeps the atom.
COUNT_SUPPORT_FLOOR = -0.5


def support_floor_for(market: str) -> float | None:
    """The smallest value the quantity can take, or None if unconstrained.

    A corner count cannot be negative, and the normal CDF does not know that.
    See calc_p_central_raw and COUNT_SUPPORT_FLOOR. The non-count metrics are
    left alone — sets_total is priced from its own empirical frequency
    (EMPIRICAL_FREQUENCY_METRICS) and the xG pair has never produced a sample
    — so this changes nothing for them and the measurement does not extend
    there.
    """
    return COUNT_SUPPORT_FLOOR if uses_poisson_floor(market) else None


def calc_p_central_raw(
    centre: float,
    sd: float,
    boundary: float,
    direction: Direction,
    support_floor: float | None = None,
) -> float:
    """The normal-CDF estimate, unclamped. See outside_model_resolution.

    ``support_floor`` conditions the estimate on the quantity being at least
    that value. Without it the normal puts mass on
    a negative number of corners, and the rung at line 0.5 UNDER collects
    every bit of it: Ruch Chorzow on 2026-09-18 had a centre of 5.30 and a
    predictive sd of 4.25, so the model claimed P(zero corners) = 0.1294 of
    which **0.1062 — 82% — was the mass below zero**. The observed ten
    matches were [5,7,7,5,2,7,3,16,3,3]; the event had never once happened.
    Priced at 30.00 that row won the top slot of the coupon (F41).

    The floor is -0.5 rather than 0.0 because the quantity is a count and a
    count of zero occupies [-0.5, 0.5); see COUNT_SUPPORT_FLOOR for the
    measurement that settled it.

    This is the same defect outside_model_resolution was written to refuse
    "the way an all-zero sample is refused", but that guard only sees it for
    the one metric priced from its empirical frequency; for every count the
    CDF hands it a number well above P_FLOOR and the guard waves it through.
    """
    if sd == 0.0:
        # Degenerate case, e.g. variance and mean are 0
        if direction == "OVER":
            p = 1.0 if centre > boundary else 0.0
        else:
            p = 1.0 if centre < boundary else 0.0
        return p

    z = (boundary - centre) / sd
    p_below_boundary = normal_cdf(z)

    if support_floor is not None:
        p_below_floor = normal_cdf((support_floor - centre) / sd)
        mass_in_support = 1.0 - p_below_floor
        if mass_in_support <= 1e-12:
            # The model puts essentially everything below the floor. It has no
            # opinion left to renormalise; say so rather than divide by noise.
            # outside_model_resolution refuses whatever comes back.
            return 0.0 if direction == "UNDER" else 1.0
        # Condition on the quantity being inside its own support. A boundary
        # at or below the floor leaves nothing under it: an UNDER 0.5 rung on
        # a count is "exactly zero", not "zero or fewer".
        p_below_boundary = max(0.0, p_below_boundary - p_below_floor)
        p_below_boundary /= mass_in_support

    return 1.0 - p_below_boundary if direction == "OVER" else p_below_boundary


def calc_p_central(
    centre: float,
    sd: float,
    boundary: float,
    direction: Direction,
    support_floor: float | None = None,
) -> float:
    return max(
        P_FLOOR,
        min(
            P_CEILING,
            calc_p_central_raw(centre, sd, boundary, direction, support_floor),
        ),
    )


# How the bookmaker's margin is taken back out of a two-sided price.
#
# "proportional" divides both implied probabilities by their sum, which assumes
# the margin is spread evenly in *relative* terms. Bookmakers do not price that
# way, and the consequence is not small. Measured on the 2,354 rungs of
# 2026-09-18 that were both priced and settled:
#
#     devigged band   proportional says   actually won
#       0.10-0.20          0.158             0.087
#       0.20-0.30          0.250             0.179
#       0.70-0.80          0.750             0.822
#       0.80-0.90          0.842             0.913
#
# Seven points of overstatement on the long shot and seven of understatement on
# the favourite — the classic favourite-longshot bias, and perfectly
# antisymmetric because the two sides of a rung are complements.
#
# That bias is not cosmetic here, because `market_p` is (a) what `bar_probability`
# shrinks the sample toward and (b) what `edge` is measured against. Inflating
# the long shot's market probability pulls its `p_bar` up and its bar down,
# while deflating the favourite's does the reverse. It is one defect producing
# both halves of the 2026-09-18 complaint: a coupon made only of long shots,
# and no short-priced row able to qualify at all (F51).
#
# "power" solves q_over^k + q_under^k = 1. Scored against the same settled
# rungs, lower is better on all three:
#
#     method           Brier     log loss   |calibration error|
#     proportional    0.17115     0.51899        0.0595
#     additive/Shin   0.16845     0.51000        0.0316
#     power           0.16768     0.50820        0.0203
#
# and it wins on both sports, on both halves of an event-id split, and on the
# four largest market families taken separately.
DEVIG_METHOD = "power"


def devig_many(implied: list[float], method: str | None = None) -> list[float] | None:
    """Take the margin out of a complete market of any width.

    The same estimator as the two-sided `devig`, and deliberately the same: a
    three-way market is not a different kind of price, and devigging "who takes
    more corners" proportionally while devigging "over/under" by power would
    leave the favourite-longshot bias in exactly the family that has no ladder
    check to catch it.

    Measured only on two-way rungs so far — that is what 2026-09-18 settled —
    so this generalisation rests on the estimator being the same one, not on
    its own measurement. SETTLE now records derived rows with their price, so
    the next fits can check it separately.
    """
    if len(implied) < 2 or any(q <= 0.0 or q >= 1.0 for q in implied):
        return None
    if (method or DEVIG_METHOD) != "power":
        total = sum(implied)
        if total <= 0.0:
            return None
        return [q / total for q in implied]

    lo, hi = 0.05, 20.0
    for _ in range(200):
        k = (lo + hi) / 2.0
        if sum(q**k for q in implied) > 1.0:
            lo = k
        else:
            hi = k
    k = (lo + hi) / 2.0
    powered = [q**k for q in implied]
    # Bisection cannot land exactly on 1; renormalise the residual (~1e-12) so
    # the result is a distribution to the last bit. It cannot reintroduce the
    # bias it is applied on top of.
    total = sum(powered)
    return [q / total for q in powered]


def devig(
    over_odds: float | None,
    under_odds: float | None,
    method: str | None = None,
) -> tuple[float, float] | None:
    if over_odds is None or under_odds is None:
        return None
    if over_odds <= 1.0 or under_odds <= 1.0:
        return None

    implied_over = 1.0 / over_odds
    implied_under = 1.0 / under_odds

    pair = devig_many([implied_over, implied_under], method)
    if pair is None:
        return None
    return pair[0], pair[1]


def ladder_centre(rungs: list[tuple[float, float]]) -> float | None:
    """
    Interpolates ladder centre where over_p crosses 0.5.
    rungs should be a list of (line, over_p), sorted by line.
    """
    if len(rungs) < 2:
        return None

    sorted_rungs = sorted(rungs, key=lambda x: x[0])

    # Check if there is a crossing of 0.5
    for i in range(len(sorted_rungs) - 1):
        line1, p1 = sorted_rungs[i]
        line2, p2 = sorted_rungs[i + 1]

        # We assume p is over_p, so it should monotonically decrease with line
        if (p1 >= 0.5 >= p2) or (p1 <= 0.5 <= p2):
            if p1 == p2:
                return (line1 + line2) / 2.0

            # Linear interpolation between the two rungs that straddle 0.5:
            #   p(line) = p1 + (line - line1) * (p2 - p1) / (line2 - line1)
            # We want line where p = 0.5
            # 0.5 = p1 + (line - line1) * (p2 - p1) / (line2 - line1)
            # 0.5 - p1 = (line - line1) * (p2 - p1) / (line2 - line1)
            # (0.5 - p1) * (line2 - line1) / (p2 - p1) = line - line1
            line = line1 + (0.5 - p1) * (line2 - line1) / (p2 - p1)
            return line

    return None


# How far our predictive spread may sit from the one the market's own ladder
# implies before the row's tail probabilities stop being credible.
#
# The ladder gate compares *centres*. Nothing compared spreads, and a
# distribution of the right centre but the wrong width is mispriced at every
# rung at once while passing the centre check: too wide and both tails are
# overstated, which is precisely where the bar is easiest to beat. On
# 2026-09-18, 12 coupon rows sat on ladders where *every* rung came back
# VALUE, and games_won_for ran at 2.69x the market's implied spread because a
# player's games-won sample mixes two-set and three-set matches against
# different opponents while the price is for one specific match.
#
# The band is deliberately loose. Measured over 314 ladders the ratio ran
# p05=0.77 to p95=1.83, so [0.5, 2.0] refuses 3.8% - a genuine outlier band,
# not a constant fitted to one day.
MIN_SPREAD_RATIO = 0.5
MAX_SPREAD_RATIO = 2.0


def ladder_implied_sd(rungs: list[tuple[float, float]]) -> float | None:
    """The spread the market's own ladder implies, from its quartiles.

    `rungs` is (line, devigged P(over line)), as for `ladder_centre`. Returns
    None when the ladder does not reach both quartiles, which is the common
    case for a short or one-sided ladder and must not be read as agreement.
    """
    points = sorted(rungs)
    if len(points) < 3:
        return None

    def quantile(target: float) -> float | None:
        for (line_a, p_a), (line_b, p_b) in zip(points, points[1:], strict=False):
            if (p_a >= target >= p_b) or (p_a <= target <= p_b):
                if p_a == p_b:
                    return (line_a + line_b) / 2.0
                return line_a + (target - p_a) * (line_b - line_a) / (p_b - p_a)
        return None

    upper = quantile(0.75)
    lower = quantile(0.25)
    if upper is None or lower is None or lower <= upper:
        return None
    # The interquartile range of a normal is 1.349 standard deviations.
    return (lower - upper) / 1.3490


def calculate_p_low(
    centre: float,
    sample_sd: float,
    n: int,
    boundary: float,
    direction: Direction,
    support_floor: float | None = None,
) -> float:
    if n == 0:
        raise ValueError("n must be greater than 0")
    se = sample_sd / math.sqrt(n)

    # Shift centre in the direction opposite to the bet.
    # If OVER, we want lower values, so subtract 1.96*SE
    # If UNDER, we want higher values, so add 1.96*SE
    shifted_centre = centre - 1.96 * se if direction == "OVER" else centre + 1.96 * se

    # Recalculate predictive SD for the shifted centre
    # We use variance = sample_sd**2, mean = shifted_centre
    # to be consistent with var_sample = max(variance, mean)
    shifted_var_sample = max(sample_sd**2, shifted_centre)
    shifted_sd = math.sqrt(shifted_var_sample * (1.0 + 1.0 / n))

    return calc_p_central(
        shifted_centre, shifted_sd, boundary, direction, support_floor
    )


def bar_probability(
    p_central: float,
    hits: int,
    n: int,
    p_low_val: float,
    market_p: float | None,
    k_price: float = K_PRICE,
    correction: float = 0.0,
    force_weight_0: bool = False,
) -> tuple[float, str]:
    p = p_central
    bar_reason = "none"

    if hits == n and n > 0:
        laplace_p = (hits + 1) / (n + 2)
        if laplace_p < p:
            p = laplace_p
            bar_reason = "laplace_cap"

    if n < 8:
        if p_low_val < p:
            p = p_low_val
            bar_reason = "p_low_cap"

    # §6.5 step 2: the calibration correction may only LOWER p, i.e. only
    # RAISE the bar. Enforcing it here and not only at fit time makes it a
    # property of the engine: a negative number in a config file cannot turn a
    # measured overconfidence into a discount.
    p = max(0.01, p - max(0.0, correction))

    if market_p is not None:
        if force_weight_0:
            w = 0.0
            bar_reason = "veto_uninformative"
        else:
            w = n / (n + k_price)
        p_bar = w * p + (1.0 - w) * market_p
    else:
        p_bar = p
        if force_weight_0:
            bar_reason = "veto_uninformative_no_price"

    return p_bar, bar_reason


def get_required_odds(p_bar: float, tier: Literal["CALL", "LEAN"] = "LEAN") -> float:
    margin = 1.05 if tier == "CALL" else 1.10
    return round(margin / p_bar, 4)


def bar_is_unreachable(
    offered_odds: float | None,
    market_p: float | None,
    n: int,
    *,
    k_price: float = K_PRICE,
    tier: Literal["CALL", "LEAN"] = "LEAN",
) -> bool:
    """True when NO sample could make this rung VALUE, at this price.

    `p_bar` is a blend of our estimate and the market's, and our estimate is
    capped at `P_CEILING`. So the largest bar probability this rung can carry,
    whatever the sample says, is

        w * P_CEILING + (1 - w) * market_p,    w = n / (n + k_price)

    and if the offered price is below `margin` over that, the row is refused by
    arithmetic rather than by evidence. On 2026-09-18 that was 1,546 of
    football's 7,379 priced rows (21.0%) and 135 of tennis's 1,148 (11.8%) —
    every short-priced favourite on the board, including all eight legs the
    operator asked about.

    This is not a defect to be tuned away: at 1.07 there is no sample on earth
    that justifies a 10% expected-value margin, because the book's own margin
    on a favourite is smaller than the edge we would have to have. It is a
    defect to let it look like a near miss. BELOW_BAR on a row that missed by
    2% and BELOW_BAR on a row that could not have qualified are different
    facts, and the operator has to be able to tell them apart (F52).
    """
    if offered_odds is None or market_p is None or n <= 0:
        return False
    w = n / (n + k_price)
    max_p_bar = w * P_CEILING + (1.0 - w) * market_p
    if max_p_bar <= 0.0:
        return False
    return offered_odds < get_required_odds(max_p_bar, tier)
