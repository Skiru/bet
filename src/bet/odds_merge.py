"""Deterministic odds merge helpers.

This fixes the common data-loss bug where a second source with the same
bookmaker key is discarded entirely. We merge bookmaker markets by canonical
market/outcome/point and preserve provenance.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Mapping

SOURCE_PRIORITY = ("oddspapi", "the-odds-api-betclic", "odds-api-io", "the-odds-api", "api-football-odds")
BOOKMAKER_PRIORITY = ("superbet", "superbet_pl", "superbet-pl", "betclic", "betclic_pl", "betclic_fr", "bet365", "pinnacle")


def normalise_token(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def canonical_market_key(raw: Any) -> str:
    key = normalise_token(raw)
    aliases = {
        "moneyline": "h2h",
        "match_winner": "h2h",
        "winner": "h2h",
        "1x2": "h2h",
        "h2h": "h2h",
        "over_under": "totals",
        "over/under": "totals",
        "total": "totals",
        "totals": "totals",
        "spread": "spreads",
        "handicap": "spreads",
        "spreads": "spreads",
    }
    return aliases.get(key, key)


def event_identity(event: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        _time_bucket(event.get("commence_time") or event.get("start_time") or event.get("date")),
        _team_key(event.get("home_team") or event.get("homeTeam") or event.get("home")),
        _team_key(event.get("away_team") or event.get("awayTeam") or event.get("away")),
    )


def _time_bucket(value: Any) -> str:
    raw = str(value or "")
    if not raw:
        return "unknown-time"
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
        return parsed.strftime("%Y-%m-%dT%H")
    except ValueError:
        return raw[:13]


def _team_key(value: Any) -> str:
    return "".join(char for char in str(value or "").lower() if char.isalnum())


def events_match(left: Mapping[str, Any], right: Mapping[str, Any], *, min_team_similarity: float = 0.80) -> bool:
    left_id = event_identity(left)
    right_id = event_identity(right)
    if left_id == right_id:
        return True
    if left_id[0] != "unknown-time" and right_id[0] != "unknown-time" and left_id[0] != right_id[0]:
        return False
    home_similarity = SequenceMatcher(None, left_id[1], right_id[1]).ratio()
    away_similarity = SequenceMatcher(None, left_id[2], right_id[2]).ratio()
    return home_similarity >= min_team_similarity and away_similarity >= min_team_similarity


def merge_event_odds(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    merged = deepcopy(dict(left))
    merged.setdefault("_source_provenance", [])
    for source in (left.get("_odds_source"), right.get("_odds_source")):
        if source and source not in merged["_source_provenance"]:
            merged["_source_provenance"].append(source)

    bookmaker_index: dict[str, dict[str, Any]] = {}
    merged_bookmakers: list[dict[str, Any]] = []
    for bookmaker in list(left.get("bookmakers", []) or []):
        bm = deepcopy(bookmaker)
        key = normalise_token(bm.get("key") or bm.get("title"))
        bm["key"] = key
        bm["markets"] = _normalise_markets(bm.get("markets", []) or [])
        bookmaker_index[key] = bm
        merged_bookmakers.append(bm)

    for bookmaker in list(right.get("bookmakers", []) or []):
        key = normalise_token(bookmaker.get("key") or bookmaker.get("title"))
        if key not in bookmaker_index:
            bm = deepcopy(bookmaker)
            bm["key"] = key
            bm["markets"] = _normalise_markets(bm.get("markets", []) or [])
            bookmaker_index[key] = bm
            merged_bookmakers.append(bm)
        else:
            bookmaker_index[key]["markets"] = merge_markets(bookmaker_index[key].get("markets", []), bookmaker.get("markets", []))

    merged["bookmakers"] = sorted(merged_bookmakers, key=lambda bm: _priority_key(normalise_token(bm.get("key")), BOOKMAKER_PRIORITY))
    return merged


def merge_markets(left: list[Mapping[str, Any]], right: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    market_index: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for market in list(left or []) + list(right or []):
        key = canonical_market_key(market.get("key") or market.get("name"))
        if not key:
            continue
        if key not in market_index:
            market_index[key] = {**deepcopy(dict(market)), "key": key, "outcomes": []}
            order.append(key)
        market_index[key]["outcomes"] = merge_outcomes(market_index[key].get("outcomes", []), market.get("outcomes", []))
    return [market_index[key] for key in order]


def merge_outcomes(left: list[Mapping[str, Any]], right: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    outcomes: dict[tuple[str, str], dict[str, Any]] = {}
    for outcome in list(left or []) + list(right or []):
        name = normalise_token(outcome.get("name") or outcome.get("label"))
        point = str(outcome.get("point", ""))
        if not name:
            continue
        # Last provider wins for the same exact bookmaker/market/outcome/point,
        # because scan order should be priority-ordered and newer providers can overwrite stale quotes.
        outcomes[(name, point)] = deepcopy(dict(outcome))
    return list(outcomes.values())


def _normalise_markets(markets: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return merge_markets([], markets)


def _priority_key(value: str, priority: tuple[str, ...]) -> tuple[int, str]:
    try:
        return (priority.index(value), value)
    except ValueError:
        return (len(priority), value)
