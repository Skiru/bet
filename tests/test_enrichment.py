"""Tests for the enrichment module — form computation and trend detection."""

from bet.stats.enrichment import compute_form


def test_compute_form_averages():
    """L10 and L5 averages are computed correctly."""
    values = [10.0, 8.0, 12.0, 9.0, 11.0, 7.0, 13.0, 6.0, 14.0, 5.0]
    result = compute_form(values)

    # L10 avg = (10+8+12+9+11+7+13+6+14+5)/10 = 95/10 = 9.5
    assert result["l10_avg"] == 9.5
    # L5 avg = (10+8+12+9+11)/5 = 50/5 = 10.0
    assert result["l5_avg"] == 10.0


def test_trend_detection_up():
    """Trend 'up' when L5 > L10 by ≥5%."""
    # L10 avg = 10.0, L5 avg = 12.0 → +20% → up
    values = [12.0, 12.0, 12.0, 12.0, 12.0, 8.0, 8.0, 8.0, 8.0, 8.0]
    result = compute_form(values)
    assert result["trend"] == "up"


def test_trend_detection_down():
    """Trend 'down' when L5 < L10 by ≥5%."""
    # L10 avg = 10.0, L5 avg = 8.0 → -20% → down
    values = [8.0, 8.0, 8.0, 8.0, 8.0, 12.0, 12.0, 12.0, 12.0, 12.0]
    result = compute_form(values)
    assert result["trend"] == "down"


def test_trend_detection_stable():
    """Trend 'stable' when L5 and L10 within ±5%."""
    # All same values → 0% change → stable
    values = [10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0]
    result = compute_form(values)
    assert result["trend"] == "stable"


def test_compute_form_empty():
    """Empty values return defaults."""
    result = compute_form([])
    assert result["l10_avg"] == 0.0
    assert result["l5_avg"] == 0.0
    assert result["trend"] == "stable"


def test_compute_form_short_list():
    """Fewer than 5 values: L5 uses all available values."""
    values = [10.0, 12.0, 8.0]
    result = compute_form(values)
    # L10 = (10+12+8)/3 = 10.0
    assert result["l10_avg"] == 10.0
    # L5 = same as L10 since len < 5
    assert result["l5_avg"] == 10.0
