import json
import pytest
from datetime import datetime, UTC
from typing import Any

from bet.sofa.contracts import Fixture, FixtureOffer, PricedRung
from bet.sofa.superbet import SuperbetClient
from bet.sofa.offer import OfferFetcher
from bet.sofa.timeutil import now

class DummyClient:
    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.calls = []

    def event_odds(self, event_id: str | int) -> dict[str, Any] | None:
        self.calls.append(event_id)
        return self.data.get(str(event_id))

def test_offer_fetcher_combines_odds():
    dummy_data = {
        "101": {
            "odds": [
                {"marketName": "Liczba goli", "name": "poniżej 2.5", "specialBetValue": "2.5", "price": 1.8},
                {"marketName": "Liczba goli", "name": "powyżej 2.5", "specialBetValue": "2.5", "price": 2.0},
                {"marketName": "Liczba kartek", "name": "poniżej 4.5", "specialBetValue": "4.5", "price": 1.5},
                {"marketName": "Unknown Market", "name": "poniżej", "specialBetValue": "1.0", "price": 1.1},
            ]
        },
        "102": {
            "odds": [
                {"marketName": "Liczba goli", "name": "powyżej 3.5", "specialBetValue": "3.5", "price": 3.0}
            ]
        }
    }
    
    client = DummyClient(dummy_data)
    fetcher = OfferFetcher(client)
    
    fixtures = [
        Fixture(
            sofascore_event_id=1,
            superbet_event_ids=["101", "102"],
            sport="football",
            kickoff_utc=now(),
            home_name="A",
            away_name="B",
            home_entity_id=1,
            away_entity_id=2,
            competition_name="C",
            competition_id=3,
            season_id=4,
            category_name="D",
            identity="CONFIRMED",
            round_number=None,
            round_name=None,
            cup_round_type=None,
            previous_leg_event_id=None,
            venue_name=None,
            referee=None,
            has_xg=False,
            ground_type=None,
            best_of=None,
        ),
        Fixture(
            sofascore_event_id=2,
            superbet_event_ids=["999"],
            sport="football",
            kickoff_utc=now(),
            home_name="X",
            away_name="Y",
            home_entity_id=5,
            away_entity_id=6,
            competition_name="Z",
            competition_id=7,
            season_id=8,
            category_name="W",
            identity="CONFIRMED",
            round_number=None,
            round_name=None,
            cup_round_type=None,
            previous_leg_event_id=None,
            venue_name=None,
            referee=None,
            has_xg=False,
            ground_type=None,
            best_of=None,
        )
    ]
    
    offers = fetcher.fetch_offers(fixtures)
    assert len(offers) == 2
    
    # Asserting no name matching, strictly event_id
    from pathlib import Path
    offer_code = (Path(__file__).parent.parent.parent / "src" / "bet" / "sofa" / "offer.py").read_text()
    assert "home_name" not in offer_code
    assert "away_name" not in offer_code
        
    offer1 = offers[0]
    assert offer1.sofascore_event_id == 1
    assert offer1.status == "PRICED"
    assert offer1.unmapped_markets == ["Unknown Market"]
    
    assert len(offer1.rungs) == 3 # 2.5 goals, 4.5 cards, 3.5 goals
    goals_25 = next(r for r in offer1.rungs if r.market == "goals_total" and r.line == 2.5)
    assert goals_25.over_odds == 2.0
    assert goals_25.under_odds == 1.8
    assert goals_25.subject == ""
    
    goals_35 = next(r for r in offer1.rungs if r.market == "goals_total" and r.line == 3.5)
    assert goals_35.over_odds == 3.0
    assert goals_35.under_odds is None
    
    cards_45 = next(r for r in offer1.rungs if r.market == "cards_points_total" and r.line == 4.5)
    assert cards_45.over_odds is None
    assert cards_45.under_odds == 1.5
    
    offer2 = offers[1]
    assert offer2.sofascore_event_id == 2
    assert len(offer2.rungs) == 0
    assert offer2.status == "NO_PRICE"
    assert offer2.unmapped_markets == []
