"""The football closeness stretch (epochs.FOOTBALL_CLOSENESS_STRETCH, off
while None; bet.sofa.closeness_stretch over bet.sofa.supremacy_stretch): a
count centre of CLOSENESS_MARKETS x exp(g1 |s| + g2 s^2), s the home side's
expected goal difference, after GAME_STATE and the count stretch, in SHEET
and in the cache replay, with its row marker, rebuild_plan's re-run, the
replay flag, the config and the fit. Offline and fast."""

from __future__ import annotations

import json
import math
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import closeness_stretch as cls
from bet.sofa import epochs, sheet_config
from bet.sofa import football_rating as fr
from bet.sofa import rebuild_plan as rp
from bet.sofa.config import config_path
from bet.sofa.game_state import MAX_SUPREMACY, GameStateTable
from scripts.sofa import calibrate_from_cache as cfc
from scripts.sofa import fit_closeness_stretch as fit
from scripts.sofa import prepare_refit as pr
from scripts.sofa import run_sheet
from scripts.sofa.calibrate_from_cache import (
    CentreRules,
    FootballRatingReplay,
    live_centre,
)
from scripts.sofa.fit_count_stretch import StretchRow
from tests.sofa.test_audit_2026_10_13_b1b2 import _book
from tests.sofa.test_audit_2026_10_13_replay import _football
from tests.sofa.test_count_stretch import _over, _rows
from tests.sofa.test_prepare_refit import _db, _fake_calibrate, _paths
from tests.sofa.test_run_sheet_wiring import _run

# the 2026-10-21 measurement's coefficients (fit 2026-01-01..10-20)
MEASURED: dict[str, dict[str, float]] = {
    "cards_points_for": {"g1": 0.017019, "g2": -0.052625},
    "cards_points_total": {"g1": 0.017664, "g2": -0.049219},
    "shots_total": {"g1": 0.014714, "g2": 0.0},
    "shots_1h_total": {"g1": 0.016324, "g2": 0.0},
}
TABLE = cls.parse_table({"markets": MEASURED})
LIMIT = rp.timedelta(minutes=45)
DAY = "2026-10-22"
AFTER = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)


# --- the switch, the markets, the file --------------------------------------


def test_the_switch_is_off_and_reads_the_day_and_the_clock(
        monkeypatch: pytest.MonkeyPatch) -> None:
    # switched on 2026-10-21 00:00Z (night 2026-10-20/21)
    assert epochs.FOOTBALL_CLOSENESS_STRETCH_FROM_UTC == datetime(2026, 10, 21, tzinfo=UTC)
    monkeypatch.setattr(epochs, "FOOTBALL_CLOSENESS_STRETCH_FROM_UTC", None)
    assert not epochs.football_closeness_stretch(
        "2027-01-01", datetime(2027, 1, 1, tzinfo=UTC))
    monkeypatch.setattr(epochs, "FOOTBALL_CLOSENESS_STRETCH_FROM_UTC",
                        datetime(2026, 10, 22, tzinfo=UTC))
    assert epochs.football_closeness_stretch(
        "2026-10-22", datetime(2026, 10, 22, 1, tzinfo=UTC))
    assert not epochs.football_closeness_stretch("2026-10-21", AFTER)
    assert not epochs.football_closeness_stretch(
        "2026-10-22", datetime(2026, 10, 21, 23, tzinfo=UTC))
    assert epochs.FOOTBALL_CLOSENESS_STRETCH_MARKER == (
        "closeness_rule", "closeness_stretch_v1", "football")


def test_exactly_the_measured_markets() -> None:
    assert set(cls.CLOSENESS_MARKETS) == set(MEASURED)
    for kept_out in ("fouls_for", "fouls_total", "corners_total",
                     "corners_1h_total", "shots_for", "corners_for",
                     "shots_on_target_total", "offsides_total"):
        assert kept_out not in cls.CLOSENESS_MARKETS
        with pytest.raises(ValueError):
            cls.parse_table({"markets": {kept_out: {"g1": 0.01, "g2": 0.0}}})
    assert cls.CLOSENESS_TERMS["cards_points_for"] == 2
    assert cls.CLOSENESS_TERMS["cards_points_total"] == 2
    assert cls.CLOSENESS_TERMS["shots_total"] == 1
    assert cls.CLOSENESS_TERMS["shots_1h_total"] == 1
    assert not cls.SPEC.phased


def test_the_installed_file_is_the_measured_fit() -> None:
    data = json.loads(config_path(cls.CONFIG_FILE).read_text())
    table = cls.parse_table(data)
    for market, cell in MEASURED.items():
        assert table.coefficients[market] == pytest.approx(
            (cell["g1"], cell["g2"]), abs=1e-6)
    assert data["fitted_from"]["train_from"] == "2026-01-01"
    assert data["fitted_from"]["evidence"] == cls.EVIDENCE
    assert data["unfitted_constants"] == ["MAX_SUPREMACY"]


def test_the_term_is_even_in_s_and_capped() -> None:
    for s in (1.5, -1.5):
        assert TABLE.multiplier("cards_points_for", s) == pytest.approx(
            math.exp(0.017019 * 1.5 - 0.052625 * 2.25))
        assert TABLE.multiplier("cards_points_total", s) == pytest.approx(
            math.exp(0.017664 * 1.5 - 0.049219 * 2.25))
    assert TABLE.multiplier("shots_total", 9.0) == pytest.approx(
        math.exp(0.014714 * MAX_SUPREMACY))
    assert TABLE.multiplier("shots_total", 0.0) == pytest.approx(1.0)
    assert TABLE.multiplier("fouls_total", 1.0) is None
    assert TABLE.multiplier("shots_total", None) is None
    assert "g1 +0.0170, g2 -0.0526" == TABLE.describe("cards_points_for")


def test_the_config_is_validated(tmp_path: Path) -> None:
    for bad in (
        {},
        {"markets": {"cards_points_total": {"g1": 1.5, "g2": 0.0}}},
        {"markets": {"cards_points_total": {"g1": 0.1}}},  # both terms
        {"markets": {"cards_points_for": {"beta": 0.1}}},  # never a beta
        {"markets": {"shots_total": {"g1": 0.1, "g2": 0.0,
                                     "by_phase": {"early": {"g1": 0.1,
                                                            "g2": 0.0}}}}},
    ):
        with pytest.raises(ValueError):
            cls.parse_table(bad)
    with pytest.raises(FileNotFoundError):
        cls.load_table(tmp_path / cls.CONFIG_FILE)


def test_the_file_enters_the_fingerprint_only_once_present(
        tmp_path: Path) -> None:
    before = sheet_config.fingerprint(tmp_path)
    assert cls.CONFIG_FILE in sheet_config.SHEET_OPTIONAL_FILES
    assert cls.CONFIG_FILE not in sheet_config.SHEET_CONFIG_FILES
    (tmp_path / cls.CONFIG_FILE).write_text("{}")
    assert sheet_config.fingerprint(tmp_path) != before


# --- SHEET ------------------------------------------------------------------


SHEET_CASES = (("cards_points_for", "Criciúma", 2.5),
               ("cards_points_for", "Operário-PR", 2.5),
               ("cards_points_total", "", 4.5), ("shots_total", "", 3.5),
               ("shots_1h_total", "", 3.5))


@pytest.mark.parametrize("market, subject, line", SHEET_CASES)
def test_switch_off_leaves_the_sheet_byte_for_byte(
        market: str, subject: str, line: float) -> None:
    fc = fr.FootballForecast(_book(), 1, 1, 2)
    plain = _rows(market, subject, line, fc)
    assert plain
    assert json.dumps(plain) == json.dumps(
        _rows(market, subject, line, fc, closeness_stretch=None))
    assert not any("CLOSENESS_STRETCH" in n for r in plain
                   for n in r["notes"])  # type: ignore[attr-defined]


@pytest.mark.parametrize("market, subject, line", SHEET_CASES)
def test_the_term_multiplies_the_centre_with_the_home_side_s(
        market: str, subject: str, line: float) -> None:
    fc = fr.FootballForecast(_book(), 1, 1, 2)
    s_home = fc.supremacy("side_a")
    assert s_home is not None and s_home != 0
    base = _over(_rows(market, subject, line, fc))
    moved = _over(_rows(market, subject, line, fc, closeness_stretch=TABLE))
    # both sides read the same |s|: the away side's own s is -s_home
    mult = TABLE.multiplier(market, s_home)
    assert mult == pytest.approx(TABLE.multiplier(market, -s_home))
    assert mult is not None and mult != pytest.approx(1.0)
    assert moved["centre"] == pytest.approx(
        float(base["centre"]) * mult, abs=1e-3)  # type: ignore[arg-type]
    assert moved["p_central"] != base["p_central"]
    assert any(n.startswith("CLOSENESS_STRETCH") for n in moved["notes"])  # type: ignore[attr-defined]
    assert any("MAX_SUPREMACY" in n for n in moved["notes"]  # type: ignore[attr-defined]
               if n.startswith("UNFITTED_CONSTANTS"))


def test_on_top_of_game_state_beta_never_in_its_place() -> None:
    fc = fr.FootballForecast(_book(), 1, 1, 2)
    s = fc.supremacy("side_a")
    assert s is not None
    gs = GameStateTable({"cards_points_for": -0.066437})
    base = _over(_rows("cards_points_for", "Criciúma", 2.5, fc, game_state=gs))
    moved = _over(_rows("cards_points_for", "Criciúma", 2.5, fc, game_state=gs,
                        closeness_stretch=TABLE))
    notes = [n.split(":")[0] for n in moved["notes"]]  # type: ignore[attr-defined]
    assert notes.index("GAME_STATE") < notes.index("CLOSENESS_STRETCH")
    assert moved["centre"] == pytest.approx(
        float(base["centre"]) * math.exp(0.017019 * abs(s) - 0.052625 * s * s),
        abs=1e-3)  # type: ignore[arg-type]


def test_a_market_without_coefficients_or_without_supremacy_is_untouched(
) -> None:
    fc = fr.FootballForecast(_book(), 1, 1, 2)
    for market, subject, line in (("fouls_total", "", 3.5),
                                  ("corners_total", "", 3.5),
                                  ("corners_for", "Criciúma", 4.5)):
        assert (_rows(market, subject, line, fc, closeness_stretch=TABLE)
                == _rows(market, subject, line, fc))
    unrated = fr.FootballForecast(_book(), 1, 1, 12345)
    assert (_rows("cards_points_total", "", 4.5, unrated,
                  closeness_stretch=TABLE)
            == _rows("cards_points_total", "", 4.5, unrated))


def test_sheet_stamps_the_marker_on_football_rows_only_while_on(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    field, rule, _sport = epochs.FOOTBALL_CLOSENESS_STRETCH_MARKER
    rc, h, rows = _run(tmp_path / "off", monkeypatch, on=set(), rating_prices=True)
    assert rc == 0 and rows
    assert not any(field in r for r in rows)
    assert all(c.get("closeness_stretch") is None for c in h.process_calls)
    monkeypatch.setattr(epochs, "football_closeness_stretch",
                        lambda d, at=None: True)
    monkeypatch.setattr(run_sheet, "load_closeness_stretch_table", lambda: TABLE)
    rc, h, rows = _run(tmp_path / "on", monkeypatch, on=set(), rating_prices=True)
    assert rc == 0
    assert all(c["closeness_stretch"] is TABLE for c in h.process_calls)
    by_sport = {r["sport"]: r for r in rows}
    assert by_sport["football"][field] == rule
    assert field not in by_sport["tennis"]
    assert epochs.sheet_has_marker(rows, epochs.FOOTBALL_CLOSENESS_STRETCH_MARKER)


# --- rebuild_plan -----------------------------------------------------------


def test_rebuild_plan_re_runs_sheet_on_a_missing_marker(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "FOOTBALL_CLOSENESS_STRETCH_FROM_UTC", None)
    stale = rp.DayState(DAY, AFTER, LIMIT, sheet_closeness_stretch=False)
    assert "SHEET" not in rp.build_plan(stale).names()
    monkeypatch.setattr(epochs, "FOOTBALL_CLOSENESS_STRETCH_FROM_UTC",
                        datetime(2026, 10, 22, tzinfo=UTC))
    plan = rp.build_plan(stale)
    assert "SHEET" in plan.names()
    sheet = next(s for s in plan.steps if s.name == "SHEET")
    assert "football_closeness_stretch" in sheet.reason
    assert "SHEET" not in rp.build_plan(rp.DayState(DAY, AFTER, LIMIT)).names()
    assert "SHEET" not in rp.build_plan(rp.DayState(
        "2026-10-21", AFTER, LIMIT, sheet_closeness_stretch=False)).names()


def test_observe_reads_the_marker_on_football_rows() -> None:
    marker = epochs.FOOTBALL_CLOSENESS_STRETCH_MARKER
    assert marker in rp.AUDIT_MARKERS
    assert marker[0] in run_sheet.AUDIT_MARKER_FIELDS
    field, rule, _ = marker
    assert not epochs.sheet_has_marker([{"sport": "football"}], marker)
    assert epochs.sheet_has_marker([{"sport": "football", field: rule},
                                    {"sport": "tennis"}], marker)


# --- the replay -------------------------------------------------------------


def test_the_replay_hook_applies_the_closeness_term() -> None:
    history, played = _football()
    target = played[-3]
    rules = CentreRules(football_rating=True, closeness_stretch=TABLE)
    fc = FootballRatingReplay(history, rules).forecast(target)
    assert fc is not None
    sup = fc.supremacy("side_a")
    assert sup is not None and sup != 0
    off = CentreRules(football_rating=True)
    for market, side, c in (("shots_total", None, 24.0),
                            ("cards_points_total", None, 4.4),
                            ("cards_points_for", "side_b", 2.2)):
        base = live_centre(target, market, side, c, fc, (), off)
        got = live_centre(target, market, side, c, fc, (), rules)
        mult = TABLE.multiplier(market, sup)
        assert mult is not None
        assert got == pytest.approx(base * mult)
    assert live_centre(target, "fouls_total", None, 24.0, fc, (), rules) == (
        pytest.approx(live_centre(target, "fouls_total", None, 24.0, fc, (), off)))
    assert cfc.CENTRE_RULES.closeness_stretch is None
    assert rules.describe()["closeness_stretch"] == "in-memory"


def test_the_replay_flag_needs_the_rating(
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv",
                        ["calibrate_from_cache.py", "--closeness-stretch"])
    with pytest.raises(SystemExit):
        cfc.main()
    assert "--closeness-stretch need --football-rating" in capsys.readouterr().err


def test_every_closeness_market_is_a_replayed_market() -> None:
    # cards points are read from the incidents (SPORT_OF_BASE), the rest
    # from the statistics (STAT_KEYS, HALF_BASES)
    bases = set(cfc.SPORT_OF_BASE) | set(cfc.HALF_BASES)
    for market in cls.CLOSENESS_MARKETS:
        assert market.rsplit("_", 1)[0] in bases, market


def test_prepare_refit_passes_the_flag_through(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _db(paths.db_path)
    seen: list[list[str]] = []
    inner = _fake_calibrate(paths.db_path)

    def runner(cmd: Sequence[str], env: dict[str, str], log: Path | None
               ) -> tuple[int, list[str]]:
        seen.append(list(cmd))
        return inner(cmd, env, log)

    with pytest.raises(pr.RefitError, match="need --football-rating"):
        pr.rebuild_cache_rows(paths, dry_run=False, confirm=True, runner=runner,
                              require_db_backup=False, closeness_stretch=True)
    with pytest.raises(pr.RefitError,
                       match="sofa_closeness_stretch.json is absent"):
        pr.rebuild_cache_rows(paths, dry_run=False, confirm=True, runner=runner,
                              require_db_backup=False, football_rating=True,
                              closeness_stretch=True)
    (paths.config_dir / cls.CONFIG_FILE).write_text(
        json.dumps({"markets": {"shots_total": {"g1": 0.015, "g2": 0.0}}}))
    report: dict[str, Any] = pr.rebuild_cache_rows(
        paths, dry_run=False, confirm=True, runner=runner,
        require_db_backup=False, football_rating=True, closeness_stretch=True)
    assert "--closeness-stretch" in seen[-1] and "--football-rating" in seen[-1]
    assert report["closeness_stretch"] is True
    rules = pr.read_replay_rules(paths)
    assert rules is not None and rules["flags"]["closeness_stretch"] is True
    args = pr.build_parser().parse_args(
        ["--date", "2026-10-22", "rebuild-cache-rows", "--closeness-stretch"])
    assert args.closeness_stretch is True


# --- the fit ----------------------------------------------------------------


def test_the_fit_reads_g_on_top_of_game_state_and_writes_the_measured_form(
) -> None:
    gs = GameStateTable({"cards_points_for": -0.066})
    rows = []
    for i in range(800):
        s = (i % 41 - 20) / 8
        c = 2.0 + (i % 5) / 2
        # the truth: GAME_STATE's beta s AND the closeness term
        y_side = c * math.exp(-0.066 * s + 0.02 * abs(s) - 0.05 * s * s)
        rows.append(StretchRow("cards_points_for", i, 0, "side_a", y_side, c, s))
        rows.append(StretchRow("shots_total", i, 0, "", 25 * c * math.exp(
            0.015 * abs(s)), 25 * c, s))
    table = fit.fit_rows(rows, ("cards_points_for", "shots_total"), gs, None)
    assert table["cards_points_for"]["g1"] == pytest.approx(0.02, abs=1e-5)
    assert table["cards_points_for"]["g2"] == pytest.approx(-0.05, abs=1e-5)
    assert table["shots_total"]["g1"] == pytest.approx(0.015, abs=1e-5)
    assert table["shots_total"]["g2"] == 0.0
    assert table["shots_total"]["n_matches"] == 800
    cls.parse_table({"markets": table})
    # without the GAME_STATE offset the fit would absorb the beta into g: the
    # offset is what keeps the term on top of it
    plain = fit.fit_rows(rows, ("cards_points_for",), GameStateTable({}), None)
    assert plain["cards_points_for"]["g1"] != pytest.approx(0.02, abs=1e-3) or (
        plain["cards_points_for"]["g2"] != pytest.approx(-0.05, abs=1e-3))
