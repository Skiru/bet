"""context_flags.py: circumstances that may argue a row down, never up.

Faza 5b of docs/PLAN_BOGATE_STATYSTYKI.md. Every rule reads fields that already
sit on the dossier -- no new provider call -- and the property under test
throughout is the one that makes this safe to add: a flag may only ever
``ARGUES_AGAINST`` or ``SUPPORTS``, and only ``tier_for_row`` (tested
separately, in test_bet_builder_draft.py) is allowed to act on it, downgrading
never past WEAK.
"""
from bet.simple_stats.contracts import (
    EventDossierV1,
    FixtureContext,
    MetricObservation,
    ProviderValue,
    RefereeProfile,
    SquadAvailability,
    StatsSheetRow,
    TeamSeasonForm,
)
from bet.simple_stats.context_flags import context_flags_for_row


def _row(**overrides):
    kwargs = dict(
        event_id="evt-1", sport="football", market="cards_total", line=4.5,
        direction="OVER", team_name=None, hits=9, sample_size=12, hit_rate=0.75,
        p_low=0.50, mean=4.6, median=4.5, sources=["bzzoiro"],
        cross_provider_agreement="AGREE", confidence="HIGH", data_quality="READY",
    )
    kwargs.update(overrides)
    return StatsSheetRow(**kwargs)


def _dossier(**overrides):
    kwargs = dict(
        event_id="evt-1", sport="football", metrics={}, readiness="READY",
        data_gaps=[], team_a_name="Home FC", team_b_name="Away FC",
    )
    kwargs.update(overrides)
    return EventDossierV1(**kwargs)


def _pv(value, match_id="m1"):
    return ProviderValue(
        provider="bzzoiro", match_id=match_id, match_date="2026-08-01",
        opponent="Someone FC", value=value, observed_at="2026-08-01T00:00:00+00:00",
    )


# --- referee ----------------------------------------------------------------


def test_referee_average_below_the_line_argues_against_over():
    row = _row(market="cards_total", line=4.5, direction="OVER")
    dossier = _dossier(referee=RefereeProfile(
        provider_referee_id="1", matches=20, avg_yellow_per_match=3.2, avg_fouls_per_match=18.0,
    ))
    flags = context_flags_for_row(row, dossier)
    assert len(flags) == 1
    assert flags[0].source == "referee" and flags[0].direction == "ARGUES_AGAINST"


def test_referee_average_above_the_line_argues_against_under_not_over():
    dossier = _dossier(referee=RefereeProfile(
        provider_referee_id="1", matches=20, avg_yellow_per_match=6.0,
    ))
    over_row = _row(market="cards_total", line=4.5, direction="OVER")
    under_row = _row(market="cards_total", line=4.5, direction="UNDER")
    assert context_flags_for_row(over_row, dossier) == []
    flags = context_flags_for_row(under_row, dossier)
    assert len(flags) == 1 and flags[0].direction == "ARGUES_AGAINST"


def test_a_thin_referee_sample_is_not_believed():
    row = _row(market="cards_total", line=4.5, direction="OVER")
    dossier = _dossier(referee=RefereeProfile(
        provider_referee_id="1", matches=2, avg_yellow_per_match=1.0,
    ))
    assert context_flags_for_row(row, dossier) == []


def test_referee_flag_is_scoped_to_match_totals_not_per_team_rows():
    """The average describes the whole match; halving it for a per-team line
    would invent a number the provider never gave."""
    row = _row(market="cards_for", team_name="Home FC", line=2.5, direction="OVER")
    dossier = _dossier(referee=RefereeProfile(
        provider_referee_id="1", matches=20, avg_yellow_per_match=1.0,
    ))
    assert context_flags_for_row(row, dossier) == []


# --- squad availability -------------------------------------------------


def test_four_unavailable_players_argues_against_that_sides_over():
    row = _row(market="shots_for", team_name="Home FC", line=10.5, direction="OVER")
    dossier = _dossier(squad_availability=[
        SquadAvailability(provider_team_id="1", side="home", unavailable_count=4),
    ])
    flags = context_flags_for_row(row, dossier)
    assert len(flags) == 1 and flags[0].source == "squad_availability"


def test_three_unavailable_players_is_not_enough_to_flag():
    row = _row(market="shots_for", team_name="Home FC", line=10.5, direction="OVER")
    dossier = _dossier(squad_availability=[
        SquadAvailability(provider_team_id="1", side="home", unavailable_count=3),
    ])
    assert context_flags_for_row(row, dossier) == []


def test_squad_flag_only_applies_to_the_absent_sides_own_row():
    row = _row(market="shots_for", team_name="Away FC", line=10.5, direction="OVER")
    dossier = _dossier(squad_availability=[
        SquadAvailability(provider_team_id="1", side="home", unavailable_count=6),
    ])
    assert context_flags_for_row(row, dossier) == []


def test_squad_flag_never_applies_to_under():
    row = _row(market="shots_for", team_name="Home FC", line=10.5, direction="UNDER")
    dossier = _dossier(squad_availability=[
        SquadAvailability(provider_team_id="1", side="home", unavailable_count=6),
    ])
    assert context_flags_for_row(row, dossier) == []


# --- derby ----------------------------------------------------------------


def test_local_derby_supports_over_on_cards():
    row = _row(market="cards_total", line=4.5, direction="OVER")
    dossier = _dossier(fixture_context=FixtureContext(is_local_derby=True))
    flags = context_flags_for_row(row, dossier)
    assert len(flags) == 1 and flags[0].direction == "SUPPORTS"


def test_non_derby_has_no_derby_flag():
    row = _row(market="cards_total", line=4.5, direction="OVER")
    dossier = _dossier(fixture_context=FixtureContext(is_local_derby=False))
    assert context_flags_for_row(row, dossier) == []


# --- weather ----------------------------------------------------------------


def test_strong_wind_argues_against_over_on_corners():
    row = _row(market="corners_total", line=9.5, direction="OVER")
    dossier = _dossier(fixture_context=FixtureContext(weather={"wind_speed": 31.0}))
    flags = context_flags_for_row(row, dossier)
    assert len(flags) == 1 and flags[0].source == "weather"


def test_calm_wind_is_not_flagged():
    row = _row(market="corners_total", line=9.5, direction="OVER")
    dossier = _dossier(fixture_context=FixtureContext(weather={"wind_speed": 8.2}))
    assert context_flags_for_row(row, dossier) == []


def test_missing_weather_does_not_crash():
    row = _row(market="corners_total", line=9.5, direction="OVER")
    dossier = _dossier(fixture_context=FixtureContext(weather=None))
    assert context_flags_for_row(row, dossier) == []


# --- season form vs. actual goals -------------------------------------------


def test_a_team_overperforming_its_xg_argues_against_its_own_over():
    row = _row(market="goals_for", team_name="Home FC", line=1.5, direction="OVER")
    dossier = _dossier(
        season_form=[TeamSeasonForm(provider_team_id="1", side="home", xgf=6.0, xg_games=5)],
        metrics={
            "goals_for": MetricObservation(
                canonical_name="goals_for",
                team_a_l10=[_pv(3.0), _pv(3.0), _pv(2.0)],
            )
        },
    )
    flags = context_flags_for_row(row, dossier)
    assert len(flags) == 1 and flags[0].source == "season_form"


def test_a_small_xg_gap_is_not_flagged():
    row = _row(market="goals_for", team_name="Home FC", line=1.5, direction="OVER")
    dossier = _dossier(
        season_form=[TeamSeasonForm(provider_team_id="1", side="home", xgf=9.0, xg_games=5)],
        metrics={
            "goals_for": MetricObservation(
                canonical_name="goals_for",
                team_a_l10=[_pv(2.0), _pv(2.0), _pv(2.0)],
            )
        },
    )
    assert context_flags_for_row(row, dossier) == []


def test_too_few_xg_games_is_not_believed():
    row = _row(market="goals_for", team_name="Home FC", line=1.5, direction="OVER")
    dossier = _dossier(
        season_form=[TeamSeasonForm(provider_team_id="1", side="home", xgf=1.0, xg_games=2)],
        metrics={
            "goals_for": MetricObservation(
                canonical_name="goals_for",
                team_a_l10=[_pv(3.0), _pv(3.0), _pv(3.0)],
            )
        },
    )
    assert context_flags_for_row(row, dossier) == []
