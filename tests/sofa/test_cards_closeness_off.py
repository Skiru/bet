"""The cards markets out of the closeness stretch (epochs.CARDS_CLOSENESS_OFF,
from 2026-11-10 00:00Z; docs/sofa/evidence/kartki_bez_closeness_2026-11-09.md):
the day's table (closeness_stretch.for_day) drops cards_points_for /
cards_points_total, shots keep the term; the card halves read the full-match
term through run_sheet.card_half_term_mults; the row marker, rebuild_plan's
re-run, the replay flag and the install guard. Offline and fast."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import closeness_stretch as cls
from bet.sofa import epochs
from bet.sofa import rebuild_plan as rp
from scripts.sofa import calibrate_from_cache as cfc
from scripts.sofa import prepare_refit as pr
from scripts.sofa import run_sheet
from tests.sofa.test_closeness_stretch import TABLE
from tests.sofa.test_prepare_refit import _db, _fake_calibrate, _paths
from tests.sofa.test_run_sheet_wiring import _run

LIMIT = rp.timedelta(minutes=45)
DAY = "2026-11-10"
AFTER = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
CARDS = ("cards_points_for", "cards_points_total")
SHOTS = ("shots_total", "shots_1h_total")


def test_the_switch_reads_the_day_and_the_clock(
        monkeypatch: pytest.MonkeyPatch) -> None:
    assert epochs.CARDS_CLOSENESS_OFF_FROM_UTC == datetime(2026, 11, 10, tzinfo=UTC)
    assert epochs.CARDS_CLOSENESS_OFF_MARKETS == frozenset(CARDS)
    assert epochs.CARDS_CLOSENESS_OFF_MARKER == (
        "cards_closeness_rule", "cards_closeness_off_v1", "football")
    assert epochs.cards_closeness_off(DAY, AFTER)
    # never into the built day before it, nor before its clock
    assert not epochs.cards_closeness_off(
        "2026-11-09", datetime(2026, 11, 9, 23, 59, tzinfo=UTC))
    assert not epochs.cards_closeness_off(
        DAY, datetime(2026, 11, 9, 23, 59, tzinfo=UTC))
    monkeypatch.setattr(epochs, "CARDS_CLOSENESS_OFF_FROM_UTC", None)
    assert not epochs.cards_closeness_off(
        "2027-01-01", datetime(2027, 1, 1, tzinfo=UTC))


def test_the_day_table_drops_the_cards_and_keeps_the_shots() -> None:
    s = 1.8
    before = cls.for_day(TABLE, "2026-11-09", datetime(2026, 11, 9, 20, tzinfo=UTC))
    assert before is TABLE
    for market in (*CARDS, *SHOTS):
        assert before.multiplier(market, s) is not None
    day = cls.for_day(TABLE, DAY, AFTER)
    for market in CARDS:
        assert day.multiplier(market, s) is None
    for market in SHOTS:
        assert day.multiplier(market, s) == pytest.approx(TABLE.multiplier(market, s))
    assert day.path == TABLE.path
    # the installed table is never mutated
    assert all(TABLE.multiplier(m, s) is not None for m in CARDS)


def test_the_card_halves_lose_the_full_match_term() -> None:
    class _Forecast:
        def supremacy(self, side: str) -> float:
            return 1.9 if side == "side_a" else -1.9

    fc: Any = _Forecast()
    on = run_sheet.card_half_term_mults(fc, None, None, None, TABLE)
    off = run_sheet.card_half_term_mults(
        fc, None, None, None, cls.for_day(TABLE, DAY, AFTER))
    mult = TABLE.multiplier("cards_points_for", cls.supremacy(fc))
    assert mult is not None and mult < 1.0
    assert on["side_a"][0] == pytest.approx(mult)
    assert off["side_a"][0] == pytest.approx(1.0)
    assert "closeness off" in off["side_a"][1]


def test_sheet_reads_the_day_table_and_stamps_the_marker(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    field, rule, _sport = epochs.CARDS_CLOSENESS_OFF_MARKER
    monkeypatch.setattr(epochs, "football_closeness_stretch",
                        lambda d, at=None: True)
    monkeypatch.setattr(run_sheet, "load_closeness_stretch_table", lambda: TABLE)
    rc, h, rows = _run(tmp_path / "before", monkeypatch, on=set(),
                       rating_prices=True)
    assert rc == 0 and rows
    assert not any(field in r for r in rows)
    assert all(c["closeness_stretch"] is TABLE for c in h.process_calls)
    monkeypatch.setattr(epochs, "cards_closeness_off", lambda d, at=None: True)
    rc, h, rows = _run(tmp_path / "on", monkeypatch, on=set(), rating_prices=True)
    assert rc == 0
    for call in h.process_calls:
        table = call["closeness_stretch"]
        assert table is not None
        assert all(table.multiplier(m, 1.5) is None for m in CARDS)
        assert all(table.multiplier(m, 1.5) is not None for m in SHOTS)
    by_sport = {r["sport"]: r for r in rows}
    assert by_sport["football"][field] == rule
    assert field not in by_sport["tennis"]
    assert epochs.sheet_has_marker(rows, epochs.CARDS_CLOSENESS_OFF_MARKER)
    assert field in run_sheet.AUDIT_MARKER_FIELDS
    assert epochs.CARDS_CLOSENESS_OFF_MARKER in rp.AUDIT_MARKERS


def test_rebuild_plan_re_runs_sheet_on_a_missing_marker() -> None:
    stale = rp.DayState(DAY, AFTER, LIMIT, sheet_cards_closeness_off=False)
    plan = rp.build_plan(stale)
    assert "SHEET" in plan.names()
    sheet = next(s for s in plan.steps if s.name == "SHEET")
    assert "cards_closeness_off" in sheet.reason
    assert "SHEET" not in rp.build_plan(rp.DayState(DAY, AFTER, LIMIT)).names()
    # the day before the switch: a sheet without the marker is not stale
    assert "SHEET" not in rp.build_plan(rp.DayState(
        "2026-11-09", datetime(2026, 11, 9, 20, tzinfo=UTC), LIMIT,
        sheet_cards_closeness_off=False)).names()


def test_the_replay_drops_the_cards_under_its_flag(
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    assert cfc.cards_out_of_closeness(TABLE, False) is TABLE
    out = cfc.cards_out_of_closeness(TABLE, True)
    assert all(out.multiplier(m, 1.5) is None for m in CARDS)
    rules = cfc.CentreRules(football_rating=True, closeness_stretch=out)
    assert rules.describe()["cards_closeness_off"] is True
    assert cfc.CentreRules(football_rating=True, closeness_stretch=TABLE
                           ).describe()["cards_closeness_off"] is False
    monkeypatch.setattr(sys, "argv", ["calibrate_from_cache.py", "--football-rating",
                                      "--cards-closeness-off"])
    with pytest.raises(SystemExit):
        cfc.main()
    assert "--cards-closeness-off needs --closeness-stretch" in capsys.readouterr().err


def test_prepare_refit_passes_the_flag_and_install_requires_it(
        tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _db(paths.db_path)
    seen: list[list[str]] = []
    inner = _fake_calibrate(paths.db_path)

    def runner(cmd: Sequence[str], env: dict[str, str], log: Path | None
               ) -> tuple[int, list[str]]:
        seen.append(list(cmd))
        return inner(cmd, env, log)

    with pytest.raises(pr.RefitError, match="needs --closeness-stretch"):
        pr.rebuild_cache_rows(paths, dry_run=False, confirm=True, runner=runner,
                              require_db_backup=False, football_rating=True,
                              cards_closeness_off=True)
    (paths.config_dir / cls.CONFIG_FILE).write_text(
        '{"markets": {"shots_total": {"g1": 0.015, "g2": 0.0}}}')
    report: dict[str, Any] = pr.rebuild_cache_rows(
        paths, dry_run=False, confirm=True, runner=runner,
        require_db_backup=False, football_rating=True, closeness_stretch=True,
        cards_closeness_off=True)
    assert "--cards-closeness-off" in seen[-1]
    assert report["cards_closeness_off"] is True
    rules = pr.read_replay_rules(paths)
    assert rules is not None and rules["flags"]["cards_closeness_off"] is True
    args = pr.build_parser().parse_args(
        ["--date", DAY, "rebuild-cache-rows", "--closeness-stretch",
         "--cards-closeness-off"])
    assert args.cards_closeness_off is True
    assert ("CARDS_CLOSENESS_OFF", epochs.cards_closeness_off,
            "cards_closeness_off") in pr.REPLAYABLE_SWITCHES
