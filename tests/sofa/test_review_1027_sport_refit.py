"""Confidence review 2026-10-27, the measured sports' curve fit:
F1 monotone curves (pool adjacent violators), F2 the Kish effective n by game
in the Wilson bound and min_bucket, F3 the CS2 Elo burn-in, and the R3 / R4
replay options of the fit (hockey late goal in the mean, CS2 decider map
posterior) plus R3's live wiring in run_sport_confidence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa import score_model as sm
from bet.sofa import sport_confidence as scf
from bet.sofa.cs2_engine import SERIES_KAPPA, MapRow, decider_posterior_p
from bet.sofa.shadow import SPORTS
from scripts.sofa import fit_sport_confidence as fsc
from scripts.sofa import run_sport_confidence as rsc


def _rows(key: str, p: float, ys: list[int], game_size: int = 1,
          prefix: str = "g") -> list[dict[str, Any]]:
    return [{"key": key, "p": p, "y": y, "game": f"{prefix}{i // game_size}"}
            for i, y in enumerate(ys)]


# --- F2 -----------------------------------------------------------------------


def test_wilson_lo_rate_equals_wilson_lo_on_integers() -> None:
    for k, n in ((0, 10), (7, 10), (180, 200), (950, 1000)):
        assert scf.wilson_lo_rate(k / n, n) == pytest.approx(scf.wilson_lo(k, n))
    assert scf.wilson_lo_rate(0.5, 0) == 0.0


def test_fit_curves_default_is_the_old_curve() -> None:
    rows = _rows("total|OVER", 0.81, [1] * 170 + [0] * 50, game_size=10)
    curve = scf.fit_curves(rows)["total|OVER"]["0.800-0.825"]
    assert curve == {"n": 220, "realised": round(170 / 220, 4),
                     "realised_lo95": round(scf.wilson_lo(170, 220), 4)}


def test_effective_n_lowers_the_bound_of_clustered_rows() -> None:
    # 60 games x 10 identical lines: every line of a game agrees (deff ~ 10)
    ys = [1] * 450 + [0] * 150
    clustered = _rows("total|OVER", 0.81, ys, game_size=10)
    independent = _rows("total|OVER", 0.81, ys, game_size=1)
    on = scf.fit_curves(independent + [], min_bucket=50, effective_n=True)
    assert on["total|OVER"]["0.800-0.825"]["deff"] == 1.0
    c = scf.fit_curves(clustered, min_bucket=50, effective_n=True)[
        "total|OVER"]["0.800-0.825"]
    assert c["deff"] > 5 and c["n"] == 600
    assert c["n_eff"] == pytest.approx(600 / c["deff"], abs=0.1)
    assert c["realised_lo95"] < on["total|OVER"]["0.800-0.825"]["realised_lo95"]
    assert c["realised_lo95"] == pytest.approx(
        scf.wilson_lo_rate(0.75, 600 / c["deff"]), abs=1e-4)
    # min_bucket reads the effective n: 600 rows but ~60 independent games
    assert scf.fit_curves(clustered, min_bucket=200, effective_n=True) == {}
    assert scf.fit_curves(clustered, min_bucket=200)  # rows alone: kept


# --- F1 -----------------------------------------------------------------------


def _non_monotone_rows() -> list[dict[str, Any]]:
    # basketball h2_team_total|OVER's shape: 0.875 bucket above the 0.90 one
    return (_rows("k|OVER", 0.88, [1] * 270 + [0] * 30, prefix="a")
            + _rows("k|OVER", 0.91, [1] * 1700 + [0] * 300, prefix="b")
            + _rows("k|OVER", 0.94, [1] * 470 + [0] * 30, prefix="c"))


def test_monotone_pass_removes_a_fall() -> None:
    raw = scf.fit_curves(_non_monotone_rows())["k|OVER"]
    assert raw["0.875-0.900"]["realised_lo95"] > raw["0.900-0.925"]["realised_lo95"]
    mono = scf.fit_curves(_non_monotone_rows(), monotone=True)["k|OVER"]
    los = [mono[b]["realised_lo95"] for b in
           ("0.875-0.900", "0.900-0.925", "0.925-0.950")]
    assert los == sorted(los)
    a, b = mono["0.875-0.900"], mono["0.900-0.925"]
    assert a["realised_lo95"] == b["realised_lo95"]
    assert a["pooled"] == b["pooled"] == ["0.875-0.900", "0.900-0.925"]
    assert a["realised_lo95_bucket"] == raw["0.875-0.900"]["realised_lo95"]
    # the pooled block's bound: Wilson on the two buckets' rows together
    assert a["realised_lo95"] == round(scf.wilson_lo(1970, 2300), 4)
    assert "pooled" not in mono["0.925-0.950"]


def test_monotone_curve_unchanged_when_already_monotone() -> None:
    rows = (_rows("k|OVER", 0.81, [1] * 160 + [0] * 40)
            + _rows("k|OVER", 0.86, [1] * 180 + [0] * 20))
    assert (scf.fit_curves(rows, monotone=True)
            == scf.fit_curves(rows, monotone=False))


def test_monotone_with_effective_n_weights_by_effective_n() -> None:
    curve = {
        "0.700-0.750": {"n": 400, "realised": 0.80, "realised_lo95": 0.75,
                        "n_eff": 200.0, "deff": 2.0},
        "0.750-0.800": {"n": 300, "realised": 0.74, "realised_lo95": 0.70,
                        "n_eff": 300.0, "deff": 1.0},
    }
    scf.monotone_curve(curve)
    pooled = scf.wilson_lo_rate((0.80 * 200 + 0.74 * 300) / 500, 500)
    assert curve["0.700-0.750"]["realised_lo95"] == round(pooled, 4)
    assert curve["0.750-0.800"]["realised_lo95"] == round(pooled, 4)


def test_monotone_cascades_over_three_buckets() -> None:
    curve = {
        "0.600-0.700": {"n": 1000, "realised": 0.70, "realised_lo95": 0.67},
        "0.700-0.750": {"n": 1000, "realised": 0.66, "realised_lo95": 0.63},
        "0.750-0.800": {"n": 1000, "realised": 0.60, "realised_lo95": 0.57},
    }
    scf.monotone_curve(curve)
    vals = [curve[b]["realised_lo95"] for b in sorted(curve)]
    assert vals[0] == vals[1] == vals[2]
    assert vals[0] == round(scf.wilson_lo_rate((0.70 + 0.66 + 0.60) / 3, 3000), 4)


def test_lookup_reads_the_pooled_bound() -> None:
    curves = scf.fit_curves(_non_monotone_rows(), monotone=True)
    cal = scf.SportCalibration({"sports": {"basketball": {
        "curves": {"h2_team_total|OVER": curves["k|OVER"]},
        "admitted": ["h2_team_total|OVER"]}}})
    lo = cal.lookup("basketball", "h2_team_total", "OVER", 0.88)
    hi = cal.lookup("basketball", "h2_team_total", "OVER", 0.91)
    assert lo is not None and hi is not None and lo.value <= hi.value


# --- F3 -----------------------------------------------------------------------


def test_burn_in_moves_the_fit_start() -> None:
    first = 1_000_000
    assert fsc.burn_in_start(500, first, 90) == first + 90 * 86400
    assert fsc.burn_in_start(first + 200 * 86400, first, 90) == first + 200 * 86400
    assert fsc.burn_in_start(500, first, 0) == 500
    assert fsc.burn_in_start(500, None, 90) == 500


def _map(eid: int, ts: int, home: int, away: int, home_won: bool,
         order: int = 1) -> MapRow:
    return MapRow(eid, ts, order, home, away, 13 if home_won else 9,
                  9 if home_won else 13, home_won, (), None, 3)


def test_cs2_rows_carry_rated_maps() -> None:
    maps = []
    ts = 1_700_000_000
    eid = 1
    for i in range(30):
        maps.append(_map(eid, ts + i * 3600, 10, 20, i % 3 != 0))
        eid += 1
    rows = scf.cs2_walk_forward_rows(maps, {}, 0, 2_000_000_000, "h")
    assert rows and all("rated_maps" in r for r in rows)
    rated = sorted({r["rated_maps"] for r in rows if r["family"] == "map_winner"})
    assert rated and rated[0] >= 10  # map_winner needs both teams rated


# --- R4 in the replay ---------------------------------------------------------


def test_settled_best_of() -> None:
    assert scf.settled_best_of([[13, 5], [13, 11]]) == 3
    assert scf.settled_best_of([[13, 5], [5, 13], [13, 2]]) == 3
    assert scf.settled_best_of([[13, 5], [5, 13]]) == 2
    assert scf.settled_best_of([[13, 5]]) == 1
    assert scf.settled_best_of([[13, 5], [5, 13], [13, 2], [13, 9]]) == 5
    assert scf.settled_best_of(None) is None


def _cs2_settled(tmp: Path, date: str) -> None:
    d = tmp / "cs2" / date
    d.mkdir(parents=True)
    graded = [
        {"family": "map_winner", "map_nr": 3, "side": "T1", "subject": "",
         "line": None, "outcome": "WIN", "model_p": 0.75, "odds": 1.3},
        {"family": "map_winner", "map_nr": 3, "side": "T2", "subject": "",
         "line": None, "outcome": "LOSS", "model_p": 0.25},
        {"family": "map_winner", "map_nr": 1, "side": "T1", "subject": "",
         "line": None, "outcome": "WIN", "model_p": 0.75},
        {"family": "match_winner", "map_nr": 0, "side": "T1", "subject": "",
         "line": None, "outcome": "WIN", "model_p": 0.8},
    ]
    doc = {"events": {"1": {"maps": [[13, 5], [5, 13], [13, 2]],
                            "graded": graded}}}
    (d / "settled.json").write_text(json.dumps(doc), encoding="utf-8")


def test_cs2_settled_rows_decider_transform(tmp_path: Path,
                                            monkeypatch: pytest.MonkeyPatch
                                            ) -> None:
    monkeypatch.setattr(epochs, "CS2_DECIDER_MAP_POSTERIOR_FROM_UTC", None)
    _cs2_settled(tmp_path, "2026-10-20")
    off = scf.cs2_settled_rows(str(tmp_path), ["2026-10-20"])
    on = scf.cs2_settled_rows(str(tmp_path), ["2026-10-20"],
                              decider_posterior=True)
    assert [r["p"] for r in off] == [0.75, 0.25, 0.75, 0.8]
    want = round(decider_posterior_p(0.75, 3, 3), 4)
    assert want == round((0.75 * SERIES_KAPPA + 1) / (SERIES_KAPPA + 2), 4)
    assert [r["p"] for r in on] == [want, round(1 - want, 4), 0.75, 0.8]
    assert on[0]["decider_posterior"] is True and "decider_posterior" not in on[2]
    assert "odds" not in on[0]  # no price on a row
    # a day the settle priced under the switch already holds the posterior
    monkeypatch.setattr(epochs, "CS2_DECIDER_MAP_POSTERIOR_FROM_UTC",
                        datetime(2026, 10, 1, tzinfo=UTC))
    again = scf.cs2_settled_rows(str(tmp_path), ["2026-10-20"],
                                 decider_posterior=True)
    assert [r["p"] for r in again] == [0.75, 0.25, 0.75, 0.8]


def test_cs2_walk_forward_decider_moves_only_decider_maps() -> None:
    maps = []
    ts = 1_700_000_000
    eid = 1
    for i in range(40):  # warm the book: team 10 strong
        maps.append(_map(eid, ts + i * 3600, 10, 20 + i % 2, True))
        eid += 1
    t = ts + 100 * 3600
    series = [_map(eid, t, 10, 20, True, 1), _map(eid, t, 10, 20, False, 2),
              _map(eid, t, 10, 20, True, 3)]
    srow = scf.SeriesRow(eid, t, 10, 20, 2, 1, 3)
    allm = maps + series
    kw: dict[str, Any] = {"series": {eid: srow}, "start_ts": t,
                          "end_ts": t + 1, "source": "h"}
    off = scf.cs2_walk_forward_rows(allm, **kw)
    on = scf.cs2_walk_forward_rows(allm, decider_posterior=True, **kw)

    def mw(rows: list[dict[str, Any]], period: int) -> float:
        return next(r["p"] for r in rows if r["family"] == "map_winner"
                    and r["period"] == period and r["side"] == "T1")
    assert mw(on, 1) == mw(off, 1) and mw(on, 2) == mw(off, 2)
    assert mw(on, 3) < mw(off, 3)
    assert mw(on, 3) == pytest.approx(
        decider_posterior_p(mw(off, 3), 3, 3), abs=2e-4)
    # series families read the plain map p either way
    ser = [(r["key"], r["p"]) for r in off if r["family"] == "match_winner"]
    assert ser == [(r["key"], r["p"]) for r in on if r["family"] == "match_winner"]


# --- R3 in the replay and live ------------------------------------------------


class _StopError(Exception):
    pass


def _capture(monkeypatch: pytest.MonkeyPatch, target: Any) -> list[Any]:
    seen: list[Any] = []

    def fake(ratings: Any, sport: Any, ts: Any, params: Any = None,
             **kw: Any) -> Any:
        seen.append(params)
        raise _StopError

    monkeypatch.setattr(target, "build_model", fake)
    return seen


def _game(ts: int) -> Any:
    return SimpleNamespace(rating=SimpleNamespace(ts=ts), result=None, event={})


@pytest.mark.parametrize("late", [True, False, None])
def test_walk_forward_forces_late_in_mean(monkeypatch: pytest.MonkeyPatch,
                                          late: bool | None) -> None:
    seen = _capture(monkeypatch, scf)
    with pytest.raises(_StopError):
        scf.walk_forward_rows([_game(100)], SPORTS["hockey"], 0, 200, 10, None,
                              "h", late_in_mean=late)
    prm = seen[0]
    if late is None:
        assert prm is None  # the old call: params untouched
    else:
        assert prm.hk_late_in_mean is late


@pytest.mark.parametrize(("switch", "late", "want"), [
    (None, None, False),
    (datetime(2026, 10, 28, tzinfo=UTC), None, True),
    (datetime(2026, 10, 29, tzinfo=UTC), None, False),
    (None, True, True),
])
def test_settled_rows_read_the_days_rule(tmp_path: Path,
                                         monkeypatch: pytest.MonkeyPatch,
                                         switch: datetime | None,
                                         late: bool | None, want: bool) -> None:
    monkeypatch.setattr(epochs, "HK_LATE_GOAL_IN_MEAN_FROM_UTC", switch)
    d = tmp_path / "shadow" / "hockey" / "2026-10-28"
    d.mkdir(parents=True)
    (d / "settled.json").write_text('{"events": {}}', encoding="utf-8")
    seen = _capture(monkeypatch, scf)
    with pytest.raises(_StopError):
        scf.settled_shadow_rows(str(tmp_path), SPORTS["hockey"], ["2026-10-28"],
                                {}, [], 10, late_in_mean=late)
    assert seen[0].hk_late_in_mean is want


def test_switch_mode() -> None:
    def on(d: str, at: datetime) -> bool:
        return d >= "2026-10-28"
    assert fsc.switch_mode("auto", "hockey", "hockey", "2026-10-28", on)
    assert not fsc.switch_mode("auto", "hockey", "hockey", "2026-10-27", on)
    assert fsc.switch_mode("on", "hockey", "hockey", "2026-10-01", on)
    assert not fsc.switch_mode("off", "hockey", "hockey", "2026-10-28", on)
    assert not fsc.switch_mode("on", "cs2", "hockey", "2026-10-28", on)


@pytest.mark.parametrize(("switch", "date", "at", "want"), [
    (None, "2026-10-28", datetime(2026, 10, 28, 8, tzinfo=UTC), False),
    (datetime(2026, 10, 28, tzinfo=UTC), "2026-10-28",
     datetime(2026, 10, 28, 8, tzinfo=UTC), True),
    # a rebuild of 10-27 after the switch's clock stays on 10-27's rule
    (datetime(2026, 10, 28, tzinfo=UTC), "2026-10-27",
     datetime(2026, 10, 28, 8, tzinfo=UTC), False),
])
def test_live_forecaster_forces_the_days_rule(monkeypatch: pytest.MonkeyPatch,
                                              switch: datetime | None, date: str,
                                              at: datetime, want: bool) -> None:
    monkeypatch.setattr(epochs, "HK_LATE_GOAL_IN_MEAN_FROM_UTC", switch)
    monkeypatch.setattr(sm, "load_events", lambda db, sp: {})
    seen = _capture(monkeypatch, sm)
    fc = rsc.DbForecaster(db_path="x.db", at=at, date=date)
    with pytest.raises(_StopError):
        fc._shadow_model("hockey")
    assert seen[0].hk_late_in_mean is want


def test_live_marker_on_hockey_score_legs(monkeypatch: pytest.MonkeyPatch
                                          ) -> None:
    sw = datetime(2026, 10, 28, tzinfo=UTC)
    monkeypatch.setattr(epochs, "HK_LATE_GOAL_IN_MEAN_FROM_UTC", sw)
    fc = rsc.DbForecaster(db_path="x.db", at=datetime(2026, 10, 28, 8, tzinfo=UTC),
                          date="2026-10-28")
    model = SimpleNamespace(params=sm.SimParams(hk_late_in_mean=True))
    fc._shadow["hockey"] = (model, None)  # type: ignore[assignment]
    total = SimpleNamespace(market_id=623)
    assert fc.late_goal_rule("hockey", total) == {
        sm.HK_LATE_GOAL_IN_MEAN_RULE: "2026-10-28T00:00:00Z"}
    assert fc.late_goal_rule("basketball", total) == {}
    model.params = sm.SimParams(hk_late_in_mean=False)
    assert fc.late_goal_rule("hockey", total) == {}
