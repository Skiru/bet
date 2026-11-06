"""The cache replay carries the three live rules no refit replayed before
2026-11-05 (docs/sofa/evidence/refit_replay_2026-11-05.md):

* --referee (epochs.FOOTBALL_REFEREE): a cards / fouls centre x the match
  referee's as-of term - the same book SHEET's referees.fixture_reads walks,
  advanced to the match's UTC day start (nothing of that day or later);
* --player-share (epochs.FOOTBALL_PLAYER_SHARE): a footballer's centre is his
  shrunk share of his side's team centre (run_sheet.player_share_centre);
* --tennis-score-winner (epochs.TENNIS_RATING_SCORE_WINNER, P14): the tennis
  rating's history loaded with score_winner=True;
* --sample-conflict-cut (P1): the friendlies added for the cut leave the
  football histories.

Each is off by default (the replay byte for byte as before). Offline."""

from __future__ import annotations

import statistics
import sys
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import football_rating as fr
from bet.sofa import player_share as psh
from bet.sofa import referees as rf
from bet.sofa.engine import sheet_count_p_raw, sheet_predictive_sd, winning_boundary
from scripts.sofa import calibrate_from_cache as cfc
from scripts.sofa.calibrate_from_cache import (
    CentreRules,
    FootballRatingReplay,
    live_centre,
)
from tests.sofa.test_audit_2026_10_13_replay import _football

TABLE = rf.parse_effect_table({"markets": {
    "cards_points_total": {"family": "cards_points", "beta": 0.6, "K": 10.0},
    "cards_points_for": {"family": "cards_points", "beta": 0.5, "K": 10.0},
    "fouls_total": {"family": "fouls", "beta": 0.7, "K": 5.0},
}})


def _with_cards(history: list[fr.FootballResult]) -> list[fr.FootballResult]:
    out = []
    for i, r in enumerate(history):
        vals = dict(r.values)
        vals["cards_points_for"] = (float(10 + 10 * (i % 4)), float(20 + 5 * (i % 3)))
        vals["fouls_for"] = (float(10 + i % 7), float(9 + i % 5))
        out.append(fr.FootballResult(
            event_id=r.event_id, ts=r.ts, competition_id=r.competition_id,
            home_id=r.home_id, away_id=r.away_id, values=vals))
    return out


def _labels(history: list[fr.FootballResult]) -> dict[int, int]:
    # three referees in turn; every fifth match unlabelled
    return {r.event_id: 70 + (i % 3) for i, r in enumerate(history) if i % 5}


# --- referee ------------------------------------------------------------------


def test_the_referee_rule_is_off_by_default() -> None:
    assert CentreRules().referee_effect is None
    assert cfc.CENTRE_RULES.referee_effect is None
    history, played = _football()
    rules = CentreRules(football_rating=True)
    replay = FootballRatingReplay(_with_cards(history), rules,
                                  referee_labels=_labels(history))
    target = played[-3]
    fc = replay.forecast(target)
    assert replay.referee_reads(target.event_id) is None
    assert live_centre(target, "cards_points_total", None, 40.0, fc, (), rules,
                       referee_reads=None) == pytest.approx(
        live_centre(target, "cards_points_total", None, 40.0, fc, (), rules))


def test_the_replay_reads_the_referee_as_sheet_does_as_of_the_day() -> None:
    history, played = _football()
    history = _with_cards(history)
    labels = _labels(history)
    rules = CentreRules(football_rating=True, referee_effect=TABLE)
    replay = FootballRatingReplay(history, rules, referee_labels=labels)
    checked = 0
    for target in played[-30:]:
        if target.event_id not in labels:
            continue
        fc = replay.forecast(target)
        got = replay.referee_reads(target.event_id)
        cut = cfc.day_start(target.timestamp)
        # SHEET: run_sheet's referee_terms.fixture_reads at the day's cut
        want = rf.fixture_reads(history, labels, cut,
                                {target.event_id: labels[target.event_id]})
        assert got == want[target.event_id]
        # nothing of the match's own day is in the referee's record
        same_day = [r for r in history if r.ts >= cut
                    and labels.get(r.event_id) == labels[target.event_id]]
        n_before = sum(1 for r in history if r.ts < cut
                       and labels.get(r.event_id) == labels[target.event_id])
        # (a match counts once its competition has MIN_LEAGUE_MATCHES before it)
        assert got is not None and 0 < got["cards_points"].n <= n_before
        assert same_day  # the fixture itself at least
        off = CentreRules(football_rating=True)
        for market, side, c in (("cards_points_total", None, 40.0),
                                ("cards_points_for", "side_a", 20.0),
                                ("fouls_total", None, 22.0)):
            applied = TABLE.apply(market, got[rf.family_of(market) or ""])
            assert applied is not None and applied[1]["status"] == rf.APPLIED
            base = live_centre(target, market, side, c, fc, (), off)
            new = live_centre(target, market, side, c, fc, (), rules,
                              referee_reads=got)
            assert new == pytest.approx(base * applied[0])
        # a market outside the table is untouched
        assert live_centre(target, "corners_total", None, 9.0, fc, (), rules,
                           referee_reads=got) == pytest.approx(
            live_centre(target, "corners_total", None, 9.0, fc, (), off))
        checked += 1
    assert checked >= 5


def test_no_referee_named_is_x1() -> None:
    history, played = _football()
    history = _with_cards(history)
    labels = _labels(history)
    target = next(p for p in reversed(played) if p.event_id not in labels)
    rules = CentreRules(football_rating=True, referee_effect=TABLE)
    replay = FootballRatingReplay(history, rules, referee_labels=labels)
    fc = replay.forecast(target)
    reads = replay.referee_reads(target.event_id)
    assert reads is not None and reads["cards_points"].referee_id is None
    off = CentreRules(football_rating=True)
    assert live_centre(target, "cards_points_total", None, 40.0, fc, (), rules,
                       referee_reads=reads) == pytest.approx(
        live_centre(target, "cards_points_total", None, 40.0, fc, (), off))


def test_the_team_rows_carry_the_term_under_the_flag(
        monkeypatch: pytest.MonkeyPatch) -> None:
    history, played = _football()
    history = _with_cards(history)
    labels = _labels(history)
    for p, r in zip(played, history, strict=True):
        p.values["cards_points"] = r.values["cards_points_for"]
    off = CentreRules(football_rating=True)
    on = CentreRules(football_rating=True, referee_effect=TABLE)

    def rows(rules: CentreRules) -> dict[tuple[Any, ...], float]:
        monkeypatch.setattr(cfc, "CENTRE_RULES", rules)
        return {(r.event_id, r.market, r.subject, r.line, r.direction): r.p_central
                for r in cfc.iter_rows(
                    played, {}, None, frozenset(),
                    FootballRatingReplay(history, rules, referee_labels=labels))}

    a, b = rows(off), rows(on)
    # the grid of lines follows the centre, so compare the common rows; every
    # row of another market is identical, line for line
    other = {k for k in a if k[1] not in TABLE.markets}
    assert other and other == {k for k in b if k[1] not in TABLE.markets}
    assert all(a[k] == b[k] for k in other)
    common = {k for k in a if k in b and k[1] in TABLE.markets}
    assert any(a[k] != b[k] for k in common)


# --- player share --------------------------------------------------------------

CELL = {"m": 40.0, "prior_share": {"*": 0.09, "F": 0.16}}
SHARE = psh.parse_table({"markets": {
    "player_shots_for": CELL,
    "player_shots_on_target_for": {**CELL, "m_accuracy": 40.0,
                                   "prior_accuracy": {"*": 0.38, "F": 0.42}},
}})


def _start(shots: float, sot: float, pos: str = "F") -> dict[str, Any]:
    return {"minutesPlayed": 90.0, "totalShots": shots, "onTargetScoringAttempt": sot,
            "shotOffTarget": shots - sot, "_started": True, "_position": pos}


def _share_ctx(team_centre: float | None, matched_events: int = 10,
               ) -> tuple[dict[bool, list[dict[str, dict[str, Any]]]],
                          cfc.ShareContext]:
    squads = [{"jan kowalski": _start(2.0 + (i % 3), 1.0 + (i % 2))}
              for i in range(10)]
    ids = list(range(100, 110))
    team = [(e, 12.0 + i) for i, e in enumerate(ids[:matched_events])]
    ctx = cfc.ShareContext(
        table=SHARE,
        team_centres=({} if team_centre is None
                      else {("shots_for", True): team_centre}),
        history_ids={True: ids, False: []},
        wide_ids={True: ids, False: []},
        team_obs={True: {"shots_for": team}})
    return {True: squads, False: []}, ctx


def _player_rows(share: cfc.ShareContext | None,
                 history: dict[bool, list[dict[str, dict[str, Any]]]],
                 ) -> list[cfc.SettledRow]:
    event = {"id": 999, "tournament": {"uniqueTournament": {"id": 17}}}
    target = {True: {"jan kowalski": _start(3.0, 1.0)}, False: None}
    return cfc.player_rows_for_event(
        event, target, history,
        {"player_shots_for": [1.5, 2.5], "player_shots_on_target_for": [0.5]},
        5, starters_only=True, starts_only=True, sample_n=10, share=share)


def test_the_share_centre_is_sheets_and_off_by_default() -> None:
    history, ctx = _share_ctx(team_centre=14.0)
    old = {(r.market, r.line, r.direction): r for r in _player_rows(None, history)}
    new = {(r.market, r.line, r.direction): r for r in _player_rows(ctx, history)}
    assert set(old) == set(new) and old
    shots = [2.0 + (i % 3) for i in range(10)]
    sot = [1.0 + (i % 2) for i in range(10)]
    team = [12.0 + i for i in range(10)]
    want = {
        "player_shots_for": psh.share_centre(
            his_volume=sum(shots), team_volume=sum(team), team_centre=14.0,
            prior_share=0.16, m=40.0),
        "player_shots_on_target_for": psh.share_centre(
            his_volume=sum(shots), team_volume=sum(team), team_centre=14.0,
            prior_share=0.16, m=40.0, his_count=sum(sot), prior_accuracy=0.42,
            m_accuracy=40.0),
    }
    for (market, line, direction), row in new.items():
        sample = shots if market == "player_shots_for" else sot
        mean = statistics.mean(sample)
        centre = want[market]
        spread = sheet_predictive_sd(market, "football", mean,
                                     statistics.variance(sample), 10, centre)
        p = sheet_count_p_raw(market, centre, spread,
                              winning_boundary(line, direction), direction)
        assert row.p_central == pytest.approx(round(p, 6), abs=1e-6)
        assert row.sample_mean == old[(market, line, direction)].sample_mean
        assert row.p_central != old[(market, line, direction)].p_central


def test_no_team_centre_or_too_few_matched_starts_keeps_the_old_centre() -> None:
    history, _ = _share_ctx(team_centre=None)
    old = {(r.market, r.line, r.direction): r.p_central
           for r in _player_rows(None, history)}
    _, ctx = _share_ctx(team_centre=None)
    assert {(r.market, r.line, r.direction): r.p_central
            for r in _player_rows(ctx, history)} == old
    _, thin = _share_ctx(team_centre=14.0, matched_events=psh.MIN_SHARE_MATCHES - 1)
    assert {(r.market, r.line, r.direction): r.p_central
            for r in _player_rows(thin, history)} == old


def test_the_team_replay_records_the_side_centres(
        monkeypatch: pytest.MonkeyPatch) -> None:
    history, played = _football()
    for p in played:
        p.values["shots"] = (float(10 + p.event_id % 5), float(8 + p.event_id % 3))
    rules = CentreRules(football_rating=True)
    monkeypatch.setattr(cfc, "CENTRE_RULES", rules)
    monkeypatch.setattr(cfc, "SHARE_TEAM_CENTRES", None)
    list(cfc.iter_rows(played, {}, None, frozenset(),
                       FootballRatingReplay(history, rules)))
    assert cfc.SHARE_TEAM_CENTRES is None
    store: dict[int, dict[tuple[str, bool], float]] = {}
    monkeypatch.setattr(cfc, "SHARE_TEAM_CENTRES", store)
    rows = list(cfc.iter_rows(played, {}, None, frozenset(),
                              FootballRatingReplay(history, rules)))
    assert store
    # every priced match is listed, with or without a share team metric
    assert {r.event_id for r in rows} <= set(store)
    eid, centres = next((e, c) for e, c in store.items() if c)
    assert set(centres) <= {("shots_for", True), ("shots_for", False),
                            ("fouls_for", True), ("fouls_for", False),
                            ("tackles_for", True), ("tackles_for", False)}
    assert any(r.event_id == eid and r.market == "shots_for" for r in rows)


def test_the_share_flag_needs_the_team_rows(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", [
        "calibrate_from_cache.py", "--football-rating", "--player-share",
        "--players", "only"])
    with pytest.raises(SystemExit):
        cfc.main()
    monkeypatch.setattr(sys, "argv", ["calibrate_from_cache.py", "--referee"])
    with pytest.raises(SystemExit):
        cfc.main()


# --- P14 / P1 ------------------------------------------------------------------


def test_the_tennis_rating_history_reads_the_score_winner_only_under_the_flag(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_history(db_path: Any, **kw: Any) -> list[Any]:
        calls.append(kw)
        return []

    class FakeRating:
        def __init__(self, *a: Any) -> None:
            pass

    monkeypatch.setattr(cfc, "load_history", fake_history)
    monkeypatch.setattr(cfc, "load_coefficients",
                        lambda: ({}, {"features": ["x"]}))
    monkeypatch.setattr(cfc, "AsOfRating", FakeRating)
    monkeypatch.setattr(cfc, "start_for_rule", lambda *a: None)
    assert cfc.RatingReplay.from_db(Path("x.db")) is not None
    assert cfc.RatingReplay.from_db(Path("x.db"), score_winner=True) is not None
    assert calls == [{}, {"score_winner": True}]


def test_the_conflict_cut_friendlies_leave_the_histories_only_under_the_flag(
        monkeypatch: pytest.MonkeyPatch) -> None:
    comp = next(iter(cfc.CONFLICT_CUT_FRIENDLY_IDS))
    past = {"id": 5, "startTimestamp": 1000, "status": {"type": "finished"},
            "tournament": {"uniqueTournament": {"id": comp}},
            "homeTeam": {"id": 11}, "awayTeam": {"id": 12},
            "homeScore": {"current": 1}, "awayScore": {"current": 0}}
    monkeypatch.setattr(cfc, "SAMPLE_CONFLICT_CUT", False)
    before = cfc.admitted_football_event(past, 11, 5000)
    monkeypatch.setattr(cfc, "SAMPLE_CONFLICT_CUT", True)
    assert not cfc.admitted_football_event(past, 11, 5000)
    assert before == cfc.is_completed_event(past)


def test_a_match_the_team_replay_did_not_price_gives_no_share_player_rows(
        tmp_path: Path) -> None:
    """--player-share: a match missing from the team replay's centres (not in
    the teams' listings yet) yields no player rows at all - they would carry
    the old centre where SHEET read the share; a priced match without a side
    centre keeps the old centre (as SHEET without a team row)."""
    from tests.sofa.test_cache_replay_player_markets import LADDER, _fixture
    cache = _fixture(tmp_path)
    cache.index()
    plain, _ = cfc.build_player_rows(cache.db, LADDER, sample_n=10, min_sample=5)
    assert any(r.event_id == 999 for r in plain)
    none, counts = cfc.build_player_rows(cache.db, LADDER, sample_n=10, min_sample=5,
                                         share=SHARE, share_centres={})
    assert none == [] and counts["share_no_team_replay"] > 0
    priced = {r.event_id: {} for r in plain}
    kept, _ = cfc.build_player_rows(cache.db, LADDER, sample_n=10, min_sample=5,
                                    share=SHARE, share_centres=priced)
    def key(r: Any) -> tuple[object, ...]:
        return (r.event_id, r.market, r.subject, r.line, r.direction, r.p_central)

    assert sorted(map(key, kept)) == sorted(map(key, plain))
