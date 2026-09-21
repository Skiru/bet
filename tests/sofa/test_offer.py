from typing import Any

from bet.sofa.contracts import Fixture
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
                {
                    "marketName": "Liczba goli",
                    "name": "poniżej 2.5",
                    "specialBetValue": "2.5",
                    "price": 1.8,
                },
                {
                    "marketName": "Liczba goli",
                    "name": "powyżej 2.5",
                    "specialBetValue": "2.5",
                    "price": 2.0,
                },
                {
                    "marketName": "Liczba kartek",
                    "name": "poniżej 4.5",
                    "specialBetValue": "4.5",
                    "price": 1.5,
                },
                {
                    "marketName": "Unknown Market",
                    "name": "poniżej",
                    "specialBetValue": "1.0",
                    "price": 1.1,
                },
            ]
        },
        "102": {
            "odds": [
                {
                    "marketName": "Liczba goli",
                    "name": "powyżej 3.5",
                    "specialBetValue": "3.5",
                    "price": 3.0,
                }
            ]
        },
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
            ground_type=None,
            default_period_count=None,
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
            ground_type=None,
            default_period_count=None,
        ),
    ]

    offers = fetcher.fetch_offers(fixtures)
    assert len(offers) == 2

    # Asserting no name matching, strictly event_id
    from pathlib import Path

    offer_code = (
        Path(__file__).parent.parent.parent / "src" / "bet" / "sofa" / "offer.py"
    ).read_text()
    assert "home_name" not in offer_code
    assert "away_name" not in offer_code

    offer1 = offers[0]
    assert offer1.sofascore_event_id == 1
    assert offer1.status == "PRICED"
    assert offer1.unmapped_markets == ["Unknown Market"]

    assert len(offer1.rungs) == 3  # 2.5 goals, 4.5 cards, 3.5 goals
    goals_25 = next(
        r for r in offer1.rungs if r.market == "goals_total" and r.line == 2.5
    )
    assert goals_25.over_odds == 2.0
    assert goals_25.under_odds == 1.8
    assert goals_25.subject == ""

    goals_35 = next(
        r for r in offer1.rungs if r.market == "goals_total" and r.line == 3.5
    )
    assert goals_35.over_odds == 3.0
    assert goals_35.under_odds is None

    cards_45 = next(
        r for r in offer1.rungs if r.market == "cards_points_total" and r.line == 4.5
    )
    assert cards_45.over_odds is None
    assert cards_45.under_odds == 1.5

    offer2 = offers[1]
    assert offer2.sofascore_event_id == 2
    assert len(offer2.rungs) == 0
    assert offer2.status == "NO_PRICE"
    assert offer2.unmapped_markets == []


def test_a_filtered_offer_refresh_must_not_shrink_the_artifact(tmp_path, monkeypatch):
    """A late refresh prices only what can still be bet — and keeps the rest.

    OFFER costs ~90 minutes over a full board, so a refresh at 18:00 that
    re-prices all 1,078 fixtures spends almost all of it on matches already
    played while the ones still open keep kicking off. `--min-minutes-to-kickoff`
    cuts that. But the stage overwrites `04_offer.json`, and SHEET prices what
    it finds there, so a filtered write would delete the rest of the day —
    which is how `simple`'s `--refresh-offer` lost Betis–Madrid and PSG–Monaco.

    This pins the merge: refreshed fixtures win, untouched fixtures survive.

    It calls the production function. An earlier version of this test
    reimplemented the same four lines in its own body, so deleting the merge
    from `run_offer` left it green — a regression test that cannot fail on the
    regression it names.
    """
    import json

    from scripts.sofa.run_offer import merge_with_previous

    previous = [
        {"sofascore_event_id": 1, "status": "OK", "rungs": [{"line": 2.5}],
         "unmapped_markets": [], "price_collisions": []},
        {"sofascore_event_id": 2, "status": "OK", "rungs": [],
         "unmapped_markets": [], "price_collisions": []},
    ]
    fresh = [
        {"sofascore_event_id": 2, "status": "OK", "rungs": [{"line": 9.5}],
         "unmapped_markets": [], "price_collisions": []},
    ]

    merged, carried_forward = merge_with_previous(fresh, previous)

    by_id = {o["sofascore_event_id"]: o for o in merged}
    assert set(by_id) == {1, 2}, "the untouched fixture must survive the refresh"
    assert by_id[2]["rungs"] == [{"line": 9.5}], "the refreshed price must win"
    assert by_id[1]["rungs"] == [{"line": 2.5}], "the carried price must be unchanged"
    assert len(merged) >= len(previous), "a refresh may never shrink the artifact"
    assert carried_forward == 1, "the count the stage reports must match what it kept"
    json.dumps(merged)


def test_a_refresh_that_touches_nothing_still_keeps_the_whole_day():
    """The degenerate case, which is the one that deletes a day.

    If the filter excludes every fixture — a refresh run after the last
    kickoff — `fresh` is empty. Returning it unchanged would write an empty
    `04_offer.json` and SHEET would price nothing, reporting a day with no
    prices rather than a refresh with no work to do.
    """
    from scripts.sofa.run_offer import merge_with_previous

    previous = [
        {"sofascore_event_id": i, "status": "OK", "rungs": [{"line": 2.5}],
         "unmapped_markets": [], "price_collisions": []}
        for i in range(1, 6)
    ]
    merged, carried_forward = merge_with_previous([], previous)
    assert len(merged) == 5
    assert carried_forward == 5
