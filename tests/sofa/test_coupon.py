import pytest
from datetime import datetime, timedelta, UTC
from copy import deepcopy

from bet.sofa.contracts import SheetRow, Fixture, FixtureOffer, Veto
from bet.sofa.coupon import build_coupon
from bet.sofa.veto import match_vetoes, find_unmatched_vetoes

@pytest.fixture
def base_sheet_row():
    return SheetRow(
        sofascore_event_id=1,
        sport="football",
        market="shots_on_target_for",
        subject="Player A",
        line=1.5,
        direction="OVER",
        sample_size=10,
        sample_mean=2.5,
        sample_sd=1.0,
        centre=2.2,
        p_central=0.7,
        market_p=0.5,
        ladder_centre=None,
        ladder_sigma=None,
        p_bar=0.6,
        bar_reason=None,
        required_odds=1.75,
        offered_odds=2.0,
        edge=0.2,
        surplus=0.25,
        verdict="VALUE",
        notes=[]
    )

@pytest.fixture
def base_fixture():
    return Fixture(
        sofascore_event_id=1,
        superbet_event_ids=["S1"],
        sport="football",
        kickoff_utc=datetime(2026, 9, 17, 20, 0, tzinfo=UTC),
        home_name="Home",
        away_name="Away",
        home_entity_id=10,
        away_entity_id=20,
        competition_name="League",
        competition_id=100,
        season_id=200,
        category_name="Country",
        identity="CONFIRMED",
        round_number=1,
        round_name=None,
        cup_round_type=None,
        previous_leg_event_id=None,
        venue_name=None,
        referee=None,
        has_xg=True,
        ground_type=None,
        best_of=None
    )

@pytest.fixture
def current_time():
    return datetime(2026, 9, 17, 10, 0, tzinfo=UTC)

def test_t26_veto_with_subject(base_sheet_row):
    row_a = base_sheet_row.model_copy(update={"subject": "Player A"})
    row_b = base_sheet_row.model_copy(update={"subject": "Player B"})
    row_c = base_sheet_row.model_copy(update={"subject": "Player C"})
    
    veto = Veto(
        sofascore_event_id=1,
        market="shots_on_target_for",
        subject="Player A",
        line=None,
        direction=None,
        reason_class="OTHER",
        reason="Test"
    )
    
    # Veto na jednego (Player A), dwa pozostale przezywaja
    assert match_vetoes(row_a, [veto]) == [veto]
    assert match_vetoes(row_b, [veto]) == []
    assert match_vetoes(row_c, [veto]) == []

def test_t27_unmatched_veto(base_sheet_row):
    row_a = base_sheet_row.model_copy(update={"subject": "Player A"})
    
    veto1 = Veto(
        sofascore_event_id=1,
        market="shots_on_target_for",
        subject="Player A",
        line=None,
        direction=None,
        reason_class="OTHER",
        reason="Match"
    )
    
    veto2 = Veto(
        sofascore_event_id=1,
        market="shots_on_target_for",
        subject="Player B",
        line=None,
        direction=None,
        reason_class="OTHER",
        reason="Unmatched"
    )
    
    unmatched = find_unmatched_vetoes([row_a], [veto1, veto2])
    assert unmatched == [veto2]

def test_t28_family_limit_by_surplus(base_sheet_row, base_fixture, current_time):
    # Dwa wiersze z tej samej rodziny (np. goals_total i goals_1h_total - both scoring)
    # Row 1 ma wiekszy edge, ale mniejszy surplus
    # Row 2 ma mniejszy edge, ale wiekszy surplus
    row1 = base_sheet_row.model_copy(update={
        "market": "goals_total",
        "edge": 0.2,       # wiekszy
        "surplus": 0.1     # mniejszy
    })
    
    row2 = base_sheet_row.model_copy(update={
        "market": "goals_1h_total",
        "edge": 0.1,       # mniejszy
        "surplus": 0.3     # wiekszy
    })
    
    offers = [] # nie potrzebujemy prices_fetched_at do tego testu jesli min_price_age sie nie martwimy... 
    # Wait, build_coupon requires fetched_at or it will drop for STALE_PRICE
    from bet.sofa.contracts import FixtureOffer, PricedRung
    offer = FixtureOffer(
        sofascore_event_id=1,
        unmapped_markets=[],
        rungs=[
            PricedRung(market="goals_total", subject="Player A", line=1.5, over_odds=2.0, under_odds=2.0, fetched_at_utc=current_time),
            PricedRung(market="goals_1h_total", subject="Player A", line=1.5, over_odds=2.0, under_odds=2.0, fetched_at_utc=current_time)
        ]
    )
    
    coupon = build_coupon(
        sheet_rows=[row1, row2],
        fixtures=[base_fixture],
        offers=[offer],
        vetoes=[],
        current_time=current_time,
        min_kickoff=current_time + timedelta(minutes=15),
        max_price_age=timedelta(minutes=45)
    )
    
    # Powinno wybrac row2 (wiekszy surplus)
    assert len(coupon.singles) == 1
    assert coupon.singles[0].market == "goals_1h_total"

def test_t29_kickoff_and_stale_price(base_sheet_row, base_fixture, current_time):
    # Row1: Kickoff in past
    fixture_past = base_fixture.model_copy(update={"kickoff_utc": current_time - timedelta(hours=1)})
    
    # Row2: Stale price
    fixture_stale = base_fixture.model_copy(update={"sofascore_event_id": 2})
    row_stale = base_sheet_row.model_copy(update={"sofascore_event_id": 2})
    
    # Row3: OK
    fixture_ok = base_fixture.model_copy(update={"sofascore_event_id": 3})
    row_ok = base_sheet_row.model_copy(update={"sofascore_event_id": 3})
    
    from bet.sofa.contracts import FixtureOffer, PricedRung
    offers = [
        FixtureOffer(
            sofascore_event_id=1,
            unmapped_markets=[],
            rungs=[PricedRung(market="shots_on_target_for", subject="Player A", line=1.5, over_odds=2.0, under_odds=2.0, fetched_at_utc=current_time)]
        ),
        FixtureOffer(
            sofascore_event_id=2,
            unmapped_markets=[],
            rungs=[PricedRung(market="shots_on_target_for", subject="Player A", line=1.5, over_odds=2.0, under_odds=2.0, fetched_at_utc=current_time - timedelta(hours=2))]
        ),
        FixtureOffer(
            sofascore_event_id=3,
            unmapped_markets=[],
            rungs=[PricedRung(market="shots_on_target_for", subject="Player A", line=1.5, over_odds=2.0, under_odds=2.0, fetched_at_utc=current_time)]
        )
    ]
    
    coupon = build_coupon(
        sheet_rows=[base_sheet_row, row_stale, row_ok],
        fixtures=[fixture_past, fixture_stale, fixture_ok],
        offers=offers,
        vetoes=[],
        current_time=current_time,
        min_kickoff=current_time + timedelta(minutes=15),
        max_price_age=timedelta(minutes=45)
    )
    
    assert len(coupon.singles) == 1
    assert coupon.singles[0].sofascore_event_id == 3
