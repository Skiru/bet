"""bet.sofa.prematch_lineups: Sofascore's predicted / confirmed line-up and
absences for every read match, in the day's artifact only - never the cache
SAMPLES and SETTLE read - and the dossier's `lineups` block that shows it."""

from __future__ import annotations

import ast
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import dossier
from bet.sofa import prematch_lineups as pl
from bet.sofa.db import migrate
from bet.sofa.errors import CircuitOpenError, ProviderError
from tests.sofa.test_dossier import NOW, football_day

KICK_AT = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


def entry(pid: int, name: str, sub: bool = False, pos: str = "M") -> dict[str, Any]:
    return {"player": {"id": pid, "name": name, "position": pos},
            "position": pos, "substitute": sub, "shirtNumber": pid}


def answer(confirmed: bool = False) -> dict[str, Any]:
    return {
        "confirmed": confirmed,
        "home": {
            "formation": "4-3-3",
            "players": [entry(11, "Jan Kowalski"), entry(14, "Piotr Zielinski"),
                        entry(13, "Adam Lewy", sub=True)],
            "missingPlayers": [{"player": {"id": 12, "name": "Marek Nowak"},
                                "type": "missing", "reason": 1,
                                "description": "Knee injury"}],
        },
        "away": {"players": [entry(21, "Ola Beta"), entry(22, "Ewa Beta", sub=True)]},
    }


class FakeClient:
    def __init__(self, payload: Any = None, fail: Exception | None = None):
        self.payload, self.fail = payload, fail
        self.asked: list[int] = []

    def event_lineups(self, id: int) -> Any | None:
        self.asked.append(id)
        if self.fail:
            raise self.fail
        return self.payload


def test_parse_predicted_confirmed_and_unpublished() -> None:
    got = pl.parse(answer())
    assert got["status"] == "OK" and got["confirmed"] is False
    home = got["home"]
    assert home["formation"] == "4-3-3"
    assert [p["name"] for p in home["starters"]] == ["Jan Kowalski", "Piotr Zielinski"]
    assert home["substitutes"][0] == {"id": 13, "name": "Adam Lewy", "position": "M",
                                      "shirt": 13}
    assert home["missing"] == [{"id": 12, "name": "Marek Nowak", "type": "missing",
                                "reason": 1, "description": "Knee injury"}]
    assert home["missing_listed"] and not got["away"]["missing_listed"]
    assert pl.parse(answer(confirmed=True))["confirmed"] is True
    assert pl.parse(None) == {"status": "NOT_PUBLISHED"}  # the client's 404
    assert pl.parse({"confirmed": False, "home": {}, "away": {}})["status"] == (
        "NOT_PUBLISHED")


def test_reask_rules_started_and_sport_scope(tmp_path: Path) -> None:
    at = KICK_AT - timedelta(hours=3)
    client = FakeClient(answer())
    counts = pl.fetch(tmp_path, [(1, "football", KICK_AT), (1, "football", KICK_AT),
                                 (2, "tennis", KICK_AT), (3, "football", at),
                                 (4, "basketball", KICK_AT)], client, at)
    assert counts == {"OK": 2, "sport_not_covered": 1, "started": 1}
    assert client.asked == [1, 4]
    assert pl.load(tmp_path)["1"]["asked_at_utc"] == "2026-10-20T09:00:00Z"
    # unconfirmed: not again within 30 min, again after
    pl.fetch(tmp_path, [(1, "football", KICK_AT)], client, at + timedelta(minutes=29))
    assert client.asked == [1, 4]
    client.payload = answer(confirmed=True)
    pl.fetch(tmp_path, [(1, "football", KICK_AT)], client, at + timedelta(minutes=31))
    assert client.asked == [1, 4, 1] and pl.load(tmp_path)["1"]["confirmed"] is True
    # confirmed is final
    counts = pl.fetch(tmp_path, [(1, "football", KICK_AT)], client,
                      at + timedelta(hours=2))
    assert counts == {"final": 1} and client.asked == [1, 4, 1]


def test_failure_and_breaker_keep_the_earlier_answer(tmp_path: Path) -> None:
    at = KICK_AT - timedelta(hours=3)
    pl.fetch(tmp_path, [(1, "football", KICK_AT)], FakeClient(answer()), at)
    later = at + timedelta(hours=1)
    pl.fetch(tmp_path, [(1, "football", KICK_AT)],
             FakeClient(fail=ProviderError("HTTP 500")), later)
    kept = pl.load(tmp_path)["1"]
    assert kept["status"] == "OK" and kept["home"]["formation"] == "4-3-3"
    assert kept["last_attempt"]["status"].startswith("FAILED ProviderError")
    counts = pl.fetch(tmp_path, [(1, "football", KICK_AT), (2, "football", KICK_AT)],
                      FakeClient(fail=CircuitOpenError("open")), later)
    assert counts == {"NOT_ASKED": 2}
    entries = pl.load(tmp_path)
    assert entries["1"]["status"] == "OK"
    assert entries["1"]["last_attempt"]["status"] == "NOT_ASKED breaker open"
    assert entries["2"]["status"] == "NOT_ASKED breaker open"
    # a failure is asked again at once (no 30-minute wait)
    client = FakeClient(answer())
    pl.fetch(tmp_path, [(2, "football", KICK_AT)], client, later)
    assert client.asked == [2]


def test_a_prematch_lineup_never_reaches_the_cache(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The trap: sofa_event_stats.lineups_json is the post-match fact player
    samples and SETTLE read, cached forever. A pre-match answer must stay in
    the day's artifact."""
    db = tmp_path / "sofa.db"
    migrate(str(db))
    monkeypatch.setenv("SOFA_DB_PATH", str(db))
    monkeypatch.setenv("SOFA_NOW", "2026-10-20T09:00:00Z")
    run = tmp_path / "run"
    legs = [{"sofascore_event_id": 500, "sport": "football",
             "kickoff_utc": "2026-10-20T12:00:00Z"}]
    line = pl.fetch_for_legs(run, legs, FakeClient(answer()))
    assert line == "składy: OK 1"
    assert pl.load(run)["500"]["status"] == "OK"
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM sofa_event_stats").fetchone() == (0,)
    con.close()
    # and the module never names a cache writer or the cached fetch
    tree = ast.parse(Path(pl.__file__).read_text(encoding="utf-8"))
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {
        n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    forbidden = {"SofaCache", "save_event_lineups", "save_event_stats",
                 "save_event_extra", "fetch_lineups"}
    assert not names & forbidden


def _cache_lineups(db: Path, event_id: int, side: str,
                   players: list[dict[str, Any]]) -> None:
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO sofa_event_stats (sofascore_event_id, fetched_at, status_type, "
        "lineups_json) VALUES (?, ?, ?, ?)",
        (event_id, "2026-10-19T00:00:00Z", "finished",
         json.dumps({"confirmed": True, side: {"players": players}})))
    con.commit()
    con.close()


def test_dossier_shows_lineup_player_legs_and_absent_regulars(tmp_path: Path) -> None:
    db, run = football_day(tmp_path)
    # Alfa (id 1): home in 101 and 105, away in 102 and 106
    regular_xi = [entry(11, "Jan Kowalski"), entry(12, "Marek Nowak"),
                  entry(13, "Adam Lewy", sub=True)]
    _cache_lineups(db, 101, "home", regular_xi)
    _cache_lineups(db, 105, "home", regular_xi)
    _cache_lineups(db, 102, "away", regular_xi)
    (run / pl.FILE).write_text(json.dumps({"events": {"500": {
        "asked_at_utc": "2026-10-20T09:00:00Z", "sport": "football",
        **pl.parse(answer())}}}))
    coupon = json.loads((run / "11_coupon.json").read_text())
    coupon["singles"] += [
        {**coupon["singles"][0], "market": "player_shots_for",
         "subject": "Kowalski, Jan", "position": 2},
        {**coupon["singles"][0], "market": "player_shots_for",
         "subject": "Nowak, Marek", "position": 3},
        {**coupon["singles"][0], "market": "player_shots_for",
         "subject": "Nieznany Gracz", "position": 4},
    ]
    (run / "11_coupon.json").write_text(json.dumps(coupon))
    written = dossier.write_for_legs(
        run, [{"sofascore_event_id": 500, "sport": "football"}], db_path=db, now=NOW)
    doc = json.loads(Path(written[500]).read_text())
    block = doc["lineups"]
    assert block["status"] == "OK" and block["confirmed"] is False
    assert block["kind"].startswith("przewidywany")
    home = block["home"]
    assert home["formation"] == "4-3-3"
    assert home["starters"][0] == "Jan Kowalski (M)"
    assert home["missing_players"][0]["description"] == "Knee injury"
    assert home["regulars"]["lineups_cached"] == 3
    assert [r["name"] for r in home["regulars"]["players"]] == [
        "Jan Kowalski", "Marek Nowak"]
    assert home["regulars_not_in_xi"] == ["Marek Nowak (3/3): missing"]
    assert "missing" in block["away"]["regulars"]  # Beta: no cached line-up
    by_subject = {r["subject"]: r for r in block["player_legs"]}
    assert by_subject["Kowalski, Jan"]["status"] == "XI"
    assert by_subject["Kowalski, Jan"]["side"] == "home"
    assert by_subject["Nowak, Marek"]["status"] == "missing"
    assert by_subject["Nieznany Gracz"]["status"].startswith("nie ma na liście")
    checklist = " | ".join(doc["web_checklist"])
    assert "dossier ma skład Sofascore (PRZEWIDYWANY" in checklist
    assert "przewidywane / potwierdzone składy (~1 h przed)" not in checklist


def test_dossier_without_a_lineup_answer_says_so(tmp_path: Path) -> None:
    db, run = football_day(tmp_path)
    written = dossier.write_for_legs(
        run, [{"sofascore_event_id": 500, "sport": "football"}], db_path=db, now=NOW)
    doc = json.loads(Path(written[500]).read_text())
    assert doc["lineups"]["status"] == "NOT_ASKED"
    assert doc["lineups"]["missing"].startswith("nie pytano")
    assert "przewidywane / potwierdzone składy (~1 h przed)" in doc["web_checklist"]
