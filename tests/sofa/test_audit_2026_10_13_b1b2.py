"""Audit 2026-10-13 B1 (game state) and B2 (UNRATED_MARKETS: rating and the
league venue multiplier). Offline and fast. Evidence:
docs/sofa/evidence/game_state_2026-10-13.md,
docs/sofa/evidence/unrated_markets_2026-10-13.md."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bet.sofa import epochs
from bet.sofa import football_rating as fr
from bet.sofa import game_state as gs
from bet.sofa.contracts import (
    FixtureOffer,
    FixtureSamples,
    MetricSample,
    Observation,
    PricedRung,
)
from scripts.sofa.run_sheet import process_fixture, sheet_row_json
from tests.sofa.test_player_markets import _fixture

DAY = 86400
REPO = Path(__file__).resolve().parents[2]


def _book() -> fr.RatingBook:
    """Team 1 scores 3 and wins corners 7-3 at home; team 2 draws 1-1 with
    corners 5-5 away. League 1, enough matches for its own rate."""
    history = []
    t = 0
    for i in range(fr.MIN_LEAGUE_MATCHES + 10):
        history.append(fr.FootballResult(
            i * 2, t, 1, 1, 100 + i,
            {"goals_for": (3.0, 1.0), "corners_for": (7.0, 3.0),
             "corners_1h_for": (4.0, 1.0)}))
        history.append(fr.FootballResult(
            i * 2 + 1, t + 1, 1, 200 + i, 2,
            {"goals_for": (1.0, 1.0), "corners_for": (5.0, 5.0),
             "corners_1h_for": (2.0, 2.0)}))
        t += DAY
    return fr.replay(history, cut_ts=10**9)


# --- switches -------------------------------------------------------------


@pytest.mark.parametrize("name,pred", [
    ("GAME_STATE_FROM_UTC", epochs.game_state_enabled),
    ("FOOTBALL_RATED_SCOPE_FROM_UTC", epochs.football_rated_scope),
    ("FOOTBALL_VENUE_PRIOR_FROM_UTC", epochs.football_venue_prior),
])
def test_b1_b2_switches_are_off_and_read_the_day_and_the_clock(
        monkeypatch: pytest.MonkeyPatch, name: str, pred: object) -> None:
    assert getattr(epochs, name) is None
    check = pred  # type: ignore[assignment]
    late = datetime(2027, 1, 1, tzinfo=UTC)
    assert not check("2027-01-01", late)  # type: ignore[operator]
    monkeypatch.setattr(epochs, name, datetime(2026, 10, 14, tzinfo=UTC))
    assert check("2026-10-14", datetime(2026, 10, 14, 1, tzinfo=UTC))  # type: ignore[operator]
    assert not check("2026-10-13", late)  # type: ignore[operator]
    assert not check("2026-10-14", datetime(2026, 10, 13, 23, tzinfo=UTC))  # type: ignore[operator]


# --- B1: game state ----------------------------------------------------------


def test_supremacy_is_the_expected_goal_difference_with_the_opposite_sign() -> None:
    fc = fr.FootballForecast(_book(), 1, 1, 2)
    home = fc.centre("goals_for", "side_a")
    away = fc.centre("goals_for", "side_b")
    assert home is not None and away is not None
    s = fc.supremacy("side_a")
    assert s == pytest.approx(home[0] - away[0])
    assert s is not None and s > 0
    assert fc.supremacy("side_b") == pytest.approx(-s)
    # an unrated team has no supremacy
    assert fr.FootballForecast(_book(), 1, 1, 12345).supremacy("side_a") is None


def test_the_game_state_multiplier_is_exp_beta_s_capped() -> None:
    table = gs.GameStateTable({"corners_for": 0.13})
    assert table.multiplier("corners_for", 1.0) == pytest.approx(math.exp(0.13))
    assert table.multiplier("corners_for", -1.0) == pytest.approx(math.exp(-0.13))
    assert table.multiplier("corners_for", 10.0) == pytest.approx(
        math.exp(0.13 * gs.MAX_SUPREMACY))
    assert table.multiplier("shots_for", 1.0) is None  # no beta: untouched
    assert table.multiplier("corners_for", None) is None


def test_fit_beta_recovers_a_known_beta() -> None:
    s = [(i % 21 - 10) / 5 for i in range(400)]
    c = [4.0 + (i % 7) for i in range(400)]
    y = [ci * math.exp(0.2 * si) for ci, si in zip(c, s, strict=True)]
    assert gs.fit_beta(c, s, y) == pytest.approx(0.2, abs=1e-6)
    assert gs.fit_beta(c, s, c) == pytest.approx(0.0, abs=1e-9)


def test_the_shipped_table_reads_and_has_the_measured_signs() -> None:
    table = gs.load_table(REPO / "config" / gs.CONFIG_FILE)
    assert set(table.betas) == set(gs.GAME_STATE_MARKETS)
    # a favourite earns more corners and shots, fewer bookings and fouls
    assert table.betas["corners_for"] > 0 and table.betas["shots_for"] > 0
    assert table.betas["cards_points_for"] < 0 and table.betas["fouls_for"] < 0
    with pytest.raises(ValueError):
        gs.parse_table({"markets": {"goals_for": {"beta": 0.1}}})
    with pytest.raises(ValueError):
        gs.parse_table({"markets": {"corners_for": {"beta": 5.0}}})
    with pytest.raises(ValueError):
        gs.parse_table({})


# --- B2: rated scope and the venue multiplier --------------------------------


def test_the_rated_scope_lets_the_rating_price_an_unrated_market() -> None:
    book = _book()
    assert fr.FootballForecast(book, 1, 1, 2).centre("corners_1h_for", "side_a") is None
    scoped = fr.FootballForecast(book, 1, 1, 2, rated_scope=fr.RATED_SCOPE_MARKETS)
    assert scoped.centre("corners_1h_for", "side_a") is not None
    assert fr.RATED_SCOPE_MARKETS <= fr.UNRATED_MARKETS
    # measured no better: the corners totals stay out of the rating
    assert not {"corners_total", "corners_1h_total", "corners_2h_total"} & (
        fr.RATED_SCOPE_MARKETS)
    assert fr.VENUE_PRIOR_MARKETS <= fr.UNRATED_MARKETS


def test_the_venue_multiplier_is_the_league_rate_over_the_samples_venues() -> None:
    book = _book()
    fc = fr.FootballForecast(book, 1, 1, 2)
    rates = book.league_rates(1, "corners_1h_for")
    assert rates is not None and rates[0] > rates[1]
    mixed = ["home", "away"] * 5
    home = fc.venue_multiplier("corners_1h_for", "side_a", mixed)
    away = fc.venue_multiplier("corners_1h_for", "side_b", mixed)
    assert home == pytest.approx(rates[0] / ((rates[0] + rates[1]) / 2))
    assert away == pytest.approx(rates[1] / ((rates[0] + rates[1]) / 2))
    assert fc.venue_multiplier("corners_1h_for", "side_a", ["home"] * 10) == (
        pytest.approx(1.0))
    assert fc.venue_multiplier("corners_1h_total", "side_a", mixed) is None
    assert fc.venue_multiplier("corners_1h_for", "side_a", [None, None]) is None


# --- SHEET -----------------------------------------------------------------


def _obs(values: list[float], start: int, venues: list[str]) -> list[Observation]:
    return [
        Observation(
            sofascore_event_id=start + i,
            match_date_utc=datetime(2026, 9, 1 + i, tzinfo=UTC),
            opponent=f"O{i}", value=v, competition_id=1, season_id=1,
            venue=venues[i],  # type: ignore[arg-type]
        )
        for i, v in enumerate(values)
    ]


def _rows(market: str, forecast: fr.FootballForecast | None,
          **kwargs: object) -> list[dict[str, object]]:
    from bet.sofa.config import SofaConfig

    values = [5.0, 6.0, 4.0, 7.0, 5.0, 6.0, 5.0, 4.0, 6.0, 5.0]
    venues = ["home", "away"] * 5
    samples = FixtureSamples(
        sofascore_event_id=1, readiness="READY", gaps=[],
        metrics={market: MetricSample(
            metric=market, side_a=_obs(values, 100, venues),
            side_b=_obs(values, 200, venues), h2h=[])},
    )
    offer = FixtureOffer(
        sofascore_event_id=1, status="PRICED", unmapped_markets=[],
        rungs=[PricedRung(market=market, subject="Criciúma", line=4.5,
                          over_odds=1.80, under_odds=1.95,
                          fetched_at_utc=datetime(2026, 9, 22, tzinfo=UTC))],
    )
    rows, _ = process_fixture(
        _fixture(), samples, offer, baselines={}, reliability={},
        engine_constants={}, vetoes=[], config=SofaConfig(), football=forecast,
        **kwargs,  # type: ignore[arg-type]
    )
    return [sheet_row_json(r) for r in rows]


def _over(rows: list[dict[str, object]]) -> dict[str, object]:
    return next(r for r in rows if r["direction"] == "OVER")


def test_switches_off_leave_the_sheet_byte_for_byte() -> None:
    fc = fr.FootballForecast(_book(), 1, 1, 2)
    for market in ("corners_for", "corners_1h_for"):
        plain = _rows(market, fc)
        off = _rows(market, fc, game_state=None, venue_prior_on=False)
        assert json.dumps(plain) == json.dumps(off)
        assert not any("GAME_STATE" in n or "VENUE_PRIOR" in n
                       for r in plain for n in r["notes"])  # type: ignore[attr-defined]


def test_game_state_moves_a_favourites_corners_centre_up() -> None:
    fc = fr.FootballForecast(_book(), 1, 1, 2)
    table = gs.GameStateTable({"corners_for": 0.13})
    s = fc.supremacy("side_a")
    assert s is not None and s > 0
    base = _over(_rows("corners_for", fc))
    moved = _over(_rows("corners_for", fc, game_state=table))
    assert moved["centre"] == pytest.approx(
        float(base["centre"]) * math.exp(0.13 * s), abs=1e-3)  # type: ignore[arg-type]
    assert float(moved["p_central"]) > float(base["p_central"])  # type: ignore[arg-type]
    assert any(n.startswith("GAME_STATE") for n in moved["notes"])  # type: ignore[attr-defined]
    assert any("MAX_SUPREMACY" in n for n in moved["notes"]  # type: ignore[attr-defined]
               if n.startswith("UNFITTED_CONSTANTS"))
    # a market without a beta is untouched
    assert _rows("corners_1h_for", fc, game_state=table) == _rows("corners_1h_for", fc)


def test_venue_prior_and_rated_scope_move_an_unrated_half_corner_centre() -> None:
    book = _book()
    fc = fr.FootballForecast(book, 1, 1, 2)
    base = _over(_rows("corners_1h_for", fc))
    venue = _over(_rows("corners_1h_for", fc, venue_prior_on=True))
    mult = fc.venue_multiplier("corners_1h_for", "side_a", ["home", "away"] * 5)
    assert mult is not None and mult > 1
    assert venue["centre"] == pytest.approx(
        float(base["centre"]) * mult, abs=1e-3)  # type: ignore[arg-type]
    assert any(n.startswith("VENUE_PRIOR") for n in venue["notes"])  # type: ignore[attr-defined]
    scoped = fr.FootballForecast(book, 1, 1, 2, rated_scope=fr.RATED_SCOPE_MARKETS)
    rated = _over(_rows("corners_1h_for", scoped))
    expected = scoped.centre("corners_1h_for", "side_a")
    assert expected is not None
    assert rated["centre"] == pytest.approx(
        fr.W_FOOTBALL_RATING * expected[0]
        + (1 - fr.W_FOOTBALL_RATING) * float(base["centre"]), abs=1e-3)  # type: ignore[arg-type]
    # a rated row never also takes the venue multiplier (the rating has its own)
    both = _over(_rows("corners_1h_for", scoped, venue_prior_on=True))
    assert both["centre"] == rated["centre"]
