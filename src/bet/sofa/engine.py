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
EMPIRICAL_FREQUENCY_METRICS = frozenset({"sets_total"})


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


def calc_p_central_raw(
    centre: float, sd: float, boundary: float, direction: Direction
) -> float:
    """The normal-CDF estimate, unclamped. See outside_model_resolution."""
    if sd == 0.0:
        # Degenerate case, e.g. variance and mean are 0
        if direction == "OVER":
            p = 1.0 if centre > boundary else 0.0
        else:
            p = 1.0 if centre < boundary else 0.0
    else:
        z = (boundary - centre) / sd
        if direction == "OVER":
            z = -z
        p = normal_cdf(z)

    return p


def calc_p_central(
    centre: float, sd: float, boundary: float, direction: Direction
) -> float:
    return max(
        P_FLOOR, min(P_CEILING, calc_p_central_raw(centre, sd, boundary, direction))
    )


def devig(
    over_odds: float | None, under_odds: float | None
) -> tuple[float, float] | None:
    if over_odds is None or under_odds is None:
        return None
    if over_odds <= 1.0 or under_odds <= 1.0:
        return None

    implied_over = 1.0 / over_odds
    implied_under = 1.0 / under_odds
    overround = implied_over + implied_under

    return implied_over / overround, implied_under / overround


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
    centre: float, sample_sd: float, n: int, boundary: float, direction: Direction
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

    return calc_p_central(shifted_centre, shifted_sd, boundary, direction)


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
