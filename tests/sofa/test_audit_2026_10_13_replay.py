"""Audit 2026-10-13 A6 / B5: the cache replay prices what SHEET prices.

A6 (--football-rating): a football marginal row's centre is the rating as of
the match's day blended with the shrunk sample centre at W_FOOTBALL_RATING
(run_sheet.process_fixture), through one hook, ``live_centre``, which also
applies the B1 / B2 terms (game state, rated scope, venue prior) when asked.
The book never holds the row's own match or a later one.

B5 (--tennis-set-ratings): the per-set games and sets_total rows, read off
the tennis rating's neighbours as of the match's day.

Every flag off = the rows as before, byte for byte. Offline and synthetic.
"""

from __future__ import annotations

import json
import math
import random
import statistics
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bet.sofa import football_rating as fr
from bet.sofa.engine import sheet_count_p_raw, sheet_predictive_sd, winning_boundary
from bet.sofa.game_state import GameStateTable, clamp_supremacy
from bet.sofa.rating_weight import RatingWeightTable
from bet.sofa.season_phase import SeasonPhaseTable
from bet.sofa.tennis_rating import FEATURES, TennisResult, build_model
from scripts.sofa import calibrate_from_cache as cfc
from scripts.sofa import prepare_refit as pr
from scripts.sofa.calibrate_from_cache import (
    MIN_SAMPLE,
    SAMPLE_N,
    CentreRules,
    FootballRatingReplay,
    Played,
    RatingReplay,
    TennisContext,
    iter_rows,
    live_centre,
    set_values,
    shrunk_centre,
)
from tests.sofa.test_prepare_refit import _db, _fake_calibrate, _paths

DAY = 86400
T0 = 1_750_000_000 - 1_750_000_000 % DAY
COMP = 17
TEAMS = 8
BASELINES = {
    "corners_for": {"global": {"mean": 5.0, "n": 5000}},
    "corners_total": {"global": {"mean": 10.0, "n": 5000}},
    "corners_1h_for": {"global": {"mean": 2.4, "n": 5000}},
}


def _football(days: int = 40, per_day: int = 4, seed: int = 5
              ) -> tuple[list[fr.FootballResult], list[Played]]:
    """One league of TEAMS sides, several matches a day (so the day cut is
    tested), the same matches as the rating's history and the replay's."""
    rng = random.Random(seed)
    attack = {t: rng.uniform(0.7, 1.4) for t in range(1, TEAMS + 1)}
    history: list[fr.FootballResult] = []
    played: list[Played] = []
    eid = 1000
    for d in range(days):
        for k in range(per_day):
            h, a = rng.sample(range(1, TEAMS + 1), 2)
            ts = T0 + d * DAY + 3600 * (10 + 2 * k)
            gh, ga = float(rng.randint(0, 3)), float(rng.randint(0, 2))
            ch = float(rng.randint(1, 9) + round(2 * attack[h]))
            ca = float(rng.randint(0, 7) + round(2 * attack[a]))
            c1h, c1a = float(rng.randint(0, int(ch))), float(rng.randint(0, int(ca)))
            history.append(fr.FootballResult(
                event_id=eid, ts=ts, competition_id=COMP, home_id=h, away_id=a,
                values={"goals_for": (gh, ga), "corners_for": (ch, ca),
                        "corners_1h_for": (c1h, c1a)}))
            played.append(Played(
                event_id=eid, timestamp=ts, home_id=h, away_id=a,
                sport="football", competition_id=COMP,
                values={"goals": (gh, ga), "corners": (ch, ca),
                        "corners_1h": (c1h, c1a)}))
            eid += 1
    return history, played


def _key(r: cfc.SettledRow) -> tuple[int, str, str, float, str]:
    return (r.event_id, r.market, r.subject, r.line, r.direction)


# --------------------------------------------------------------------------
# flags off = as before
# --------------------------------------------------------------------------


def test_every_new_rule_is_off_by_default() -> None:
    assert CentreRules() == cfc.CENTRE_RULES
    assert not cfc.CENTRE_RULES.football_rating
    assert cfc.CENTRE_RULES.game_state is None
    assert cfc.TENNIS_SET_RATINGS is False


def test_a_book_that_rates_nobody_leaves_every_row_as_it_was() -> None:
    """The hook is the identity where the rating gives no centre - the rows
    with an empty book are the rows without one, field for field."""
    _, played = _football()
    plain = list(iter_rows(played, BASELINES))
    empty = FootballRatingReplay([], CentreRules(football_rating=True))
    hooked = list(iter_rows(played, BASELINES, None, frozenset(), empty))
    assert plain and hooked == plain
    assert empty.forecasts == len(played)


def test_without_the_set_flag_the_set_markets_read_no_rating() -> None:
    fc = build_model(_tennis_history(), COEF, T0 + 70 * DAY).forecast(
        1, 2, "ATP", "Hard", datetime.fromtimestamp(T0 + 70 * DAY, UTC))
    assert fc is not None
    reader = cfc.rating_reader(fc, "side_a")
    assert reader("games_set1_total", 9.5, "OVER") is None
    assert reader("sets_total", 2.5, "OVER") is None
    assert reader("games_won_for", 10.5, "OVER") is not None


# --------------------------------------------------------------------------
# A6: the football rating as SHEET reads it
# --------------------------------------------------------------------------


def test_the_book_holds_only_matches_before_the_matchs_day() -> None:
    history, played = _football()
    replay = FootballRatingReplay(history, CentreRules(football_rating=True))
    for match in played[40::23]:
        fc = replay.forecast(match)
        assert fc is not None
        cut = match.timestamp - match.timestamp % DAY
        assert replay.seen == sum(1 for r in history if r.ts < cut)
        assert match.event_id not in {r.event_id for r in history[:replay.seen]}
        assert all(r.ts < match.timestamp for r in history[:replay.seen])
    with pytest.raises(ValueError):
        replay.advance(T0)  # never backwards


def test_the_centre_never_reads_the_matchs_own_result_or_a_later_one() -> None:
    history, played = _football()
    target = played[-6]
    cut = target.timestamp - target.timestamp % DAY
    # the target and everything from its day on, replaced by nonsense
    scrambled = [
        fr.FootballResult(**{**r.__dict__, "values": {
            m: (v[0] + 17.0, 0.0) for m, v in r.values.items()}})
        if r.ts >= cut else r for r in history]
    centres = []
    for hist in (history, scrambled):
        fc = FootballRatingReplay(hist, CentreRules(football_rating=True)
                                  ).forecast(target)
        assert fc is not None
        centres.append((fc.centre("corners_for", "side_a"),
                        fc.centre("goals_for", "side_b")))
    assert centres[0] == centres[1] and centres[0][0] is not None


def test_a_football_row_is_priced_at_sheets_blended_centre() -> None:
    history, played = _football()
    football = FootballRatingReplay(history, CentreRules(football_rating=True))
    rows = list(iter_rows(played, BASELINES, None, frozenset(), football))
    plain = {_key(r): r for r in iter_rows(played, BASELINES)}
    constants = cfc._load_engine_constants()
    checked = 0
    for target in played[-12:]:
        cut = target.timestamp - target.timestamp % DAY
        book = fr.replay(history, cut, shared_league_link=True)
        fc = fr.FootballForecast(book, COMP, target.home_id, target.away_id)
        before = [m for m in played if m.timestamp < target.timestamp]
        for side, team, idx in (("side_a", target.home_id, 0),
                                ("side_b", target.away_id, 1)):
            sample = [m.values["corners"][0 if m.home_id == team else 1]
                      for m in before if team in (m.home_id, m.away_id)
                      ][-SAMPLE_N:]
            if len(sample) < MIN_SAMPLE:
                continue
            rated = fc.centre("corners_for", side)
            assert rated is not None
            sample_centre = shrunk_centre(target, "corners_for", sample,
                                          BASELINES, constants)
            # run_sheet.process_fixture, the rating branch
            centre = (fr.W_FOOTBALL_RATING * rated[0]
                      + (1 - fr.W_FOOTBALL_RATING) * sample_centre)
            mine = [r for r in rows if r.event_id == target.event_id
                    and r.market == "corners_for" and r.subject == str(team)]
            assert {r.line for r in mine} <= set(cfc.lines_for(centre))
            assert mine
            n, mean = len(sample), statistics.mean(sample)
            sd = sheet_predictive_sd("corners_for", "football", mean,
                                     statistics.variance(sample), n, centre, None)
            for r in mine:
                p = sheet_count_p_raw("corners_for", centre, sd,
                                      winning_boundary(r.line, r.direction),
                                      r.direction, None)
                assert r.p_central == pytest.approx(round(p, 6), abs=1e-9)
                assert r.actual == target.values["corners"][idx]
                checked += 1
    assert checked > 30
    # corners_total is out of the rating's scope (UNRATED_MARKETS): unchanged
    totals = [r for r in rows if r.market == "corners_total"]
    assert totals and all(r == plain[_key(r)] for r in totals)


def test_the_hook_applies_venue_and_game_state_in_sheets_order() -> None:
    history, played = _football()
    target = played[-3]
    rules = CentreRules(football_rating=True, venue_prior=True,
                        game_state=GameStateTable({"corners_for": 0.11}))
    fc = FootballRatingReplay(history, rules).forecast(target)
    assert fc is not None
    rated = fc.centre("corners_for", "side_b")
    sup = fc.supremacy("side_b")
    assert rated is not None and sup is not None
    got = live_centre(target, "corners_for", "side_b", 4.0, fc, (), rules)
    blended = fr.W_FOOTBALL_RATING * rated[0] + (1 - fr.W_FOOTBALL_RATING) * 4.0
    assert got == pytest.approx(blended * math.exp(0.11 * clamp_supremacy(sup)))
    # an unrated market of VENUE_PRIOR_MARKETS: the league multiplier alone
    venues: Sequence[str | None] = ("home", "home", "away", "home")
    assert fc.centre("corners_1h_for", "side_a") is None
    mult = fc.venue_multiplier("corners_1h_for", "side_a", venues)
    assert mult is not None and mult != 1.0
    assert live_centre(target, "corners_1h_for", "side_a", 2.0, fc, venues,
                       rules) == pytest.approx(2.0 * mult)
    off = CentreRules(football_rating=True)
    assert live_centre(target, "corners_1h_for", "side_a", 2.0, fc, venues,
                       off) == 2.0
    # rated scope: corners_1h_for is rated once the switch's markets are in
    scoped = FootballRatingReplay(
        history, CentreRules(football_rating=True, rated_scope=True)
    ).forecast(target)
    assert scoped is not None and scoped.centre("corners_1h_for", "side_a")
    # no forecast, or a player market: the sample centre
    assert live_centre(target, "corners_for", "side_a", 3.3, None) == 3.3
    assert live_centre(target, "player_shots_for", "side_a", 3.3, fc) == 3.3


def test_the_hook_applies_the_markets_weight_and_the_season_phase() -> None:
    """B14 / C1: the market's fitted W (rating_weight.blend) replaces
    W_FOOTBALL_RATING, and the phase multiplier comes last, as in SHEET."""
    history, played = _football()
    target = played[-3]
    weights = RatingWeightTable({"goals_for": 0.95})
    phase = SeasonPhaseTable({"goals_for": {"late": 0.05}})
    rules = CentreRules(football_rating=True, rating_weights=weights,
                        season_phase=phase)
    replay = FootballRatingReplay(history, rules)
    fc = replay.forecast(target)
    assert fc is not None
    rated = fc.centre("goals_for", "side_a")
    assert rated is not None
    got = live_centre(target, "goals_for", "side_a", 1.2, fc, (), rules,
                      phase="late")
    assert got == pytest.approx((0.95 * rated[0] + 0.05 * 1.2) * math.exp(0.05))
    # no phase, or a market without a coefficient: the blend alone
    assert live_centre(target, "goals_for", "side_a", 1.2, fc, (), rules
                       ) == pytest.approx(0.95 * rated[0] + 0.05 * 1.2)
    # a market without a fitted W keeps W_FOOTBALL_RATING
    rc = fc.centre("corners_for", "side_a")
    assert rc is not None
    assert live_centre(target, "corners_for", "side_a", 4.0, fc, (), rules,
                       phase="late") == pytest.approx(
        fr.W_FOOTBALL_RATING * rc[0] + (1 - fr.W_FOOTBALL_RATING) * 4.0)
    # the phases are computed only when the term is on
    assert FootballRatingReplay(history, CentreRules(football_rating=True)
                                ).phases == {}
    assert set(replay.phases) == {r.event_id for r in history}


# --------------------------------------------------------------------------
# B5: the tennis per-set markets off the neighbours
# --------------------------------------------------------------------------

COEF = {"TOUR": [0.0, 0.8, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]}
PLAYERS = 30


def _tennis_history(n_days: int = 80, per_day: int = 24) -> list[TennisResult]:
    rng = random.Random(9)
    strength = {p: rng.gauss(0.0, 1.0) for p in range(1, PLAYERS + 1)}
    out: list[TennisResult] = []
    for d in range(n_days):
        for k in range(per_day):
            h, a = rng.sample(range(1, PLAYERS + 1), 2)
            home_won = rng.random() < 1.0 / (1.0 + math.exp(strength[a] - strength[h]))
            sets = [(6, rng.randint(0, 4)), (rng.randint(0, 4), 6)]
            if rng.random() < 0.6:
                sets.append((6, rng.randint(0, 4)))
            else:
                sets[1] = (6, sets[1][0])
            if not home_won:
                sets = [(y, x) for x, y in sets]
            out.append(TennisResult(
                event_id=len(out) + 1, ts=T0 + d * DAY + k * 3000, tier="TOUR",
                surface="hard", home_id=h, away_id=a, home_won=home_won,
                sets=tuple(sets), minutes=95.0, completed=True))
    return out


def _tennis_played(history: list[TennisResult]) -> list[Played]:
    out = []
    for r in history:
        values = {"games": (float(sum(x for x, _ in r.sets)),
                            float(sum(y for _, y in r.sets)))}
        for i, (x, y) in enumerate(r.sets, start=1):
            values[f"games_set{i}"] = (float(x), float(y))
        won = sum(1 for x, y in r.sets if x > y)
        values["sets"] = (float(won), float(len(r.sets) - won))
        out.append(Played(
            event_id=r.event_id, timestamp=r.ts, home_id=r.home_id,
            away_id=r.away_id, sport="tennis", competition_id=1, values=values,
            tennis=TennisContext("ATP", "Hard", False)))
    return out


SET_MARKETS = {"games_set1_total", "games_set2_total", "games_won_set1_for",
               "games_won_set2_for", "games_won_set3_for", "sets_total"}


def test_set_rows_are_read_off_the_neighbours_as_of_the_day(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfc, "TENNIS_SET_RATINGS", True)
    history = _tennis_history()
    played = _tennis_played(history)
    # rows for the last days only (the window the check reads); every earlier
    # match still builds the samples
    rows = list(iter_rows(played, {}, RatingReplay(history, COEF, tuple(FEATURES)),
                          emit_from=T0 + 75 * DAY, emit_to=T0 + 77 * DAY))
    assert rows and min(r.event_id for r in rows) > max(
        m.event_id for m in played if m.timestamp < T0 + 75 * DAY)
    got = {r.market for r in rows}
    assert SET_MARKETS <= got
    assert "games_set3_total" not in got and "sets_for" not in got
    by_event: dict[int, list[cfc.SettledRow]] = {}
    for r in rows:
        if r.market in SET_MARKETS:
            by_event.setdefault(r.event_id, []).append(r)
    checked: dict[str, int] = dict.fromkeys(SET_MARKETS, 0)
    models: dict[int, object] = {}
    for match in [m for m in played if m.timestamp >= T0 + 75 * DAY][:40]:
        cut = match.timestamp - match.timestamp % DAY
        if cut not in models:
            models[cut] = build_model(history, COEF, cut)
        fc = models[cut].forecast(  # type: ignore[attr-defined]
            match.home_id, match.away_id, "ATP", "Hard",
            datetime.fromtimestamp(match.timestamp, UTC))
        if fc is None:
            continue
        for r in by_event.get(match.event_id, []):
            side = (None if r.market.endswith("_total")
                    else "side_a" if r.subject == str(match.home_id) else "side_b")
            want = fc.read(r.market, side, r.line, r.direction)
            assert want is not None
            assert r.p_central == pytest.approx(want, abs=1e-6)
            checked[r.market] += 1
    assert all(v > 5 for v in checked.values()), checked


def test_set_values_reads_the_set_score() -> None:
    event = {"homeScore": {"current": 2, "period1": 6, "period2": 3, "period3": 7},
             "awayScore": {"current": 1, "period1": 4, "period2": 6, "period3": 5}}
    assert set_values(event) == {
        "games_set1": (6.0, 4.0), "games_set2": (3.0, 6.0),
        "games_set3": (7.0, 5.0), "sets": (2.0, 1.0)}
    two = {"homeScore": {"current": 0, "period1": 3, "period2": 4},
           "awayScore": {"current": 2, "period1": 6, "period2": 6}}
    assert set_values(two) == {"games_set1": (3.0, 6.0),
                               "games_set2": (4.0, 6.0), "sets": (0.0, 2.0)}


# --------------------------------------------------------------------------
# prepare_refit: the flags reach the replay and the fit's fitted_from
# --------------------------------------------------------------------------


def test_rebuild_passes_the_new_flags_and_records_them(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _db(paths.db_path)
    seen: list[list[str]] = []
    inner = _fake_calibrate(paths.db_path)

    def runner(cmd: Sequence[str], env: dict[str, str], log: Path | None
               ) -> tuple[int, list[str]]:
        seen.append(list(cmd))
        return inner(cmd, env, log)

    pr.rebuild_cache_rows(paths, dry_run=False, confirm=True, runner=runner,
                          require_db_backup=False)
    for flag in ("--football-rating", "--rated-scope", "--venue-prior",
                 "--game-state", "--rating-weight", "--season-phase",
                 "--tennis-set-ratings"):
        assert flag not in seen[0]
    (paths.config_dir / "sofa_game_state.json").write_text(
        json.dumps({"markets": {"corners_for": {"beta": 0.1}}}))
    with pytest.raises(pr.RefitError, match="sofa_rating_weight.json is absent"):
        pr.rebuild_cache_rows(
            paths, dry_run=False, confirm=True, runner=runner,
            require_db_backup=False, football_rating=True, rating_weight=True)
    for name in ("sofa_rating_weight.json", "sofa_season_phase.json"):
        (paths.config_dir / name).write_text("{}")
    report = pr.rebuild_cache_rows(
        paths, dry_run=False, confirm=True, runner=runner,
        require_db_backup=False, football_rating=True, rated_scope=True,
        venue_prior=True, game_state=True, rating_weight=True,
        season_phase=True, tennis_set_ratings=True)
    for flag in ("--football-rating", "--rated-scope", "--venue-prior",
                 "--game-state", "--rating-weight", "--season-phase",
                 "--tennis-set-ratings"):
        assert flag in seen[1]
    assert report["football_rating"] and report["tennis_set_ratings"]
    rules = pr.read_replay_rules(paths)
    assert rules is not None and rules["flags"]["football_rating"] is True
    assert rules["flags"]["game_state"] is True

    calib = tmp_path / "cal.json"
    calib.write_text(json.dumps({"fitted_from": {"db_path": "x"}, "pooled": {}}))
    pr.stamp_replay_rules(calib, rules)
    doc = json.loads(calib.read_text())
    assert doc["fitted_from"]["db_path"] == "x"
    assert doc["fitted_from"]["replay_rules"]["flags"]["tennis_set_ratings"]


def test_rebuild_refuses_the_centre_terms_without_the_rating(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _db(paths.db_path)
    with pytest.raises(pr.RefitError, match="need --football-rating"):
        pr.rebuild_cache_rows(paths, dry_run=False, confirm=True,
                              runner=_fake_calibrate(paths.db_path),
                              require_db_backup=False, game_state=True)
    with pytest.raises(pr.RefitError, match="tennis rating"):
        pr.rebuild_cache_rows(paths, dry_run=False, confirm=True,
                              runner=_fake_calibrate(paths.db_path),
                              require_db_backup=False, tennis_rating=False,
                              tennis_set_ratings=True)


def test_the_replay_refuses_the_centre_terms_without_the_rating(
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["calibrate_from_cache.py", "--venue-prior"])
    with pytest.raises(SystemExit):
        cfc.main()
    assert "need --football-rating" in capsys.readouterr().err
