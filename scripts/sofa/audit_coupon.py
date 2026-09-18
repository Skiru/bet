#!/usr/bin/env python3
"""Take a day's coupon apart: structure, arithmetic, and anti-selection.

Offline. Reads the day's artifacts and re-derives every number in every coupon
row **from the fields of that row**, rather than trusting the row. Three
questions, in the order they can falsify each other:

1. Is the artifact consistent with itself — does every coupon row exist in the
   sheet as VALUE, and did every VALUE row either reach the coupon or get a
   recorded reason for not doing so? A row that vanished in silence is the
   defect this pipeline has produced most often.

2. Does the arithmetic of each row hold? required_odds == margin / p_bar,
   surplus == offered - required, edge == p_central - market_p,
   p_bar == w*p + (1-w)*market_p with w = n/(n+K_PRICE).

3. Is the selection anti-selective against error in p? coupon.py sorts by
   surplus, and surplus grows as p is overstated, so the rows most likely to
   be wrong are the rows most likely to be picked. That is not a hypothesis
   about this day, it is a property of the mechanism, so the distributions
   below are the real test: if VALUE concentrates in the markets with the
   weakest measurement, it is an artifact and not an edge.

Exit: 0 = nothing found, 1 = findings.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import sys
from pathlib import Path
from typing import Any

from bet.sofa.config import SofaConfig
from bet.sofa.engine import K_PRICE
from bet.sofa.market_mapper import get_mechanism_family

MARGIN_LEAN = 1.10
MARGIN_CALL = 1.05
TOL = 5e-3
# p_bar is written to four decimals, so any comparison against a quantity
# derived from it inherits a half-ulp of 5e-5. Allow twice that.
P_ROUNDING_TOL = 1e-4


def _load(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def check_structure(
    coupon: dict[str, Any], sheet: list[dict[str, Any]], findings: list[str]
) -> None:
    singles = coupon.get("singles", [])
    dropped = coupon.get("dropped", []) or []

    sheet_key = {
        (
            r["sofascore_event_id"],
            r["market"],
            r["subject"],
            r["line"],
            r["direction"],
        ): r
        for r in sheet
    }

    for row in singles:
        key = (
            row["sofascore_event_id"],
            row["market"],
            row["subject"],
            row["line"],
            row["direction"],
        )
        source = sheet_key.get(key)
        if source is None:
            findings.append(f"STRUCTURE: coupon row {key} is not in the sheet at all")
        elif source["verdict"] != "VALUE":
            findings.append(
                f"STRUCTURE: coupon row {key} is {source['verdict']} in the sheet"
            )

    # Every VALUE row is either selected or dropped with a reason. Silence is
    # the failure mode, not exclusion.
    selected = {
        (r["sofascore_event_id"], r["market"], r["subject"], r["line"], r["direction"])
        for r in singles
    }
    dropped_keys = set()
    for d in dropped:
        r = d.get("row", d)
        dropped_keys.add(
            (
                r.get("sofascore_event_id"),
                r.get("market"),
                r.get("subject"),
                r.get("line"),
                r.get("direction"),
            )
        )
        if not d.get("reason"):
            findings.append(f"STRUCTURE: a dropped row carries no reason: {r}")

    for key, r in sheet_key.items():
        if r["verdict"] != "VALUE":
            continue
        if key not in selected and key not in dropped_keys:
            findings.append(
                f"STRUCTURE: VALUE row {key} is neither in the coupon nor in dropped "
                "— it vanished in silence"
            )


def check_arithmetic(
    singles: list[dict[str, Any]],
    sheet_by_key: dict[Any, dict[str, Any]],
    findings: list[str],
) -> None:
    for row in singles:
        key = (
            row["sofascore_event_id"],
            row["market"],
            row["subject"],
            row["line"],
            row["direction"],
        )
        label = (
            f"{row['market']} {row['subject'] or '-'} {row['line']} {row['direction']}"
        )

        p_bar = row["p_bar"]
        req = row["required_odds"]
        # The bar is 1.10 unless the row says otherwise; check both and report
        # which one it matches, rather than assuming.
        #
        # Compare in probability space, not in odds space. p_bar is stored to
        # four decimals, and odds are 1/p, so the half-ulp of that rounding is
        # magnified by 1/p**2 — at p_bar = 0.058 a difference of 2.5e-5 in p
        # becomes 0.008 in odds, which an absolute odds tolerance reports as a
        # broken row. Five such rows were reported before this was checked, and
        # every one of them was arithmetically exact.
        implied = [m / req for m in (MARGIN_LEAN, MARGIN_CALL)]
        if not any(abs(i - p_bar) < P_ROUNDING_TOL for i in implied):
            findings.append(
                f"ARITHMETIC [{label}]: p_bar {p_bar:.6f} matches neither "
                f"{MARGIN_LEAN}/required_odds ({implied[0]:.6f}) nor "
                f"{MARGIN_CALL}/required_odds ({implied[1]:.6f})"
            )

        surplus = row["offered_odds"] - req
        if abs(surplus - row["surplus"]) > TOL:
            findings.append(
                f"ARITHMETIC [{label}]: surplus {row['surplus']:.4f} != "
                f"offered {row['offered_odds']} - required {req:.4f} = {surplus:.4f}"
            )

        if row.get("market_p") is not None and row.get("edge") is not None:
            edge = row["p_central"] - row["market_p"]
            if abs(edge - row["edge"]) > TOL:
                findings.append(
                    f"ARITHMETIC [{label}]: edge {row['edge']:.4f} != "
                    f"p_central - market_p = {edge:.4f}"
                )

        # p_bar from the shrinkage identity. Only checkable when the row was
        # not capped (Laplace / p_low) — the sheet records that in bar_reason.
        src = sheet_by_key.get(key)
        if src is not None and row.get("market_p") is not None:
            reason = src.get("bar_reason") or "none"
            if reason == "none":
                n = row["sample_size"]
                w = n / (n + K_PRICE)
                expect = w * row["p_central"] + (1 - w) * row["market_p"]
                if abs(expect - p_bar) > TOL:
                    findings.append(
                        f"ARITHMETIC [{label}]: p_bar {p_bar:.4f} != "
                        f"w*p_central + (1-w)*market_p = {expect:.4f} "
                        f"(n={n}, w={w:.3f})"
                    )


def report_distributions(
    singles: list[dict[str, Any]], fixtures_by_id: dict[int, dict[str, Any]]
) -> None:
    if not singles:
        print("  (no rows)")
        return

    def show(title: str, counter: collections.Counter[Any]) -> None:
        print(f"\n  by {title}:")
        for k, v in counter.most_common():
            print(f"    {str(k):45} {v:3d}")

    show("market", collections.Counter(r["market"] for r in singles))
    show(
        "mechanism family",
        collections.Counter(get_mechanism_family(r["market"]) for r in singles),
    )
    show(
        "competition",
        collections.Counter(
            (
                fixtures_by_id.get(r["sofascore_event_id"], {}).get("competition_name")
                or "?"
            )
            for r in singles
        ),
    )
    show("sport", collections.Counter(r["sport"] for r in singles))

    print("\n  by sample_size:")
    for n, c in sorted(collections.Counter(r["sample_size"] for r in singles).items()):
        flag = (
            "  <- below 8: p_low caps, and the bar is mostly price, not model"
            if n < 8
            else ""
        )
        print(f"    n={n:<3} {c:3d}{flag}")

    surpluses = sorted(r["surplus"] for r in singles)
    print("\n  surplus distribution:")
    print(
        f"    min {surpluses[0]:+.3f}  median {surpluses[len(surpluses) // 2]:+.3f}  "
        f"max {surpluses[-1]:+.3f}"
    )
    extreme = [r for r in singles if r["surplus"] > 0.40]
    if extreme:
        print(
            f"    {len(extreme)} row(s) with surplus > +0.40 — suspect BY DEFINITION,"
        )
        print("    there are no free 40% on a liquid market. Take each apart by hand:")
        for r in extreme:
            print(
                f"      {r['match_name']}: {r['market']} {r['subject'] or '-'} "
                f"{r['line']} {r['direction']} @ {r['offered_odds']} "
                f"(req {r['required_odds']:.2f}, n={r['sample_size']})"
            )



def _row_bounds(row: dict[str, Any]) -> tuple[int | None, int | None]:
    """The smallest and largest count consistent with a row winning.

    Integer counts, so "powyżej 2.5" is ">= 3" and "poniżej 2.5" is "<= 2".
    """
    if row["direction"] == "OVER":
        return (math.floor(row["line"]) + 1, None)
    return (None, math.ceil(row["line"]) - 1)


def _metric_base(market: str) -> str:
    for suffix in ("_total", "_for"):
        if market.endswith(suffix):
            return market[: -len(suffix)]
    return market


def check_internal_consistency(
    singles: list[dict[str, Any]],
    fixtures_by_id: dict[int, dict[str, Any]],
    findings: list[str],
) -> None:
    """Rows on one fixture that cannot all win.

    A coupon is allowed to hold several rows on one match — they are priced
    and settled separately — but it must never hold two that contradict each
    other outright, because one of them is then a guaranteed loser bought on
    purpose. The relations checked are the ones that hold by arithmetic, not
    by judgement:

      * a side's own count can never exceed the match total for that metric,
        so "team over 2.5 goals" and "match under 0.5 goals" cannot both win;
      * the same ladder must not appear twice on one fixture.

    Both came back clean on 2026-09-18; the check exists so that stays true
    when the market map grows, which is exactly when it stops being obvious.
    """
    by_fixture: dict[int, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in singles:
        by_fixture[row["sofascore_event_id"]].append(row)

    for fixture_id, rows in by_fixture.items():
        name = fixtures_by_id.get(fixture_id, {})
        label = (
            f"{name.get('home_name', '?')} - {name.get('away_name', '?')}"
            if name
            else str(fixture_id)
        )

        seen: collections.Counter[tuple[str, str]] = collections.Counter(
            (r["market"], r["subject"]) for r in rows
        )
        for (market, subject), count in seen.items():
            if count > 1:
                findings.append(
                    f"{label}: {count} rows on the same ladder "
                    f"{market} {subject or '-'} — one claim bought twice"
                )

        for index, first in enumerate(rows):
            for second in rows[index + 1 :]:
                if _metric_base(first["market"]) != _metric_base(second["market"]):
                    continue
                if first["market"].endswith("_for") and second["market"].endswith(
                    "_total"
                ):
                    side, whole = first, second
                elif second["market"].endswith("_for") and first["market"].endswith(
                    "_total"
                ):
                    side, whole = second, first
                else:
                    continue
                side_min, _ = _row_bounds(side)
                _, whole_max = _row_bounds(whole)
                if side_min is not None and whole_max is not None:
                    if side_min > whole_max:
                        findings.append(
                            f"{label}: CONTRADICTION — "
                            f"{side['market']} {side['subject']} "
                            f"{side['line']} {side['direction']} needs >= "
                            f"{side_min}, but {whole['market']} "
                            f"{whole['line']} {whole['direction']} allows at "
                            f"most {whole_max}"
                        )


def report_ladder_profile(
    singles: list[dict[str, Any]], sheet: list[dict[str, Any]]
) -> None:
    """How much of each coupon row's own ladder also came back VALUE.

    Not a finding and not a gate — a description. A rung that is VALUE while
    its neighbours are not is a local disagreement with one price. A rung that
    is VALUE because every rung of its ladder is says something else: the
    model and the market disagree about where the centre of the distribution
    sits, and one row has been picked out of a single disagreement. The two
    deserve different confidence and the artifact should not make them look
    alike.
    """
    ladders: dict[tuple[Any, ...], list[dict[str, Any]]] = collections.defaultdict(
        list
    )
    for row in sheet:
        key = (
            row["sofascore_event_id"],
            row["market"],
            row["subject"],
            row["direction"],
        )
        ladders[key].append(row)

    profile: collections.Counter[str] = collections.Counter()
    for row in singles:
        key = (
            row["sofascore_event_id"],
            row["market"],
            row["subject"],
            row["direction"],
        )
        priced = [r for r in ladders.get(key, []) if r["offered_odds"] is not None]
        value = sum(1 for r in priced if r["verdict"] == "VALUE")
        if len(priced) <= 1:
            profile["single-rung ladder (no neighbours to compare)"] += 1
        elif value == len(priced):
            profile["every rung of its ladder is VALUE (centre disagreement)"] += 1
        elif value / len(priced) >= 0.5:
            profile["most of its ladder is VALUE"] += 1
        else:
            profile["a local disagreement (<50% of its ladder)"] += 1

    print()
    print("--- 4.4 what kind of disagreement each row rests on ---")
    print()
    for label, count in profile.most_common():
        print(f"    {label:58s} {count}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    args = parser.parse_args()

    run_dir = Path(SofaConfig.from_env().runs_dir) / args.date
    coupon = _load(run_dir / "06_coupon.json")
    sheet = _load(run_dir / "05_sheet.json")
    fixtures = _load(run_dir / "02_fixtures.json") or []

    if coupon is None or sheet is None:
        print(f"missing artifacts in {run_dir}", file=sys.stderr)
        return 2

    # The drops are written to their own artifact, not into 06_coupon.json.
    # Reading only the coupon made every dropped row look like it had vanished
    # in silence — 1015 false findings, which is exactly the failure this
    # harness exists to detect, so it has to read where the reasons actually
    # live before it is allowed to claim one is missing.
    if coupon.get("dropped") is None:
        dropped = _load(run_dir / "06_dropped.json")
        if dropped is None:
            print(
                f"neither 06_coupon.json nor 06_dropped.json records drops in "
                f"{run_dir} — cannot tell a silent loss from an unread file",
                file=sys.stderr,
            )
            return 2
        coupon["dropped"] = dropped

    if isinstance(sheet, dict):
        sheet = sheet.get("rows", [])
    singles = coupon.get("singles", [])
    fixtures_by_id = {f["sofascore_event_id"]: f for f in fixtures}
    sheet_by_key = {
        (
            r["sofascore_event_id"],
            r["market"],
            r["subject"],
            r["line"],
            r["direction"],
        ): r
        for r in sheet
    }

    findings: list[str] = []
    check_structure(coupon, sheet, findings)
    check_arithmetic(singles, sheet_by_key, findings)
    check_internal_consistency(singles, fixtures_by_id, findings)

    verdicts = collections.Counter(r["verdict"] for r in sheet)
    print("=" * 74)
    print(f"COUPON AUDIT — {args.date}")
    print("=" * 74)
    print(f"sheet rows: {len(sheet)}   {dict(verdicts)}")
    n_dropped = len(coupon.get("dropped", []) or [])
    print(f"coupon singles: {len(singles)}   dropped: {n_dropped}")

    print("\n--- 4.1/4.2 structure and arithmetic ---")
    if findings:
        for f in findings:
            print(f"  ! {f}")
    else:
        print("  no structural or arithmetic finding")

    print("\n--- 4.3 anti-selection: what kind of rows won the slots ---")
    report_distributions(singles, fixtures_by_id)
    report_ladder_profile(singles, sheet)

    if singles:
        n_small = sum(1 for r in singles if r["sample_size"] < 8)
        if n_small:
            print(
                f"\n  {n_small} of {len(singles)} rows have n < 8. For these the bar is"
            )
            print("  dominated by market_p, so they measure the price against the")
            print("  devigged line, not this model. Describe them as such.")

    print("\n--- dropped reasons ---")
    for reason, c in collections.Counter(
        d.get("reason") for d in (coupon.get("dropped") or [])
    ).most_common():
        print(f"  {str(reason):28} {c:3d}")

    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
