"""DAY_ANCHOR (identity plan K2): the anchor team's only game in the hour is
this hockey / basketball / volleyball event, whatever the other name says;
epochs.DAY_ANCHOR_FROM_UTC; scripts/sofa/measure_day_anchor.py's backtest."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from bet.sofa import entity_map as em
from bet.sofa import epochs
from bet.sofa import sport_identity as si
from bet.sofa.db import get_connection, migrate
from scripts.sofa import measure_day_anchor as mda
from tests.sofa.test_sport_identity import AT, KICK, FakeClient, _ev, _listed, _series

TEAMS = {"Tryhoop Okayama": 337532}


def _one(
    listing: list[dict],
    t1: str = "Tryhoop Okayama",
    t2: str = "Takamatsu",
    ids: dict[str, int] | None = None,
    on: bool = True,
    sport: str = "basketball",
    query: int = 337532,
) -> dict:
    ids = TEAMS if ids is None else ids
    (r,), _ = si.identify(
        [_ev("1", t1, t2, sport=sport)],
        FakeClient({query: listing}),
        None,
        lambda s, n: ids.get(n),
        AT,
        "2026-10-06",
        day_anchor=on,
    )
    return r


def _bb(
    eid: int,
    home: tuple[int, str],
    away: tuple[int, str],
    start: datetime = KICK,
    **kw: object,
) -> dict:
    e = _listed(eid, home, away, start, slug="basketball")
    e.update(kw)
    return e


def test_the_anchor_teams_only_game_is_this_event_whatever_the_name() -> None:
    # 2026-10-14: Superbet "Tryhoop Okayama - Takamatsu", Sofascore
    # "Tryhoop Okayama - Kagawa Five Arrows" 16491061: no name in common.
    listing = [
        _bb(16491061, (337532, "Tryhoop Okayama"), (124602, "Kagawa Five Arrows"))
    ]
    off = _one(listing, on=False)
    assert off["status"] == si.NOT_IDENTIFIED and off["reason"] == "NO_MATCH_IN_LISTING"
    r = _one(listing)
    assert r["status"] == si.IDENTIFIED and r["match_method"] == "DAY_ANCHOR"
    assert (r["sofascore_event_id"], r["home_is_team1"]) == (16491061, True)
    assert r["name_scores"]["team1"] == 100.0 and r["name_scores"]["team2"] < 82
    assert r["sofascore_away"] == "Kagawa Five Arrows"


def test_the_anchor_reads_the_orientation_from_its_id() -> None:
    listing = [_bb(5, (124602, "Kagawa Five Arrows"), (337532, "Tryhoop Okayama"))]
    r = _one(listing)
    assert r["status"] == si.IDENTIFIED and r["home_is_team1"] is False
    # the anchor may be team2
    r = _one(listing, t1="Takamatsu", t2="Tryhoop Okayama")
    assert r["status"] == si.IDENTIFIED and r["home_is_team1"] is True


def test_two_games_of_the_anchor_in_the_hour_is_ambiguous() -> None:
    listing = [
        _bb(1, (337532, "Tryhoop Okayama"), (124602, "Kagawa Five Arrows")),
        _bb(2, (9, "Other"), (337532, "Tryhoop Okayama"), KICK + timedelta(minutes=50)),
    ]
    r = _one(listing)
    assert r["status"] == si.NOT_IDENTIFIED and r["reason"] == "AMBIGUOUS"


def test_the_other_sides_own_id_must_be_in_the_game() -> None:
    listing = [_bb(1, (337532, "Tryhoop Okayama"), (124602, "Kagawa Five Arrows"))]
    r = _one(listing, ids={**TEAMS, "Takamatsu": 777})
    assert r["status"] == si.NOT_IDENTIFIED and r["reason"] == "RESOLVED_ID_DISAGREES"
    # ...and the old rule still names the case: Sparta - Kometa against
    # Sparta - Liberec, Kometa resolved elsewhere, is no game of this event
    sparta = [_listed(9001, (10, "Sparta Praha"), (77, "Bili Tygri Liberec"))]
    (r,), _ = si.identify(
        [_ev("1", "Sparta Praha", "Kometa Brno")],
        FakeClient({10: sparta}),
        None,
        lambda s, n: {"Sparta Praha": 10, "Kometa Brno": 20}.get(n),
        AT,
        "2026-10-06",
        day_anchor=True,
    )
    assert r["status"] == si.NOT_IDENTIFIED


def test_the_window_gender_and_schedule_still_hold() -> None:
    late = [
        _bb(
            1,
            (337532, "Tryhoop Okayama"),
            (124602, "Kagawa"),
            KICK + timedelta(minutes=75),
        )
    ]
    assert _one(late)["reason"] == "NO_GAME_WITHIN_1H"
    postponed = [
        _bb(
            1,
            (337532, "Tryhoop Okayama"),
            (124602, "Kagawa"),
            status={"type": "postponed"},
        )
    ]
    assert _one(postponed)["reason"] == "NOT_AS_SCHEDULED"
    women = _bb(1, (337532, "Tryhoop Okayama"), (124602, "Kagawa"))
    women["homeTeam"]["gender"] = women["awayTeam"]["gender"] = "F"
    assert _one([women])["status"] == si.NOT_IDENTIFIED


def test_a_query_only_team_is_no_anchor() -> None:
    listing = [_bb(1, (233932, "CD Español de Talca"), (5, "Colo Colo"))]
    (r,), _ = si.identify(
        [_ev("1", "Espanol de Talca", "U. De Santiago", sport="basketball")],
        FakeClient({233932: listing}),
        None,
        lambda s, n: None,
        AT,
        "2026-10-06",
        query_teams=lambda s, n: 233932 if n == "Espanol de Talca" else None,
        day_anchor=True,
    )
    assert r["status"] == si.NOT_IDENTIFIED


def test_cs2_is_left_out() -> None:
    # 10-06: BAKS - Clutchain on Superbet, BakS - OldBoys on Sofascore
    listing = [
        _series(
            17269864,
            (413708, "BakS eSports"),
            (1133468, "OldBoys"),
            KICK + timedelta(minutes=15),
        )
    ]
    r = _one(
        listing,
        t1="BAKS",
        t2="Clutchain",
        ids={"BAKS": 413708},
        sport="cs2",
        query=413708,
    )
    assert r["status"] == si.NOT_IDENTIFIED


def test_the_switch_is_next_days_midnight() -> None:
    assert epochs.DAY_ANCHOR_FROM_UTC == datetime(2026, 10, 15, tzinfo=UTC)
    assert epochs.day_anchor("2026-10-15", datetime(2026, 10, 15, 0, 1, tzinfo=UTC))
    assert not epochs.day_anchor("2026-10-15", datetime(2026, 10, 14, 23, tzinfo=UTC))
    assert not epochs.day_anchor("2026-10-14", datetime(2026, 10, 15, 6, tzinfo=UTC))


def test_the_opponent_of_a_day_anchor_is_a_candidate_never_learned(
    tmp_path: Path,
) -> None:
    path = str(tmp_path / "s.db")
    migrate(path)
    conn = get_connection(path)
    listing = [
        _bb(16491061, (337532, "Tryhoop Okayama"), (124602, "Kagawa Five Arrows"))
    ]
    r = _one(listing)
    counts = em.learn_records(conn, [r], "2026-10-15T01:00:00Z")
    assert (
        counts[em.CANDIDATE] == 1 and counts[em.LEARNED] == 1
    )  # the anchor's own name
    assert em.held_row(conn, "basketball", "takamatsu") is None
    cand = conn.execute(
        "SELECT superbet_name, candidate_id, reason FROM sofa_entity_candidate"
    ).fetchall()
    assert [tuple(c) for c in cand] == [("Takamatsu", 124602, "DAY_ANCHOR")]


# --- the backtest --------------------------------------------------------------------


def test_anchor_pick_rules() -> None:
    g = {
        1: mda.Game(1, 1000, 10, 20, "M", "notstarted"),
        2: mda.Game(2, 1000 + 7200, 30, 10, "M", "notstarted"),
    }
    assert mda.anchor_pick(g, 10, None, 1000, 3600, "M")[0] == "PICK"
    assert mda.anchor_pick(g, 10, None, 1000, 3 * 3600, "M")[0] == "AMBIGUOUS"
    assert mda.anchor_pick(g, 10, 99, 1000, 3600, "M")[0] == "ID_DISAGREES"
    assert mda.anchor_pick(g, 10, None, 1000, 3600, "W")[0] == "NONE"
    off = {1: mda.Game(1, 1000, 10, 20, "M", "postponed")}
    assert mda.anchor_pick(off, 10, None, 1000, 3600, "M")[0] == "NONE"


def test_predict_needs_the_anchors_to_agree() -> None:
    rec = {
        "kickoff_utc": "1970-01-01T00:16:40Z",
        "team1": "A",
        "team2": "B",
        "team1_id": 10,
        "team2_id": 20,
    }
    by_team = {
        10: {1: mda.Game(1, 1000, 10, 20, "M", "x")},
        20: {1: mda.Game(1, 1000, 10, 20, "M", "x")},
    }
    assert mda.predict(rec, by_team, 3600)[0] == "PICK"
    by_team[20] = {2: mda.Game(2, 1000, 30, 20, "M", "x")}
    assert mda.predict(rec, by_team, 3600)[0] != "PICK"
    assert (
        mda.predict({**rec, "team1_id": None, "team2_id": None}, by_team, 3600)[0]
        == "NO_ANCHOR"
    )


def test_load_games_keeps_the_newest_fetched_version(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "x.db")
    conn.execute(
        "CREATE TABLE sofa_listed_event (event_id INT, sport TEXT,"
        " start_ts INT, fetched_at TEXT, event_json TEXT)"
    )
    conn.execute(
        "CREATE TABLE sofa_entity_events (sofascore_entity_id INT, kind TEXT,"
        " page INT, fetched_at TEXT, events_json TEXT)"
    )
    conn.execute(
        "CREATE TABLE cs2_series (sofascore_event_id INT, start_ts INT,"
        " home_id INT, away_id INT, status_type TEXT, fetched_at TEXT)"
    )
    import json

    def ev(start: int, status: str) -> dict:
        return {
            "id": 1,
            "startTimestamp": start,
            "status": {"type": status},
            "tournament": {"category": {"sport": {"slug": "ice-hockey"}}},
            "homeTeam": {"id": 10, "gender": "M"},
            "awayTeam": {"id": 20, "gender": "M"},
        }

    conn.execute(
        "INSERT INTO sofa_listed_event VALUES (1, 'ice-hockey', 5000,"
        " '2026-10-10T00:00:00+00:00', ?)",
        (json.dumps(ev(5000, "finished")),),
    )
    # an OLD page still shows the game at another date
    conn.execute(
        "INSERT INTO sofa_entity_events VALUES (10, 'next', 0,"
        " '2026-10-01T00:00:00+00:00', ?)",
        (json.dumps({"events": [ev(9000, "notstarted")]}),),
    )
    got = mda.load_games(conn, ["ice-hockey"], 0, {10})
    assert got[10][1].start_ts == 5000 and got[10][1].status == "finished"
