"""CS2 shadow: parsing Superbet's CS2 lines and grading them from Sofascore.

Item shapes are copied from Superbet's Ninjas in Pyjamas - GamerLegion offer
and the map/lineup shapes from Sofascore's magic - GamerLegion (2026-09-28).
"""

from bet.sofa.cs2 import (
    Cs2Line,
    MapResult,
    actual_value,
    build_map_result,
    grade,
    parse_event,
    parse_line,
)

T1, T2 = "Ninjas in Pyjamas", "GamerLegion"


def _item(
    market: str, name: str, price: float, spec: dict | None = None, info: str = "", **kw
) -> dict:
    return {
        "marketName": market,
        "name": name,
        "info": info or name,
        "price": price,
        "specifiers": spec,
        "status": "active",
        **kw,
    }


def test_map_handicap_line_is_team1s_handicap_for_both_outcomes() -> None:
    items = [
        _item(
            "Handicap map", "Ninjas in Pyjamas (-1.5)", 3.4, {"hcp": "-1.5"}, code="1"
        ),
        _item("Handicap map", "GamerLegion (1.5)", 1.26, {"hcp": "-1.5"}, code="2"),
    ]
    lines = parse_event(items, "e1", T1, T2)
    assert {(ln.side, ln.line) for ln in lines} == {("T1", -1.5), ("T2", -1.5)}
    # GamerLegion 2-0: NiP -1.5 loses, GamerLegion +1.5 wins.
    for ln in lines:
        assert grade(ln, -2.0) == ("LOSS" if ln.side == "T1" else "WIN")


def test_player_kills_direction_and_subject() -> None:
    under = parse_line(
        _item(
            "1.mapa - liczba zabójstw zawodnika (z dogrywką)",
            "FL4MUS - poniżej 16.5",
            1.9,
            {"player": "FL4MUS", "total": "16.5"},
        ),
        "e1",
        T1,
        T2,
    )
    assert under == Cs2Line("e1", "player_kills", 1, "FL4MUS", 16.5, "UNDER", 1.9)


def test_one_sided_lines_combos_and_boosts_are_dropped() -> None:
    items = [
        _item("Liczba map", "poniżej 3.5", 2.9, {"total": "3.5"}),
        _item(
            "Boost",
            "1.mapa - FL4MUS powyżej 16.5 zabójstw",
            1.95,
            {"player": "FL4MUS", "total": "16.5"},
        ),
        _item(
            "Ninjas in Pyjamas wygra 1. mapę; Snax powyżej 12.5 zabójstw na 1. mapie",
            "x",
            4.0,
        ),
        _item(
            "1. mapa - liczba zabójstw z AWP zawodnika (z dogrywką)",
            "hypex - poniżej 6.5",
            1.8,
            {"player": "hypex", "total": "  6.5 "},
        ),
    ]
    assert parse_event(items, "e1", T1, T2) == []


def _maps() -> list[MapResult]:
    # Sofascore home = magic = Superbet team2 here; GamerLegion (T1) won 13-10, 13-5.
    game = {
        "status": {"type": "finished"},
        "homeScore": {"display": 10},
        "awayScore": {"display": 13},
    }
    lineups = {
        "homeTeamPlayers": [
            {
                "player": {"name": "mo0n"},
                "kills": 16,
                "deaths": 12,
                "assists": 3,
                "headshots": 9,
            }
        ],
        "awayTeamPlayers": [
            {
                "player": {"name": "REZ"},
                "kills": 21,
                "deaths": 14,
                "assists": 5,
                "headshots": 11,
            }
        ],
    }
    m1 = build_map_result(game, lineups, sofascore_home_is_t1=False)
    game2 = {
        "status": {"type": "finished"},
        "homeScore": {"display": 5},
        "awayScore": {"display": 13},
    }
    m2 = build_map_result(game2, None, sofascore_home_is_t1=False)
    assert m1 is not None and m2 is not None
    return [m1, m2]


def test_orientation_follows_superbet_team1() -> None:
    maps = _maps()
    assert (maps[0].t1_rounds, maps[0].t2_rounds) == (13, 10)
    assert maps[0].players["rez"][0] == "T1"
    assert maps[0].players["mo0n"][0] == "T2"


def test_grading_from_map_data() -> None:
    maps = _maps()
    t1, t2 = "GamerLegion", "magic"
    rez = Cs2Line("e", "player_kills", 1, "REZ", 19.5, "OVER", 1.8)
    assert actual_value(rez, maps, t1, t2) == 21.0 and grade(rez, 21.0) == "WIN"
    rounds = Cs2Line("e", "map_rounds_total", 1, "", 21.5, "UNDER", 1.8)
    assert grade(rounds, actual_value(rounds, maps, t1, t2) or 0) == "LOSS"  # 23 rounds
    winner = Cs2Line("e", "match_winner", 0, "", None, "T1", 1.5)
    assert grade(winner, actual_value(winner, maps, t1, t2) or 0) == "WIN"
    maps_total = Cs2Line("e", "maps_total", 0, "", 2.5, "UNDER", 1.6)
    assert grade(maps_total, actual_value(maps_total, maps, t1, t2) or 0) == "WIN"


def test_a_map_that_was_not_played_is_not_graded() -> None:
    third = Cs2Line("e", "map_rounds_total", 3, "", 21.5, "OVER", 1.8)
    assert actual_value(third, _maps(), "GamerLegion", "magic") is None


def test_a_player_without_a_lineup_row_is_not_graded() -> None:
    ghost = Cs2Line("e", "player_kills", 2, "REZ", 15.5, "OVER", 1.8)
    assert actual_value(ghost, _maps(), "GamerLegion", "magic") is None
