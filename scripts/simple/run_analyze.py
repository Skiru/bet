#!/usr/bin/env python3
"""ANALYZE: STATS_SHEET_V1 hit-rate rows from an EVENT_DOSSIER_V1[] artifact.

Usage:
    python3 scripts/simple/run_analyze.py --dossier PATH --output-dir PATH [-v]

Pure computation over the ENRICH artifact -- no network calls, so no quota
preflight. Emits the repo-standard AGENT_SUMMARY:{json} contract via
scripts/agent_output.py.

Exit codes: 0 = OK, 1 = PARTIAL, 2 = FAILED.
"""
import argparse
import sys
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
src_path = str(ROOT / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)
scripts_path = str(ROOT / "scripts")
if scripts_path not in sys.path:
    sys.path.insert(0, scripts_path)

from agent_output import AgentOutput, add_agent_args  # noqa: E402

from bet.db.connection import get_db  # noqa: E402
from bet.simple_stats.analyze import analyze_dossiers, limit_rows_per_event  # noqa: E402
from bet.simple_stats.artifact_io import sha256_file, write_json_atomic  # noqa: E402
from bet.simple_stats.contracts import (  # noqa: E402
    EventDossierListV1,
    MarketContextV1,
    StatsSheetV1,
    SuperbetOfferV1,
    TipsterSignalV1,
)
from bet.simple_stats.coupons import MIN_SINGLE_P_LOW  # noqa: E402
from bet.simple_stats.market_context import attach_market_context_column  # noqa: E402
from bet.simple_stats.superbet_offer import attach_superbet_column  # noqa: E402
from bet.simple_stats.persistence import (  # noqa: E402
    default_db_path,
    fixture_ids_by_event_id,
    persist_stats_sheet,
)
from bet.simple_stats.run_context import record_run  # noqa: E402
from bet.simple_stats.tipster_signal import attach_tipster_column  # noqa: E402

STEP = "simple_stats:ANALYZE"


def main() -> None:
    parser = argparse.ArgumentParser(description="ANALYZE: simple_stats stats sheet")
    parser.add_argument("--dossier", required=True, help="Path to EVENT_DOSSIER_V1[] JSON (from run_enrich.py)")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--db-path", default=None, help=f"SQLite DB to persist into (default: {default_db_path()})"
    )
    parser.add_argument(
        "--market-context",
        default=None,
        help="Optional MARKET_CONTEXT_V1 from run_market_context.py. Fills "
             "row.market_signal and nothing else -- a bookmaker price and a "
             "model probability are reported beside the statistics, never mixed "
             "into them.",
    )
    parser.add_argument(
        "--superbet-offer",
        default=None,
        help="Optional SUPERBET_OFFER_V1 from run_superbet.py. Fills the "
             "`superbet` column: the price on the operator's own book, and -- "
             "more importantly -- whether the line is on it at all. Absent, "
             "every row's column stays None and the sheet is unchanged.",
    )
    parser.add_argument(
        "--tipster-signal",
        default=None,
        help="Optional TIPSTER_SIGNAL_V1 from run_tipsters.py. Fills row.tipster "
             "and nothing else -- public agreement is reported beside the "
             "statistics, never mixed into them.",
    )
    parser.add_argument(
        "--max-rows-per-event",
        type=int,
        default=None,
        help="Cap stats-sheet rows kept per event, strongest p_low first "
             "(default: unlimited). Faza 2 sizing guard against the sheet "
             "outgrowing the analyst's context window as market coverage grows.",
    )
    add_agent_args(parser)
    args = parser.parse_args()

    out = AgentOutput(STEP, verbose=args.verbose, stop_on_error=args.stop_on_error)
    started_at = datetime.now(timezone.utc).isoformat()

    dossier_path = Path(args.dossier)
    dossier_list = EventDossierListV1.model_validate_json(dossier_path.read_text(encoding="utf-8"))
    run_id = dossier_list.run_id or "unknown"
    # EVENT_DOSSIER_V1 now carries its own date; the filename convention is
    # only a fallback for artifacts written before that field existed.
    betting_date = dossier_list.date or dossier_path.stem.replace("_event_dossiers", "")
    out.event("run_start", run_id=run_id, date=betting_date, dossiers=len(dossier_list.dossiers))

    try:
        stats_sheet = analyze_dossiers(dossier_list)
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        out.error(f"analysis crashed: {exc}", recoverable=False, run_id=run_id)
        _record(args, run_id, betting_date, "FAILED", {"error": str(exc)}, started_at, str(exc))
        out.summary(verdict="FAILED", metrics={"total_rows": 0, "run_id": run_id})
        sys.exit(2)

    if args.max_rows_per_event is not None:
        pre_cap = len(stats_sheet.rows)
        capped_rows = limit_rows_per_event(stats_sheet.rows, args.max_rows_per_event)
        stats_sheet = StatsSheetV1(
            run_id=stats_sheet.run_id,
            date=stats_sheet.date,
            generated_at=stats_sheet.generated_at,
            rows=capped_rows,
        )
        out.event(
            "rows_capped_per_event",
            max_rows_per_event=args.max_rows_per_event,
            rows_before=pre_cap,
            rows_after=len(stats_sheet.rows),
        )

    # Both optional columns are attached after every statistic is computed, so
    # the numbers above cannot depend on either even by accident. A missing or
    # unreadable file leaves that column at None on every row; the sheet is
    # still a complete sheet.
    market_metrics: dict = {"market_context": None}
    if args.market_context:
        context_path = Path(args.market_context)
        context = None
        try:
            context = MarketContextV1.model_validate_json(context_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            out.warning(
                f"market context unusable, continuing without the column: {exc}",
                path=str(context_path),
            )
            market_metrics["market_context_error"] = str(exc)

        # Yesterday's prices attached to today's rows is the worst failure this
        # column has available: a stale quote looks exactly like a live one, and
        # a model read for a match already played is not a forecast. Same guard
        # the tipster column carries, and for the same reason -- --start-at
        # analyze with a hand-passed path is precisely how it would happen.
        if context is not None and context.date and context.date != betting_date:
            out.error(
                f"market context is for {context.date}, not {betting_date} -- refusing to attach it",
                recoverable=True,
                path=str(context_path),
            )
            market_metrics["market_context_error"] = f"date_mismatch:{context.date}!={betting_date}"
            context = None

        if context is not None:
            stats_sheet = attach_market_context_column(stats_sheet, context)
            signalled = [r for r in stats_sheet.rows if r.market_signal]
            with_verdict = [r for r in signalled if r.market_signal.verdict != "NO_MARKET_DATA"]
            market_metrics = {
                "market_context": str(context_path),
                "market_rows_in_scope": len(signalled),
                "market_rows_with_verdict": len(with_verdict),
                "market_confirms": sum(1 for r in with_verdict if r.market_signal.verdict == "CONFIRMS"),
                "market_contradicts": sum(1 for r in with_verdict if r.market_signal.verdict == "CONTRADICTS"),
                "market_split": sum(1 for r in with_verdict if r.market_signal.verdict == "SPLIT"),
                "football_unlimited_entitled": context.football_unlimited_entitled,
            }
            out.event(
                "market_signal_column_attached",
                rows_in_scope=len(signalled),
                rows_with_verdict=len(with_verdict),
                events_covered=len(context.events),
            )

    tipster_metrics: dict = {"tipster_signal": None}
    if args.tipster_signal:
        signal_path = Path(args.tipster_signal)
        signal = None
        try:
            signal = TipsterSignalV1.model_validate_json(signal_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            out.warning(f"tipster signal unusable, continuing without the column: {exc}", path=str(signal_path))
            tipster_metrics["tipster_signal_error"] = str(exc)

        # A signal for another day must never attach. run_pipeline.py names the
        # file per date so this should not happen, but --start-at analyze with a
        # hand-passed path is exactly how it would, and yesterday's opinions
        # silently labelled as today's is the worst failure available to this
        # column.
        if signal is not None and signal.date and signal.date != betting_date:
            out.error(
                f"tipster signal is for {signal.date}, not {betting_date} -- refusing to attach it",
                recoverable=True,
                path=str(signal_path),
            )
            tipster_metrics["tipster_signal_error"] = f"date_mismatch:{signal.date}!={betting_date}"
            signal = None

        if signal is not None:
            stats_sheet = attach_tipster_column(stats_sheet, signal)
            covered = sum(1 for r in stats_sheet.rows if r.tipster and r.tipster.verdict != "NO_COVERAGE")
            tipster_metrics = {
                "tipster_signal": str(signal_path),
                "tipster_rows_with_opinion": covered,
                "tipster_events_covered": len(signal.events),
                "tipster_countable_claims": signal.countable_claims,
            }
            out.event(
                "tipster_column_attached",
                rows_with_opinion=covered,
                events_covered=len(signal.events),
                countable_claims=signal.countable_claims,
            )

    # The operator's own book. Third and last of the optional columns, and the
    # only one that can say "this line is not on the screen" -- the other two
    # can only ever disagree about a price for a bet that exists.
    superbet_metrics: dict = {"superbet_offer": None}
    if args.superbet_offer:
        offer_path = Path(args.superbet_offer)
        offer = None
        try:
            offer = SuperbetOfferV1.model_validate_json(offer_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            out.warning(
                f"superbet offer unusable, continuing without the column: {exc}",
                path=str(offer_path),
            )
            superbet_metrics["superbet_offer_error"] = str(exc)

        # Same date guard the other two columns carry, and it matters more here:
        # yesterday's price for a market that has since been re-laddered looks
        # exactly like today's, and the operator bets from it.
        if offer is not None and offer.date and offer.date != betting_date:
            out.error(
                f"superbet offer is for {offer.date}, not {betting_date} -- refusing to attach it",
                recoverable=True,
                path=str(offer_path),
            )
            superbet_metrics["superbet_offer_error"] = f"date_mismatch:{offer.date}!={betting_date}"
            offer = None

        if offer is not None:
            stats_sheet = attach_superbet_column(stats_sheet, offer)
            availability: dict[str, int] = {}
            for row in stats_sheet.rows:
                if row.superbet is None:
                    continue
                availability[row.superbet.availability] = (
                    availability.get(row.superbet.availability, 0) + 1
                )
            superbet_metrics = {
                "superbet_offer": str(offer_path),
                "superbet_events_matched": offer.events_matched,
                "superbet_rows_offered": availability.get("OFFERED", 0),
                "superbet_rows_line_not_offered": availability.get("LINE_NOT_OFFERED", 0),
                "superbet_rows_market_not_offered": availability.get("MARKET_NOT_OFFERED", 0),
                "superbet_rows_event_not_matched": availability.get("EVENT_NOT_MATCHED", 0),
                "superbet_rows_suspended": availability.get("SUSPENDED", 0),
            }
            out.event("superbet_column_attached", **{
                key: value for key, value in superbet_metrics.items() if key != "superbet_offer"
            })
            if not availability.get("OFFERED"):
                out.warning(
                    "not one row on this sheet is on Superbet at its own line. Check "
                    "the offer artifact's line_coverage before reading any p_low as a bet."
                )

    output_path = Path(args.output_dir) / f"{dossier_path.stem}_stats_sheet.json"
    write_json_atomic(output_path, stats_sheet.model_dump(mode="json"))
    digest = sha256_file(output_path)
    out.event("artifact_written", path=str(output_path), sha256=digest, rows=len(stats_sheet.rows))

    # Faza 2 sizing guard: the full sheet stays on disk for audit, but the
    # analyst reads this slim companion -- same rows minus everything below
    # the coupon's own p_low floor, which build_coupons.py would drop anyway.
    top_rows = [row for row in stats_sheet.rows if row.p_low >= MIN_SINGLE_P_LOW]
    top_sheet = StatsSheetV1(
        run_id=stats_sheet.run_id,
        date=stats_sheet.date,
        generated_at=stats_sheet.generated_at,
        rows=top_rows,
    )
    top_path = Path(args.output_dir) / f"{dossier_path.stem}_stats_sheet_top.json"
    write_json_atomic(top_path, top_sheet.model_dump(mode="json"))
    top_digest = sha256_file(top_path)
    out.event("top_artifact_written", path=str(top_path), sha256=top_digest, rows=len(top_rows))

    rows = stats_sheet.rows
    by_confidence = dict(Counter(row.confidence for row in rows))
    by_agreement = dict(Counter(row.cross_provider_agreement for row in rows))
    by_market = dict(Counter(row.market for row in rows))
    corroborated = sum(1 for row in rows if len(row.sources) > 1)

    if args.verbose:
        for index, row in enumerate(rows[:50], start=1):
            out.candidate(
                row.event_id[:12],
                row.sport,
                market=row.market,
                line=row.line,
                direction=row.direction,
                hit_rate=round(row.hit_rate, 3),
                sample_size=row.sample_size,
                confidence=row.confidence,
                agreement=row.cross_provider_agreement,
            )

    persisted, persist_error = _persist(out, args, stats_sheet, betting_date)

    metrics = {
        "run_id": run_id,
        "date": betting_date,
        "total_rows": len(rows),
        "events_covered": len({row.event_id for row in rows}),
        "rows_by_confidence": by_confidence,
        "rows_by_agreement": by_agreement,
        "rows_by_market": by_market,
        "multi_source_rows": corroborated,
        "output_path": str(output_path),
        "output_sha256": digest,
        "top_output_path": str(top_path),
        "top_output_sha256": top_digest,
        "top_rows": len(top_rows),
        "persisted": persisted,
        "persist_error": persist_error,
        **market_metrics,
        **tipster_metrics,
        **superbet_metrics,
    }

    if not rows:
        out.error("no stats-sheet rows produced: every dossier was BLOCKED or had no market data", recoverable=False)
        verdict = "FAILED"
    elif not corroborated or not persisted:
        # Rows exist and are usable, but nothing was corroborated by a second
        # provider (or the DB write failed) -- worth a human's attention, so
        # not a clean OK.
        if not corroborated:
            out.warning("no row is backed by more than one provider", multi_source_rows=0)
        verdict = "PARTIAL"
    else:
        verdict = "OK"

    _record(args, run_id, betting_date, verdict, metrics, started_at, persist_error)
    out.summary(verdict=verdict, metrics=metrics)
    sys.exit(0 if verdict == "OK" else (1 if verdict == "PARTIAL" else 2))


def _persist(out: AgentOutput, args, stats_sheet, betting_date: str) -> tuple[bool, str | None]:
    try:
        with get_db(args.db_path or default_db_path()) as conn:
            fixture_ids = fixture_ids_by_event_id(conn, {row.event_id for row in stats_sheet.rows})
            persist_stats_sheet(stats_sheet, fixture_ids, betting_date, conn)
        out.event("db_persisted", table="analysis_results", events=len(fixture_ids))
        return True, None
    except Exception as exc:
        out.error(f"DB persistence failed: {exc}", recoverable=True)
        return False, str(exc)


def _record(args, run_id: str, date: str, status: str, stats: dict, started_at: str, error: str | None) -> None:
    try:
        record_run(
            date=date,
            step="ANALYZE",
            status=status,
            run_id=run_id,
            db_path=args.db_path,
            stats=stats,
            error_message=error,
            started_at=started_at,
        )
    except Exception as exc:  # noqa: BLE001 - bookkeeping must never mask the run's own result
        print(f"[{STEP}] WARNING: could not record pipeline_runs row: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
