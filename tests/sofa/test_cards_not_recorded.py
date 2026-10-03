"""Cards, corners and offsides read only where the payload recorded them (2026-10-04).

Three measured defects, all over the whole cached football history
(data/night_2026-10-03/guards2/), with the payloads below verbatim from the
DB (docs/sofa/evidence/cards_and_omitted_zeros_2026-10-04.json):

1. A goals-and-dismissals incident list (no substitution) lists red cards and
   mostly not the yellows. Read as card points it counted the reds only: the
   mean card points of partial-feed matches was 3.40 and of matches without
   statistics 3.74, against 4.54 in the full feed; with such lists refused
   they read 4.44 and 4.45 (full feed 4.48). And its card-free list beside a
   yellowCards 0-0 was 16.7% of the partial feed's card values.
2. The per-half full feed omits an item whose full-match pair is 0-0, so
   every genuine offsides 0-0 there (and every card-free match) was
   STAT_KEY_ABSENT: offsides 0-0 2.46% of the full feed as read, 4.82% once
   restored; all 205 such events with lineups sum totalOffside to 0.
3. A partial feed's single corner a match: 970 measured where a Poisson on
   the teams' other matches predicts 70 (that model predicts 75 of the full
   feed's 77).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from bet.sofa.cache import SofaCache
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import GapReason
from bet.sofa.db import migrate
from bet.sofa.metrics import (
    OMITTED_ZERO_KEYS,
    PARTIAL_FEED_MIN_TOTAL,
    calculate_cards_points,
    cards_not_recorded,
    extract_flat_statistics,
    extract_metric,
    fill_omitted_zero_pairs,
    zero_pair_not_recorded,
)
from bet.sofa.samples import process_historical_event
from scripts.sofa.calibrate_from_cache import match_values
from scripts.sofa.run_settle import STAT_GAP_REASONS, stat_gap_events

REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "docs/sofa/evidence/cards_and_omitted_zeros_2026-10-04.json"

RED_ONLY_PARTIAL = 12504996  # Promotion League: yellowCards 2-2, incidents one red
ZERO_PARTIAL_NO_SUBS = 12639760  # 3. Liga: no card, no substitution, yellowCards 0-0
YELLOWS_PARTIAL_NO_SUBS = (
    12732757  # Gamma Ethniki: 3 yellow incidents == yellowCards 0-3
)
PARTIAL_WITH_SUBS = 12125590  # Esiliiga B: substitutions, cards incl. a second yellow
OMITTED_NO_CARDS = 12420585  # Liga MX: per-half full feed, no yellowCards item, no card
OMITTED_ONE_RED = 14035273  # Scottish Premiership: no yellowCards item, one red
OMITTED_OFFSIDES = 13638765  # Serie B (BR): no offsides item; lineups totalOffside 0
NO_HALVES_FULL = 15546877  # TOPLYGA: full feed without halves, no yellowCards item
ONE_CORNER_PARTIAL = 13335717  # Faroe 1. Deild: partial feed, corners 1-0
ONE_CORNER_FULL = 14054563  # Betclic 2. Liga: full feed, corners 1-0
RED_ONLY_NO_STATS = 12659049  # Carioca B2: no statistics, incidents one red


def _case(event_id: int) -> dict[str, Any]:
    doc = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    for entry in doc["events"]:
        if entry["sofascore_event_id"] == event_id:
            return dict(entry)
    raise KeyError(event_id)


def _listing(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": case["sofascore_event_id"],
        "startTimestamp": 1_758_000_000,
        "status": {"type": "finished"},
        "homeTeam": {"id": 1, "name": case["home"]},
        "awayTeam": {"id": 2, "name": case["away"]},
        "homeScore": dict(case["homeScore"]),
        "awayScore": dict(case["awayScore"]),
    }


def _metric(event_id: int, metric: str, is_home: bool = True) -> float | GapReason:
    case = _case(event_id)
    flat = extract_flat_statistics(case["statistics"])
    return extract_metric(
        metric, "football", flat, case["incidents"], _listing(case), is_home
    )


def _stats(periods: dict[str, dict[str, tuple[float, float]]]) -> dict[str, Any]:
    return {
        "statistics": [
            {
                "period": period,
                "groups": [
                    {
                        "statisticsItems": [
                            {"key": k, "homeValue": h, "awayValue": a}
                            for k, (h, a) in items.items()
                        ]
                    }
                ],
            }
            for period, items in periods.items()
        ]
    }


SUB = {"incidentType": "substitution", "isHome": True}
GOAL = {"incidentType": "goal", "isHome": True}


def _card(cls: str, is_home: bool = True, **extra: Any) -> dict[str, Any]:
    return {"incidentType": "card", "incidentClass": cls, "isHome": is_home, **extra}


# --- 1. a goals-and-dismissals incident list is no card record ---------------


def test_red_card_only_list_beside_yellows_in_the_statistics_is_not_two_points() -> (
    None
):
    # The old reading: 2.0 (the red), while the statistics show four yellows.
    for metric in ("cards_points_total", "cards_points_for"):
        for is_home in (True, False):
            got = _metric(RED_ONLY_PARTIAL, metric, is_home)
            assert got is GapReason.CARDS_NOT_RECORDED, (metric, is_home, got)


def test_red_card_only_list_without_statistics_is_not_a_record_either() -> None:
    case = _case(RED_ONLY_NO_STATS)
    assert case["statistics"] is None
    assert (
        calculate_cards_points(case["incidents"], None) is GapReason.CARDS_NOT_RECORDED
    )


def test_card_free_list_without_substitutions_beside_yellow_zero_is_not_a_zero() -> (
    None
):
    got = _metric(ZERO_PARTIAL_NO_SUBS, "cards_points_total")
    assert got is GapReason.ZERO_NOT_RECORDED
    # The same payload's other statistics are untouched.
    assert _metric(ZERO_PARTIAL_NO_SUBS, "corners_total") == 12.0


def test_a_list_that_shows_its_yellows_is_still_read() -> None:
    assert _metric(YELLOWS_PARTIAL_NO_SUBS, "cards_points_total") == 3.0
    assert _metric(YELLOWS_PARTIAL_NO_SUBS, "cards_points_for", False) == 3.0


def test_a_detailed_list_is_read_exactly_as_before() -> None:
    assert _metric(PARTIAL_WITH_SUBS, "cards_points_total") == 6.0


@pytest.mark.parametrize(
    ("incidents", "stats", "expected"),
    [
        ([SUB, _card("red")], None, None),
        ([GOAL, _card("yellow"), _card("red")], None, None),
        ([GOAL, _card("red")], None, GapReason.CARDS_NOT_RECORDED),
        ([GOAL, _card("yellowRed")], None, GapReason.CARDS_NOT_RECORDED),
        # a rescinded yellow or a staff yellow shows no player's yellow
        (
            [_card("yellow", rescinded=True), _card("red")],
            None,
            GapReason.CARDS_NOT_RECORDED,
        ),
        ([_card("yellow", manager={"id": 9})], None, GapReason.CARDS_NOT_RECORDED),
        ([GOAL], {"yellowCards": (0.0, 0.0)}, GapReason.ZERO_NOT_RECORDED),
        ([SUB], {"yellowCards": (0.0, 0.0)}, None),
        # no card and no yellow statistic (or a nonzero one) stays the old
        # STAT_KEY_ABSENT, decided by calculate_cards_points
        ([GOAL], None, None),
        ([GOAL], {"yellowCards": (1.0, 2.0)}, None),
    ],
)
def test_cards_not_recorded_rules(
    incidents: list[dict[str, Any]],
    stats: dict[str, tuple[float, float]] | None,
    expected: GapReason | None,
) -> None:
    assert cards_not_recorded({"incidents": incidents}, stats) is expected


# --- 2. the per-half full feed's omitted 0-0 ---------------------------------


def test_omitted_yellow_item_with_no_card_is_a_card_free_match() -> None:
    # Was STAT_KEY_ABSENT: every genuine card-free match left the sample.
    assert _metric(OMITTED_NO_CARDS, "cards_points_total") == 0.0
    assert _metric(OMITTED_NO_CARDS, "offsides_total") == 4.0


def test_omitted_yellow_item_with_one_red_is_two_points() -> None:
    assert _metric(OMITTED_ONE_RED, "cards_points_total") == 2.0
    assert _metric(OMITTED_ONE_RED, "cards_points_for", True) == 2.0
    assert _metric(OMITTED_ONE_RED, "cards_points_for", False) == 0.0


def test_omitted_offsides_item_is_offsides_nil_nil_and_so_are_its_halves() -> None:
    case = _case(OMITTED_OFFSIDES)
    raw_keys = {
        item["key"]
        for period in case["statistics"]["statistics"]
        if period["period"] == "ALL"
        for group in period["groups"]
        for item in group["statisticsItems"]
    }
    assert "offsides" not in raw_keys and "passes" in raw_keys
    for metric in (
        "offsides_total",
        "offsides_for",
        "offsides_1h_total",
        "offsides_2h_for",
    ):
        assert _metric(OMITTED_OFFSIDES, metric) == 0.0, metric


def test_full_feed_without_halves_is_not_filled() -> None:
    # That shape keeps its 0-0 items; an absent one there is not a zero.
    flat = extract_flat_statistics(_case(NO_HALVES_FULL)["statistics"])
    assert "yellowCards" not in flat["ALL"]
    assert "1ST" not in flat


def test_fill_rules() -> None:
    full_halves = {
        "ALL": {"passes": (300.0, 280.0), "fouls": (10.0, 12.0)},
        "1ST": {"passes": (150.0, 140.0)},
        "2ND": {"passes": (150.0, 140.0)},
    }
    fill_omitted_zero_pairs(full_halves)
    for period in ("ALL", "1ST", "2ND"):
        for key in OMITTED_ZERO_KEYS:
            assert full_halves[period][key] == (0.0, 0.0)
    # untracked keys are never filled
    assert "cornerKicks" not in full_halves["ALL"]
    assert "fouls" not in full_halves["1ST"]

    partial = {"ALL": {"cornerKicks": (3.0, 4.0)}, "1ST": {"cornerKicks": (1.0, 2.0)}}
    fill_omitted_zero_pairs(partial)
    assert "offsides" not in partial["ALL"]

    no_halves = {"ALL": {"passes": (300.0, 280.0)}}
    fill_omitted_zero_pairs(no_halves)
    assert "offsides" not in no_halves["ALL"]

    sent = {
        "ALL": {"passes": (1.0, 1.0), "offsides": (2.0, 1.0)},
        "1ST": {"offsides": (2.0, 1.0)},
    }
    fill_omitted_zero_pairs(sent)
    assert sent["ALL"]["offsides"] == (2.0, 1.0)

    # a half that carries the key while the match does not: not this shape
    odd = {"ALL": {"passes": (1.0, 1.0)}, "1ST": {"offsides": (1.0, 0.0)}}
    fill_omitted_zero_pairs(odd)
    assert "offsides" not in odd["ALL"]


# --- 3. a partial feed's single corner ---------------------------------------


def test_partial_feed_single_corner_is_not_a_count() -> None:
    for metric in ("corners_total", "corners_for"):
        for is_home in (True, False):
            assert (
                _metric(ONE_CORNER_PARTIAL, metric, is_home)
                is GapReason.ZERO_NOT_RECORDED
            )


def test_full_feed_single_corner_is_kept() -> None:
    assert _metric(ONE_CORNER_FULL, "corners_total") == 1.0


@pytest.mark.parametrize(
    ("pair", "full", "refused"),
    [
        ((1.0, 0.0), False, True),
        ((0.0, 1.0), False, True),
        ((1.0, 1.0), False, False),
        ((2.0, 0.0), False, False),
        ((1.0, 0.0), True, False),
    ],
)
def test_single_corner_rule(
    pair: tuple[float, float], full: bool, refused: bool
) -> None:
    all_stats = {"cornerKicks": pair, "fouls": (10.0, 11.0)}
    if full:
        all_stats["passes"] = (300.0, 250.0)
    assert bool(zero_pair_not_recorded("cornerKicks", all_stats)) is refused
    assert PARTIAL_FEED_MIN_TOTAL == {"cornerKicks": 1.0}


def test_single_corner_halves_inherit() -> None:
    stats = _stats(
        {
            "ALL": {"cornerKicks": (1.0, 0.0)},
            "1ST": {"cornerKicks": (1.0, 0.0)},
            "2ND": {"cornerKicks": (0.0, 0.0)},
        }
    )
    flat = extract_flat_statistics(stats)
    for metric in ("corners_1h_total", "corners_2h_total"):
        got = extract_metric(metric, "football", flat, None, {}, True)
        assert got is GapReason.ZERO_NOT_RECORDED


# --- SAMPLES, the cache replay, the rating and SETTLE agree ------------------


@pytest.fixture
def cache(tmp_path: Path) -> SofaCache:
    db = str(tmp_path / "sofa.db")
    migrate(db)
    return SofaCache(SofaConfig(db_path=db))


def test_samples_record_the_cards_gap_with_its_note(cache: SofaCache) -> None:
    case = _case(RED_ONLY_PARTIAL)
    conn = sqlite3.connect(cache.config.db_path)
    conn.execute(
        "INSERT INTO sofa_event_stats (sofascore_event_id, fetched_at,"
        " statistics_json, incidents_json, status_type)"
        " VALUES (?, '2026-09-19T05:00:15+00:00', ?, ?, 'finished')",
        (
            RED_ONLY_PARTIAL,
            json.dumps(case["statistics"]),
            json.dumps(case["incidents"]),
        ),
    )
    conn.commit()
    conn.close()
    out = process_historical_event(
        MagicMock(),
        cache,
        _listing(case),
        1,
        "football",
        {"cards_points_total", "cards_points_for"},
        MagicMock(),
    )
    assert out["collected"]["cards_points_total"] is GapReason.CARDS_NOT_RECORDED
    assert "no card record" in out["zero_notes"]["cards_points_total"]


def test_the_cache_replay_agrees() -> None:
    def values(event_id: int) -> dict[str, tuple[float, float]]:
        case = _case(event_id)
        stats = json.dumps(case["statistics"]) if case["statistics"] else None
        inc = json.dumps(case["incidents"]) if case["incidents"] else None
        return match_values(_listing(case), "football", stats, inc)

    assert "cards_points" not in values(RED_ONLY_PARTIAL)
    assert "cards_points" not in values(ZERO_PARTIAL_NO_SUBS)
    assert values(PARTIAL_WITH_SUBS)["cards_points"] == (2.0, 4.0)
    assert values(OMITTED_NO_CARDS)["cards_points"] == (0.0, 0.0)
    assert values(OMITTED_OFFSIDES)["offsides"] == (0.0, 0.0)
    assert values(OMITTED_OFFSIDES)["offsides_1h"] == (0.0, 0.0)
    assert "corners" not in values(ONE_CORNER_PARTIAL)
    assert values(ONE_CORNER_FULL)["corners"] == (1.0, 0.0)


def test_the_football_rating_history_agrees_and_is_reparsed() -> None:
    from bet.sofa import football_rating

    def parsed(event_id: int) -> dict[str, tuple[float, float]]:
        case = _case(event_id)
        event = _listing(case)
        event["tournament"] = {
            "id": 5,
            "uniqueTournament": {"id": 17},
            "category": {"sport": {"slug": "football"}},
        }
        result = football_rating.parse_event(
            event, case["statistics"], case["incidents"]
        )
        assert result is not None
        return dict(result.values)

    assert "cards_points_for" not in parsed(RED_ONLY_PARTIAL)
    assert parsed(OMITTED_ONE_RED)["cards_points_for"] == (2.0, 0.0)
    assert "corners_for" not in parsed(ONE_CORNER_PARTIAL)
    assert football_rating.HISTORY_PARSER_VERSION >= "2026-10-04.2"


def test_settle_skips_it_and_the_morning_refetch_re_asks(tmp_path: Path) -> None:
    assert "CARDS_NOT_RECORDED" in STAT_GAP_REASONS
    skips = tmp_path / "07_settle_skips.json"
    skips.write_text(
        json.dumps(
            {
                "skipped_events": [
                    {
                        "sofascore_event_id": RED_ONLY_PARTIAL,
                        "skipped": {"cards_points_total:CARDS_NOT_RECORDED": 2},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    assert stat_gap_events(skips) == frozenset({RED_ONLY_PARTIAL})
