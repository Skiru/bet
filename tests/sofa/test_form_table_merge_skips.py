"""run_sheet.merge_form_table_rows keeps a skip record for every rung the
FOOTBALL_FORM_TABLE per-family merge leaves unpriced, per (market,
direction), and the table run's own reasons (audit 2026-11-07). Counts only:
no priced row's p changes. Offline."""

from __future__ import annotations

from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa.contracts import GapReason, SheetRow
from scripts.sofa import run_sheet as rs

Skip = tuple[Any, GapReason, str]


def _row(market: str, direction: str, p: float, line: float = 1.5) -> SheetRow:
    return SheetRow.model_construct(
        sport="football", market=market, subject="A", line=line,
        direction=direction, p_central=p)


class _Rung:
    def __init__(self, market: str, line: float, over: float | None = 1.8,
                 under: float | None = 1.9) -> None:
        self.market, self.subject, self.line = market, "A", line
        self.over_odds, self.under_odds = over, under


@pytest.fixture(autouse=True)
def families(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "FOOTBALL_FORM_TABLE_FAMILIES",
                        frozenset({"goals_2h_total|OVER"}))


def _keys(kept: list[Skip]) -> list[tuple[str, float, GapReason, str]]:
    return [(s[0].market, s[0].line, s[1], s[2].split(":")[0]) for s in kept]


def test_a_rung_only_the_no_table_run_priced_gets_a_record() -> None:
    plain = [_row("goals_2h_total", "OVER", 0.6), _row("goals_2h_total", "UNDER", 0.4)]
    out, kept = rs.merge_form_table_rows(plain, [], [])
    assert [(r.direction, r.p_central) for r in out] == [("UNDER", 0.4)]
    assert _keys(kept) == [("goals_2h_total", 1.5, GapReason.NOT_RATED,
                            rs.FORM_TABLE_RUN_NOT_PRICED)]


def test_the_table_runs_own_reason_is_kept_for_a_table_family() -> None:
    plain = [_row("goals_2h_total", "OVER", 0.6), _row("goals_2h_total", "UNDER", 0.4)]
    t_skip: list[Skip] = [(_Rung("goals_2h_total", 1.5), GapReason.THIN_SAMPLE, "t"),
                          (_Rung("cards_points_for", 1.5), GapReason.NOT_RATED, "z")]
    out, kept = rs.merge_form_table_rows(plain, [], [], t_skip)
    assert [(r.direction, r.p_central) for r in out] == [("UNDER", 0.4)]
    # the table run's reason, no synthetic one beside it; a non-table rung's
    # table skip is not the sheet's
    assert _keys(kept) == [("goals_2h_total", 1.5, GapReason.THIN_SAMPLE, "t")]


def test_skips_follow_the_direction() -> None:
    # no-table run skipped the rung, table run priced both sides: OVER is the
    # table's, UNDER (not a family) stays unpriced -> the record stays
    skipped: list[Skip] = [(_Rung("goals_2h_total", 1.5), GapReason.NOT_RATED, "x")]
    table = [_row("goals_2h_total", "OVER", 0.66),
             _row("goals_2h_total", "UNDER", 0.34)]
    out, kept = rs.merge_form_table_rows([], skipped, table)
    assert [(r.direction, r.p_central) for r in out] == [("OVER", 0.66)]
    assert _keys(kept) == [("goals_2h_total", 1.5, GapReason.NOT_RATED, "x")]
    # a one-sided rung (OVER only quoted) priced by the table: nothing left
    one_sided: list[Skip] = [(_Rung("goals_2h_total", 1.5, under=None),
                              GapReason.NOT_RATED, "x")]
    _, kept = rs.merge_form_table_rows([], one_sided, table)
    assert kept == []


def test_priced_rows_are_unchanged_by_the_skip_bookkeeping() -> None:
    plain = [_row("goals_2h_total", "OVER", 0.6), _row("goals_2h_total", "UNDER", 0.4),
             _row("corners_total", "OVER", 0.7, line=9.5)]
    table = [_row("goals_2h_total", "OVER", 0.66), _row("corners_total", "OVER", 0.9,
                                                       line=9.5)]
    t_skip: list[Skip] = [(_Rung("goals_2h_total", 2.5), GapReason.THIN_SAMPLE, "t")]
    with_skips, _ = rs.merge_form_table_rows(plain, [], table, t_skip)
    without, _ = rs.merge_form_table_rows(plain, [], table)
    assert [(r.market, r.direction, r.p_central) for r in with_skips] == [
        (r.market, r.direction, r.p_central) for r in without] == [
        ("goals_2h_total", "OVER", 0.66), ("goals_2h_total", "UNDER", 0.4),
        ("corners_total", "OVER", 0.7)]
