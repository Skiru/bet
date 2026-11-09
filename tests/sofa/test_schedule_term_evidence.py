"""epochs.SCHEDULE_TERM: the line evidence of the term's keys at the corrected
p (bet.sofa.schedule_term_evidence, scripts/sofa/backfill_schedule_term_p.py,
fit_line_evidence.py, refresh_line_evidence.py step 1c) - the scope, nothing
before the switch's day, the backfill for old rows and the rows' own p from
the switch, the floor keys untouched, and the backfill's corrected p against
SHEET's own rows. Offline."""

from __future__ import annotations

import gzip
import json
from collections import Counter
from pathlib import Path
from typing import Any, cast

import pytest

from bet.sofa import epochs
from bet.sofa import line_evidence as le
from bet.sofa import schedule_term_evidence as ste
from bet.sofa.confidence import Calibration
from bet.sofa.football_sim import neutral_params
from scripts.sofa import backfill_schedule_term_p as bf
from scripts.sofa import fit_line_evidence as fle
from tests.sofa import test_schedule_term as tst

SWITCH_DAY = "2026-11-10"


@pytest.fixture(autouse=True)
def _clock_on_the_switch_day(monkeypatch: pytest.MonkeyPatch) -> None:
    """The switch reads the day and the build clock: the clock is the
    switch day's morning (the morning refresh's)."""
    monkeypatch.setenv("SOFA_NOW", "2026-11-10T06:00:00Z")


def test_scope_is_the_switch_markets_without_the_floor_keys() -> None:
    assert epochs.SCHEDULE_TERM_FROM_UTC is not None
    assert ste.first_whole_day() == SWITCH_DAY
    assert ste.markets() == epochs.SCHEDULE_TERM_MARKETS
    assert not ste.markets() & epochs.SCHEDULE_TERM_FLOOR_EXCLUDED
    assert ste.sheet_markets() | ste.sim_markets() == ste.markets()
    assert not ste.sheet_markets() & epochs.FOOTBALL_SIM_MARKETS
    assert ste.sim_markets() == (epochs.FOOTBALL_SIM_MARKETS
                                 - epochs.SCHEDULE_TERM_FLOOR_EXCLUDED)
    assert ste.ours("result_1x2|OVER") and ste.ours("women:double_chance|OVER")
    for key in ("htft|OVER", "btts_halves|OVER", "goals_total|OVER",
                "women:corners_total|UNDER", "__sport__"):
        assert not ste.ours(key), key


def _row(market: str, *, eid: int = 1, p: float = 0.7, sport: str = "football",
         subject: str = "1", line: float = 0.5, direction: str = "OVER",
         outcome: str = "WIN") -> dict[str, Any]:
    return {"sport": sport, "market": market, "sofascore_event_id": eid,
            "subject": subject, "line": line, "direction": direction,
            "p_central": p, "offered_odds": 1.5, "outcome": outcome}


def _bfill(**sheet: float) -> ste.Backfill:
    return ste.Backfill(sheet=dict(sheet))


def test_evidence_p_old_rows_from_the_backfill_new_rows_their_own() -> None:
    old, new = "2026-11-08", SWITCH_DAY
    r = _row("result_1x2", p=0.7)
    key = ste.sheet_key(old, 1, "result_1x2", "1", 0.5, "OVER")
    table = _bfill(**{key: 0.66})
    assert ste.evidence_p(r, old, table) == (True, 0.66)
    assert ste.evidence_p(r, new, table) == (True, 0.7)  # own (corrected) p
    # an old row the table does not hold: no evidence, never the stored p
    assert ste.evidence_p(_row("result_1x2", eid=2), old, table) == (True, None)
    # out of scope: another market, a floor key, another sport
    for row in (_row("corners_total"), _row("btts_halves", subject="Tak/Tak"),
                _row("result_1x2", sport="tennis")):
        assert ste.evidence_p(row, old, table) == (False, None)
    # a mixed switch day reads the backfill for its rows too: the live switch
    # was moved by the operator into 2026-11-09 at 11:30Z, so the first whole
    # day is 11-10; a 00:00Z start is its own day
    assert ste.first_whole_day() == SWITCH_DAY
    assert ste.first_whole_day(epochs.SCHEDULE_TERM_FROM_UTC.replace(hour=17)) == (
        "2026-11-10")
    assert ste.first_whole_day(epochs.SCHEDULE_TERM_FROM_UTC.replace(
        day=10, hour=0, minute=0)) == "2026-11-10"


def test_simulator_lines_floor_keys_untouched_in_scope_corrected() -> None:
    lines = [{"day": "2026-10-20", "eid": 5, "market": "htft", "subject": "1/1",
              "direction": "OVER", "p": 0.4, "y": 1, "odds": 2.5},
             {"day": "2026-10-20", "eid": 5, "market": "result_1h", "subject": "1",
              "direction": "OVER", "p": 0.5, "y": 0, "odds": 2.0},
             {"day": "2026-10-20", "eid": 5, "market": "btts_any_half", "subject": "",
              "direction": "UNDER", "p": 0.45, "y": 1, "odds": 2.1}]
    table = ste.Backfill(sim_lines={
        ste.sim_line_key("2026-10-20", 5, "htft", "1/1", "OVER"): 0.38})
    got = list(ste.sim_lines(lines, table))
    assert [(g["market"], g["p"]) for g in got] == [("htft", 0.38),
                                                     ("btts_any_half", 0.45)]
    assert got[1] == lines[2]


def test_nothing_is_read_before_the_switch_day(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any, **_k: Any) -> None:
        raise AssertionError("read before the switch")

    monkeypatch.setattr(ste, "load_backfill", boom)
    assert fle.schedule_term_backfill("2026-11-08") is None
    monkeypatch.setattr(ste, "load_backfill", lambda *a, **k: _bfill(x=0.5))
    got = fle.schedule_term_backfill(SWITCH_DAY)
    assert got is not None and dict(got.sheet) == {"x": 0.5}


def test_a_missing_table_warns_and_keeps_the_rows(
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(ste, "BACKFILL", Path("/nonexistent/schedule_term_p.json.gz"))
    assert fle.schedule_term_backfill(SWITCH_DAY) is None
    assert "WARN schedule_term" in capsys.readouterr().err


def test_backfill_file_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "t.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump({"schema": ste.SCHEMA, "sheet": {"a": 0.5}, "sim_lines": {"b": 0.25},
                   "built_through": "2026-11-08"}, fh)
    got = ste.load_backfill(path)
    assert got is not None and len(got) == 2
    assert got.meta["built_through"] == "2026-11-08"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump({"schema": 99}, fh)
    with pytest.raises(ValueError):
        ste.load_backfill(path)


# --- fit_line_evidence --------------------------------------------------------------


class _Curve:
    """Calibration stand-in: the confidence is the p itself."""

    def realised(self, _m: str, p: float, *_a: Any, **_k: Any) -> tuple[float, int]:
        return p, 1000


ROWS = [_row("result_1x2", eid=1, p=0.80), _row("result_1x2", eid=2, p=0.75),
        _row("corners_total", eid=1, p=0.72, subject="", line=9.5),
        _row("btts_halves", eid=1, p=0.71, subject="Nie/Nie"),
        _row("htft", eid=1, p=0.73, subject="1/1")]
OLD, NEW = "2026-11-08", SWITCH_DAY


def _runs(tmp_path: Path) -> Path:
    for day in (OLD, NEW):
        d = tmp_path / day
        d.mkdir(parents=True)
        (d / "02_fixtures.json").write_text(json.dumps(
            [{"sofascore_event_id": 1, "competition_name": "Liga"},
             {"sofascore_event_id": 2, "competition_name": "Liga"}]))
        (d / "07_settled.json").write_text(json.dumps(ROWS))
    return tmp_path


TABLE = _bfill(**{ste.sheet_key(OLD, 1, "result_1x2", "1", 0.5, "OVER"): 0.70,
                  ste.sheet_key(OLD, 1, "htft", "1/1", 0.5, "OVER"): 0.60})


def _read(runs: Path, scope: frozenset[str], only: bool = False
          ) -> list[tuple[str, str, float]]:
    cal = cast(Calibration, _Curve())
    return [(str(r["game"]), str(r["key"]), float(r["p"]))
            for r in fle.sheet_rows(runs, [OLD, NEW], cal,
                                    p_for=fle.schedule_term_p_for(TABLE, scope),
                                    only_scoped=only)]


def test_sheet_rows_old_from_the_backfill_new_own_others_as_stored(
        tmp_path: Path) -> None:
    runs = _runs(tmp_path)
    plain = [(str(r["game"]), str(r["key"]), float(r["p"]))
             for r in fle.sheet_rows(runs, [OLD, NEW], cast(Calibration, _Curve()))]
    got = _read(runs, ste.sheet_markets())
    want = []
    for game, key, p in plain:
        if key == "result_1x2|OVER" and game == f"{OLD}:1":
            want.append((game, key, 0.70))  # the backfill's corrected p
        elif key == "result_1x2|OVER" and game == f"{OLD}:2":
            continue  # not in the table: no evidence
        else:
            want.append((game, key, p))  # own p (new day) or out of scope
    assert got == want
    # the in-scope rows alone
    assert _read(runs, ste.sheet_markets(), only=True) == [
        (f"{OLD}:1", "result_1x2|OVER", 0.70),
        (f"{NEW}:1", "result_1x2|OVER", 0.80), (f"{NEW}:2", "result_1x2|OVER", 0.75)]
    # the simulator's scope: htft corrected, its floor key never
    sim = _read(runs, ste.sim_markets(), only=True)
    assert (f"{OLD}:1", "htft|OVER", 0.60) in sim
    assert not [k for _, k, _ in sim if k.startswith("btts_halves")]


def test_the_merge_moves_only_the_in_scope_keys(tmp_path: Path) -> None:
    runs = _runs(tmp_path)
    cal = cast(Calibration, _Curve())
    fitted = le.fit(fle.sheet_rows(runs, [OLD, NEW], cal))
    before = json.loads(json.dumps(fitted))
    fle.apply_schedule_term(fitted, fle.sheet_rows(
        runs, [OLD, NEW], cal,
        p_for=fle.schedule_term_p_for(TABLE, ste.sheet_markets()), only_scoped=True))
    sport = "football"
    for key in before["keys"][sport]:
        if key != "result_1x2|OVER":
            assert fitted["keys"][sport][key] == before["keys"][sport][key], key
    assert fitted["keys"][sport]["result_1x2|OVER"]["n"] == 3  # one old row dropped
    assert before["keys"][sport]["result_1x2|OVER"]["n"] == 4
    for name in ("sport_printable", "sport_printable_by_gap", "design_effect"):
        assert fitted[name] == before[name], name
    for key, cells in before["bands"][sport].items():
        if key != "result_1x2|OVER":
            assert fitted["bands"][sport][key] == cells, key


# --- the backfill against SHEET's own rows -------------------------------------------


def test_backfill_corrected_p_equals_sheets_corrected_rows(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """process_fixture's rows without the term, re-priced by the backfill at
    the term, equal process_fixture's rows with it (the sheet path: NB
    arithmetic within the notes' 3-dp rounding; the simulator within its
    paths)."""
    th, ta = -0.08, 0.06
    term = tst._applied(th, ta)
    off = tst._sheet(None)
    on = {tst._key(r): r for r in tst._sheet(term)}
    monkeypatch.setattr(bf, "SIMS", 1000)  # the test's SimPricer
    want = {ste.sheet_key("2026-11-08", r["sofascore_event_id"], r["market"],
                          r["subject"], r["line"], r["direction"]): r
            for r in off if r["market"] in ste.markets()}
    assert {r["market"] for r in want.values()} >= {
        "double_chance", "result_1x2", "draw_no_bet", "result_or_over",
        "first_goal", "htft"}
    counts: Counter[str] = Counter()
    got = bf.price_day("2026-11-08", want, off, lambda _d, _e: term,
                       neutral_params(), 1, counts, {})
    assert set(got) == set(want), counts
    for key, r in want.items():
        sheet = on[tst._key(r)]
        tol = 2e-3 if r["market"] in epochs.FOOTBALL_SIM_MARKETS else 1.5e-4
        assert abs(got[key] - sheet["p_central"]) <= tol, (key, got[key], sheet)
        assert got[key] != r["p_central"], key  # the term moved it
    # the floor key is never priced
    assert not [k for k in got if "|btts_any_half|" in k]


def test_a_zero_term_keeps_the_rows_p() -> None:
    off = tst._sheet(None)
    zero = tst._applied(0.0, 0.0)
    want = {ste.sheet_key("2026-11-08", r["sofascore_event_id"], r["market"],
                          r["subject"], r["line"], r["direction"]): r
            for r in off if r["market"] in ste.markets()}
    got = bf.price_day("2026-11-08", want, [], lambda _d, _e: zero, None, 1,
                       Counter(), {})
    assert got == {k: r["p_central"] for k, r in want.items()}


def test_a_row_sheet_priced_under_the_switch_is_never_corrected_twice() -> None:
    """A mixed day (the switch moved into 2026-11-09 at 11:30Z): a settled
    row that carries p_central_no_schedule_term was priced by SHEET under the
    switch - its own p_central is the corrected p, whatever the term."""
    off = tst._sheet(None)
    moved = tst._applied(0.05, -0.04)
    want = {ste.sheet_key("2026-11-09", r["sofascore_event_id"], r["market"],
                          r["subject"], r["line"], r["direction"]):
            {**r, "p_central_no_schedule_term": 0.5}
            for r in off if r["market"] in ste.markets()}
    assert want
    counts: Counter[str] = Counter()
    got = bf.price_day("2026-11-09", want, [], lambda _d, _e: moved, None, 1,
                       counts, {})
    assert got == {k: r["p_central"] for k, r in want.items()}
    assert counts["sheet:own_corrected"] == len(want)


def test_backfill_days_stop_at_the_switch_and_the_day(tmp_path: Path) -> None:
    for day in ("2026-10-12", "2026-10-14", "2026-11-09", SWITCH_DAY):
        (tmp_path / day).mkdir()
        (tmp_path / day / "07_settled.json").write_text("[]")
        (tmp_path / day / "05_sheet.json").write_text("[]")
    assert bf.days_to_read(tmp_path, "2026-11-12", SWITCH_DAY, {}) == [
        "2026-10-14", "2026-11-09"]
    assert bf.days_to_read(tmp_path, "2026-11-09", SWITCH_DAY, {}) == ["2026-10-14"]
    seen = {"2026-10-14": bf._fingerprint(tmp_path / "2026-10-14" / "07_settled.json")}
    assert bf.days_to_read(tmp_path, "2026-11-12", SWITCH_DAY, seen) == ["2026-11-09"]
    assert bf.days_to_read(tmp_path, "2026-11-12", None, {}) == []


def test_refresh_runs_the_backfill_only_under_the_switch() -> None:
    from scripts.sofa import refresh_line_evidence as rle

    assert not rle.schedule_term_step("2026-11-08", False)
    assert rle.schedule_term_step("2026-11-09", False)  # the mixed switch day
    assert rle.schedule_term_step(SWITCH_DAY, False)
    assert not rle.schedule_term_step(SWITCH_DAY, True)  # never in a dry run
    cmd = rle.schedule_term_command(SWITCH_DAY)
    assert cmd[1:] == ["scripts/sofa/backfill_schedule_term_p.py", "--before",
                       SWITCH_DAY]
