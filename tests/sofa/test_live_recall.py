import json
from datetime import UTC, datetime

import pytest

from bet.sofa.cache import SofaCache
from bet.sofa.client import SofascoreClient
from bet.sofa.config import SofaConfig
from bet.sofa.resolve import SofaResolver, split_match_name


@pytest.mark.sofa_live
def test_live_recall(tmp_path):
    config = SofaConfig(db_path=str(tmp_path / "test.db"))
    from bet.sofa.db import migrate

    migrate(config.db_path)

    cache = SofaCache(config)
    client = SofascoreClient(config)
    resolver = SofaResolver(config, client, cache)

    with open("docs/sofa/evidence/per_fixture_match_test.json") as f:
        data = json.load(f)

    # we need to simulate the resolve logic
    # but we don't have kickoff_utc!
    # The file has: "match_name", "sofascore_id", "tournament", "round", "success"
    # But wait, without kickoff, how can I use resolve_entity which requires it?
    # Maybe we can fetch the event by sofascore_id first to get its startTimestamp,
    # then resolve it to see if it matches! Yes!

    total = 0
    successes = 0
    gaps = {}

    for sport, fixtures in data.items():
        for bf in fixtures:
            # L1 measures recall over the whole file, not a sample of it.
            total += 1
            expected_id = bf.get("sofascore_id")
            if not expected_id:
                continue

            # get real kickoff
            event_data = client.event(expected_id)
            if not event_data or "event" not in event_data:
                continue

            start_ts = event_data["event"]["startTimestamp"]
            kickoff = datetime.fromtimestamp(start_ts, UTC)

            side_a, side_b = split_match_name(bf["match_name"])

            eid, evt, is_ambig = resolver.resolve_entity(sport, side_a, kickoff, side_b)
            if not evt:
                eid, evt, is_ambig = resolver.resolve_entity(
                    sport, side_b, kickoff, side_a
                )

            if evt and evt["id"] == expected_id:
                successes += 1
            else:
                if is_ambig:
                    gaps["AMBIGUOUS"] = gaps.get("AMBIGUOUS", 0) + 1
                else:
                    gaps["NO_MATCH"] = gaps.get("NO_MATCH", 0) + 1

    recall = successes / total if total > 0 else 0
    print(f"Recall: {recall * 100:.1f}%, Successes: {successes}/{total}")
    print(f"Gaps: {gaps}")
