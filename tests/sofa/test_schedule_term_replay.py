"""epochs.SCHEDULE_TERM in the curve fitters (--schedule-term): one full
calendar read per match equals SHEET's windowed read; each fitter's hook puts
exactly exp(t) on the pure rating goals centres (DC / 1X2 / DNB replay, the
first goal, the simulator - whose 0.60-floor keys keep the uncorrected
centres); off, nothing moves and nothing is stamped; the flag is recorded;
the simulator curves' dated staged read. Offline, synthetic."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import football_rating as fr
from bet.sofa import football_sim_curves as fsc
from bet.sofa import schedule_term as st
from bet.sofa.confidence import Calibration
from bet.sofa.config import config_path
from bet.sofa.football_incidents import FIRST_GOAL, first_goal_probs
from bet.sofa.football_sim import MinuteMatch, neutral_params
from bet.sofa.schedule_features import DAY_S, Calendar, calendar_from_events
from scripts.sofa import fit_double_chance_curve as dc_fit
from scripts.sofa import fit_football_sim_curves as fsim
from scripts.sofa import fit_incident_set_curves as fisc
from scripts.sofa import fit_result_1x2_dnb_curve as f1x2
from scripts.sofa import fit_score_market_curves as fscore
from tests.sofa.test_fit_incident_set_curves import _rec
from tests.sofa.test_schedule_features import ev
from tests.sofa.test_schedule_term import (
    UCL,
    K,
    _db,
    _keys,
    _synthetic_events,
    _terms,
)


def _installed_terms() -> st.ScheduleTerms:
    return _terms(**json.loads(config_path(st.CONFIG_FILE).read_text())["coef"])


# --- the per-match read == SHEET's windowed read ---------------------------------


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_the_replay_read_equals_the_windowed_sheet_read(
    tmp_path: Path, seed: int,
) -> None:
    events = _synthetic_events(seed)
    keys = _keys(events)
    terms = _installed_terms()
    conn = _db(tmp_path, events)
    sheet = st.fixture_terms(conn, keys, terms, [UCL])
    replay = st.ReplayTerms(calendar_from_events(events, "football", [UCL]), terms)
    moved = 0
    for k in keys:
        got = replay.term(k.event_id, k.kickoff_ts, k.home_id, k.away_id,
                          k.competition_id, k.season_id)
        want = sheet[k.event_id]
        assert (got.status, got.t_home, got.t_away) == (
            want.status, want.t_home, want.t_away)
        if got.status == st.APPLIED:
            assert (got.home, got.away) == (want.home, want.away)
        moved += got.moves
    assert moved > 4
    assert sum(replay.statuses.values()) == len(keys)
    # the loader reads the same calendar from the DB's listings (read-only)
    loaded = st.load_replay_terms(tmp_path / "x.db", terms, [UCL])
    assert len(loaded.calendar) == len(replay.calendar)


def test_the_replay_read_takes_the_listed_season_and_national_flag() -> None:
    events = [ev(1, K - 3 * DAY_S, 1, 2), ev(2, K - 4 * DAY_S, 3, 4),
              ev(3, K, 1, 3, national=True, season=5),
              # sides 5 / 6: 30 days off since season 7, the fixture opens 8
              ev(4, K - 30 * DAY_S, 5, 6, season=7), ev(5, K, 5, 6, season=8)]
    terms = _terms(own_R5_season_start=-0.3, own_R5_other=-0.1)
    rt = st.ReplayTerms(calendar_from_events(events, "football", [UCL]), terms)
    assert rt.term(3, K, 1, 3, 17).status == st.NATIONAL
    # no season given: the listing's (what the windowed key's
    # Fixture.season_id carries) - the season start, not "other"
    got = rt.term(5, K, 5, 6, 17)
    assert got.home is not None and got.home.layoff_kind == "season_start"
    assert got.t_home == pytest.approx(-0.3) and got.moves
    assert rt.term(5, K, 5, 6, 17, season_id=7).t_home == pytest.approx(-0.1)


def test_scale_is_the_wrappers_arithmetic() -> None:
    from tests.sofa.test_schedule_term import _forecast

    base = _forecast()
    w = st.ScheduleTermForecast.wrap(base, -0.0731, 0.0412)
    for side, t in (("side_a", -0.0731), ("side_b", 0.0412)):
        b, c = base.centre("goals_for", side), w.centre("goals_for", side)
        assert b is not None and c is not None
        assert c[0] == st.scale(b[0], t)  # bit for bit
    assert st.scale(1.37, 0.0) == 1.37


# --- the hooks --------------------------------------------------------------------


class FixedTerms(st.ReplayTerms):
    """A ReplayTerms whose term per event id is given (the hooks' tests)."""

    def __init__(self, ts: dict[int, tuple[float, float]]) -> None:
        super().__init__(Calendar(sport="football"), _installed_terms())
        self.ts = ts

    def term(self, event_id: int, kickoff_ts: int, home_id: int, away_id: int,
             competition_id: int | None, season_id: int | None = None,
             national: bool | None = None) -> st.FixtureTerm:
        th, ta = self.ts.get(event_id, (0.0, 0.0))
        status = st.APPLIED if (th or ta) else st.NO_COVERAGE
        self.statuses[status] = self.statuses.get(status, 0) + 1
        return st.FixtureTerm(status, th, ta, None, None)


def _league(n: int = 150) -> list[fr.FootballResult]:
    out = []
    for i in range(n):
        h, a = 1 + i % 6, 1 + (i + 1 + i // 6) % 6
        if h == a:
            a = 1 + (a % 6)
        out.append(fr.FootballResult(i + 1, 1_700_000_000 + i * DAY_S, 9, h, a,
                                     {"goals_for": (float(i % 3), float(i % 2))}))
    return out


def _terms_for(history: Sequence[fr.FootballResult]) -> dict[int, tuple[float, float]]:
    return {r.event_id: ((-0.1, 0.05) if r.event_id % 3 else (0.0, 0.0))
            for r in history}


def test_dc_replay_puts_exp_t_on_both_goals_centres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = _league()
    monkeypatch.setattr(dc_fit, "SCHEDULE", None)
    off = dc_fit.replay(history, 0, 2**31)
    monkeypatch.setattr(dc_fit, "SCHEDULE", FixedTerms(_terms_for(history)))
    on = dc_fit.replay(history, 0, 2**31)
    assert len(off) == len(on) > 20
    moved = 0
    for a, b in zip(off, on, strict=True):
        th, ta = _terms_for(history)[a.event_id]
        assert b.lh == st.scale(a.lh, th) and b.la == st.scale(a.la, ta)
        assert (b.x, b.y, b.link, b.ts) == (a.x, a.y, a.link, a.ts)
        moved += b.lh != a.lh
    assert moved > 10
    # the 1X2 / DNB fit reads the same replay (dc_fit.replay), so its lh / la
    assert f1x2.replay is dc_fit.replay


def test_the_stamp_is_empty_off_and_names_the_flag_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(dc_fit, "SCHEDULE", None)
    monkeypatch.setattr(dc_fit, "SCHEDULE_DB", None)
    assert dc_fit.schedule_stamp(["--cup-strength"]) == {}
    rt = FixedTerms({})
    rt.term(1, 0, 1, 2, 9)
    monkeypatch.setattr(dc_fit, "SCHEDULE", rt)
    monkeypatch.setattr(dc_fit, "SCHEDULE_DB", "copy.db")
    got = dc_fit.schedule_stamp(["--schedule-term", "--cup-strength"])
    assert got["replay_rules"]["flags"] == ["--cup-strength", "--schedule-term"]
    stamp = got["schedule_term"]
    assert stamp["flag"] == "--schedule-term" and stamp["calendar_db"] == "copy.db"
    assert stamp["rule"] == "schedule_term_v1" and len(stamp["config_sha256"]) == 64
    assert stamp["statuses"] == {st.NO_COVERAGE: 1}
    assert "SCHEDULE_COVERAGE_DAYS" in stamp["unfitted_constants"]


def test_the_flag_needs_a_db_and_is_off_by_default() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    dc_fit.add_schedule_args(ap)
    off = ap.parse_args([])
    assert dc_fit.schedule_db(off) is None and dc_fit.replay_flags(off) == []
    with pytest.raises(SystemExit, match="--db-path"):
        dc_fit.schedule_db(ap.parse_args(["--schedule-term"]))
    on = ap.parse_args(["--schedule-term", "--db-path", "c.db"])
    assert dc_fit.schedule_db(on) == "c.db"
    assert dc_fit.replay_flags(on) == ["--schedule-term"]


def test_the_1x2_cache_carries_the_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pickle

    hist = tmp_path / "h.pkl"
    hist.write_bytes(pickle.dumps(("fp", _league())))
    cache = tmp_path / "m.csv.gz"
    monkeypatch.setattr(f1x2, "phases_by_event", lambda h: {})
    monkeypatch.setattr(dc_fit, "SCHEDULE", FixedTerms({}))
    fp, rows = f1x2.load_matches(hist, 0, 2**31, cache)
    assert fp == "fp" + f1x2.SCHEDULE_TAG and rows
    assert len(f1x2.load_matches(hist, 0, 2**31, cache)[1]) == len(rows)
    monkeypatch.setattr(dc_fit, "SCHEDULE", None)
    with pytest.raises(SystemExit, match="schedule-term"):
        f1x2.load_matches(hist, 0, 2**31, cache)
    fp_off, _ = f1x2.load_matches(hist, 0, 2**31, None)
    assert fp_off == "fp"


def test_score_curves_take_the_rule_of_their_rows(tmp_path: Path) -> None:
    rows = tmp_path / "rows.csv.gz"
    assert fscore.rows_schedule_term(rows) is None
    (tmp_path / "curves.json").write_text(json.dumps(
        {"fitted_from": {"awarded_excluded": True}}))
    assert fscore.rows_schedule_term(rows) is None
    (tmp_path / "curves.json").write_text(json.dumps(
        {"fitted_from": {"schedule_term": {"flag": "--schedule-term"}}}))
    assert fscore.rows_schedule_term(rows) == {"flag": "--schedule-term"}


def test_first_goal_reads_the_corrected_centres_and_rates_do_not_move(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = _league(260)
    records = {r.event_id: _rec(1 if r.event_id % 4 == 0 else 0) for r in history}
    end = history[-1].ts + DAY_S
    monkeypatch.setattr(dc_fit, "SCHEDULE", None)
    off = fisc.replay_football(history, records, end, 7.0)
    monkeypatch.setattr(dc_fit, "SCHEDULE", FixedTerms(_terms_for(history)))
    on = fisc.replay_football(history, records, end, 7.0)

    def key(r: dict[str, Any]) -> tuple[Any, ...]:
        return (r["event_id"], r["key"], r["subject"], r["line"])

    a = {key(r): r for r in off}
    b = {key(r): r for r in on}
    assert set(a) == set(b)
    fg_moved = 0
    for k, r in a.items():
        if r["market"] != FIRST_GOAL:
            assert b[k]["p"] == r["p"]  # red cards / penalties: no centre
            continue
        fg_moved += b[k]["p"] != r["p"]
    assert fg_moved > 10
    # one match by hand: first_goal_probs on centre x exp(t)
    book = fr.RatingBook(shared_league_link=True)
    book.unit_strength_from_parent = False
    probe = history[-1]
    for done in history[:-1]:
        if done.ts - done.ts % DAY_S < probe.ts - probe.ts % DAY_S:
            book.update(done)
    fc = fr.FootballForecast(book, probe.competition_id, probe.home_id, probe.away_id)
    ch, ca = fc.centre("goals_for", "side_a"), fc.centre("goals_for", "side_b")
    assert ch is not None and ca is not None
    th, ta = _terms_for(history)[probe.event_id]
    want = first_goal_probs(st.scale(ch[0], th), st.scale(ca[0], ta), 7.0)
    got = {r["subject"]: r["p"] for r in on
           if r["event_id"] == probe.event_id and r["market"] == FIRST_GOAL}
    assert got and all(got[s] == round(want[s], 6) for s in got)


def _minute(eid: int = 1) -> MinuteMatch:
    return MinuteMatch(event_id=eid, ts=0, competition_id=1, home_id=1, away_id=2,
                       women=False, ft=(2, 1), ht=(1, 0), goals=((1, 10, 0),),
                       reds=(), added=(None, None))


def test_the_simulator_moves_every_key_but_the_floor_keys() -> None:
    values = {"goals_for": (1.6, 0.9), "cards_points_for": (20.0, 25.0)}
    term = st.FixtureTerm(st.APPLIED, -0.2, 0.15, None, None)
    base = fsim.centres_of_values(values)
    corr = fsim.centres_of_values(values, term)
    assert base is not None and corr is not None
    assert corr.goals == (st.scale(1.6, -0.2), st.scale(0.9, 0.15))
    assert corr.cards == base.cards == (20.0, 25.0)
    assert fsim.centres_of_values(values, None) == base
    excluded = _installed_terms().excluded_markets
    assert excluded == {"btts_any_half", "btts_halves", "half_goals_combo",
                        "team_scores_both_halves"}
    fsim._init(neutral_params().to_json(), frozenset(excluded))
    try:
        m = _minute()
        plain = {(r["market"], r["subject"], r["direction"]): r["p"]
                 for r in fsim.rows_for((m, base))}
        moved = {(r["market"], r["subject"], r["direction"]): r["p"]
                 for r in fsim.rows_for((m, corr, base))}
        alt = {(r["market"], r["subject"], r["direction"]): r["p"]
               for r in fsim.rows_for((m, corr))}
        # off: a 3-tuple with equal centres is the 2-tuple
        assert {(r["market"], r["subject"], r["direction"]): r["p"]
                for r in fsim.rows_for((m, base, base))} == plain
    finally:
        fsim._init(neutral_params().to_json())
    assert set(plain) == set(moved)
    changed = 0
    for k, p in moved.items():
        if k[0] in excluded:
            assert p == plain[k]  # the floor keys: uncorrected
        else:
            assert p == alt[k]  # every other key: the corrected simulation
            changed += p != plain[k]
    assert changed > 5


def test_every_hooked_fitter_takes_the_flag() -> None:
    repo = Path(__file__).resolve().parents[2]
    for script in ("fit_double_chance_curve", "fit_result_1x2_dnb_curve",
                   "fit_score_market_curves", "fit_incident_set_curves",
                   "fit_football_sim_curves"):
        src = (repo / "scripts" / "sofa" / f"{script}.py").read_text()
        assert "--schedule-term" in src, script
        assert "schedule_term" in src, script


# --- the simulator curves' dated staged read --------------------------------------


def _write(path: Path, doc: dict[str, Any]) -> Path:
    path.write_text(json.dumps(doc))
    return path


def test_sim_curves_read_the_staged_file_from_its_start(tmp_path: Path) -> None:
    main = _write(tmp_path / fsc.FILE, {"by_market_direction": {}})
    assert fsc.path_for("2026-11-12", datetime(2026, 11, 12, tzinfo=UTC), main) == main
    staged = _write(tmp_path / "sofa_football_sim_curves.next.2026-11-12.json",
                    {"effective_from": "2026-11-12T00:00:00Z"})
    later = _write(tmp_path / "sofa_football_sim_curves.next.2026-11-14.json",
                   {"effective_from": "2026-11-14T00:00:00Z"})
    _write(tmp_path / "sofa_football_sim_curves.next.json", {
        "effective_from": "2026-11-01T00:00:00Z"})  # undated: never read
    at = datetime(2026, 11, 13, 9, tzinfo=UTC)
    assert fsc.path_for("2026-11-11", at, main) == main
    assert fsc.path_for("2026-11-12", at, main) == staged
    assert fsc.path_for("2026-11-13", at, main) == staged
    # the day reached, the build clock not yet
    assert fsc.path_for("2026-11-12", datetime(2026, 11, 11, 23, tzinfo=UTC),
                        main) == main
    assert fsc.path_for("2026-11-15", datetime(2026, 11, 15, tzinfo=UTC),
                        main) == later
    # a staged file without effective_from is never read
    _write(later, {})
    assert fsc.path_for("2026-11-15", datetime(2026, 11, 15, tzinfo=UTC),
                        main) == staged
    _write(later, {"effective_from": "2026-11-13T00:00:00Z"})
    with pytest.raises(ValueError, match="disagrees"):
        fsc.path_for("2026-11-15", datetime(2026, 11, 15, tzinfo=UTC), main)


def test_for_day_overlays_the_staged_curves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    curve = {"0.700-0.725": {"n": 500, "realised": 0.8, "realised_lo95": 0.77}}
    _write(tmp_path / fsc.FILE, {"by_market_direction": {"htft|OVER": curve}})
    staged = {**curve, "0.725-0.750": {"n": 500, "realised": 0.9,
                                       "realised_lo95": 0.88}}
    _write(tmp_path / "sofa_football_sim_curves.next.2026-11-12.json", {
        "effective_from": "2026-11-12T00:00:00Z",
        "by_market_direction": {"htft|OVER": staged}})
    cal = Calibration.load()
    monkeypatch.setattr(fsc, "config_path", lambda name: tmp_path / name)
    before = fsc.for_day(cal, "2026-11-11", datetime(2026, 11, 11, 12, tzinfo=UTC))
    after = fsc.for_day(cal, "2026-11-12", datetime(2026, 11, 12, 1, tzinfo=UTC))
    assert before.by_market_direction["htft|OVER"] == curve
    assert after.by_market_direction["htft|OVER"] == staged


def test_the_staged_sim_curves_start_with_the_schedule_term() -> None:
    """The live config: the installed file until 2026-11-10 00:00Z, then the
    schedule term's refit staged as sofa_football_sim_curves.next.2026-11-10.json
    (effective_from = epochs.SCHEDULE_TERM_FROM_UTC); its four 0.60-floor keys
    are the installed file's."""
    import json

    from bet.sofa import epochs

    main = config_path(fsc.FILE)
    staged = main.parent / "sofa_football_sim_curves.next.2026-11-10.json"
    assert fsc.staged_paths(main.parent) == [staged]
    at = epochs.SCHEDULE_TERM_FROM_UTC
    assert at == datetime(2026, 11, 10, tzinfo=UTC)
    assert fsc.path_for("2026-11-09", datetime(2026, 11, 9, 23, tzinfo=UTC)) == main
    assert fsc.path_for("2026-11-10", at) == staged
    assert fsc.path_for("2026-11-10", at - timedelta(minutes=1)) == main
    inst = json.loads(main.read_text())["by_market_direction"]
    new = json.loads(staged.read_text())["by_market_direction"]
    for market in epochs.SCHEDULE_TERM_FLOOR_EXCLUDED:
        for d in ("OVER", "UNDER"):
            assert inst.get(f"{market}|{d}") == new.get(f"{market}|{d}")
