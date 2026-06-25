"""Pure parsers for brittle S2 tipster sources."""
from __future__ import annotations

import re
from typing import Any, Callable, Mapping, Sequence


DISCIPLINE_MAP = {
    "piłka nożna": "football",
    "tenis": "tennis",
    "koszykówka": "basketball",
    "siatkówka": "volleyball",
    "hokej": "hockey",
    "piłka ręczna": "handball",
    "baseball": "baseball",
    "mma": "mma",
    "esport": "esport",
    "boks": "boxing",
}


def strip_html_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", text).strip()


def extract_zawodtyper_bets_payload(body: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if not isinstance(body, Mapping) or not body.get("success"):
        return []
    data = body.get("data")
    if not isinstance(data, list) or not data:
        return []
    if not isinstance(data[0], Mapping):
        return []
    if "comment_id" not in data[0] or "match_name" not in data[0]:
        return []
    return [item for item in data if isinstance(item, Mapping)]


def parse_zawodtyper_xhr_bets(
    bets_data: Sequence[Mapping[str, Any]],
    *,
    now_iso: str,
    classify_market: Callable[[str, str], str],
    extract_direction: Callable[[str, str], str],
    extract_stats_cited: Callable[[str], list[str]],
    text_cleaner: Callable[[str], str] = strip_html_text,
) -> list[dict[str, Any]]:
    picks: list[dict[str, Any]] = []
    by_event_key: dict[str, dict[str, Any]] = {}

    for bet in bets_data:
        if bet.get("comment_type") != "bet":
            continue
        match_name = str(bet.get("match_name") or "").strip()
        if not match_name:
            continue

        parts = re.split(r"\s*[-–—]\s*", match_name, maxsplit=1)
        if len(parts) != 2:
            parts = re.split(r"\s+vs\.?\s+", match_name, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) != 2:
            continue

        home = parts[0].strip()
        away = parts[1].strip()
        if len(home) < 2 or len(away) < 2:
            continue

        event_key = f"{home.lower()}|{away.lower()}"
        content = text_cleaner(str(bet.get("content") or ""))
        author_stats = bet.get("author_stats") or {}
        bet_count = int(author_stats.get("bet_count", 0) or 0)
        ratio_raw = author_stats.get("ratio")
        ratio = float(ratio_raw) if ratio_raw else 0.0
        accuracy = int(ratio * 100) if ratio > 0 and bet_count >= 3 else None

        reasoning_parts: list[str] = []
        if accuracy and bet_count >= 3:
            reasoning_parts.append(f"Tipster {bet.get('author_name', '')}: {accuracy}% ({bet_count} bets)")
        if content and len(content) > 30:
            reasoning_parts.append(content)
        reasoning = " | ".join(reasoning_parts) if reasoning_parts else ""

        pick_type = str(bet.get("type") or "").strip()
        sport = DISCIPLINE_MAP.get(str(bet.get("discipline") or "").lower().strip(), "football")
        odds_raw = bet.get("rate")
        odds = float(odds_raw) if odds_raw is not None else None
        candidate = {
            "source_site": "ZawodTyper",
            "tipster_name": bet.get("author_name", "ZawodTyper"),
            "sport": sport,
            "event": f"{home} vs {away}",
            "home_team": home,
            "away_team": away,
            "competition": "",
            "market": pick_type or "N/A",
            "market_type": classify_market(pick_type, content),
            "direction": extract_direction(pick_type, content),
            "odds": odds,
            "reasoning": reasoning[:800],
            "accuracy_pct": accuracy,
            "confidence": "high" if accuracy and accuracy >= 65 and bet_count >= 10 else ("medium" if accuracy and accuracy >= 55 and bet_count >= 5 else "low"),
            "stats_cited": extract_stats_cited(content),
            "fetch_time": now_iso,
        }

        existing = by_event_key.get(event_key)
        if existing is None:
            by_event_key[event_key] = candidate
            continue

        if len(candidate.get("reasoning") or "") > len(existing.get("reasoning") or ""):
            by_event_key[event_key] = candidate
        elif (candidate.get("accuracy_pct") or 0) > (existing.get("accuracy_pct") or 0):
            by_event_key[event_key] = candidate

    picks.extend(by_event_key.values())
    return picks
