"""The football player shots stretch (epochs.FOOTBALL_PLAYER_STRETCH, off
while None; bet.sofa.player_stretch over bet.sofa.supremacy_stretch): a
footballer's shots centre x exp(beta x s), s his own side's expected goal
difference, in SHEET and in the cache replay's player rows, with its row
marker, rebuild_plan's re-run, the replay flag, the config and the fit.
Offline and fast."""

from __future__ import annotations

import json
import math
import sqlite3
import statistics
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import epochs, sheet_config
from bet.sofa import football_rating as fr
from bet.sofa import player_stretch as pst
from bet.sofa import rebuild_plan as rp
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import FixtureOffer
from bet.sofa.engine import sheet_count_p_raw, sheet_predictive_sd, winning_boundary
from bet.sofa.game_state import MAX_SUPREMACY
from scripts.sofa import calibrate_from_cache as cfc
from scripts.sofa import fit_player_stretch as fit
from scripts.sofa import prepare_refit as pr
from scripts.sofa import run_sheet
from scripts.sofa.run_sheet import process_fixture, sheet_row_json
from tests.sofa.test_audit_2026_10_13_b1b2 import _book
from tests.sofa.test_cache_replay_player_markets import (
    KOWALSKI_SHOTS,
    LADDER,
)
from tests.sofa.test_cache_replay_player_markets import (
    _fixture as _cache_fixture,
)
from tests.sofa.test_player_markets import _fixture, _player_samples, _rung
from tests.sofa.test_prepare_refit import _db, _fake_calibrate, _paths
from tests.sofa.test_run_sheet_wiring import _run

TABLE = pst.parse_table({"markets": {
    "player_shots_for": {"beta": 0.126},
    "player_shots_on_target_for": {"beta": 0.117}}})
LIMIT = rp.timedelta(minutes=45)
DAY = "2026-10-18"
AFTER = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)
SHOTS = [3.0, 2.0, 4.0, 1.0, 3.0, 2.0, 5.0, 2.0, 3.0, 2.0]


# --- the switch, the multiplier, the config ---------------------------------


def test_the_switch_is_off_and_reads_the_day_and_the_clock(
        monkeypatch: pytest.MonkeyPatch) -> None:
    assert epochs.FOOTBALL_PLAYER_STRETCH_FROM_UTC is None
    assert not epochs.football_player_stretch(
        "2027-01-01", datetime(2027, 1, 1, tzinfo=UTC))
    monkeypatch.setattr(epochs, "FOOTBALL_PLAYER_STRETCH_FROM_UTC",
                        datetime(2026, 10, 18, tzinfo=UTC))
    assert epochs.football_player_stretch(
        "2026-10-18", datetime(2026, 10, 18, 1, tzinfo=UTC))
    assert not epochs.football_player_stretch("2026-10-17", AFTER)
    assert not epochs.football_player_stretch(
        "2026-10-18", datetime(2026, 10, 17, 23, tzinfo=UTC))
    assert epochs.FOOTBALL_PLAYER_STRETCH_MARKER == (
        "player_stretch_rule", "player_stretch_v1", "football")


def test_the_multiplier_reads_exp_beta_s_capped() -> None:
    assert TABLE.multiplier("player_shots_for", 1.0) == pytest.approx(
        math.exp(0.126))
    assert TABLE.multiplier("player_shots_on_target_for", -1.0) == pytest.approx(
        math.exp(-0.117))
    assert TABLE.multiplier("player_shots_for", 7.0) == pytest.approx(
        math.exp(0.126 * MAX_SUPREMACY))
    assert TABLE.multiplier("player_fouls_for", 1.0) is None
    assert TABLE.multiplier("player_shots_for", None) is None


def test_the_config_is_validated() -> None:
    assert pst.PLAYER_STRETCH_MARKETS == (
        "player_shots_for", "player_shots_on_target_for")
    for bad in (
        {},
        # not the shot-detail markets, not the other player markets
        {"markets": {"player_left_foot_shots_for": {"beta": 0.1}}},
        {"markets": {"player_fouls_for": {"beta": 0.1}}},
        {"markets": {"player_shots_for": {"beta": 1.2}}},
        {"markets": {"player_shots_for": {"beta": 0.1, "beta2": 0.01}}},
        {"markets": {"player_shots_for": {"g1": 0.1, "g2": 0.0}}},
        {"markets": {"player_shots_for": {"by_phase": {"early": {"beta": 0.1}}}}},
    ):
        with pytest.raises(ValueError):
            pst.parse_table(bad)


def test_load_table_raises_on_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        pst.load_table(tmp_path / pst.CONFIG_FILE)
    (tmp_path / pst.CONFIG_FILE).write_text(json.dumps(
        {"markets": {"player_shots_for": {"beta": 0.1}}}))
    assert pst.load_table(tmp_path / pst.CONFIG_FILE).multiplier(
        "player_shots_for", 2.0) == pytest.approx(math.exp(0.2))


def test_the_installed_file_enters_the_fingerprint_only_once_present(
        tmp_path: Path) -> None:
    before = sheet_config.fingerprint(tmp_path)
    assert pst.CONFIG_FILE in sheet_config.SHEET_OPTIONAL_FILES
    assert pst.CONFIG_FILE not in sheet_config.SHEET_CONFIG_FILES
    (tmp_path / pst.CONFIG_FILE).write_text("{}")
    assert sheet_config.fingerprint(tmp_path) != before


# --- SHEET ------------------------------------------------------------------


def _player_rows(forecast: fr.FootballForecast | None, side: str = "side_a",
                 market: str = "player_shots_for",
                 **kwargs: object) -> list[dict[str, object]]:
    samples = _player_samples(SHOTS)
    sample = samples.players["player_shots_for|Romarinho"]
    sample = sample.model_copy(update={"side": side, "metric": market})
    samples = samples.model_copy(update={"players": {
        f"{market}|Romarinho": sample}})
    offer = FixtureOffer(sofascore_event_id=1, status="PRICED",
                         rungs=[_rung(market, "Romarinho", 2.5, over=2.6)],
                         unmapped_markets=[])
    rows, _ = process_fixture(
        _fixture(), samples, offer, baselines={}, reliability={},
        engine_constants={}, vetoes=[], config=SofaConfig(), football=forecast,
        stats_only=True, **kwargs,  # type: ignore[arg-type]
    )
    return [sheet_row_json(r) for r in rows]


def _over(rows: list[dict[str, object]]) -> dict[str, object]:
    return next(r for r in rows if r["direction"] == "OVER")


def test_switch_off_leaves_the_player_row_byte_for_byte() -> None:
    fc = fr.FootballForecast(_book(), 1, 1, 2)
    plain = _player_rows(fc)
    assert plain
    assert json.dumps(plain) == json.dumps(_player_rows(fc, player_stretch=None))
    assert not any("PLAYER_STRETCH" in n for r in plain
                   for n in r["notes"])  # type: ignore[attr-defined]


@pytest.mark.parametrize("side", ["side_a", "side_b"])
def test_the_stretch_reads_his_own_side_s_supremacy(side: str) -> None:
    fc = fr.FootballForecast(_book(), 1, 1, 2)
    s = fc.supremacy(side)
    assert s is not None and s != 0
    base = _over(_player_rows(fc, side))
    moved = _over(_player_rows(fc, side, player_stretch=TABLE))
    assert float(base["centre"]) == pytest.approx(statistics.mean(SHOTS))  # type: ignore[arg-type]
    assert moved["centre"] == pytest.approx(
        statistics.mean(SHOTS) * math.exp(0.126 * s), abs=1e-3)
    # the favourite's striker (home here) shoots more, the outsider's less
    assert (float(moved["centre"]) > float(base["centre"])) == (s > 0)  # type: ignore[arg-type]
    assert moved["p_central"] != base["p_central"]
    assert any(n.startswith("PLAYER_STRETCH") for n in moved["notes"])  # type: ignore[attr-defined]
    assert any("MAX_SUPREMACY" in n for n in moved["notes"]  # type: ignore[attr-defined]
               if n.startswith("UNFITTED_CONSTANTS"))


def test_no_forecast_another_player_market_or_no_rating_is_untouched() -> None:
    fc = fr.FootballForecast(_book(), 1, 1, 2)
    assert (_player_rows(None, player_stretch=TABLE) == _player_rows(None))
    only_sot = pst.parse_table({"markets": {
        "player_shots_on_target_for": {"beta": 0.117}}})
    assert (_player_rows(fc, player_stretch=only_sot) == _player_rows(fc))
    unrated = fr.FootballForecast(_book(), 1, 1, 12345)
    assert (_player_rows(unrated, player_stretch=TABLE) == _player_rows(unrated))


def test_sheet_stamps_the_marker_on_football_rows_only_while_on(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    field, rule, _sport = epochs.FOOTBALL_PLAYER_STRETCH_MARKER
    rc, h, rows = _run(tmp_path / "off", monkeypatch, on=set(), rating_prices=True)
    assert rc == 0 and rows
    assert not any(field in r for r in rows)
    assert all(c.get("player_stretch") is None for c in h.process_calls)
    monkeypatch.setattr(epochs, "football_player_stretch", lambda d, at=None: True)
    monkeypatch.setattr(run_sheet, "load_player_stretch_table", lambda: TABLE)
    rc, h, rows = _run(tmp_path / "on", monkeypatch, on=set(), rating_prices=True)
    assert rc == 0
    assert all(c["player_stretch"] is TABLE for c in h.process_calls)
    by_sport = {r["sport"]: r for r in rows}
    assert by_sport["football"][field] == rule
    assert field not in by_sport["tennis"]
    assert epochs.sheet_has_marker(rows, epochs.FOOTBALL_PLAYER_STRETCH_MARKER)


# --- rebuild_plan -----------------------------------------------------------


def test_rebuild_plan_re_runs_sheet_on_a_missing_marker(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "TENNIS_MATCH_WINNER_FROM_UTC", None)
    stale = rp.DayState(DAY, AFTER, LIMIT, sheet_player_stretch=False)
    assert "SHEET" not in rp.build_plan(stale).names()
    monkeypatch.setattr(epochs, "FOOTBALL_PLAYER_STRETCH_FROM_UTC",
                        datetime(2026, 10, 18, tzinfo=UTC))
    plan = rp.build_plan(stale)
    sheet = next(s for s in plan.steps if s.name == "SHEET")
    assert "football_player_stretch" in sheet.reason
    assert "SHEET" not in rp.build_plan(rp.DayState(DAY, AFTER, LIMIT)).names()
    assert "SHEET" not in rp.build_plan(rp.DayState(
        "2026-10-17", AFTER, LIMIT, sheet_player_stretch=False)).names()


def test_observe_reads_the_marker_on_football_rows() -> None:
    marker = epochs.FOOTBALL_PLAYER_STRETCH_MARKER
    assert marker in rp.AUDIT_MARKERS
    assert marker[0] in run_sheet.AUDIT_MARKER_FIELDS


# --- the replay -------------------------------------------------------------


class _Forecast:
    def __init__(self, s_home: float) -> None:
        self.s = s_home

    def supremacy(self, side: str) -> float:
        return self.s if side == "side_a" else -self.s


class _Football:
    """A rating replay stub: s_home per event id, the calls in order."""

    def __init__(self, by_home: dict[int, float]) -> None:
        self.by_home = by_home
        self.calls: list[int] = []

    def forecast_fixture(self, competition_id: int, home_id: int, away_id: int,
                         kickoff_ts: int) -> _Forecast:
        self.calls.append(kickoff_ts)
        return _Forecast(0.8 if home_id == 1 else 0.0)


def test_target_supremacy_reads_the_targets_in_kickoff_order() -> None:
    football = _Football({})
    targets = [
        {"id": 3, "startTimestamp": 300, "homeTeam": {"id": 1}, "awayTeam": {"id": 2},
         "tournament": {"uniqueTournament": {"id": 17}}},
        {"id": 1, "startTimestamp": 100, "homeTeam": {"id": 5}, "awayTeam": {"id": 1},
         "tournament": {"uniqueTournament": {"id": 17}}},
        {"id": 2, "startTimestamp": 200, "homeTeam": {"id": 1}, "awayTeam": {"id": 2},
         "tournament": {}},  # no competition: no entry
    ]
    out = cfc.target_supremacy(targets, football)  # type: ignore[arg-type]
    assert football.calls == [100, 300]
    assert out == {1: {True: 0.0, False: -0.0}, 3: {True: 0.8, False: -0.8}}


def _player_replay(tmp_path: Path, **kw: Any) -> list[cfc.SettledRow]:
    tmp_path.mkdir()
    cache = _cache_fixture(tmp_path)
    cache.index()
    rows, _ = cfc.build_player_rows(cache.db, LADDER, sample_n=10, min_sample=5,
                                    **kw)
    return [r for r in rows if r.event_id == 999]


def test_the_replay_prices_the_player_centre_with_his_side_s_term(
        tmp_path: Path) -> None:
    plain = _player_replay(tmp_path / "a")
    off = _player_replay(tmp_path / "b", player_stretch=None)
    assert plain == off
    football = _Football({})
    moved = _player_replay(tmp_path / "c", player_stretch=TABLE,
                           football=football)
    # fouls are not stretched; Kowalski's (HOME = team 1, s_home 0.8) shots are
    assert ([r for r in moved if r.market == "player_fouls_for"]
            == [r for r in plain if r.market == "player_fouls_for"])
    shots = {(r.line, r.direction): r.p_central for r in moved
             if r.market == "player_shots_for"}
    sample = [float(v) for v in KOWALSKI_SHOTS]
    mean = statistics.mean(sample)
    centre = mean * math.exp(0.126 * 0.8)
    sd = sheet_predictive_sd("player_shots_for", "football", mean,
                             statistics.variance(sample), len(sample), centre)
    for (line, direction), p in shots.items():
        assert p == pytest.approx(round(sheet_count_p_raw(
            "player_shots_for", centre, sd, winning_boundary(line, direction),
            direction), 6))
    assert shots != {(r.line, r.direction): r.p_central for r in plain
                     if r.market == "player_shots_for"}
    with pytest.raises(ValueError, match="football rating replay"):
        _player_replay(tmp_path / "d", player_stretch=TABLE)


def test_main_runs_the_player_replay_with_its_own_book(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs = tmp_path / "runs"
    (runs / "2026-10-01").mkdir(parents=True)
    (runs / "2026-10-01" / "04_offer.json").write_text(json.dumps([{
        "sofascore_event_id": 999,
        "rungs": [{"market": m, "line": x} for m, xs in LADDER.items() for x in xs]}]))
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / pst.CONFIG_FILE).write_text(json.dumps(
        {"markets": {"player_shots_for": {"beta": 0.126}}}))
    seen: list[Any] = []

    def sup(targets: Any, football: Any) -> dict[int, dict[bool, float | None]]:
        seen.append(football)
        return {999: {True: 0.8, False: -0.8}}

    monkeypatch.setattr(cfc, "target_supremacy", sup)
    monkeypatch.setenv("SOFA_CONFIG_DIR", str(config_dir))
    out = {}
    for name, extra in (("off", []), ("on", ["--player-stretch"])):
        where = tmp_path / name
        where.mkdir()
        _cache_fixture(where).index()
        monkeypatch.setattr(cfc, "CENTRE_RULES", cfc.CentreRules())
        monkeypatch.setattr(sys, "argv", [
            "calibrate_from_cache", "--db-path", str(where / "sofa.db"),
            "--runs-dir", str(runs), "--players", "only", "--football-rating",
            *extra])
        assert cfc.main() == 0
        with sqlite3.connect(where / "sofa.db") as conn:
            out[name] = conn.execute(
                "SELECT market, subject, line, direction, p_central FROM "
                "sofa_settled_row WHERE sofascore_event_id = 999 "
                "ORDER BY market, subject, line, direction").fetchall()
    assert len(seen) == 1 and isinstance(seen[0], cfc.FootballRatingReplay)
    fouls = [r for r in out["on"] if r[0] == "player_fouls_for"]
    assert fouls == [r for r in out["off"] if r[0] == "player_fouls_for"]
    assert ([r for r in out["on"] if r[0] == "player_shots_for"]
            != [r for r in out["off"] if r[0] == "player_shots_for"])


def test_the_replay_flag_needs_the_rating(
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["calibrate_from_cache.py", "--player-stretch"])
    with pytest.raises(SystemExit):
        cfc.main()
    assert "--player-stretch need --football-rating" in capsys.readouterr().err


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
                              require_db_backup=False, player_stretch=True)
    with pytest.raises(pr.RefitError, match="sofa_player_stretch.json is absent"):
        pr.rebuild_cache_rows(paths, dry_run=False, confirm=True, runner=runner,
                              require_db_backup=False, football_rating=True,
                              player_stretch=True)
    (paths.config_dir / pst.CONFIG_FILE).write_text(
        json.dumps({"markets": {"player_shots_for": {"beta": 0.126}}}))
    report: dict[str, Any] = pr.rebuild_cache_rows(
        paths, dry_run=False, confirm=True, runner=runner,
        require_db_backup=False, football_rating=True, player_stretch=True)
    assert "--player-stretch" in seen[-1] and "--football-rating" in seen[-1]
    assert report["player_stretch"] is True
    rules = pr.read_replay_rules(paths)
    assert rules is not None and rules["flags"]["player_stretch"] is True
    args = pr.build_parser().parse_args(
        ["--date", "2026-10-18", "rebuild-cache-rows", "--player-stretch"])
    assert args.player_stretch is True


# --- the fit ----------------------------------------------------------------


def test_fit_observations_recovers_known_beta_and_drops_unrated_sides() -> None:
    obs = []
    sup: dict[int, dict[bool, float | None]] = {}
    for i in range(800):
        s = (i % 41 - 20) / 8
        sup[i] = {True: s, False: None}
        c = 1.0 + (i % 6) / 2
        obs.append(fit.PlayerObs(i, 0, True, "player_shots_for", c,
                                 c * math.exp(0.126 * s)))
        obs.append(fit.PlayerObs(i, 0, False, "player_shots_for", c, 99.0))
    table = fit.fit_observations(obs, sup, ("player_shots_for",
                                            "player_shots_on_target_for"))
    assert table["player_shots_for"]["beta"] == pytest.approx(0.126, abs=1e-5)
    assert table["player_shots_for"]["n_rows"] == 800
    assert table["player_shots_on_target_for"] == {
        "beta": 0.0, "n_rows": 0, "n_matches": 0}
    pst.parse_table({"markets": table})


def test_collect_reads_one_observation_per_priced_sample(tmp_path: Path) -> None:
    cache = _cache_fixture(tmp_path)
    cache.index()
    obs, events = fit.collect(cache.db, ("player_shots_for",), None,
                              2**40, sample_n=10, min_sample=5)
    target = [o for o in obs if o.event_id == 999]
    assert [(o.metric, o.is_home) for o in target] == [("player_shots_for", True)]
    assert target[0].centre == pytest.approx(statistics.mean(KOWALSKI_SHOTS))
    assert target[0].y == 3.0
    assert 999 in events
    # the window is the kickoff's
    late, _ = fit.collect(cache.db, ("player_shots_for",), None,
                          int(events[999]["startTimestamp"]), sample_n=10,
                          min_sample=5)
    assert all(o.event_id != 999 for o in late)


def test_the_fit_book_reads_the_epochs_as_of_before_and_the_cup_list(
        monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, datetime | None]] = []

    def link(date: str, at: datetime | None = None) -> bool:
        seen.append((date, at))
        return True

    monkeypatch.setattr(fit.epochs, "link_shared_league", link)
    rules = fit.book_rules("2026-10-17", None, False)
    assert seen == [("2026-10-16", datetime(2026, 10, 17, tzinfo=UTC))]
    assert rules.cup_strength is not None and rules.cup_strength.competitions
    assert rules.cup_strength_path == "config/sofa_cup_strength.json"
    plain = fit.book_rules("2026-10-17", None, True)
    assert plain.cup_strength is None and plain.cup_strength_path is None


def test_target_supremacy_skips_a_target_without_a_kickoff() -> None:
    football = _Football({})
    targets = [
        {"id": 4, "homeTeam": {"id": 1}, "awayTeam": {"id": 2},
         "tournament": {"uniqueTournament": {"id": 17}}},
        {"id": 5, "startTimestamp": None, "homeTeam": {"id": 1},
         "awayTeam": {"id": 2}, "tournament": {"uniqueTournament": {"id": 17}}},
        {"id": 6, "startTimestamp": 50, "homeTeam": {"id": 1},
         "awayTeam": {"id": 2}, "tournament": {"uniqueTournament": {"id": 17}}},
    ]
    assert cfc.target_supremacy(targets, football) == {  # type: ignore[arg-type]
        6: {True: 0.8, False: -0.8}}
    assert football.calls == [50]
