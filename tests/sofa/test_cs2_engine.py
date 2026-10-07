"""CS2 engine and store: the arithmetic against hand-computed values, the
pre-match cut, and the fixes from the 2026-09-28 deep reviews."""

import math
import random
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest

from bet.sofa import cs2_engine as eng
from bet.sofa.cs2 import Cs2Line
from bet.sofa.cs2_store import (
    complete_ids,
    history_summary,
    is_complete,
    maps_reproduce_score,
    save_series,
)
from bet.sofa.db import migrate
from bet.sofa.engine import P_CEILING, P_FLOOR, nb_survival, normal_cdf, predictive_sd

# --- series arithmetic ----------------------------------------------------------


def test_best_of_three_by_hand() -> None:
    d = eng.series_distribution(0.6, 3)
    assert d[(2, 0)] == pytest.approx(0.36)
    assert d[(2, 1)] == pytest.approx(2 * 0.36 * 0.4)  # 0.288
    assert d[(0, 2)] == pytest.approx(0.16)
    assert d[(1, 2)] == pytest.approx(2 * 0.16 * 0.6)  # 0.192
    assert sum(d.values()) == pytest.approx(1.0)


def test_best_of_five_one_and_two() -> None:
    d5 = eng.series_distribution(0.6, 5)
    assert sum(q for (a, b), q in d5.items() if a > b) == pytest.approx(0.68256)
    assert sum(d5.values()) == pytest.approx(1.0)
    d1 = eng.series_distribution(0.7, 1)
    assert d1 == {(1, 0): pytest.approx(0.7), (0, 1): pytest.approx(0.3)}
    assert eng.series_distribution(0.5, 2)[(1, 1)] == pytest.approx(0.5)
    for bad in ((0.5, 4), (1.2, 3), (0.5, 0)):
        with pytest.raises(ValueError):
            eng.series_distribution(*bad)


def test_elo_by_hand() -> None:
    assert eng.elo_expected(1500, 1500) == pytest.approx(0.5)
    assert eng.elo_expected(1900, 1500) == pytest.approx(10 / 11)
    book = eng.EloBook()
    book.update(1, 2)
    assert book.rating(1) == pytest.approx(1500 + eng.ELO_K / 2)
    assert book.rating(2) == pytest.approx(1500 - eng.ELO_K / 2)
    assert not book.rated(1, 2)
    # Raw Elo is exactly the sigmoid of the logit gap.
    book.ratings[1], book.ratings[2] = 1700.0, 1500.0
    assert eng._sigmoid(eng.logit_diff(book, 1, 2)) == pytest.approx(
        eng.elo_expected(1700, 1500)
    )


def test_fit_logistic_recovers_a_known_curve() -> None:
    rng = random.Random(7)
    xs = [rng.uniform(-2, 2) for _ in range(4000)]
    ys = [1.0 if rng.random() < eng._sigmoid(0.3 + 0.6 * x) else 0.0 for x in xs]
    a, b = eng.fit_logistic(xs, ys)
    assert a == pytest.approx(0.3, abs=0.1)
    assert b == pytest.approx(0.6, abs=0.1)


def test_rating_model_is_oriented_to_team1_and_uses_the_home_term() -> None:
    book = eng.EloBook(ratings={1: 1600.0, 2: 1500.0})
    book.played[1] = book.played[2] = eng.MIN_MAPS_RATED
    model = eng.RatingModel(book, a=0.2, b=0.5)
    d = eng.logit_diff(book, 1, 2)
    assert model.p_map(1, 2, team1_is_home=True) == pytest.approx(
        eng._sigmoid(0.2 + 0.5 * d)
    )
    # Team1 away: P(home 2 wins) = sigmoid(a + b * (-d)); team1 gets the rest.
    assert model.p_map(1, 2, team1_is_home=False) == pytest.approx(
        1 - eng._sigmoid(0.2 - 0.5 * d)
    )
    assert eng.RatingModel(eng.EloBook()).p_map(1, 2, True) is None


# --- counts and pushes ------------------------------------------------------------


KILLS = [30, 12, 25, 8, 22, 19, 35, 14, 21, 10]  # var 72 > mean 19.6: NB


def test_count_model_is_the_pipelines_negative_binomial() -> None:
    mean = sum(KILLS) / 10
    var = sum((v - mean) ** 2 for v in KILLS) / 9
    var_pred = predictive_sd(var, mean, 10, apply_poisson_floor=False) ** 2
    over = eng.count_p(KILLS, 19.5, over=True)
    assert over is not None and over.model == "negative_binomial" and over.n == 10
    # OVER 19.5 is X >= 20, i.e. nb_survival(..., 19) = P(X > 19).
    assert over.p == pytest.approx(nb_survival(mean, var_pred, 19))
    under = eng.count_p(KILLS, 19.5, over=False)
    assert under is not None and over.p + under.p == pytest.approx(1.0)
    assert eng.count_p(KILLS[:7], 19.5, over=True) is None  # below MIN_SAMPLE


def test_an_integer_line_leaves_the_push_out_of_both_sides() -> None:
    """Review A-4: the push mass went into UNDER; grade() voids it."""
    mean = sum(KILLS) / 10
    var = sum((v - mean) ** 2 for v in KILLS) / 9
    vp = predictive_sd(var, mean, 10, apply_poisson_floor=False) ** 2
    p_over = nb_survival(mean, vp, 20)  # X > 20
    p_under = 1 - nb_survival(mean, vp, 19)  # X <= 19
    got_over = eng.count_p(KILLS, 20.0, over=True)
    got_under = eng.count_p(KILLS, 20.0, over=False)
    assert got_over is not None and got_under is not None
    assert got_over.p == pytest.approx(p_over / (p_over + p_under))
    assert got_over.p + got_under.p == pytest.approx(1.0)


def test_under_dispersed_counts_use_a_normal() -> None:
    """Review A-6: deaths are bounded by rounds; no Poisson floor on them."""
    deaths = [14, 15, 16, 15, 14, 15, 16, 15, 14, 15]
    mean = sum(deaths) / 10
    var = sum((v - mean) ** 2 for v in deaths) / 9
    vp = predictive_sd(var, mean, 10, apply_poisson_floor=False) ** 2
    sd = math.sqrt(max(vp, eng.MIN_VAR_RATIO * mean))  # the floor binds here
    got = eng.count_p(deaths, 14.5, over=True)
    assert got is not None and got.model == "normal"
    assert got.p == pytest.approx(eng.clamp(1 - normal_cdf((14.5 - mean) / sd)))


def test_rounds_are_shrunk_toward_the_base_rate() -> None:
    """Review A-1: Laplace alone lost to a constant rate."""
    values = [22, 24, 19, 26, 21, 23, 17, 25, 18, 30]  # 7 of 10 over 20.5
    got = eng.shrunk_frequency(values, 20.5, True, base=0.45)
    k = eng.K_ROUNDS
    assert got is not None and got.p == pytest.approx((7 + k * 0.45) / (10 + k))
    under = eng.shrunk_frequency(values, 20.5, False, base=0.45)
    assert under is not None and got.p + under.p == pytest.approx(1.0)
    assert eng.shrunk_frequency(values, 20.5, True, base=None) is None
    # An integer line: the two maps at exactly 22 are neither side.
    pushes = eng.shrunk_frequency(
        [22, 22, 24, 19, 26, 21, 23, 17, 25, 18], 22.0, True, base=0.5
    )
    assert pushes is not None and pushes.n == 8
    assert eng.base_rate([21, 23] * 150, 22.0) == pytest.approx(0.5)
    assert eng.base_rate([21, 23] * 10, 22.0) is None  # under MIN_FIT


def test_clamp_bounds() -> None:
    assert eng.clamp(1.0) == P_CEILING and eng.clamp(0.0) == P_FLOOR
    assert math.isclose(eng.clamp(0.3), 0.3)


# --- history in the store -------------------------------------------------------


A, B, C = 101, 202, 303  # Sofascore team ids


def series(
    eid: int,
    ts: int,
    home: int,
    away: int,
    maps: list[tuple[int | None, int | None]],
    players: dict[int, list[tuple[str, int, str, int]]] | None = None,
    winners: list[int] | None = None,
) -> tuple[dict, list[dict], dict[int, dict]]:
    """(event, games, lineups) in Sofascore's own shapes."""
    games, lineups = [], {}
    home_maps = 0
    for i, (h, a) in enumerate(maps):
        gid = eid * 10 + i
        code = winners[i] if winners else (1 if (h or 0) > (a or 0) else 2)
        home_maps += code == 1
        games.append(
            {
                "id": gid,
                "startTimestamp": ts + i,
                "status": {"type": "finished"},
                "homeScore": {"display": h},
                "awayScore": {"display": a},
                "winnerCode": code,
                "hasCompleteStatistics": True,
            }
        )
        rows = (players or {}).get(i, [])
        lineups[gid] = {
            "homeTeamPlayers": [
                {"player": {"id": pid, "name": n}, "kills": k}
                for side, pid, n, k in rows
                if side == "home"
            ],
            "awayTeamPlayers": [
                {"player": {"id": pid, "name": n}, "kills": k}
                for side, pid, n, k in rows
                if side == "away"
            ],
        }
    event = {
        "id": eid,
        "startTimestamp": ts,
        "homeTeam": {"id": home, "name": f"T{home}"},
        "awayTeam": {"id": away, "name": f"T{away}"},
        "homeScore": {"current": home_maps},
        "awayScore": {"current": len(maps) - home_maps},
        "status": {"type": "finished", "description": "Ended"},
        "tournament": {"name": "CCT", "category": {"name": "Counter Strike"}},
    }
    return event, games, lineups


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    db = str(tmp_path / "t.db")
    migrate(db)
    return sqlite3.connect(db)


def store(conn: sqlite3.Connection, *args: object, **kw: object) -> None:
    event, games, lineups = series(*args, **kw)  # type: ignore[arg-type]
    save_series(conn, event, games, lineups, "2026-09-28T00:00:00Z", True)


def test_history_is_cut_before_the_start_and_excludes_the_graded_series(
    conn: sqlite3.Connection,
) -> None:
    store(conn, 1, 1000, A, B, [(13, 5)])
    store(conn, 2, 2000, A, B, [(13, 7)])
    store(conn, 3, 3000, A, B, [(5, 13)])  # starts after the cut
    assert [m.event_id for m in eng.load_history(conn, 2500, exclude_event=2)] == [1]
    assert [m.event_id for m in eng.load_history(conn, 2500, None)] == [1, 2]


def test_maps_with_only_a_winner_feed_the_ratings_not_the_rounds(
    conn: sqlite3.Connection,
) -> None:
    """Review A-3: 19% of maps had a winner and no rounds, and were dropped."""
    store(conn, 1, 1000, A, B, [(None, None)], winners=[2])
    (m,) = eng.load_history(conn, 5000, None)
    assert m.home_won is False and m.home_rounds is None
    assert eng.total_rounds([m]) == []


def test_a_player_is_followed_by_id_across_teams_not_by_namesake(
    conn: sqlite3.Connection,
) -> None:
    # REZ (id 7) played for C, then moved to A; another "rez" (id 8) plays for B.
    for i in range(10):
        store(
            conn,
            10 + i,
            1000 + i * 10,
            C,
            B,
            [(13, 9)],
            {0: [("home", 7, "REZ", 30), ("away", 8, "rez", 5)]},
        )
    store(conn, 30, 2000, A, B, [(13, 10)], {0: [("home", 7, "REZ", 20)]})
    hist = eng.load_history(conn, 5000, None)
    values = eng.player_values(hist, A, "REZ", "kills")
    assert sorted(values) == sorted([20] + [30] * 10)
    assert 5 not in values


def test_team_kills_needs_five_complete_rows(conn: sqlite3.Connection) -> None:
    five = [("home", i, f"p{i}", 14) for i in range(5)]
    for i in range(8):
        store(conn, 40 + i, 1000 + i, A, B, [(13, 8)], {0: five})
    store(conn, 60, 2000, A, B, [(13, 8)], {0: five[:4]})
    assert eng.team_kills(eng.load_history(conn, 5000, None), A) == [70] * 8


def test_rounds_count_a_shared_map_once(conn: sqlite3.Connection) -> None:
    """Review A-1: when A met B inside both samples, the map was counted twice."""
    for i in range(10):
        store(conn, 70 + i, 1000 + i, A, B, [(13, 9)])  # every map shared
    hist = eng.load_history(conn, 9999, None)
    unique = {(m.event_id, m.order) for m in eng._rounds_maps(hist, A)}
    unique |= {(m.event_id, m.order) for m in eng._rounds_maps(hist, B)}
    assert len(unique) == 10


def dominant_history(conn: sqlite3.Connection) -> list[eng.MapRow]:
    """A beats B on every map of six best-of-three series."""
    for i in range(6):
        store(conn, 70 + i, 1000 + i * 100, A, B, [(13, 6), (13, 9)])
    return eng.load_history(conn, 9999, None)


def test_model_probability_per_family(conn: sqlite3.Connection) -> None:
    hist = dominant_history(conn)
    ratings = eng.build_ratings(hist)  # 12 maps: under MIN_FIT, raw Elo
    assert (ratings.a, ratings.b) == (0.0, 1.0)
    p_map = ratings.p_map(A, B, team1_is_home=True)
    assert p_map is not None and p_map > 0.5

    def mp(
        family: str,
        side: str,
        line: float | None = None,
        subject: str = "",
        map_nr: int = 0,
    ) -> eng.ModelP | None:
        ln = Cs2Line("e", family, map_nr, subject, line, side, 1.9)
        return eng.model_probability(ln, A, B, "TeamA", "TeamB", 3, hist, ratings, True)

    d = eng.series_distribution(round(p_map, 6), 3)
    win = mp("match_winner", "T1")
    assert win is not None and win.p == pytest.approx(eng.clamp(d[(2, 0)] + d[(2, 1)]))
    lose_map = mp("map_winner", "T2", map_nr=1)
    assert lose_map is not None and lose_map.p == pytest.approx(eng.clamp(1 - p_map))
    # Round 2 found the constant-p series overpredicting three-map series;
    # since 2026-10-07 these families read the series-level (Beta-mixed)
    # distribution, never the constant-p one.
    mixed = eng.series_distribution_mixed(eng.clamp(p_map), 3)
    over = mp("maps_total", "OVER", 2.5)
    assert over is not None and over.model == "elo_series_mixed"
    assert over.p == pytest.approx(eng.clamp(mixed[(2, 1)] + mixed[(1, 2)]))
    assert over.p < eng.clamp(d[(2, 1)] + d[(1, 2)])  # fewer deciders
    hcp = mp("maps_handicap", "T1", -1.5)
    assert hcp is not None and hcp.p == pytest.approx(eng.clamp(mixed[(2, 0)]))
    tm = mp("team_maps", "OVER", 0.5, subject="TeamB")
    assert tm is not None and tm.p == pytest.approx(eng.clamp(1 - mixed[(2, 0)]))
    exact = mp("exact_maps", "2:1")
    assert exact is not None and exact.p == pytest.approx(eng.clamp(mixed[(2, 1)]))
    assert mp("rounds_handicap", "T1", 4.5) is None  # never modelled
    # Rounds: 12 maps, fewer than MIN_FIT for a base rate - no number.
    assert mp("map_rounds_total", "OVER", 20.5, map_nr=1) is None


def test_map_rounds_total_is_the_history_base_rate(conn: sqlite3.Connection) -> None:
    """Round 2: the teams' own samples carried nothing; the base rate alone."""
    for i in range(250):
        store(
            conn, 3000 + i, 1000 + i, A + i % 7, B + i % 5, [(13, 9 if i % 4 else 11)]
        )
    hist = eng.load_history(conn, 99_999, None)
    ratings = eng.build_ratings(hist)
    ln = Cs2Line("e", "map_rounds_total", 1, "", 22.5, "OVER", 1.9)
    got = eng.model_probability(ln, A, B, "a", "b", 3, hist, ratings, True)
    # 24 rounds when i % 4 == 0 (63 of 0..249), else 22: 63/250 over 22.5.
    assert got is not None and got.model == "base_rate"
    assert got.p == pytest.approx(63 / 250) and got.n == 250


def test_the_normal_branch_does_not_claim_certainty_from_a_constant() -> None:
    got = eng.count_p([5] * 8, 5.5, over=True)
    assert got is not None and got.model == "normal" and got.p > P_FLOOR


def test_team1_away_flips_the_numbers(conn: sqlite3.Connection) -> None:
    hist = dominant_history(conn)
    ratings = eng.build_ratings(hist)
    ln = Cs2Line("e", "match_winner", 0, "", None, "T1", 1.9)
    as_home = eng.model_probability(ln, A, B, "a", "b", 3, hist, ratings, True)
    # Superbet's team1 is B (the weak side, Sofascore's away).
    weak = eng.model_probability(ln, B, A, "b", "a", 3, hist, ratings, False)
    assert as_home is not None and weak is not None
    assert as_home.p > 0.5 > weak.p
    assert as_home.p == pytest.approx(1 - weak.p)


def test_no_rating_no_number(conn: sqlite3.Connection) -> None:
    store(conn, 90, 1000, A, B, [(13, 6)])
    hist = eng.load_history(conn, 9999, None)
    ln = Cs2Line("e", "match_winner", 0, "", None, "T1", 1.9)
    ratings = eng.build_ratings(hist)
    assert eng.model_probability(ln, A, B, "a", "b", 3, hist, ratings, True) is None


def test_calibration_shrinks_an_overconfident_elo(conn: sqlite3.Connection) -> None:
    """Review A-2: raw Elo overrated favourites; the fit on its own
    walk-forward predictions must pull b below 1 when results are noisier."""
    rng = random.Random(3)
    teams = list(range(1, 21))
    strength = {t: rng.gauss(0, 0.5) for t in teams}
    ts = 1000
    for eid in range(600):
        h, a = rng.sample(teams, 2)
        p = eng._sigmoid(strength[h] - strength[a] + 0.15)  # a home edge
        maps = [(13, 9) if rng.random() < p else (9, 13) for _ in range(2)]
        store(conn, 1000 + eid, ts + eid, h, a, maps)
    ratings = eng.build_ratings(eng.load_history(conn, 10_000, None))
    assert ratings.n_fit >= eng.MIN_FIT
    assert ratings.a > 0  # the home edge is found
    bt = eng.elo_backtest(eng.load_history(conn, 10_000, None))
    assert bt["maps_held_out"] > 0 and bt["brier_calibrated_held_out"] is not None
    assert bt["brier_calibrated_held_out"] < 0.25


def test_compare_to_price_is_the_arithmetic_it_claims() -> None:
    rows = [
        {"superbet_event_id": "a", "fair_p": 0.6, "model_p": 0.8, "outcome": "WIN"},
        {"superbet_event_id": "a", "fair_p": 0.4, "model_p": 0.2, "outcome": "LOSS"},
        {"superbet_event_id": "b", "fair_p": 0.5, "model_p": None, "outcome": "WIN"},
    ]
    c = eng.compare_to_price(rows, "x")
    assert c is not None and (c.series, c.sides) == (1, 2)
    assert c.brier_price == pytest.approx(0.16)
    assert c.brier_model == pytest.approx(0.04)
    assert c.brier_blend == pytest.approx(0.09)
    assert c.model_beats_price
    assert eng.compare_to_price(rows[2:], "x") is None


# --- the store ----------------------------------------------------------------------


def test_store_roundtrip_and_resumability(conn: sqlite3.Connection) -> None:
    rows = [("home", i, f"h{i}", 10) for i in range(5)]
    rows += [("away", 10 + i, f"a{i}", 9) for i in range(5)]
    event, games, lineups = series(
        500, 1000, A, B, [(13, 11), (16, 14)], {0: rows, 1: rows}
    )
    save_series(conn, event, games, lineups, "t", True)
    assert complete_ids(conn, [500, 501]) == {500}
    maps = conn.execute(
        "SELECT map_order, home_rounds, away_rounds, has_player_rows FROM cs2_map "
        "ORDER BY map_order"
    ).fetchall()
    assert maps == [(1, 13, 11, 1), (2, 16, 14, 1)]
    # A settle run that did not fetch lineups keeps what the backfill stored.
    save_series(conn, event, games, {}, "t2", True)
    assert conn.execute("SELECT COUNT(*) FROM cs2_player_map").fetchone()[0] == 20
    summary = history_summary(conn)
    assert (summary["series"], summary["maps_finished"], summary["player_rows"]) == (
        1,
        2,
        20,
    )
    assert summary["maps_with_players"] == 2 and summary["teams"] == 2


def test_a_changed_game_list_leaves_no_stale_map(conn: sqlite3.Connection) -> None:
    """Review B-2: map 12 survived a re-listing and map_order 1 appeared twice."""
    event, games, lineups = series(7, 1000, A, B, [(13, 5), (13, 9), (5, 13)])
    save_series(conn, event, games, lineups, "t", False)
    relisted = [dict(games[1], id=999, startTimestamp=1000), games[1]]
    save_series(conn, event, relisted, {}, "t2", False)
    got = conn.execute(
        "SELECT game_id, map_order FROM cs2_map WHERE sofascore_event_id = 7 "
        "ORDER BY map_order"
    ).fetchall()
    assert got == [(999, 1), (71, 2)]


def test_a_404_games_list_is_not_complete() -> None:
    """Review B-1: 17205934, a 2-0, was stored complete with zero maps."""
    event, games, lineups = series(8, 1000, A, B, [(13, 5), (13, 9)])
    assert not is_complete(event, [], {}, timedelta(hours=5))
    assert not maps_reproduce_score(event, games[:1])
    assert maps_reproduce_score(event, games)
    walkover = {**event, "status": {"type": "finished", "description": "Walkover"}}
    assert is_complete(walkover, [], {}, timedelta(hours=1))
    # A placeholder "notstarted" map in a walkover is not a map (round 2).
    placeholder = [{"id": 1, "status": {"type": "notstarted"}}]
    assert is_complete(walkover, placeholder, {}, timedelta(hours=1))
    # An "Ended" 0-0 with nothing listed is missing data (round 2).
    empty = {**event, "homeScore": {"current": 0}, "awayScore": {"current": 0}}
    assert not is_complete(empty, [], {}, timedelta(hours=5))
    # A permanent gap stops being asked after GAP_GIVE_UP.
    assert is_complete(event, [], {}, timedelta(days=15))


def test_is_complete_waits_for_player_rows_then_gives_up() -> None:
    event, games, lineups = series(600, 1000, A, B, [(13, 5)])
    assert not is_complete(event, games, lineups, timedelta(hours=5))  # 0 rows
    assert is_complete(event, games, lineups, timedelta(hours=80))
    pending = {**event, "status": {"type": "inprogress"}}
    assert not is_complete(pending, games, lineups, timedelta(hours=80))


def test_a_complete_flag_that_the_data_contradicts_is_asked_again(
    conn: sqlite3.Connection,
) -> None:
    """Rows written before the score check: a 2-0 flagged complete with no maps."""
    event, games, lineups = series(9, 1000, A, B, [(13, 5), (13, 9)])
    save_series(conn, event, [], {}, "t", True)  # the old, wrong write
    assert complete_ids(conn, [9]) == set()
    save_series(conn, event, games, lineups, "t2", True)
    assert complete_ids(conn, [9]) == {9}
    walkover = {
        **event,
        "id": 10,
        "status": {"type": "finished", "description": "Walkover"},
        "homeScore": {"current": 0},
        "awayScore": {"current": 0},
    }
    save_series(conn, walkover, [], {}, "t", True)
    assert complete_ids(conn, [10]) == {10}


def test_sql_and_python_agree_on_a_zero_winner_code(conn: sqlite3.Connection) -> None:
    """Round 2: winner_code 0 fell back to rounds in Python but not in SQL,
    so the series was re-asked forever."""
    event, games, lineups = series(11, 1000, A, B, [(13, 5)], winners=[0])
    event["homeScore"], event["awayScore"] = {"current": 1}, {"current": 0}
    assert maps_reproduce_score(event, games)  # rounds say home won
    save_series(conn, event, games, lineups, "t", True)
    assert complete_ids(conn, [11]) == {11}


def test_old_gaps_are_waived_by_age_in_sql(conn: sqlite3.Connection) -> None:
    event, _, _ = series(12, 1000, A, B, [(13, 5), (13, 9)])
    save_series(conn, event, [], {}, "t", True)  # a 2-0 with no maps
    assert complete_ids(conn, [12], now_ts=1000 + 3600) == set()
    assert complete_ids(conn, [12], now_ts=1000 + 15 * 86400) == {12}


def test_complete_none_keeps_the_stored_flag(conn: sqlite3.Connection) -> None:
    event, games, lineups = series(13, 1000, A, B, [(13, 5)])
    save_series(conn, event, games, lineups, "t", True)
    save_series(conn, event, games, {}, "t2", None)  # a settle that skipped lineups
    flag = conn.execute("SELECT complete FROM cs2_series WHERE sofascore_event_id = 13")
    assert flag.fetchone() == (1,)


def test_player_lines_get_a_number_through_model_probability(
    conn: sqlite3.Connection,
) -> None:
    """Found live: a team-subject check ran before the player branch, so every
    player line came back None. Tested end to end, not through the helper."""
    for i in range(10):
        store(
            conn,
            4000 + i,
            1000 + i,
            A,
            B,
            [(13, 9)],
            {0: [("home", 7, "REZ", 18 + (i % 5) * 3)]},
        )
    hist = eng.load_history(conn, 99_999, None)
    ratings = eng.build_ratings(hist)
    for side in ("OVER", "UNDER"):
        ln = Cs2Line("e", "player_kills", 1, "REZ", 23.5, side, 1.9)
        got = eng.model_probability(
            ln, A, B, "GamerLegion", "magic", 3, hist, ratings, True
        )
        assert got is not None and got.n == 10, side
    ghost = Cs2Line("e", "player_kills", 1, "nobody", 23.5, "OVER", 1.9)
    assert eng.model_probability(ghost, A, B, "a", "b", 3, hist, ratings, True) is None


def _pmap(eid, ts, home, away, home_won, hp, ap):
    players = tuple((home, pid, f"p{pid}", ()) for pid in hp) + tuple(
        (away, pid, f"p{pid}", ()) for pid in ap)
    return eng.MapRow(eid, ts, 1, home, away, 13 if home_won else 5,
                      5 if home_won else 13, home_won, players)


def test_the_player_elo_follows_players_not_team_names():
    """Team 1's five players beat everyone; they move to a new team id (3).
    The team-name Elo starts 3 from scratch, the player Elo does not."""
    book = eng.PlayerEloBook()
    stars, others = (1, 2, 3, 4, 5), (6, 7, 8, 9, 10)
    for i in range(10):
        book.update(_pmap(i, i, 1, 2, True, stars, others))
    assert book.ratings[1] > eng.ELO_START > book.ratings[6]
    book.update(_pmap(99, 99, 3, 2, True, stars, others))  # same players, new name
    gap = book.gap(3, 2)
    assert gap is not None and gap > 0


def test_a_lineup_under_four_players_is_not_rated():
    book = eng.PlayerEloBook()
    book.update(_pmap(1, 1, 1, 2, True, (1, 2, 3), (6, 7, 8, 9, 10)))
    assert book.ratings == {} and book.gap(1, 2) is None


def test_build_ratings_uses_the_player_model_once_it_is_fitted():
    hist = []
    rng = __import__("random").Random(3)
    for i in range(400):
        home, away = (1, 2) if i % 2 else (2, 1)
        lineup = {1: (1, 2, 3, 4, 5), 2: (6, 7, 8, 9, 10)}
        won = rng.random() < (0.75 if home == 1 else 0.25)
        hist.append(_pmap(i, i, home, away, won, lineup[home], lineup[away]))
    model = eng.build_ratings(hist)
    assert model.p_fit >= eng.MIN_FIT and model.players is not None
    p = model.p_map(1, 2, team1_is_home=True)
    assert p is not None and p > 0.6


def test_the_map_score_distribution_is_a_race_to_thirteen():
    d = eng.map_score_distribution(0.5)
    assert sum(d.values()) == pytest.approx(1.0, abs=1e-9)
    assert all(max(a, b) >= 13 and a != b for a, b in d)
    assert all(abs(a - b) >= 2 or max(a, b) == 13 for a, b in d if a + b > 24)
    assert eng.map_win_probability(0.5) == pytest.approx(0.5)


def test_the_round_probability_reproduces_the_map_probability():
    for p_map in (0.3, 0.5, 0.7, 0.85):
        assert eng.map_win_probability(eng.round_probability(p_map)) == pytest.approx(
            p_map, abs=1e-3)
        dist = eng.map_distribution_for(p_map)
        assert sum(v for (a, b), v in dist.items() if a > b) == pytest.approx(
            p_map, abs=2e-3)


def test_the_shock_brings_overtime_down_to_the_measured_share():
    plain = eng.map_score_distribution(0.5)
    mixed = eng.mixed_score_distribution(0.5)
    ot = lambda d: sum(v for (a, b), v in d.items() if a + b > 24)  # noqa: E731
    assert ot(mixed) < ot(plain)
    assert 0.08 < ot(mixed) < 0.14


def test_a_round_handicap_is_priced_from_the_rating():
    from bet.sofa.cs2 import Cs2Line

    class R:
        book = eng.EloBook()

        def p_map(self, t1, t2, home):
            return 0.7

    R.book.played.update({1: 50, 2: 50})
    fields = Cs2Line.__dataclass_fields__
    base = {k: None for k in fields}
    base.update(superbet_event_id="1", family="map_rounds_handicap", map_nr=1,
                subject="", line=-3.5, side="T1", odds=1.9)
    line = Cs2Line(**{k: base[k] for k in fields})
    mp = eng.model_probability(line, 1, 2, "A", "B", 3, [], R(), True)
    assert mp is not None and mp.model == "round_race"
    other = Cs2Line(**{**{k: base[k] for k in fields}, "side": "T2"})
    mq = eng.model_probability(other, 1, 2, "A", "B", 3, [], R(), True)
    assert mq is not None and mp.p + mq.p == pytest.approx(1.0, abs=1e-6)
    assert 0.3 < mp.p < 0.7  # a 70% favourite covers -3.5 less often than it wins
