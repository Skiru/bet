"""The cache replay prices tennis games as SHEET does since
epochs.TENNIS_RATING_PRICES_FROM_UTC (2026-10-07): the rating's neighbours as
of the match's day, built incrementally, never from a later match.

AsOfRating must be build_model at every cut; the replay's p must be
MatchForecast.read (the three RATING_PRICED markets) and the 50/50 mix with the
NB for games_total; handicap_games / most_games rows settle like
run_settle._settle_derived.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime

import pytest

from bet.sofa.tennis_rating import (
    FEATURES,
    NEIGHBOURS,
    W_GAMES_TOTAL_RATING,
    AsOfRating,
    TennisResult,
    build_model,
)
from scripts.sofa.calibrate_from_cache import (
    MIN_SAMPLE,
    Played,
    RatingReplay,
    TennisContext,
    iter_rows,
)

DAY = 86400
T0 = 1_700_000_000 - 1_700_000_000 % DAY
COEF = {"TOUR": [0.0, 0.8, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]}
PLAYERS = 40


def _history(n_days: int = 80, per_day: int = 24, seed: int = 3
             ) -> list[TennisResult]:
    rng = random.Random(seed)
    strength = {p: rng.gauss(0.0, 1.0) for p in range(1, PLAYERS + 1)}
    out: list[TennisResult] = []
    eid = 1
    for d in range(n_days):
        for k in range(per_day):
            h, a = rng.sample(range(1, PLAYERS + 1), 2)
            p_home = 1.0 / (1.0 + 2.718 ** (strength[a] - strength[h]))
            home_won = rng.random() < p_home
            sets = [(6, rng.randint(0, 4)), (rng.randint(0, 4), 6)]
            if rng.random() < 0.4:
                sets.append((6, 3) if home_won else (3, 6))
            if not home_won and len(sets) == 2:
                sets = [(b, a_) for a_, b in sets]
            n_h = sum(1 for x, y in sets if x > y)
            n_a = len(sets) - n_h
            if (n_h > n_a) != home_won:
                sets = [(y, x) for x, y in sets]
            out.append(TennisResult(
                event_id=eid, ts=T0 + d * DAY + k * 3000, tier="TOUR",
                surface="hard", home_id=h, away_id=a, home_won=home_won,
                sets=tuple(sets), minutes=95.0, completed=True))
            eid += 1
    return out


def _forecast_key(model, home: int, away: int, ts: int):
    fc = model.forecast(home, away, "ATP", "Hard", datetime.fromtimestamp(ts, UTC))
    return None if fc is None else (fc.p_home, fc.neighbours_home,
                                    fc.neighbours_away)


def test_as_of_rating_is_build_model_at_every_cut() -> None:
    history = _history()
    asof = AsOfRating(history, COEF, FEATURES)
    for d in (50, 60, 79):
        cut = T0 + d * DAY
        want = build_model(history, COEF, cut)
        got = asof.model_at(cut)
        assert got.table_size == want.table_size > NEIGHBOURS
        for home, away in ((1, 2), (3, 17), (40, 5)):
            assert _forecast_key(got, home, away, cut + 5000) == \
                _forecast_key(want, home, away, cut + 5000)


def test_as_of_rating_never_reads_a_later_match() -> None:
    history = _history()
    cut = T0 + 60 * DAY
    flipped = [
        TennisResult(**{**r.__dict__, "home_won": not r.home_won,
                        "sets": tuple((b, a) for a, b in r.sets)})
        if r.ts >= cut else r for r in history]
    ra, rb = AsOfRating(history, COEF), AsOfRating(flipped, COEF)
    a, b = ra.model_at(cut), rb.model_at(cut)
    assert _forecast_key(a, 1, 2, cut) == _forecast_key(b, 1, 2, cut)
    with pytest.raises(ValueError):
        ra.model_at(cut - DAY)  # a cut that goes back is refused


def _played(history: list[TennisResult], first_day: int) -> list[Played]:
    """Every match of the window as a replayed match with a games value; the
    side's earlier games form the samples, so the window starts late."""
    out = []
    for r in history:
        if r.ts < T0 + first_day * DAY:
            continue
        gh = float(sum(a for a, _ in r.sets))
        ga = float(sum(b for _, b in r.sets))
        out.append(Played(
            event_id=r.event_id, timestamp=r.ts, home_id=r.home_id,
            away_id=r.away_id, sport="tennis", competition_id=1,
            values={"games": (gh, ga)},
            tennis=TennisContext("ATP", "Hard", False)))
    return out


def _all_history_played() -> list[Played]:
    return _played(_history(), 0)


def test_replay_prices_games_with_the_rating_as_of_the_day() -> None:
    history = _history()
    played = _played(history, 0)
    rating = RatingReplay(history, COEF, tuple(FEATURES))
    rows = list(iter_rows(played, {}, rating))
    plain = list(iter_rows(played, {}))
    assert rating.forecasts > 100
    by_key = {(r.event_id, r.market, r.subject, r.line, r.direction): r
              for r in rows}
    plain_by = {(r.event_id, r.market, r.subject, r.line, r.direction): r
                for r in plain}
    checked = {"games_won_for": 0, "games_total": 0}
    for ev in [m for m in played if m.timestamp >= T0 + 70 * DAY][:30]:
        cut = ev.timestamp - ev.timestamp % DAY
        fc = build_model(history, COEF, cut).forecast(
            ev.home_id, ev.away_id, "ATP", "Hard",
            datetime.fromtimestamp(ev.timestamp, UTC))
        if fc is None:
            continue
        for key, row in by_key.items():
            if key[0] != ev.event_id:
                continue
            if row.market == "games_won_for":
                side = "side_a" if row.subject == str(ev.home_id) else "side_b"
                assert row.p_central == pytest.approx(
                    fc.read("games_won_for", side, row.line, row.direction),
                    abs=1e-6)
                checked["games_won_for"] += 1
            elif row.market == "games_total":
                p_rating = fc.read("games_total", None, row.line, row.direction)
                nb = plain_by[key].p_central
                assert row.p_central == pytest.approx(
                    W_GAMES_TOTAL_RATING * p_rating
                    + (1 - W_GAMES_TOTAL_RATING) * nb, abs=1e-5)
                checked["games_total"] += 1
    assert all(v > 20 for v in checked.values()), checked


def test_handicap_and_most_rows_settle_like_run_settle() -> None:
    history = _history()
    played = {m.event_id: m for m in _played(history, 0)}
    rows = [r for r in iter_rows(list(played.values()), {},
                                 RatingReplay(history, COEF, tuple(FEATURES)))
            if r.market in ("handicap_games", "most_games")]
    assert {r.market for r in rows} == {"handicap_games", "most_games"}
    for r in rows:
        m = played[r.event_id]
        home, away = m.values["games"]
        margin = home - away if r.subject == str(m.home_id) else away - home
        assert r.actual == margin and r.direction == "OVER"
        want = margin > -r.line if r.market == "handicap_games" else margin > 0
        assert r.outcome == ("WIN" if want else "LOSS")
        assert r.sample_size >= MIN_SAMPLE


def test_no_rating_is_the_replay_as_it_was() -> None:
    history = _history()
    played = _played(history, 0)
    assert not [r for r in iter_rows(played, {})
                if r.market in ("handicap_games", "most_games")]


def test_a_best_of_five_listing_is_read_as_best_of_five() -> None:
    """Review 2026-10-07: defaultPeriodCount is not on a listing, so the replay
    read every match as best of three and priced best-of-five matches the sheet
    refuses. The winner of a completed best-of-five has three sets."""
    from bet.sofa.metrics import infer_best_of

    bo5 = {"homeScore": {"current": 3}, "awayScore": {"current": 1}}
    bo3 = {"homeScore": {"current": 2}, "awayScore": {"current": 0}}
    assert infer_best_of(bo5) == 5 and infer_best_of(bo3) == 3
