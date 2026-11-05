"""SHADOW and the CS2 snapshot record the Superbet markets they do not read
(bet.sofa.unmapped_prices; pokrycie_sportow_2026-11-05, gap 5).

A record, read by nothing: from the payload already fetched (no request),
one gz file per snapshot and sport under the event's day, the football
record's fields plus `sport` and `marketId`. OFFER's own readers keep seeing
OFFER's files only.
"""

from __future__ import annotations

import gzip
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import cs2, shadow, unmapped_prices
from scripts.sofa import run_cs2, run_shadow

ROOT = Path(__file__).parents[2]
DATE = "2026-09-28"


def _odd(market_id: int, market: str, name: str, price: float,
         spec: dict[str, str] | None = None, code: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "marketId": market_id, "marketName": market, "name": name, "info": "",
        "price": price, "specifiers": spec or {}, "status": "active",
        "offerStateId": 1, "outcomeId": market_id * 10 + int(price * 100),
        "specialBetValue": (spec or {}).get("total"),
    }
    if code is not None:
        out["code"] = code
    return out


HOCKEY_READ = [
    _odd(623, "Liczba goli", "poniżej 5.5", 1.9, {"total": "5.5"}, "-"),
    _odd(623, "Liczba goli", "powyżej 5.5", 1.9, {"total": "5.5"}, "+"),
]
HOCKEY_UNREAD = [
    _odd(990001, "Pierwsza bramka - minuta", "do 10:00", 2.4),
    _odd(990001, "Pierwsza bramka - minuta", "po 10:00", 1.5),
]


class _Board:
    def __init__(self) -> None:
        self.asked: list[str] = []

    def events_by_date(self, start: datetime, end: datetime,
                       offer_state: str) -> list[dict[str, Any]]:
        return [
            {"sportId": 3, "eventId": 1, "matchName": "HC Sparta·HC Kometa",
             "utcDate": "2026-09-28T16:00:00Z", "tournamentId": 7},
            {"sportId": 55, "eventId": 5, "matchName": "Vitality·MOUZ",
             "utcDate": "2026-09-28T18:00:00Z", "tournamentId": 8},
        ]

    def event_odds(self, event_id: str) -> dict[str, Any]:
        self.asked.append(str(event_id))
        if str(event_id) == "1":
            return {"odds": HOCKEY_READ + HOCKEY_UNREAD}
        return {"odds": [
            _odd(0, "Liczba map", "poniżej 2.5", 1.8, {"total": "2.5"}),
            _odd(0, "Liczba map", "powyżej 2.5", 1.95, {"total": "2.5"}),
            _odd(0, "Pierwsza krew na 1. mapie", "Vitality", 1.7),
        ]}

    def _get_json(self, path: str) -> dict[str, Any]:
        return {"data": {"tournaments": []}}


def _rows(path: Path) -> list[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def test_shadow_records_the_markets_it_does_not_read(tmp_path: Path) -> None:
    board = _Board()
    at = datetime(2026, 9, 28, 14, tzinfo=UTC)
    result = run_shadow.snapshot(DATE, board, str(tmp_path), at=at)  # type: ignore[arg-type]
    assert board.asked == ["1"], "no request beyond the snapshot's own"
    (path,) = unmapped_prices.files(tmp_path / DATE, "hockey")
    assert path.name.startswith("hockey_") and result["unmapped_prices_files"] == [
        str(path)]
    rows = _rows(path)
    assert [r["name"] for r in rows] == ["do 10:00", "po 10:00"]
    first = rows[0]
    assert first["sport"] == "hockey" and first["marketId"] == 990001
    assert first["sofascore_event_id"] is None and first["superbet_event_id"] == "1"
    assert first["fetched_at_utc"] == "2026-09-28T14:00:00Z"
    assert first["price"] == 2.4 and first["outcomeId"] == HOCKEY_UNREAD[0]["outcomeId"]
    # the read market is graded as before, never recorded here
    snap = tmp_path / "shadow" / "hockey" / DATE / "snapshots.jsonl"
    (rec,) = [json.loads(x) for x in snap.read_text().splitlines()]
    assert len(rec["lines"]) == 2
    # OFFER's readers do not see the sport's file
    assert list(unmapped_prices.read(tmp_path / DATE)) == []
    assert list(unmapped_prices.read(tmp_path / DATE, "hockey")) == rows


def test_cs2_records_the_markets_it_does_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    at = datetime(2026, 9, 28, 12, tzinfo=UTC)
    monkeypatch.setattr(run_cs2, "now", lambda: at)
    board = _Board()
    result = run_cs2.snapshot(DATE, board, str(tmp_path))  # type: ignore[arg-type]
    assert board.asked == ["5"]
    (path,) = unmapped_prices.files(tmp_path / DATE, "cs2")
    assert result["unmapped_prices_files"] == [str(path)]
    (row,) = _rows(path)
    assert row["sport"] == "cs2" and row["marketName"] == "Pierwsza krew na 1. mapie"
    assert row["superbet_event_id"] == "5" and row["sofascore_event_id"] is None


def test_nothing_unread_writes_no_file(tmp_path: Path) -> None:
    assert unmapped_prices.write(tmp_path, [], datetime.now(UTC), "hockey") is None
    assert not (tmp_path / unmapped_prices.DIRNAME).exists()


def test_reads_market_follows_the_parsers_switches() -> None:
    t1, t2 = "Lakers", "Celtics"
    assert shadow.reads_market(HOCKEY_READ[0], "hockey", t1, t2)
    assert not shadow.reads_market(HOCKEY_UNREAD[0], "hockey", t1, t2)
    v2 = next(iter(shadow.PLAYER_V2_MARKETS["basketball"]))
    odd = _odd(v2, "x", "y", 1.9)
    assert not shadow.reads_market(odd, "basketball", t1, t2, player_v2=False)
    assert shadow.reads_market(odd, "basketball", t1, t2, player_v2=True)
    dc = _odd(1, "Podwójna szansa", "1X", 1.3)
    assert not shadow.reads_market(dc, "basketball", t1, t2)
    assert shadow.reads_market(dc, "basketball", t1, t2, derived=True)
    # every odd parse_line reads is of a read market
    for item in HOCKEY_READ:
        assert shadow.parse_line(item, "hockey", "1", t1, t2) is not None
    assert cs2.reads_market(_odd(0, "Handicap map", "Vitality (-1.5)", 2.0), "A", "B")
    kills = "3.mapa - liczba zabójstw zawodnika (z dogrywką)"
    assert cs2.reads_market(_odd(0, kills, "REZ - powyżej 25.5", 1.8), "A", "B")
    assert not cs2.reads_market(_odd(0, "Pierwsza krew", "A", 1.8), "A", "B")


def test_the_offer_record_is_unchanged() -> None:
    rec = unmapped_prices.record(7, "9", HOCKEY_UNREAD[0],
                                 datetime(2026, 9, 28, tzinfo=UTC))
    assert "sport" not in rec and "marketId" not in rec
    assert rec["sofascore_event_id"] == 7


def test_no_stage_gate_or_grader_reads_the_record() -> None:
    """A record: only its writers (OFFER, SHADOW, CS2) and the read-only
    measure_* evidence scripts import the module; the writers never read it."""
    writers = {"src/bet/sofa/offer.py", "scripts/sofa/run_offer.py",
               "scripts/sofa/run_shadow.py", "scripts/sofa/run_cs2.py"}
    pattern = re.compile(
        r"^\s*(from bet\.sofa import (\([^)]*|[^\n]*)\bunmapped_prices\b"
        r"|from bet\.sofa\.unmapped_prices import|import bet\.sofa\.unmapped_prices)",
        re.M)
    hits = set()
    for base in ("src/bet/sofa", "scripts/sofa"):
        for path in (ROOT / base).rglob("*.py"):
            rel = str(path.relative_to(ROOT))
            if rel == "src/bet/sofa/unmapped_prices.py":
                continue
            if pattern.search(path.read_text(encoding="utf-8")):
                hits.add(rel)
    readers = {h for h in hits - writers
               if not Path(h).name.startswith("measure_")}
    assert not readers, readers
    for rel in writers:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "unmapped_prices.read" not in text
        assert "unmapped_prices.files" not in text
