"""Audit 2026-10-13 B15 / A5 in the cache replay: calibrate_from_cache
--opponent-correction rescales a football sample exactly as SHEET does under
epochs.SAMPLE_OPPONENT_CORRECTION (bet.sofa.opponent_correction, run_sheet.
process_fixture), so a refit can fit the football curves on the corrected
centre. Off = the rows as before, byte for byte. Offline and synthetic."""

from __future__ import annotations

import random
import statistics
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bet.sofa import football_rating as fr
from bet.sofa.contracts import MetricSample, Observation
from bet.sofa.opponent_correction import (
    CORRECTED_METRICS,
    SampleCorrector,
    correct_total,
    corrected_metric,
)
from scripts.sofa import calibrate_from_cache as cfc
from scripts.sofa import prepare_refit as pr
from scripts.sofa.calibrate_from_cache import (
    MIN_SAMPLE,
    SAMPLE_N,
    CentreRules,
    FootballRatingReplay,
    Played,
    ReplayOpponentCorrection,
    iter_rows,
    live_centre,
)
from scripts.sofa.run_sheet import deduplicate_observations
from tests.sofa.test_prepare_refit import _db, _fake_calibrate, _paths

DAY = 86400
T0 = 1_750_000_000 - 1_750_000_000 % DAY
LEAGUES = {1: 17, 2: 17, 3: 17, 4: 17, 5: 29, 6: 29, 7: 29, 8: 29}
CUP = 99
BASELINES = {
    "corners_for": {"global": {"mean": 5.0, "n": 5000}},
    "corners_total": {"global": {"mean": 10.0, "n": 5000}},
    "goals_for": {"global": {"mean": 1.3, "n": 5000}},
    "goals_total": {"global": {"mean": 2.6, "n": 5000}},
}
RATED = CentreRules(football_rating=True)
CORRECTED = CentreRules(football_rating=True, opponent_correction=True)


def _football(days: int = 50, seed: int = 11
              ) -> tuple[list[fr.FootballResult], list[Played]]:
    """Two leagues of four (league 29 stronger on corners), league matches
    every day and a cross-league cup tie every third day - so samples hold
    opponents of both leagues and some pairs are not LINKED."""
    rng = random.Random(seed)
    attack = {t: rng.uniform(0.6, 1.5) + (0.6 if LEAGUES[t] == 29 else 0.0)
              for t in LEAGUES}
    defence = {t: rng.uniform(0.6, 1.5) for t in LEAGUES}
    history: list[fr.FootballResult] = []
    played: list[Played] = []
    eid = 5000
    for d in range(days):
        pairs: list[tuple[int, int, int]] = [
            (*rng.sample([1, 2, 3, 4], 2), 17), (*rng.sample([5, 6, 7, 8], 2), 29)]
        if d % 3 == 0:
            pairs.append((rng.choice([1, 2, 3, 4]), rng.choice([5, 6, 7, 8]), CUP))
        for k, (h, a, comp) in enumerate(pairs):
            ts = T0 + d * DAY + 3600 * (12 + 2 * k)
            gh, ga = float(rng.randint(0, 3)), float(rng.randint(0, 2))
            ch = float(max(0, round(rng.gauss(4 * attack[h] * defence[a], 1.5))))
            ca = float(max(0, round(rng.gauss(4 * attack[a] * defence[h], 1.5))))
            history.append(fr.FootballResult(
                event_id=eid, ts=ts, competition_id=comp, home_id=h, away_id=a,
                values={"goals_for": (gh, ga), "corners_for": (ch, ca)}))
            played.append(Played(
                event_id=eid, timestamp=ts, home_id=h, away_id=a,
                sport="football", competition_id=comp,
                values={"goals": (gh, ga), "corners": (ch, ca)}))
            eid += 1
    return history, played


def _key(r: cfc.SettledRow) -> tuple[int, str, str, float, str]:
    return (r.event_id, r.market, r.subject, r.line, r.direction)


# --- off = as before ------------------------------------------------------


def test_the_correction_is_off_by_default() -> None:
    assert cfc.CENTRE_RULES.opponent_correction is False
    assert CentreRules().describe()["opponent_correction"] is False


def test_off_the_rows_are_the_rows_without_it() -> None:
    """Off: the rated replay's rows are untouched by the new code. On with a
    book that rates nobody: every observation stays raw, field for field."""
    history, played = _football()
    plain = list(iter_rows(played, BASELINES))
    unrated = list(iter_rows(played, BASELINES, None, frozenset(),
                             FootballRatingReplay([], CORRECTED)))
    assert plain and unrated == plain
    rated = list(iter_rows(played, BASELINES, None, frozenset(),
                           FootballRatingReplay(history, RATED)))
    again = list(iter_rows(played, BASELINES, None, frozenset(),
                           FootballRatingReplay(history, RATED)))
    assert rated == again


def test_goals_stay_raw_and_corners_move() -> None:
    history, played = _football()
    rated = {_key(r): r for r in iter_rows(
        played, BASELINES, None, frozenset(), FootballRatingReplay(history, RATED))}
    corrected = {_key(r): r for r in iter_rows(
        played, BASELINES, None, frozenset(),
        FootballRatingReplay(history, CORRECTED))}
    assert corrected_metric("goals_for") is None
    assert corrected_metric("corners_total") == "corners_for"
    goals = {k for k in rated if k[1].startswith("goals_")}
    assert goals and all(corrected[k] == rated[k] for k in goals)
    moved = [k for k in rated if k[1].startswith("corners_") and k in corrected
             and corrected[k].sample_mean != rated[k].sample_mean]
    assert moved


# --- on = SHEET's sample ----------------------------------------------------


def _observations(before: Sequence[Played], team: int, total: bool
                  ) -> list[Observation]:
    """SAMPLES' corners sample of `team` (newest SAMPLE_N), as Observations
    with the B13 opponent fields SHEET corrects from."""
    out: list[Observation] = []
    for m in before:
        if team not in (m.home_id, m.away_id):
            continue
        home = m.home_id == team
        own, other = m.values["corners"] if home else m.values["corners"][::-1]
        opp = m.away_id if home else m.home_id
        out.append(Observation(
            sofascore_event_id=m.event_id,
            match_date_utc=datetime.fromtimestamp(m.timestamp, UTC),
            opponent=f"T{opp}", value=own + other if total else own,
            competition_id=m.competition_id, season_id=1,
            venue="home" if home else "away", opponent_id=opp,
            against=None if total else other))
    return out[-SAMPLE_N:]


def test_on_the_sample_and_the_centre_are_sheets() -> None:
    """For each late fixture: the replay's corrected corners_for / _total
    sample is what run_sheet computes from the same observations - the
    SampleCorrector on the book as of the day for a side, correct_total then
    deduplicate_observations for a total - and the row is priced at that
    sample's live centre."""
    history, played = _football()
    football = FootballRatingReplay(history, CORRECTED)
    rows = list(iter_rows(played, BASELINES, None, frozenset(), football))
    constants = cfc._load_engine_constants()
    checked_side = checked_total = cross = 0
    for target in played[-15:]:
        cut = target.timestamp - target.timestamp % DAY
        book = fr.replay(history, cut, shared_league_link=True)
        sheet = SampleCorrector(book)
        before = [m for m in played if m.timestamp < target.timestamp]
        home, away = target.home_id, target.away_id
        fc = fr.FootballForecast(book, target.competition_id or 0, home, away)
        for side, team, other in (("side_a", home, away), ("side_b", away, home)):
            obs = _observations(before, team, total=False)
            if len(obs) < MIN_SAMPLE:
                continue
            values = [o.value for o in sheet.correct(obs, "corners_for", team, other)]
            cross += sum(1 for o in obs
                         if book.link(team, o.opponent_id or 0, "corners_for")[0]
                         != fr.LINKED)
            mine = [r for r in rows if r.event_id == target.event_id
                    and r.market == "corners_for" and r.subject == str(team)]
            assert mine
            assert mine[0].sample_mean == round(statistics.mean(values), 4)
            assert mine[0].sample_mean != round(
                statistics.mean(o.value for o in obs), 4)
            want = cfc._settle_centred(
                target, "corners_for", str(team), mine[0].actual, values,
                BASELINES, constants, None,
                lambda c, s=side, o=obs: live_centre(
                    target, "corners_for", s, c, fc,
                    tuple(x.venue for x in o)))
            assert [(r.line, r.direction, r.p_central) for r in want] == [
                (r.line, r.direction, r.p_central) for r in mine]
            checked_side += 1
        side_a = _observations(before, home, total=True)
        side_b = _observations(before, away, total=True)
        if len(side_a) < MIN_SAMPLE or len(side_b) < MIN_SAMPLE:
            continue
        metrics = {
            "corners_total": MetricSample(metric="corners_total", side_a=side_a,
                                          side_b=side_b, h2h=[]),
            "corners_for": MetricSample(
                metric="corners_for",
                side_a=_observations(before, home, total=False),
                side_b=_observations(before, away, total=False), h2h=[]),
        }
        pooled = deduplicate_observations(
            correct_total(sheet, metrics, "corners_total", home, away))
        mine = [r for r in rows if r.event_id == target.event_id
                and r.market == "corners_total"]
        assert mine
        assert mine[0].sample_size == len(pooled)
        assert mine[0].sample_mean == round(
            statistics.mean(o.value for o in pooled), 4)
        checked_total += 1
    assert checked_side >= 10 and checked_total >= 3
    assert cross  # the sample held non-LINKED opponents too


def test_the_side_and_total_helpers_match_the_corrector() -> None:
    """ReplayOpponentCorrection on Past tuples = SampleCorrector on the same
    observations, including an unknown opponent (raw) and a shared meeting
    of the two sides (read from the home side's list, as dedup keeps it)."""
    history, played = _football()
    target = played[-1]
    cut = target.timestamp - target.timestamp % DAY
    book = fr.replay(history, cut, shared_league_link=True)
    replay = ReplayOpponentCorrection(book)
    home, away = target.home_id, target.away_id
    meeting = cfc.Past(T0, 1, 3.0, 8.0, 17, True, "home", away)
    home_past = [cfc.Past(T0 + i, 10 + i, 4.0 + i, 9.0 + i, 17, True, "home",
                          opp) for i, opp in enumerate((3, 4, None, 6))]
    home_past.append(meeting)
    away_past = [cfc.Past(T0 + 50, 1, 5.0, 8.0, 17, True, "away", home),
                 cfc.Past(T0 + 51, 60, 2.0, 7.0, 29, True, "away", 7)]
    corrector = SampleCorrector(book)
    side = corrector.correct(
        [Observation(sofascore_event_id=p.event_id,
                     match_date_utc=datetime.fromtimestamp(p.timestamp, UTC),
                     opponent="x", value=p.own, competition_id=17, season_id=1,
                     venue=None, opponent_id=p.opponent, against=None)
         for p in home_past], "corners_for", home, away)
    assert replay.side(home_past, "corners_for", home, away) == [
        o.value for o in side]
    assert replay.side(home_past, "goals_for", home, away) == [
        p.own for p in home_past]
    got = replay.total(home_past, away_past, "corners_total", home, away)
    assert len(got) == len(home_past) + 1  # the meeting once
    f = corrector.factors(home, away, away, "corners_for")
    assert f is not None
    assert got[-2] == pytest.approx(3.0 * f[0] + 5.0 * f[1])
    assert got[2] == 11.0  # unknown opponent: raw
    assert "corners_for" in CORRECTED_METRICS


# --- flags ---------------------------------------------------------------


def test_the_replay_refuses_the_correction_without_the_rating(
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv",
                        ["calibrate_from_cache.py", "--opponent-correction"])
    with pytest.raises(SystemExit):
        cfc.main()
    assert "--opponent-correction need --football-rating" in capsys.readouterr().err


def test_prepare_refit_passes_and_records_the_flag(tmp_path: Path) -> None:
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
                              require_db_backup=False, opponent_correction=True)
    pr.rebuild_cache_rows(paths, dry_run=False, confirm=True, runner=runner,
                          require_db_backup=False, football_rating=True)
    assert "--opponent-correction" not in seen[-1]
    rules = pr.read_replay_rules(paths)
    assert rules is not None and rules["flags"]["opponent_correction"] is False
    pr.rebuild_cache_rows(paths, dry_run=False, confirm=True, runner=runner,
                          require_db_backup=False, football_rating=True,
                          opponent_correction=True)
    assert "--opponent-correction" in seen[-1]
    rules = pr.read_replay_rules(paths)
    assert rules is not None and rules["flags"]["opponent_correction"] is True
    args = pr.build_parser().parse_args(
        ["rebuild-cache-rows", "--football-rating", "--opponent-correction"])
    assert args.opponent_correction is True
