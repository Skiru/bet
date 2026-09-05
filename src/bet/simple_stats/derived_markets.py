"""Markets Superbet posts, this pipeline never generates, and our samples can reach.

Why this module exists
----------------------
ANALYZE emits one row per (market, line, direction) from a fixed vocabulary of
over/under totals. Superbet's screen carries a second family that vocabulary
cannot express at all: *comparative* markets. "Liczba rzutów rożnych - H2H"
(which side takes more corners), "Rzuty rożne handicap", "Najwięcej strzałów",
"Najwięcej kartek", and the per-half variants of each. Measured over nine
fixtures pulled from the per-event endpoint on 2026-09-05, every one of those
fixtures carried the corner H2H and the corner "najwięcej" markets, and eight
of nine carried the cards handicap.

None of them reach ``superbet_offer.json``: ``normalize_lines`` only keeps a
name that parses as powyżej/poniżej, and only records an unmapped name if it
*also* contains the word "liczba". "Najwięcej kartek" contains neither. So the
whole family is invisible to the pipeline -- not dropped as unpriceable, but
never seen.

They are, however, a function of quantities ENRICH already samples per team:
``corners_for``, ``shots_for``, ``shots_on_target_for`` hold each side's own
last ten. P(A outshoots B) is arithmetic over two samples we already hold.

What was measured before any of this was written
------------------------------------------------
An offline replay over the settled slates on disk (2026-08-28...09-03; each
fixture's pre-kickoff l10 against ``runs/_backtest_actuals.json``, which carries
per-team ``*_for`` counts for 392 football fixtures). Three-way Brier, lower is
better, against the honest yardstick -- not zero, but *the pooled base rate*,
which is what you get for knowing nothing about the fixture:

    metric                n     base    model    gate .65      95% CI
    corners_for          288   0.5837   0.5518   0.695 (95)  [.600 .789]
    shots_for            199   0.5059   0.4818   0.716 (95)  [.621 .800]
    shots_on_target_for  210   0.5823   0.5315   0.720 (50)  [.600 .840]
    cards_for            274   0.6374   0.6404   --          --
    fouls_for            213   0.5623   0.5801   0.549 (51)  --
    corners_1h_for        82   0.5648   0.5789   0.520 (25)  --

**Three of six are worse than knowing nothing.** cards_for and fouls_for score
above their own base rate: the samples carry no usable signal about which side
out-cards or out-fouls the other, and at the 0.65 gate fouls hit 0.549 -- a
confident call that is barely a coin. corners_1h_for fails for the ordinary
reason halves fail, 82 fixtures of a quantity whose mean is under 3. Those three
are refused here rather than merely warned about, because a probability that
loses to its own base rate is worse than no probability: it reads like evidence.

The estimator, and what each piece is
-------------------------------------
1. **Independent Poisson difference (Skellam).** P(A>B), P(A=B), P(A<B) from
   two means. Independence is an assumption, not a measurement -- see the
   caveat below.
2. **A flat home correction**, +/- ``home_delta``/2 on the two means.
   ``home_delta`` is measured per metric over the same replay: corners +1.19,
   shots +2.40, SOT +0.86. It matters more than anything else here, because an
   l10 sample mixes home and away matches while the fixture being priced has a
   home side. The two pieces separate cleanly on corners, against a base rate
   of 0.5837: 0.5744 with neither, 0.5618 with shrinkage alone, 0.5575 with the
   correction alone, 0.5518 with both -- the correction is worth more than the
   shrinkage, and without it the calibration curve sits a full bucket low.
3. **Shrinkage toward the metric's base rate**, ``SHRINK_K = 0.8``.

What was tried and did not survive
----------------------------------
Normalising *each observation* by its own venue (subtract delta/2 from a home
match, add it to an away one) instead of applying one flat correction. It could
only be tested on 2026-09-02 and 09-03, because ``ProviderValue.venue`` does not
exist in any earlier dossier -- all 3,935 observations before 09-02 carry
``None``. On the 39-49 fixtures per metric where it can be tested it moved
Brier by 0.001-0.003 in both directions, which at that n is noise. It is not
implemented. This is the same conclusion the pooled-venue work reached from the
other end: venue is a prior, not a split.

The three caveats a reader is owed
----------------------------------
* **``SHRINK_K`` and ``GATE`` were chosen on this data.** Both were picked off a
  grid run against the same 288 rows they are reported on, so the gate hit rates
  are optimistic and neither bootstrap prices that selection in. Treat 0.695 as
  the top of a range whose bottom is ``price_floor``, 0.600.
* **The rows are not 288 independent days.** 2026-08-29 alone is 132 of the 288
  corner fixtures, 46%, so an iid bootstrap over rows overstates its own
  precision. Resampling whole slates instead barely moves the floor -- corners
  0.603 against the iid 0.600, shots 0.635 against 0.621 -- so clustering turns
  out not to be what limits this. ``price_floor`` takes the lower of the two
  either way. Six slates make a coarse block bootstrap and a seventh could
  move it.
* **Independence is assumed, never measured.** Two sides' corner counts in one
  match are plausibly correlated through game state (a team chasing takes more
  corners *and* concedes fewer). The measured calibration is the defence: if the
  assumption were badly wrong the calibration curve would not be monotone. It is
  a defence, not a proof.
* **Nothing here was ever settled against a *price*.** The replay says how often
  the estimate was right, not whether it beat what Superbet charged: no
  historical comparative-market prices exist on disk. Every "value" statement
  built on this module is a statement about a probability, and the surplus is
  arithmetic on top of an unvalidated premise.

This module is deliberately import-isolated from ``coupons`` and
``bet_builder_draft``. A derived probability is not a row, cannot be a leg,
cannot be staked, and must never be compared against ``p_low`` as though the two
had the same standing.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

# Outcome order used everywhere in this module: (side A more, equal, side B
# more), where A is the *home* side for football. Equality is a real outcome and
# a frequent one -- corners land level on 12.2% of fixtures and cards on 20.1%
# -- and on the three-way "H2H" market it loses. Collapsing it into a two-way is
# the single commonest way this family is misread.
Triple = tuple[float, float, float]

Verdict = Literal[
    "USABLE",
    "REFUSED_NO_SIGNAL",
    "REFUSED_UNKNOWN_METRIC",
    "REFUSED_THIN_SAMPLE",
    "REFUSED_OUT_OF_RANGE",
]

# Below this many observations on either side the estimate is not offered at
# all. Not tuned: it is ``MIN_SAMPLE`` from the replay, which required five a
# side to admit a fixture, so anything thinner has never been measured.
MIN_SAMPLE = 5

# Weight on the model against the metric's base rate.
SHRINK_K = 0.8

# Above this the estimate is called "confident" and gets its measured hit rate
# quoted. Chosen on the replay data -- see the caveat in the module docstring.
GATE = 0.65


@dataclass(frozen=True)
class Calibration:
    """What the replay measured for one metric. Every field is a measurement."""

    base: Triple
    home_delta: float
    n: int
    brier_base: float
    brier_model: float
    gate_hits: float | None
    gate_n: int | None
    # Two intervals over the same hits, because the rows are not independent
    # draws: one slate (2026-08-29) is 46% of the corner replay, so an iid
    # bootstrap flatters itself. ``gate_ci_by_day`` resamples whole slates
    # instead. They disagree less than expected -- corners 0.600 against 0.592
    # at the bottom -- but the disagreement is the point, and pricing uses
    # whichever is lower. Six slates is a coarse block bootstrap; say so.
    gate_ci: tuple[float, float] | None
    gate_ci_by_day: tuple[float, float] | None = None
    # Superbet's own market names for this comparison, as seen on the per-event
    # endpoint on 2026-09-05. The three-way is "najwięcej"/"H2H"; the two-way is
    # the handicap ladder at +/-0.5.
    three_way_names: tuple[str, ...] = ()
    handicap_names: tuple[str, ...] = ()

    @property
    def price_floor(self) -> float | None:
        """The probability a confident call must clear before a price is judged.

        The lower of the two bootstrap floors. Not the point estimate: the gate
        and the shrinkage were both chosen on these same rows, so the point
        estimate is the optimistic end of what was measured, and the floor is
        the number a bet should have to beat.
        """
        floors = [ci[0] for ci in (self.gate_ci, self.gate_ci_by_day) if ci]
        return min(floors) if floors else None


CALIBRATION: dict[str, Calibration] = {
    "corners_for": Calibration(
        base=(0.528, 0.122, 0.351),
        home_delta=1.19,
        n=288,
        brier_base=0.5837,
        brier_model=0.5518,
        gate_hits=0.695,
        gate_n=95,
        gate_ci=(0.600, 0.789),
        gate_ci_by_day=(0.603, 0.748),
        three_way_names=("Liczba rzutów rożnych - H2H",),
        handicap_names=("Rzuty rożne handicap",),
    ),
    "shots_for": Calibration(
        base=(0.583, 0.025, 0.392),
        home_delta=2.40,
        n=199,
        brier_base=0.5059,
        brier_model=0.4818,
        gate_hits=0.716,
        gate_n=95,
        gate_ci=(0.621, 0.800),
        gate_ci_by_day=(0.635, 0.812),
        three_way_names=("Najwięcej strzałów",),
        handicap_names=(),
    ),
    "shots_on_target_for": Calibration(
        base=(0.529, 0.119, 0.352),
        home_delta=0.86,
        n=210,
        brier_base=0.5823,
        brier_model=0.5315,
        gate_hits=0.720,
        gate_n=50,
        gate_ci=(0.600, 0.840),
        gate_ci_by_day=(0.615, 0.854),
        three_way_names=("Najwięcej celnych strzałów",),
        handicap_names=("Liczba celnych strzałów - handicap",),
    ),
}

# Metrics whose comparative market Superbet posts, whose sample we hold, and
# whose estimate lost to its own base rate in the replay. The reason travels
# with the refusal so a reader is never told merely "no".
REFUSED: dict[str, str] = {
    "cards_for": (
        "Brier 0.6404 przeciw bazie 0.6374 na 274 meczach - model przegrywa z "
        "samą częstością bazową. Osobno: nasze cards_for liczy tylko żółte, a "
        "Superbet liczy też czerwone, więc próbka i rynek mierzą co innego."
    ),
    "cards_points_for": (
        "Tylko 16 rozegranych meczów ma i próbkę, i wynik - metryka powstała "
        "2026-09-03. Nie zmierzone, nie odmówione: brak danych."
    ),
    "fouls_for": (
        "Brier 0.5801 przeciw bazie 0.5623 na 213 meczach, a przy progu 0.65 "
        "trafność 0.549 (n=51) - pewne typy są niemal rzutem monetą."
    ),
    "corners_1h_for": (
        "Brier 0.5789 przeciw bazie 0.5648 na 82 meczach; przy progu 0.65 "
        "trafność 0.520 (n=25), przy 0.70 - 0.467 (n=15). Połowy są za cienkie."
    ),
}


def _poisson_pmf(k: int, lam: float) -> float:
    """P(X = k) for X ~ Poisson(lam), computed in log space.

    The direct form ``exp(-lam) * lam**k / factorial(k)`` is what this was, and
    it raises ``OverflowError`` once ``factorial(k)`` outgrows a float -- around
    k = 170, which is inside the range a larger ``cap`` would ask for. Log space
    has no such ceiling and loses nothing at the scales here.
    """
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam + k * math.log(lam) - math.lgamma(k + 1))


def skellam_three_way(lam_a: float, lam_b: float, *, cap: int = 80) -> Triple:
    """P(A>B), P(A=B), P(A<B) for two independent Poisson counts.

    ``cap`` truncates the two supports, and the result is renormalised so
    truncation cannot leak probability -- but renormalising does not make
    truncation free, because it redistributes the missing tail across both
    sides unevenly. The cap was 45 and that was too low: at lambda 25 a side,
    which a corrected shots line reaches, it moved the answer by 2.3e-05.
    At 80 the same comparison against 200 moves it by less than 1e-12.
    """
    pa = [_poisson_pmf(k, lam_a) for k in range(cap)]
    pb = [_poisson_pmf(k, lam_b) for k in range(cap)]
    more = equal = less = 0.0
    for i, ai in enumerate(pa):
        if ai == 0.0:
            continue
        for j, bj in enumerate(pb):
            p = ai * bj
            if i > j:
                more += p
            elif i == j:
                equal += p
            else:
                less += p
    total = more + equal + less
    if total <= 0:
        return (1 / 3, 1 / 3, 1 / 3)
    return (more / total, equal / total, less / total)


def shrink(p: Triple, base: Triple, k: float = SHRINK_K) -> Triple:
    return (
        k * p[0] + (1 - k) * base[0],
        k * p[1] + (1 - k) * base[1],
        k * p[2] + (1 - k) * base[2],
    )


@dataclass(frozen=True)
class DerivedEstimate:
    """One comparative market's probability, with everything needed to doubt it."""

    metric: str
    verdict: Verdict
    reason: str = ""
    probabilities: Triple | None = None
    lam_home: float | None = None
    lam_away: float | None = None
    n_home: int = 0
    n_away: int = 0
    mean_home: float | None = None
    mean_away: float | None = None
    calibration: Calibration | None = None

    @property
    def confident(self) -> bool:
        if not self.probabilities:
            return False
        return max(self.probabilities[0], self.probabilities[2]) >= GATE

    @property
    def called_side(self) -> str | None:
        if not self.probabilities:
            return None
        if self.probabilities[0] >= self.probabilities[2]:
            return "home"
        return "away"


def estimate(
    metric: str, home_sample: Sequence[float], away_sample: Sequence[float]
) -> DerivedEstimate:
    """The comparative estimate for one fixture, or a refusal that says why."""
    if metric in REFUSED:
        return DerivedEstimate(
            metric=metric, verdict="REFUSED_NO_SIGNAL", reason=REFUSED[metric]
        )
    cal = CALIBRATION.get(metric)
    if cal is None:
        return DerivedEstimate(
            metric=metric,
            verdict="REFUSED_UNKNOWN_METRIC",
            reason=(
                "Ta metryka nie przeszła replayu - nie wiadomo, czy estymator na niej "
                "działa. Zmierz ją, zanim jej użyjesz."
            ),
        )
    if len(home_sample) < MIN_SAMPLE or len(away_sample) < MIN_SAMPLE:
        return DerivedEstimate(
            metric=metric,
            verdict="REFUSED_THIN_SAMPLE",
            reason=(
                f"Próbka {len(home_sample)}/{len(away_sample)}, "
                f"minimum to {MIN_SAMPLE} na stronę."
            ),
            n_home=len(home_sample),
            n_away=len(away_sample),
            calibration=cal,
        )
    mean_home = sum(home_sample) / len(home_sample)
    mean_away = sum(away_sample) / len(away_sample)
    lam_home = mean_home + cal.home_delta / 2
    lam_away = mean_away - cal.home_delta / 2
    # The home correction is additive and was measured on aggregate means. When
    # a sample mean is so low that the correction drives a rate to zero, the
    # additive model is outside the range it was fitted in -- and clamping the
    # rate to a small positive number does not rescue it, it *manufactures* an
    # asymmetry: an all-zero pair of samples came out as 0.451 / 0.457 / 0.092,
    # a confident-looking distribution built from two samples that said nothing.
    #
    # This never happened once in the 697 replayed fixtures, so refusing costs
    # nothing that was ever measured, and a mean of zero is in any case the
    # documented shape of "the provider had no data" rather than of "the team
    # took no corners".
    if lam_home <= 0 or lam_away <= 0 or mean_home == 0 or mean_away == 0:
        return DerivedEstimate(
            metric=metric,
            verdict="REFUSED_OUT_OF_RANGE",
            reason=(
                f"Średnie {mean_home:.2f}/{mean_away:.2f} przy korekcie "
                f"{cal.home_delta:+.2f} dają nieujemną intensywność albo zerową "
                "próbkę. W 697 meczach replayu taki przypadek nie wystąpił ani "
                "razu, więc estymator nie był tu nigdy sprawdzony. Zero w tej "
                "metryce zwykle znaczy 'dostawca nie miał danych', nie 'zero rzutów'."
            ),
            n_home=len(home_sample),
            n_away=len(away_sample),
            mean_home=mean_home,
            mean_away=mean_away,
            calibration=cal,
        )
    probs = shrink(skellam_three_way(lam_home, lam_away), cal.base)
    return DerivedEstimate(
        metric=metric,
        verdict="USABLE",
        probabilities=probs,
        lam_home=lam_home,
        lam_away=lam_away,
        n_home=len(home_sample),
        n_away=len(away_sample),
        mean_home=mean_home,
        mean_away=mean_away,
        calibration=cal,
    )


# --- the price side, which needs no model at all --------------------------


def devig(prices: Sequence[float]) -> tuple[float, ...]:
    """Proportional devig, the same method ``superbet_offer`` uses on totals.

    Proportional and not Shin, so a number from here is comparable with
    ``market_probability`` elsewhere in the pipeline rather than being a second,
    silently different convention.
    """
    if any(p <= 1.0 for p in prices):
        raise ValueError("a decimal price must exceed 1.0")
    implied = [1.0 / p for p in prices]
    total = sum(implied)
    return tuple(x / total for x in implied)


def overround(prices: Sequence[float]) -> float:
    return sum(1.0 / p for p in prices) - 1.0


def dutch(prices: Sequence[float]) -> float:
    """The single price equivalent to backing every one of these outcomes.

    Used to compare a union assembled out of a three-way market ("remis" plus
    the outsider) against the two-way that pays for the same union in one leg.
    """
    return 1.0 / sum(1.0 / p for p in prices)


@dataclass(frozen=True)
class CrossMarketGap:
    """The same outcome, two prices, one screen."""

    outcome: str
    direct_price: float
    synthetic_price: float

    @property
    def gain(self) -> float:
        return self.direct_price / self.synthetic_price - 1.0


def handicap_versus_three_way(
    *,
    favourite_price: float,
    draw_price: float,
    outsider_price: float,
    handicap_outsider_price: float,
) -> CrossMarketGap:
    """Compare "outsider +0.5" against "draw + outsider" bought on the 3-way.

    Both pay exactly when the outsider's count is greater than *or equal to* the
    favourite's, so any difference is margin, not opinion.

    Measured on six of the nine fixtures pulled on 2026-09-05 that carried both
    corner markets: the handicap paid **+7.5% to +10.6%** more, every time, with
    no exception, while the *favourite's* price was identical to the last digit
    in both markets. The cause is structural rather than a mispricing to be
    hunted: the three-way carried 12.5-13.3% overround and the two-way 8.3-8.9%,
    and the whole difference sits on the outsider.
    """
    return CrossMarketGap(
        outcome="outsider covers (+0.5)",
        direct_price=handicap_outsider_price,
        synthetic_price=dutch([draw_price, outsider_price]),
    )


def range_from_ladder(
    *,
    under_low: tuple[float, float] | None,
    under_high: tuple[float, float] | None,
) -> tuple[float | None, float | None, float | None]:
    """The three range buckets implied by two rungs of the over/under ladder.

    "Liczba rzutów rożnych - przedziały" (<9 / 9-11 / 12+) is the same partition
    as under 8.5 / between / over 11.5, and this pipeline already prices that
    ladder -- so the range market can be checked against it with no model.

    Each rung is passed as **both** its prices, ``(poniżej, powyżej)``, and is
    devigged before use. That is not fastidiousness: an earlier version read
    ``1 / poniżej`` as P(under) and subtracted two such numbers, which compares
    a vigged quantity against a vigged quantity and produced a −25.6% "finding"
    on the top bucket of Inter-Napoli that was an artefact of the method. On the
    same fixture the honest figures are −7.1% / −17.8% / −6.8%, and what they
    show is not a mispriced bucket but a market carrying 11.4% overround with
    the middle bucket paying most of it.

    Returns probabilities, not prices, and ``None`` where a rung is missing
    rather than interpolating one.
    """
    p_under_low = devig(under_low)[0] if under_low else None
    p_under_high = devig(under_high)[0] if under_high else None
    middle = None
    if p_under_low is not None and p_under_high is not None:
        middle = max(0.0, p_under_high - p_under_low)
    top = None if p_under_high is None else max(0.0, 1.0 - p_under_high)
    return (p_under_low, middle, top)


def required_price(probability: float, margin: float = 1.05) -> float:
    """The price a probability needs before it is worth taking, with a margin.

    Deliberately the same shape as the coupon's bar -- ``1/p x margin`` -- so a
    reader can compare, and deliberately *not* imported from ``coupons``: a
    derived estimate has no tier, so there is no ``TIER_MARGIN`` to look up and
    pretending otherwise would give it a standing it has not earned.

    On the confident side of the gate the honest input is not the point estimate
    but ``Calibration.price_floor`` -- the lower of the two bootstrap floors,
    0.600 for corners, 0.621 for shots, 0.600 for SOT -- which puts the minimum
    price near 1.75 rather than near 1.50.
    """
    if not 0.0 < probability < 1.0:
        raise ValueError("probability must be in (0, 1)")
    return margin / probability
