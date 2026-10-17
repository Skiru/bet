"""The football goals stretch (epochs.FOOTBALL_GOALS_STRETCH, off while
None; bet.sofa.goals_stretch): a goals centre x exp(beta x s) on a side,
exp(g1 |s| + g2 s^2) on a total, in SHEET and in the cache replay, with its
row marker, rebuild_plan's re-run, the replay flag and the config. Offline
and fast."""

from __future__ import annotations

import json
import math
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import epochs, sheet_config
from bet.sofa import football_rating as fr
from bet.sofa import goals_stretch as gst
from bet.sofa import rebuild_plan as rp
from bet.sofa.contracts import (
    FixtureOffer,
    FixtureSamples,
    MetricSample,
    PricedRung,
)
from bet.sofa.game_state import MAX_SUPREMACY
from scripts.sofa import calibrate_from_cache as cfc
from scripts.sofa import prepare_refit as pr
from scripts.sofa import run_sheet
from scripts.sofa.calibrate_from_cache import (
    CentreRules,
    FootballRatingReplay,
    live_centre,
)
from scripts.sofa.run_sheet import process_fixture, sheet_row_json
from tests.sofa.test_audit_2026_10_13_b1b2 import _book, _obs
from tests.sofa.test_audit_2026_10_13_replay import _football
from tests.sofa.test_player_markets import _fixture
from tests.sofa.test_prepare_refit import _db, _fake_calibrate, _paths
from tests.sofa.test_run_sheet_wiring import _run

TABLE = gst.GoalsStretchTable({
    "goals_for": (0.07,), "goals_1h_for": (0.18,),
    "goals_total": (-0.0145, 0.024)})
LIMIT = rp.timedelta(minutes=45)
DAY = "2026-10-18"
AFTER = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)


# --- the switch ------------------------------------------------------------


def test_the_switch_is_off_and_reads_the_day_and_the_clock(
        monkeypatch: pytest.MonkeyPatch) -> None:
    assert epochs.FOOTBALL_GOALS_STRETCH_FROM_UTC == (
        datetime(2026, 10, 17, 13, 37, tzinfo=UTC))
    for _off in ("FOOTBALL_GOALS_STRETCH_FROM_UTC",
                 "FOOTBALL_COUNT_STRETCH_FROM_UTC",
                 "FOOTBALL_PLAYER_STRETCH_FROM_UTC"):
        monkeypatch.setattr(epochs, _off, None)
    late = datetime(2027, 1, 1, tzinfo=UTC)
    assert not epochs.football_goals_stretch("2027-01-01", late)
    monkeypatch.setattr(epochs, "FOOTBALL_GOALS_STRETCH_FROM_UTC",
                        datetime(2026, 10, 18, tzinfo=UTC))
    assert epochs.football_goals_stretch(
        "2026-10-18", datetime(2026, 10, 18, 1, tzinfo=UTC))
    assert not epochs.football_goals_stretch("2026-10-17", AFTER)
    assert not epochs.football_goals_stretch(
        "2026-10-18", datetime(2026, 10, 17, 23, tzinfo=UTC))
    assert epochs.FOOTBALL_GOALS_STRETCH_MARKER == (
        "goals_stretch_rule", epochs.FOOTBALL_GOALS_STRETCH, "football")


# --- the multiplier --------------------------------------------------------


def test_a_side_market_reads_exp_beta_s_capped() -> None:
    assert TABLE.multiplier("goals_for", 1.0) == pytest.approx(math.exp(0.07))
    assert TABLE.multiplier("goals_for", -1.0) == pytest.approx(math.exp(-0.07))
    assert TABLE.multiplier("goals_for", 10.0) == pytest.approx(
        math.exp(0.07 * MAX_SUPREMACY))


def test_a_total_reads_exp_g1_abs_s_plus_g2_s_squared_even_in_s() -> None:
    for s in (1.5, -1.5):
        assert TABLE.multiplier("goals_total", s) == pytest.approx(
            math.exp(-0.0145 * 1.5 + 0.024 * 1.5 ** 2))
    capped = MAX_SUPREMACY
    assert TABLE.multiplier("goals_total", -9.0) == pytest.approx(
        math.exp(-0.0145 * capped + 0.024 * capped ** 2))
    assert TABLE.multiplier("goals_total", 0.0) == pytest.approx(1.0)


def test_an_absent_market_or_no_supremacy_is_the_identity() -> None:
    assert TABLE.multiplier("goals_2h_for", 1.0) is None
    assert TABLE.multiplier("goals_for", None) is None
    assert TABLE.multiplier("corners_for", 1.0) is None


def test_the_supremacy_a_market_reads() -> None:
    fc = fr.FootballForecast(_book(), 1, 1, 2)
    s = fc.supremacy("side_a")
    assert s is not None and s > 0
    assert gst.stretch_supremacy(fc, "goals_for", "side_b") == pytest.approx(-s)
    # a total reads the home side's, whatever side it is asked with
    assert gst.stretch_supremacy(fc, "goals_total", None) == pytest.approx(s)
    assert gst.stretch_supremacy(fc, "goals_for", None) is None
    unrated = fr.FootballForecast(_book(), 1, 1, 12345)
    assert gst.stretch_supremacy(unrated, "goals_total", None) is None


def test_fit_terms_recovers_known_coefficients() -> None:
    s = [(i % 41 - 20) / 8 for i in range(800)]
    c = [1.0 + (i % 7) / 3 for i in range(800)]
    y = [ci * math.exp(0.15 * si) for ci, si in zip(c, s, strict=True)]
    assert gst.fit_terms("goals_for", c, s, y)[0] == pytest.approx(0.15, abs=1e-6)
    yt = [ci * math.exp(-0.02 * abs(si) + 0.03 * si * si)
          for ci, si in zip(c, s, strict=True)]
    g1, g2 = gst.fit_terms("goals_total", c, s, yt)
    assert g1 == pytest.approx(-0.02, abs=1e-6) and g2 == pytest.approx(0.03, abs=1e-6)
    assert gst.fit_terms("goals_for", c, s, c)[0] == pytest.approx(0.0, abs=1e-9)
    assert gst.fit_terms("goals_total", [], [], []) == (0.0, 0.0)


# --- the config ------------------------------------------------------------


def test_the_config_is_validated() -> None:
    table = gst.parse_table({"markets": {
        "goals_for": {"beta": 0.07, "n_rows": 10},
        "goals_total": {"g1": -0.01, "g2": 0.02}}})
    assert table.coefficients == {"goals_for": (0.07,), "goals_total": (-0.01, 0.02)}
    for bad in (
        {},
        {"markets": {"corners_for": {"beta": 0.1}}},  # not a goals market
        {"markets": {"goals_for": {"beta": 2.0}}},  # beyond MAX_ABS_COEFFICIENT
        {"markets": {"goals_for": {"beta": True}}},
        {"markets": {"goals_for": {"g1": 0.1, "g2": 0.1}}},  # a side has a beta
        {"markets": {"goals_total": {"beta": 0.1}}},  # a total has g1 / g2
        {"markets": {"goals_total": {"g1": 0.1, "g2": float("nan")}}},
        {"markets": {"goals_total": 0.1}},
    ):
        with pytest.raises(ValueError):
            gst.parse_table(bad)


def test_load_table_raises_on_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        gst.load_table(tmp_path / gst.CONFIG_FILE)
    (tmp_path / gst.CONFIG_FILE).write_text(json.dumps(
        {"markets": {"goals_2h_total": {"g1": 0.0, "g2": 0.03}}}))
    assert gst.load_table(tmp_path / gst.CONFIG_FILE).multiplier(
        "goals_2h_total", 2.0) == pytest.approx(math.exp(0.12))


def test_the_installed_file_enters_the_fingerprint_only_once_present(
        tmp_path: Path) -> None:
    # sheets priced before the file existed keep their config_sha
    before = sheet_config.fingerprint(tmp_path)
    assert gst.CONFIG_FILE in sheet_config.SHEET_OPTIONAL_FILES
    assert gst.CONFIG_FILE not in sheet_config.SHEET_CONFIG_FILES
    (tmp_path / gst.CONFIG_FILE).write_text("{}")
    assert sheet_config.fingerprint(tmp_path) != before


# --- SHEET -----------------------------------------------------------------


def _rows(market: str, subject: str, line: float,
          forecast: fr.FootballForecast | None, **kwargs: object,
          ) -> list[dict[str, object]]:
    from bet.sofa.config import SofaConfig

    values = [1.0, 2.0, 0.0, 3.0, 1.0, 2.0, 1.0, 0.0, 2.0, 1.0]
    venues = ["home", "away"] * 5
    samples = FixtureSamples(
        sofascore_event_id=1, readiness="READY", gaps=[],
        metrics={market: MetricSample(
            metric=market, side_a=_obs(values, 100, venues),
            side_b=_obs(values, 200, venues), h2h=[])},
    )
    offer = FixtureOffer(
        sofascore_event_id=1, status="PRICED", unmapped_markets=[],
        rungs=[PricedRung(market=market, subject=subject, line=line,
                          over_odds=1.80, under_odds=1.95,
                          fetched_at_utc=datetime(2026, 9, 22, tzinfo=UTC))],
    )
    rows, _ = process_fixture(
        _fixture(), samples, offer, baselines={}, reliability={},
        engine_constants={}, vetoes=[], config=SofaConfig(), football=forecast,
        stats_only=True, **kwargs,  # type: ignore[arg-type]
    )
    return [sheet_row_json(r) for r in rows]


def _over(rows: list[dict[str, object]]) -> dict[str, object]:
    return next(r for r in rows if r["direction"] == "OVER")


SHEET_CASES = (("goals_for", "Criciúma", 1.5), ("goals_total", "", 2.5))


@pytest.mark.parametrize("market, subject, line", SHEET_CASES)
def test_switch_off_leaves_the_sheet_byte_for_byte(
        market: str, subject: str, line: float) -> None:
    fc = fr.FootballForecast(_book(), 1, 1, 2)
    plain = _rows(market, subject, line, fc)
    assert plain
    assert json.dumps(plain) == json.dumps(
        _rows(market, subject, line, fc, goals_stretch=None))
    assert not any("GOALS_STRETCH" in n for r in plain
                   for n in r["notes"])  # type: ignore[attr-defined]


@pytest.mark.parametrize("market, subject, line", SHEET_CASES)
def test_the_stretch_multiplies_the_blended_goals_centre(
        market: str, subject: str, line: float) -> None:
    fc = fr.FootballForecast(_book(), 1, 1, 2)
    s = fc.supremacy("side_a")
    assert s is not None and s > 0
    base = _over(_rows(market, subject, line, fc))
    moved = _over(_rows(market, subject, line, fc, goals_stretch=TABLE))
    mult = TABLE.multiplier(market, s)
    assert mult is not None and mult != pytest.approx(1.0)
    assert moved["centre"] == pytest.approx(
        float(base["centre"]) * mult, abs=1e-3)  # type: ignore[arg-type]
    assert any(n.startswith("GOALS_STRETCH") for n in moved["notes"])  # type: ignore[attr-defined]
    assert any("MAX_SUPREMACY" in n for n in moved["notes"]  # type: ignore[attr-defined]
               if n.startswith("UNFITTED_CONSTANTS"))


def test_a_market_without_coefficients_or_a_fixture_without_supremacy_is_untouched(
) -> None:
    fc = fr.FootballForecast(_book(), 1, 1, 2)
    assert (_rows("goals_2h_for", "Criciúma", 0.5, fc, goals_stretch=TABLE)
            == _rows("goals_2h_for", "Criciúma", 0.5, fc))
    unrated = fr.FootballForecast(_book(), 1, 1, 12345)
    assert (_rows("goals_for", "Criciúma", 1.5, unrated, goals_stretch=TABLE)
            == _rows("goals_for", "Criciúma", 1.5, unrated))


def test_sheet_stamps_the_marker_on_football_rows_only_while_on(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    field, rule, _sport = epochs.FOOTBALL_GOALS_STRETCH_MARKER
    rc, _h, rows = _run(tmp_path / "off", monkeypatch, on=set(), rating_prices=True)
    assert rc == 0 and rows
    assert not any(field in r for r in rows)
    monkeypatch.setattr(epochs, "football_goals_stretch", lambda d, at=None: True)
    loaded: list[bool] = []

    def load() -> gst.GoalsStretchTable:
        loaded.append(True)
        return TABLE

    monkeypatch.setattr(run_sheet, "load_goals_stretch_table", load)
    rc, _h, rows = _run(tmp_path / "on", monkeypatch, on=set(), rating_prices=True)
    assert rc == 0 and loaded
    by_sport = {r["sport"]: r for r in rows}
    assert by_sport["football"][field] == rule
    assert field not in by_sport["tennis"]
    assert epochs.sheet_has_marker(rows, epochs.FOOTBALL_GOALS_STRETCH_MARKER)


# --- rebuild_plan ----------------------------------------------------------


def test_rebuild_plan_re_runs_sheet_on_a_missing_marker(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "TENNIS_MATCH_WINNER_FROM_UTC", None)
    for _off in ("FOOTBALL_GOALS_STRETCH_FROM_UTC",
                 "FOOTBALL_COUNT_STRETCH_FROM_UTC",
                 "FOOTBALL_PLAYER_STRETCH_FROM_UTC"):
        monkeypatch.setattr(epochs, _off, None)
    stale = rp.DayState(DAY, AFTER, LIMIT, sheet_goals_stretch=False)
    # off: a sheet without the marker is the sheet of the day
    assert "SHEET" not in rp.build_plan(stale).names()
    monkeypatch.setattr(epochs, "FOOTBALL_GOALS_STRETCH_FROM_UTC",
                        datetime(2026, 10, 18, tzinfo=UTC))
    plan = rp.build_plan(stale)
    assert "SHEET" in plan.names()
    sheet = next(s for s in plan.steps if s.name == "SHEET")
    assert "football_goals_stretch" in sheet.reason
    assert "SHEET" not in rp.build_plan(rp.DayState(DAY, AFTER, LIMIT)).names()
    # a day before the switch keeps its sheet
    assert "SHEET" not in rp.build_plan(rp.DayState(
        "2026-10-17", AFTER, LIMIT, sheet_goals_stretch=False)).names()


def test_observe_reads_the_marker_on_football_rows() -> None:
    marker = epochs.FOOTBALL_GOALS_STRETCH_MARKER
    assert marker in rp.AUDIT_MARKERS
    assert marker[0] in run_sheet.AUDIT_MARKER_FIELDS
    field, rule, _ = marker
    assert not epochs.sheet_has_marker([{"sport": "football"}], marker)
    assert epochs.sheet_has_marker([{"sport": "football", field: rule},
                                    {"sport": "tennis"}], marker)


# --- the replay ------------------------------------------------------------


def test_the_replay_hook_applies_the_stretch_after_game_state() -> None:
    history, played = _football()
    target = played[-3]
    rules = CentreRules(football_rating=True, goals_stretch=TABLE)
    fc = FootballRatingReplay(history, rules).forecast(target)
    assert fc is not None
    sup = fc.supremacy("side_a")
    rated = fc.centre("goals_for", "side_b")
    assert sup is not None and rated is not None
    blended = fr.W_FOOTBALL_RATING * rated[0] + (1 - fr.W_FOOTBALL_RATING) * 1.2
    got = live_centre(target, "goals_for", "side_b", 1.2, fc, (), rules)
    assert got == pytest.approx(blended * TABLE.multiplier("goals_for", -sup))  # type: ignore[operator]
    total = fc.centre("goals_total", None)
    assert total is not None
    t_blend = fr.W_FOOTBALL_RATING * total[0] + (1 - fr.W_FOOTBALL_RATING) * 2.6
    assert live_centre(target, "goals_total", None, 2.6, fc, (), rules) == (
        pytest.approx(t_blend * TABLE.multiplier("goals_total", sup)))  # type: ignore[operator]
    off = CentreRules(football_rating=True)
    assert live_centre(target, "goals_for", "side_b", 1.2, fc, (), off) == (
        pytest.approx(blended))
    assert cfc.CENTRE_RULES.goals_stretch is None
    assert rules.describe()["goals_stretch"] == "in-memory"


def test_the_replay_flag_needs_the_rating(
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["calibrate_from_cache.py", "--goals-stretch"])
    with pytest.raises(SystemExit):
        cfc.main()
    assert "--goals-stretch need --football-rating" in capsys.readouterr().err


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
                              require_db_backup=False, goals_stretch=True)
    with pytest.raises(pr.RefitError, match="sofa_goals_stretch.json is absent"):
        pr.rebuild_cache_rows(paths, dry_run=False, confirm=True, runner=runner,
                              require_db_backup=False, football_rating=True,
                              goals_stretch=True)
    (paths.config_dir / gst.CONFIG_FILE).write_text(
        json.dumps({"markets": {"goals_for": {"beta": 0.07}}}))
    report: dict[str, Any] = pr.rebuild_cache_rows(
        paths, dry_run=False, confirm=True, runner=runner,
        require_db_backup=False, football_rating=True, goals_stretch=True)
    assert "--goals-stretch" in seen[-1] and "--football-rating" in seen[-1]
    assert report["goals_stretch"] is True
    rules = pr.read_replay_rules(paths)
    assert rules is not None and rules["flags"]["goals_stretch"] is True


# --- the fit ---------------------------------------------------------------


def test_the_fit_reads_a_totals_supremacy_off_the_home_goals_row() -> None:
    from bet.sofa import centre_replay as cr
    from scripts.sofa import fit_goals_stretch as fit
    from scripts.sofa.measure_game_state import CentreRules as FitRules

    history, _ = _football(days=60)
    start = datetime.fromtimestamp(history[0].ts, UTC).date().isoformat()
    end = datetime.fromtimestamp(history[-1].ts, UTC).date().isoformat()
    rows = fit.collect(history, start, end, ("goals_total",), FitRules())
    assert set(rows) == {"goals_total"}
    centres, sup, y, events = rows["goals_total"]
    assert centres and len(centres) == len(sup) == len(y) == len(events)
    home = {r.event_id: r.supremacy for r in cr.walk(
        history, 0, 2**62, ("goals_for",)) if r.side == "side_a"}
    totals = [r for r in cr.walk(history, 0, 2**62, ("goals_total",))
              if r.event_id in events]
    assert sorted(sup) == pytest.approx(sorted(home[r.event_id] for r in totals))
    assert len(gst.fit_terms("goals_total", centres, sup, y)) == 2


# --- goals_stretch_v2: per season phase ------------------------------------

PHASED = gst.parse_table({"markets": {
    "goals_for": {"beta": 0.062, "by_phase": {
        "early": {"beta": 0.018}, "mid": {"beta": 0.056},
        "late": {"beta": 0.064}, "final": {"beta": 0.063},
        "none": {"beta": 0.082}}},
    "goals_1h_for": {"beta": 0.167, "by_phase": {"early": {"beta": 0.145}}},
    "goals_2h_for": {"by_phase": {"early": {"beta": 0.100}}},
    "goals_total": {"g1": -0.0145, "g2": 0.024},
}})


def test_the_rule_is_v2() -> None:
    assert epochs.FOOTBALL_GOALS_STRETCH == "goals_stretch_v2"
    assert epochs.FOOTBALL_GOALS_STRETCH_MARKER[1] == "goals_stretch_v2"


def test_a_phase_reads_its_own_coefficients() -> None:
    assert PHASED.multiplier("goals_for", 1.0, "early") == pytest.approx(
        math.exp(0.018))
    assert PHASED.multiplier("goals_for", 1.0, "late") == pytest.approx(
        math.exp(0.064))
    # no phase is the table's "none"
    assert PHASED.multiplier("goals_for", 1.0, None) == pytest.approx(
        math.exp(0.082))
    assert PHASED.multiplier("goals_for", -2.0, "mid") == pytest.approx(
        math.exp(-2 * 0.056))
    assert "phase early" in PHASED.describe("goals_for", "early")


def test_a_phase_the_table_lacks_falls_back_to_the_single_set_else_identity(
) -> None:
    assert PHASED.multiplier("goals_1h_for", 1.0, "early") == pytest.approx(
        math.exp(0.145))
    for phase in ("mid", "late", "final", None):
        assert PHASED.multiplier("goals_1h_for", 1.0, phase) == pytest.approx(
            math.exp(0.167))
    assert "phase" not in PHASED.describe("goals_1h_for", "mid")
    # a market with only per-phase sets: identity outside them
    assert PHASED.multiplier("goals_2h_for", 1.0, "early") == pytest.approx(
        math.exp(0.100))
    assert PHASED.multiplier("goals_2h_for", 1.0, "mid") is None
    # a single-only market ignores the phase
    assert PHASED.multiplier("goals_total", 1.5, "early") == pytest.approx(
        TABLE.multiplier("goals_total", 1.5))
    assert PHASED.multiplier("goals_for", None, "early") is None


def test_the_per_phase_config_is_validated() -> None:
    assert PHASED.by_phase["goals_1h_for"] == {"early": (0.145,)}
    assert "goals_2h_for" not in PHASED.coefficients
    for bad in (
        {"markets": {"goals_for": {"by_phase": {"spring": {"beta": 0.1}}}}},
        {"markets": {"goals_for": {"by_phase": {}}}},
        {"markets": {"goals_for": {"by_phase": {"early": 0.1}}}},
        {"markets": {"goals_for": {"by_phase": {"early": {"beta": 3.0}}}}},
        {"markets": {"goals_total": {"by_phase": {"early": {"beta": 0.1}}}}},
        {"markets": {"goals_for": {"beta": 0.1, "beta2": 0.01}}},  # no s^2 here
        {"markets": {"goals_for": {"n_rows": 5}}},  # no coefficients at all
    ):
        with pytest.raises(ValueError):
            gst.parse_table(bad)


def test_sheet_reads_the_fixture_s_season_phase() -> None:
    fc = fr.FootballForecast(_book(), 1, 1, 2)
    s = fc.supremacy("side_a")
    assert s is not None
    base = _over(_rows("goals_for", "Criciúma", 1.5, fc))
    for phase, beta in (("early", 0.018), ("final", 0.063), (None, 0.082)):
        moved = _over(_rows("goals_for", "Criciúma", 1.5, fc,
                            goals_stretch=PHASED, season_phase_label=phase))
        assert moved["centre"] == pytest.approx(
            float(base["centre"]) * math.exp(beta * s), abs=1e-3)  # type: ignore[arg-type]


def test_the_replay_reads_the_phase_and_computes_it_for_a_phased_table() -> None:
    history, played = _football()
    target = played[-3]
    rules = CentreRules(football_rating=True, goals_stretch=PHASED)
    replay = FootballRatingReplay(history, rules)
    # phases are read for a per-phase table even with --season-phase off
    assert replay.phases and target.event_id in replay.phases
    assert not FootballRatingReplay(
        history, CentreRules(football_rating=True, goals_stretch=TABLE)).phases
    fc = replay.forecast(target)
    assert fc is not None
    sup = fc.supremacy("side_a")
    assert sup is not None
    early = live_centre(target, "goals_for", "side_a", 1.2, fc, (), rules,
                        phase="early")
    late = live_centre(target, "goals_for", "side_a", 1.2, fc, (), rules,
                       phase="late")
    assert early / late == pytest.approx(math.exp((0.018 - 0.064) * sup))


def test_the_fit_parses_per_phase_and_recovers_phase_coefficients() -> None:
    from scripts.sofa import fit_goals_stretch as fit

    assert fit.parse_per_phase(["goals_for", "goals_1h_for:early"],
                               ["goals_for", "goals_1h_for"]) == {
        "goals_for": ("early", "mid", "late", "final", "none"),
        "goals_1h_for": ("early",)}
    with pytest.raises(ValueError):
        fit.parse_per_phase(["goals_for:spring"], ["goals_for"])
    with pytest.raises(ValueError):
        fit.parse_per_phase(["goals_2h_for"], ["goals_for"])
    n = 1200
    s = [(i % 41 - 20) / 8 for i in range(n)]
    c = [1.0 + (i % 7) / 3 for i in range(n)]
    phases: list[str | None] = ["early" if i % 3 == 0 else None for i in range(n)]
    true = {"early": 0.02, "none": 0.09}
    y = [ci * math.exp(true["early" if p == "early" else "none"] * si)
         for ci, si, p in zip(c, s, phases, strict=True)]
    cells = fit.fit_by_phase("goals_for", c, s, y, phases,
                             ("early", "mid", "none"), min_rows=100)
    assert set(cells) == {"early", "none"}  # mid has no rows
    assert cells["early"]["beta"] == pytest.approx(0.02, abs=1e-5)
    assert cells["none"]["beta"] == pytest.approx(0.09, abs=1e-5)
    assert cells["early"]["n_rows"] == 400
    # the written cells read back
    table = gst.parse_table({"markets": {"goals_for": {
        "beta": 0.05, "by_phase": cells}}})
    assert table.multiplier("goals_for", 1.0, "early") == pytest.approx(
        math.exp(0.02), abs=1e-5)


def test_the_recommended_per_phase_command_leaves_no_phase_to_the_single_set(
) -> None:
    from scripts.sofa import fit_goals_stretch as fit

    per_phase = fit.parse_per_phase(
        ["goals_for:early,mid,late,final", "goals_1h_for:early",
         "goals_2h_for:early"], list(gst.GOALS_STRETCH_MARKETS))
    assert per_phase == {"goals_for": ("early", "mid", "late", "final"),
                         "goals_1h_for": ("early",), "goals_2h_for": ("early",)}
    table = gst.parse_table({"markets": {"goals_for": {
        "beta": 0.071,
        "by_phase": {p: {"beta": 0.05} for p in per_phase["goals_for"]}}}})
    assert table.multiplier("goals_for", 1.0, None) == pytest.approx(math.exp(0.071))
    assert table.multiplier("goals_for", 1.0, "late") == pytest.approx(math.exp(0.05))


def test_the_fit_offset_carries_the_installed_phase_and_the_cup_book_by_default(
        tmp_path: Path) -> None:
    from scripts.sofa import fit_goals_stretch as fit

    phase_table, cup = fit.offset_tables(None, False, None, False)
    assert phase_table is not None and phase_table.coefficients
    assert cup is not None and cup.competitions
    assert fit.offset_tables(None, True, None, True) == (None, None)
    with pytest.raises(ValueError):
        fit.offset_tables(str(tmp_path / "x.json"), True, None, False)
    with pytest.raises(ValueError):
        fit.offset_tables(None, False, str(tmp_path / "x.json"), True)


def test_the_goals_fit_walk_reads_the_cup_book(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from bet.sofa import centre_replay as cr
    from bet.sofa.cup_strength import load as load_cup
    from scripts.sofa import fit_goals_stretch as fit
    from scripts.sofa.measure_game_state import CentreRules as FitRules

    seen: list[object] = []
    real = cr.apply_cup_strength

    def spy(book: fr.RatingBook, cup: object) -> fr.RatingBook:
        seen.append(cup)
        return real(book, cup)  # type: ignore[arg-type]

    monkeypatch.setattr(cr, "apply_cup_strength", spy)
    history, _ = _football(days=20)
    start = datetime.fromtimestamp(history[0].ts, UTC).date().isoformat()
    end = datetime.fromtimestamp(history[-1].ts, UTC).date().isoformat()
    cup = load_cup()
    fit.collect(history, start, end, ("goals_for",), FitRules(), cup_strength=cup)
    fit.collect(history, start, end, ("goals_for",), FitRules())
    assert seen == [cup, None]
