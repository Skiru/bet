from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import os
from typing import Any, Mapping

from bet.discovery.coordinator import EventDiscoveryCoordinator
from bet.enrichment.multisport_foundation.provider_authorization import build_authorization_report
from bet.enrichment.multisport_foundation.provider_mapping import build_provider_mapping_plan

EXPECTED_SPORTS: tuple[str, ...] = (
    "football",
    "volleyball",
    "basketball",
    "tennis",
    "hockey",
    "cs2",
    "dota2",
    "valorant",
)

_FOOTBALL_ROUTING = Path(__file__).resolve().parents[3] / "config" / "football_routing.yaml"
_FOOTBALL_CAPABILITY_MATRIX = Path(__file__).resolve().parents[3] / "config" / "provider_capability_matrix.json"


def _has_lines(event: Mapping[str, Any]) -> bool:
    for market in list(event.get("odds_markets", []) or []) + list(event.get("safety_markets", []) or []):
        if not isinstance(market, Mapping):
            continue
        if market.get("point") not in (None, ""):
            return True
        if market.get("line") not in (None, ""):
            return True
    return False


def _sport_events(events: list[dict[str, Any]], sport: str) -> list[dict[str, Any]]:
    return [event for event in events if str(event.get("sport") or "") == sport]


def build_expected_sport_contract(env: Mapping[str, str] | None = None) -> dict[str, dict[str, Any]]:
    env_map = dict(os.environ if env is None else env)
    discovery_sources = EventDiscoveryCoordinator._default_sources()

    mapping_plan = build_provider_mapping_plan(env_map)
    mapping_by_sport = mapping_plan.get("provider_mapping_by_sport", {})
    authorization_report = build_authorization_report(env_map)
    authorization_by_sport = authorization_report.get("provider_access_by_sport", {})

    contract: dict[str, dict[str, Any]] = {}
    for sport in EXPECTED_SPORTS:
        supported_sources = [source for source in discovery_sources if sport in source.supported_sports]
        provider_names = [source.name for source in supported_sources]
        provider_configured = any(source.is_available() for source in supported_sources)
        discovery_implemented = bool(provider_names)

        enrichment_mapping = list(mapping_by_sport.get(sport, []) or [])
        enrichment_access = list(authorization_by_sport.get(sport, []) or [])
        enrichment_implemented = sport == "football" or bool(enrichment_mapping)
        if sport == "football":
            enrichment_ready = _FOOTBALL_ROUTING.exists() and _FOOTBALL_CAPABILITY_MATRIX.exists()
            enrichment_blocker = "" if enrichment_ready else "football enrichment routing files missing"
        elif enrichment_mapping:
            mapping_statuses = {item.get("status", "") for item in enrichment_mapping}
            auth_statuses = {item.get("status", "") for item in enrichment_access}
            enrichment_ready = False
            enrichment_blocker = ", ".join(sorted((mapping_statuses | auth_statuses) - {""}))
        else:
            enrichment_ready = False
            enrichment_blocker = "no multisport enrichment route declared"

        if not discovery_implemented:
            status = "NOT_IMPLEMENTED"
        elif not provider_configured:
            status = "CONFIG_MISSING"
        elif enrichment_ready:
            status = "IMPLEMENTED"
        else:
            status = "PARTIAL"

        contract[sport] = {
            "sport": sport,
            "discovery_implemented": discovery_implemented,
            "provider_names": provider_names,
            "provider_configured": provider_configured,
            "can_produce_events": discovery_implemented and provider_configured,
            "can_produce_odds_markets_lines": discovery_implemented and provider_configured,
            "can_produce_enrichment_needed_for_s7": enrichment_ready,
            "enrichment_implemented": enrichment_implemented,
            "enrichment_blocker": enrichment_blocker,
            "status": status,
        }
    return contract


def build_sport_coverage_matrix(
    discovery_artifact: Mapping[str, Any],
    market_matrix: Mapping[str, Any],
    contract: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    contract = contract or build_expected_sport_contract()
    requested_sports = list(discovery_artifact.get("requested_sports") or EXPECTED_SPORTS)
    raw_by_sport = dict(discovery_artifact.get("raw_by_sport") or {})
    merged_by_sport = dict(discovery_artifact.get("by_sport") or {})
    provider_counts = dict(discovery_artifact.get("provider_counts_by_sport") or {})
    provider_errors = dict(discovery_artifact.get("provider_errors_by_sport") or {})
    matrix_events = list(market_matrix.get("events") or [])
    generation_stats = dict(market_matrix.get("generation_stats") or {})
    stale_by_sport = defaultdict(int)
    for bucket in ("already_played_filtered_by_sport", "date_mismatch_filtered_by_sport"):
        for sport, count in dict(generation_stats.get(bucket) or {}).items():
            stale_by_sport[sport] += int(count or 0)

    rows: dict[str, dict[str, Any]] = {}
    for sport in EXPECTED_SPORTS:
        sport_contract = dict(contract.get(sport) or {})
        sport_events = _sport_events(matrix_events, sport)
        events_with_competition = sum(1 for event in sport_events if event.get("competition"))
        events_with_participants = sum(1 for event in sport_events if event.get("home_team") and event.get("away_team"))
        events_with_markets = sum(1 for event in sport_events if event.get("odds_markets") or event.get("safety_markets"))
        events_with_odds = sum(1 for event in sport_events if event.get("odds_markets"))
        events_with_lines = sum(1 for event in sport_events if _has_lines(event))
        raw_discovery_count = int(raw_by_sport.get(sport, merged_by_sport.get(sport, 0)) or 0)
        future_or_live_count = len(sport_events)
        sport_provider_counts = dict(provider_counts.get(sport) or {})
        sport_provider_errors = list(provider_errors.get(sport) or [])

        blocker_reason = ""
        if not sport_contract.get("discovery_implemented"):
            coverage_status = "NOT_IMPLEMENTED"
            blocker_reason = "no discovery adapter declared"
        elif not sport_contract.get("provider_configured"):
            coverage_status = "CONFIG_MISSING"
            blocker_reason = "no configured discovery provider"
        elif raw_discovery_count <= 0:
            coverage_status = "PROVIDER_UNAVAILABLE" if sport_provider_errors or sport_contract.get("provider_names") else "UNKNOWN"
            blocker_reason = "discovery returned zero fixtures"
        elif future_or_live_count <= 0:
            coverage_status = "PROVIDER_UNAVAILABLE"
            blocker_reason = "all discovered fixtures were filtered before market matrix"
        elif events_with_markets <= 0 or events_with_odds <= 0:
            coverage_status = "NO_MARKETS_OR_ODDS"
            blocker_reason = "no odds/market data reached market matrix"
        elif not sport_contract.get("can_produce_enrichment_needed_for_s7"):
            coverage_status = "PARTIAL"
            blocker_reason = str(sport_contract.get("enrichment_blocker") or "S7 enrichment path not ready")
        else:
            coverage_status = "PASS"

        rows[sport] = {
            "sport": sport,
            "requested": sport in requested_sports,
            "raw_discovery_count": raw_discovery_count,
            "merged_discovery_count": int(merged_by_sport.get(sport, 0) or 0),
            "future_or_live_count": future_or_live_count,
            "stale_filtered_count": stale_by_sport.get(sport, 0),
            "events_with_competition": events_with_competition,
            "events_with_participants": events_with_participants,
            "events_with_markets": events_with_markets,
            "events_with_odds": events_with_odds,
            "events_with_lines": events_with_lines,
            "provider_counts": sport_provider_counts,
            "provider_errors": sport_provider_errors,
            "coverage_status": coverage_status,
            "blocker_reason": blocker_reason,
        }
    return rows


def build_tennis_wimbledon_audit(
    discovery_artifact: Mapping[str, Any],
    market_matrix: Mapping[str, Any],
    contract: Mapping[str, Mapping[str, Any]] | None = None,
    *,
    betting_day: str,
    command_run: str,
) -> dict[str, Any]:
    contract = contract or build_expected_sport_contract()
    coverage = build_sport_coverage_matrix(discovery_artifact, market_matrix, contract)
    tennis_contract = dict(contract.get("tennis") or {})
    discovery_events = [event for event in list(discovery_artifact.get("events") or []) if event.get("sport") == "tennis"]
    wimbledon_events = [
        event for event in discovery_events
        if "wimbledon" in str(event.get("competition") or "").lower()
    ]

    player_fields_present = sum(1 for event in wimbledon_events if event.get("home_team") and event.get("away_team"))
    tournament_present = sum(1 for event in wimbledon_events if event.get("competition"))
    round_present = sum(1 for event in wimbledon_events if event.get("round"))
    start_time_present = sum(1 for event in wimbledon_events if event.get("kickoff"))
    surface_present = sum(1 for event in wimbledon_events if event.get("surface"))
    sample_events = [
        {
            "player_a": event.get("home_team", ""),
            "player_b": event.get("away_team", ""),
            "tournament": event.get("competition", ""),
            "start_time": event.get("kickoff", ""),
            "source": event.get("source", ""),
        }
        for event in wimbledon_events[:5]
    ]

    tennis_row = coverage["tennis"]
    if not tennis_contract.get("discovery_implemented"):
        status = "NOT_IMPLEMENTED"
    elif not tennis_contract.get("provider_configured"):
        status = "CONFIG_MISSING"
    elif tennis_row["raw_discovery_count"] <= 0 or (betting_day == "2026-06-29" and not wimbledon_events):
        status = "PROVIDER_EMPTY_OR_UNAVAILABLE"
    elif player_fields_present != len(wimbledon_events) or tournament_present != len(wimbledon_events) or start_time_present != len(wimbledon_events):
        status = "PARSER_BUG"
    elif tennis_row["events_with_markets"] <= 0 or tennis_row["events_with_odds"] <= 0:
        status = "NO_MARKETS_OR_ODDS"
    else:
        status = "PASS"

    provider_used = sorted(
        provider
        for provider, count in tennis_row["provider_counts"].items()
        if int(count or 0) > 0
    )

    return {
        "tennis_adapter_path": "src/bet/discovery/sources/odds_api_io.py",
        "provider_used": provider_used,
        "command_run": command_run,
        "raw_tennis_event_count": tennis_row["raw_discovery_count"],
        "wimbledon_event_count": len(wimbledon_events),
        "sample_wimbledon_events": sample_events,
        "player_a_player_b_present_count": player_fields_present,
        "tournament_present_count": tournament_present,
        "round_present_count": round_present,
        "start_time_present_count": start_time_present,
        "surface_present_count": surface_present,
        "provider_errors": tennis_row["provider_errors"],
        "config_missing": not tennis_contract.get("provider_configured"),
        "parser_errors": status == "PARSER_BUG",
        "tennis_coverage_status": status,
    }


def render_expected_sport_contract_markdown(contract: Mapping[str, Mapping[str, Any]]) -> str:
    lines = ["# Expected Sport Contract", ""]
    for sport in EXPECTED_SPORTS:
        row = dict(contract[sport])
        lines.extend(
            [
                f"## {sport}",
                f"- discovery_adapter_implemented: `{row['discovery_implemented']}`",
                f"- provider_names: `{row['provider_names']}`",
                f"- provider_configured: `{row['provider_configured']}`",
                f"- can_produce_events: `{row['can_produce_events']}`",
                f"- can_produce_odds_markets_lines: `{row['can_produce_odds_markets_lines']}`",
                f"- can_produce_enrichment_needed_for_s7: `{row['can_produce_enrichment_needed_for_s7']}`",
                f"- status: `{row['status']}`",
            ]
        )
        if row.get("enrichment_blocker"):
            lines.append(f"- enrichment_blocker: `{row['enrichment_blocker']}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_sport_coverage_matrix_markdown(matrix: Mapping[str, Mapping[str, Any]]) -> str:
    lines = [
        "# Live Session Sport Provider Coverage Matrix",
        "",
        "| sport | raw_discovery | merged_discovery | future_or_live | stale_filtered | competition | participants | markets | odds | lines | status | blocker |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for sport in EXPECTED_SPORTS:
        row = dict(matrix[sport])
        lines.append(
            "| {sport} | {raw} | {merged} | {future} | {stale} | {competition} | {participants} | {markets} | {odds} | {lines_count} | {status} | {blocker} |".format(
                sport=sport,
                raw=row["raw_discovery_count"],
                merged=row["merged_discovery_count"],
                future=row["future_or_live_count"],
                stale=row["stale_filtered_count"],
                competition=row["events_with_competition"],
                participants=row["events_with_participants"],
                markets=row["events_with_markets"],
                odds=row["events_with_odds"],
                lines_count=row["events_with_lines"],
                status=row["coverage_status"],
                blocker=(row["blocker_reason"] or "-").replace("|", "/"),
            )
        )
    lines.append("")
    for sport in EXPECTED_SPORTS:
        row = dict(matrix[sport])
        lines.append(f"## {sport}")
        lines.append(f"- provider_counts: `{row['provider_counts']}`")
        lines.append(f"- provider_errors: `{row['provider_errors']}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_tennis_wimbledon_audit_markdown(audit: Mapping[str, Any], *, as_of: str) -> str:
    lines = [
        "# Tennis Wimbledon Discovery Audit",
        "",
        f"- as_of: `{as_of}`",
        f"- tennis_adapter_path: `{audit['tennis_adapter_path']}`",
        f"- provider_used: `{audit['provider_used']}`",
        f"- command_run: `{audit['command_run']}`",
        f"- raw_tennis_event_count: `{audit['raw_tennis_event_count']}`",
        f"- wimbledon_event_count: `{audit['wimbledon_event_count']}`",
        f"- player_a_player_b_present_count: `{audit['player_a_player_b_present_count']}`",
        f"- tournament_present_count: `{audit['tournament_present_count']}`",
        f"- round_present_count: `{audit['round_present_count']}`",
        f"- start_time_present_count: `{audit['start_time_present_count']}`",
        f"- surface_present_count: `{audit['surface_present_count']}`",
        f"- provider_errors: `{audit['provider_errors']}`",
        f"- config_missing: `{audit['config_missing']}`",
        f"- parser_errors: `{audit['parser_errors']}`",
        f"- TENNIS_COVERAGE_STATUS: `{audit['tennis_coverage_status']}`",
        "",
        "## Sample Wimbledon Events",
    ]
    samples = list(audit.get("sample_wimbledon_events") or [])
    if not samples:
        lines.append("- none")
    else:
        for sample in samples:
            lines.append(
                f"- {sample['player_a']} vs {sample['player_b']} | {sample['tournament']} | {sample['start_time']} | source={sample['source']}"
            )
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"
