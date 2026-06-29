from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bet.pipeline.sport_coverage import (  # noqa: E402
    EXPECTED_SPORTS,
    build_sport_coverage_matrix,
    build_tennis_wimbledon_audit,
)


def _base_contract() -> dict[str, dict]:
    return {
        sport: {
            "sport": sport,
            "discovery_implemented": True,
            "provider_names": ["odds-api-io"],
            "provider_configured": True,
            "can_produce_events": True,
            "can_produce_odds_markets_lines": True,
            "can_produce_enrichment_needed_for_s7": True,
            "enrichment_implemented": True,
            "enrichment_blocker": "",
            "status": "IMPLEMENTED",
        }
        for sport in EXPECTED_SPORTS
    }


def _base_discovery() -> dict:
    return {
        "requested_sports": list(EXPECTED_SPORTS),
        "raw_by_sport": {"football": 2, "tennis": 2},
        "by_sport": {"football": 2, "tennis": 2},
        "provider_counts_by_sport": {
            "football": {"odds-api-io": 2},
            "tennis": {"odds-api-io": 2},
            "valorant": {"odds-api-io": 0},
        },
        "provider_errors_by_sport": {
            "football": [],
            "tennis": ["odds-api/tennis: auth failed (401)"],
            "valorant": ["odds-api-io/valorant: provider timeout"],
        },
        "events": [
            {
                "sport": "football",
                "competition": "Premier League",
                "home_team": "Team A",
                "away_team": "Team B",
                "kickoff": "2026-06-29T18:00:00+00:00",
                "source": "odds-api-io",
            },
            {
                "sport": "football",
                "competition": "Premier League",
                "home_team": "Team C",
                "away_team": "Team D",
                "kickoff": "2026-06-29T20:00:00+00:00",
                "source": "odds-api-io",
            },
            {
                "sport": "tennis",
                "competition": "ATP - Wimbledon, London, Great Britain",
                "home_team": "Rublev, Andrey",
                "away_team": "Safiullin, Roman",
                "kickoff": "2026-06-29T10:00:00+00:00",
                "source": "odds-api-io",
            },
            {
                "sport": "tennis",
                "competition": "WTA - Wimbledon, London, Great Britain",
                "home_team": "Player A",
                "away_team": "Player B",
                "kickoff": "2026-06-29T12:00:00+00:00",
                "source": "odds-api-io",
            },
        ],
    }


def _base_matrix() -> dict:
    return {
        "generation_stats": {
            "already_played_filtered_by_sport": {"hockey": 1},
            "date_mismatch_filtered_by_sport": {"basketball": 2},
        },
        "events": [
            {
                "sport": "football",
                "competition": "Premier League",
                "home_team": "Team A",
                "away_team": "Team B",
                "kickoff": "2026-06-29T18:00:00+00:00",
                "odds_markets": [{"market": "1X2", "source": "multi-source"}],
                "safety_markets": [],
            },
            {
                "sport": "tennis",
                "competition": "ATP - Wimbledon, London, Great Britain",
                "home_team": "Rublev, Andrey",
                "away_team": "Safiullin, Roman",
                "kickoff": "2026-06-29T10:00:00+00:00",
                "odds_markets": [{"market": "Match Winner", "source": "multi-source"}],
                "safety_markets": [{"market": "Total Games", "line": 22.5, "source": "stats_cache"}],
            },
            {
                "sport": "tennis",
                "competition": "WTA - Wimbledon, London, Great Britain",
                "home_team": "Player A",
                "away_team": "Player B",
                "kickoff": "2026-06-29T12:00:00+00:00",
                "odds_markets": [{"market": "Match Winner", "source": "multi-source"}],
                "safety_markets": [],
            },
        ],
    }


def test_sport_coverage_matrix_includes_all_expected_sports():
    matrix = build_sport_coverage_matrix(_base_discovery(), _base_matrix(), _base_contract())

    assert set(matrix) == set(EXPECTED_SPORTS)


def test_unsupported_sports_are_not_implemented_not_silently_absent():
    contract = _base_contract()
    contract["valorant"] = {
        **contract["valorant"],
        "discovery_implemented": False,
        "provider_names": [],
        "provider_configured": False,
        "can_produce_events": False,
        "can_produce_odds_markets_lines": False,
        "can_produce_enrichment_needed_for_s7": False,
        "status": "NOT_IMPLEMENTED",
    }

    matrix = build_sport_coverage_matrix(_base_discovery(), _base_matrix(), contract)

    assert matrix["valorant"]["coverage_status"] == "NOT_IMPLEMENTED"
    assert matrix["valorant"]["raw_discovery_count"] == 0


def test_tennis_coverage_status_is_explicit_pass_when_wimbledon_present():
    audit = build_tennis_wimbledon_audit(
        _base_discovery(),
        _base_matrix(),
        _base_contract(),
        betting_day="2026-06-29",
        command_run="discover_events --sports tennis",
    )

    assert audit["tennis_coverage_status"] == "PASS"
    assert audit["wimbledon_event_count"] == 2


def test_wimbledon_sanity_check_fails_closed_when_tennis_returns_zero():
    discovery = _base_discovery()
    discovery["raw_by_sport"]["tennis"] = 0
    discovery["by_sport"]["tennis"] = 0
    discovery["events"] = [event for event in discovery["events"] if event["sport"] != "tennis"]
    matrix = _base_matrix()
    matrix["events"] = [event for event in matrix["events"] if event["sport"] != "tennis"]

    audit = build_tennis_wimbledon_audit(
        discovery,
        matrix,
        _base_contract(),
        betting_day="2026-06-29",
        command_run="discover_events --sports tennis",
    )

    assert audit["tennis_coverage_status"] == "PROVIDER_EMPTY_OR_UNAVAILABLE"


def test_no_sport_with_zero_data_can_be_reported_pass():
    matrix = build_sport_coverage_matrix(_base_discovery(), _base_matrix(), _base_contract())

    assert matrix["hockey"]["raw_discovery_count"] == 0
    assert matrix["hockey"]["coverage_status"] != "PASS"


def test_provider_errors_are_preserved_in_matrix_and_tennis_audit():
    coverage = build_sport_coverage_matrix(_base_discovery(), _base_matrix(), _base_contract())
    audit = build_tennis_wimbledon_audit(
        _base_discovery(),
        _base_matrix(),
        _base_contract(),
        betting_day="2026-06-29",
        command_run="discover_events --sports tennis",
    )

    assert coverage["tennis"]["provider_errors"] == ["odds-api/tennis: auth failed (401)"]
    assert audit["provider_errors"] == ["odds-api/tennis: auth failed (401)"]


def test_no_markets_or_odds_status_is_explicit_for_tennis_when_matrix_is_empty():
    matrix = deepcopy(_base_matrix())
    for event in matrix["events"]:
        if event["sport"] == "tennis":
            event["odds_markets"] = []
            event["safety_markets"] = []

    audit = build_tennis_wimbledon_audit(
        _base_discovery(),
        matrix,
        _base_contract(),
        betting_day="2026-06-29",
        command_run="discover_events --sports tennis",
    )

    assert audit["tennis_coverage_status"] == "NO_MARKETS_OR_ODDS"
