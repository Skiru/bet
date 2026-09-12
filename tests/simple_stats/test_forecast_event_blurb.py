"""build_event_blurb: one short context line per match, from data already on
the dossier -- no provider call, never priced, never a sample.
"""
from __future__ import annotations

from bet.simple_stats.contracts import (
    EventDossierV1,
    EventRecord,
    FixtureContext,
    SquadAvailability,
)
from bet.simple_stats.forecast import build_event_blurb


def _event(competition="Brasileirao Serie A", event_id="e1") -> EventRecord:
    return EventRecord(
        event_id=event_id, sport="football", competition=competition,
        home_team="Botafogo", away_team="Red Bull Bragantino",
        start_time="2026-09-12T19:00:00+00:00",
        identity_confidence="CONFIRMED", status="ACTIVE",
    )


def _dossier(**kw) -> EventDossierV1:
    base = dict(
        event_id="e1", sport="football", metrics={}, readiness="READY",
        team_a_name="Botafogo", team_b_name="Red Bull Bragantino",
    )
    base.update(kw)
    return EventDossierV1(**base)


def test_blocked_dossier_prints_only_its_own_gap_reason():
    """Nothing else is known about an event nothing was fetched for."""
    dossier = _dossier(
        readiness="BLOCKED",
        data_gaps=["not enriched: Superbet prices other fixtures of 'X' today "
                   "but not this one: no price the operator can take"],
    )
    blurb = build_event_blurb(dossier, _event())
    assert blurb == dossier.data_gaps[0]


def test_blocked_dossier_with_no_gap_reason_says_so():
    dossier = _dossier(readiness="BLOCKED", data_gaps=[])
    assert build_event_blurb(dossier, _event()) == "brak danych"


def test_derby_and_round_and_weather_are_all_shown():
    dossier = _dossier(
        fixture_context=FixtureContext(
            round_name="Regular season · Matchday 27",
            is_local_derby=True,
            weather={"description": "deszcz", "temperature_c": 12, "wind_speed": 8.2},
        ),
    )
    blurb = build_event_blurb(dossier, _event())
    assert "Regular season · Matchday 27" in blurb
    assert "derby" in blurb
    assert "deszcz" in blurb and "12°C" in blurb and "wiatr 8.2 km/h" in blurb


def test_missing_weather_description_falls_back_to_temperature_and_wind():
    dossier = _dossier(
        fixture_context=FixtureContext(
            weather={"description": None, "temperature_c": 20, "wind_speed": 5.0}
        ),
    )
    blurb = build_event_blurb(dossier, _event())
    assert "20°C" in blurb and "wiatr 5.0 km/h" in blurb


def test_no_fixture_context_and_no_absences_is_an_empty_blurb():
    dossier = _dossier()
    assert build_event_blurb(dossier, _event()) == ""


def test_zero_unavailable_count_is_not_reported():
    dossier = _dossier(
        squad_availability=[
            SquadAvailability(provider_team_id="1", side="home", unavailable_count=0),
        ]
    )
    assert build_event_blurb(dossier, _event()) == ""


def test_absences_are_named_per_side_using_team_a_b_names():
    dossier = _dossier(
        squad_availability=[
            SquadAvailability(provider_team_id="163", side="home", unavailable_count=6),
            SquadAvailability(provider_team_id="168", side="away", unavailable_count=4),
        ]
    )
    blurb = build_event_blurb(dossier, _event())
    assert "nieobecni Botafogo: 6" in blurb
    assert "nieobecni Red Bull Bragantino: 4" in blurb


def test_youth_tier_is_labelled_in_polish():
    dossier = _dossier()
    event = _event(competition="U19 league")
    blurb = build_event_blurb(dossier, event)
    assert "młodzieżowy" in blurb


def test_partial_dossier_with_a_discovery_gap_still_leads_with_it():
    """Regression: --enrich-all's fallback path writes 'event blocked at
    discovery: ...' into data_gaps with readiness=PARTIAL, not BLOCKED. The
    old BLOCKED-only gate silently dropped this reason for exactly that
    dossier shape."""
    dossier = _dossier(
        readiness="PARTIAL",
        data_gaps=["event blocked at discovery: fixture status is 'postponed'"],
    )
    blurb = build_event_blurb(dossier, _event())
    assert "event blocked at discovery" in blurb


def test_a_blocked_dossier_with_real_context_shows_both():
    """A BLOCKED dossier is not guaranteed to be context-empty -- fixture_context
    can be fetched before a later gap blocks the rest. The old early return
    discarded it; now every clause still builds."""
    dossier = _dossier(
        readiness="BLOCKED",
        data_gaps=["not enriched: no price the operator can take"],
        fixture_context=FixtureContext(is_local_derby=True),
    )
    blurb = build_event_blurb(dossier, _event())
    assert "not enriched" in blurb
    assert "derby" in blurb


def test_multiple_gaps_are_all_shown_not_just_the_first():
    dossier = _dossier(
        readiness="BLOCKED",
        data_gaps=["kickoff already passed: cannot be backed pre-match",
                   "no provider returned any data for this event"],
    )
    blurb = build_event_blurb(dossier, _event())
    assert "kickoff already passed" in blurb
    assert "no provider returned any data" in blurb


def test_missing_team_names_fall_back_to_polish_side_labels_not_raw_tokens():
    """team_a_name/team_b_name are optional on EventDossierV1 with no
    guarantee tied to squad_availability being populated -- the fallback
    must not leak the internal 'home'/'away' literal to the reader."""
    dossier = _dossier(
        team_a_name=None, team_b_name=None,
        squad_availability=[
            SquadAvailability(provider_team_id="1", side="home", unavailable_count=3),
        ],
    )
    blurb = build_event_blurb(dossier, _event())
    assert "nieobecni gospodarze: 3" in blurb
    assert "home" not in blurb


def test_unclassified_competition_prints_no_tier_guess():
    """competition_tier() returns None for anything not in the pinned map, and
    the blurb must not invent a label for it -- same rule the map's own
    docstring states."""
    dossier = _dossier()
    event = _event(competition="Some Obscure League Nobody Classified")
    assert build_event_blurb(dossier, event) == ""
