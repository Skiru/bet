"""MARKET COVERAGE - label every Superbet market OFFER could not read (plan F1.1).

Read-only over the day's artifacts: `01_board.json`, `02_fixtures.json` and
`04_offer.json`. No client, no bridge, no database. It changes nothing OFFER
maps or the coupon selects; it writes a report:

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/report_market_coverage.py \
        --date 2026-10-05

by default to runs/sofa/<d>/market_coverage.json and .md (``--out-json`` /
``--out-md`` elsewhere). The method is in `bet.sofa.market_coverage`.

``--sports`` adds the measured sports (hockey, basketball, volleyball, CS2;
night plan 2026-10-12 C5) to runs/sofa/<d>/market_coverage_sports.json and
.md. SHADOW and CS2 record only the lines they read, so their unread market
names come from the raw Superbet payloads: ``--sports-raw-dir <dir>`` reads
saved payloads (``*.json``, one event each, with Superbet's ``sportId``),
otherwise the offer is asked live (Superbet only, no bridge: one listing call
and up to ``--sports-max-events`` event calls per sport, pre-match events of
the day - a finished match has no offer left). The day's snapshots.jsonl are
summarised beside it. ``--sports-only`` skips the football / tennis report.
Nothing the pipeline reads is written or changed.

Exit: 0 OK (every unmapped name has a label), 1 PARTIAL (some names are
UNCLASSIFIED - a rule is missing; they are listed), 2 FAILED (an artifact is
missing or unreadable).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (str(_REPO_ROOT), str(_REPO_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.market_coverage import (  # noqa: E402
    MEASURED_SPORTS,
    build_report,
    build_sports_report,
    render_markdown,
    render_sports_markdown,
    snapshot_inventory,
    sport_payload_names,
)

STAGE = "MARKET_COVERAGE"
# Superbet sportId of each measured sport (shadow.SPORTS, cs2.SUPERBET_CS2_SPORT_ID).
SPORT_BY_SUPERBET_ID = {3: "hockey", 4: "basketball", 1: "volleyball", 55: "cs2"}


def _load(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", required=True)
    ap.add_argument("--runs-dir", default=None, help="default: SofaConfig runs_dir")
    ap.add_argument("--out-json", default=None)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--sports", action="store_true",
                    help="also inventory the measured sports' unread markets")
    ap.add_argument("--sports-only", action="store_true",
                    help="only the measured sports (implies --sports)")
    ap.add_argument("--sports-raw-dir", default=None,
                    help="saved raw Superbet event payloads instead of a live probe")
    ap.add_argument("--sports-max-events", type=int, default=40,
                    help="live probe: events asked per sport (default 40)")
    ap.add_argument("--sports-out-dir", default=None,
                    help="where market_coverage_sports.* go (default: the day's dir)")
    args = ap.parse_args(argv)

    runs_dir = Path(args.runs_dir or SofaConfig.from_env().runs_dir)
    day = runs_dir / args.date
    if args.sports or args.sports_only:
        rc = _sports(args, runs_dir, day)
        if args.sports_only or rc == 2:
            return rc
    try:
        board = _load(day / "01_board.json")
        fixtures = _load(day / "02_fixtures.json")
        offers = _load(day / "04_offer.json")
    except (OSError, ValueError) as exc:
        print(f"{STAGE}: FAILED - {exc}", file=sys.stderr)
        failed = {"stage": STAGE, "verdict": "FAILED", "error": str(exc)}
        print("SOFA_SUMMARY: " + json.dumps(failed))
        return 2

    report = build_report(offers, fixtures, board, date=args.date)
    # Every OFFER refresh rewrites 04_offer.json: say which bytes this report
    # describes.
    report["inputs"] = {}
    for name in ("01_board.json", "02_fixtures.json", "04_offer.json"):
        path = day / name
        mtime = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        report["inputs"][name] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "mtime_utc": mtime.isoformat(timespec="seconds"),
        }
    out_json = Path(args.out_json) if args.out_json else day / "market_coverage.json"
    out_md = Path(args.out_md) if args.out_md else day / "market_coverage.md"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    out_md.write_text(render_markdown(report), encoding="utf-8")

    unclassified = report["by_label"]["UNCLASSIFIED"]
    verdict = "OK" if unclassified["occurrences"] == 0 else "PARTIAL"
    metrics = {
        "fixtures": report["fixtures"],
        "mapped_instances": report["mapped"]["instances"],
        "unmapped_occurrences": report["unmapped"]["occurrences"],
        "unmapped_distinct_names": report["unmapped"]["distinct_names"],
        **{
            f"{lab.lower()}_occurrences": v["occurrences"]
            for lab, v in report["by_label"].items()
        },
        **{
            f"{lab.lower()}_distinct_names": v["distinct_names"]
            for lab, v in report["by_label"].items()
        },
    }
    summary: dict[str, Any] = {
        "stage": STAGE,
        "verdict": verdict,
        "metrics": metrics,
        "output_path": str(out_json),
    }
    print("SOFA_SUMMARY: " + json.dumps(summary))
    return 0 if verdict == "OK" else 1


def _sport_of(payload: dict[str, Any]) -> str | None:
    try:
        return SPORT_BY_SUPERBET_ID.get(int(payload.get("sportId") or 0))
    except (TypeError, ValueError):
        return None


def _saved_payloads(raw_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted(raw_dir.glob("*.json")):
        payload = _load(path)
        if isinstance(payload, dict) and _sport_of(payload):
            out.append(payload)
    return out


def _live_payloads(date: str, max_events: int) -> tuple[list[dict[str, Any]], int]:
    """Pre-match payloads of the day's measured-sport events, asked live
    (Superbet only); returns (payloads, events that failed)."""
    import time
    from datetime import timedelta

    from bet.sofa.superbet import SuperbetClient

    client = SuperbetClient()
    start = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
    rows = client.events_by_date(
        start, start + timedelta(days=1), offer_state="prematch")
    taken: dict[str, int] = {}
    out: list[dict[str, Any]] = []
    failed = 0
    for row in rows:
        sport = _sport_of(row)
        if sport is None or taken.get(sport, 0) >= max_events:
            continue
        try:
            payload = client.event_odds(row["eventId"])
        except Exception:  # noqa: BLE001 - one event, not the report
            failed += 1
            if client.breaker_tripped:
                break
            continue
        taken[sport] = taken.get(sport, 0) + 1
        if payload:
            out.append(payload)
        time.sleep(0.3)
    return out, failed


def _snapshot_file(runs_dir: Path, sport: str, date: str) -> Path:
    if sport == "cs2":
        return runs_dir / "cs2" / date / "snapshots.jsonl"
    return runs_dir / "shadow" / sport / date / "snapshots.jsonl"


def _sports(args: argparse.Namespace, runs_dir: Path, day: Path) -> int:
    failed = 0
    try:
        if args.sports_raw_dir:
            payloads = _saved_payloads(Path(args.sports_raw_dir))
            source = f"zapisane payloady: {args.sports_raw_dir}"
        else:
            payloads, failed = _live_payloads(args.date, args.sports_max_events)
            source = (f"próba oferty Superbetu na żywo "
                      f"{datetime.now(UTC).isoformat(timespec='seconds')}, "
                      f"do {args.sports_max_events} meczów na sport")
    except (OSError, ValueError) as exc:
        print(f"{STAGE}_SPORTS: FAILED - {exc}", file=sys.stderr)
        print("SOFA_SUMMARY: " + json.dumps(
            {"stage": f"{STAGE}_SPORTS", "verdict": "FAILED", "error": str(exc)}))
        return 2

    events: list[dict[str, Any]] = []
    for payload in payloads:
        sport = _sport_of(payload)
        if sport is None:
            continue
        (team1, team2), read, unread = sport_payload_names(payload, sport)
        if not read and not unread:
            continue  # no pre-match offer left
        events.append({"sport": sport, "superbet_event_id": str(payload.get("eventId")),
                       "team1": team1, "team2": team2, "read": read, "unread": unread})

    snapshots: dict[str, Any] = {}
    for sport in MEASURED_SPORTS:
        path = _snapshot_file(runs_dir, sport, args.date)
        if path.exists():
            with path.open(encoding="utf-8") as fh:
                snapshots[sport] = snapshot_inventory(
                    json.loads(line) for line in fh if line.strip())

    report = build_sports_report(
        events, date=args.date, snapshots=snapshots, source=source)
    report["probe_failures"] = failed
    out_dir = Path(args.sports_out_dir) if args.sports_out_dir else day
    out_json = out_dir / "market_coverage_sports.json"
    out_md = out_dir / "market_coverage_sports.md"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    out_md.write_text(render_sports_markdown(report), encoding="utf-8")

    unclassified = report["by_label"]["UNCLASSIFIED"]["occurrences"]
    verdict = "OK" if events and unclassified == 0 and not failed else "PARTIAL"
    print("SOFA_SUMMARY: " + json.dumps({
        "stage": f"{STAGE}_SPORTS",
        "verdict": verdict,
        "metrics": {
            "probed_events": report["probed_events"],
            "unread_names": report["unread_names"],
            "probe_failures": failed,
            **{f"{lab.lower()}_occurrences": v["occurrences"]
               for lab, v in report["by_label"].items()},
        },
        "output_path": str(out_json),
    }))
    return 0 if verdict == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
