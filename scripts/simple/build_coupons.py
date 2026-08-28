#!/usr/bin/env python3
"""Write one betting day's coupons: singles + Bet Builder slips, ranked.

Usage:
    python3 scripts/simple/build_coupons.py --date 2026-08-29
    python3 scripts/simple/build_coupons.py --stats-sheet PATH --event-list PATH \
        --output runs/2026-08-29/2026-08-29_kupony.md

Reads the finished artifacts, writes `<date>_kupony.md` (the operator's file)
and `<date>_coupons.json` (the machine-readable one). No network, no DB, no
provider calls -- so it is safe to re-run as often as you like.

**Prints no combined price and cannot be made to.** Corners, cards, fouls and
shots in one match are strongly positively correlated, so multiplying the legs
understates the slip's real probability in the direction that flatters the bet.
Read the combined price off Superbet's own screen.

Exit codes: 0 = coupons written, 1 = nothing cleared the bar, 2 = bad input.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from bet.simple_stats.artifact_io import write_json_atomic  # noqa: E402
from bet.simple_stats.contracts import EventListV1, StatsSheetV1  # noqa: E402
from bet.simple_stats.bet_builder_draft import (  # noqa: E402
    _CORRELATED_FOOTBALL_FAMILY as _CORRELATED_MARKETS,
)
from bet.simple_stats.coupons import CouponSet, build_coupons, market_label  # noqa: E402


def _kickoff(iso: str) -> str:
    return iso[11:16] if len(iso) >= 16 else ""


def render_markdown(coupons: CouponSet) -> str:
    """The operator's file. Polish, because that is who reads it."""
    out: list[str] = []
    a = out.append

    a(f"# Kupony {coupons.date}")
    a("")
    a(f"**Run:** `{coupons.run_id}` · **Wygenerowano:** {coupons.generated_at[:19]}Z")
    a(
        f"**Podstawa:** {coupons.rows_considered} wierszy / "
        f"{coupons.events_considered} meczów · "
        f"**{len(coupons.singles)} singli**, **{len(coupons.slips)} kuponów BB**"
    )
    a("")
    for note in coupons.notes:
        a(f"> {note}")
        a(">")
    a("")

    # --- singles ---------------------------------------------------------
    a("## Single")
    a("")
    if not coupons.singles:
        a("_Żaden wiersz nie przeszedł progu — dzień bez typów singlowych._")
    else:
        a("| # | Pewność | Mecz | Rynek | Strona | Surowo | n | Zgodność | Rynek | Typerzy | Min. kurs | Tier |")
        a("|--:|--------:|------|-------|--------|-------:|--:|----------|-------|---------|----------:|------|")
        for s in coupons.singles:
            subject = f" · {s.subject}" if s.subject else ""
            market = f"{s.market_label} {s.line}{subject}"
            mkt = "—"
            if s.market_verdict and s.market_verdict != "NO_MARKET_DATA":
                verdict = {
                    "CONFIRMS": "POTWIERDZA",
                    "CONTRADICTS": "PRZECZY",
                    "SPLIT": "PODZIELONY",
                }.get(s.market_verdict, s.market_verdict)
                mkt = verdict
                if s.market_price:
                    mkt += f" · {s.market_price} @{s.market_bookmaker}"
            a(
                f"| {s.rank} | {s.p_low * 100:.1f}% | {s.match} | {market} | {s.direction} "
                f"| {s.hits}/{s.sample_size} | {s.sample_size} | {s.cross_provider_agreement} "
                f"| {mkt} | {s.tipster or 'brak'} | **{s.min_acceptable_odds:.2f}** | {s.tier} |"
            )
        a("")
        a("Zastrzeżenia do poszczególnych typów:")
        a("")
        for s in coupons.singles:
            if s.caveats:
                a(f"- **#{s.rank} {s.match}** — {'; '.join(s.caveats)}")
        a("")

    # --- slips -----------------------------------------------------------
    a("## Bet Builder")
    a("")
    if not coupons.slips:
        a("_Żaden mecz nie dał dwóch nóg wystarczającej jakości._")
    else:
        for slip in coupons.slips:
            a(
                f"### {slip.rank}. {slip.match} · {slip.competition} · "
                f"{_kickoff(slip.kickoff)} UTC"
            )
            a("")
            a("| Noga | Strona | Pewność | Surowo | Min. kurs | Tier |")
            a("|------|--------|--------:|-------:|----------:|------|")
            for leg in slip.draft.legs:
                who = leg.player_name or leg.team_name
                subject = f" · {who}" if who else ""
                # BetBuilderLeg carries hit_rate and sample_size, not hits.
                hits = int(round(leg.hit_rate * leg.sample_size))
                a(
                    f"| {market_label(leg.market)} {leg.line}{subject} | {leg.direction} "
                    f"| {leg.p_low * 100:.1f}% | {hits}/{leg.sample_size} "
                    f"| **{leg.min_acceptable_odds:.2f}** | {leg.tier} |"
                )
            a("")
            # The contract's own note is English, because bet-analyst reads it.
            # The operator's file says the same thing in the file's language;
            # the risk level itself comes from the contract, never re-derived.
            correlated = sum(
                1 for leg in slip.draft.legs if leg.market in _CORRELATED_MARKETS
            )
            if slip.draft.correlation_risk == "HIGH":
                a(
                    f"⚠️ **Korelacja HIGH** — {correlated} z {len(slip.draft.legs)} nóg "
                    "pochodzi z tej samej skorelowanej rodziny (rożne / kartki / faule / "
                    "strzały w jednym meczu). Mecz faulowy jest meczem kartkowym, więc te "
                    "nogi wchodzą razem znacznie częściej, niż wynikałoby z niezależności. "
                    "Kupon jest przez to **mniej nieprawdopodobny**, niż sugerują same nogi "
                    "— i kurs Superbetu już to uwzględnia. Nigdy nie mnóż nóg."
                )
            elif slip.draft.correlation_risk == "LOW":
                a(
                    "ℹ️ Nogi spoza jednej skorelowanej rodziny, ale zdarzenia w tym samym "
                    "meczu nigdy nie są w pełni niezależne."
                )
            a("")
            a("**Kurs łączny: odczytaj z ekranu Superbetu.** Nie jest tu liczony.")
            a("")

    a("---")
    a("")
    a("Bez kursu łącznego, bez EV, bez stawki — celowo. Każdy kurs sprawdzasz sam;")
    a("typ poniżej minimalnego kursu nie jest typem.")
    a("")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--date", default=None, help="Betting day; resolves the default paths under runs/<date>/")
    parser.add_argument("--stats-sheet", default=None)
    parser.add_argument("--event-list", default=None)
    parser.add_argument("--output", default=None, help="Markdown path (default: runs/<date>/<date>_kupony.md)")
    parser.add_argument("--max-singles", type=int, default=15)
    parser.add_argument("--max-slips", type=int, default=8)
    parser.add_argument("--max-legs", type=int, default=4)
    parser.add_argument("--min-p-low", type=float, default=None)
    args = parser.parse_args()

    if not args.date and not args.stats_sheet:
        parser.error("give --date, or --stats-sheet explicitly")

    run_dir = ROOT / "runs" / args.date if args.date else None
    sheet_path = Path(args.stats_sheet) if args.stats_sheet else (
        run_dir / f"{args.date}_event_dossiers_stats_sheet.json"
    )
    if not sheet_path.exists():
        print(json.dumps({"error": f"stats sheet not found: {sheet_path}"}), file=sys.stderr)
        sys.exit(2)

    event_list_path = Path(args.event_list) if args.event_list else (
        run_dir / f"{args.date}_event_list.json" if run_dir else None
    )
    event_list = None
    if event_list_path and event_list_path.exists():
        event_list = EventListV1.model_validate_json(event_list_path.read_text(encoding="utf-8"))
    else:
        # Without it every coupon names a hash instead of a fixture. Worth a
        # loud warning rather than a silently uglier file.
        print(
            f"WARNING: no event list at {event_list_path} -- coupons will not name their fixtures",
            file=sys.stderr,
        )

    sheet = StatsSheetV1.model_validate_json(sheet_path.read_text(encoding="utf-8"))
    kwargs = dict(
        max_singles=args.max_singles, max_slips=args.max_slips, max_legs=args.max_legs
    )
    if args.min_p_low is not None:
        kwargs["min_p_low"] = args.min_p_low
    coupons = build_coupons(sheet, event_list, **kwargs)

    date = coupons.date or args.date or "unknown"
    md_path = Path(args.output) if args.output else (
        (run_dir or Path.cwd()) / f"{date}_kupony.md"
    )
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(coupons), encoding="utf-8")
    write_json_atomic(md_path.parent / f"{date}_coupons.json", coupons.model_dump(mode="json"))

    print(
        json.dumps(
            {
                "markdown": str(md_path),
                "json": str(md_path.parent / f"{date}_coupons.json"),
                "singles": len(coupons.singles),
                "slips": len(coupons.slips),
                "rows_considered": coupons.rows_considered,
                "events_considered": coupons.events_considered,
                "excluded": coupons.excluded,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    sys.exit(0 if (coupons.singles or coupons.slips) else 1)


if __name__ == "__main__":
    main()
