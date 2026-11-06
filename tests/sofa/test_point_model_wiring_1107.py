"""epochs.VB_POINT_MODEL (volleyball rally-point model in SPORT_CONFIDENCE)
and epochs.TENNIS_HANDICAP_POINT_MODEL (tennis per-set games handicap from
the point model in SHEET), both from 2026-11-06 17:30Z by the build clock
(operator 2026-11-06: install what is better than the current estimator;
moved from 11-07 00:00Z into the day, 11-06 mixed). Offline."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa import rebuild_plan as rp
from bet.sofa import sport_confidence as scf
from bet.sofa import tennis_handicap_point as thp
from bet.sofa import tennis_point_curves as tpc
from bet.sofa import tennis_point_sheet as tps
from bet.sofa import vb_point_pricer as vpp
from bet.sofa import volleyball_point_model as vpm
from bet.sofa.confidence import Calibration
from bet.sofa.config import config_path
from bet.sofa.tennis_point_model import PointMatch, SideServe
from scripts.sofa import fit_line_evidence as fle
from scripts.sofa import refresh_line_evidence as rle
from scripts.sofa import run_sport_confidence as rsc
from scripts.sofa.run_sheet import AUDIT_MARKER_FIELDS

ON = datetime(2026, 11, 6, 17, 30, tzinfo=UTC)
REPO = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------
# Switches
# --------------------------------------------------------------------------


def test_both_switches_are_from_11_06_17_30_by_the_day_and_the_build_clock(
) -> None:
    assert epochs.VB_POINT_MODEL_FROM_UTC == ON
    assert epochs.TENNIS_HANDICAP_POINT_MODEL_FROM_UTC == ON
    for fn in (epochs.vb_point_model, epochs.tennis_handicap_point_model):
        assert not fn("2026-11-05", ON + timedelta(hours=5))
        assert not fn("2026-11-06", ON - timedelta(minutes=1))
        assert fn("2026-11-06", ON)
        assert fn("2026-11-07", ON + timedelta(hours=8))
    # the per-set handicap widens the point model's scope only from 17:30Z
    assert epochs.tennis_point_markets(
        "2026-11-06", ON - timedelta(minutes=1)) == (
        epochs.TENNIS_POINT_MODEL_MARKETS)
    assert epochs.tennis_point_markets("2026-11-07", ON) == (
        epochs.TENNIS_POINT_MODEL_MARKETS
        | epochs.TENNIS_HANDICAP_POINT_MODEL_MARKETS)
    assert epochs.tennis_point_markets("2026-11-05", ON) == frozenset()
    # the full-match handicap failed the calibration rule: never in scope
    assert "handicap_games" not in epochs.tennis_point_markets("2026-11-07", ON)


def test_the_volleyball_scope_is_the_families_that_passed() -> None:
    fams = {scf.allowed_markets("volleyball", True, True)[m]
            for m in epochs.VB_POINT_MODEL_MARKETS}
    assert fams == {"winner", "points_handicap", "points_total", "set_handicap",
                    "exact_sets", "set_winner", "set_points_total",
                    "points_odd_even"}
    # measured worse than the current estimator (or no rally curve): kept
    for mid in (230058, 100077, 781, -11, -12, -13, -14, -15):
        assert mid not in epochs.VB_POINT_MODEL_MARKETS


# --------------------------------------------------------------------------
# Volleyball: the rally curves are overlaid by the switch's build clock
# --------------------------------------------------------------------------


def test_the_rally_curves_follow_the_build_clock_not_the_file() -> None:
    day = scf.calibration_path_for("2026-11-06")
    assert day.name.endswith(".next.2026-11-06.json")
    cal = scf.SportCalibration.load(day)
    assert cal is not None
    # before the switch: the very same object, nothing overlaid
    assert scf.with_vb_point_curves(
        cal, "2026-11-06", ON - timedelta(minutes=1)) is cal
    on = scf.with_vb_point_curves(cal, "2026-11-06", ON)
    assert on is not None and on is not cal
    staged = json.loads(scf.calibration_path_for("2026-11-07").read_text(
        encoding="utf-8"))
    # 11-06 after 17:30Z reads exactly the volleyball section 11-07 reads
    assert on.doc["sports"]["volleyball"] == staged["sports"]["volleyball"]
    # every other sport (11-06's basketball period curves) untouched
    for sport in ("hockey", "basketball", "cs2"):
        assert on.doc["sports"][sport] == cal.doc["sports"][sport]
    assert on.doc["effective_from"] == cal.doc["effective_from"]
    # the overlay is only the rally keys; on 11-07's file it is a no-op
    source = json.loads(config_path(scf.VB_POINT_CURVES_FILE).read_text(
        encoding="utf-8"))
    fams = {scf.allowed_markets("volleyball", True, True)[m]
            for m in epochs.VB_POINT_MODEL_MARKETS}
    assert {k.split("|")[0] for k in source["curves"]} == fams
    assert sorted(source["curves"]) == sorted(
        source["vb_point_model_curves"]["keys"])
    old = cal.doc["sports"]["volleyball"]["curves"]
    for key, curve in on.doc["sports"]["volleyball"]["curves"].items():
        if key not in source["curves"]:
            assert old[key] == curve
    eleven = scf.SportCalibration(staged)
    assert scf.with_vb_point_curves(
        eleven, "2026-11-07", ON + timedelta(hours=8)).doc == staged  # type: ignore[union-attr]


def test_the_staged_sport_calibration_moves_with_the_switch() -> None:
    path = scf.calibration_path_for("2026-11-07")
    assert path.name == "sofa_sport_confidence_calibration.next.2026-11-07.json"
    assert scf.calibration_path_for("2026-11-06").name.endswith(
        ".next.2026-11-06.json")
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert epochs.VB_POINT_MODEL_FROM_UTC is not None
    # the staged file starts the first whole day of the switch
    assert doc["effective_from"] == "2026-11-07"
    prev = json.loads(scf.calibration_path_for("2026-11-06").read_text(
        encoding="utf-8"))
    vb = doc["sports"]["volleyball"]
    keys = set(vb["vb_point_model_curves"]["keys"])
    fams = {scf.allowed_markets("volleyball", True, True)[m]
            for m in epochs.VB_POINT_MODEL_MARKETS}
    assert {k.split("|")[0] for k in keys} == fams
    # every other key and every other sport byte for byte the 11-06 file's
    for key, curve in vb["curves"].items():
        if key not in keys:
            assert prev["sports"]["volleyball"]["curves"][key] == curve
    for sport in ("hockey", "basketball", "cs2"):
        assert doc["sports"][sport] == prev["sports"][sport]


# --------------------------------------------------------------------------
# Volleyball: the as-of walk and the pricer
# --------------------------------------------------------------------------


def _vb_history(n: int = 60, seed: int = 3) -> list[vpm.VbMatch]:
    rng = random.Random(seed)
    out = []
    for i in range(n):
        h, a = rng.sample(range(1, 9), 2)
        sets = [(25, rng.randint(15, 23)) if rng.random() < 0.5 + 0.05 * (h - a)
                else (rng.randint(15, 23), 25) for _ in range(3)]
        out.append(vpm.VbMatch(1000 + i, 1_000_000 + i * 3600 * (1 + i % 3), 7,
                               h, a, False, tuple(s[0] for s in sets),
                               tuple(s[1] for s in sets)))
    out.sort(key=lambda m: (m.ts, m.event_id))
    return out


def test_the_walker_equals_the_batch_forecast_in_any_order() -> None:
    hist = _vb_history()
    fixtures = [vpm.VbMatch(5000 + i, hist[k].ts, 7, 1, 2 + i % 3, False, (), ())
                for i, k in enumerate((50, 10, 30, 59, 10))]
    fixtures.append(vpm.VbMatch(9999, hist[-1].ts + 99, 7, 3, 4, False, (), ()))
    # a fixture already played (a rebuild of a past day): its own match is
    # cached and must not teach it
    played = hist[20]
    fixtures.append(vpm.VbMatch(played.event_id, played.ts + 7200, 7,
                                played.home, played.away, False, (), ()))
    batch = vpp.forecast_fixtures(hist, fixtures)
    walker = vpp.Walker(hist)
    for m in fixtures:  # out of start order on purpose
        assert walker.forecast(m) == batch[m.event_id]
    # the same as the measurement's walk_forward for the played match
    assert batch[played.event_id] == vpm.walk_forward(
        hist, {played.event_id}, vpp.PARAMS)[played.event_id]


def test_the_pricer_is_seeded_oriented_and_scoped() -> None:
    hist = _vb_history()
    fx = vpp.fixture_match(77, datetime.fromtimestamp(hist[-1].ts + 60, UTC),
                           1, 2, 7, vpp.women_by_team(hist))
    assert fx is not None
    pricer = vpp.VbPricer(vpp.forecast_fixtures(hist, [fx]), sims=2000)
    t1 = pricer.p(77, True, 745, 0, "", None, "T1")
    t1_swapped = pricer.p(77, False, 745, 0, "", None, "T1")
    assert t1 is not None and t1_swapped is not None
    assert t1 + t1_swapped == pytest.approx(1.0)
    over = pricer.p(77, True, 230060, 0, "", 180.5, "OVER")
    under = pricer.p(77, True, 230060, 0, "", 180.5, "UNDER")
    assert over is not None and under is not None
    assert over + under == pytest.approx(1.0)
    again = vpp.VbPricer(pricer.forecasts, sims=2000)
    assert again.p(77, True, 745, 0, "", None, "T1") == t1
    assert pricer.p(77, True, 230058, 0, "", 3.5, "OVER") is None  # sets_total
    assert pricer.p(78, True, 745, 0, "", None, "T1") is None  # no forecast
    assert vpp.fixture_match(1, datetime(2026, 11, 7, tzinfo=UTC), None, 2, 7,
                             {}) is None


@dataclass
class _Line:
    market_id: int
    period: int = 0
    subject: str = ""
    line: float | None = None
    side: str = "T1"


class _NoModel:
    def expected(self, *a: Any, **k: Any) -> None:
        return None


def test_sport_confidence_reads_the_rally_model_only_under_the_switch(
        monkeypatch: pytest.MonkeyPatch) -> None:
    hist = _vb_history()
    fixture = {"sofascore_event_id": 77, "superbet_event_id": "sb77",
               "home_id": 1, "away_id": 2, "competition_id": 7,
               "home_is_team1": True,
               "sofascore_start_utc": datetime.fromtimestamp(
                   hist[-1].ts + 60, UTC).isoformat()}
    ev = type("Ev", (), {"kickoff_utc": fixture["sofascore_start_utc"]})()

    def forecaster(at: datetime) -> rsc.DbForecaster:
        fc = rsc.DbForecaster(db_path="/nonexistent", at=at, date="2026-11-07")
        fc._shadow["volleyball"] = (_NoModel(), scf.TeamGames.build([], None))  # type: ignore[arg-type]
        fc._vb_walker = vpp.Walker(hist)
        fc._vb_women = vpp.women_by_team(hist)
        return fc

    on = forecaster(ON + timedelta(hours=6))
    p_on = on.probability("volleyball", fixture, ev, _Line(745))
    assert p_on is not None
    assert on.vb_point_rule("volleyball", _Line(745)) == {
        epochs.VB_POINT_MODEL_LEG_FIELD: epochs.VB_POINT_MODEL}
    # out of scope (sets_total) still goes to the score model (none here)
    assert on.probability("volleyball", fixture, ev, _Line(230058, line=3.5,
                                                            side="OVER")) is None
    assert on.vb_point_rule("volleyball", _Line(230058)) == {}
    assert on.vb_point_rule("hockey", _Line(745)) == {}
    monkeypatch.setattr(epochs, "VB_POINT_MODEL_FROM_UTC", None)
    off = forecaster(ON + timedelta(hours=6))
    assert off.probability("volleyball", fixture, ev, _Line(745)) is None
    assert off.vb_point_rule("volleyball", _Line(745)) == {}


def test_line_evidence_reads_the_rally_p_or_skips(tmp_path: Path) -> None:
    rows = [
        {"sport": "volleyball", "family": "winner", "market_id": 745, "period": 0,
         "subject": "", "line": None, "side": "T1", "key": "winner|TEAM",
         "p": 0.8, "y": 1, "game": "s:2026-10-01:111"},
        {"sport": "volleyball", "family": "winner", "market_id": 745, "period": 0,
         "subject": "", "line": None, "side": "T1", "key": "winner|TEAM",
         "p": 0.8, "y": 1, "game": "s:2026-10-01:222"},
        {"sport": "volleyball", "family": "sets_total", "market_id": 230058,
         "period": 0, "subject": "", "line": 3.5, "side": "OVER",
         "key": "sets_total|OVER", "p": 0.4, "y": 0, "game": "s:2026-10-01:111"},
    ]
    (tmp_path / "volleyball_superbet_settled.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    cal = scf.SportCalibration({"sports": {"volleyball": {"curves": {}}}})
    key = vpp.backfill_key("2026-10-01", "111", 745, 0, "", None, "T1")
    got = list(fle.sport_rows(tmp_path, cal, str(tmp_path), {key: 0.61}))
    assert [(r["key"], r["p"], r["game"]) for r in got] == [
        ("winner|TEAM", 0.61, "s:2026-10-01:111"),  # the rally model's p
        ("sets_total|OVER", 0.4, "s:2026-10-01:111"),  # out of scope: as before
    ]  # 222 has no rally p: skipped, never read at the score model's
    plain = list(fle.sport_rows(tmp_path, cal, str(tmp_path)))
    assert [r["p"] for r in plain] == [0.8, 0.8, 0.4]


def test_backfill_keys_and_the_refresh_step(tmp_path: Path) -> None:
    assert vpp.backfill_key("2026-10-01", "15", "745", None, None, None, "T1") == (
        "2026-10-01|15|745|0|||T1")
    assert vpp.backfill_key("2026-10-01", 15, 1069, 0, "", -3.5, "T2") == (
        "2026-10-01|15|1069|0||-3.5|T2")
    path = tmp_path / "p.json.gz"
    vpp.write_backfill({"b": 0.2, "a": 0.1}, path)
    assert vpp.load_backfill(path) == {"a": 0.1, "b": 0.2}
    assert vpp.load_backfill(tmp_path / "none.json.gz") == {}
    assert rle.vb_point_command("2026-11-07")[1:] == [
        "scripts/sofa/backfill_vb_point_p.py", "--before", "2026-11-07"]
    src = (REPO / "scripts" / "sofa" / "refresh_line_evidence.py").read_text(
        encoding="utf-8")
    assert "epochs.vb_point_model(args.before)" in src


# --------------------------------------------------------------------------
# Tennis: the per-set handicap from the point model
# --------------------------------------------------------------------------


def _t_match(eid: int, ts: int, home: int, away: int) -> PointMatch:
    serve = SideServe(played=90, won=60, aces=5, dfs=3, set_aces=(2, 3, None),
                      set_dfs=(1, 2, None))
    return PointMatch(
        event_id=eid, ts=ts, tier="TOUR", surface="hard", female=False,
        tournament=7, home_id=home, away_id=away, home_won=True,
        sets=((6, 4), (6, 3)), completed=True, best_of=3,
        match_tiebreak_decider=False, home=serve,
        away=SideServe(played=80, won=45, aces=2, dfs=4, set_aces=(1, 1, None),
                       set_dfs=(2, 2, None)))


def _t_pricer(markets: frozenset[str]) -> tps.PointPricer:
    hist = [_t_match(100 + i, 1_000_000 + i * 86400, 1, 3 + i % 3)
            for i in range(30)]
    fx = tps.fixture_match(999, datetime.fromtimestamp(hist[-1].ts + 1, UTC), 1, 2,
                           "ATP", "Hardcourt outdoor", 7, 3, {1: False})
    assert fx is not None
    return tps.PointPricer(tps.forecast_fixtures(hist, [fx]), sims=2000,
                           markets=markets)


def test_the_point_pricer_reads_the_set_handicap_only_in_scope() -> None:
    wide = _t_pricer(epochs.TENNIS_POINT_MODEL_MARKETS
                     | epochs.TENNIS_HANDICAP_POINT_MODEL_MARKETS)
    ms = wide.market_sim(999)
    assert ms is not None
    for market in sorted(epochs.TENNIS_HANDICAP_POINT_MODEL_MARKETS):
        for side in (0, 1):
            p = wide.p(999, market, side, -1.5, "OVER")
            assert p is not None and p == thp.p_handicap(ms, market, side, -1.5)
            assert wide.p(999, market, side, -1.5, "UNDER") is None  # OVER only
            centre = wide.centre(999, market, side)
            assert centre == thp.mean_sd(ms, market, side)
        assert wide.p(999, market, None, -1.5, "OVER") is None  # needs a side
        # "home -1.5" and "away +1.5" are the two sides of one line
        home = wide.p(999, market, 0, -1.5, "OVER")
        away = wide.p(999, market, 1, 1.5, "OVER")
        assert home is not None and away is not None
        assert home + away == pytest.approx(1.0)
        assert wide.covers("tennis", market)
    base = _t_pricer(epochs.TENNIS_POINT_MODEL_MARKETS)
    assert base.p(999, "handicap_games_won_set1", 0, -1.5, "OVER") is None
    assert not base.covers("tennis", "handicap_games_won_set1")
    assert wide.p(999, "handicap_games", 0, -3.5, "OVER") is None  # never wired


def test_the_handicap_curves_are_read_only_under_their_switch() -> None:
    old = {"0.700-0.750": {"n": 900, "realised": 0.74, "realised_lo95": 0.71}}
    cal = Calibration(
        pooled={}, by_market={"handicap_games_won_set1": old},
        pooled_by_sport={},
        by_market_direction={"handicap_games_won_set1|OVER": old,
                             "handicap_games|OVER": old},
        by_class={})
    before = tpc.for_day(cal, "2026-11-06", ON - timedelta(hours=1))
    assert before.by_market_direction["handicap_games_won_set1|OVER"] == old
    # a mixed day: a sheet priced before 17:30Z keeps the neighbours' curves
    unmarked = tpc.for_day(cal, "2026-11-06", ON + timedelta(hours=1),
                           handicap_rows=False)
    assert unmarked.by_market_direction["handicap_games_won_set1|OVER"] == old
    field, rule, _ = epochs.TENNIS_HANDICAP_POINT_MODEL_MARKER
    assert tpc.handicap_rows_marked([{"sport": "tennis", field: rule},
                                     {"sport": "football"}])
    assert not tpc.handicap_rows_marked([{"sport": "tennis", field: rule},
                                         {"sport": "tennis"}])
    assert tpc.handicap_rows_marked([])
    mixed = tpc.for_day(cal, "2026-11-06", ON + timedelta(minutes=1))
    on = tpc.for_day(cal, "2026-11-07", ON + timedelta(hours=8))
    assert mixed.by_market_direction == on.by_market_direction
    doc = json.loads(config_path(tpc.HANDICAP_FILE).read_text(encoding="utf-8"))
    assert (on.by_market_direction["handicap_games_won_set1|OVER"]
            == doc["by_market_direction"]["handicap_games_won_set1|OVER"])
    assert "handicap_games_won_set1" in on.no_pool_keys
    # the full-match handicap keeps its installed curve
    assert on.by_market_direction["handicap_games|OVER"] == old
    keys = {k.partition("|")[0] for sec in ("by_market", "by_market_direction",
                                             "thin_by_market_direction")
            for k in doc.get(sec) or {}}
    assert keys == set(epochs.TENNIS_HANDICAP_POINT_MODEL_MARKETS)


def test_handicap_evidence_reads_backfill_then_own_p_from_its_own_day() -> None:
    row = {"sport": "tennis", "market": "handicap_games_won_set1",
           "sofascore_event_id": 5, "subject": "A B", "line": -1.5,
           "direction": "OVER", "p_central": 0.66}
    key = tpc.backfill_key("2026-11-06", 5, "handicap_games_won_set1", "A B",
                           -1.5, "OVER")
    at = ON + timedelta(hours=7)
    assert tpc.evidence_p_for(row, "2026-11-06", {key: 0.58}, "2026-11-07",
                              at) == (True, 0.58)
    # 11-06 is mixed (rows priced by the neighbours before 17:30Z, settled
    # rows carry no marker): backfill only, never the row's own p
    assert tpc.evidence_p_for(row, "2026-11-06", {}, "2026-11-07", at) == (
        True, None)
    assert tpc.evidence_p_for(row, "2026-11-07", {}, "2026-11-08",
                              at + timedelta(days=1)) == (True, 0.66)
    # a day the handicap switch is off reads the handicap as out of scope
    assert tpc.evidence_p_for(row, "2026-11-05", {key: 0.58}, "2026-11-06",
                              ON - timedelta(hours=17)) == (False, None)
    base = {**row, "market": "aces_total", "subject": ""}
    assert tpc.evidence_p_for(base, "2026-11-06", {}, "2026-11-07", at) == (
        True, 0.66)


def test_the_handicap_sheet_marker_and_the_rebuild(
        monkeypatch: pytest.MonkeyPatch) -> None:
    field, rule, sport = epochs.TENNIS_HANDICAP_POINT_MODEL_MARKER
    assert (field, rule, sport) == ("tennis_handicap_point_model_rule",
                                    epochs.TENNIS_HANDICAP_POINT_MODEL, "tennis")
    assert field in AUDIT_MARKER_FIELDS
    assert epochs.TENNIS_HANDICAP_POINT_MODEL_MARKER in rp.AUDIT_MARKERS
    for name in ("TENNIS_MATCH_WINNER_FROM_UTC", "FOOTBALL_SIM_FROM_UTC",
                 "FOOTBALL_FORM_TABLE_FROM_UTC"):
        if hasattr(epochs, name):
            monkeypatch.setattr(epochs, name, None)
    limit = timedelta(minutes=45)
    stale = rp.DayState("2026-11-07", ON + timedelta(hours=8), limit,
                        sheet_tennis_handicap_point_model=False)
    assert "SHEET" in rp.build_plan(stale).names()
    fresh = rp.DayState("2026-11-07", ON + timedelta(hours=8), limit)
    assert "SHEET" not in rp.build_plan(fresh).names()
    before = rp.DayState("2026-11-06", ON - timedelta(hours=8), limit,
                         sheet_tennis_handicap_point_model=False)
    assert "SHEET" not in rp.build_plan(before).names()
    # the mixed day: a rebuild after 17:30Z re-prices the morning's sheet
    mixed = rp.DayState("2026-11-06", ON + timedelta(minutes=5), limit,
                        sheet_tennis_handicap_point_model=False)
    assert "SHEET" in rp.build_plan(mixed).names()


# --- the per-set handicap on the derived path (run_sheet -> derived) ------


@dataclass
class _FixedPricer(tps.PointPricer):
    value: float | None = None

    def p(self, event_id: int, market: str, side: int | None, line: float,
          direction: str) -> float | None:
        if market not in self.markets or direction != "OVER" or side is None:
            return None
        return None if self.value is None else self.value + 0.1 * side


def _derived(pricer: tps.PointPricer, point_markets: frozenset[str]) -> tuple[
        list[Any], list[Any]]:
    from bet.sofa.derived import price_derived_rungs
    from scripts.sofa.run_sheet import _point_model_rating_p
    from tests.sofa.test_review_1027_r2_tennis_set_handicap import (
        _fixture,
        _offer,
        _samples,
    )
    return price_derived_rungs(
        fixture=_fixture(), samples=_samples(), offer=_offer(),
        correlations={}, vetoes=[], min_sample=5, max_ladder_sigma=1.5,
        k_price=10.0, unfitted=[],
        rating_p=_point_model_rating_p(pricer, 1, None), stats_only=True,
        point_markets=point_markets)


def test_the_derived_set_handicap_rows_read_the_point_model() -> None:
    scope = epochs.TENNIS_HANDICAP_POINT_MODEL_MARKETS
    pricer = _FixedPricer(forecasts={}, markets=tps.MARKETS | scope,
                          value=0.6)
    rows, _ = _derived(pricer, scope & pricer.markets)
    by_subject = {r.subject: r for r in rows}
    assert by_subject["lloyd harris"].p_central == 0.6
    assert by_subject["juncheng shang"].p_central == 0.7
    for r in rows:
        assert any(n.startswith("TENNIS_POINT_MODEL: p") for n in r.notes)
        assert not any("W_TENNIS_RATING" in n for n in r.notes)


def test_no_point_model_p_is_refused_never_the_joint() -> None:
    scope = epochs.TENNIS_HANDICAP_POINT_MODEL_MARKETS
    pricer = _FixedPricer(forecasts={}, markets=tps.MARKETS | scope)
    rows, skipped = _derived(pricer, scope)
    assert rows == []
    assert {reason.value for _, reason, _ in skipped} == {"NOT_RATED"}


def test_off_the_derived_rows_are_untouched_by_the_point_pricer() -> None:
    # the switch off: the pricer's scope lacks the handicap, nothing changes
    pricer = _FixedPricer(forecasts={}, markets=tps.MARKETS, value=0.6)
    from bet.sofa.derived import price_derived_rungs
    from tests.sofa.test_review_1027_r2_tennis_set_handicap import (
        _fixture,
        _offer,
        _samples,
    )
    old, _ = price_derived_rungs(
        fixture=_fixture(), samples=_samples(), offer=_offer(),
        correlations={}, vetoes=[], min_sample=5, max_ladder_sigma=1.5,
        k_price=10.0, unfitted=[], rating_p=None, stats_only=True)
    new, _ = _derived(pricer, frozenset())
    assert [r.model_dump() for r in new] == [r.model_dump() for r in old]
