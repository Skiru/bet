from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from bet.enrichment.football_data_foundation.source_probe_contracts import (
    SourceProbeResult,
)


def run_probe(source_family: str) -> SourceProbeResult:
    import_status = "IMPORT_FAILED"
    dependency_status = "DEPENDENCY_MISSING"
    constructor_status = "NOT_IMPLEMENTED"
    declared_operations: list[str] = []
    declared_capabilities: list[str] = []
    offline_fixture_status = "OFFLINE_FIXTURE_MISSING"
    fixture_paths: list[str] = []
    diagnostics: dict[str, Any] = {}

    # Define metadata mapping for families
    mapping = {
        "espn_live_baseline": {
            "module": "bet.enrichment.football_data_foundation.active_enrichment",
            "class": "ActiveEnrichmentOrchestrator",  # generic or none
            "deps": [],
            "fixtures": [
                "tests/fixtures/football_data_foundation/espn_world_cup_usa_australia_scoreboard.json",
                "reports/football_data_foundation/live_validation/world-cup-2026/"
                "2026-06-20_2026-06-21_clean_final/event_enrichment_results.json"
            ],
            "ops": ["active_enrichment", "live_validation"],
            "caps": ["current_discovery", "current_recent_form", "detailed_metrics", "confirmed_lineups"]
        },
        "sportdb": {
            "module": "bet.api_clients.sportdb_mcp",
            "class": "SportDBMCPClient",  # illustrative
            "deps": [],
            "fixtures": [],
            "ops": ["detailed_metrics"],
            "caps": ["detailed_metrics"]
        },
        "football-data.org": {
            "module": "bet.enrichment.football_data_foundation.open_reference_sources.football_data_org_bridge",
            "class": "FootballDataOrgBridge",
            "deps": [],
            "fixtures": [],
            "ops": ["get_fixtures_result"],
            "caps": ["current_discovery"]
        },
        "soccerdata_clubelo": {
            "module": "bet.enrichment.football_data_foundation.soccerdata_sources.clubelo",
            "class": "ClubEloConnector",
            "deps": ["soccerdata"],
            "fixtures": [],
            "ops": ["read_by_date", "read_team_history"],
            "caps": ["current_recent_form"]
        },
        "soccerdata_espn": {
            "module": "bet.enrichment.football_data_foundation.soccerdata_sources.espn",
            "class": "ESPNConnector",
            "deps": ["soccerdata"],
            "fixtures": [],
            "ops": ["read_schedule", "read_matchsheet", "read_lineup"],
            "caps": ["current_discovery", "fixture_team_statistics", "confirmed_lineups"]
        },
        "soccerdata_fbref": {
            "module": "bet.enrichment.football_data_foundation.soccerdata_sources.fbref",
            "class": "FBrefConnector",
            "deps": ["soccerdata"],
            "fixtures": [],
            "ops": [
                "read_leagues", "read_seasons", "read_schedule",
                "read_team_season_stats", "read_team_match_stats",
                "read_player_season_stats", "read_player_match_stats",
                "read_lineup", "read_events"
            ],
            "caps": ["standings_competition_context", "current_discovery", "fixture_team_statistics", "confirmed_lineups"]
        },
        "soccerdata_understat": {
            "module": "bet.enrichment.football_data_foundation.soccerdata_sources.understat",
            "class": "UnderstatConnector",
            "deps": ["soccerdata"],
            "fixtures": [],
            "ops": [
                "read_leagues", "read_seasons", "read_schedule",
                "read_team_match_stats", "read_player_season_stats",
                "read_player_match_stats", "read_shot_events"
            ],
            "caps": ["current_discovery", "fixture_team_statistics", "current_recent_form"]
        },
        "soccerdata_whoscored": {
            "module": "bet.enrichment.football_data_foundation.soccerdata_sources.whoscored",
            "class": "WhoScoredConnector",
            "deps": ["soccerdata"],
            "fixtures": [],
            "ops": ["read_schedule", "read_missing_players", "read_events"],
            "caps": ["current_discovery", "injuries_suspensions", "fixture_team_statistics"]
        },
        "soccerdata_sofascore": {
            "module": "bet.enrichment.football_data_foundation.soccerdata_sources.sofascore",
            "class": "SofascoreConnector",
            "deps": ["soccerdata"],
            "fixtures": [],
            "ops": ["read_leagues", "read_seasons", "read_league_table", "read_schedule"],
            "caps": ["current_discovery", "standings_competition_context"]
        },
        "soccerdata_sofifa": {
            "module": "bet.enrichment.football_data_foundation.soccerdata_sources.sofifa",
            "class": "SoFIFAConnector",
            "deps": ["soccerdata"],
            "fixtures": [],
            "ops": ["read_leagues", "read_versions", "read_teams", "read_players", "read_team_ratings", "read_player_ratings"],
            "caps": ["current_recent_form", "roster_availability"]
        },
        "soccerdata_matchhistory": {
            "module": "bet.enrichment.football_data_foundation.soccerdata_sources.matchhistory",
            "class": "MatchHistoryConnector",
            "deps": ["soccerdata"],
            "fixtures": [],
            "ops": ["read_games"],
            "caps": ["h2h_head_to_head"]
        },
        "soccerdata_fivethirtyeight": {
            "module": "bet.enrichment.football_data_foundation.soccerdata_sources.fivethirtyeight",
            "class": "FiveThirtyEightConnector",
            "deps": ["soccerdata"],
            "fixtures": [],
            "ops": [],
            "caps": []
        },
        "statsbomb_open_data": {
            "module": "bet.enrichment.football_data_foundation.open_reference_sources.statsbomb_open_data",
            "class": "StatsBombOpenDataConnector",
            "deps": [],
            "fixtures": [
                "tests/fixtures/football_data_foundation/statsbomb_open_data/competitions.json",
                "tests/fixtures/football_data_foundation/statsbomb_open_data/matches/43/3.json",
                "tests/fixtures/football_data_foundation/statsbomb_open_data/events/1001.json",
                "tests/fixtures/football_data_foundation/statsbomb_open_data/lineups/1001.json",
                "tests/fixtures/football_data_foundation/statsbomb_open_data/three-sixty/1001.json"
            ],
            "ops": ["read_competitions", "read_matches", "read_events", "read_lineups", "read_360"],
            "caps": ["canonical_event_team_identity", "current_discovery", "fixture_team_statistics", "confirmed_lineups"]
        },
        "statsbombpy": {
            "module": "bet.enrichment.football_data_foundation.open_reference_sources.statsbombpy_bridge",
            "class": "StatsBombPyBridge",
            "deps": ["statsbombpy"],
            "fixtures": [],
            "ops": ["competitions"],
            "caps": ["canonical_event_team_identity"]
        },
        "kaggle_european_soccer": {
            "module": "bet.enrichment.football_data_foundation.open_reference_sources.kaggle_european_soccer",
            "class": "KaggleEuropeanSoccerConnector",
            "deps": ["sqlite3"],
            "fixtures": [
                "tests/fixtures/football_data_foundation/kaggle_european_soccer/matches.csv"
            ],
            "ops": ["read_matches"],
            "caps": ["h2h_head_to_head"]
        },
        "openfootball": {
            "module": "bet.enrichment.football_data_foundation.open_reference_sources.openfootball",
            "class": "OpenFootballConnector",
            "deps": [],
            "fixtures": [
                "tests/fixtures/football_data_foundation/openfootball/world_cup_2022.json"
            ],
            "ops": ["read_matches"],
            "caps": ["current_recent_form"]
        },
        "fotmob_probe": {
            "module": "bet.enrichment.football_data_foundation.rich_unofficial_sources.fotmob_probe",
            "class": "FotMobProbe",
            "deps": [],
            "fixtures": [
                "tests/fixtures/football_data_foundation/rich_probes/fotmob_matches.json"
            ],
            "ops": ["probe_matches"],
            "caps": ["current_discovery"]
        },
        "sofascore_rich_probe": {
            "module": "bet.enrichment.football_data_foundation.rich_unofficial_sources.sofascore_rich_probe",
            "class": "SofaScoreRichProbe",
            "deps": [],
            "fixtures": [
                "tests/fixtures/football_data_foundation/rich_probes/sofascore_stats.json"
            ],
            "ops": ["probe_stats"],
            "caps": ["fixture_team_statistics"]
        },
        "scraperfc_sofascore": {
            "module": "bet.enrichment.football_data_foundation.rich_unofficial_sources.scraperfc_sofascore_bridge",
            "class": "ScraperFCSofascoreBridge",
            "deps": ["ScraperFC"],
            "fixtures": [],
            "ops": ["read_match_stats"],
            "caps": ["fixture_team_statistics"]
        },
        "socceraction": {
            "module": "bet.enrichment.football_data_foundation.event_model_bridges.socceraction_bridge",
            "class": "SoccerActionBridge",
            "deps": ["socceraction"],
            "fixtures": [],
            "ops": ["convert_events"],
            "caps": ["fixture_team_statistics"]
        },
        "kloppy": {
            "module": "bet.enrichment.football_data_foundation.event_model_bridges.kloppy_bridge",
            "class": "KloppyBridge",
            "deps": ["kloppy"],
            "fixtures": [],
            "ops": ["load_tracking_data"],
            "caps": ["fixture_team_statistics"]
        },
        "floodlight": {
            "module": "bet.enrichment.football_data_foundation.event_model_bridges.floodlight_bridge",
            "class": "FloodlightBridge",
            "deps": ["floodlight"],
            "fixtures": [],
            "ops": ["load_events"],
            "caps": ["fixture_team_statistics"]
        },
        "mplsoccer": {
            "module": "bet.enrichment.football_data_foundation.event_model_bridges.mplsoccer_bridge",
            "class": "MplSoccerBridge",
            "deps": ["mplsoccer"],
            "fixtures": [],
            "ops": ["draw_pitch"],
            "caps": ["fixture_team_statistics"]
        }
    }

    meta = mapping.get(source_family)
    if not meta:
        return SourceProbeResult(
            source_family=source_family,
            import_status="IMPORT_FAILED",
            dependency_status="DEPENDENCY_MISSING",
            constructor_status="NOT_IMPLEMENTED",
            offline_fixture_status="OFFLINE_FIXTURE_MISSING"
        )

    # 1. Module import check
    module_name = meta["module"]
    try:
        mod = importlib.import_module(module_name)
        import_status = "IMPORT_OK"
        diagnostics["module_imported"] = True
    except Exception as exc:
        import_status = "IMPORT_FAILED"
        diagnostics["import_error"] = str(exc)
        # If the local module fails to import, we stop
        return SourceProbeResult(
            source_family=source_family,
            import_status=import_status,
            dependency_status="DEPENDENCY_MISSING",
            constructor_status="CONSTRUCTOR_FAILED",
            offline_fixture_status="OFFLINE_FIXTURE_MISSING",
            diagnostics=diagnostics
        )

    # 2. Dependency import check
    deps = meta.get("deps", [])
    deps_ok = True
    missing_deps = []
    for dep in deps:
        try:
            importlib.import_module(dep)
        except Exception as exc:
            deps_ok = False
            missing_deps.append(dep)
            diagnostics[f"dependency_error_{dep}"] = str(exc)

    if deps_ok:
        dependency_status = "IMPORT_OK"
    else:
        dependency_status = "DEPENDENCY_MISSING"
        diagnostics["missing_dependencies"] = missing_deps

    # 3. Constructor / init check (safe offline)
    class_name = meta.get("class")
    if class_name and import_status == "IMPORT_OK":
        cls = getattr(mod, class_name, None)
        if cls:
            declared_operations = list(meta.get("ops", []))
            declared_capabilities = list(meta.get("caps", []))

            # FiveThirtyEightConnector inherits but has no operations because FiveThirtyEight class is not in soccerdata
            if source_family == "soccerdata_fivethirtyeight":
                constructor_status = "CONSTRUCTOR_FAILED"
                diagnostics["constructor_error"] = "FiveThirtyEight not supported in soccerdata build."
            elif source_family.startswith("soccerdata_") and source_family != "soccerdata_fivethirtyeight":
                # soccerdata classes try to create cache directories and scrape web on instantiation.
                # It is UNSAFE to probe online constructor. We mark them as UNSAFE_TO_PROBE.
                # However, if soccerdata package is missing, we mark CONSTRUCTOR_FAILED.
                if dependency_status == "IMPORT_OK":
                    constructor_status = "UNSAFE_TO_PROBE"
                else:
                    constructor_status = "CONSTRUCTOR_FAILED"
            elif source_family == "sportdb" or source_family == "football-data.org":
                # These API clients require credentials or network to initiate, unsafe/unsupported without mocks.
                constructor_status = "UNSAFE_TO_PROBE"
            else:
                try:
                    # Instantiate safely
                    instance = cls()
                    constructor_status = "CONSTRUCTOR_OK"
                    # Discover operations from instance
                    if hasattr(instance, "supported_operations"):
                        declared_operations = list(instance.supported_operations)
                    if hasattr(instance, "supported_capabilities"):
                        declared_capabilities = list(instance.supported_capabilities)
                except Exception as exc:
                    if dependency_status == "IMPORT_OK":
                        constructor_status = "CONSTRUCTOR_FAILED"
                        diagnostics["constructor_error"] = str(exc)
                    else:
                        constructor_status = "CONSTRUCTOR_FAILED"
                        diagnostics["constructor_error"] = f"Dependency missing: {str(exc)}"
        else:
            constructor_status = "CONSTRUCTOR_FAILED"
            diagnostics["constructor_error"] = f"Class {class_name} not found in module {module_name}"
    else:
        constructor_status = "NOT_IMPLEMENTED"

    # 4. Safe offline fixture availability check
    expected_fixtures = meta.get("fixtures", [])
    if expected_fixtures:
        all_found = True
        found_paths = []
        for f in expected_fixtures:
            p = Path(f)
            if p.exists():
                found_paths.append(str(p))
            else:
                all_found = False

        if all_found:
            offline_fixture_status = "OFFLINE_FIXTURE_AVAILABLE"
            fixture_paths = found_paths
        else:
            offline_fixture_status = "OFFLINE_FIXTURE_MISSING"
    else:
        offline_fixture_status = "OFFLINE_FIXTURE_MISSING"

    return SourceProbeResult(
        source_family=source_family,
        import_status=import_status,
        dependency_status=dependency_status,
        constructor_status=constructor_status,
        declared_operations=declared_operations,
        declared_capabilities=declared_capabilities,
        offline_fixture_status=offline_fixture_status,
        fixture_paths=fixture_paths,
        diagnostics=diagnostics
    )


if __name__ == "__main__":
    import json
    from dataclasses import asdict

    FAMILIES = [
        "espn_live_baseline",
        "sportdb",
        "football-data.org",
        "soccerdata_clubelo",
        "soccerdata_espn",
        "soccerdata_fbref",
        "soccerdata_understat",
        "soccerdata_whoscored",
        "soccerdata_sofascore",
        "soccerdata_sofifa",
        "soccerdata_matchhistory",
        "soccerdata_fivethirtyeight",
        "statsbomb_open_data",
        "statsbombpy",
        "kaggle_european_soccer",
        "openfootball",
        "fotmob_probe",
        "sofascore_rich_probe",
        "scraperfc_sofascore",
        "socceraction",
        "kloppy",
        "floodlight",
        "mplsoccer"
    ]

    results = []
    for fam in FAMILIES:
        res = run_probe(fam)
        results.append(asdict(res))

    out_dir = Path("reports/football_data_foundation/source_admission_benchmark")
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "02_import_dependency_probe.json"
    json_path.write_text(json.dumps({"schema_version": "2.0", "probes": results}, indent=2) + "\n", encoding="utf-8")

    # Generate Markdown Table
    desc = (
        "This report aggregates import safety, external package dependency "
        "statuses, constructor testability, and offline fixture "
        "availability for all 23 source families."
    )
    md_lines = [
        "# Football Data Foundation - Import and Dependency Probe",
        "",
        desc,
        "",
        "| Source Family | Import Status | Dependency Status | Constructor Status | Offline Fixture Status |",
        "| :--- | :--- | :--- | :--- | :--- |"
    ]
    for r in results:
        fam_name = r['source_family']
        imp_s = r['import_status']
        dep_s = r['dependency_status']
        con_s = r['constructor_status']
        off_s = r['offline_fixture_status']
        md_lines.append(
            f"| **{fam_name}** | {imp_s} | {dep_s} | {con_s} | {off_s} |"
        )
    md_lines.append("")

    md_path = out_dir / "02_import_dependency_probe.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    print("Probes run successfully and reports written.")

