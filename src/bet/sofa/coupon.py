"""COUPON — selection (PLAN §6.8).

Nothing here re-computes a probability or a threshold. It picks among rows the
engine already priced, and it says out loud why every VALUE row it did not pick
was dropped.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from bet.sofa.confidence import MAX_DISAGREEMENT, Calibration
from bet.sofa.contracts import (
    Coupon,
    CouponRow,
    Fixture,
    FixtureOffer,
    SheetRow,
    Veto,
)
from bet.sofa.market_mapper import get_mechanism_family
from bet.sofa.veto import match_vetoes

# The day's row cap. `None` means no cap, which is the default: a cap that
# binds does not trim the worst rows, it trims whichever rows sort last, and
# on 2026-09-18 it dropped 738 of 920 VALUE rows across 131 fixtures that the
# sheet had already passed. Callers that want a portfolio-sized coupon pass
# one explicitly.
MAX_SINGLES: int | None = None
MAX_PER_FIXTURE = 3
MAX_PER_MECHANISM_FAMILY_PER_FIXTURE = 1
MIN_ODDS_FLOOR = 1.25

# How old the freshest match behind a row may be.
#
# The price had a 45-minute limit from the start; the sample had none at all,
# and the two are the same kind of claim — "this number still describes the
# thing I am betting on". Measured on 2026-09-21: the highest-surplus single
# of the day (+2.741, at odds of 5.90) rested on a sample whose most recent
# match was 105 days old, and one row reached the coupon on a sample last
# updated 193 days earlier. This is not incidental. A sample that has stopped
# tracking a player disagrees with the current price more often than a fresh
# one does, and `coupon.py` ranks on exactly that disagreement, so staleness
# is actively selected for.
#
# 60 days is deliberately looser than the 180-day builder guard is tight: it
# has to survive an off-season gap in a minor league without emptying the
# board, while still refusing a sample that predates a player's current form.
# A row with no usable date is kept — unknown is not the same as stale, and
# refusing it would silently drop whole markets whose observations carry no
# match date.
MAX_SAMPLE_AGE_DAYS = 60


@dataclass(frozen=True)
class DroppedRow:
    """A VALUE row that did not make the coupon, and the reason it did not.

    L19/L25/A4: a row that falls out in silence is indistinguishable from a row
    that was never generated, and the operator needs to tell those apart.
    """

    row: SheetRow
    reason: str
    detail: str = ""


@dataclass(frozen=True)
class CouponResult:
    coupon: Coupon
    dropped: list[DroppedRow]


def build_coupon(
    sheet_rows: list[SheetRow],
    fixtures: list[Fixture],
    offers: list[FixtureOffer],
    vetoes: list[Veto],
    current_time: datetime,
    min_kickoff: datetime,
    max_price_age: timedelta,
    min_odds_floor: float = MIN_ODDS_FLOOR,
    max_singles: int | None = MAX_SINGLES,
    max_sample_age_days: int = MAX_SAMPLE_AGE_DAYS,
    calibration: Calibration | None = None,
) -> CouponResult:
    """Select singles from VALUE rows, reporting every exclusion."""
    fixtures_by_id = {f.sofascore_event_id: f for f in fixtures}

    fetched_at_by_key: dict[tuple[int, str, str, float, str], datetime] = {}
    for offer in offers:
        for rung in offer.rungs:
            if rung.over_odds is not None:
                fetched_at_by_key[
                    (
                        offer.sofascore_event_id,
                        rung.market,
                        rung.subject,
                        rung.line,
                        "OVER",
                    )
                ] = rung.fetched_at_utc
            if rung.under_odds is not None:
                fetched_at_by_key[
                    (
                        offer.sofascore_event_id,
                        rung.market,
                        rung.subject,
                        rung.line,
                        "UNDER",
                    )
                ] = rung.fetched_at_utc

    candidates: list[tuple[SheetRow, Fixture]] = []
    dropped: list[DroppedRow] = []

    for row in sheet_rows:
        if row.verdict != "VALUE":
            continue

        fixture = fixtures_by_id.get(row.sofascore_event_id)
        if not fixture:
            dropped.append(DroppedRow(row, "NO_FIXTURE"))
            continue

        # L19: a finished or imminent match must not top the sheet.
        #
        # Superbet's clock, not Sofascore's (F26). Superbet is who accepts the
        # bet, and its clock is what decides whether the market is open. For
        # ITF tournaments Sofascore's kickoff runs 7-9 h late — a finished
        # match looks upcoming — and on 2026-09-18 six fixtures would have
        # passed this gate with the result already known. They were saved only
        # by the bookmaker delisting them, which is protection by accident:
        # it does nothing for a match being played live and still priced.
        # The most conservative available clock is the right one here.
        effective_kickoff = min(
            [t for t in (fixture.kickoff_utc, fixture.superbet_kickoff_utc) if t]
        )
        if effective_kickoff <= min_kickoff:
            dropped.append(
                DroppedRow(
                    row,
                    "KICKOFF_TOO_SOON",
                    f"kickoff {effective_kickoff.isoformat()} is not after "
                    f"{min_kickoff.isoformat()}"
                    + (
                        ""
                        if not fixture.kickoff_disagreement_h
                        else f" (sources disagree by "
                        f"{fixture.kickoff_disagreement_h:.1f} h)"
                    ),
                )
            )
            continue

        if row.offered_odds is None or row.offered_odds < min_odds_floor:
            dropped.append(
                DroppedRow(
                    row,
                    "ODDS_TOO_LOW",
                    f"offered {row.offered_odds} < {min_odds_floor}",
                )
            )
            continue

        matched_vetoes = match_vetoes(row, vetoes)
        if matched_vetoes:
            dropped.append(DroppedRow(row, "VETOED", matched_vetoes[0].reason))
            continue

        # A4/L25: a price read this morning is not the price tonight.
        key = (row.sofascore_event_id, row.market, row.subject, row.line, row.direction)
        fetched_at = fetched_at_by_key.get(key)
        if fetched_at is None:
            dropped.append(
                DroppedRow(row, "STALE_PRICE", "no fetched_at for this rung")
            )
            continue
        age = current_time - fetched_at
        if age > max_price_age:
            dropped.append(
                DroppedRow(
                    row,
                    "STALE_PRICE",
                    f"price is {age.total_seconds() / 60:.0f} min old, limit "
                    f"{max_price_age.total_seconds() / 60:.0f} min",
                )
            )
            continue

        # How far the model sits ABOVE the devigged price.
        #
        # This gate existed only on the staked path until 2026-09-21, so the
        # singles file — the one that is NOT staked — was the more permissive
        # of the two products while reading the same sheet and the same
        # samples. Measured on 6,187 rows carrying a real price
        # (confidence.py:37-51):
        #
        #     model - price     n     model says   realised
        #     +0.10-0.15      441       0.609        0.444
        #     +0.20-0.30      255       0.677        0.400
        #     +0.30 and up    328       0.800        0.451
        #
        # Past +0.10 the realised rate drops BELOW a coin flip while the
        # claim keeps climbing. And `surplus`, which this stage sorts on,
        # grows with exactly that gap — so the selector concentrates in the
        # measured-negative region by construction. On 2026-09-21 all 22
        # tennis singles sat above +0.177, six of them above +0.30.
        if row.market_p is not None:
            disagreement = row.p_central - row.market_p
            if disagreement > MAX_DISAGREEMENT:
                dropped.append(
                    DroppedRow(
                        row,
                        "DISAGREES_WITH_PRICE",
                        f"model {row.p_central:.3f} is {disagreement:+.3f} "
                        f"above the devigged price {row.market_p:.3f}, "
                        f"limit {MAX_DISAGREEMENT:.2f}",
                    )
                )
                continue

        # A row may not claim more than its market has ever been observed to
        # deliver.
        #
        # CONFIDENCE has refused this since 2026-09-21; the coupon did not,
        # and the two paths disagreeing about the same measured fact is how a
        # market ends up banned from one and dominant in the other.
        # `games_won_for` has 9,286 settled rows and no bucket above 0.825 —
        # its best measured bucket realises 0.756 — yet 7 coupon rows that day
        # carried p_central 0.900. That is not an optimistic estimate, it is a
        # claim about a region the data refuses to describe.
        #
        # Only markets that HAVE a curve are gated. One with no curve at all
        # is unmeasured rather than contradicted, and falls to the other
        # gates.
        if calibration is not None:
            ceiling = calibration.measured_ceiling(row.market)
            if ceiling is not None and row.p_central >= ceiling:
                dropped.append(
                    DroppedRow(
                        row,
                        "ABOVE_MEASURED_CEILING",
                        f"p_central {row.p_central:.3f} is at or above "
                        f"{row.market}'s measured ceiling of {ceiling:.3f}",
                    )
                )
                continue

        # The same question as the price gate, asked of the evidence.
        if (
            row.sample_newest_days is not None
            and row.sample_newest_days > max_sample_age_days
        ):
            dropped.append(
                DroppedRow(
                    row,
                    "STALE_SAMPLE",
                    f"newest observation is {row.sample_newest_days} days old, "
                    f"limit {max_sample_age_days}",
                )
            )
            continue

        candidates.append((row, fixture))

    # L18: within a family the slot goes to the biggest price advantage, not to
    # the biggest probability gap. A row that does not clear the bar must never
    # evict one that does.
    #
    # F36: that advantage is measured *relatively*. The absolute surplus,
    # offered - margin/p_bar, carries a 1/p term, so at equal opportunity
    # quality a long shot scores many times higher: across one day's 920 VALUE
    # rows the median surplus fell 79x from the lowest p band to the highest,
    # while the relative figure fell only 11x. The rest was scale. Ranking on
    # it made the coupon a longshot scanner — median p_bar 0.129, against 0.225
    # on this key — which matters because p is overstated in precisely that
    # tail. Dividing removes the scale so a row at p=0.55 competes on level
    # terms with one at p=0.08.
    def _price_advantage(pair: tuple[SheetRow, Fixture]) -> float:
        row = pair[0]
        if row.surplus is None or not row.required_odds:
            return 0.0
        return row.surplus / row.required_odds

    candidates.sort(key=_price_advantage, reverse=True)

    # Breadth before depth. Ranking rows globally and cutting at a cap means a
    # fixture's second and third rows outrank another fixture's *only* row, so
    # the cap removes whole matches while leaving three rows on one of them.
    # Ordering by (how many rows this fixture already has, rank) makes every
    # fixture's best row compete before any fixture's second, so a cap — if
    # one is set at all — trims depth and never breadth.
    depth_of: dict[int, int] = {}
    ranked: list[tuple[int, float, SheetRow, Fixture]] = []
    for row, fixture in candidates:
        fid = row.sofascore_event_id
        depth = depth_of.get(fid, 0)
        depth_of[fid] = depth + 1
        ranked.append((depth, -_price_advantage((row, fixture)), row, fixture))
    ranked.sort(key=lambda item: (item[0], item[1]))
    ordered = [(row, fixture) for _, _, row, fixture in ranked]

    selected: list[CouponRow] = []
    per_fixture: dict[int, int] = {}
    families_per_fixture: dict[int, dict[str, int]] = {}

    for row, fixture in ordered:
        fid = row.sofascore_event_id

        if max_singles is not None and len(selected) >= max_singles:
            dropped.append(
                DroppedRow(row, "MAX_SINGLES", f"cap {max_singles} reached")
            )
            continue

        if per_fixture.get(fid, 0) >= MAX_PER_FIXTURE:
            dropped.append(
                DroppedRow(row, "MAX_PER_FIXTURE", f"cap {MAX_PER_FIXTURE} reached")
            )
            continue

        family = get_mechanism_family(row.market)
        families = families_per_fixture.setdefault(fid, {})
        # The constant is read, not decorative. It used to be defined and never
        # referenced, with "one" hardcoded in `if family in families` — so
        # changing it did nothing while looking as though it would (F31).
        if families.get(family, 0) >= MAX_PER_MECHANISM_FAMILY_PER_FIXTURE:
            dropped.append(
                DroppedRow(
                    row,
                    "FAMILY_SLOT_TAKEN",
                    f"family '{family}' already has "
                    f"{MAX_PER_MECHANISM_FAMILY_PER_FIXTURE} row(s) with more "
                    f"surplus",
                )
            )
            continue

        # An explicit refusal, not an assert. A VALUE row with no surplus would
        # sort as 0.0, pass every gate, and then bring down the whole COUPON
        # stage here — and asserts vanish under -O, so the guard was
        # conditional on how the process was started. Every other exclusion in
        # this stage says why; so does this one (F31).
        if row.offered_odds is None:
            dropped.append(DroppedRow(row, "NO_ODDS", "VALUE row carries no price"))
            continue
        if row.surplus is None:
            dropped.append(
                DroppedRow(row, "NO_SURPLUS", "VALUE row carries no surplus")
            )
            continue
        selected.append(
            CouponRow(
                sofascore_event_id=row.sofascore_event_id,
                match_name=f"{fixture.home_name} - {fixture.away_name}",
                kickoff_utc=fixture.kickoff_utc,
                sport=row.sport,
                market=row.market,
                subject=row.subject,
                line=row.line,
                direction=row.direction,
                sample_size=row.sample_size,
                centre=row.centre,
                p_central=row.p_central,
                market_p=row.market_p,
                calibration_correction=row.calibration_correction,
                sample_newest_days=row.sample_newest_days,
                p_bar=row.p_bar,
                offered_odds=row.offered_odds,
                required_odds=row.required_odds,
                edge=row.edge,
                surplus=row.surplus,
            )
        )

        per_fixture[fid] = per_fixture.get(fid, 0) + 1
        families[family] = families.get(family, 0) + 1

    return CouponResult(
        coupon=Coupon(created_at_utc=current_time, singles=selected),
        dropped=dropped,
    )
