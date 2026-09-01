"""Offer-driven lines, and the player join that must refuse rather than guess.

The join is the only operation in this pipeline whose failure mode is a
*plausible* row: a prop filed against the wrong human reads exactly like a
correct one and carries a real price. So most of this file is about the cases
where the answer must be "no".
"""
import json
from pathlib import Path

import pytest

from bet.simple_stats.analyze import analyze_dossier
from bet.simple_stats.contracts import (
    EventDossierV1,
    MetricObservation,
    PlayerMetricObservation,
    ProviderValue,
    StatsSheetV1,
    SuperbetEventOffer,
    SuperbetLine,
    SuperbetOfferV1,
)
from bet.simple_stats.offered_lines import (
    MAX_OFFERED_LINES_PER_SAMPLE,
    OfferedLines,
    resolve_player_names,
    select_lines,
)
from bet.simple_stats.superbet_offer import attach_superbet_column, normalize_lines


def _pv(value, day, provider="bzzoiro", opponent="Opponent FC"):
    return ProviderValue(
        provider=provider,
        match_id=f"m{day}",
        match_date=f"2026-01-{day:02d}",
        opponent=opponent,
        value=value,
        observed_at="2026-01-01T00:00:00+00:00",
    )


def _line(market, line, direction="OVER", team_name=None, player_name=None):
    return SuperbetLine(
        market=market,
        line=line,
        direction=direction,
        team_name=team_name,
        player_name=player_name,
        price=1.85,
        source_market_name="x",
        source_outcome_name="y",
    )


def _offer(*lines, event_id="evt1"):
    return SuperbetOfferV1(
        generated_at="2026-01-01T00:00:00+00:00",
        events=[
            SuperbetEventOffer(
                superbet_event_id="sb1",
                superbet_match_name="A – B",
                sport="football",
                kickoff="2026-01-01T18:00:00+00:00",
                event_id=event_id,
                lines=list(lines),
            )
        ],
    )


# --- the player join --------------------------------------------------------


def test_surname_first_and_forename_first_are_the_same_player():
    assert resolve_player_names(["Renan Lodi"], ["Lodi, Renan"]) == {
        "Lodi, Renan": "Renan Lodi"
    }


def test_accents_do_not_stop_a_join():
    """Superbet writes "Vitao", "Preciado, Angelo", "Perez, Tomas"; bzzoiro has
    the accents. Keeping them cost eight of forty-nine joins on the first
    fixture measured with both sources in hand."""
    resolved = resolve_player_names(
        ["Vitão", "Ángelo Preciado", "Tomás Pérez"],
        ["Vitao", "Preciado, Angelo", "Perez, Tomas"],
    )
    assert resolved == {
        "Vitao": "Vitão",
        "Preciado, Angelo": "Ángelo Preciado",
        "Perez, Tomas": "Tomás Pérez",
    }


def test_a_squad_that_lists_only_the_forename_still_joins():
    """"Tressoldi, Ruan" against a squad carrying just "Ruan" -- exact token
    containment, which is stricter than similarity and runs before it."""
    assert resolve_player_names(["Ruan"], ["Tressoldi, Ruan"]) == {
        "Tressoldi, Ruan": "Ruan"
    }


def test_containment_refuses_when_two_of_ours_fit():
    """A bare surname that fits two squad members is not a join, it is a coin
    toss, and the wrong side of it is unrecoverable downstream."""
    assert resolve_player_names(["Lucas Silva", "Gerson Silva"], ["Silva"]) == {}


def test_containment_refuses_when_two_of_theirs_fit():
    """The uniqueness rule runs in both directions: one of our players matching
    two of Superbet's strings is equally ambiguous."""
    assert resolve_player_names(["Silva"], ["Silva, Lucas", "Silva, Gerson"]) == {}


def test_two_of_our_entries_folding_to_one_name_is_refused():
    """Two *different* dossier spellings that fold to the same token bag are
    two provider ids we cannot tell apart, so neither may claim the price.
    The same string twice is not this case -- that is one player listed twice,
    and it collapses before the join ever sees it."""
    assert resolve_player_names(["Lucas Silva", "Silva, Lucas"], ["Silva, Lucas"]) == {}
    assert resolve_player_names(["Fred", "Fred"], ["Fred"]) == {"Fred": "Fred"}


def test_an_exact_match_is_never_stolen_by_a_looser_one():
    """"Lucas Silva" is exact for "Silva, Lucas"; the containment pass must not
    then hand "Silva, Lucas" to the bare "Silva" instead."""
    resolved = resolve_player_names(["Lucas Silva", "Silva"], ["Silva, Lucas"])
    assert resolved == {"Silva, Lucas": "Lucas Silva"}


def test_unrelated_names_do_not_join():
    assert resolve_player_names(["Renan Lodi"], ["Cassierra, Mateo"]) == {}


@pytest.mark.parametrize("ours,theirs", [([], ["A"]), (["A"], []), ([], [])])
def test_an_empty_pool_joins_nothing(ours, theirs):
    assert resolve_player_names(ours, theirs) == {}


def test_no_two_superbet_strings_ever_claim_the_same_player():
    ours = ["Lucas Silva", "Gerson Silva", "Renan Lodi"]
    theirs = ["Silva, Lucas", "Silva, Gerson", "Lodi, Renan"]
    resolved = resolve_player_names(ours, theirs)
    assert len(set(resolved.values())) == len(resolved)


# --- the index --------------------------------------------------------------


def test_no_offer_is_an_empty_index_and_every_lookup_falls_back():
    offered = OfferedLines.from_offer(None)
    assert not offered
    assert offered.lines_for(event_id="evt1", market="corners_total") is None


def test_lines_are_indexed_per_market_and_side():
    offered = OfferedLines.from_offer(
        _offer(
            _line("corners_total", 8.5),
            _line("corners_total", 9.5),
            _line("corners_for", 4.5, team_name="Remo"),
        )
    )
    assert offered.lines_for(event_id="evt1", market="corners_total") == (8.5, 9.5)
    assert offered.lines_for(
        event_id="evt1", market="corners_for", team_name="Remo"
    ) == (4.5,)
    # A side we were not given is not the match total wearing a team name.
    assert offered.lines_for(
        event_id="evt1", market="corners_for", team_name="Coritiba"
    ) is None


def test_over_and_under_at_one_line_are_one_line():
    offered = OfferedLines.from_offer(
        _offer(
            _line("corners_total", 8.5, "OVER"),
            _line("corners_total", 8.5, "UNDER"),
        )
    )
    assert offered.lines_for(event_id="evt1", market="corners_total") == (8.5,)


def test_player_lines_are_indexed_under_our_spelling():
    offered = OfferedLines.from_offer(
        _offer(_line("player_total_shots", 1.5, player_name="Lodi, Renan")),
        player_names_by_event={"evt1": ["Renan Lodi"]},
    )
    assert offered.lines_for(
        event_id="evt1", market="player_total_shots", player_name="Renan Lodi"
    ) == (1.5,)
    assert offered.unresolved_players == ()


def test_an_unresolved_player_is_dropped_and_named():
    """Indexing it under Superbet's spelling would produce a key nothing ever
    looks up, which reads as coverage instead of as the gap it is."""
    offered = OfferedLines.from_offer(
        _offer(_line("player_fouls", 0.5, player_name="Kowalski, Jan")),
        player_names_by_event={"evt1": ["Renan Lodi"]},
    )
    assert offered.by_key == {}
    assert offered.unresolved_players == ("Kowalski, Jan",)


def test_without_our_squad_no_player_line_is_indexed():
    offered = OfferedLines.from_offer(
        _offer(_line("player_fouls", 0.5, player_name="Lodi, Renan"))
    )
    assert offered.by_key == {}
    assert offered.unresolved_players == ("Lodi, Renan",)


# --- trimming ---------------------------------------------------------------


def test_no_limit_keeps_every_line_sorted():
    assert select_lines([9.5, 6.5, 8.5], median=8.0, limit=None) == [6.5, 8.5, 9.5]


def test_trimming_keeps_the_lines_the_sample_can_speak_to():
    """Superbet posts sixteen corner lines on a big fixture. A line four goals
    clear of everything the sample produced yields 22/22 and a p_low that means
    nothing, so the ones nearest the median survive."""
    ladder = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5]
    assert select_lines(ladder, median=8.0, limit=4) == [6.5, 7.5, 8.5, 9.5]


def test_trimming_ties_break_on_the_lower_line_so_runs_are_reproducible():
    assert select_lines([7.5, 8.5], median=8.0, limit=1) == [7.5]


# --- end to end through ANALYZE --------------------------------------------


def _dossier(values, *, player=None):
    metrics = {
        "corners_total": MetricObservation(
            canonical_name="corners_total",
            team_a_l10=[_pv(value, day + 1) for day, value in enumerate(values)],
        )
    }
    return EventDossierV1(
        event_id="evt1",
        sport="football",
        metrics=metrics,
        readiness="READY",
        data_gaps=[],
        player_metrics=[player] if player else [],
    )


def test_without_an_offer_analyze_prices_the_static_grid():
    rows = analyze_dossier(_dossier([8.0, 9.0, 10.0, 11.0, 9.0, 10.0, 8.0, 9.0]))
    lines = sorted({row.line for row in rows if row.market == "corners_total"})
    assert lines == [6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5]


def test_with_an_offer_analyze_prices_the_lines_the_book_posts():
    """The inversion, end to end: 13.5 is not in STANDARD_MARKET_LINES and 6.5
    is, and the sheet follows the book rather than the grid."""
    offered = OfferedLines.from_offer(
        _offer(_line("corners_total", 9.5), _line("corners_total", 13.5))
    )
    rows = analyze_dossier(
        _dossier([8.0, 9.0, 10.0, 11.0, 9.0, 10.0, 8.0, 9.0]), offered
    )
    lines = sorted({row.line for row in rows if row.market == "corners_total"})
    assert lines == [9.5, 13.5]


def test_a_market_the_book_does_not_post_still_falls_back_to_the_grid():
    """Partial coverage is per (event, market, side): an offer that carries
    corners must not silence every other market on the same fixture."""
    offered = OfferedLines.from_offer(_offer(_line("cards_total", 4.5)))
    rows = analyze_dossier(
        _dossier([8.0, 9.0, 10.0, 11.0, 9.0, 10.0, 8.0, 9.0]), offered
    )
    lines = sorted({row.line for row in rows if row.market == "corners_total"})
    assert lines == [6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5]


def test_a_long_offered_ladder_is_trimmed_to_the_sample():
    offered = OfferedLines.from_offer(
        _offer(*[_line("corners_total", line) for line in
                 (2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5)])
    )
    rows = analyze_dossier(
        _dossier([9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0]), offered
    )
    lines = sorted({row.line for row in rows if row.market == "corners_total"})
    assert len(lines) == MAX_OFFERED_LINES_PER_SAMPLE
    assert 9.5 in lines and 2.5 not in lines


def test_a_player_prop_is_priced_at_the_books_own_player_ladder():
    player = PlayerMetricObservation(
        player_id="p1",
        player_name="Renan Lodi",
        team_side="home",
        canonical_name="player_total_shots",
        l10=[
            _pv(float(value), day + 1)
            for day, value in enumerate([1, 2, 0, 3, 1, 2, 1, 0])
        ],
    )
    offered = OfferedLines.from_offer(
        _offer(
            _line("player_total_shots", 4.5, player_name="Lodi, Renan"),
            _line("player_total_shots", 5.5, player_name="Lodi, Renan"),
        ),
        player_names_by_event={"evt1": ["Renan Lodi"]},
    )
    rows = analyze_dossier(_dossier([8.0] * 8, player=player), offered)
    props = sorted({row.line for row in rows if row.market == "player_total_shots"})
    # 4.5 and 5.5 are both outside PLAYER_PROP_LINES' fallback grid.
    assert props == [4.5, 5.5]


# --- the whole loop, on a payload a bookmaker actually wrote -----------------

REAL_PAYLOAD = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "simple_stats"
    / "superbet_event_remo_coritiba_2026-08-31.json"
)


def test_a_real_payload_ends_up_as_a_priced_player_row():
    """Raw Superbet JSON -> lines -> offered ladder -> sheet row -> price.

    Every step in that chain existed before 2026-09-01 except the two ends, and
    the row this produces is the thing that could not exist at all: a player prop
    with a number on it from the operator's own book.
    """
    raw = json.loads(REAL_PAYLOAD.read_text(encoding="utf-8"))
    lines, _ = normalize_lines(raw, team_names=("Remo", "Coritiba"))
    event_offer = SuperbetEventOffer(
        superbet_event_id=str(raw["eventId"]),
        superbet_match_name=raw["matchName"],
        sport="football",
        kickoff=raw["utcDate"],
        event_id="evt1",
        lines=lines,
    )
    offer = SuperbetOfferV1(
        generated_at="2026-01-01T00:00:00+00:00", events=[event_offer]
    )

    # The dossier's spelling differs from Superbet's, which is the point.
    player = PlayerMetricObservation(
        player_id="p1",
        player_name="Ivaldo, Ze",
        team_side="home",
        canonical_name="player_total_shots",
        l10=[
            _pv(float(value), day + 1)
            for day, value in enumerate([1, 2, 0, 1, 1, 2, 0, 1])
        ],
    )
    dossier = _dossier([8.0] * 8, player=player)
    offered = OfferedLines.from_offer(
        offer, player_names_by_event={"evt1": ["Ivaldo, Ze"]}
    )

    rows = analyze_dossier(dossier, offered)
    props = [row for row in rows if row.market == "player_total_shots"]
    # The captured fixture posts exactly 0.5 and 1.5 for this player.
    assert sorted({row.line for row in props}) == [0.5, 1.5]

    sheet = StatsSheetV1(
        run_id="r", date="2026-08-31",
        generated_at="2026-01-01T00:00:00+00:00", rows=rows,
    )
    priced = attach_superbet_column(sheet, offer)
    offered_props = [
        row for row in priced.rows
        if row.market == "player_total_shots"
        and row.superbet is not None
        and row.superbet.availability == "OFFERED"
    ]
    assert offered_props, "a player prop must now carry a real Superbet price"
    assert all(row.superbet.price > 1.0 for row in offered_props)
    assert {row.superbet.source_market_name for row in offered_props} == {
        "Zawodnik - liczba strzałów"
    }
