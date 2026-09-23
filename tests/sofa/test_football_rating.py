"""Opponent-adjusted football ratings (bet.sofa.football_rating) and SHEET.

Measured before it was wired in: on 2026-09-18..22 (1,360 settled matches,
74,712 priced rows) the rating at W = 0.5 took Brier from 0.1952 to 0.1928 on
every market (0.1922 with the exclusions), better on all five days. These
tests pin what that number depends on: the league a rate comes from, the
opponent a count was earned against, and that only the centre moves.
"""

from datetime import UTC, datetime

import pytest

from bet.sofa.contracts import (
    FixtureOffer,
    FixtureSamples,
    MetricSample,
    Observation,
    PricedRung,
)
from bet.sofa.football_rating import (
    MIN_LEAGUE_MATCHES,
    MIN_TEAM_MATCHES,
    UNRATED_MARKETS,
    W_FOOTBALL_RATING,
    FootballForecast,
    FootballResult,
    RatingBook,
    base_metric,
    parse_event,
    replay,
)
from scripts.sofa.run_sheet import process_fixture
from tests.sofa.test_player_markets import _fixture

DAY = 86400


def _match(
    eid: int, ts: int, home: int, away: int, goals: tuple[float, float],
    competition: int = 1, shots: tuple[float, float] | None = None,
) -> FootballResult:
    values = {"goals_for": goals}
    if shots is not None:
        values["shots_for"] = shots
    return FootballResult(eid, ts, competition, home, away, values)


def _league(n: int, competition: int, goals: tuple[float, float], start: int = 0,
            teams: tuple[int, int] = (900, 901)) -> list[FootballResult]:
    return [
        _match(start + i, start + i * DAY, teams[0] + 2 * i, teams[1] + 2 * i,
               goals, competition)
        for i in range(n)
    ]


def test_market_names_map_to_their_per_side_metric():
    assert base_metric("corners_total") == "corners_for"
    assert base_metric("goals_1h_for") == "goals_1h_for"
    assert base_metric("both_over_goals") is None
    assert base_metric("xg_total") is None


def test_a_listing_event_carries_goals_and_halves():
    event = {
        "id": 5, "startTimestamp": 1000,
        "tournament": {"id": 77, "uniqueTournament": {"id": 17},
                       "category": {"sport": {"slug": "football"}}},
        "status": {"type": "finished", "code": 100},
        "homeTeam": {"id": 1}, "awayTeam": {"id": 2},
        "homeScore": {"current": 2, "period1": 1, "period2": 1},
        "awayScore": {"current": 1, "period1": 0, "period2": 1},
    }
    r = parse_event(event)
    assert r is not None and r.competition_id == 17  # uniqueTournament, as fixtures
    assert r.values["goals_for"] == (2.0, 1.0)
    assert r.values["goals_1h_for"] == (1.0, 0.0)
    assert "corners_for" not in r.values, "no statistics, no corners - never 0.0"


def test_each_league_keeps_its_own_rate():
    history = _league(40, 1, (3.0, 2.0)) + _league(40, 2, (1.0, 0.0), start=10_000)
    history.sort(key=lambda r: r.ts)
    book = replay(history, cut_ts=10**9)
    high = book.league_rates(1, "goals_for")
    low = book.league_rates(2, "goals_for")
    assert high is not None and low is not None
    assert high[0] == pytest.approx(3.0) and high[1] == pytest.approx(2.0)
    assert low[0] == pytest.approx(1.0) and low[1] == pytest.approx(0.0)


def test_a_thin_league_falls_back_to_the_global_rate():
    history = _league(MIN_LEAGUE_MATCHES, 1, (2.0, 1.0)) + _league(
        3, 2, (5.0, 5.0), start=100_000)
    book = replay(history, cut_ts=10**9)
    rates = book.league_rates(2, "goals_for")
    assert rates is not None and rates[0] < 5.0  # not its own three matches


def test_a_count_is_read_against_the_opponent_it_was_earned_against():
    # Team 1 scores 3 against a leaky side (2) and team 3 scores 3 against a
    # tight one (4). Same raw count; the rating must credit team 3 more.
    history = _league(MIN_LEAGUE_MATCHES, 1, (1.5, 1.0), start=0)
    t = MIN_LEAGUE_MATCHES * DAY
    eid = 10_000
    for i in range(20):  # establish 2 as leaky, 4 as tight
        history.append(_match(eid, t, 50 + i, 2, (0.0, 0.0)))
        history.append(_match(eid + 1, t + 1, 70 + i, 2, (3.0, 1.0)))
        history.append(_match(eid + 2, t + 2, 90 + i, 4, (0.0, 0.0)))
        eid += 3
        t += DAY
    history.append(_match(eid, t, 1, 2, (3.0, 1.0)))
    history.append(_match(eid + 1, t + 1, 3, 4, (3.0, 1.0)))
    book = replay(history, cut_ts=10**12)
    assert book.teams[(2, "goals_for")].defence > book.teams[(4, "goals_for")].defence
    assert book.teams[(3, "goals_for")].attack > book.teams[(1, "goals_for")].attack


def test_a_match_is_rated_only_from_the_matches_before_it():
    history = _league(MIN_LEAGUE_MATCHES + 5, 1, (1.0, 1.0))
    later = _match(99_999, 10**8, 900, 901, (9.0, 9.0))
    book = replay([*history, later], cut_ts=10**8)
    rates = book.league_rates(1, "goals_for")
    assert rates is not None and rates[0] == pytest.approx(1.0)


def _rated_book() -> RatingBook:
    history = []
    t = 0
    for i in range(MIN_LEAGUE_MATCHES + 10):
        # teams 1 and 2 play everyone else; 1 always scores 3, 2 always 1
        history.append(_match(i * 2, t, 1, 100 + i, (3.0, 1.0)))
        history.append(_match(i * 2 + 1, t + 1, 200 + i, 2, (1.0, 1.0)))
        t += DAY
    return replay(history, cut_ts=10**9)


def test_the_forecast_is_rate_times_attack_times_opponent_defence():
    book = _rated_book()
    f = FootballForecast(book, 1, 1, 2)
    exp = book.expected(1, 1, 2, "goals_for")
    assert exp is not None
    total = f.centre("goals_total", None)
    home = f.centre("goals_for", "side_a")
    away = f.centre("goals_for", "side_b")
    assert total is not None and home is not None and away is not None
    assert total[0] == pytest.approx(exp[0] + exp[1])
    assert home[0] == pytest.approx(exp[0]) and away[0] == pytest.approx(exp[1])
    assert home[0] > away[0]


def test_unrated_teams_and_excluded_markets_get_no_centre():
    book = _rated_book()
    assert FootballForecast(book, 1, 1, 12345).centre("goals_total", None) is None
    assert book.team_matches(12345, "goals_for") < MIN_TEAM_MATCHES
    assert "corners_total" in UNRATED_MARKETS
    assert FootballForecast(book, 1, 1, 2).centre("corners_total", None) is None
    assert FootballForecast(book, 1, 1, 2).centre("shots_total", None) is None


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
    goals = [2, 3, 1, 4, 2, 3, 2, 1, 3, 2]
    return FixtureSamples(
        sofascore_event_id=1, readiness="READY", gaps=[],
        metrics={"goals_total": MetricSample(
            metric="goals_total", side_a=_obs(goals, 100),
            side_b=_obs(goals, 200), h2h=[])},
    )


def _offer() -> FixtureOffer:
    return FixtureOffer(
        sofascore_event_id=1, status="PRICED", unmapped_markets=[],
        rungs=[PricedRung(market="goals_total", subject="", line=2.5,
                          over_odds=1.80, under_odds=1.95,
                          fetched_at_utc=datetime(2026, 9, 22, tzinfo=UTC))],
    )


def _rows(forecast: FootballForecast | None):
    from bet.sofa.config import SofaConfig

    rows, _ = process_fixture(
        _fixture(), _samples(), _offer(), baselines={}, reliability={},
        engine_constants={}, vetoes=[], config=SofaConfig(), football=forecast,
    )
    return rows


def test_sheet_moves_the_centre_and_nothing_else():
    book = _rated_book()
    forecast = FootballForecast(book, 1, 1, 2)
    rated = next(r for r in _rows(forecast) if r.direction == "OVER")
    plain = next(r for r in _rows(None) if r.direction == "OVER")
    expected = forecast.centre("goals_total", None)
    assert expected is not None
    assert rated.centre == pytest.approx(
        W_FOOTBALL_RATING * expected[0] + (1 - W_FOOTBALL_RATING) * plain.centre,
        abs=1e-3)
    assert rated.sample_mean == plain.sample_mean
    assert rated.sample_sd == plain.sample_sd
    assert rated.p_central > plain.p_central  # team 1 scores 3 a match
    assert any(n.startswith("FOOTBALL_RATING") for n in rated.notes)
    assert any("W_FOOTBALL_RATING" in n for n in rated.notes
               if n.startswith("UNFITTED_CONSTANTS"))
    assert not any(n.startswith("FOOTBALL_RATING") for n in plain.notes)
