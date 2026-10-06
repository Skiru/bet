"""The CS2 measurement chain's defects found by the 2026-10-01 audit.

F1  a player line without lineups held the whole series STATS_PENDING past
    what the daily loop ever reaches (grace 72 h, loop ~53 h);
F2  "MIBR (K)" never matched "MIBR fe"; F8 "KUUSAMO" never matched
    "KUUSAMO.gg";
F4  the series-only path dropped non-series sides uncounted, and final;
F5  a series still waiting on D-2 was never asked again;
F6  settle never wrote sofascore_start_utc, so IN_PLAY_PRICE could not fire;
F8b settled.json was read-modified-written without a lock.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa import cs2
from bet.sofa import sport_day as sd
from scripts.sofa import cs2_daily, settle_cs2
from tests.sofa.test_cs2_stages import (
    DATE,
    KICKOFF,
    FakeSofascore,
    run_settle,
    settled,
    write_snapshot,
)

NO_STATS = [dict(g, hasCompleteStatistics=False) for g in FakeSofascore().games]


# --- F1 -------------------------------------------------------------------------


def test_series_lines_grade_now_and_only_the_player_line_waits(
    tmp_path: Path,
) -> None:
    write_snapshot(tmp_path)  # maps_total pair + REZ map-3 kills pair
    run_settle(tmp_path, FakeSofascore(games=NO_STATS), 50)
    rec = settled(tmp_path)["1"]
    assert rec["state"] == "SETTLED"
    assert {r["family"] for r in rec["graded"]} == {"maps_total"}
    assert rec["stats_pending"] == 2 and rec["pending_sides"] == 2
    assert rec["pending_reason"] == "STATS_PENDING"
    assert settle_cs2.is_waiting(rec)
    # asked again, and once the rows land the player line is graded too
    sofa = FakeSofascore()
    result = run_settle(tmp_path, sofa, 60)
    assert result["metrics"]["kept"] == 0 and sofa.calls
    rec = settled(tmp_path)["1"]
    assert {r["family"] for r in rec["graded"]} == {"maps_total", "player_kills"}
    assert rec["pending_sides"] == 0 and not settle_cs2.is_waiting(rec)


def test_a_failed_retry_never_replaces_the_partial_grades(tmp_path: Path) -> None:
    write_snapshot(tmp_path)
    run_settle(tmp_path, FakeSofascore(games=NO_STATS), 50)
    # lookup fails: the pinned id answers nothing (C2), nor does the search
    lost = {"listed": False, "event_answers": False}
    run_settle(tmp_path, FakeSofascore(**lost), 60)
    rec = settled(tmp_path)["1"]
    assert rec["state"] == "SETTLED" and rec["last_retry_state"] == "NOT_ON_SOFASCORE"
    assert {r["family"] for r in rec["graded"]} == {"maps_total"}
    assert rec["pending_sides"] == 2
    # past GIVE_UP_AFTER the waiting sides are given up, the grades kept
    run_settle(tmp_path, FakeSofascore(**lost), 24 * 8)
    rec = settled(tmp_path)["1"]
    assert rec["state"] == "SETTLED" and rec["pending_sides"] == 0
    assert rec["gave_up_pending"] == 2 and not settle_cs2.is_waiting(rec)


# --- F2 / F8 --------------------------------------------------------------------


def _score(a: str, b: str) -> float:
    return cs2.esports_score(cs2.esports_name(a), cs2.esports_name(b))


def test_womens_markers_fold_to_one_and_never_match_a_mens_roster() -> None:
    assert _score("MIBR (K)", "MIBR fe") > cs2.NAME_MATCH_THRESHOLD
    assert _score("MIBR (K)", "MIBR Female") > cs2.NAME_MATCH_THRESHOLD
    assert _score("MIBR (W)", "MIBR fe") > cs2.NAME_MATCH_THRESHOLD
    assert _score("MIBR (K)", "MIBR") == 0.0
    assert _score("MIBR", "MIBR fe") == 0.0


def test_dot_gg_is_an_affix() -> None:
    assert _score("KUUSAMO", "KUUSAMO.gg") > cs2.NAME_MATCH_THRESHOLD


def test_pick_event_finds_the_womens_series() -> None:
    ev = {
        "id": 7,
        "startTimestamp": int(KICKOFF.timestamp()),
        "homeTeam": {"name": "MIBR fe"},
        "awayTeam": {"name": "FURIA fe"},
        "tournament": {"category": {"name": "Counter Strike"}},
    }
    mens = {**ev, "id": 8, "homeTeam": {"name": "MIBR"}, "awayTeam": {"name": "FURIA"}}
    hit = cs2.pick_event([ev, mens], "MIBR (K)", "FURIA (K)", KICKOFF)
    assert hit is not None and hit != "AMBIGUOUS" and hit[0]["id"] == 7


# --- F4 -------------------------------------------------------------------------


def test_series_only_counts_add_up_and_map_lines_stay_retryable(
    tmp_path: Path,
) -> None:
    write_snapshot(tmp_path)
    rounds_less = [
        {"id": g["id"], "startTimestamp": g["startTimestamp"],
         "status": {"type": "finished"}, "homeScore": {}, "awayScore": {}}
        for g in FakeSofascore().games
    ]
    result = run_settle(tmp_path, FakeSofascore(games=rounds_less), 30)
    rec = settled(tmp_path)["1"]
    assert rec["state"] == "SETTLED" and rec["series_only"] is True
    counted = (
        len(rec["graded"]) + rec["void"] + rec["ungradeable"] + rec["unpaired"]
        + rec["series_only_skipped"]
    )
    assert rec["series_only_skipped"] == 2 and counted == rec["priced_sides"] == 4
    assert rec["pending_reason"] == "SERIES_ONLY" and settle_cs2.is_waiting(rec)
    assert result["metrics"]["series_only_skipped"] == 2
    # a coupon leg on a map line is pending, not UNGRADEABLE, while it waits
    leg = {"superbet_event_id": "1", "family": "map_winner", "map_nr": 1,
           "subject": "", "line": None, "side": "T1", "odds": 1.5,
           "team1": "GamerLegion", "team2": "magic",
           "kickoff_utc": "2026-09-26T15:00:00Z"}
    coupon = {"sport": "cs2", "date": DATE, "legs": [leg]}
    (out,) = sd.grade_legs(coupon, {DATE: {"events": {"1": rec}}})
    assert out["outcome"] == "PENDING:SERIES_ONLY"
    # past a week: final, still counted
    run_settle(tmp_path, FakeSofascore(games=rounds_less), 24 * 8)
    rec = settled(tmp_path)["1"]
    assert rec["pending_sides"] == 0 and rec["series_only_skipped"] == 2
    (out,) = sd.grade_legs(coupon, {DATE: {"events": {"1": rec}}})
    assert out["outcome"] == "UNGRADEABLE"


# --- F5 -------------------------------------------------------------------------


def test_the_morning_plan_sweeps_d7_to_d2() -> None:
    _, morning, _ = cs2_daily.plan(
        "2026-10-01", 30, datetime.now(UTC), datetime.now(UTC), 0
    )
    assert ["scripts/sofa/settle_cs2.py", "--sweep-from", "2026-09-24",
            "--sweep-to", "2026-09-29"] in morning


def test_waiting_dates_reads_only_the_files(tmp_path: Path) -> None:
    def day(date: str, events: dict[str, Any] | None) -> None:
        d = tmp_path / "cs2" / date
        d.mkdir(parents=True)
        (d / "snapshots.jsonl").write_text("{}\n")
        if events is not None:
            (d / "settled.json").write_text(json.dumps({"events": events}))

    day("2026-09-24", {"a": {"state": "SETTLED", "pending_sides": 0}})
    day("2026-09-25", {"a": {"state": "SETTLED", "pending_sides": 2}})
    day("2026-09-26", {"a": {"state": "NOT_ON_SOFASCORE"}})
    day("2026-09-27", None)  # never settled
    day("2026-09-28", {"a": {"state": "GAVE_UP"}, "b": {"state": "VOID"}})
    dates = settle_cs2.date_range("2026-09-23", "2026-09-28")
    assert settle_cs2.waiting_dates(str(tmp_path), dates) == [
        "2026-09-25", "2026-09-26", "2026-09-27",
    ]


# --- F6 -------------------------------------------------------------------------


def test_settle_writes_sofascores_start(tmp_path: Path) -> None:
    write_snapshot(tmp_path)
    run_settle(tmp_path, FakeSofascore(), 6)
    rec = settled(tmp_path)["1"]
    assert rec["sofascore_start_utc"] == "2026-09-26T15:00:00Z"
    leg = {"superbet_event_id": "1", "family": "maps_total", "map_nr": 0,
           "subject": "", "line": 2.5, "side": "OVER", "odds": 1.95,
           "team1": "GamerLegion", "team2": "magic",
           "kickoff_utc": "2026-09-26T15:00:00Z",
           "price_fetched_at_utc": "2026-09-26T15:01:00Z"}
    (out,) = sd.grade_legs(
        {"sport": "cs2", "date": DATE, "legs": [leg]}, {DATE: {"events": {"1": rec}}}
    )
    assert out["outcome"] == "IN_PLAY_PRICE"


# --- F8b ------------------------------------------------------------------------


def test_a_concurrent_writers_series_survives_the_merge(tmp_path: Path) -> None:
    write_snapshot(tmp_path)
    path = tmp_path / "cs2" / DATE / "settled.json"

    class Sneaky(FakeSofascore):
        def event(self, event_id: int) -> dict[str, Any]:
            # another settle writes a series this run never touches
            path.write_text(json.dumps({"events": {"other": {"state": "VOID"}}}))
            return super().event(event_id)

    run_settle(tmp_path, Sneaky(), 6)
    events = settled(tmp_path)
    assert events["other"] == {"state": "VOID"} and events["1"]["state"] == "SETTLED"
    assert (path.parent / "settled.json.lock").exists()


# --- not found, then retried --------------------------------------------------------


def test_a_price_after_sofascores_start_is_never_graded(tmp_path: Path) -> None:
    # Review 2026-10-04 (Spirit - ShindeN 10-03): Superbet moved the kickoff
    # past Sofascore's start and a snapshot taken after that start was graded.
    write_snapshot(tmp_path)
    path = tmp_path / "cs2" / "2026-09-26" / "snapshots.jsonl"
    first = json.loads(path.read_text())
    late = {**first, "fetched_at_utc": "2026-09-26T15:00:45Z",
            "kickoff_utc": "2026-09-26T15:20:00Z",
            "lines": [dict(ln, odds=1.05) for ln in first["lines"]]}
    path.write_text(json.dumps(first) + "\n" + json.dumps(late) + "\n")
    run_settle(tmp_path, FakeSofascore(), 6)
    rec = settled(tmp_path)["1"]
    assert rec["cut_at_sofascore_start"] is True
    odds = {(r["family"], r["side"]): r["odds"] for r in rec["graded"]}
    assert odds[("maps_total", "OVER")] == 1.95, "the 12:00 price, not 15:00:45"


def test_a_failed_retry_keeps_what_the_not_found_record_knew(tmp_path: Path) -> None:
    # Review 2026-10-04: an ERROR replaced NOT_ON_SOFASCORE and dropped the
    # tournament, so the series left the unsettleable-tournament counts.
    write_snapshot(tmp_path)
    run_settle(tmp_path, FakeSofascore(listed=False), 6)
    assert settled(tmp_path)["1"]["state"] == "NOT_ON_SOFASCORE"

    sofa = FakeSofascore()
    original = settle_cs2.Cs2Sofascore.find

    def boom(self: Any, *a: Any, **k: Any) -> Any:
        raise RuntimeError("ProviderError: HTTP 403")

    settle_cs2.Cs2Sofascore.find = boom  # type: ignore[method-assign]
    try:
        run_settle(tmp_path, sofa, 30)
    finally:
        settle_cs2.Cs2Sofascore.find = original  # type: ignore[method-assign]
    rec = settled(tmp_path)["1"]
    assert rec["state"] == "ERROR" and rec["previous_state"] == "NOT_ON_SOFASCORE"
    assert rec["tournament"] == "CCT - EU" and rec["priced_sides"] == 4


def test_chained_failed_retries_keep_the_first_not_found_state(tmp_path: Path) -> None:
    write_snapshot(tmp_path)
    run_settle(tmp_path, FakeSofascore(listed=False), 6)
    original = settle_cs2.Cs2Sofascore.find

    def boom(self: Any, *a: Any, **k: Any) -> Any:
        raise RuntimeError("ProviderError: HTTP 403")

    settle_cs2.Cs2Sofascore.find = boom  # type: ignore[method-assign]
    try:
        run_settle(tmp_path, FakeSofascore(), 30)
        run_settle(tmp_path, FakeSofascore(), 54)
        run_settle(tmp_path, FakeSofascore(), 24 * 8)
    finally:
        settle_cs2.Cs2Sofascore.find = original  # type: ignore[method-assign]
    rec = settled(tmp_path)["1"]
    assert rec["previous_state"] == "NOT_ON_SOFASCORE"
    assert rec["state"] in ("ERROR", "GAVE_UP")
