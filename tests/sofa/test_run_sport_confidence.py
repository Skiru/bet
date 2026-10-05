"""scripts/sofa/run_sport_confidence.py - the sport legs the one coupon may
print (plan 2026-10-05, F7 producer, F8). Offline: a fake forecaster."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import sport_confidence as scf
from bet.sofa import sport_identity as si
from scripts.sofa import run_sport_confidence as rsc

DATE = "2026-10-06"
AT = datetime(2026, 10, 6, 15, 0, tzinfo=UTC)
LEG_FIELDS = {
    "sport", "group_key", "sofascore_event_id", "superbet_event_id", "market_id",
    "family", "period", "subject", "line", "side", "confidence", "calibrated_on",
    "calibration_n", "sample_hit_rate", "sample_k", "sample_n", "forecast_p",
    "forecast_source", "odds", "x", "overround", "kickoff_utc", "source_date",
    "price_fetched_at_utc", "match", "competition",
}


class FakeForecaster:
    def __init__(self, p: dict[tuple[int | str, str], float]) -> None:
        self.p = p
        self.calls: list[str] = []

    def probability(self, sport: str, fixture: Any, ev: Any, line: Any) -> float | None:
        self.calls.append(sport)
        key = line.family if sport == "cs2" else line.market_id
        return self.p.get((key, line.side))

    def sample(self, sport: str, fixture: Any, ev: Any, line: Any) -> tuple[int, int]:
        return 7, 10


def _line(mid: int, family: str, side: str, odds: float, line: float | None = None,
          subject: str = "") -> dict[str, Any]:
    return {"superbet_event_id": "1", "market_id": mid, "family": family,
            "period": 0, "subject": subject, "line": line, "side": side,
            "odds": odds}


def _snapshot(kick: str = "2026-10-06T18:00:00Z", fetched: str = "2026-10-06T14:30:00Z",
              lines: list[dict[str, Any]] | None = None, sb: str = "1",
              tournament: str = "Czechy - Extraliga") -> dict[str, Any]:
    return {"fetched_at_utc": fetched, "superbet_event_id": sb,
            "match_name": "Sparta Praha·Kometa Brno", "team1": "Sparta Praha",
            "team2": "Kometa Brno", "kickoff_utc": kick, "tournament": tournament,
            "lines": lines if lines is not None else [
                _line(623, "total", "OVER", 1.30, 4.5),
                _line(623, "total", "UNDER", 3.40, 4.5),
                _line(630, "winner", "T1", 1.80),
                _line(630, "winner", "T2", 2.00),
                _line(775, "odd_even", "ODD", 1.9),  # not a hockey market here
            ]}


def _write(tmp: Path, sport: str, snaps: list[dict[str, Any]], date: str = DATE) -> None:
    day = tmp / "shadow" / sport / date
    day.mkdir(parents=True, exist_ok=True)
    (day / "snapshots.jsonl").write_text("".join(json.dumps(s) + "\n" for s in snaps))


def _fixtures(tmp: Path, records: list[dict[str, Any]],
              sports: list[str] | None = None) -> None:
    (tmp / DATE).mkdir(parents=True, exist_ok=True)
    (tmp / DATE / si.FIXTURES_FILE).write_text(json.dumps(
        {"date": DATE, "sports_run": sports or list(si.SPORT_KEYS),
         "fixtures": records}))


def _fixture(sb: str = "1", sport: str = "hockey", **extra: Any) -> dict[str, Any]:
    return {"superbet_event_id": sb, "sport": sport, "status": si.IDENTIFIED,
            "sofascore_event_id": 9001, "home_id": 10, "away_id": 20,
            "home_is_team1": True, "competition_id": 55,
            "sofascore_start_utc": "2026-10-06T18:00:00Z", **extra}


def _calibration(tmp: Path, sports: dict[str, list[str]] | None = None) -> Path:
    curve = {"0.800-0.825": {"n": 400, "realised": 0.84, "realised_lo95": 0.80},
             "0.000-0.600": {"n": 900, "realised": 0.45, "realised_lo95": 0.42}}
    sports = sports if sports is not None else {
        "hockey": ["total|OVER", "total|UNDER", "winner|TEAM"]}
    doc = {"min_bucket": 200, "fitted_from": {"before": "2026-10-05"},
           "sports": {s: {"curves": {k: curve for k in keys}, "admitted": keys}
                      for s, keys in sports.items()}}
    path = tmp / "cal.json"
    path.write_text(json.dumps(doc))
    return path


def _build(tmp: Path, cal: Path | None, forecaster: Any = None,
           at: datetime = AT) -> tuple[dict[str, Any], int]:
    fc = forecaster or FakeForecaster({(623, "OVER"): 0.81, (623, "UNDER"): 0.19,
                                       (630, "T1"): 0.81, (630, "T2"): 0.19})
    return rsc.build(DATE, str(tmp), cal or tmp / "missing.json", fc, at,
                     sports=("hockey",))


def test_a_leg_carries_exactly_the_agreed_fields(tmp_path: Path):
    _write(tmp_path, "hockey", [_snapshot()])
    _fixtures(tmp_path, [_fixture()])
    doc, code = _build(tmp_path, _calibration(tmp_path))
    assert code == 0
    assert doc["sports"]["hockey"]["status"] == "OK"
    # 1.30 x 0.80 = 1.04 >= 0.90 -> a leg; T1 1.80 x 0.80 = 1.44 -> a leg
    legs = {(g["market_id"], g["side"]): g for g in doc["legs"]}
    assert set(legs) == {(623, "OVER"), (630, "T1")}
    leg = legs[(623, "OVER")]
    assert set(leg) == LEG_FIELDS
    assert leg["group_key"] == "sofa:9001" and leg["sofascore_event_id"] == 9001
    assert leg["confidence"] == 0.80 and leg["forecast_p"] == 0.81
    assert leg["calibrated_on"] == "hockey:total|OVER" and leg["calibration_n"] == 400
    assert leg["x"] == pytest.approx(1.04) and leg["forecast_source"] == "score_model"
    assert (leg["sample_k"], leg["sample_n"], leg["sample_hit_rate"]) == (7, 10, 0.7)
    assert leg["overround"] == pytest.approx(1 / 1.3 + 1 / 3.4 - 1, abs=1e-4)
    assert leg["match"] == "Sparta Praha - Kometa Brno"
    assert leg["source_date"] == DATE
    assert doc["sports"]["hockey"]["refused"]["MARKET_NOT_ALLOWED"] == 1
    # the low sides read the catch-all bucket: under the floor
    assert doc["sports"]["hockey"]["refused"]["BELOW_FLOOR"] == 2
    on_disk = json.loads((tmp_path / DATE / rsc.ARTIFACT).read_text())
    assert on_disk["legs"] == doc["legs"]
    assert set(on_disk) == {"created_at_utc", "date", "calibration_fitted_from",
                            "rule", "sports", "legs"}


def test_the_price_filters_are_the_official_coupons(tmp_path: Path):
    assert rsc.price_filter(0.80, 1.12, 0.05) == "BELOW_MIN_X"  # 0.896
    assert rsc.price_filter(0.80, 1.125, 0.05) is None  # exactly 0.90
    assert rsc.price_filter(0.95, 1.08, 0.05) == "ODDS_TOO_LOW"  # < 1/0.9202
    assert rsc.price_filter(0.80, 1.5, 0.151) == "MARGIN_TOO_HIGH"
    assert rsc.price_filter(0.80, 1.5, 0.15) is None
    assert rsc.price_filter(0.69, 2.0, 0.05) == "BELOW_FLOOR"
    assert rsc.price_filter(0.80, 1.5, -0.01) == "NEGATIVE_MARGIN"


def test_no_calibration_file_is_not_calibrated_and_partial(tmp_path: Path):
    _write(tmp_path, "hockey", [_snapshot()])
    _fixtures(tmp_path, [_fixture()])
    fc = FakeForecaster({})
    doc, code = _build(tmp_path, None, fc)
    assert code == 1
    assert doc["sports"]["hockey"]["status"] == "NOT_CALIBRATED"
    assert doc["legs"] == [] and fc.calls == []  # no model is even read
    assert (tmp_path / DATE / rsc.ARTIFACT).exists()
    # a file without the sport, or with nothing admitted: the same
    doc, code = _build(tmp_path, _calibration(tmp_path, {"basketball": ["total|OVER"]}))
    assert code == 1 and doc["sports"]["hockey"]["status"] == "NOT_CALIBRATED"
    doc, code = _build(tmp_path, _calibration(tmp_path, {"hockey": []}))
    assert code == 1 and doc["sports"]["hockey"]["status"] == "NOT_CALIBRATED"


def test_no_fixtures_file_is_not_identified_and_partial(tmp_path: Path):
    _write(tmp_path, "hockey", [_snapshot()])
    doc, code = _build(tmp_path, _calibration(tmp_path))
    assert code == 1 and doc["legs"] == []
    assert doc["sports"]["hockey"]["status"] == "NOT_IDENTIFIED"
    assert doc["sports"]["hockey"]["refused"]["NOT_IDENTIFIED"] == 4


def test_an_unidentified_or_duplicate_event_prints_nothing(tmp_path: Path):
    _write(tmp_path, "hockey", [_snapshot(), _snapshot(sb="2", lines=[
        {**ln, "superbet_event_id": "2"} for ln in _snapshot()["lines"]])])
    _fixtures(tmp_path, [
        _fixture(status=si.NOT_IDENTIFIED, reason="AMBIGUOUS"),
        _fixture(sb="2", status=si.DUPLICATE_SUPERBET_TEAM)])
    doc, _ = _build(tmp_path, _calibration(tmp_path))
    assert doc["legs"] == []
    assert doc["sports"]["hockey"]["refused"] == {
        "MARKET_NOT_ALLOWED": 2, "NOT_IDENTIFIED": 4, si.DUPLICATE_SUPERBET_TEAM: 4}


def test_started_stale_and_out_of_day_events_are_refused(tmp_path: Path):
    _write(tmp_path, "hockey", [_snapshot()])
    _fixtures(tmp_path, [_fixture(sofascore_start_utc="2026-10-06T15:10:00Z")])
    doc, _ = _build(tmp_path, _calibration(tmp_path))
    # Sofascore's earlier start is the clock: 10 minutes away < the margin
    assert doc["sports"]["hockey"]["refused"]["KICKED_OFF"] == 4
    _write(tmp_path, "hockey", [_snapshot(fetched="2026-10-06T12:00:00Z")])
    _fixtures(tmp_path, [_fixture()])
    doc, _ = _build(tmp_path, _calibration(tmp_path), at=AT + timedelta(hours=1))
    assert doc["sports"]["hockey"]["refused"]["STALE_PRICE"] == 4  # 4 h old
    tmp2 = tmp_path / "next"
    _write(tmp2, "hockey", [_snapshot(kick="2026-10-07T00:30:00Z")])
    _write(tmp2, "hockey", [_snapshot(kick="2026-10-07T00:30:00Z")], "2026-10-07")
    (tmp2 / DATE).mkdir(parents=True)
    (tmp2 / DATE / si.FIXTURES_FILE).write_text(json.dumps(
        {"sports_run": ["hockey"], "fixtures": [_fixture()]}))
    doc, _ = rsc.build(DATE, str(tmp2), _calibration(tmp2), FakeForecaster({}), AT,
                       sports=("hockey",))
    assert doc["legs"] == [] and doc["sports"]["hockey"]["refused"] == {}


def test_a_key_that_is_not_admitted_is_not_calibrated(tmp_path: Path):
    _write(tmp_path, "hockey", [_snapshot()])
    _fixtures(tmp_path, [_fixture()])
    doc, code = _build(tmp_path, _calibration(tmp_path, {"hockey": ["winner|TEAM"]}))
    assert code == 0
    assert [(g["market_id"], g["side"]) for g in doc["legs"]] == [(630, "T1")]
    assert doc["sports"]["hockey"]["refused"]["NOT_CALIBRATED"] == 2


def test_volleyball_needs_a_tournament_with_a_settled_event(tmp_path: Path):
    lines = [{"superbet_event_id": "1", "market_id": 745, "family": "winner",
              "period": 0, "subject": "", "line": None, "side": s, "odds": o}
             for s, o in (("T1", 1.4), ("T2", 2.8))]
    _write(tmp_path, "volleyball", [_snapshot(lines=lines, tournament="Polska - PlusLiga")])
    _fixtures(tmp_path, [_fixture(sport="volleyball")])
    cal = _calibration(tmp_path, {"volleyball": ["winner|TEAM"]})
    fc = FakeForecaster({(745, "T1"): 0.81, (745, "T2"): 0.19})
    doc, _ = rsc.build(DATE, str(tmp_path), cal, fc, AT, sports=("volleyball",))
    assert doc["legs"] == []
    assert doc["sports"]["volleyball"]["refused"]["TOURNAMENT_NEVER_SETTLED"] == 2
    prev = tmp_path / "shadow" / "volleyball" / "2026-10-03"
    prev.mkdir(parents=True)
    (prev / "settled.json").write_text(json.dumps({"events": {"5": {
        "state": "SETTLED", "tournament": "Polska - PlusLiga"}}}))
    doc, _ = rsc.build(DATE, str(tmp_path), cal, fc, AT, sports=("volleyball",))
    assert [g["side"] for g in doc["legs"]] == ["T1"]


def test_a_cs2_leg_names_its_teams_and_map(tmp_path: Path):
    day = tmp_path / "cs2" / DATE
    day.mkdir(parents=True)
    lines = [{"superbet_event_id": "8", "family": "map_winner", "map_nr": 1,
              "subject": "", "line": None, "side": s, "odds": o}
             for s, o in (("T1", 1.5), ("T2", 2.5))]
    (day / "snapshots.jsonl").write_text(json.dumps({
        "fetched_at_utc": "2026-10-06T14:30:00Z", "superbet_event_id": "8",
        "match_name": "NAVI Junior·BIG", "team1": "NAVI Junior", "team2": "BIG",
        "kickoff_utc": "2026-10-06T18:00:00Z", "tournament": "CCT", "lines": lines})
        + "\n")
    _fixtures(tmp_path, [_fixture(sb="8", sport="cs2", best_of=3)])
    cal = _calibration(tmp_path, {"cs2": ["map_winner|TEAM"]})
    fc = FakeForecaster({("map_winner", "T1"): 0.81, ("map_winner", "T2"): 0.19})
    doc, code = rsc.build(DATE, str(tmp_path), cal, fc, AT, sports=("cs2",))
    assert code == 0
    (leg,) = doc["legs"]
    assert set(leg) == LEG_FIELDS | {"team1", "team2", "map_nr"}
    assert leg["market_id"] is None and leg["map_nr"] == 1 and leg["period"] == 1
    assert leg["forecast_source"] == "cs2_engine"
    assert (leg["team1"], leg["team2"]) == ("NAVI Junior", "BIG")


def test_sport_legs_never_reach_the_settled_table_or_the_football_curves():
    root = Path(__file__).resolve().parents[2]
    for rel in ("scripts/sofa/run_sport_confidence.py",
                "scripts/sofa/fit_sport_confidence.py",
                "src/bet/sofa/sport_confidence.py",
                "src/bet/sofa/sport_identity.py"):
        text = (root / rel).read_text(encoding="utf-8")
        assert "sofa_settled_row" not in text, rel
        assert "sofa_confidence_calibration.json" not in text.replace(
            "sofa_sport_confidence_calibration.json", ""), rel
    fit = (root / "scripts/sofa/fit_confidence.py").read_text(encoding="utf-8")
    assert rsc.ARTIFACT not in fit and "sport_confidence" not in fit
    # the producer opens the database read-only
    assert "mode=ro" in (root / "scripts/sofa/run_sport_confidence.py").read_text()
    assert scf.CALIBRATION_FILE != "sofa_confidence_calibration.json"


def test_the_frozen_clock_is_refused_on_the_real_runs_dir(monkeypatch, capsys):
    from bet.sofa import timeutil

    monkeypatch.setenv("SOFA_NOW", "2026-10-06T10:00:00Z")
    monkeypatch.setenv("SOFA_RUNS_DIR", str(timeutil.REAL_RUNS_DIR))
    monkeypatch.setattr("sys.argv", ["run_sport_confidence.py", "--date", DATE])
    assert rsc.main() == 2
    assert "REFUSED" in capsys.readouterr().err


def test_the_db_forecaster_orients_the_model_to_superbets_team1():
    from types import SimpleNamespace

    from bet.sofa import score_model as sm
    from bet.sofa.shadow import SPORTS, ShadowLine

    history = [sm.FootballResult(
        i, i, 5, 100 + i % 4, 200 + i % 4,
        {**{f"p{k}_for": (1.5, 0.5) for k in (1, 2, 3)},
         sm.REG_METRIC["hockey"]: (4.5, 1.5)}) for i in range(80)]
    model = sm.build_model(history, SPORTS["hockey"], cut_ts=10**9)
    fc = rsc.DbForecaster("unused.db", AT)
    fc._shadow["hockey"] = (model, scf.TeamGames({}))
    ev = SimpleNamespace(kickoff_utc="2026-10-06T18:00:00Z", team1="a", team2="b")
    t1 = ShadowLine("1", 630, "winner", 0, "", None, "T1", 1.5)
    t2 = ShadowLine("1", 630, "winner", 0, "", None, "T2", 2.5)
    straight = _fixture(home_id=100, away_id=200, competition_id=5)
    crossed = _fixture(sb="2", home_id=100, away_id=200, competition_id=5,
                       home_is_team1=False)
    p_home = fc.probability("hockey", straight, ev, t1)
    p_away_as_t1 = fc.probability("hockey", crossed, ev, t1)
    p_away = fc.probability("hockey", straight, ev, t2)
    assert p_home is not None and p_away_as_t1 is not None and p_away is not None
    assert p_home > 0.8  # the home side scores three times as much
    assert p_away_as_t1 == pytest.approx(p_away, abs=0.03)
    unrated = _fixture(sb="3", home_id=999, away_id=200, competition_id=5)
    assert fc.probability("hockey", unrated, ev, t1) is None


def test_a_snapshot_taken_after_the_clock_is_not_read(tmp_path: Path):
    later = _snapshot(fetched="2026-10-06T16:00:00Z", lines=[
        _line(623, "total", "OVER", 1.10, 4.5), _line(623, "total", "UNDER", 6.0, 4.5)])
    _write(tmp_path, "hockey", [_snapshot(), later])
    _fixtures(tmp_path, [_fixture()])
    doc, _ = _build(tmp_path, _calibration(tmp_path))
    over = [g for g in doc["legs"] if g["market_id"] == 623]
    assert [g["odds"] for g in over] == [1.30]
    assert over[0]["price_fetched_at_utc"] == "2026-10-06T14:30:00Z"


def _status(tmp: Path, events: dict[int, dict[str, Any]]) -> None:
    (tmp / DATE).mkdir(parents=True, exist_ok=True)
    (tmp / DATE / "fixture_status.json").write_text(json.dumps(
        {"events": {str(k): v for k, v in events.items()}}))


@pytest.mark.parametrize("state", ["postponed", "canceled", "interrupted"])
def test_a_pinned_game_not_as_scheduled_is_refused(tmp_path: Path, state: str):
    # K14 for the measured sports (2026-10-05): FIXTURE_CHECK reads the
    # pinned id; a postponed / cancelled / halted game prints nothing.
    _write(tmp_path, "hockey", [_snapshot()])
    _fixtures(tmp_path, [_fixture()])
    _status(tmp_path, {9001: {"status": state, "start_utc": "2026-10-06T18:00:00Z",
                              "why": "printed"}})
    doc, _ = _build(tmp_path, _calibration(tmp_path))
    hockey = doc["sports"]["hockey"]
    assert doc["legs"] == []
    assert hockey["refused"]["FIXTURE_NOT_AS_SCHEDULED"] == 4
    assert hockey["fixtures_not_as_scheduled"] == [{
        "sofascore_event_id": 9001, "superbet_event_id": "1", "status": state,
        "match": "Sparta Praha - Kometa Brno"}]


def test_an_unverified_or_absent_check_refuses_nothing(tmp_path: Path):
    _write(tmp_path, "hockey", [_snapshot()])
    _fixtures(tmp_path, [_fixture()])
    baseline, _ = _build(tmp_path, _calibration(tmp_path))
    _status(tmp_path, {9001: {"status": "UNVERIFIED", "reason": "NO_BRIDGE"},
                       9002: {"status": "postponed"}})  # another game
    doc, _ = _build(tmp_path, _calibration(tmp_path))
    assert len(doc["legs"]) == len(baseline["legs"]) == 2
    assert "FIXTURE_NOT_AS_SCHEDULED" not in doc["sports"]["hockey"]["refused"]


def test_a_fresh_start_replaces_the_pinned_one_in_the_kickoff_gate(tmp_path: Path):
    # K12: SPORT_IDENTITY pinned 18:00Z; Sofascore now says 15:10Z (inside the
    # margin at 15:00Z) - the gate reads the fresh start, as CONFIDENCE does.
    _write(tmp_path, "hockey", [_snapshot()])
    _fixtures(tmp_path, [_fixture()])
    _status(tmp_path, {9001: {"status": "notstarted",
                              "start_utc": "2026-10-06T15:10:00Z"}})
    doc, _ = _build(tmp_path, _calibration(tmp_path))
    assert doc["legs"] == []
    assert doc["sports"]["hockey"]["refused"]["KICKED_OFF"] == 4


def test_a_cs2_team_rounds_line_the_curve_was_not_fitted_on_is_refused(
        tmp_path: Path):
    # 2026-10-05 night: the team-rounds curve is fitted on 9.5-12.5 only; a
    # 6.5 on a lopsided series read it by p alone (realised 0.30 at 0.731).
    day = tmp_path / "cs2" / DATE
    day.mkdir(parents=True)
    lines = [{"superbet_event_id": "8", "family": "map_team_rounds", "map_nr": 1,
              "subject": "NAVI Junior", "line": ln, "side": s, "odds": o}
             for ln in (6.5, 10.5) for s, o in (("OVER", 1.3), ("UNDER", 3.2))]
    (day / "snapshots.jsonl").write_text(json.dumps({
        "fetched_at_utc": "2026-10-06T14:30:00Z", "superbet_event_id": "8",
        "match_name": "NAVI Junior·BIG", "team1": "NAVI Junior", "team2": "BIG",
        "kickoff_utc": "2026-10-06T18:00:00Z", "tournament": "CCT", "lines": lines})
        + "\n")
    _fixtures(tmp_path, [_fixture(sb="8", sport="cs2", best_of=3)])
    cal = _calibration(tmp_path, {"cs2": ["map_team_rounds|OVER"]})
    fc = FakeForecaster({("map_team_rounds", "OVER"): 0.81,
                         ("map_team_rounds", "UNDER"): 0.19})
    doc, _ = rsc.build(DATE, str(tmp_path), cal, fc, AT, sports=("cs2",))
    assert [g["line"] for g in doc["legs"]] == [10.5]
    assert doc["sports"]["cs2"]["refused"][scf.LINE_OUTSIDE_FIT] == 2
    assert scf.line_in_fit("hockey", "total", 7.5)
    assert not scf.line_in_fit("cs2", "map_team_rounds", None)
