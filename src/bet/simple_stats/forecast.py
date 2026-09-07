"""What we expect to happen, before anything about what it is priced at.

The sheet has always answered "what is P(over 21.5 fouls)". It has never
answered "how many fouls do you expect", and those are different claims with
different audiences. A probability can only be checked in aggregate, over
hundreds of rows, which is a thing this repository does in ``backtest_slate.py``
and an operator cannot do at the screen. A point forecast with an interval can
be checked against one scoreboard, and it is the form in which a read is
actually held: *twenty-four fouls, give or take four, and here is what that is
built out of.*

So this module is the sheet turned the other way round. One card per
(fixture, market, subject), carrying:

* **the expectation** -- the centre the count model prices from, with a
  predictive interval, in the units the market settles in;
* **the attribution** -- what that centre is made of: this sample at this
  weight, this league's own measured baseline at the rest, and which way the
  referee moved it;
* **the drivers** -- h2h, recent form, the official -- each labelled with what
  it has been *measured* to be worth, which for most of them is "the sample
  already knows this";
* **the reliability** -- this market's own error over the fixtures in ``runs/``
  that have been played, so a card for fouls (MAE 4.33 against 4.67 for a
  league constant, 568 fixtures) does not read like a card for first-half goals
  (MAE 0.856 against 0.852 -- the constant wins);
* **the ladder** -- every rung with its probability, and the price *last*.

Why the drivers are labelled and not summed. Asked raw, against the actual foul
count, the pooled sample scores +0.459, the referee's own rate +0.317, the h2h
mean +0.291 and recent form +0.329 -- four reasons, all real. Asked against the
*residual* the league-aware forecast leaves, h2h scores +0.000 (CI -0.102 to
+0.106), recency +0.015 and the referee +0.144 (CI -0.004 to +0.292). They are
not four reasons. They are four descriptions of one fact -- a high-foul pairing
in a high-foul league -- and adding them up counts that fact four times. This
repository has paid for that error twice already: ``p_low`` realising 23 points
above its own claim, and the cross-provider corroboration effect turning out to
be an artifact of which rows have small samples. A card that says "expect 24.4
fouls, and the referee and the h2h both agree" is honest. A card that says
"expect 24.4 fouls *because* the referee, *and* because the h2h, *and* because
the form" is a card that will talk itself into 28.

The one measured exception is the referee on card markets, and it is an
exception about *level*, not about confidence: blended in, it does nothing for
MAE (-0.021, CI [-0.101, +0.057]) and halves the bias, -0.37 to -0.12. It moves
where we think the centre is and does not make any single match more
predictable. ``analyze._blend_referee`` applies it; this module reports it.

Nothing here computes a threshold, a stake or an edge. The card is what we
think will happen; whether that is worth a price is a separate question asked
in ``coupons.py`` and answered by the operator.
"""
from __future__ import annotations

import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from bet.simple_stats.analyze import (
    MAX_COUNT_MODEL_PROBABILITY,
    SHRINKAGE_K,
    drifted_markets,
    market_reliability,
    scope_values,
    shrinkage_target,
    tennis_match_format,
)
from bet.simple_stats.calibration import honest_probability
from bet.simple_stats.contracts import (
    EventDossierV1,
    StatsSheetRow,
    StatsSheetV1,
)
from bet.simple_stats.providers import ProviderValue

# The predictive interval printed on every card. 80% rather than 95% on
# purpose: at 95% a fouls card reads "24.4, somewhere between 16 and 33", which
# is true, useless, and trains the reader to ignore the interval. 80% is the
# band a reader can hold two of in their head and still tell two fixtures
# apart, and it is labelled as 80% wherever it is rendered.
INTERVAL_MASS = 0.80
_INTERVAL_Z = 1.2816

# How the measured error becomes a grade. Both thresholds are relative to the
# market's own spread, because an absolute one would grade every low-count
# market as excellent and every high-count market as broken: 0.4 of a card is a
# different claim from 0.4 of a foul.
#
# ``skill`` is ``1 - mae/mae_baseline``, so it is already scale-free. The floor
# is set at 2% rather than 0% because the difference between a sample that ties
# a constant and one that loses to it by a whisker is not a difference an
# operator should act on -- both mean "the league average is doing the work".
_SKILL_FLOOR = 0.02
_BIAS_CEILING_IN_SD = 0.25

# Below this the forecast is not merely uninformative, it is *harmful*: the
# fixture-specific sample makes the answer worse than the scope's own average.
# Set at -2% for the same reason the floor is +2% -- a tie is a tie -- and it
# exists because six scopes are past it: every tennis market this pipeline
# prices -- games_won@BO5 -2.5%, total_sets@BO3 -6.2%, total_games@BO3 -8.8%,
# games_won@BO3 -12.4%, total_sets@BO5 -59.9% -- plus red_cards_total at
# -47.0%, which forecasts 0.35 red cards against an actual 0.16. The tennis
# markets are the ones the 2026-09-07 file led with, and the analyst had to
# hand-write four vetoes to keep them off the coupon. A grade states it once
# instead.
_WORSE_THAN_AVERAGE = -0.02


@dataclass(frozen=True)
class Driver:
    """One candidate reason, with what it has been measured to be worth.

    ``status`` is the whole point of the type. ``PRICES_IN`` means the sample
    already carries this and it may be shown as agreement but never counted as
    support; ``SHARPENS`` means it measurably reduced the forecast's error and
    is genuine independent evidence; ``SHIFTS`` means it measurably corrects the
    level without sharpening anything; ``UNMEASURED`` means nobody has checked,
    which is not the same as either.
    """

    name: str
    value: float | None
    reference: float | None
    status: str
    detail: str
    observations: int | None = None

    @property
    def delta(self) -> float | None:
        """How far this driver sits from what it should be compared against."""
        if self.value is None or self.reference is None:
            return None
        return self.value - self.reference

    @property
    def agrees(self) -> bool | None:
        """Whether the driver points the same way as the forecast's own lean."""
        delta = self.delta
        return None if delta is None else delta > 0


@dataclass(frozen=True)
class Rung:
    """One line and side, with its probability and -- last -- its price."""

    line: float
    direction: str
    p_central: float | None
    p_low: float | None
    hits: int
    sample_size: int
    price: float | None = None
    min_odds: float | None = None
    # ``p_central`` after this market's own settled record at this claim; see
    # calibration.honest_probability. It is the number the day's reads are
    # ranked by, and it may only ever be lower than or equal to p_central.
    p_honest: float | None = None
    honest_note: str | None = None

    @property
    def at_ceiling(self) -> bool:
        """Whether this rung is the count model's clamp rather than a reading.

        ``analyze._clamp_count_probability`` caps a count model at
        ``MAX_COUNT_MODEL_PROBABILITY``, so a line the sample never came near
        reports exactly that number for every such line and says nothing about
        which of them is more likely. It is a fact about our own arithmetic --
        not about a price -- and it is the reason a probability ranking fills
        with "under 8.5 tackles, 95%" restated twenty times.

        Reported rather than removed: the rung stays in the JSON and in the
        fixture's own ladder, marked. What it does not do is represent its card
        at the top of the file when the card has something informative to say.
        """
        return (
            self.p_central is not None
            and self.p_central >= MAX_COUNT_MODEL_PROBABILITY
        )

    @property
    def claim_correction(self) -> float | None:
        """How many points this market's record took off the claim, if any."""
        if self.p_central is None or self.p_honest is None:
            return None
        return self.p_honest - self.p_central

    @property
    def price_gap_pct(self) -> float | None:
        """How far the posted price sits from the threshold, in percent.

        Signed so positive means the book pays more than the bar asks. Reported
        rather than gated: the operator has said plainly that a rung a few
        percent under its threshold is still a bet he may want, and a card that
        deleted it would be making that call for him.
        """
        if self.price is None or not self.min_odds:
            return None
        return (self.price / self.min_odds - 1.0) * 100.0


@dataclass(frozen=True)
class ForecastCard:
    """What we expect in one market of one fixture, and what it is built from."""

    event_id: str
    sport: str
    market: str
    subject: str | None
    expected: float
    spread: float
    sample_mean: float
    sample_median: float | None
    sample_size: int
    sample_min: float | None
    sample_max: float | None
    baseline: float | None
    baseline_source: str
    weight: float
    reliability: Mapping[str, object] | None
    grade: str
    grade_reason: str
    # Set only where the sample has been measured to drift against settlement.
    # Carried next to the grade rather than folded into it; see ``_drift_note``.
    drift: Mapping[str, object] | None = None
    drift_note: str | None = None
    drivers: list[Driver] = field(default_factory=list)
    rungs: list[Rung] = field(default_factory=list)
    centre_note: str | None = None
    scope_excluded: Mapping[str, int] = field(default_factory=dict)

    @property
    def interval(self) -> tuple[float, float]:
        """The 80% predictive band, floored at zero -- counts are not negative."""
        half = _INTERVAL_Z * self.spread
        return (max(0.0, self.expected - half), self.expected + half)

    @property
    def reliability_scope(self) -> str:
        """The key this card's error was measured under."""
        return self.market

    def headline(self) -> str:
        """One line an operator can read without the rest of the card."""
        low, high = self.interval
        return (
            f"{self.market}{'' if self.subject is None else ' · ' + self.subject}: "
            f"expected {self.expected:.2f} "
            f"(80% {low:.1f}-{high:.1f}, n={self.sample_size}, {self.grade})"
        )

    def ranked_rungs(
        self,
        limit: int | None = None,
        *,
        informative_only: bool = False,
        direction: str | None = None,
    ) -> list[Rung]:
        """Every rung, most likely first, on the corrected probability.

        The opposite ordering to ``best_rungs`` and the one the operator asked
        for: "which statistic, in which direction, at which value is most
        likely". Ties are broken toward the wider claim -- more evidence, then
        the higher line -- so the top of a ladder outranks the fourth
        restatement of the same read one line down.

        ``direction`` narrows to one side. It exists because the two sides of a
        prop are not comparable as reads: an UNDER on a count that averages 0.4
        is near-certain by arithmetic and beats every OVER on the board, so a
        single ranking is always an UNDER ranking. Superbet posts football props
        **OVER-only** -- on the 2026-09-07 offer, 4,690 prop rows on the stats
        sheet came back ``OFFERED`` and not one of them was an UNDER -- so the
        side a single ranking buries is the only side that exists as a market.
        """
        scored = [
            r
            for r in self.rungs
            if r.p_honest is not None
            and not (informative_only and r.at_ceiling)
            and (direction is None or r.direction == direction)
        ]
        scored.sort(key=lambda r: (-(r.p_honest or 0.0), -r.sample_size, -r.line))
        return scored if limit is None else scored[:limit]

    def best_rungs(self, limit: int = 4) -> list[Rung]:
        """The rungs nearest even money, which are the ones that carry a claim.

        A rung at 0.97 is arithmetic about where the sample's maximum sits, not
        a read on the fixture, and it is where "certainty for free" comes from.
        Ordered by distance from 0.5 so a reader sees the informative end of the
        ladder first, which is the opposite of ordering by confidence.
        """
        scored = [r for r in self.rungs if r.p_central is not None]
        scored.sort(key=lambda r: abs((r.p_central or 0.5) - 0.5))
        return scored[:limit]


def _entry_for(
    reliability: Mapping[str, Mapping[str, object]],
    scope: str,
    market: str,
    sport: str,
) -> tuple[Mapping[str, object] | None, str | None]:
    """``(entry, the scope it was borrowed from)`` for one card.

    An exact hit borrows nothing. A tennis market with no entry for *this*
    format falls back to the other one and says so, because silence is the
    worst of the three answers available: ``total_games@BO5`` sits just under
    the 25-fixture floor, which is exactly a US Open men's final, and reporting
    that market as never-checked hides that its best-of-three twin runs 18.3
    points hot on its confident rows and that ``games_won@BO5`` runs 22.9.

    Where more than one format could be borrowed from, the *worse* one is
    taken. A format we could not measure must not inherit the kinder reading of
    a format we could.
    """
    exact = reliability.get(scope)
    if exact is not None:
        return exact, None
    if sport != "tennis":
        return reliability.get(market), None
    others = {
        key: entry
        for key, entry in reliability.items()
        if key.startswith(f"{market}@")
    }
    if not others:
        return None, None
    worst = min(others, key=lambda k: float(others[k].get("skill") or 0.0))
    return others[worst], worst


def _grade(
    reliability: Mapping[str, object] | None,
    *,
    borrowed_from: str | None = None,
) -> tuple[str, str]:
    """``(grade, why)`` from a market's measured error.

    Five grades, and the three that matter are the negative ones.
    ``OVERCONFIDENT`` says the level is fine and the *probability* is not: the
    rows on this market claiming 75% or more have measurably realised less,
    which is the number the bar is computed from and therefore the one with
    money on it. It is checked before the level grades because a market can
    have a perfectly good centre and a hot tail at once -- ``shots_for``
    scores +4.3% over 551 settled fixtures and its rows claiming 70% or more
    have realised 71.2% against a claimed 77.9%, over 527 fixtures.

    ``LEVEL_ONLY`` says the sample did not beat the scope's own mean, so the
    *level* of the forecast is worth something and the way it separates one
    rung from the next is a fitted distribution rather than evidence.
    ``BIASED`` says the forecast is systematically off in a known direction,
    which is a thing to correct for by hand and not a thing to bet through.

    ``skill`` is read only where the measurement says it is comparable. A
    market that happens well under once a match has an MAE dominated by its
    base rate -- ``player_offsides`` averages 0.13 and scores +24.2% because
    predicting roughly nothing for everybody is close to right without
    discriminating between anybody -- so for those the level grades are skipped
    and the calibration is the whole verdict.
    """
    if not reliability:
        return "UNMEASURED", "this market has never been settled against a result"
    prefix = (
        ""
        if borrowed_from is None
        else f"this format has too few settled fixtures to measure, so the "
        f"figures below are {borrowed_from}'s and are read as a floor on what "
        f"to expect here, not as a measurement of it: "
    )
    skill = float(reliability.get("skill") or 0.0)
    bias = float(reliability.get("bias") or 0.0)
    sd = float(reliability.get("actual_sd") or 0.0)
    fixtures = int(reliability.get("fixtures") or 0)
    mae = float(reliability.get("mae") or 0.0)
    constant = float(reliability.get("mae_constant") or 0.0)
    comparable = bool(reliability.get("skill_comparable", True))
    hot_above = reliability.get("hot_above")
    hot = reliability.get("hot_above_detail")
    hot_sentence = ""
    if hot_above is not None and isinstance(hot, Mapping):
        hot_sentence = (
            f"rows on this market claiming {float(hot_above):.0%} or more have "
            f"realised {float(hot['realised']):.1%} against a claimed "
            f"{float(hot['claimed']):.1%} over {int(hot['fixtures'])} settled "
            f"fixtures ({float(hot['gap']):+.1%}, 95% interval from "
            f"{float(hot['gap_ci_low']):+.1%}, resampled by fixture)"
        )
    # The two level grades run *before* the confidence grade, and the reason
    # they have to is ``games_won@BO3``. It is hot above 0.55 and its skill is
    # -12.4% -- the worst on the tennis board, six times past this threshold --
    # and while OVERCONFIDENT returned first it was the only thing said about
    # that market. OVERCONFIDENT's own text asserts "the level is not the
    # problem here", so on a market that loses to its own constant the grade
    # was stating the opposite of the finding, and the day's census (which
    # counts by grade) reported one tennis market as worse than average when
    # every one of them is.
    #
    # Nothing is lost by the reorder: the hot tail is carried into whichever
    # grade wins, and the *number* is corrected by ``honest_probability``,
    # which reads the reliability entry directly and never consults the grade.
    # A market with an acceptable centre and a hot tail still grades
    # OVERCONFIDENT, which is the case the check was written for.
    also = f". Its confident rungs are hot as well: {hot_sentence}" if hot_sentence else ""
    if sd and abs(bias) > _BIAS_CEILING_IN_SD * sd:
        return (
            "BIASED",
            prefix + f"forecast runs {bias:+.2f} against actual over {fixtures} settled "
            f"fixtures ({abs(bias) / sd:.0%} of the market's own spread, on an "
            f"actual mean of {float(reliability.get('actual_mean') or 0):.2f}) -- "
            f"correct for it by hand before reading any rung" + also,
        )
    if skill <= _WORSE_THAN_AVERAGE:
        return (
            "WORSE_THAN_AVERAGE",
            prefix + f"over {fixtures} settled fixtures this forecast was {abs(skill):.1%} "
            f"*worse* than simply predicting the average of {float(reliability.get('actual_mean') or 0):.2f} "
            f"(MAE {mae:.2f} vs {constant:.2f}) -- the fixture-specific sample is "
            f"costing accuracy, so the average is the better read and no rung here "
            f"is evidence about this match" + also,
        )
    if hot_sentence:
        return (
            "OVERCONFIDENT",
            prefix + f"the level is not the problem here, the confidence is, and it "
            f"is only a problem above a point: {hot_sentence}. Below "
            f"{float(hot_above):.0%} the market is calibrated -- so read the "
            f"expectation, and discount the confidence only on the rungs that "
            f"claim at least that much",
        )
    if not comparable:
        # Reached only by a market whose skill is *positive* and whose bias is
        # inside the ceiling. The base-rate argument runs one way only: it
        # makes a positive skill unimpressive, because predicting roughly
        # nothing for everybody is close to right without discriminating
        # between anybody. It does not make a negative one meaningless -- you
        # cannot lose to the constant by luck, you have to predict the wrong
        # level -- which is why this check now sits *after* BIASED and
        # WORSE_THAN_AVERAGE rather than in front of them. In front, it graded
        # red_cards_total LEVEL_ONLY ("the level is worth something") for a
        # market forecasting 0.35 against an actual 0.16.
        return (
            "LEVEL_ONLY",
            prefix + f"this market happens "
            f"{float(reliability.get('actual_mean') or 0):.2f} times a match, so "
            f"its MAE is dominated by the base rate and its {skill:+.1%} skill "
            f"is not evidence that we forecast it well; the level is worth "
            f"something and the rung separation is not evidence",
        )
    if skill < _SKILL_FLOOR:
        return (
            "LEVEL_ONLY",
            prefix + f"over {fixtures} settled fixtures the sample only matched predicting "
            f"the average (MAE {mae:.2f} vs {constant:.2f}); the level is worth "
            f"something, the rung separation is a fitted distribution and not "
            f"evidence",
        )
    return (
        "MEASURED",
        prefix + f"over {fixtures} settled fixtures the sample beat predicting the average "
        f"by {skill:.1%} (MAE {mae:.2f} vs {constant:.2f}), bias {bias:+.2f}",
    )


def _drift_reconciliation(
    delta: float, reliability: Mapping[str, object] | None
) -> str:
    """Why the grade line's ``bias`` and this drift are different numbers.

    They sit on adjacent bullets and are the same error measured at two stages,
    so left unexplained they read as a contradiction. ``bias`` is signed
    forecast-minus-actual on the *shrunk* centre; ``delta`` is
    actual-minus-sample on the *raw* one. Shrinkage toward the league baseline
    pulls the centre back toward the truth, so the surviving error is the
    smaller of the two -- on ``cards_points_total`` 0.55 raw becomes 0.34 after
    shrinkage, so the baseline recovers about two-fifths and three-fifths reach
    the rung.

    Empty when there is nothing to reconcile: no reliability entry, or the two
    measurements point opposite ways, which happens on a market centred enough
    that both numbers are noise (``goals_for`` is -0.02 against +0.05) and where
    claiming a relationship would be reading a pattern into two zeroes.
    """
    if not reliability:
        return ""
    bias = reliability.get("bias")
    if not isinstance(bias, (int, float)) or not bias or not delta:
        return ""
    survives = -float(bias)
    if (survives > 0) != (delta > 0):
        return ""
    if abs(survives) >= abs(delta):
        return (
            f" The grade line's `bias` of {float(bias):+.2f} is this same error "
            f"measured after shrinkage, and it is no smaller, so the league "
            f"baseline is not absorbing any of it."
        )
    return (
        f" The grade line's `bias` of {float(bias):+.2f} is this same error "
        f"after shrinkage toward the league baseline -- so the baseline "
        f"recovers about {1.0 - abs(survives) / abs(delta):.0%} of the drift "
        f"and the remaining {abs(survives):.2f} a match is what reaches the "
        f"rung."
    )


def _drift_note(
    entry: Mapping[str, object] | None,
    reliability: Mapping[str, object] | None = None,
) -> str | None:
    """The sentence a drifted market carries *beside* its grade, or ``None``.

    Beside, not instead of, and the reason is measured rather than editorial.
    The grade answers two questions -- did the fixture's own sample beat
    predicting the average, and do the rungs realise what they claim -- and
    ``cards_points_total``, the market this exists for, is the best football
    scope in ``market_reliability.json`` on both: skill +9.7%, calibration
    error 0.0001. Grading it down would delete two true facts in order to
    report a third.

    The third is independent of both. ``BIASED`` already fires on
    ``|bias| > 0.25 * actual_sd``, which is a question about *materiality*;
    drift is ``|z| > 3``, a question about *certainty*; and the two cross.
    ``shots_total`` carries 2.8 times this market's bias and is not drifted,
    because its spread is wide enough to swallow it. ``red_cards_total`` is
    graded ``BIASED`` and is centred here. Neither test implies the other.

    And what the operator acts on is a *side*. No grade in the file names one,
    because skill and calibration are properties of a market rather than of a
    direction -- so the fact that a low sample makes every UNDER on the ladder
    look better than it is has nowhere else to be said.
    """
    if not entry:
        return None
    delta = float(entry.get("delta") or 0.0)
    side = str(entry.get("overstated_side") or "")
    other = "OVER" if side == "UNDER" else "UNDER"
    return (
        f"the sample for this market does not measure quite what the book "
        f"settles: it runs {abs(delta):.2f} a match "
        f"{'low' if delta > 0 else 'high'} against what actually happened, over "
        f"{int(entry.get('fixtures') or 0)} settled fixtures "
        f"(z={float(entry.get('z') or 0.0):+.2f}, one row per fixture) -- so "
        f"every {side} rung here is overstated and every {other} understated, "
        f"by roughly that much of a count. This is a third question from the "
        f"grade above, which is about skill and calibration and does not "
        f"include it; project memory records the cause as competition mix, not "
        f"a transcription fault, so the numbers are read correctly off matches "
        f"that are not this fixture's mix."
        + _drift_reconciliation(delta, reliability)
        + " Not corrected for anywhere in the pipeline, deliberately -- see "
        "`_why_not_a_correction` in `config/sample_drift.json`"
    )


def _bucket_values(
    metric, bucket: str, *, match_format: str | None
) -> list[ProviderValue]:
    """One scoped bucket of a metric, or an empty list.

    Scoped with the same rules the sheet used, so a driver cannot be computed
    off observations the sample itself refused -- a h2h "agreement" built out of
    a pre-season friendly the row already dropped would be worse than no
    driver at all.
    """
    raw = getattr(metric, bucket, None) or []
    kept, _ = scope_values(list(raw), match_format=match_format)
    return kept


def _drivers_for(
    market: str,
    dossier: EventDossierV1,
    subject: str | None,
    *,
    match_format: str | None,
) -> list[Driver]:
    """The candidate reasons for one market, each carrying its measured status.

    Built only for a match total. A per-team or per-player row has no h2h
    bucket it can attribute (``_team_total_rows`` never reads one, because an
    h2h value names no side) and no referee claim that is about it rather than
    about the fixture, so inventing drivers there would be filling a template.
    """
    if subject is not None:
        return []
    metric = (dossier.metrics or {}).get(market)
    if metric is None:
        return []
    measured = (market_reliability_drivers() or {}).get(market, {})
    own = _bucket_values(metric, "team_a_l10", match_format=match_format) + _bucket_values(
        metric, "team_b_l10", match_format=match_format
    )
    if not own:
        return []
    sides = statistics.fmean(v.value for v in own)
    drivers: list[Driver] = []

    h2h = _bucket_values(metric, "h2h", match_format=match_format)
    if h2h:
        entry = measured.get("h2h") or {}
        drivers.append(
            Driver(
                name="h2h",
                value=statistics.fmean(v.value for v in h2h),
                reference=sides,
                status=str(entry.get("status") or "UNMEASURED"),
                observations=len(h2h),
                detail=_driver_detail("h2h", entry),
            )
        )

    recent = [
        _recent_mean(_bucket_values(metric, bucket, match_format=match_format))
        for bucket in ("team_a_l10", "team_b_l10")
    ]
    if all(value is not None for value in recent):
        entry = measured.get("recency") or {}
        drivers.append(
            Driver(
                name="recency",
                value=statistics.fmean(v for v in recent if v is not None),
                reference=sides,
                status=str(entry.get("status") or "UNMEASURED"),
                observations=3,
                detail=_driver_detail("recency", entry),
            )
        )

    referee = dossier.referee
    rate = _referee_rate(market, referee)
    if rate is not None and referee is not None:
        entry = measured.get("referee") or {}
        drivers.append(
            Driver(
                name="referee",
                value=rate,
                reference=sides,
                status=str(entry.get("status") or "UNMEASURED"),
                observations=referee.matches,
                detail=(
                    f"{referee.name or referee.provider_referee_id} averages "
                    f"{rate:.2f}/match over {referee.matches} matches. "
                    + _driver_detail("referee", entry)
                ),
            )
        )
    return drivers


def _driver_detail(name: str, entry: Mapping[str, object]) -> str:
    """The measured sentence that goes next to a driver's number."""
    if not entry:
        return (
            f"{name} has not been measured against this market's residual -- "
            f"read it as context, not as support"
        )
    r = entry.get("partial_r")
    ci = entry.get("ci") or [None, None]
    observations = entry.get("observations")
    if entry.get("status") == "SHARPENS":
        return (
            f"measured to reduce this market's error: partial r={r:+.3f} "
            f"(95% CI {ci[0]:+.3f} to {ci[1]:+.3f}) over {observations} settled "
            f"observations -- independent evidence"
        )
    return (
        f"the sample already carries this: partial r={r:+.3f} against the "
        f"residual (95% CI {ci[0]:+.3f} to {ci[1]:+.3f}, {observations} settled "
        f"observations). Agreement here is corroboration, not extra confidence"
    )


_DRIVER_TABLE: dict | None = None


def market_reliability_drivers() -> dict:
    """``{market: {driver: {...}}}`` from ``config/market_reliability.json``.

    Cached beside the reliability scopes rather than inside them because the
    two answer different questions -- how wrong is this market, and which of
    the reasons for it are real -- and a caller usually wants one of the two.
    """
    global _DRIVER_TABLE
    if _DRIVER_TABLE is None:
        from bet.simple_stats.analyze import _MARKET_RELIABILITY_PATH, _load_json

        raw = _load_json(_MARKET_RELIABILITY_PATH).get("drivers") or {}
        _DRIVER_TABLE = raw if isinstance(raw, dict) else {}
    return _DRIVER_TABLE


def reset_forecast_caches() -> None:
    """Forget the driver table. For tests only."""
    global _DRIVER_TABLE
    _DRIVER_TABLE = None


def _recent_mean(rows: Sequence[ProviderValue], n: int = 3) -> float | None:
    """Mean of the ``n`` newest dated observations, or None when none are dated.

    Undated rows are skipped rather than treated as old: tennis-abstract stamps
    a whole tournament with its start date and ``player_*`` buckets are 28%
    dateless, so "no date" is a statement about the provider and not about when
    the match was played.
    """
    dated = sorted(
        (r for r in rows if r.match_date), key=lambda r: r.match_date or "", reverse=True
    )[:n]
    return statistics.fmean(r.value for r in dated) if dated else None


def _referee_rate(market: str, referee) -> float | None:
    """The official's own rate in this market's units, when comparable.

    Only the markets an official plausibly controls, and only above the same
    fifteen-match floor ``analyze._blend_referee`` uses -- a rate off eight
    matches has a standard error wider than the effect.
    """
    if referee is None or (getattr(referee, "matches", 0) or 0) < 15:
        return None
    if market in ("fouls_total", "fouls_1h_total", "fouls_2h_total"):
        return getattr(referee, "avg_fouls_per_match", None)
    if market in ("cards_total", "cards_1h_total", "cards_2h_total"):
        return getattr(referee, "avg_yellow_per_match", None)
    if market == "cards_points_total":
        yellows = getattr(referee, "avg_yellow_per_match", None)
        if yellows is None:
            return None
        return yellows + 2.0 * (getattr(referee, "avg_red_per_match", None) or 0.0)
    if market in ("goals_total", "goals_1h_total", "goals_2h_total"):
        return getattr(referee, "avg_goals_per_match", None)
    return None


def _subject_of(row: StatsSheetRow) -> str | None:
    """Whose number this is: a player, a team, or the match itself (None)."""
    return row.player_name or row.team_name


def build_cards(
    stats_sheet: StatsSheetV1,
    dossiers: Iterable[EventDossierV1],
    *,
    competitions: Mapping[str, str] | None = None,
    include_players: bool = True,
    min_sample: int = 3,
) -> list[ForecastCard]:
    """One card per (fixture, market, subject) the sheet has rows for.

    Pure: no clock, no network, no database. Given a sheet and its dossiers it
    returns the same cards, which is what makes a read reviewable after the
    fact against the same two files.

    ``include_players`` is **on** by default since 2026-09-07. It was off, on
    the reasoning that props measured -30.5% ROI against posted prices and that
    21,000 rows would bury the thirty that matter. Both halves of that have
    stopped being reasons. The ROI is a statement about Superbet's prices and
    this file no longer decides anything about a price -- the operator prices
    live and asked for the statistics. And burial was a property of the old
    ordering: with every rung ranked on its corrected probability the props
    that deserve the top of the list reach it and the rest sort themselves
    below, which is what the ranking is for. It costs 3,520 prop cards against
    658 team cards on the 2026-09-07 board, so the rendered file keeps a higher
    probability floor and a per-fixture cap on prop cards while the JSON keeps
    every one of them.
    """
    by_event = {d.event_id: d for d in dossiers}
    grouped: dict[tuple[str, str, str | None], list[StatsSheetRow]] = {}
    for row in stats_sheet.rows:
        if not include_players and row.player_name:
            continue
        if row.p_central is None or row.shrunk_mean is None:
            continue
        grouped.setdefault((row.event_id, row.market, _subject_of(row)), []).append(row)

    cards: list[ForecastCard] = []
    reliability = market_reliability()
    drift = drifted_markets()
    for (event_id, market, subject), rows in grouped.items():
        dossier = by_event.get(event_id)
        if dossier is None:
            continue
        sample_size = max(r.sample_size for r in rows)
        if sample_size < min_sample:
            continue
        # The centre is a *pricing* quantity computed per direction (a provider
        # conflict resolves against the side being priced), so the two sides can
        # differ by the width of one conflicted observation. The card states one
        # expectation, so it states the midpoint of the two and says nothing it
        # cannot support -- taking the OVER's centre would tilt every card the
        # same way.
        centres = [r.shrunk_mean for r in rows if r.shrunk_mean is not None]
        expected = statistics.fmean(centres)
        dispersion = statistics.fmean(
            r.dispersion for r in rows if r.dispersion is not None
        ) if any(r.dispersion is not None for r in rows) else 0.0
        spread = (dispersion**2 * (1.0 + 1.0 / sample_size)) ** 0.5 if sample_size else 0.0
        match_format = (
            tennis_match_format((competitions or {}).get(event_id))
            if dossier.sport == "tennis"
            else None
        )
        scope = market if dossier.sport == "football" else f"{market}@{match_format or 'UNKNOWN'}"
        entry, borrowed = _entry_for(reliability, scope, market, dossier.sport)
        grade, why = _grade(entry, borrowed_from=borrowed)
        baseline, source = shrinkage_target(
            market,
            rows[0].venue,
            str(getattr(getattr(dossier, "fixture_context", None), "league_id", "") or "")
            or None,
        )
        rungs = []
        for r in sorted(rows, key=lambda r: (r.line, r.direction)):
            honest, honest_note = honest_probability(r.p_central, entry)
            rungs.append(
                Rung(
                    line=r.line,
                    direction=r.direction,
                    p_central=r.p_central,
                    p_low=r.p_low,
                    hits=r.hits,
                    sample_size=r.sample_size,
                    price=(r.superbet.price if r.superbet else None),
                    p_honest=honest,
                    honest_note=honest_note,
                )
            )
        cards.append(
            ForecastCard(
                event_id=event_id,
                sport=dossier.sport,
                market=market,
                subject=subject,
                expected=expected,
                spread=spread,
                sample_mean=statistics.fmean(
                    r.mean for r in rows if r.mean is not None
                ) if any(r.mean is not None for r in rows) else expected,
                sample_median=next((r.median for r in rows if r.median is not None), None),
                sample_size=sample_size,
                sample_min=next((r.sample_min for r in rows if r.sample_min is not None), None),
                sample_max=next((r.sample_max for r in rows if r.sample_max is not None), None),
                baseline=baseline,
                baseline_source=source,
                weight=sample_size / (sample_size + SHRINKAGE_K),
                reliability=entry,
                grade=grade,
                grade_reason=why,
                # Keyed on the bare market: the audit settles football team
                # markets, so a tennis scope is simply absent and a prop is
                # never measured here at all.
                drift=drift.get(market),
                drift_note=_drift_note(drift.get(market), entry),
                drivers=_drivers_for(
                    market, dossier, subject, match_format=match_format
                ),
                rungs=rungs,
                centre_note=next((r.centre_note for r in rows if r.centre_note), None),
                scope_excluded=next(
                    (r.sample_excluded for r in rows if r.sample_excluded), {}
                ),
            )
        )
    cards.sort(key=lambda c: (c.event_id, c.market, c.subject or ""))
    return cards
