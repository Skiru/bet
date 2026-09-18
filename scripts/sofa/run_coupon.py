#!/usr/bin/env python3
"""COUPON — E9. Selects singles and writes the human report.

The markdown is generated from the very objects the arithmetic ran on, never
from a second pass: a report that disagrees with its own numbers is a report to
throw away (L27).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

from pydantic import RootModel

from bet.sofa.config import SofaConfig
from bet.sofa.contracts import Fixture, FixtureOffer, SheetRow, Veto
from bet.sofa.coupon import CouponResult, build_coupon
from bet.sofa.stage import set_stage
from bet.sofa.timeutil import now
from bet.sofa.veto import find_unmatched_vetoes


def read_file(path: Path) -> bytes | None:
    if not path.exists():
        return None
    return path.read_bytes()


def render_markdown(
    result: CouponResult,
    sheet_rows: list[SheetRow],
    unmatched_vetoes: list[Veto],
) -> str:
    coupon = result.coupon
    stamp = coupon.created_at_utc.strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"# Kupon ({stamp} UTC)", ""]

    rows_by_key = {
        (r.sofascore_event_id, r.market, r.subject, r.line, r.direction): r
        for r in sheet_rows
    }

    if not coupon.singles:
        lines.append("Brak zakładów (pusty slate lub wszystkie odrzucone).")
        lines.append("")
    else:
        lines += [
            f"## Single ({len(coupon.singles)})",
            "",
            "| Mecz | Kickoff | Rynek | Kier. | n | Środek | p_central | "
            "market_p | edge | p_bar | req | oferta | nadwyżka |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for r in coupon.singles:
            subject = f" ({r.subject})" if r.subject else ""
            market_p = f"{r.market_p:.3f}" if r.market_p is not None else "—"
            edge = f"{r.edge:+.3f}" if r.edge is not None else "—"
            lines.append(
                f"| {r.match_name} | {r.kickoff_utc.strftime('%H:%M')} "
                f"| {r.market}{subject} {r.line:g} | {r.direction} "
                f"| {r.sample_size} | {r.centre:.2f} | {r.p_central:.3f} "
                f"| {market_p} | {edge} | {r.p_bar:.3f} "
                f"| {r.required_odds:.2f} | **{r.offered_odds:.2f}** "
                f"| +{r.surplus:.4f} |"
            )
        lines.append("")

        lines += ["### Próbka za każdym wierszem", ""]
        for r in coupon.singles:
            key = (r.sofascore_event_id, r.market, r.subject, r.line, r.direction)
            sheet_row = rows_by_key.get(key)
            subject = f" ({r.subject})" if r.subject else ""
            lines.append(
                f"- **{r.match_name}** — {r.market}{subject} {r.line:g} {r.direction}"
            )
            if sheet_row is None:
                lines.append("  - (brak wiersza arkusza — niespodziewane)")
                continue
            lines.append(
                f"  - n={sheet_row.sample_size}, średnia={sheet_row.sample_mean:.3f}, "
                f"sd={sheet_row.sample_sd:.3f} → środek {sheet_row.centre:.3f}"
            )
            ladder_c = (
                f"{sheet_row.ladder_centre:.3f}"
                if sheet_row.ladder_centre is not None
                else "—"
            )
            ladder_s = (
                f"{sheet_row.ladder_sigma:.3f}"
                if sheet_row.ladder_sigma is not None
                else "—"
            )
            lines.append(
                f"  - środek drabiny={ladder_c}, ladder_sigma={ladder_s}, "
                f"ograniczenie progu: {sheet_row.bar_reason}"
            )
            lines.append(
                f"  - {sheet_row.required_odds:.4f} = 1.10 / {sheet_row.p_bar:.4f}; "
                f"nadwyżka {r.offered_odds:.2f} − {sheet_row.required_odds:.4f} "
                f"= {r.surplus:+.4f}"
            )
            if sheet_row.notes:
                lines.append(f"  - uwagi: {'; '.join(sheet_row.notes)}")
        lines.append("")

    if result.dropped:
        lines += [
            f"## Wiersze VALUE odrzucone ({len(result.dropped)})",
            "",
            "| Mecz (event) | Rynek | Kier. | Nadwyżka | Powód | Szczegół |",
            "|---|---|---|---|---|---|",
        ]
        for d in result.dropped:
            surplus = f"{d.row.surplus:+.4f}" if d.row.surplus is not None else "—"
            subject = f" ({d.row.subject})" if d.row.subject else ""
            lines.append(
                f"| {d.row.sofascore_event_id} | {d.row.market}{subject} "
                f"{d.row.line:g} | {d.row.direction} | {surplus} "
                f"| `{d.reason}` | {d.detail} |"
            )
        lines.append("")

    if unmatched_vetoes:
        lines += [f"## UNMATCHED_VETO ({len(unmatched_vetoes)})", ""]
        lines.append(
            "Te veta nie pasowały do żadnego wiersza arkusza — sprawdź klucz, "
            "bo veto, które nic nie robi, wygląda jak veto, które zadziałało (L20)."
        )
        lines.append("")
        for v in unmatched_vetoes:
            lines.append(
                f"- event `{v.sofascore_event_id}` market=`{v.market}` "
                f"subject=`{v.subject}` line=`{v.line}` dir=`{v.direction}` "
                f"— {v.reason_class}: {v.reason}"
            )
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    # Every request underneath this call is this stage's cost (F22).
    set_stage("COUPON")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=now().strftime("%Y-%m-%d"), help="YYYY-MM-DD")
    args = parser.parse_args()

    config = SofaConfig.from_env()
    run_dir = Path(config.runs_dir) / args.date

    sheet_data = read_file(run_dir / "05_sheet.json")
    fixtures_data = read_file(run_dir / "02_fixtures.json")
    offer_data = read_file(run_dir / "04_offer.json")
    vetoes_path = run_dir / "vetoes.json"

    if sheet_data is None or fixtures_data is None or offer_data is None:
        print("Missing required artifacts", file=sys.stderr)
        return 2

    fixtures = RootModel[list[Fixture]].model_validate_json(fixtures_data).root
    sheet_rows = RootModel[list[SheetRow]].model_validate_json(sheet_data).root
    offers = RootModel[list[FixtureOffer]].model_validate_json(offer_data).root

    vetoes: list[Veto] = []
    vetoes_data = read_file(vetoes_path)
    if vetoes_data and vetoes_data.strip():
        vetoes = RootModel[list[Veto]].model_validate_json(vetoes_data).root

    # T27: a veto matching nothing is reported, never silently ignored.
    unmatched_vetoes = find_unmatched_vetoes(sheet_rows, vetoes)
    for v in unmatched_vetoes:
        print(f"UNMATCHED_VETO: {v.model_dump_json()}", file=sys.stderr)

    current_time = now()
    result = build_coupon(
        sheet_rows=sheet_rows,
        fixtures=fixtures,
        offers=offers,
        vetoes=vetoes,
        current_time=current_time,
        min_kickoff=current_time + timedelta(minutes=15),
        max_price_age=timedelta(minutes=config.price_max_age_min),
    )

    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "06_coupon.json").write_text(
        json.dumps(result.coupon.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (run_dir / "06_coupon.md").write_text(
        render_markdown(result, sheet_rows, unmatched_vetoes), encoding="utf-8"
    )
    (run_dir / "06_dropped.json").write_text(
        json.dumps(
            [
                {
                    "sofascore_event_id": d.row.sofascore_event_id,
                    "market": d.row.market,
                    "subject": d.row.subject,
                    "line": d.row.line,
                    "direction": d.row.direction,
                    "surplus": d.row.surplus,
                    "reason": d.reason,
                    "detail": d.detail,
                }
                for d in result.dropped
            ],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    if not vetoes_path.exists():
        vetoes_path.write_text("[]\n", encoding="utf-8")

    drop_reasons: dict[str, int] = {}
    for d in result.dropped:
        drop_reasons[d.reason] = drop_reasons.get(d.reason, 0) + 1

    summary = {
        "stage": "COUPON",
        "verdict": "PARTIAL" if unmatched_vetoes else "OK",
        "metrics": {
            "selected": len(result.coupon.singles),
            "value_rows": sum(1 for r in sheet_rows if r.verdict == "VALUE"),
            "dropped": len(result.dropped),
            "drop_reasons": drop_reasons,
            "unmatched_vetoes": len(unmatched_vetoes),
        },
        "output_path": str(run_dir / "06_coupon.json"),
    }
    print(f"SOFA_SUMMARY: {json.dumps(summary)}", flush=True)
    return 1 if unmatched_vetoes else 0


if __name__ == "__main__":
    sys.exit(main())
