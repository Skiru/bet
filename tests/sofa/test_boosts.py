"""Superbet boosts: read from the offer API, graded against SETTLE.

The payload shapes below are cut down from the live 2026-09-23 responses for
Seattle Sounders - Real Salt Lake (a three-leg combo, 2.90 -> 3.15) and
Barcelona - Paris FC (Ewa Pajor 2+ goals, 2.67 -> 3.00).
"""

from datetime import UTC, datetime

from bet.sofa.boosts import (
    extract_boosts,
    grade_boost,
    is_boosted_event,
    merge_snapshots,
    parse_original_price,
)
from bet.sofa.offer import classify_odd
from scripts.sofa.audit_boosts import grade_day

AT = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)


def _plain(uuid: str, market: str, name: str, line: str | None, price: float) -> dict:
    return {"uuid": uuid, "marketName": market, "name": name,
            "specialBetValue": line, "price": price, "tags": "pm_boostable_market,v2"}


def _seattle(*, drop_leg: bool = False) -> dict:
    legs = [
        _plain("sot", "Liczba celnych strzałów - Seattle Sounders", "powyżej 5.5", "5.5", 2.10),
        _plain("goals", "Liczba goli", "powyżej 1.5", "1.5", 1.14),
        _plain("corners", "Seattle Sounders - liczba rzutów rożnych", "powyżej 4.5", "4.5", 1.36),
    ]
    if drop_leg:
        legs = legs[:2]
    combo = {
        "uuid": "boost-1", "marketName": "SOT; goals; corners", "name": "SOT; goals; corners",
        "price": 3.15, "tags": "price_boost,boost_non_core_market,price_boost_combo,v2",
        "extra": {"originalPrice": "220:2.900000", "boostLevel": "normal"},
        "oddComponents": [
            {"oddID": "sot", "marketLineName": "Liczba celnych strzałów - Seattle Sounders",
             "oddName": "powyżej 5.5", "specifiers": {"total": "5.5"}},
            {"oddID": "goals", "marketLineName": "Liczba goli", "oddName": "powyżej 1.5",
             "specifiers": {"total": "1.5"}},
            {"oddID": "corners", "marketLineName": "Seattle Sounders - liczba rzutów rożnych",
             "oddName": "powyżej 4.5", "specifiers": {"total": "4.5"}},
        ],
    }
    return {"eventId": "9001", "matchName": "Seattle Sounders·Real Salt Lake",
            "sportId": 5, "utcDate": "2026-09-24T01:30:00Z", "odds": [*legs, combo]}


def test_a_combo_is_read_leg_by_leg_at_its_plain_prices() -> None:
    [b] = extract_boosts(_seattle(), AT)
    assert b.combo and b.original_price == 2.90 and b.boosted_price == 3.15
    assert round(b.boost_pct or 0, 3) == 0.086
    assert [(leg.market, leg.subject, leg.line, leg.direction) for leg in b.legs] == [
        ("shots_on_target_for", "seattle sounders", 5.5, "OVER"),
        ("goals_total", "", 1.5, "OVER"),
        ("corners_for", "seattle sounders", 4.5, "OVER"),
    ]
    assert [leg.leg_price for leg in b.legs] == [2.10, 1.14, 1.36]
    assert round(b.leg_price_product or 0, 2) == 3.26


def test_a_leg_the_event_does_not_list_is_read_from_the_component() -> None:
    [b] = extract_boosts(_seattle(drop_leg=True), AT)
    corners = b.legs[2]
    assert (corners.market, corners.line, corners.direction) == ("corners_for", 4.5, "OVER")
    assert corners.leg_price is None
    assert b.leg_price_product is None, "a product with a missing leg is no yardstick"


def test_a_single_boost_is_read_from_its_source_odd() -> None:
    event = {"eventId": "9002", "matchName": "Barcelona (K)·Paris FC (K)", "sportId": 5,
             "utcDate": "2026-09-23T19:00:00Z", "odds": [
                 {"uuid": "src", "marketName": "Zawodnik - strzeli 2+ gole",
                  "name": "Pajor, Ewa", "specialBetValue": "Pajor, Ewa", "price": 2.67},
                 {"uuid": "boost-2", "marketName": "Boost", "name": "Pajor, Ewa strzeli 2+ gole",
                  "price": 3.0, "tags": "price_boost,boost_non_core_market,v2",
                  "extra": {"originalPrice": "9479:2.670000", "sourceOddUuid": "9479:src"}},
             ]}
    [b] = extract_boosts(event, AT)
    assert not b.combo
    assert b.legs[0].market_name == "Zawodnik - strzeli 2+ gole"
    assert b.legs[0].leg_price == 2.67


def test_boostable_is_not_boosted() -> None:
    """`pm_boostable_market` sits on a third of all odds; it is eligibility,
    not a boosted price, and a substring test would read every one of them."""
    event = _seattle()
    event["odds"] = event["odds"][:3]
    assert extract_boosts(event, AT) == []
    assert not is_boosted_event({"matchTags": "v2,pm_boostable_market"})
    assert is_boosted_event({"matchTags": "v2,manual,price_boost"})


def test_a_leg_from_another_sport_is_not_read_as_football() -> None:
    """Handball "Powyżej 60.5 goli" classifies as football goals_total."""
    event = {"eventId": "9003", "matchName": "MKS Kalisz·Ostrów Wielkopolski",
             "sportId": 11, "utcDate": "2026-09-23T18:15:00Z", "odds": [
                 {"uuid": "b", "marketName": "Liczba goli", "name": "powyżej 60.5",
                  "specialBetValue": "60.5", "price": 2.30, "tags": "price_boost,v2",
                  "extra": {"originalPrice": "1:2.07"}}]}
    [b] = extract_boosts(event, AT)
    assert b.legs[0].market is None
    assert b.legs[0].unmapped == "sport 11 is not a sofa sport"


def test_original_price_parsing() -> None:
    assert parse_original_price("220:2.900000") == 2.9
    assert parse_original_price("2.5") == 2.5
    assert parse_original_price(None) is None
    assert parse_original_price("220:junk") is None


def test_a_second_snapshot_adds_an_observation_and_moves_the_price() -> None:
    [first] = extract_boosts(_seattle(), AT)
    event = _seattle()
    event["odds"][-1]["price"] = 3.05
    [second] = extract_boosts(event, datetime(2026, 9, 23, 18, 0, tzinfo=UTC))
    [merged] = merge_snapshots([first], [second])
    assert merged.boosted_price == 3.05
    assert [o.boosted_price for o in merged.observations] == [3.15, 3.05]


def _settled(eid: int, outcomes: list[str]) -> dict:
    keys = [("shots_on_target_for", "seattle sounders", 5.5), ("goals_total", "", 1.5),
            ("corners_for", "seattle sounders", 4.5)]
    return {(eid, m, s, ln, "OVER"): {"outcome": o}
            for (m, s, ln), o in zip(keys, outcomes, strict=False)}


def test_grading_follows_the_slip_rule() -> None:
    [b] = extract_boosts(_seattle(), AT)
    assert grade_boost(b, None, {}) == ("UNSETTLED", "NOT_ON_BOARD")
    assert grade_boost(b, 7, _settled(7, ["WIN", "WIN", "WIN"])) == ("WIN", None)
    assert grade_boost(b, 7, _settled(7, ["WIN", "LOSS"])) == ("LOSS", None)
    assert grade_boost(b, 7, _settled(7, ["WIN", "WIN"])) == ("UNSETTLED", "LEG_NOT_SETTLED")
    assert grade_boost(b, 7, _settled(7, ["WIN", "PUSH", "WIN"])) == (
        "UNSETTLED", "LEG_PUSHED")


def test_a_lost_leg_loses_even_beside_a_leg_we_cannot_read() -> None:
    [b] = extract_boosts(_seattle(), AT)
    b.legs[1].market = None
    assert grade_boost(b, 7, _settled(7, ["LOSS"])) == ("LOSS", None)
    assert grade_boost(b, 7, _settled(7, ["WIN", "WIN", "WIN"])) == (
        "UNSETTLED", "UNMAPPED_LEG")


def test_the_day_grade_carries_both_break_evens() -> None:
    [b] = extract_boosts(_seattle(), AT)
    fixtures = [{"sofascore_event_id": 7, "superbet_event_ids": ["9001"]}]
    settled = [{"sofascore_event_id": 7, "market": m, "subject": s, "line": ln,
                "direction": "OVER", "outcome": "WIN"}
               for (_, m, s, ln, _), _v in _settled(7, ["WIN"] * 3).items()]
    g = grade_day([b], fixtures, settled)["kombinacje"]
    assert (g.offered, g.graded, g.won) == (1, 1, 1)
    assert round(g.units_boosted, 2) == 2.15 and round(g.units_original, 2) == 1.90
    assert round(g.breakeven_boosted, 4) == round(1 / 3.15, 4)


def test_classify_odd_is_offers_classification() -> None:
    """The boost legs settle against the sheet only if they are classified the
    way OFFER classified the same odd."""
    assert classify_odd({"marketName": "Liczba goli", "name": "poniżej 2.5",
                         "specialBetValue": "2.5"}) == (("goals_total", "", 2.5, "UNDER"), None)
    assert classify_odd({"marketName": "Liczba goli", "name": "powyżej 2.5",
                         "specialBetValue": None}) == (None, "Liczba goli (no line)")
    assert classify_odd({"marketName": "Nieznany rynek", "name": "x"}) == (
        None, "Nieznany rynek")
