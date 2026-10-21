"""scripts/sofa/fit_joint_curves.py - the raw-sample football joints'
history curves: the replay never puts a match in its own sample, keeps a
friendly out of the histories and the fit, splits train / holdout / final by
time, gives the women's matches their own class key; the side correlation is
the file's where it has one; the staged curves land where CONFIDENCE reads a
joint (offline, synthetic matches)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from bet.sofa.comparability import MatchKind
from bet.sofa.confidence import Calibration
from scripts.sofa import fit_joint_curves as fj
from scripts.sofa import install_new_market_curves as inst
from scripts.sofa.calibrate_from_cache import MIN_SAMPLE, Played, load_cache

DAY = 86400
H0 = 1000 * DAY
H1 = 1100 * DAY
CUT = 1200 * DAY


def _match(i: int, ts: int, home: int, away: int, fouls: tuple[float, float],
           kind: str = MatchKind.REGULAR, competition: int = 17) -> Played:
    return Played(event_id=i, timestamp=ts, home_id=home, away_id=away,
                  sport="football", competition_id=competition,
                  values={"fouls": fouls}, kind=kind)


def _league(n: int, start: int, step: int = DAY) -> list[Played]:
    # teams 1 and 2 play each other repeatedly; values vary so the sample
    # has a spread
    return [_match(i, start + i * step, 1 + i % 2, 2 - i % 2,
                   (10.0 + i % 5, 12.0 - i % 3)) for i in range(n)]


def test_no_row_before_both_sides_hold_min_sample() -> None:
    played = _league(MIN_SAMPLE, 10 * DAY)
    res = fj.replay_base(played, "fouls", 0.0, H0, H1, CUT)
    assert res.matches == 0 and not res.final


def test_rows_split_by_time_and_keyed_as_confidence_reads_them() -> None:
    played = _league(40, H0 - 20 * DAY)
    res = fj.replay_base(played, "fouls", 0.0, H0, H1, CUT)
    assert res.matches == 40 - MIN_SAMPLE
    assert set(res.final) >= {"both_over_fouls|OVER", "both_over_fouls|UNDER",
                              "handicap_fouls|OVER", "most_fouls|OVER"}
    n_train = sum(map(len, res.train.values()))
    n_hold = sum(map(len, res.holdout.values()))
    assert n_train and n_hold
    assert n_train + n_hold == sum(map(len, res.final.values()))
    p, y, m, label = res.holdout["both_over_fouls|OVER"][0]
    assert 0 < p < 1 and y in (0, 1) and float(label) % 1 == 0.5
    assert all(len(o) == 3 for o in res.final["both_over_fouls|OVER"])
    assert H0 <= next(x.timestamp for x in played if x.event_id == m) < H1


def test_a_match_is_never_in_its_own_sample() -> None:
    played = _league(MIN_SAMPLE, 10 * DAY)
    # the ninth match: both samples hold the eight before it, never itself -
    # an outlier value would otherwise move its own forecast
    a = fj.replay_base([*played, _match(99, 30 * DAY, 1, 2, (10.0, 12.0))],
                       "fouls", 0.0, H0, H1, CUT)
    b = fj.replay_base([*played, _match(99, 30 * DAY, 1, 2, (60.0, 0.0))],
                       "fouls", 0.0, H0, H1, CUT)
    assert ([p for p, _, _ in a.final["most_fouls|OVER"]]
            == [p for p, _, _ in b.final["most_fouls|OVER"]])


def test_friendly_is_neither_a_row_nor_in_a_history() -> None:
    played = _league(MIN_SAMPLE, 10 * DAY)
    comp = next(iter(fj.FRIENDLY_COMPETITION_IDS))
    friendly = [_match(50 + i, 20 * DAY + i, 1, 2, (30.0, 30.0),
                       kind=MatchKind.FRIENDLY, competition=comp)
                for i in range(3)]
    base = fj.replay_base([*played, _match(99, 30 * DAY, 1, 2, (10.0, 12.0))],
                          "fouls", 0.0, H0, H1, CUT)
    mixed = fj.replay_base(
        [*played, *friendly, _match(99, 30 * DAY, 1, 2, (10.0, 12.0))],
        "fouls", 0.0, H0, H1, CUT)
    assert mixed.final == base.final


def test_friendly_competition_rows_stay_out_of_the_fit() -> None:
    comp = next(iter(fj.FRIENDLY_COMPETITION_IDS))
    played = [_match(i, 10 * DAY + i * DAY, 1 + i % 2, 2 - i % 2,
                     (10.0 + i % 5, 12.0 - i % 3), competition=comp)
              for i in range(20)]
    assert not fj.replay_base(played, "fouls", 0.0, H0, H1, CUT).final


def test_women_matches_get_their_own_key_and_leave_the_men_holdout() -> None:
    played = _league(40, H0 - 20 * DAY)
    women = frozenset(m.event_id for m in played)
    res = fj.replay_base(played, "fouls", 0.0, H0, H1, CUT, women)
    key = "both_over_fouls|OVER"
    assert res.final[key] == res.final[f"women:{key}"]
    assert not res.holdout.get(key)
    assert res.holdout[f"women:{key}"]


def test_side_correlation_prefers_the_file_then_the_measurement() -> None:
    doc = {"fouls": {"correlation": 0.044}, "corners_1h": {"correlation": None}}
    measured = {"fouls": (0.3, 900, 800), "corners_1h": (-0.12, 900, 800),
                "tackles": (None, 50, 0)}
    staged, used = fj.side_correlations(doc, ["fouls", "corners_1h", "tackles"],
                                        measured)
    assert used == {"fouls": 0.044, "corners_1h": -0.12, "tackles": 0.0}
    assert staged["fouls"] == {"correlation": 0.044}
    assert staged["corners_1h"]["correlation"] == -0.12
    assert "tackles" not in staged
    assert doc["corners_1h"]["correlation"] is None  # input untouched


def test_a_marginal_centre_base_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        fj.main(["--db-path", str(tmp_path / "x.db"), "--out-dir",
                 str(tmp_path), "--bases", "fouls,corners"])


def test_load_cache_read_only_never_creates_a_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.db"
    with pytest.raises(sqlite3.OperationalError):
        load_cache(missing, read_only=True)
    assert not missing.exists()


CURVE = {"0.700-0.750": {"n": 500, "realised": 0.74, "realised_lo95": 0.71},
         "0.750-0.800": {"n": 450, "realised": 0.79, "realised_lo95": 0.76}}


def test_staged_group_installs_where_confidence_reads_a_joint(
        tmp_path: Path) -> None:
    assert fj.GROUP in inst.GROUPS
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / inst.FOOTBALL_TARGET).write_text(json.dumps(
        {"by_market": {}, "by_market_direction": {},
         "by_class": {"women": {"by_market_direction": {}}}}))
    keys = {"both_over_fouls|OVER": ({"pass": True}, CURVE),
            "both_over_fouls|UNDER": ({"pass": False}, CURVE),
            "women:both_over_fouls|OVER": ({"pass": True}, CURVE)}
    fj.write_group(tmp_path / "refit" / fj.GROUP, keys, {"before": "x"},
                   {"fouls": 0.044})
    rc = inst.main(["--dir", str(tmp_path / "refit"), "--config-dir", str(cfg),
                    "--backup-dir", str(tmp_path / "backup"), "--confirm",
                    "--test-cmd", "true"])
    assert rc == 0
    cal = Calibration.load(cfg / inst.FOOTBALL_TARGET)
    hit = cal.realised("both_over_fouls", 0.76, "football", "OVER")
    assert hit is not None and hit[0] == 0.76
    assert hit[1] == "market:both_over_fouls|OVER"
    # the failed direction has no curve: a derived key never reads a pool
    assert cal.realised("both_over_fouls", 0.76, "football", "UNDER") is None
    women = cal.realised("both_over_fouls", 0.72, "football", "OVER", "women")
    assert women is not None and women[1] == "women:market:both_over_fouls|OVER"


def test_women_from_stored_reads_only_women_matches_split_by_kickoff(
        tmp_path: Path) -> None:
    comp = next(iter(fj.FRIENDLY_COMPETITION_IDS))
    rows = tmp_path / "rows.csv"
    rows.write_text(
        "1,17,both_over_goals,0.5,OVER,0.71,WIN\n"     # women, train
        "2,17,both_over_goals,0.5,OVER,0.72,LOSS\n"    # women, holdout
        "3,17,both_over_goals,0.5,OVER,0.73,WIN\n"     # men: out
        f"4,{comp},both_over_goals,0.5,OVER,0.74,WIN\n"  # friendly: out
        "5,17,most_corners,0.0,OVER,0.75,PUSH\n"       # no grade: out
        "6,17,most_corners,0.0,OVER,0.76,WIN\n")       # after the cut: out
    ts = {1: H0 - DAY, 2: H0 + DAY, 3: H0 - DAY, 4: H0 - DAY, 5: H0 - DAY,
          6: CUT + DAY}
    res = fj.women_from_stored(rows, ts, frozenset({1, 2, 4, 5, 6}),
                               H0, H1, CUT)
    key = "women:both_over_goals|OVER"
    assert set(res.final) == {key}
    assert res.train[key] == [(0.71, 1, "0.5")]
    assert res.holdout[key] == [(0.72, 0, 2, "0.5")]
    assert len(res.final[key]) == 2


def test_parallel_replay_equals_the_single_process_one(
        monkeypatch: pytest.MonkeyPatch) -> None:
    import multiprocessing as mp
    played = _league(30, H0 - 15 * DAY)
    women = frozenset({played[-1].event_id})
    monkeypatch.setattr(fj, "_PLAYED", played)
    monkeypatch.setattr(fj, "_WOMEN", women)
    with mp.get_context("fork").Pool(2) as pool:
        par = fj.replay_parallel(pool, "fouls", 0.044, H0, H1, CUT, chunk=5)
    one = fj.replay_base(played, "fouls", 0.044, H0, H1, CUT, women)
    assert par.matches == one.matches
    assert par.final == one.final and par.holdout == one.holdout
    assert par.train == one.train


def _obs(p: float, hits: int, n: int, label: str) -> list[tuple[float, int, str]]:
    return [(p, 1 if i < hits else 0, label) for i in range(n)]


def test_gate_lines_fits_and_gates_each_line_on_its_own_rows() -> None:
    # line 0.5 realises 0.80 at p 0.80 (train and holdout alike); line 1.5
    # realised 0.90 in training but 0.70 on the holdout: it overstates
    train = _obs(0.80, 800, 1000, "0.5") + _obs(0.81, 900, 1000, "1.5")
    hold = ([(0.80, y, i, "0.5") for i, (_, y, _) in
             enumerate(_obs(0.80, 400, 500, "0.5"))]
            + [(0.81, y, 1000 + i, "1.5") for i, (_, y, _) in
               enumerate(_obs(0.81, 350, 500, "1.5"))])
    final = train + [(p, y, label) for p, y, _, label in hold]
    v = fj.gate_lines(train, hold, final)
    assert v["0.5"][0]["pass"] is True
    assert v["1.5"][0]["pass"] is False
    assert "overstates" in v["1.5"][0]["why"]
    assert v["0.5"][1]["0.800-0.825"]["n"] == 1500


def test_line_curve_installs_reads_first_and_survives_a_refit(
        tmp_path: Path) -> None:
    from bet.sofa.fit_meta import carry_separately_fitted_curves
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / inst.FOOTBALL_TARGET).write_text(json.dumps(
        {"by_market": {}, "by_market_direction": {}}))
    key = "both_over_goals_1h|UNDER"
    lines = {key: {"0.5": ({"pass": True}, CURVE),
                   "1.5": ({"pass": False}, CURVE)}}
    fj.write_group(tmp_path / "refit" / fj.GROUP,
                   {key: ({"pass": False}, CURVE)}, {"before": "x"}, {}, lines)
    rc = inst.main(["--dir", str(tmp_path / "refit"), "--config-dir", str(cfg),
                    "--backup-dir", str(tmp_path / "backup"), "--confirm",
                    "--test-cmd", "true"])
    assert rc == 0
    doc = json.loads((cfg / inst.FOOTBALL_TARGET).read_text())
    assert doc["by_market_direction_line"] == {key: {"0.5": CURVE}}
    assert f"{key}@0.5" in doc[inst.FITTED_FROM_KEY]
    assert key not in doc["by_market_direction"]
    cal = Calibration.load(cfg / inst.FOOTBALL_TARGET)
    hit = cal.realised("both_over_goals_1h", 0.76, "football", "UNDER", line=0.5)
    assert hit is not None and hit[1] == f"line:{key}@0.5"
    # the failed line has no curve and no pooled one stands in
    assert cal.realised("both_over_goals_1h", 0.76, "football", "UNDER",
                        line=1.5) is None
    # a full refit rebuilds the file: the line curve is carried
    new: dict[str, object] = {"by_market_direction": {}}
    carried = carry_separately_fitted_curves(new, doc)
    assert carried == [f"{key}@0.5"]
    assert new["by_market_direction_line"] == {key: {"0.5": CURVE}}
