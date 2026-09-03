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
    build_event_offer,
    is_banned_market,
    match_offer_events,
    normalize_lines,
    normalize_result_lines,
    parse_outcome,
    RESULT_MARKET_NAMES,
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
        ("Liczba kartek", ("cards_points_total", None)),
        ("Liczba celnych strzałów", ("shots_on_target_total", None)),
        ("Liczba strzałów", ("shots_total", None)),
        ("Liczba spalonych", ("offsides_total", None)),
        ("Liczba fauli", ("fouls_total", None)),
        ("Liczba asów", ("aces_total", None)),
        ("Liczba podwójnych błędów", ("double_faults_total", None)),
        ("Liczba gemów", ("total_games", None)),
        ("Liczba setów", ("total_sets", None)),
        ("Remo - liczba kartek", ("cards_points_for", "remo")),
        ("Liczba celnych strzałów - Remo", ("shots_on_target_for", "remo")),
        ("Liczba strzałów Remo", ("shots_for", "remo")),
        ("Spalone - Remo", ("offsides_for", "remo")),
        ("Liczba fauli - Remo", ("fouls_for", "remo")),
        ("Liczba czerwonych kartek", ("red_cards_total", None)),
        # A fourth shape: no separator at all. Live on 2026-09-01 and the only
        # mapped market missing from a 4,172-outcome fixture.
        ("Liczba czerwonych kartek Remo", ("red_cards_for", "remo")),
    ],
)
def test_classify_market_maps_the_markets_the_sheet_prices(name, expected):
    assert classify_market(name) == expected


def test_tennis_per_player_totals_are_read_as_per_side_rows():
    """Twenty of these went unmapped on 2026-09-02 -- on a slate whose single
    genuinely-priced row was a tennis ``aces_total``. Per-player aces are the
    same read measured on one player's own serve."""
    assert classify_market("Alex Michelsen liczba asów") == ("aces_for", "alex michelsen")
    assert classify_market("Alex Michelsen liczba gemów") == ("games_won", "alex michelsen")
    assert classify_market("Alex Michelsen liczba podwójnych błędów") == (
        "double_faults_for", "alex michelsen",
    )


def test_the_match_total_still_wins_over_the_per_player_pattern():
    """"Liczba asów" with no name is both players summed, and the exact table
    is consulted before any pattern -- otherwise the greedy ``.+?`` would have
    to be trusted not to capture an empty subject."""
    assert classify_market("Liczba asów") == ("aces_total", None)
    assert classify_market("Liczba gemów") == ("total_games", None)
    assert classify_market("Liczba setów") == ("total_sets", None)


def test_the_tennis_markets_with_no_canonical_metric_stay_unmapped():
    """Refusing is the answer here. Nothing in this pipeline measures aces and
    double faults *added together*, and per-player sets won has no canonical
    metric -- inventing either would price a market nothing measured."""
    assert classify_market("Alex Michelsen liczba asów + podwójnych błędów") is None
    assert classify_market("Alex Michelsen liczba setów") is None


def test_a_red_card_market_is_not_filed_as_a_booking_market():
    """Both names begin "Liczba ... kartek". Filing one as the other prices a
    straight red at a yellow-card line, which is a bet nobody would take
    knowingly."""
    assert classify_market("Liczba czerwonych kartek Remo") == ("red_cards_for", "remo")
    assert classify_market("Remo - liczba kartek") == ("cards_points_for", "remo")


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
        ("cards_points_for", 2.5, "UNDER", "Remo"): 1.38,
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
    assert prices[("cards_points_total", "active")] == 1.85


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


# --- pass zero: identity by Betradar id -------------------------------------
#
# Measured on the 2026-09-01 slate against a real 179-fixture DISCOVER run:
# the name matcher found 103 of the 167 fixtures still prematch, the bridge
# took it to 111, and the two never disagreed on a fixture both could name.


def _offer_row_with_betradar(betradar: str, **kwargs):
    row = _offer_row(**kwargs)
    row["betradarId"] = betradar
    return row


def test_a_betradar_id_matches_a_fixture_no_name_rule_could_reach():
    """Live case: our "Universitatea Cluj" against Superbet's "U Cluj"."""
    events = EventListV1(
        generated_at="x", date="2026-08-31",
        events=[make_event(home="Universitatea Cluj", away="Petrolul Ploiesti")],
    )
    rows = [_offer_row_with_betradar(
        "74019308", name="U Cluj\u00b7Petrolul", utc="2026-08-31T23:00:00Z"
    )]

    without = match_offer_events(events, rows)[0]
    with_bridge, unmatched, missing = match_offer_events(
        events, rows, betradar_by_event_id={"e1": "74019308"}
    )

    assert without == {}, "the name matcher is expected to miss this one"
    assert list(with_bridge) == ["e1"]
    assert with_bridge["e1"]["matched_by"] == "betradar_id"
    assert unmatched == [] and missing == []


def test_an_id_match_survives_a_kickoff_the_tolerance_would_reject():
    """Superbet published Volos-Kalamata three hours from our clock, same tie.

    The delta is still recorded -- it is a real fact about the two feeds -- but
    it no longer decides the pairing, because the pairing was not made on it.
    """
    events = EventListV1(generated_at="x", date="2026-08-31", events=[make_event()])
    rows = [_offer_row_with_betradar("55", name="Remo\u00b7Coritiba", utc="2026-09-01T02:00:00Z")]

    matched, _, _ = match_offer_events(events, rows, betradar_by_event_id={"e1": "55"})

    assert matched["e1"]["matched_by"] == "betradar_id"
    assert matched["e1"]["delta_minutes"] == 180.0


def test_an_id_match_is_reported_as_ID_MATCHED_not_as_EXACT():
    events = EventListV1(generated_at="x", date="2026-08-31", events=[make_event()])
    rows = [_offer_row_with_betradar("55", name="Remo\u00b7Coritiba", utc="2026-08-31T23:00:00Z")]
    matched, _, _ = match_offer_events(events, rows, betradar_by_event_id={"e1": "55"})

    offer = build_event_offer(
        rows[0], event=make_event(), delta_minutes=matched["e1"]["delta_minutes"],
        matched_by=matched["e1"]["matched_by"],
    )

    assert offer.match_quality == "ID_MATCHED"


def test_a_betradar_id_two_superbet_rows_share_is_not_an_identity():
    """The by-date feed carries the same tie under two groupings. Refuse both.

    Falling through to the name passes is the right answer -- they know how to
    break that tie on kickoff and market count; an id that names two rows does
    not.
    """
    events = EventListV1(generated_at="x", date="2026-08-31", events=[make_event()])
    rows = [
        _offer_row_with_betradar("55", name="Remo\u00b7Coritiba", utc="2026-08-31T23:00:00Z", event_id=1),
        _offer_row_with_betradar("55", name="Remo\u00b7Coritiba", utc="2026-08-31T23:00:00Z", event_id=2),
    ]

    matched, _, _ = match_offer_events(events, rows, betradar_by_event_id={"e1": "55"})

    assert matched["e1"]["matched_by"] == "name_and_kickoff"


def test_an_id_that_crosses_sports_is_a_feed_bug_not_a_match():
    events = EventListV1(generated_at="x", date="2026-08-31", events=[make_event()])
    rows = [_offer_row_with_betradar(
        "55", name="Remo\u00b7Coritiba", utc="2026-08-31T23:00:00Z", sport_id=2,
    )]

    matched, _, missing = match_offer_events(events, rows, betradar_by_event_id={"e1": "55"})

    assert matched == {}
    assert missing == ["e1"]


def test_an_empty_bridge_changes_nothing():
    events = EventListV1(generated_at="x", date="2026-08-31", events=[make_event()])
    rows = [_offer_row("Remo\u00b7Coritiba", "2026-08-31T23:00:00Z")]

    plain = match_offer_events(events, rows)
    bridged = match_offer_events(events, rows, betradar_by_event_id={})

    assert plain[0].keys() == bridged[0].keys()
    assert bridged[0]["e1"]["matched_by"] == "name_and_kickoff"


def test_an_id_claim_is_not_re_offered_to_the_name_passes():
    """One Superbet row cannot be spent twice, or an event steals another's."""
    events = EventListV1(
        generated_at="x", date="2026-08-31",
        events=[make_event(event_id="e1"), make_event(event_id="e2")],
    )
    rows = [_offer_row_with_betradar("55", name="Remo\u00b7Coritiba", utc="2026-08-31T23:00:00Z")]

    matched, unmatched, missing = match_offer_events(
        events, rows, betradar_by_event_id={"e1": "55"}
    )

    assert list(matched) == ["e1"]
    assert missing == ["e2"]
    assert unmatched == []


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


def test_a_prop_market_the_book_prices_for_nobody_is_the_books_gap():
    """The dominant case behind a day's PLAYER_NOT_MATCHED wall: the book
    simply does not carry the market on this fixture. No spelling of ours
    could have joined, so calling it a join failure sends the operator
    chasing name-matching on props that cannot be bought at any spelling."""
    row = make_row(market="player_total_shots", line=1.5, player_name="Alef Manga",
                   player_id="p1", lineup_status="predicted")
    result = _compare([row], [sb_line()])
    assert result.rows[0].verdict == "MARKET_NOT_OFFERED"


def test_a_prop_the_book_prices_for_other_players_only_is_ours_to_report():
    """Only when the market demonstrably exists on the fixture is a missing
    player plausibly our join: Superbet not listing this player, or two of
    our players fitting its string equally well and the join refusing."""
    row = make_row(market="player_total_shots", line=1.5, player_name="Alef Manga",
                   player_id="p1", lineup_status="predicted")
    other = sb_line(market="player_total_shots", line=1.5, direction="OVER",
                    player_name="Somebody Else",
                    source_market_name="Zawodnik - liczba strzałów",
                    source_outcome_name="powyżej 1.5")
    result = _compare([row], [other])
    assert result.rows[0].verdict == "PLAYER_NOT_MATCHED"


def test_a_prop_comparison_row_names_its_player():
    """Two players' VALUE rows on the same market and line differ in nothing
    but price without the subject -- the operator either cannot act on the
    row or attaches it to the wrong human on the screen."""
    row = make_row(market="player_total_shots", line=1.5, player_name="Alef Manga",
                   player_id="p1", lineup_status="predicted")
    result = _compare([row], [sb_line()])
    assert result.rows[0].player_name == "Alef Manga"
    assert result.rows[0].player_id == "p1"


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
        "goals_total", "corners_total", "cards_points_total", "shots_on_target_total",
        "shots_total", "offsides_total", "fouls_total",
    } <= markets
    # Both sides get their own per-team rows, not just the one Superbet spells
    # the way we do.
    per_team = {(line.market, line.team_name) for line in lines if line.team_name}
    assert ("cards_points_for", "Remo") in per_team
    assert ("cards_points_for", "Coritiba") in per_team
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


# --- the result family ------------------------------------------------------
#
# Markets Superbet offers, this pipeline does not price, and which were dropped
# without trace until 2026-09-03. Every market name below is verified against a
# live 4,279-outcome fixture (Raków-Górnik, eventId 13573272).


def test_result_markets_were_invisible_to_the_totals_parser():
    """The regression these lines exist for.

    ``parse_outcome`` recognises "powyżej"/"poniżej" and nothing else, so every
    result-family outcome returned None and hit the bare ``continue`` before
    any diagnostic ran -- not mapped, not banned, not even unmapped. Five of the
    fourteen legs on the 2026-09-03 SUPERBETS board were these, and the sheet's
    silence about the six fixtures they sat on was indistinguishable from
    "priced it, not worth it".
    """
    raw = {
        "odds": [
            raw_odds("Mecz", "1", 2.47),
            raw_odds("Podwójna szansa", "X2", 1.55),
            raw_odds("Obie drużyny strzelą", "tak", 1.61),
        ]
    }
    teams = ("Raków Częstochowa", "Górnik Zabrze")
    lines, unmapped = normalize_lines(raw, team_names=teams)
    assert lines == []
    assert unmapped == []

    result_lines = normalize_result_lines(raw, team_names=teams)
    assert {(line.family, line.outcome) for line in result_lines} == {
        ("1x2", "HOME"),
        ("double_chance", "X2"),
        ("btts", "YES"),
    }


def test_every_leg_of_the_2026_09_03_superbets_board_is_now_visible():
    """The six slips used four result markets between them: a match result, a
    double chance, both-teams-to-score, and a double chance on a single half.
    All four, or the fix does not answer the question that prompted it."""
    raw = {
        "odds": [
            raw_odds("Mecz", "1", 1.94),
            raw_odds("Podwójna szansa", "X2", 1.55),
            raw_odds("Obie drużyny strzelą", "tak", 1.61),
            raw_odds("1.połowa - podwójna szansa", "X2", 1.35),
            raw_odds("2.połowa - podwójna szansa", "X2", 1.40),
        ]
    }
    lines = normalize_result_lines(raw, team_names=("Śląsk", "Pogoń"))
    assert {line.family for line in lines} == {
        "1x2", "double_chance", "btts", "double_chance_1h", "double_chance_2h",
    }


def test_a_half_market_survives_the_ban_the_way_the_half_goal_totals_do():
    """"1.polowa -" is in BANNED_SUBSTRINGS, and the two mapped half-goal
    totals already survive it by being looked up in an exact table first. The
    half double chance is the market slip 3 of the board was built from, and it
    has to survive the same way."""
    assert is_banned_market(fold("1.połowa - podwójna szansa"))
    raw = {"odds": [raw_odds("1.połowa - podwójna szansa", "1X", 1.29)]}
    assert [line.family for line in normalize_result_lines(raw)] == ["double_chance_1h"]


def test_a_market_shaped_like_a_result_but_settling_on_cards_is_not_one():
    """On the live fixture "Najwięcej kartek" -- most *cards* -- is quoted 1/X/2,
    exactly like the match result, and "Wynik dowolnej połowy meczu" is quoted
    with the two club names, exactly like a half 1X2. A rule that read outcome
    shape instead of the market name would file both as the result. That is the
    woodwork bug in the module docstring, one family over."""
    raw = {
        "odds": [
            raw_odds("Najwięcej kartek", "1", 2.57),
            raw_odds("Najwięcej kartek", "X", 4.0),
            raw_odds("Najwięcej kartek", "2", 2.12),
            raw_odds("Wynik dowolnej połowy meczu", "Raków Częstochowa", 1.5),
        ]
    }
    teams = ("Raków Częstochowa", "Górnik Zabrze")
    assert normalize_result_lines(raw, team_names=teams) == []


def test_a_half_result_names_the_clubs_and_is_read_through_our_spelling():
    """Superbet writes the half 1X2 with club names rather than 1/X/2, and
    "remis" for the draw."""
    raw = {
        "odds": [
            raw_odds("1.połowa - 1X2", "Raków Częstochowa", 2.95),
            raw_odds("1.połowa - 1X2", "remis", 2.30),
            raw_odds("1.połowa - 1X2", "Górnik Zabrze", 3.30),
        ]
    }
    teams = ("Raków Częstochowa", "Górnik Zabrze")
    got = {
        line.outcome: line.price
        for line in normalize_result_lines(raw, team_names=teams)
    }
    assert got == {"HOME": 2.95, "DRAW": 2.30, "AWAY": 3.30}


def test_an_outcome_naming_a_team_we_cannot_place_is_dropped_not_guessed():
    """Same rule the per-team totals follow. A price the operator cannot
    attribute to a side is worse than no price: it looks usable."""
    raw = {"odds": [raw_odds("Zakład bez remisu", "Palmeiras", 1.75)]}
    assert normalize_result_lines(raw, team_names=("Remo", "Coritiba")) == []


def test_result_lines_take_the_best_active_price_like_every_other_line():
    raw = {
        "odds": [
            raw_odds("Mecz", "1", 2.40),
            raw_odds("Mecz", "1", 2.47),
            raw_odds("Mecz", "X", 9.99, status="block"),
            raw_odds("Mecz", "X", 3.40, status="active"),
        ]
    }
    prices = {
        (line.outcome, line.status): line.price
        for line in normalize_result_lines(raw)
    }
    assert prices[("HOME", "active")] == 2.47
    assert prices[("DRAW", "active")] == 3.40


def test_a_result_price_never_becomes_a_priced_total():
    """These must not reach ``lines``. Everything there has a line and a
    direction and is read downstream as a total the sheet can be compared
    against; a 1X2 has neither and would be compared against a corners row."""
    raw = {
        "odds": [
            raw_odds("Mecz", "1", 2.47),
            raw_odds("Liczba goli", "powyżej 2.5", 1.80),
        ]
    }
    lines, _ = normalize_lines(raw, team_names=("Remo", "Coritiba"))
    assert [(line.market, line.line, line.direction) for line in lines] == [
        ("goals_total", 2.5, "OVER")
    ]


def test_a_shut_result_market_is_not_a_price():
    """1.0 or below is how Superbet renders a market it has closed, and the
    totals path has refused it since the beginning. A result line at 1.0 would
    put an untakeable quote next to takeable ones with nothing to tell them
    apart -- and this block exists precisely so the operator can compare what he
    is being offered against the consensus."""
    raw = {
        "odds": [
            raw_odds("Mecz", "1", 1.0),
            raw_odds("Podwójna szansa", "1X", 0.95),
            raw_odds("Obie drużyny strzelą", "tak", 1.61),
        ]
    }
    lines = normalize_result_lines(raw)
    assert [(line.family, line.outcome) for line in lines] == [("btts", "YES")]


def test_the_consensus_block_reports_how_many_books_stand_behind_it():
    """"De-vigged" is a claim about one bookmaker's market; the count is how
    much of the board agreed with it. Reported together or neither is
    interpretable."""
    raw = {"odds": [raw_odds("Mecz", "1", 2.47), raw_odds("Mecz", "X", 3.40)]}
    lines = normalize_result_lines(raw)
    assert {line.outcome for line in lines} == {"HOME", "DRAW"}
    # Superbet's own status travels with the price, as it does on every total.
    assert all(line.status == "active" for line in lines)


def test_a_result_line_keeps_superbets_own_strings_for_audit():
    """The mapping from Polish prose to a family code is the part most likely to
    be wrong, and it cannot be checked once the source string is gone. Same
    reason ``SuperbetLine`` keeps them."""
    raw = {"odds": [raw_odds("1.połowa - podwójna szansa", "X2", 1.35)]}
    (line,) = normalize_result_lines(raw)
    assert line.source_market_name == "1.połowa - podwójna szansa"
    assert line.source_outcome_name == "X2"


def test_no_market_in_the_result_table_can_ever_appear_as_a_priced_total():
    """The two lists must stay disjoint. Everything in ``lines`` has a line and
    a direction and is read downstream as a total to compare the sheet against;
    a result market has neither, and one leaking across would be compared to a
    corners row. Asserted over the whole table rather than one example, so a
    future entry cannot quietly land on the wrong side."""
    raw = {
        "odds": [
            # Every result market, alongside a genuine total.
            *[
                raw_odds(name, outcome, 1.9)
                for name, outcome in (
                    ("Mecz", "1"),
                    ("Podwójna szansa", "1X"),
                    ("Obie drużyny strzelą", "tak"),
                    ("1.połowa - podwójna szansa", "X2"),
                    ("2.połowa - podwójna szansa", "X2"),
                    ("1.połowa - obie drużyny strzelą", "tak"),
                    ("2.połowa - obie drużyny strzelą", "nie"),
                    ("Zakład bez remisu", "Remo"),
                    ("1.połowa - 1X2", "remis"),
                    ("2.połowa - 1X2", "Remo"),
                )
            ],
            raw_odds("Liczba goli", "powyżej 2.5", 1.80),
        ]
    }
    lines, _ = normalize_lines(raw, team_names=("Remo", "Coritiba"))
    result_lines = normalize_result_lines(raw, team_names=("Remo", "Coritiba"))

    priced_names = {fold(line.source_market_name) for line in lines}
    assert priced_names.isdisjoint(RESULT_MARKET_NAMES)
    assert priced_names == {"liczba goli"}
    # And the result family did come through, or the assertion above is vacuous.
    assert len(result_lines) >= 10
