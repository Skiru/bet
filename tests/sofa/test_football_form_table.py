"""epochs.FOOTBALL_FORM_TABLE (item 5 of the refit 2026-11-05, frozen rules
in docs/sofa/evidence/refit_replay_2026-11-05.md section 6): the football
goals rating's step x1.25 and the goals centres moved by the season table as
of the match. Off, every book is the old one; on, the table counts only what
the book learnt, and the replays (cache replay, result-market fits) carry
the same book. Offline."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from bet.sofa import epochs
from bet.sofa import football_rating as fr
from bet.sofa import rebuild_plan as rp
from scripts.sofa import calibrate_from_cache as cfc
from scripts.sofa import fit_double_chance_curve as dc_fit
from scripts.sofa import prepare_refit as pr
from tests.sofa.test_refit_replay_switch_guard import _cfg, _staged


def _history() -> list[fr.FootballResult]:
    """Six sides of one league and season; side 1 wins every match."""
    out = []
    eid = 0
    for rnd in range(12):
        for h, a in ((1, 2), (3, 4), (5, 6), (2, 3), (4, 5), (6, 1)):
            if rnd % 2:
                h, a = a, h
            eid += 1
            gh, ga = (2.0, 1.0)
            if a == 1:
                gh, ga = 0.0, 2.0
            elif h != 1:
                gh, ga = 1.0, 1.0
            out.append(fr.FootballResult(
                eid, 1_000_000 + eid * 3600, 17, h, a,
                {"goals_for": (gh, ga), "goals_1h_for": (gh / 2, ga / 2)},
                season_id=99))
    return out


def test_the_switch_is_on_from_11_07_per_family() -> None:
    # per family from 2026-11-07 00:00Z (report section 12, moved from 11-09
    # by the operator): 11-06 (mixed at 17:30Z already) and every earlier day
    # never read the table, at any clock
    late = datetime(2026, 11, 12, tzinfo=UTC)
    assert not epochs.football_form_table("2026-11-06", late)
    assert not epochs.football_form_table(
        "2026-11-07", datetime(2026, 11, 6, 23, 59, tzinfo=UTC))
    assert epochs.football_form_table("2026-11-07", late)
    assert epochs.FOOTBALL_FORM_TABLE_FAMILIES
    # the families the measured damage sits in stay off the table
    for hurt in ("cards_points_for|UNDER", "cards_points_total|UNDER",
                 "goals_for|OVER", "goals_1h_for|OVER", "most_goals|OVER"):
        assert hurt not in epochs.FOOTBALL_FORM_TABLE_FAMILIES


def test_off_the_book_is_the_old_one() -> None:
    hist = _history()
    a = fr.replay(hist, 10**10)
    b = fr.replay(hist, 10**10, form_table=False)
    assert a.season_table is None and b.season_table is None
    fa = fr.FootballForecast(a, 17, 1, 2).centre("goals_for", "side_a")
    fb = fr.FootballForecast(b, 17, 1, 2).centre("goals_for", "side_a")
    assert fa == fb


def test_on_the_leader_moves_up_and_the_step_is_faster() -> None:
    hist = _history()
    off = fr.replay(hist, 10**10)
    on = fr.replay(hist, 10**10, form_table=True)
    assert on.alpha_override == fr.FORM_TABLE_ALPHA
    assert on.season_table is not None
    # every match learnt is in the table, once per side
    games = sum(r.games for r in on.season_table.rows[(17, 99)].values())
    assert games == 2 * len(hist)
    # the step alone: a book with only the faster step differs from off
    step_only = fr.RatingBook()
    step_only.alpha_override.update(fr.FORM_TABLE_ALPHA)
    for r in hist:
        step_only.update(r)
    c_off = fr.FootballForecast(off, 17, 1, 2).centre("goals_for", "side_a")
    c_step = fr.FootballForecast(step_only, 17, 1, 2).centre("goals_for", "side_a")
    c_on = fr.FootballForecast(on, 17, 1, 2).centre("goals_for", "side_a")
    assert c_off is not None and c_step is not None and c_on is not None
    assert c_step[0] != c_off[0]
    # side 1 leads the table: the table moves its centre above the step's
    assert c_on[0] > c_step[0]
    assert "season table d" in c_on[1]
    # the opponent's centre goes down
    a_step = fr.FootballForecast(step_only, 17, 1, 2).centre("goals_for", "side_b")
    a_on = fr.FootballForecast(on, 17, 1, 2).centre("goals_for", "side_b")
    assert a_step is not None and a_on is not None and a_on[0] < a_step[0]
    # a metric outside FORM_TABLE_METRICS is never moved by the table
    assert "goals_2h_for" not in fr.FORM_TABLE_METRICS


def test_the_table_is_as_of_the_cut() -> None:
    hist = _history()
    cut = hist[20].ts
    book = fr.replay(hist, cut, form_table=True)
    assert book.season_table is not None
    games = sum(r.games for r in book.season_table.rows[(17, 99)].values())
    assert games == 2 * sum(1 for r in hist if r.ts < cut)


def test_a_result_without_a_season_is_not_in_the_table() -> None:
    book = fr.enable_form_table(fr.RatingBook())
    book.update(replace(_history()[0], season_id=None))
    assert book.season_table is not None and not book.season_table.rows


def test_the_cache_replay_and_the_result_fits_carry_the_book(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rules = cfc.CentreRules(football_rating=True, form_table=True)
    rp = cfc.FootballRatingReplay(_history(), rules)
    assert rp.book.season_table is not None
    assert rp.book.alpha_override == fr.FORM_TABLE_ALPHA
    assert rules.describe()["form_table"] is True
    assert cfc.FootballRatingReplay(
        _history(), cfc.CentreRules(football_rating=True)).book.season_table is None
    monkeypatch.setattr(dc_fit, "CUP", None)
    dc_fit.set_form_table(False)
    off = dc_fit.replay(_history(), 1_000_000 + 40 * 3600, 10**10)
    dc_fit.set_form_table(True)
    try:
        on = dc_fit.replay(_history(), 1_000_000 + 40 * 3600, 10**10)
    finally:
        dc_fit.set_form_table(False)
    assert [m.event_id for m in on] == [m.event_id for m in off]
    leader = [(m.lh, n.lh) for m, n in zip(on, off, strict=True)
              if m.event_id == on[-1].event_id]
    assert leader and leader[0][0] != leader[0][1]


def test_a_refit_replay_without_the_table_is_refused_once_it_is_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    on = {"closeness_stretch": True, "player_coverage": True,
          "awarded_excluded": True, "referee": True, "player_share": True,
          "sample_conflict_cut": True, "tennis_score_winner": True}
    eve = datetime(2026, 11, 6, 22, 0, tzinfo=UTC)
    monkeypatch.setattr(epochs, "FOOTBALL_FORM_TABLE_FROM_UTC", None)
    refusals, _ = pr.replay_switch_gaps(_staged(**on), at=eve,
                                        config_dir=_cfg(tmp_path))
    assert not any("FOOTBALL_FORM_TABLE" in r for r in refusals)
    monkeypatch.setattr(epochs, "FOOTBALL_FORM_TABLE_FROM_UTC",
                        datetime(2026, 11, 7, tzinfo=UTC))
    refusals, _ = pr.replay_switch_gaps(_staged(**on), at=eve,
                                        config_dir=_cfg(tmp_path))
    assert any(r.startswith("FOOTBALL_FORM_TABLE is on") for r in refusals)
    # every row on the table book (the measurement arm) is not SHEET's rule
    refusals, _ = pr.replay_switch_gaps(_staged(**on, form_table=True), at=eve,
                                        config_dir=_cfg(tmp_path))
    assert any(r.startswith("FOOTBALL_FORM_TABLE is on") for r in refusals)
    refusals, _ = pr.replay_switch_gaps(
        _staged(**on, form_table_per_family=True), at=eve,
        config_dir=_cfg(tmp_path))
    assert not any("FOOTBALL_FORM_TABLE" in r for r in refusals)
    args = pr.build_parser().parse_args(
        ["--date", "2026-11-07", "rebuild-cache-rows", "--form-table",
         "--form-table-per-family"])
    assert args.form_table and args.form_table_per_family


def test_rebuild_plan_re_runs_sheet_on_a_missing_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    day, after = "2026-11-07", datetime(2026, 11, 7, 9, 0, tzinfo=UTC)
    stale = rp.DayState(day, after, timedelta(minutes=45), sheet_form_table=False)
    monkeypatch.setattr(epochs, "FOOTBALL_FORM_TABLE_FROM_UTC", None)
    assert not any("football_form_table" in s.reason
                   for s in rp.build_plan(stale).steps if s.name == "SHEET")
    monkeypatch.setattr(epochs, "FOOTBALL_FORM_TABLE_FROM_UTC",
                        datetime(2026, 11, 7, tzinfo=UTC))
    sheet = next(s for s in rp.build_plan(stale).steps if s.name == "SHEET")
    assert "football_form_table" in sheet.reason
    assert epochs.FOOTBALL_FORM_TABLE_MARKER in rp.AUDIT_MARKERS
