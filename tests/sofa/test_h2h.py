"""bet.sofa.h2h: every read match's head-to-head asked of Sofascore, and the
dossier that shows it (operator 2026-10-21, Real Madrid - RB Leipzig: the
cached listings stopped short of the four meetings and nothing said so)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from bet.sofa import dossier, h2h
from bet.sofa.errors import CircuitOpenError, ProviderError
from tests.sofa.test_dossier import DAY, KICK, NOW, ev, football_day


def stats(home_corners: int, away_corners: int) -> dict[str, Any]:
    return {"statistics": [{"period": "ALL", "groups": [{"statisticsItems": [
        {"key": "cornerKicks", "homeValue": home_corners,
         "awayValue": away_corners}]}]}]}


class FakeClient:
    def __init__(self, meetings: list[dict[str, Any]], fail: Exception | None = None):
        self.meetings = meetings
        self.fail = fail
        self.asked: list[str] = []

    def event(self, id: int) -> Any | None:
        self.asked.append(f"event {id}")
        return {"event": {"id": id, "customId": f"c{id}"}}

    def event_h2h_events(self, custom_id: str) -> Any | None:
        self.asked.append(f"h2h {custom_id}")
        if self.fail:
            raise self.fail
        return {"events": self.meetings}

    def event_statistics(self, id: int) -> Any | None:
        self.asked.append(f"stats {id}")
        return stats(7, 4)

    def event_incidents(self, id: int) -> Any | None:
        self.asked.append(f"incidents {id}")
        return {"incidents": []}


class FakeCache:
    def __init__(self) -> None:
        self.saved: dict[int, tuple[Any, Any, str]] = {}

    def get_event_detail(self, sofascore_event_id: int) -> dict[str, Any] | None:
        return None

    def get_event_stats(self, sofascore_event_id: int, kickoff_ts: int | None = None
                        ) -> tuple[Any, Any, str] | None:
        return self.saved.get(sofascore_event_id)

    def save_event_stats(self, sofascore_event_id: int, statistics: Any,
                         incidents: Any, status_type: str) -> None:
        self.saved[sofascore_event_id] = (statistics, incidents, status_type)


def test_fetch_keeps_finished_meetings_saves_their_stats_and_asks_once(
        tmp_path: Path) -> None:
    meetings = [ev(900, KICK - 900 * DAY, 2, 1, 2, 2),
                ev(901, KICK - 500 * DAY, 1, 2, 1, 0),
                ev(500, KICK, 1, 2, 0, 0, status="notstarted")]  # the fixture
    client, cache = FakeClient(meetings), FakeCache()
    counts = h2h.fetch(tmp_path, [500, 500], client, cache)
    assert counts == {"OK": 1, "cached": 0}
    entry = h2h.load(tmp_path)["500"]
    assert entry["status"] == "OK" and entry["custom_id"] == "c500"
    assert [m["id"] for m in entry["meetings"]] == [901, 900]
    assert set(cache.saved) == {900, 901}
    asked = len(client.asked)
    assert h2h.fetch(tmp_path, [500], client, cache) == {"cached": 1}
    assert len(client.asked) == asked  # an OK answer is not asked again


def test_a_provider_error_is_the_entry_status_and_a_breaker_stops_the_rest(
        tmp_path: Path) -> None:
    h2h.fetch(tmp_path, [1], FakeClient([], ProviderError("HTTP 500")), FakeCache())
    assert h2h.load(tmp_path)["1"]["status"].startswith("FAILED ProviderError")
    counts = h2h.fetch(tmp_path, [1, 2], FakeClient([], CircuitOpenError("open")),
                       FakeCache())
    assert counts["FAILED"] == 2
    assert {e["status"] for e in h2h.load(tmp_path).values()} == {
        "FAILED breaker open"}


def test_dossier_shows_a_fetched_meeting_the_cache_missed_with_the_legs_metrics(
        tmp_path: Path) -> None:
    db, run = football_day(tmp_path)
    old = ev(900, KICK - 900 * DAY, 2, 1, 2, 2)  # Beta - Alfa, years ago
    con = sqlite3.connect(db)
    con.execute("INSERT INTO sofa_event_stats (sofascore_event_id, fetched_at, "
                "statistics_json, incidents_json, status_type) VALUES (?,?,?,?,?)",
                (900, "2026-10-20T08:00:00+00:00", json.dumps(stats(7, 4)), None,
                 "finished"))
    con.commit()
    con.close()
    (run / h2h.FILE).write_text(json.dumps({"events": {"500": {
        "status": "OK", "fetched_at_utc": "2026-10-20T08:30:00Z",
        "meetings": [old]}}}))
    legs = [{"sofascore_event_id": 500, "sport": "football"}]
    doc = json.loads(Path(dossier.write_for_legs(run, legs, db_path=db, now=NOW)[500])
                     .read_text())
    rows = doc["head_to_head"]
    assert rows[-1]["date"].startswith("2024") and rows[-1]["venue"] == "wyjazd"
    assert rows[-1]["metrics"] == {"corners_total": 11}
    assert len(rows) == 3  # both cached meetings kept beside it
    source = doc["head_to_head_source"]
    assert source["sofascore_h2h"] == "OK" and source["meetings_returned"] == 1
    assert source["cache_listings_from"]["home"] is not None
    assert not any(x.startswith("h2h:") for x in doc["web_checklist"])


def test_dossier_without_an_h2h_answer_says_so_and_the_checklist_asks(
        tmp_path: Path) -> None:
    db, run = football_day(tmp_path)
    legs = [{"sofascore_event_id": 500, "sport": "football"}]
    doc = json.loads(Path(dossier.write_for_legs(run, legs, db_path=db, now=NOW)[500])
                     .read_text())
    assert doc["head_to_head_source"]["sofascore_h2h"] == "NOT_ASKED"
    assert any(x.startswith("h2h: Sofascore nie odpowiedział (NOT_ASKED)")
               for x in doc["web_checklist"])
