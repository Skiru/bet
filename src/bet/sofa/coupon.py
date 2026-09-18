"""COUPON — selection (PLAN §6.8).

Nothing here re-computes a probability or a threshold. It picks among rows the
engine already priced, and it says out loud why every VALUE row it did not pick
was dropped.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

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

MAX_SINGLES = 40
MAX_PER_FIXTURE = 3
MAX_PER_MECHANISM_FAMILY_PER_FIXTURE = 1
MIN_ODDS_FLOOR = 1.25


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

        candidates.append((row, fixture))

    # L18: within a family the slot goes to the biggest price surplus, not to
    # the biggest probability gap. A row that does not clear the bar must never
    # evict one that does.
    candidates.sort(
        key=lambda pair: pair[0].surplus if pair[0].surplus is not None else 0.0,
        reverse=True,
    )

    selected: list[CouponRow] = []
    per_fixture: dict[int, int] = {}
    families_per_fixture: dict[int, set[str]] = {}

    for row, fixture in candidates:
        fid = row.sofascore_event_id

        if len(selected) >= MAX_SINGLES:
            dropped.append(DroppedRow(row, "MAX_SINGLES", f"cap {MAX_SINGLES} reached"))
            continue

        if per_fixture.get(fid, 0) >= MAX_PER_FIXTURE:
            dropped.append(
                DroppedRow(row, "MAX_PER_FIXTURE", f"cap {MAX_PER_FIXTURE} reached")
            )
            continue

        family = get_mechanism_family(row.market)
        families = families_per_fixture.setdefault(fid, set())
        if family in families:
            dropped.append(
                DroppedRow(
                    row,
                    "FAMILY_SLOT_TAKEN",
                    f"family '{family}' already filled by a higher-surplus row",
                )
            )
            continue

        assert row.offered_odds is not None  # guaranteed by the ODDS_TOO_LOW gate
        assert row.surplus is not None
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
                p_bar=row.p_bar,
                offered_odds=row.offered_odds,
                required_odds=row.required_odds,
                edge=row.edge,
                surplus=row.surplus,
            )
        )

        per_fixture[fid] = per_fixture.get(fid, 0) + 1
        families.add(family)

    return CouponResult(
        coupon=Coupon(created_at_utc=current_time, singles=selected),
        dropped=dropped,
    )
