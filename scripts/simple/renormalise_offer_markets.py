#!/usr/bin/env python3
"""Re-file a stored SUPERBET offer's lines under the current market names.

Why this exists. ``SuperbetOfferV1`` stores *normalised* lines: each carries a
canonical ``market`` and, beside it, ``source_market_name`` -- Superbet's own
words for the market it came from. When the mapping from those words to a
canonical name changes, every offer already on disk is filed under the old
name, and a sheet built by the new code asks for a market the artifact does not
contain. It does not error; it reports the line as not offered.

That happened on 2026-09-03, when "Liczba kartek" was repointed from
``cards_total`` (yellows) to ``cards_points_total`` (booking points): the day's
own offer file still filed the Grenal's five-rung card ladder under
``cards_total``, so a re-run of that day priced its card rows against no price
at all.

This is a re-normalisation and not a repair: ``classify_market`` is re-run on
the stored ``source_market_name``, which is the same input the original
normalisation used. Nothing is guessed and nothing is re-fetched -- the prices,
the lines, the statuses and the team names are untouched. ``team_name`` in
particular is *ours* (resolved against the event record at collection time) and
``classify_market`` returns Superbet's spelling, so it is deliberately kept.

Only ever useful on a re-run of a past day. A live run collects the offer with
the current code and needs none of this.

    python3 scripts/simple/renormalise_offer_markets.py --offer PATH [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (str(ROOT), str(ROOT / "src")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from bet.simple_stats.artifact_io import write_json_atomic  # noqa: E402
from bet.simple_stats.contracts import SuperbetOfferV1  # noqa: E402
from bet.simple_stats.superbet_offer import (  # noqa: E402
    classify_market,
    classify_player_market,
)


def _current_market(line) -> str | None:
    """What the current code would call this line's market, or None.

    Player markets are classified by their own table, and a name neither table
    recognises leaves the line alone: an unmapped name is a diagnostic, and
    dropping a priced line because a table moved would be worse than leaving it
    under a stale name.
    """
    raw = line.source_market_name
    if not raw:
        return None
    if line.player_name is not None:
        player = classify_player_market(raw)
        return player[0] if player else None
    match = classify_market(raw)
    return match[0] if match else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offer", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    path = Path(args.offer)
    offer = SuperbetOfferV1.model_validate_json(path.read_text(encoding="utf-8"))

    moves: Counter[tuple[str, str]] = Counter()
    events = []
    for event in offer.events:
        lines = []
        for line in event.lines:
            current = _current_market(line)
            if current is None or current == line.market:
                lines.append(line)
                continue
            moves[(line.market, current)] += 1
            lines.append(line.model_copy(update={"market": current}))
        events.append(event.model_copy(update={"lines": lines}))

    total = sum(moves.values())
    print(f"events: {len(events)}  lines re-filed: {total}")
    for (before, after), count in moves.most_common():
        print(f"  {before} -> {after}: {count}")
    if args.dry_run:
        print("dry run: nothing written")
        return 0
    if not total:
        print("nothing to do")
        return 0
    write_json_atomic(path, offer.model_copy(update={"events": events}).model_dump(mode="json"))
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
