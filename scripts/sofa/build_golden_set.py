#!/usr/bin/env python3
"""Build the E4 golden set from a real board, with raw payloads embedded.

`per_fixture_match_test.json` is not a golden set: it records the algorithm's
own output, with no match date, no Sofascore team names and no independently
confirmed expected id. A resolution to *another fixture of the same team* is
indistinguishable from a success in it — and that is precisely the failure that
builds a dossier out of somebody else's match.

This script produces something that can measure precision:

* 40 football and 20 tennis fixtures sampled from a real board (fixed seed),
* for each, the raw `/search/all` and `/team/{id}/events/last/{page}` responses,
  so the test replays offline,
* `expected: null` on every entry — **you** fill it in.

The output is written with ``kind: "needs_labelling"``. It becomes
``kind: "measured"`` only when a human has set every `expected` and
`expected_sofascore_id` by checking the fixture on sofascore.com, and has
flipped the kind by hand. The test refuses to quote precision from any other
kind, so an unlabelled file cannot be mistaken for a measurement.

Usage:
    python -m scripts.sofa.build_golden_set --date 2026-09-18
    # then label tests/fixtures/sofascore/golden_matches.json by hand
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

from bet.sofa.client import SofascoreClient
from bet.sofa.config import SofaConfig
from bet.sofa.names import normalize_name
from bet.sofa.timeutil import now

OUT_PATH = Path("tests/fixtures/sofascore/golden_matches.json")
FOOTBALL_TARGET = 40
TENNIS_TARGET = 20
SEED = 42


def candidate_entity_ids(search_body: Any, sport: str) -> list[int]:
    """Up to three plausible entity ids — never just results[0] (L23)."""
    if not isinstance(search_body, dict):
        return []
    ids: list[int] = []
    for result in search_body.get("results", []):
        if result.get("type") != "team":
            continue
        entity = result.get("entity", {})
        if entity.get("sport", {}).get("slug") != sport:
            continue
        if entity.get("id") is not None:
            ids.append(int(entity["id"]))
        if len(ids) == 3:
            break
    return ids


def build_entry(
    board_fixture: dict[str, Any], client: SofascoreClient
) -> dict[str, Any] | None:
    side_a = board_fixture["side_a"]
    sport = board_fixture["sport"]

    try:
        search_body = client.search(normalize_name(side_a))
    except Exception as exc:  # noqa: BLE001
        return {
            "superbet_match_name": board_fixture["match_name"],
            "sport": sport,
            "kickoff_utc": board_fixture["kickoff_utc"],
            "expected": None,
            "expected_sofascore_id": None,
            "expected_home_name": None,
            "expected_away_name": None,
            "expected_tournament": None,
            "covers": [],
            "note": f"search failed: {exc!r}",
            "payloads": {"search": None, "entity_events": None},
        }

    entity_ids = candidate_entity_ids(search_body, sport)
    listings: list[dict[str, Any]] = []
    for entity_id in entity_ids:
        for page in range(3):
            try:
                body = client.entity_events(entity_id, "last", page)
            except Exception:  # noqa: BLE001
                break
            if not body:
                break
            listings.append({"entity_id": entity_id, "page": page, "body": body})
            if not body.get("hasNextPage"):
                break

    return {
        "superbet_match_name": board_fixture["match_name"],
        "sport": sport,
        "kickoff_utc": board_fixture["kickoff_utc"],
        # Left null on purpose. A machine-filled expectation measures the
        # machine; only a human checking sofascore.com can label this.
        "expected": None,
        "expected_sofascore_id": None,
        "expected_home_name": None,
        "expected_away_name": None,
        "expected_tournament": None,
        "covers": ["search", "events"] if listings else ["search"],
        "note": "",
        "payloads": {
            "search": {
                "query_contains": normalize_name(side_a),
                "source": "live",
                "body": search_body,
            },
            "entity_events": listings[0] if listings else None,
            "entity_events_all": listings,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=now().strftime("%Y-%m-%d"), help="YYYY-MM-DD")
    parser.add_argument("--out", default=str(OUT_PATH))
    args = parser.parse_args()

    config = SofaConfig.from_env()
    board_path = Path(config.runs_dir) / args.date / "01_board.json"
    if not board_path.exists():
        print(
            f"{board_path} missing — run `run_board.py --date {args.date}` first",
            file=sys.stderr,
        )
        return 2

    board = json.loads(board_path.read_text(encoding="utf-8"))
    football = [b for b in board if b["sport"] == "football"]
    tennis = [b for b in board if b["sport"] == "tennis"]

    rng = random.Random(SEED)
    sample = rng.sample(football, min(FOOTBALL_TARGET, len(football))) + rng.sample(
        tennis, min(TENNIS_TARGET, len(tennis))
    )

    client = SofascoreClient(config)
    entries = [e for e in (build_entry(b, client) for b in sample) if e]

    payload = {
        "kind": "needs_labelling",
        "_doc": [
            "UNLABELLED. Every `expected` below is null.",
            "",
            "To turn this into a measurement: open each fixture on sofascore.com,",
            "confirm the match by date AND both participants, then set `expected`",
            "to 'match' or 'no_match' and `expected_sofascore_id` to the id you",
            "confirmed. Fill expected_home_name / expected_away_name from the page.",
            "Only then set kind to 'measured'.",
            "",
            "tests/sofa/test_resolve_golden.py refuses to quote the E4 precision",
            "AC from any kind other than 'measured'.",
        ],
        "ac_status": {
            "required_entries": FOOTBALL_TARGET + TENNIS_TARGET,
            "required_football": FOOTBALL_TARGET,
            "required_tennis": TENNIS_TARGET,
            "actual_entries": len(entries),
            "met": False,
            "blocker": "entries are not labelled yet",
        },
        "entries": entries,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(
        "SOFA_SUMMARY: "
        + json.dumps(
            {
                "stage": "BUILD_GOLDEN",
                "verdict": "PARTIAL",
                "metrics": {
                    "entries": len(entries),
                    "football": sum(1 for e in entries if e["sport"] == "football"),
                    "tennis": sum(1 for e in entries if e["sport"] == "tennis"),
                    "with_listings": sum(
                        1 for e in entries if e["payloads"]["entity_events"]
                    ),
                    "needs_labelling": len(entries),
                },
                "output_path": str(out_path),
            }
        )
    )
    return 1  # PARTIAL: never OK until a human has labelled it


if __name__ == "__main__":
    sys.exit(main())
