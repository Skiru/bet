"""A football side's sample rescaled to a neutral opponent and today's domain.

Audit 2026-10-13 B15 (with A5; Part 6 W1, W4, W7). A side's sample is half of
the football centre (all of it on football_rating.UNRATED_MARKETS), and until
this it was the raw last ten: ten corners earned against the league's worst
defence counted like ten earned against its best, and a sample earned in a
weaker league counted 1:1 against a European opponent (the Aktobe pattern,
football_rating).

Each observation of side A, earned against O_k, is read as the rating reads a
match (Maher 1982; RatingBook.expected):

    x' = x / def(O_k)^c * exp(g),   g = lf(A, B) - lf(A, O_k)

with `def` the opponent's defence ratio in the rating book SHEET holds, `c`
CROSS_RATIO_POWER when (A, O_k) is not a LINKED pair (else 1), `lf(X, Y)`
the book's log strength gap on X's rate for a LINKED_BY_STRENGTH pair (0
otherwise) and B today's opponent. A match total is the sum of the two
corrected halves: A's own count as above and the opponent's,
``against / att(O_k)^c * exp(-g)`` - the split comes from the side's
``*_for`` sample (Observation.against, B13).

Goals stay raw (CORRECTED_METRICS). An observation stays raw when its
opponent is unknown (no opponent_id: a
sample written before 2026-10-13), not rated on the metric
(< MIN_TEAM_MATCHES), when the market has no rating metric, or when a total
has no for / against split.

Behind epochs.SAMPLE_OPPONENT_CORRECTION_FROM_UTC (None: nothing calls this).
Measured: docs/sofa/evidence/sample_opponent_correction_2026-10-13.md.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from bet.sofa.contracts import MetricSample, Observation
from bet.sofa.football_rating import (
    CROSS_RATIO_POWER,
    LINKED,
    LINKED_BY_STRENGTH,
    MIN_TEAM_MATCHES,
    RatingBook,
    base_metric,
)
from bet.sofa.players import is_player_metric

NOTE = "SAMPLE_OPPONENT_CORRECTED"
# The rating metrics the correction was measured on (Test H). Goals stay raw:
# SAMPLES reads a league's goals from the same competition only, the rating
# already carries half their centre, and they were not measured.
CORRECTED_METRICS = frozenset({
    "corners_for", "corners_1h_for", "corners_2h_for",
    "shots_for", "shots_1h_for", "shots_on_target_for", "shots_on_target_1h_for",
    "fouls_for", "fouls_1h_for", "cards_points_for", "offsides_for",
})


def corrected_metric(market: str) -> str | None:
    """The rating metric a `market`'s sample is corrected on, or None when
    it stays raw (goals, a player market, no rating metric). The one rule
    SHEET (SampleCorrector.correct) and the cache replay
    (calibrate_from_cache --opponent-correction) both read."""
    metric = base_metric(market)
    if (metric is None or metric not in CORRECTED_METRICS
            or is_player_metric(market)):
        return None
    return metric


@dataclass
class SampleCorrector:
    """The correction of one build, on the rating book SHEET holds."""

    book: RatingBook
    _gaps: dict[tuple[int, int, str], tuple[bool, float]] = field(
        default_factory=dict, repr=False)

    def _gap(self, team: int, opponent: int, metric: str) -> tuple[bool, float]:
        """(LINKED?, log strength factor on `team`'s rate against `opponent`)."""
        key = (team, opponent, metric)
        hit = self._gaps.get(key)
        if hit is None:
            status, lf = self.book.link(team, opponent, metric)
            hit = (status == LINKED, lf if status == LINKED_BY_STRENGTH else 0.0)
            self._gaps[key] = hit
        return hit

    def factors(
        self, team: int, opponent: int, today_opponent: int | None, metric: str
    ) -> tuple[float, float] | None:
        """(multiplier of the side's own count, of the opponent's count) for a
        match `team` played against `opponent`; None if the opponent is not
        rated on the metric."""
        rated = self.book.teams.get((opponent, metric))
        if rated is None or rated.n < MIN_TEAM_MATCHES:
            return None
        linked, lf_k = self._gap(team, opponent, metric)
        lf_0 = (self._gap(team, today_opponent, metric)[1]
                if today_opponent is not None else 0.0)
        power = 1.0 if linked else CROSS_RATIO_POWER
        g = lf_0 - lf_k
        return (math.exp(g) / rated.defence ** power,
                math.exp(-g) / rated.attack ** power)

    def correct(
        self,
        observations: Sequence[Observation],
        market: str,
        team: int,
        today_opponent: int | None,
        split: Mapping[tuple[int, int], Observation] | None = None,
    ) -> list[Observation]:
        """The observations of `team`'s sample for `market`, corrected where
        they can be. `split` (split_index): the ``*_for`` observations by
        (event, opponent), needed for a match total."""
        metric = corrected_metric(market)
        if metric is None:
            return list(observations)
        total = market.endswith("_total")
        out: list[Observation] = []
        for o in observations:
            if o.opponent_id is None:
                out.append(o)
                continue
            f = self.factors(team, o.opponent_id, today_opponent, metric)
            if f is None:
                out.append(o)
                continue
            if not total:
                out.append(o.model_copy(update={"value": o.value * f[0]}))
                continue
            own = (split or {}).get((o.sofascore_event_id, o.opponent_id))
            if (own is None or own.against is None
                    or abs(own.value + own.against - o.value) > 1e-9):
                out.append(o)
                continue
            out.append(o.model_copy(
                update={"value": own.value * f[0] + own.against * f[1]}))
        return out


def split_index(
    sample: MetricSample | None,
) -> dict[tuple[int, int], Observation]:
    """A ``*_for`` sample's observations by (event, opponent): the for /
    against split of a total's observation of the same match and side."""
    out: dict[tuple[int, int], Observation] = {}
    if sample is None:
        return out
    for lst in (sample.side_a, sample.side_b, sample.h2h):
        for o in lst:
            if o.opponent_id is not None and o.against is not None:
                out.setdefault((o.sofascore_event_id, o.opponent_id), o)
    return out


def correct_total(
    corrector: SampleCorrector,
    metrics: Mapping[str, MetricSample],
    market: str,
    home: int,
    away: int,
) -> list[list[Observation]]:
    """A total's three pools (side_a, side_b, h2h) corrected, in SHEET's
    order. An h2h match is read from the side its opponent_id says it was
    recorded for."""
    sample = metrics[market]
    fm = for_market(market)
    split = split_index(metrics.get(fm) if fm else None)
    side_a = corrector.correct(sample.side_a, market, home, away, split)
    side_b = corrector.correct(sample.side_b, market, away, home, split)
    h2h: list[Observation] = []
    for o in sample.h2h:
        team, other = ((home, away) if o.opponent_id == away
                       else (away, home) if o.opponent_id == home
                       else (None, None))
        h2h.extend(corrector.correct([o], market, team, other, split)
                   if team is not None else [o])
    return [side_a, side_b, h2h]


def for_market(market: str) -> str | None:
    """The side metric whose observations split a total (``corners_total`` ->
    ``corners_for``); None for any other market."""
    if not market.endswith("_total"):
        return None
    return market[: -len("_total")] + "_for"


def gate_values(row: Mapping[str, object], raw: list[float]) -> list[float]:
    """What CONFIDENCE's shape gates and MODEL_ABOVE_OWN_SAMPLE read: the
    sample SHEET priced from (`corrected_sample`, written only under
    epochs.SAMPLE_OPPONENT_CORRECTION), else the raw observations (W7)."""
    corrected = row.get("corrected_sample")
    if isinstance(corrected, list) and len(corrected) == len(raw):
        return [float(v) for v in corrected]
    return raw


def mode_values(row: Mapping[str, object], values: list[float]) -> list[float]:
    """What MODE_LOSES reads: a corrected sample is continuous (every value
    distinct, so statistics.mode would return its first one), so its values
    are rounded to the nearest count first; a raw sample is read as it is."""
    corrected = row.get("corrected_sample")
    if isinstance(corrected, list) and len(corrected) == len(values):
        return [float(math.floor(v + 0.5)) for v in values]
    return values
