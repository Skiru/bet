"""2026-09-10: fixes for failure modes identified in the 2026-09-09 coupon audit.

Covers:
1. CEILING_QUALITY_MISMATCH (PSG - Slovan Bratislava: 6-1 blowout on goals_total UNDER 4.5).
2. CEILING_SIEGE_CORNER_INVERSION (Rangers - St. Mirren: 12 corners on corners_for UNDER 7.5).
3. Unmeasured tennis prop markets (aces and double faults where ESPN feeds no box-scores).
4. Unsupported league metrics (e.g. Copa Colombia corners where bzzoiro feeds no corners).
5. Sub-1.10 odds floor (e.g. 0-0 on Pohang - Gimcheon @ 1.02).
"""
import pytest
from bet.simple_stats.context_flags import (
    CEILING_QUALITY_MISMATCH,
    CEILING_SIEGE_CORNER_INVERSION,
    is_continental_competition,
    is_quality_mismatch,
    is_siege_corner_match,
    lean_ceilings_for_row,
)
from bet.simple_stats.contracts import (
    EventDossierV1,
    EventListV1,
    EventRecord,
    FixtureContext,
    MetricObservation,
    ProviderValue,
    StatsSheetRow,
    StatsSheetV1,
    SuperbetEventOffer,
    SuperbetLine,
    SuperbetOfferV1,
)
from bet.simple_stats.coupons import (
    CEILING_ZERO_WEIGHT,
    MIN_SINGLE_ODDS_FLOOR,
    _LEAGUE_UNSUPPORTED_METRICS,
    _TENNIS_UNMEASURED_MARKETS,
    build_coupons,
)


def _pv(value: float) -> ProviderValue:
    return ProviderValue(provider="test", value=value, as_of="2026-09-10T00:00:00Z")


def _dossier(
    team_a="Paris Saint-Germain",
    team_b="ŠK Slovan Bratislava",
    league_id="7",
    sport="football",
) -> EventDossierV1:
    return EventDossierV1(
        event_id="test_ev",
        sport=sport,
        team_a_name=team_a,
        team_b_name=team_b,
        readiness="READY",
        fixture_context=FixtureContext(
            league_id=league_id,
            round_name="League phase · Matchday 1",
        ),
    )


def _row(
    event_id="test_ev",
    market="goals_total",
    line=4.5,
    direction="UNDER",
    team_name=None,
    p_low=0.68,
    p_central=0.85,
    sport="football",
    hits=10,
    sample_size=10,
) -> StatsSheetRow:
    return StatsSheetRow(
        event_id=event_id,
        sport=sport,
        market=market,
        line=line,
        direction=direction,
        team_name=team_name,
        hits=hits,
        sample_size=sample_size,
        hit_rate=hits / sample_size,
        p_low=p_low,
        p_central=p_central,
        mean=2.5,
        median=2.5,
        shrunk_mean=2.5,
        dispersion=1.0,
        sources=["bzzoiro"],
        cross_provider_agreement="AGREE",
        data_quality="READY",
        confidence="HIGH",
    )


# --- Moduł 1: CEILING_QUALITY_MISMATCH -------------------------------------


def test_continental_competition_detection():
    assert is_continental_competition(_dossier(league_id="7")) is True   # UCL
    assert is_continental_competition(_dossier(league_id="8")) is True   # UEL
    assert is_continental_competition(_dossier(league_id="83")) is True  # UECL
    assert is_continental_competition(_dossier(league_id="1")) is False  # EPL
    assert is_continental_competition(_dossier(league_id=None)) is False


def test_quality_mismatch_identifies_elite_vs_underdog_in_continental_cup():
    # PSG vs Slovan in Champions League
    dossier = _dossier(team_a="Paris Saint-Germain", team_b="ŠK Slovan Bratislava", league_id="7")
    assert is_quality_mismatch(dossier) is True

    # Real Madrid vs outsider
    dossier = _dossier(team_a="Real Madrid", team_b="FC Sheriff", league_id="7")
    assert is_quality_mismatch(dossier) is True

    # Two elite clubs (Arsenal vs Napoli) - no mismatch
    dossier = _dossier(team_a="Arsenal", team_b="Napoli", league_id="7")
    assert is_quality_mismatch(dossier) is False

    # Domestic league match (PSG vs Marseille in Ligue 1) - domestic context
    dossier = _dossier(team_a="Paris Saint-Germain", team_b="Marseille", league_id="6")
    assert is_quality_mismatch(dossier) is False


def test_quality_mismatch_ceiling_attached_to_goal_unders():
    dossier = _dossier(team_a="Paris Saint-Germain", team_b="ŠK Slovan Bratislava", league_id="7")
    row_under = _row(market="goals_total", line=4.5, direction="UNDER")
    ceilings = lean_ceilings_for_row(row_under, dossier)
    assert CEILING_QUALITY_MISMATCH in ceilings

    # OVER is not penalized
    row_over = _row(market="goals_total", line=2.5, direction="OVER")
    assert CEILING_QUALITY_MISMATCH not in lean_ceilings_for_row(row_over, dossier)

    # Corners are not a goal market
    row_corners = _row(market="corners_total", line=8.5, direction="UNDER")
    assert CEILING_QUALITY_MISMATCH not in lean_ceilings_for_row(row_corners, dossier)


def test_quality_mismatch_in_ceiling_zero_weight():
    assert "QUALITY_MISMATCH" in CEILING_ZERO_WEIGHT


# --- Moduł 2: CEILING_SIEGE_CORNER_INVERSION -------------------------------


def test_siege_corner_match_identifies_dominant_home_club():
    dossier = _dossier(team_a="Rangers", team_b="St. Mirren", league_id="11")
    row_rangers_under = _row(market="corners_for", line=7.5, direction="UNDER", team_name="Rangers")
    assert is_siege_corner_match(row_rangers_under, dossier) is True

    # OVER on Rangers corners is not a siege inversion
    row_rangers_over = _row(market="corners_for", line=7.5, direction="OVER", team_name="Rangers")
    assert is_siege_corner_match(row_rangers_over, dossier) is False

    # St. Mirren corners UNDER is not siege on Rangers
    row_away_under = _row(market="corners_for", line=3.5, direction="UNDER", team_name="St. Mirren")
    assert is_siege_corner_match(row_away_under, dossier) is False


def test_siege_corner_ceiling_attached_to_corner_unders():
    dossier = _dossier(team_a="Rangers", team_b="St. Mirren", league_id="11")
    row = _row(market="corners_for", line=7.5, direction="UNDER", team_name="Rangers")
    ceilings = lean_ceilings_for_row(row, dossier)
    assert CEILING_SIEGE_CORNER_INVERSION in ceilings


def test_siege_corner_in_ceiling_zero_weight():
    assert "SIEGE_CORNER_INVERSION" in CEILING_ZERO_WEIGHT


# --- Moduł 3 & 4 & 5: Coupon exclusions -----------------------------------


def test_unmeasured_tennis_props_excluded_from_coupons():
    sheet = StatsSheetV1(
        run_id="test",
        date="2026-09-10",
        generated_at="2026-09-10T00:00:00Z",
        rows=[
            _row(event_id="tennis_1", market="double_faults_total", line=11.5, direction="UNDER", sport="tennis"),
            _row(event_id="tennis_1", market="aces_total", line=8.5, direction="OVER", sport="tennis"),
            _row(event_id="tennis_1", market="total_games", line=22.5, direction="OVER", sport="tennis"),
        ],
    )
    events = EventListV1(
        date="2026-09-10",
        generated_at="2026-09-10T00:00:00Z",
        events=[
            EventRecord(
                event_id="tennis_1",
                sport="tennis",
                competition="WTA US Open",
                player_one="Mirra Andreeva",
                player_two="Coco Gauff",
                start_time="2026-09-10T20:00:00Z",
                status="ACTIVE",
                identity_confidence="CONFIRMED",
            )
        ],
    )
    coupons = build_coupons(sheet, events)
    assert coupons.excluded.get("tennis_unmeasured_prop") == 2
    # total_games is a length market and survives
    surviving_markets = [s.market for s in coupons.singles]
    assert "double_faults_total" not in surviving_markets
    assert "aces_total" not in surviving_markets


def test_unsupported_league_metrics_excluded():
    sheet = StatsSheetV1(
        run_id="test",
        date="2026-09-10",
        generated_at="2026-09-10T00:00:00Z",
        rows=[
            _row(event_id="colombia_1", market="corners_total", line=8.5, direction="OVER"),
            _row(event_id="colombia_1", market="goals_total", line=2.5, direction="OVER"),
        ],
    )
    events = EventListV1(
        date="2026-09-10",
        generated_at="2026-09-10T00:00:00Z",
        events=[
            EventRecord(
                event_id="colombia_1",
                sport="football",
                competition="Copa Colombia",
                home_team="Real Cundinamarca",
                away_team="Internacional de Bogotá",
                start_time="2026-09-10T20:00:00Z",
                status="ACTIVE",
                identity_confidence="CONFIRMED",
                fixture_context=FixtureContext(league_id="81"),
            )
        ],
    )
    coupons = build_coupons(sheet, events)
    assert coupons.excluded.get("league_metric_unsupported") == 1
    surviving_markets = [s.market for s in coupons.singles]
    assert "corners_total" not in surviving_markets


def test_odds_below_floor_excluded():
    sheet = StatsSheetV1(
        run_id="test",
        date="2026-09-10",
        generated_at="2026-09-10T00:00:00Z",
        rows=[
            _row(event_id="match_low", market="goals_total", line=0.5, direction="OVER"),
        ],
    )
    events = EventListV1(
        date="2026-09-10",
        generated_at="2026-09-10T00:00:00Z",
        events=[
            EventRecord(
                event_id="match_low",
                sport="football",
                competition="K League 1",
                home_team="Pohang Steelers",
                away_team="Gimcheon Sangmu",
                start_time="2026-09-10T20:00:00Z",
                status="ACTIVE",
                identity_confidence="CONFIRMED",
            )
        ],
    )
    offer = SuperbetOfferV1(
        date="2026-09-10",
        generated_at="2026-09-10T00:00:00Z",
        events=[
            SuperbetEventOffer(
                superbet_event_id="sb_1",
                superbet_match_name="Pohang Steelers - Gimcheon Sangmu",
                sport="football",
                kickoff="2026-09-10T20:00:00Z",
                event_id="match_low",
                lines=[
                    SuperbetLine(
                        market="goals_total",
                        line=0.5,
                        direction="OVER",
                        price=1.02,
                        source_market_name="Liczba goli",
                        source_outcome_name="powyżej 0.5",
                    ),
                    SuperbetLine(
                        market="goals_total",
                        line=0.5,
                        direction="UNDER",
                        price=12.0,
                        source_market_name="Liczba goli",
                        source_outcome_name="poniżej 0.5",
                    ),
                ],
            )
        ],
    )
    coupons = build_coupons(sheet, events, superbet_offer=offer, min_odds_floor=1.10)
    assert coupons.excluded.get("odds_below_floor") == 1
    assert len(coupons.singles) == 0
