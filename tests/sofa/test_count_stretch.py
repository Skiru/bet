"""The football count stretch (epochs.FOOTBALL_COUNT_STRETCH, off while
None; bet.sofa.count_stretch over bet.sofa.supremacy_stretch): a count
centre outside GAME_STATE x exp(beta x s [+ beta2 x s^2]) on a side,
exp(g1 |s| + g2 s^2) on a total, in SHEET and in the cache replay, with its
row marker, rebuild_plan's re-run, the replay flag, the config and the fit.
Offline and fast."""

from __future__ import annotations

import json
import math
import sqlite3
import sys
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import count_stretch as cst
from bet.sofa import epochs, sheet_config
from bet.sofa import football_rating as fr
from bet.sofa import rebuild_plan as rp
from bet.sofa import supremacy_stretch as ss
from bet.sofa.contracts import (
    FixtureOffer,
    FixtureSamples,
    MetricSample,
    PricedRung,
)
from bet.sofa.db import migrate
from bet.sofa.game_state import MAX_SUPREMACY, GameStateTable
from scripts.sofa import calibrate_from_cache as cfc
from scripts.sofa import fit_count_stretch as fit
from scripts.sofa import prepare_refit as pr
from scripts.sofa import run_sheet
from scripts.sofa.calibrate_from_cache import (
    CentreRules,
    FootballRatingReplay,
    live_centre,
)
from scripts.sofa.measure_game_state import CentreRules as GameStateRules
from scripts.sofa.run_sheet import process_fixture, sheet_row_json
from tests.sofa.test_audit_2026_10_13_b1b2 import _book, _obs
from tests.sofa.test_audit_2026_10_13_replay import _football
from tests.sofa.test_cache_replay_player_markets import _statistics
from tests.sofa.test_player_markets import _fixture
from tests.sofa.test_prepare_refit import _db, _fake_calibrate, _paths
from tests.sofa.test_run_sheet_wiring import _run

# the 2026-10-17 measurement's coefficients (fit from 2026-01-01)
MEASURED: dict[str, dict[str, float]] = {
    "corners_1h_for": {"beta": 0.1390}, "corners_2h_for": {"beta": 0.1202},
    "shots_1h_for": {"beta": 0.0425}, "shots_2h_for": {"beta": 0.1609},
    "shots_on_target_for": {"beta": 0.0518},
    "shots_on_target_1h_for": {"beta": 0.0796},
    "shots_on_target_2h_for": {"beta": 0.1873},
    "offsides_for": {"beta": 0.0262}, "saves_for": {"beta": -0.1693},
    "saves_1h_for": {"beta": -0.1859},
    "throw_ins_for": {"beta": 0.0457, "beta2": -0.0171},
    "goal_kicks_for": {"beta": -0.1360},
    "shots_on_target_total": {"g1": 0.0204, "g2": 0.0},
    "saves_total": {"g1": 0.0212, "g2": 0.0},
    "saves_1h_total": {"g1": 0.0250, "g2": 0.0},
    "throw_ins_total": {"g1": 0.0069, "g2": -0.0190},
}
TABLE = cst.parse_table({"markets": MEASURED})
LIMIT = rp.timedelta(minutes=45)
DAY = "2026-10-18"
AFTER = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)


# --- the switch and the markets ---------------------------------------------


def test_the_switch_is_off_and_reads_the_day_and_the_clock(
        monkeypatch: pytest.MonkeyPatch) -> None:
    assert epochs.FOOTBALL_COUNT_STRETCH_FROM_UTC is None
    assert not epochs.football_count_stretch(
        "2027-01-01", datetime(2027, 1, 1, tzinfo=UTC))
    monkeypatch.setattr(epochs, "FOOTBALL_COUNT_STRETCH_FROM_UTC",
                        datetime(2026, 10, 18, tzinfo=UTC))
    assert epochs.football_count_stretch(
        "2026-10-18", datetime(2026, 10, 18, 1, tzinfo=UTC))
    assert not epochs.football_count_stretch("2026-10-17", AFTER)
    assert not epochs.football_count_stretch(
        "2026-10-18", datetime(2026, 10, 17, 23, tzinfo=UTC))
    assert epochs.FOOTBALL_COUNT_STRETCH_MARKER == (
        "count_stretch_rule", "count_stretch_v1", "football")


def test_exactly_the_measured_markets_and_none_of_game_state() -> None:
    assert set(cst.COUNT_STRETCH_MARKETS) == set(MEASURED)
    assert len(cst.COUNT_STRETCH_MARKETS) == 16
    for kept_out in ("corners_for", "shots_for", "cards_points_for",
                     "fouls_for", "tackles_for", "fouls_total", "corners_total"):
        assert kept_out not in cst.COUNT_STRETCH_MARKETS
        with pytest.raises(ValueError):
            cst.parse_table({"markets": {kept_out: {"beta": 0.1}}})
    assert cst.COUNT_STRETCH_TERMS["throw_ins_for"] == 2
    assert cst.COUNT_STRETCH_TERMS["throw_ins_total"] == 2
    assert cst.COUNT_STRETCH_TERMS["saves_total"] == 1
    assert not cst.SPEC.phased and cst.SPEC.side_quadratic


# --- the multiplier ---------------------------------------------------------


def test_a_side_market_reads_exp_beta_s_capped() -> None:
    assert TABLE.multiplier("saves_for", 1.0) == pytest.approx(math.exp(-0.1693))
    assert TABLE.multiplier("saves_for", -1.0) == pytest.approx(math.exp(0.1693))
    assert TABLE.multiplier("corners_1h_for", 9.0) == pytest.approx(
        math.exp(0.1390 * MAX_SUPREMACY))


def test_a_quadratic_side_market_reads_s_and_s_squared() -> None:
    for s in (1.5, -1.5):
        assert TABLE.multiplier("throw_ins_for", s) == pytest.approx(
            math.exp(0.0457 * s - 0.0171 * s * s))
    assert "beta2 -0.0171" in TABLE.describe("throw_ins_for")


def test_a_total_reads_abs_s_and_s_squared_even_in_s() -> None:
    for s in (2.0, -2.0):
        assert TABLE.multiplier("saves_total", s) == pytest.approx(
            math.exp(0.0212 * 2.0))
        assert TABLE.multiplier("throw_ins_total", s) == pytest.approx(
            math.exp(0.0069 * 2.0 - 0.0190 * 4.0))
    assert TABLE.multiplier("shots_on_target_total", 0.0) == pytest.approx(1.0)


def test_an_absent_market_or_no_supremacy_is_the_identity() -> None:
    small = cst.parse_table({"markets": {"saves_for": {"beta": -0.17}}})
    assert small.multiplier("goal_kicks_for", 1.0) is None
    assert small.multiplier("saves_for", None) is None
    assert small.multiplier("corners_for", 1.0) is None
    # no phase is read: a count term is single
    assert small.multiplier("saves_for", 1.0, "early") == pytest.approx(
        math.exp(-0.17))


def test_the_config_is_validated() -> None:
    assert TABLE.coefficients["throw_ins_for"] == (0.0457, -0.0171)
    assert TABLE.coefficients["saves_total"] == (0.0212, 0.0)
    for bad in (
        {},
        {"markets": {"saves_for": {"beta": 1.5}}},
        {"markets": {"saves_for": {"g1": 0.1, "g2": 0.0}}},
        {"markets": {"saves_total": {"g1": 0.1}}},  # a total gives both
        {"markets": {"saves_total": {"beta": 0.1}}},
        {"markets": {"saves_for": {"beta": 0.1, "beta2": float("inf")}}},
        {"markets": {"saves_for": {"by_phase": {"early": {"beta": 0.1}}}}},
        {"markets": {"saves_for": {"beta": 0.1,
                                   "by_phase": {"early": {"beta": 0.1}}}}},
        {"markets": {"saves_for": "0.1"}},
    ):
        with pytest.raises(ValueError):
            cst.parse_table(bad)


def test_load_table_raises_on_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        cst.load_table(tmp_path / cst.CONFIG_FILE)
    (tmp_path / cst.CONFIG_FILE).write_text(json.dumps(
        {"markets": {"saves_total": {"g1": 0.02, "g2": 0.0}}}))
    assert cst.load_table(tmp_path / cst.CONFIG_FILE).multiplier(
        "saves_total", -1.0) == pytest.approx(math.exp(0.02))


def test_the_installed_file_enters_the_fingerprint_only_once_present(
        tmp_path: Path) -> None:
    before = sheet_config.fingerprint(tmp_path)
    assert cst.CONFIG_FILE in sheet_config.SHEET_OPTIONAL_FILES
    assert cst.CONFIG_FILE not in sheet_config.SHEET_CONFIG_FILES
    (tmp_path / cst.CONFIG_FILE).write_text("{}")
    assert sheet_config.fingerprint(tmp_path) != before


# --- SHEET ------------------------------------------------------------------


def _rows(market: str, subject: str, line: float,
          forecast: fr.FootballForecast | None, **kwargs: object,
          ) -> list[dict[str, object]]:
    from bet.sofa.config import SofaConfig

    values = [3.0, 4.0, 2.0, 5.0, 3.0, 4.0, 3.0, 2.0, 4.0, 3.0]
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


SHEET_CASES = (("saves_for", "Operário-PR", 3.5), ("throw_ins_for", "Criciúma", 3.5),
               ("saves_total", "", 3.5), ("shots_on_target_total", "", 3.5))


@pytest.mark.parametrize("market, subject, line", SHEET_CASES)
def test_switch_off_leaves_the_sheet_byte_for_byte(
        market: str, subject: str, line: float) -> None:
    fc = fr.FootballForecast(_book(), 1, 1, 2)
    plain = _rows(market, subject, line, fc)
    assert plain
    assert json.dumps(plain) == json.dumps(
        _rows(market, subject, line, fc, count_stretch=None))
    assert not any("COUNT_STRETCH" in n for r in plain
                   for n in r["notes"])  # type: ignore[attr-defined]


@pytest.mark.parametrize("market, subject, line", SHEET_CASES)
def test_the_stretch_multiplies_the_sample_only_centre(
        market: str, subject: str, line: float) -> None:
    fc = fr.FootballForecast(_book(), 1, 1, 2)
    s_home = fc.supremacy("side_a")
    assert s_home is not None and s_home > 0
    # a total reads the home side's s; Operário-PR is the away side
    s = -s_home if subject == "Operário-PR" else s_home
    base = _over(_rows(market, subject, line, fc))
    moved = _over(_rows(market, subject, line, fc, count_stretch=TABLE))
    mult = TABLE.multiplier(market, s)
    assert mult is not None and mult != pytest.approx(1.0)
    assert moved["centre"] == pytest.approx(
        float(base["centre"]) * mult, abs=1e-3)  # type: ignore[arg-type]
    assert any(n.startswith("COUNT_STRETCH") for n in moved["notes"])  # type: ignore[attr-defined]
    assert any("MAX_SUPREMACY" in n for n in moved["notes"]  # type: ignore[attr-defined]
               if n.startswith("UNFITTED_CONSTANTS"))


def test_the_stretch_multiplies_the_blended_centre_after_the_rating() -> None:
    # corners_1h_for rated (RATED_SCOPE_MARKETS): the blend, then the term
    fc = fr.FootballForecast(_book(), 1, 1, 2,
                             rated_scope=fr.RATED_SCOPE_MARKETS)
    s = fc.supremacy("side_a")
    assert s is not None
    base = _over(_rows("corners_1h_for", "Criciúma", 2.5, fc))
    assert any(n.startswith("FOOTBALL_RATING") for n in base["notes"])  # type: ignore[attr-defined]
    moved = _over(_rows("corners_1h_for", "Criciúma", 2.5, fc,
                        count_stretch=TABLE))
    assert moved["centre"] == pytest.approx(
        float(base["centre"]) * math.exp(0.1390 * s), abs=1e-3)  # type: ignore[arg-type]


def test_after_game_state_and_venue_prior_on_their_own_centre() -> None:
    # the count term multiplies whatever centre the earlier terms left; a
    # GAME_STATE table on another market and the venue prior do not stop it
    fc = fr.FootballForecast(_book(), 1, 1, 2)
    s = fc.supremacy("side_a")
    assert s is not None
    gs = GameStateTable({"corners_for": 0.1})
    base = _over(_rows("corners_1h_for", "Criciúma", 2.5, fc, game_state=gs,
                       venue_prior_on=True))
    moved = _over(_rows("corners_1h_for", "Criciúma", 2.5, fc, game_state=gs,
                        venue_prior_on=True, count_stretch=TABLE))
    assert any(n.startswith("VENUE_PRIOR") for n in moved["notes"])  # type: ignore[attr-defined]
    notes = [n.split(":")[0] for n in moved["notes"]]  # type: ignore[attr-defined]
    assert notes.index("VENUE_PRIOR") < notes.index("COUNT_STRETCH")
    assert moved["centre"] == pytest.approx(
        float(base["centre"]) * math.exp(0.1390 * s), abs=1e-3)  # type: ignore[arg-type]


def test_a_market_without_coefficients_or_a_fixture_without_supremacy_is_untouched(
) -> None:
    fc = fr.FootballForecast(_book(), 1, 1, 2)
    only_saves = cst.parse_table({"markets": {"saves_for": {"beta": -0.17}}})
    assert (_rows("goal_kicks_for", "Criciúma", 6.5, fc, count_stretch=only_saves)
            == _rows("goal_kicks_for", "Criciúma", 6.5, fc))
    # GAME_STATE's markets are never stretched by the count table
    assert (_rows("corners_for", "Criciúma", 4.5, fc, count_stretch=TABLE)
            == _rows("corners_for", "Criciúma", 4.5, fc))
    unrated = fr.FootballForecast(_book(), 1, 1, 12345)
    assert (_rows("saves_for", "Criciúma", 3.5, unrated, count_stretch=TABLE)
            == _rows("saves_for", "Criciúma", 3.5, unrated))


def test_sheet_stamps_the_marker_on_football_rows_only_while_on(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    field, rule, _sport = epochs.FOOTBALL_COUNT_STRETCH_MARKER
    rc, h, rows = _run(tmp_path / "off", monkeypatch, on=set(), rating_prices=True)
    assert rc == 0 and rows
    assert not any(field in r for r in rows)
    assert all(c.get("count_stretch") is None for c in h.process_calls)
    monkeypatch.setattr(epochs, "football_count_stretch", lambda d, at=None: True)
    monkeypatch.setattr(run_sheet, "load_count_stretch_table", lambda: TABLE)
    rc, h, rows = _run(tmp_path / "on", monkeypatch, on=set(), rating_prices=True)
    assert rc == 0
    assert all(c["count_stretch"] is TABLE for c in h.process_calls)
    by_sport = {r["sport"]: r for r in rows}
    assert by_sport["football"][field] == rule
    assert field not in by_sport["tennis"]
    assert epochs.sheet_has_marker(rows, epochs.FOOTBALL_COUNT_STRETCH_MARKER)


# --- rebuild_plan -----------------------------------------------------------


def test_rebuild_plan_re_runs_sheet_on_a_missing_marker(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "TENNIS_MATCH_WINNER_FROM_UTC", None)
    stale = rp.DayState(DAY, AFTER, LIMIT, sheet_count_stretch=False)
    assert "SHEET" not in rp.build_plan(stale).names()
    monkeypatch.setattr(epochs, "FOOTBALL_COUNT_STRETCH_FROM_UTC",
                        datetime(2026, 10, 18, tzinfo=UTC))
    plan = rp.build_plan(stale)
    assert "SHEET" in plan.names()
    sheet = next(s for s in plan.steps if s.name == "SHEET")
    assert "football_count_stretch" in sheet.reason
    assert "SHEET" not in rp.build_plan(rp.DayState(DAY, AFTER, LIMIT)).names()
    assert "SHEET" not in rp.build_plan(rp.DayState(
        "2026-10-17", AFTER, LIMIT, sheet_count_stretch=False)).names()


def test_observe_reads_the_marker_on_football_rows() -> None:
    marker = epochs.FOOTBALL_COUNT_STRETCH_MARKER
    assert marker in rp.AUDIT_MARKERS
    assert marker[0] in run_sheet.AUDIT_MARKER_FIELDS
    field, rule, _ = marker
    assert not epochs.sheet_has_marker([{"sport": "football"}], marker)
    assert epochs.sheet_has_marker([{"sport": "football", field: rule},
                                    {"sport": "tennis"}], marker)


# --- the replay -------------------------------------------------------------


def test_the_replay_hook_applies_the_count_stretch() -> None:
    history, played = _football()
    target = played[-3]
    rules = CentreRules(football_rating=True, count_stretch=TABLE)
    fc = FootballRatingReplay(history, rules).forecast(target)
    assert fc is not None
    sup = fc.supremacy("side_a")
    assert sup is not None
    # saves_for has no rating: the sample-only centre x the term
    got = live_centre(target, "saves_for", "side_b", 3.0, fc, (), rules)
    assert got == pytest.approx(3.0 * math.exp(-0.1693 * -sup))
    total = live_centre(target, "saves_total", None, 6.0, fc, (), rules)
    assert total == pytest.approx(6.0 * math.exp(0.0212 * abs(sup)))
    off = CentreRules(football_rating=True)
    assert live_centre(target, "saves_for", "side_b", 3.0, fc, (), off) == 3.0
    # a goals market is not the count table's
    assert live_centre(target, "goals_for", "side_a", 1.2, fc, (), rules) == (
        pytest.approx(live_centre(target, "goals_for", "side_a", 1.2, fc, (), off)))
    assert cfc.CENTRE_RULES.count_stretch is None
    assert rules.describe()["count_stretch"] == "in-memory"


def test_the_replay_flag_needs_the_rating(
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["calibrate_from_cache.py", "--count-stretch"])
    with pytest.raises(SystemExit):
        cfc.main()
    assert "--count-stretch need --football-rating" in capsys.readouterr().err


def test_every_count_stretch_market_is_a_replayed_market() -> None:
    # the replay writes a `_for` and a `_total` row per football base it
    # reads (STAT_KEYS, HALF_BASES): every stretched market is among them
    bases = set(cfc.STAT_KEYS) | set(cfc.HALF_BASES)
    for market in cst.COUNT_STRETCH_MARKETS:
        base = market.rsplit("_", 1)[0]
        assert base in bases, market


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
                              require_db_backup=False, count_stretch=True)
    with pytest.raises(pr.RefitError, match="sofa_count_stretch.json is absent"):
        pr.rebuild_cache_rows(paths, dry_run=False, confirm=True, runner=runner,
                              require_db_backup=False, football_rating=True,
                              count_stretch=True)
    (paths.config_dir / cst.CONFIG_FILE).write_text(
        json.dumps({"markets": {"saves_for": {"beta": -0.17}}}))
    report: dict[str, Any] = pr.rebuild_cache_rows(
        paths, dry_run=False, confirm=True, runner=runner,
        require_db_backup=False, football_rating=True, count_stretch=True)
    assert "--count-stretch" in seen[-1] and "--football-rating" in seen[-1]
    assert report["count_stretch"] is True
    rules = pr.read_replay_rules(paths)
    assert rules is not None and rules["flags"]["count_stretch"] is True
    args = pr.build_parser().parse_args(
        ["--date", "2026-10-18", "rebuild-cache-rows", "--count-stretch"])
    assert args.count_stretch is True


# --- the fit ----------------------------------------------------------------


def test_fit_terms_recovers_known_coefficients_in_each_form() -> None:
    s = [(i % 41 - 20) / 8 for i in range(900)]
    c = [2.0 + (i % 7) / 3 for i in range(900)]
    y = [ci * math.exp(0.05 * si - 0.02 * si * si) for ci, si in zip(c, s, strict=True)]
    b1, b2 = ss.fit_terms(False, c, s, y, 2)
    assert b1 == pytest.approx(0.05, abs=1e-6) and b2 == pytest.approx(-0.02, abs=1e-6)
    yt = [ci * math.exp(0.03 * abs(si)) for ci, si in zip(c, s, strict=True)]
    (g1,) = ss.fit_terms(True, c, s, yt, 1)
    assert g1 == pytest.approx(0.03, abs=1e-6)
    assert ss.cell_json(True, (g1,)) == {"g1": round(g1, 6), "g2": 0.0}
    assert ss.cell_json(False, (b1, b2)) == {"beta": round(b1, 6),
                                             "beta2": round(b2, 6)}
    with pytest.raises(ValueError):
        ss.fit_terms(False, c, s, y, 3)


def test_fit_rows_writes_each_market_in_its_measured_form() -> None:
    rows = []
    for i in range(600):
        s = (i % 41 - 20) / 8
        c = 2.0 + (i % 5) / 2
        rows.append(fit.StretchRow("saves_for", i, 0, "side_a", c * math.exp(-0.17 * s),
                                   c, s))
        rows.append(fit.StretchRow("throw_ins_total", i, 0, "", 40 * c * math.exp(
            0.007 * abs(s) - 0.019 * s * s), 40 * c, s))
        rows.append(fit.StretchRow("saves_total", i, 0, "", 2 * c * math.exp(
            0.02 * abs(s)), 2 * c, s))
    table = fit.fit_rows(rows, ("saves_for", "throw_ins_total", "saves_total"))
    assert table["saves_for"]["beta"] == pytest.approx(-0.17, abs=1e-5)
    assert "beta2" not in table["saves_for"]
    assert table["throw_ins_total"]["g1"] == pytest.approx(0.007, abs=1e-5)
    assert table["throw_ins_total"]["g2"] == pytest.approx(-0.019, abs=1e-5)
    assert table["saves_total"]["g2"] == 0.0
    assert table["saves_total"]["g1"] == pytest.approx(0.02, abs=1e-5)
    assert table["saves_for"]["n_rows"] == 600
    assert table["saves_for"]["n_matches"] == 600
    cst.parse_table({"markets": table})  # what it writes reads back


def test_the_fit_reads_the_counts_the_history_lacks_from_event_stats(
        tmp_path: Path) -> None:
    db = tmp_path / "sofa.db"
    migrate(str(db))
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO sofa_event_stats (sofascore_event_id, fetched_at,"
            " statistics_json, incidents_json, status_type, lineups_json)"
            " VALUES (?, '2026-10-01', ?, NULL, 'finished', NULL)",
            (7, json.dumps(_statistics({"goalkeeperSaves": 4, "throwIns": 21},
                                       {"goalkeeperSaves": 2, "throwIns": 18}))))
    history = [
        fr.FootballResult(7, 100, 1, 1, 2, {"goals_for": (1.0, 0.0),
                                            "corners_for": (5.0, 3.0)}),
        # listing-only goals: no statistics row is looked up
        fr.FootballResult(8, 200, 1, 1, 2, {"goals_for": (2.0, 2.0)}),
    ]
    assert fit.extra_metrics(cst.COUNT_STRETCH_MARKETS) == (
        "goal_kicks_for", "saves_1h_for", "saves_for", "shots_2h_for",
        "shots_on_target_2h_for", "throw_ins_for")
    out, added = fit.extend_history(history, db, ("saves_for", "throw_ins_for"))
    assert out[0].values["saves_for"] == (4.0, 2.0)
    assert out[0].values["throw_ins_for"] == (21.0, 18.0)
    assert out[0].values["corners_for"] == (5.0, 3.0)
    assert out[1] == history[1]
    assert added == {"saves_for": 1, "throw_ins_for": 1}


def test_the_walk_replays_a_shrunk_count_centre_with_the_side_s_supremacy(
) -> None:
    history, _ = _football(days=80)
    with_saves = [replace(r, values={**r.values, "saves_for": (
        3.0 + (r.event_id % 3), 2.0 + (r.event_id % 4))}) for r in history]
    k = {"saves_for": 15.0, "saves_total": 15.0, "corners_1h_for": 15.0}
    rows = list(fit.walk(with_saves, 0, 2**62, ("saves_for", "saves_total",
                                                "corners_1h_for"),
                         k, GameStateRules()))
    markets = {r.market for r in rows}
    assert markets == {"saves_for", "saves_total", "corners_1h_for"}
    by_event: dict[tuple[int, str], dict[str, fit.StretchRow]] = {}
    for r in rows:
        by_event.setdefault((r.event_id, r.market), {})[r.side] = r
    for (_eid, market), sides in by_event.items():
        if market.endswith("_for"):
            assert sides["side_a"].supremacy == pytest.approx(
                -sides["side_b"].supremacy)
        else:
            home = by_event.get((_eid, "saves_for"), {}).get("side_a")
            if home is not None:
                assert sides[""].supremacy == pytest.approx(home.supremacy)
    assert all(r.centre > 0 for r in rows)
    # the running league rate stands only from MIN_LEAGUE_MATCHES matches
    first_saves = min(r.ts for r in rows if r.market == "saves_for")
    assert sum(1 for r in history if r.ts < first_saves) >= fr.MIN_LEAGUE_MATCHES


def test_the_count_walk_reads_the_cup_book_when_given(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from bet.sofa.cup_strength import load as load_cup

    seen: list[object] = []
    real = fit.apply_cup_strength

    def spy(book: fr.RatingBook, cup: object) -> fr.RatingBook:
        seen.append(cup)
        return real(book, cup)  # type: ignore[arg-type]

    monkeypatch.setattr(fit, "apply_cup_strength", spy)
    history, _ = _football(days=10)
    cup = load_cup()
    list(fit.walk(history, 0, 2**62, ("corners_1h_for",), {}, GameStateRules(),
                  cup_strength=cup))
    list(fit.walk(history, 0, 2**62, ("corners_1h_for",), {}, GameStateRules()))
    assert seen == [cup, None]
