"""Tests verifying the 5 Iteration 2 backtest improvements:
1. Rejection of synthetic fallback rows (synthetic_fallback_rejected).
2. Exclusion of unpriceable market families (UNPRICEABLE_MARKET_FAMILIES = red cards).
3. Tightened OVER threshold (min_p_low >= 0.58) and sample size (n >= 12).
4. Default min_odds_floor = 1.25 and 1.35-1.60 sweet-spot bonus in rung_score.
5. Bet Builder leg team_name mapping fallback to subject in backtest_slate.py.
"""
from types import SimpleNamespace

from bet.simple_stats.contracts import (
    EventListV1,
    EventRecord,
    StatsSheetRow,
    StatsSheetV1,
    SuperbetEventOffer,
    SuperbetLine,
    SuperbetOfferV1,
)
from bet.simple_stats.coupons import (
    MIN_SINGLE_ODDS_FLOOR,
    RUNG_BONUS_135_160,
    UNPRICEABLE_MARKET_FAMILIES,
    build_coupons,
)
from scripts.simple import backtest_slate as bt


def _event(event_id="evt-1", competition="Premier League", home=None, away=None):
    return EventRecord(
        event_id=event_id,
        sport="football",
        competition=competition,
        home_team=home or f"Home-{event_id}",
        away_team=away or f"Away-{event_id}",
        start_time="2026-09-15T20:00:00+00:00",
        status="ACTIVE",
        identity_confidence="CONFIRMED",
    )


def _row(
    event_id="evt-1",
    market="corners_total",
    line=8.5,
    direction="UNDER",
    p_low=0.62,
    p_central=0.80,
    sample_size=14,
    hits=11,
    sources=None,
    team_name=None,
    player_id=None,
    player_name=None,
):
    return StatsSheetRow(
        event_id=event_id,
        sport="football",
        market=market,
        line=line,
        direction=direction,
        team_name=team_name,
        player_id=player_id,
        player_name=player_name,
        hits=hits,
        sample_size=sample_size,
        hit_rate=hits / sample_size,
        p_low=p_low,
        p_central=p_central,
        mean=7.5,
        median=7.0,
        shrunk_mean=7.5,
        dispersion=1.2,
        sources=sources or ["bzzoiro"],
        cross_provider_agreement="AGREE",
        data_quality="READY",
        confidence="HIGH",
    )


def _sheet(*rows):
    return StatsSheetV1(
        run_id="test-run",
        date="2026-09-15",
        generated_at="2026-09-15T00:00:00Z",
        rows=list(rows),
    )


def _events(*evs):
    return EventListV1(
        run_id="test-run",
        date="2026-09-15",
        generated_at="2026-09-15T00:00:00Z",
        events=list(evs),
    )


# ---------------------------------------------------------------------------
# 1. Fallback removal & synthetic_fallback_rejected gate
# ---------------------------------------------------------------------------
def test_synthetic_fallback_rejected_gate():
    row_fb = _row(sources=["fallback"])
    row_mixed = _row(event_id="evt-2", sources=["bzzoiro", "fallback_inject"])
    row_valid = _row(event_id="evt-3", sources=["bzzoiro", "espn-football"])

    sheet = _sheet(row_fb, row_mixed, row_valid)
    events = _events(
        _event("evt-1"),
        _event("evt-2", home="Liverpool", away="Everton"),
        _event("evt-3", home="Man City", away="Tottenham"),
    )

    coupons = build_coupons(sheet, events, not_before=None)
    assert coupons.excluded.get("synthetic_fallback_rejected") == 2
    assert len(coupons.singles) == 1
    assert coupons.singles[0].event_id == "evt-3"


# ---------------------------------------------------------------------------
# 2. UNPRICEABLE_MARKET_FAMILIES (Red cards)
# ---------------------------------------------------------------------------
def test_unpriceable_market_families_excluded():
    assert "red_cards_total" in UNPRICEABLE_MARKET_FAMILIES
    assert "red_cards_1h_total" in UNPRICEABLE_MARKET_FAMILIES
    assert "red_cards_2h_total" in UNPRICEABLE_MARKET_FAMILIES
    assert "red_cards_for" in UNPRICEABLE_MARKET_FAMILIES

    rows = [
        _row(event_id="evt-1", market="red_cards_total", line=0.5),
        _row(event_id="evt-2", market="red_cards_1h_total", line=0.5),
        _row(event_id="evt-3", market="red_cards_2h_total", line=0.5),
        _row(event_id="evt-4", market="red_cards_for", line=0.5, team_name="Arsenal"),
        _row(event_id="evt-5", market="corners_total", line=8.5),
    ]
    sheet = _sheet(*rows)
    events = _events(
        _event("evt-1"),
        _event("evt-2"),
        _event("evt-3"),
        _event("evt-4"),
        _event("evt-5"),
    )

    coupons = build_coupons(sheet, events, not_before=None)
    assert coupons.excluded.get("unpriceable_market_family") == 4
    assert len(coupons.singles) == 1
    assert coupons.singles[0].market == "corners_total"


# ---------------------------------------------------------------------------
# 3. OVER lines: min_p_low = 0.58 and summary totals n >= 12
# ---------------------------------------------------------------------------
def test_over_min_p_low_tightened():
    # UNDER with p_low 0.52 clears 0.50 floor
    under_row = _row(event_id="evt-1", direction="UNDER", p_low=0.52, sample_size=15, hits=10)
    # OVER with p_low 0.52 fails 0.58 floor
    over_low = _row(event_id="evt-2", direction="OVER", p_low=0.52, sample_size=15, hits=10)
    # OVER with p_low 0.60 clears 0.58 floor
    over_ok = _row(event_id="evt-3", direction="OVER", p_low=0.60, sample_size=15, hits=11)

    sheet = _sheet(under_row, over_low, over_ok)
    events = _events(_event("evt-1"), _event("evt-2"), _event("evt-3"))

    coupons = build_coupons(sheet, events, not_before=None)
    assert coupons.excluded.get("p_low_below_threshold") == 1
    singles_events = {s.event_id for s in coupons.singles}
    assert "evt-1" in singles_events
    assert "evt-2" not in singles_events
    assert "evt-3" in singles_events


def test_over_summary_totals_require_sample_size_at_least_12():
    # Summary total OVER with n = 10 (< 12) -> excluded
    small_summary_over = _row(
        event_id="evt-1", market="corners_total", direction="OVER", p_low=0.62, sample_size=10, hits=8
    )
    # Summary total OVER with n = 12 (>= 12) -> accepted
    ok_summary_over = _row(
        event_id="evt-2", market="corners_total", direction="OVER", p_low=0.62, sample_size=12, hits=10
    )
    # Summary total UNDER with n = 10 -> NOT excluded by sample_size_below_threshold
    small_summary_under = _row(
        event_id="evt-3", market="corners_total", direction="UNDER", p_low=0.62, sample_size=10, hits=8
    )
    # Team total OVER with n = 10 -> NOT a summary total, not excluded by sample_size_below_threshold
    team_over = _row(
        event_id="evt-4", market="corners_for", team_name="Arsenal", direction="OVER",
        p_low=0.62, sample_size=10, hits=8
    )

    sheet = _sheet(small_summary_over, ok_summary_over, small_summary_under, team_over)
    events = _events(_event("evt-1"), _event("evt-2"), _event("evt-3"), _event("evt-4"))

    coupons = build_coupons(sheet, events, not_before=None)
    assert coupons.excluded.get("sample_size_below_threshold") == 1
    singles_events = {s.event_id for s in coupons.singles}
    assert "evt-1" not in singles_events
    assert "evt-2" in singles_events
    assert "evt-3" in singles_events
    assert "evt-4" in singles_events


# ---------------------------------------------------------------------------
# 4. min_odds_floor = 1.25 default and rung_score bonus
# ---------------------------------------------------------------------------
def test_min_odds_floor_and_sweet_spot_bonus():
    assert MIN_SINGLE_ODDS_FLOOR == 1.25
    assert RUNG_BONUS_135_160 > 0.05

    # Check build_coupons.py argument parser default
    from scripts.simple.build_coupons import _build_parser

    parser = _build_parser()
    actions = {a.dest: a.default for a in parser._actions}
    assert actions.get("min_odds_floor") == 1.25

    # Ladder selection test: rung in 1.35-1.60 gets prioritized with bonus
    row_120 = _row(event_id="evt-1", market="corners_total", line=7.5, direction="UNDER", p_low=0.70)
    row_145 = _row(event_id="evt-1", market="corners_total", line=8.5, direction="UNDER", p_low=0.65)

    # 1) Single line below floor is excluded by odds_below_floor
    offer_below = SuperbetOfferV1(
        date="2026-09-15",
        generated_at="2026-09-15T00:00:00Z",
        events=[
            SuperbetEventOffer(
                superbet_event_id="sb_1",
                superbet_match_name="Arsenal - Chelsea",
                sport="football",
                kickoff="2026-09-15T20:00:00Z",
                event_id="evt-1",
                lines=[
                    SuperbetLine(
                        market="corners_total", line=7.5, direction="UNDER", price=1.22,
                        source_market_name="Rożne", source_outcome_name="poniżej 7.5",
                    ),
                ],
            )
        ],
    )
    coupons_below = build_coupons(_sheet(row_120), _events(_event("evt-1")), superbet_offer=offer_below, min_odds_floor=1.25)
    assert coupons_below.excluded.get("odds_below_floor") == 1
    assert len(coupons_below.singles) == 0

    # 2) Ladder selection test: rung in 1.35-1.60 gets chosen
    offer_ladder = SuperbetOfferV1(
        date="2026-09-15",
        generated_at="2026-09-15T00:00:00Z",
        events=[
            SuperbetEventOffer(
                superbet_event_id="sb_1",
                superbet_match_name="Arsenal - Chelsea",
                sport="football",
                kickoff="2026-09-15T20:00:00Z",
                event_id="evt-1",
                lines=[
                    SuperbetLine(
                        market="corners_total", line=7.5, direction="UNDER", price=1.22,
                        source_market_name="Rożne", source_outcome_name="poniżej 7.5",
                    ),
                    SuperbetLine(
                        market="corners_total", line=8.5, direction="UNDER", price=1.45,
                        source_market_name="Rożne", source_outcome_name="poniżej 8.5",
                    ),
                ],
            )
        ],
    )
    coupons = build_coupons(_sheet(row_120, row_145), _events(_event("evt-1")), superbet_offer=offer_ladder, min_odds_floor=1.25)
    assert len(coupons.singles) == 1
    assert coupons.singles[0].line == 8.5
    assert coupons.singles[0].superbet_price == 1.45


# ---------------------------------------------------------------------------
# 5. Bet Builder leg mapping fallback to subject in backtest_slate.py
# ---------------------------------------------------------------------------
def test_backtest_slate_bb_leg_team_name_or_subject():
    # Create leg with subject instead of team_name
    leg_subject = SimpleNamespace(
        market="goals_for",
        line=1.5,
        direction="UNDER",
        team_name=None,
        subject="Burnley",
        player_name=None,
        player_id=None,
        p_low=0.65,
        tier="LEAN",
        superbet_price=1.40,
        market_verdict="VALUE",
    )
    slip = SimpleNamespace(
        match="Burnley v Middlesbrough",
        rank=1,
        event_id="e1",
        draft=SimpleNamespace(
            legs=[leg_subject],
            legs_priced_separately=True,
            correlation_risk=0.1,
            builder_score=0.75,
        ),
    )
    coupons = SimpleNamespace(slips=[slip], singles=[])
    events = EventListV1(
        run_id="test",
        date="2026-09-15",
        generated_at="2026-09-15T00:00:00Z",
        events=[
            EventRecord(
                event_id="e1",
                sport="football",
                competition="Championship",
                home_team="Burnley",
                away_team="Middlesbrough",
                start_time="2026-09-15T20:00:00Z",
                status="ACTIVE",
                identity_confidence="CONFIRMED",
            )
        ],
    )
    # Actuals: Burnley scored 1, Middlesbrough scored 2
    actuals = {
        "e1": {
            "home": {"goals_for": 1.0},
            "away": {"goals_for": 2.0},
        }
    }

    # Settle slips: Burnley 1 < 1.5 -> WON
    records = bt.settle_slips(coupons, events, actuals)
    assert len(records) == 1
    assert records[0]["outcome"] == "WON"
    assert records[0]["legs_won"] == 1

    # Settle slip legs
    leg_records = bt.settle_slip_legs(coupons, events, actuals)
    assert len(leg_records) == 1
    assert leg_records[0]["outcome"] == "WON"
    assert leg_records[0]["actual"] == 1.0
