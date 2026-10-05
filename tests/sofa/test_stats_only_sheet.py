"""K0/K1/K11 (plan 2026-10-05): in the stats-only epoch the price does not
enter p_central, the rating is published beside it as `forecast_p`, and an
old-rule sheet is exactly what it was."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from bet.sofa import epochs
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import FixtureOffer, PricedRung
from bet.sofa.football_rating import FootballForecast
from scripts.sofa.run_sheet import process_fixture, sheet_row_json
from tests.sofa.test_football_rating import _rated_book
from tests.sofa.test_football_rating import _samples as football_samples
from tests.sofa.test_player_markets import _fixture
from tests.sofa.test_tennis_rating import _POOL, _forecast, dataclasses_replace_tennis
from tests.sofa.test_tennis_rating import _samples as tennis_samples


def _tennis_offer(over: float, under: float) -> FixtureOffer:
    fetched = datetime(2026, 9, 22, 20, tzinfo=UTC)
    rungs = [
        PricedRung(market="games_total", subject="", line=20.5,
                   over_odds=over, under_odds=under, fetched_at_utc=fetched),
        PricedRung(market="games_won_for", subject="Kenta Kawada", line=10.5,
                   over_odds=over, under_odds=under, fetched_at_utc=fetched),
        PricedRung(market="games_won_set1_for", subject="Kenta Kawada", line=4.5,
                   over_odds=over, under_odds=under, fetched_at_utc=fetched),
    ]
    return FixtureOffer(sofascore_event_id=1, status="PRICED",
                        unmapped_markets=[], rungs=rungs)


def _tennis(over: float, under: float, stats_only: bool, rated: bool = True):
    rows, _ = process_fixture(
        dataclasses_replace_tennis(), tennis_samples(), _tennis_offer(over, under),
        baselines={}, reliability={}, engine_constants={}, vetoes=[],
        config=SofaConfig(), rating=_forecast(_POOL) if rated else None,
        stats_only=stats_only,
    )
    return {(r.market, r.direction): r for r in rows}


def test_p_central_does_not_read_the_price_in_the_stats_only_epoch():
    short = _tennis(1.40, 3.00, stats_only=True)
    long_ = _tennis(3.00, 1.40, stats_only=True)
    assert short.keys() == long_.keys()
    for key, row in short.items():
        assert row.market_p != long_[key].market_p
        assert row.p_central == long_[key].p_central, key
        assert row.epoch == epochs.STATS_ONLY


def test_the_old_rule_still_reads_the_price():
    short = _tennis(1.40, 3.00, stats_only=False)
    long_ = _tennis(3.00, 1.40, stats_only=False)
    key = ("games_total", "OVER")
    assert short[key].p_central != long_[key].p_central
    assert short[key].epoch is None and short[key].forecast_p is None


def test_a_rated_tennis_row_is_priced_by_the_sample_and_forecast_by_the_rating():
    rows = _tennis(1.85, 1.85, stats_only=True)
    plain = _tennis(1.85, 1.85, stats_only=True, rated=False)
    over = rows[("games_total", "OVER")]
    # the rating's own P (totals 18, 20, 31, 21 > 20.5: 2 of 4), unblended
    assert over.forecast_p == pytest.approx(0.5)
    assert over.forecast_source == "tennis_rating"
    # the claim is the sample's estimator, the same with or without a rating
    assert over.p_central == plain[("games_total", "OVER")].p_central
    assert not any(n.startswith(("TENNIS_RATING", "P_SHRUNK_TO_PRICE",
                                 "CENTRE_SHRUNK_TO_LADDER")) for n in over.notes)
    unfitted = " ".join(n for n in over.notes if n.startswith("UNFITTED_CONSTANTS"))
    assert "W_TENNIS_RATING" not in unfitted
    assert "K_TENNIS_LADDER_CENTRE" not in unfitted


def _football_offer(over: float, under: float) -> FixtureOffer:
    return FixtureOffer(
        sofascore_event_id=1, status="PRICED", unmapped_markets=[],
        rungs=[PricedRung(market="goals_total", subject="", line=2.5,
                          over_odds=over, under_odds=under,
                          fetched_at_utc=datetime(2026, 9, 22, tzinfo=UTC))],
    )


def _football(stats_only: bool, forecast: FootballForecast | None,
              over: float = 1.80, under: float = 1.95):
    rows, _ = process_fixture(
        _fixture(), football_samples(), _football_offer(over, under),
        baselines={}, reliability={}, engine_constants={}, vetoes=[],
        config=SofaConfig(), football=forecast, stats_only=stats_only,
    )
    return next(r for r in rows if r.direction == "OVER")


def test_the_football_forecast_is_the_rating_alone_and_model_p_is_unchanged():
    forecast = FootballForecast(_rated_book(), 1, 1, 2)
    new = _football(True, forecast)
    old = _football(False, forecast)
    # p_central (the leg's model_p) keeps the W_FOOTBALL_RATING blend
    assert new.p_central == old.p_central
    assert new.forecast_source == "football_rating"
    assert new.forecast_p is not None and new.forecast_p != new.p_central
    # the forecast does not read the price either
    assert _football(True, forecast, 3.0, 1.3).forecast_p == new.forecast_p
    assert _football(True, None).forecast_p is None


def test_an_old_rule_row_is_written_without_the_new_fields():
    old = _football(False, None)
    assert "epoch" not in sheet_row_json(old)
    assert "forecast_p" not in sheet_row_json(old)
    new = sheet_row_json(_football(True, None))
    assert new["epoch"] == "stats_only" and new["forecast_p"] is None


def test_the_epoch_starts_at_the_cutover_and_honours_a_frozen_clock(monkeypatch):
    before = epochs.STATS_ONLY_FROM_UTC.replace(microsecond=0)
    from datetime import timedelta
    assert epochs.stats_only("2026-10-05", before) is True
    assert epochs.stats_only("2026-10-05", before - timedelta(seconds=1)) is False
    assert epochs.stats_only("2026-10-04", before + timedelta(days=3)) is False
    monkeypatch.setenv("SOFA_NOW", "2026-10-01T10:00:00Z")
    assert epochs.stats_only("2026-10-06") is False
    assert epochs.sheet_epoch([{"epoch": "stats_only"}, {}]) is None
    assert epochs.sheet_epoch([{}]) == epochs.OLD
