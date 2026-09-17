"""T04 — precision of resolution on the golden set (L24).

Recall without precision is not a measurement of matching: a fixture resolved to
*another match of the same team* is scored as a success by a recall-only file
and then builds the dossier from somebody else's game.

Responses come from the raw payloads embedded in the golden file, not from a
hand-written mock. A mock that answers the way the algorithm expects measures
the mock.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.cache import SofaCache
from bet.sofa.config import SofaConfig
from bet.sofa.db import migrate
from bet.sofa.names import normalize_name
from bet.sofa.resolve import SofaResolver

GOLDEN_PATH = Path("tests/fixtures/sofascore/golden_matches.json")

# Only a file that says it was measured may be quoted as the E4 precision AC.
MEASURED_KINDS = {"measured"}
REQUIRED_PRECISION = 0.98


@pytest.fixture(scope="module")
def golden() -> dict[str, Any]:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


class ReplayClient:
    """Serves exactly the payloads the golden entry recorded, and nothing else."""

    def __init__(self, entry: dict[str, Any]) -> None:
        self.entry = entry
        self.search_calls = 0

    def search(self, q: str) -> Any:
        self.search_calls += 1
        recorded = self.entry["payloads"].get("search")
        if not recorded:
            return None
        if recorded["query_contains"] not in q.lower():
            # A query we never recorded an answer for is a miss, not a guess.
            return {"results": []}
        return recorded["body"]

    def entity_events(self, entity_id: int, kind: str, page: int) -> Any:
        recorded = self.entry["payloads"].get("entity_events")
        if not recorded or entity_id != recorded["entity_id"]:
            return None
        if page > 0 or kind != "last":
            # The recorded listing is page 0 of "last"; anything else is absent.
            return {"events": [], "hasNextPage": False}
        return recorded["body"]

    def event(self, id: int) -> Any:
        return None


def resolve_entry(entry: dict[str, Any], tmp_path: Path) -> dict[str, Any] | None:
    config = SofaConfig(
        db_path=str(tmp_path / f"golden_{abs(hash(entry['superbet_match_name']))}.db")
    )
    migrate(config.db_path)
    cache = SofaCache(config)
    client = ReplayClient(entry)
    resolver = SofaResolver(config, client, cache)  # type: ignore[arg-type]

    side_a, side_b = entry["superbet_match_name"].split("·")
    kickoff = datetime.fromisoformat(entry["kickoff_utc"].replace("Z", "+00:00"))

    if "search" not in entry["covers"]:
        # The search half was never recorded for this entry; seed the entity as
        # verified so the test exercises the half that IS backed by a payload.
        cache.save_entity(
            sport=entry["sport"],
            query_key=normalize_name(side_a),
            sofascore_id=entry["payloads"]["entity_events"]["entity_id"],
            sofascore_name=side_a,
            entity_type="team",
            country=None,
            status="verified",
        )

    _entity_id, event, _ambiguous = resolver.resolve_entity(
        entry["sport"], side_a, kickoff, side_b
    )
    if event is None:
        _entity_id, event, _ambiguous = resolver.resolve_entity(
            entry["sport"], side_b, kickoff, side_a
        )
    return event


def test_golden_file_is_self_describing(golden: dict[str, Any]) -> None:
    """The file must say what it is, so nobody quotes a number it cannot support."""
    assert golden["kind"] in {"measured", "partial_measured", "synthetic"}
    assert golden["entries"], "an empty golden set measures nothing"
    for entry in golden["entries"]:
        assert entry["expected"] in {"match", "no_match"}
        assert entry["payloads"]["entity_events"], (
            f"{entry['superbet_match_name']} has no recorded listing; an entry "
            "without a payload cannot be replayed offline"
        )
        source = entry["payloads"]["entity_events"]["source"]
        assert Path(source).exists(), f"evidence file {source} is gone"


def test_no_false_match_on_the_golden_set(
    golden: dict[str, Any], tmp_path: Path
) -> None:
    """Precision: a wrong match blocks, an honest miss does not.

    This runs on every kind of golden set, because "never resolve to the wrong
    match" is a behaviour we want guarded whatever the set's provenance. What a
    non-measured set may NOT do is stand in for the E4 acceptance criterion —
    that is the next test.
    """
    correct = 0
    false_matches: list[str] = []

    for entry in golden["entries"]:
        event = resolve_entry(entry, tmp_path)
        name = entry["superbet_match_name"]

        if entry["expected"] == "match":
            if event is None:
                continue  # a miss costs recall, not precision
            if event["id"] == entry["expected_sofascore_id"]:
                correct += 1
                assert event["homeTeam"]["name"] == entry["expected_home_name"]
                assert event["awayTeam"]["name"] == entry["expected_away_name"]
            else:
                false_matches.append(
                    f"{name}: resolved to {event['id']} "
                    f"({event['homeTeam']['name']} v {event['awayTeam']['name']}), "
                    f"expected {entry['expected_sofascore_id']}"
                )
        else:
            if event is not None:
                false_matches.append(
                    f"{name}: expected no match, resolved to {event['id']} "
                    f"({event['homeTeam']['name']} v {event['awayTeam']['name']})"
                )

    assert not false_matches, "false matches:\n" + "\n".join(false_matches)

    decided = correct + len(false_matches)
    precision = correct / decided if decided else 0.0
    assert precision >= REQUIRED_PRECISION, f"precision {precision:.3f}"


def test_e4_precision_ac_requires_a_measured_set(golden: dict[str, Any]) -> None:
    """The AC of E4 is 60 hand-labelled fixtures. Say so when they are missing.

    This test passes while recording, in the failure message, that the AC is not
    met — the point is that nobody can read "T04 green" as "precision >= 0.98 on
    60 fixtures" when the file itself says it is not that.
    """
    ac = golden["ac_status"]
    if golden["kind"] in MEASURED_KINDS:
        football = sum(1 for e in golden["entries"] if e["sport"] == "football")
        tennis = sum(1 for e in golden["entries"] if e["sport"] == "tennis")
        assert len(golden["entries"]) >= ac["required_entries"]
        assert football >= ac["required_football"]
        assert tennis >= ac["required_tennis"]
        assert ac["met"] is True
        return

    # Not a measured set: the file must admit it, and say why.
    assert ac["met"] is False, (
        "a non-measured golden set must not claim the E4 AC is met"
    )
    assert ac["blocker"], "a set that does not meet the AC must record why"
    pytest.skip(
        f"E4 precision AC NOT MET: golden set is '{golden['kind']}' with "
        f"{ac['actual_entries']} of {ac['required_entries']} entries. "
        f"Blocker: {ac['blocker']}"
    )
