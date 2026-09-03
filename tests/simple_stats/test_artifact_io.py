"""Reading back artifacts this repo's schema has moved on from.

Re-running a finished day is routine here -- resume at SUPERBET, re-analyze,
rebuild the coupons -- so a schema change must not turn yesterday's artifacts
into rubble. On 2026-09-02 it did: bzzoiro-tennis was removed, ``ModelPrediction``
lost its seven tennis fields, and every ``market_context.json`` already on disk
became unreadable at once. The three readers failed three different ways, and
the quietest was the worst.
"""
import json

import pytest

from bet.simple_stats.artifact_io import load_market_context


def _context(extra_prediction_fields: dict | None = None) -> dict:
    predictions = {"prob_goals_over_25": 0.55}
    predictions.update(extra_prediction_fields or {})
    return {
        "run_id": "RID-1",
        "date": "2026-09-02",
        "generated_at": "2026-09-02T10:00:00+00:00",
        "events": [
            {
                "event_id": "evt-1",
                "provider_event_id": "m1",
                "predictions": predictions,
            }
        ],
    }


def test_a_current_artifact_is_validated_strictly(tmp_path):
    path = tmp_path / "market_context.json"
    path.write_text(json.dumps(_context()), encoding="utf-8")
    context, dropped = load_market_context(path)
    assert dropped == []
    assert context.events[0].predictions.prob_goals_over_25 == 0.55


def test_fields_the_schema_has_forgotten_are_dropped_and_named(tmp_path):
    """The 2026-09-02 case exactly: seven tennis prediction fields removed from
    the contract, still present in every recorded artifact."""
    path = tmp_path / "market_context.json"
    path.write_text(
        json.dumps(
            _context({"prob_games_over_215": None, "expected_total_sets": None})
        ),
        encoding="utf-8",
    )
    context, dropped = load_market_context(path)
    assert dropped == ["expected_total_sets", "prob_games_over_215"]
    # The rest of the column still attaches; the alternative in run_analyze.py
    # was to drop the whole market read and continue as if it had never existed.
    assert context.events[0].predictions.prob_goals_over_25 == 0.55


def test_an_artifact_that_is_simply_wrong_still_raises(tmp_path):
    """This widens the door for fields the schema *used* to have, not for
    rubbish. A malformed artifact must not be laundered into a usable one."""
    path = tmp_path / "market_context.json"
    broken = _context()
    broken["events"][0]["predictions"]["prob_goals_over_25"] = "not a number"
    path.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(ValueError):
        load_market_context(path)
