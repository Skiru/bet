"""Odds conversion, EV calculation, and staking utilities."""


def implied_probability(decimal_odds: float) -> float:
    """Convert decimal odds to implied probability. E.g., 2.0 → 0.50"""
    if decimal_odds <= 0:
        return 0.0
    return 1.0 / decimal_odds


def decimal_to_american(decimal_odds: float) -> str:
    """Convert decimal odds to American format."""
    if decimal_odds <= 1.0:
        return "+0"
    if decimal_odds >= 2.0:
        return f"+{round((decimal_odds - 1) * 100)}"
    else:
        return f"-{round(100 / (decimal_odds - 1))}"


def american_to_decimal(american: str) -> float:
    """Convert American odds string to decimal. +150 → 2.50, -200 → 1.50"""
    american = american.strip()
    if not american:
        return 1.0
    try:
        value = int(american.replace("+", ""))
    except ValueError:
        return 1.0
    if value >= 0:
        return 1 + value / 100
    else:
        return 1 + 100 / abs(value)


def expected_value(probability: float, odds: float) -> float:
    """EV = (probability * odds) - 1. Positive = +EV."""
    return (probability * odds) - 1


def min_acceptable_odds(hit_rate: float) -> float:
    """Minimum odds for +EV: 1 / hit_rate."""
    if hit_rate <= 0:
        return float("inf")
    return 1.0 / hit_rate


def kelly_fraction(
    probability: float, odds: float, fraction: float = 0.25
) -> float:
    """Fractional Kelly criterion. Returns fraction of bankroll to stake.

    Full Kelly: f = (p * (odds - 1) - (1 - p)) / (odds - 1)
    We apply a fraction (default 1/4) for safety.
    Returns 0 when EV ≤ 0.
    """
    if odds <= 1.0 or probability <= 0 or probability >= 1:
        return 0.0
    edge = probability * (odds - 1) - (1 - probability)
    if edge <= 0:
        return 0.0
    full_kelly = edge / (odds - 1)
    return full_kelly * fraction


def flat_stake(bankroll: float, max_stake: float = 2.0) -> float:
    """Flat staking: min(max_stake, bankroll * 0.05)."""
    if bankroll <= 0:
        return 0.0
    return min(max_stake, bankroll * 0.05)
