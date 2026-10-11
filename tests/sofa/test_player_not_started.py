"""A footballer who did not START voids his player market (operator, 2026-10-11).

Patrik Walemark (Lech, 2026-10-10) came on for 30 minutes with 2 shots on
target; Superbet returned his "celne strzały powyżej 0.5" as "Zwrot" while
SETTLE graded it WIN. 2,685 of 12,322 settled player rows of 10-05..10-10
were such bench appearances. SETTLE now says PLAYER_NOT_STARTED, and
`regrade_settled.py --player-not-started` deletes the live rows graded before.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

from bet.sofa.db import migrate
from bet.sofa.players import STARTED_KEY, squad_statistics, started
from bet.sofa.settleability import IDENTITY_REASONS
from scripts.sofa import run_settle

REPO = Path(__file__).resolve().parents[2]


def _entry(name: str, shots: int | None, substitute: bool | None) -> dict[str, Any]:
    entry: dict[str, Any] = {"player": {"name": name}}
    if shots is not None:
        entry["statistics"] = {"minutesPlayed": 30, "totalShots": shots}
    if substitute is not None:
        entry["substitute"] = substitute
    return entry


def _lineups(*away: dict[str, Any]) -> dict[str, Any]:
    return {"home": {"players": [_entry("Someone Home", 1, False)]},
            "away": {"players": list(away)}}


def _row(subject: str = "Patrik Walemark") -> dict[str, Any]:
    return {"market": "player_shots_for", "subject": subject, "line": 0.5,
            "direction": "OVER"}


def test_the_squad_says_who_started() -> None:
    squad = squad_statistics(_lineups(
        _entry("Patrik Wålemark", 2, True),
        _entry("Mikael Ishak", 3, False),
        _entry("Unused Sub", None, True),
        _entry("Old Payload", 1, None),
    ), is_home=False)
    assert squad is not None
    assert started(squad["patrik walemark"]) is False
    assert started(squad["mikael ishak"]) is True
    # An unused substitute has no statistics: nothing is added, so his entry
    # stays empty and reads as "no statistics", as before.
    assert squad["unused sub"] == {}
    assert started(squad["old payload"]) is None
    assert STARTED_KEY not in squad["old payload"]


def test_settle_voids_a_player_who_came_off_the_bench() -> None:
    squads = {True: squad_statistics(_lineups(), is_home=True),
              False: squad_statistics(_lineups(_entry("Patrik Wålemark", 2, True)),
                                      is_home=False)}
    assert run_settle._settle_player(_row(), squads, False) == "PLAYER_NOT_STARTED"


def test_settle_grades_a_starter_as_before() -> None:
    squads = {True: squad_statistics(_lineups(), is_home=True),
              False: squad_statistics(_lineups(_entry("Patrik Wålemark", 2, False)),
                                      is_home=False)}
    assert run_settle._settle_player(_row(), squads, False) == (2.0, "WIN")


def test_did_not_play_is_still_did_not_play() -> None:
    lineups = _lineups({"player": {"name": "Patrik Wålemark"},
                        "statistics": {"totalShots": 0}, "substitute": True})
    squads = {True: squad_statistics(lineups, is_home=True),
              False: squad_statistics(lineups, is_home=False)}
    assert run_settle._settle_player(_row(), squads, False) == "PLAYER_DID_NOT_PLAY"


def test_a_payload_without_the_flag_is_graded() -> None:
    """Every cached football squad carries `substitute` (3,000 sampled
    matches, 2026-10-11); one that does not is graded, not guessed void."""
    squads = {True: None,
              False: squad_statistics(_lineups(_entry("Patrik Wålemark", 2, None)),
                                      is_home=False)}
    assert run_settle._settle_player(_row(), squads, False) == (2.0, "WIN")


def test_settleability_reads_it_as_a_subject_reason() -> None:
    assert "PLAYER_NOT_STARTED" in IDENTITY_REASONS


def _db(tmp_path: Path, day: str, substitute: bool) -> tuple[Path, Path]:
    runs = tmp_path / "runs"
    (runs / day).mkdir(parents=True)
    (runs / day / "02_fixtures.json").write_text(json.dumps([
        {"sofascore_event_id": 7, "home_entity_id": 10, "away_entity_id": 20}]))
    (runs / day / "03_samples.json").write_text(json.dumps([
        {"sofascore_event_id": 7,
         "players": {"player_shots_for|Patrik Walemark": {"side": "side_b"}}}]))
    db = tmp_path / "s.db"
    migrate(str(db))
    con = sqlite3.connect(db)
    event = {"id": 7, "homeTeam": {"id": 10}, "awayTeam": {"id": 20},
             "status": {"type": "finished", "code": 100}}
    con.execute(
        "insert into sofa_event_detail (sofascore_event_id, fetched_at, status_type,"
        " detail_json) values (7, '2026-10-11T00:00:00Z', 'finished', ?)",
        (json.dumps({"event": event}),))
    con.execute(
        "insert into sofa_event_stats (sofascore_event_id, fetched_at, status_type,"
        " statistics_json, incidents_json, lineups_json) values"
        " (7, '2026-10-11T00:00:00Z', 'finished', NULL, NULL, ?)",
        (json.dumps(_lineups(_entry("Patrik Wålemark", 2, substitute))),))
    con.execute(
        "insert into sofa_settled_row (run_date, sofascore_event_id, sport,"
        " competition_id, market, subject, line, direction, sample_size,"
        " sample_mean, sample_sd, p_central, p_bar, market_p, actual_value,"
        " outcome, settled_at, offered_odds, verdict) values"
        " (?, 7, 'football', 1, 'player_shots_for', 'Patrik Walemark', 0.5, 'OVER',"
        " 10, 1.8, 1.0, 0.7, 0.7, NULL, 2.0, 'WIN', '2026-10-11T00:00:00Z',"
        " 1.28, 'BELOW_BAR')", (day,))
    con.commit()
    con.close()
    return runs, db


def _regrade(runs: Path, db: Path, *flags: str) -> subprocess.CompletedProcess[str]:
    env = {"PYTHONPATH": "src:.", "PATH": "/usr/bin:/bin",
           "SOFA_RUNS_DIR": str(runs), "SOFA_DB_PATH": str(db)}
    return subprocess.run(
        [sys.executable, "scripts/sofa/regrade_settled.py", "--player-not-started",
         *flags], cwd=REPO, capture_output=True, text=True, env=env)


def _count(db: Path) -> int:
    con = sqlite3.connect(db)
    try:
        return int(con.execute("select count(*) from sofa_settled_row").fetchone()[0])
    finally:
        con.close()


def test_regrade_deletes_a_bench_row_and_keeps_an_undo_copy(tmp_path: Path) -> None:
    runs, db = _db(tmp_path, "2026-10-10", substitute=True)
    dry = _regrade(runs, db, "--dry-run")
    assert dry.returncode == 0, dry.stderr
    assert '"delete": 1' in dry.stdout
    assert _count(db) == 1  # a dry run writes nothing
    done = _regrade(runs, db, "--apply")
    assert done.returncode == 0, done.stderr
    assert _count(db) == 0
    logs = list(runs.glob("regrade_*.json"))
    assert logs
    undo = json.loads(logs[0].read_text())
    assert undo["mode"] == "player-not-started"
    assert undo["actions"][0]["row"]["subject"] == "Patrik Walemark"


def test_regrade_keeps_a_starter_row(tmp_path: Path) -> None:
    runs, db = _db(tmp_path, "2026-10-10", substitute=False)
    done = _regrade(runs, db, "--apply")
    assert done.returncode == 0, done.stderr
    assert '"kept": 1' in done.stdout
    assert _count(db) == 1


# --- a printed leg of a voided player is a refund (7c and the ledger) -------


def test_settle_lists_the_void_leg_and_7c_reads_it_as_a_refund(
    tmp_path: Path, monkeypatch: Any
) -> None:
    from datetime import UTC, datetime

    from scripts.sofa import audit_settlement

    day = "2026-10-10"
    run_dir = tmp_path / "runs" / day
    run_dir.mkdir(parents=True)
    row = {"sofascore_event_id": 7, "sport": "football",
           "market": "player_shots_on_target_for", "subject": "Patrik Walemark",
           "line": 0.5, "direction": "OVER", "sample_size": 7, "sample_mean": 1.3,
           "sample_sd": 0.9, "p_central": 0.7, "p_bar": 0.6, "market_p": None,
           "offered_odds": 1.28, "verdict": "BELOW_BAR"}
    (run_dir / "05_sheet.json").write_text(json.dumps([row]))
    (run_dir / "02_fixtures.json").write_text(json.dumps([
        {"sofascore_event_id": 7, "sport": "football",
         "kickoff_utc": "2026-10-10T15:30:00Z", "home_entity_id": 10,
         "away_entity_id": 20, "home_name": "Śląsk", "away_name": "Lech"}]))
    (run_dir / "03_samples.json").write_text(json.dumps([
        {"sofascore_event_id": 7, "players": {
            "player_shots_on_target_for|Patrik Walemark": {"side": "side_b"}}}]))
    start = int(datetime(2026, 10, 10, 15, 30, tzinfo=UTC).timestamp())
    event = {"id": 7, "startTimestamp": start,
             "homeTeam": {"id": 10}, "awayTeam": {"id": 20},
             "status": {"type": "finished", "code": 100},
             "tournament": {"uniqueTournament": {"id": 202}}}
    lineups = _lineups({"player": {"name": "Patrik Wålemark"}, "substitute": True,
                        "statistics": {"minutesPlayed": 30, "totalShots": 2,
                                       "onTargetScoringAttempt": 2}})
    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("SOFA_DB_PATH", str(tmp_path / "sofa.db"))
    monkeypatch.setenv("SOFA_MAX_CONCURRENCY", "1")
    monkeypatch.setattr(run_settle, "SofascoreClient", lambda config: object())
    monkeypatch.setattr(run_settle, "SofaCache", lambda config: object())
    monkeypatch.setattr(run_settle, "_event_payload",
                        lambda c, k, e, r=False: (event, None, None))
    monkeypatch.setattr(run_settle, "fetch_lineups", lambda c, k, e: lineups)
    monkeypatch.setattr(sys, "argv", ["run_settle", "--date", day])
    run_settle.main()
    assert json.loads((run_dir / "07_settled.json").read_text()) == []
    skips = json.loads((run_dir / "07_settle_skips.json").read_text())
    assert skips["void_legs"] == [{
        "sofascore_event_id": 7, "market": "player_shots_on_target_for",
        "subject": "Patrik Walemark", "line": 0.5, "direction": "OVER",
        "reason": "PLAYER_NOT_STARTED"}]
    key = (7, "player_shots_on_target_for", "Patrik Walemark", 0.5, "OVER")
    graded = audit_settlement.coupon_settled_by_key(
        str(tmp_path / "sofa.db"), run_dir, day, {key})
    assert graded[key]["outcome"] == audit_settlement.REFUND
    assert graded[key]["reason"] == "PLAYER_NOT_STARTED"


def test_the_void_legs_reader_skips_a_malformed_entry() -> None:
    from bet.sofa.settle import void_leg_keys

    doc = {"void_legs": [
        {"sofascore_event_id": 7, "market": "player_shots_for", "subject": "A",
         "line": 0.5, "direction": "OVER", "reason": "PLAYER_DID_NOT_PLAY"},
        {"broken": True}]}
    assert void_leg_keys(doc) == {
        (7, "player_shots_for", "A", 0.5, "OVER"): "PLAYER_DID_NOT_PLAY"}
    assert void_leg_keys(None) == {}


# --- not in the matchday squad at all -----------------------------------------


def _evander_squads() -> dict[bool, Any]:
    lineups = {"home": {"players": [_entry("Miguel Almirón", 2, False)]},
               "away": {"players": [_entry("Kévin Denkey", 3, False),
                                    _entry("Pavel Bucha", 1, False)]}}
    return {True: squad_statistics(lineups, is_home=True),
            False: squad_statistics(lineups, is_home=False)}


def test_a_sampled_player_missing_from_his_matchday_squad_is_void() -> None:
    """Evander (Cincinnati, 2026-10-10): printed in the e2e replay, not in
    the 20-man squad - Superbet voids it; PLAYER_NOT_MATCHED left it pending."""
    row = {"market": "player_shots_for", "subject": "Evander", "line": 1.5,
           "direction": "OVER"}
    squads = _evander_squads()
    assert run_settle._settle_player(row, squads, False) == "PLAYER_NOT_MATCHED"
    assert run_settle._settle_player(row, squads, False, None, "evander") == (
        "PLAYER_NOT_IN_SQUAD")
    # Without his side the squad cannot be named: not matched, as before.
    assert run_settle._settle_player(row, squads, None, None, "evander") == (
        "PLAYER_NOT_MATCHED")


def test_a_token_candidate_in_his_squad_is_not_called_absent() -> None:
    row = {"market": "player_shots_for", "subject": "Denkey, Kevin Ayeboe",
           "line": 1.5, "direction": "OVER"}
    squads = _evander_squads()
    assert run_settle._settle_player(row, squads, False, None, "kevin denkey ii") == (
        "PLAYER_NOT_MATCHED")


def test_not_in_squad_is_a_void_reason() -> None:
    from bet.sofa.settle import PLAYER_VOID_REASONS

    assert PLAYER_VOID_REASONS == {
        "PLAYER_DID_NOT_PLAY", "PLAYER_NOT_STARTED", "PLAYER_NOT_IN_SQUAD"}
    assert "PLAYER_NOT_IN_SQUAD" in IDENTITY_REASONS


def test_sample_names_come_from_every_sample() -> None:
    doc = [{"sofascore_event_id": 7, "players": {
        "player_shots_for|Evander": {"matched_name": "evander", "side": "side_b"},
        "player_shots_for|X": {"side": "side_a"}}}]
    assert run_settle.player_sample_names(doc) == {
        (7, "player_shots_for|Evander"): "evander"}
