"""Coverage audit 2026-10-23 P12 (B12): a CS2 series graded from the result
alone carries the engine's model_p under
epochs.CS2_SERIES_ONLY_MODEL_P_FROM_UTC, read by the settle clock; the series
settled before it get theirs once through attach_series_only_models."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import epochs
from scripts.sofa import settle_cs2 as sc
from tests.sofa.test_cs2_stages import KICKOFF, FakeSofascore, write_snapshot

SWITCH = datetime(2026, 10, 24, tzinfo=UTC)


def _rounds_less() -> list[dict[str, Any]]:
    return [{"id": g["id"], "startTimestamp": g["startTimestamp"],
             "status": {"type": "finished"}, "homeScore": {}, "awayScore": {}}
            for g in FakeSofascore().games]


def _settle(tmp_path: Path, at: datetime, monkeypatch: pytest.MonkeyPatch
            ) -> tuple[dict[str, Any], list[int]]:
    calls: list[int] = []

    def fake_attach(graded: list[dict[str, Any]], *a: Any) -> None:
        calls.append(len(graded))
        for g in graded:
            g["model_p"] = 0.6

    monkeypatch.setattr(sc, "attach_model", fake_attach)
    monkeypatch.setattr(sc, "store_series", lambda *a, **k: None)
    if not (tmp_path / "cs2" / "2026-09-26").exists():
        write_snapshot(tmp_path)
    snaps = [json.loads(x) for x in (tmp_path / "cs2" / "2026-09-26" /
                                     sc.SNAPSHOTS_FILE).read_text().splitlines()]
    (ev,) = sc.latest_pre_kickoff(snaps).values()
    rec = sc.settle_one(ev, sc.Cs2Sofascore(FakeSofascore(games=_rounds_less()),
                                            None), at, str(tmp_path / "x.db"),
                        snaps)
    return rec, calls


def test_series_only_rows_get_model_p_only_from_the_switch(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "CS2_SERIES_ONLY_MODEL_P_FROM_UTC", SWITCH)
    before, calls = _settle(tmp_path, SWITCH - timedelta(minutes=1), monkeypatch)
    assert before["series_only"] and calls == []
    assert all("model_p" not in g for g in before["graded"])
    after, calls = _settle(tmp_path, SWITCH + timedelta(hours=1), monkeypatch)
    assert after["series_only"] and calls == [len(after["graded"])] and calls[0] > 0
    assert all(g["model_p"] == 0.6 for g in after["graded"])
    monkeypatch.setattr(epochs, "CS2_SERIES_ONLY_MODEL_P_FROM_UTC", None)
    off, calls = _settle(tmp_path, SWITCH + timedelta(hours=1), monkeypatch)
    assert calls == [] and all("model_p" not in g for g in off["graded"])


def _store(tmp_path: Path) -> str:
    db = str(tmp_path / "s.db")
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE cs2_series (sofascore_event_id INTEGER, "
                     "start_ts INTEGER, home_id INTEGER, away_id INTEGER, "
                     "best_of INTEGER)")
        conn.execute("INSERT INTO cs2_series VALUES (900, ?, 5, 6, 3)",
                     (int(KICKOFF.timestamp()),))
    return db


def _settled_file(tmp_path: Path) -> Path:
    day = tmp_path / "cs2" / "2026-09-26"
    day.mkdir(parents=True, exist_ok=True)
    g = {"superbet_event_id": "1", "family": "match_winner", "map_nr": 0,
         "subject": "", "line": None, "side": "T1", "odds": 1.8, "outcome": "WIN"}
    events = {
        "1": {"state": "SETTLED", "series_only": True, "sofascore_event_id": 900,
              "home_is_team1": True, "team1": "a", "team2": "b", "match_name": "a·b",
              "kickoff_utc": "2026-09-26T15:00:00Z", "tournament": None,
              "graded": [dict(g), dict(g, side="T2", outcome="LOSS")]},
        "2": {"state": "SETTLED", "sofascore_event_id": 901, "home_is_team1": True,
              "kickoff_utc": "2026-09-26T15:00:00Z", "graded": [dict(g)]},
    }
    path = day / sc.SETTLED_FILE
    path.write_text(json.dumps({"date": "2026-09-26", "events": events}))
    return path


def test_the_backfill_attaches_once_and_only_under_the_switch(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[dict[str, Any], dict[str, Any], bool]] = []

    def fake_attach(graded: list[dict[str, Any]], ev: Any, event: dict[str, Any],
                    detail: dict[str, Any], home_is_t1: bool, *a: Any) -> None:
        seen.append((event, detail, home_is_t1))
        for g in graded:
            g["model_p"] = 0.55

    monkeypatch.setattr(sc, "attach_model", fake_attach)
    monkeypatch.setattr(epochs, "CS2_SERIES_ONLY_MODEL_P_FROM_UTC", SWITCH)
    db, path = _store(tmp_path), _settled_file(tmp_path)
    original = path.read_text()
    off = sc.attach_series_only_models(str(tmp_path), "2026-09-26", db,
                                       SWITCH - timedelta(seconds=1))
    assert off == {"state": "SWITCH_OFF"} and path.read_text() == original
    dry = sc.attach_series_only_models(str(tmp_path), "2026-09-26", db,
                                       SWITCH, dry_run=True)
    assert dry["state"] == "DRY_RUN" and dry["rows"] == 2
    assert path.read_text() == original
    done = sc.attach_series_only_models(str(tmp_path), "2026-09-26", db, SWITCH)
    assert done["series"] == 1 and done["with_model_p"] == 2
    event, detail, home_is_t1 = seen[-1]
    assert event["homeTeam"]["id"] == 5 and detail["bestOf"] == 3 and home_is_t1
    events = json.loads(path.read_text())["events"]
    assert [g["model_p"] for g in events["1"]["graded"]] == [0.55, 0.55]
    assert "model_p" not in events["2"]["graded"][0]  # not series-only: untouched
    again = sc.attach_series_only_models(str(tmp_path), "2026-09-26", db, SWITCH)
    assert again["series"] == 0  # idempotent
