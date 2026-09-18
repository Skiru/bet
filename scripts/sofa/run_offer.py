import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import RootModel

from bet.sofa.config import SofaConfig
from bet.sofa.contracts import Fixture
from bet.sofa.offer import OfferFetcher
from bet.sofa.stage import set_stage
from bet.sofa.superbet import SuperbetClient
from bet.sofa.timeutil import now


def main() -> int:
    # Every request underneath this call is this stage's cost (F22).
    set_stage("OFFER")
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD", default=now().strftime("%Y-%m-%d"))
    args = parser.parse_args()

    config = SofaConfig.from_env()
    client = SuperbetClient(
        base_url="https://production-superbet-offer-pl.freetls.fastly.net"
    )
    fetcher = OfferFetcher(client)

    fixtures_path = Path(config.runs_dir) / args.date / "02_fixtures.json"
    if not fixtures_path.exists():
        print(f"{fixtures_path} missing", file=sys.stderr)
        return 2

    with open(fixtures_path, "rb") as f:
        fixtures_data = f.read()

    fixtures = RootModel[list[Fixture]].model_validate_json(fixtures_data).root

    try:
        offers = fetcher.fetch_offers(fixtures)
    except Exception as e:
        summary = {
            "stage": "OFFER",
            "verdict": "FAILED",
            "metrics": {"error": str(e)},
            "output_path": None,
        }
        print(f"SOFA_SUMMARY: {json.dumps(summary)}", flush=True)
        return 2

    out_path = Path(config.runs_dir) / args.date / "04_offer.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    dumped = [o.model_dump(mode="json") for o in offers]
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(dumped, f, indent=2)

    total_two_way = sum(
        1
        for o in offers
        for r in o.rungs
        if r.over_odds is not None and r.under_odds is not None
    )
    total_unmapped = sum(len(o.unmapped_markets) for o in offers)
    empty_offers = sum(1 for o in offers if not o.rungs)

    metrics: dict[str, Any] = {
        "input_fixtures": len(fixtures),
        "output_offers": len(offers),
        "total_two_way_rungs": total_two_way,
        "total_unmapped": total_unmapped,
        "empty_offers": empty_offers,
    }

    # Fixtures on the board with no priced rung at all, and market names we
    # could not classify, are both diagnostics the operator has to see — a
    # market Superbet added should surface as unmapped, not vanish (T16).
    if fixtures and empty_offers == len(offers):
        verdict = "FAILED"
    elif empty_offers or total_unmapped:
        verdict = "PARTIAL"
    else:
        verdict = "OK"

    summary = {
        "stage": "OFFER",
        "verdict": verdict,
        "metrics": metrics,
        "output_path": str(out_path),
    }

    print(f"SOFA_SUMMARY: {json.dumps(summary)}", flush=True)
    return {"OK": 0, "PARTIAL": 1, "FAILED": 2}[verdict]


if __name__ == "__main__":
    sys.exit(main())
