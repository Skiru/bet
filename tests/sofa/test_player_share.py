"""The footballer share model (epochs.FOOTBALL_PLAYER_SHARE, off while None;
bet.sofa.player_share): a footballer's shots / SOT centre is his shrunk share
of his side's volume over his starts x his side's team centre today (SHEET's
team row), x his shrunk accuracy for SOT - the arithmetic, the config, SHEET
(off byte for byte, the team row first, the rows back in the offer's order,
no team row = the old centre), the marker, rebuild_plan's re-run and the
measurement's config writer. Offline and fast."""

from __future__ import annotations

import gzip
import json
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bet.sofa import epochs, sheet_config
from bet.sofa import football_rating as fr
from bet.sofa import player_share as psh
from bet.sofa import player_stretch as pst
from bet.sofa import rebuild_plan as rp
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import FixtureOffer, MetricSample, Observation
from scripts.sofa import measure_player_share as mps
from scripts.sofa import run_sheet
from scripts.sofa.run_sheet import process_fixture, sheet_row_json
from tests.sofa.test_audit_2026_10_13_b1b2 import _book
from tests.sofa.test_player_markets import _fixture, _player_samples, _rung
from tests.sofa.test_run_sheet_wiring import _run

TABLE = psh.parse_table({"markets": {
    "player_shots_for": {"m": 40.0, "prior_share": {"*": 0.09, "F": 0.16}},
    "player_shots_on_target_for": {
        "m": 40.0, "prior_share": {"*": 0.10},
        "m_accuracy": 40.0, "prior_accuracy": {"*": 0.38}},
    "player_fouls_for": {"m": 80.0, "prior_share": {"*": 0.085}}}})
STRETCH = pst.parse_table({"markets": {"player_shots_for": {"beta": 0.126}}})
SHOTS = [3.0, 2.0, 4.0, 1.0, 3.0, 2.0, 5.0, 2.0, 3.0, 2.0]
SOT = [1.0, 1.0, 2.0, 0.0, 1.0, 0.0, 2.0, 1.0, 1.0, 0.0]
TEAM = [12.0, 10.0, 14.0, 9.0, 11.0, 10.0, 15.0, 8.0, 12.0, 9.0]
LIMIT = rp.timedelta(minutes=45)
DAY = "2026-10-21"
AFTER = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)


# --- arithmetic and config ------------------------------------------------------


def test_share_centre_shrinks_his_share_to_the_prior_and_scales_the_side() -> None:
    raw = psh.share_centre(his_volume=27, team_volume=110, team_centre=12.0,
                           prior_share=0.09, m=0.0)
    assert raw == pytest.approx(27 / 110 * 12.0)
    shrunk = psh.share_centre(his_volume=27, team_volume=110, team_centre=12.0,
                              prior_share=0.09, m=40.0)
    assert shrunk == pytest.approx((27 + 40 * 0.09) / 150 * 12.0)
    # nothing seen: the prior share alone
    assert psh.share_centre(his_volume=0, team_volume=0, team_centre=10.0,
                            prior_share=0.1, m=0.0) == pytest.approx(1.0)
    # SOT: x (his SOT + m_acc x prior) / (his shots + m_acc)
    sot = psh.share_centre(his_volume=27, team_volume=110, team_centre=12.0,
                           prior_share=0.09, m=40.0, his_count=9,
                           prior_accuracy=0.38, m_accuracy=40.0)
    assert sot == pytest.approx(shrunk * (9 + 40 * 0.38) / (27 + 40))


def test_share_inputs_sum_only_the_matches_every_list_knows() -> None:
    got = psh.share_inputs([(1, 2.0), (2, 1.0), (3, 4.0)],
                           [(1, 10.0), (3, 12.0), (4, 9.0)])
    assert (got.his_volume, got.team_volume, got.matches, got.his_count) == (
        6.0, 22.0, 2, None)
    got = psh.share_inputs([(1, 2.0), (2, 1.0), (3, 4.0)],
                           [(1, 10.0), (2, 8.0), (3, 12.0)],
                           [(1, 1.0), (3, 2.0)])
    assert (got.his_volume, got.team_volume, got.matches, got.his_count) == (
        6.0, 22.0, 2, 3.0)


def test_the_config_is_validated(tmp_path: Path) -> None:
    for bad in (
        {},
        {"markets": {"player_assists_for": {"m": 1, "prior_share": {"*": 0.1}}}},
        {"markets": {"player_shots_for": {"m": -1, "prior_share": {"*": 0.1}}}},
        {"markets": {"player_shots_for": {"m": 1, "prior_share": {"F": 0.1}}}},
        {"markets": {"player_shots_for": {"m": 1, "prior_share": {"*": 1.5}}}},
        # SOT needs its accuracy
        {"markets": {"player_shots_on_target_for": {
            "m": 1, "prior_share": {"*": 0.1}}}},
    ):
        with pytest.raises(ValueError):
            psh.parse_table(bad)
    cell = TABLE.cell("player_shots_for")
    assert cell is not None
    assert cell.share_prior("F") == 0.16 and cell.share_prior(None) == 0.09
    assert cell.share_prior("D") == 0.09 and cell.accuracy_prior("F") is None
    with pytest.raises(FileNotFoundError):
        psh.load_table(tmp_path / psh.CONFIG_FILE)


def test_the_file_enters_the_fingerprint_only_once_present(tmp_path: Path) -> None:
    before = sheet_config.fingerprint(tmp_path)
    assert psh.CONFIG_FILE in sheet_config.SHEET_OPTIONAL_FILES
    (tmp_path / psh.CONFIG_FILE).write_text("{}")
    assert sheet_config.fingerprint(tmp_path) != before


def test_the_switch_is_off_and_reads_the_day_and_the_clock(
        monkeypatch: pytest.MonkeyPatch) -> None:
    # switched on 2026-10-21 00:00Z (night 2026-10-20/21)
    assert epochs.FOOTBALL_PLAYER_SHARE_FROM_UTC == datetime(2026, 10, 21, tzinfo=UTC)
    monkeypatch.setattr(epochs, "FOOTBALL_PLAYER_SHARE_FROM_UTC", None)
    assert not epochs.football_player_share("2027-01-01",
                                            datetime(2027, 1, 1, tzinfo=UTC))
    monkeypatch.setattr(epochs, "FOOTBALL_PLAYER_SHARE_FROM_UTC",
                        datetime(2026, 10, 21, tzinfo=UTC))
    assert epochs.football_player_share(DAY, AFTER)
    assert not epochs.football_player_share("2026-10-20", AFTER)
    assert not epochs.football_player_share(DAY, datetime(2026, 10, 20, 23, tzinfo=UTC))
    assert epochs.FOOTBALL_PLAYER_SHARE_MARKER == (
        "player_share_rule", "player_share_v1", "football")


# --- SHEET ------------------------------------------------------------------


def _obs(values: list[float], start: int = 1000) -> list[Observation]:
    return [Observation(sofascore_event_id=start + i,
                        match_date_utc=datetime(2026, 9, 1 + i, tzinfo=UTC),
                        opponent=f"Opp{i}", value=v, minutes=90.0,
                        competition_id=1, season_id=1, venue="home")
            for i, v in enumerate(values)]


def _samples(team: bool = True, sot: bool = False) -> object:
    samples = _player_samples(SHOTS)
    players = dict(samples.players)
    if sot:
        shots = players["player_shots_for|Romarinho"]
        players["player_shots_on_target_for|Romarinho"] = shots.model_copy(
            update={"metric": "player_shots_on_target_for",
                    "observations": _obs(SOT)})
    metrics = ({"shots_for": MetricSample(metric="shots_for", side_a=_obs(TEAM),
                                          side_b=_obs(TEAM, 2000), h2h=[])}
               if team else {})
    return samples.model_copy(update={"players": players, "metrics": metrics})


def _rows(*, team_rung: bool = True, team_sample: bool = True,
          market: str = "player_shots_for", **kwargs: object
          ) -> tuple[list[dict[str, object]], list[tuple[object, ...]]]:
    rungs = [_rung(market, "Romarinho", 0.5, over=1.3)]  # the player first
    if team_rung:
        rungs.append(_rung("shots_for", "Criciúma", 10.5, over=1.9))
    offer = FixtureOffer(sofascore_event_id=1, status="PRICED", rungs=rungs,
                         unmapped_markets=[])
    rows, skipped = process_fixture(
        _fixture(), _samples(team_sample, sot=market != "player_shots_for"),  # type: ignore[arg-type]
        offer, baselines={}, reliability={}, engine_constants={}, vetoes=[],
        config=SofaConfig(), stats_only=True, **kwargs,  # type: ignore[arg-type]
    )
    return [sheet_row_json(r) for r in rows], list(skipped)


def _over(rows: list[dict[str, object]], market: str) -> dict[str, object]:
    return next(r for r in rows if r["direction"] == "OVER" and r["market"] == market)


def test_switch_off_is_byte_for_byte() -> None:
    plain, skipped = _rows()
    assert plain
    off, off_skipped = _rows(player_share=None)
    assert json.dumps(plain) == json.dumps(off)
    assert repr(skipped) == repr(off_skipped)
    assert not any("PLAYER_SHARE" in n for r in plain for n in r["notes"])  # type: ignore[attr-defined]
    assert not any("player_share_rule" in r for r in plain)


def test_the_player_centre_is_his_share_of_the_team_row_s_centre() -> None:
    off, _ = _rows()
    on, _ = _rows(player_share=TABLE)
    team = _over(on, "shots_for")
    assert team == _over(off, "shots_for")  # the team row is untouched
    t = float(team["centre"])  # type: ignore[arg-type]
    assert t == pytest.approx(statistics.mean(TEAM), abs=1e-3)
    player = _over(on, "player_shots_for")
    want = (sum(SHOTS) + 40 * 0.09) / (sum(TEAM) + 40) * t
    assert player["centre"] == pytest.approx(want, abs=1e-3)
    assert player["p_central"] != _over(off, "player_shots_for")["p_central"]
    assert any(str(n).startswith("PLAYER_SHARE: centre") for n in player["notes"])  # type: ignore[attr-defined]
    # the rows come back in the offer's order (the player rung was first)
    assert [r["market"] for r in on] == [r["market"] for r in off]


def test_sot_carries_the_shrunk_accuracy() -> None:
    on, _ = _rows(player_share=TABLE, market="player_shots_on_target_for")
    t = statistics.mean(TEAM)
    share = (sum(SHOTS) + 40 * 0.10) / (sum(TEAM) + 40)
    acc = (sum(SOT) + 40 * 0.38) / (sum(SHOTS) + 40)
    assert _over(on, "player_shots_on_target_for")["centre"] == pytest.approx(
        share * t * acc, abs=1e-3)


def test_fouls_are_his_share_of_his_side_s_fouls_for_centre() -> None:
    fouls = [2.0, 1.0, 0.0, 3.0, 1.0, 2.0, 1.0, 0.0, 2.0, 1.0]
    team = [11.0, 13.0, 9.0, 14.0, 12.0, 10.0, 12.0, 11.0, 13.0, 10.0]
    samples = _samples(team=False)
    players = dict(samples.players)  # type: ignore[attr-defined]
    players["player_fouls_for|Romarinho"] = players[
        "player_shots_for|Romarinho"].model_copy(
        update={"metric": "player_fouls_for", "observations": _obs(fouls)})
    samples = samples.model_copy(update={  # type: ignore[attr-defined]
        "players": players,
        "metrics": {"fouls_for": MetricSample(metric="fouls_for", side_a=_obs(team),
                                              side_b=_obs(team, 2000), h2h=[])}})
    offer = FixtureOffer(sofascore_event_id=1, status="PRICED", rungs=[
        _rung("player_fouls_for", "Romarinho", 0.5, over=1.4),
        _rung("fouls_for", "Criciúma", 11.5, over=1.9)], unmapped_markets=[])

    def run(table: psh.ShareTable | None) -> list[dict[str, object]]:
        rows, _ = process_fixture(
            _fixture(), samples, offer, baselines={}, reliability={},  # type: ignore[arg-type]
            engine_constants={}, vetoes=[], config=SofaConfig(), stats_only=True,
            player_share=table)
        return [sheet_row_json(r) for r in rows]

    off, on = run(None), run(TABLE)
    t = float(_over(on, "fouls_for")["centre"])  # type: ignore[arg-type]
    assert _over(on, "fouls_for") == _over(off, "fouls_for")
    want = (sum(fouls) + 80 * 0.085) / (sum(team) + 80) * t
    player = _over(on, "player_fouls_for")
    assert player["centre"] == pytest.approx(want, abs=1e-3)
    assert player["centre"] != _over(off, "player_fouls_for")["centre"]
    assert any("fouls_for centre" in str(n) for n in player["notes"])  # type: ignore[attr-defined]


def test_no_team_row_or_no_team_sample_keeps_the_old_centre_and_says_so() -> None:
    for kw in ({"team_rung": False}, {"team_sample": False}):
        off, _ = _rows(**kw)  # type: ignore[arg-type]
        on, _ = _rows(player_share=TABLE, **kw)  # type: ignore[arg-type]
        a, b = _over(off, "player_shots_for"), _over(on, "player_shots_for")
        assert a["centre"] == b["centre"] and a["p_central"] == b["p_central"]
        assert any(str(n).startswith("PLAYER_SHARE:") and "own sample" in str(n)
                   for n in b["notes"])  # type: ignore[attr-defined]


def test_a_shared_centre_skips_the_player_stretch() -> None:
    fc = fr.FootballForecast(_book(), 1, 1, 2)
    stretched, _ = _rows(football=fc, player_stretch=STRETCH)
    assert any(str(n).startswith("PLAYER_STRETCH")
               for n in _over(stretched, "player_shots_for")["notes"])  # type: ignore[attr-defined]
    shared, _ = _rows(football=fc, player_stretch=STRETCH, player_share=TABLE)
    notes = _over(shared, "player_shots_for")["notes"]
    assert not any(str(n).startswith("PLAYER_STRETCH") for n in notes)  # type: ignore[attr-defined]
    assert any(str(n).startswith("PLAYER_SHARE: centre") for n in notes)  # type: ignore[attr-defined]


def test_a_tennis_fixture_ignores_the_table() -> None:
    fixture = _fixture().model_copy(update={"sport": "tennis"})
    offer = FixtureOffer(sofascore_event_id=1, status="PRICED", unmapped_markets=[],
                         rungs=[_rung("player_shots_for", "Romarinho", 0.5)])
    a, _ = process_fixture(fixture, _samples(), offer, baselines={},  # type: ignore[arg-type]
                           reliability={}, engine_constants={}, vetoes=[],
                           config=SofaConfig(), stats_only=True)
    b, _ = process_fixture(fixture, _samples(), offer, baselines={},  # type: ignore[arg-type]
                           reliability={}, engine_constants={}, vetoes=[],
                           config=SofaConfig(), stats_only=True, player_share=TABLE)
    assert [sheet_row_json(r) for r in a] == [sheet_row_json(r) for r in b]


def test_sheet_stamps_the_marker_on_football_rows_only_while_on(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    field, rule, _sport = epochs.FOOTBALL_PLAYER_SHARE_MARKER
    rc, h, rows = _run(tmp_path / "off", monkeypatch, on=set(), rating_prices=True)
    assert rc == 0 and rows
    assert not any(field in r for r in rows)
    assert all(c.get("player_share") is None for c in h.process_calls)
    monkeypatch.setattr(epochs, "football_player_share", lambda d, at=None: True)
    monkeypatch.setattr(run_sheet.psh, "load_table", lambda: TABLE)
    rc, h, rows = _run(tmp_path / "on", monkeypatch, on=set(), rating_prices=True)
    assert rc == 0
    assert all(c["player_share"] is TABLE for c in h.process_calls)
    by_sport = {r["sport"]: r for r in rows}
    assert by_sport["football"][field] == rule
    assert field not in by_sport["tennis"]


def test_rebuild_plan_re_runs_sheet_on_a_missing_marker(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "TENNIS_MATCH_WINNER_FROM_UTC", None)
    monkeypatch.setattr(epochs, "FOOTBALL_PLAYER_SHARE_FROM_UTC", None)
    stale = rp.DayState(DAY, AFTER, LIMIT, sheet_player_share=False)
    assert "SHEET" not in rp.build_plan(stale).names()
    monkeypatch.setattr(epochs, "FOOTBALL_PLAYER_SHARE_FROM_UTC",
                        datetime(2026, 10, 21, tzinfo=UTC))
    sheet = next(s for s in rp.build_plan(stale).steps if s.name == "SHEET")
    assert "football_player_share" in sheet.reason
    assert "SHEET" not in rp.build_plan(rp.DayState(DAY, AFTER, LIMIT)).names()
    marker = epochs.FOOTBALL_PLAYER_SHARE_MARKER
    assert marker in rp.AUDIT_MARKERS
    assert marker[0] in run_sheet.AUDIT_MARKER_FIELDS


# --- the measurement's config writer ---------------------------------------


def test_analyse_writes_a_config_sheet_can_read(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    feats = tmp_path / "f.jsonl.gz"
    with gzip.open(feats, "wt") as fh:
        for i in range(60):
            for metric in ("player_shots_for", "player_shots_on_target_for"):
                fh.write(json.dumps({
                    "ts": 1_760_000_000 + i * 86400 * 5, "ev": i, "c": 1, "m": metric,
                    "n": 6, "mean": 1.5, "var": 1.2, "ca": 1.6, "y": float(i % 4),
                    "pos": "F" if i % 2 else "M", "hv": 9.0, "tv": 70.0, "k": 6,
                    "sv": 3.0 if metric != "player_shots_for" else None,
                    "T": 12.0}) + "\n")
    out = tmp_path / "staged" / psh.CONFIG_FILE
    monkeypatch.setattr(mps, "GRID_M", (0.0, 40.0))
    monkeypatch.setattr(mps, "GRID_M_ACC", (0.0, 40.0))
    monkeypatch.setattr(sys, "argv", [
        "measure_player_share.py", "analyse", "--features", str(feats),
        "--split", "2026-01-01", "--markets", "player_shots_for",
        "player_shots_on_target_for", "--write-config", str(out)])
    assert mps.main() == 0
    table = psh.load_table(out)
    cell = table.cell("player_shots_on_target_for")
    assert cell is not None and cell.m_accuracy is not None
    assert set(table.markets) == {"player_shots_for", "player_shots_on_target_for"}
