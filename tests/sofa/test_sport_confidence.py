"""bet.sofa.sport_confidence - statistics-only confidence for the measured
sports (plan 2026-10-05, F2-F6, F8)."""

from __future__ import annotations

import random
from collections import Counter
from typing import Any

import pytest

from bet.sofa import cs2_engine as eng
from bet.sofa import sport_confidence as scf
from bet.sofa.cs2 import Cs2Line
from bet.sofa.shadow import MARKETS, PLAYER_MARKETS, SPORTS, ShadowLine

HOCKEY = SPORTS["hockey"]
DAY = 86400


def _event(eid: int, ts: int, home: int, away: int, hp: list[int], ap: list[int],
           name: str = "League", round_name: str | None = None) -> dict[str, Any]:
    hs, as_ = sum(hp), sum(ap)
    code = 1 if hs > as_ else 2 if as_ > hs else 3
    event: dict[str, Any] = {
        "id": eid, "startTimestamp": ts,
        "tournament": {"id": 9, "name": name,
                       "uniqueTournament": {"id": 5, "name": name},
                       "category": {"sport": {"slug": "ice-hockey"}}},
        "status": {"type": "finished", "description": "Ended"},
        "homeTeam": {"id": home, "name": f"Team {home}", "gender": "M"},
        "awayTeam": {"id": away, "name": f"Team {away}", "gender": "M"},
        "homeScore": {**{f"period{i + 1}": v for i, v in enumerate(hp)},
                      "current": hs, "normaltime": hs},
        "awayScore": {**{f"period{i + 1}": v for i, v in enumerate(ap)},
                      "current": as_, "normaltime": as_},
        "winnerCode": code,
    }
    if round_name:
        event["roundInfo"] = {"name": round_name}
    return event


def _history(n: int = 160, seed: int = 3) -> dict[int, dict[str, Any]]:
    rng = random.Random(seed)
    teams = [101, 102, 103, 104]
    out: dict[int, dict[str, Any]] = {}
    for i in range(n):
        home, away = teams[i % 4], teams[(i + 1 + i // 4) % 4]
        if home == away:
            away = teams[(i + 2) % 4]
        hp = [rng.randint(0, 2) for _ in range(3)]
        ap = [rng.randint(0, 2) for _ in range(3)]
        if sum(hp) == sum(ap):
            hp[2] += 1
        out[1000 + i] = _event(1000 + i, 10 * DAY + i * 3600 * 6, home, away, hp, ap)
    return out


# --- F2 -------------------------------------------------------------------------


def test_every_allowed_market_is_the_shadow_market_it_claims():
    for sport, markets in scf.ALLOWED_MARKETS.items():
        for mid, family in markets.items():
            spec = MARKETS[sport][mid]  # type: ignore[index]
            assert spec.family == family, (sport, mid)
            assert spec.kind not in ("odd_even", "yes_no", "exact")
            assert mid not in PLAYER_MARKETS[sport]  # type: ignore[index]
            if spec.kind == "dnb":  # only a set's winner, which has no draw
                assert (sport, family) == ("volleyball", "set_winner")


def test_the_excluded_markets_stay_out():
    bb = scf.ALLOWED_MARKETS["basketball"]
    assert not any(f.startswith(("h2_", "quarter_")) for f in bb.values())
    hockey = scf.ALLOWED_MARKETS["hockey"]
    assert 662 not in hockey  # period dnb
    assert scf.family_of("cs2", None, "map_rounds_total") is None
    assert scf.family_of("cs2", None, "team_kills") is None
    assert scf.family_of("cs2", None, "map_team_rounds") == "map_team_rounds"
    assert scf.family_of("hockey", 775, "odd_even") is None


def test_history_and_settled_families_partition_the_allow_list():
    for sport, markets in scf.ALLOWED_MARKETS.items():
        history = {markets[m] for m in scf.HISTORY_MARKETS[sport]}
        assert history.isdisjoint(scf.SETTLED_ONLY_FAMILIES[sport])
        assert history | scf.SETTLED_ONLY_FAMILIES[sport] == set(markets.values())


# --- the curve --------------------------------------------------------------------


def test_edges_and_wilson_are_fit_confidences():
    from scripts.sofa import fit_confidence as fc

    assert scf.EDGES == fc.EDGES
    for k, n in ((0, 0), (5, 10), (180, 200), (950, 1000)):
        assert scf.wilson_lo(k, n) == fc.wilson_lo(k, n)


def _rows(key: str, p: float, n: int, hits: int, game_prefix: str = "g"
          ) -> list[dict[str, Any]]:
    return [{"key": key, "p": p, "y": 1 if i < hits else 0,
             "game": f"{game_prefix}{i}"} for i in range(n)]


def test_a_bucket_under_200_rows_is_not_part_of_the_curve():
    rows = _rows("total|OVER", 0.81, 250, 205) + _rows("total|OVER", 0.91, 150, 140)
    curves = scf.fit_curves(rows)
    assert list(curves["total|OVER"]) == ["0.800-0.825"]
    entry = curves["total|OVER"]["0.800-0.825"]
    assert entry["n"] == 250 and entry["realised"] == 0.82
    assert entry["realised_lo95"] == round(scf.wilson_lo(205, 250), 4)


def _calibration(admitted: list[str]) -> scf.SportCalibration:
    curves = scf.fit_curves(_rows("total|OVER", 0.81, 250, 205))
    return scf.SportCalibration({"min_bucket": 200, "sports": {"hockey": {
        "curves": curves, "admitted": admitted, "not_calibrated": {}}}})


def test_the_confidence_is_the_buckets_lower_bound_for_an_admitted_key_only():
    cal = _calibration(["total|OVER"])
    got = cal.lookup("hockey", "total", "OVER", 0.812)
    assert got is not None
    assert got.value == round(scf.wilson_lo(205, 250), 4)
    assert got.n == 250 and got.calibrated_on == "hockey:total|OVER"
    assert cal.lookup("hockey", "total", "OVER", 0.95) is None  # no such bucket
    assert cal.lookup("hockey", "total", "UNDER", 0.812) is None
    assert cal.lookup("basketball", "total", "OVER", 0.812) is None
    assert _calibration([]).lookup("hockey", "total", "OVER", 0.812) is None


def test_admission_refuses_an_overstating_bucket_and_one_with_no_evidence():
    curves = {"a|OVER": {"0.800-0.825": {"n": 300, "realised": 0.82,
                                          "realised_lo95": 0.80}},
              "b|OVER": {"0.800-0.825": {"n": 300, "realised": 0.82,
                                          "realised_lo95": 0.80}},
              "c|OVER": {"0.800-0.825": {"n": 300, "realised": 0.82,
                                          "realised_lo95": 0.80}}}
    holdout = (_rows("a|OVER", 0.81, 250, 200, "a") + _rows("b|OVER", 0.81, 250, 190, "b")
               + _rows("c|OVER", 0.81, 50, 10, "c"))
    checks = {"history_holdout": scf.evaluate(curves, holdout)}
    admitted, refused = scf.admission(curves, checks)
    # a: 0.80 printed, 0.80 realised; b: 0.80 vs 0.76 (4 pp over)
    assert admitted == ["a|OVER"]
    assert refused["b|OVER"].startswith("OVERSTATES: history_holdout bucket")
    # c: 50 rows only, but 0.20 realised against 0.80 is beyond doubt
    assert refused["c|OVER"].startswith("OVERSTATES_PRINTABLE")


def test_admission_needs_a_tested_printable_bucket():
    curves = {"d|OVER": {"0.800-0.825": {"n": 300, "realised": 0.82,
                                          "realised_lo95": 0.80},
                         "0.000-0.600": {"n": 900, "realised": 0.40,
                                          "realised_lo95": 0.37}}}
    # the catch-all bucket is large and honest, the printable one thin
    rows = _rows("d|OVER", 0.30, 500, 200, "x") + _rows("d|OVER", 0.81, 50, 40, "y")
    admitted, refused = scf.admission(
        curves, {"superbet_settled": scf.evaluate(curves, rows)})
    assert admitted == []
    assert refused["d|OVER"].startswith("NO_OOS_PRINTABLE_BUCKET")


def test_evaluate_bootstraps_over_games_not_lines():
    curves = {"k|TEAM": {"0.800-0.825": {"n": 300, "realised": 0.8,
                                          "realised_lo95": 0.8}}}
    # 40 games, 10 lines each, all a game's lines the same outcome
    rows = [{"key": "k|TEAM", "p": 0.81, "y": int(g < 32), "game": f"g{g}"}
            for g in range(40) for _ in range(10)]
    out = scf.evaluate(curves, rows)["k|TEAM"]
    assert out["games"] == 40 and out["n"] == 400
    point, lo, hi = out["realised_minus_confidence"]
    assert point == 0.0
    # per-game clustering: the interval is that of 40 draws, not 400
    assert hi - lo > 0.15


# --- F4: walk-forward, no future leak ------------------------------------------------


def _wf(events: dict[int, dict[str, Any]], start: int, end: int) -> list[dict[str, Any]]:
    history = scf.parse_history(events, HOCKEY)
    return scf.walk_forward_rows(history, HOCKEY, start, end, 200, None, "t")


def test_walk_forward_never_reads_the_game_itself_or_a_later_one():
    events = _history()
    target = 1000 + 140
    t_ts = events[target]["startTimestamp"]
    base = [r for r in _wf(events, t_ts - 30 * 3600, t_ts + 1) if r["game"] == f"h:{target}"]
    assert base, "the target game must be scored"
    # the game's own score and every later game rewritten: the forecasts of
    # the target game do not move; only its outcomes may
    changed = dict(events)
    for eid, e in events.items():
        if e["startTimestamp"] >= t_ts:
            changed[eid] = _event(eid, e["startTimestamp"], e["homeTeam"]["id"],
                                  e["awayTeam"]["id"], [5, 5, 5], [0, 0, 0])
    again = [r for r in _wf(changed, t_ts - 30 * 3600, t_ts + 1)
             if r["game"] == f"h:{target}"]
    assert [(r["key"], r["line"], r["p"]) for r in base] == [
        (r["key"], r["line"], r["p"]) for r in again]


def test_games_sharing_a_start_are_forecast_before_either_is_learnt():
    events = _history()
    ts = events[1150]["startTimestamp"]
    twin = _event(5000, ts, 101, 103, [9, 9, 9], [0, 0, 0])
    with_twin = {**events, 5000: twin}
    a = [r for r in _wf(events, ts, ts + 1) if r["game"] == "h:1150"]
    b = [r for r in _wf(with_twin, ts, ts + 1) if r["game"] == "h:1150"]
    assert a and [r["p"] for r in a] == [r["p"] for r in b]


def test_walk_forward_rows_carry_no_price():
    rows = _wf(_history(), 10 * DAY + 120 * 6 * 3600, 10 * DAY + 160 * 6 * 3600)
    assert rows
    for r in rows:
        assert not {"odds", "fair_p", "overround", "price"} & set(r)
        assert r["market_id"] in scf.HISTORY_MARKETS["hockey"]
        assert r["key"] == scf.curve_key(r["family"], r["side"])
        if r["line"] is not None:  # no line past the game's simulated support
            assert scf.DEGENERATE_P <= r["p"] <= 1 - scf.DEGENERATE_P


def test_synthetic_lines_sit_on_the_games_own_distribution():
    from bet.sofa.shadow import GameResult

    sims = [GameResult((g, 0, 0), (0, 0, 1), g, 1, "T1" if g > 1 else "T2", False)
            for g in range(10)]
    lines = scf.synthetic_lines(HOCKEY, 623, sims)  # regulation total = g + 1
    totals = sorted({ln.line for ln in lines})
    # the simulated totals 1..10 at each quantile, half a point up
    assert totals == sorted({1 + int(q * 9) + 0.5 for q in scf.LINE_QUANTILES})
    assert totals[0] == 1.5 and totals[-1] == 9.5
    assert {ln.side for ln in lines} == {"OVER", "UNDER"}
    hcp = scf.synthetic_lines(HOCKEY, 604, sims)  # margin = g - 1
    assert {ln.line for ln in hcp} == {-(int(q * 9) - 1 + 0.5)
                                       for q in scf.LINE_QUANTILES}


# --- F3: the sample ----------------------------------------------------------------


def test_the_sample_reads_the_teams_last_ten_league_games_on_the_line():
    events = {
        i: _event(i, 1000 + i, 101 if i % 2 else 201, 201 if i % 2 else 101,
                  [1, 1, 1], [0, 0, 0]) for i in range(1, 15)}
    # a cup round and a friendly do not count
    events[50] = _event(50, 1050, 101, 999, [5, 5, 5], [0, 0, 0], round_name="Final")
    events[51] = _event(51, 1051, 101, 999, [5, 5, 5], [0, 0, 0],
                        name="Club Friendly Games")
    games = scf.TeamGames.build(events.values(), HOCKEY)
    over = ShadowLine("x", 623, "total", 0, "", 2.5, "OVER", 1.9)
    k, n = scf.sample_hit_rate(over, HOCKEY, 101, 201, games, before_ts=2000)
    # the two teams only ever met: their last ten each are the same ten games
    assert (k, n) == (10, 10)
    # team1's own goals: home wins 3-0, so team 101 scored 3 in its home games
    tt = ShadowLine("x", 658, "team_total", 0, "T1", 1.5, "OVER", 1.9)
    k, n = scf.sample_hit_rate(tt, HOCKEY, 101, 201, games, before_ts=2000)
    assert n == 10 and k == sum(1 for i in range(5, 15) if i % 2)
    # nothing at or after the kickoff
    _, n_early = scf.sample_hit_rate(over, HOCKEY, 101, 201, games, before_ts=1004)
    assert n_early == 3


# --- CS2 ---------------------------------------------------------------------------


def test_counted_base_rate_is_the_engines():
    rng = random.Random(1)
    values = [rng.randint(0, 16) for _ in range(500)]
    for line in (9.5, 10.5, 12.5):
        assert scf.counted_base_rate(Counter(values), line) == pytest.approx(
            eng.base_rate(values, line))
    assert scf.counted_base_rate(Counter(values[:10]), 9.5) is None


def _cs2_history(n: int = 400) -> tuple[list[eng.MapRow], dict[int, scf.SeriesRow]]:
    rng = random.Random(5)
    maps: list[eng.MapRow] = []
    series: dict[int, scf.SeriesRow] = {}
    strength = {1: 0.7, 2: 0.55, 3: 0.45, 4: 0.3}
    for i in range(n):
        home, away = rng.sample([1, 2, 3, 4], 2)
        ts = 1000 + i * 3600
        won = []
        for order in (1, 2):
            hw = rng.random() < strength[home] / (strength[home] + strength[away])
            won.append(hw)
            maps.append(eng.MapRow(i, ts, order, home, away, 13 if hw else 8,
                                   8 if hw else 13, hw, ()))
        hm, am = sum(won), 2 - sum(won)
        series[i] = scf.SeriesRow(i, ts, home, away, hm, am, 3)
    return maps, series


def test_cs2_walk_forward_is_the_engine_at_each_series_start(monkeypatch):
    maps, series = _cs2_history()
    monkeypatch.setattr(scf, "REFIT_DAYS_CS2", 0)  # refit before every series
    target = 350
    ts = series[target].start_ts
    rows = scf.cs2_walk_forward_rows(maps, series, ts, ts + 1, "t")
    p_rows = [r for r in rows if r["family"] == "map_winner" and r["side"] == "T1"]
    assert p_rows
    before = [m for m in maps if m.start_ts < ts]
    ratings = eng.build_ratings(before)
    line = Cs2Line("e", "map_winner", 1, "", None, "T1", 1.9)
    home, away = series[target].home_id, series[target].away_id
    want = eng.model_probability(line, home, away, "a", "b", 3, before, ratings, True)
    assert want is not None
    assert p_rows[0]["p"] == round(want.p, 4)
    rounds = [r for r in rows if r["family"] == "map_team_rounds"
              and r["subject"] == "T1" and r["line"] == 10.5 and r["side"] == "OVER"]
    tline = Cs2Line("e", "map_team_rounds", 1, "a", 10.5, "OVER", 1.9)
    want_r = eng.model_probability(tline, home, away, "a", "b", 3, before, ratings,
                                   True)
    assert want_r is not None and rounds[0]["p"] == round(want_r.p, 4)


def test_cs2_walk_forward_does_not_see_the_future():
    maps, series = _cs2_history()
    ts = series[300].start_ts
    a = [r for r in scf.cs2_walk_forward_rows(maps, series, ts, ts + 1, "t")]
    flipped = [eng.MapRow(m.event_id, m.start_ts, m.order, m.home_id, m.away_id,
                          m.away_rounds, m.home_rounds, not m.home_won, m.players)
               if m.start_ts >= ts else m for m in maps]
    b = scf.cs2_walk_forward_rows(flipped, series, ts, ts + 1, "t")
    assert [(r["key"], r["line"], r["p"]) for r in a] == [
        (r["key"], r["line"], r["p"]) for r in b]


def test_cs2_settled_rows_take_model_p_and_allowed_families_only(tmp_path):
    import json

    day = tmp_path / "cs2" / "2026-10-01"
    day.mkdir(parents=True)
    graded = [
        {"family": "map_winner", "map_nr": 1, "subject": "", "line": None,
         "side": "T1", "odds": 1.5, "fair_p": 0.6, "outcome": "WIN", "model_p": 0.66},
        {"family": "map_rounds_total", "map_nr": 1, "subject": "", "line": 21.5,
         "side": "OVER", "odds": 1.8, "outcome": "LOSS", "model_p": 0.5},
        {"family": "match_winner", "map_nr": 0, "subject": "", "line": None,
         "side": "T2", "odds": 2.5, "outcome": "LOSS", "model_p": None},
    ]
    (day / "settled.json").write_text(json.dumps(
        {"events": {"77": {"state": "SETTLED", "graded": graded}}}))
    rows = scf.cs2_settled_rows(str(tmp_path), ["2026-10-01", "2026-10-02"])
    assert [(r["family"], r["p"], r["y"]) for r in rows] == [("map_winner", 0.66, 1)]
    assert "fair_p" not in rows[0] and "odds" not in rows[0]


def test_cs2_sample_counts_each_teams_own_maps():
    maps = [eng.MapRow(i, i, 1, 1, 2, 13, 5, True, ()) for i in range(12)]
    line = Cs2Line("e", "map_winner", 1, "", None, "T1", 1.9)
    k, n = scf.cs2_sample_hit_rate(line, None, 1, 2, maps, {})
    assert (k, n) == (10, 10)  # the same ten maps, counted once
    rounds = Cs2Line("e", "map_team_rounds", 1, "x", 12.5, "OVER", 1.9)
    assert scf.cs2_sample_hit_rate(rounds, "T1", 1, 2, maps, {}) == (10, 10)
    assert scf.cs2_sample_hit_rate(rounds, "T2", 1, 2, maps, {}) == (0, 10)
    assert scf.cs2_sample_hit_rate(rounds, None, 1, 2, maps, {}) == (0, 0)


def test_the_printable_region_is_the_official_floor():
    from bet.sofa.confidence import PROFILES

    assert scf.PRINTABLE_FROM == PROFILES["standard"].floor
    curves = {"k|TEAM": {"0.800-0.825": {"n": 300, "realised": 0.8,
                                          "realised_lo95": 0.78},
                         "0.000-0.600": {"n": 300, "realised": 0.4,
                                          "realised_lo95": 0.35}}}
    rows = (_rows("k|TEAM", 0.81, 100, 80, "a") + _rows("k|TEAM", 0.30, 100, 40, "b"))
    out = scf.evaluate(curves, rows)["k|TEAM"]
    assert out["n"] == 200
    assert out["printable"]["n"] == 100 and out["printable"]["realised"] == 0.8
    assert out["printable"]["confidence"] == 0.78


def test_the_fit_scripts_tables_read_the_calibration_file():
    from scripts.sofa import fit_sport_confidence as fsc

    curves = scf.fit_curves(_rows("total|OVER", 0.81, 250, 205))
    oos = scf.evaluate(curves, _rows("total|OVER", 0.81, 250, 200, "o"))
    doc = {"sports": {"hockey": {
        "fitted_from": {"fit_window_utc": ["2025-09-05T00:00:00Z",
                                           "2026-09-05T00:00:00Z"],
                        "holdout_window_utc": ["2026-09-05T00:00:00Z",
                                               "2026-10-05T00:00:00Z"],
                        "rows": {}, "games": {}},
        "curves": curves, "admitted": ["total|OVER"], "not_calibrated": {},
        "oos": {"history_holdout": oos}}}}
    text = fsc.tables_markdown(doc)
    assert "| total|OVER | ADMITTED | history_holdout | 250 |" in text
    assert "0.800-0.825" in text
