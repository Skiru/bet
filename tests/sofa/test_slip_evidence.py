"""bet.sofa.slip_evidence: a chat slip leg's league / h2h / referee evidence,
cut at the match's kickoff - a past day rebuilt (the 2026-10-31 backtest)
never reads a game played after the match."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from bet.sofa import referees, slip_evidence
from bet.sofa.dossier import matchup_key
from tests.sofa.test_dossier import DAY, KICK, _stats, ev, make_db

LEG = {"sofascore_event_id": 500, "sport": "football", "match": "Alfa - Beta",
       "market": "corners_total", "subject": "", "line": 7.5, "direction": "OVER",
       "confidence": 0.8, "offered_odds": 1.3}


def _day(tmp_path: Path) -> tuple[Path, Path]:
    events = [
        ev(301, KICK - 5 * DAY, 1, 2, 1, 0),  # Alfa - Beta, before the match
        ev(302, KICK - 30 * DAY, 2, 1, 0, 0),  # Beta - Alfa, before
        ev(303, KICK + DAY, 1, 2, 2, 2),  # a meeting AFTER the kickoff
        ev(304, KICK - 3 * DAY, 1, 3, 1, 1),
    ]
    detail = ev(500, KICK, 1, 2, 0, 0, status="notstarted")
    db = tmp_path / "sofa.db"
    make_db(db, events, detail)
    con = sqlite3.connect(db)
    for eid, corners in ((301, (6, 4)), (302, (2, 2)), (303, (15, 9)), (304, (5, 5))):
        con.execute(
            "INSERT INTO sofa_event_stats (sofascore_event_id, fetched_at, "
            "statistics_json, status_type) VALUES (?, ?, ?, ?)",
            (eid, "2026-10-25T08:00:00+00:00", _stats(corners, (50, 50)), "finished"))
    con.commit()
    con.close()
    run = tmp_path / "runs" / "2026-10-20"
    run.mkdir(parents=True)
    (run / "02_fixtures.json").write_text(json.dumps([{
        "sofascore_event_id": 500, "home_entity_id": 1, "away_entity_id": 2,
        "home_name": "Alfa", "away_name": "Beta",
        "kickoff_utc": "2026-10-20T12:00:00Z"}]))
    return db, run


def test_h2h_reads_only_meetings_before_the_kickoff(tmp_path: Path) -> None:
    db, run = _day(tmp_path)
    got = slip_evidence.evidence_for_legs(run, [LEG], db_path=db)
    cell = got[matchup_key(LEG)]
    # 301: 10 corners (over 7.5), 302: 4 (under); 303 after the kickoff with 24
    # would make it 2/3
    assert cell["h2h"] == "1/2"
    # four cached games of the season: no league share below LEAGUE_RATE_MIN
    assert "league" not in cell
    assert "referee" not in cell  # corners are no referee metric


def test_referee_games_stop_at_the_kickoff(tmp_path: Path) -> None:
    db, _ = _day(tmp_path)
    referees.ensure_schema(db)
    con = sqlite3.connect(db)
    for eid, start in ((500, KICK), (301, KICK - 5 * DAY), (302, KICK - 30 * DAY),
                       (303, KICK + DAY)):
        con.execute(
            "INSERT INTO sofa_event_referee (event_id, referee_id, referee_name, "
            "start_ts, unique_tournament_id, sport, source, fetched_at) "
            "VALUES (?, 7, 'X', ?, 77, 'football', 'test', '2026-10-25')",
            (eid, start))
    con.commit()
    games = slip_evidence._referee_games(con, 500, KICK, ["corners_total"])
    assert sorted(g["corners_total"] for g in games) == [4, 10]  # never 303's 24
    assert slip_evidence._referee_games(con, 500, KICK, []) == []
    con.close()


def test_a_match_without_both_team_ids_gets_nothing(tmp_path: Path) -> None:
    db, run = _day(tmp_path)
    (run / "02_fixtures.json").write_text(json.dumps([{
        "sofascore_event_id": 500, "home_entity_id": 1,
        "kickoff_utc": "2026-10-20T12:00:00Z"}]))
    assert slip_evidence.evidence_for_legs(run, [LEG], db_path=db) == {}
    assert slip_evidence.evidence_for_legs(run, [{**LEG, "market": "player_shots"}],
                                           db_path=db) == {}
