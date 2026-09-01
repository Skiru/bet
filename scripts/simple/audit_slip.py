#!/usr/bin/env python3
"""Price one Superbet leg or slip against the bzzoiro consensus, and say no.

    python3 scripts/simple/audit_slip.py \
        --price 1.48 --market team_to_score --side away \
        --home-win 1.50 --draw 4.43 --away-win 5.45 \
        --over-25 1.52 --under-25 2.41

    python3 scripts/simple/audit_slip.py \
        --price 2.05 --market 1h_over_0_5_under_2_5_and_2h_over_0_5 \
        --home-win 7.47 --draw 4.23 --away-win 1.45 \
        --over-25 2.01 --under-25 1.81

    python3 scripts/simple/audit_slip.py --price 1.42 --market sample \
        --hits 5 --sample-size 6

No network. The odds are the ones ``bet-analyst`` already has in hand from
``mcp__bzzoiro__get_match_detail`` or ``/events/{id}/odds/``, and keeping the
fetch out of here means the arithmetic can be re-run on a screenshot months
later -- which is exactly how the 2026-08-30/31 ledger was reconstructed.

``--market sample`` is the fallback for markets the odds feed does not carry
(corners, fouls, shots, player props): it prices a Wilson lower bound off a real
sample instead of the consensus, the same bound ``analyze.py`` uses. It is a
weaker answer than the market's and says so in its output.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from bet.simple_stats.analyze import wilson_lower_bound  # noqa: E402
from bet.simple_stats.slip_audit import (  # noqa: E402
    RANGE_MARKETS,
    audit_leg,
    fit_match_lambdas,
    probability_team_scores,
    range_market_ceiling,
    slip_price_floor,
)

MARKETS = ["team_to_score", "sample", *sorted(RANGE_MARKETS)]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--price", type=float, required=True, help="Superbet price")
    parser.add_argument("--market", choices=MARKETS, required=True)
    parser.add_argument("--side", choices=["home", "away"], default="home")
    parser.add_argument("--label", default=None)
    parser.add_argument("--home-win", type=float)
    parser.add_argument("--draw", type=float)
    parser.add_argument("--away-win", type=float)
    parser.add_argument("--over-25", type=float)
    parser.add_argument("--under-25", type=float)
    parser.add_argument("--hits", type=int, help="--market sample only")
    parser.add_argument("--sample-size", type=int, help="--market sample only")
    parser.add_argument(
        "--leg-probability",
        type=float,
        action="append",
        default=[],
        help="repeat once per leg to also report the slip's hard price floor",
    )
    return parser


def _needs_odds(args: argparse.Namespace) -> bool:
    return args.market != "sample"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    notes: list[str] = []

    if _needs_odds(args):
        if None in (args.home_win, args.draw, args.away_win):
            print(
                "--home-win/--draw/--away-win are required for this market",
                file=sys.stderr,
            )
            return 2
        lam_home, lam_away = fit_match_lambdas(
            home_win=args.home_win,
            draw=args.draw,
            away_win=args.away_win,
            over_25=args.over_25,
            under_25=args.under_25,
        )
        if args.over_25 is None or args.under_25 is None:
            notes.append(
                "no totals line given -- the 1X2 alone barely pins the match "
                "rate, so treat the match rate below as indicative"
            )
        if args.market == "team_to_score":
            lam = lam_home if args.side == "home" else lam_away
            fair = probability_team_scores(lam)
            print(f"match rate: home {lam_home:.2f} / away {lam_away:.2f} goals")
        else:
            fair = RANGE_MARKETS[args.market].probability(lam_home + lam_away)
            ceiling, at_lambda, floor = range_market_ceiling(args.market)
            print(f"match rate: {lam_home + lam_away:.2f} goals total")
            print(
                f"market ceiling: {ceiling:.1%} at a {at_lambda:.2f}-goal match "
                f"-> no price under {floor:.2f} is ever worth taking"
            )
            if args.price < floor:
                notes.append(
                    f"price {args.price:.2f} is below the market's own ceiling "
                    f"floor of {floor:.2f} -- refusable without reading the fixture"
                )
    else:
        if not args.hits or not args.sample_size:
            print(
                "--hits and --sample-size are required for --market sample",
                file=sys.stderr,
            )
            return 2
        fair = wilson_lower_bound(args.hits, args.sample_size)
        print(
            f"sample: {args.hits}/{args.sample_size} = "
            f"{args.hits / args.sample_size:.0%}, Wilson 95% lower bound {fair:.1%}"
        )
        notes.append(
            "a sample bound is weaker evidence than a consensus price: it says "
            "what has happened, not what this fixture is worth"
        )

    verdict = audit_leg(
        label=args.label or args.market, price=args.price, fair_probability=fair
    )
    print()
    print(f"{verdict.label}")
    print(f"  offered      {verdict.price:.2f}  ({verdict.implied_probability:.1%})")
    print(f"  fair         {verdict.fair_odds:.2f}  ({verdict.fair_probability:.1%})")
    print(f"  edge         {verdict.edge:+.1%}")
    print(f"  expectation  {verdict.expected_value:+.1%} per unit staked")
    print(f"  VERDICT      {verdict.verdict} -- {verdict.reason}")

    if args.leg_probability:
        floor = slip_price_floor(args.leg_probability)
        print()
        weakest = min(args.leg_probability)
        print(f"  slip floor   {floor:.2f} (weakest leg {weakest:.1%})")
        if args.price <= floor:
            print("               the other legs are being carried for nothing")

    for note in notes:
        print(f"  note: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
