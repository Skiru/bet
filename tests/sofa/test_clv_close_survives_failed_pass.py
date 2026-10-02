"""A failed capture pass must not erase an earlier good close (review 2026-10-02).

audit_clv kept the latest record per leg and a `missing` record won, so a
Superbet timeout on the last pass before kickoff erased the T-20 close (1 of
96 legs on the real 2026-10-01 file). capture_closing now tags a failed fetch
with `error`, audit_clv prefers the latest priced record in the window, the
appender repairs a torn tail, and the loop guard reads the pid's command line.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from bet.sofa.contracts import Fixture, FixtureOffer, PricedRung
from scripts.sofa import audit_clv
from scripts.sofa import capture_closing as cc

KO = datetime(2026, 10, 1, 18, 0, tzinfo=UTC)
EID = 7


def _day(tmp_path: Path) -> Path:
    day = tmp_path / "2026-10-01"
    day.mkdir()
    fixture = {"sofascore_event_id": EID, "superbet_event_ids": ["1"],
               "sport": "football", "kickoff_utc": KO.isoformat(),
               "home_name": "A", "away_name": "B", "home_entity_id": 1,
               "away_entity_id": 2, "competition_name": "L", "competition_id": 3,
               "season_id": 4, "category_name": "C", "identity": "CONFIRMED",
               "round_number": None, "round_name": None, "cup_round_type": None,
               "previous_leg_event_id": None, "venue_name": None, "referee": None,
               "ground_type": None, "default_period_count": 2}
    (day / "02_fixtures.json").write_text(json.dumps([fixture]))
    leg = {"sofascore_event_id": EID, "kickoff_utc": KO.isoformat(),
           "market": "corners_total", "subject": "", "line": 9.5,
           "direction": "OVER", "offered_odds": 1.9}
    (day / "08_confidence.json").write_text(
        json.dumps({"singles": [leg], "pdf_max_singles": None}))
    return day


def _offer() -> FixtureOffer:
    return FixtureOffer(
        sofascore_event_id=EID, status="PRICED", unmapped_markets=[], rungs=[
            PricedRung(market="corners_total", subject="", line=9.5,
                       over_odds=1.80, under_odds=1.95,
                       fetched_at_utc=KO - timedelta(minutes=20))])


class Raising:
    def fetch_offers(self, fixtures: list[Fixture]) -> list[FixtureOffer]:
        raise TimeoutError("superbet read timeout")


class Good:
    def fetch_offers(self, fixtures: list[Fixture]) -> list[FixtureOffer]:
        return [_offer()]


class SwallowsListingError:
    """OfferFetcher's shape: a listing's error is kept, the fixture dropped."""

    def __init__(self) -> None:
        self.errors: list[tuple[str, str]] = []

    def fetch_offers(self, fixtures: list[Fixture]) -> list[FixtureOffer]:
        self.errors.append(("1", "HTTPError: 503"))
        return []


class Pulled:
    def __init__(self) -> None:
        self.errors: list[tuple[str, str]] = []

    def fetch_offers(self, fixtures: list[Fixture]) -> list[FixtureOffer]:
        return []


def _records(day: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in (day / "closing.jsonl").read_text().splitlines()]


def test_a_failed_last_pass_keeps_the_earlier_close(tmp_path: Path) -> None:
    day = _day(tmp_path)
    assert cc.run_once(day, Good(), KO - timedelta(minutes=20)) == 1
    assert cc.run_once(day, Raising(), KO - timedelta(minutes=10)) == 1
    last = _records(day)[-1]
    assert last["missing"] is True and "TimeoutError" in last["error"]
    rows = audit_clv.closing_rows(tmp_path, "2026-10-01")
    assert len(rows) == 1 and rows[0].odds_close == 1.80


def test_a_listing_error_inside_the_fetcher_is_an_error_not_a_pull(
    tmp_path: Path,
) -> None:
    day = _day(tmp_path)
    cc.run_once(day, SwallowsListingError(), KO - timedelta(minutes=10))
    assert "HTTPError: 503" in _records(day)[-1]["error"]


def test_a_pulled_market_is_missing_without_error(tmp_path: Path) -> None:
    day = _day(tmp_path)
    cc.run_once(day, Pulled(), KO - timedelta(minutes=10))
    rec = _records(day)[-1]
    assert rec["missing"] is True and "error" not in rec
    assert audit_clv.closing_rows(tmp_path, "2026-10-01") == []


def test_a_later_good_close_still_beats_an_earlier_one(tmp_path: Path) -> None:
    day = _day(tmp_path)
    cc.run_once(day, Raising(), KO - timedelta(minutes=25))
    cc.run_once(day, Good(), KO - timedelta(minutes=10))
    rows = audit_clv.closing_rows(tmp_path, "2026-10-01")
    assert len(rows) == 1


def test_a_torn_tail_is_repaired_before_the_next_append(tmp_path: Path) -> None:
    day = _day(tmp_path)
    (day / "closing.jsonl").write_text('{"variant": "official", "leg_k')
    cc.run_once(day, Good(), KO - timedelta(minutes=20))
    lines = (day / "closing.jsonl").read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["odds_close"] == 1.80


def test_a_reused_pid_after_a_reboot_does_not_block(tmp_path: Path) -> None:
    day = tmp_path / "2026-10-01"
    day.mkdir()
    (day / cc.PID_FILE).write_text(str(os.getppid()), encoding="utf-8")
    assert cc.loop_holder(day, lambda pid: "/usr/sbin/someone_else") is None
    assert cc.loop_holder(
        day, lambda pid: "python scripts/sofa/capture_closing.py --date 2026-10-02"
    ) is None, "a loop for another date is not this day's"
    assert cc.loop_holder(
        day, lambda pid: "python scripts/sofa/capture_closing.py --date 2026-10-01"
    ) == os.getppid()
