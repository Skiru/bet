#!/usr/bin/env python3
"""CONFIDENCE — rank legs by measured reliability, and build Bet Builders.

The coupon stage answers "is this worth its price". This one answers "how
often does this actually happen", which is the question an operator who has
already accepted a shaded price is asking. See bet.sofa.confidence for why the
two are different and why the first one is a losing argument here.

Reads the sheet, the offer and the fixtures that are already on disk. Costs no
provider call. Writes 08_confidence.json and 08_confidence.md.

Usage:
    python -m scripts.sofa.run_confidence --date 2026-09-19 --floor 0.80
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.confidence import (  # noqa: E402
    MAX_BUILDER_LEGS,
    MIN_BUILDER_LEGS,
    MAX_DISAGREEMENT,
    Calibration,
    is_derived,
    combined_probability,
    fair_odds,
    quantity_family,
)
from bet.sofa.engine import (  # noqa: E402
    uses_empirical_frequency,
    uses_poisson_floor,
)

# A leg below this is not what the operator means by a strong read. The floor
# is on the measured LOWER bound, not on what the model claims.
DEFAULT_FLOOR = 0.80
# Superbet's own shading is accepted, but a price below this is not a shaded
# price, it is a rounding error with a stake attached.
MIN_ODDS = 1.01
MAX_PRICE_AGE = timedelta(minutes=45)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", required=True)
    ap.add_argument("--floor", type=float, default=DEFAULT_FLOOR)
    ap.add_argument("--runs-dir", default="runs/sofa")
    args = ap.parse_args()

    run_dir = Path(args.runs_dir) / args.date
    sheet = json.loads((run_dir / "05_sheet.json").read_text(encoding="utf-8"))
    fixtures = {
        f["sofascore_event_id"]: f
        for f in json.loads((run_dir / "02_fixtures.json").read_text(encoding="utf-8"))
    }
    offers = json.loads((run_dir / "04_offer.json").read_text(encoding="utf-8"))
    fetched: dict[tuple, str] = {}
    for o in offers:
        for r in o.get("rungs", []):
            for d in ("OVER", "UNDER"):
                fetched[
                    (o["sofascore_event_id"], r["market"], r.get("subject", ""),
                     r["line"], d)
                ] = r.get("fetched_at_utc")

    cal = Calibration.load()
    now = datetime.now(timezone.utc)

    legs: list[dict] = []
    refused: dict[str, int] = defaultdict(int)
    for row in sheet:
        odds = row.get("offered_odds")
        if odds is None:
            refused["NO_PRICE"] += 1
            continue
        if odds < MIN_ODDS:
            refused["ODDS_TOO_LOW"] += 1
            continue
        fx = fixtures.get(row["sofascore_event_id"])
        if fx is None:
            refused["NO_FIXTURE"] += 1
            continue
        ko = datetime.fromisoformat(fx["kickoff_utc"].replace("Z", "+00:00"))
        if ko <= now:
            refused["KICKED_OFF"] += 1
            continue
        key = (row["sofascore_event_id"], row["market"], row.get("subject", ""),
               row["line"], row["direction"])
        ts = fetched.get(key)
        if ts is None:
            refused["NO_FETCHED_AT"] += 1
            continue
        if now - datetime.fromisoformat(ts.replace("Z", "+00:00")) > MAX_PRICE_AGE:
            refused["STALE_PRICE"] += 1
            continue

        # The calibration was fitted over count metrics only — fit_confidence
        # skips the empirical-frequency and non-count families, so the pooled
        # curve says nothing about them. Serving them from it anyway put
        # games_won_for and sets_total at the top of the list at a claimed
        # 0.811 against a price of 20.00. A metric outside the fit is refused.
        if uses_empirical_frequency(row["market"]) or not uses_poisson_floor(
            row["market"]
        ):
            refused["NOT_IN_CALIBRATION_FIT"] += 1
            continue
        # See DERIVED_PREFIXES. A joint of two sides is not a count of one
        # thing, has 2-252 settled rows of its own, and no sample in the
        # artifacts can check it.
        if is_derived(row["market"]):
            refused["DERIVED_NOT_CALIBRATABLE"] += 1
            continue

        hit = cal.realised(row["market"], row["p_central"])
        if hit is None:
            # No measurement for this bucket. The model's own number is not a
            # substitute for one, so the leg is refused rather than guessed.
            refused["NOT_CALIBRATED"] += 1
            continue
        realised_lo, source, n_cal = hit
        if realised_lo < args.floor:
            refused["BELOW_CONFIDENCE_FLOOR"] += 1
            continue
        # See MAX_DISAGREEMENT. Shading means the book pays us less than the
        # event is worth; this is the opposite case, where we claim far more
        # than the book does, and it is measured to end below a coin flip.
        if realised_lo - 1.0 / odds > MAX_DISAGREEMENT:
            refused["DISAGREES_WITH_PRICE"] += 1
            continue

        legs.append(
            {
                "sofascore_event_id": row["sofascore_event_id"],
                "match": f"{fx['home_name']} - {fx['away_name']}",
                "competition": fx.get("competition_name"),
                "sport": row["sport"],
                "kickoff_utc": fx["kickoff_utc"],
                "market": row["market"],
                "subject": row.get("subject", ""),
                "line": row["line"],
                "direction": row["direction"],
                "model_p": round(row["p_central"], 4),
                "confidence": realised_lo,
                "calibrated_on": source,
                "calibration_n": n_cal,
                "sample_size": row["sample_size"],
                "offered_odds": odds,
                "implied_p": round(1.0 / odds, 4),
                # What Superbet's shading costs on THIS leg, in probability
                # and then in money. The operator has accepted the shading;
                # this is so he can see how much of it he is accepting.
                "shading": round(realised_lo - 1.0 / odds, 4),
                "leg_ev": round(realised_lo * odds - 1.0, 4),
                "market_p": row.get("market_p"),
            }
        )

    legs.sort(key=lambda r: (-r["leg_ev"], -r["confidence"]))

    # Bet Builders: same fixture, one leg per market family, 2-4 legs.
    builders: list[dict] = []
    by_fixture: dict[int, list[dict]] = defaultdict(list)
    for leg in legs:
        by_fixture[leg["sofascore_event_id"]].append(leg)
    for eid, group in by_fixture.items():
        # One leg per QUANTITY, not per market: a team's goals and the match
        # total are the same quantity counted twice (lambda 2.165), and
        # multiplying them would sell two legs as four. See QUANTITY_FAMILIES.
        best_per_quantity: dict[str, dict] = {}
        for leg in group:
            fam = quantity_family(leg["market"])
            cur = best_per_quantity.get(fam)
            if cur is None or leg["confidence"] > cur["confidence"]:
                best_per_quantity[fam] = leg
        pool = sorted(best_per_quantity.values(), key=lambda r: -r["confidence"])
        if len(pool) < MIN_BUILDER_LEGS:
            continue
        for size in range(MIN_BUILDER_LEGS, min(MAX_BUILDER_LEGS, len(pool)) + 1):
            combo = pool[:size]
            p = combined_probability([c["confidence"] for c in combo])
            builders.append(
                {
                    "sofascore_event_id": eid,
                    "match": combo[0]["match"],
                    "competition": combo[0]["competition"],
                    "kickoff_utc": combo[0]["kickoff_utc"],
                    "legs": [
                        {
                            "market": c["market"], "subject": c["subject"],
                            "line": c["line"], "direction": c["direction"],
                            "confidence": c["confidence"], "odds": c["offered_odds"],
                        }
                        for c in combo
                    ],
                    "n_legs": size,
                    "combined_probability": round(p, 4),
                    "fair_odds": fair_odds(p),
                    # Shading compounds. Each leg returns confidence*odds; a
                    # builder priced at the product of its legs returns the
                    # product of those, so a 4.5 pp shade per leg is not a
                    # 4.5 pp shade on the slip. This is the reference price,
                    # NOT Superbet's builder price (see fair_odds).
                    "odds_if_product": round(
                        __import__("math").prod(c["offered_odds"] for c in combo), 2
                    ),
                    "ev_if_product_priced": round(
                        __import__("math").prod(
                            c["confidence"] * c["offered_odds"] for c in combo
                        )
                        - 1.0,
                        4,
                    ),
                }
            )
    builders.sort(key=lambda b: (-b["ev_if_product_priced"], -b["combined_probability"]))

    # A fixture emits a 2-, 3- and 4-leg builder off the same ranked pool, so
    # the smaller ones are SUBSETS of the larger. Staking all three is staking
    # one opinion three times at three stakes, and on 2026-09-19 that dressed
    # 54 fixtures up as 79 independent bets with 46 of 148 legs repeated.
    # Every builder stays in the artifact because comparing 2 against 4 on one
    # fixture is exactly how the operator picks; only one per fixture is
    # marked as stakeable.
    best_seen: set[int] = set()
    for b in builders:
        eid = b["sofascore_event_id"]
        b["best_for_fixture"] = eid not in best_seen
        best_seen.add(eid)

    out = {
        "created_at_utc": now.isoformat().replace("+00:00", "Z"),
        "confidence_floor": args.floor,
        "legs": legs,
        "builders": builders,
    }
    (run_dir / "08_confidence.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    lines = [
        f"# Confidence view — {args.date}",
        "",
        f"Built {out['created_at_utc']}. Floor: measured lower bound >= {args.floor}.",
        "",
        "`confidence` is the **lower bound of the realised rate** for this market at "
        "this model probability, fitted on 1,868,474 settled rows — not the model's "
        "own claim. The curve tops out near 0.92: there is no 98% leg.",
        "",
        "## Legs",
        "",
        "| conf | odds | implied | shading | leg EV | market | line | match | kickoff |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for leg in legs[:60]:
        subj = f" {leg['subject']}" if leg["subject"] else ""
        lines.append(
            f"| {leg['confidence']:.3f} | {leg['offered_odds']} | "
            f"{leg['implied_p']:.3f} | {leg['shading']:+.3f} | {leg['leg_ev']:+.3f} | "
            f"{leg['market']}{subj} | {leg['line']} {leg['direction']} | "
            f"{leg['match']} | {leg['kickoff_utc'][11:16]}Z |"
        )
    lines += [
        "",
        "## Bet Builders (same match)",
        "",
        "`fair_odds` is what the combination must pay to be worth its risk. It is "
        "**not** a prediction of Superbet's Bet Builder price — the book applies its "
        "own correlation adjustment, so compare against the screen.",
        "",
        "| legs | combined p | fair odds | odds if product | EV at that price | match | selection |",
        "|---|---|---|---|---|---|---|",
    ]
    for b in [x for x in builders if x["best_for_fixture"]][:40]:
        sel = " + ".join(
            f"{x['market']} {x['line']} {x['direction']}" for x in b["legs"]
        )
        lines.append(
            f"| {b['n_legs']} | {b['combined_probability']:.3f} | {b['fair_odds']} | "
            f"{b['odds_if_product']} | {b['ev_if_product_priced']:+.3f} | "
            f"{b['match']} | {sel} |"
        )
    (run_dir / "08_confidence.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "stage": "CONFIDENCE", "verdict": "OK",
        "metrics": {
            "legs": len(legs), "builders": len(builders), "stakeable_builders": sum(1 for b in builders if b["best_for_fixture"]),
            "fixtures_with_legs": len(by_fixture), "refused": dict(refused),
        },
        "output_path": str(run_dir / "08_confidence.json"),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
