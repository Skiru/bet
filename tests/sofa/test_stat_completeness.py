"""Frozen, broken /statistics in the cache (bet.sofa.stat_completeness).

2026-09-28: Racing de Cordoba - Godoy Cruz (Primera B Nacional) was cached a
few hours after the match with two keys (cards only) while every one of the
17 sample matches of both teams, from the same competition, carried 31 keys
including corners. Sofascore fills lower-league statistics in days later;
re-asked, event 15275908 went from 2 keys to 31. 40 of the 52 ungraded
variant singles of 2026-09-27 sat on such matches.
"""

import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bet.sofa.db import migrate
from bet.sofa.stat_completeness import (
    BROKEN,
    CachedStats,
    EventMeta,
    build_norms,
    classify,
    event_meta,
    parse_statistics,
    used_keys,
)

FULL = frozenset(
    {"cornerKicks", "fouls", "totalShotsOnGoal", "yellowCards", "redCards"}
)
CARDS = frozenset({"yellowCards", "redCards"})
HALVES = frozenset({"ALL", "1ST", "2ND"})
T0 = 1_790_000_000
HOUR = 3600


def _stats(
    eid: int,
    keys: frozenset[str],
    periods: frozenset[str] = HALVES,
    lag_h: float = 200.0,
) -> CachedStats:
    return CachedStats(eid, T0 + lag_h * HOUR, keys, periods if keys else frozenset())


def _meta(group: int = 703, sport: str = "football") -> EventMeta:
    return EventMeta(sport, group, "Argentina | Primera B Nacional", T0)


def _judge(events: list[CachedStats], group: int = 703) -> dict[int, str]:
    meta = {e.event_id: _meta(group) for e in events}
    norms = build_norms(events, meta)
    return {
        e.event_id: classify(e, meta[e.event_id], norms[("football", group)]).verdict
        for e in events
    }


def test_a_cards_only_snapshot_in_a_league_that_has_corners_is_broken_and_fresh():
    events = [_stats(i, FULL) for i in range(6)]
    events.append(_stats(99, CARDS, frozenset({"ALL"}), lag_h=5.0))
    meta = {e.event_id: _meta() for e in events}
    norm = build_norms(events, meta)[("football", 703)]
    f = classify(events[-1], meta[99], norm)
    assert f.verdict == "PARTIAL_KEYS" and f.verdict in BROKEN
    assert "cornerKicks" in f.missing_keys
    assert f.missing_periods == ("1ST", "2ND")
    assert f.fresh and f.lag_hours == pytest.approx(5.0)


def test_a_league_that_only_ever_publishes_cards_is_not_a_defect():
    verdicts = _judge([_stats(i, CARDS, frozenset({"ALL"})) for i in range(8)])
    assert set(verdicts.values()) == {"COMPLETE"}


def test_a_late_partial_is_broken_but_not_worth_a_refetch():
    events = [_stats(i, FULL) for i in range(6)] + [_stats(99, CARDS, lag_h=400.0)]
    meta = {e.event_id: _meta() for e in events}
    f = classify(events[-1], meta[99], build_norms(events, meta)[("football", 703)])
    assert f.verdict == "PARTIAL_KEYS" and not f.fresh


def test_nothing_is_broken_where_the_group_has_stats_and_honest_where_it_has_none():
    covered = [_stats(i, FULL) for i in range(6)] + [_stats(99, frozenset())]
    assert _judge(covered)[99] == "EMPTY_IN_COVERED"
    barren = [_stats(i, frozenset()) for i in range(6)] + [_stats(99, FULL)]
    verdicts = _judge(barren, group=1)
    assert verdicts[0] == "NO_COVERAGE"


def test_every_key_but_no_half_breakdown_is_a_partial_period():
    events = [_stats(i, FULL) for i in range(6)] + [
        _stats(99, FULL, frozenset({"ALL"}))
    ]
    assert _judge(events)[99] == "PARTIAL_PERIODS"


def test_a_group_too_small_to_have_a_norm_says_so():
    events = [_stats(i, FULL) for i in range(3)] + [_stats(99, CARDS)]
    assert _judge(events)[99] == "NO_NORM"


def test_statistics_are_read_from_the_all_period_only():
    body = {
        "statistics": [
            {
                "period": "ALL",
                "groups": [{"statisticsItems": [{"key": "cornerKicks"}]}],
            },
            {"period": "1ST", "groups": [{"statisticsItems": [{"key": "fouls"}]}]},
        ]
    }
    keys, periods = parse_statistics(json.dumps(body))
    assert keys == {"cornerKicks"} and periods == {"ALL", "1ST"}
    assert parse_statistics(None) == (frozenset(), frozenset())
    assert parse_statistics("not json") == (frozenset(), frozenset())


def _listing(
    eid: int, sport: str, category: int, unique: int, start: int
) -> dict[str, object]:
    return {
        "id": eid,
        "startTimestamp": start,
        "tournament": {
            "name": "t",
            "category": {"id": category, "name": "Cat", "sport": {"slug": sport}},
            "uniqueTournament": {"id": unique, "name": "U"},
        },
    }


def test_football_groups_by_competition_and_tennis_by_category():
    f = event_meta(_listing(1, "football", 48, 703, T0))
    t = event_meta(_listing(2, "tennis", 785, 9402, T0))
    assert f is not None and f.group_id == 703
    assert t is not None and t.group_id == 785  # a tennis week is too few to norm
    assert event_meta({"id": 3}) is None


def _body(keys: frozenset[str], periods: frozenset[str] = HALVES) -> str:
    return json.dumps(
        {
            "statistics": [
                {
                    "period": p,
                    "groups": [{"statisticsItems": [{"key": k} for k in keys]}],
                }
                for p in periods
            ]
        }
    )


_INSERT = (
    "INSERT INTO sofa_event_stats (sofascore_event_id, fetched_at, statistics_json,"
    " status_type) VALUES (?, ?, ?, 'finished')"
)


def test_the_audit_reads_the_cache_and_names_the_recoverable_settle_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    db = tmp_path / "sofa.db"
    migrate(str(db))
    conn = sqlite3.connect(db)
    listings = [_listing(i, "football", 48, 703, T0) for i in range(1, 8)]
    conn.execute(
        "INSERT INTO sofa_entity_events VALUES (1, 'last', 0, ?, ?)",
        ("2026-09-28T00:00:00+00:00", json.dumps({"events": listings})),
    )
    late = datetime.fromtimestamp(T0 + 200 * HOUR, tz=UTC).isoformat()
    early = datetime.fromtimestamp(T0 + 5 * HOUR, tz=UTC).isoformat()
    for i in range(1, 7):
        conn.execute(_INSERT, (i, late, _body(FULL)))
    conn.execute(_INSERT, (7, early, _body(CARDS, frozenset({"ALL"}))))
    conn.commit()
    conn.close()
    day = tmp_path / "runs/sofa/2026-09-27"
    day.mkdir(parents=True)
    (day / "07_settle_skips.json").write_text(
        json.dumps(
            {
                "skipped_events": [
                    {
                        "sofascore_event_id": 7,
                        "home_name": "Racing",
                        "away_name": "Godoy",
                        "skipped": {"corners_total:STAT_KEY_ABSENT": 10},
                    },
                ]
            }
        )
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SOFA_DB_PATH", str(db))
    monkeypatch.setattr(
        sys, "argv", ["audit", "--date", "2026-09-27", "--out-dir", "out"]
    )

    from scripts.sofa.audit_stat_completeness import main

    assert main() == 1  # something fresh is broken
    report = json.loads(next((tmp_path / "out").glob("*.json")).read_text())
    assert [b["event_id"] for b in report["broken"]] == [7]
    assert report["broken"][0]["fresh"] is True
    assert report["settle"]["stat_gap_rows_on_broken_events"] == 10
    assert report["counts"]["football"] == {"COMPLETE": 6, "PARTIAL_KEYS": 1}


def test_a_key_no_market_reads_is_not_a_defect():
    # First run flagged 37,193 football matches for punches / errorsLeadToShot /
    # xG - keys added in later seasons; a live probe recovered 1 of 20.
    newer = FULL | {"punches", "errorsLeadToShot", "expectedGoals"}
    events = [_stats(i, newer) for i in range(6)] + [_stats(99, FULL)]
    assert _judge(events)[99] == "COMPLETE"
    assert "punches" not in used_keys("football")
    assert {"cornerKicks", "fouls"} <= used_keys("football")
    assert {"aces", "doubleFaults"} <= used_keys("tennis")


def test_an_empty_match_in_a_league_with_no_market_keys_is_not_broken():
    # A cards-only league: an empty cached match there loses no market.
    events = [_stats(i, CARDS, frozenset({"ALL"})) for i in range(6)]
    events.append(_stats(99, frozenset()))
    assert _judge(events)[99] == "NO_COVERAGE"
