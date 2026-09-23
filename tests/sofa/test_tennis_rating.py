"""The tennis rating forecast (bet.sofa.tennis_rating) and how SHEET uses it.

Measured before it was wired in: on 2026-09-18..22 (179 settled matches,
5,375 priced rows) price + rating scored Brier 0.2282 against 0.2329 for the
price + sample SHEET had shipped - cluster-bootstrap difference 0.0047, 95%
[0.0016, 0.0077] - and tied the price alone (0.2284). These tests pin the
pieces that number depends on.
"""

import json
import math
import random
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bet.sofa.contracts import (
    FixtureOffer,
    FixtureSamples,
    MetricSample,
    Observation,
    PricedRung,
)
from bet.sofa.tennis_rating import (
    FEATURES,
    MIN_RATED,
    RATED_MARKETS,
    W_TENNIS_RATING,
    MatchForecast,
    Outcome,
    RatingBook,
    TennisResult,
    blend_with_price,
    build_model,
    fit_logistic,
    load_coefficients,
    parse_event,
    replay,
    surface_family,
    tier_group,
    won_a_set,
)
from scripts.sofa.run_sheet import process_fixture, tennis_forecast
from tests.sofa.test_player_markets import dataclasses_replace_tennis

DAY = 86400


def _result(
    eid: int, ts: int, home: int, away: int, home_won: bool = True,
    sets: tuple[tuple[int, int], ...] = ((6, 3), (6, 4)),
    minutes: float | None = 90.0, completed: bool = True, tier: str = "ITF",
) -> TennisResult:
    return TennisResult(
        event_id=eid, ts=ts, tier=tier, surface="hard", home_id=home,
        away_id=away, home_won=home_won, sets=sets, minutes=minutes,
        completed=completed,
    )


def _event(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": 7,
        "startTimestamp": 1_700_000_000,
        "tournament": {"category": {"name": "Challenger",
                                    "sport": {"slug": "tennis"}}},
        "groundType": "Red clay",
        "homeTeam": {"id": 1, "type": 1},
        "awayTeam": {"id": 2, "type": 1},
        "status": {"type": "finished", "description": "Ended"},
        "winnerCode": 2,
        "homeScore": {"period1": 6, "period2": 3, "period3": 4},
        "awayScore": {"period1": 4, "period2": 6, "period3": 6},
        "time": {"period1": 2400, "period2": 2100, "period3": 2700},
    }
    base.update(over)
    return base


# --- parsing ---------------------------------------------------------------


def test_a_listing_event_becomes_a_result():
    r = parse_event(_event())
    assert r is not None
    assert r.tier == "CH" and r.surface == "clay"
    assert r.sets == ((6, 4), (3, 6), (4, 6))
    assert not r.home_won and r.completed
    assert r.minutes == pytest.approx(120.0)


def test_doubles_walkovers_and_unfinished_matches_are_not_results():
    assert parse_event(_event(homeTeam={"id": 1, "type": 2})) is None
    assert parse_event(
        _event(status={"type": "finished", "description": "Walkover"})) is None
    assert parse_event(
        _event(status={"type": "inprogress", "description": "2nd set"})) is None


def test_a_retirement_is_time_on_court_but_not_a_match_score():
    r = parse_event(_event(status={"type": "finished", "description": "Retired"}))
    assert r is not None and not r.completed


def test_a_missing_set_duration_leaves_minutes_unknown_not_short():
    r = parse_event(_event(time={"period1": 2400, "period2": 2100}))
    assert r is not None and r.minutes is None


def test_labels_fold_to_the_family_the_rating_uses():
    assert surface_family("Hardcourt indoor") == "hard"
    assert surface_family("Red clay indoor") == "clay"
    assert surface_family(None) == "hard"
    assert tier_group("ITF Women") == "ITF"
    assert tier_group("WTA 125") == "CH"
    assert tier_group("ATP") == "TOUR"


# --- the ratings -----------------------------------------------------------


def test_a_match_is_rated_only_from_the_matches_before_it():
    # Player 1 beats player 2 twelve times; the thirteenth match's features
    # must not know the thirteenth result.
    history = [_result(i, 1_000_000 + i * DAY, 1, 2) for i in range(13)]
    history.append(_result(99, 1_000_000 + 13 * DAY, 1, 2, home_won=False))
    _, rated = replay(history, cut_ts=10**10)
    last_result, last_feats = rated[-1]
    assert last_result.event_id == 99
    assert last_feats["lp"] > 0  # still the favourite: the loss is in the future
    book, rated_cut = replay(history, cut_ts=1_000_000 + 13 * DAY)
    assert all(r.event_id != 99 for r, _ in rated_cut)
    assert book.rated(1) == 13


def test_a_retired_match_does_not_move_the_rating():
    book = RatingBook()
    book.update(_result(1, 1000, 1, 2, completed=False))
    assert book.overall[1] == 1500.0 and book.rated(1) == 0
    assert book.log[1].matches, "but it is on the player's log for fatigue"


def test_the_context_terms_read_the_players_own_log():
    book = RatingBook()
    t0 = 10_000_000
    book.update(_result(1, t0 - 40 * DAY, 3, 4))  # player 3, long ago
    book.update(_result(2, t0 - 2 * DAY, 1, 5, minutes=150.0))  # player 1, 2 days
    book.update(_result(3, t0 - 1 * DAY, 1, 6, minutes=60.0))
    f = book.features(1, 3, "hard", t0)
    assert f["dmin78"] == pytest.approx((150.0 + 60.0) / 60.0)
    assert f["dn7"] == 2.0
    assert f["drest"] == -1.0  # player 3 back from 40 days, player 1 is not


def test_fit_logistic_recovers_known_coefficients():
    rng = random.Random(4)
    xs, ys = [], []
    for _ in range(6000):
        x = [rng.gauss(0, 1), rng.gauss(0, 1)]
        p = 1 / (1 + math.exp(-(0.3 + 0.8 * x[0] - 0.5 * x[1])))
        xs.append(x)
        ys.append(1.0 if rng.random() < p else 0.0)
    w = fit_logistic(xs, ys)
    assert w[0] == pytest.approx(0.3, abs=0.1)
    assert w[1] == pytest.approx(0.8, abs=0.1)
    assert w[2] == pytest.approx(-0.5, abs=0.1)


def test_a_config_fitted_on_other_features_is_refused(tmp_path: Path):
    path = tmp_path / "tennis_rating.json"
    path.write_text(json.dumps({"features": ["lp"], "tiers": {}}))
    with pytest.raises(ValueError):
        load_coefficients(path)
    assert load_coefficients(tmp_path / "absent.json") is None


def test_the_checked_in_config_matches_the_features():
    loaded = load_coefficients()
    assert loaded is not None, "config/tennis_rating.json must be checked in"
    coefficients, meta = loaded
    assert set(coefficients) == {"ITF", "CH", "TOUR"}
    assert all(len(c) == len(FEATURES) + 1 for c in coefficients.values())
    assert meta["fitted_from"]["cut_utc"].startswith("2026-09-17")


def test_an_unrated_player_gets_no_forecast():
    history = [_result(i, 1_000_000 + i * DAY, 1, 2 + i) for i in range(MIN_RATED + 1)]
    coefficients = {"ITF": [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0]}
    model = build_model(history, coefficients, cut_ts=10**10)
    kickoff = datetime.fromtimestamp(1_000_000 + 30 * DAY, tz=UTC)
    # player 1 has eleven matches, player 50 none
    assert model.forecast(1, 50, "ITF Men", "Hard", kickoff) is None


# --- reading markets off the neighbours ------------------------------------


def _forecast(home: list[Outcome], away: list[Outcome] | None = None) -> MatchForecast:
    mirrored = [
        Outcome(1 - o.p, o.games_against, o.games_for, o.sets, o.tiebreaks,
                (o.set1[1], o.set1[0]), (o.set2[1], o.set2[0]))
        for o in home
    ]
    return MatchForecast(
        p_home=0.3, neighbours_home=tuple(home),
        neighbours_away=tuple(away if away is not None else mirrored),
        rated_home=20, rated_away=20,
    )


# Home is the underdog: two straight-set losses, one three-set loss, one win.
_POOL = [
    Outcome(0.3, 6, 12, 2, 0, (3, 6), (3, 6)),   # lost by 6
    Outcome(0.3, 8, 12, 2, 0, (4, 6), (4, 6)),   # lost by 4
    Outcome(0.3, 15, 16, 3, 1, (7, 6), (2, 6)),  # lost a decider, by 1
    Outcome(0.3, 12, 9, 2, 0, (6, 4), (6, 5)),   # won
]


def test_handicap_reads_the_subjects_margin_with_the_selections_sign():
    f = _forecast(_POOL)
    # "Home (+5.5)" wins unless home loses by six or more: 3 of 4.
    assert f.probability("handicap_games", "side_a", 5.5, "OVER") == 0.75
    # "Away (-5.5)" is the mirror: only the 6-game loss covers it.
    assert f.probability("handicap_games", "side_b", -5.5, "OVER") == 0.25


def test_an_integer_line_that_lands_is_neither_over_nor_under():
    f = _forecast(_POOL)
    # totals 18, 20, 31, 21
    assert f.probability("games_total", None, 20.0, "OVER") == 0.5
    assert f.probability("games_total", None, 20.0, "UNDER") == 0.25


def test_sets_and_player_games_come_off_the_same_neighbours():
    f = _forecast(_POOL)
    assert f.probability("sets_total", None, 2.5, "OVER") == 0.25
    assert f.probability("games_won_for", "side_a", 7.5, "OVER") == 0.75
    assert f.probability("games_won_for", "side_b", 11.5, "OVER") == 0.75


def test_unmeasured_markets_are_readable_but_not_priced():
    f = _forecast(_POOL)
    assert "tiebreaks_total" not in RATED_MARKETS
    assert f.probability("tiebreaks_total", None, 0.5, "OVER") is None
    assert f.read("tiebreaks_total", None, 0.5, "OVER") == 0.25
    assert f.read("most_games", "draw", 0.0, "OVER") == 0.0
    assert f.probability("aces_total", None, 5.5, "OVER") is None


def test_winning_a_set():
    assert [won_a_set(o) for o in _POOL] == [False, False, True, True]
    assert _forecast(_POOL).p_side_wins_a_set("side_a") == 0.5


def test_the_rating_is_blended_with_the_price_not_substituted_for_it():
    assert blend_with_price(0.8, 0.6) == pytest.approx(
        W_TENNIS_RATING * 0.8 + (1 - W_TENNIS_RATING) * 0.6)
    assert blend_with_price(0.8, None) == 0.8


# --- SHEET -----------------------------------------------------------------


def _obs(values: list[float], start: int) -> list[Observation]:
    return [
        Observation(
            sofascore_event_id=start + i,
            match_date_utc=datetime(2026, 9, 1 + i, tzinfo=UTC),
            opponent=f"O{i}", value=v, competition_id=1, season_id=1, venue=None,
        )
        for i, v in enumerate(values)
    ]


def _samples() -> FixtureSamples:
    games = [18, 20, 22, 19, 25, 21, 17, 23, 20, 24]
    won = [12, 12, 9, 12, 13, 12, 12, 10, 12, 13]
    return FixtureSamples(
        sofascore_event_id=1, readiness="READY", gaps=[],
        metrics={
            "games_total": MetricSample(
                metric="games_total", side_a=_obs(games, 100),
                side_b=_obs(games, 200), h2h=[]),
            "games_won_for": MetricSample(
                metric="games_won_for", side_a=_obs(won, 300),
                side_b=_obs(won, 400), h2h=[]),
            "games_won_set1_for": MetricSample(
                metric="games_won_set1_for",
                side_a=_obs([6, 6, 4, 6, 3, 6, 6, 2, 6, 6], 500),
                side_b=_obs([6, 3, 6, 4, 6, 6, 1, 6, 6, 4], 600), h2h=[]),
        },
    )


def _offer() -> FixtureOffer:
    fetched = datetime(2026, 9, 22, 20, tzinfo=UTC)
    rungs = [
        PricedRung(market="games_total", subject="", line=20.5,
                   over_odds=1.85, under_odds=1.85, fetched_at_utc=fetched),
        PricedRung(market="games_won_for", subject="Kenta Kawada", line=10.5,
                   over_odds=1.70, under_odds=2.00, fetched_at_utc=fetched),
        PricedRung(market="games_won_set1_for", subject="Kenta Kawada", line=4.5,
                   over_odds=1.60, under_odds=2.20, fetched_at_utc=fetched),
    ]
    return FixtureOffer(sofascore_event_id=1, status="PRICED",
                        unmapped_markets=[], rungs=rungs)


def _rows(rating: MatchForecast | None):
    from bet.sofa.config import SofaConfig

    rows, _ = process_fixture(
        dataclasses_replace_tennis(), _samples(), _offer(), baselines={},
        reliability={}, engine_constants={}, vetoes=[], config=SofaConfig(),
        rating=rating,
    )
    return rows


def test_sheet_prices_a_rated_market_from_price_plus_rating():
    rating = _forecast(_POOL)
    rows = _rows(rating)
    over = next(r for r in rows if r.market == "games_total" and r.direction == "OVER")
    expected = blend_with_price(0.5, over.market_p)  # totals 18,20,31,21 > 20.5
    assert over.p_central == pytest.approx(expected, abs=1e-4)
    assert over.sample_frequency is None, "the claim is the rating, not the sample"
    assert any(n.startswith("TENNIS_RATING") for n in over.notes)
    assert not any(n.startswith("P_SHRUNK_TO_PRICE") for n in over.notes)
    assert any("W_TENNIS_RATING" in n for n in over.notes
               if n.startswith("UNFITTED_CONSTANTS"))
    # The sample is still published beside the forecast.
    assert over.sample_size == 20 and over.sample_mean == pytest.approx(20.9)


def test_sheet_reads_a_player_market_from_that_players_side():
    rows = _rows(_forecast(_POOL))
    over = next(r for r in rows
                if r.market == "games_won_for" and r.direction == "OVER")
    # Kenta Kawada is the home player: games 6, 8, 15, 12 -> 2 of 4 over 10.5
    assert over.p_central == pytest.approx(blend_with_price(0.5, over.market_p),
                                           abs=1e-4)


def test_an_unmeasured_market_keeps_the_sample_path():
    rated = _rows(_forecast(_POOL))
    unrated = _rows(None)
    key = ("games_won_set1_for", "OVER")
    a = next(r for r in rated if (r.market, r.direction) == key)
    b = next(r for r in unrated if (r.market, r.direction) == key)
    assert a.p_central == b.p_central
    assert any(n.startswith("P_SHRUNK_TO_PRICE") for n in a.notes)


def test_without_a_rating_nothing_changes():
    rows = _rows(None)
    assert not any(n.startswith("TENNIS_RATING") for r in rows for n in r.notes)


def test_best_of_five_and_football_are_not_forecast():
    fixture = dataclasses_replace_tennis()

    class _Model:
        def forecast(self, *args: object) -> str:
            return "forecast"

    assert tennis_forecast(_Model(), fixture) == "forecast"  # type: ignore[arg-type]
    five = fixture.model_copy(update={"default_period_count": 5})
    assert tennis_forecast(_Model(), five) is None  # type: ignore[arg-type]
    football = fixture.model_copy(update={"sport": "football"})
    assert tennis_forecast(_Model(), football) is None  # type: ignore[arg-type]
    assert tennis_forecast(None, fixture) is None
