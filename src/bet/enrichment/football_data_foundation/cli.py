from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from bet.enrichment.football_data_foundation.event_model_bridges.floodlight_bridge import (
    FloodlightBridge,
)
from bet.enrichment.football_data_foundation.event_model_bridges.kloppy_bridge import (
    KloppyBridge,
)
from bet.enrichment.football_data_foundation.event_model_bridges.mplsoccer_bridge import (
    MplSoccerBridge,
)
from bet.enrichment.football_data_foundation.event_model_bridges.socceraction_bridge import (
    SoccerActionBridge,
)
from bet.enrichment.football_data_foundation.open_reference_sources.football_data_org_bridge import (
    FootballDataOrgBridge,
)
from bet.enrichment.football_data_foundation.open_reference_sources.kaggle_european_soccer import (
    KaggleEuropeanSoccerConnector,
)
from bet.enrichment.football_data_foundation.open_reference_sources.openfootball import (
    OpenFootballConnector,
)
from bet.enrichment.football_data_foundation.open_reference_sources.statsbomb_open_data import (
    StatsBombOpenDataConnector,
)
from bet.enrichment.football_data_foundation.open_reference_sources.statsbombpy_bridge import (
    StatsBombPyBridge,
)
from bet.enrichment.football_data_foundation.rich_unofficial_sources.fotmob_probe import (
    FotMobProbe,
)
from bet.enrichment.football_data_foundation.rich_unofficial_sources.scraperfc_sofascore_bridge import (
    ScraperFCSofascoreBridge,
)
from bet.enrichment.football_data_foundation.rich_unofficial_sources.sofascore_rich_probe import (
    SofaScoreRichProbe,
)
from bet.enrichment.football_data_foundation.soccerdata_sources.clubelo import (
    ClubEloConnector,
)
from bet.enrichment.football_data_foundation.soccerdata_sources.espn import (
    ESPNConnector,
)
from bet.enrichment.football_data_foundation.soccerdata_sources.fbref import (
    FBrefConnector,
)
from bet.enrichment.football_data_foundation.soccerdata_sources.fivethirtyeight import (
    FiveThirtyEightConnector,
)
from bet.enrichment.football_data_foundation.soccerdata_sources.matchhistory import (
    MatchHistoryConnector,
)
from bet.enrichment.football_data_foundation.soccerdata_sources.sofascore import (
    SofascoreConnector,
)
from bet.enrichment.football_data_foundation.soccerdata_sources.sofifa import (
    SoFIFAConnector,
)
from bet.enrichment.football_data_foundation.soccerdata_sources.understat import (
    UnderstatConnector,
)
from bet.enrichment.football_data_foundation.soccerdata_sources.whoscored import (
    WhoScoredConnector,
)


def run_smoke(league: str, season: int, max_rows: int, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Starting Football Data Foundation smoke test for league: {league}, season: {season}")

    results = {}

    # 1. SoccerData Sources
    connectors = {
        "ClubElo": ClubEloConnector(),
        "ESPN": ESPNConnector(),
        "FBref": FBrefConnector(),
        "FiveThirtyEight": FiveThirtyEightConnector(),
        "MatchHistory": MatchHistoryConnector(),
        "Sofascore": SofascoreConnector(),
        "SoFIFA": SoFIFAConnector(),
        "Understat": UnderstatConnector(),
        "WhoScored": WhoScoredConnector(),
        "StatsBombOpenData": StatsBombOpenDataConnector(),
        "StatsBombPy": StatsBombPyBridge(),
        "KaggleEuropeanSoccer": KaggleEuropeanSoccerConnector(),
        "FootballDataOrg": FootballDataOrgBridge(),
        "OpenFootball": OpenFootballConnector(),
        "FotMobProbe": FotMobProbe(),
        "SofaScoreRichProbe": SofaScoreRichProbe(),
        "ScraperFCSofascore": ScraperFCSofascoreBridge(),
        "SoccerAction": SoccerActionBridge(),
        "Kloppy": KloppyBridge(),
        "Floodlight": FloodlightBridge(),
        "MplSoccer": MplSoccerBridge(),
    }

    for name, conn in connectors.items():
        print(f"  Running connector: {name} ... ", end="", flush=True)
        try:
            # Determine appropriate operation for the connector
            op = conn.supported_operations[0] if conn.supported_operations else "fetch"

            # Run execution (passing league, season, max_rows etc if supported)
            res = conn.execute(op, league=league, season=season, max_rows=max_rows)

            results[name] = {
                "status": str(res.status),
                "error_code": res.error_code,
                "row_count": len(res.value) if isinstance(res.value, list) else 0,
                "bundle_id": res.bundle_id or "NONE"
            }
            print(f"{res.status}")
        except Exception as e:
            results[name] = {
                "status": "CRASHED",
                "error": str(e)
            }
            print(f"CRASHED: {e}")

    # Write smoke test report
    report_path = output_dir / "smoke_report.json"
    report_data = {
        "timestamp": datetime.now(UTC).isoformat(),
        "parameters": {
            "league": league,
            "season": season,
            "max_rows": max_rows
        },
        "connectors": results
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
    print(f"Smoke test complete! Report written to: {report_path}")

def main() -> None:
    parser = argparse.ArgumentParser(description="Football Data Foundation CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    smoke_parser = subparsers.add_parser("smoke", help="Run live/smoke checks on connectors")
    smoke_parser.add_argument("--league", default="ENG-Premier League", help="League name")
    smoke_parser.add_argument("--season", type=int, default=2024, help="Season year")
    smoke_parser.add_argument("--max-rows", type=int, default=5, help="Max rows to return")
    smoke_parser.add_argument("--output-dir", default="reports/football_data_foundation", help="Output directory")

    args = parser.parse_args()
    if args.command == "smoke":
        run_smoke(args.league, args.season, args.max_rows, Path(args.output_dir))

if __name__ == "__main__":
    main()
