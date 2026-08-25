"""Tests for bet.simple_stats.analyze: hit-rate STATS_SHEET_V1 rows."""
from bet.stats.market_ranking import STANDARD_MARKET_LINES

from bet.simple_stats.analyze import (
    _cross_provider_agreement,
    analyze_dossier,
    compute_hit_rate,
)
from bet.simple_stats.contracts import EventDossierV1, MetricObservation, ProviderValue


def _pv(provider, value, match_date, opponent="Opponent FC", match_id="m"):
    return ProviderValue(
        provider=provider,
        match_id=match_id,
        match_date=match_date,
        opponent=opponent,
        value=value,
        observed_at="2026-01-01T00:00:00+00:00",
    )


def test_hit_rate_not_replaced_by_mean():
    # One outlier drags the mean above the line even though only 1 of 5
    # matches actually cleared it -- hit_rate must reflect that, not the mean.
    values = [2.0, 3.0, 4.0, 4.0, 35.0]
    mean = sum(values) / len(values)
    assert mean > 9.5

    hits, total, pushes = compute_hit_rate(values, 9.5, "OVER")
    assert (hits, total, pushes) == (1, 5, 0)
    assert hits / total == 0.2


def test_all_standard_lines_tested():
    values = [8.0, 9.0, 10.0, 11.0, 12.0, 9.0, 10.0, 8.0]
    obs = MetricObservation(
        canonical_name="corners_total",
        team_a_l10=[_pv("espn-football", v, f"2026-01-{i + 1:02d}", match_id=f"a{i}") for i, v in enumerate(values)],
    )
    dossier = EventDossierV1(
        event_id="evt1",
        sport="football",
        metrics={"corners_total": obs},
        readiness="READY",
        data_gaps=[],
    )

    rows = analyze_dossier(dossier)
    corners_market = next(m for m in STANDARD_MARKET_LINES["football"] if m["market"] == "Corners Total")

    seen = {(r.line, r.direction) for r in rows if r.market == "corners_total"}
    for line in corners_market["lines"]:
        assert (line, "OVER") in seen
        assert (line, "UNDER") in seen


def test_blocked_dossier_never_reaches_analyze():
    dossier = EventDossierV1(event_id="evt2", sport="football", metrics={}, readiness="BLOCKED", data_gaps=["x"])
    assert analyze_dossier(dossier) == []


def test_sample_size_zero_rows_are_not_emitted():
    dossier = EventDossierV1(
        event_id="evt3",
        sport="tennis",
        metrics={},  # no observations at all for any tennis market
        readiness="PARTIAL",
        data_gaps=["no data"],
    )
    assert analyze_dossier(dossier) == []


def test_agreement_survives_differing_opponent_spellings():
    """Providers spell the same opponent differently ("Ulsan Hyundai FC" vs
    "Ulsan HD") and stamp dates in different formats. Keying agreement on the
    raw opponent string made every cross-provider pair read as SINGLE_SOURCE,
    silently disabling the check the pipeline exists to surface.
    """
    observations = [
        ProviderValue(
            provider="sportdb", match_id="a", match_date="2026-07-26T10:30:00.000Z",
            opponent="Ulsan HD", value=9.0, observed_at="2026-08-25T00:00:00+00:00",
        ),
        ProviderValue(
            provider="api-football", match_id="b", match_date="2026-07-26T05:00:00+00:00",
            opponent="Ulsan Hyundai FC", value=9.0, observed_at="2026-08-25T00:00:00+00:00",
        ),
    ]
    assert _cross_provider_agreement("corners_total", observations) == "AGREE"


def test_same_day_different_matches_are_not_conflated():
    """Two teams both played on the same day against different opponents;
    that is not corroboration of one match."""
    observations = [
        ProviderValue(
            provider="sportdb", match_id="a", match_date="2026-07-26T10:30:00.000Z",
            opponent="Ulsan HD", value=9.0, observed_at="2026-08-25T00:00:00+00:00",
        ),
        ProviderValue(
            provider="api-football", match_id="b", match_date="2026-07-26T05:00:00+00:00",
            opponent="Daejeon", value=3.0, observed_at="2026-08-25T00:00:00+00:00",
        ),
    ]
    assert _cross_provider_agreement("corners_total", observations) == "SINGLE_SOURCE"


def test_disagreement_detected_across_spellings():
    observations = [
        ProviderValue(
            provider="sportdb", match_id="a", match_date="2026-07-26T10:30:00.000Z",
            opponent="Ulsan HD", value=9.0, observed_at="2026-08-25T00:00:00+00:00",
        ),
        ProviderValue(
            provider="api-football", match_id="b", match_date="2026-07-26T05:00:00+00:00",
            opponent="Ulsan Hyundai FC", value=15.0, observed_at="2026-08-25T00:00:00+00:00",
        ),
    ]
    assert _cross_provider_agreement("corners_total", observations) == "DISAGREE"
