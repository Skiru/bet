"""Goals are counted at 90 minutes everywhere, the cache replay included.

On 2026-09-26 the cache replay read ``homeScore.current``, which carries the
penalty shootout: a J.League 2 cup tie that finished 2-2 read 7-5, and J2's
fitted goals_total baseline came out 3.87 against a real ~2.46.
"""

import json
from pathlib import Path
from typing import Any

from bet.sofa.db import get_connection, migrate
from bet.sofa.metrics import regulation_score
from scripts.sofa.calibrate_from_cache import load_cache

SHOOTOUT: dict[str, Any] = {
    "id": 15281332,
    "startTimestamp": 1_750_000_000,
    "status": {"code": 120, "description": "AP", "type": "finished"},
    "homeTeam": {"id": 1},
    "awayTeam": {"id": 2},
    "tournament": {
        "category": {"sport": {"slug": "football"}},
        "uniqueTournament": {"id": 402},
    },
    "homeScore": {"current": 7, "normaltime": 2, "penalties": 5},
    "awayScore": {"current": 5, "normaltime": 2, "penalties": 3},
}


def test_a_shootout_counts_the_ninety_minute_score() -> None:
    assert regulation_score(SHOOTOUT) == (2.0, 2.0)


def test_a_regular_match_counts_current() -> None:
    event = {
        "status": {"code": 100, "type": "finished"},
        "homeScore": {"current": 3},
        "awayScore": {"current": 1},
    }
    assert regulation_score(event) == (3.0, 1.0)


def test_a_missing_score_is_none() -> None:
    assert regulation_score({"status": {"code": 100}, "homeScore": {}}) is None


def test_the_cache_replay_reads_the_ninety_minute_score(tmp_path: Path) -> None:
    db = str(tmp_path / "sofa.db")
    migrate(db)
    with get_connection(db) as conn:
        conn.execute(
            "INSERT INTO sofa_entity_events VALUES (?, ?, ?, ?, ?)",
            (1, "last", 0, "2026-09-26T00:00:00Z", json.dumps({"events": [SHOOTOUT]})),
        )
        conn.commit()
    played = load_cache(Path(db))
    assert len(played) == 1
    assert played[0].values["goals"] == (2.0, 2.0)
