"""A2 (plan 2026-10-05): a player prop is graded only from his own squad.

`_settle_player` searched the home squad first and took the first name over
the 85 threshold, so an away "Weverson" could be graded off a home
"Reverson" (token_sort_ratio 87.5). The squad SAMPLES matched him in
(03_samples.json players[...].side, side_a = home) now decides, and a name
the other squad matches as well is PLAYER_AMBIGUOUS.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa.db import migrate
from scripts.sofa import run_settle

REPO = Path(__file__).resolve().parents[2]


def _stats(shots: int) -> dict[str, Any]:
    return {"minutesPlayed": 90, "totalShots": shots}


def _row(subject: str, line: float = 1.5) -> dict[str, Any]:
    return {"market": "player_shots_for", "subject": subject, "line": line,
            "direction": "OVER"}


SQUADS = {True: {"reverson": _stats(0)}, False: {"weverson": _stats(3)}}


def test_the_away_player_is_not_graded_off_a_home_namesake() -> None:
    assert run_settle._settle_player(_row("Weverson"), SQUADS, False) == (3.0, "WIN")


def test_the_old_search_order_would_have_taken_the_home_name() -> None:
    # Without the away squad, home's Reverson still clears the threshold: the
    # defect the side rule removes.
    only_home = {True: SQUADS[True], False: None}
    assert run_settle._settle_player(_row("Weverson"), only_home, None) == (0.0, "LOSS")
    # With his own side known, the home squad is never searched.
    assert run_settle._settle_player(_row("Weverson"), only_home, False) == (
        "PLAYER_NOT_MATCHED")


def test_without_a_side_a_hit_in_both_squads_is_ambiguous() -> None:
    assert run_settle._settle_player(_row("Weverson"), SQUADS, None) == (
        "PLAYER_AMBIGUOUS")


def test_a_name_in_both_squads_is_ambiguous_even_with_a_side() -> None:
    squads = {True: {"pedro silva": _stats(2)}, False: {"pedro silva": _stats(0)}}
    assert run_settle._settle_player(_row("Silva, Pedro"), squads, True) == (
        "PLAYER_AMBIGUOUS")


def test_the_sample_side_reads_onto_the_events_home_and_away() -> None:
    fixture = {"home_entity_id": 10, "away_entity_id": 20}
    same = {"homeTeam": {"id": 10}, "awayTeam": {"id": 20}}
    swapped = {"homeTeam": {"id": 20}, "awayTeam": {"id": 10}}
    other = {"homeTeam": {"id": 30}, "awayTeam": {"id": 40}}
    assert run_settle.player_own_home("side_b", fixture, same) is False
    assert run_settle.player_own_home("side_b", fixture, swapped) is True
    assert run_settle.player_own_home("side_a", fixture, other) is None
    assert run_settle.player_own_home(None, fixture, same) is None


def test_player_sides_reads_03_samples() -> None:
    samples = [{"sofascore_event_id": 7, "players": {
        "player_shots_for|Weverson": {"side": "side_b"},
        "player_shots_for|Odd": {"side": "nowhere"}}}]
    assert run_settle.player_sides(samples) == {
        (7, "player_shots_for|Weverson"): "side_b"}


# ---------------------------------------------------------------------------
# regrade_settled.py --players
# ---------------------------------------------------------------------------


def _lineups() -> dict[str, Any]:
    def side(name: str, shots: int) -> dict[str, Any]:
        return {"players": [{"player": {"name": name}, "statistics": _stats(shots)}]}
    return {"home": side("Reverson", 0), "away": side("Weverson", 3)}


def test_regrade_players_flips_a_row_graded_off_the_wrong_squad(tmp_path: Path) -> None:
    day = "2026-09-24"
    runs = tmp_path / "runs"
    (runs / day).mkdir(parents=True)
    (runs / day / "02_fixtures.json").write_text(json.dumps([
        {"sofascore_event_id": 7, "home_entity_id": 10, "away_entity_id": 20}]))
    (runs / day / "03_samples.json").write_text(json.dumps([
        {"sofascore_event_id": 7,
         "players": {"player_shots_for|Weverson": {"side": "side_b"}}}]))
    db = tmp_path / "s.db"
    migrate(str(db))
    con = sqlite3.connect(db)
    event = {"id": 7, "homeTeam": {"id": 10}, "awayTeam": {"id": 20},
             "status": {"type": "finished", "code": 100}}
    con.execute(
        "insert into sofa_event_detail (sofascore_event_id, fetched_at, status_type,"
        " detail_json) values (7, '2026-09-25T00:00:00Z', 'finished', ?)",
        (json.dumps({"event": event}),),
    )
    con.execute(
        "insert into sofa_event_stats (sofascore_event_id, fetched_at, status_type,"
        " statistics_json, incidents_json, lineups_json) values"
        " (7, '2026-09-25T00:00:00Z', 'finished', NULL, NULL, ?)",
        (json.dumps(_lineups()),),
    )
    con.execute(
        "insert into sofa_settled_row (run_date, sofascore_event_id, sport,"
        " competition_id, market, subject, line, direction, sample_size,"
        " sample_mean, sample_sd, p_central, p_bar, market_p, actual_value,"
        " outcome, settled_at, offered_odds, verdict) values"
        " (?, 7, 'football', 1, 'player_shots_for', 'Weverson', 1.5, 'OVER',"
        " 10, 1.8, 1.0, 0.6, 0.6, 0.5, 0.0, 'LOSS', '2026-09-25T00:00:00Z',"
        " 1.9, 'VALUE')",
        (day,),
    )
    con.commit()
    con.close()
    env = {"PYTHONPATH": "src:.", "PATH": "/usr/bin:/bin",
           "SOFA_RUNS_DIR": str(runs), "SOFA_DB_PATH": str(db)}

    dry = subprocess.run(
        [sys.executable, "scripts/sofa/regrade_settled.py", "--players", "--dry-run"],
        cwd=REPO, capture_output=True, text=True, env=env)
    assert dry.returncode == 0, dry.stderr
    assert "LOSS (0) -> WIN (3)" in dry.stdout
    con = sqlite3.connect(db)
    assert con.execute("select outcome from sofa_settled_row").fetchone() == ("LOSS",)
    con.close()

    done = subprocess.run(
        [sys.executable, "scripts/sofa/regrade_settled.py", "--players", "--apply"],
        cwd=REPO, capture_output=True, text=True, env=env)
    assert done.returncode == 0, done.stderr
    con = sqlite3.connect(db)
    assert con.execute(
        "select outcome, actual_value from sofa_settled_row").fetchone() == ("WIN", 3.0)
    con.close()
    assert list(runs.glob("regrade_*.json")), "the undo copy is written first"


def test_settle_reads_the_side_from_03_samples(
    tmp_path: Path, monkeypatch: Any
) -> None:
    day = "2026-09-24"
    run_dir = tmp_path / "runs" / day
    run_dir.mkdir(parents=True)
    row = {"sofascore_event_id": 7, "sport": "football",
           "market": "player_shots_for", "subject": "Weverson", "line": 1.5,
           "direction": "OVER", "sample_size": 10, "sample_mean": 1.8,
           "sample_sd": 1.0, "p_central": 0.6, "p_bar": 0.6, "market_p": 0.5,
           "offered_odds": 1.9, "verdict": "VALUE"}
    (run_dir / "05_sheet.json").write_text(json.dumps([row]))
    (run_dir / "02_fixtures.json").write_text(json.dumps([
        {"sofascore_event_id": 7, "sport": "football",
         "kickoff_utc": "2026-09-24T18:00:00Z", "home_entity_id": 10,
         "away_entity_id": 20, "home_name": "Home", "away_name": "Away"}]))
    (run_dir / "03_samples.json").write_text(json.dumps([
        {"sofascore_event_id": 7,
         "players": {"player_shots_for|Weverson": {"side": "side_b"}}}]))
    start = int(datetime(2026, 9, 24, 18, tzinfo=UTC).timestamp())
    event = {"id": 7, "startTimestamp": start,
             "homeTeam": {"id": 10}, "awayTeam": {"id": 20},
             "status": {"type": "finished", "code": 100},
             "tournament": {"uniqueTournament": {"id": 17}}}
    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("SOFA_DB_PATH", str(tmp_path / "sofa.db"))
    monkeypatch.setenv("SOFA_MAX_CONCURRENCY", "1")
    monkeypatch.setattr(run_settle, "SofascoreClient", lambda config: object())
    monkeypatch.setattr(run_settle, "SofaCache", lambda config: object())
    monkeypatch.setattr(run_settle, "_event_payload",
                        lambda c, k, e, r=False: (event, None, None))
    monkeypatch.setattr(run_settle, "fetch_lineups", lambda c, k, e: _lineups())
    monkeypatch.setattr(sys, "argv", ["run_settle", "--date", day])
    run_settle.main()
    settled = json.loads((run_dir / "07_settled.json").read_text())
    assert [(r["subject"], r["actual_value"], r["outcome"]) for r in settled] == [
        ("Weverson", 3.0, "WIN")]
