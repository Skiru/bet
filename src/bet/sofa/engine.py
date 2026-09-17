import math
from typing import Literal

from bet.sofa.contracts import Direction

MAX_LADDER_SIGMA = 1.25
K_PRICE = 10.0


def normal_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def predictive_sd(variance: float, mean: float, n: int) -> float:
    if n == 0:
        raise ValueError("n must be greater than 0")
    var_sample = max(variance, mean)
    var_pred = var_sample * (1.0 + 1.0 / n)
    return math.sqrt(var_pred)


def winning_boundary(line: float, direction: Direction) -> float:
    if line.is_integer():
        if direction == "OVER":
            return math.floor(line) + 0.5
        else:
            return math.ceil(line) - 0.5
    return line


def calc_p_central(
    centre: float, sd: float, boundary: float, direction: Direction
) -> float:
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

    return max(0.05, min(0.95, p))


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
