"""The tier-profile terms of the tennis rating (dhigh, dtour).

Found 2026-09-28: Ruien Zhang (55 of 58 cached matches ITF, Elo 1632) against
Storm Hunter (30 of 40 on the WTA tour, Elo 1742) was rated 0.409 to win while
Superbet's devigged price said 0.044, and that 0.409 carried a games_won_for
leg onto the PDF. One Elo pool treats points earned in ITF and on the tour as
the same currency; the pools barely mix, so it never learns they are not.
On the history before 2026-09-17 the lower-tier side of a match with a
profile gap of 0.7-1.0 was forecast 0.491 and won 0.255 (n=1,303). Out of
sample (2026-09-17..27, 1,933 matches), refitted on the same history, Brier
went from 0.2073 with six features to 0.1983 with these eight.
"""

import json
import math
import random
from pathlib import Path

import pytest

from bet.sofa.tennis_rating import (
    FEATURES,
    MIN_RATED,
    RatingBook,
    TennisResult,
    build_model,
    calibrated_p,
    fit_coefficients,
    load_coefficients,
    replay,
)

DAY = 86400
LEGACY = ("lp", "lps", "dmin78", "drest", "dn7", "dform")


def _r(eid: int, ts: int, home: int, away: int, tier: str,
       home_won: bool = True, completed: bool = True) -> TennisResult:
    return TennisResult(
        event_id=eid, ts=ts, tier=tier, surface="hard", home_id=home,
        away_id=away, home_won=home_won, sets=((6, 3), (6, 4)), minutes=90.0,
        completed=completed,
    )


def test_the_profile_is_the_share_of_matches_above_itf_and_on_tour():
    book = RatingBook()
    book.update(_r(1, 1000, 1, 9, "ITF"))
    book.update(_r(2, 2000, 1, 9, "ITF", completed=False))  # a retirement counts
    book.update(_r(3, 3000, 2, 9, "TOUR"))
    book.update(_r(4, 4000, 2, 9, "CH"))
    f = book.features(1, 2, "hard", 5000)
    # player 1: 0/2 above ITF, 0/2 tour; player 2: 2/2 above ITF, 1/2 tour
    assert f["dhigh"] == pytest.approx(-1.0)
    assert f["dtour"] == pytest.approx(-0.5)
    assert book.features(7, 8, "hard", 5000)["dhigh"] == 0.0  # no history


def test_the_profile_is_read_before_the_match_is_counted():
    # Player 1 has only ever played ITF, player 2 only tour; then they meet at
    # tour level. Read before the match: -1 / -1. Read after it (a leak),
    # player 1 would already be 1/13 tour and dhigh would be 1/13 - 1.
    history = [_r(i, 1_000_000 + i * DAY, 1, 10 + i, "ITF") for i in range(12)]
    history += [_r(50 + i, 1_000_000 + i * DAY + 1, 2, 30 + i, "TOUR")
                for i in range(12)]
    history.sort(key=lambda r: r.ts)
    history.append(_r(99, 1_000_000 + 12 * DAY, 1, 2, "TOUR"))
    _, rated = replay(history, cut_ts=10**10)
    last, feats = rated[-1]
    assert last.event_id == 99
    assert feats["dhigh"] == -1.0 and feats["dtour"] == -1.0


def test_a_config_fitted_before_the_terms_existed_prices_as_it_did(tmp_path: Path):
    # Today's checked-in config (six features) must keep pricing exactly as
    # before until it is deliberately re-fitted - never mid-day.
    coefficients = [0.05, 0.7, 0.2, -0.02, -0.08, -0.04, -0.06]
    feats = {"lp": -0.63, "lps": -0.6, "dmin78": 0.0, "drest": 0.0,
             "dn7": 2.0, "dform": -0.49, "dhigh": -0.8, "dtour": -0.8}
    legacy = calibrated_p(coefficients, feats, LEGACY)
    moved = {**feats, "dhigh": 0.9, "dtour": 0.9}
    assert calibrated_p(coefficients, moved, LEGACY) == legacy
    z = coefficients[0] + sum(c * feats[n] for c, n in zip(coefficients[1:], LEGACY))
    assert legacy == pytest.approx(1 / (1 + math.exp(-z)))

    path = tmp_path / "tennis_rating.json"
    path.write_text(json.dumps({"features": list(LEGACY),
                                "tiers": {"ITF": {"coefficients": coefficients}}}))
    loaded = load_coefficients(path)
    assert loaded is not None and loaded[1]["features"] == list(LEGACY)


def test_the_new_terms_are_what_moves_a_cross_tier_forecast():
    full = [0.0] * (len(FEATURES) + 1)
    full[1 + FEATURES.index("dhigh")] = 2.0
    base = dict.fromkeys(FEATURES, 0.0)
    assert calibrated_p(full, base) == pytest.approx(0.5)
    assert calibrated_p(full, {**base, "dhigh": -0.8}) < 0.2


def _two_pools(seed: int) -> list[TennisResult]:
    """Two closed pools that both settle near 1500: an ITF pool, and a tour
    pool one logit stronger. Four matches in a hundred cross between them."""
    rng = random.Random(seed)
    itf, tour = list(range(1, 41)), list(range(101, 141))
    skill = {p: rng.gauss(0.0, 0.3) for p in itf}
    skill |= {p: 1.5 + rng.gauss(0.0, 0.3) for p in tour}
    out: list[TennisResult] = []
    for i in range(7000):
        if rng.random() < 0.04:
            pair, tier = [rng.choice(itf), rng.choice(tour)], "CH"
            rng.shuffle(pair)
        else:
            pool = itf if rng.random() < 0.5 else tour
            pair, tier = rng.sample(pool, 2), ("ITF" if pool is itf else "TOUR")
        h, a = pair
        p = 1 / (1 + math.exp(-(skill[h] - skill[a])))
        out.append(_r(i, 1_000_000 + i * 3600, h, a, tier, home_won=rng.random() < p))
    return out


def test_two_closed_pools_are_told_apart_only_with_the_profile():
    history = _two_pools(seed=11)
    split = history[5000].ts
    _, rated = replay(history, cut_ts=split)
    cross = [(r, f) for r, f in replay(history, cut_ts=10**10)[1]
             if r.ts >= split and r.tier == "CH"]
    assert len(cross) > 40

    def itf_side_forecast(names: tuple[str, ...]) -> tuple[float, float]:
        fitted = fit_coefficients(rated, names)
        coefficients = {t: e["coefficients"] for t, e in fitted.items()}
        preds, wins = [], []
        for r, f in cross:
            p_home = calibrated_p(coefficients["CH"], f, names)
            home_is_itf = r.home_id < 100
            preds.append(p_home if home_is_itf else 1 - p_home)
            wins.append(float(r.home_won == home_is_itf))
        return sum(preds) / len(preds), sum(wins) / len(wins)

    legacy_pred, actual = itf_side_forecast(LEGACY)
    full_pred, _ = itf_side_forecast(FEATURES)
    assert actual < 0.35, "the ITF pool really is weaker"
    assert legacy_pred - actual > 0.10, "the Elo alone cannot see it"
    assert abs(full_pred - actual) < abs(legacy_pred - actual) / 2


def test_build_model_applies_the_config_by_name():
    history = _two_pools(seed=3)[:3000]
    names = LEGACY
    one = [0.0, 1.0] + [0.0] * (len(names) - 1)
    coefficients = {t: one for t in ("ITF", "CH", "TOUR")}
    model = build_model(history, coefficients, cut_ts=10**10, names=names)
    assert model.names == names
    assert model.book.rated(1) >= MIN_RATED


def test_sheet_serves_a_six_feature_config_by_its_own_names(monkeypatch):
    # Without names=meta["features"] SHEET would feed seven coefficients to
    # eight features and raise on every tennis day until the refit.
    from types import SimpleNamespace

    import scripts.sofa.run_sheet as run_sheet

    coefficients = [0.05, 0.7, 0.2, -0.02, -0.08, -0.04, -0.06]
    loaded = ({t: coefficients for t in ("ITF", "CH", "TOUR")},
              {"features": list(LEGACY)})
    monkeypatch.setattr(run_sheet, "load_coefficients", lambda: loaded)
    monkeypatch.setattr(run_sheet, "load_history", lambda _p: _two_pools(seed=5)[:2000])
    fixtures = [SimpleNamespace(sport="tennis")]
    model = run_sheet.load_tennis_rating(
        SimpleNamespace(db_path="unused"), fixtures, "2026-09-28"  # type: ignore[arg-type]
    )
    assert model is not None and model.names == LEGACY
    from datetime import UTC, datetime
    kickoff = datetime(2026, 9, 28, tzinfo=UTC)
    forecast = model.forecast(1, 101, "Challenger", "Hard", kickoff)
    assert forecast is not None and 0.0 < forecast.p_home < 1.0
