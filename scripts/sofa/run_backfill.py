#!/usr/bin/env python3
"""E10 — replay past days and settle them into ``sofa_settled_row``.

For each league/season/round: pull the finished events, rebuild each match's
sample **as it stood before its own kickoff**, price a grid of lines and settle
them against the real result.

What this produces is probability calibration, not ROI: there are no historical
Superbet prices, so ``market_p`` is NULL on every backfilled row (PLAN §A9).

Usage:
    python -m scripts.sofa.run_backfill --leagues 17,8,35 --seasons 2024,2025
    python -m scripts.sofa.run_backfill --plan config/sofa_backfill_plan.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa.cache import SofaCache
from bet.sofa.client import SofascoreClient
from bet.sofa.config import SofaConfig
from bet.sofa.db import get_connection, migrate
from bet.sofa.errors import CircuitOpenError, ProviderError
from bet.sofa.metrics import (
    check_identities,
    extract_flat_statistics,
    extract_metric,
)
from bet.sofa.samples import FRIENDLY_COMPETITION_IDS
from bet.sofa.settle import (
    SettledRow,
    historical_sample,
    insert_settled_rows,
    is_completed_event,
    settle_metric,
)
from bet.sofa.stage import set_stage

# Markets worth settling backwards: the counting markets Superbet actually
# prices. Props are excluded on purpose (L30).
FOOTBALL_BACKFILL_METRICS = [
    "goals_total",
    "goals_1h_total",
    "goals_2h_total",
    "corners_total",
    "cards_points_total",
    "fouls_total",
    "shots_total",
    "shots_on_target_total",
]
TENNIS_BACKFILL_METRICS = ["games_total", "sets_total", "aces_total"]

# cards_points needs /incidents; everything else lives in /statistics or the listing.
NEEDS_INCIDENTS = {"cards_points_total", "cards_points_for"}


def season_events(
    client: SofascoreClient, unique_tournament_id: int, season_id: int
) -> list[dict[str, Any]]:
    """Every event of one season, walking the paginated season endpoint."""
    events: list[dict[str, Any]] = []
    page = 0
    while page < 60:
        payload = client.season_events(unique_tournament_id, season_id, "last", page)
        if not payload:
            break
        batch = payload.get("events") or []
        if not batch:
            break
        events.extend(batch)
        if not payload.get("hasNextPage"):
            break
        page += 1
    return events


def team_history(
    client: SofascoreClient, cache: SofaCache, team_id: int, pages: int = 4
) -> list[dict[str, Any]]:
    """Team listing history, cached so the same team is fetched once per run."""
    events: list[dict[str, Any]] = []
    for page in range(pages):
        payload = cache.get_entity_events(team_id, "last", page)
        if payload is None:
            payload = client.entity_events(team_id, "last", page)
            if payload:
                cache.save_entity_events(team_id, "last", page, payload)
        if not payload:
            break
        batch = payload.get("events") or []
        if not batch:
            break
        events.extend(batch)
        if not payload.get("hasNextPage"):
            break
    return events


def event_payloads(
    client: SofascoreClient, cache: SofaCache, event_id: int, want_incidents: bool
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Statistics and incidents for one finished event, permanently cached."""
    cached = cache.get_event_stats(event_id)
    if cached:
        return cached[0], cached[1]
    stats = client.event_statistics(event_id)
    incidents = client.event_incidents(event_id) if want_incidents else None
    cache.save_event_stats(event_id, stats, incidents, "finished")
    return stats, incidents


def backfill_event(
    client: SofascoreClient,
    cache: SofaCache,
    event: dict[str, Any],
    sport: str,
    metrics: list[str],
    config: SofaConfig,
    k_centre: float,
    k_price: float,
) -> list[SettledRow]:
    """Settle one historical match against a sample built from before its kickoff."""
    if not is_completed_event(event):
        return []

    start_ts = event.get("startTimestamp")
    if not start_ts:
        return []
    kickoff = datetime.fromtimestamp(start_ts, UTC)

    home = event.get("homeTeam", {})
    away = event.get("awayTeam", {})
    home_id, away_id = home.get("id"), away.get("id")
    if home_id is None or away_id is None:
        return []

    want_incidents = any(m in NEEDS_INCIDENTS for m in metrics)
    actual_stats, actual_incidents = event_payloads(
        client, cache, int(event["id"]), want_incidents
    )
    actual_flat = extract_flat_statistics(actual_stats)
    if check_identities(actual_flat, actual_incidents, event, sport) is not None:
        return []

    history = team_history(client, cache, int(home_id)) + team_history(
        client, cache, int(away_id)
    )

    # Pre-fetch the payloads the sample will need, once per event.
    stats_by_event: dict[int, dict[str, Any] | None] = {}
    incidents_by_event: dict[int, dict[str, Any] | None] = {}
    for past in history:
        past_id = past.get("id")
        past_ts = past.get("startTimestamp")
        if past_id is None or not past_ts:
            continue
        if datetime.fromtimestamp(past_ts, UTC) >= kickoff:
            continue
        if not is_completed_event(past):
            continue
        if int(past_id) in stats_by_event:
            continue
        stats_by_event[int(past_id)], incidents_by_event[int(past_id)] = event_payloads(
            client, cache, int(past_id), want_incidents
        )

    rows: list[SettledRow] = []
    for metric in metrics:
        actual = extract_metric(
            metric, sport, actual_flat, actual_incidents, event, is_home=True
        )
        if not isinstance(actual, float):
            continue

        # A _total market is one sample per match: pool both sides' histories,
        # then deduplicate — a head-to-head sits in both and must count once (L13).
        pooled = historical_sample(
            history,
            before_utc=kickoff,
            entity_id=int(home_id),
            sport=sport,
            metric=metric,
            metrics_by_event=stats_by_event,
            incidents_by_event=incidents_by_event,
            sample_n=config.sample_n,
            excluded_competition_ids=FRIENDLY_COMPETITION_IDS,
            ground_type=event.get("groundType"),
            best_of=event.get("defaultPeriodCount"),
        ) + historical_sample(
            history,
            before_utc=kickoff,
            entity_id=int(away_id),
            sport=sport,
            metric=metric,
            metrics_by_event=stats_by_event,
            incidents_by_event=incidents_by_event,
            sample_n=config.sample_n,
            excluded_competition_ids=FRIENDLY_COMPETITION_IDS,
            ground_type=event.get("groundType"),
            best_of=event.get("defaultPeriodCount"),
        )
        seen_ids: set[int] = set()
        values: list[float] = []
        for past_id, value in pooled:
            if past_id in seen_ids:
                continue
            seen_ids.add(past_id)
            values.append(value)

        rows.extend(
            settle_metric(
                run_date=kickoff.strftime("%Y-%m-%d"),
                event=event,
                sport=sport,
                metric=metric,
                actual_value=actual,
                sample_values=values,
                min_sample=config.min_sample,
                k_centre=k_centre,
                k_price=k_price,
                # No league prior exists before E11 has run on this very data;
                # starting from the sample mean is the correct empty state.
                prior=None,
            )
        )
    return rows


def load_plan(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.plan:
        raw = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        return list(raw.get("targets", raw))
    leagues = [int(x) for x in args.leagues.split(",") if x.strip()]
    seasons = [int(x) for x in args.seasons.split(",") if x.strip()]
    return [
        {"unique_tournament_id": lg, "season_id": sn, "sport": args.sport}
        for lg in leagues
        for sn in seasons
    ]


def already_settled_event_ids(db_path: str) -> set[int]:
    """Events this backfill has already settled.

    The checkpoint is the settled table itself rather than a separate state
    file: a state file can disagree with reality, whereas a row in
    ``sofa_settled_row`` is the very thing the run exists to produce. A 3-hour
    backfill interrupted at hour 2 resumes instead of starting over.
    """
    with get_connection(db_path) as conn:
        return {
            int(row["sofascore_event_id"])
            for row in conn.execute(
                "SELECT DISTINCT sofascore_event_id FROM sofa_settled_row"
            )
        }


def main() -> int:
    # Every request underneath this call is this stage's cost (F22).
    set_stage("BACKFILL")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plan", help="JSON file of {unique_tournament_id, season_id, sport}"
    )
    parser.add_argument(
        "--leagues", default="", help="comma-separated uniqueTournament ids"
    )
    parser.add_argument("--seasons", default="", help="comma-separated season ids")
    parser.add_argument("--sport", default="football", choices=["football", "tennis"])
    parser.add_argument("--max-events", type=int, default=0, help="0 = no limit")
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="re-settle events that already have rows (default: skip them)",
    )
    parser.add_argument(
        "--report", default="docs/sofascore-api/evidence/e10_backfill.md"
    )
    args = parser.parse_args()

    targets = load_plan(args)
    if not targets:
        print(
            "No backfill targets given (--plan or --leagues/--seasons)", file=sys.stderr
        )
        return 2

    config = SofaConfig.from_env()
    migrate(config.db_path)
    client = SofascoreClient(config)
    cache = SofaCache(config)

    total_rows = 0
    per_league: dict[int, int] = defaultdict(int)
    months: set[str] = set()
    events_seen = 0
    failures = 0
    resumed = 0

    done_ids: set[int] = set() if args.no_resume else already_settled_event_ids(
        config.db_path
    )
    if done_ids:
        print(f"resuming: {len(done_ids)} events already settled", file=sys.stderr)

    for target in targets:
        ut_id = int(target["unique_tournament_id"])
        season_id = int(target["season_id"])
        sport = str(target.get("sport", args.sport))
        metrics = (
            FOOTBALL_BACKFILL_METRICS
            if sport == "football"
            else TENNIS_BACKFILL_METRICS
        )

        try:
            events = season_events(client, ut_id, season_id)
        except (ProviderError, CircuitOpenError) as exc:
            failures += 1
            print(f"league {ut_id} season {season_id}: {exc}", file=sys.stderr)
            continue

        for event in events:
            if args.max_events and events_seen >= args.max_events:
                break

            event_id = event.get("id")
            if event_id is not None and int(event_id) in done_ids:
                resumed += 1
                continue

            events_seen += 1
            try:
                rows = backfill_event(
                    client,
                    cache,
                    event,
                    sport,
                    metrics,
                    config,
                    k_centre=10.0,
                    k_price=10.0,
                )
            except (ProviderError, CircuitOpenError) as exc:
                failures += 1
                print(f"event {event.get('id')}: {exc}", file=sys.stderr)
                continue
            if not rows:
                continue
            with get_connection(config.db_path) as conn:
                total_rows += insert_settled_rows(conn, rows)
            per_league[ut_id] += len(rows)
            ts = event.get("startTimestamp")
            if ts:
                months.add(datetime.fromtimestamp(ts, UTC).strftime("%Y-%m"))

    with get_connection(config.db_path) as conn:
        db_rows = conn.execute("SELECT COUNT(*) AS c FROM sofa_settled_row").fetchone()[
            "c"
        ]
        db_leagues = conn.execute(
            "SELECT COUNT(DISTINCT competition_id) AS c FROM sofa_settled_row"
        ).fetchone()["c"]

    # AC of E10: >= 20 000 rows, >= 8 leagues, >= 3 calendar months.
    meets_ac = db_rows >= 20000 and db_leagues >= 8 and len(months) >= 3
    verdict = (
        "OK" if meets_ac and not failures else ("PARTIAL" if db_rows else "FAILED")
    )

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        "\n".join(
            [
                "# E10 Backfill",
                "",
                f"Run: {datetime.now(UTC).isoformat()}",
                f"Targets: {len(targets)} · events walked: {events_seen} · "
                f"provider failures: {failures}",
                "",
                f"- Rows written this run: **{total_rows}**",
                f"- Rows in `sofa_settled_row` total: **{db_rows}**",
                f"- Distinct competitions: **{db_leagues}**",
                f"- Calendar months covered this run: **{len(months)}** "
                f"({', '.join(sorted(months)) or 'none'})",
                "",
                f"AC (>=20000 rows, >=8 leagues, >=3 months): "
                f"**{'MET' if meets_ac else 'NOT MET'}**",
                "",
                "`market_p` is NULL on every row: there are no historical "
                "Superbet prices, so this data calibrates probability and says "
                "nothing about ROI (PLAN §A9).",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(
        "SOFA_SUMMARY: "
        + json.dumps(
            {
                "stage": "BACKFILL",
                "verdict": verdict,
                "metrics": {
                    "rows_written": total_rows,
                    "rows_total": db_rows,
                    "leagues": db_leagues,
                    "months": len(months),
                    "events": events_seen,
                    "events_skipped_already_settled": resumed,
                    "failures": failures,
                    "meets_ac": meets_ac,
                },
                "output_path": str(report_path),
            }
        )
    )
    return 0 if verdict == "OK" else (1 if verdict == "PARTIAL" else 2)


if __name__ == "__main__":
    sys.exit(main())
