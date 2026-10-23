#!/usr/bin/env python3
"""P5 of the coverage audit 2026-10-23 (B5): a footballer's Sofascore slug
read as a second name (epochs.PLAYER_SLUG_NAME_FROM_UTC). Read-only evidence.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_audit1023_p5_slug.py \\
        --db-path data/refit_2026-10-23_allin/sofa_copy.db \\
        --days 2026-10-21,2026-10-22,2026-10-23 [--history-limit 40000] [--json-out f]

`live`: every quoted player the day's 03_samples.json left "matched no squad
member" (NO_ENTITY_FOUND) is matched again over the squads of his fixture's
sampled matches (the event ids its metric observations carry, cached
lineups) with players.match_player_by_slug, on build_player_samples' terms
(found on one side only, one squad name); each hit lists his starts and
every Sofascore player id the matched entries carry (one id = one person).

`history` (the false-match test): over the newest `--history-limit` cached
football lineups, every entry whose slug names other tokens than its name;
how often that slug is shared inside its squad (the matcher refuses), how
often its tokens are another member's NAME (a Superbet name the fuzzy
matcher already gives to that member, never reaching the slug), and across
the whole sample how many slugs carry more than one player id (one slug,
two people - the case a per-match match could mix up).
"""

from __future__ import annotations

import argparse
import collections
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "src", ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from bet.sofa.names import normalize_name  # noqa: E402
from bet.sofa.players import (  # noqa: E402
    PLAYER_ID_KEY,
    SLUG_NAME_KEY,
    _name_tokens,
    match_player_by_slug,
    squad_statistics,
    started,
)


def _lineups(con: sqlite3.Connection, eid: int) -> dict[str, Any] | None:
    row = con.execute("SELECT lineups_json FROM sofa_event_stats "
                      "WHERE sofascore_event_id = ?", (eid,)).fetchone()
    if not row or not row[0]:
        return None
    try:
        value = json.loads(row[0])
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _side_events(fixture: dict[str, Any]) -> dict[str, set[int]]:
    out: dict[str, set[int]] = {"side_a": set(), "side_b": set()}
    for sample in (fixture.get("metrics") or {}).values():
        for side in out:
            for o in sample.get(side) or []:
                if isinstance(o.get("sofascore_event_id"), int):
                    out[side].add(o["sofascore_event_id"])
    return out


def _entity_side(con: sqlite3.Connection, eid: int, entity: int) -> bool | None:
    row = con.execute("SELECT event_json FROM sofa_listed_event WHERE event_id=?",
                      (eid,)).fetchone()
    if not row:
        return None
    ev = json.loads(row[0])
    if (ev.get("homeTeam") or {}).get("id") == entity:
        return True
    if (ev.get("awayTeam") or {}).get("id") == entity:
        return False
    return None


def live(con: sqlite3.Connection, days: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for day in days:
        run = ROOT / "runs" / "sofa" / day
        samples = json.loads((run / "03_samples.json").read_text())
        fixtures = {f["sofascore_event_id"]: f for f in json.loads(
            (run / "02_fixtures.json").read_text())}
        hits, misses = [], 0
        for fx in samples:
            missing = sorted({g["detail"].split("'")[1] if "'" in g["detail"]
                              else g["detail"].split('"')[1]
                              for g in fx.get("gaps") or []
                              if g.get("reason") == "NO_ENTITY_FOUND"
                              and "matched no squad member" in g["detail"]})
            if not missing:
                continue
            meta = fixtures.get(fx["sofascore_event_id"]) or {}
            events = _side_events(fx)
            squads: dict[str, list[tuple[int, dict[str, Any]]]] = {
                "side_a": [], "side_b": []}
            for side, entity in (("side_a", meta.get("home_entity_id")),
                                 ("side_b", meta.get("away_entity_id"))):
                for eid in sorted(events[side]):
                    lineups = _lineups(con, eid)
                    home = _entity_side(con, eid, int(entity or 0))
                    if lineups is None or home is None:
                        continue
                    sq = squad_statistics(lineups, is_home=home, slug_name=True,
                                          player_id=True)
                    if sq:
                        squads[side].append((eid, sq))
            for player in missing:
                names: dict[str, set[str]] = {"side_a": set(), "side_b": set()}
                starts: dict[str, int] = {"side_a": 0, "side_b": 0}
                ids: set[int] = set()
                for side, items in squads.items():
                    for _eid, sq in items:
                        key = match_player_by_slug(player, sq)
                        if key is None:
                            continue
                        names[side].add(key)
                        pid = sq[key].get(PLAYER_ID_KEY)
                        if isinstance(pid, int):
                            ids.add(pid)
                        if (sq[key].get("minutesPlayed") is not None
                                and started(sq[key]) is not False):
                            starts[side] += 1
                answered = [s for s in names if names[s]]
                if len(answered) == 1 and len(names[answered[0]]) == 1:
                    side = answered[0]
                    hits.append({"fixture": fx["sofascore_event_id"],
                                 "player": player,
                                 "matched": sorted(names[side])[0],
                                 "side": side, "starts": starts[side],
                                 "player_ids": sorted(i for i in ids if i)})
                elif answered:
                    misses += 1
        out[day] = {"recovered": hits, "refused_ambiguous": misses,
                    "recovered_players": len({h["player"] for h in hits}),
                    "recovered_with_5_starts": len({
                        h["player"] for h in hits if h["starts"] >= 5}),
                    "one_id_each": all(len(h["player_ids"]) == 1 for h in hits)}
    return out


def history(con: sqlite3.Connection, limit: int) -> dict[str, Any]:
    counts: collections.Counter[str] = collections.Counter()
    slug_ids: dict[str, set[int]] = collections.defaultdict(set)
    for (raw,) in con.execute(
        "SELECT s.lineups_json FROM sofa_event_stats s JOIN sofa_listed_event l "
        "ON l.event_id = s.sofascore_event_id WHERE l.sport = 'football' "
        "AND s.lineups_json IS NOT NULL AND length(s.lineups_json) > 100 "
        "ORDER BY l.start_ts DESC LIMIT ?", (limit,),
    ):
        try:
            lineups = json.loads(raw)
        except ValueError:
            continue
        counts["lineups"] += 1
        for home in (True, False):
            side = (lineups.get("home" if home else "away") or {})
            for entry in side.get("players") or []:
                player = (entry or {}).get("player") or {}
                slug, pid = player.get("slug"), player.get("id")
                if isinstance(slug, str) and isinstance(pid, int):
                    slug_ids[slug].add(pid)
            sq = squad_statistics(lineups, is_home=home, slug_name=True)
            if not sq:
                continue
            name_tokens = {k: _name_tokens(k) for k in sq}
            for key, st in sq.items():
                slug_name = st.get(SLUG_NAME_KEY)
                if not isinstance(slug_name, str):
                    continue
                counts["entries"] += 1
                tokens = _name_tokens(slug_name)
                if tokens == name_tokens[key]:
                    continue
                counts["slug_differs"] += 1
                same_slug = sum(1 for s in sq.values()
                                if s.get(SLUG_NAME_KEY) == slug_name)
                if same_slug > 1:
                    counts["slug_shared_in_squad(refused)"] += 1
                other = [k for k, t in name_tokens.items()
                         if k != key and t == tokens]
                if other:
                    counts["slug_is_another_members_name"] += 1
                if match_player_by_slug(slug_name, sq) == key:
                    counts["slug_matcher_finds_him"] += 1
                elif match_player_by_slug(slug_name, sq) is not None:
                    counts["slug_matcher_finds_someone_else"] += 1
                if normalize_name(slug_name) != key:
                    counts["differs_normalised"] += 1
    multi = {s: sorted(i) for s, i in slug_ids.items() if len(i) > 1}
    counts["distinct_slugs"] = len(slug_ids)
    counts["slugs_with_2plus_ids"] = len(multi)
    return {"counts": dict(counts),
            "examples_2plus_ids": dict(sorted(multi.items())[:20])}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db-path", required=True)
    ap.add_argument("--days", default="")
    ap.add_argument("--history-limit", type=int, default=40000)
    ap.add_argument("--json-out")
    args = ap.parse_args()
    con = sqlite3.connect(f"file:{args.db_path}?mode=ro", uri=True)
    report: dict[str, Any] = {}
    if args.days:
        report["live"] = live(con, args.days.split(","))
    if args.history_limit:
        report["history"] = history(con, args.history_limit)
    text = json.dumps(report, indent=1, ensure_ascii=False)
    if args.json_out:
        Path(args.json_out).write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
