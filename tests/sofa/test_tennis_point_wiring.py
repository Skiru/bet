"""epochs.TENNIS_POINT_MODEL (operator 2026-11-05, from 2026-11-06 00:00Z):
the per-set games and serve-count rows of tennis are priced by the bottom-up
point model (bet.sofa.tennis_point_sheet), read their own history curves
(bet.sofa.tennis_point_curves, config/sofa_tennis_point_curves.json) only
under the switch, and the sheet carries a marker so a rebuild re-runs SHEET.
Offline: a hand-built history, no DB."""

from __future__ import annotations

import dataclasses
import gzip
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from bet.sofa import epochs
from bet.sofa import rebuild_plan as rp
from bet.sofa import tennis_point_curves as tpc
from bet.sofa import tennis_point_sheet as tps
from bet.sofa.confidence import Calibration
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import (
    FixtureOffer,
    FixtureSamples,
    MetricSample,
    Observation,
    PricedRung,
)
from bet.sofa.tennis_point_model import PointMatch, SideServe
from scripts.sofa.run_sheet import (
    AUDIT_MARKER_FIELDS,
    process_fixture,
    sheet_row_json,
    stamp_marker,
)
from tests.sofa.test_player_markets import dataclasses_replace_tennis

ON = datetime(2026, 11, 6, 0, 0, tzinfo=UTC)
SCOPE = {
    "games_set1_total", "games_set2_total",
    "aces_for", "aces_total", "aces_set1_for", "aces_set1_total",
    "aces_set2_for", "aces_set2_total",
    "double_faults_for", "double_faults_total", "double_faults_set1_for",
    "double_faults_set1_total", "double_faults_set2_for",
    "double_faults_set2_total",
    "serve_points_for", "serve_points_total", "serve_points_set1_for",
    "serve_points_set1_total", "serve_points_set2_for",
    "serve_points_set2_total",
}


def test_the_switch_is_from_the_next_day_and_by_the_build_clock() -> None:
    assert epochs.TENNIS_POINT_MODEL_FROM_UTC == ON
    assert not epochs.tennis_point_model("2026-11-05", ON + timedelta(hours=5))
    assert not epochs.tennis_point_model("2026-11-06", ON - timedelta(minutes=1))
    assert epochs.tennis_point_model("2026-11-06", ON)
    assert epochs.tennis_point_model("2026-11-07", ON + timedelta(days=1))


def test_the_scope_is_exactly_the_measured_families() -> None:
    assert epochs.TENNIS_POINT_MODEL_MARKETS == SCOPE
    # measured NOT better (games_total / games_won_for) or not better than
    # today's estimator (sets_total): never in scope
    for market in ("games_total", "games_won_for", "sets_total",
                   "tiebreaks_total", "games_set3_total"):
        assert market not in epochs.TENNIS_POINT_MODEL_MARKETS
    assert tps.in_scope("tennis", "aces_total")
    assert not tps.in_scope("football", "aces_total")


# --------------------------------------------------------------------------
# The as-of forecast and the pricer
# --------------------------------------------------------------------------


def _match(eid: int, ts: int, home: int, away: int, won: int = 60,
           aces: int = 5) -> PointMatch:
    serve = SideServe(played=90, won=won, aces=aces, dfs=3,
                      set_aces=(aces // 2, aces - aces // 2, None),
                      set_dfs=(1, 2, None))
    return PointMatch(
        event_id=eid, ts=ts, tier="TOUR", surface="hard", female=False,
        tournament=7, home_id=home, away_id=away, home_won=True,
        sets=((6, 4), (6, 4)), completed=True, best_of=3,
        match_tiebreak_decider=False, home=serve,
        away=SideServe(played=80, won=45, aces=2, dfs=4,
                       set_aces=(1, 1, None), set_dfs=(2, 2, None)))


def _history() -> list[PointMatch]:
    return [_match(100 + i, 1_000_000 + i * 86400, 1, 3 + (i % 3))
            for i in range(30)]


def _fixture_match(ts: int) -> PointMatch:
    m = tps.fixture_match(999, datetime.fromtimestamp(ts, UTC), 1, 2,
                          "ATP", "Hardcourt outdoor", 7, 3, {1: False})
    assert m is not None
    return m


def test_a_fixture_is_forecast_from_the_matches_before_its_start_only() -> None:
    hist = _history()
    start = hist[10].ts
    before = tps.forecast_fixtures(hist, [_fixture_match(start)])[999]
    # a different future cannot move the forecast
    future = [*hist[:10], *[dataclasses.replace(m, home=None, away=None,
                                                 sets=((0, 6), (0, 6)))
                            for m in hist[10:]]]
    assert tps.forecast_fixtures(future, [_fixture_match(start)])[999] == before
    # the past does
    later = tps.forecast_fixtures(hist, [_fixture_match(hist[-1].ts + 1)])[999]
    assert later.home.serve_points_seen > before.home.serve_points_seen


def test_best_of_five_or_no_ids_is_not_priced_and_gender_is_either_side() -> None:
    kick = datetime(2026, 11, 6, 12, tzinfo=UTC)
    assert tps.fixture_match(1, kick, 1, 2, "ATP", None, 7, 5, {}) is None
    assert tps.fixture_match(1, kick, None, 2, "ATP", None, 7, 3, {}) is None
    # an unstated format is not guessed as best of three (audit 2026-11-07)
    assert tps.fixture_match(1, kick, 1, 2, "WTA", "Clay", 7, None, {2: True}) is None
    m = tps.fixture_match(1, kick, 1, 2, "WTA", "Clay", 7, 3, {2: True})
    assert m is not None and m.female and m.surface == "clay"
    assert not m.completed  # the fixture teaches nothing


def test_pricer_directions_complement_and_integer_lines_push() -> None:
    hist = _history()
    pricer = tps.PointPricer(
        tps.forecast_fixtures(hist, [_fixture_match(hist[-1].ts + 1)]), sims=2000)
    for market, side in (("aces_total", None), ("aces_for", 0),
                         ("games_set1_total", None), ("serve_points_set2_for", 1)):
        over = pricer.p(999, market, side, 8.5, "OVER")
        under = pricer.p(999, market, side, 8.5, "UNDER")
        assert over is not None and under is not None
        assert over + under == pytest.approx(1.0)
        o_int = pricer.p(999, market, side, 8.0, "OVER")
        u_int = pricer.p(999, market, side, 8.0, "UNDER")
        assert o_int is not None and u_int is not None
        assert o_int + u_int <= 1.0 + 1e-9  # the push on 8 wins neither
    assert pricer.p(999, "games_total", None, 20.5, "OVER") is None  # out of scope
    assert pricer.p(12345, "aces_total", None, 8.5, "OVER") is None  # no forecast
    centre = pricer.centre(999, "aces_total", None)
    assert centre is not None and centre[0] > 0 and centre[1] > 0
    # seeded by the event id: the same p on a re-run
    again = tps.PointPricer(pricer.forecasts, sims=2000)
    assert again.p(999, "aces_total", None, 8.5, "OVER") == pricer.p(
        999, "aces_total", None, 8.5, "OVER")


# --------------------------------------------------------------------------
# SHEET
# --------------------------------------------------------------------------


def _samples() -> FixtureSamples:
    def obs(values: list[float], start: int) -> list[Observation]:
        return [Observation(sofascore_event_id=start + i,
                            match_date_utc=datetime(2026, 9, 1 + i, tzinfo=UTC),
                            opponent=f"O{i}", value=v, competition_id=1,
                            season_id=1, venue=None, opponent_id=9000 + i)
                for i, v in enumerate(values)]

    def ms(metric: str, a: list[float], b: list[float]) -> MetricSample:
        return MetricSample(metric=metric, side_a=obs(a, 100), side_b=obs(b, 200),
                            h2h=[])
    return FixtureSamples(
        sofascore_event_id=1, readiness="READY", gaps=[],
        metrics={
            "aces_for": ms("aces_for", [4.0] * 10, [3.0] * 10),
            "aces_total": ms("aces_total", [7.0] * 10, [8.0] * 10),
            "games_total": ms("games_total", [21.0, 23.0] * 5, [22.0, 20.0] * 5),
        })


def _offer() -> FixtureOffer:
    fetched = datetime(2026, 9, 22, 20, tzinfo=UTC)
    return FixtureOffer(sofascore_event_id=1, status="PRICED", unmapped_markets=[],
                        rungs=[PricedRung(market=m, subject=s, line=line,
                                          over_odds=1.85, under_odds=1.85,
                                          fetched_at_utc=fetched)
                               for m, s, line in (("aces_for", "Kenta Kawada", 3.5),
                                                  ("aces_total", "", 9.5),
                                                  ("games_total", "", 21.5))])


def _sheet(pricer: tps.PointPricer | None) -> dict[tuple[str, str], dict[str, object]]:
    kwargs = {} if pricer is None else {"point_pricer": pricer}
    rows, _ = process_fixture(
        dataclasses_replace_tennis(), _samples(), _offer(),
        baselines={}, reliability={}, engine_constants={}, vetoes=[],
        config=SofaConfig(), stats_only=True,
        **kwargs,  # type: ignore[arg-type]
    )
    return {(r.market, r.direction): sheet_row_json(r) for r in rows}


def _pricer() -> tps.PointPricer:
    hist = [dataclasses.replace(m, home_id=1 if i % 2 else 2, away_id=50 + i)
            for i, m in enumerate(_history())]
    fx = tps.fixture_match(1, datetime(2026, 9, 23, tzinfo=UTC), 1, 2,
                           "ITF Men", "Hardcourt outdoor", 1, 3, {})
    assert fx is not None
    return tps.PointPricer(tps.forecast_fixtures(hist, [fx]), sims=2000)


def test_sheet_prices_in_scope_rows_from_the_model_and_leaves_the_rest() -> None:
    off = _sheet(None)
    pricer = _pricer()
    on = _sheet(pricer)
    assert set(on) == set(off)
    # out of scope: byte for byte
    for key in (("games_total", "OVER"), ("games_total", "UNDER")):
        assert on[key] == off[key]
    for market, side, line in (("aces_for", 0, 3.5), ("aces_total", None, 9.5)):
        for direction in ("OVER", "UNDER"):
            row = on[(market, direction)]
            expected = pricer.p(1, market, side, line, direction)
            assert expected is not None
            assert row["p_central"] == round(expected, 4)
            centre = pricer.centre(1, market, side)
            assert centre is not None and row["centre"] == round(centre[0], 4)
            notes = row.get("notes") or []
            assert isinstance(notes, list)
            assert any(str(n).startswith(tps.NOTE) for n in notes)
    key = ("aces_total", "OVER")
    assert on[key]["p_central"] != off[key]["p_central"]


def test_sheet_refuses_an_in_scope_row_the_model_cannot_price() -> None:
    empty = tps.PointPricer({})
    rows, skipped = process_fixture(
        dataclasses_replace_tennis(), _samples(), _offer(),
        baselines={}, reliability={}, engine_constants={}, vetoes=[],
        config=SofaConfig(), stats_only=True, point_pricer=empty)
    assert {r.market for r in rows} == {"games_total"}
    assert {str(reason) for _, reason, _ in skipped} >= {"NOT_RATED"}


def test_the_sheet_marker_and_the_rebuild(monkeypatch: pytest.MonkeyPatch) -> None:
    field, rule, sport = epochs.TENNIS_POINT_MODEL_MARKER
    assert (field, rule, sport) == ("tennis_point_model_rule",
                                    epochs.TENNIS_POINT_MODEL, "tennis")
    assert field in AUDIT_MARKER_FIELDS
    assert epochs.TENNIS_POINT_MODEL_MARKER in rp.AUDIT_MARKERS
    rows, _ = process_fixture(
        dataclasses_replace_tennis(), _samples(), _offer(),
        baselines={}, reliability={}, engine_constants={}, vetoes=[],
        config=SofaConfig(), stats_only=True)
    stamped = [sheet_row_json(r) for r in stamp_marker(
        rows, epochs.TENNIS_POINT_MODEL_MARKER, True)]
    assert epochs.sheet_has_marker(stamped, epochs.TENNIS_POINT_MODEL_MARKER)
    plain = [sheet_row_json(r) for r in rows]
    assert all(field not in r for r in plain)  # absent when off
    assert not epochs.sheet_has_marker(plain, epochs.TENNIS_POINT_MODEL_MARKER)
    # rebuild_plan re-runs SHEET on a sheet built before the switch
    monkeypatch.setattr(epochs, "TENNIS_MATCH_WINNER_FROM_UTC", None)
    limit = timedelta(minutes=45)
    stale = rp.DayState("2026-11-06", ON + timedelta(hours=8), limit,
                        sheet_tennis_point_model=False)
    assert "SHEET" in rp.build_plan(stale).names()
    fresh = rp.DayState("2026-11-06", ON + timedelta(hours=8), limit)
    assert "SHEET" not in rp.build_plan(fresh).names()
    before = rp.DayState("2026-11-05", ON + timedelta(hours=8), limit,
                         sheet_tennis_point_model=False)
    assert "SHEET" not in rp.build_plan(before).names()


# --------------------------------------------------------------------------
# CONFIDENCE: the keys' own curves, only under the switch
# --------------------------------------------------------------------------

OLD = {"0.700-0.750": {"n": 900, "realised": 0.74, "realised_lo95": 0.71}}
NEW = {"0.750-0.800": {"n": 1200, "realised": 0.77, "realised_lo95": 0.745}}


def _cal() -> Calibration:
    return Calibration(
        pooled={},
        by_market={"aces_total": OLD, "games_total": OLD},
        pooled_by_sport={"tennis": {"0.600-0.700": {"n": 9000, "realised": 0.66,
                                                     "realised_lo95": 0.65},
                                    "0.700-0.750": {"n": 9000, "realised": 0.74,
                                                    "realised_lo95": 0.73}}},
        by_market_direction={"aces_total|OVER": OLD, "games_total|OVER": OLD},
        by_class={"tennis_women": {"by_market": {"aces_total": OLD},
                                   "by_market_direction": {"aces_total|OVER": OLD},
                                   "pooled_by_sport": {}}},
    )


def _curves(tmp_path: Path) -> Path:
    path = tmp_path / tpc.FILE
    path.write_text(json.dumps({
        "by_market": {"aces_total": NEW},
        "by_market_direction": {"aces_total|OVER": NEW, "games_total|OVER": NEW},
        "thin_by_market_direction": {},
        "by_class": {"tennis_women": {"by_market_direction": {"aces_total|OVER": NEW}}},
    }), encoding="utf-8")
    return path


def test_curves_are_read_only_under_the_switch(tmp_path: Path) -> None:
    cal, path = _cal(), _curves(tmp_path)
    off = tpc.for_day(cal, "2026-11-05", ON + timedelta(hours=3), path)
    assert off is cal
    on = tpc.for_day(cal, "2026-11-06", ON + timedelta(hours=3), path)
    # the old curve of the key is gone, the file's is read
    assert on.realised("aces_total", 0.72, "tennis", "OVER") is None
    hit = on.realised("aces_total", 0.77, "tennis", "OVER")
    assert hit is not None and hit[0] == 0.745
    # no pool stands in for a hole in the key's own curve
    assert on.realised("aces_total", 0.65, "tennis", "UNDER") is None
    # an out-of-scope key is untouched (games_total is not the model's)
    assert on.realised("games_total", 0.72, "tennis", "OVER") == cal.realised(
        "games_total", 0.72, "tennis", "OVER")
    # the class reads the file's class section only
    w = on.realised("aces_total", 0.77, "tennis", "OVER", "tennis_women")
    assert w is not None and w[0] == 0.745
    assert on.realised("aces_total", 0.72, "tennis", "OVER", "tennis_women") is None
    # the installed calibration object is never modified
    assert cal.by_market["aces_total"] == OLD


def test_on_without_the_file_the_keys_have_no_curve(tmp_path: Path) -> None:
    on = tpc.for_day(_cal(), "2026-11-06", ON + timedelta(hours=3),
                     tmp_path / "absent.json")
    assert on.realised("aces_total", 0.72, "tennis", "OVER") is None
    assert on.realised("games_total", 0.72, "tennis", "OVER") is not None


def test_the_curves_are_not_stripped_as_live_only(tmp_path: Path) -> None:
    from bet.sofa import live_only_curves as loc
    stripped = loc.strip(_cal(), ["by_market:aces_total",
                                  "by_market_direction:aces_total|OVER"])
    on = tpc.for_day(stripped, "2026-11-06", ON + timedelta(hours=3), _curves(tmp_path))
    hit = on.realised("aces_total", 0.77, "tennis", "OVER")
    assert hit is not None and hit[0] == 0.745


def test_the_installed_file_if_present_holds_only_scope_keys() -> None:
    doc = tpc.load()
    if doc is None:
        pytest.skip("config/sofa_tennis_point_curves.json not installed")
    for name in tpc.SECTIONS:
        for key in doc.get(name) or {}:
            assert key.partition("|")[0] in epochs.TENNIS_POINT_MODEL_MARKETS
    for sec in (doc.get("by_class") or {}).values():
        for name in tpc.SECTIONS:
            for key in sec.get(name) or {}:
                assert key.partition("|")[0] in epochs.TENNIS_POINT_MODEL_MARKETS


# --------------------------------------------------------------------------
# Line evidence: a line is read at the point model's p or not at all
# --------------------------------------------------------------------------


def test_evidence_reads_the_backfilled_or_own_p_never_the_old_one(
        tmp_path: Path) -> None:
    row = {"sport": "tennis", "market": "aces_total", "sofascore_event_id": 5,
           "subject": "", "line": 9.5, "direction": "OVER", "p_central": 0.81}
    key = tpc.backfill_key("2026-11-01", 5, "aces_total", "", 9.5, "OVER")
    assert tpc.evidence_p(row, "2026-11-01", {key: 0.63}, "2026-11-06") == (True, 0.63)
    assert tpc.evidence_p(row, "2026-11-01", {}, "2026-11-06") == (True, None)
    assert tpc.evidence_p(row, "2026-11-07", {}, "2026-11-06") == (True, 0.81)
    other = {**row, "market": "games_total"}
    assert tpc.evidence_p(other, "2026-11-01", {}, "2026-11-06") == (False, None)
    path = tmp_path / "b.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump({key: 0.63}, fh)
    assert tpc.load_backfill(path) == {key: 0.63}
    assert tpc.load_backfill(tmp_path / "none.json.gz") == {}


def test_evidence_merge_replaces_only_the_point_models_keys() -> None:
    fitted = {
        "keys": {"tennis": {"aces_total|OVER": {"n": 1},
                            "tennis_women:aces_total|OVER": {"n": 2},
                            "games_total|OVER": {"n": 3}},
                 "football": {"aces_total|OVER": {"n": 9}}},
        "bands": {"tennis": {"aces_total|OVER": {"a": 1}, "*": {"b": 2},
                             "games_total|OVER": {"c": 3}}},
        "sport_printable": {"tennis": {"n": 100}},
    }
    point_fit = {
        "keys": {"tennis": {"aces_total|UNDER": {"n": 7},
                            "games_total|OVER": {"n": 99}}},
        "bands": {"tennis": {"aces_total|UNDER": {"z": 1}, "*": {"zz": 2}}},
        "sport_printable": {"tennis": {"n": 1}},
    }
    tpc.merge_evidence(fitted, point_fit)
    assert fitted["keys"]["tennis"] == {"aces_total|UNDER": {"n": 7},
                                        "games_total|OVER": {"n": 3}}
    assert fitted["keys"]["football"] == {"aces_total|OVER": {"n": 9}}
    assert fitted["bands"]["tennis"] == {"aces_total|UNDER": {"z": 1},
                                         "*": {"b": 2},
                                         "games_total|OVER": {"c": 3}}
    assert fitted["sport_printable"] == {"tennis": {"n": 100}}


def test_a_fixture_already_played_never_teaches_its_own_forecast() -> None:
    hist = _history()
    played = dataclasses.replace(hist[10], event_id=999, home_id=1, away_id=2)
    with_it = [*hist[:10], played, *hist[11:]]
    # the fixture's kickoff says later than the match really started
    late = _fixture_match(hist[12].ts)
    got = tps.forecast_fixtures(with_it, [late])[999]
    want = tps.forecast_fixtures(hist[:10], [_fixture_match(played.ts)])[999]
    assert got == want
