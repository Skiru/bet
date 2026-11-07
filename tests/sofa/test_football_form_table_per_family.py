"""epochs.FOOTBALL_FORM_TABLE per family (coordinator 2026-11-06, report
docs/sofa/evidence/refit_replay_2026-11-05.md section 12): SHEET prices a
football fixture on the book without the season table and on the book with
it; a row of a family in FOOTBALL_FORM_TABLE_FAMILIES takes the table run's
row, every other row the no-table run's. Offline."""

from __future__ import annotations

from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa.contracts import GapReason, SheetRow
from scripts.sofa import run_sheet as rs


def _row(market: str, direction: str, p: float, line: float = 1.5,
         subject: str = "A") -> SheetRow:
    return SheetRow.model_construct(
        sport="football", market=market, subject=subject, line=line,
        direction=direction, p_central=p)


class _Rung:
    def __init__(self, market: str, subject: str, line: float) -> None:
        self.market, self.subject, self.line = market, subject, line


@pytest.fixture
def families(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "FOOTBALL_FORM_TABLE_FAMILIES",
                        frozenset({"goals_2h_total|OVER", "corners_for|UNDER"}))


def test_the_family_is_market_and_direction(families: None) -> None:
    assert epochs.football_form_table_family("goals_2h_total", "OVER")
    assert not epochs.football_form_table_family("goals_2h_total", "UNDER")
    assert not epochs.football_form_table_family("cards_points_for", "UNDER")


def test_the_list_is_empty_and_the_switch_off_until_the_gate_passes() -> None:
    # set together with FOOTBALL_FORM_TABLE_FROM_UTC only after the full gate
    # against the 11-07 file (report section 12)
    if epochs.FOOTBALL_FORM_TABLE_FROM_UTC is None:
        assert epochs.FOOTBALL_FORM_TABLE_FAMILIES == frozenset()
    else:
        assert epochs.FOOTBALL_FORM_TABLE_FAMILIES


def test_each_row_comes_from_its_familys_run(families: None) -> None:
    plain = [_row("goals_2h_total", "OVER", 0.60), _row("goals_2h_total", "UNDER", 0.40),
             _row("cards_points_for", "UNDER", 0.70), _row("corners_for", "UNDER", 0.55)]
    table = [_row("goals_2h_total", "OVER", 0.66), _row("goals_2h_total", "UNDER", 0.34),
             _row("cards_points_for", "UNDER", 0.80), _row("corners_for", "UNDER", 0.52)]
    out, _ = rs.merge_form_table_rows(plain, [], table)
    got = {(r.market, r.direction): r.p_central for r in out}
    assert got == {("goals_2h_total", "OVER"): 0.66,      # table family
                   ("goals_2h_total", "UNDER"): 0.40,     # its other side is not
                   ("cards_points_for", "UNDER"): 0.70,   # cards stay off the table
                   ("corners_for", "UNDER"): 0.52}
    # the no-table run's order
    assert [(r.market, r.direction) for r in out] == [
        (r.market, r.direction) for r in plain]


def test_a_table_family_follows_the_table_run_only(families: None) -> None:
    plain = [_row("goals_2h_total", "OVER", 0.60, line=2.5)]
    table = [_row("goals_2h_total", "OVER", 0.66, line=1.5)]
    skipped: list[tuple[Any, GapReason, str]] = [
        (_Rung("goals_2h_total", "A", 1.5), GapReason.NOT_RATED, "x"),
        (_Rung("cards_points_for", "A", 1.5), GapReason.NOT_RATED, "y")]
    out, kept = rs.merge_form_table_rows(plain, skipped, table)
    # 2.5 priced only without the table: no row; 1.5 priced only with it: kept
    assert [(r.line, r.p_central) for r in out] == [(1.5, 0.66)]
    # skips per (market, direction): 1.5 UNDER (not a table family) is still
    # unpriced, so its no-table record stays; 2.5 OVER dropped by the merge
    # gets its own record (audit 2026-11-07)
    assert [(s[0].market, s[0].line, s[2].split(":")[0]) for s in kept] == [
        ("goals_2h_total", 1.5, "x"), ("cards_points_for", 1.5, "y"),
        ("goals_2h_total", 2.5, rs.FORM_TABLE_RUN_NOT_PRICED)]


def test_no_families_is_the_no_table_sheet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "FOOTBALL_FORM_TABLE_FAMILIES", frozenset())
    plain = [_row("goals_for", "OVER", 0.6)]
    out, _ = rs.merge_form_table_rows(plain, [], [_row("goals_for", "OVER", 0.9)])
    assert out == plain


def test_the_replay_walks_a_plain_book_beside_the_table_one() -> None:
    from scripts.sofa import calibrate_from_cache as cfc
    per = cfc.CentreRules(football_rating=True, form_table=True,
                          form_table_families=frozenset({"goals_2h_for|UNDER"}))
    plain = cfc._plain_rules(per)
    assert not plain.form_table and not plain.form_table_families
    assert per.describe()["form_table_families"] == ["goals_2h_for|UNDER"]
    # --form-table alone: every row on the table book (a measurement arm)
    whole = cfc.CentreRules(football_rating=True, form_table=True)
    assert cfc._plain_rules(whole) is whole


def test_the_staged_curves_of_11_07_change_only_table_families() -> None:
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "config"
    path = root / "sofa_confidence_calibration.next.2026-11-07.json"
    if not path.exists():
        pytest.skip("no 11-07 staged file")
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["effective_from"] == "2026-11-07T00:00:00Z"
    assert doc["staged_change"]["effective_from"] == doc["effective_from"]
    for _sec, key in doc["staged_change"]["form_table_families_refit"]:
        assert key in epochs.FOOTBALL_FORM_TABLE_FAMILIES
