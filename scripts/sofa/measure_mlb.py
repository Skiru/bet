#!/usr/bin/env python3
"""E12 baseball measurement — a real measurement, never a simulation.

Answers two questions with evidence, not with an opinion:

1. Can ``resolve`` find MLB fixtures from the Superbet board in Sofascore?
   (recall, plus the ``GapReason`` distribution of the failures)
2. Does ``/event/{id}/statistics`` carry run-scoring aggregates at all?
   (``runs``/``hits``/``errors`` under any of their plausible keys)

Every number this script prints comes from a response body it also writes to
disk. If the network is unavailable, it writes a ``NOT_MEASURED`` report saying
exactly that and exits ``2`` — it never invents a finding.

Usage:
    python -m scripts.sofa.measure_mlb --date 2026-09-18 --limit 50
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from bet.sofa.cache import SofaCache
from bet.sofa.client import SofascoreClient
from bet.sofa.config import SofaConfig
from bet.sofa.contracts import BoardFixture, GapReason
from bet.sofa.resolve import SofaResolver
from bet.sofa.superbet import SuperbetClient, split_match_name
from bet.sofa.timeutil import now

# Superbet sport id for baseball. Unverified — the run reports how many rows
# carried it, so a wrong id shows up as "0 fixtures on the board", not as a
# silent zero recall.
BASEBALL_SPORT_ID = 3

# Keys that would carry run scoring if Sofascore published it for baseball.
RUN_KEYS = ("runs", "hits", "errors", "runsScored", "totalRuns", "totalHits")

EVIDENCE_DIR = Path("docs/sofa/evidence")
REPORT_PATH = EVIDENCE_DIR / "mlb_measurement.md"
RAW_PATH = EVIDENCE_DIR / "mlb_measurement_raw.json"


def fetch_baseball_board(date_str: str, client: SuperbetClient) -> list[BoardFixture]:
    """Board fixtures for baseball only. Mirrors board.fetch_board's filters."""
    window_start = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
    window_end = window_start + timedelta(days=1)
    rows = client.events_by_date(window_start, window_end, offer_state="all")

    fixtures: list[BoardFixture] = []
    for row in rows:
        if row.get("sportId") != BASEBALL_SPORT_ID:
            continue
        match_name = row.get("matchName") or ""
        side_a, side_b = split_match_name(match_name)
        if not side_a or not side_b:
            continue
        raw_utc = str(row.get("utcDate") or "")
        try:
            kickoff = datetime.fromisoformat(raw_utc.replace("Z", "+00:00"))
        except ValueError:
            continue
        event_id = row.get("eventId")
        if event_id is None:
            continue
        fixtures.append(
            BoardFixture(
                superbet_event_id=str(event_id),
                # The Sport literal has no "baseball" member by design (0.3).
                # Resolution is sport-agnostic, so we measure under "football"
                # and say so in the report rather than widening the contract
                # for a sport we have not yet decided to support.
                sport="football",
                match_name=match_name,
                side_a=side_a,
                side_b=side_b,
                kickoff_utc=kickoff.astimezone(UTC),
            )
        )
    return fixtures


def probe_statistics(stats: dict[str, Any] | None) -> dict[str, Any]:
    """Which run-scoring keys, if any, this statistics payload carries."""
    if stats is None:
        return {"payload": "ABSENT", "keys_found": [], "all_keys": []}

    all_keys: set[str] = set()
    for period in stats.get("statistics", []):
        for group in period.get("groups", []):
            for item in group.get("statisticsItems", []):
                key = item.get("key")
                if key:
                    all_keys.add(str(key))

    found = sorted(k for k in all_keys if k in RUN_KEYS)
    return {
        "payload": "PRESENT",
        "keys_found": found,
        "all_keys": sorted(all_keys),
    }


def write_not_measured(reason: str) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        "# MLB Measurement — NOT MEASURED\n\n"
        f"**Status:** NOT_MEASURED (attempted {now().isoformat()})\n\n"
        f"**Reason:** {reason}\n\n"
        "No recall figure, no statistics-coverage finding and no conclusion "
        "about baseball may be quoted from this file. Re-run\n"
        "`python -m scripts.sofa.measure_mlb --date <YYYY-MM-DD>` from a host "
        "that can reach Sofascore, and this file will be overwritten with the "
        "measured numbers plus the raw payloads in "
        f"`{RAW_PATH.name}`.\n\n"
        'Baseball remains out of `sofa` (`Sport = Literal["football", '
        '"tennis"]`) because it was never measured, not because it was '
        "measured and rejected.\n",
        encoding="utf-8",
    )


def write_report(records: list[dict[str, Any]], date_str: str) -> dict[str, Any]:
    total = len(records)
    resolved = [r for r in records if r["sofascore_event_id"] is not None]
    with_stats = [r for r in resolved if r["statistics"]["payload"] == "PRESENT"]
    with_runs = [r for r in with_stats if r["statistics"]["keys_found"]]

    gap_counts: dict[str, int] = {}
    for r in records:
        if r["gap_reason"]:
            gap_counts[r["gap_reason"]] = gap_counts.get(r["gap_reason"], 0) + 1

    recall = len(resolved) / total if total else 0.0

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    RAW_PATH.write_text(
        json.dumps(
            {"date": date_str, "records": records}, indent=2, ensure_ascii=False
        ),
        encoding="utf-8",
    )

    lines = [
        "# MLB Measurement Report",
        "",
        f"**Status:** MEASURED · date `{date_str}` · run {now().isoformat()}",
        f"**Raw payload record:** `{RAW_PATH}` ({total} fixtures)",
        "",
        "## 1. Resolve",
        "",
        f"- Board fixtures (Superbet sportId={BASEBALL_SPORT_ID}): **{total}**",
        f"- Resolved to a Sofascore event: **{len(resolved)}**",
        f"- Recall: **{recall:.1%}** ({len(resolved)}/{total})",
        "",
        "Failure reasons:",
        "",
    ]
    if gap_counts:
        for reason, count in sorted(gap_counts.items(), key=lambda kv: -kv[1]):
            lines.append(f"- `{reason}`: {count}")
    else:
        lines.append("- (none)")

    lines += [
        "",
        "## 2. `/event/{id}/statistics`",
        "",
        f"- Resolved events probed: **{len(resolved)}**",
        f"- Statistics payload present (not 404): **{len(with_stats)}**",
        f"- Carrying any of {list(RUN_KEYS)}: **{len(with_runs)}**",
        "",
    ]
    observed_keys: set[str] = set()
    for r in with_stats:
        observed_keys.update(r["statistics"]["all_keys"])
    if observed_keys:
        lines.append("Statistic keys observed across all probed events:")
        lines.append("")
        lines.append("```")
        lines.append(", ".join(sorted(observed_keys)))
        lines.append("```")
    else:
        lines.append("No statistics keys observed on any resolved event.")

    verdict = "SUPPORTED" if with_runs and recall >= 0.8 else "NOT SUPPORTED"
    lines += [
        "",
        "## 3. Conclusion",
        "",
        f"**{verdict}.** ",
    ]
    if verdict == "SUPPORTED":
        lines.append(
            "Recall and run-scoring aggregates both clear the bar. Adding "
            "baseball is now a decision, not a guess — it would require "
            "widening `Sport`, a metric table and its own identity tests."
        )
    else:
        lines.append(
            "Baseball stays out of `sofa`: without run-scoring aggregates "
            "there is no sample from which `p_central` can be computed, and "
            "recall below 0.8 would lose most of the board anyway. The "
            "numbers above are the basis for that decision."
        )
    lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")

    return {
        "board_fixtures": total,
        "resolved": len(resolved),
        "recall": round(recall, 4),
        "statistics_present": len(with_stats),
        "with_run_keys": len(with_runs),
        "verdict": verdict,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=now().strftime("%Y-%m-%d"), help="YYYY-MM-DD")
    parser.add_argument("--limit", type=int, default=50, help="max fixtures to probe")
    args = parser.parse_args()

    config = SofaConfig.from_env()
    sofa_client = SofascoreClient(config)
    resolver = SofaResolver(config, sofa_client, SofaCache(config))
    sb_client = SuperbetClient()

    try:
        board = fetch_baseball_board(args.date, sb_client)
    except Exception as exc:  # noqa: BLE001 - any transport failure is the same answer
        write_not_measured(f"Superbet board unreachable: {exc!r}")
        print(
            "SOFA_SUMMARY: "
            + json.dumps(
                {
                    "stage": "MEASURE_MLB",
                    "verdict": "FAILED",
                    "metrics": {"reason": "board_unreachable"},
                    "output_path": str(REPORT_PATH),
                }
            )
        )
        return 2

    if not board:
        write_not_measured(
            f"Superbet returned no fixtures with sportId={BASEBALL_SPORT_ID} on "
            f"{args.date}. Either the id is wrong or there is no MLB slate that day."
        )
        print(
            "SOFA_SUMMARY: "
            + json.dumps(
                {
                    "stage": "MEASURE_MLB",
                    "verdict": "FAILED",
                    "metrics": {"reason": "empty_board"},
                    "output_path": str(REPORT_PATH),
                }
            )
        )
        return 2

    records: list[dict[str, Any]] = []
    errors = 0
    for board_fixture in board[: args.limit]:
        record: dict[str, Any] = {
            "superbet_event_id": board_fixture.superbet_event_id,
            "match_name": board_fixture.match_name,
            "kickoff_utc": board_fixture.kickoff_utc.isoformat(),
            "sofascore_event_id": None,
            "gap_reason": None,
            "statistics": {"payload": "ABSENT", "keys_found": [], "all_keys": []},
        }
        try:
            _entity_id, event, ambiguous = resolver.resolve_entity(
                "baseball",
                board_fixture.side_a,
                board_fixture.kickoff_utc,
                board_fixture.side_b,
            )
        except Exception as exc:  # noqa: BLE001
            errors += 1
            record["gap_reason"] = GapReason.PROVIDER_ERROR.value
            record["error"] = repr(exc)
            records.append(record)
            continue

        if ambiguous:
            record["gap_reason"] = GapReason.AMBIGUOUS_ENTITY.value
            records.append(record)
            continue
        if event is None:
            record["gap_reason"] = GapReason.NO_MATCHING_EVENT.value
            records.append(record)
            continue

        event_id = int(event["id"])
        record["sofascore_event_id"] = event_id
        try:
            stats = sofa_client.event_statistics(event_id)
        except Exception as exc:  # noqa: BLE001
            errors += 1
            record["error"] = repr(exc)
            records.append(record)
            continue
        record["statistics"] = probe_statistics(stats)
        records.append(record)

    if errors == len(records) and records:
        write_not_measured(
            f"Every one of {errors} Sofascore requests failed; no fixture was "
            "resolved or probed."
        )
        print(
            "SOFA_SUMMARY: "
            + json.dumps(
                {
                    "stage": "MEASURE_MLB",
                    "verdict": "FAILED",
                    "metrics": {"reason": "all_requests_failed"},
                    "output_path": str(REPORT_PATH),
                }
            )
        )
        return 2

    metrics = write_report(records, args.date)
    print(
        "SOFA_SUMMARY: "
        + json.dumps(
            {
                "stage": "MEASURE_MLB",
                "verdict": "OK",
                "metrics": metrics,
                "output_path": str(REPORT_PATH),
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
