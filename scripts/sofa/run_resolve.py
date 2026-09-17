import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from pydantic import RootModel

from bet.sofa.cache import SofaCache
from bet.sofa.client import SofascoreClient
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import BoardFixture, GapReason
from bet.sofa.names import normalize_name
from bet.sofa.resolve import (
    NAME_EXACT_THRESHOLD,
    SofaResolver,
    parse_fixture,
    split_match_name,
)
from bet.sofa.timeutil import now


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD", default=now().strftime("%Y-%m-%d"))
    args = parser.parse_args()

    config = SofaConfig.from_env()
    client = SofascoreClient(config)
    cache = SofaCache(config)
    resolver = SofaResolver(config, client, cache)

    board_path = Path(config.runs_dir) / args.date / "01_board.json"
    if not board_path.exists():
        print(f"{board_path} missing", file=sys.stderr)
        return 2

    with open(board_path, encoding="utf-8") as f:
        board_data = json.load(f)

    fixtures = (
        RootModel[list[BoardFixture]].model_validate_json(json.dumps(board_data)).root
    )

    resolved_fixtures = {}
    duplicates = 0
    gaps = defaultdict(int)

    for bf in fixtures:
        side_a, side_b = split_match_name(bf.match_name)
        if not side_a or not side_b:
            side_a, side_b = bf.side_a, bf.side_b

        if not side_a or not side_b:
            gaps[GapReason.NO_ENTITY_FOUND] += 1
            continue

        # Try resolve side_a first
        opponent = side_b
        entity_id, event, is_ambig = resolver.resolve_entity(
            bf.sport, side_a, bf.kickoff_utc, side_b
        )

        if is_ambig:
            gaps[GapReason.AMBIGUOUS_ENTITY] += 1
            continue

        if not event:
            # Fallback to side_b
            opponent = side_a
            entity_id, event, is_ambig = resolver.resolve_entity(
                bf.sport, side_b, bf.kickoff_utc, side_a
            )
            if is_ambig:
                gaps[GapReason.AMBIGUOUS_ENTITY] += 1
                continue

        if not event:
            gaps[GapReason.NO_MATCHING_EVENT] += 1
            continue

        sf_id = event["id"]
        if sf_id in resolved_fixtures:
            # A2/L12: two board entries pointing at one Sofascore event are one
            # fixture with two superbet ids, not two fixtures.
            if bf.superbet_event_id not in resolved_fixtures[sf_id].superbet_event_ids:
                resolved_fixtures[sf_id].superbet_event_ids.append(
                    bf.superbet_event_id
                )
            duplicates += 1
        else:
            # The opponent's name cleared the fuzzy threshold but may not have
            # matched exactly; recording which it was keeps `identity` a fact
            # rather than a constant.
            quality = resolver.match_quality(
                event, bf.kickoff_utc, normalize_name(opponent)
            )
            identity = (
                "CONFIRMED"
                if quality is not None and quality >= NAME_EXACT_THRESHOLD
                else "FUZZY"
            )
            resolved_fixtures[sf_id] = parse_fixture(
                event, bf.sport, [bf.superbet_event_id], client, identity=identity
            )

    out_path = Path(config.runs_dir) / args.date / "02_fixtures.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    dumped = [f.model_dump(mode="json") for f in resolved_fixtures.values()]
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(dumped, f, indent=2)

    fuzzy = sum(1 for f in resolved_fixtures.values() if f.identity == "FUZZY")
    recall = len(resolved_fixtures) / len(fixtures) if fixtures else 0.0

    metrics = {
        "input_board": len(fixtures),
        "output_fixtures": len(resolved_fixtures),
        "duplicate_board_entries_merged": duplicates,
        "identity_fuzzy": fuzzy,
        "recall": round(recall, 4),
        "gaps": {k.value: v for k, v in gaps.items()},
    }

    # A slate that resolved nothing is not a quiet day, it is a broken stage.
    if fixtures and not resolved_fixtures:
        verdict = "FAILED"
    elif gaps:
        verdict = "PARTIAL"
    else:
        verdict = "OK"

    summary = {
        "stage": "RESOLVE",
        "verdict": verdict,
        "metrics": metrics,
        "output_path": str(out_path),
    }
    print(f"SOFA_SUMMARY: {json.dumps(summary)}")
    return {"OK": 0, "PARTIAL": 1, "FAILED": 2}[verdict]


if __name__ == "__main__":
    sys.exit(main())
