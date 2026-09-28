"""CS2 shadow measurement: parsing Superbet's lines and grading them.

Item shapes are copied from Superbet's Ninjas in Pyjamas - GamerLegion offer
(2026-09-28); map, lineup and status shapes from Sofascore's magic -
GamerLegion (2026-09-26, 2-1: Dust2 13-6, Cache 8-13, Ancient 19-17 in
overtime), which dust2.us confirms map for map.
"""

from datetime import UTC, datetime, timedelta

import pytest

from bet.sofa.cs2 import (
    Cs2Line,
    MapResult,
    actual_value,
    build_map_result,
    build_series,
    esports_name,
    event_state,
    fair_probability,
    grade,
    latest_pre_kickoff,
    parse_event,
    parse_line,
    pick_event,
    settle_event,
    summarize,
)

T1, T2 = "Ninjas in Pyjamas", "GamerLegion"
KICKOFF = datetime(2026, 9, 26, 15, 0, tzinfo=UTC)


def item(
    market: str,
    name: str,
    price: float,
    spec: dict | None = None,
    info: str = "",
    **kw: object,
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


def one(market: str, name: str, spec: dict | None = None, info: str = "") -> Cs2Line:
    parsed = parse_line(item(market, name, 1.8, spec, info), "e1", T1, T2)
    assert parsed is not None, (market, name)
    return parsed


# --- parsing ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("market", "name", "spec", "info", "expected"),
    [
        (
            "Zwycięzca (z dogrywką)",
            "GamerLegion",
            None,
            "",
            ("match_winner", 0, "", None, "T2"),
        ),
        (
            "Mapa X - zwycięzca (z dogrywką)",
            "2. - Ninjas in Pyjamas",
            {"mapnr": "2"},
            "",
            ("map_winner", 2, "", None, "T1"),
        ),
        (
            "Liczba map",
            "powyżej 2.5",
            {"total": "2.5"},
            "",
            ("maps_total", 0, "", 2.5, "OVER"),
        ),
        (
            "Handicap map",
            "GamerLegion (1.5)",
            {"hcp": "-1.5"},
            "",
            ("maps_handicap", 0, "", -1.5, "T2"),
        ),
        (
            "Liczba rund (z dogrywką)",
            "Poniżej 87.5",
            {"total": "87.5"},
            "",
            ("rounds_total", 0, "", 87.5, "UNDER"),
        ),
        (
            "Handicap rund (z dogrywką)",
            "Ninjas in Pyjamas (4.5)",
            {"hcp": "4.5"},
            "",
            ("rounds_handicap", 0, "", 4.5, "T1"),
        ),
        (
            "Ninjas in Pyjamas liczba rund (z dogrywką)",
            "poniżej 43.5",
            {"total": "43.5"},
            "Ninjas in Pyjamas wygra poniże 43.5 rund w meczu (z dogrywką)",
            ("team_rounds", 0, T1, 43.5, "UNDER"),
        ),
        (
            "GamerLegion liczba map",
            "powyżej 1.5",
            {"total": "1.5"},
            "GamerLegion wygra powyżej 1.5 map w meczu",
            ("team_maps", 0, T2, 1.5, "OVER"),
        ),
        (
            "1.mapa - Liczba rund (z dogrywką)",
            "Powyżej 21.5",
            {"mapnr": "1", "total": "21.5"},
            "",
            ("map_rounds_total", 1, "", 21.5, "OVER"),
        ),
        (
            "2. mapa - Handicap rund (z dogrywką)",
            "GamerLegion (2.5)",
            {"hcp": "-2.5", "mapnr": "2"},
            "",
            ("map_rounds_handicap", 2, "", -2.5, "T2"),
        ),
        (
            "3.mapa - GamerLegion liczba rund (z dogrywką)",
            "poniżej 10.5",
            {"mapnr": "3", "total": "10.5"},
            "GamerLegion wygra poniżej 10.5 rund na 3. mapie",
            ("map_team_rounds", 3, T2, 10.5, "UNDER"),
        ),
        (
            "1.mapa - GamerLegion - liczba zabójstw (z dogrywką)",
            "powyżej 69.5",
            {"total": "69.5"},
            "",
            ("team_kills", 1, T2, 69.5, "OVER"),
        ),
        (
            "1.mapa - liczba zabójstw zawodnika (z dogrywką)",
            "FL4MUS - poniżej 16.5",
            {"player": "FL4MUS", "total": "16.5"},
            "",
            ("player_kills", 1, "FL4MUS", 16.5, "UNDER"),
        ),
        (
            "2.mapa - liczba śmierci zawodnika (z dogrywką)",
            "REZ - powyżej 15.5",
            {"player": "REZ", "total": "15.5"},
            "",
            ("player_deaths", 2, "REZ", 15.5, "OVER"),
        ),
        (
            "3.mapa - liczba headshotów zawodnika (z dogrywką)",
            "Snax - powyżej 8.5",
            {"player": "Snax", "total": "8.5"},
            "",
            ("player_headshots", 3, "Snax", 8.5, "OVER"),
        ),
        (
            "1.mapa - liczba asyst zawodnika (z dogrywką)",
            "Krimbo - poniżej 5.5",
            {"player": " Krimbo ", "total": "5.5"},
            "Krimbo Poniżej 5.5 asyst na 1.mapie",
            ("player_assists", 1, "Krimbo", 5.5, "UNDER"),
        ),
    ],
)
def test_every_family_parses_from_superbets_own_shape(
    market: str, name: str, spec: dict | None, info: str, expected: tuple
) -> None:
    ln = one(market, name, spec, info)
    assert (ln.family, ln.map_nr, ln.subject, ln.line, ln.side) == expected


@pytest.mark.parametrize(
    ("market", "name", "spec", "kw"),
    [
        ("Boost", "1.mapa - FL4MUS powyżej 16.5 zabójstw", {"player": "FL4MUS"}, {}),
        (
            "Ninjas in Pyjamas wygra 1. mapę; Snax powyżej 12.5 zabójstw na 1. mapie",
            "x",
            None,
            {},
        ),
        (
            "1. mapa - liczba zabójstw z AWP zawodnika (z dogrywką)",
            "hypex - poniżej 6.5",
            {"player": "hypex", "total": "6.5"},
            {},
        ),
        ("Dokładny wynik", "2:0", None, {}),
        ("1. mapa - 1. runda - zwycięzca", "Ninjas in Pyjamas", None, {}),
        (
            "1.mapa - Zwycięzca i liczba rund (z dogrywką)",
            "Ninjas in Pyjamas i powyżej 20.5",
            {"mapnr": "1", "total": "20.5"},
            {},
        ),
        ("Liczba map", "powyżej 2.5", {"total": "2.5"}, {"tags": "price_boost,v2"}),
        ("Liczba map", "powyżej 2.5", {"total": "2.5"}, {"status": "suspended"}),
        ("Liczba map", "powyżej 2.5", {"total": "2.5"}, {"price": 1.0}),
        ("Liczba map", "2.5", {"total": "2.5"}, {}),  # no direction word
    ],
)
def test_what_cannot_be_graded_or_is_not_the_price_is_dropped(
    market: str, name: str, spec: dict | None, kw: dict
) -> None:
    raw = {**item(market, name, 1.8, spec), **kw}
    assert parse_line(raw, "e1", T1, T2) is None


def test_the_longer_team_name_wins_when_one_contains_the_other() -> None:
    ln = parse_line(
        item("Zwycięzca (z dogrywką)", "Team X Academy", 1.8),
        "e",
        "Team X",
        "Team X Academy",
    )
    assert ln is not None and ln.side == "T2"


def test_only_complete_unambiguous_pairs_survive() -> None:
    maps = [
        item("Liczba map", "poniżej 2.5", 2.0, {"total": "2.5"}),
        item("Liczba map", "powyżej 2.5", 1.7, {"total": "2.5"}),
        item("Liczba map", "poniżej 3.5", 1.1, {"total": "3.5"}),
    ]
    dup = [
        item("Liczba rund (z dogrywką)", "Poniżej 45.5", 1.9, {"total": "45.5"}),
        item("Liczba rund (z dogrywką)", "Poniżej 45.5", 1.8, {"total": "45.5"}),
        item("Liczba rund (z dogrywką)", "Powyżej 45.5", 1.9, {"total": "45.5"}),
    ]
    lines = parse_event(maps + dup, "e1", T1, T2)
    assert {(ln.family, ln.line, ln.side) for ln in lines} == {
        ("maps_total", 2.5, "UNDER"),
        ("maps_total", 2.5, "OVER"),
    }


def test_esports_name_folds_without_football_rewrites() -> None:
    assert esports_name("BIG Academy") == "big academy"  # no "(r)" marker
    assert esports_name(" -proHor ") == "prohor"
    assert esports_name("Vålerenga") == "valerenga"
    assert esports_name("Praga Esports") == "praga esports"  # no exonym rewrite


def test_fair_probability_uses_the_pipelines_devig() -> None:
    p = fair_probability(1.8, 2.0)
    assert p is not None and 0.5 < p < 1 / 1.8


# --- snapshots ---------------------------------------------------------------


def snap(at: str, kickoff: str, odds: float) -> dict:
    lines = [
        Cs2Line("e1", "maps_total", 0, "", 2.5, "OVER", odds).as_dict(),
        Cs2Line("e1", "maps_total", 0, "", 2.5, "UNDER", 1.9).as_dict(),
    ]
    return {
        "fetched_at_utc": at,
        "superbet_event_id": "e1",
        "match_name": "A·B",
        "team1": "A",
        "team2": "B",
        "kickoff_utc": kickoff,
        "lines": lines,
    }


def test_the_last_price_before_the_start_is_kept() -> None:
    evs = latest_pre_kickoff(
        [
            snap("2026-09-26T10:00:00Z", "2026-09-26T15:00:00Z", 1.70),
            snap("2026-09-26T14:30:00Z", "2026-09-26T15:00:00Z", 1.80),
            snap("2026-09-26T15:10:00Z", "2026-09-26T15:00:00Z", 3.00),  # in play
        ]
    )
    over = evs["e1"].sides[("maps_total", 0, "", 2.5, "OVER")]
    assert over.odds == 1.80
    assert (
        evs["e1"].fetched_at[("maps_total", 0, "", 2.5, "OVER")]
        == "2026-09-26T14:30:00Z"
    )


def test_a_rescheduled_series_keeps_its_newest_kickoff() -> None:
    evs = latest_pre_kickoff(
        [
            snap("2026-09-26T10:00:00Z", "2026-09-26T12:00:00Z", 1.70),
            snap("2026-09-26T13:00:00Z", "2026-09-26T18:00:00Z", 1.90),  # delayed
        ]
    )
    assert evs["e1"].kickoff_utc == "2026-09-26T18:00:00Z"
    assert evs["e1"].sides[("maps_total", 0, "", 2.5, "OVER")].odds == 1.90


# --- finding the series ------------------------------------------------------------


def sofa_event(
    eid: int, home: str, away: str, start: datetime, category: str = "Counter Strike"
) -> dict:
    return {
        "id": eid,
        "startTimestamp": int(start.timestamp()),
        "homeTeam": {"name": home},
        "awayTeam": {"name": away},
        "tournament": {"category": {"name": category}},
    }


def test_pick_event_orients_and_filters() -> None:
    lol = sofa_event(1, T1, T2, KICKOFF, category="LoL")
    far = sofa_event(2, T1, T2, KICKOFF + timedelta(hours=9))
    other = sofa_event(3, T1, "Astralis", KICKOFF)
    right = sofa_event(
        4, "GamerLegion", "Ninjas in Pyjamas", KICKOFF + timedelta(minutes=40)
    )
    hit = pick_event([lol, far, other, right], T1, T2, KICKOFF)
    assert hit is not None and hit != "AMBIGUOUS"
    event, home_is_t1 = hit
    assert event["id"] == 4 and home_is_t1 is False


def test_two_fitting_series_are_ambiguous_not_a_coin_toss() -> None:
    a = sofa_event(1, T1, T2, KICKOFF)
    b = sofa_event(2, T1, T2, KICKOFF + timedelta(hours=2))
    assert pick_event([a, b], T1, T2, KICKOFF) == "AMBIGUOUS"
    assert pick_event([a, a], T1, T2, KICKOFF) != "AMBIGUOUS"  # one id, listed twice


# --- the result ------------------------------------------------------------------


def status(kind: str, description: str = "Ended") -> dict:
    return {"status": {"type": kind, "description": description}}


@pytest.mark.parametrize(
    ("detail", "hours_after", "expected"),
    [
        (status("finished"), 5, "FINISHED"),
        (status("finished", "Walkover"), 5, "UNUSUAL"),
        (status("canceled", "Canceled"), 5, "VOID"),
        (status("inprogress", "Map 3"), 5, "PENDING"),
        (status("inprogress", "Map 3"), 49, "PENDING"),  # stale, not unplayed
        (status("notstarted", "Not started"), 49, "VOID"),
        (status("postponed", "Postponed"), 20, "PENDING"),
    ],
)
def test_event_state_follows_superbets_rules(
    detail: dict, hours_after: int, expected: str
) -> None:
    assert (
        event_state(detail, KICKOFF, KICKOFF + timedelta(hours=hours_after)) == expected
    )


def game(gid: int, start: int, home: int, away: int, kind: str = "finished") -> dict:
    return {
        "id": gid,
        "startTimestamp": start,
        "status": {"type": kind},
        "homeScore": {"display": home},
        "awayScore": {"display": away},
    }


MAGIC_GL = {"homeScore": {"current": 2}, "awayScore": {"current": 1}}  # magic home
GAMES = [game(12, 2000, 8, 13), game(11, 1000, 13, 6), game(13, 3000, 19, 17)]
ANCIENT_LINEUPS = {
    "homeTeamPlayers": [
        {
            "player": {"name": "sFade8"},
            "kills": 32,
            "deaths": 28,
            "assists": 4,
            "headshots": 14,
        }
    ],
    "awayTeamPlayers": [
        {
            "player": {"name": "REZ"},
            "kills": 28,
            "deaths": 27,
            "assists": 6,
            "headshots": 12,
        }
    ],
}


def series(home_is_t1: bool = False) -> list[MapResult]:
    # Superbet lists it "GamerLegion·magic": team1 is Sofascore's away side.
    maps = build_series(MAGIC_GL, GAMES, {13: ANCIENT_LINEUPS}, home_is_t1)
    assert maps is not None
    return maps


def test_maps_are_in_played_order_and_oriented_to_team1() -> None:
    maps = series()
    assert [(m.t1_rounds, m.t2_rounds) for m in maps] == [(6, 13), (13, 8), (17, 19)]
    assert ("T1", "rez") in maps[2].players
    assert ("T2", "sfade8") in maps[2].players


def test_maps_that_do_not_reproduce_the_series_score_are_refused() -> None:
    assert build_series(MAGIC_GL, GAMES[:2], {}, False) is None  # 1-1 against 2-1
    bad = [*GAMES[:2], game(13, 3000, 19, 17, kind="inprogress")]
    assert build_series(MAGIC_GL, bad, {}, False) is None
    assert build_series(MAGIC_GL, [], {}, False) is None


TEAM1, TEAM2 = "GamerLegion", "magic"


@pytest.mark.parametrize(
    ("line", "actual", "outcome"),
    [
        (Cs2Line("e", "match_winner", 0, "", None, "T2", 2.0), -1.0, "WIN"),
        (Cs2Line("e", "maps_handicap", 0, "", 1.5, "T1", 1.3), -1.0, "WIN"),
        (Cs2Line("e", "maps_total", 0, "", 2.5, "OVER", 2.1), 3.0, "WIN"),
        (Cs2Line("e", "team_maps", 0, TEAM1, 0.5, "OVER", 1.2), 1.0, "WIN"),
        (Cs2Line("e", "rounds_total", 0, "", 70.5, "OVER", 1.9), 76.0, "WIN"),
        (Cs2Line("e", "rounds_handicap", 0, "", 4.5, "T1", 1.9), -4.0, "WIN"),
        (Cs2Line("e", "team_rounds", 0, TEAM2, 40.5, "UNDER", 1.9), 40.0, "WIN"),
        (Cs2Line("e", "map_winner", 3, "", None, "T1", 1.9), -2.0, "LOSS"),
        (Cs2Line("e", "map_rounds_total", 3, "", 21.5, "OVER", 1.9), 36.0, "WIN"),
        (Cs2Line("e", "map_rounds_handicap", 1, "", 6.5, "T1", 1.9), -7.0, "LOSS"),
        (Cs2Line("e", "map_team_rounds", 2, TEAM1, 12.5, "OVER", 1.9), 13.0, "WIN"),
        (Cs2Line("e", "player_kills", 3, "REZ", 25.5, "OVER", 1.9), 28.0, "WIN"),
        (Cs2Line("e", "player_deaths", 3, "sfade8", 27.5, "UNDER", 1.9), 28.0, "LOSS"),
        (Cs2Line("e", "player_headshots", 3, "REZ", 12.5, "UNDER", 1.9), 12.0, "WIN"),
        (Cs2Line("e", "player_assists", 3, "REZ", 6.0, "OVER", 1.9), 6.0, "VOID"),
    ],
)
def test_every_family_grades_from_the_series(
    line: Cs2Line, actual: float, outcome: str
) -> None:
    got = actual_value(line, series(), TEAM1, TEAM2)
    assert got == actual
    assert grade(line, got) == outcome


def test_what_superbet_voids_is_not_graded() -> None:
    maps = series()
    fourth = Cs2Line("e", "map_rounds_total", 4, "", 21.5, "OVER", 1.9)
    absent = Cs2Line("e", "player_kills", 3, "Snax", 15.5, "OVER", 1.9)
    no_rows = Cs2Line("e", "player_kills", 1, "REZ", 15.5, "OVER", 1.9)
    short_team = Cs2Line("e", "team_kills", 3, TEAM1, 60.5, "OVER", 1.9)
    for ln in (fourth, absent, no_rows, short_team):
        assert actual_value(ln, maps, TEAM1, TEAM2) is None, ln


def test_team_kills_needs_the_whole_team_and_sums_it() -> None:
    rows = [{"player": {"name": f"p{i}"}, "kills": 10 + i} for i in range(5)]
    mp = build_map_result(game(1, 1, 13, 11), {"homeTeamPlayers": rows}, True)
    assert mp is not None
    ln = Cs2Line("e", "team_kills", 1, TEAM1, 59.5, "OVER", 1.9)
    assert actual_value(ln, [mp], TEAM1, TEAM2) == 60.0


def test_settle_event_grades_both_sides_or_neither() -> None:
    ev = latest_pre_kickoff(
        [snap("2026-09-26T10:00:00Z", "2026-09-26T15:00:00Z", 1.8)]
    )["e1"]
    maps = series()
    rows, counts = settle_event(ev, maps)
    assert sorted(r["outcome"] for r in rows) == ["LOSS", "WIN"]  # 3 maps: OVER wins
    assert all(r["fair_p"] is not None for r in rows)
    del ev.sides[("maps_total", 0, "", 2.5, "UNDER")]
    rows, counts = settle_event(ev, maps)
    assert rows == [] and counts["unpaired"] == 1


def test_summarize_is_the_arithmetic_it_claims() -> None:
    rows = [
        {
            "superbet_event_id": "a",
            "odds": 2.0,
            "partner_odds": 1.8,
            "fair_p": 0.48,
            "outcome": "WIN",
        },
        {
            "superbet_event_id": "a",
            "odds": 1.8,
            "partner_odds": 2.0,
            "fair_p": 0.52,
            "outcome": "LOSS",
        },
    ]
    s = summarize(rows, "x")
    assert s is not None
    assert (s.events, s.sides, s.hit) == (1, 2, 0.5)
    assert s.fair_p == pytest.approx(0.5)
    assert s.roi == pytest.approx(0.0)  # +1.0 and -1.0
    assert s.brier == pytest.approx((0.52**2 + 0.52**2) / 2)
    assert s.margin == pytest.approx(1 / 2.0 + 1 / 1.8 - 1)
    assert summarize([], "x") is None


# --- review findings (2026-09-28) ------------------------------------------------


@pytest.mark.parametrize(
    "market",
    [
        "1.mapa - Liczba rund w 1. połowie",
        "1.mapa - Liczba rund",
        "1.mapa - GamerLegion liczba rund w 1. połowie",
        "1.mapa - Handicap rund w 1. połowie",
        "1.mapa - liczba zabójstw zawodnika w 1. połowie",
        "1.mapa - GamerLegion - liczba zabójstw w 1. połowie",
    ],
)
def test_map_markets_without_overtime_are_not_read_as_whole_maps(market: str) -> None:
    """Finding 2: prefix regexes graded half and regulation-only markets
    against whole maps with overtime."""
    raw = item(
        market,
        "GamerLegion (-2.5) powyżej 12.5",
        1.8,
        {"total": "12.5", "hcp": "-2.5", "player": "REZ"},
    )
    assert parse_line(raw, "e1", T1, T2) is None


def test_contained_names_orient_on_the_exact_name_not_a_tie() -> None:
    """Finding 1: "team spirit" scored 100 against "team spirit academy" both
    ways round, and the tie picked 'straight' - reversing every team line."""
    ev = sofa_event(1, "Team Spirit Academy", "Team Spirit", KICKOFF)
    hit = pick_event([ev], "Team Spirit", "Team Spirit Academy", KICKOFF)
    assert hit == (ev, False)  # Sofascore's home is Superbet's team2
    academy = sofa_event(2, "Sprout", "BIG Academy", KICKOFF)
    assert pick_event([academy], "BIG", "Sprout", KICKOFF) is None


def test_distinct_names_still_orient_both_ways() -> None:
    ev = sofa_event(1, "Team Spirit Academy", "Sprout", KICKOFF)
    hit = pick_event([ev], "Sprout", "Team Spirit Academy", KICKOFF)
    assert hit is not None and hit != "AMBIGUOUS" and hit[1] is False


def test_a_missing_kills_field_is_not_zero_kills() -> None:
    """Finding 5."""
    rows = [{"player": {"name": f"p{i}"}, "kills": 20} for i in range(4)]
    rows.append({"player": {"name": "p4"}})
    mp = build_map_result(game(1, 1, 13, 11), {"homeTeamPlayers": rows}, True)
    assert mp is not None
    ln = Cs2Line("e", "team_kills", 1, TEAM1, 85.5, "OVER", 1.9)
    assert actual_value(ln, [mp], TEAM1, TEAM2) is None


@pytest.mark.parametrize(
    ("name", "hcp", "ok"),
    [
        ("Ninjas in Pyjamas (-1.5)", "-1.5", True),
        ("GamerLegion (1.5)", "-1.5", True),
        ("GamerLegion (-1.5)", "-1.5", False),
        ("Ninjas in Pyjamas (1.5)", "-1.5", False),
        ("GamerLegion", "-1.5", False),
    ],
)
def test_a_handicap_name_must_agree_with_its_specifier(
    name: str, hcp: str, ok: bool
) -> None:
    """Finding 7."""
    raw = item("Handicap map", name, 1.8, {"hcp": hcp})
    assert (parse_line(raw, "e1", T1, T2) is not None) is ok


def test_a_winner_market_with_a_draw_is_dropped_whole() -> None:
    """Finding 8: a three-way market devigged as two-way."""
    items = [
        item("Zwycięzca (z dogrywką)", "Ninjas in Pyjamas", 2.4),
        item("Zwycięzca (z dogrywką)", "GamerLegion", 2.2),
        item("Zwycięzca (z dogrywką)", "Remis", 4.0),
    ]
    assert parse_event(items, "e1", T1, T2) == []
    two_way = items[:2]
    assert len(parse_event(two_way, "e1", T1, T2)) == 2


def test_stats_missing_only_for_player_lines_on_played_maps() -> None:
    from bet.sofa.cs2 import SnapshotEvent, stats_missing

    maps = [MapResult(13, 10, {}), MapResult(13, 5, {("T1", "rez"): {"kills": 9}})]
    ev = SnapshotEvent("e", "A·B", "A", "B", "2026-09-26T15:00:00Z", None)
    ev.sides[("player_kills", 2, "REZ", 9.5, "OVER")] = Cs2Line(
        "e", "player_kills", 2, "REZ", 9.5, "OVER", 1.9
    )
    ev.sides[("player_kills", 3, "REZ", 9.5, "OVER")] = Cs2Line(
        "e", "player_kills", 3, "REZ", 9.5, "OVER", 1.9
    )  # map 3 not played
    assert stats_missing(ev, maps) is False
    ev.sides[("player_kills", 1, "REZ", 9.5, "OVER")] = Cs2Line(
        "e", "player_kills", 1, "REZ", 9.5, "OVER", 1.9
    )
    assert stats_missing(ev, maps) is True


# --- review round 2 (2026-09-28) -------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Masonic", "Masonic Esports"),
        ("33", "33 Esports"),
        ("MASQ", "Masq Esports"),
        ("Nemiga", "Nemiga Gaming"),
        ("Team Spirit", "Spirit"),
    ],
)
def test_organisation_affixes_do_not_block_a_match(a: str, b: str) -> None:
    """R1: the affix-blind scorer rejected these once token_set was dropped."""
    ev = sofa_event(1, b, "Astralis", KICKOFF)
    hit = pick_event([ev], a, "Astralis", KICKOFF)
    assert hit == (ev, True)


def test_academy_is_still_a_different_roster() -> None:
    ev = sofa_event(1, "BIG Academy", "Astralis", KICKOFF)
    assert pick_event([ev], "BIG", "Astralis", KICKOFF) is None


def test_a_dead_copy_of_a_side_does_not_make_a_market_three_way() -> None:
    """R2."""
    spec = {"mapnr": "1"}
    pair = [
        item("Mapa X - zwycięzca (z dogrywką)", "1. - Ninjas in Pyjamas", 1.9, spec),
        item("Mapa X - zwycięzca (z dogrywką)", "1. - GamerLegion", 1.9, spec),
    ]
    for dead in ({"status": "suspended"}, {"tags": "price_boost,v2"}, {"price": 1.0}):
        copy = {
            **item("Mapa X - zwycięzca (z dogrywką)", "1. - Remis", 3.0, spec),
            **dead,
        }
        assert len(parse_event([*pair, copy], "e1", T1, T2)) == 2, dead


def test_one_nickname_on_both_rosters_grades_neither() -> None:
    """Round 2 (c): two 'snax' rows collided and one side's stats vanished."""
    home = [{"player": {"name": "Snax"}, "kills": 20}]
    away = [{"player": {"name": "snax"}, "kills": 10}]
    mp = build_map_result(
        game(1, 1, 13, 11), {"homeTeamPlayers": home, "awayTeamPlayers": away}, True
    )
    assert mp is not None and len(mp.players) == 2
    ln = Cs2Line("e", "player_kills", 1, "Snax", 14.5, "OVER", 1.9)
    assert actual_value(ln, [mp], TEAM1, TEAM2) is None
