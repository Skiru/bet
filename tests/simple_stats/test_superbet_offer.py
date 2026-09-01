"""SUPERBET: the operator's own book, and the traps in reading it.

Every test here is about a way this stage can be confidently wrong rather than
loudly broken, because that is the failure mode a betting artifact has. A price
mapped from the wrong Polish market name is still a number, still renders in
the table, and is still unplaceable at the counter.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bet.api_clients.superbet import (
    SuperbetClient,
    SuperbetConfig,
    SuperbetError,
    format_window,
    split_match_name,
)
from bet.simple_stats.contracts import (
    EventListV1,
    EventRecord,
    StatsSheetRow,
    StatsSheetV1,
    SuperbetEventOffer,
    SuperbetLine,
    SuperbetOfferV1,
)
from bet.simple_stats.superbet_offer import (
    attach_superbet_column,
    build_event_offer,
    classify_market,
    classify_player_market,
    collect_superbet_offer,
    compare_sheet_to_offer,
    default_window,
    fold,
    lookup_line,
    match_offer_events,
    normalize_lines,
    parse_outcome,
)

# --- fixtures ---------------------------------------------------------------


def make_event(
    event_id: str = "e1",
    sport: str = "football",
    home: str = "Remo",
    away: str = "Coritiba",
    start: str = "2026-08-31T23:00:00+00:00",
) -> EventRecord:
    if sport == "tennis":
        return EventRecord(
            event_id=event_id, sport="tennis", competition="ATP US Open",
            player_one=home, player_two=away, start_time=start,
            identity_confidence="CONFIRMED", status="ACTIVE",
        )
    return EventRecord(
        event_id=event_id, sport="football", competition="Brasileirao",
        home_team=home, away_team=away, start_time=start,
        identity_confidence="CONFIRMED", status="ACTIVE",
    )


def make_row(**kwargs) -> StatsSheetRow:
    base = dict(
        event_id="e1", sport="football", market="corners_total", line=8.5,
        direction="OVER", hits=19, sample_size=24, hit_rate=19 / 24, p_low=0.595,
        mean=10.5, median=10.0, sources=["bzzoiro"],
        cross_provider_agreement="AGREE", confidence="HIGH", data_quality="READY",
    )
    base.update(kwargs)
    return StatsSheetRow(**base)


def raw_odds(market_name: str, outcome: str, price: float, status: str = "active") -> dict:
    return {"marketName": market_name, "name": outcome, "price": price, "status": status}


# --- the Polish fold --------------------------------------------------------


def test_fold_maps_l_with_stroke_rather_than_deleting_it():
    """NFKD does not decompose ł, so the ascii fold deletes it outright.

    Every market name this module matches contains at least one ł. Without the
    explicit table "strzałów" folds to "strzaow" and the entire mapping matches
    nothing -- silently, because an unmapped market is a normal thing to see.
    """
    assert fold("Liczba strzałów") == "liczba strzalow"
    assert fold("1. połowa") == "1. polowa"
    assert fold("Liczba podwójnych błędów") == "liczba podwojnych bledow"
    assert fold("Iga Świątek") == "iga swiatek"


# --- market classification --------------------------------------------------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Liczba goli", ("goals_total", None)),
        ("Liczba rzutów rożnych", ("corners_total", None)),
        ("Liczba kartek", ("cards_total", None)),
        ("Liczba celnych strzałów", ("shots_on_target_total", None)),
        ("Liczba strzałów", ("shots_total", None)),
        ("Liczba spalonych", ("offsides_total", None)),
        ("Liczba fauli", ("fouls_total", None)),
        ("Liczba asów", ("aces_total", None)),
        ("Liczba podwójnych błędów", ("double_faults_total", None)),
        ("Liczba gemów", ("total_games", None)),
        ("Liczba setów", ("total_sets", None)),
        ("Remo - liczba kartek", ("cards_for", "remo")),
        ("Liczba celnych strzałów - Remo", ("shots_on_target_for", "remo")),
        ("Liczba strzałów Remo", ("shots_for", "remo")),
        ("Spalone - Remo", ("offsides_for", "remo")),
        ("Liczba fauli - Remo", ("fouls_for", "remo")),
    ],
)
def test_classify_market_maps_the_markets_the_sheet_prices(name, expected):
    assert classify_market(name) == expected


def test_woodwork_is_not_shots_on_target():
    """"Obramowanie bramki" is the frame of the goal, not the target.

    The first draft of this mapping matched on substrings and reported
    "Remo over 1.5 shots on target at 10.00" -- a shots-off-the-woodwork price
    wearing a shots-on-target label, which is a number an operator would
    happily stake against. This is the single most dangerous name in the feed.
    """
    assert classify_market("Remo - Liczba strzałów w obramowanie bramki") is None
    assert classify_market("Liczba strzałów w obramowanie bramki") is None


def test_goalkeeper_saves_are_not_shots():
    assert classify_market("Liczba obronionych strzałów przez bramkarza") is None
    assert classify_market("Coritiba - liczba obronionych strzałów przez bramkarza") is None


def test_combination_markets_never_map():
    """A name containing ';' is a pre-priced parlay, not a single outcome."""
    assert classify_market("Powyżej 2.5 gola w meczu; Powyżej 27.5 strzałów w meczu") is None
    assert classify_market("Poniżej 2.5 gola w meczu; Poniżej 8.5 rz.rożnych w meczu") is None


def test_period_scope_does_not_answer_a_full_match_query():
    assert classify_market("1. połowa - liczba celnych strzałów") is None
    assert classify_market("2. połowa - liczba fauli") is None
    assert classify_market("1. set - liczba gemów") is None
    # The two half-goal totals are mapped on purpose and must survive the ban.
    assert classify_market("1.połowa - liczba goli") == ("goals_1h_total", None)
    assert classify_market("2.połowa - liczba goli") == ("goals_2h_total", None)


def test_player_and_aggregate_markets_never_map():
    for name in (
        "Zawodnik - liczba strzałów",
        "Carrillo, Guido powyżej 0.5 celnych strzałów",
        "Każda z drużyn powyżej X kartek",
        "Którykolwiek z zawodników odda powyżej X strzałów",
        "Najwięcej celnych strzałów",
        "Dokładna liczba kartek",
        "Liczba rzutów rożnych - przedziały",
        "Nieparzysta/parzysta liczba rzutów rożnych",
        "Rzuty rożne handicap",
        "Liczba rzutów rożnych - H2H",
    ):
        assert classify_market(name) is None, name


def test_parse_outcome():
    assert parse_outcome("powyżej 8.5") == ("OVER", 8.5)
    assert parse_outcome("poniżej 12.5") == ("UNDER", 12.5)
    assert parse_outcome("poniżej 3,5") == ("UNDER", 3.5)
    assert parse_outcome("1") is None
    assert parse_outcome("Tak") is None
    assert parse_outcome(None) is None


# --- line normalisation -----------------------------------------------------


def test_normalize_lines_extracts_match_and_team_totals():
    raw = {
        "odds": [
            raw_odds("Liczba rzutów rożnych", "powyżej 8.5", 1.40),
            raw_odds("Liczba rzutów rożnych", "poniżej 8.5", 2.70),
            raw_odds("Remo - liczba kartek", "poniżej 2.5", 1.38),
            raw_odds("Remo - Liczba strzałów w obramowanie bramki", "powyżej 1.5", 10.0),
        ]
    }
    lines, _ = normalize_lines(raw, team_names=("Remo", "Coritiba"))
    got = {(line.market, line.line, line.direction, line.team_name): line.price for line in lines}
    assert got == {
        ("corners_total", 8.5, "OVER", None): 1.40,
        ("corners_total", 8.5, "UNDER", None): 2.70,
        ("cards_for", 2.5, "UNDER", "Remo"): 1.38,
    }


def test_team_lines_use_our_spelling_not_superbets():
    """Superbet writes "Estudiantes La Plata"; DISCOVER has "Estudiantes".

    A per-team line filed under the book's spelling joins to nothing, and the
    coverage counts then say the market is missing when it is on the screen.
    """
    raw = {"odds": [raw_odds("Estudiantes La Plata - liczba kartek", "poniżej 2.5", 1.5)]}
    lines, _ = normalize_lines(raw, team_names=("Estudiantes", "Newells Old Boys"))
    assert [line.team_name for line in lines] == ["Estudiantes"]


def test_ambiguous_team_containment_is_dropped_not_guessed():
    """Two sides sharing a token must not resolve by containment.

    Filing a per-team line against the wrong side of a derby is worse than
    having no per-team line: the number looks right and describes the opponent.
    """
    raw = {"odds": [raw_odds("Atletico - liczba kartek", "poniżej 2.5", 1.5)]}
    lines, _ = normalize_lines(raw, team_names=("Atletico Madryt", "Atletico Bilbao"))
    assert lines == []


def test_team_line_for_a_team_not_in_this_fixture_is_dropped():
    raw = {"odds": [raw_odds("Palmeiras - liczba kartek", "poniżej 2.5", 1.5)]}
    lines, _ = normalize_lines(raw, team_names=("Remo", "Coritiba"))
    assert lines == []


def test_best_price_wins_and_active_beats_blocked():
    raw = {
        "odds": [
            raw_odds("Liczba goli", "poniżej 2.5", 1.60),
            raw_odds("Liczba goli", "poniżej 2.5", 1.68),
            raw_odds("Liczba kartek", "poniżej 5.5", 9.99, status="block"),
            raw_odds("Liczba kartek", "poniżej 5.5", 1.85, status="active"),
        ]
    }
    lines, _ = normalize_lines(raw, team_names=("Remo", "Coritiba"))
    prices = {(line.market, line.status): line.price for line in lines}
    assert prices[("goals_total", "active")] == 1.68
    # The blocked 9.99 must never outrank the takeable 1.85 on price alone.
    assert prices[("cards_total", "active")] == 1.85


def test_price_of_one_or_below_is_not_a_price():
    raw = {"odds": [raw_odds("Liczba goli", "poniżej 6.5", 1.0)]}
    lines, _ = normalize_lines(raw, team_names=("Remo", "Coritiba"))
    assert lines == []


def test_unmapped_totals_are_reported_but_exotica_is_not():
    raw = {
        "odds": [
            raw_odds("Liczba odbiorów", "powyżej 30.5", 1.9),
            raw_odds("Zawodnik - liczba strzałów", "powyżej 0.5", 1.5),
        ]
    }
    _, unmapped = normalize_lines(raw, team_names=("Remo", "Coritiba"))
    assert unmapped == ["Liczba odbiorów"]


# --- fixture matching -------------------------------------------------------


def _offer_row(name: str, utc: str, sport_id: int = 5, event_id: int = 1, markets: int = 100):
    return {
        "eventId": event_id, "matchName": name, "utcDate": utc,
        "sportId": sport_id, "marketCount": markets, "odds": [],
    }


def test_match_on_participants_and_kickoff():
    events = EventListV1(generated_at="x", date="2026-08-31", events=[make_event()])
    rows = [_offer_row("Remo·Coritiba", "2026-08-31T23:00:00Z")]
    matched, unmatched, missing = match_offer_events(events, rows)
    assert list(matched) == ["e1"]
    assert matched["e1"]["delta_minutes"] == 0.0
    assert unmatched == [] and missing == []


def test_football_kickoff_drift_beyond_tolerance_is_not_the_same_fixture():
    events = EventListV1(generated_at="x", date="2026-08-31", events=[make_event()])
    rows = [_offer_row("Remo·Coritiba", "2026-09-01T04:00:00Z")]
    matched, unmatched, missing = match_offer_events(events, rows)
    assert matched == {}
    assert missing == ["e1"]
    assert len(unmatched) == 1


def test_tennis_tolerates_a_court_order_estimate():
    """Superbet had Dimitrov-Popyrin at 22:25 where we had 20:40. Same match.

    Tennis start times are court-order estimates. A football fixture moving 105
    minutes is a different fixture; a tennis one is an ordinary Monday.
    """
    events = EventListV1(
        generated_at="x", date="2026-08-31",
        events=[make_event("t1", "tennis", "Grigor Dimitrov", "Alexei Popyrin",
                           "2026-08-31T20:40:00+00:00")],
    )
    rows = [_offer_row("Grigor Dimitrov·Alexei Popyrin", "2026-08-31T22:25:00Z", sport_id=2)]
    matched, _, _ = match_offer_events(events, rows)
    assert list(matched) == ["t1"]
    assert matched["t1"]["delta_minutes"] == pytest.approx(105.0)


def test_participant_order_does_not_matter():
    events = EventListV1(generated_at="x", date="2026-08-31", events=[make_event()])
    rows = [_offer_row("Coritiba·Remo", "2026-08-31T23:00:00Z")]
    matched, _, _ = match_offer_events(events, rows)
    assert list(matched) == ["e1"]


def test_simulated_football_never_matches():
    """sportId 75 is FIFA sim: "Real Madryt (Liam)·Atletico Madryt (Alexis)".

    Those normalise to real club names once the parenthetical handle is
    stripped, so without the sport-id gate a player's console match can land on
    a betting sheet beside a real fixture.
    """
    events = EventListV1(
        generated_at="x", date="2026-08-31",
        events=[make_event("e2", home="Real Madryt", away="Atletico Madryt",
                           start="2026-08-31T20:30:00+00:00")],
    )
    rows = [_offer_row("Real Madryt (Liam)·Atletico Madryt (Alexis)",
                       "2026-08-31T20:30:00Z", sport_id=75)]
    matched, unmatched, missing = match_offer_events(events, rows)
    assert matched == {}
    assert missing == ["e2"]
    # Not reported as an unmatched Superbet fixture either: it is not football.
    assert unmatched == []


def test_duplicate_offer_rows_pick_the_closest_kickoff_then_the_richer_market():
    events = EventListV1(generated_at="x", date="2026-08-31", events=[make_event()])
    rows = [
        _offer_row("Remo·Coritiba", "2026-08-31T23:20:00Z", event_id=1, markets=900),
        _offer_row("Remo·Coritiba", "2026-08-31T23:00:00Z", event_id=2, markets=12),
    ]
    matched, unmatched, _ = match_offer_events(events, rows)
    assert matched["e1"]["raw"]["eventId"] == 2
    assert [row["eventId"] for row in unmatched] == [1]


def test_our_event_absent_from_the_book_is_reported():
    events = EventListV1(
        generated_at="x", date="2026-08-31",
        events=[make_event(), make_event("e2", home="Sutton", away="Wealdstone")],
    )
    matched, _, missing = match_offer_events(
        events, [_offer_row("Remo·Coritiba", "2026-08-31T23:00:00Z")]
    )
    assert list(matched) == ["e1"]
    assert missing == ["e2"]


# --- comparison -------------------------------------------------------------


def make_offer(lines: list[SuperbetLine], event_id: str = "e1") -> SuperbetOfferV1:
    return SuperbetOfferV1(
        generated_at="2026-08-31T21:00:00+00:00", date="2026-08-31",
        events=[
            SuperbetEventOffer(
                superbet_event_id="123", superbet_match_name="Remo·Coritiba",
                sport="football", kickoff="2026-08-31T23:00:00Z",
                event_id=event_id, match_quality="EXACT", lines=lines,
            )
        ],
    )


def sb_line(**kwargs) -> SuperbetLine:
    base = dict(
        market="corners_total", line=8.5, direction="OVER", price=1.40,
        source_market_name="Liczba rzutów rożnych", source_outcome_name="powyżej 8.5",
    )
    base.update(kwargs)
    return SuperbetLine(**base)


def _compare(rows, lines, **kwargs):
    sheet = StatsSheetV1(generated_at="x", date="2026-08-31", rows=rows)
    events = EventListV1(generated_at="x", date="2026-08-31", events=[make_event()])
    return compare_sheet_to_offer(
        sheet, make_offer(lines), events, generated_at="2026-08-31T21:00:00+00:00", **kwargs
    )


def test_value_when_the_book_pays_the_minimum():
    # p_low 0.595, AGREE, n=24 -> CALL, min = 1.05/0.595 = 1.7647
    result = _compare([make_row()], [sb_line(price=1.90)])
    row = result.rows[0]
    assert row.verdict == "VALUE"
    assert row.superbet_price == 1.90
    assert row.odds_surplus == pytest.approx(1.90 - row.min_acceptable_odds, abs=1e-4)


def test_priced_below_threshold_is_a_real_answer_not_a_gap():
    result = _compare([make_row()], [sb_line(price=1.40)])
    assert result.rows[0].verdict == "PRICED_BELOW_THRESHOLD"
    assert result.rows[0].superbet_price == 1.40


def test_line_not_offered_reports_the_nearest_rung():
    """The headline failure of 2026-08-31: our 4.5 against a ladder from 7.5."""
    row = make_row(market="shots_on_target_total", line=4.5, direction="OVER")
    ladder = [
        sb_line(market="shots_on_target_total", line=line, direction="OVER", price=price)
        for line, price in ((7.5, 1.53), (8.5, 1.95), (9.5, 2.52))
    ]
    result = _compare([row], ladder)
    got = result.rows[0]
    assert got.verdict == "LINE_NOT_OFFERED"
    assert got.nearest_offered_line == 7.5
    assert got.nearest_offered_price == 1.53
    assert got.superbet_price is None


def test_line_coverage_flags_a_market_with_no_overlap_at_all():
    rows = [
        make_row(market="shots_on_target_total", line=4.5, direction="OVER"),
        make_row(market="corners_total", line=8.5, direction="OVER"),
    ]
    lines = [
        sb_line(market="shots_on_target_total", line=7.5, direction="OVER", price=1.5),
        sb_line(market="corners_total", line=8.5, direction="OVER", price=1.4),
    ]
    result = _compare(rows, lines)
    assert result.line_coverage["football:shots_on_target_total"]["no_overlap"] is True
    assert result.line_coverage["football:corners_total"]["no_overlap"] is False


def test_market_not_offered_is_distinct_from_line_not_offered():
    row = make_row(market="fouls_total", line=20.5)
    result = _compare([row], [sb_line()])
    assert result.rows[0].verdict == "MARKET_NOT_OFFERED"
    assert result.rows[0].nearest_offered_line is None


def test_direction_is_part_of_the_lookup():
    """An over price must never answer an under row."""
    result = _compare([make_row(direction="UNDER")], [sb_line(direction="OVER", price=1.4)])
    assert result.rows[0].verdict == "MARKET_NOT_OFFERED"


def test_team_scope_is_part_of_the_lookup():
    row = make_row(market="corners_for", team_name="Remo", line=6.5, direction="UNDER")
    other = sb_line(market="corners_for", team_name="Coritiba", line=6.5,
                    direction="UNDER", price=1.48)
    result = _compare([row], [other])
    assert result.rows[0].verdict == "MARKET_NOT_OFFERED"


def test_suspended_outcome_is_not_a_price_to_bet():
    result = _compare([make_row()], [sb_line(price=1.90, status="block")])
    assert result.rows[0].verdict == "OUTCOME_SUSPENDED"
    assert result.rows[0].odds_surplus is None


def test_event_not_matched_is_distinct_from_market_missing():
    sheet = StatsSheetV1(generated_at="x", date="2026-08-31", rows=[make_row(event_id="zzz")])
    events = EventListV1(
        generated_at="x", date="2026-08-31",
        events=[make_event(), make_event("zzz", home="A", away="B")],
    )
    result = compare_sheet_to_offer(sheet, make_offer([sb_line()]), events)
    assert result.rows[0].verdict == "EVENT_NOT_MATCHED"


def test_unbettable_tiers_are_not_compared():
    """A DROP row has no minimum price, so it has nothing to compare against."""
    result = _compare([make_row(sample_size=2, hits=2, data_quality="PARTIAL")], [sb_line()])
    assert result.rows == []
    assert result.rows_considered == 0


def test_value_rows_sort_above_everything_else():
    rows = [
        make_row(event_id="e1", market="corners_total", line=8.5, p_low=0.90),
        make_row(event_id="e1", market="goals_total", line=2.5, p_low=0.50,
                 cross_provider_agreement="SINGLE_SOURCE"),
    ]
    lines = [
        sb_line(market="corners_total", line=8.5, price=1.05),
        sb_line(market="goals_total", line=2.5, price=9.00,
                source_market_name="Liczba goli"),
    ]
    result = _compare(rows, lines)
    assert result.rows[0].market == "goals_total"
    assert result.rows[0].verdict == "VALUE"


def test_comparison_is_reproducible_given_generated_at():
    first = _compare([make_row()], [sb_line(price=1.90)])
    second = _compare([make_row()], [sb_line(price=1.90)])
    assert first.model_dump() == second.model_dump()


def test_min_p_low_narrows_the_comparison():
    rows = [make_row(p_low=0.20, market="goals_total"), make_row(p_low=0.80)]
    result = _compare(rows, [sb_line()], min_p_low=0.5)
    assert result.rows_considered == 1


# --- the stats-sheet column -------------------------------------------------


def test_attach_column_is_total_over_rows():
    sheet = StatsSheetV1(
        generated_at="x", date="2026-08-31",
        rows=[make_row(), make_row(market="fouls_total", line=20.5)],
    )
    attached = attach_superbet_column(sheet, make_offer([sb_line(price=1.9)]))
    assert [row.superbet.availability for row in attached.rows] == [
        "OFFERED", "MARKET_NOT_OFFERED",
    ]
    assert attached.rows[0].superbet.price == 1.9
    assert attached.rows[0].superbet.superbet_event_id == "123"


def test_attach_column_does_not_mutate_the_input_sheet():
    sheet = StatsSheetV1(generated_at="x", date="2026-08-31", rows=[make_row()])
    attach_superbet_column(sheet, make_offer([sb_line()]))
    assert sheet.rows[0].superbet is None


def test_lookup_line_with_no_offer_says_so():
    assert lookup_line(None, market="goals_total", line=2.5, direction="OVER",
                       team_name=None)[0] == "EVENT_NOT_MATCHED"


# --- client -----------------------------------------------------------------


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeTransport:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params or {}))
        return self._responses.pop(0)


def test_format_window_is_the_shape_by_date_wants():
    assert format_window(datetime(2026, 8, 31, 20, 35, tzinfo=UTC)) == "2026-08-31 20:35:00"
    # A naive datetime is treated as UTC rather than local: a betting day is UTC.
    assert format_window(datetime(2026, 8, 31, 20, 35)) == "2026-08-31 20:35:00"


def test_split_match_name_uses_the_middle_dot():
    assert split_match_name("Remo·Coritiba") == ("Remo", "Coritiba")
    assert split_match_name("Remo") == ("Remo", "")
    assert split_match_name(None) == ("", "")


def test_client_unwraps_the_envelope():
    transport = FakeTransport([FakeResponse({"error": False, "data": [{"eventId": 1}]})])
    client = SuperbetClient(SuperbetConfig(max_retries=0), transport=transport)
    rows = client.events_by_date(
        datetime(2026, 8, 31, tzinfo=UTC), datetime(2026, 9, 1, tzinfo=UTC)
    )
    assert rows == [{"eventId": 1}]
    assert client.request_count == 1


def test_client_treats_error_true_as_a_refusal_even_on_200():
    transport = FakeTransport([FakeResponse({"error": True, "data": []})])
    client = SuperbetClient(SuperbetConfig(max_retries=0), transport=transport)
    with pytest.raises(SuperbetError):
        client.event_odds(1)


def test_client_raises_on_http_error():
    transport = FakeTransport([FakeResponse({}, status_code=500)])
    client = SuperbetClient(SuperbetConfig(max_retries=0), transport=transport)
    with pytest.raises(SuperbetError) as excinfo:
        client.event_odds(1)
    assert excinfo.value.http_status == 500


def test_event_odds_reads_the_single_element_list():
    """The endpoint returns a list, not an object. Treating it as an object
    raises on every call, which is a total outage that looks like a network
    fault."""
    transport = FakeTransport([FakeResponse({"error": False, "data": [{"eventId": 7, "odds": []}]})])
    client = SuperbetClient(SuperbetConfig(max_retries=0), transport=transport)
    assert client.event_odds(7) == {"eventId": 7, "odds": []}


# --- the collector ----------------------------------------------------------


class FakeClient:
    def __init__(self, by_date, odds_by_id=None, odds_error=None):
        self._by_date = by_date
        self._odds = odds_by_id or {}
        self._odds_error = odds_error
        self.request_count = 0
        self.odds_calls: list[int] = []

    def events_by_date(self, start, end, offer_state="prematch"):
        self.request_count += 1
        if isinstance(self._by_date, Exception):
            raise self._by_date
        return self._by_date

    def event_odds(self, event_id):
        self.request_count += 1
        self.odds_calls.append(event_id)
        if self._odds_error:
            raise self._odds_error
        return self._odds.get(event_id)


def test_collect_only_prices_matched_fixtures():
    """The night window carries ~850 events, nearly all of them esports.

    One request per matched fixture; none for the rest. Fetching odds for a
    fixture the sheet has no row about spends a request to learn nothing.
    """
    events = EventListV1(generated_at="x", date="2026-08-31", run_id="r", events=[make_event()])
    rows = [
        _offer_row("Remo·Coritiba", "2026-08-31T23:00:00Z", event_id=11),
        _offer_row("Something·Else", "2026-08-31T23:00:00Z", event_id=12),
        _offer_row("Csgo Team A·Csgo Team B", "2026-08-31T23:00:00Z", sport_id=190, event_id=13),
    ]
    client = FakeClient(rows, {11: {**rows[0], "odds": [raw_odds("Liczba goli", "poniżej 2.5", 1.68)]}})
    offer = collect_superbet_offer(events, client=client, generated_at="t")
    assert client.odds_calls == [11]
    assert offer.events_matched == 1
    assert offer.events_on_offer == 3
    assert offer.events[0].lines[0].market == "goals_total"


def test_collect_survives_a_dead_offer_host():
    events = EventListV1(generated_at="x", date="2026-08-31", events=[make_event()])
    offer = collect_superbet_offer(
        events, client=FakeClient(SuperbetError("unknown domain")), generated_at="t"
    )
    assert offer.events == []
    assert offer.data_gaps and "unknown domain" in offer.data_gaps[0]


def test_collect_survives_one_dead_fixture():
    """One fixture's odds call failing is a gap, not a dead run."""
    events = EventListV1(generated_at="x", date="2026-08-31", events=[make_event()])
    rows = [_offer_row("Remo·Coritiba", "2026-08-31T23:00:00Z", event_id=11)]
    client = FakeClient(rows, odds_error=SuperbetError("HTTP 503"))
    offer = collect_superbet_offer(events, client=client, generated_at="t")
    assert offer.events_matched == 1
    assert offer.data_gaps


def test_collect_cap_reports_the_fixtures_it_did_not_price():
    events = EventListV1(
        generated_at="x", date="2026-08-31",
        events=[
            make_event("e1", start="2026-08-31T20:00:00+00:00"),
            make_event("e2", home="Sutton", away="Wealdstone", start="2026-08-31T23:00:00+00:00"),
        ],
    )
    rows = [
        _offer_row("Remo·Coritiba", "2026-08-31T20:00:00Z", event_id=11),
        _offer_row("Sutton·Wealdstone", "2026-08-31T23:00:00Z", event_id=12),
    ]
    offer = collect_superbet_offer(
        events, client=FakeClient(rows), max_events=1, generated_at="t"
    )
    assert offer.events_matched == 1
    assert "e2" in offer.our_events_without_offer
    assert any("capped at 1" in gap for gap in offer.data_gaps)


def test_default_window_runs_past_midnight():
    """South-American football and the US Open night session both run past
    00:00 UTC on the betting day they belong to."""
    start, end = default_window("2026-08-31")
    assert start.isoformat() == "2026-08-31T00:00:00+00:00"
    assert end.isoformat() == "2026-09-01T06:00:00+00:00"


def test_build_event_offer_flags_a_fuzzy_kickoff():
    raw = _offer_row("Remo·Coritiba", "2026-08-31T23:30:00Z")
    offer = build_event_offer(raw, event=make_event(), delta_minutes=30.0)
    assert offer.match_quality == "FUZZY"
    assert offer.kickoff_delta_minutes == 30.0
    offer_exact = build_event_offer(raw, event=make_event(), delta_minutes=0.0)
    assert offer_exact.match_quality == "EXACT"


# --- the new verdicts and the two-pass matcher -----------------------------


def test_a_matched_fixture_pricing_nothing_is_not_a_market_gap():
    """A finished fixture is still in the by-date feed with zero markets.

    Reading that as "this market is missing" made 52 finished fixtures look
    like 12,000 missing markets on the first live run, which buried the
    genuine coverage problem underneath them.
    """
    offer = SuperbetOfferV1(
        generated_at="x", date="2026-08-31",
        events=[SuperbetEventOffer(
            superbet_event_id="1", superbet_match_name="Remo·Coritiba", sport="football",
            kickoff="2026-08-31T23:00:00Z", event_id="e1", match_quality="EXACT",
            lines=[], status="FINISHED",
        )],
    )
    sheet = StatsSheetV1(generated_at="x", date="2026-08-31", rows=[make_row()])
    events = EventListV1(generated_at="x", date="2026-08-31", events=[make_event()])
    result = compare_sheet_to_offer(sheet, offer, events)
    assert result.rows[0].verdict == "OFFER_EMPTY"


def test_a_prop_the_book_does_not_price_for_this_player_is_ours_to_report():
    """Superbet prices player props heavily and this pipeline reads them now.

    The row below has no matching Superbet player string, so the answer is
    PLAYER_NOT_MATCHED -- our join failing -- and never MARKET_NOT_OFFERED,
    which would blame the book for a gap that is ours.
    """
    row = make_row(market="player_total_shots", line=1.5, player_name="Alef Manga",
                   player_id="p1", lineup_status="predicted")
    result = _compare([row], [sb_line()])
    assert result.rows[0].verdict == "PLAYER_NOT_MATCHED"


def test_a_caller_that_passes_no_alias_map_still_gets_the_old_answer():
    """``lookup_line`` must not start blaming the book just because a caller
    has not been taught to resolve players yet."""
    assert lookup_line(None, market="player_fouls", line=1.5, direction="UNDER",
                       team_name=None)[0] == "SCOPE_NOT_SUPPORTED"


def test_player_market_with_an_alias_map_but_no_fixture_is_not_matched():
    assert lookup_line(None, market="player_fouls", line=1.5, direction="UNDER",
                       team_name=None, player_name="X",
                       player_aliases={})[0] == "EVENT_NOT_MATCHED"


@pytest.mark.parametrize(
    "ours,theirs,expected",
    [
        ("estudiantes", "estudiantes la plata", True),
        ("la serena", "deportes la serena", True),
        ("newells old boys", "newells old boys", True),
        ("inter", "inter turku", True),
        # Two clubs sharing one token are not the same club.
        ("inter miami", "inter turku", False),
        ("atletico madryt", "atletico bilbao", False),
        ("remo", "coritiba", False),
        ("", "remo", False),
    ],
)
def test_sides_compatible(ours, theirs, expected):
    from bet.simple_stats.superbet_offer import sides_compatible

    assert sides_compatible(ours, theirs) is expected


def test_pass_two_recovers_a_club_long_form():
    """"Estudiantes" vs "Estudiantes La Plata" cost a real fixture on the first
    live run, and the fixture was on the screen the whole time."""
    events = EventListV1(
        generated_at="x", date="2026-08-31",
        events=[make_event("e1", home="Estudiantes", away="Newells Old Boys",
                           start="2026-08-31T22:00:00+00:00")],
    )
    rows = [_offer_row("Estudiantes La Plata·Newell's Old Boys", "2026-08-31T22:00:00Z")]
    matched, _, missing = match_offer_events(events, rows)
    assert list(matched) == ["e1"]
    assert missing == []


def test_pass_two_refuses_when_two_of_our_events_could_claim_it():
    """DISCOVER can hold the same fixture twice under two spellings.

    When it does, a tolerant match is a coin flip between them, and the right
    answer is to match neither -- pricing one of a duplicated pair would put
    the same bet on the sheet twice with only one of them carrying a price.
    """
    events = EventListV1(
        generated_at="x", date="2026-08-31",
        events=[
            make_event("e1", home="Inter Turku", away="Kuopion Palloseura",
                       start="2026-08-31T16:00:00+00:00"),
            make_event("e2", home="FC Inter Turku", away="Kuopion Palloseura",
                       start="2026-08-31T16:00:00+00:00"),
        ],
    )
    rows = [_offer_row("Inter Turku·KuPS Kuopio", "2026-08-31T16:00:00Z")]
    matched, _, missing = match_offer_events(events, rows)
    assert matched == {}
    assert sorted(missing) == ["e1", "e2"]


def test_pass_two_still_respects_the_kickoff_tolerance():
    events = EventListV1(
        generated_at="x", date="2026-08-31",
        events=[make_event("e1", home="Estudiantes", away="Newells Old Boys",
                           start="2026-08-31T22:00:00+00:00")],
    )
    rows = [_offer_row("Estudiantes La Plata·Newell's Old Boys", "2026-09-01T04:00:00Z")]
    matched, _, missing = match_offer_events(events, rows)
    assert matched == {}
    assert missing == ["e1"]


def test_a_started_fixture_absent_from_the_book_is_not_a_matching_failure():
    """``offerState=prematch`` drops a fixture the moment it goes live.

    A run started after the first kickoff will always find some of its own
    fixtures missing, and reading that as a matcher defect sends somebody
    hunting a bug in the one part of this that was working.
    """
    events = EventListV1(
        generated_at="x", date="2026-08-31", run_id="r",
        events=[make_event("e1", start="2026-08-31T18:00:00+00:00")],
    )
    offer = collect_superbet_offer(
        events, client=FakeClient([]), generated_at="t",
        now=datetime(2026, 8, 31, 21, 0, tzinfo=UTC),
    )
    assert offer.our_events_without_offer == ["e1"]
    assert offer.our_events_kicked_off == ["e1"]
    # And it must not become a data gap, because a gap makes the step PARTIAL.
    assert offer.data_gaps == []


def test_a_future_fixture_absent_from_the_book_is_reported_plainly():
    events = EventListV1(
        generated_at="x", date="2026-08-31", run_id="r",
        events=[make_event("e1", start="2026-08-31T23:00:00+00:00")],
    )
    offer = collect_superbet_offer(
        events, client=FakeClient([]), generated_at="t",
        now=datetime(2026, 8, 31, 21, 0, tzinfo=UTC),
    )
    assert offer.our_events_without_offer == ["e1"]
    assert offer.our_events_kicked_off == []


# --- against a real captured payload ---------------------------------------


REAL_PAYLOAD = (
    Path(__file__).resolve().parents[1]
    / "fixtures" / "simple_stats" / "superbet_event_remo_coritiba_2026-08-31.json"
)


def test_real_payload_maps_the_markets_the_sheet_prices():
    """Pinned against a real Remo-Coritiba payload captured 2026-08-31.

    Synthetic market names test the rules; this tests the rules against prose a
    bookmaker actually wrote, which is where the surprises live.
    """
    raw = json.loads(REAL_PAYLOAD.read_text(encoding="utf-8"))
    lines, unmapped = normalize_lines(raw, team_names=("Remo", "Coritiba"))
    markets = {line.market for line in lines}
    assert {
        "goals_total", "corners_total", "cards_total", "shots_on_target_total",
        "shots_total", "offsides_total", "fouls_total",
    } <= markets
    # Both sides get their own per-team rows, not just the one Superbet spells
    # the way we do.
    per_team = {(line.market, line.team_name) for line in lines if line.team_name}
    assert ("cards_for", "Remo") in per_team
    assert ("cards_for", "Coritiba") in per_team
    # And the traps stay out.
    assert not any("obramowanie" in line.source_market_name.lower() for line in lines)
    assert not any(";" in line.source_market_name for line in lines)
    assert unmapped == [] or all("liczba" in name.lower() for name in unmapped)


def test_real_payload_reads_the_player_market_it_carries():
    """The same captured fixture carries "Zawodnik - liczba strzałów", which
    this stage refused to read until 2026-09-01. Superbet's own spelling is
    kept verbatim; resolving it to one of our players happens elsewhere."""
    raw = json.loads(REAL_PAYLOAD.read_text(encoding="utf-8"))
    lines, _ = normalize_lines(raw, team_names=("Remo", "Coritiba"))
    props = [line for line in lines if line.market == "player_total_shots"]
    assert props, "the captured payload has player shot lines"
    assert {line.player_name for line in props} == {"Ze Ivaldo"}
    assert {line.line for line in props} == {0.5, 1.5}
    # A prop names a player, never a side.
    assert all(line.team_name is None for line in props)


def test_shot_sub_populations_never_become_a_plain_shot_prop():
    """Superbet splits player shots by body part; bzzoiro does not. Pricing
    "shots with the head" off a total-shots sample is the woodwork trap wearing
    a different name."""
    for market_name in (
        "Zawodnik - liczba strzałów głową",
        "Zawodnik - liczba celnych strzałów lewą nogą",
        "Zawodnik - liczba strzałów spoza pola karnego",
    ):
        assert classify_player_market(market_name) is None
        assert classify_market(market_name) is None


def test_real_payload_prices_are_verbatim_decimals():
    raw = json.loads(REAL_PAYLOAD.read_text(encoding="utf-8"))
    lines, _ = normalize_lines(raw, team_names=("Remo", "Coritiba"))
    corners = {
        (line.line, line.direction): line.price
        for line in lines if line.market == "corners_total"
    }
    # Read straight off the captured feed: over 7.5 corners at 1.23.
    assert corners[(7.5, "OVER")] == 1.23
    assert corners[(7.5, "UNDER")] == 3.6
    assert all(price > 1.0 for price in corners.values())
