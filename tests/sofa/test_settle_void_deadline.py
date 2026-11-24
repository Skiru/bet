"""Superbet voids a match not played by the end of the day after the start it
was offered at, 23:59 local time at the venue (Regulamin Zakładów Online
5.E.1.a, approved 2026-02-10; read on support.superbet.pl 2026-10-13). Until
2026-10-13 the code read the 2022 rules' 48 h (settle.VOID_AFTER), which
graded a match replayed 30 h later on the next-but-one day and refunded none
of them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from bet.sofa import cs2, shadow
from bet.sofa.settle import (
    moved_beyond_void,
    not_played_beyond_void,
    venue_timezone,
    void_deadline,
)

# 20:00 in Warsaw (CEST, UTC+2)
OFFERED = datetime(2026, 10, 8, 18, 0, tzinfo=UTC)


def _event(start: datetime, *, kind: str = "finished", venue: str | None = None,
           category: str | None = None, home: str | None = None,
           sport: str = "football") -> dict[str, Any]:
    return {
        "startTimestamp": int(start.timestamp()),
        "status": {"type": kind},
        "venue": {"country": {"alpha2": venue}} if venue else None,
        "tournament": {"category": {"alpha2": category, "sport": {"slug": sport}}},
        "homeTeam": {"country": {"alpha2": home}} if home else {},
    }


def test_deadline_is_the_end_of_the_next_local_day() -> None:
    warsaw = ZoneInfo("Europe/Warsaw")
    assert void_deadline(OFFERED, warsaw) == datetime(2026, 10, 9, 21, 59, tzinfo=UTC)
    assert void_deadline(OFFERED) == datetime(2026, 10, 9, 23, 59, tzinfo=UTC)
    # a 23:30 local start keeps the whole next day, not 24 h
    late = datetime(2026, 10, 8, 21, 30, tzinfo=UTC)
    assert void_deadline(late, warsaw) == datetime(2026, 10, 9, 21, 59, tzinfo=UTC)


def test_venue_zone_venue_then_competition_then_home_side() -> None:
    assert venue_timezone(_event(OFFERED, venue="PL", category="EN")).key == "Europe/Warsaw"  # type: ignore[attr-defined]
    assert venue_timezone(_event(OFFERED, category="PL")).key == "Europe/Warsaw"  # type: ignore[attr-defined]
    assert venue_timezone(_event(OFFERED, home="JP")).key == "Asia/Tokyo"  # type: ignore[attr-defined]
    # a tennis player's nationality is not where he plays
    assert venue_timezone(_event(OFFERED, home="JP", sport="tennis")) is UTC
    assert venue_timezone(_event(OFFERED)) is UTC
    assert venue_timezone(None) is UTC


def test_moved_past_the_deadline_is_void_inside_48_h() -> None:
    clocks = [OFFERED]
    # replayed next day 23:00 local: valid
    assert not moved_beyond_void(_event(datetime(2026, 10, 9, 21, 0, tzinfo=UTC),
                                        category="PL"), clocks)
    # two days on at 19:00 local (47 h): void now, graded under the 48 h rule
    two_days = OFFERED + timedelta(hours=47)
    assert moved_beyond_void(_event(two_days, category="PL"), clocks)
    # brought forward: the 48 h rule as before
    assert not moved_beyond_void(_event(OFFERED - timedelta(hours=47), category="PL"), clocks)
    assert moved_beyond_void(_event(OFFERED - timedelta(hours=49), category="PL"), clocks)


def test_still_postponed_reads_the_venue_deadline() -> None:
    ev = _event(OFFERED, kind="postponed", category="PL")
    assert not not_played_beyond_void(ev, [OFFERED], datetime(2026, 10, 9, 21, 58, tzinfo=UTC))
    assert not_played_beyond_void(ev, [OFFERED], datetime(2026, 10, 9, 22, 0, tzinfo=UTC))


def test_measured_sports_and_cs2_read_the_same_deadline() -> None:
    detail = _event(OFFERED, kind="postponed", category="PL", sport="ice-hockey")
    before = datetime(2026, 10, 9, 21, 58, tzinfo=UTC)
    after = datetime(2026, 10, 9, 22, 0, tzinfo=UTC)
    sport = shadow.SPORTS["hockey"]
    assert shadow.event_state(detail, sport, OFFERED, before) == "PENDING"
    assert shadow.event_state(detail, sport, OFFERED, after) == "VOID"
    series = {"status": {"type": "notstarted"}}  # no country: UTC
    assert cs2.event_state(series, OFFERED, datetime(2026, 10, 9, 23, 58, tzinfo=UTC)) == "PENDING"
    assert cs2.event_state(series, OFFERED, datetime(2026, 10, 10, 0, 0, tzinfo=UTC)) == "VOID"


# --- a country with several zones (2026-11-24): the venue's own place decides --
# SAP Center (San Jose) and Indian Wells read America/New_York before, so a
# West-Coast match's deadline came three hours early (dossier venue_zone,
# 2026-11-15).


def _place(city: str | None = None, *, country: str = "US", state: str | None = None,
           coords: tuple[float, float] | None = None) -> dict[str, Any]:
    node: dict[str, Any] = {"country": {"alpha2": country}}
    if city is not None:
        node["city"] = {"name": city, "country": {"alpha2": country}}
        if state:
            node["city"]["state"] = state
    if coords:
        node["venueCoordinates"] = {"latitude": coords[0], "longitude": coords[1]}
    return node


def _at(venue: dict[str, Any] | None, *, sport: str = "football", category: str | None = None,
        home_country: str | None = None, home_venue: dict[str, Any] | None = None) -> dict[str, Any]:
    home: dict[str, Any] = {}
    if home_country:
        home["country"] = {"alpha2": home_country}
    if home_venue is not None:
        home["venue"] = home_venue
    return {
        "startTimestamp": int(OFFERED.timestamp()),
        "status": {"type": "postponed"},
        "venue": venue,
        "tournament": {"category": {"alpha2": category, "sport": {"slug": sport}}},
        "homeTeam": home,
    }


def _key(event: dict[str, Any]) -> str:
    return str(venue_timezone(event))


def test_west_coast_venues_read_their_own_zone() -> None:
    # SAP Center as the 2026-11 NHL payload has it: city, no state, no coordinates
    assert _key(_at(_place("San Jose"), sport="ice-hockey")) == "America/Los_Angeles"
    assert _key(_at(_place("Indian Wells"), sport="tennis")) == "America/Los_Angeles"
    # accents / case do not matter
    assert _key(_at(_place("SAN JOSÉ"))) == "America/Los_Angeles"


def test_state_decides_when_the_city_is_not_listed() -> None:
    assert _key(_at(_place("Kalamazoo", state="US-MI"))) == "America/Detroit"
    assert _key(_at(_place("Somewhere", state="US-TX"))) == "America/Chicago"
    assert _key(_at(_place("Somewhere", country="CA", state="CA-AB"))) == "America/Edmonton"
    # a split state: El Paso is Mountain although Texas reads Central
    assert _key(_at(_place("El Paso", state="US-TX"))) == "America/Denver"
    # a listed city with another state is not that city
    assert _key(_at(_place("San Jose", state="US-IL"))) == "America/Chicago"


def test_coordinates_decide_last_within_the_radius() -> None:
    perth = _place("Unknown suburb", country="AU", coords=(-31.99, 115.89))
    assert _key(_at(perth)) == "Australia/Perth"
    # far from every listed place: the country's zone, as before
    outback = _place("Unknown", country="AU", coords=(-25.0, 135.0))
    assert _key(_at(outback)) == "Australia/Sydney"
    # Campo Grande is also a Rio de Janeiro district: never by name, only by coordinates
    assert _key(_at(_place("Campo Grande", country="BR"))) == "America/Sao_Paulo"
    campo_grande = _place("Campo Grande", country="BR", coords=(-20.45, -54.60))
    assert _key(_at(campo_grande)) == "America/Campo_Grande"


def test_unknown_or_ambiguous_place_keeps_the_country_zone() -> None:
    # Columbia SC (Eastern) and Columbia MO (Central): not guessed
    assert _key(_at(_place("Columbia"))) == "America/New_York"
    assert _key(_at(_place(None))) == "America/New_York"
    # Canary Islands: an hour behind Madrid
    assert _key(_at(_place("Las Palmas de Gran Canaria", country="ES"))) == "Atlantic/Canary"
    assert _key(_at(_place("Madrid", country="ES"))) == "Europe/Madrid"
    # a single-zone country is never refined
    assert _key(_at(_place("San Jose", country="PL"))) == "Europe/Warsaw"


def test_home_ground_places_a_team_sport_inside_the_chosen_country() -> None:
    # NHL: no event venue, category "North America" with no country, home side US
    nhl = _at(None, sport="ice-hockey", home_country="US", home_venue=_place("San Jose"))
    assert _key(nhl) == "America/Los_Angeles"
    # the home ground never chooses the country: a club whose listed ground is
    # abroad (Al-Hilal Omdurman in the Rwandan league) reads the competition's
    abroad = _at(None, category="RW", home_country="SD",
                 home_venue=_place("Omdurman", country="SD"))
    assert _key(abroad) == "Africa/Kigali"
    # tennis has no home ground
    player = _at(None, sport="tennis", home_country="US", home_venue=_place("San Jose"))
    assert venue_timezone(player) is UTC


def test_west_coast_postponed_game_voids_at_its_own_midnight() -> None:
    offered = datetime(2026, 11, 15, 3, 0, tzinfo=UTC)  # 19:00 PST on the 14th
    detail = _at(_place("San Jose"), sport="ice-hockey")
    assert void_deadline(offered, venue_timezone(detail)) == datetime(
        2026, 11, 16, 7, 59, tzinfo=UTC)
    sport = shadow.SPORTS["hockey"]
    # New York's deadline (04:59Z) has passed, Los Angeles' has not
    assert shadow.event_state(detail, sport, offered,
                              datetime(2026, 11, 16, 6, 0, tzinfo=UTC)) == "PENDING"
    assert shadow.event_state(detail, sport, offered,
                              datetime(2026, 11, 16, 8, 0, tzinfo=UTC)) == "VOID"
