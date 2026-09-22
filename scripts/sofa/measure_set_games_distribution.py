"""Distribution of a tennis player's games won in one set, from the cache.

Evidence for putting `games_won_set{1,2,3}_for` into
`EMPIRICAL_FREQUENCY_METRICS`. See
docs/sofa/evidence/games_won_per_set_distribution.md.
"""

from __future__ import annotations

import collections
import json
import sqlite3
import sys

from bet.sofa.config import SofaConfig
from bet.sofa.settle import NORMAL_FINISH_STATUS_CODE


def main() -> int:
    config = SofaConfig.from_env()
    conn = sqlite3.connect(config.db_path)
    conn.row_factory = sqlite3.Row

    dist: collections.Counter[tuple[int, int]] = collections.Counter()
    seen: set[int] = set()
    events = 0

    for row in conn.execute("SELECT events_json FROM sofa_entity_events"):
        payload = json.loads(row["events_json"]) or {}
        for event in payload.get("events", []):
            event_id = event.get("id")
            if event_id in seen:
                continue
            sport = (
                (event.get("tournament") or {})
                .get("category", {})
                .get("sport", {})
                .get("slug")
            )
            if sport != "tennis":
                continue
            status = event.get("status") or {}
            if status.get("type") != "finished":
                continue
            if status.get("code") != NORMAL_FINISH_STATUS_CODE:
                continue
            seen.add(event_id)
            events += 1
            home = event.get("homeScore") or {}
            away = event.get("awayScore") or {}
            for set_index in (1, 2, 3):
                key = f"period{set_index}"
                if key in home and key in away:
                    dist[(set_index, home[key])] += 1
                    dist[(set_index, away[key])] += 1

    print(f"tennis events: {events}")
    for set_index in (1, 2, 3):
        total = sum(v for (s, _), v in dist.items() if s == set_index)
        if not total:
            continue
        print(f"--- set {set_index} (n={total}) ---")
        for games in range(0, 10):
            n = dist.get((set_index, games), 0)
            print(f"   {games}: {n:6d} {100 * n / total:5.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
