"""P3 / K7 (coverage audit 2026-10-23): a hockey / basketball player's
history from every peer team he played for (player_model.load_appearances
(any_team=True), epochs.player_history_any_team), its in-memory replay in
fit_player_model, and the constants a day reads (player_model.
params_path_for: a dated staged file, never the installed one a built day
reads). Offline: the fake database of test_player_model."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bet.sofa import epochs, player_model
from bet.sofa.player_model import line_probability, load_appearances
from bet.sofa.shadow import ShadowLine
from tests.sofa.test_player_model import (
    AWAY_ID,
    HOME_ID,
    KO_TS,
    SOG,
    T1,
    T2,
    add_game,
    entry,
    hockey_history,
    make_db,
)

PEER, FAR = 30, 40  # a team A met; a team neither A nor B met
DAY = 86400


def _traded_history(conn: sqlite3.Connection) -> None:
    """Novak's eight games for HOME (test_player_model.hockey_history);
    Ball (7) six games for PEER against FAR, one for PEER against HOME, then
    one for HOME; Lyubushkin (8) six games for PEER, none for HOME / AWAY;
    Far (9) plays only for FAR."""
    hockey_history(conn, games=8)
    for i in range(6):
        add_game(
            conn,
            300 + i,
            KO_TS - (40 + i) * DAY,
            [
                entry(PEER, 7, "LaMelo Ball", {"secondsPlayed": 1000, "shots": 5}),
                entry(PEER, 8, "Ilya Lyubushkin", {"secondsPlayed": 900, "shots": 1}),
                entry(FAR, 9, "Far Away", {"secondsPlayed": 900, "shots": 9}),
            ],
            home=PEER,
            away=FAR,
            names=("Peer HC", "Far HC"),
        )
    add_game(
        conn,
        310,
        KO_TS - 30 * DAY,
        [
            entry(HOME_ID, 1, "Jan Novak", {"secondsPlayed": 1200, "shots": 3}),
            entry(PEER, 7, "LaMelo Ball", {"secondsPlayed": 1000, "shots": 6}),
        ],
        home=HOME_ID,
        away=PEER,
        names=(T1, "Peer HC"),
    )
    add_game(
        conn,
        320,
        KO_TS - 1 * DAY,
        [entry(HOME_ID, 7, "LaMelo Ball", {"secondsPlayed": 1100, "shots": 4})],
    )
    conn.commit()


def _sog(subject: str) -> ShadowLine:
    return ShadowLine("1", SOG, "player_shots_on_goal", 0, subject, 2.5, "OVER", 1.9)


def _apps(conn: sqlite3.Connection, any_team: bool) -> list[player_model.Appearance]:
    return load_appearances(
        conn, "hockey", [HOME_ID, AWAY_ID], KO_TS - 60, None,
        team_from_side=True, any_team=any_team,
    )


def test_a_traded_player_keeps_his_former_peers_games(tmp_path: Path) -> None:
    conn = make_db(tmp_path / "db.sqlite")
    _traded_history(conn)
    old = line_probability(_sog("Ball, LaMelo"), "hockey", _apps(conn, False))
    new = line_probability(_sog("Ball, LaMelo"), "hockey", _apps(conn, True))
    # Before: one game for his new team. After: that one, and PEER's seven.
    assert old.p is None and old.reason == "THIN_SAMPLE" and old.n == 1
    assert new.p is not None and new.n == 8 and new.player_id == 7
    # FAR was never an opponent of HOME / AWAY: its players are not read.
    assert 9 not in {a.player_id for a in _apps(conn, True)}


def test_the_pool_and_an_untraded_player_are_unchanged(tmp_path: Path) -> None:
    conn = make_db(tmp_path / "db.sqlite")
    _traded_history(conn)
    off, on = _apps(conn, False), _apps(conn, True)
    assert [a for a in on if not a.foreign] == off
    assert all(a.team_id == PEER for a in on if a.foreign)
    for prm in player_model.load_params().values():
        a = line_probability(_sog("Novak, Jan"), "hockey", off, prm)
        b = line_probability(_sog("Novak, Jan"), "hockey", on, prm)
        assert a == b and a.p is not None


def test_a_player_new_to_both_teams_is_found_among_the_peers(tmp_path: Path) -> None:
    conn = make_db(tmp_path / "db.sqlite")
    _traded_history(conn)
    off = line_probability(_sog("Lyubushkin, Ilya"), "hockey", _apps(conn, False))
    on = line_probability(_sog("Lyubushkin, Ilya"), "hockey", _apps(conn, True))
    assert off.p is None and off.reason == "NOT_IN_HISTORY"
    assert on.p is not None and on.n == 6 and on.player_id == 8
    # A team player is always asked first: Novak is not looked up abroad.
    assert player_model.find_player("Novak, Jan", _apps(conn, True)) == (1, None)


def test_two_peers_agreeing_are_nobody(tmp_path: Path) -> None:
    conn = make_db(tmp_path / "db.sqlite")
    _traded_history(conn)
    add_game(
        conn,
        330,
        KO_TS - 20 * DAY,
        [entry(PEER, 18, "I. Lyubushkin", {"secondsPlayed": 900, "shots": 1})],
        home=PEER,
        away=FAR,
        names=("Peer HC", "Far HC"),
    )
    conn.commit()
    got = line_probability(_sog("Lyubushkin, Ilya"), "hockey", _apps(conn, True))
    assert got.p is None and got.reason == "NAME_UNCERTAIN"


def test_any_team_needs_the_side_rule(tmp_path: Path) -> None:
    conn = make_db(tmp_path / "db.sqlite")
    _traded_history(conn)
    with pytest.raises(ValueError):
        load_appearances(conn, "hockey", [HOME_ID], KO_TS, None, any_team=True)


def test_the_replay_reproduces_the_any_team_sample(tmp_path: Path) -> None:
    from scripts.sofa import fit_player_model as fpm

    conn = make_db(tmp_path / "db.sqlite")
    _traded_history(conn)
    target = 900
    add_game(
        conn,
        target,
        KO_TS,
        [
            entry(HOME_ID, 7, "LaMelo Ball", {"secondsPlayed": 1000, "shots": 3}),
            entry(HOME_ID, 1, "Jan Novak", {"secondsPlayed": 1000, "shots": 3}),
        ],
    )
    conn.commit()
    specs = fpm.family_specs("hockey")
    sog = [s.family for s in specs].index("player_shots_on_goal")
    cutoff = player_model.history_cutoff(KO_TS, KO_TS)
    sql = load_appearances(
        conn, "hockey", [HOME_ID, AWAY_ID], cutoff, target,
        team_from_side=True, any_team=True,
    )
    spec = player_model.PLAYER_MARKETS["hockey"][SOG]
    for any_team, n_ball in ((False, None), (True, 8)):
        history = fpm.History.from_db(
            conn, "hockey", team_from_side=True, any_team=any_team
        )
        recs = {r.pid: r for r in fpm.replay_game(history, target, specs)}
        if n_ball is None:
            assert 7 not in recs  # one game: below MIN_APPEARANCES
            continue
        ball = recs[7]
        own = player_model.own_sample(7, sql, spec, 60)
        assert [(ts, s, v[sog]) for ts, s, v in ball.own] == [
            (a.ts, a.seconds, x) for a, x in own
        ]
        # The pool is the two teams' alone, as line_probability's.
        prm = player_model.sport_params("hockey")
        got = fpm.record_distribution(ball, sog, "player_shots_on_goal", prm)
        assert got is not None
        p = player_model.calibrate_side(
            player_model.side_probability(_sog("Ball, LaMelo"), got[0]) or 0.0,
            prm.calibration_b,
        )
        assert line_probability(
            _sog("Ball, LaMelo"), "hockey", sql, prm
        ).p == pytest.approx(p, abs=1e-12)
        assert recs[1].own == {
            r.pid: r
            for r in fpm.replay_game(
                fpm.History.from_db(conn, "hockey", team_from_side=True),
                target,
                specs,
            )
        }[1].own


def _record() -> dict[str, object]:
    return {
        "fetched_at_utc": "2026-09-28T14:00:00Z",
        "superbet_event_id": "1",
        "kickoff_utc": "2026-09-28T16:00:00Z",
        "team1": T1,
        "team2": T2,
        "lines": [
            ShadowLine(
                "1", SOG, "player_shots_on_goal", 0, "Ball, LaMelo", 2.5, side, odds
            ).as_dict()
            for side, odds in (("OVER", 1.8), ("UNDER", 2.0))
        ],
    }


def _forecast(db: Path) -> list[dict[str, object]]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return player_model.forecast_records(
            conn, "hockey", "ice-hockey", [_record()], "x", set(), KO_TS
        )
    finally:
        conn.close()


def test_the_forecast_follows_the_days_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "db.sqlite"
    conn = make_db(db)
    _traded_history(conn)
    conn.close()
    early = datetime(2026, 9, 1, tzinfo=UTC)
    monkeypatch.setattr(epochs, "PLAYER_TEAM_FROM_SIDE_FROM_UTC", early)
    monkeypatch.setattr(epochs, "PLAYER_HISTORY_ANY_TEAM_FROM_UTC", None)
    monkeypatch.setattr(
        epochs, "PLAYER_HISTORY_ANY_TEAM_SPORTS", frozenset({"hockey"})
    )
    off = _forecast(db)
    assert {r["model_reason"] for r in off} == {"THIN_SAMPLE"}
    assert all("player_history_rule" not in r for r in off)
    # Switched on after this snapshot's clock: still off.
    monkeypatch.setattr(
        epochs, "PLAYER_HISTORY_ANY_TEAM_FROM_UTC", datetime(2026, 9, 29, tzinfo=UTC)
    )
    assert _forecast(db) == off
    monkeypatch.setattr(epochs, "PLAYER_HISTORY_ANY_TEAM_FROM_UTC", early)
    # On, but not for this sport.
    monkeypatch.setattr(
        epochs, "PLAYER_HISTORY_ANY_TEAM_SPORTS", frozenset({"basketball"})
    )
    assert _forecast(db) == off
    monkeypatch.setattr(
        epochs, "PLAYER_HISTORY_ANY_TEAM_SPORTS", frozenset({"hockey"})
    )
    on = _forecast(db)
    assert all(r["model_p"] is not None and r["model_n"] == 8 for r in on)
    assert {r["player_history_rule"] for r in on} == {
        player_model.PLAYER_HISTORY_RULE
    }


def _staged(config: Path, day: str, eff: str | None = None) -> Path:
    doc = json.loads(
        player_model.config_path(player_model.PARAMS_FILE).read_text(encoding="utf-8")
    )
    doc["effective_from"] = eff or day
    doc["fitted_from"] = {**doc["fitted_from"], "fitted_at_utc": f"staged-{day}"}
    path = config / f"sofa_player_model.next.{day}.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_a_staged_file_is_read_from_its_day_and_clock(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    main = config / player_model.PARAMS_FILE
    main.write_text(
        player_model.config_path(player_model.PARAMS_FILE).read_text(encoding="utf-8")
    )
    at = datetime(2026, 10, 24, 1, tzinfo=UTC)
    assert player_model.params_path_for("2026-10-24", at, config) == main
    staged = _staged(config, "2026-10-24")
    assert player_model.params_path_for("2026-10-24", at, config) == staged
    assert player_model.params_path_for("2026-10-25", at, config) == staged
    # A built day, and a coming day's game forecast before that day begins.
    assert player_model.params_path_for("2026-10-23", at, config) == main
    before = datetime(2026, 10, 23, 20, tzinfo=UTC)
    assert player_model.params_path_for("2026-10-24", before, config) == main
    assert player_model.config_identity(staged)["model_config"] == "staged-2026-10-24"
    _staged(config, "2026-10-26", eff="2026-10-27")
    with pytest.raises(ValueError):
        player_model.params_path_for("2026-10-24", at, config)


def test_the_switch_is_judged_per_sport(monkeypatch: pytest.MonkeyPatch) -> None:
    at = datetime(2026, 10, 24, 1, tzinfo=UTC)
    monkeypatch.setattr(
        epochs, "PLAYER_HISTORY_ANY_TEAM_FROM_UTC", datetime(2026, 10, 24, tzinfo=UTC)
    )
    monkeypatch.setattr(
        epochs, "PLAYER_HISTORY_ANY_TEAM_SPORTS", frozenset({"hockey"})
    )
    assert epochs.player_history_any_team("2026-10-24", at, "hockey")
    assert not epochs.player_history_any_team("2026-10-24", at, "basketball")
    # A call without a sport is football's.
    assert not epochs.player_history_any_team("2026-10-24", at)
    assert not epochs.player_history_any_team("2026-10-23", at, "hockey")
