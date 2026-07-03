"""Sport-specific market family mappers and promotion validators for multi-sport support.

Provides normalization, line semantics validation, name resolution, and promotion gating
for tennis, basketball, volleyball, esports, hockey, and football.
"""
from __future__ import annotations

import json
from typing import Any, Mapping


def normalize_selection_name(selection: str, event: Mapping[str, Any]) -> str:
    """Normalizes generic home/away/draw labels to canonical team or player names."""
    sel = str(selection or "").strip().lower()
    home = str(event.get("home_team") or event.get("canonical_event_name") or "Home").split(" vs ")[0].strip()
    away = str(event.get("away_team") or event.get("canonical_event_name") or "Away").split(" vs ")[-1].strip()

    if sel in {"home", "1", "player1", "player_1"}:
        return home
    if sel in {"away", "2", "player2", "player_2"}:
        return away
    if sel in {"draw", "x"}:
        return "Draw"
    if sel in {"over", "under"}:
        return selection.strip().title()
    return str(selection or "Unknown")


def map_multisport_market(sport: str, row: Mapping[str, Any], event: Mapping[str, Any]) -> dict[str, Any] | None:
    """Maps a raw provider row to a structured multisport promotion schema."""
    sport_lower = str(sport or event.get("sport") or "").lower()
    prov_key = str(row.get("provider_market_key") or row.get("market_type") or "unknown").lower()
    raw_family = str(row.get("market_family") or row.get("market") or "").lower()
    
    # Extract line and selection
    line = row.get("line")
    selection = str(row.get("selection") or row.get("outcome_name") or "")
    normalized_sel = normalize_selection_name(selection, event)
    row_id = str(row.get("row_id") or row.get("market_row_id") or "unknown_row")

    # Outputs to populate
    market_family = ""
    human_name = ""
    line_semantics = "LINE_FREE"
    line_required = False
    line_free_type = None
    allowed_line_alternatives = []
    blocker = None

    if sport_lower == "football":
        # Preserve football mapping
        if "double_chance" in prov_key or "double chance" in raw_family:
            market_family = "double_chance"
            human_name = f"Double chance - {normalized_sel}"
            line_free_type = "DOUBLE_CHANCE"
        elif "draw_no_bet" in prov_key or "draw no bet" in raw_family:
            market_family = "result"
            human_name = f"Draw No Bet - {normalized_sel}"
            line_free_type = "DRAW_NO_BET"
        elif prov_key in {"h2h", "result", "moneyline", "winner"}:
            market_family = "result"
            human_name = f"Match result - {normalized_sel}"
            line_free_type = "MATCH_RESULT"
        elif "goals" in prov_key or "goals" in raw_family:
            if "team" in prov_key or "team" in raw_family:
                market_family = "team_goals"
            else:
                market_family = "goals_totals"
            line_required = True
            line_semantics = "NUMERIC_LINE_REQUIRED"
        elif "corners" in prov_key or "corners" in raw_family:
            market_family = "corners"
            line_required = True
            line_semantics = "NUMERIC_LINE_REQUIRED"
        elif "cards" in prov_key or "cards" in raw_family:
            market_family = "cards"
            line_required = True
            line_semantics = "NUMERIC_LINE_REQUIRED"
        elif "shots" in prov_key or "shots" in raw_family:
            market_family = "shots"
            line_required = True
            line_semantics = "NUMERIC_LINE_REQUIRED"
        else:
            market_family = "unknown"
            blocker = "MARKET_FAMILY_MAPPER_MISSING"

    elif sport_lower == "tennis":
        # Tennis mapping: h2h / moneyline -> match winner
        if prov_key in {"h2h", "moneyline", "winner", "match_winner", "ml", "ml_1st_set"}:
            market_family = "result"
            human_name = f"Match winner - {normalized_sel}"
            line_free_type = "MATCH_WINNER"
            line_semantics = "LINE_FREE"
        elif "spread" in prov_key or "handicap" in prov_key:
            market_family = "game_handicap"
            line_required = True
            line_semantics = "NUMERIC_LINE_REQUIRED"
        elif "totals" in prov_key or "total" in prov_key:
            market_family = "total_games"
            line_required = True
            line_semantics = "NUMERIC_LINE_REQUIRED"
        else:
            market_family = "unknown"
            blocker = "MARKET_FAMILY_MAPPER_MISSING"

    elif sport_lower == "basketball":
        # Basketball mapping: h2h -> moneyline, spreads -> spread, totals -> total points
        if prov_key in {"h2h", "moneyline", "winner", "ml", "ml_ht", "ml_q1"}:
            market_family = "result"
            human_name = f"Moneyline - {normalized_sel}"
            line_free_type = "MONEYLINE"
            line_semantics = "LINE_FREE"
        elif "spread" in prov_key or "handicap" in prov_key:
            market_family = "spread"
            line_required = True
            line_semantics = "NUMERIC_LINE_REQUIRED"
        elif "team_total" in prov_key or "team_totals" in prov_key or "team_total_home" in prov_key or "team_total_away" in prov_key:
            market_family = "team_totals"
            line_required = True
            line_semantics = "NUMERIC_LINE_REQUIRED"
        elif "totals" in prov_key or "total" in prov_key:
            market_family = "totals"
            line_required = True
            line_semantics = "NUMERIC_LINE_REQUIRED"
        else:
            market_family = "unknown"
            blocker = "MARKET_FAMILY_MAPPER_MISSING"

    elif sport_lower == "volleyball":
        # Volleyball mapping: h2h -> match winner
        if prov_key in {"h2h", "moneyline", "winner", "ml"}:
            market_family = "result"
            human_name = f"Match winner - {normalized_sel}"
            line_free_type = "MATCH_WINNER"
            line_semantics = "LINE_FREE"
        elif "spread" in prov_key or "handicap" in prov_key:
            market_family = "set_handicap"
            line_required = True
            line_semantics = "NUMERIC_LINE_REQUIRED"
        elif "totals" in prov_key or "total" in prov_key:
            market_family = "total_points"
            line_required = True
            line_semantics = "NUMERIC_LINE_REQUIRED"
        else:
            market_family = "unknown"
            blocker = "MARKET_FAMILY_MAPPER_MISSING"

    elif sport_lower == "hockey":
        # Hockey mapping: h2h -> moneyline, spreads -> puck line / handicap, totals -> total goals
        if prov_key in {"h2h", "moneyline", "winner", "ml", "3-way"}:
            market_family = "result"
            human_name = f"Moneyline - {normalized_sel}"
            line_free_type = "MONEYLINE"
            line_semantics = "LINE_FREE"
        elif "spread" in prov_key or "handicap" in prov_key:
            market_family = "handicap"
            line_required = True
            line_semantics = "NUMERIC_LINE_REQUIRED"
        elif "totals" in prov_key or "total" in prov_key:
            market_family = "total_goals"
            line_required = True
            line_semantics = "NUMERIC_LINE_REQUIRED"
        else:
            market_family = "unknown"
            blocker = "MARKET_FAMILY_MAPPER_MISSING"

    elif sport_lower in {"cs2", "valorant", "dota2", "esports"}:
        # Esports mapping: h2h -> match winner
        if prov_key in {"h2h", "moneyline", "winner", "ml", "1st_map_moneyline", "2nd_map_moneyline"}:
            market_family = "result"
            human_name = f"Match winner - {normalized_sel}"
            line_free_type = "MATCH_WINNER"
            line_semantics = "LINE_FREE"
        elif "spread" in prov_key or "handicap" in prov_key:
            market_family = "map_handicap"
            line_required = True
            line_semantics = "NUMERIC_LINE_REQUIRED"
        elif "totals" in prov_key or "total" in prov_key:
            market_family = "total_maps"
            line_required = True
            line_semantics = "NUMERIC_LINE_REQUIRED"
        else:
            market_family = "unknown"
            blocker = "MARKET_FAMILY_MAPPER_MISSING"

    else:
        # Default fallback
        if prov_key in {"h2h", "moneyline", "winner", "ml"}:
            market_family = "result"
            human_name = f"Match winner - {normalized_sel}"
            line_free_type = "MATCH_WINNER"
            line_semantics = "LINE_FREE"
        else:
            market_family = "unknown"
            blocker = "SPORT_PROMOTER_NOT_IMPLEMENTED"

    # Line semantics validation
    if line_semantics == "NUMERIC_LINE_REQUIRED":
        if line is None or str(line).strip().upper() in {"", "UNKNOWN", "NONE", "NULL", "N/A"}:
            blocker = "LINE_SEMANTICS_MISSING"
        else:
            names = {
                "goals_totals": "Total goals",
                "team_goals": "Team goals",
                "total_games": "Total games",
                "game_handicap": "Game handicap",
                "spread": "Spread",
                "totals": "Total points",
                "team_totals": "Team total points",
                "set_handicap": "Set handicap",
                "total_points": "Total points",
                "map_handicap": "Map handicap",
                "total_maps": "Total maps",
                "corners": "Total corners",
                "cards": "Total cards",
                "shots": "Total shots",
                "handicap": "Handicap",
                "total_goals": "Total goals",
            }
            base_name = names.get(market_family, market_family.replace("_", " ").title())
            human_name = f"{base_name} - {normalized_sel} {line}"
            allowed_line_alternatives = [
                f"{base_name} - {normalized_sel} on the main operator line",
                f"{base_name} - {normalized_sel} on an alternative operator line"
            ]

    # Validate provider refs
    if not row_id or row_id.strip() == "":
        blocker = "PROVIDER_REF_MISSING"

    # Validate human name
    if not human_name or human_name.strip() == "":
        blocker = "HUMAN_MARKET_NAME_MISSING"

    return {
        "sport": sport_lower,
        "provider_market_key": prov_key,
        "market_family": market_family,
        "human_searchable_market_name": human_name,
        "line_semantics": line_semantics,
        "line_required": line_required,
        "line_free_market_type": line_free_type,
        "allowed_line_alternatives": allowed_line_alternatives,
        "provider_market_refs": [row_id],
        "promotion_blocker": blocker,
    }
