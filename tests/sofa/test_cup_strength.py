"""League strength learnt in international club cups
(epochs.FOOTBALL_CUP_STRENGTH_FROM_UTC, bet.sofa.cup_strength): the book's
per-(domestic competition, metric) correction, its switch, the SHEET marker
and rebuild_plan's re-run, the replay flag. Off = the book as it was.
Offline and fast."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import cup_strength, epochs
from bet.sofa import football_rating as fr
from bet.sofa import rebuild_plan as rp
from scripts.sofa import run_sheet

CUP = 7          # UEFA Champions League
LEAGUE_A = 101   # a strong domestic league
LEAGUE_B = 202   # a weak one
LOWER_A = 103    # league A's lower division (links A to the pool)
LOWER_B = 203
DAY_S = 86400
LIMIT = timedelta(minutes=45)


def _match(eid: int, ts: int, comp: int, home: int, away: int,
           goals: tuple[float, float], shots: tuple[float, float] = (12, 10),
           corners: tuple[float, float] = (5, 4)) -> fr.FootballResult:
    return fr.FootballResult(
        event_id=eid, ts=ts, competition_id=comp, home_id=home, away_id=away,
        values={"goals_for": goals, "shots_for": shots, "corners_for": corners})


def _history() -> list[fr.FootballResult]:
    """Two leagues of four teams, each linked to its lower division, then a
    run of cup matches where league A's clubs beat league B's by more than
    the book's sigma expects."""
    out: list[fr.FootballResult] = []
    ts = 1_700_000_000
    eid = 0
    a_teams, b_teams = [1, 2, 3, 4], [11, 12, 13, 14]
    a_low, b_low = [21, 22], [31, 32]
    for rnd in range(40):
        for comp, teams in ((LEAGUE_A, a_teams), (LEAGUE_B, b_teams)):
            for i in range(0, len(teams), 2):
                h, a = teams[(i + rnd) % 4], teams[(i + 1 + rnd) % 4]
                eid += 1
                out.append(_match(eid, ts, comp, h, a, (1 + rnd % 2, 1)))
        for low, comp, top in ((a_low, LOWER_A, a_teams), (b_low, LOWER_B, b_teams)):
            eid += 1
            out.append(_match(eid, ts + 3600, comp, low[rnd % 2], low[1 - rnd % 2],
                              (1, 1)))
            # a domestic cup tie: the top side against its lower division
            eid += 1
            out.append(_match(eid, ts + 7200, 900 + comp, top[rnd % 4], low[rnd % 2],
                              (2, 1)))
        ts += 3 * DAY_S
    for rnd in range(30):
        eid += 1
        out.append(_match(eid, ts, CUP, a_teams[rnd % 4], b_teams[rnd % 4], (3, 0),
                          shots=(20, 6)))
        ts += 3 * DAY_S
    return sorted(out, key=lambda r: r.ts)   # the history is in time order


def _book(on: bool, eta: dict[str, float] | None = None) -> fr.RatingBook:
    return fr.replay(
        _history(), 2**62, shared_league_link=True,
        cup_competitions=frozenset({CUP}) if on else frozenset(),
        cup_eta=(eta if eta is not None else {"goals_for": 0.05}) if on else None)


# --- the book ---------------------------------------------------------------------


def test_off_is_the_book_as_it_was() -> None:
    plain = fr.RatingBook(shared_league_link=True)
    for r in _history():
        plain.update(r)
    off = _book(False)
    assert off.teams == plain.teams
    assert off.strength == plain.strength
    assert not off.cup_delta
    # a step without a cup list does nothing either
    no_list = fr.replay(_history(), 2**62, shared_league_link=True,
                        cup_eta={"goals_for": 0.05})
    assert no_list.teams == plain.teams and not no_list.cup_delta


def test_cup_matches_teach_the_stronger_league_its_correction() -> None:
    book = _book(True)
    da = book.cup_delta[(LEAGUE_A, "goals_for")]
    db = book.cup_delta[(LEAGUE_B, "goals_for")]
    assert da.sigma > 0 > db.sigma
    assert da.n == db.n > 0
    # only the metrics with a step are learnt
    assert (LEAGUE_A, "shots_for") not in book.cup_delta
    assert (LEAGUE_A, "corners_for") not in book.cup_delta


def test_the_correction_is_read_only_on_a_cup_fixture() -> None:
    book = _book(True)
    base = _book(False)
    status, lf_cup = book.link(1, 11, "goals_for", CUP)
    assert status == fr.LINKED_BY_STRENGTH
    extra = book.cup_extra(CUP, book.domain(1), book.domain(11), "goals_for")
    assert extra > 0
    _s, lf_plain = book.link(1, 11, "goals_for")          # no competition
    _s, lf_other = book.link(1, 11, "goals_for", 999)     # not a listed cup
    assert lf_cup == pytest.approx(lf_plain + extra)
    assert lf_other == lf_plain
    # a metric without a step reads no correction
    _s, c_cup = book.link(1, 11, "corners_for", CUP)
    _s, c_plain = book.link(1, 11, "corners_for")
    assert c_cup == c_plain
    # the forecast of a cup fixture moves toward the stronger league's side
    fc_on = fr.FootballForecast(book, CUP, 1, 11)
    fc_off = fr.FootballForecast(base, CUP, 1, 11)
    on_h = fc_on.centre("goals_for", "side_a")
    off_h = fc_off.centre("goals_for", "side_a")
    assert on_h is not None and off_h is not None
    assert on_h[0] > off_h[0]


def test_a_same_league_or_domestic_pairing_is_untouched() -> None:
    book = _book(True)
    assert book.cup_extra(CUP, LEAGUE_A, LEAGUE_A, "goals_for") == 0.0
    assert book.cup_extra(None, LEAGUE_A, LEAGUE_B, "goals_for") == 0.0
    assert book.cup_extra(CUP, None, LEAGUE_B, "goals_for") == 0.0
    # a domain that is itself a cup is not a domestic league
    assert book.cup_extra(CUP, CUP, LEAGUE_B, "goals_for") == 0.0


def test_a_cup_match_with_the_rule_on_moves_the_ratios_less() -> None:
    # the correction explains part of the cup residual, so the stronger
    # league's attackers absorb less of it than without the rule
    hist = _history()
    cut = hist[-1].ts
    on = fr.replay(hist, cut, True, cup_competitions=frozenset({CUP}),
                   cup_eta={"goals_for": 0.05})
    off = fr.replay(hist, cut, True)
    last = hist[-1]
    on.update(last)
    off.update(last)
    assert (on.teams[(last.home_id, "goals_for")].attack
            <= off.teams[(last.home_id, "goals_for")].attack)


# --- the config file ----------------------------------------------------------------


def test_the_installed_file_loads() -> None:
    cup = cup_strength.load()
    assert CUP in cup.competitions and len(cup.competitions) == 9
    assert set(cup.eta) == {"goals_for", "goals_1h_for", "goals_2h_for", "shots_for"}
    assert "corners_for" not in cup.eta  # measured no better


@pytest.mark.parametrize("data", [
    {"competitions": [], "eta": {"goals_for": 0.05}},
    {"competitions": [7], "eta": {}},
    {"competitions": [7], "eta": {"goals_for": 1.5}},
])
def test_a_malformed_file_raises(tmp_path: Path, data: dict[str, Any]) -> None:
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        cup_strength.load(p)
    with pytest.raises(FileNotFoundError):
        cup_strength.load(tmp_path / "absent.json")


def test_apply_refuses_a_book_already_updated() -> None:
    cup = cup_strength.CupStrength(frozenset({CUP}), {"goals_for": 0.05})
    fresh = cup_strength.apply(fr.RatingBook(), cup)
    assert fresh.cup_competitions == {CUP} and fresh.cup_eta == {"goals_for": 0.05}
    assert cup_strength.apply(fr.RatingBook(), None).cup_competitions == frozenset()
    used = fr.RatingBook()
    used.update(_history()[0])
    with pytest.raises(ValueError):
        cup_strength.apply(used, cup)


# --- the switch, the marker, rebuild_plan ------------------------------------------


def test_the_switch_reads_the_day_and_the_clock() -> None:
    on_at = datetime(2026, 10, 16, 0, 0, tzinfo=UTC)
    assert epochs.FOOTBALL_CUP_STRENGTH_FROM_UTC == on_at
    assert not epochs.football_cup_strength("2026-10-15", on_at)
    assert not epochs.football_cup_strength("2026-10-16", on_at - timedelta(seconds=1))
    assert epochs.football_cup_strength("2026-10-16", on_at)
    assert epochs.FOOTBALL_CUP_STRENGTH_MARKER == (
        "cup_strength_rule", epochs.FOOTBALL_CUP_STRENGTH, "football")


def test_rebuild_re_runs_a_sheet_without_the_marker_from_the_switch() -> None:
    day, at = "2026-10-16", datetime(2026, 10, 16, 6, 0, tzinfo=UTC)
    plan = rp.build_plan(rp.DayState(day, at, LIMIT, sheet_cup_strength=False))
    sheet = next(s for s in plan.steps if s.name == "SHEET")
    assert "football_cup_strength" in sheet.reason
    assert "SHEET" not in rp.build_plan(rp.DayState(day, at, LIMIT)).names()
    # 10-15 (built before the switch) is never re-priced under it
    for d, t in (("2026-10-15", at),
                 ("2026-10-15", datetime(2026, 10, 15, 22, tzinfo=UTC))):
        assert "SHEET" not in rp.build_plan(
            rp.DayState(d, t, LIMIT, sheet_cup_strength=False)).names()


def test_the_marker_is_read_only_on_football_rows() -> None:
    field, rule, _ = epochs.FOOTBALL_CUP_STRENGTH_MARKER
    m = epochs.FOOTBALL_CUP_STRENGTH_MARKER
    assert epochs.sheet_has_marker([{"sport": "tennis"}], m)
    assert not epochs.sheet_has_marker([{"sport": "football"}], m)
    assert epochs.sheet_has_marker([{"sport": "football", field: rule}], m)
    assert field in run_sheet.AUDIT_MARKER_FIELDS


def test_sheet_book_arguments_follow_the_switch() -> None:
    assert run_sheet.cup_book_args(False) == {}
    args = run_sheet.cup_book_args(True)
    assert args["cup_competitions"] == cup_strength.load().competitions
    assert args["cup_eta"] == cup_strength.load().eta
    book = fr.replay(_history(), 2**62, True, **args)
    assert book.cup_competitions and book.cup_eta


def test_sheet_stamps_the_marker_only_while_on() -> None:
    rows = [run_sheet.SheetRow.model_construct(sport="football"),
            run_sheet.SheetRow.model_construct(sport="tennis")]
    off = run_sheet.stamp_marker(rows, epochs.FOOTBALL_CUP_STRENGTH_MARKER, False)
    assert off is rows
    on = run_sheet.stamp_marker(rows, epochs.FOOTBALL_CUP_STRENGTH_MARKER, True)
    assert on[0].cup_strength_rule == epochs.FOOTBALL_CUP_STRENGTH
    assert on[1].cup_strength_rule is None


# --- the replay ---------------------------------------------------------------------


def test_the_replay_rules_carry_the_cup_strength() -> None:
    from scripts.sofa import calibrate_from_cache as cfc

    cup = cup_strength.CupStrength(frozenset({CUP}), {"goals_for": 0.05})
    rules = cfc.CentreRules(football_rating=True, cup_strength=cup,
                            cup_strength_path="x.json")
    replay_ = cfc.FootballRatingReplay(_history(), rules)
    assert replay_.book.cup_competitions == {CUP}
    assert rules.describe()["cup_strength"] == "x.json"
    off = cfc.FootballRatingReplay(_history(), cfc.CentreRules(football_rating=True))
    assert off.book.cup_competitions == frozenset()
    assert cfc.CentreRules().describe()["cup_strength"] is None
    # the replayed book is SHEET's book
    replay_.advance(2**62)
    sheet_book = fr.replay(_history(), 2**62, True, cup_competitions=frozenset({CUP}),
                           cup_eta={"goals_for": 0.05})
    assert replay_.book.cup_delta == sheet_book.cup_delta
    assert replay_.book.teams == sheet_book.teams


def test_the_measurement_prices_cup_rows_from_both_books() -> None:
    from scripts.sofa import measure_cross_league_cups as m

    hist = [replace(r, competition_id=CUP) if r.competition_id == CUP else r
            for r in _history()]
    rows = m.inbook_replay(hist, 0, ["goals_for"], [0.05])
    assert rows["goals_for"]
    r0 = rows["goals_for"][-1]
    assert r0["lh_E_0.05"] != r0["lh_A"]


def test_the_spill_measurement_reads_only_non_cup_matches_that_moved() -> None:
    from scripts.sofa import measure_cross_league_cups as m

    hist = _history()
    # one more league round after the cup run: its centres feel the cup
    last = hist[-1].ts
    tail = [_match(10_000 + i, last + DAY_S * (i + 1), LEAGUE_A, 1 + i % 4,
                   1 + (i + 1) % 4, (1, 1)) for i in range(4)]
    rows = m.spill_replay(hist + tail, last + 1, {"goals_for": 0.05})
    assert rows["goals_for"]
    assert all(r[0] > last for r in rows["goals_for"])          # never a cup row
    assert all(r[3] != r[5] or r[4] != r[6] for r in rows["goals_for"])
    res = m.spill_measure(rows, 0, 7.586)
    assert res["goals_for"]["n_moved"] == len(rows["goals_for"])
