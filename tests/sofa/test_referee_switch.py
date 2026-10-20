"""The referee term (epochs.FOOTBALL_REFEREE, off while None;
bet.sofa.referees): off = the sheet byte for byte, on = a cards / fouls
centre x ratio ** beta after the earlier terms, no referee = multiplier 1
with referee_read NO_REFEREE, the marker, rebuild_plan's re-run, the config
and the fixture reads' cut (no look-ahead). Offline and fast."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bet.sofa import epochs
from bet.sofa import football_rating as fr
from bet.sofa import rebuild_plan as rp
from bet.sofa import referees as rf
from bet.sofa.game_state import GameStateTable
from scripts.sofa import run_sheet
from tests.sofa.test_audit_2026_10_13_b1b2 import _book
from tests.sofa.test_count_stretch import _over, _rows
from tests.sofa.test_run_sheet_wiring import _run

TABLE = rf.parse_effect_table({"markets": {
    "cards_points_for": {"family": "cards_points", "beta": 0.4, "K": 5.0},
    "cards_points_total": {"family": "cards_points", "beta": 0.4, "K": 5.0},
    "fouls_for": {"family": "fouls", "beta": 1.0, "K": 20.0},
}})
STRICT = rf.RefereeRead(77, 12, 18.0, 4.0)  # 12 matches at 1.5x the league
LIMIT = rp.timedelta(minutes=45)
DAY = "2026-10-22"
AFTER = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)


def test_the_switch_is_off_and_reads_the_day_and_the_clock(
        monkeypatch: pytest.MonkeyPatch) -> None:
    # switched on 2026-10-21 00:00Z (night 2026-10-20/21)
    assert epochs.FOOTBALL_REFEREE_FROM_UTC == datetime(2026, 10, 21, tzinfo=UTC)
    monkeypatch.setattr(epochs, "FOOTBALL_REFEREE_FROM_UTC", None)
    assert not epochs.football_referee(DAY, AFTER)
    monkeypatch.setattr(epochs, "FOOTBALL_REFEREE_FROM_UTC",
                        datetime(2026, 10, 22, tzinfo=UTC))
    assert epochs.football_referee(DAY, AFTER)
    assert not epochs.football_referee("2026-10-21", AFTER)
    assert not epochs.football_referee(DAY, datetime(2026, 10, 21, 23, tzinfo=UTC))


def test_effect_table_apply_reads_status_and_multiplier() -> None:
    assert TABLE.apply("corners_for", STRICT) is None
    mult, info = TABLE.apply("cards_points_for", None) or (0.0, {})
    assert mult == 1.0 and info == {"status": rf.NO_REFEREE}
    mult, info = TABLE.apply("cards_points_for", rf.RefereeRead(5, 0, 0.0, 4.0)) or (0.0, {})
    assert mult == 1.0 and info["status"] == rf.NO_RECORD
    mult, info = TABLE.apply("cards_points_for", STRICT) or (0.0, {})
    assert info["status"] == rf.APPLIED
    assert mult == pytest.approx(((18.0 + 5.0) / (12 + 5.0)) ** 0.4)


def test_the_config_is_validated(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        rf.parse_effect_table({"markets": {}})
    with pytest.raises(ValueError):
        rf.parse_effect_table({"markets": {"corners_for": {
            "family": "cards_points", "beta": 0.1, "K": 5}}})
    with pytest.raises(ValueError):
        rf.parse_effect_table({"markets": {"fouls_for": {
            "family": "fouls", "beta": 0.1, "K": 0}}})
    with pytest.raises(FileNotFoundError):
        rf.load_effect_table(tmp_path / "missing.json")


def test_the_installed_config_parses_when_present() -> None:
    from bet.sofa.config import config_path
    p = config_path(rf.CONFIG_FILE)
    if p.exists():
        table = rf.load_effect_table(p)
        assert all(rf.family_of(m) == c.family for m, c in table.markets.items())


def test_family_of() -> None:
    assert rf.family_of("cards_points_total") == "cards_points"
    assert rf.family_of("fouls_2h_for") == "fouls"
    assert rf.family_of("corners_for") is None
    assert rf.family_of("player_fouls_for") is None


# --- SHEET ------------------------------------------------------------------

CASES = (("cards_points_for", "Criciúma", 1.5), ("cards_points_total", "", 4.5),
         ("fouls_for", "Criciúma", 3.5))


@pytest.mark.parametrize("market, subject, line", CASES)
def test_switch_off_leaves_the_sheet_byte_for_byte(
        market: str, subject: str, line: float) -> None:
    fc = fr.FootballForecast(_book(), 1, 1, 2)
    plain = _rows(market, subject, line, fc)
    assert plain
    assert json.dumps(plain) == json.dumps(
        _rows(market, subject, line, fc, referee_effect=None,
              referee_reads={"cards_points": STRICT, "fouls": STRICT}))
    assert not any("referee" in k for r in plain for k in r)


@pytest.mark.parametrize("market, subject, line", CASES)
def test_the_term_multiplies_the_centre(market: str, subject: str, line: float) -> None:
    fc = fr.FootballForecast(_book(), 1, 1, 2)
    base = _over(_rows(market, subject, line, fc))
    reads = {"cards_points": STRICT, "fouls": STRICT}
    moved = _over(_rows(market, subject, line, fc, referee_effect=TABLE,
                        referee_reads=reads))
    cell = TABLE.markets[market]
    mult = STRICT.ratio(cell.k) ** cell.beta
    assert mult > 1.0
    assert moved["centre"] == pytest.approx(float(base["centre"]) * mult, abs=1e-3)  # type: ignore[arg-type]
    assert moved["referee_read"]["status"] == rf.APPLIED  # type: ignore[index]
    assert moved["referee_read"]["n"] == 12  # type: ignore[index]
    assert any(n.startswith("REFEREE:") for n in moved["notes"])  # type: ignore[attr-defined]
    assert any("MIN_LEAGUE_MATCHES" in n for n in moved["notes"]  # type: ignore[attr-defined]
               if n.startswith("UNFITTED_CONSTANTS"))


def test_after_game_state() -> None:
    fc = fr.FootballForecast(_book(), 1, 1, 2)
    gs = GameStateTable({"cards_points_for": -0.09})
    base = _over(_rows("cards_points_for", "Criciúma", 1.5, fc, game_state=gs))
    moved = _over(_rows("cards_points_for", "Criciúma", 1.5, fc, game_state=gs,
                        referee_effect=TABLE, referee_reads={"cards_points": STRICT}))
    notes = [n.split(":")[0] for n in moved["notes"]]  # type: ignore[attr-defined]
    assert notes.index("GAME_STATE") < notes.index("REFEREE")
    assert moved["centre"] == pytest.approx(
        float(base["centre"]) * STRICT.ratio(5.0) ** 0.4, abs=1e-3)  # type: ignore[arg-type]


def test_no_referee_is_multiplier_one_and_says_so() -> None:
    fc = fr.FootballForecast(_book(), 1, 1, 2)
    base = _over(_rows("cards_points_for", "Criciúma", 1.5, fc))
    for reads in (None, {}, {"cards_points": rf.RefereeRead(None, 0, 0.0, 4.0)}):
        moved = _over(_rows("cards_points_for", "Criciúma", 1.5, fc,
                            referee_effect=TABLE, referee_reads=reads))
        assert moved["centre"] == base["centre"]
        assert moved["p_central"] == base["p_central"]
        assert moved["referee_read"] == {"status": rf.NO_REFEREE}
    # a market outside the table carries nothing
    other = _over(_rows("corners_for", "Criciúma", 4.5, fc, referee_effect=TABLE,
                        referee_reads={"cards_points": STRICT}))
    assert "referee_read" not in other


def test_sheet_stamps_the_marker_on_football_rows_only_while_on(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    field, rule, _sport = epochs.FOOTBALL_REFEREE_MARKER
    rc, h, rows = _run(tmp_path / "off", monkeypatch, on=set(), rating_prices=True)
    assert rc == 0 and rows
    assert not any(field in r for r in rows)
    assert all(c.get("referee_effect") is None for c in h.process_calls)
    monkeypatch.setattr(epochs, "football_referee", lambda d, at=None: True)
    monkeypatch.setattr(rf, "load_effect_table", lambda path=None: TABLE)
    rc, h, rows = _run(tmp_path / "on", monkeypatch, on=set(), rating_prices=True)
    assert rc == 0
    assert all(c["referee_effect"] is TABLE for c in h.process_calls)
    by_sport = {r["sport"]: r for r in rows}
    assert by_sport["football"][field] == rule
    assert field not in by_sport["tennis"]
    assert epochs.sheet_has_marker(rows, epochs.FOOTBALL_REFEREE_MARKER)
    _ = run_sheet


def test_rebuild_plan_re_runs_sheet_on_a_missing_marker(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "FOOTBALL_REFEREE_FROM_UTC", None)
    stale = rp.DayState(DAY, AFTER, LIMIT, sheet_referee=False)
    assert not any("football_referee" in s.reason
                   for s in rp.build_plan(stale).steps if s.name == "SHEET")
    monkeypatch.setattr(epochs, "FOOTBALL_REFEREE_FROM_UTC",
                        datetime(2026, 10, 22, tzinfo=UTC))
    plan = rp.build_plan(stale)
    sheet = next(s for s in plan.steps if s.name == "SHEET")
    assert "football_referee" in sheet.reason


# --- the fixture reads: strictly before the cut -------------------------------


def _result(eid: int, ts: int, cards: tuple[float, float]) -> fr.FootballResult:
    return fr.FootballResult(eid, ts, 1, 10 + eid, 20 + eid,
                             {"cards_points_for": cards, "fouls_for": (11.0, 12.0)})


def test_fixture_reads_never_see_the_cut_or_after() -> None:
    history = [_result(i, 100 + i, (2.0, 2.0)) for i in range(rf.MIN_LEAGUE_MATCHES)]
    history += [_result(500, 1000, (4.0, 4.0)),   # referee 7, before the cut
                _result(501, 2000, (0.0, 0.0)),   # referee 7, the cut itself
                _result(502, 3000, (9.0, 9.0))]   # referee 7, after
    labels = {500: 7, 501: 7, 502: 7}
    reads = rf.fixture_reads(history, labels, 2000, {900: 7, 901: None})
    r = reads[900]["cards_points"]
    assert r.n == 1 and r.ratio_sum == pytest.approx(2.0)
    assert reads[901]["cards_points"].referee_id is None
    assert reads[900]["fouls"].n == 1
