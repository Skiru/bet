import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Literal

from pydantic import RootModel

from bet.sofa.cache import SofaCache
from bet.sofa.client import SofascoreClient
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import BoardFixture, Fixture, GapReason
from bet.sofa.errors import CircuitOpenError, ProviderError
from bet.sofa.names import normalize_name
from bet.sofa.resolve import (
    NAME_EXACT_THRESHOLD,
    SofaResolver,
    parse_fixture,
    split_match_name,
)
from bet.sofa.stage import set_stage
from bet.sofa.timeutil import now


def main() -> int:
    # Every request underneath this call is this stage's cost (F22).
    set_stage("RESOLVE")
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

    resolved_fixtures: dict[int, Fixture] = {}
    duplicates = 0
    gaps: dict[GapReason, int] = defaultdict(int)
    breaker_open = False

    # What a previous run of this stage, for this date, already resolved.
    #
    # A re-run after kickoff is not a repeat of the morning's run, because the
    # two listing routes stop covering the match: `events/next` drops a fixture
    # once it starts and `events/last` does not pick it up until Sofascore
    # marks it finished, so a live or just-finished match is in NEITHER.
    # Measured on 2026-09-18 by replaying RESOLVE at 21:30 against the same
    # board the 12:20 run used: Wisła Kraków's `next/0` began 2026-10-11 and
    # its `last/0` ended 2026-09-11, with that evening's fixture in the hole.
    # 131 of the morning's 491 fixtures vanished — every one of them a match
    # that had already kicked off, including Espanyol·Elche and Wisła·Śląsk.
    #
    # So the stage is additive within a date: a second run may correct and may
    # add, and cannot silently narrow the slate. Newly resolved events win, and
    # anything the new pass could not see is carried forward (F54).
    out_path = Path(config.runs_dir) / args.date / "02_fixtures.json"
    previous: dict[int, Fixture] = {}
    if out_path.exists():
        try:
            with open(out_path, encoding="utf-8") as f:
                previous = {
                    fixture.sofascore_event_id: fixture
                    for fixture in RootModel[list[Fixture]]
                    .model_validate_json(json.dumps(json.load(f)))
                    .root
                }
        except Exception as exc:  # a corrupt artifact must not kill the stage
            print(f"PREVIOUS_ARTIFACT_UNREADABLE {out_path}: {exc}", file=sys.stderr)
            previous = {}

    try:
        for bf in fixtures:
            try:
                side_a, side_b = split_match_name(bf.match_name)
                if not side_a or not side_b:
                    side_a, side_b = bf.side_a, bf.side_b

                if not side_a or not side_b:
                    gaps[GapReason.NO_ENTITY_FOUND] += 1
                    continue

                # Try resolve side_a first
                opponent = side_b
                entity_id, event, is_ambig = resolver.resolve_entity(
                    bf.sport,
                    side_a,
                    bf.kickoff_utc,
                    side_b,
                    board_side_a=side_a,
                    board_side_b=side_b,
                )

                if is_ambig:
                    gaps[GapReason.AMBIGUOUS_ENTITY] += 1
                    continue

                if not event:
                    # Fallback to side_b
                    opponent = side_a
                    # side_a/side_b swap for the retry; the board's order
                    # does not, and the F25 gates need the board's order.
                    entity_id, event, is_ambig = resolver.resolve_entity(
                        bf.sport,
                        side_b,
                        bf.kickoff_utc,
                        side_a,
                        board_side_a=side_a,
                        board_side_b=side_b,
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
                    existing_ids = resolved_fixtures[sf_id].superbet_event_ids
                    if bf.superbet_event_id not in existing_ids:
                        resolved_fixtures[sf_id].superbet_event_ids.append(
                            bf.superbet_event_id
                        )
                    duplicates += 1
                else:
                    # The opponent's name cleared the fuzzy threshold but may not have
                    # matched exactly; recording which it was keeps `identity` a fact
                    # rather than a constant.
                    quality = resolver.match_quality(
                        event,
                        bf.kickoff_utc,
                        normalize_name(opponent),
                        sport=bf.sport,
                        superbet_side_a=side_a,
                        superbet_side_b=side_b,
                    )
                    identity: Literal["CONFIRMED", "FUZZY"] = (
                        "CONFIRMED"
                        if quality is not None and quality >= NAME_EXACT_THRESHOLD
                        else "FUZZY"
                    )
                    resolved_fixtures[sf_id] = parse_fixture(
                        event,
                        bf.sport,
                        [bf.superbet_event_id],
                        client,
                        identity=identity,
                        superbet_kickoff_utc=bf.kickoff_utc,
                        cache=cache,
                    )
            except CircuitOpenError:
                # The breaker gave up on the provider. Every remaining
                # fixture would fail the same way, so stop asking - but
                # fall through to write what we already have.
                gaps[GapReason.PROVIDER_ERROR] += 1
                breaker_open = True
                break
            except ProviderError as e:
                # One fixture's provider failure is a gap in the slate, not
                # the end of the stage. Losing 613 fixtures to a single
                # timeout is what this replaces.
                print(f"PROVIDER_ERROR {bf.match_name}: {e}", file=sys.stderr)
                gaps[GapReason.PROVIDER_ERROR] += 1
                continue
    finally:
        # F5 only held for CircuitOpenError, because the write sat after the
        # loop: any other exception — the sqlite3.OperationalError of F14, say
        # — left no artifact at all, and with it no record of the fixtures that
        # had already resolved. The write belongs in finally (F15).
        carried = 0
        for event_id, fixture in previous.items():
            if event_id in resolved_fixtures:
                # Both passes saw it; keep the fresh one, but never lose a
                # board entry the earlier pass had already bridged to it.
                bridged = resolved_fixtures[event_id].superbet_event_ids
                for superbet_id in fixture.superbet_event_ids:
                    if superbet_id not in bridged:
                        bridged.append(superbet_id)
                continue
            resolved_fixtures[event_id] = fixture
            carried += 1

        out_path.parent.mkdir(parents=True, exist_ok=True)
        dumped = [f.model_dump(mode="json") for f in resolved_fixtures.values()]
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(dumped, f, indent=2)

    fuzzy = sum(1 for f in resolved_fixtures.values() if f.identity == "FUZZY")
    recall = len(resolved_fixtures) / len(fixtures) if fixtures else 0.0
    # `carried` is bound in the finally block above, which always runs first.

    metrics = {
        "input_board": len(fixtures),
        "breaker_open": breaker_open,
        "output_fixtures": len(resolved_fixtures),
        "carried_from_previous_run": carried,
        "resolved_this_run": len(resolved_fixtures) - carried,
        "duplicate_board_entries_merged": duplicates,
        "identity_fuzzy": fuzzy,
        "recall": round(recall, 4),
        "gaps": {k.value: v for k, v in gaps.items()},
    }

    # A slate that resolved nothing is not a quiet day, it is a broken stage.
    if fixtures and not resolved_fixtures:
        verdict = "FAILED"
    elif breaker_open:
        # Artifact written, but the slate is knowingly incomplete.
        verdict = "PARTIAL"
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
    print(f"SOFA_SUMMARY: {json.dumps(summary)}", flush=True)
    return {"OK": 0, "PARTIAL": 1, "FAILED": 2}[verdict]


if __name__ == "__main__":
    sys.exit(main())
