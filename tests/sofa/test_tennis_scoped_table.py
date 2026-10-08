"""The scoped tennis neighbour table and the V5 rating start
(epochs.TENNIS_SCOPED_TABLE_FROM_UTC, off; track A4,
docs/sofa/evidence/tennis_calibration_2026-10-08.md).

Off, the model is the pooled one byte for byte (GOLDEN_DIGEST was computed
from the code before the change). On, the neighbours come from the match's
(tier, gender) cell, else its tier's, else the pooled table - never from a
match at or after the cut.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa import rebuild_plan as rp
from bet.sofa.tennis_rating import (
    ALL_FEATURES,
    FEATURES,
    NEIGHBOURS,
    SCOPED_MIN_TABLE,
    V5_FEATURES,
    AsOfRating,
    RatingBook,
    TennisRatingModel,
    TennisResult,
    build_model,
    fit_tier_start,
    load_coefficients,
    parse_event,
    replay,
)
from scripts.sofa.calibrate_from_cache import RatingReplay

DAY = 86400
T0 = 1_700_000_000 - 1_700_000_000 % DAY
COEF = {t: [0.0, 0.9, 0.1, 0, 0, 0, 0, 0, 0] for t in ("ITF", "CH", "TOUR")}
# computed by the pre-change code on _history() (see the module docstring)
GOLDEN_DIGEST = "0f19f02f77235a8b9706380aeedf15048d977fe6dc4ac2cd38b41cba07bccfbc"


def _history(n_days: int = 120, per_day: int = 40, seed: int = 11,
             players: int = 90) -> list[TennisResult]:
    # the order of every rng call is part of GOLDEN_DIGEST: do not tidy it
    rng = random.Random(seed)
    out: list[TennisResult] = []
    eid = 1
    strength = {p: rng.gauss(0, 1) for p in range(1, players + 1)}
    for d in range(n_days):
        for k in range(per_day):
            h, a = rng.sample(range(1, players + 1), 2)
            tier = ("ITF", "CH", "TOUR")[(h + a) % 3]
            ph = 1 / (1 + 2.718 ** (strength[a] - strength[h]))
            hw = rng.random() < ph
            _ = [(6, rng.randint(0, 4)), (rng.randint(0, 4), 6)]
            third = rng.random() < 0.4
            win = [(6, rng.randint(0, 4)), (6, rng.randint(0, 4))]
            if third:
                win = [(6, rng.randint(0, 4)), (rng.randint(0, 4), 6),
                       (7, 6) if rng.random() < .3 else (
                           (0, 1) if (tier == "ITF" and rng.random() < .4)
                           else (6, rng.randint(0, 4)))]
            sets = win if hw else [(b, a_) for a_, b in win]
            nh = sum(1 for x, y in sets if x > y)
            if (nh > len(sets) - nh) != hw:
                sets = [(y, x) for x, y in sets]
            out.append(TennisResult(
                eid, T0 + d * DAY + k * 600, tier, ("hard", "clay", "grass")[eid % 3],
                h, a, hw, tuple(sets), 90.0 if eid % 5 else None, eid % 17 != 0))
            eid += 1
    return out


def _gendered(rows: dict[tuple[str, bool], int], n_days: int = 100,
              seed: int = 5) -> list[TennisResult]:
    """`rows[(tier, female)]` matches a day; men are players 1-40, women 41-80;
    a (tier, gender) cell plays its own score pattern."""
    rng = random.Random(seed)
    out: list[TennisResult] = []
    eid = 1
    for d in range(n_days):
        k = 0
        for (tier, female), n in sorted(rows.items()):
            for _ in range(n):
                lo = 41 if female else 1
                h, a = rng.sample(range(lo, lo + 40), 2)
                hw = rng.random() < 0.5 + 0.01 * ((h - a) % 7 - 3)
                lost = rng.randint(0, 4) + (2 if tier == "TOUR" else 0)
                win = [(6, lost), (6, rng.randint(0, 4))]
                sets = win if hw else [(b, a_) for a_, b in win]
                out.append(TennisResult(
                    eid, T0 + d * DAY + k * 300, tier, "hard", h, a, hw,
                    tuple(sets), 90.0, True, female))
                eid += 1
                k += 1
    return out


def _digest(model: TennisRatingModel) -> str:
    m = hashlib.sha256()
    ts = T0 + 119 * DAY
    for i, (hh, aa) in enumerate([(1, 2), (3, 4), (5, 6), (7, 8), (9, 10),
                                  (11, 12), (13, 14), (15, 16)]):
        for cat in ("ITF Men", "Challenger", "ATP"):
            f = model.forecast(hh, aa, cat, "Clay",
                               datetime.fromtimestamp(ts + i * 3600, UTC))
            if f is None:
                m.update(b"none")
                continue
            m.update(repr(f.p_home).encode())
            for o in f.neighbours_home + f.neighbours_away:
                m.update(repr((o.p, o.games_for, o.games_against, o.sets,
                               o.tiebreaks, o.set1, o.set2,
                               o.match_tiebreak)).encode())
    return m.hexdigest()


def _fc(model: TennisRatingModel, home: int, away: int, cat: str, cut: int) -> Any:
    return model.forecast(home, away, cat, "Hard",
                          datetime.fromtimestamp(cut + 3600, UTC))


# --- off = identical --------------------------------------------------------

def test_off_is_the_pooled_model_byte_for_byte() -> None:
    h = _history()
    cut = T0 + 100 * DAY
    assert _digest(build_model(h, COEF, cut)) == GOLDEN_DIGEST
    assert _digest(AsOfRating(h, COEF).model_at(cut)) == GOLDEN_DIGEST
    # the switch's own defaults are the off position
    assert _digest(build_model(h, COEF, cut, FEATURES, False, None)) == GOLDEN_DIGEST
    model = build_model(h, COEF, cut)
    assert not model.scoped and not model._cells
    assert model.book.tier_start is None
    assert "lp_t" not in model.book.features(1, 2, "hard", cut)


def test_off_by_default_in_the_epochs() -> None:
    assert epochs.TENNIS_SCOPED_TABLE_FROM_UTC is None
    assert not epochs.tennis_scoped_table_enabled("2026-10-09")
    assert not epochs.tennis_scoped_table_enabled(
        "2026-10-30", datetime(2026, 10, 30, tzinfo=UTC))


def test_the_pooled_forecast_names_its_scope() -> None:
    h = _history()
    fc = _fc(build_model(h, COEF, T0 + 100 * DAY), 1, 2, "ATP", T0 + 100 * DAY)
    assert fc.table_scope == "pooled"


# --- on = scoped neighbours --------------------------------------------------

def test_on_reads_the_tier_gender_cell() -> None:
    h = _gendered({("TOUR", False): 12, ("TOUR", True): 12, ("CH", False): 12})
    cut = T0 + 90 * DAY
    model = build_model(h, COEF, cut, scoped=True)
    men = _fc(model, 1, 2, "ATP", cut)
    women = _fc(model, 41, 42, "WTA", cut)
    assert men.table_scope == women.table_scope == "tier_gender"
    for fc, female in ((men, False), (women, True)):
        pool = fc.neighbours_home + fc.neighbours_away
        assert len(fc.neighbours_home) == NEIGHBOURS
        assert {(o.tier, o.female) for o in pool} == {("TOUR", female)}
    off = build_model(h, COEF, cut)
    assert {o.tier for o in
            _fc(off, 1, 2, "ATP", cut).neighbours_home} >= {"TOUR"}
    assert _fc(off, 1, 2, "ATP", cut).neighbours_home != men.neighbours_home


def test_a_match_tiebreak_never_enters_a_tour_cell() -> None:
    h = _history()
    cut = T0 + 100 * DAY
    model = build_model(h, COEF, cut, scoped=True)
    assert any(o.match_tiebreak for o in model._cells[("ITF", None)].rows)
    for tier in ("CH", "TOUR"):
        assert not any(o.match_tiebreak for o in model._cells[(tier, None)].rows)


def test_a_thin_cell_falls_to_the_tier_then_to_the_pooled_table() -> None:
    # TOUR women: 6 matches a day, a thin cell < SCOPED_MIN_TABLE, the
    # tier (men + women) is thick -> the tier's cell
    h = _gendered({("TOUR", False): 12, ("TOUR", True): 6, ("CH", False): 1})
    cut = T0 + 99 * DAY
    model = build_model(h, COEF, cut, scoped=True)
    assert len(model._cells[("TOUR", True)].rows) < SCOPED_MIN_TABLE
    assert len(model._cells[("TOUR", None)].rows) >= SCOPED_MIN_TABLE
    fc = _fc(model, 41, 42, "WTA", cut)
    assert fc is not None and fc.table_scope == "tier"
    assert {o.tier for o in fc.neighbours_home + fc.neighbours_away} == {"TOUR"}
    # Challenger: ~200 outcomes in its tier cell, below the floor -> pooled,
    # and then the pooled forecast of the unscoped model, neighbour for neighbour
    assert len(model._cells[("CH", None)].rows) < SCOPED_MIN_TABLE
    fc3 = _fc(model, 1, 2, "Challenger", cut)
    off3 = _fc(build_model(h, COEF, cut), 1, 2, "Challenger", cut)
    assert fc3 is not None and fc3.table_scope == "pooled"
    assert fc3.neighbours_home == off3.neighbours_home
    assert fc3.neighbours_away == off3.neighbours_away


def test_every_cell_thin_is_the_pooled_model() -> None:
    h = _history(n_days=40)
    cut = T0 + 40 * DAY
    on = build_model(h, COEF, cut, scoped=True)
    off = build_model(h, COEF, cut)
    assert off.table_size >= NEIGHBOURS
    assert all(len(c.rows) < SCOPED_MIN_TABLE for c in on._cells.values())
    got = [_fc(on, p, p + 1, "ATP", cut) for p in (1, 5, 9, 13)]
    assert got == [_fc(off, p, p + 1, "ATP", cut) for p in (1, 5, 9, 13)]
    assert all(g is not None and g.table_scope == "pooled" for g in got)


def test_every_outcome_is_filed_under_its_tier_and_its_gender() -> None:
    h = _gendered({("TOUR", False): 6, ("TOUR", True): 6, ("ITF", True): 3})
    model = build_model(h, COEF, T0 + 60 * DAY, scoped=True)
    by_gender = sum(len(c.rows) for (_t, g), c in model._cells.items() if g is not None)
    by_tier = sum(len(c.rows) for (_t, g), c in model._cells.items() if g is None)
    assert by_gender == by_tier == model.table_size
    for (tier, g), cell in model._cells.items():
        assert cell.keys == sorted(cell.keys)
        assert all(o.tier == tier and (g is None or o.female == g) for o in cell.rows)


def test_as_of_rating_scoped_is_build_model_scoped_at_every_cut() -> None:
    h = _gendered({("TOUR", False): 10, ("TOUR", True): 10, ("ITF", True): 6})
    asof = AsOfRating(h, COEF, FEATURES, scoped=True)
    for d in (40, 60, 90):
        cut = T0 + d * DAY
        want = build_model(h, COEF, cut, scoped=True)
        got = asof.model_at(cut)
        assert got.table_size == want.table_size
        assert {k: (v.keys, v.rows) for k, v in got._cells.items()} == \
            {k: (v.keys, v.rows) for k, v in want._cells.items()}
        for home, away, cat in ((1, 2, "ATP"), (41, 42, "WTA"), (43, 44, "ITF Women")):
            a, b = _fc(got, home, away, cat, cut), _fc(want, home, away, cat, cut)
            assert a == b and a is not None


def test_no_match_at_or_after_the_cut_is_in_any_cell() -> None:
    h = _gendered({("TOUR", False): 10, ("TOUR", True): 10})
    cut = T0 + 50 * DAY
    marked = [
        TennisResult(**{**r.__dict__, "sets": ((6, 0), (6, 0))})
        if r.ts >= cut else r for r in h]
    for build in (
        lambda hist: build_model(hist, COEF, cut, scoped=True),
        lambda hist: AsOfRating(hist, COEF, FEATURES, scoped=True).model_at(cut),
    ):
        a, b = build(h), build(marked)
        assert {k: v.rows for k, v in a._cells.items()} == \
            {k: v.rows for k, v in b._cells.items()}
        assert _fc(a, 1, 2, "ATP", cut) == _fc(b, 1, 2, "ATP", cut)


def test_the_replay_holds_no_state_between_two_rules() -> None:
    """calibrate_from_cache keeps nothing on disk for the rating: the history
    is rebuilt in memory on every run, so the pooled and the scoped replay
    cannot collide; and the shared history list is not mutated."""
    h = _gendered({("TOUR", False): 10, ("TOUR", True): 8})
    before = list(h)
    pooled = RatingReplay(h, COEF, FEATURES)
    scoped = RatingReplay(h, COEF, FEATURES, scoped=True)
    cut = T0 + 90 * DAY
    a = pooled._rating.model_at(cut)
    b = scoped._rating.model_at(cut)
    assert not a.scoped and b.scoped
    assert _fc(a, 41, 42, "WTA", cut).table_scope == "pooled"
    assert _fc(b, 41, 42, "WTA", cut).table_scope in ("tier", "tier_gender")
    assert h == before


# --- the gender of a match ---------------------------------------------------

def _event(gender: str | None) -> dict[str, Any]:
    home = {"id": 1, "type": 1, **({"gender": gender} if gender else {})}
    return {
        "id": 9, "startTimestamp": T0,
        "tournament": {"category": {"name": "WTA", "sport": {"slug": "tennis"}},
                       "slug": "x", "uniqueTournament": {"id": 1}},
        "homeTeam": home, "awayTeam": {"id": 2, "type": 1},
        "status": {"type": "finished", "description": "Ended"}, "winnerCode": 1,
        "homeScore": {"period1": 6, "period2": 6},
        "awayScore": {"period1": 3, "period2": 4},
    }


def test_the_gender_comes_from_the_home_player_of_the_listing() -> None:
    f, m, none = (parse_event(_event(g)) for g in ("F", "M", None))
    assert f is not None and m is not None and none is not None
    assert f.female and not m.female and not none.female


# --- V5: the tier-initialised start -----------------------------------------

def test_tier_start_changes_where_a_newcomer_begins() -> None:
    start = {"ITF": -80.0, "CH": 0.0, "TOUR": 60.0}
    book, plain = RatingBook(start), RatingBook()
    r = TennisResult(1, T0, "TOUR", "hard", 1, 2, True, ((6, 3), (6, 4)), 90.0, True)
    r2 = TennisResult(
        2, T0 + 1, "ITF", "hard", 3, 1, True, ((6, 3), (6, 4)), 90.0, True)
    for b in (book, plain):
        b.update(r)
    # both began at 1500 + 60: the gap after one match is the plain one
    assert book.overall_t[1] - book.overall_t[2] == pytest.approx(
        plain.overall[1] - plain.overall[2])
    assert book.overall_t[1] + book.overall_t[2] == pytest.approx(2 * 1560.0)
    for b in (book, plain):
        b.update(r2)
    # player 3 entered at the ITF offset, player 1 kept what it had
    assert book.n[3] == 1 and 1500.0 - 80.0 < book.overall_t[3] < 1500.0 - 80.0 + 125
    f = book.features(1, 3, "hard", T0 + 2)
    assert f["lp_t"] == pytest.approx(
        (book.overall_t[1] - book.overall_t[3]) * math.log(10) / 400)
    # the production features are those of the plain book, untouched
    assert {k: v for k, v in f.items() if k != "lp_t"} == \
        plain.features(1, 3, "hard", T0 + 2)


def test_a_zero_start_is_the_production_elo() -> None:
    h = _history(n_days=30)
    zero = {"ITF": 0.0, "CH": 0.0, "TOUR": 0.0}
    book, _ = replay(h, T0 + 30 * DAY, zero)
    for p in range(1, 10):
        assert book.overall_t[p] == pytest.approx(book.overall[p])


def test_a_config_naming_lp_t_needs_its_start() -> None:
    h = _history(n_days=10)
    names = V5_FEATURES
    coef = {t: [0.0] * (len(names) + 1) for t in ("ITF", "CH", "TOUR")}
    with pytest.raises(ValueError, match="tier_start"):
        build_model(h, coef, T0 + 10 * DAY, names)
    with pytest.raises(ValueError, match="tier_start"):
        AsOfRating(h, coef, names)
    build_model(h, coef, T0 + 10 * DAY, names, tier_start={"ITF": 0.0})
    AsOfRating(h, coef, names, tier_start={"ITF": 0.0})


def test_v5_features_replace_lp_and_fit_nothing_by_default() -> None:
    assert "lp_t" not in FEATURES and V5_FEATURES[0] == "lp_t"
    assert V5_FEATURES[1:] == FEATURES[1:]
    assert set(V5_FEATURES) <= set(ALL_FEATURES)


def test_fit_tier_start_is_centred_and_uses_matches_before_the_cut_only() -> None:
    h = _history(n_days=120)
    cut = T0 + 100 * DAY
    off = fit_tier_start(h, cut)
    assert set(off) == {"ITF", "CH", "TOUR"}
    flipped = [TennisResult(**{**r.__dict__, "home_won": not r.home_won})
               if r.ts >= cut else r for r in h]
    assert fit_tier_start(flipped, cut) == off
    # centred over the players: the offsets weighted by players sum to zero
    book = RatingBook()
    first: dict[int, str] = {}
    for r in h:
        if r.ts >= cut:
            break
        first.setdefault(r.home_id, r.tier)
        first.setdefault(r.away_id, r.tier)
        book.update(r)
    n = {t: sum(1 for p, tt in first.items() if tt == t and book.n[p] >= 30)
         for t in off}
    assert sum(n[t] * off[t] for t in off) == pytest.approx(0.0, abs=1e-6)


def test_load_coefficients_accepts_a_v5_config_and_keeps_tier_start(
    tmp_path: Path,
) -> None:
    names = list(V5_FEATURES)
    cfg = {"features": names, "tier_start": {"ITF": -10.0, "CH": 1.0, "TOUR": 9.0},
           "tiers": {"TOUR": {"coefficients": [0.0] * (len(names) + 1), "n": 1}}}
    path = tmp_path / "tennis_rating.json"
    path.write_text(json.dumps(cfg))
    coefficients, meta = load_coefficients(path)  # type: ignore[misc]
    assert meta["features"] == names and meta["tier_start"]["TOUR"] == 9.0
    bad = dict(cfg, features=["lp_t", "nope"])
    path.write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        load_coefficients(path)


def test_v5_scoped_forecast_runs_end_to_end() -> None:
    h = _gendered({("TOUR", False): 16, ("TOUR", True): 16})
    names = V5_FEATURES
    coef = {t: [0.0, 1.0, 0.1] + [0.0] * 6 for t in ("ITF", "CH", "TOUR")}
    start = {"ITF": -50.0, "CH": 0.0, "TOUR": 50.0}
    cut = T0 + 80 * DAY
    on = build_model(h, coef, cut, names, scoped=True, tier_start=start)
    via = AsOfRating(h, coef, names, scoped=True, tier_start=start).model_at(cut)
    a, b = _fc(on, 1, 2, "ATP", cut), _fc(via, 1, 2, "ATP", cut)
    assert a == b and a is not None and a.table_scope == "tier_gender"


# --- a V5 config while the switch is off -------------------------------------

def _v5_meta(with_start: bool = True) -> tuple[dict[str, list[float]], dict[str, Any]]:
    names = list(V5_FEATURES)
    coef = {t: [0.0, 1.0, 0.1] + [0.0] * 6 for t in ("ITF", "CH", "TOUR")}
    meta: dict[str, Any] = {"features": names}
    if with_start:
        meta["tier_start"] = {"ITF": -50.0, "CH": 0.0, "TOUR": 50.0}
    return coef, meta


def test_the_old_rule_passes_tier_start_only_to_a_config_that_names_lp_t() -> None:
    from bet.sofa.tennis_rating import start_for_rule

    start = {"ITF": -1.0}
    assert start_for_rule(V5_FEATURES, start, False) is start
    assert start_for_rule(V5_FEATURES, start, True) is start
    assert start_for_rule(V5_FEATURES, None, False) is None  # check_start raises
    assert start_for_rule(FEATURES, start, False) is None  # old config: untouched
    assert start_for_rule(FEATURES, start, True) is start


def test_sheet_loads_a_v5_config_while_the_switch_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from bet.sofa.config import SofaConfig
    from scripts.sofa import run_sheet as rs

    h = _history()
    cut = T0 + 100 * DAY
    day = datetime.fromtimestamp(cut, UTC).strftime("%Y-%m-%d")
    cut = int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())
    fixtures: Any = [SimpleNamespace(sport="tennis")]
    monkeypatch.setattr(rs, "load_history", lambda _db: h)

    coef, meta = _v5_meta()
    monkeypatch.setattr(rs, "load_coefficients", lambda: (coef, meta))
    model = rs.load_tennis_rating(SofaConfig(), fixtures, day, scoped=False)
    assert model is not None and not model.scoped and not model._cells
    expect = build_model(h, coef, cut, V5_FEATURES, tier_start=meta["tier_start"])
    assert _digest(model) == _digest(expect)

    # lp_t WITHOUT tier_start still raises
    coef2, meta2 = _v5_meta(with_start=False)
    monkeypatch.setattr(rs, "load_coefficients", lambda: (coef2, meta2))
    with pytest.raises(ValueError, match="tier_start"):
        rs.load_tennis_rating(SofaConfig(), fixtures, day, scoped=False)

    # the production config (no lp_t) is byte for byte what it was, even if a
    # stray tier_start sits in the file
    monkeypatch.setattr(rs, "load_coefficients", lambda: (
        COEF, {"features": list(FEATURES), "tier_start": {"ITF": 5.0}}))
    old = rs.load_tennis_rating(SofaConfig(), fixtures, day, scoped=False)
    assert old is not None and old.book.tier_start is None
    assert _digest(old) == _digest(build_model(h, COEF, cut))


def test_the_replay_loads_a_v5_config_with_the_switch_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.sofa import calibrate_from_cache as cc

    h = _history()
    coef, meta = _v5_meta()
    monkeypatch.setattr(cc, "load_history", lambda _db: h)
    monkeypatch.setattr(cc, "load_coefficients", lambda: (coef, meta))
    off = RatingReplay.from_db(Path("x.db"), scoped=False)
    on = RatingReplay.from_db(Path("x.db"), scoped=True)
    assert off is not None and on is not None
    assert off._rating.book.tier_start == meta["tier_start"]
    assert on._rating.book.tier_start == meta["tier_start"]
    coef2, meta2 = _v5_meta(with_start=False)
    monkeypatch.setattr(cc, "load_coefficients", lambda: (coef2, meta2))
    with pytest.raises(ValueError, match="tier_start"):
        RatingReplay.from_db(Path("x.db"), scoped=False)


# --- the rule marker and the rebuild ----------------------------------------

def test_a_sheet_of_the_other_table_rule_is_re_priced_by_the_rebuild(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rule = epochs.TENNIS_SCOPED_TABLE
    assert epochs.sheet_tennis_scoped_table(
        [{"sport": "tennis", "tennis_table_rule": rule}, {"sport": "football"}])
    assert not epochs.sheet_tennis_scoped_table([{"sport": "tennis"}])
    assert epochs.sheet_tennis_scoped_table([{"sport": "football"}])  # no tennis
    assert epochs.sheet_tennis_scoped_table([])
    at = datetime(2026, 10, 9, 7, 0, tzinfo=UTC)
    limit = timedelta(minutes=45)
    off = rp.build_plan(rp.DayState("2026-10-09", at, limit, sheet_tennis_table=False))
    assert "SHEET" not in off.names()  # switch off: nothing changes today
    monkeypatch.setattr(epochs, "TENNIS_SCOPED_TABLE_FROM_UTC",
                        datetime(2026, 10, 9, tzinfo=UTC))
    assert epochs.tennis_scoped_table_enabled("2026-10-09", at)
    assert not epochs.tennis_scoped_table_enabled("2026-10-08", at)
    stale = rp.build_plan(
        rp.DayState("2026-10-09", at, limit, sheet_tennis_table=False))
    sheet = next(s for s in stale.steps if s.name == "SHEET")
    assert "tennis" in sheet.reason
    assert stale.names().index("SHEET") < stale.names().index("CONFIDENCE")
    assert "SHEET" not in rp.build_plan(
        rp.DayState("2026-10-09", at, limit, sheet_tennis_table=True)).names()
    old = rp.build_plan(rp.DayState("2026-10-08", at, limit, sheet_tennis_table=False))
    assert "SHEET" not in old.names()


def test_a_sheet_row_carries_the_table_rule_only_under_it() -> None:
    from bet.sofa.contracts import SheetRow
    from scripts.sofa.run_sheet import sheet_row_json

    assert "tennis_table_rule" in SheetRow.model_fields

    class _R:
        def __init__(self, rule: str | None) -> None:
            self.rule = rule

        def model_dump(self, mode: str = "json") -> dict[str, Any]:
            return {"epoch": "x", "tennis_table_rule": self.rule}

    assert "tennis_table_rule" not in sheet_row_json(_R(None))  # type: ignore[arg-type]
    assert sheet_row_json(_R(epochs.TENNIS_SCOPED_TABLE))[  # type: ignore[arg-type]
        "tennis_table_rule"] == epochs.TENNIS_SCOPED_TABLE
