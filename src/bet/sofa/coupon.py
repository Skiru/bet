from datetime import datetime, timedelta
from typing import List, Dict, Tuple

from bet.sofa.contracts import CouponRow, Fixture, SheetRow, FixtureOffer, Veto, Coupon
from bet.sofa.market_mapper import get_mechanism_family
from bet.sofa.veto import match_vetoes

MAX_SINGLES = 40
MAX_PER_FIXTURE = 3
MAX_PER_MECHANISM_FAMILY_PER_FIXTURE = 1

def build_coupon(
    sheet_rows: List[SheetRow],
    fixtures: List[Fixture],
    offers: List[FixtureOffer],
    vetoes: List[Veto],
    current_time: datetime,
    min_kickoff: datetime,
    max_price_age: timedelta,
    min_odds_floor: float = 1.25
) -> Tuple[Coupon, List[SheetRow], List[SheetRow]]:
    """
    Returns (Coupon, unmatched_vetoes_rows, dropped_rows) ? 
    Actually, we just need to return Coupon and a list of unselected candidates.
    But let's keep it simple.
    """
    fixtures_by_id = {f.sofascore_event_id: f for f in fixtures}
    
    fetched_at_by_key = {}
    for offer in offers:
        for rung in offer.rungs:
            if rung.over_odds is not None:
                fetched_at_by_key[(offer.sofascore_event_id, rung.market, rung.subject, rung.line, "OVER")] = rung.fetched_at_utc
            if rung.under_odds is not None:
                fetched_at_by_key[(offer.sofascore_event_id, rung.market, rung.subject, rung.line, "UNDER")] = rung.fetched_at_utc

    candidates = []
    dropped = []

    for row in sheet_rows:
        if row.verdict != "VALUE":
            continue

        fixture = fixtures_by_id.get(row.sofascore_event_id)
        if not fixture:
            dropped.append((row, "NO_FIXTURE"))
            continue

        if fixture.kickoff_utc <= min_kickoff:
            dropped.append((row, "KICKOFF_TOO_SOON"))
            continue

        if row.offered_odds is None or row.offered_odds < min_odds_floor:
            dropped.append((row, "ODDS_TOO_LOW"))
            continue

        matched_vetoes = match_vetoes(row, vetoes)
        if matched_vetoes:
            dropped.append((row, f"VETOED: {matched_vetoes[0].reason}"))
            continue

        key = (row.sofascore_event_id, row.market, row.subject, row.line, row.direction)
        fetched_at = fetched_at_by_key.get(key)
        if not fetched_at or current_time - fetched_at > max_price_age:
            dropped.append((row, "STALE_PRICE"))
            continue

        candidates.append((row, fixture))

    # T28: Limit rodziny wybiera wiersz o największej nadwyżce (surplus)
    candidates.sort(key=lambda x: x[0].surplus if x[0].surplus is not None else 0.0, reverse=True)

    selected_singles = []
    selected_per_fixture = {}
    selected_families_per_fixture = {}

    for row, fixture in candidates:
        if len(selected_singles) >= MAX_SINGLES:
            break

        fid = row.sofascore_event_id
        if selected_per_fixture.get(fid, 0) >= MAX_PER_FIXTURE:
            continue

        family = get_mechanism_family(row.market)
        families = selected_families_per_fixture.get(fid, set())

        if family in families:
            continue

        selected_singles.append(CouponRow(
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
            surplus=row.surplus
        ))

        selected_per_fixture[fid] = selected_per_fixture.get(fid, 0) + 1
        families.add(family)
        selected_families_per_fixture[fid] = families

    coupon = Coupon(
        created_at_utc=current_time,
        singles=selected_singles
    )

    return coupon
