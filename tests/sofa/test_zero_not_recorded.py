"""A 0-0 that means "not recorded" is no observation and no grade (2026-10-03).

The 10-03 verifier found event 16494320 (Wealdstone - Halifax) stored with
corners 0-0 beside total tackles 0/1; 28 such corner zeros sat in the samples
of 20 of the day's fixtures. Measured over the whole cached football history
(data/night_2026-10-03/guards/), the full feed (the payload carrying
`passes`) has 0-0 corners at 0.02% and the partial feeds at 2.87% with the
same mean - the excess is the provider's placeholder. The payloads below are
verbatim from the DB (docs/sofa/evidence/zero_not_recorded_2026-10-03.json).
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
    NEED_FULL_FEED,
    ZERO_PAIR_GUARDED,
    extract_flat_statistics,
    extract_metric,
    zero_pair_not_recorded,
)
from bet.sofa.samples import process_historical_event
from scripts.sofa.calibrate_from_cache import match_values
from scripts.sofa.run_settle import STAT_GAP_REASONS, stat_gap_events

REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "docs/sofa/evidence/zero_not_recorded_2026-10-03.json"


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
    return extract_metric(metric, "football", flat, None, _listing(case), is_home)


def _stats(all_period: dict[str, tuple[float, float]]) -> dict[str, Any]:
    items = [
        {"key": k, "homeValue": h, "awayValue": a} for k, (h, a) in all_period.items()
    ]
    return {"statistics": [{"period": "ALL", "groups": [{"statisticsItems": items}]}]}


# --- the verifier's case, exactly as stored --------------------------------


def test_wealdstone_halifax_corners_are_not_an_observation() -> None:
    for metric in ("corners_total", "corners_for"):
        for is_home in (True, False):
            got = _metric(16494320, metric, is_home)
            assert got is GapReason.ZERO_NOT_RECORDED, (metric, is_home, got)


def test_wealdstone_halifax_keeps_what_was_counted() -> None:
    # The same payload's fouls (14-9) and shots (6-6) are real numbers.
    assert _metric(16494320, "fouls_total") == 23.0
    assert _metric(16494320, "shots_total") == 12.0
    assert _metric(16494320, "offsides_total") == 6.0
    # Tackles 0/1 was already the placeholder (ZERO_MEANS_UNTRACKED).
    assert _metric(16494320, "tackles_total") is GapReason.NO_STATISTICS


def test_the_note_names_the_companion() -> None:
    flat = extract_flat_statistics(_case(16494320)["statistics"])
    note = zero_pair_not_recorded("cornerKicks", flat["ALL"])
    assert note == "cornerKicks 0-0 beside placeholder totalTackle 0-1"


# --- partial feeds ------------------------------------------------------------


def test_cove_rangers_six_one_with_no_shot_on_target_is_refused() -> None:
    assert _metric(16568814, "corners_total") is GapReason.ZERO_NOT_RECORDED
    assert _metric(16568814, "shots_on_target_total") is GapReason.ZERO_NOT_RECORDED


def test_corners_beside_a_goal_kick_placeholder_are_refused() -> None:
    assert _metric(16560277, "corners_total") is GapReason.ZERO_NOT_RECORDED


def test_a_partial_feed_zero_alone_is_refused_for_the_rare_keys() -> None:
    all_period = {"cornerKicks": (0.0, 0.0), "yellowCards": (2.0, 1.0)}
    assert zero_pair_not_recorded("cornerKicks", all_period) == (
        "cornerKicks 0-0 in a partial feed (no passes)"
    )


# --- what must stay ----------------------------------------------------------


def test_a_full_feed_nil_nil_without_a_placeholder_stays() -> None:
    # Liga de Expansion MX 4-2: the genuine tail lives in the full feed.
    assert _metric(16522425, "corners_total") == 0.0


def test_offsides_nil_nil_alone_stays_in_every_feed() -> None:
    partial = {"offsides": (0.0, 0.0), "freeKicks": (12.0, 9.0), "cornerKicks": (5.0, 4.0)}
    assert zero_pair_not_recorded("offsides", partial) is None
    # Full feed: a tackle placeholder only doubles the offsides 0-0 rate.
    full = {"offsides": (0.0, 0.0), "passes": (400.0, 380.0), "totalTackle": (0.0, 2.0)}
    assert zero_pair_not_recorded("offsides", full) is None


def test_offsides_beside_a_partial_feed_placeholder_is_refused() -> None:
    partial = {"offsides": (0.0, 0.0), "freeKicks": (0.0, 0.0), "cornerKicks": (5.0, 4.0)}
    assert zero_pair_not_recorded("offsides", partial) == "offsides 0-0 beside freeKicks 0-0"


def test_a_one_sided_zero_and_a_nonzero_pair_are_never_touched() -> None:
    for pair in ((0.0, 3.0), (4.0, 0.0), (5.0, 4.0)):
        assert zero_pair_not_recorded("cornerKicks", {"cornerKicks": pair}) is None


def test_saves_and_cards_are_not_guarded() -> None:
    # A keeper can make no save; cards points come from the incidents.
    assert "goalkeeperSaves" not in ZERO_PAIR_GUARDED
    assert "yellowCards" not in ZERO_PAIR_GUARDED
    assert NEED_FULL_FEED <= ZERO_PAIR_GUARDED


def test_no_shot_at_all_does_not_count_its_own_parts_as_evidence() -> None:
    # totalShotsOnGoal 0-0 implies shotsOnGoal/shotsOffGoal 0-0; only the
    # partial feed refuses it here, not the implied companions.
    full = {"totalShotsOnGoal": (0.0, 0.0), "shotsOnGoal": (0.0, 0.0),
            "shotsOffGoal": (0.0, 0.0), "passes": (300.0, 310.0)}
    assert zero_pair_not_recorded("totalShotsOnGoal", full) is None


def test_the_halves_inherit_the_full_match_refusal() -> None:
    stats = _stats({"cornerKicks": (0.0, 0.0), "goalKicks": (0.0, 0.0)})
    stats["statistics"] += [
        {"period": p, "groups": [{"statisticsItems": [
            {"key": "cornerKicks", "homeValue": 0, "awayValue": 0}]}]}
        for p in ("1ST", "2ND")
    ]
    flat = extract_flat_statistics(stats)
    got = extract_metric("corners_1h_total", "football", flat, None, {}, True)
    assert got is GapReason.ZERO_NOT_RECORDED


# --- SAMPLES, the cache replay and SETTLE agree ------------------------------


@pytest.fixture
def cache(tmp_path: Path) -> SofaCache:
    db = str(tmp_path / "sofa.db")
    migrate(db)
    return SofaCache(SofaConfig(db_path=db))


def test_samples_record_the_gap_with_its_note(cache: SofaCache) -> None:
    case = _case(16494320)
    conn = sqlite3.connect(cache.config.db_path)
    conn.execute(
        "INSERT INTO sofa_event_stats (sofascore_event_id, fetched_at,"
        " statistics_json, incidents_json, status_type)"
        " VALUES (?, '2026-09-19T05:00:15+00:00', ?, NULL, 'finished')",
        (16494320, json.dumps(case["statistics"])),
    )
    conn.commit()
    conn.close()
    out = process_historical_event(
        MagicMock(), cache, _listing(case), 1, "football",
        {"corners_total", "fouls_total"}, MagicMock(),
    )
    assert out["collected"]["corners_total"] is GapReason.ZERO_NOT_RECORDED
    assert out["collected"]["fouls_total"].value == 23.0
    assert out["zero_notes"] == {
        "corners_total": "cornerKicks 0-0 beside placeholder totalTackle 0-1"
    }


def test_the_cache_replay_drops_the_same_pair() -> None:
    case = _case(16494320)
    values = match_values(_listing(case), "football", json.dumps(case["statistics"]), None)
    assert "corners" not in values
    assert values["fouls"] == (14.0, 9.0)
    kept = _case(16522425)
    assert match_values(_listing(kept), "football", json.dumps(kept["statistics"]), None)[
        "corners"
    ] == (0.0, 0.0)


def test_settle_skips_it_as_a_stat_gap_the_morning_refetch_re_asks(
    tmp_path: Path,
) -> None:
    # run_settle grades through extract_metric, so the row is skipped with
    # "corners_total:ZERO_NOT_RECORDED" instead of graded at zero; the
    # --refetch-stat-gaps pass must pick that event up again.
    assert "ZERO_NOT_RECORDED" in STAT_GAP_REASONS
    skips = tmp_path / "07_settle_skips.json"
    skips.write_text(json.dumps({"skipped_events": [
        {"sofascore_event_id": 16494320,
         "skipped": {"corners_total:ZERO_NOT_RECORDED": 4}},
        {"sofascore_event_id": 1, "skipped": {"PUSH": 1}},
    ]}), encoding="utf-8")
    assert stat_gap_events(skips) == frozenset({16494320})
