"""The rule markers of the audit 2026-10-13 SHEET switches and the fitted
config fingerprint (correctness fix, 2026-10-14): SHEET stamps them on its
rows, rebuild_plan re-runs SHEET on a sheet built before a switch went on
(on 2026-10-13 the 18:10Z switches left the morning sheet in place and SHEET
was re-run by hand), and names a sheet priced on other fitted constants.
Also the TENNIS_RATING note states what p_central is. Offline and fast."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import epochs, sheet_config
from bet.sofa import rebuild_plan as rp
from scripts.sofa import run_sheet
from tests.sofa.test_audit_2026_10_13_tennis import _sheet as tennis_sheet
from tests.sofa.test_run_sheet_wiring import _run

LIMIT = timedelta(minutes=45)
DAY = "2026-10-14"
AFTER = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)

FOOTBALL = (
    ("sheet_game_state", epochs.GAME_STATE_MARKER),
    ("sheet_rated_scope", epochs.FOOTBALL_RATED_SCOPE_MARKER),
    ("sheet_venue_prior", epochs.FOOTBALL_VENUE_PRIOR_MARKER),
    ("sheet_season_phase", epochs.SEASON_PHASE_MARKER),
    ("sheet_rating_weight", epochs.FOOTBALL_RATING_WEIGHT_MARKER),
)
ALL = (*FOOTBALL, ("sheet_tennis_set", epochs.TENNIS_SET_RATING_PRICES_MARKER))


# --- epochs: which rows a marker is read on ------------------------------------


def test_a_marker_is_read_only_on_its_own_sports_rows() -> None:
    field, rule, _sport = epochs.GAME_STATE_MARKER
    tennis = {"sport": "tennis"}
    assert epochs.sheet_has_marker([tennis], epochs.GAME_STATE_MARKER)
    assert epochs.sheet_has_marker([], epochs.GAME_STATE_MARKER)
    assert not epochs.sheet_has_marker(
        [tennis, {"sport": "football"}], epochs.GAME_STATE_MARKER)
    assert epochs.sheet_has_marker(
        [tennis, {"sport": "football", field: rule}], epochs.GAME_STATE_MARKER)
    field, rule, _sport = epochs.TENNIS_SET_RATING_PRICES_MARKER
    assert epochs.sheet_has_marker(
        [{"sport": "football"}], epochs.TENNIS_SET_RATING_PRICES_MARKER)
    assert not epochs.sheet_has_marker(
        [{"sport": "tennis", field: "old"}], epochs.TENNIS_SET_RATING_PRICES_MARKER)


# --- rebuild_plan ----------------------------------------------------------------


@pytest.mark.parametrize("attr, marker", ALL)
def test_a_sheet_without_a_switch_marker_is_re_run(attr: str, marker: Any) -> None:
    plan = rp.build_plan(rp.DayState(DAY, AFTER, LIMIT, **{attr: False}))
    assert "SHEET" in plan.names()
    sheet = next(s for s in plan.steps if s.name == "SHEET")
    assert "switch now on" in sheet.reason
    assert plan.names().index("SHEET") < plan.names().index("CONFIDENCE")
    assert "SHEET" not in rp.build_plan(rp.DayState(DAY, AFTER, LIMIT)).names()


@pytest.mark.parametrize("attr, marker", ALL)
def test_a_day_or_clock_before_the_switch_keeps_the_sheet(
    attr: str, marker: Any,
) -> None:
    # 10-12 is never re-priced under the 10-13 switches, and 10-13 before
    # 18:10Z keeps its morning sheet; after 18:10Z it is re-run (mixed day)
    for day, at in (("2026-10-12", AFTER),
                    ("2026-10-13", datetime(2026, 10, 13, 12, tzinfo=UTC))):
        assert "SHEET" not in rp.build_plan(
            rp.DayState(day, at, LIMIT, **{attr: False})).names()
    assert "SHEET" in rp.build_plan(rp.DayState(
        "2026-10-13", datetime(2026, 10, 13, 18, 30, tzinfo=UTC), LIMIT,
        **{attr: False})).names()


def test_the_tennis_set_marker_waits_for_the_rating_prices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # SHEET reads TENNIS_SET_RATING_PRICES only on top of the rating prices
    monkeypatch.setattr(epochs, "tennis_rating_prices", lambda d, at=None: False)
    assert "SHEET" not in rp.build_plan(
        rp.DayState(DAY, AFTER, LIMIT, sheet_tennis_set=False)).names()


def _write_day(runs: Path, rows: list[dict[str, Any]]) -> None:
    run = runs / DAY
    run.mkdir(parents=True)
    kickoff = "2026-10-14T18:00:00Z"
    (run / "02_fixtures.json").write_text(json.dumps([{
        "sofascore_event_id": 1, "sport": "tennis",
        "kickoff_utc": kickoff, "superbet_kickoff_utc": kickoff}]))
    (run / "04_offer.json").write_text(json.dumps([{
        "sofascore_event_id": 1, "status": "PRICED",
        "superbet_started_utc": None, "superbet_kickoff_seen_utc": kickoff,
        "rungs": [{"market": "games_total", "subject": "", "line": 20.5,
                   "over_odds": 1.9, "under_odds": 1.9,
                   "fetched_at_utc": "2026-10-14T08:55:00Z"}]}]))
    (run / "05_sheet.json").write_text(json.dumps(rows))
    (run / "sport_fixtures.json").write_text(json.dumps({"events": []}))
    (run / "06_coupon.json").write_text("{}")


def _rules() -> dict[str, str]:
    return {"epoch": epochs.STATS_ONLY, "link_rule": epochs.LINK_SHARED_LEAGUE,
            "dispersion_rule": epochs.COUNT_DISPERSION,
            "k_rule": epochs.PER_MARKET_K,
            "tennis_table_rule": epochs.TENNIS_SCOPED_TABLE}


def test_a_sheet_without_football_does_not_re_run_forever(tmp_path: Path) -> None:
    # the opponent_rule trap: football switches on, no football row to carry
    # their markers - nothing to re-price
    field, rule, _ = epochs.TENNIS_SET_RATING_PRICES_MARKER
    _write_day(tmp_path, [{"sport": "tennis", **_rules(), field: rule}])
    state = rp.observe(str(tmp_path), DAY, AFTER, LIMIT)
    assert all(getattr(state, attr) for attr, _m in ALL)
    assert "SHEET" not in rp.build_plan(state).names()


def test_a_tennis_row_without_its_marker_re_runs_sheet(tmp_path: Path) -> None:
    _write_day(tmp_path, [{"sport": "tennis", **_rules()}])
    state = rp.observe(str(tmp_path), DAY, AFTER, LIMIT)
    assert not state.sheet_tennis_set
    sheet = next(s for s in rp.build_plan(state).steps if s.name == "SHEET")
    assert "tennis_set_rating_prices" in sheet.reason


# --- the fitted config fingerprint ------------------------------------------------


def test_the_fingerprint_follows_every_fitted_file(tmp_path: Path) -> None:
    empty = sheet_config.fingerprint(tmp_path)
    assert len(empty) == sheet_config.DIGEST_CHARS
    seen = {empty}
    for name in sheet_config.SHEET_CONFIG_FILES:
        (tmp_path / name).write_text("{}")
        seen.add(sheet_config.fingerprint(tmp_path))
    assert len(seen) == len(sheet_config.SHEET_CONFIG_FILES) + 1
    assert sheet_config.fingerprint(tmp_path) == sheet_config.fingerprint(tmp_path)
    assert "sofa_confidence_calibration.json" not in sheet_config.SHEET_CONFIG_FILES


def test_other_constants_are_named_never_re_run() -> None:
    kept = rp.build_plan(rp.DayState(DAY, AFTER, LIMIT, sheet_config_sha="a" * 16,
                                     config_sha="b" * 16))
    assert "SHEET" not in kept.names()
    note = next(n for n in kept.notes if n.startswith("CONFIG_CHANGED"))
    assert "SHEET kept" in note
    rerun = rp.build_plan(rp.DayState(DAY, AFTER, LIMIT, sheet_game_state=False,
                                      sheet_config_sha="a" * 16, config_sha="b" * 16))
    assert "SHEET" in rerun.names()
    assert any("re-runs" in n for n in rerun.notes if n.startswith("CONFIG_CHANGED"))
    for sheet_sha in (None, "b" * 16):  # an unstamped sheet, the same config
        plan = rp.build_plan(rp.DayState(DAY, AFTER, LIMIT, sheet_config_sha=sheet_sha,
                                         config_sha="b" * 16))
        assert not any(n.startswith("CONFIG_CHANGED") for n in plan.notes)


def test_observe_reads_the_rows_fingerprint(tmp_path: Path) -> None:
    current = sheet_config.fingerprint()
    _write_day(tmp_path, [{"sport": "tennis", "config_sha": "x" * 16},
                          {"sport": "tennis", "config_sha": "x" * 16}])
    state = rp.observe(str(tmp_path), DAY, AFTER, LIMIT)
    assert state.sheet_config_sha == "x" * 16 and state.config_sha == current
    (tmp_path / DAY / "05_sheet.json").write_text(json.dumps(
        [{"sport": "tennis", "config_sha": "x" * 16}, {"sport": "tennis"}]))
    assert rp.observe(str(tmp_path), DAY, AFTER, LIMIT).sheet_config_sha == "mixed"


# --- SHEET stamps them --------------------------------------------------------------


SWITCHES = ("game_state_enabled", "football_rated_scope", "football_venue_prior",
            "season_phase_enabled", "football_rating_weight")


def _switches_on(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (*SWITCHES, "tennis_set_rating_prices"):
        monkeypatch.setattr(epochs, name, lambda d, at=None: True)
    for loader in ("load_game_state_table", "load_season_phase_table",
                   "load_rating_weight_table"):
        monkeypatch.setattr(run_sheet, loader, lambda: object())


def test_sheet_stamps_each_switch_on_its_own_sports_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _switches_on(monkeypatch)
    rc, _h, rows = _run(tmp_path, monkeypatch, on=set(), rating_prices=True)
    assert rc == 0
    by_sport = {r["sport"]: r for r in rows}
    for _attr, (field, rule, sport) in ALL:
        assert by_sport[sport][field] == rule
        other = "tennis" if sport == "football" else "football"
        assert field not in by_sport[other]
    assert all(epochs.sheet_has_marker(rows, m) for _a, m in ALL)
    assert {r["config_sha"] for r in rows} == {sheet_config.fingerprint()}


def test_sheet_with_the_switches_off_carries_no_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    rc, _h, rows = _run(tmp_path, monkeypatch, on=set(), rating_prices=True)
    assert rc == 0
    fields = {m[0] for _a, m in ALL}
    for row in rows:
        assert not fields & set(row)
        assert row["config_sha"] == sheet_config.fingerprint()


def test_the_set_marker_needs_the_rating_prices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _switches_on(monkeypatch)
    _rc, _h, rows = _run(tmp_path, monkeypatch, on=set(), rating_prices=False)
    tennis = next(r for r in rows if r["sport"] == "tennis")
    assert "tennis_set_rule" not in tennis


# --- the TENNIS_RATING note -------------------------------------------------------


def _rating_notes(rows: list[dict[str, Any]], market: str) -> list[str]:
    return [n for r in rows if r["market"] == market
            for n in r["notes"] if str(n).startswith("TENNIS_RATING")]


@pytest.mark.parametrize("market, rule", [
    ("games_won_for", "epochs.TENNIS_RATING_PRICES"),
    ("games_won_set1_for", "epochs.TENNIS_SET_RATING_PRICES"),
])
def test_a_rating_alone_row_says_so_not_blended(market: str, rule: str) -> None:
    rows = tennis_sheet(True)  # priced rungs, stats-only
    notes = _rating_notes(rows, market)
    assert notes
    for note in notes:
        assert "blended" not in note
        assert f"p_central is the rating alone, no price ({rule})" in note
    for r in rows:
        if r["market"] == market:
            assert r["p_central"] == pytest.approx(r["forecast_p"], abs=1e-4)


def test_the_old_rule_note_still_names_the_blend() -> None:
    class Forecast:
        neighbours_home = (1, 2)
        rated_home = rated_away = 5

        def p_side_wins(self, side: str) -> float:
            return 0.6

    blended = run_sheet.rating_note(Forecast(), "side_a", 0.7, 0.5)  # type: ignore[arg-type]
    assert "blended 0.25 with market_p 0.5000 (W_TENNIS_RATING);" in blended
    alone = run_sheet.rating_note(Forecast(), "side_a", 0.7, None)  # type: ignore[arg-type]
    assert "no price on this rung, rating alone (W_TENNIS_RATING);" in alone
